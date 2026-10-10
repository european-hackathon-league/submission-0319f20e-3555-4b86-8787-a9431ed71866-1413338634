import json

import pytest

from database.store import audit, connect, transaction


@pytest.fixture
def g60_chain(client):
    """One G60/US requirement traced to a feedback sheet row, scored and approved by a PM."""
    payload = {"title": "G60 feedback", "kind": "feedback", "reference": "G60_feedback.xlsx", "vehicle": "G60",
               "market": "US", "actor": "system:importer", "records": [
                   {"content": "Rear seats lack USB-C charging", "location": {"sheet": "Feedback", "row": 42}},
                   {"content": "Charging ports are fine", "location": {"sheet": "Feedback", "row": 43}},
               ]}
    response = client.post("/imports/records", json=payload)
    assert response.status_code == 201, response.text
    with connect() as connection:
        evidence = {row["content"]: row["id"] for row in connection.execute("SELECT id, content FROM evidence")}
    with transaction() as connection:
        statements = [
            ("INSERT INTO analysis_runs VALUES ('run','G60','US','reference','v1','p1','hash','[]','[]','{}','t')", ()),
            ("INSERT INTO findings VALUES ('finding','run','G60','US','rear-charging','problem','No rear USB-C',0.9,'t')",
             ()),
            ("INSERT INTO finding_evidence VALUES ('finding', ?, 'supports')",
             (evidence["Rear seats lack USB-C charging"],)),
            ("INSERT INTO finding_evidence VALUES ('finding', ?, 'conflicts')", (evidence["Charging ports are fine"],)),
            ("INSERT INTO requirements (id,vehicle,market,topic,status,created_at,updated_at) "
             "VALUES ('req','G60','US','rear-charging','proposed','t','t')", ()),
            ("INSERT INTO requirement_versions VALUES ('v1','req',1,'Rear USB-C','Provide rear USB-C','Charge devices',"
             "'[\"2 ports\"]','[\"cost unknown\"]','{}','ai:reference:v1','From findings','t')", ()),
            ("INSERT INTO requirement_findings VALUES ('v1','finding')", ()),
            ("INSERT INTO scores VALUES ('s1','v1','r1','{}','{}',3.2,'B','{}','t1')", ()),
            ("INSERT INTO scores VALUES ('s2','v1','r1','{}','{}',3.8,'A','{}','t2')", ()),
            ("UPDATE requirements SET current_version_id = 'v1' WHERE id = 'req'", ()),
            ("INSERT INTO decisions VALUES ('d1','req','v1','s2','approve','human:troy','Strong US signal','t3')", ()),
            ("UPDATE requirements SET approved_version_id = 'v1', approved_score_id = 's2', status = 'approved' "
             "WHERE id = 'req'", ()),
            ("INSERT INTO requirements (id,vehicle,market,topic,status,created_at,updated_at) "
             "VALUES ('req-cn','G60','CN','rear-charging','proposed','t','t')", ()),
        ]
        for statement, params in statements:
            connection.execute(statement, params)
        audit(connection, "decision", "d1", "requirement.approved", "human:troy", "Strong US signal")
    return evidence


def test_single_query_traces_requirement_to_sheet_and_row(g60_chain):
    with connect() as connection:
        rows = connection.execute("SELECT * FROM v_requirement_trace WHERE key = 'REQ-G60-US-001' "
                                  "ORDER BY relation DESC").fetchall()
    assert [(row["relation"], json.loads(row["evidence_location"])) for row in rows] == [
        ("supports", {"sheet": "Feedback", "row": 42}), ("conflicts", {"sheet": "Feedback", "row": 43})]
    assert rows[0]["source_title"] == "G60 feedback" and len(rows[0]["source_content_hash"]) == 64
    assert rows[0]["finding_summary"] == "No rear USB-C" and rows[0]["version"] == 1


