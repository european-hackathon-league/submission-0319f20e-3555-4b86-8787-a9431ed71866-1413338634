"""Pod E: BMW import, sales weights, preserve attributes, coverage and report context.

Every fixture is a simulated workbook, PDF or text file generated here with openpyxl/pypdf; no BMW file
is read. No test reaches the network: OpenAI is the offline fake from tests/fakes.py.
"""

import io
import json
import sqlite3
from collections import defaultdict
from datetime import datetime

import pytest
from openpyxl import Workbook
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from server import market_data
from server.platform import CAPABILITIES, run_capability

FEEDBACK_HEADER = ["ID", "Source", "Brand", "Country", "Derivate (e-code)", "Engine Type", "Feedback Type",
                   "Customer Feedback", "Vfc level2 Name", "Vfc level3 Name"]
SALES_HEADER = ["market", "market_code", "volume_2024", "volume_2025", "volume_2030"]


def workbook_bytes(sheets: dict) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(name)
        for row in rows:
            sheet.append(row)
    target = io.BytesIO()
    workbook.save(target)
    return target.getvalue()


def pdf_bytes(texts: list[str]) -> bytes:
    writer = PdfWriter()
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    for text in texts:
        page = writer.add_blank_page(width=300, height=300)
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 20 250 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = stream
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def feedback_rows() -> list[list]:
    """Simulated G60 feedback: 8 US feedback IDs (6 from Simulated B = 75 %), 2 GB IDs, 1 KR ID."""
    rows = [FEEDBACK_HEADER]
    for index in range(6):
        rows.append([f"SIM-US-{index}", "Simulated B", "BMW", "US", "G60", "BEV", "Likes",
                     f"Simulated: the seats stay comfortable on long trips, variant {index}.", "Seats", "Front seats"])
    for index in range(6, 8):
        rows.append([f"SIM-US-{index}", "Simulated A", "BMW", "US", "G60", "BEV", "Difficult to Use",
                     f"Simulated: the phone charging pad is slow, variant {index}.", "Phone charging", "Wireless"])
    rows.append(["SIM-US-0", "Simulated B", "BMW", "US", "G60", "BEV", "Likes",
                 "Simulated: the seats stay comfortable on long trips, variant 0.", "Seats", "Seat comfort"])
    rows += [["SIM-GB-1", "Simulated C", "BMW", "GB", "G60", "PHEV", "Likes", "Simulated: quiet cabin.", "Noise", None],
             ["SIM-GB-2", "Simulated C", "BMW", "GB", "G60", "PHEV", "Wants", "Simulated: more storage.", "Storage", None],
             ["SIM-KR-1", "Simulated D", "BMW", "KR", "G60", "ICE", "Likes", "Simulated: great display.", "Display", None]]
    return rows


def study_sheets() -> dict:
    return {
        "US_2025": [["Seating", None, "BMW 5 Series G60", "BMW 7 Series G70"],
                    ["I Love It", "% of column, sample base", .40, .10],
                    ["Delightful", "% of column, sample base", .30, .10],
                    ["Price/deal offered", None, None, None],
                    ["I Love It", "% of column, sample base", .50, .10],
                    ["Delightful", "% of column, sample base", .40, .10],
                    ["Wireless charging", None, None, None],
                    ["I Love It", "% of column, sample base", .10, .10],
                    ["Delightful", "% of column, sample base", .10, .10]],
        "EU_2025": [["Interior", "G60"], ["Mean", 8.5], ["Exterior styling", None], ["Mean", 7.0],
                    ["Ride", None], ["Mean", 6.0], ["Value for money", None], ["Mean", 9.5]],
    }


def sales_sheets(eu_2025: int = 100, with_row: bool = True) -> dict:
    g60 = [SALES_HEADER, ["Europe", "EU", 90, eu_2025, 110], ["China", "CN", 45, 50, 60], ["USA", "US", 35, 40, 45],
           ["Germany", "DE", 25, 30, 35]]
    if with_row:
        g60.append(["Rest of world", "ROW", 5, 10, 15])
    return {"G60_G68": g60, "G70": [SALES_HEADER, ["Europe", "EU", 10, 10, 12], ["USA", "US", 10, 30, 12]]}


