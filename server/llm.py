"""Shared OpenAI client for every capability that interprets or drafts (PLATFORM_BUILD_PLAN.md 5.6).

Responses API with strict Structured Outputs and the Embeddings API. Every call records model, prompt
version, input hash, token usage and latency into run.metrics['llm']; identical requests are served
from the llm_cache table without a call; a per-run call cap bounds cost. Failures are explicit
(ProviderUnavailable, LLMOutputInvalid): nothing falls back to a deterministic method silently.

Never call the client inside a SQLite write transaction: the cache commits its own short transaction,
and a model call must not hold the write lock. BMW records may be sent only through this module.
Model output is untrusted data; cited evidence is grounded locally (ground_citations) before storage.
"""

import json
import math
import os
import re
import time
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ValidationError

from database.store import connect, encode, now, transaction
from server.analysis_engine import AnalysisError, ProviderUnavailable, _strict_json
from server.platform import RunHandle, input_hash

__all__ = ["AnalysisError", "LLMBudgetExceeded", "LLMClient", "LLMOutputInvalid", "Provider", "ProviderUnavailable",
           "ground_citations", "llm_client", "locate_quote", "override_llm_client", "resolve_provider", "strict_schema"]

Provider = Literal["openai", "deterministic"]
Transport = Callable[[str, dict, float], dict]  # (API path, JSON payload, timeout seconds) -> parsed JSON response
API_URL = "https://api.openai.com/v1"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_PROMPT_VERSION = "embedding-v1"
EMBEDDING_BATCH = 256
MAX_RESPONSE_BYTES = 8_000_000
MAX_RECORDED_REQUESTS = 100
_UNSUPPORTED_KEYWORDS = ("minLength", "maxLength", "default")


class LLMOutputInvalid(AnalysisError):
    """The model answered, but its output failed strict JSON, schema or grounding checks."""


class LLMBudgetExceeded(ProviderUnavailable):
    """The run reached OPENAI_MAX_CALLS_PER_RUN."""


