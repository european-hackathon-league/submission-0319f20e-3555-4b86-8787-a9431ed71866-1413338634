import socket
import ssl
import threading
import time
from email.message import Message

import pytest

from server import web_fetch


def dns(address="93.184.216.34"):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:secret@example.org", "https://@example.org",
                                 "http://example.org:8000", "https://example.org:0", "https://[invalid", "https://example.org/a b",
                                 "https://example.org/" + "a" * 2000])
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


def test_tls_verification_and_host_header_keep_the_original_hostname(monkeypatch):
    seen = {"request": b""}

    class Socket:
        def setsockopt(self, *args):
            pass

        def sendall(self, data):
            seen["request"] += data

        def close(self):
            pass

    def connect(address, **kwargs):
        seen["address"] = address
        return Socket()

    def wrap(context, sock, *, server_hostname):
        assert context.check_hostname
        assert context.verify_mode == ssl.CERT_REQUIRED
        seen["tls_hostname"] = server_hostname
        return sock

    class Response:
        status = 200
        headers = Message()
        headers["Content-Type"] = "text/plain; charset=utf-8"

        def getheader(self, name, default=None):
            return self.headers.get(name, default)

        def read(self, limit):
            return b"Research"

    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: dns())
    monkeypatch.setattr(socket, "create_connection", connect)
    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", wrap)
    monkeypatch.setattr(web_fetch.http.client.HTTPSConnection, "getresponse", lambda self: Response())
    web_fetch.fetch_snapshot("https://bücher.example/résumé?q=café")
    assert seen["address"] == ("93.184.216.34", 443)
    assert seen["tls_hostname"] == "xn--bcher-kva.example"
    assert b"Host: xn--bcher-kva.example\r\n" in seen["request"]
    assert b"GET /r%C3%A9sum%C3%A9?q=caf%C3%A9 HTTP/1.1\r\n" in seen["request"]


def test_fetched_page_enters_same_evidence_pipeline(client, monkeypatch):
    content = " \n<p>Charging research snapshot</p>\n "
    monkeypatch.setattr(web_fetch, "fetch_snapshot", lambda _: {"url": "https://example.org/final", "content": content})
    response = client.post("/imports/web-fetch", json={"url": "https://example.org/start", "title": "Research"})
    assert response.status_code == 201, response.text
    record = client.get("/evidence").json()["items"][0]
    assert record["location"]["url"] == "https://example.org/final"
    assert record["content"] == "Charging research snapshot"
    original = client.get(f"/sources/{record['source_id']}/original").json()
    assert original == {"url": "https://example.org/final", "content": content, "observed_at": None}


@pytest.fixture
def page(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: dns())

    class Response:
        status = 200

        def __init__(self):
            self.headers = Message()
            self.headers["Content-Type"] = "text/html; charset=utf-8"
            self.raw = b"<p>Research</p>"

        def getheader(self, name, default=None):
            return self.headers.get(name, default)

        def read(self, limit):
            return self.raw[:limit]

    response = Response()

    class Connection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return response

        def close(self):
            pass

    monkeypatch.setattr(web_fetch.http.client, "HTTPSConnection", Connection)
    return response


@pytest.mark.parametrize("headers,raw,message", [
    ({"Content-Type": "application/pdf"}, b"PDF", "HTML or text"),
    ({"Content-Encoding": "gzip"}, b"compressed", "Compressed"),
    ({"Content-Type": "text/html; charset=not-an-encoding"}, b"text", "encoding"),
    ({"Content-Type": "text/html; charset=utf-8"}, b"\xff", "encoding"),
    ({}, b"x" * (web_fetch.MAX_WEB_BYTES + 1), "1 MB"),
    ({}, b"x" * 500_001, "500,000"),
])
def test_unusable_or_oversized_pages_are_rejected(page, headers, raw, message):
    for name, value in headers.items():
        if name in page.headers:
            page.headers.replace_header(name, value)
        else:
            page.headers[name] = value
    page.raw = raw
    with pytest.raises(web_fetch.WebFetchError, match=message):
        web_fetch.fetch_snapshot("https://example.org/research")


