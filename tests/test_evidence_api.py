import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pytest

from database.store import connect
from server.evidence import import_records
from server.models import RecordsImport


def records_payload(**overrides):
    return {"title": "Charging interviews", "kind": "feedback", "reference": "sample-interviews",
            "vehicle": "G60", "market": "US", "records": [
                {"content": "Public charging is confusing", "location": {"sheet": "Feedback", "row": 2},
                 "vehicle": "G60", "market": "US", "metadata": {"sentiment": "problem", "topic": "charging"}}], **overrides}


def test_import_deduplicates_and_preserves_location_original_and_audit(client):
    payload = records_payload()
    first = client.post("/imports/records", json=payload)
    assert first.status_code == 201, first.text
    assert first.json()["record_count"] == 1
    second = client.post("/imports/records", json=payload).json()
    assert second["deduplicated"] is True
    assert second["source_id"] == first.json()["source_id"]
    source = client.get("/sources/" + second["source_id"]).json()
    assert source["content_hash"] == first.json()["sha256"]
    evidence = client.get("/evidence", params={"source_id": source["id"]}).json()
    assert evidence["total"] == 1
    record = evidence["items"][0]
    assert record["location"] == {"sheet": "Feedback", "row": 2}
    assert record["observed_at"] is None
    assert client.get("/sources/" + source["id"] + "/original").status_code == 200
    assert client.get("/evidence/" + record["id"]).json()["content"] == payload["records"][0]["content"]
    assert client.get("/evidence?q=nonexistent").json()["total"] == 0
    assert client.get("/evidence?market=CN").json()["total"] == 0


def test_import_rejects_mixed_scope_and_traversal(client):
    payload = records_payload(market="CN")
    assert client.post("/imports/records", json=payload).status_code == 422
    assert client.get("/sources").json() == []
    assert client.post("/imports/local", json={"path": "../../.env"}).status_code == 422
    assert client.get("/evidence/missing").status_code == 404
    assert client.get("/sources/missing/original").status_code == 404


def test_parallel_duplicate_imports_are_atomic(db):
    command = RecordsImport.model_validate(records_payload())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: import_records(command), range(4)))
    assert len({item["source_id"] for item in results}) == 1
    assert sum(not item["deduplicated"] for item in results) == 1


def test_invalid_form_inputs_are_validation_errors(client):
    data = b"Feedback,Vehicle,Market\nSeat is uncomfortable,G60,US\n"
    response = client.post("/imports/files", files={"file": ("feedback.csv", data)}, data={"kind": "invalid"})
    assert response.status_code == 422


def test_web_snapshot_links_url_and_retains_original(client):
    response = client.post("/imports/web", json={"url": "https://example.org/research", "title": "Selected research",
                                                 "content": "<html><script>bad()</script><body><p>Charging needs better planning.</p></body></html>"})
    assert response.status_code == 201, response.text
    record = client.get("/evidence").json()["items"][0]
    assert "bad()" not in record["content"]
    assert record["location"]["url"] == "https://example.org/research"
    assert client.get("/sources").json()[0]["kind"] == "web"


@pytest.mark.parametrize("records", [None, 1, "records", {}, [None]])
def test_invalid_record_collections_return_422(client, records):
    response = client.post("/imports/records", json=records_payload(records=records))
    assert response.status_code == 422, response.text
    assert client.get("/sources").json() == []


@pytest.mark.parametrize("field,value", [("metadata", {"value": float("nan")}),
                                         ("location", {"value": float("inf")}),
                                         ("metadata", {"nested": {"value": "\ud800"}})])
def test_invalid_nested_json_returns_serializable_validation_error(client, field, value):
    payload = records_payload()
    payload["records"][0][field] = value
    response = client.post("/imports/records", content=json.dumps(payload), headers={"Content-Type": "application/json"})
    assert response.status_code == 422, response.text
    assert client.get("/sources").json() == []