def _http_transport(api_key: str) -> Transport:
    def send(path: str, payload: dict, timeout: float) -> dict:
        request = Request(API_URL + path, data=json.dumps(payload).encode(), method="POST",
                          headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            # Never include response bodies, prompts or credentials in error text.
            raise ProviderUnavailable(f"OpenAI request failed with HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise ProviderUnavailable("OpenAI request failed or timed out") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ProviderUnavailable("OpenAI response exceeded the allowed size")
        try:
            result = _strict_json(raw)
        except (ValueError, RecursionError):
            raise ProviderUnavailable("OpenAI returned invalid JSON") from None
        if not isinstance(result, dict):
            raise ProviderUnavailable("OpenAI returned an unexpected response")
        return result

    return send


def strict_schema(schema: type[BaseModel]) -> dict:
    """Pydantic JSON schema in OpenAI strict form: every property required, no additional properties.

    Length limits and defaults are not part of the supported subset; Pydantic re-validates them after the
    response arrives. Optional fields therefore become required-but-nullable, as strict mode expects.
    """
    result = schema.model_json_schema()

    def visit(node):
        if isinstance(node, dict):
            for keyword in _UNSUPPORTED_KEYWORDS:
                node.pop(keyword, None)
            if node.get("type") == "object" and isinstance(node.get("properties"), dict):
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(result)
    return result


def _output_text(result: dict) -> str:
    if result.get("status") != "completed":
        raise ProviderUnavailable("OpenAI response did not complete")
    output, fragments = result.get("output"), []
    if not isinstance(output, list):
        raise ProviderUnavailable("OpenAI returned malformed output")
    for item in output:
        if not isinstance(item, dict):
            raise ProviderUnavailable("OpenAI returned malformed output")
        if item.get("type") == "reasoning":
            continue
        if item.get("type") != "message" or item.get("role") != "assistant" or item.get("status") != "completed":
            raise ProviderUnavailable("OpenAI returned an unexpected output item")
        content = item.get("content")
        if not isinstance(content, list):
            raise ProviderUnavailable("OpenAI returned malformed content")
        for part in content:
            if not isinstance(part, dict):
                raise ProviderUnavailable("OpenAI returned malformed content")
            if part.get("type") == "refusal":
                raise ProviderUnavailable("OpenAI declined the request")
            if part.get("type") != "output_text" or not isinstance(part.get("text"), str):
                raise ProviderUnavailable("OpenAI returned malformed text content")
            fragments.append(part["text"])
    return "".join(fragments)


def _usage(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}

    def count(*names):
        for name in names:
            value = raw.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return value
        return 0

    usage = {"input_tokens": count("input_tokens", "prompt_tokens"), "output_tokens": count("output_tokens")}
    usage["total_tokens"] = count("total_tokens") or usage["input_tokens"] + usage["output_tokens"]
    return usage


class LLMClient:
    def __init__(self, *, model: str, transport: Transport, embedding_model: str = DEFAULT_EMBEDDING_MODEL,
                 max_calls_per_run: int = 40, timeout_seconds: float = 90, cache: bool = True):
        if not model.strip() or not embedding_model.strip():
            raise ProviderUnavailable("OpenAI model names must not be blank")
        self.model, self.embedding_model = model.strip(), embedding_model.strip()
        self.max_calls_per_run, self.timeout_seconds = max_calls_per_run, timeout_seconds
        self.cache, self._transport = cache, transport

    def method_version(self, prompt_version: str) -> str:
        return f"openai:{self.model}:{prompt_version}"

    # Recording -------------------------------------------------------------------------------------

    @staticmethod
    def _metrics(run: RunHandle) -> dict:
        llm = run.metrics.setdefault("llm", {})
        for key in ("calls", "cache_hits", "input_tokens", "output_tokens", "total_tokens"):
            llm.setdefault(key, 0)
        llm.setdefault("latency_ms", 0.0)
        llm.setdefault("models", [])
        llm.setdefault("requests", [])
        return llm

    def _reserve(self, run: RunHandle) -> dict:
        llm = self._metrics(run)
        if llm["calls"] >= self.max_calls_per_run:
            raise LLMBudgetExceeded(f"OpenAI call budget of {self.max_calls_per_run} per run is exhausted "
                                    "(OPENAI_MAX_CALLS_PER_RUN)")
        llm["calls"] += 1
        return llm

    def _record(self, run: RunHandle, *, kind: str, task: str, model: str, prompt_version: str, key: str,
                cached: bool, usage: dict, latency_ms: float) -> None:
        llm = self._metrics(run)
        if cached:
            llm["cache_hits"] += 1
        else:
            for name in ("input_tokens", "output_tokens", "total_tokens"):
                llm[name] += usage.get(name, 0)
            llm["latency_ms"] = round(llm["latency_ms"] + latency_ms, 1)
        if model not in llm["models"]:
            llm["models"].append(model)
        if len(llm["requests"]) < MAX_RECORDED_REQUESTS:
            llm["requests"].append({"kind": kind, "task": task, "model": model, "prompt_version": prompt_version,
                                    "input_hash": key, "cached": cached, "usage": usage,
                                    "latency_ms": round(latency_ms, 1)})
        else:
            llm["requests_truncated"] = llm.get("requests_truncated", 0) + 1

    def _cache_get(self, key: str, model: str, prompt_version: str):
        if not self.cache:
            return None
        with closing(connect()) as connection:
            row = connection.execute("SELECT response FROM llm_cache WHERE input_hash=? AND model=? AND prompt_version=?",
                                     (key, model, prompt_version)).fetchone()
        return json.loads(row[0]) if row else None

    def _cache_put(self, key: str, model: str, prompt_version: str, response, usage: dict) -> None:
        if self.cache:
            with transaction() as connection:
                connection.execute("INSERT OR IGNORE INTO llm_cache (input_hash, model, prompt_version, response, usage, "
                                   "created_at) VALUES (?,?,?,?,?,?)",
                                   (key, model, prompt_version, encode(response), encode(usage), now()))

    def _send(self, path: str, payload: dict) -> tuple[dict, float]:
        started = time.monotonic()
        result = self._transport(path, payload, self.timeout_seconds)
        if not isinstance(result, dict):
            raise ProviderUnavailable("OpenAI returned an unexpected response")
        return result, (time.monotonic() - started) * 1000

    # Public API ------------------------------------------------------------------------------------

    def structured(self, *, task: str, prompt_version: str, instructions: str, input: dict | str,
                   schema: type[BaseModel], run: RunHandle, max_output_tokens: int = 8000) -> BaseModel:
        """One strict Structured Outputs request; returns the validated schema instance."""
        text = input if isinstance(input, str) else json.dumps(input, ensure_ascii=False, sort_keys=True,
                                                               allow_nan=False, default=str)
        json_schema = strict_schema(schema)
        key = input_hash({"task": task, "instructions": instructions, "input": text, "schema": json_schema,
                          "max_output_tokens": max_output_tokens})
        cached = self._cache_get(key, self.model, prompt_version)
        if cached is not None:
            try:
                parsed = schema.model_validate(cached)
            except ValidationError:
                parsed = None
            if parsed is not None:
                self._record(run, kind="structured", task=task, model=self.model, prompt_version=prompt_version,
                             key=key, cached=True, usage={}, latency_ms=0)
                return parsed
        self._reserve(run)
        payload = {"model": self.model, "instructions": instructions, "input": text, "store": False,
                   "max_output_tokens": max_output_tokens,
                   "text": {"format": {"type": "json_schema", "name": re.sub(r"[^A-Za-z0-9_-]+", "_", task)[:64] or "output",
                                       "strict": True, "schema": json_schema}}}
        result, latency = self._send("/responses", payload)
        usage = _usage(result.get("usage"))
        self._record(run, kind="structured", task=task, model=self.model, prompt_version=prompt_version, key=key,
                     cached=False, usage=usage, latency_ms=latency)
        output = _output_text(result)
        try:
            raw = _strict_json(output)
        except (ValueError, RecursionError):
            raise LLMOutputInvalid(f"OpenAI output for {task} is not strict JSON") from None
        try:
            parsed = schema.model_validate(raw)
        except ValidationError:
            raise LLMOutputInvalid(f"OpenAI output for {task} does not match the required schema") from None
        self._cache_put(key, self.model, prompt_version, raw, usage)
        return parsed

    def web_search(self, *, task: str, prompt_version: str, instructions: str, inputs: list[str],
                   schema: type[BaseModel], run: RunHandle, max_output_tokens: int = 8000,
                   max_workers: int = 4) -> list[tuple[BaseModel, list[str]]]:
        """Structured Outputs requests with OpenAI's web_search tool, one per input, in input order.

        Returns (validated output, URLs the search returned or opened) per input. The URL list lets the
        caller reject cited pages the search never saw. Only public research questions belong here.
        Requests run concurrently over HTTP; recording and caching stay on the calling thread.
        """
        json_schema = strict_schema(schema)
        name = re.sub(r"[^A-Za-z0-9_-]+", "_", task)[:64] or "output"
        keys = [input_hash({"task": task, "instructions": instructions, "input": text, "schema": json_schema,
                            "tools": ["web_search"], "max_output_tokens": max_output_tokens}) for text in inputs]
        results: dict[int, tuple[BaseModel, list[str]]] = {}
        for index, key in enumerate(keys):
            cached = self._cache_get(key, self.model, prompt_version)
            try:
                parsed = schema.model_validate(cached["output"]) if isinstance(cached, dict) else None
            except (ValidationError, KeyError):
                parsed = None
            if parsed is not None:
                self._record(run, kind="web_search", task=task, model=self.model, prompt_version=prompt_version,
                             key=key, cached=True, usage={}, latency_ms=0)
                results[index] = (parsed, list(cached.get("sources", [])))
        missing = [index for index in range(len(inputs)) if index not in results]
        for _ in missing:
            self._reserve(run)

        def send(index: int):
            payload = {"model": self.model, "instructions": instructions, "input": inputs[index], "store": False,
                       "max_output_tokens": max_output_tokens, "tools": [{"type": "web_search"}],
                       "include": ["web_search_call.action.sources"],
                       "text": {"format": {"type": "json_schema", "name": name, "strict": True, "schema": json_schema}}}
            return self._send("/responses", payload)

        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(missing) or 1))) as pool:
            responses = dict(zip(missing, pool.map(send, missing)))
        for index in missing:
            result, latency = responses[index]
            usage = _usage(result.get("usage"))
            self._record(run, kind="web_search", task=task, model=self.model, prompt_version=prompt_version,
                         key=keys[index], cached=False, usage=usage, latency_ms=latency)
            sources, message = [], {"status": result.get("status"), "output": []}
            for item in result.get("output") or []:
                if isinstance(item, dict) and item.get("type") == "web_search_call":
                    action = item.get("action") if isinstance(item.get("action"), dict) else {}
                    sources += [source["url"] for source in action.get("sources") or []
                                if isinstance(source, dict) and isinstance(source.get("url"), str)]
                    if isinstance(action.get("url"), str):
                        sources.append(action["url"])
                else:
                    message["output"].append(item)
            text = _output_text(message)
            try:
                raw = _strict_json(text)
                parsed = schema.model_validate(raw)
            except (ValueError, RecursionError, ValidationError):
                raise LLMOutputInvalid(f"OpenAI web research output for {task} does not match the required schema") from None
            sources = list(dict.fromkeys(sources))
            self._cache_put(keys[index], self.model, prompt_version, {"output": raw, "sources": sources}, usage)
            results[index] = (parsed, sources)
        return [results[index] for index in range(len(inputs))]

    def embed(self, texts: list[str], *, run: RunHandle) -> list[list[float]]:
        """Embedding vectors in input order; cached per text and model."""
        if not isinstance(texts, list) or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise AnalysisError("Embeddings need a list of non-empty strings")
        keys = [input_hash({"embedding": text}) for text in texts]
        vectors: dict[str, list[float]] = {}
        for key in dict.fromkeys(keys):
            cached = self._cache_get(key, self.embedding_model, EMBEDDING_PROMPT_VERSION)
            if cached is not None:
                vectors[key] = cached
                self._record(run, kind="embedding", task="embed", model=self.embedding_model,
                             prompt_version=EMBEDDING_PROMPT_VERSION, key=key, cached=True, usage={}, latency_ms=0)
        missing = [(key, text) for key, text in dict(zip(keys, texts)).items() if key not in vectors]
        for start in range(0, len(missing), EMBEDDING_BATCH):
            batch = missing[start:start + EMBEDDING_BATCH]
            self._reserve(run)
            result, latency = self._send("/embeddings", {"model": self.embedding_model, "input": [t for _, t in batch]})
            data = result.get("data")
            if not isinstance(data, list) or len(data) != len(batch):
                raise ProviderUnavailable("OpenAI returned malformed embeddings")
            ordered = sorted(data, key=lambda item: item.get("index", -1) if isinstance(item, dict) else -1)
            usage = _usage(result.get("usage"))
            self._record(run, kind="embedding", task="embed", model=self.embedding_model,
                         prompt_version=EMBEDDING_PROMPT_VERSION, key=input_hash([key for key, _ in batch]),
                         cached=False, usage=usage, latency_ms=latency)
            for (key, _), item in zip(batch, ordered):
                vector = item.get("embedding") if isinstance(item, dict) else None
                if (not isinstance(vector, list) or not vector or any(
                        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector)):
                    raise ProviderUnavailable("OpenAI returned malformed embeddings")
                vectors[key] = [float(v) for v in vector]
                self._cache_put(key, self.embedding_model, EMBEDDING_PROMPT_VERSION, vectors[key], {})
        if len({len(vector) for vector in vectors.values()}) > 1:
            raise ProviderUnavailable("OpenAI returned embeddings of inconsistent dimensions")
        return [vectors[key] for key in keys]