REPORT_TEXT = ("Simulated annual report for tests.\n"
               "Deliveries in China rose to 700,000 vehicles in 2025.\n"
               "The EBIT margin for the automotive segment in Europe reached 6 percent.\n"
               "The Neue Klasse launches with a new generation of iDrive and digital services.\n")


@pytest.fixture
def bmw_data(tmp_path, monkeypatch):
    root = tmp_path / "data"
    folder = root / "BMW-Data"
    folder.mkdir(parents=True)
    (folder / "G60_feedback_simulated.xlsx").write_bytes(workbook_bytes({"Feedback_Explorer": feedback_rows()}))
    (folder / "F70_G60_G70_customer_studies_simulated.xlsx").write_bytes(workbook_bytes(study_sheets()))
    (folder / "sales_volumes_simulated.xlsx").write_bytes(workbook_bytes(sales_sheets()))
    (folder / "G60_OptionList_simulated.PDF").write_bytes(pdf_bytes(["Simulated option page one",
                                                                      "Simulated option page two"]))
    (folder / "annual_report_simulated.txt").write_text(REPORT_TEXT)
    (folder / "README.zip").write_bytes(b"ignored: unsupported suffix")
    monkeypatch.setenv("DATA_DIR", str(root))
    return folder


def query(db, sql, params=()):
    with sqlite3.connect(db) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(sql, params)]


def imported(client):
    response = client.post("/market-data/import-bmw", json={"actor": "PM"})
    assert response.status_code == 201, response.text
    return response.json()


# Import ---------------------------------------------------------------------------------------------

def test_import_covers_every_vehicle_and_market_and_is_idempotent(client, db, bmw_data):
    body = imported(client)
    scopes = {f["path"].split("/")[-1]: {(s["vehicle"], s["market"]) for s in f["scopes"]} for f in body["files"]}
    assert scopes["G60_feedback_simulated.xlsx"] == {("G60", "US"), ("G60", "GB"), ("G60", "KR")}
    assert scopes["F70_G60_G70_customer_studies_simulated.xlsx"] == {("G60", "US"), ("G70", "US"), ("G60", "EU")}
    assert scopes["sales_volumes_simulated.xlsx"] == {(v, m) for v in ("G60", "G68") for m in ("EU", "CN", "US", "DE", "ROW")} \
        | {("G70", "EU"), ("G70", "US")}
    # The option list declares a vehicle but no market: it joins the reference markets with customer evidence.
    assert scopes["G60_OptionList_simulated.PDF"] == {("G60", "US"), ("G60", "GB"), ("G60", "EU")}
    assert scopes["annual_report_simulated.txt"] == {("G60", "US")}
    assert "README.zip" not in scopes
    assert body["method_version"] == "bmw-import-v1" and body["run_id"] and body["audit_event_id"]
    evidence = query(db, "SELECT count(*) AS n FROM evidence")[0]["n"]
    assert body["totals"]["new_evidence"] == evidence
    us = query(db, "SELECT metadata FROM evidence WHERE vehicle='G60' AND market='US' "
                   "AND json_extract(metadata, '$.record_type')='customer_feedback'")
    assert len(us) == 9  # every classification row is kept; dedup of feedback IDs happens in the analyses
    kinds = {row["reference"]: row["kind"] for row in query(db, "SELECT reference, kind FROM sources")}
    assert kinds["G60_feedback_simulated.xlsx"] == "feedback" and kinds["sales_volumes_simulated.xlsx"] == "sales"

    again = imported(client)
    assert again["totals"]["new_evidence"] == 0
    assert again["totals"]["deduplicated"] == again["totals"]["sources"] == body["totals"]["sources"]
    assert query(db, "SELECT count(*) AS n FROM evidence")[0]["n"] == evidence
    run = query(db, "SELECT * FROM runs WHERE id=?", (body["run_id"],))[0]
    assert run["capability"] == "market_data.import_bmw" and run["status"] == "succeeded"


