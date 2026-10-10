-- Read-only views for API, MCP, UI and export (notes/database-contract.md section 5).
-- Columns may be added later; existing ones are not renamed or removed without agreement.

-- Latest score of each requirement's current version (helper, not part of the contract).
CREATE VIEW v_current_scores AS
SELECT r.id AS requirement_id, s.id AS score_id, s.total AS score_total, s.evidence_grade, s.rubric_version
FROM requirements r
JOIN scores s ON s.rowid = (SELECT s2.rowid FROM scores s2 WHERE s2.version_id = r.current_version_id
                            ORDER BY s2.created_at DESC, s2.rowid DESC LIMIT 1);

CREATE VIEW v_requirement_list AS
WITH last_decision AS (
    SELECT d.* FROM decisions d
    WHERE d.rowid = (SELECT d2.rowid FROM decisions d2 WHERE d2.requirement_id = d.requirement_id
                     ORDER BY d2.rowid DESC LIMIT 1)
), current_links AS (
    SELECT r.id AS requirement_id, rf.finding_id, fe.evidence_id, e.source_id
    FROM requirements r
    JOIN requirement_findings rf ON rf.version_id = r.current_version_id
    LEFT JOIN finding_evidence fe ON fe.finding_id = rf.finding_id
    LEFT JOIN evidence e ON e.id = fe.evidence_id
), counts AS (
    SELECT requirement_id, count(DISTINCT finding_id) AS finding_count, count(DISTINCT evidence_id) AS evidence_count,
           count(DISTINCT source_id) AS source_count
    FROM current_links GROUP BY requirement_id
)
SELECT r.id AS requirement_id, r.key, r.vehicle, r.market, r.topic, r.status, r.current_version_id,
       v.version, v.title, v.statement, v.customer_need, v.acceptance_criteria, v.assumptions,
       cs.score_id, cs.score_total,
       CASE WHEN cs.score_total IS NULL THEN NULL
            ELSE rank() OVER (PARTITION BY r.vehicle, r.market, cs.score_total IS NULL ORDER BY cs.score_total DESC)
       END AS rank,
       cs.evidence_grade, cs.rubric_version, r.approved_version_id,
       coalesce(c.finding_count, 0) AS finding_count, coalesce(c.evidence_count, 0) AS evidence_count,
       coalesce(c.source_count, 0) AS source_count,
       ld.action AS last_decision_action, ld.actor AS last_decision_actor, ld.rationale AS last_decision_rationale,
       ld.created_at AS last_decision_at,
       (SELECT count(*) FROM review_items ri WHERE ri.requirement_id = r.id AND ri.status = 'open') AS open_review_count,
       r.updated_at
FROM requirements r
LEFT JOIN requirement_versions v ON v.id = r.current_version_id
LEFT JOIN v_current_scores cs ON cs.requirement_id = r.id
LEFT JOIN last_decision ld ON ld.requirement_id = r.id
LEFT JOIN counts c ON c.requirement_id = r.id;

CREATE VIEW v_requirement_trace AS
SELECT r.id AS requirement_id, r.key, v.id AS version_id, v.version,
       f.id AS finding_id, f.kind AS finding_kind, f.topic AS finding_topic, f.summary AS finding_summary,
       f.confidence AS finding_confidence, fe.relation,
       e.id AS evidence_id, e.content AS evidence_content, e.location AS evidence_location,
       e.metadata AS evidence_metadata, e.observed_at AS evidence_observed_at,
       s.id AS source_id, s.title AS source_title, s.kind AS source_kind, s.original_path AS source_original_path,
       s.content_hash AS source_content_hash
FROM requirements r
JOIN requirement_versions v ON v.requirement_id = r.id
JOIN requirement_findings rf ON rf.version_id = v.id
JOIN findings f ON f.id = rf.finding_id
JOIN finding_evidence fe ON fe.finding_id = f.id
JOIN evidence e ON e.id = fe.evidence_id
JOIN sources s ON s.id = e.source_id;

CREATE VIEW v_audit_timeline AS
SELECT a.sequence, a.created_at, a.actor, ac.display_name AS actor_name, ac.kind AS actor_kind,
       ac.role AS actor_role, a.action, a.entity_type, a.entity_id,
       CASE a.entity_type
           WHEN 'requirement' THEN a.entity_id
           WHEN 'requirement_version' THEN (SELECT requirement_id FROM requirement_versions WHERE id = a.entity_id)
           WHEN 'version' THEN (SELECT requirement_id FROM requirement_versions WHERE id = a.entity_id)
           WHEN 'score' THEN (SELECT v.requirement_id FROM scores s JOIN requirement_versions v ON v.id = s.version_id
                              WHERE s.id = a.entity_id)
           WHEN 'decision' THEN (SELECT requirement_id FROM decisions WHERE id = a.entity_id)
           WHEN 'review' THEN (SELECT requirement_id FROM review_items WHERE id = a.entity_id)
           WHEN 'review_item' THEN (SELECT requirement_id FROM review_items WHERE id = a.entity_id)
       END AS requirement_id,
       a.rationale, a.before_state, a.after_state, a.event_hash
FROM audit_events a
LEFT JOIN actors ac ON ac.id = a.actor;

CREATE VIEW v_topic_markets AS
SELECT r.vehicle, r.topic, r.market, r.id AS requirement_id, r.key, r.status, cs.score_total, cs.evidence_grade,
       r.approved_version_id
FROM requirements r
LEFT JOIN v_current_scores cs ON cs.requirement_id = r.id;

CREATE VIEW v_open_reviews AS
SELECT ri.id AS review_id, r.id AS requirement_id, r.key, r.vehicle, r.market, ri.reason, ri.changes,
       ri.suggested_action, ri.approved_version_id, ri.proposed_version_id, ri.created_at
FROM review_items ri
JOIN requirements r ON r.id = ri.requirement_id
WHERE ri.status = 'open';
