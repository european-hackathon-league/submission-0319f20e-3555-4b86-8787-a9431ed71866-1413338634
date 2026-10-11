-- Platform foundation (PLATFORM_BUILD_PLAN.md section 5.1): agent substrate, signals and sentiment,
-- markets, requests, prioritization, BMW market context and the shared OpenAI response cache.
-- Every table any pod consumes exists here, so pods 0010-0015 only add to it.
--
-- Conventions: TEXT ids from store.new_id(), ISO-8601 UTC TEXT timestamps, JSON in TEXT with json_valid.
-- Rows are never deleted (status changes instead). Decision-like rows are append-only and human-only:
-- the API rejects ai:/system: actors and these triggers refuse them independently of API code.
-- Every actor column registers unknown actors as discovered (like 0007), then rejects inactive ones.

-- Agent substrate ------------------------------------------------------------------------------------

-- One row per agent role. Agents act as actors 'ai:agent:<slug>' (the deterministic scorer as
-- 'system:agent:<slug>'); inserting an agent registers its actor.
CREATE TABLE agents (
    id TEXT PRIMARY KEY CHECK(id IN ('ai:agent:' || slug, 'system:agent:' || slug)),
    slug TEXT NOT NULL UNIQUE CHECK(slug GLOB '[a-z0-9]*' AND slug NOT GLOB '*[^a-z0-9-]*'),
    display_name TEXT NOT NULL,
    department TEXT NOT NULL CHECK(department IN
        ('orchestration', 'customer_insights', 'market_intelligence', 'requirements', 'governance', 'communications')),
    description TEXT NOT NULL,
    autonomy_level TEXT NOT NULL CHECK(autonomy_level IN ('A0', 'A1', 'A2', 'A3')),
    capabilities TEXT NOT NULL CHECK(json_valid(capabilities) AND json_type(capabilities) = 'array'),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'paused', 'retired')),
    parent_agent_id TEXT REFERENCES agents(id),
    status_changed_by TEXT,                        -- human who last paused/resumed/retired (trigger)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Work queue; the next phase's Kanban board. Every update increments revision (optimistic locking).
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    vehicle TEXT NOT NULL,
    market TEXT NOT NULL,
    topic TEXT,
    capability TEXT NOT NULL,
    title TEXT NOT NULL,
    input TEXT NOT NULL CHECK(json_valid(input)),
    requested_by TEXT NOT NULL,
    assigned_agent_id TEXT REFERENCES agents(id),
    parent_task_id TEXT REFERENCES tasks(id),
    status TEXT NOT NULL CHECK(status IN
        ('backlog', 'queued', 'running', 'awaiting_human', 'succeeded', 'failed', 'cancelled')),
    priority INTEGER NOT NULL DEFAULT 50 CHECK(priority BETWEEN 0 AND 100),
    recurrence_days INTEGER CHECK(recurrence_days IS NULL OR recurrence_days > 0),
    due_at TEXT,
    last_run_id TEXT,
    revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX tasks_scope_status ON tasks(vehicle, market, status);
CREATE INDEX tasks_due ON tasks(status, due_at) WHERE recurrence_days IS NOT NULL;

-- Every capability execution, whether triggered by a human, a task or an agent (server/platform.py).
CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    capability TEXT NOT NULL,
    task_id TEXT REFERENCES tasks(id),
    actor TEXT NOT NULL,
    vehicle TEXT,
    market TEXT,
    method_version TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    inputs TEXT NOT NULL CHECK(json_valid(inputs)),
    outputs TEXT CHECK(outputs IS NULL OR json_valid(outputs)),
    metrics TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metrics)),
    status TEXT NOT NULL CHECK(status IN ('running', 'succeeded', 'failed')),
    error TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    CHECK((status = 'running') = (finished_at IS NULL))
);
CREATE INDEX runs_capability ON runs(capability, started_at);
CREATE INDEX runs_task ON runs(task_id);
CREATE INDEX runs_scope ON runs(vehicle, market, started_at);

CREATE TABLE threads (
    id TEXT PRIMARY KEY,
    vehicle TEXT,
    market TEXT,
    kind TEXT NOT NULL CHECK(kind IN ('agent', 'human', 'request', 'review')),
    subject TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'closed'))
);
CREATE INDEX threads_entity ON threads(entity_type, entity_id);

-- Internal working conversation records; append-only. Nothing here is ever sent externally.
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES threads(id),
    author TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('human', 'agent', 'system', 'tool')),
    body TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(payload)),
    run_id TEXT REFERENCES runs(id),
    created_at TEXT NOT NULL
);
CREATE INDEX messages_thread ON messages(thread_id, created_at);

-- Shared OpenAI response cache (server/llm.py): identical requests never cost a second call.
CREATE TABLE llm_cache (
    input_hash TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    response TEXT NOT NULL CHECK(json_valid(response)),
    usage TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(usage)),
    created_at TEXT NOT NULL,
    UNIQUE(input_hash, model, prompt_version)
);

-- Signals and sentiment (Pod A) ---------------------------------------------------------------------