@pytest.mark.parametrize("observed_at", ["yesterday", "2025-02-30", "20250101", "2025-01-01T25:00:00"])
def test_invalid_dates_are_rejected_for_records_and_web(client, observed_at):
    payload = records_payload()
    payload["records"][0]["observed_at"] = observed_at
    assert client.post("/imports/records", json=payload).status_code == 422
    assert client.post("/imports/web", json={"url": "https://example.org", "title": "Research",
                                            "content": "Needs better seats", "observed_at": observed_at}).status_code == 422


def test_dates_metadata_scope_aliases_and_literal_search_survive_import(client):
    payload = records_payload(vehicle="g60", market="usa", metadata={"source": {"year": 2024}})
    payload["records"] = [{"content": "A 100% charging problem", "location": {"row": 2},
                            "observed_at": "2024-02-29", "metadata": {"rating": 3}}]
    response = client.post("/imports/records", json=payload)
    assert response.status_code == 201, response.text
    source = client.get("/sources", params={"vehicle": "g60", "market": "United States"}).json()[0]
    assert source["observed_at"] == "2024-02-29"
    assert source["metadata"] == payload["metadata"]
    evidence = client.get("/evidence", params={"vehicle": "g60", "market": "usa", "q": "100%"}).json()
    assert evidence["total"] == 1
    assert evidence["items"][0]["observed_at"] == "2024-02-29"
    assert client.get("/evidence?q=_").json()["total"] == 0
    for route in ("/sources", "/evidence"):
        assert client.get(route, params={"market": " "}).status_code == 422


@pytest.mark.parametrize("url", ["https://[broken", "https://example.org:bad", "https://user:pass@example.org",
                                  "https://example .org", "ftp://example.org", "https://example.org/\npath"])
def test_invalid_web_urls_are_validation_errors(client, url):
    response = client.post("/imports/web", json={"url": url, "title": "Research", "content": "Text"})
    assert response.status_code == 422, response.text


def test_web_snapshot_invalid_unicode_is_a_validation_error(client):
    payload = {"url": "https://example.org", "title": "Research", "content": "\ud800"}
    response = client.post("/imports/web", content=json.dumps(payload), headers={"content-type": "application/json"})
    assert response.status_code == 422, response.text


def test_invalid_unicode_in_extra_field_name_is_a_validation_error(client):
    payload = records_payload(**{"\ud800": "bad key"})
    response = client.post("/imports/records", content=json.dumps(payload), headers={"content-type": "application/json"})
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("field", ["title", "reference", "vehicle", "market", "\ud800"])
def test_source_registration_rejects_invalid_unicode(client, field):
    payload = {"title": "Research", "reference": "Source note", "kind": "document", field: "\ud800"}
    response = client.post("/sources", content=json.dumps(payload), headers={"content-type": "application/json"})
    assert response.status_code == 422, response.text
    assert client.get("/sources").json() == []


def test_web_blank_chunks_offsets_original_and_dates(client):
    content = " " * 50_003 + "Seat discomfort is a problem.  "
    payload = {"url": "https://example.org/research", "title": "Research", "content": content,
               "observed_at": "2025-01-01T12:00:00Z"}
    response = client.post("/imports/web", json=payload)
    assert response.status_code == 201, response.text
    record = client.get("/evidence").json()["items"][0]
    assert record["location"]["text_offset"] == 50_003
    assert record["content"] == "Seat discomfort is a problem."
    original = client.get("/sources/" + response.json()["source_id"] + "/original")
    assert original.json()["content"] == content
    assert original.json()["observed_at"] == payload["observed_at"]
    assert "web.json" in original.headers["content-disposition"]
    payload["observed_at"] = "2025-02-01T12:00:00Z"
    assert client.post("/imports/web", json=payload).json()["deduplicated"] is False


