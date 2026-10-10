"""Exercise the HTTP adapter without contacting a database or external service."""

import httpx
import pytest

from mcp_server.backend_client import BackendClient
from mcp_server.errors import EvidenceError

SOURCE = {
    "id": "0a28d3a2-9437-4f50-a25d-5145757aa496",
    "title": "Public source fixture",
    "kind": "document",
    "reference": "https://example.com/bmw",
    "vehicle": "G60",
    "market": "US",
    "created_at": "2026-10-10T10:00:00Z",
}
PRIVATE_BODY = "private-provider-body api-key-DO-NOT-EXPOSE"


def assert_safe_error(error: EvidenceError) -> None:
    assert isinstance(error.code, str) and error.code.strip()
    assert isinstance(error.message, str) and error.message.strip()
    assert PRIVATE_BODY not in str(error)
    assert PRIVATE_BODY not in error.message


def test_source_reads_use_the_existing_routes_and_preserve_records():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=[SOURCE] if request.url.path == "/sources" else SOURCE)

    with httpx.Client(transport=httpx.MockTransport(handle)) as transport:
        client = BackendClient("http://backend.invalid/", client=transport)
        assert client.list_sources(vehicle="G60", market="US") == [SOURCE]
        assert client.get_source(SOURCE["id"]) == SOURCE

    assert [request.method for request in requests] == ["GET", "GET"]
    assert requests[0].url.path == "/sources"
    assert dict(requests[0].url.params) == {"vehicle": "G60", "market": "US"}
    assert requests[1].url.path == f"/sources/{SOURCE['id']}"


def test_optional_scope_is_omitted_and_filter_values_are_encoded():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=[])

    with httpx.Client(transport=httpx.MockTransport(handle)) as transport:
        client = BackendClient("http://backend.invalid", client=transport)
        assert client.list_sources() == []
        assert client.list_sources(vehicle="G60 M Sport", market="US/CA") == []

    assert not requests[0].url.query
    assert dict(requests[1].url.params) == {"vehicle": "G60 M Sport", "market": "US/CA"}


def test_imported_web_sources_keep_backend_provenance_and_long_references():
    source = {
        **SOURCE,
        "kind": "web",
        "reference": "https://example.com/research?reference=" + "a" * 900,
        "metadata": {"provider": "exa", "published_at": None, "retrieved_at": "2026-10-10T11:00:00Z"},
        "content_hash": "a" * 64,
        "observed_at": None,
        "original_path": "snapshot.json",
    }

    def handle(request):
        return httpx.Response(200, json=source if request.url.path.endswith(SOURCE["id"]) else [source])

    with httpx.Client(transport=httpx.MockTransport(handle)) as transport:
        client = BackendClient("http://backend.invalid", client=transport)
        assert client.get_source(SOURCE["id"]) == source
        assert client.list_sources() == [source]


def test_source_identifier_cannot_add_query_or_fragment():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=SOURCE)

    identifier = "source?reserved#characters"
    with httpx.Client(transport=httpx.MockTransport(handle)) as transport:
        client = BackendClient("http://backend.invalid", client=transport)
        assert client.get_source(identifier) == SOURCE

    assert requests[0].url.raw_path == b"/sources/source%3Freserved%23characters"
    assert requests[0].url.query == b""
    assert requests[0].url.fragment == ""


@pytest.mark.parametrize("identifier", ["", ".", "..", "../health", "\\health", "source\nheader"])
def test_invalid_source_paths_are_rejected_before_network_access(identifier):
    def handle(request):
        pytest.fail("Invalid source paths must not make an HTTP request")

    with httpx.Client(transport=httpx.MockTransport(handle)) as transport:
        client = BackendClient("http://backend.invalid", client=transport)
        with pytest.raises(EvidenceError) as raised:
            client.get_source(identifier)
    assert_safe_error(raised.value)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422, 429, 500, 503])
def test_http_failures_are_actionable_without_exposing_response_bodies(status):
    def handle(request):
        return httpx.Response(status, text=PRIVATE_BODY)

    with httpx.Client(transport=httpx.MockTransport(handle)) as transport:
        client = BackendClient("http://backend.invalid", client=transport)
        with pytest.raises(EvidenceError) as raised:
            client.get_source(SOURCE["id"])
    assert_safe_error(raised.value)


@pytest.mark.parametrize("exception", [httpx.ReadTimeout, httpx.ConnectError])
def test_transport_failures_are_safe_evidence_errors(exception):
    def handle(request):
        raise exception(PRIVATE_BODY, request=request)

    with httpx.Client(transport=httpx.MockTransport(handle)) as transport:
        client = BackendClient("http://backend.invalid", client=transport)
        with pytest.raises(EvidenceError) as raised:
            client.list_sources()
    assert_safe_error(raised.value)


@pytest.mark.parametrize("method", ["list_sources", "get_source"])
def test_invalid_json_is_not_returned_as_evidence(method):
    def handle(request):
        return httpx.Response(200, text=PRIVATE_BODY)

    with httpx.Client(transport=httpx.MockTransport(handle)) as transport:
        client = BackendClient("http://backend.invalid", client=transport)
        with pytest.raises(EvidenceError) as raised:
            getattr(client, method)(*([SOURCE["id"]] if method == "get_source" else []))
    assert_safe_error(raised.value)


@pytest.mark.parametrize(
    ("method", "body"),
    [("list_sources", {}), ("list_sources", ["not a source"]), ("get_source", []), ("get_source", None)],
)
def test_unexpected_backend_shapes_fail_closed(method, body):
    def handle(request):
        return httpx.Response(200, json=body)

    with httpx.Client(transport=httpx.MockTransport(handle)) as transport:
        client = BackendClient("http://backend.invalid", client=transport)
        with pytest.raises(EvidenceError) as raised:
            getattr(client, method)(*([SOURCE["id"]] if method == "get_source" else []))
    assert_safe_error(raised.value)


def test_backend_redirects_are_not_followed():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(307, headers={"location": "https://unexpected.example/private"})

    with httpx.Client(transport=httpx.MockTransport(handle)) as transport:
        client = BackendClient("http://backend.invalid", client=transport)
        with pytest.raises(EvidenceError) as raised:
            client.list_sources()
    assert_safe_error(raised.value)
    assert len(requests) == 1


def test_oversized_backend_response_is_rejected_before_json_parsing():
    def handle(request):
        return httpx.Response(200, content=b" " * 2_000_001)

    with httpx.Client(transport=httpx.MockTransport(handle)) as transport:
        client = BackendClient("http://backend.invalid", client=transport)
        with pytest.raises(EvidenceError) as raised:
            client.list_sources()
    assert_safe_error(raised.value)
    assert "size" in raised.value.message.lower()
