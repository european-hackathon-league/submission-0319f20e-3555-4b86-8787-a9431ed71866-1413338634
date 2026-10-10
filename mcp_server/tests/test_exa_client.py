"""Mocked provider checks: real request shapes, provenance, and no secret leakage."""

import hashlib
import json
from datetime import date, datetime
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

import mcp_server.cache as cache_module
from mcp_server.cache import FileCache
from mcp_server.errors import EvidenceError
from mcp_server.exa_client import ExaClient
from mcp_server.models import FetchRequest, SearchRequest

PUBLIC_QUERY = "BMW G60 US public infotainment features"
PUBLIC_URL = "https://www.bmwusa.com/vehicles/5-series/sedan/overview.html"
API_KEY = "unit-test-exa-secret-do-not-leak"


@pytest.fixture(autouse=True)
def no_ambient_credentials(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)


@pytest.fixture
def cache(tmp_path):
    return FileCache(tmp_path / "cache")


def search_request(**overrides):
    return SearchRequest(query=PUBLIC_QUERY, public_data_confirmed=True, **overrides)


def fetch_request(identifier=PUBLIC_URL, **overrides):
    return FetchRequest(identifier=identifier, query=PUBLIC_QUERY, public_data_confirmed=True, **overrides)


def provider_result(**overrides):
    return {
        "id": "exa-public-bmw-page",
        "url": PUBLIC_URL,
        "title": "BMW 5 Series public overview",
        "publishedDate": "2025-01-15T12:00:00Z",
        "highlights": ["The public overview describes the vehicle's infotainment features."],
        **overrides,
    }


def provider_response(results=None, **overrides):
    return {
        "requestId": "exa-request-123",
        "results": [provider_result()] if results is None else results,
        "costDollars": {"total": 0.005},
        **overrides,
    }


def provider_client(cache, handler, api_key=API_KEY):
    return ExaClient(api_key=api_key, client=httpx.Client(transport=httpx.MockTransport(handler)), cache=cache)


def test_search_uses_scoped_bounded_official_request_and_returns_candidate(cache):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=provider_response())

    response = provider_client(cache, handler).search(search_request(
        trusted_domains=["bmwusa.com"],
        start_published_date=date(2024, 1, 1),
        end_published_date=date(2026, 1, 1),
        max_results=3,
    ))

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert str(request.url) == "https://api.exa.ai/search"
    assert request.headers["x-api-key"] == API_KEY
    payload = json.loads(request.content)
    assert payload["type"] == "auto"
    assert payload["numResults"] == 3
    assert payload["includeDomains"] == ["bmwusa.com"]
    assert payload["startPublishedDate"].startswith("2024-01-01")
    assert payload["endPublishedDate"].startswith("2026-01-01")
    assert payload["contents"]["highlights"] is True
    assert "G60" in payload["query"] and "US" in payload["query"]
    assert PUBLIC_QUERY in payload["query"]
    assert response["provider"] == "exa"
    assert response["persistence_status"] == "not_persisted"
    assert response["cache"] == {"hit": False, "stale": False}
    candidate = response["candidates"][0]
    assert candidate["candidate_id"]
    assert candidate["canonical_url"] == PUBLIC_URL
    assert candidate["original_url"] == PUBLIC_URL
    assert candidate["query"] == PUBLIC_QUERY
    assert candidate["search_query"] == payload["query"]
    assert candidate["vehicle"] == "G60" and candidate["market"] == "US"
    assert candidate["exa_result_id"] == "exa-public-bmw-page"
    assert candidate["publication_date"] is not None
    assert datetime.fromisoformat(candidate["retrieved_at"].replace("Z", "+00:00")).tzinfo is not None
    assert candidate["supporting_excerpt"]
    assert candidate["excerpt_hash"] == hashlib.sha256(candidate["supporting_excerpt"].encode()).hexdigest()
    assert candidate["review_status"] == "unreviewed"
    assert candidate["persisted"] is False
    assert "exa-request-123" in json.dumps(candidate["provider_metadata"])
    assert API_KEY not in json.dumps(response)


def test_missing_key_never_calls_provider(cache):
    requests = []
    client = provider_client(cache, lambda request: requests.append(request), api_key=None)
    with pytest.raises(EvidenceError) as error:
        client.search(search_request())
    assert error.value.code
    assert "EXA_API_KEY" in error.value.message
    assert requests == []


