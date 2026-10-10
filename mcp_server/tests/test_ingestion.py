"""Negative-path selection tests: no unreviewed claim silently becomes a decision."""

import json
from unittest.mock import Mock

import httpx
import pytest

from mcp_server.cache import FileCache
from mcp_server.errors import EvidenceError
from mcp_server.exa_client import ExaClient
from mcp_server.ingestion import import_candidate
from mcp_server.models import FetchRequest, SearchRequest


@pytest.fixture
def snapshot(tmp_path):
    cache = FileCache(tmp_path / "cache")
    transport = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
        "requestId": "synthetic-request", "results": [{
            "id": "synthetic-source", "url": "https://example.com/public-product",
            "title": "Synthetic public product context", "text": "Illustrative public product text.",
        }],
    })))
    exa = ExaClient(api_key="synthetic-test-only", client=transport, cache=cache)
    candidate = exa.fetch(FetchRequest(identifier="https://example.com/public-product",
                                     query="BMW cabin features", public_data_confirmed=True))["candidates"][0]
    yield cache, exa, candidate
    transport.close()


def selection(cache, backend, candidate, **overrides):
    args = {"candidate_id": candidate["candidate_id"], "actor": "Test reviewer",
            "rationale": "Selected source context", "selection_confirmed": True}
    return import_candidate(cache, backend, **{**args, **overrides})


@pytest.mark.parametrize("invalid", [
    {"selection_confirmed": False}, {"actor": " "}, {"rationale": " "}, {"candidate_id": "unknown"},
])
def test_invalid_selection_never_contacts_backend(snapshot, invalid):
    cache, _, candidate = snapshot
    backend = Mock()
    with pytest.raises(EvidenceError):
        selection(cache, backend, candidate, **invalid)
    assert backend.mock_calls == []


def test_search_lead_requires_fetch_before_import(snapshot):
    cache, exa, _ = snapshot
    lead = exa.search(SearchRequest(query="BMW cabin features", public_data_confirmed=True))["candidates"][0]
    backend = Mock()
    with pytest.raises(EvidenceError, match="FETCH_REQUIRED"):
        selection(cache, backend, lead)
    assert backend.mock_calls == []


def test_damaged_cached_snapshot_never_contacts_backend(snapshot):
    cache, _, candidate = snapshot
    path = next(cache.directory.glob("*.json"))
    value = json.loads(path.read_text())
    value["value"]["candidates"][0]["content"] += " damaged"
    path.write_text(json.dumps(value))
    backend = Mock()
    with pytest.raises(EvidenceError, match="INVALID_CANDIDATE"):
        selection(cache, backend, candidate)
    assert backend.mock_calls == []


def test_missing_backend_route_never_fabricates_persistence(snapshot):
    cache, _, candidate = snapshot
    backend = Mock()
    backend.import_records.side_effect = EvidenceError("API_NOT_FOUND", "API returned HTTP 404")
    with pytest.raises(EvidenceError, match="API_NOT_FOUND"):
        selection(cache, backend, candidate)
    backend.get_source.assert_not_called()


def test_readback_failure_preserves_actual_import_confirmation(snapshot):
    cache, _, candidate = snapshot
    backend = Mock()
    backend.import_records.return_value = {
        "source_id": "persisted-source", "import_id": "persisted-import", "record_count": 1,
        "deduplicated": False, "sha256": "backend-snapshot-hash",
    }
    backend.get_source.side_effect = EvidenceError("API_TIMEOUT", "API timed out")
    result = selection(cache, backend, candidate)
    assert result["persisted"] is True
    assert result["provenance_verified"] is False
    assert result["source_id"] == "persisted-source"
    assert result["review_status"] == "unreviewed"
    assert "audit_event_id" not in result


def test_provenance_loss_is_reported_after_real_import(snapshot):
    cache, _, candidate = snapshot
    backend = Mock()
    backend.import_records.return_value = {"source_id": "persisted-source"}
    backend.get_source.return_value = {"metadata": {}}
    with pytest.raises(EvidenceError, match="PROVENANCE_MISMATCH"):
        selection(cache, backend, candidate)
