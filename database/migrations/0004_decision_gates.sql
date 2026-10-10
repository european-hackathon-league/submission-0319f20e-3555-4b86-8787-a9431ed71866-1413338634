-- Human decision gates and requirement keys (notes/database-contract.md sections 1 and 4).
-- The database itself refuses an AI approval, independent of API code.

ALTER TABLE requirements ADD COLUMN key TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_requirements_key ON requirements(key);

-- Last number issued per vehicle and market, so a key is never reused.
CREATE TABLE IF NOT EXISTS requirement_key_sequences (
    vehicle TEXT NOT NULL,
    market TEXT NOT NULL,
    last_number INTEGER NOT NULL CHECK(last_number >= 0),
    PRIMARY KEY(vehicle, market)
);

-- Keys for requirements that already exist, in creation order.
UPDATE requirements SET key = (
    SELECT 'REQ-' || ranked.vehicle || '-' || ranked.market || '-' || printf('%03d', ranked.number)
    FROM (SELECT id, vehicle, market,
                 row_number() OVER (PARTITION BY vehicle, market ORDER BY created_at, rowid) AS number
          FROM requirements) AS ranked
    WHERE ranked.id = requirements.id
) WHERE key IS NULL;
INSERT INTO requirement_key_sequences (vehicle, market, last_number)
SELECT vehicle, market, count(*) FROM requirements GROUP BY vehicle, market;

CREATE TRIGGER requirements_key_assigned_by_database BEFORE INSERT ON requirements
WHEN NEW.key IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'requirement keys are assigned by the database'); END;

CREATE TRIGGER requirements_assign_key AFTER INSERT ON requirements
BEGIN
    INSERT INTO requirement_key_sequences (vehicle, market, last_number)
    SELECT NEW.vehicle, NEW.market, 0
    WHERE NOT EXISTS (SELECT 1 FROM requirement_key_sequences WHERE vehicle = NEW.vehicle AND market = NEW.market);
    UPDATE requirement_key_sequences SET last_number = last_number + 1
    WHERE vehicle = NEW.vehicle AND market = NEW.market;
    UPDATE requirements SET key = 'REQ-' || NEW.vehicle || '-' || NEW.market || '-' || printf('%03d', (
        SELECT last_number FROM requirement_key_sequences WHERE vehicle = NEW.vehicle AND market = NEW.market
    )) WHERE id = NEW.id;
END;

CREATE TRIGGER requirements_identity_fixed BEFORE UPDATE OF key, vehicle, market, topic ON requirements
WHEN OLD.key IS NOT NULL AND (NEW.key IS NOT OLD.key OR NEW.vehicle IS NOT OLD.vehicle
                              OR NEW.market IS NOT OLD.market OR NEW.topic IS NOT OLD.topic)
BEGIN SELECT RAISE(ABORT, 'requirement key, vehicle, market and topic are fixed'); END;

CREATE TRIGGER requirements_no_delete BEFORE DELETE ON requirements
BEGIN SELECT RAISE(ABORT, 'requirements are never deleted'); END;

CREATE TRIGGER requirement_key_sequences_no_delete BEFORE DELETE ON requirement_key_sequences
BEGIN SELECT RAISE(ABORT, 'requirement key sequences are never reset'); END;
CREATE TRIGGER requirement_key_sequences_increase BEFORE UPDATE ON requirement_key_sequences
WHEN NEW.last_number <= OLD.last_number OR NEW.vehicle IS NOT OLD.vehicle OR NEW.market IS NOT OLD.market
BEGIN SELECT RAISE(ABORT, 'requirement key sequences only increase'); END;

-- Decisions: humans only; approve and reject need a PM role; version and score must match.
CREATE TRIGGER decisions_human_actor BEFORE INSERT ON decisions
WHEN NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor AND kind = 'human')
BEGIN SELECT RAISE(ABORT, 'decisions require a human actor'); END;

CREATE TRIGGER decisions_pm_role BEFORE INSERT ON decisions
WHEN NEW.action IN ('approve', 'reject')
 AND EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor AND kind = 'human')
 AND NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor AND kind = 'human' AND role IN ('pm', 'lead_pm'))
BEGIN SELECT RAISE(ABORT, 'approve and reject require a PM role'); END;

CREATE TRIGGER decisions_consistent_scope BEFORE INSERT ON decisions
WHEN NOT EXISTS (SELECT 1 FROM requirement_versions v JOIN scores s ON s.version_id = v.id
                 WHERE v.id = NEW.version_id AND v.requirement_id = NEW.requirement_id AND s.id = NEW.score_id)
BEGIN SELECT RAISE(ABORT, 'decision version and score must belong to the requirement'); END;

-- Approval pointers: only set by the latest decision on the requirement, an approve of that version and score.
CREATE TRIGGER requirements_insert_unapproved BEFORE INSERT ON requirements
WHEN NEW.approved_version_id IS NOT NULL OR NEW.approved_score_id IS NOT NULL OR NEW.status <> 'proposed'
BEGIN SELECT RAISE(ABORT, 'new requirements start proposed and unapproved'); END;

CREATE TRIGGER requirements_approval_gate BEFORE UPDATE OF approved_version_id, approved_score_id ON requirements
WHEN (NEW.approved_version_id IS NOT OLD.approved_version_id OR NEW.approved_score_id IS NOT OLD.approved_score_id)
 AND (NEW.approved_version_id IS NULL) <> (NEW.approved_score_id IS NULL)
BEGIN SELECT RAISE(ABORT, 'approved version and score are set together'); END;

-- Status workflow. approved / rejected / postponed follow the latest human decision; needs_review can be
-- raised by anyone (new evidence); an approved requirement reopens through needs_review, not proposed.
CREATE TRIGGER requirements_status_workflow BEFORE UPDATE OF status ON requirements
WHEN NEW.status IS NOT OLD.status AND (
    (NEW.status = 'proposed' AND OLD.status = 'approved')
    OR (NEW.status IN ('approved', 'rejected', 'postponed') AND NOT EXISTS (
        SELECT 1 FROM (SELECT action FROM decisions WHERE requirement_id = NEW.id
                       ORDER BY rowid DESC LIMIT 1) AS latest
        WHERE latest.action = CASE NEW.status WHEN 'approved' THEN 'approve'
                                              WHEN 'rejected' THEN 'reject' ELSE 'postpone' END))
)
BEGIN SELECT RAISE(ABORT, 'status change is not allowed by the decision workflow'); END;

CREATE TRIGGER requirements_approved_has_version BEFORE UPDATE OF status, approved_version_id ON requirements
WHEN NEW.status = 'approved' AND NEW.approved_version_id IS NULL
BEGIN SELECT RAISE(ABORT, 'an approved requirement needs an approved version'); END;

-- Created last so it fires first (SQLite runs the newest trigger first) and names the real cause.
CREATE TRIGGER requirements_approval_requires_decision
BEFORE UPDATE OF approved_version_id, approved_score_id ON requirements
WHEN NEW.approved_version_id IS NOT NULL
 AND (NEW.approved_version_id IS NOT OLD.approved_version_id OR NEW.approved_score_id IS NOT OLD.approved_score_id)
 AND NOT EXISTS (
    SELECT 1 FROM (SELECT version_id, score_id, action FROM decisions WHERE requirement_id = NEW.id
                   ORDER BY rowid DESC LIMIT 1) AS latest
    WHERE latest.action = 'approve' AND latest.version_id = NEW.approved_version_id
      AND latest.score_id = NEW.approved_score_id)
BEGIN SELECT RAISE(ABORT, 'approval requires a PM decision'); END;