def test_import_scopes_files_without_vehicle_or_market_by_request(client, db, bmw_data):
    response = client.post("/market-data/import-bmw", json={
        "paths": ["BMW-Data/annual_report_simulated.txt"],
        "document_scopes": [{"vehicle": "G70", "market": "CN"}, {"vehicle": "G60", "market": "EU"}]})
    assert response.status_code == 201, response.text
    assert {(s["vehicle"], s["market"]) for s in response.json()["files"][0]["scopes"]} == {("G70", "CN"), ("G60", "EU")}


@pytest.mark.parametrize("payload", [{"paths": ["../outside.txt"]}, {"directory": "../.."},
                                     {"paths": ["BMW-Data/missing.xlsx"]}])
def test_import_stays_inside_data_dir(client, db, bmw_data, payload):
    assert client.post("/market-data/import-bmw", json=payload).status_code == 422
    assert query(db, "SELECT count(*) AS n FROM sources")[0]["n"] == 0


def test_unreadable_file_fails_the_run_before_any_write(client, db, bmw_data):
    (bmw_data / "broken_feedback.xlsx").write_bytes(b"not a workbook")
    response = client.post("/market-data/import-bmw", json={})
    assert response.status_code == 422 and "broken_feedback.xlsx" in response.json()["detail"]
    assert query(db, "SELECT count(*) AS n FROM sources")[0]["n"] == 0
    run = query(db, "SELECT status FROM runs WHERE capability='market_data.import_bmw'")
    assert [row["status"] for row in run] == ["failed"]


# Market weights ------------------------------------------------------------------------------------

def test_weights_sum_to_one_per_vehicle_and_period_with_sub_markets_nested(client, db, bmw_data):
    imported(client)
    response = client.post("/market-data/weights/derive", json={})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["method_version"] == "sales-share-v1" and set(body["vehicles"]) == {"G60", "G68", "G70"}
    totals = defaultdict(float)
    for item in body["items"]:
        totals[item["vehicle"], item["period"]] += item["share"]
        assert 0 <= item["share"] <= 1 and item["evidence_ids"] and item["run_id"] == body["run_id"]
    assert totals and all(abs(total - 1) < 1e-9 for total in totals.values())
    g60 = {(i["market"], i["period"]): i for i in body["items"] if i["vehicle"] == "G60"}
    assert ("DE", "2025") not in g60  # DE rolls up into EU and never enters the denominator
    assert g60["EU", "2025"]["share"] == pytest.approx(100 / 200)
    assert g60["EU", "2025"]["metrics"]["nested_markets"] == {"DE": {"parent": "EU", "units": 30.0}}
    assert g60["EU", "2025"]["metrics"]["source_column"] == "volume_2025"
    assert g60["EU", "2030"]["metrics"]["period_type"] == "projection"
    cited = query(db, "SELECT json_extract(metadata, '$.record_type') AS t FROM evidence WHERE id IN (SELECT value "
                      "FROM json_each(?))", (json.dumps(g60["EU", "2025"]["evidence_ids"]),))
    assert {row["t"] for row in cited} == {"sales_aggregate"}
    codes = {w["code"] for w in body["warnings"]}
    assert {"combined_vehicle_sales", "projection_periods"} <= codes

    again = client.post("/market-data/weights/derive", json={}).json()
    assert again["changes"]["created"] == again["changes"]["updated"] == 0
    assert again["changes"]["unchanged"] == len(body["items"])
    listed = client.get("/market-data/weights", params={"vehicle": "G60", "period": "2025"}).json()
    assert listed["total"] == 4 and {"items", "total", "limit", "offset"} <= set(listed)