-- A PM-authorised standing search; its rationale is the authorisation for repeated public searches.
CREATE TABLE watchlists (
    id TEXT PRIMARY KEY,
    vehicle TEXT NOT NULL,
    market TEXT NOT NULL,
    topic TEXT NOT NULL,
    label TEXT NOT NULL,
    query_terms TEXT NOT NULL CHECK(json_valid(query_terms)),   -- template parts only, never evidence text
    competitors TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(competitors)),
    domain_group TEXT NOT NULL CHECK(domain_group IN ('press', 'forums', 'social', 'video', 'all')),
    domains TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(domains)),
    cadence_days INTEGER NOT NULL DEFAULT 7 CHECK(cadence_days BETWEEN 1 AND 90),
    max_results INTEGER NOT NULL DEFAULT 10 CHECK(max_results BETWEEN 1 AND 10),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'paused')),
    created_by TEXT NOT NULL,                      -- human only (trigger)
    rationale TEXT NOT NULL CHECK(length(trim(rationale)) > 0),
    status_changed_by TEXT,                        -- human who last paused/resumed (trigger)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX watchlists_scope ON watchlists(vehicle, market, topic);

-- Unreviewed public monitoring results. Not evidence until a human imports one.
CREATE TABLE signal_items (
    id TEXT PRIMARY KEY,
    watchlist_id TEXT NOT NULL REFERENCES watchlists(id),
    run_id TEXT NOT NULL REFERENCES runs(id),
    vehicle TEXT NOT NULL,
    market TEXT NOT NULL,
    topic TEXT NOT NULL,
    url TEXT NOT NULL,
    url_hash TEXT NOT NULL,
    domain TEXT NOT NULL,
    title TEXT,
    excerpt TEXT NOT NULL CHECK(length(excerpt) <= 1000),
    content_hash TEXT NOT NULL,
    published_at TEXT,
    retrieved_at TEXT NOT NULL,
    date_basis TEXT NOT NULL CHECK(date_basis IN ('published', 'retrieved')),
    review_status TEXT NOT NULL DEFAULT 'unreviewed' CHECK(review_status IN ('unreviewed', 'imported', 'dismissed')),
    evidence_id TEXT REFERENCES evidence(id),
    reviewed_by TEXT,                              -- human who imported or dismissed (trigger)
    reviewed_at TEXT,
    UNIQUE(watchlist_id, url_hash, content_hash),
    CHECK((review_status = 'imported') = (evidence_id IS NOT NULL)),
    CHECK((review_status = 'unreviewed') = (reviewed_by IS NULL))
);
CREATE INDEX signal_items_scope ON signal_items(vehicle, market, topic, review_status);

CREATE TABLE sentiment_scores (
    id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL CHECK(subject_type IN ('signal_item', 'evidence')),
    subject_id TEXT NOT NULL,
    topic TEXT,
    method_version TEXT NOT NULL,                  -- 'lexicon-v1' or 'openai:<model>:<prompt_version>'
    polarity REAL NOT NULL CHECK(polarity BETWEEN -1 AND 1),
    label TEXT NOT NULL CHECK(label IN ('positive', 'negative', 'neutral', 'mixed')),
    aspects TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(aspects)),  -- [{topic, polarity, span:[start,end]}]
    input_hash TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id),
    created_at TEXT NOT NULL,
    UNIQUE(subject_type, subject_id, method_version)
);
CREATE INDEX sentiment_scores_subject ON sentiment_scores(subject_type, subject_id);

-- Markets (Pod B; market_weights populated by Pod E) ------------------------------------------------

CREATE TABLE market_weights (
    id TEXT PRIMARY KEY,
    vehicle TEXT NOT NULL,
    market TEXT NOT NULL,
    period TEXT NOT NULL,
    units REAL NOT NULL CHECK(units >= 0),
    share REAL NOT NULL CHECK(share BETWEEN 0 AND 1),
    evidence_ids TEXT NOT NULL CHECK(json_valid(evidence_ids)),
    method_version TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id),
    created_at TEXT NOT NULL,
    UNIQUE(vehicle, market, period, method_version)
);

CREATE TABLE market_conflicts (
    id TEXT PRIMARY KEY,
    vehicle TEXT NOT NULL,
    topic TEXT NOT NULL,
    related_topic TEXT,
    markets TEXT NOT NULL CHECK(json_valid(markets)),
    conflict_type TEXT NOT NULL CHECK(conflict_type IN
        ('priority_divergence', 'direction_conflict', 'target_incompatible', 'evidence_gap')),
    severity TEXT NOT NULL CHECK(severity IN ('low', 'medium', 'high')),
    metrics TEXT NOT NULL CHECK(json_valid(metrics)),
    evidence_ids TEXT NOT NULL CHECK(json_valid(evidence_ids)),
    requirement_ids TEXT NOT NULL CHECK(json_valid(requirement_ids)),
    recommendation TEXT NOT NULL CHECK(recommendation IN
        ('global', 'market_variant', 'selectable_mode', 'optional_package', 'pm_tradeoff', 'needs_research')),
    rationale TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    method_version TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id),
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'resolved', 'superseded', 'dismissed')),
    created_at TEXT NOT NULL
);
CREATE INDEX market_conflicts_scope ON market_conflicts(vehicle, status);
-- Re-detection is idempotent: at most one open conflict per fingerprint; changed inputs supersede it.
CREATE UNIQUE INDEX market_conflicts_one_open ON market_conflicts(fingerprint) WHERE status = 'open';

