-- Pod F: agent runtime substrate (PLATFORM_BUILD_PLAN.md section 8, notes/agent-runtime.md).
-- Adds per-agent model configuration, task execution bookkeeping and the human gates that
-- server/agent_runtime.py also enforces, then seeds the agent registry from the roster in
-- notes/pm-role-research/05-agentic-layer-design.md. No rows are deleted or rewritten.

-- Agents --------------------------------------------------------------------------------------------

-- model NULL means "use OPENAI_MODEL at run time"; never hard-code a model name here. Deterministic
-- system: agents never have a model. Changing a model is a human configuration change (model_changed_by).
ALTER TABLE agents ADD COLUMN model TEXT CHECK(model IS NULL OR length(trim(model)) BETWEEN 1 AND 100);
ALTER TABLE agents ADD COLUMN model_changed_by TEXT;

CREATE TRIGGER agents_model_human BEFORE UPDATE OF model ON agents
WHEN NEW.model IS NOT OLD.model
BEGIN
    INSERT INTO actors (id, kind, display_name, role, origin)
    SELECT NEW.model_changed_by, kind, NEW.model_changed_by, CASE kind WHEN 'human' THEN 'pm' ELSE kind END, 'discovered'
    FROM (SELECT CASE WHEN lower(NEW.model_changed_by) GLOB 'ai:*' THEN 'ai'
                      WHEN lower(NEW.model_changed_by) GLOB 'system:*' THEN 'system' ELSE 'human' END AS kind)
    WHERE NEW.model_changed_by IS NOT NULL AND NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.model_changed_by);
    SELECT RAISE(ABORT, 'inactive actor')
    WHERE EXISTS (SELECT 1 FROM actors WHERE id = NEW.model_changed_by AND active = 0);
    SELECT RAISE(ABORT, 'this action requires a human actor')
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.model_changed_by AND kind = 'human');
    SELECT RAISE(ABORT, 'deterministic agents have no model') WHERE NEW.id GLOB 'system:*' AND NEW.model IS NOT NULL;
END;

CREATE TRIGGER agents_model_deterministic BEFORE INSERT ON agents
WHEN NEW.id GLOB 'system:*' AND NEW.model IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'deterministic agents have no model'); END;

-- Registration is idempotent: inserting an id that is already registered is a no-op, so a reviewed
-- registry row (status, model, human status history) is never overwritten by a re-seed. Change agents
-- through the runtime API (human gates) or an UPDATE in a later migration.
CREATE TRIGGER agents_register_once BEFORE INSERT ON agents
WHEN EXISTS (SELECT 1 FROM agents WHERE id = NEW.id)
BEGIN SELECT RAISE(IGNORE); END;

-- Tasks ---------------------------------------------------------------------------------------------

ALTER TABLE tasks ADD COLUMN error TEXT;          -- last execution error; cleared when an execution succeeds
ALTER TABLE tasks ADD COLUMN started_at TEXT;     -- last claim for execution (fences stale workers)
ALTER TABLE tasks ADD COLUMN finished_at TEXT;    -- last recorded execution outcome
ALTER TABLE tasks ADD COLUMN updated_by TEXT;     -- actor of the last change; a human for cancel and accept
CREATE INDEX tasks_parent ON tasks(parent_task_id);
CREATE INDEX tasks_agent ON tasks(assigned_agent_id, status);

-- Cancelling a task and accepting a proposal that waited at a human gate are human decisions.
CREATE TRIGGER tasks_human_gates BEFORE UPDATE OF status ON tasks
WHEN NEW.status IS NOT OLD.status
  AND (NEW.status = 'cancelled' OR (OLD.status = 'awaiting_human' AND NEW.status = 'succeeded'))
BEGIN
    INSERT INTO actors (id, kind, display_name, role, origin)
    SELECT NEW.updated_by, kind, NEW.updated_by, CASE kind WHEN 'human' THEN 'pm' ELSE kind END, 'discovered'
    FROM (SELECT CASE WHEN lower(NEW.updated_by) GLOB 'ai:*' THEN 'ai'
                      WHEN lower(NEW.updated_by) GLOB 'system:*' THEN 'system' ELSE 'human' END AS kind)
    WHERE NEW.updated_by IS NOT NULL AND NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.updated_by);
    SELECT RAISE(ABORT, 'inactive actor') WHERE EXISTS (SELECT 1 FROM actors WHERE id = NEW.updated_by AND active = 0);
    SELECT RAISE(ABORT, 'this action requires a human actor')
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.updated_by AND kind = 'human');
END;

CREATE TRIGGER tasks_terminal BEFORE UPDATE OF status ON tasks
WHEN NEW.status IS NOT OLD.status AND OLD.status IN ('succeeded', 'cancelled')
BEGIN SELECT RAISE(ABORT, 'succeeded and cancelled tasks are final'); END;