_override: LLMClient | None = None


@contextmanager
def override_llm_client(client: LLMClient | None):
    """Tests inject a client with a fake transport; llm_client() returns it inside the block."""
    global _override
    previous, _override = _override, client
    try:
        yield client
    finally:
        _override = previous


def _env_number(name: str, default: float, minimum: float, maximum: float, cast=int):
    try:
        value = cast(os.environ.get(name, "").strip() or default)
    except ValueError:
        raise ProviderUnavailable(f"{name} must be a number") from None
    if not minimum <= value <= maximum:
        raise ProviderUnavailable(f"{name} must be between {minimum} and {maximum}")
    return value


def llm_client() -> LLMClient:
    """The configured OpenAI client; raises ProviderUnavailable when the key or model is missing."""
    if _override is not None:
        return _override
    api_key, model = os.environ.get("OPENAI_API_KEY", "").strip(), os.environ.get("OPENAI_MODEL", "").strip()
    if not api_key or not model:
        raise ProviderUnavailable("OpenAI requires OPENAI_API_KEY and OPENAI_MODEL; select provider 'deterministic' "
                                  "for the labelled offline baseline")
    return LLMClient(model=model, transport=_http_transport(api_key),
                     embedding_model=os.environ.get("OPENAI_EMBEDDING_MODEL", "").strip() or DEFAULT_EMBEDDING_MODEL,
                     max_calls_per_run=_env_number("OPENAI_MAX_CALLS_PER_RUN", 40, 1, 10_000),
                     timeout_seconds=_env_number("OPENAI_TIMEOUT_SECONDS", 90, 1, 600, float))


