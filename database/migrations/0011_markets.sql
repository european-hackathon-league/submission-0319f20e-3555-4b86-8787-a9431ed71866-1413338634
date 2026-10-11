-- Pod B market balancer (server/markets.py, notes/market-balancer.md): guards beyond 0009.
-- The tables, the human-actor gate on market_resolutions, the one-open-conflict-per-fingerprint index
-- and the conflict status workflow are in 0009; this file only adds to them.

-- Conflict history (every detection of the same fingerprint, oldest first) is read on every detail view.
CREATE INDEX market_conflicts_fingerprint ON market_conflicts(fingerprint, created_at);

-- A human resolution decides an open conflict. Resolving a superseded, resolved or dismissed conflict
-- would record a decision on stale inputs, so the database refuses it independently of the API.
CREATE TRIGGER market_resolutions_open_conflict BEFORE INSERT ON market_resolutions
WHEN NOT EXISTS (SELECT 1 FROM market_conflicts WHERE id = NEW.conflict_id AND status = 'open')
BEGIN SELECT RAISE(ABORT, 'market resolutions require an open conflict'); END;

-- Resolutions list the requirements they created or linked, for source-to-decision traceability.
CREATE TRIGGER market_resolutions_requirement_array BEFORE INSERT ON market_resolutions
WHEN json_type(NEW.requirement_ids) IS NOT 'array'
BEGIN SELECT RAISE(ABORT, 'market resolution requirement_ids must be a JSON array'); END;

-- Linking an invented or unrelated requirement must not bypass API traceability validation.
CREATE TRIGGER market_resolutions_requirement_scope BEFORE INSERT ON market_resolutions
WHEN json_type(NEW.requirement_ids) = 'array' AND EXISTS (
    SELECT 1 FROM json_each(NEW.requirement_ids) link
    WHERE link.type != 'text' OR NOT EXISTS (
        SELECT 1 FROM requirements r JOIN market_conflicts c ON c.id = NEW.conflict_id
        WHERE r.id = link.value AND r.vehicle = c.vehicle
          AND r.market IN (SELECT value FROM json_each(c.markets))
          AND (r.topic = c.topic OR r.topic = c.related_topic)
    )
)
BEGIN SELECT RAISE(ABORT, 'resolution requirements must belong to the conflict scope'); END;