def test_declared_encoding_keeps_the_decoded_snapshot_exact(page):
    page.headers.replace_header("Content-Type", "text/plain; charset=iso-8859-1")
    page.raw = b" \nCharging caf\xe9 research\n "
    assert web_fetch.fetch_snapshot("https://example.org/research")["content"] == " \nCharging café research\n "


def test_incomplete_page_is_never_imported_as_a_snapshot(page):
    client_socket, server_socket = socket.socketpair()
    try:
        server_socket.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 100\r\n\r\npartial")
        server_socket.shutdown(socket.SHUT_WR)
        response = web_fetch.http.client.HTTPResponse(client_socket)
        response.begin()

        def read(limit):
            raw = response.read(limit)
            page.length = response.length
            return raw

        page.read = read
        with pytest.raises(web_fetch.WebFetchError, match="declared content length"):
            web_fetch.fetch_snapshot("https://example.org/research")
        response.close()
    finally:
        client_socket.close()
        server_socket.close()


@pytest.mark.parametrize("location", [None, "https://example.org/again"])
def test_missing_and_excessive_redirects_are_rejected(page, location):
    page.status = 302
    if location:
        page.headers["Location"] = location
    with pytest.raises(web_fetch.WebFetchError, match="redirect"):
        web_fetch.fetch_snapshot("https://example.org/research")


def test_invalid_fetch_metadata_never_reaches_network(client, monkeypatch):
    requests = []
    monkeypatch.setattr(web_fetch, "fetch_snapshot", lambda url: requests.append(url))
    for extra in ({"observed_at": "yesterday"}, {"actor": "x" * 201}):
        response = client.post("/imports/web-fetch", json={"url": "https://example.org", "title": "Research", **extra})
        assert response.status_code == 422, response.text
    assert requests == []


def test_dns_lookup_has_an_overall_deadline(monkeypatch):
    release = threading.Event()
    finished = threading.Event()

    def blocked_resolver(*args, **kwargs):
        release.wait(1)
        finished.set()
        return dns()

    monkeypatch.setattr(socket, "getaddrinfo", blocked_resolver)
    monkeypatch.setattr(web_fetch, "MAX_FETCH_SECONDS", 0.05)
    try:
        with pytest.raises(web_fetch.WebFetchError, match="time limit"):
            web_fetch.fetch_snapshot("https://example.org/research")
    finally:
        release.set()
        assert finished.wait(1)


@pytest.mark.parametrize("phase", ["headers", "body"])
def test_slow_response_is_interrupted_at_overall_deadline(monkeypatch, phase):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    finished = threading.Event()

    def connect_to_test_server(*args, **kwargs):
        connection = socket.socket()
        connection.settimeout(1)
        connection.connect(listener.getsockname())
        return connection

    def server():
        try:
            with listener.accept()[0] as server_socket:
                server_socket.settimeout(1)
                request = b""
                while b"\r\n\r\n" not in request:
                    request += server_socket.recv(4096)
                if phase == "body":
                    server_socket.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
                                          b"Content-Length: 10\r\nConnection: close\r\n\r\na")
                else:
                    server_socket.sendall(b"HTTP/1.1 200")
                server_socket.recv(1)  # The deadline shuts down the client socket.
        finally:
            finished.set()

    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: dns())
    monkeypatch.setattr(socket, "create_connection", connect_to_test_server)
    monkeypatch.setattr(web_fetch, "MAX_FETCH_SECONDS", 0.1)
    threading.Thread(target=server, daemon=True).start()
    started = time.monotonic()
    try:
        with pytest.raises(web_fetch.WebFetchError, match="time limit"):
            web_fetch.fetch_snapshot("http://example.org/research")
        assert time.monotonic() - started < 1
    finally:
        listener.close()
        assert finished.wait(1)
