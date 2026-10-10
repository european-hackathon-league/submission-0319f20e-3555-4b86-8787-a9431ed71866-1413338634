-- People, roles and the vehicle/market catalogue (notes/database-contract.md sections 1-3).
-- Seed rows are written by database/seed.py, which runs right after this file.

CREATE TABLE IF NOT EXISTS actors (
    id TEXT PRIMARY KEY CHECK(id = 'PM' OR id GLOB 'human:*' OR id GLOB 'ai:*' OR id GLOB 'system:*'),
    kind TEXT NOT NULL CHECK(kind IN ('human', 'ai', 'system')),
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('lead_pm', 'pm', 'analyst', 'engineering', 'viewer', 'ai', 'system')),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK((kind = 'human') = (role NOT IN ('ai', 'system'))),
    CHECK(kind <> 'ai' OR role = 'ai'),
    CHECK(kind <> 'system' OR role = 'system')
);

CREATE TABLE IF NOT EXISTS vehicles (
    code TEXT PRIMARY KEY,
    series TEXT,
    body TEXT,
    status TEXT NOT NULL CHECK(status IN ('seeded', 'discovered', 'confirmed')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS markets (
    code TEXT PRIMARY KEY,
    name TEXT,
    parent_code TEXT REFERENCES markets(code),
    status TEXT NOT NULL CHECK(status IN ('seeded', 'discovered', 'confirmed')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Actors are referenced by append-only history, so they are deactivated, never deleted or renamed.
CREATE TRIGGER actors_no_delete BEFORE DELETE ON actors
BEGIN SELECT RAISE(ABORT, 'actors are deactivated, never deleted'); END;
CREATE TRIGGER actors_fixed_identity BEFORE UPDATE OF id, kind ON actors
BEGIN SELECT RAISE(ABORT, 'actor id and kind are fixed'); END;

-- Every actor written to history must be a known, active actor. Triggers instead of foreign keys:
-- adding an FK would mean rebuilding append-only tables.
CREATE TRIGGER audit_events_known_actor BEFORE INSERT ON audit_events
WHEN NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor AND active = 1)
BEGIN SELECT RAISE(ABORT, 'unknown or inactive actor'); END;
CREATE TRIGGER requirement_versions_known_actor BEFORE INSERT ON requirement_versions
WHEN NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor AND active = 1)
BEGIN SELECT RAISE(ABORT, 'unknown or inactive actor'); END;
CREATE TRIGGER decisions_known_actor BEFORE INSERT ON decisions
WHEN NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor AND active = 1)
BEGIN SELECT RAISE(ABORT, 'unknown or inactive actor'); END;

-- Unknown vehicle and market codes are registered as discovered, never rejected. Plain INSERT ... WHERE
-- NOT EXISTS, because an outer INSERT OR REPLACE would turn an inner OR IGNORE into a replace.
CREATE TRIGGER sources_register_scope AFTER INSERT ON sources
BEGIN
    INSERT INTO vehicles (code, status) SELECT NEW.vehicle, 'discovered'
    WHERE NOT EXISTS (SELECT 1 FROM vehicles WHERE code = NEW.vehicle);
    INSERT INTO markets (code, status) SELECT NEW.market, 'discovered'
    WHERE NOT EXISTS (SELECT 1 FROM markets WHERE code = NEW.market);
END;
CREATE TRIGGER evidence_register_scope AFTER INSERT ON evidence
BEGIN
    INSERT INTO vehicles (code, status) SELECT NEW.vehicle, 'discovered'
    WHERE NOT EXISTS (SELECT 1 FROM vehicles WHERE code = NEW.vehicle);
    INSERT INTO markets (code, status) SELECT NEW.market, 'discovered'
    WHERE NOT EXISTS (SELECT 1 FROM markets WHERE code = NEW.market);
END;
CREATE TRIGGER requirements_register_scope AFTER INSERT ON requirements
BEGIN
    INSERT INTO vehicles (code, status) SELECT NEW.vehicle, 'discovered'
    WHERE NOT EXISTS (SELECT 1 FROM vehicles WHERE code = NEW.vehicle);
    INSERT INTO markets (code, status) SELECT NEW.market, 'discovered'
    WHERE NOT EXISTS (SELECT 1 FROM markets WHERE code = NEW.market);
END;

-- Codes already present in a v2 database.
INSERT INTO vehicles (code, status)
SELECT DISTINCT vehicle, 'discovered' FROM (
    SELECT vehicle FROM sources UNION SELECT vehicle FROM evidence UNION SELECT vehicle FROM requirements
) WHERE vehicle NOT IN (SELECT code FROM vehicles);
INSERT INTO markets (code, status)
SELECT DISTINCT market, 'discovered' FROM (
    SELECT market FROM sources UNION SELECT market FROM evidence UNION SELECT market FROM requirements
) WHERE market NOT IN (SELECT code FROM markets);
