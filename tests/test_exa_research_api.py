"""Exa reaches the shared API only after explicit public research and selection."""

import httpx
import pytest

from mcp_server.cache import FileCache
from mcp_server.exa_client import ExaClient
from server import exa_research


def test_status_and_unconfigured_search_do_not_call_provider(client, monkeypatch, tmp_path):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    transport = httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("unexpected provider call")))
    research = ExaClient(api_key="", client=transport, cache=FileCache(tmp_path / "cache"))
    monkeypatch.setattr(exa_research, "exa_client", lambda: research)
    assert client.get("/research/exa/status").json() == {"provider": "exa", "configured": False}
    missing_confirmation = client.post("/research/exa/search", json={"query": "BMW charging experience"})
    assert missing_confirmation.status_code == 422
    unavailable = client.post("/research/exa/search", json={
        "query": "BMW charging experience", "public_data_confirmed": True,
    })
    assert unavailable.status_code == 503
    assert "EXA_CONFIGURATION_ERROR" in unavailable.json()["detail"]
    transport.close()


@pytest.mark.parametrize("market", ["US", "EU", "CN"])
def test_market_scoped_search_fetch_and_selected_import(client, monkeypatch, tmp_path, market):
    calls = []

    def provider(request):
        calls.append(request.url.path)
        if request.url.path == "/search":
            return httpx.Response(200, json={"results": [{
                "id": "public-lead", "url": "https://example.com/public-charging",
                "title": "Public charging overview", "highlights": ["Public charging summary"],
            }]})
        return httpx.Response(200, json={"statuses": [{"status": "success"}], "results": [{
            "id": "public-lead", "url": "https://example.com/public-charging",
            "title": "Public charging overview", "text": "Public charging overview for research review.",
        }]})

    transport = httpx.Client(transport=httpx.MockTransport(provider))
    research = ExaClient(api_key="synthetic-test-only", client=transport, cache=FileCache(tmp_path / "cache"))
    monkeypatch.setattr(exa_research, "exa_client", lambda: research)
    scope = {"query": "BMW charging experience", "vehicle": "G60", "market": market,
             "public_data_confirmed": True}
    search = client.post("/research/exa/search", json={**scope, "max_results": 1})
    assert search.status_code == 200
    lead = search.json()["candidates"][0]
    assert lead["market"] == market and lead["content_status"] == "search_lead"
    denied = client.post("/research/exa/import", json={
        "candidate_id": lead["candidate_id"], "actor": "Test PM", "rationale": "Public comparison",
        "selection_confirmed": True,
    })
    assert denied.status_code == 422
    assert "FETCH_REQUIRED" in denied.json()["detail"]
    fetched = client.post("/research/exa/fetch", json={**scope, "identifier": lead["canonical_url"]})
    assert fetched.status_code == 200
    candidate = fetched.json()["candidates"][0]
    assert candidate["market"] == market and candidate["content_status"] == "fetched"
    imported = client.post("/research/exa/import", json={
        "candidate_id": candidate["candidate_id"], "actor": "Test PM",
        "rationale": "Selected public charging context", "selection_confirmed": True,
    })
    assert imported.status_code == 201
    assert imported.json()["provenance_verified"] is True
    saved = client.get(f"/sources/{imported.json()['source_id']}").json()
    assert saved["market"] == market
    assert saved["metadata"]["web_evidence"]["candidate_id"] == candidate["candidate_id"]
    assert calls == ["/search", "/contents"]
    transport.close()
