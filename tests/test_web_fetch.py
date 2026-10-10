import socket
from email.message import Message

import pytest

from server import web_fetch


def dns(address="93.184.216.34"):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:secret@example.org", "http://example.org:8000", "https://[invalid"])
def test_invalid_web_urls_are_rejected(url):
    with pytest.raises(web_fetch.WebFetchError):
        web_fetch.public_target(url)


def test_private_and_mixed_dns_are_rejected(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: dns("127.0.0.1"))
    with pytest.raises(web_fetch.WebFetchError, match="public"):
        web_fetch.public_target("http://internal.example")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: dns() + dns("10.0.0.1"))
    with pytest.raises(web_fetch.WebFetchError, match="public"):
        web_fetch.public_target("https://mixed.example")


def test_fetch_pins_dns_preserves_html_and_checks_redirects(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: dns())
    seen = []

    class Response:
        status = 200
        headers = Message()
        headers["Content-Type"] = "text/html; charset=utf-8"

        def getheader(self, name, default=None):
            return self.headers.get(name, default)

        def read(self, limit):
            return b"<p>Customer charging research</p>"

    class Connection:
        def __init__(self, host, **kwargs):
            seen.append(host)

        def request(self, method, path, headers):
            self._create_connection(("rebinding.example", 443), 1)

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(socket, "create_connection", lambda address, **kwargs: seen.append(address))
    monkeypatch.setattr(web_fetch.http.client, "HTTPSConnection", Connection)
    result = web_fetch.fetch_snapshot("https://example.org/research")
    assert result["content"] == "<p>Customer charging research</p>"
    assert seen == ["example.org", ("93.184.216.34", 443)]
    Response.status = 302
    Response.headers["Location"] = "http://127.0.0.1"
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *args, **kwargs: dns(host) if host == "127.0.0.1" else dns())
    with pytest.raises(web_fetch.WebFetchError, match="public"):
        web_fetch.fetch_snapshot("https://example.org/research")


def test_fetched_page_enters_same_evidence_pipeline(client, monkeypatch):
    monkeypatch.setattr(web_fetch, "fetch_snapshot", lambda _: {"url": "https://example.org/final", "content": "<p>Charging research snapshot</p>"})
    response = client.post("/imports/web-fetch", json={"url": "https://example.org/start", "title": "Research"})
    assert response.status_code == 201, response.text
    record = client.get("/evidence").json()["items"][0]
    assert record["location"]["url"] == "https://example.org/final"
    assert record["content"] == "Charging research snapshot"
