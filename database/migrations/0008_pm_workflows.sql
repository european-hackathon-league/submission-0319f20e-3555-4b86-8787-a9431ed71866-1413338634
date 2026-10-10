-- Durable orchestration of BMW's PM process. Domain records remain append-only;
-- this projection is checkpointed and every transition is recorded in audit_events.
CREATE TABLE pm_workflows (
    id TEXT PRIMARY KEY,
    vehicle TEXT NOT NULL,
    market TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('initial', 'update')),
    provider TEXT NOT NULL CHECK(provider IN ('deterministic', 'openai')),
    actor TEXT NOT NULL,
    request_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'failed', 'awaiting_review', 'completed')),
    revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
    stages TEXT NOT NULL,
    evidence_ids TEXT NOT NULL DEFAULT '[]',
    analysis_id TEXT REFERENCES analysis_runs(id),
    requirement_snapshots TEXT NOT NULL DEFAULT '[]',
    error TEXT,
    lease_token TEXT,
    lease_expires_at REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK((status = 'running') = (lease_token IS NOT NULL)),
    CHECK((lease_token IS NULL) = (lease_expires_at IS NULL))
);

CREATE UNIQUE INDEX pm_workflows_one_running_scope ON pm_workflows(vehicle, market)
WHERE status = 'running';
CREATE INDEX pm_workflows_scope ON pm_workflows(vehicle, market, created_at);

CREATE TRIGGER pm_workflows_identity_fixed
BEFORE UPDATE OF id, vehicle, market, kind, provider, actor, request_key, created_at ON pm_workflows
WHEN NEW.id IS NOT OLD.id OR NEW.vehicle IS NOT OLD.vehicle OR NEW.market IS NOT OLD.market
 OR NEW.kind IS NOT OLD.kind OR NEW.provider IS NOT OLD.provider OR NEW.actor IS NOT OLD.actor
 OR NEW.request_key IS NOT OLD.request_key OR NEW.created_at IS NOT OLD.created_at
BEGIN SELECT RAISE(ABORT, 'workflow identity is fixed'); END;

CREATE TRIGGER pm_workflows_completed_immutable BEFORE UPDATE ON pm_workflows
WHEN OLD.status = 'completed'
BEGIN SELECT RAISE(ABORT, 'completed workflows are immutable'); END;

CREATE TRIGGER pm_workflows_no_delete BEFORE DELETE ON pm_workflows
BEGIN SELECT RAISE(ABORT, 'workflows are never deleted'); END;