@pytest.mark.parametrize("status", [401, 402, 403, 429, 500, 503])
def test_provider_failures_are_clear_and_do_not_expose_raw_response(cache, status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": f"provider echoed {API_KEY}", "requestId": "failed-request"})

    with pytest.raises(EvidenceError) as error:
        provider_client(cache, handler).search(search_request())
    assert error.value.code
    assert error.value.message
    assert str(status) in error.value.message
    assert API_KEY not in str(error.value)
    assert API_KEY not in error.value.message
    assert "provider echoed" not in error.value.message
    assert len(calls) == 1


def test_provider_timeout_is_sanitized(cache):
    def handler(request):
        raise httpx.ReadTimeout(f"transport leaked {API_KEY}", request=request)

    with pytest.raises(EvidenceError) as error:
        provider_client(cache, handler).search(search_request())
    assert API_KEY not in error.value.message
    assert error.value.code


@pytest.mark.parametrize("payload", [{}, {"results": "invalid"}, ["invalid"]])
def test_malformed_provider_response_is_not_treated_as_empty_success(cache, payload):
    with pytest.raises(EvidenceError):
        provider_client(cache, lambda _: httpx.Response(200, json=payload)).search(search_request())


def test_non_json_provider_response_is_sanitized(cache):
    with pytest.raises(EvidenceError) as error:
        provider_client(cache, lambda _: httpx.Response(200, text=f"<html>{API_KEY}</html>")).search(search_request())
    assert API_KEY not in error.value.message


def test_oversized_provider_response_is_rejected(cache):
    with pytest.raises(EvidenceError) as error:
        provider_client(cache, lambda _: httpx.Response(200, content=b"x" * 2_000_001)).search(search_request())
    assert "size" in error.value.message.lower()


def test_empty_results_are_honest_and_missing_publication_date_is_not_invented(cache):
    empty = provider_client(cache, lambda _: httpx.Response(200, json=provider_response([]))).search(search_request())
    assert empty["candidates"] == []

    missing_date = provider_result()
    missing_date.pop("publishedDate")
    response = provider_client(cache, lambda _: httpx.Response(200, json=provider_response([missing_date]))).search(
        search_request(market="DE"),
    )
    assert response["candidates"][0]["publication_date"] is None


def test_canonical_url_dedupes_tracking_variants_but_preserves_page_query(cache):
    results = [
        provider_result(url="https://example.com/review?utm_source=demo#section"),
        provider_result(id="same-page", url="https://example.com/review?fbclid=tracking"),
        provider_result(id="page-one", url="https://example.com/review?page=1"),
        provider_result(id="page-two", url="https://example.com/review?page=2"),
    ]
    response = provider_client(cache, lambda _: httpx.Response(200, json=provider_response(results))).search(
        search_request(),
    )
    urls = [candidate["canonical_url"] for candidate in response["candidates"]]
    assert set(urls) == {
        "https://example.com/review",
        "https://example.com/review?page=1",
        "https://example.com/review?page=2",
    }
    assert len(urls) == 3


def test_repeated_search_and_new_client_without_key_reuse_cache(cache):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=provider_response())

    client = provider_client(cache, handler)
    first = client.search(search_request())
    second = client.search(search_request())
    offline = provider_client(cache, handler, api_key=None).search(search_request())
    assert len(requests) == 1
    assert second["cache"] == {"hit": True, "stale": False}
    assert offline["cache"] == {"hit": True, "stale": False}
    assert first["candidates"] == second["candidates"] == offline["candidates"]


def test_cache_only_miss_never_calls_provider(cache):
    requests = []
    with pytest.raises(EvidenceError):
        provider_client(cache, lambda request: requests.append(request)).search(search_request(cache_only=True))
    assert requests == []


def test_stale_evidence_requires_explicit_cache_only_replay(tmp_path, monkeypatch):
    clock = [1_000.0]
    monkeypatch.setattr(cache_module, "time", SimpleNamespace(time=lambda: clock[0]))
    cache = FileCache(tmp_path / "cache", ttl_seconds=10)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=provider_response())

    first = provider_client(cache, handler).search(search_request())
    clock[0] += 11
    offline = provider_client(cache, handler, api_key=None)
    with pytest.raises(EvidenceError):
        offline.search(search_request())
    replay = offline.search(search_request(cache_only=True))
    assert replay["cache"] == {"hit": True, "stale": True}
    assert replay["candidates"] == first["candidates"]
    assert len(requests) == 1