CREATE TABLE market_resolutions (
    id TEXT PRIMARY KEY,
    conflict_id TEXT NOT NULL REFERENCES market_conflicts(id),
    decision TEXT NOT NULL CHECK(decision IN
        ('adopt_global', 'market_variants', 'selectable_mode', 'optional_package', 'defer', 'dismiss')),
    actor TEXT NOT NULL,                           -- human PM only (trigger)
    rationale TEXT NOT NULL CHECK(length(trim(rationale)) > 0),
    requirement_ids TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(requirement_ids)),
    created_at TEXT NOT NULL
);
CREATE INDEX market_resolutions_conflict ON market_resolutions(conflict_id, created_at);

-- Requests (Pod C) ----------------------------------------------------------------------------------

CREATE TABLE request_clusters (
    id TEXT PRIMARY KEY,
    vehicle TEXT NOT NULL,
    topic TEXT NOT NULL,
    canonical_title TEXT NOT NULL,
    method_version TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id),
    created_at TEXT NOT NULL
);

CREATE TABLE intake_requests (
    id TEXT PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,                      -- 'MR-G60-CN-0001', assigned by the API
    vehicle TEXT NOT NULL,
    market TEXT NOT NULL,
    origin_type TEXT NOT NULL CHECK(origin_type IN
        ('market_org', 'dealer', 'engineering', 'sales', 'board', 'customer_channel', 'other')),
    origin_name TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    topic TEXT,
    requested_at TEXT NOT NULL,
    simulated INTEGER NOT NULL DEFAULT 0 CHECK(simulated IN (0, 1)),
    scope_flags TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(scope_flags)),
    status TEXT NOT NULL CHECK(status IN ('new', 'triaged', 'linked', 'converted', 'declined', 'deferred')),
    cluster_id TEXT REFERENCES request_clusters(id),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX intake_requests_scope ON intake_requests(vehicle, market, status);
CREATE INDEX intake_requests_cluster ON intake_requests(cluster_id);

CREATE TABLE request_links (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES intake_requests(id),
    entity_type TEXT NOT NULL CHECK(entity_type IN ('requirement', 'finding', 'evidence', 'market_conflict')),
    entity_id TEXT NOT NULL,
    relation TEXT NOT NULL CHECK(relation IN ('supports', 'conflicts', 'duplicates', 'addresses')),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'removed')),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(request_id, entity_type, entity_id, relation)
);

CREATE TABLE request_triage (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES intake_requests(id),
    rubric_version TEXT NOT NULL,
    factors TEXT NOT NULL CHECK(json_valid(factors)),
    weights TEXT NOT NULL CHECK(json_valid(weights)),
    total REAL NOT NULL,
    explanation TEXT NOT NULL CHECK(json_valid(explanation)),
    run_id TEXT NOT NULL REFERENCES runs(id),
    created_at TEXT NOT NULL
);
CREATE INDEX request_triage_request ON request_triage(request_id, created_at);

CREATE TABLE request_decisions (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES intake_requests(id),
    decision TEXT NOT NULL CHECK(decision IN ('convert', 'link', 'decline', 'defer')),
    actor TEXT NOT NULL,                           -- human PM only (trigger)
    rationale TEXT NOT NULL CHECK(length(trim(rationale)) > 0),
    requirement_id TEXT REFERENCES requirements(id),
    created_at TEXT NOT NULL
);
CREATE INDEX request_decisions_request ON request_decisions(request_id, created_at);

-- Prioritization (Pod D) ----------------------------------------------------------------------------

CREATE TABLE priority_inputs (
    id TEXT PRIMARY KEY,
    requirement_id TEXT NOT NULL REFERENCES requirements(id),
    version_id TEXT NOT NULL REFERENCES requirement_versions(id),
    factor TEXT NOT NULL,
    value REAL NOT NULL CHECK(value BETWEEN 0 AND 5),
    derivation TEXT NOT NULL CHECK(json_valid(derivation)),
    method_version TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id),
    created_at TEXT NOT NULL
);
CREATE INDEX priority_inputs_version ON priority_inputs(version_id, factor, created_at);

CREATE TABLE priority_sensitivity (
    id TEXT PRIMARY KEY,
    vehicle TEXT NOT NULL,
    market TEXT NOT NULL,
    rubric_version TEXT NOT NULL,
    perturbation TEXT NOT NULL CHECK(json_valid(perturbation)),
    results TEXT NOT NULL CHECK(json_valid(results)),
    run_id TEXT NOT NULL REFERENCES runs(id),
    created_at TEXT NOT NULL
);

CREATE TABLE scope_rubrics (
    id TEXT PRIMARY KEY,
    vehicle TEXT NOT NULL,
    market TEXT NOT NULL,
    rubric_version TEXT NOT NULL,
    weights TEXT NOT NULL CHECK(json_valid(weights)),
    actor TEXT NOT NULL,                           -- human PM only (trigger)
    rationale TEXT NOT NULL CHECK(length(trim(rationale)) > 0),
    created_at TEXT NOT NULL
);
CREATE INDEX scope_rubrics_scope ON scope_rubrics(vehicle, market, created_at);

-- BMW data and context (Pod E) ----------------------------------------------------------------------

