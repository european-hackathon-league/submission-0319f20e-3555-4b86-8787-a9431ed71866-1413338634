"""Thin MCP access to durable PM workflows, sharing the API's gates and traceability."""

from typing import Literal


def register_workflow_tools(mcp, request, identifier):
    @mcp.tool()
    async def list_actors() -> list[dict]:
        """Discover declared actors and roles; actor labels are not authenticated identities."""
        return await request("GET", "/actors")

    @mcp.tool()
    async def create_pm_workflow(
        request_key: str, actor: str, vehicle: str = "G60", market: str = "US",
        kind: Literal["initial", "update"] = "initial",
        provider: Literal["deterministic", "openai"] = "deterministic",
    ) -> dict:
        """Create a resumable BMW planning run. Reuse the request key only for the identical command.

        OpenAI runs use live AI; deterministic runs are explicit reference demonstrations.
        Agents analyze and propose. A human must decide each exact requirement and score.
        """
        return await request("POST", "/workflows", payload={
            "request_key": request_key, "actor": actor, "vehicle": vehicle, "market": market,
            "kind": kind, "provider": provider,
        })

    @mcp.tool()
    async def list_pm_workflows(vehicle: str = "G60", market: str = "US") -> list[dict]:
        """List persisted planning runs for a vehicle and market, including failures and review gates."""
        return await request("GET", "/workflows", params={"vehicle": vehicle, "market": market})

    @mcp.tool()
    async def get_pm_workflow(workflow_id: str) -> dict:
        """Read current revision, checkpoints, errors and outputs before resuming or completing."""
        return await request("GET", f"/workflows/{identifier(workflow_id)}")

    @mcp.tool()
    async def run_pm_workflow(workflow_id: str, expected_revision: int, actor: str) -> dict:
        """Run/resume bounded autonomous stages and stop at human review; never approve requirements.

        On timeout read the workflow before retrying; another worker may still hold its lease.
        """
        return await request("POST", f"/workflows/{identifier(workflow_id)}/run", payload={
            "expected_revision": expected_revision, "actor": actor,
        })

    @mcp.tool()
    async def complete_pm_workflow(workflow_id: str, expected_revision: int, actor: str, rationale: str) -> dict:
        """Record planning completion only after human PM decisions and current evidence checks pass.

        Requires an active human PM and explicit rationale. This is not an engineering release approval.
        """
        return await request("POST", f"/workflows/{identifier(workflow_id)}/complete", payload={
            "expected_revision": expected_revision, "actor": actor, "rationale": rationale,
        })

    @mcp.tool()
    async def get_pm_workflow_brief(workflow_id: str) -> dict:
        """Get priority rationale, exact evidence locations, assumptions, conflicts and PM next actions.

        Completed runs use frozen versions, scores and decision IDs; later changes cannot rewrite the brief.
        """
        return await request("GET", f"/workflows/{identifier(workflow_id)}/brief")