def test_cache_identity_includes_scope_domains_dates_and_result_count(cache):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=provider_response())

    client = provider_client(cache, handler)
    variants = [
        {},
        {"market": "DE"},
        {"vehicle": "G61"},
        {"trusted_domains": ["bmwusa.com"]},
        {"start_published_date": date(2025, 1, 1)},
        {"end_published_date": date(2025, 12, 31)},
        {"max_results": 2},
    ]
    for values in variants:
        client.search(search_request(**values))
    assert len(requests) == len(variants)
    for values in variants:
        assert client.search(search_request(**values))["cache"]["hit"] is True
    assert len(requests) == len(variants)


@pytest.mark.parametrize("changes", [
    {"public_data_confirmed": False},
    {"query": "BMW G60 customer alex.private@example.com infotainment complaint"},
    {"query": "BMW customer VIN WBA12345678901234 has a private complaint"},
    {"query": "BMW internal dataset 2025 customer comments"},
    {"vehicle": "alex.private@example.com"},
    {"query": "x" * 10_000},
    {"max_results": 0},
    {"max_results": 101},
    {"trusted_domains": ["localhost"]},
    {"start_published_date": date(2026, 1, 1), "end_published_date": date(2024, 1, 1)},
])
def test_unsafe_or_unbounded_search_never_calls_provider(cache, changes):
    requests = []
    data = {"query": PUBLIC_QUERY, "public_data_confirmed": True, **changes}
    client = provider_client(cache, lambda request: requests.append(request))
    with pytest.raises((EvidenceError, ValidationError)):
        client.search(SearchRequest(**data))
    assert requests == []
    assert not list(cache.directory.glob("*.json"))


def test_public_confirmation_is_required():
    with pytest.raises(ValidationError):
        SearchRequest(query=PUBLIC_QUERY)
    with pytest.raises(ValidationError):
        FetchRequest(identifier=PUBLIC_URL, query=PUBLIC_QUERY)


def test_fetch_uses_official_contents_body_and_preserves_candidate_state(cache):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=provider_response(
            statuses=[{"id": PUBLIC_URL, "status": "success", "source": "cached"}],
        ))

    response = provider_client(cache, handler).fetch(fetch_request())
    assert len(requests) == 1
    assert str(requests[0].url) == "https://api.exa.ai/contents"
    payload = json.loads(requests[0].content)
    assert payload.get("ids", payload.get("urls")) == [PUBLIC_URL]
    assert not ("ids" in payload and "urls" in payload)
    assert "contents" not in payload
    assert payload.get("highlights") is True or payload.get("text")
    candidate = response["candidates"][0]
    assert candidate["query"] == PUBLIC_QUERY
    assert candidate["review_status"] == "unreviewed"
    assert candidate["persisted"] is False


def test_fetch_known_exa_id_resolves_from_search_cache(cache):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=provider_response())

    client = provider_client(cache, handler)
    client.search(search_request())
    response = client.fetch(fetch_request(identifier="exa-public-bmw-page"))
    assert response["candidates"][0]["canonical_url"] == PUBLIC_URL
    assert len(requests) == 2
    assert str(requests[1].url) == "https://api.exa.ai/contents"


def test_fetched_content_is_reusable_without_key(cache):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=provider_response())

    first = provider_client(cache, handler).fetch(fetch_request())
    offline = provider_client(cache, handler, api_key=None).fetch(fetch_request())
    assert len(requests) == 1
    assert offline["cache"] == {"hit": True, "stale": False}
    assert offline["candidates"] == first["candidates"]


@pytest.mark.parametrize("identifier", [
    "unknown-provider-id",
    "http://localhost/internal",
    "http://127.0.0.1/internal",
    "http://10.0.0.1/private",
    "http://[::1]/internal",
    "https://username:password@example.com/private",
    "file:///etc/passwd",
])
def test_unknown_ids_and_nonpublic_urls_never_reach_provider(cache, identifier):
    requests = []
    client = provider_client(cache, lambda request: requests.append(request))
    with pytest.raises((EvidenceError, ValidationError)):
        client.fetch(fetch_request(identifier=identifier))
    assert requests == []


def test_contents_failure_status_is_not_treated_as_success(cache):
    response = provider_response([], statuses=[{
        "id": PUBLIC_URL,
        "status": "error",
        "error": {"tag": "CRAWL_NOT_FOUND", "httpStatusCode": 404},
    }])
    with pytest.raises(EvidenceError):
        provider_client(cache, lambda _: httpx.Response(200, json=response)).fetch(fetch_request())