CREATE TABLE preserve_attributes (
    id TEXT PRIMARY KEY,
    vehicle TEXT NOT NULL,
    market TEXT NOT NULL,
    topic TEXT NOT NULL,
    label TEXT NOT NULL,
    evidence_ids TEXT NOT NULL CHECK(json_valid(evidence_ids)),
    strength REAL NOT NULL CHECK(strength BETWEEN 0 AND 1),
    method_version TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id),
    created_at TEXT NOT NULL
);
CREATE INDEX preserve_attributes_scope ON preserve_attributes(vehicle, market, topic);

CREATE TABLE coverage_reports (
    id TEXT PRIMARY KEY,
    vehicle TEXT NOT NULL,
    market TEXT NOT NULL,
    metrics TEXT NOT NULL CHECK(json_valid(metrics)),
    warnings TEXT NOT NULL CHECK(json_valid(warnings)),
    method_version TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id),
    created_at TEXT NOT NULL
);
CREATE INDEX coverage_reports_scope ON coverage_reports(vehicle, market, created_at);

-- Weekly sentiment, keeping BMW evidence, imported public pages and unreviewed monitoring apart.
-- The date is published_at / observed_at; retrieval or import dates are counted in undated_n.
-- Topic is the score's primary topic; Pod A may recreate this view with the same leading columns.
CREATE VIEW v_sentiment_weekly AS
WITH scored AS (
    SELECT si.vehicle, si.market, coalesce(s.topic, si.topic) AS topic, 'public_monitoring' AS source_class,
           s.method_version, s.polarity, s.label, coalesce(si.published_at, si.retrieved_at) AS dated_at,
           CASE WHEN si.published_at IS NULL THEN 1 ELSE 0 END AS undated, s.subject_id
    FROM sentiment_scores s JOIN signal_items si ON s.subject_type = 'signal_item' AND si.id = s.subject_id
    UNION ALL
    SELECT e.vehicle, e.market, s.topic, CASE WHEN src.kind = 'web' THEN 'public_imported' ELSE 'bmw_evidence' END,
           s.method_version, s.polarity, s.label, coalesce(e.observed_at, e.created_at),
           CASE WHEN e.observed_at IS NULL THEN 1 ELSE 0 END, s.subject_id
    FROM sentiment_scores s JOIN evidence e ON s.subject_type = 'evidence' AND e.id = s.subject_id
    JOIN sources src ON src.id = e.source_id
)
SELECT vehicle, market, topic, strftime('%Y-%W', dated_at) AS week, source_class, method_version,
       count(*) AS n, avg(polarity) AS mean_polarity,
       avg(CASE WHEN label = 'negative' THEN 1.0 ELSE 0.0 END) AS negative_share,
       avg(CASE WHEN label = 'positive' THEN 1.0 ELSE 0.0 END) AS positive_share,
       sum(undated) AS undated_n, json_group_array(subject_id) AS subject_ids
FROM scored
GROUP BY vehicle, market, topic, week, source_class, method_version;

-- Actor registration and human gates ----------------------------------------------------------------

CREATE TRIGGER agents_register_actor BEFORE INSERT ON agents
BEGIN
    INSERT INTO actors (id, kind, display_name, role, origin)
    SELECT NEW.id, kind, NEW.display_name, kind, 'seeded'
    FROM (SELECT CASE WHEN NEW.id GLOB 'system:*' THEN 'system' ELSE 'ai' END AS kind)
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.id);
    SELECT RAISE(ABORT, 'agent actors must be ai or system actors')
    WHERE EXISTS (SELECT 1 FROM actors WHERE id = NEW.id AND kind = 'human');
END;

CREATE TRIGGER agents_identity_fixed BEFORE UPDATE OF id, slug, created_at ON agents
WHEN NEW.id IS NOT OLD.id OR NEW.slug IS NOT OLD.slug OR NEW.created_at IS NOT OLD.created_at
BEGIN SELECT RAISE(ABORT, 'agent identity is fixed'); END;

-- Pause, resume and retire are human decisions: status_changed_by is set in the same UPDATE.
CREATE TRIGGER agents_status_human BEFORE UPDATE OF status ON agents
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
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.status_changed_by AND kind = 'human');
END;

CREATE TRIGGER tasks_actor BEFORE INSERT ON tasks
BEGIN
    INSERT INTO actors (id, kind, display_name, role, origin)
    SELECT NEW.requested_by, kind, NEW.requested_by, CASE kind WHEN 'human' THEN 'pm' ELSE kind END, 'discovered'
    FROM (SELECT CASE WHEN lower(NEW.requested_by) GLOB 'ai:*' THEN 'ai'
                      WHEN lower(NEW.requested_by) GLOB 'system:*' THEN 'system' ELSE 'human' END AS kind)
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.requested_by);
    SELECT RAISE(ABORT, 'inactive actor') WHERE EXISTS (SELECT 1 FROM actors WHERE id = NEW.requested_by AND active = 0);
END;

CREATE TRIGGER tasks_revision BEFORE UPDATE ON tasks
WHEN NEW.revision IS NOT OLD.revision + 1 OR NEW.id IS NOT OLD.id OR NEW.requested_by IS NOT OLD.requested_by
  OR NEW.created_at IS NOT OLD.created_at
BEGIN SELECT RAISE(ABORT, 'task updates must keep identity and increment revision'); END;

