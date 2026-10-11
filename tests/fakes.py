"""Offline OpenAI double for server/llm.py. No test may reach the network.

Use the `fake_llm` fixture (tests/conftest.py): it installs an LLMClient with this transport for the
test. Set `responder` to answer structured requests and optionally `embedder` for embeddings:

    def test_x(client, fake_llm):
        fake_llm.responder = lambda request: {"label": "positive", ...}   # parsed schema output
        ...
        assert fake_llm.calls("/responses")[0]["text"]["format"]["name"] == "my_task"

`request` is the Responses payload; json.loads(request["input"]) recovers a dict input. A responder may
return a full raw response by returning FakeOpenAI.raw(...), or raise ProviderUnavailable to simulate
an outage.
"""

import hashlib
import json

from server.llm import LLMClient

FAKE_MODEL = "fake-model"


class FakeOpenAI:
    def __init__(self, responder=None, embedder=None, dimensions: int = 8):
        self.requests: list[tuple[str, dict]] = []
        self.responder = responder
        self.embedder = embedder
        self.dimensions = dimensions
        self.usage = {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}

    def calls(self, path: str) -> list[dict]:
        return [payload for request_path, payload in self.requests if request_path == path]

    @staticmethod
    def raw(text: str, status: str = "completed", usage: dict | None = None) -> dict:
        return {"_raw": True, "status": status, "usage": usage or {},
                "output": [{"type": "message", "role": "assistant", "status": "completed",
                            "content": [{"type": "output_text", "text": text}]}]}

    def vector(self, text: str) -> list[float]:
        """Deterministic pseudo-embedding: identical texts get identical vectors."""
        digest = hashlib.sha256(text.encode()).digest()
        return [byte / 255 - 0.5 for byte in digest[:self.dimensions]]

    def __call__(self, path: str, payload: dict, timeout: float) -> dict:
        self.requests.append((path, payload))
        if path == "/embeddings":
            embed = self.embedder or self.vector
            return {"data": [{"index": i, "embedding": embed(text)} for i, text in enumerate(payload["input"])],
                    "usage": {"prompt_tokens": 5 * len(payload["input"]), "total_tokens": 5 * len(payload["input"])}}
        if path != "/responses":
            raise AssertionError(f"Unexpected OpenAI path {path}")
        if self.responder is None:
            raise AssertionError("Set fake_llm.responder before calling a structured capability")
        result = self.responder(payload)
        if isinstance(result, dict) and result.get("_raw"):
            return {key: value for key, value in result.items() if key != "_raw"} | {
                "usage": result.get("usage") or self.usage}
        return {**self.raw(json.dumps(result)), "usage": self.usage}


def fake_client(fake: FakeOpenAI, **options) -> LLMClient:
    return LLMClient(model=FAKE_MODEL, transport=fake, **options)
