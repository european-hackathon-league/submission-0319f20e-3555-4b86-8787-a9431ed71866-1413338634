-- Pod E: BMW data and market context (PLATFORM_BUILD_PLAN.md, Pod E; notes/bmw-data-coverage.md).
-- Adds to the 0009 tables only: derivation state for market_weights, preserve_attributes and
-- coverage_reports, the sales-region roll-up of the country codes in the BMW workbooks, and
-- market_context for annual-report statements with page citations. Rows are never deleted.

-- Sales-region roll-up ------------------------------------------------------------------------------
-- sales_volumes.xlsx reports four non-overlapping regions (EU = BMW's Europe sales region, CN, US, ROW).
-- Feedback workbooks name individual countries; each rolls up into its region through parent_code, like
-- DE and GB (database/seed.py). Weights and coverage use this chain, so a country never counts twice.
INSERT INTO markets (code, name, parent_code, status) VALUES
    ('DK', 'Denmark', 'EU', 'seeded'),
    ('ES', 'Spain', 'EU', 'seeded'),
    ('FI', 'Finland', 'EU', 'seeded'),
    ('FR', 'France', 'EU', 'seeded'),
    ('LV', 'Latvia', 'EU', 'seeded'),
    ('NO', 'Norway', 'EU', 'seeded'),
    ('SE', 'Sweden', 'EU', 'seeded'),
    ('AU', 'Australia', 'ROW', 'seeded'),
    ('CA', 'Canada', 'ROW', 'seeded'),
    ('JP', 'Japan', 'ROW', 'seeded'),
    ('KR', 'South Korea', 'ROW', 'seeded'),
    ('ZA', 'South Africa', 'ROW', 'seeded')
ON CONFLICT(code) DO UPDATE SET
    name = coalesce(markets.name, excluded.name),
    parent_code = coalesce(markets.parent_code, excluded.parent_code),
    status = CASE WHEN markets.status = 'discovered' THEN 'seeded' ELSE markets.status END;

-- Market weights (sales-share-v1) --------------------------------------------------------------------
-- UNIQUE(vehicle, market, period, method_version) from 0009 stays the identity. Re-deriving unchanged
-- inputs writes nothing (input_hash). Changed inputs update the row in place: revision + 1, a new run_id,
-- and an audit event holding before and after. A market absent from the latest sales file is superseded,
-- so current shares always sum to 1 per vehicle and period.
ALTER TABLE market_weights ADD COLUMN status TEXT NOT NULL DEFAULT 'current'
    CHECK(status IN ('current', 'superseded'));
ALTER TABLE market_weights ADD COLUMN input_hash TEXT;
ALTER TABLE market_weights ADD COLUMN metrics TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metrics));
ALTER TABLE market_weights ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK(revision >= 1);
ALTER TABLE market_weights ADD COLUMN updated_at TEXT;
CREATE INDEX market_weights_scope ON market_weights(vehicle, period, status);

CREATE TRIGGER market_weights_revision BEFORE UPDATE ON market_weights
WHEN NEW.id IS NOT OLD.id OR NEW.vehicle IS NOT OLD.vehicle OR NEW.market IS NOT OLD.market
  OR NEW.period IS NOT OLD.period OR NEW.method_version IS NOT OLD.method_version
  OR NEW.created_at IS NOT OLD.created_at OR NEW.revision IS NOT OLD.revision + 1 OR NEW.run_id IS OLD.run_id
BEGIN SELECT RAISE(ABORT, 'market_weights updates keep identity, increment revision and cite a new run'); END;

-- Preserve attributes (preserve-v1) ------------------------------------------------------------------
-- One row per fingerprint (vehicle, market, topic, attribute, source type, method). attribute is NULL
-- for the topic as a whole. strength is always the deterministic preserve-v1 value; ai holds the
-- provider, model, method_version, run_id and grounded citations when OpenAI named or summarised it.
-- Changes update in place (revision + 1, new run, audit before/after); attributes that no longer
-- qualify are retired, never deleted.
ALTER TABLE preserve_attributes ADD COLUMN attribute TEXT;
ALTER TABLE preserve_attributes ADD COLUMN source_type TEXT NOT NULL DEFAULT 'feedback'
    CHECK(source_type IN ('feedback', 'study'));
ALTER TABLE preserve_attributes ADD COLUMN metrics TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metrics));
ALTER TABLE preserve_attributes ADD COLUMN status TEXT NOT NULL DEFAULT 'current'
    CHECK(status IN ('current', 'retired'));