def test_local_import_symlink_boundary_and_invalid_paths(client, tmp_path, monkeypatch):
    root = tmp_path / "input"
    root.mkdir()
    monkeypatch.setenv("DATA_DIR", str(root))
    outside = tmp_path / "outside.txt"
    outside.write_text("Private text")
    (root / "escape.txt").symlink_to(outside)
    (root / "loop.txt").symlink_to(root / "loop.txt")
    for path in ("escape.txt", "loop.txt", "bad\x00.txt", str(outside), "../outside.txt"):
        assert client.post("/imports/local", json={"path": path}).status_code == 422
    (root / "feedback.txt").write_text("Charging is confusing")
    imported = client.post("/imports/local", json={"path": "feedback.txt"})
    assert imported.status_code == 201, imported.text
    original = client.get("/sources/" + imported.json()["source_id"] + "/original")
    assert original.content == b"Charging is confusing"


def test_damaged_archive_is_never_accepted_as_an_original(client, db):
    payload = records_payload()
    imported = client.post("/imports/records", json=payload).json()
    source = client.get("/sources/" + imported["source_id"]).json()
    original = db.parent / "originals" / source["original_path"]
    original.write_bytes(b"corrupted")
    assert client.get("/sources/" + imported["source_id"] + "/original").status_code == 503
    assert client.post("/imports/records", json=payload).status_code == 503
    assert original.read_bytes() == b"corrupted"
    assert len(client.get("/sources").json()) == 1


def test_database_failure_does_not_publish_partial_import(client, db, monkeypatch):
    def broken_audit(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr("server.evidence.audit", broken_audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        client.post("/imports/records", json=records_payload())
    with closing(connect()) as connection:
        assert connection.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM evidence").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM imports").fetchone()[0] == 0
    assert not (db.parent / "originals").exists()


def test_archive_failure_rolls_back_all_import_records(client, db):
    (db.parent / "originals").write_text("Archive directory unavailable")
    assert client.post("/imports/records", json=records_payload()).status_code == 503
    assert client.get("/sources").json() == []
    assert client.get("/evidence").json()["total"] == 0
    with closing(connect()) as connection:
        assert connection.execute("SELECT count(*) FROM imports").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 0


def test_import_resource_limits_and_invalid_forms(client):
    payload = records_payload()
    payload["records"][0]["metadata"] = {"large": "x" * (128 * 1024)}
    assert client.post("/imports/records", json=payload).status_code == 422
    payload = records_payload(records=[{"content": "x" * 100_000, "location": {"row": i}} for i in range(51)])
    assert client.post("/imports/records", json=payload).status_code == 422
    data = b"Feedback,Vehicle,Market\nBad seats,G60,US\n"
    for form in ({"title": "x" * 201}, {"vehicle": "x" * 51}, {"market": " "}, {"actor": " "}):
        response = client.post("/imports/files", files={"file": ("feedback.csv", data)}, data=form)
        assert response.status_code == 422, response.text


def test_oversized_file_and_local_imports_return_413(client, tmp_path, monkeypatch):
    monkeypatch.setattr("server.evidence.MAX_FILE_BYTES", 1024)
    data = b"x" * 1025
    assert client.post("/imports/files", files={"file": ("feedback.txt", data)}).status_code == 413
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "feedback.txt").write_bytes(data)
    assert client.post("/imports/local", json={"path": "feedback.txt"}).status_code == 413
    assert client.get("/sources").json() == []


def test_identical_file_bytes_deduplicate_per_scope_and_keep_download_name(client):
    data = b"Seat is uncomfortable"
    first = client.post("/imports/files", files={"file": ("C:\\input\\feedback.txt", data)}).json()
    second = client.post("/imports/files", files={"file": ("renamed.txt", data)}).json()
    other_scope = client.post("/imports/files", files={"file": ("feedback.txt", data)}, data={"market": "CN"}).json()
    assert second["source_id"] == first["source_id"]
    assert second["deduplicated"] is True
    assert other_scope["source_id"] != first["source_id"]
    original = client.get("/sources/" + first["source_id"] + "/original")
    assert original.content == data
    assert "feedback.txt" in original.headers["content-disposition"]
