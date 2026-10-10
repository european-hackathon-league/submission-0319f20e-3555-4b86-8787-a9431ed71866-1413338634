"""One explicit, bounded live Exa request; never required for offline demos."""

import json
import os
import tempfile
from pathlib import Path

from mcp_server.cache import FileCache
from mcp_server.errors import EvidenceError
from mcp_server.exa_client import ExaClient
from mcp_server.models import SearchRequest


def main():
    if not os.environ.get("EXA_API_KEY", "").strip():
        raise SystemExit("EXA_API_KEY is not configured; live smoke skipped. No provider request was made.")
    output = Path(os.environ.get("EXA_CACHE_DIR", str(Path.home() / ".cache" / "bmw-mcp" / "exa")))
    # A temporary cache ensures this explicitly requested smoke is one live request.
    with tempfile.TemporaryDirectory(prefix="bmw-exa-smoke-") as directory:
        try:
            result = ExaClient(cache=FileCache(Path(directory))).search(SearchRequest(
                query="BMW 5 Series charging features", vehicle="G60", market="US",
                trusted_domains=["bmwusa.com"], max_results=1, public_data_confirmed=True,
            ))
        except EvidenceError as exc:
            raise SystemExit(str(exc)) from None
        output.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Copy through FileCache so the smoke also becomes a reusable exact-request cache.
        for entry in Path(directory).glob("*.json"):
            destination = output / entry.name
            with destination.open("w", encoding="utf-8") as handle:
                os.chmod(destination, 0o600)
                handle.write(entry.read_text(encoding="utf-8"))
        print(json.dumps({"provider": result["provider"], "request_metadata": result["request_metadata"],
                          "candidates": result["candidates"], "cache_directory": str(output)}, indent=2))


if __name__ == "__main__":
    main()
