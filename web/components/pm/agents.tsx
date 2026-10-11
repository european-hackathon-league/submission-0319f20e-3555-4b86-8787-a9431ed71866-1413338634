"use client";
import { useQuery } from "@tanstack/react-query";
import { Bot, Cpu, ShieldCheck, UserCheck } from "lucide-react";
import { api, date, readable } from "@/lib/api";
import { useWorkspace } from "./context";
import { RunsFeed } from "./runs-feed";
import { Empty, ErrorMessage, Loading, Panel, Status } from "./shared";

type Agent = {
  id: string;
  slug: string;
  display_name: string;
  department: string;
  description: string;
  autonomy_level: string;
  capabilities: string[];
  status: string;
  parent_agent_id: string | null;
  kind: string;
  provider?: string | null;
  effective_model?: string | null;
};
type Task = {
  id: string;
  capability: string;
  title: string;
  status: string;
  assigned_agent_id: string | null;
  requested_by: string;
  recurrence_days: number | null;
  due_at: string | null;
  updated_at: string;
  error: string | null;
};
type Page<T> = { items: T[]; total?: number };

/** Mirrors AUTONOMY_NOTES in server/agent_runtime.py. */
const AUTONOMY: Record<string, string> = {
  A0: "Runs autonomously",
  A1: "Proposes; a PM reviews the result",
  A2: "Its proposals need a human accept",
  A3: "Drafts only; a human acts",
};

function AgentCard({ agent }: { agent: Agent }) {
  return (
    <article className="agent-card">
      <header>
        <span className="agent-icon">{agent.kind === "system" ? <Cpu size={16} /> : <Bot size={16} />}</span>
        <div>
          <h3>{agent.display_name}</h3>
          <span className="muted">{readable(agent.department)}</span>
        </div>
        <span className={`agent-autonomy autonomy-${agent.autonomy_level}`} title={AUTONOMY[agent.autonomy_level]}>
          {agent.autonomy_level}
        </span>
      </header>
      <p>{agent.description}</p>
      <div className="agent-meta">
        <span className="mono">
          {agent.kind === "system" ? "Deterministic code" : [agent.provider, agent.effective_model].filter(Boolean).join(" · ") || "No model"}
        </span>
        <Status value={agent.status} />
      </div>
      {agent.capabilities.length > 0 ? (
        <ul className="agent-capabilities">
          {agent.capabilities.map((capability) => (
            <li key={capability} className="mono">
              {capability}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted agent-nocap">Delegates and reviews; calls no capability itself.</p>
      )}
    </article>
  );
}

/** Agent registry (GET /agents), task queue (GET /tasks) and recorded capability runs (GET /runs). */
export function AgentsPage() {
  const { scope } = useWorkspace();
  const agents = useQuery({ queryKey: ["agents"], queryFn: ({ signal }) => api<Page<Agent>>("/agents?limit=200", { signal }) });
  const tasks = useQuery({
    queryKey: ["tasks", scope.vehicle, scope.market],
    queryFn: ({ signal }) =>
      api<Page<Task>>(`/tasks?vehicle=${encodeURIComponent(scope.vehicle)}&market=${encodeURIComponent(scope.market)}&limit=200`, { signal }),
  });

  const all = agents.data?.items ?? [];
  const orchestrator = all.find((a) => !a.parent_agent_id);
  const workers = all.filter((a) => a.parent_agent_id);
  const names = new Map(all.map((a) => [a.id, a.display_name]));

  return (
    <div className="multi-agent-page">
      <h1>Multi-agentic system</h1>
      <p className="agent-lede">
        An orchestrator plans the work for {scope.vehicle} / {scope.market} and hands bounded tasks to specialist agents. Each agent may
        call only its registered capabilities, every call is recorded as a run, scoring is deterministic code, and every requirement
        decision stops at a human PM.
      </p>

      <div className="agent-gates">
        <div>
          <ShieldCheck size={16} />
          <span>Capability permissions are enforced by the API, not by prompts.</span>
        </div>
        <div>
          <UserCheck size={16} />
          <span>The database rejects approvals from AI or system actors.</span>
        </div>
      </div>

      <div className="agent-legend">
        {Object.entries(AUTONOMY).map(([level, note]) => (
          <span key={level}>
            <span className={`agent-autonomy autonomy-${level}`}>{level}</span> {note}
          </span>
        ))}
      </div>

      {agents.error ? (
        <ErrorMessage error={agents.error} retry={() => void agents.refetch()} />
      ) : agents.isPending ? (
        <Loading label="Loading the agent registry…" />
      ) : (
        <>
          {orchestrator && (
            <section className="agent-tier">
              <h2>Orchestrator</h2>
              <div className="agent-grid agent-grid-single">
                <AgentCard agent={orchestrator} />
              </div>
            </section>
          )}
          <section className="agent-tier">
            <h2>Specialist agents ({workers.length})</h2>
            <div className="agent-grid">
              {workers.map((agent) => (
                <AgentCard key={agent.id} agent={agent} />
              ))}
            </div>
          </section>
        </>
      )}

      <Panel title="Task queue" description={`Bounded tasks the orchestrator or a PM created for ${scope.vehicle} / ${scope.market}, with their status and assigned agent.`}>
        {tasks.error ? (
          <ErrorMessage error={tasks.error} retry={() => void tasks.refetch()} />
        ) : tasks.isPending ? (
          <Loading />
        ) : !tasks.data.items.length ? (
          <Empty title="No tasks in this scope" description="Tasks appear here when the orchestrator or a PM schedules work." />
        ) : (
          <table className="agent-tasks">
            <thead>
              <tr>
                <th>Task</th>
                <th>Capability</th>
                <th>Agent</th>
                <th>Requested by</th>
                <th>Status</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {tasks.data.items.map((task) => (
                <tr key={task.id}>
                  <td>
                    {task.title}
                    {task.recurrence_days ? <span className="muted"> · every {task.recurrence_days} days</span> : null}
                    {task.error && <div className="agent-task-error">{task.error}</div>}
                  </td>
                  <td className="mono">{task.capability}</td>
                  <td>{task.assigned_agent_id ? names.get(task.assigned_agent_id) ?? task.assigned_agent_id : <span className="muted">Unassigned</span>}</td>
                  <td>{task.requested_by}</td>
                  <td>
                    <Status value={task.status} />
                  </td>
                  <td>{date(task.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <RunsFeed />
    </div>
  );
}
