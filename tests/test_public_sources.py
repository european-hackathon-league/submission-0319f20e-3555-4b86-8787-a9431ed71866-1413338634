"""Public data connectors: NHTSA complaints/recalls and grounded OpenAI web research, offline."""

import json

import pytest

from server import public_sources
from server.public_sources import grounded
from tests.fakes import FakeOpenAI

MODELS = {"c": ["I5", "X5"], "r": ["I5"]}
COMPLAINTS = {"I5": [
    {"odiNumber": 111, "components": "FORWARD COLLISION AVOIDANCE", "dateComplaintFiled": "05/05/2026",
     "dateOfIncident": "05/03/2026", "summary": "Phantom braking warning on the highway with no obstacle.",
     "crash": False, "fire": False},
    {"odiNumber": 112, "components": "ELECTRICAL SYSTEM:PROPULSION SYSTEM:TRACTION BATTERY",
     "dateComplaintFiled": "12/10/2025", "summary": "The car stopped charging at a public DC charger.",
     "crash": False, "fire": False},
]}
RECALLS = {"I5": [{"NHTSACampaignNumber": "24V104000", "ReportReceivedDate": "12/02/2024",
                   "Component": "ELECTRONIC STABILITY CONTROL (ESC)", "Summary": "ESC software may fail.",
                   "Consequence": "Increased crash risk."}]}


@pytest.fixture
def nhtsa(monkeypatch):
    calls = []

    def fake(path, params, warnings=None):
        calls.append((path, params))
        if path == "/products/vehicle/models":
            return {"results": [{"model": name} for name in MODELS[params["issueType"]]]}
        if params["modelYear"] != 2024:
            return {"results": []}
        if path == "/complaints/complaintsByVehicle":
            return {"results": COMPLAINTS.get(params["model"], [])}
        return {"results": RECALLS.get(params["model"], [])}

    monkeypatch.setattr(public_sources, "_get_json", fake)
    return calls


def evidence(client, source_id):
    return client.get(f"/evidence?vehicle=G60&market=US&source_id={source_id}").json()["items"]


def test_nhtsa_imports_dated_public_records_once(client, nhtsa):
    result = client.post("/public-sources/nhtsa/import", json={"vehicle": "G60", "market": "US"})
    assert result.status_code == 201, result.text
    body = result.json()
    assert body["models"] == ["2024 I5", "2025 I5", "2026 I5"]  # X5 is not a G60 model
    assert (body["new_complaints"], body["new_recalls"]) == (2, 1)
    assert {"make": "BMW", "model": "I5", "modelYear": 2024} in [params for _, params in nhtsa]
    assert all(set(params) <= {"make", "model", "modelYear", "issueType"} for _, params in nhtsa)

    complaints, recalls = (evidence(client, source["source_id"]) for source in body["sources"])
    assert {e["observed_at"] for e in complaints} == {"2026-05-05", "2025-12-10"}
    assert recalls[0]["observed_at"] == "2024-02-12"  # recalls are DD/MM/YYYY
    by_odi = {e["location"]["odi_number"]: e for e in complaints}
    assert by_odi["111"]["metadata"]["topic"] == "Driver assistance experience"
    assert by_odi["112"]["metadata"]["topic"] == "Charging experience"
    assert by_odi["111"]["metadata"]["sentiment"] == "problem"
    sources = {s["id"]: s for s in client.get("/sources?vehicle=G60&market=US").json()}
    assert {sources[s["source_id"]]["kind"] for s in body["sources"]} == {"web"}
    assert sources[body["sources"][0]["source_id"]]["metadata"]["connector"] == "nhtsa"

    again = client.post("/public-sources/nhtsa/import", json={"vehicle": "G60", "market": "US"}).json()
    assert (again["new_complaints"], again["new_recalls"], again["sources"]) == (0, 0, [])


def test_nhtsa_rejects_unsupported_scopes(client, nhtsa):
    assert client.post("/public-sources/nhtsa/import", json={"vehicle": "G60", "market": "EU"}).status_code == 422
    assert client.post("/public-sources/nhtsa/import", json={"vehicle": "F70", "market": "US"}).status_code == 422
    assert nhtsa == []


def test_grounding_requires_a_url_the_search_returned():
    seen = ["https://www.reddit.com/r/BMWi5/comments/abc", "https://bmwblog.com/2024/06/30/i5-review/"]
    assert grounded("https://reddit.com/r/BMWi5/comments/abc/plug_and_charge/?utm_source=x", seen)
    assert grounded("https://www.bmwblog.com/2024/06/30/i5-review", seen)
    assert not grounded("https://reddit.com/r/BMWi5/comments/xyz", seen)
    assert not grounded("https://bmwblog.com/", seen)
    assert not grounded("javascript:alert(1)", seen)


