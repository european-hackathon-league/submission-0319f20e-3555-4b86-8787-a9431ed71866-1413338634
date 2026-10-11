-- Pod D – prioritization v2 (PLATFORM_BUILD_PLAN.md section 8, notes/prioritization-v2.md).
-- 0009 already creates priority_inputs, priority_sensitivity and scope_rubrics with their human gate
-- (scope_rubrics_human_actor), append-only and no-delete triggers. This migration only adds integrity
-- rules and read helpers on top; it never changes 0009's columns.

-- A scope uses a known rubric, and its weights are recorded as one JSON object (validated by the API).
-- Created after 0009's human gate, so it fires first (SQLite runs the newest trigger first).
CREATE TRIGGER scope_rubrics_known_rubric BEFORE INSERT ON scope_rubrics
WHEN NEW.rubric_version NOT IN ('customer-priority-v1', 'customer-priority-v2')
  OR json_type(NEW.weights) IS NOT 'object'
BEGIN SELECT RAISE(ABORT, 'scope rubric must be customer-priority-v1 or customer-priority-v2 with a weights object'); END;

-- A derived factor value belongs to a version of the same requirement and records its derivation object.
CREATE TRIGGER priority_inputs_consistent BEFORE INSERT ON priority_inputs
WHEN json_type(NEW.derivation) IS NOT 'object'
  OR NOT EXISTS (SELECT 1 FROM requirement_versions WHERE id = NEW.version_id AND requirement_id = NEW.requirement_id)
BEGIN SELECT RAISE(ABORT, 'priority input must belong to a version of its requirement and record a derivation'); END;

-- Sensitivity results are a record of one deterministic analysis; later runs append, never rewrite.
CREATE TRIGGER priority_sensitivity_no_update BEFORE UPDATE ON priority_sensitivity
BEGIN SELECT RAISE(ABORT, 'priority_sensitivity is append-only'); END;

CREATE INDEX priority_inputs_requirement ON priority_inputs(requirement_id, created_at);
CREATE INDEX priority_sensitivity_scope ON priority_sensitivity(vehicle, market, rubric_version, created_at);

-- The latest derived value per requirement version and factor (append-only history stays in the table).
CREATE VIEW v_priority_inputs_latest AS
SELECT p.*
FROM priority_inputs p
WHERE p.rowid = (SELECT p2.rowid FROM priority_inputs p2
                 WHERE p2.version_id = p.version_id AND p2.factor = p.factor
                 ORDER BY p2.created_at DESC, p2.rowid DESC LIMIT 1);
