CREATE TABLE IF NOT EXISTS imports (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id),
    filename TEXT NOT NULL,
    record_count INTEGER NOT NULL CHECK(record_count >= 0),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id),
    vehicle TEXT NOT NULL,
    market TEXT NOT NULL,
    content TEXT NOT NULL CHECK(length(content) > 0),
    location TEXT NOT NULL CHECK(json_valid(location)),
    metadata TEXT NOT NULL CHECK(json_valid(metadata)),
    observed_at TEXT,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(source_id, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_evidence_scope ON evidence(vehicle, market);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id TEXT PRIMARY KEY,
    vehicle TEXT NOT NULL,
    market TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    evidence_ids TEXT NOT NULL CHECK(json_valid(evidence_ids)),
    warnings TEXT NOT NULL CHECK(json_valid(warnings)),
    result TEXT NOT NULL CHECK(json_valid(result)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES analysis_runs(id),
    vehicle TEXT NOT NULL,
    market TEXT NOT NULL,
    topic TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('problem', 'strength', 'need', 'context')),
    summary TEXT NOT NULL,
    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_findings_scope ON findings(vehicle, market);
CREATE TABLE IF NOT EXISTS finding_evidence (
    finding_id TEXT NOT NULL REFERENCES findings(id),
    evidence_id TEXT NOT NULL REFERENCES evidence(id),
    relation TEXT NOT NULL CHECK(relation IN ('supports', 'conflicts')),
    PRIMARY KEY(finding_id, evidence_id, relation)
);

CREATE TABLE IF NOT EXISTS requirements (
    id TEXT PRIMARY KEY,
    vehicle TEXT NOT NULL,
    market TEXT NOT NULL,
    topic TEXT NOT NULL,
    current_version_id TEXT REFERENCES requirement_versions(id) DEFERRABLE INITIALLY DEFERRED,
    approved_version_id TEXT REFERENCES requirement_versions(id) DEFERRABLE INITIALLY DEFERRED,
    approved_score_id TEXT REFERENCES scores(id) DEFERRABLE INITIALLY DEFERRED,
    status TEXT NOT NULL CHECK(status IN ('proposed', 'approved', 'rejected', 'postponed', 'needs_review')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(vehicle, market, topic)
);
CREATE TABLE IF NOT EXISTS requirement_versions (
    id TEXT PRIMARY KEY,
    requirement_id TEXT NOT NULL REFERENCES requirements(id),
    version INTEGER NOT NULL CHECK(version > 0),
    title TEXT NOT NULL,
    statement TEXT NOT NULL,
    customer_need TEXT NOT NULL,
    acceptance_criteria TEXT NOT NULL CHECK(json_valid(acceptance_criteria)),
    assumptions TEXT NOT NULL CHECK(json_valid(assumptions)),
    factors TEXT NOT NULL CHECK(json_valid(factors)),
    actor TEXT NOT NULL,
    rationale TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(requirement_id, version)
);
CREATE TABLE IF NOT EXISTS requirement_findings (
    version_id TEXT NOT NULL REFERENCES requirement_versions(id),
    finding_id TEXT NOT NULL REFERENCES findings(id),
    PRIMARY KEY(version_id, finding_id)
);
CREATE TABLE IF NOT EXISTS scores (
    id TEXT PRIMARY KEY,
    version_id TEXT NOT NULL REFERENCES requirement_versions(id),
    rubric_version TEXT NOT NULL,
    factors TEXT NOT NULL CHECK(json_valid(factors)),
    weights TEXT NOT NULL CHECK(json_valid(weights)),
    total REAL NOT NULL,
    evidence_grade TEXT NOT NULL,
    explanation TEXT NOT NULL CHECK(json_valid(explanation)),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scores_version ON scores(version_id, created_at);
CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    requirement_id TEXT NOT NULL REFERENCES requirements(id),
    version_id TEXT NOT NULL REFERENCES requirement_versions(id),
    score_id TEXT NOT NULL REFERENCES scores(id),
    action TEXT NOT NULL CHECK(action IN ('approve', 'reject', 'postpone', 'challenge')),
    actor TEXT NOT NULL,
    rationale TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_items (
    id TEXT PRIMARY KEY,
    requirement_id TEXT NOT NULL REFERENCES requirements(id),
    approved_version_id TEXT REFERENCES requirement_versions(id),
    proposed_version_id TEXT NOT NULL REFERENCES requirement_versions(id),
    reason TEXT NOT NULL,
    changes TEXT NOT NULL CHECK(json_valid(changes)),
    suggested_action TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('open', 'resolved', 'superseded')),
    created_at TEXT NOT NULL,
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_reviews_status ON review_items(status, requirement_id);
CREATE TABLE IF NOT EXISTS audit_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    rationale TEXT NOT NULL,
    before_state TEXT CHECK(before_state IS NULL OR json_valid(before_state)),
    after_state TEXT CHECK(after_state IS NULL OR json_valid(after_state)),
    metadata TEXT NOT NULL CHECK(json_valid(metadata)),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_events(entity_type, entity_id, sequence);
