from concurrent.futures import ThreadPoolExecutor

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