CREATE TRIGGER runs_actor BEFORE INSERT ON runs
BEGIN
    INSERT INTO actors (id, kind, display_name, role, origin)
    SELECT NEW.actor, kind, NEW.actor, CASE kind WHEN 'human' THEN 'pm' ELSE kind END, 'discovered'
    FROM (SELECT CASE WHEN lower(NEW.actor) GLOB 'ai:*' THEN 'ai'
                      WHEN lower(NEW.actor) GLOB 'system:*' THEN 'system' ELSE 'human' END AS kind)
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor);
    SELECT RAISE(ABORT, 'inactive actor') WHERE EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor AND active = 0);
END;

-- A running run may record its outcome once; the identity and inputs never change.
CREATE TRIGGER runs_finished_immutable BEFORE UPDATE ON runs
WHEN OLD.finished_at IS NOT NULL OR NEW.id IS NOT OLD.id OR NEW.capability IS NOT OLD.capability
  OR NEW.task_id IS NOT OLD.task_id OR NEW.actor IS NOT OLD.actor OR NEW.vehicle IS NOT OLD.vehicle
  OR NEW.market IS NOT OLD.market OR NEW.method_version IS NOT OLD.method_version
  OR NEW.input_hash IS NOT OLD.input_hash OR NEW.inputs IS NOT OLD.inputs OR NEW.started_at IS NOT OLD.started_at
BEGIN SELECT RAISE(ABORT, 'runs are immutable once finished; identity and inputs are fixed'); END;

CREATE TRIGGER threads_actor BEFORE INSERT ON threads
BEGIN
    INSERT INTO actors (id, kind, display_name, role, origin)
    SELECT NEW.created_by, kind, NEW.created_by, CASE kind WHEN 'human' THEN 'pm' ELSE kind END, 'discovered'
    FROM (SELECT CASE WHEN lower(NEW.created_by) GLOB 'ai:*' THEN 'ai'
                      WHEN lower(NEW.created_by) GLOB 'system:*' THEN 'system' ELSE 'human' END AS kind)
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.created_by);
    SELECT RAISE(ABORT, 'inactive actor') WHERE EXISTS (SELECT 1 FROM actors WHERE id = NEW.created_by AND active = 0);
END;

CREATE TRIGGER threads_identity_fixed BEFORE UPDATE ON threads
WHEN NEW.id IS NOT OLD.id OR NEW.kind IS NOT OLD.kind OR NEW.subject IS NOT OLD.subject
  OR NEW.entity_type IS NOT OLD.entity_type OR NEW.entity_id IS NOT OLD.entity_id
  OR NEW.created_by IS NOT OLD.created_by OR NEW.created_at IS NOT OLD.created_at
  OR NEW.vehicle IS NOT OLD.vehicle OR NEW.market IS NOT OLD.market
BEGIN SELECT RAISE(ABORT, 'only a thread status may change'); END;

CREATE TRIGGER messages_actor BEFORE INSERT ON messages
BEGIN
    INSERT INTO actors (id, kind, display_name, role, origin)
    SELECT NEW.author, kind, NEW.author, CASE kind WHEN 'human' THEN 'pm' ELSE kind END, 'discovered'
    FROM (SELECT CASE WHEN lower(NEW.author) GLOB 'ai:*' THEN 'ai'
                      WHEN lower(NEW.author) GLOB 'system:*' THEN 'system' ELSE 'human' END AS kind)
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.author);
    SELECT RAISE(ABORT, 'inactive actor') WHERE EXISTS (SELECT 1 FROM actors WHERE id = NEW.author AND active = 0);
    SELECT RAISE(ABORT, 'messages cannot be added to a closed thread')
    WHERE EXISTS (SELECT 1 FROM threads WHERE id = NEW.thread_id AND status = 'closed');
END;

CREATE TRIGGER watchlists_human_actor BEFORE INSERT ON watchlists
BEGIN
    INSERT INTO actors (id, kind, display_name, role, origin)
    SELECT NEW.created_by, kind, NEW.created_by, CASE kind WHEN 'human' THEN 'pm' ELSE kind END, 'discovered'
    FROM (SELECT CASE WHEN lower(NEW.created_by) GLOB 'ai:*' THEN 'ai'
                      WHEN lower(NEW.created_by) GLOB 'system:*' THEN 'system' ELSE 'human' END AS kind)
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.created_by);
    SELECT RAISE(ABORT, 'inactive actor') WHERE EXISTS (SELECT 1 FROM actors WHERE id = NEW.created_by AND active = 0);
    SELECT RAISE(ABORT, 'this action requires a human actor')
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.created_by AND kind = 'human');
END;

CREATE TRIGGER watchlists_identity_fixed BEFORE UPDATE OF id, vehicle, market, created_by, created_at ON watchlists
WHEN NEW.id IS NOT OLD.id OR NEW.vehicle IS NOT OLD.vehicle OR NEW.market IS NOT OLD.market
  OR NEW.created_by IS NOT OLD.created_by OR NEW.created_at IS NOT OLD.created_at
BEGIN SELECT RAISE(ABORT, 'watchlist identity is fixed'); END;

CREATE TRIGGER watchlists_status_human BEFORE UPDATE OF status ON watchlists
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
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.status_changed_by AND kind = 'human');
END;