def search_response(pages, sources):
    return FakeOpenAI.raw(json.dumps({"pages": pages})) | {"output": [
        {"type": "web_search_call", "status": "completed",
         "action": {"type": "search", "query": "q", "sources": [{"type": "url", "url": url} for url in sources]}},
        *FakeOpenAI.raw(json.dumps({"pages": pages}))["output"]]}


def page(url, sentiment="negative", date="2025-05-15"):
    return {"url": url, "title": "Owner thread", "published_date": date, "publisher_type": "owner_forum",
            "paraphrase": "An owner struggled to find a working CCS fast charger.", "sentiment": sentiment}


def test_web_research_imports_only_grounded_pages_and_sends_no_bmw_data(client, fake_llm):
    client.post("/imports/records", json={"vehicle": "G60", "market": "US", "title": "BMW feedback", "reference": "f",
                                          "records": [{"content": "CONFIDENTIAL verbatim about charging",
                                                       "location": {"row": 1}}]})
    fake_llm.responder = lambda request: search_response(
        [page("https://bmwi5forum.com/threads/low-battery.178/"), page("https://invented.example/post", "positive")],
        ["https://bmwi5forum.com/threads/low-battery.178/"])
    response = client.post("/public-sources/web-research/import",
                           json={"vehicle": "G60", "market": "US", "topics": ["charging"], "max_per_topic": 3})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["imported"] == 1
    assert body["rejected"] == [{"topic": "charging", "url": "https://invented.example/post",
                                 "reason": "not_returned_by_search"}]
    request = fake_llm.calls("/responses")[0]
    assert request["tools"] == [{"type": "web_search"}]
    assert "CONFIDENTIAL" not in json.dumps(request)
    record = evidence(client, body["source"]["source_id"])[0]
    assert record["location"]["url"] == "https://bmwi5forum.com/threads/low-battery.178/"
    assert record["observed_at"] == "2025-05-15"
    assert record["metadata"]["ai_paraphrase"] is True and record["metadata"]["sentiment"] == "problem"

    again = client.post("/public-sources/web-research/import",
                        json={"vehicle": "G60", "market": "US", "topics": ["charging"], "max_per_topic": 3}).json()
    assert len(fake_llm.calls("/responses")) == 1  # cached
    assert again["imported"] == 0 and again["per_topic"]["charging"]["already_imported"] == 1


def test_web_research_without_openai_is_explicitly_unavailable(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post("/public-sources/web-research/import", json={"vehicle": "G60", "market": "US"})
    assert response.status_code == 503
    connectors = {c["key"]: c for c in client.get("/public-sources/catalog?vehicle=G60&market=US").json()["connectors"]}
    assert connectors["web_research"]["available"] is False and connectors["nhtsa"]["available"] is True


def test_public_evidence_flows_into_requirements_and_the_source_mix(client, nhtsa):
    client.post("/imports/records", json={
        "vehicle": "G60", "market": "US", "title": "BMW feedback", "reference": "feedback.json", "kind": "feedback",
        "records": [{"content": "Public charging is hard to find on road trips.", "location": {"row": 1},
                     "metadata": {"Feedback Type": "Dislikes"}}]})
    client.post("/public-sources/nhtsa/import", json={"vehicle": "G60", "market": "US"})
    assert client.post("/pipeline/run", json={"vehicle": "G60", "market": "US", "provider": "deterministic"}).status_code == 201

    mix = client.get("/public-sources/mix?vehicle=G60&market=US").json()
    origins = {source["title"]: (source["origin"], source["role"]) for source in mix["sources"]}
    assert origins["BMW feedback"] == ("bmw_internal", "customer_voice")
    assert {origin for origin, _ in origins.values()} == {"bmw_internal", "public_official"}
    official = [s for s in mix["sources"] if s["origin"] == "public_official"]
    assert sum(s["linked_requirements"] for s in official) >= 2
    assert mix["totals"]["requirements_with_public_evidence"] >= 2
    charging = next(r for r in client.get("/requirements?vehicle=G60&market=US").json()["items"] if r["topic"] == "charging")
    trace = client.get(f"/requirements/{charging['id']}/trace").json()
    assert {source["kind"] for source in trace["sources"]} == {"feedback", "web"}