def test_requirement_list_uses_latest_score_and_decision(g60_chain):
    with connect() as connection:
        row = connection.execute("SELECT * FROM v_requirement_list WHERE key = 'REQ-G60-US-001'").fetchone()
        other = connection.execute("SELECT rank, score_total FROM v_requirement_list WHERE market = 'CN'").fetchone()
    assert (row["score_id"], row["score_total"], row["evidence_grade"], row["rank"]) == ("s2", 3.8, "A", 1)
    assert (row["finding_count"], row["evidence_count"], row["source_count"]) == (1, 2, 1)
    assert (row["last_decision_action"], row["last_decision_actor"]) == ("approve", "human:troy")
    assert row["status"] == "approved" and row["approved_version_id"] == "v1" and row["open_review_count"] == 0
    assert tuple(other) == (None, None)


def test_audit_timeline_resolves_requirement_and_actor(g60_chain):
    with connect() as connection:
        rows = connection.execute("SELECT * FROM v_audit_timeline WHERE requirement_id = 'req' "
                                  "ORDER BY sequence").fetchall()
        actors = [row["actor"] for row in connection.execute("SELECT actor FROM v_audit_timeline ORDER BY sequence")]
    assert [(row["action"], row["actor_name"], row["actor_role"]) for row in rows] == [
        ("requirement.approved", "Troy", "lead_pm")]
    assert actors[0] == "system:importer" and len(rows[0]["event_hash"]) == 64


def test_topic_markets_and_open_reviews(g60_chain):
    with transaction() as connection:
        connection.execute("INSERT INTO requirement_versions VALUES ('v2','req',2,'Rear USB-C 100W','s','n','[]','[]',"
                           "'{}','ai:reference:v1','New evidence','t4')")
        connection.execute("INSERT INTO review_items VALUES ('review','req','v1','v2','New evidence','{}','approve',"
                           "'open','t4',NULL)")
    with connect() as connection:
        markets = connection.execute("SELECT market, key, status, score_total FROM v_topic_markets "
                                     "WHERE vehicle = 'G60' AND topic = 'rear-charging' ORDER BY market").fetchall()
        reviews = connection.execute("SELECT key, proposed_version_id FROM v_open_reviews").fetchall()
        count = connection.execute("SELECT open_review_count FROM v_requirement_list WHERE requirement_id = 'req'")
        assert count.fetchone()[0] == 1
    assert [tuple(row) for row in markets] == [("CN", "REQ-G60-CN-001", "proposed", None),
                                               ("US", "REQ-G60-US-001", "approved", 3.8)]
    assert [tuple(row) for row in reviews] == [("REQ-G60-US-001", "v2")]


def test_views_match_contract_columns(db):
    contract = {
        "v_requirement_list": "requirement_id key vehicle market topic status current_version_id version title "
        "statement customer_need acceptance_criteria assumptions score_id score_total rank evidence_grade "
        "rubric_version approved_version_id finding_count evidence_count source_count last_decision_action "
        "last_decision_actor last_decision_rationale last_decision_at open_review_count updated_at",
        "v_requirement_trace": "requirement_id key version_id version finding_id finding_kind finding_topic "
        "finding_summary finding_confidence relation evidence_id evidence_content evidence_location "
        "evidence_metadata evidence_observed_at source_id source_title source_kind source_original_path "
        "source_content_hash",
        "v_audit_timeline": "sequence created_at actor actor_name actor_kind actor_role action entity_type entity_id "
        "requirement_id rationale before_state after_state event_hash",
        "v_topic_markets": "vehicle topic market requirement_id key status score_total evidence_grade "
        "approved_version_id",
        "v_open_reviews": "review_id requirement_id key vehicle market reason changes suggested_action "
        "approved_version_id proposed_version_id created_at",
    }
    with connect() as connection:
        for view, columns in contract.items():
            assert [row["name"] for row in connection.execute(f"PRAGMA table_info({view})")] == columns.split(), view