-- Monitoring content is fixed; only a human review (import or dismiss) changes an item.
CREATE TRIGGER signal_items_content_fixed BEFORE UPDATE ON signal_items
WHEN NEW.id IS NOT OLD.id OR NEW.watchlist_id IS NOT OLD.watchlist_id OR NEW.run_id IS NOT OLD.run_id
  OR NEW.vehicle IS NOT OLD.vehicle OR NEW.market IS NOT OLD.market OR NEW.topic IS NOT OLD.topic
  OR NEW.url IS NOT OLD.url OR NEW.url_hash IS NOT OLD.url_hash OR NEW.domain IS NOT OLD.domain
  OR NEW.title IS NOT OLD.title OR NEW.excerpt IS NOT OLD.excerpt OR NEW.content_hash IS NOT OLD.content_hash
  OR NEW.published_at IS NOT OLD.published_at OR NEW.retrieved_at IS NOT OLD.retrieved_at
  OR NEW.date_basis IS NOT OLD.date_basis OR OLD.review_status <> 'unreviewed'
BEGIN SELECT RAISE(ABORT, 'signal items are reviewed once; their content is fixed'); END;

CREATE TRIGGER signal_items_review_human BEFORE UPDATE OF review_status ON signal_items
WHEN NEW.review_status IS NOT OLD.review_status
BEGIN
    INSERT INTO actors (id, kind, display_name, role, origin)
    SELECT NEW.reviewed_by, kind, NEW.reviewed_by, CASE kind WHEN 'human' THEN 'pm' ELSE kind END, 'discovered'
    FROM (SELECT CASE WHEN lower(NEW.reviewed_by) GLOB 'ai:*' THEN 'ai'
                      WHEN lower(NEW.reviewed_by) GLOB 'system:*' THEN 'system' ELSE 'human' END AS kind)
    WHERE NEW.reviewed_by IS NOT NULL AND NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.reviewed_by);
    SELECT RAISE(ABORT, 'inactive actor') WHERE EXISTS (SELECT 1 FROM actors WHERE id = NEW.reviewed_by AND active = 0);
    SELECT RAISE(ABORT, 'this action requires a human actor')
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.reviewed_by AND kind = 'human');
END;

-- Detected conflicts are evidence of a moment: only status and metrics (e.g. a later AI brief) change.
CREATE TRIGGER market_conflicts_fixed BEFORE UPDATE ON market_conflicts
WHEN NEW.id IS NOT OLD.id OR NEW.vehicle IS NOT OLD.vehicle OR NEW.topic IS NOT OLD.topic
  OR NEW.related_topic IS NOT OLD.related_topic OR NEW.markets IS NOT OLD.markets
  OR NEW.conflict_type IS NOT OLD.conflict_type OR NEW.severity IS NOT OLD.severity
  OR NEW.evidence_ids IS NOT OLD.evidence_ids OR NEW.requirement_ids IS NOT OLD.requirement_ids
  OR NEW.recommendation IS NOT OLD.recommendation OR NEW.rationale IS NOT OLD.rationale
  OR NEW.fingerprint IS NOT OLD.fingerprint OR NEW.method_version IS NOT OLD.method_version
  OR NEW.run_id IS NOT OLD.run_id OR NEW.created_at IS NOT OLD.created_at
BEGIN SELECT RAISE(ABORT, 'detected conflicts are fixed; supersede them instead'); END;

-- resolved / dismissed follow the latest human resolution; superseded is set by re-detection.
CREATE TRIGGER market_conflicts_status_workflow BEFORE UPDATE OF status ON market_conflicts
WHEN NEW.status IS NOT OLD.status AND (
    OLD.status <> 'open'
    OR (NEW.status = 'resolved' AND NOT EXISTS (
        SELECT 1 FROM (SELECT decision FROM market_resolutions WHERE conflict_id = NEW.id
                       ORDER BY rowid DESC LIMIT 1) AS latest WHERE latest.decision NOT IN ('defer', 'dismiss')))
    OR (NEW.status = 'dismissed' AND NOT EXISTS (
        SELECT 1 FROM (SELECT decision FROM market_resolutions WHERE conflict_id = NEW.id
                       ORDER BY rowid DESC LIMIT 1) AS latest WHERE latest.decision = 'dismiss'))
)
BEGIN SELECT RAISE(ABORT, 'conflict status change is not allowed by the resolution workflow'); END;

CREATE TRIGGER market_resolutions_human_actor BEFORE INSERT ON market_resolutions
BEGIN
    INSERT INTO actors (id, kind, display_name, role, origin)
    SELECT NEW.actor, kind, NEW.actor, CASE kind WHEN 'human' THEN 'pm' ELSE kind END, 'discovered'
    FROM (SELECT CASE WHEN lower(NEW.actor) GLOB 'ai:*' THEN 'ai'
                      WHEN lower(NEW.actor) GLOB 'system:*' THEN 'system' ELSE 'human' END AS kind)
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor);
    SELECT RAISE(ABORT, 'inactive actor') WHERE EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor AND active = 0);
    SELECT RAISE(ABORT, 'this action requires a human actor')
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor AND kind = 'human');
END;

