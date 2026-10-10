"""Fetch an explicitly selected public research page as an immutable source snapshot."""

import http.client
import ipaddress
import queue
import socket
import threading
import time
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException
from pydantic import Field, field_validator

from server.evidence import web_import
from server.models import Scope, Text, WebImport, observed_date

router = APIRouter()
MAX_WEB_BYTES = 1_000_000
MAX_FETCH_SECONDS = 30
# Timed-out OS resolver calls cannot be cancelled. Bound the number of workers
# they can occupy, and use daemon threads so they cannot hold service shutdown.
_RESOLVER_SLOTS = threading.BoundedSemaphore(8)


class WebFetchRequest(Scope):
    url: Text = Field(max_length=2000)
    title: Text = Field(max_length=200)
    observed_at: str | None = None
    actor: Text = Field(default="PM", max_length=200)

    _validate_observed_at = field_validator("observed_at")(observed_date)


class WebFetchError(ValueError):
    pass


def remaining_time(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise WebFetchError("Research page retrieval exceeded its time limit")
    return remaining


def resolve_target(hostname, port, deadline):
    remaining_time(deadline)
    if not _RESOLVER_SLOTS.acquire(blocking=False):
        raise WebFetchError("Research hostname resolver is busy; retry later")
    result = queue.Queue(maxsize=1)

    def resolve():
        try:
            result.put(socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM))
        except Exception as exc:
            result.put(exc)
        finally:
            _RESOLVER_SLOTS.release()

    threading.Thread(target=resolve, daemon=True).start()
    try:
        answers = result.get(timeout=remaining_time(deadline))
    except queue.Empty:
        raise WebFetchError("Research page retrieval exceeded its time limit") from None
    if isinstance(answers, Exception):
        raise answers
    return answers


def public_target(url, *, deadline=None):
    try:
        parsed = urlsplit(url)
        if (len(url) > 2000 or parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or any(char.isspace() or ord(char) < 32 for char in url)):
            raise WebFetchError("Use a public HTTP(S) URL without credentials")
        hostname = parsed.hostname.encode("idna").decode("ascii")
        port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
        if port != (443 if parsed.scheme == "https" else 80):
            raise WebFetchError("Selected web sources must use the standard HTTP(S) port")
        answers = resolve_target(hostname, port, deadline if deadline is not None else time.monotonic() + MAX_FETCH_SECONDS)
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
    deadline = time.monotonic() + MAX_FETCH_SECONDS
    for _ in range(4):
        scheme, hostname, port, address, path = public_target(current, deadline=deadline)
        factory = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
        connection = factory(hostname, port=port, timeout=min(15, remaining_time(deadline)))
        # Pin the validated address. TLS still verifies the original hostname;
        # redirects are revalidated, and environment proxy settings are unused.
        connection._create_connection = lambda destination, timeout, source_address=None: socket.create_connection(
            (address, port), timeout=timeout, source_address=source_address)
        expired = threading.Event()
        socket_holder = [None]

        def expire(connection=connection, expired=expired, socket_holder=socket_holder):
            expired.set()
            # A socket read timeout restarts on every received byte. Shutdown
            # interrupts slow headers and bodies at the overall deadline too.
            sock = getattr(connection, "sock", None) or socket_holder[0]
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        timer = threading.Timer(remaining_time(deadline), expire)
        timer.daemon = True
        timer.start()
        try:
            connection.request("GET", path, headers={"User-Agent": "BMW-Evidence-Research/0.2", "Accept-Encoding": "identity"})
            # getresponse() detaches the socket on Connection: close replies;
            # retain it so the deadline also interrupts those response bodies.
            socket_holder[0] = getattr(connection, "sock", None)
            response = connection.getresponse()
            remaining_time(deadline)
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
            if response.getheader("Content-Encoding", "identity").strip().lower() not in ("identity", ""):
                raise WebFetchError("Compressed web responses are not supported; import a decoded snapshot")
            raw = response.read(MAX_WEB_BYTES + 1)
            remaining_time(deadline)
            if len(raw) > MAX_WEB_BYTES:
                raise WebFetchError("Research page exceeds the 1 MB limit")
            if getattr(response, "length", None):
                raise WebFetchError("Research page ended before its declared content length")
            charset = response.headers.get_content_charset() or "utf-8"
            try:
                text = raw.decode(charset)
            except (LookupError, UnicodeError):
                raise WebFetchError("Research page cannot be decoded using its declared character encoding") from None
            if len(text) > 500_000:
                raise WebFetchError("Research page exceeds the 500,000 character limit")
            return {"url": current, "content": text}
        except (OSError, http.client.HTTPException):
            if expired.is_set():
                raise WebFetchError("Research page retrieval exceeded its time limit") from None
            raise WebFetchError("Could not retrieve the selected research page") from None
        finally:
            timer.cancel()
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
