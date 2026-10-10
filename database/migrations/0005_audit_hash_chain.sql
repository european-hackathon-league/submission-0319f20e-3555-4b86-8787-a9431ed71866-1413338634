-- Tamper-evident audit trail. store.audit() links every event to the previous one with SHA-256. If the
-- database already holds events, the migration hook writes a genesis event sealing them under one digest.

ALTER TABLE audit_events ADD COLUMN prev_hash TEXT;
ALTER TABLE audit_events ADD COLUMN event_hash TEXT;

-- Access events (access.*, *.viewed, *.downloaded) and timelines filter by action and time.
CREATE INDEX IF NOT EXISTS idx_audit_action_time ON audit_events(action, created_at);

-- SQLite cannot compute SHA-256, so the database enforces the linkage and verify recomputes the hashes.
-- The first event of an empty trail links to the empty pre-chain digest (store.pre_chain_digest([])).
-- After unhashed (pre-chain) history only the genesis event may follow; every other event extends the head.
-- Rows that collide with an existing event are left to the append-only and uniqueness guards.
CREATE TRIGGER audit_events_chain BEFORE INSERT ON audit_events
WHEN NOT EXISTS (SELECT 1 FROM audit_events WHERE id = NEW.id OR sequence = NEW.sequence) AND (
    NEW.event_hash IS NULL OR length(NEW.event_hash) <> 64 OR NEW.prev_hash IS NULL OR (
    CASE WHEN NOT EXISTS (SELECT 1 FROM audit_events)
         THEN NEW.prev_hash <> 'cd49f14745c74ecd14fd9d101b8a9abb265cb345c1f18c9ef4d79f761d6aa4a7'
         WHEN (SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1) IS NULL
         THEN NEW.action <> 'audit.chain.started'
         ELSE NEW.prev_hash IS NOT (SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1)
    END))
BEGIN SELECT RAISE(ABORT, 'audit hash chain broken: write audit events through store.audit()'); END;
