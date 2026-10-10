"""Small, bounded JSON requests; errors deliberately omit response bodies."""

import json

import httpx

from mcp_server.errors import EvidenceError


def request_json(client: httpx.Client, method: str, url: str, *, service: str, **kwargs):
    try:
        with client.stream(method, url, follow_redirects=False, **kwargs) as response:
            status = response.status_code
            if not 200 <= status < 300:
                codes = {401: "AUTHENTICATION_FAILED", 403: "ACCESS_DENIED", 402: "CREDITS_EXHAUSTED",
                         404: "NOT_FOUND", 429: "RATE_LIMITED"}
                code = codes.get(status, "UNAVAILABLE" if status >= 500 else "REQUEST_REJECTED")
                raise EvidenceError(f"{service}_{code}", f"{service} returned HTTP {status}; no automatic retry was made.")
            chunks = bytearray()
            for chunk in response.iter_bytes(chunk_size=65536):
                chunks.extend(chunk)
                if len(chunks) > 2_000_000:
                    raise EvidenceError(f"{service}_INVALID_RESPONSE", f"{service} response exceeded the size limit.")
            try:
                return json.loads(chunks)
            except (ValueError, UnicodeError):
                raise EvidenceError(f"{service}_INVALID_RESPONSE", f"{service} returned invalid JSON.") from None
    except httpx.TimeoutException:
        raise EvidenceError(f"{service}_TIMEOUT", f"{service} request timed out; retry explicitly if appropriate.") from None
    except httpx.HTTPError:
        raise EvidenceError(f"{service}_UNAVAILABLE", f"{service} could not be reached.") from None