-- Agent registry seed -------------------------------------------------------------------------------
-- Autonomy level = the strongest human gate the agent's outputs pass through (A0 autonomous, A1 proposes,
-- A2 needs a human accept, A3 drafts only). Capability names are the registered operations each agent may
-- run; pods A-E register theirs at import, Pod F registers pipeline.*. Inserting an agent registers its
-- actor (0009 trigger agents_register_actor: kind and role 'ai', or 'system' for the deterministic scorer).

INSERT INTO agents (id, slug, display_name, department, description, autonomy_level, capabilities, parent_agent_id,
                    created_at, updated_at)
VALUES ('ai:agent:orchestrator', 'orchestrator', 'Orchestrator (PM chief of staff)', 'orchestration',
        'Plans the work for a vehicle and market scope, sequences the other agents through tasks and compiles the '
        || 'morning brief. Delegates instead of running capabilities itself and stops at every human gate.',
        'A0', '[]', NULL, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

INSERT INTO agents (id, slug, display_name, department, description, autonomy_level, capabilities, parent_agent_id,
                    created_at, updated_at)
VALUES
    ('ai:agent:feedback-analyst', 'feedback-analyst', 'Feedback analyst', 'customer_insights',
     'Reads and structures BMW verbatims and studies into source-linked findings (likes, defects, wants, '
     || 'difficulties), scores their sentiment and keeps the list of attributes customers love.',
     'A1', '["pipeline.analyze","signals.score_sentiment","market_data.import_bmw","market_data.derive_preserve"]',
     'ai:agent:orchestrator', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('ai:agent:trend-scout', 'trend-scout', 'Trend scout', 'market_intelligence',
     'Monitors PM-authorised public web watchlists for trends and summarises what changed. Public results stay '
     || 'unreviewed signals until a PM imports them.',
     'A1', '["signals.refresh_watchlist","signals.backfill_watchlist","signals.summarise"]',
     'ai:agent:orchestrator', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('ai:agent:competitor-analyst', 'competitor-analyst', 'Competitor analyst', 'market_intelligence',
     'Scans competitor watchlists on the public web only, from templated queries (model, topic, market and '
     || 'competitor names); never sends BMW records to search.',
     'A1', '["signals.refresh_watchlist","signals.backfill_watchlist"]',
     'ai:agent:orchestrator', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('ai:agent:market-balancer', 'market-balancer', 'Market balancer', 'market_intelligence',
     'Compares topics across markets, derives sales-based market weights and proposes conflicts with a '
     || 'recommendation; a PM resolves every conflict.',
     'A1', '["markets.compare","markets.detect_conflicts","market_data.derive_weights"]',
     'ai:agent:orchestrator', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('ai:agent:request-triage', 'request-triage', 'Request triage', 'communications',
     'Structures inbound market, dealer, sales and engineering requests: clusters them, proposes evidence for '
     || 'and against and ranks them with the triage rubric. A PM converts, links, declines or defers.',
     'A1', '["requests.cluster","requests.link_evidence","requests.triage"]',
     'ai:agent:orchestrator', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('ai:agent:requirement-writer', 'requirement-writer', 'Requirement writer', 'requirements',
     'Drafts SMART requirement proposals from analysed findings, separating need, response and acceptance '
     || 'test and labelling targets as PM assumptions. Proposals wait for a PM decision.',
     'A1', '["pipeline.generate_requirements"]',
     'ai:agent:orchestrator', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('system:agent:scorer', 'scorer', 'Scorer', 'requirements',
     'Deterministic, versioned scoring and ranking code, not an LLM: derives factor inputs, ranks requirements '
     || 'and measures rank sensitivity. Agents only explain its scores.',
     'A0', '["priorities.derive_inputs","priorities.rank","priorities.sensitivity"]',
     'ai:agent:orchestrator', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('ai:agent:challenger', 'challenger', 'Challenger', 'governance',
     'Checks grounding and argues against a draft: missing evidence, contradicting markets, unrealistic targets '
     || 'and scope drift into pricing or engineering. A PM resolves each challenge.',
     'A2', '[]',
     'ai:agent:orchestrator', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('ai:agent:change-watcher', 'change-watcher', 'Change watcher', 'governance',
     'Reassesses all evidence in scope against the approved baseline and opens review items for decisions it '
     || 'touches; a PM accepts every revision.',
     'A2', '["pipeline.assess_updates"]',
     'ai:agent:orchestrator', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('ai:agent:comms-drafter', 'comms-drafter', 'Comms drafter', 'communications',
     'Drafts gate packs, market responses, engineering handoffs and minutes from recorded decisions only. '
     || 'Drafts stay internal; nothing is ever sent.',
     'A3', '[]',
     'ai:agent:orchestrator', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('ai:agent:research-planner', 'research-planner', 'Research planner', 'customer_insights',
     'Measures evidence coverage and representativeness and turns gaps (low grade, conflicts, missing markets) '
     || 'into research or clinic briefs.',
     'A1', '["market_data.coverage"]',
     'ai:agent:orchestrator', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