CREATE TRIGGER intake_requests_actor BEFORE INSERT ON intake_requests
BEGIN
    INSERT INTO actors (id, kind, display_name, role, origin)
    SELECT NEW.created_by, kind, NEW.created_by, CASE kind WHEN 'human' THEN 'pm' ELSE kind END, 'discovered'
    FROM (SELECT CASE WHEN lower(NEW.created_by) GLOB 'ai:*' THEN 'ai'
                      WHEN lower(NEW.created_by) GLOB 'system:*' THEN 'system' ELSE 'human' END AS kind)
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.created_by);
    SELECT RAISE(ABORT, 'inactive actor') WHERE EXISTS (SELECT 1 FROM actors WHERE id = NEW.created_by AND active = 0);
END;

-- What was asked, by whom and when is fixed; topic, origin, clustering and status are edited (audited).
CREATE TRIGGER intake_requests_identity_fixed BEFORE UPDATE ON intake_requests
WHEN NEW.id IS NOT OLD.id OR NEW.key IS NOT OLD.key OR NEW.vehicle IS NOT OLD.vehicle OR NEW.market IS NOT OLD.market
  OR NEW.title IS NOT OLD.title OR NEW.body IS NOT OLD.body OR NEW.requested_at IS NOT OLD.requested_at
  OR NEW.simulated IS NOT OLD.simulated OR NEW.created_by IS NOT OLD.created_by OR NEW.created_at IS NOT OLD.created_at
BEGIN SELECT RAISE(ABORT, 'request identity and text are fixed'); END;

-- converted / declined / deferred follow the latest human request decision.
CREATE TRIGGER intake_requests_status_workflow BEFORE UPDATE OF status ON intake_requests
WHEN NEW.status IS NOT OLD.status AND NEW.status IN ('converted', 'declined', 'deferred') AND NOT EXISTS (
    SELECT 1 FROM (SELECT decision FROM request_decisions WHERE request_id = NEW.id
                   ORDER BY rowid DESC LIMIT 1) AS latest
    WHERE latest.decision = CASE NEW.status WHEN 'converted' THEN 'convert'
                                            WHEN 'declined' THEN 'decline' ELSE 'defer' END)
BEGIN SELECT RAISE(ABORT, 'request status change requires a matching human decision'); END;

CREATE TRIGGER request_links_actor BEFORE INSERT ON request_links
BEGIN
    INSERT INTO actors (id, kind, display_name, role, origin)
    SELECT NEW.created_by, kind, NEW.created_by, CASE kind WHEN 'human' THEN 'pm' ELSE kind END, 'discovered'
    FROM (SELECT CASE WHEN lower(NEW.created_by) GLOB 'ai:*' THEN 'ai'
                      WHEN lower(NEW.created_by) GLOB 'system:*' THEN 'system' ELSE 'human' END AS kind)
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.created_by);
    SELECT RAISE(ABORT, 'inactive actor') WHERE EXISTS (SELECT 1 FROM actors WHERE id = NEW.created_by AND active = 0);
END;

CREATE TRIGGER request_links_fixed BEFORE UPDATE ON request_links
WHEN NEW.id IS NOT OLD.id OR NEW.request_id IS NOT OLD.request_id OR NEW.entity_type IS NOT OLD.entity_type
  OR NEW.entity_id IS NOT OLD.entity_id OR NEW.relation IS NOT OLD.relation
  OR NEW.created_by IS NOT OLD.created_by OR NEW.created_at IS NOT OLD.created_at
BEGIN SELECT RAISE(ABORT, 'only a request link status may change'); END;

CREATE TRIGGER request_decisions_human_actor BEFORE INSERT ON request_decisions
BEGIN
    INSERT INTO actors (id, kind, display_name, role, origin)
    SELECT NEW.actor, kind, NEW.actor, CASE kind WHEN 'human' THEN 'pm' ELSE kind END, 'discovered'
    FROM (SELECT CASE WHEN lower(NEW.actor) GLOB 'ai:*' THEN 'ai'
                      WHEN lower(NEW.actor) GLOB 'system:*' THEN 'system' ELSE 'human' END AS kind)
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor);
    SELECT RAISE(ABORT, 'inactive actor') WHERE EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor AND active = 0);
    SELECT RAISE(ABORT, 'this action requires a human actor')
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor AND kind = 'human');
END;

CREATE TRIGGER scope_rubrics_human_actor BEFORE INSERT ON scope_rubrics
BEGIN
    INSERT INTO actors (id, kind, display_name, role, origin)
    SELECT NEW.actor, kind, NEW.actor, CASE kind WHEN 'human' THEN 'pm' ELSE kind END, 'discovered'
    FROM (SELECT CASE WHEN lower(NEW.actor) GLOB 'ai:*' THEN 'ai'
                      WHEN lower(NEW.actor) GLOB 'system:*' THEN 'system' ELSE 'human' END AS kind)
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor);
    SELECT RAISE(ABORT, 'inactive actor') WHERE EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor AND active = 0);
    SELECT RAISE(ABORT, 'this action requires a human actor')
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.actor AND kind = 'human');
END;

-- Append-only records and no deletes ----------------------------------------------------------------