def resolve_provider(provider: str, *, prompt_version: str, deterministic_method: str) -> tuple[LLMClient | None, str]:
    """(client, method_version) for an AI-interpretation capability; deterministic returns no client.

    Call before record_run so the run carries the right method_version. OpenAI selected but not
    configured raises ProviderUnavailable; it never falls back to the deterministic method.
    """
    if provider == "deterministic":
        return None, deterministic_method
    if provider != "openai":
        raise ProviderUnavailable(f"Unsupported provider: {provider}")
    client = llm_client()
    return client, client.method_version(prompt_version)


def locate_quote(text: str, quote: str) -> tuple[int, int] | None:
    """Character span of quote in text: exact first, then ignoring case and whitespace runs."""
    if not isinstance(text, str) or not isinstance(quote, str) or not quote.strip():
        return None
    quote = quote.strip()
    position = text.find(quote)
    if position >= 0:
        return position, position + len(quote)
    chars, index, previous_space = [], [], False
    for offset, char in enumerate(text):
        if char.isspace():
            if previous_space:
                continue
            chars.append(" ")
            previous_space = True
        else:
            lower = char.lower()
            chars.append(lower if len(lower) == 1 else char)
            previous_space = False
        index.append(offset)
    needle = "".join(c.lower() if len(c.lower()) == 1 else c for c in re.sub(r"\s+", " ", quote))
    position = "".join(chars).find(needle)
    if position < 0:
        return None
    return index[position], index[position + len(needle) - 1] + 1


def ground_citations(citations: Iterable[dict], texts: Mapping[str, str], *, id_key: str = "evidence_id",
                     quote_key: str = "quote") -> list[dict]:
    """Attach a local span to each model citation; reject ids outside scope and quotes not in the record.

    Models quote; code locates. Returns copies with 'span': [start, end]. Ungrounded output raises
    LLMOutputInvalid, so it is rejected rather than stored.
    """
    grounded = []
    for citation in citations:
        record_id, quote = citation.get(id_key), citation.get(quote_key)
        if record_id not in texts:
            raise LLMOutputInvalid(f"Model cited {id_key} outside the supplied scope")
        span = locate_quote(texts[record_id], quote)
        if span is None:
            raise LLMOutputInvalid(f"Model quote is not present in the cited {id_key}")
        grounded.append({**citation, "span": list(span)})
    return grounded
