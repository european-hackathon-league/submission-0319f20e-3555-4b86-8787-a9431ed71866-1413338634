-- Actors the API writes as free text (e.g. 'Alice', 'AI:openai', 'System:reference') are registered as
-- discovered instead of rejected, like vehicle and market codes. Kind comes from the prefix: ai:/AI: is an
-- AI provider, system:/System: a component, anything else a human. Until there is SSO a named human is a
-- PM; a lead PM reviews discovered actors (database.cli verify) and deactivates any that should not decide.
-- The decision gates are unchanged: AI and system actors can never decide or approve.

-- The API sets status and the approval pointers in two UPDATEs of one transaction, so a per-statement
-- "approved needs a version" check fires too early. Status still needs the latest decision to be an
-- approve (requirements_status_workflow) and the pointers must match it (requirements_approval_requires_decision).
DROP TRIGGER requirements_approved_has_version;

DROP VIEW v_audit_timeline;
DROP TRIGGER audit_events_known_actor;
DROP TRIGGER requirement_versions_known_actor;
DROP TRIGGER decisions_known_actor;
DROP TRIGGER decisions_human_actor;
DROP TRIGGER decisions_pm_role;
DROP TRIGGER actors_no_delete;
DROP TRIGGER actors_fixed_identity;

-- Rebuild to relax the id format CHECK and record where each actor came from.
CREATE TABLE actors_v7 (
    id TEXT PRIMARY KEY CHECK(length(trim(id)) > 0 AND id = trim(id)),
    kind TEXT NOT NULL CHECK(kind IN ('human', 'ai', 'system')),
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('lead_pm', 'pm', 'analyst', 'engineering', 'viewer', 'ai', 'system')),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    origin TEXT NOT NULL DEFAULT 'seeded' CHECK(origin IN ('seeded', 'discovered')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK((kind = 'human') = (role NOT IN ('ai', 'system'))),
    CHECK(kind <> 'ai' OR role = 'ai'),
    CHECK(kind <> 'system' OR role = 'system')
);
INSERT INTO actors_v7 (id, kind, display_name, role, active, origin, created_at)
SELECT id, kind, display_name, role, active, 'seeded', created_at FROM actors;
DROP TABLE actors;
ALTER TABLE actors_v7 RENAME TO actors;

CREATE TRIGGER actors_no_delete BEFORE DELETE ON actors
BEGIN SELECT RAISE(ABORT, 'actors are deactivated, never deleted'); END;
CREATE TRIGGER actors_fixed_identity BEFORE UPDATE OF id, kind ON actors
BEGIN SELECT RAISE(ABORT, 'actor id and kind are fixed'); END;

-- One trigger per table so the steps run in a fixed order: register, then check.
CREATE TRIGGER audit_events_actor BEFORE INSERT ON audit_events
BEGIN
    INSERT INTO actors (id, kind, display_name, role, origin)
    SELECT NEW.actor, kind, NEW.actor, CASE kind WHEN 'human' THEN 'pm' ELSE kind END, 'discovered'
    FROM (SELECT CASE WHEN lower(NEW.actor) GLOB 'ai:*' THEN 'ai'
                      WHEN lower(NEW.actor) GLOB 'system:*' THEN 'system' ELSE 'human' END AS kind)
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor);
    SELECT RAISE(ABORT, 'inactive actor') WHERE EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor AND active = 0);
END;

CREATE TRIGGER requirement_versions_actor BEFORE INSERT ON requirement_versions
BEGIN
    INSERT INTO actors (id, kind, display_name, role, origin)
    SELECT NEW.actor, kind, NEW.actor, CASE kind WHEN 'human' THEN 'pm' ELSE kind END, 'discovered'
    FROM (SELECT CASE WHEN lower(NEW.actor) GLOB 'ai:*' THEN 'ai'
                      WHEN lower(NEW.actor) GLOB 'system:*' THEN 'system' ELSE 'human' END AS kind)
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor);
    SELECT RAISE(ABORT, 'inactive actor') WHERE EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor AND active = 0);
END;

CREATE TRIGGER decisions_actor BEFORE INSERT ON decisions
BEGIN
    INSERT INTO actors (id, kind, display_name, role, origin)
    SELECT NEW.actor, kind, NEW.actor, CASE kind WHEN 'human' THEN 'pm' ELSE kind END, 'discovered'
    FROM (SELECT CASE WHEN lower(NEW.actor) GLOB 'ai:*' THEN 'ai'
                      WHEN lower(NEW.actor) GLOB 'system:*' THEN 'system' ELSE 'human' END AS kind)
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor);
    SELECT RAISE(ABORT, 'inactive actor') WHERE EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor AND active = 0);
    SELECT RAISE(ABORT, 'decisions require a human actor')
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor AND kind = 'human');
    SELECT RAISE(ABORT, 'approve and reject require a PM role')
    WHERE NEW.action IN ('approve', 'reject')
      AND NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor AND role IN ('pm', 'lead_pm'));
END;

-- Unchanged from 0006; recreated because it reads actors.
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