ALTER TABLE preserve_attributes ADD COLUMN fingerprint TEXT;
ALTER TABLE preserve_attributes ADD COLUMN input_hash TEXT;
ALTER TABLE preserve_attributes ADD COLUMN summary TEXT;
ALTER TABLE preserve_attributes ADD COLUMN ai TEXT CHECK(ai IS NULL OR json_valid(ai));
ALTER TABLE preserve_attributes ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK(revision >= 1);
ALTER TABLE preserve_attributes ADD COLUMN updated_at TEXT;
CREATE UNIQUE INDEX preserve_attributes_fingerprint ON preserve_attributes(fingerprint) WHERE fingerprint IS NOT NULL;

CREATE TRIGGER preserve_attributes_revision BEFORE UPDATE ON preserve_attributes
WHEN NEW.id IS NOT OLD.id OR NEW.vehicle IS NOT OLD.vehicle OR NEW.market IS NOT OLD.market
  OR NEW.topic IS NOT OLD.topic OR NEW.attribute IS NOT OLD.attribute OR NEW.source_type IS NOT OLD.source_type
  OR NEW.method_version IS NOT OLD.method_version OR NEW.fingerprint IS NOT OLD.fingerprint
  OR NEW.created_at IS NOT OLD.created_at OR NEW.revision IS NOT OLD.revision + 1 OR NEW.run_id IS OLD.run_id
BEGIN SELECT RAISE(ABORT, 'preserve_attributes updates keep identity, increment revision and cite a new run'); END;

-- Coverage reports (coverage-v1) ---------------------------------------------------------------------
-- A report is written only when its inputs changed (input_hash); the previous current report of the
-- scope is then superseded. Reports are otherwise immutable.
ALTER TABLE coverage_reports ADD COLUMN status TEXT NOT NULL DEFAULT 'current'
    CHECK(status IN ('current', 'superseded'));
ALTER TABLE coverage_reports ADD COLUMN input_hash TEXT;

CREATE TRIGGER coverage_reports_supersede_only BEFORE UPDATE ON coverage_reports
WHEN NEW.id IS NOT OLD.id OR NEW.vehicle IS NOT OLD.vehicle OR NEW.market IS NOT OLD.market
  OR NEW.metrics IS NOT OLD.metrics OR NEW.warnings IS NOT OLD.warnings
  OR NEW.method_version IS NOT OLD.method_version OR NEW.run_id IS NOT OLD.run_id
  OR NEW.created_at IS NOT OLD.created_at OR NEW.input_hash IS NOT OLD.input_hash
  OR NOT (OLD.status = 'current' AND NEW.status = 'superseded')
BEGIN SELECT RAISE(ABORT, 'coverage_reports are immutable; a current report may only be superseded'); END;

-- Annual-report market context -----------------------------------------------------------------------
-- Market and product-strategy statements located on document pages (never pricing or business cases).
-- Every row cites one page record (evidence_id, page) with an exact quote and its span in that record.
-- provider/method_version say whether OpenAI drafted the statement or the deterministic page locator
-- found it. Append-only; identical re-extractions are deduplicated by fingerprint.
CREATE TABLE market_context (
    id TEXT PRIMARY KEY,
    vehicle TEXT NOT NULL,
    market TEXT NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('regional_sales', 'series_deliveries', 'ev_adoption',
        'digital_services', 'neue_klasse', 'rd_priorities')),
    statement TEXT NOT NULL CHECK(length(trim(statement)) > 0),
    subject_market TEXT,
    subject_series TEXT,
    value TEXT,
    unit TEXT,
    period TEXT,
    source_id TEXT NOT NULL REFERENCES sources(id),
    evidence_id TEXT NOT NULL REFERENCES evidence(id),
    page INTEGER,
    quote TEXT NOT NULL CHECK(length(trim(quote)) > 0),
    span TEXT NOT NULL CHECK(json_valid(span) AND json_type(span) = 'array'),
    provider TEXT NOT NULL CHECK(provider IN ('openai', 'deterministic')),
    method_version TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id),
    fingerprint TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE INDEX market_context_scope ON market_context(vehicle, market, category);
CREATE INDEX market_context_source ON market_context(source_id, page);
CREATE TRIGGER market_context_no_update BEFORE UPDATE ON market_context
BEGIN SELECT RAISE(ABORT, 'market_context is append-only'); END;
CREATE TRIGGER market_context_no_delete BEFORE DELETE ON market_context
BEGIN SELECT RAISE(ABORT, 'market_context is append-only'); END;

-- Current state for consumers (Pods B and D) that should not see superseded or retired rows.
CREATE VIEW v_market_weights_current AS
SELECT * FROM market_weights WHERE status = 'current';
CREATE VIEW v_preserve_attributes_current AS
SELECT * FROM preserve_attributes WHERE status = 'current';
CREATE VIEW v_coverage_current AS
SELECT * FROM coverage_reports WHERE status = 'current';
