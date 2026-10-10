import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from mcp.server import MCPServer


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
mcp = MCPServer("BMW Product Evidence")


def api_get(path: str) -> dict | list:
    try:
        with urlopen(f"{API_BASE_URL}{path}", timeout=10) as response:
            return json.load(response)
    except HTTPError as exc:
        raise ValueError(f"API returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise ConnectionError(f"Cannot reach API at {API_BASE_URL}") from exc


@mcp.tool()
def list_sources(vehicle: str | None = None, market: str | None = None) -> list[dict]:
    """List imported source records, optionally filtered by vehicle or market."""
    params = {key: value for key, value in {"vehicle": vehicle, "market": market}.items() if value is not None}
    query = "?" + urlencode(params) if params else ""
    return api_get(f"/sources{query}")


@mcp.tool()
def get_source(source_id: str) -> dict:
    """Get one source record by its ID."""
    from urllib.parse import quote

    return api_get(f"/sources/{quote(source_id, safe='')}")


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8001, json_response=True, stateless_http=True)
