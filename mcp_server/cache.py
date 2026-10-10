"""Bounded local cache of public candidates, never the application's evidence DB."""

import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from mcp_server.models import digest

CACHE_VERSION = 1
MAX_ENTRY_BYTES = 2_000_000


@dataclass(frozen=True)
class CacheHit:
    value: dict
    stale: bool


class FileCache:
    def __init__(self, directory: Path, ttl_seconds: int = 86400, max_entries: int = 128):
        if ttl_seconds < 0 or not 1 <= max_entries <= 1024:
            raise ValueError("Invalid cache limits")
        self.directory = Path(directory)
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries

    def _path(self, key: str) -> Path:
        return self.directory / f"{digest(key)}.json"

    def _owned_paths(self):
        return (path for path in self.directory.glob("*.json")
                if re.fullmatch(r"[0-9a-f]{64}\.json", path.name) and not path.is_symlink())

    def _read(self, path: Path, allow_stale: bool) -> CacheHit | None:
        try:
            if path.is_symlink() or path.stat().st_size > MAX_ENTRY_BYTES:
                return None
            entry = json.loads(path.read_text(encoding="utf-8"))
            if entry["version"] != CACHE_VERSION or not isinstance(entry["value"], dict):
                return None
            stored_at = float(entry["stored_at"])
            if not 0 <= stored_at <= time.time() + 60:
                return None
            stale = time.time() - stored_at > self.ttl_seconds
            return CacheHit(entry["value"], stale) if allow_stale or not stale else None
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def get(self, key: str, allow_stale: bool = False) -> CacheHit | None:
        return self._read(self._path(key), allow_stale)

    def set(self, key: str, value: dict) -> bool:
        """Cache failure does not discard a successfully retrieved candidate."""
        temporary = None
        try:
            payload = json.dumps({"version": CACHE_VERSION, "stored_at": time.time(), "value": value}, allow_nan=False)
            if len(payload.encode("utf-8")) > MAX_ENTRY_BYTES:
                return False
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory, delete=False) as handle:
                temporary = handle.name
                handle.write(payload)
            os.replace(temporary, self._path(key))
            temporary = None
            entries = sorted(self._owned_paths(), key=lambda path: path.stat().st_mtime)
            for path in entries[:-self.max_entries]:
                path.unlink(missing_ok=True)
            return True
        except (OSError, ValueError, TypeError):
            return False
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    def candidates(self):
        for path in self._owned_paths():
            entry = self._read(path, allow_stale=True)
            if entry:
                candidates = entry.value.get("candidates", [])
                if isinstance(candidates, list):
                    yield from (item for item in candidates if isinstance(item, dict))