def test_changed_sales_file_updates_in_place_and_supersedes_dropped_markets(client, db, bmw_data):
    imported(client)
    first = {(i["vehicle"], i["market"], i["period"]): i
             for i in client.post("/market-data/weights/derive", json={"vehicle": "G60"}).json()["items"]}
    (bmw_data / "sales_volumes_simulated.xlsx").write_bytes(workbook_bytes(sales_sheets(eu_2025=150, with_row=False)))
    imported(client)
    body = client.post("/market-data/weights/derive", json={"vehicle": "G60"}).json()
    assert body["changes"]["superseded"] == 3  # ROW in 2024, 2025 and 2030
    assert "older_sales_file_ignored" in {w["code"] for w in body["warnings"]}
    current = {(i["market"], i["period"]): i for i in body["items"]}
    assert ("ROW", "2025") not in current
    assert current["EU", "2025"]["share"] == pytest.approx(150 / 240)
    assert current["EU", "2025"]["revision"] == 2 and current["EU", "2025"]["id"] == first["G60", "EU", "2025"]["id"]
    assert abs(sum(i["share"] for i in body["items"] if i["period"] == "2025") - 1) < 1e-9
    history = client.get("/market-data/weights", params={"vehicle": "G60", "market": "ROW", "status": "superseded"})
    assert history.json()["total"] == 3
    events = query(db, "SELECT action FROM audit_events WHERE entity_type='market_weight' AND entity_id=?",
                   (current["EU", "2025"]["id"],))
    assert [e["action"] for e in events] == ["market_weight.created", "market_weight.updated"]
    with pytest.raises(sqlite3.IntegrityError, match="increment revision"):
        with sqlite3.connect(db) as connection:
            connection.execute("UPDATE market_weights SET share = 0.5 WHERE id = ?", (current["EU", "2025"]["id"],))


# Preserve attributes ---------------------------------------------------------------------------------

