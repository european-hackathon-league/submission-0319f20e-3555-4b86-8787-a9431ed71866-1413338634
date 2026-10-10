"""Cache storage remains separate from backend persistence and preserves provenance."""

import json
import stat
from types import SimpleNamespace

import pytest

import mcp_server.cache as cache_module
from mcp_server.cache import FileCache


def test_cache_roundtrip_survives_new_instance(tmp_path):
    path = tmp_path / "cache"
    value = {"candidates": [{"candidate_id": "candidate-1", "retrieved_at": "2025-01-01T00:00:00Z"}]}
    FileCache(path).set("request-1", value)
    hit = FileCache(path).get("request-1")
    assert hit is not None
    assert hit.value == value
    assert hit.stale is False
    assert FileCache(path).get("missing") is None


def test_cache_keys_do_not_collide_or_become_filesystem_paths(tmp_path):
    cache = FileCache(tmp_path / "cache")
    cache.set("../outside.json", {"value": "first"})
    cache.set("different-request", {"value": "second"})
    assert cache.get("../outside.json").value == {"value": "first"}
    assert cache.get("different-request").value == {"value": "second"}
    assert not (tmp_path / "outside.json").exists()


def test_cache_caps_number_of_requests(tmp_path):
    cache = FileCache(tmp_path / "cache", max_entries=2)
    for number in range(5):
        cache.set(f"request-{number}", {"number": number})
    hits = [cache.get(f"request-{number}") for number in range(5)]
    assert sum(hit is not None for hit in hits) <= 2
    assert cache.get("request-4").value == {"number": 4}


def test_cache_discovers_known_provider_candidates(tmp_path):
    cache = FileCache(tmp_path / "cache")
    candidate = {"candidate_id": "candidate-1", "exa_result_id": "exa-1", "canonical_url": "https://example.com/"}
    cache.set("search", {"candidates": [candidate]})
    cache.set("empty", {"candidates": []})
    assert candidate in list(cache.candidates())


def test_expired_cache_requires_explicit_stale_access_without_changing_provenance(tmp_path, monkeypatch):
    clock = [1_000.0]
    monkeypatch.setattr(cache_module, "time", SimpleNamespace(time=lambda: clock[0]))
    cache = FileCache(tmp_path / "cache", ttl_seconds=10)
    value = {"candidates": [{"retrieved_at": "2025-01-01T00:00:00Z"}]}
    cache.set("request", value)
    assert cache.get("request").stale is False
    clock[0] += 11
    assert cache.get("request") is None
    stale = cache.get("request", allow_stale=True)
    assert stale.stale is True
    assert stale.value == value


def test_corrupt_cache_is_a_miss(tmp_path):
    directory = tmp_path / "cache"
    cache = FileCache(directory)
    cache.set("request", {"candidates": []})
    path = next(directory.glob("*.json"))
    path.write_text("not valid JSON", encoding="utf-8")
    assert cache.get("request") is None
    assert list(cache.candidates()) == []


@pytest.mark.parametrize("mutation", [{"version": 999}, {"stored_at": 1e99}, {"stored_at": "nan"}])
def test_future_or_unknown_format_cache_is_not_trusted(tmp_path, mutation):
    directory = tmp_path / "cache"
    cache = FileCache(directory)
    cache.set("request", {"candidates": []})
    path = next(directory.glob("*.json"))
    entry = json.loads(path.read_text())
    entry.update(mutation)
    path.write_text(json.dumps(entry), encoding="utf-8")
    assert cache.get("request", allow_stale=True) is None


def test_cache_files_are_private_and_symlinks_are_not_read(tmp_path):
    directory = tmp_path / "cache"
    cache = FileCache(directory)
    cache.set("request", {"candidates": []})
    path = next(directory.glob("*.json"))
    assert stat.S_IMODE(directory.stat().st_mode) & 0o077 == 0
    assert stat.S_IMODE(path.stat().st_mode) & 0o077 == 0
    original = path.read_text()
    outside = tmp_path / "other.json"
    outside.write_text(original, encoding="utf-8")
    path.unlink()
    path.symlink_to(outside)
    assert cache.get("request") is None


def test_oversized_cache_value_is_not_written(tmp_path):
    cache = FileCache(tmp_path / "cache")
    assert cache.set("huge", {"text": "x" * (cache_module.MAX_ENTRY_BYTES + 1)}) is False
    assert cache.get("huge") is None