CREATE TRIGGER messages_no_update BEFORE UPDATE ON messages
BEGIN SELECT RAISE(ABORT, 'messages is append-only'); END;
CREATE TRIGGER request_triage_no_update BEFORE UPDATE ON request_triage
BEGIN SELECT RAISE(ABORT, 'request_triage is append-only'); END;
CREATE TRIGGER priority_inputs_no_update BEFORE UPDATE ON priority_inputs
BEGIN SELECT RAISE(ABORT, 'priority_inputs is append-only'); END;
CREATE TRIGGER market_resolutions_no_update BEFORE UPDATE ON market_resolutions
BEGIN SELECT RAISE(ABORT, 'market_resolutions is append-only'); END;
CREATE TRIGGER request_decisions_no_update BEFORE UPDATE ON request_decisions
BEGIN SELECT RAISE(ABORT, 'request_decisions is append-only'); END;
CREATE TRIGGER scope_rubrics_no_update BEFORE UPDATE ON scope_rubrics
BEGIN SELECT RAISE(ABORT, 'scope_rubrics is append-only'); END;
CREATE TRIGGER sentiment_scores_no_update BEFORE UPDATE ON sentiment_scores
BEGIN SELECT RAISE(ABORT, 'sentiment_scores is append-only'); END;
CREATE TRIGGER llm_cache_no_update BEFORE UPDATE ON llm_cache
BEGIN SELECT RAISE(ABORT, 'llm_cache is append-only'); END;

CREATE TRIGGER agents_no_delete BEFORE DELETE ON agents
BEGIN SELECT RAISE(ABORT, 'agents is never deleted; retire instead'); END;
CREATE TRIGGER tasks_no_delete BEFORE DELETE ON tasks
BEGIN SELECT RAISE(ABORT, 'tasks is never deleted; cancel instead'); END;
CREATE TRIGGER runs_no_delete BEFORE DELETE ON runs
BEGIN SELECT RAISE(ABORT, 'runs is never deleted'); END;
CREATE TRIGGER threads_no_delete BEFORE DELETE ON threads
BEGIN SELECT RAISE(ABORT, 'threads is never deleted; close instead'); END;
CREATE TRIGGER messages_no_delete BEFORE DELETE ON messages
BEGIN SELECT RAISE(ABORT, 'messages is append-only'); END;
CREATE TRIGGER llm_cache_no_delete BEFORE DELETE ON llm_cache
BEGIN SELECT RAISE(ABORT, 'llm_cache is append-only'); END;
CREATE TRIGGER watchlists_no_delete BEFORE DELETE ON watchlists
BEGIN SELECT RAISE(ABORT, 'watchlists is never deleted; pause instead'); END;
CREATE TRIGGER signal_items_no_delete BEFORE DELETE ON signal_items
BEGIN SELECT RAISE(ABORT, 'signal_items is never deleted; dismiss instead'); END;
CREATE TRIGGER sentiment_scores_no_delete BEFORE DELETE ON sentiment_scores
BEGIN SELECT RAISE(ABORT, 'sentiment_scores is append-only'); END;
CREATE TRIGGER market_weights_no_delete BEFORE DELETE ON market_weights
BEGIN SELECT RAISE(ABORT, 'market_weights is never deleted'); END;
CREATE TRIGGER market_conflicts_no_delete BEFORE DELETE ON market_conflicts
BEGIN SELECT RAISE(ABORT, 'market_conflicts is never deleted; supersede or dismiss instead'); END;
CREATE TRIGGER market_resolutions_no_delete BEFORE DELETE ON market_resolutions
BEGIN SELECT RAISE(ABORT, 'market_resolutions is append-only'); END;
CREATE TRIGGER request_clusters_no_delete BEFORE DELETE ON request_clusters
BEGIN SELECT RAISE(ABORT, 'request_clusters is never deleted'); END;
CREATE TRIGGER intake_requests_no_delete BEFORE DELETE ON intake_requests
BEGIN SELECT RAISE(ABORT, 'intake_requests is never deleted; decline instead'); END;
CREATE TRIGGER request_links_no_delete BEFORE DELETE ON request_links
BEGIN SELECT RAISE(ABORT, 'request_links is never deleted; mark it removed'); END;
CREATE TRIGGER request_triage_no_delete BEFORE DELETE ON request_triage
BEGIN SELECT RAISE(ABORT, 'request_triage is append-only'); END;
CREATE TRIGGER request_decisions_no_delete BEFORE DELETE ON request_decisions
BEGIN SELECT RAISE(ABORT, 'request_decisions is append-only'); END;
CREATE TRIGGER priority_inputs_no_delete BEFORE DELETE ON priority_inputs
BEGIN SELECT RAISE(ABORT, 'priority_inputs is append-only'); END;
CREATE TRIGGER priority_sensitivity_no_delete BEFORE DELETE ON priority_sensitivity
BEGIN SELECT RAISE(ABORT, 'priority_sensitivity is never deleted'); END;
CREATE TRIGGER scope_rubrics_no_delete BEFORE DELETE ON scope_rubrics
BEGIN SELECT RAISE(ABORT, 'scope_rubrics is append-only'); END;
CREATE TRIGGER preserve_attributes_no_delete BEFORE DELETE ON preserve_attributes
BEGIN SELECT RAISE(ABORT, 'preserve_attributes is never deleted'); END;
CREATE TRIGGER coverage_reports_no_delete BEFORE DELETE ON coverage_reports
BEGIN SELECT RAISE(ABORT, 'coverage_reports is never deleted'); END;