def test_preserve_from_explicit_likes_and_study_top_box(client, db, bmw_data):
    imported(client)
    response = client.post("/market-data/preserve/derive", json={"vehicle": "G60", "provider": "deterministic"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["method_version"] == "preserve-v1" and body["provider"] == "deterministic"
    items = body["items"]
    assert all(0 <= item["strength"] <= 1 and item["evidence_ids"] and item["provider"] == "deterministic"
               for item in items)
    feedback = {(i["market"], i["topic"], i["attribute"]): i for i in items if i["source_type"] == "feedback"}
    assert set(feedback) == {("US", "comfort", None), ("US", "comfort", "Seats")}
    seats = feedback["US", "comfort", "Seats"]
    assert seats["metrics"]["positive_feedback_ids"] == 6 and seats["metrics"]["feedback_ids"] == 6
    assert seats["strength"] == pytest.approx(market_data.wilson_lower(6, 6), abs=1e-6)
    assert len(seats["evidence_ids"]) == 7  # SIM-US-0 is classified on two rows; strength counts it once
    study = {(i["market"], i["attribute"]): i for i in items if i["source_type"] == "study"}
    assert study["US", "Seating"]["strength"] == pytest.approx(.70)
    assert ("US", "Wireless charging") not in study
    assert ("EU", "Interior") in study and ("EU", "Ride") not in study
    assert body["excluded_out_of_scope"] == {"EU": ["Value for money"], "US": ["Price/deal offered"]}
    assert not any(i["market"] in ("GB", "KR") for i in items)  # too few explicit likes to claim a strength

    again = client.post("/market-data/preserve/derive", json={"vehicle": "G60", "provider": "deterministic"}).json()
    assert again["changes"]["created"] == again["changes"]["updated"] == 0 and again["changes"]["unchanged"] == len(items)
    listed = client.get("/market-data/preserve", params={"vehicle": "G60", "market": "US", "source_type": "study"})
    assert listed.json()["total"] == 1


def _naming_responder(quote=None):
    def respond(request):
        candidates = json.loads(request["input"])["candidates"]
        return {"attributes": [{
            "candidate_id": c["candidate_id"], "label": f"Simulated label {c['category']}",
            "summary": "Customers value comfortable seats on long trips.",
            "citations": [{"evidence_id": c["examples"][0]["evidence_id"],
                           "quote": quote or c["examples"][0]["text"][11:40]}]} for c in candidates]}
    return respond


def test_preserve_openai_names_attributes_with_grounded_quotes(client, db, bmw_data, fake_llm):
    imported(client)
    fake_llm.responder = _naming_responder()
    response = client.post("/market-data/preserve/derive", json={"vehicle": "G60", "market": "US"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["naming_method_version"].startswith("openai:fake-model:") and body["naming_run_id"]
    named = [i for i in body["items"] if i["source_type"] == "feedback"]
    assert named and all(i["provider"] == "openai" and i["model"] == "fake-model" and i["ai_run_id"] for i in named)
    texts = {row["id"]: row["content"] for row in query(db, "SELECT id, content FROM evidence")}
    for item in named:
        assert item["label"].startswith("Simulated label")
        assert item["strength"] == pytest.approx(market_data.wilson_lower(6, 6), abs=1e-6)  # strength stays counted
        for citation in item["ai"]["citations"]:
            start, end = citation["span"]
            assert texts[citation["evidence_id"]][start:end] == citation["quote"]
    assert all(i["provider"] == "deterministic" for i in body["items"] if i["source_type"] == "study")
    naming_run = query(db, "SELECT * FROM runs WHERE id=?", (body["naming_run_id"],))[0]
    assert json.loads(naming_run["metrics"])["llm"]["models"] == ["fake-model"]
    payloads = [json.loads(call["input"]) for call in fake_llm.calls("/responses")]
    assert all(set(c) == {"candidate_id", "topic", "category", "positive_feedback_ids", "examples"}
               for payload in payloads for c in payload["candidates"])


def test_preserve_rejects_ungrounded_model_quotes_without_writing(client, db, bmw_data, fake_llm):
    imported(client)
    fake_llm.responder = _naming_responder(quote="customers adore the rocket boosters")
    response = client.post("/market-data/preserve/derive", json={"vehicle": "G60", "market": "US"})
    assert response.status_code == 502
    assert query(db, "SELECT count(*) AS n FROM preserve_attributes")[0]["n"] == 0
    statuses = {row["capability"]: row["status"] for row in query(db, "SELECT capability, status FROM runs")}
    assert statuses["market_data.derive_preserve"] == statuses["market_data.name_preserve"] == "failed"


def test_preserve_openai_without_configuration_fails_clearly(client, db, bmw_data, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    imported(client)
    response = client.post("/market-data/preserve/derive", json={"vehicle": "G60"})
    assert response.status_code == 503
    assert query(db, "SELECT count(*) AS n FROM preserve_attributes")[0]["n"] == 0


# Coverage --------------------------------------------------------------------------------------------

def test_coverage_flags_single_source_dominance_and_markets_without_customer_evidence(client, db, bmw_data):
    imported(client)
    client.post("/market-data/weights/derive", json={})
    response = client.post("/market-data/coverage", json={"vehicle": "G60"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["method_version"] == "coverage-v1"
    reports = {item["market"]: item for item in body["items"]}
    assert {"US", "GB", "KR", "EU", "CN", "ROW", "DE"} <= set(reports)
    us = reports["US"]
    warnings = {w["code"]: w for w in us["warnings"]}
    assert warnings["single_source_dominance"]["share"] == pytest.approx(.75)
    assert warnings["single_source_dominance"]["source"] == "Simulated B"
    assert warnings["undated_evidence"]["dated_share"] == 0
    assert "small_sample" in warnings
    assert us["metrics"]["customer_feedback"]["unique_feedback_ids"] == 8
    assert us["metrics"]["customer_feedback"]["by_provenance"]["Simulated B"]["share"] == pytest.approx(.75)
    assert us["metrics"]["market_weight"]["2025"] == pytest.approx(.2)
    assert set(us["metrics"]["by_source_file"]) == {"G60_feedback_simulated.xlsx", "sales_volumes_simulated.xlsx",
                                                    "F70_G60_G70_customer_studies_simulated.xlsx",
                                                    "G60_OptionList_simulated.PDF", "annual_report_simulated.txt"}
    assert us["metrics"]["topics"]["comfort"]["feedback_ids"] == 6
    cn = {w["code"]: w for w in reports["CN"]["warnings"]}
    assert cn["no_customer_evidence"]["severity"] == "high"  # 25 % of G60 sales, no customer voice
    eu = {w["code"]: w for w in reports["EU"]["warnings"]}
    assert "aggregate_only" in eu and eu["sub_market_evidence"]["markets"] == ["DE", "GB"]
    assert reports["EU"]["metrics"]["rollup"]["unique_feedback_ids"] == 2
    assert reports["GB"]["metrics"]["sales_region"] == "EU"

    again = client.post("/market-data/coverage", json={"vehicle": "G60"}).json()
    assert again["changes"] == {"created": 0, "unchanged": len(reports), "superseded": 0}
    listed = client.get("/market-data/coverage", params={"vehicle": "G60", "market": "US"}).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == us["id"]


def test_coverage_supersedes_reports_when_evidence_changes(client, db, bmw_data):
    imported(client)
    first = client.post("/market-data/coverage", json={"vehicle": "G60", "market": "CN"}).json()["items"][0]
    client.post("/market-data/weights/derive", json={})
    second = client.post("/market-data/coverage", json={"vehicle": "G60", "market": "CN"}).json()
    assert second["changes"] == {"created": 1, "unchanged": 0, "superseded": 1}
    history = client.get("/market-data/coverage", params={"vehicle": "G60", "market": "CN", "status": "all"}).json()
    assert {item["status"] for item in history["items"]} == {"current", "superseded"}
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with sqlite3.connect(db) as connection:
            connection.execute("UPDATE coverage_reports SET warnings='[]' WHERE id=?", (first["id"],))


def test_markets_without_sales_are_not_reported_as_gaps(client, db, bmw_data):
    (bmw_data / "sales_volumes_simulated.xlsx").write_bytes(workbook_bytes({"F70": [
        SALES_HEADER, ["Europe", "EU", 10, 10, 10], ["USA", "US", 0, 0, 0]]}))
    imported(client)
    client.post("/market-data/weights/derive", json={"vehicle": "F70"})
    reports = {r["market"]: r for r in client.post("/market-data/coverage", json={"vehicle": "F70"}).json()["items"]}
    assert [w["code"] for w in reports["US"]["warnings"]] == ["no_sales"]


# Annual-report context --------------------------------------------------------------------------------

def _report_source(db):
    return query(db, "SELECT id FROM sources WHERE reference='annual_report_simulated.txt'")[0]["id"]


def test_report_context_deterministic_cites_pages_and_skips_financials(client, db, bmw_data):
    imported(client)
    source_id = _report_source(db)
    response = client.post("/market-data/context/extract", json={"source_id": source_id, "provider": "deterministic"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["provider"] == "deterministic" and body["method_version"] == "report-pages-v1" and body["created"]
    content = query(db, "SELECT content FROM evidence WHERE source_id=?", (source_id,))[0]["content"]
    for item in body["items"]:
        start, end = item["span"]
        assert content[start:end] == item["quote"] and not item["ai_generated"]
        assert "EBIT" not in item["quote"] and "margin" not in item["quote"]
    assert {"neue_klasse", "regional_sales"} <= {item["category"] for item in body["items"]}
    again = client.post("/market-data/context/extract", json={"source_id": source_id, "provider": "deterministic"})
    assert again.json()["created"] == 0 and again.json()["duplicates"] == body["created"]


def test_report_context_openai_keeps_only_grounded_in_scope_statements(client, db, bmw_data, fake_llm):
    imported(client)
    source_id = _report_source(db)

    def respond(request):
        page = json.loads(request["input"])["pages"][0]
        base = {"evidence_id": page["evidence_id"], "subject_series": None, "unit": None, "period": "2025"}
        return {"items": [
            {**base, "category": "regional_sales", "statement": "China deliveries grew.", "subject_market": "CN",
             "value": "700,000", "quote": "Deliveries in China rose to 700,000 vehicles in 2025."},
            {**base, "category": "regional_sales", "statement": "Europe margin.", "subject_market": "EU",
             "value": "6", "quote": "The EBIT margin for the automotive segment in Europe reached 6 percent."},
            {**base, "category": "neue_klasse", "statement": "Invented.", "subject_market": None, "value": None,
             "quote": "The Neue Klasse flies."},
            {**base, "category": "regional_sales", "statement": "Wrong value.", "subject_market": "CN",
             "value": "900,000", "quote": "Deliveries in China rose to 700,000 vehicles in 2025."}]}

    fake_llm.responder = respond
    body = client.post("/market-data/context/extract", json={"source_id": source_id}).json()
    assert body["provider"] == "openai" and body["model"] == "fake-model"
    assert body["rejected"] == {"out_of_scope": 1, "ungrounded": 1, "value_not_in_quote": 1}
    [item] = body["items"]
    assert item["ai_generated"] and item["subject_market"] == "CN" and item["value"] == "700,000"
    assert item["run_id"] == body["run_id"] and item["method_version"].startswith("openai:fake-model:")


def test_report_context_needs_a_document_source(client, db, bmw_data):
    assert client.post("/market-data/context/extract", json={"source_id": "missing",
                                                             "provider": "deterministic"}).status_code == 404


# Capabilities, scopes and MCP ----------------------------------------------------------------------------

def test_capabilities_are_registered_as_autonomous_and_run_for_agents(db, bmw_data):
    names = {"market_data.import_bmw", "market_data.derive_weights", "market_data.derive_preserve",
             "market_data.coverage", "market_data.extract_report_context"}
    assert names <= set(CAPABILITIES)
    assert all(CAPABILITIES[name].autonomy_level == "A0" for name in names)
    result = run_capability("market_data.import_bmw", {"paths": ["BMW-Data/sales_volumes_simulated.xlsx"]},
                            "ai:agent:market-data")
    assert result["run_ids"] and result["outputs"]["totals"]["new_sources"] == 12
    weights = run_capability("market_data.derive_weights", {"vehicle": "G70"}, "ai:agent:market-data")
    assert weights["outputs"]["changes"]["created"] == 6
    with pytest.raises(Exception) as error:
        run_capability("market_data.derive_preserve", {"vehicle": "G60", "provider": "anthropic"}, "ai:agent:x")
    assert getattr(error.value, "status_code", None) == 422


def test_scopes_summarise_evidence_per_vehicle_and_market(client, db, bmw_data):
    imported(client)
    items = {(i["vehicle"], i["market"]): i for i in client.get("/market-data/scopes").json()["items"]}
    assert items["G60", "US"]["unique_feedback_ids"] == 8
    assert items["G60", "US"]["by_record_type"]["customer_feedback"] == 9
    assert items["G60", "DE"]["sales_region"] == "EU" and items["G60", "KR"]["sales_region"] == "ROW"


async def test_mcp_tools_call_the_market_data_api_without_blank_filters():
    from mcp_server.market_data_tools import register_market_data_tools

    tools, calls = {}, []

    class Recorder:
        def tool(self, *args, **kwargs):
            def decorator(function):
                tools[function.__name__] = function
                return function
            return decorator

    async def api_request(method, path, *, params=None, payload=None):
        calls.append((method, path, params, payload))
        return {"ok": True}

    register_market_data_tools(Recorder(), api_request, lambda value: value)
    assert {"import_bmw_data", "derive_sales_weights", "list_sales_weights", "derive_preserve_attributes",
            "list_preserve_attributes", "derive_coverage_reports", "list_coverage_reports",
            "extract_report_context", "list_market_context", "list_data_scopes"} == set(tools)
    await tools["list_sales_weights"](vehicle="G60")
    await tools["derive_preserve_attributes"](vehicle="G60")
    assert calls[0] == ("GET", "/market-data/weights", {"vehicle": "G60", "status": "current", "limit": 200,
                                                        "offset": 0}, None)
    assert calls[1] == ("POST", "/market-data/preserve/derive", None,
                        {"vehicle": "G60", "provider": "openai", "actor": "ai:mcp"})


def test_simulated_feedback_dates_are_not_invented(client, db, bmw_data):
    rows = feedback_rows()
    rows[0] = [*FEEDBACK_HEADER, "Date"]
    rows[1] = [*rows[1], datetime(2025, 3, 1)]
    (bmw_data / "G60_feedback_simulated.xlsx").write_bytes(workbook_bytes({"Feedback_Explorer": rows}))
    imported(client)
    dated = query(db, "SELECT count(*) AS n FROM evidence WHERE observed_at IS NOT NULL")[0]["n"]
    assert dated == 1
