"""Fetch an explicitly selected public research page as an immutable source snapshot."""

import http.client
import ipaddress
import socket
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException
from pydantic import Field

from server.evidence import web_import
from server.models import Scope, Text, WebImport

router = APIRouter()
MAX_WEB_BYTES = 1_000_000


class WebFetchRequest(Scope):
    url: Text = Field(max_length=2000)
    title: Text = Field(max_length=200)
    observed_at: str | None = None
    actor: Text = "PM"


class WebFetchError(ValueError):
    pass


def public_target(url):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password
                or any(ord(char) < 32 for char in url)):
            raise WebFetchError("Use a public HTTP(S) URL without credentials")
        hostname = parsed.hostname.encode("idna").decode("ascii")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if port != (443 if parsed.scheme == "https" else 80):
            raise WebFetchError("Selected web sources must use the standard HTTP(S) port")
        answers = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        addresses = sorted({answer[4][0] for answer in answers})
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise WebFetchError("Selected web sources must resolve exclusively to public internet addresses")
        path = urlunsplit(("", "", quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~"),
                           quote(parsed.query, safe="%=&?/:@!$'()*+,;~-._"), ""))
        return parsed.scheme, hostname, port, addresses[0], path
    except (ValueError, UnicodeError, OSError) as exc:
        if isinstance(exc, WebFetchError):
            raise
        raise WebFetchError("Cannot resolve a valid public source URL") from None


def fetch_snapshot(url):
    current = url
    for _ in range(4):
        scheme, hostname, port, address, path = public_target(current)
        factory = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
        connection = factory(hostname, port=port, timeout=15)
        # Pin the validated address. TLS still verifies the original hostname;
        # redirects are revalidated, and environment proxy settings are unused.
        connection._create_connection = lambda destination, timeout, source_address=None: socket.create_connection(
            (address, port), timeout=timeout, source_address=source_address)
        try:
            connection.request("GET", path, headers={"User-Agent": "BMW-Evidence-Research/0.2", "Accept-Encoding": "identity"})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise WebFetchError("Research page returned a redirect without a destination")
                current = urljoin(current, location)
                continue
            if response.status != 200:
                raise WebFetchError(f"Research page returned HTTP {response.status}")
            media_type = response.headers.get_content_type()
            if media_type not in ("text/html", "text/plain", "text/markdown", "application/xhtml+xml"):
                raise WebFetchError("Selected URL must be an HTML or text page; use file import for PDFs")
            if response.getheader("Content-Encoding", "identity").lower() not in ("identity", ""):
                raise WebFetchError("Compressed web responses are not supported; import a decoded snapshot")
            raw = response.read(MAX_WEB_BYTES + 1)
            if len(raw) > MAX_WEB_BYTES:
                raise WebFetchError("Research page exceeds the 1 MB limit")
            charset = response.headers.get_content_charset() or "utf-8"
            try:
                text = raw.decode(charset)
            except (LookupError, UnicodeError):
                raise WebFetchError("Research page cannot be decoded using its declared character encoding") from None
            if len(text) > 500_000:
                raise WebFetchError("Research page exceeds the 500,000 character limit")
            return {"url": current, "content": text}
        except (OSError, http.client.HTTPException):
            raise WebFetchError("Could not retrieve the selected research page") from None
        finally:
            connection.close()
    raise WebFetchError("Research page has too many redirects")


@router.post("/imports/web-fetch", status_code=201)
def fetch_web_source(command: WebFetchRequest):
    try:
        snapshot = fetch_snapshot(command.url)
        imported = WebImport(**command.model_dump(exclude={"url"}), **snapshot)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return web_import(imported)
