"""Exa's official HTTP API behind a stable, candidate-only research contract."""

import copy
import json
import os
from datetime import datetime, time, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from mcp_server.cache import FileCache
from mcp_server.errors import EvidenceError
from mcp_server.http import request_json
from mcp_server.integrity import valid_candidate
from mcp_server.models import FetchRequest, SearchRequest, canonicalize_url, digest

EXA_BASE_URL = "https://api.exa.ai"
MAX_CONTENT_CHARACTERS = 10000
MAX_EXCERPT_CHARACTERS = 1000


class ExaClient:
    def __init__(self, api_key: str | None = None, client: httpx.Client | None = None, cache: FileCache | None = None):
        self.api_key = (api_key if api_key is not None else os.environ.get("EXA_API_KEY", "")).strip()
        self.client = client or httpx.Client(timeout=httpx.Timeout(30, connect=5), trust_env=False)
        cache_dir = Path(os.environ.get("EXA_CACHE_DIR", str(Path.home() / ".cache" / "bmw-mcp" / "exa")))
        self.cache = cache if cache is not None else FileCache(cache_dir)

    def search(self, request: SearchRequest) -> dict:
        request = SearchRequest.model_validate(request.model_dump())
        scoped_query = f"{request.query}; vehicle {request.vehicle}; market {request.market}; public automotive evidence"
        payload = {"query": scoped_query, "type": "auto", "numResults": request.max_results,
                   "contents": {"highlights": True}}
        if request.trusted_domains:
            payload["includeDomains"] = request.trusted_domains
        for field, target, boundary in (
            (request.start_published_date, "startPublishedDate", time.min),
            (request.end_published_date, "endPublishedDate", time.max),
        ):
            if field:
                payload[target] = datetime.combine(field, boundary, timezone.utc).isoformat()
        return self._execute("/search", payload, request, scoped_query)

    def fetch(self, request: FetchRequest) -> dict:
        request = FetchRequest.model_validate(request.model_dump())
        identifier = request.identifier
        discovery = None
        is_url = "://" in identifier
        canonical = canonicalize_url(identifier) if is_url else None
        for candidate in self.cache.candidates():
            if not valid_candidate(candidate):
                continue
            if (is_url and candidate.get("canonical_url") == canonical
                    or not is_url and candidate.get("exa_result_id") == identifier):
                discovery = candidate
                if (candidate.get("content_status") == "search_lead"
                        and all(candidate.get(key) == getattr(request, key) for key in ("query", "vehicle", "market"))):
                    break
        if not is_url:
            if not discovery:
                raise EvidenceError("UNKNOWN_EXA_RESULT", "Use a public URL or an Exa result ID from this local search cache.")
            canonical = canonicalize_url(discovery.get("canonical_url", ""))
        payload = {"ids": [canonical], "text": {"maxCharacters": MAX_CONTENT_CHARACTERS}}
        return self._execute("/contents", payload, request, None, discovery)

    def _execute(self, endpoint, payload, request, scoped_query, discovery=None):
        key = json.dumps({"version": 1, "endpoint": endpoint, "payload": payload,
                          "query": request.query, "vehicle": request.vehicle, "market": request.market}, sort_keys=True)
        hit = self.cache.get(key, allow_stale=request.cache_only)
        if hit and self._valid_cached_response(hit.value):
            result = copy.deepcopy(hit.value)
            result["cache"] = {"hit": True, "stale": hit.stale}
            if hit.stale:
                result["warnings"].append("Explicit cache-only replay: content is stale; retrieval time is unchanged.")
            if not self.api_key:
                result["warnings"].append("EXA_API_KEY is not configured; serving previously cached public evidence.")
            return result
        if request.cache_only:
            raise EvidenceError("CACHE_MISS", "No usable cached response exists for this exact query, scope, and filters.")
        if not self.api_key:
            raise EvidenceError("EXA_CONFIGURATION_ERROR", "Set EXA_API_KEY to use Exa, or replay a cached request. Imported backend sources remain available.")
        raw = request_json(self.client, "POST", EXA_BASE_URL + endpoint, service="EXA",
                           headers={"x-api-key": self.api_key}, json=payload)
        if not isinstance(raw, dict) or not isinstance(raw.get("results"), list):
            raise EvidenceError("EXA_INVALID_RESPONSE", "Exa response did not contain a result list.")
        if endpoint == "/contents":
            statuses = raw.get("statuses", [])
            if not isinstance(statuses, list) or any(not isinstance(s, dict) or s.get("status") != "success" for s in statuses):
                raise EvidenceError("EXA_CONTENT_UNAVAILABLE", "Exa could not retrieve the requested source content.")
        metadata = self._metadata(raw, endpoint)
        retrieved_at = datetime.now(timezone.utc).isoformat()
        candidates, seen = [], set()
        warnings = ["Unreviewed web leads; verify source claims, date, scope, and conflicting evidence before use.",
                    "No backend source or audit record was written by this research request."]
        for item in raw["results"][:50]:
            candidate = self._candidate(item, request, scoped_query, retrieved_at, metadata, endpoint, discovery)
            url = candidate["canonical_url"]
            if url in seen:
                continue
            if isinstance(request, SearchRequest) and request.trusted_domains:
                host = urlsplit(url).hostname
                if not any(host == d or host.endswith("." + d) for d in request.trusted_domains):
                    warnings.append("An out-of-domain provider result was excluded.")
                    continue
            seen.add(url)
            candidates.append(candidate)
            if len(candidates) >= (request.max_results if isinstance(request, SearchRequest) else 1):
                break
        if endpoint == "/contents" and (not candidates or not candidates[0]["content"]):
            raise EvidenceError("EXA_CONTENT_UNAVAILABLE", "Exa returned no usable source text; no fetched evidence was cached.")
        result = {"provider": "exa", "candidates": candidates, "cache": {"hit": False, "stale": False},
                  "persistence_status": "not_persisted", "warnings": warnings, "request_metadata": metadata}
        if not self.cache.set(key, result):
            result["warnings"].append("The local cache could not save this response; retain it before restarting.")
        return result

    @staticmethod
    def _valid_cached_response(value):
        if (value.get("provider") != "exa" or value.get("persistence_status") != "not_persisted"
                or not isinstance(value.get("candidates"), list) or not isinstance(value.get("warnings"), list)):
            return False
        return all(valid_candidate(candidate) for candidate in value["candidates"])

    @staticmethod
    def _metadata(raw, endpoint):
        metadata = {"endpoint": endpoint}
        for source, target in (("requestId", "request_id"), ("resolvedSearchType", "resolved_search_type")):
            value = raw.get(source)
            if isinstance(value, str):
                metadata[target] = value[:200]
        cost = raw.get("costDollars")
        if isinstance(cost, dict) and type(cost.get("total")) in {int, float} and 0 <= cost["total"] < 100000:
            metadata["cost_dollars_total"] = cost["total"]
        return metadata

    @staticmethod
    def _candidate(item, request, scoped_query, retrieved_at, metadata, endpoint, discovery):
        if not isinstance(item, dict) or not isinstance(item.get("url"), str):
            raise EvidenceError("EXA_INVALID_RESPONSE", "Exa result did not contain a source URL.")
        canonical = canonicalize_url(item["url"])
        for name in ("title", "id", "text", "publishedDate"):
            if item.get(name) is not None and not isinstance(item[name], str):
                raise EvidenceError("EXA_INVALID_RESPONSE", "Exa source metadata had an unexpected type.")
        highlights = item.get("highlights") or []
        if not isinstance(highlights, list) or any(not isinstance(h, str) for h in highlights):
            raise EvidenceError("EXA_INVALID_RESPONSE", "Exa source highlights had an unexpected type.")
        content = (item.get("text") or "")[:MAX_CONTENT_CHARACTERS].strip()
        excerpt = ("\n".join(highlights) or content)[:MAX_EXCERPT_CHARACTERS].strip()
        published = item.get("publishedDate") or None
        date_warning = None
        if published:
            try:
                datetime.fromisoformat(published.replace("Z", "+00:00"))
            except ValueError:
                date_warning = "Provider publication date could not be parsed; no publication date was inferred."
                published = None
        uncertainties = ["Requested vehicle/market is research context, not verified source applicability.",
                         "Source claims and supporting excerpt require human verification."]
        if not published:
            uncertainties.append(date_warning or "Publication date unavailable; retrieval time is not publication time.")
        if not excerpt:
            uncertainties.append("Search result has no supporting excerpt; fetch content before selecting it.")
        excerpt_hash = digest(excerpt)
        result = {
            "candidate_id": "exa:" + digest(canonical + "\n" + excerpt_hash + "\n" + request.vehicle + "\n" + request.market),
            "provider": "exa", "exa_result_id": item.get("id"), "query": request.query,
            "search_query": scoped_query, "title": (item.get("title") or canonical)[:500],
            "original_url": item["url"], "canonical_url": canonical, "publication_date": published,
            "retrieved_at": retrieved_at, "supporting_excerpt": excerpt, "excerpt_hash": excerpt_hash,
            "url_hash": digest(canonical), "hash_algorithm": "sha256", "provider_metadata": metadata,
            "vehicle": request.vehicle, "market": request.market,
            "market_applicability": "requested_scope_not_verified", "evidence_level": "unverified_web_source",
            "review_status": "unreviewed", "persisted": False, "uncertainties": uncertainties,
            "content_status": "fetched" if endpoint == "/contents" else "search_lead",
        }
        if endpoint == "/contents":
            result["content"] = content
            result["content_hash"] = digest(content)
            result["content_hash_scope"] = "returned_text_up_to_10000_characters_not_original_document"
            result["fetched_identifier"] = request.identifier
        if discovery:
            original_discovery = discovery.get("discovery_provenance") or discovery
            if original_discovery.get("search_query"):
                result["discovery_provenance"] = {key: original_discovery.get(key) for key in (
                    "candidate_id", "query", "search_query", "retrieved_at", "provider_metadata", "exa_result_id")}
        # Identify this exact research snapshot, not just a URL or the first excerpt.
        result.pop("candidate_id")
        result["candidate_id"] = "exa:" + digest(json.dumps(result, sort_keys=True, allow_nan=False))
        return result
