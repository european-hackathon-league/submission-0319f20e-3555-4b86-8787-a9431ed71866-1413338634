-- Pod C: request intake and triage (PLATFORM_BUILD_PLAN.md section 8, notes/request-intake.md).
-- Adds to the 0009 request tables; nothing defined there is renamed or removed.
--
-- * Keys MR-<vehicle>-<market>-NNNN come from request_key_sequences in the creating transaction and are
--   never reused (like requirement_key_sequences in 0004).
-- * Classifications are an append-only history; the request row carries the values in effect. Fields a
--   PM set by hand are listed in pm_pinned and are never overwritten by classification or clustering.
-- * Proposed links record how they were found (basis: method, run, matched terms, quote and span).
--   Removing or restoring a link is a PM judgment: status_changed_by is a human (trigger).
-- * 'linked' follows a human 'link' decision like the other decided statuses in 0009, and a decided
--   request never falls back to new/triaged without a new human decision.

-- Last number issued per vehicle and market, so a request key is never reused.
CREATE TABLE request_key_sequences (
    vehicle TEXT NOT NULL,
    market TEXT NOT NULL,
    last_number INTEGER NOT NULL CHECK(last_number >= 0),
    PRIMARY KEY(vehicle, market)
);
INSERT INTO request_key_sequences (vehicle, market, last_number)
SELECT vehicle, market, count(*) FROM intake_requests GROUP BY vehicle, market;

CREATE TRIGGER request_key_sequences_no_delete BEFORE DELETE ON request_key_sequences
BEGIN SELECT RAISE(ABORT, 'request key sequences are never reset'); END;
CREATE TRIGGER request_key_sequences_increase BEFORE UPDATE ON request_key_sequences
WHEN NEW.last_number <= OLD.last_number OR NEW.vehicle IS NOT OLD.vehicle OR NEW.market IS NOT OLD.market
BEGIN SELECT RAISE(ABORT, 'request key sequences only increase'); END;

-- Request attributes. effort is the PM's rough estimate (unknown stays NULL and is flagged in triage);
-- attribute is the finer customer attribute inside the topic (server/intake.py ATTRIBUTES);
-- external_ref is the originating system's reference (fixtures: 'sim-...'), unique and fixed.
ALTER TABLE intake_requests ADD COLUMN effort TEXT CHECK(effort IS NULL OR effort IN ('low', 'medium', 'high'));
ALTER TABLE intake_requests ADD COLUMN attribute TEXT;
ALTER TABLE intake_requests ADD COLUMN pm_pinned TEXT NOT NULL DEFAULT '[]'
    CHECK(json_valid(pm_pinned) AND json_type(pm_pinned) = 'array');
ALTER TABLE intake_requests ADD COLUMN external_ref TEXT;
CREATE UNIQUE INDEX intake_requests_external_ref ON intake_requests(external_ref) WHERE external_ref IS NOT NULL;
CREATE INDEX intake_requests_topic ON intake_requests(vehicle, topic);

CREATE TRIGGER intake_requests_external_ref_fixed BEFORE UPDATE OF external_ref ON intake_requests
WHEN NEW.external_ref IS NOT OLD.external_ref
BEGIN SELECT RAISE(ABORT, 'request identity and text are fixed'); END;

CREATE TRIGGER intake_requests_linked_needs_decision BEFORE UPDATE OF status ON intake_requests
WHEN NEW.status IS NOT OLD.status AND NEW.status = 'linked' AND NOT EXISTS (
    SELECT 1 FROM (SELECT decision FROM request_decisions WHERE request_id = NEW.id
                   ORDER BY rowid DESC LIMIT 1) AS latest
    WHERE latest.decision = 'link')
BEGIN SELECT RAISE(ABORT, 'request status change requires a matching human decision'); END;

CREATE TRIGGER intake_requests_decided_status_kept BEFORE UPDATE OF status ON intake_requests
WHEN NEW.status IS NOT OLD.status AND OLD.status IN ('linked', 'converted', 'declined', 'deferred')
 AND NEW.status IN ('new', 'triaged')
BEGIN SELECT RAISE(ABORT, 'a decided request changes status only through a new human decision'); END;

-- Classification history (keyword baseline or OpenAI), append-only.
CREATE TABLE request_classifications (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES intake_requests(id),
    topic TEXT NOT NULL,
    attribute TEXT,
    scope_flags TEXT NOT NULL CHECK(json_valid(scope_flags) AND json_type(scope_flags) = 'array'),
    basis TEXT NOT NULL CHECK(json_valid(basis)),          -- matched keywords with spans, or model quote + span
    applied TEXT NOT NULL CHECK(json_valid(applied) AND json_type(applied) = 'array'),  -- fields written to the request
    method_version TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id),
    created_at TEXT NOT NULL
);
CREATE INDEX request_classifications_request ON request_classifications(request_id, created_at);
CREATE TRIGGER request_classifications_no_update BEFORE UPDATE ON request_classifications
BEGIN SELECT RAISE(ABORT, 'request_classifications is append-only'); END;
CREATE TRIGGER request_classifications_no_delete BEFORE DELETE ON request_classifications
BEGIN SELECT RAISE(ABORT, 'request_classifications is append-only'); END;

-- Link provenance and the human gate on removal/restoration.
ALTER TABLE request_links ADD COLUMN basis TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(basis));
ALTER TABLE request_links ADD COLUMN run_id TEXT REFERENCES runs(id);
ALTER TABLE request_links ADD COLUMN status_changed_by TEXT;
ALTER TABLE request_links ADD COLUMN status_changed_at TEXT;
CREATE INDEX request_links_request ON request_links(request_id, status);

CREATE TRIGGER request_links_basis_fixed BEFORE UPDATE OF basis, run_id ON request_links
WHEN NEW.basis IS NOT OLD.basis OR NEW.run_id IS NOT OLD.run_id
BEGIN SELECT RAISE(ABORT, 'only a request link status may change'); END;

CREATE TRIGGER request_links_status_human BEFORE UPDATE OF status ON request_links
WHEN NEW.status IS NOT OLD.status
BEGIN
    INSERT INTO actors (id, kind, display_name, role, origin)
    SELECT NEW.status_changed_by, kind, NEW.status_changed_by, CASE kind WHEN 'human' THEN 'pm' ELSE kind END, 'discovered'
    FROM (SELECT CASE WHEN lower(NEW.status_changed_by) GLOB 'ai:*' THEN 'ai'
                      WHEN lower(NEW.status_changed_by) GLOB 'system:*' THEN 'system' ELSE 'human' END AS kind)
    WHERE NEW.status_changed_by IS NOT NULL AND NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.status_changed_by);
    SELECT RAISE(ABORT, 'inactive actor')
    WHERE EXISTS (SELECT 1 FROM actors WHERE id = NEW.status_changed_by AND active = 0);
    SELECT RAISE(ABORT, 'this action requires a human actor')
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.status_changed_by AND kind = 'human')
       OR NEW.status_changed_at IS OLD.status_changed_at;
END;

-- The triage a PM decided on (optional optimistic check; stale triage ids are refused by the API).
ALTER TABLE request_decisions ADD COLUMN triage_id TEXT REFERENCES request_triage(id);

-- Freeze the exact proposal and score on which the PM's intake decision was based.
ALTER TABLE request_decisions ADD COLUMN requirement_version_id TEXT REFERENCES requirement_versions(id);
ALTER TABLE request_decisions ADD COLUMN score_id TEXT REFERENCES scores(id);
