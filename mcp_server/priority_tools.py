"""Pod D prioritization v2 tools. The rubric switch (POST /priorities/rubric) is a human gate and is not exposed here.

Tools call the API through the injected api_request(method, path, *, params=None, payload=None) and
use identifier(value) to encode path segments. Registered by mcp_server/main.py.
"""

from typing import Literal

Factor = Literal["market_demand", "sentiment_momentum", "request_pressure"]


def _present(**values):
    return {key: value for key, value in values.items() if value is not None}


def register_priority_tools(mcp, api_request, identifier):
    @mcp.tool()
    async def get_priority_rubrics(vehicle: str | None = None, market: str | None = None) -> dict:
        """List customer-priority-v1/v2 definitions, derived-factor formulas, default weights and the scope rubric history.

        Switching a scope's rubric is a human PM decision made in the API or web workspace, never through MCP.
        """
        return await api_request("GET", "/priorities/rubrics", params=_present(vehicle=vehicle, market=market))

    @mcp.tool()
    async def derive_priority_inputs(vehicle: str = "G60", market: str = "US", requirement_ids: list[str] | None = None,
                                     as_of: str | None = None, rescore: bool = True, actor: str = "ai:mcp") -> dict:
        """Derive market demand, sentiment momentum and request pressure (0–5) with recorded derivations and source ids.

        Missing data gives a neutral 2.5 with a not-measured flag. In a v2 scope, changed values rescore the requirement
        and open a review for approved requirements whose score changes; nothing is approved automatically.
        """
        return await api_request("POST", "/priorities/inputs/derive", payload=_present(
            vehicle=vehicle, market=market, requirement_ids=requirement_ids, as_of=as_of, rescore=rescore, actor=actor))

    @mcp.tool()
    async def list_priority_inputs(vehicle: str | None = None, market: str | None = None,
                                   requirement_id: str | None = None, version_id: str | None = None,
                                   factor: Factor | None = None, latest_only: bool = False,
                                   limit: int = 100, offset: int = 0) -> dict:
        """Read recorded derived factor values with their formula, inputs, flags, source ids and run ids."""
        return await api_request("GET", "/priorities/inputs", params=_present(
            vehicle=vehicle, market=market, requirement_id=requirement_id, version_id=version_id, factor=factor,
            latest_only=latest_only, limit=limit, offset=offset))

    @mcp.tool()
    async def get_priority_ranking(vehicle: str = "G60", market: str = "US", limit: int = 100, offset: int = 0) -> dict:
        """Read a scope's ranking: score, factor contributions, derivations, evidence grade, preserve warnings, stability."""
        return await api_request("GET", "/priorities/ranking", params={
            "vehicle": vehicle, "market": market, "limit": limit, "offset": offset})

    @mcp.tool()
    async def run_priority_sensitivity(vehicle: str = "G60", market: str = "US", each_weight: float = 0.2,
                                       actor: str = "ai:mcp") -> dict:
        """Record a deterministic rank-sensitivity analysis: each weight ±20 % and a 3-level grid over the top two weights."""
        return await api_request("POST", "/priorities/sensitivity", payload={
            "vehicle": vehicle, "market": market, "each_weight": each_weight, "actor": actor})

    @mcp.tool()
    async def list_priority_sensitivity(vehicle: str | None = None, market: str | None = None,
                                        limit: int = 20, offset: int = 0) -> dict:
        """List recorded sensitivity analyses (newest first) with scenarios and per-requirement rank ranges."""
        return await api_request("GET", "/priorities/sensitivity", params=_present(
            vehicle=vehicle, market=market, limit=limit, offset=offset))

    @mcp.tool()
    async def get_priority_portfolio(vehicle: str = "G60") -> dict:
        """Read the topic × market matrix of v2 scores with the sales-weighted demand index and open market conflicts."""
        return await api_request("GET", "/priorities/portfolio", params={"vehicle": vehicle})

    @mcp.tool()
    async def explain_priority_ranking(vehicle: str = "G60", market: str = "US", requirement_ids: list[str] | None = None,
                                       limit: int = 10, provider: Literal["openai", "deterministic"] = "openai",
                                       actor: str = "ai:mcp") -> dict:
        """Explain a ranking in plain language from recorded scores and derivations, citing their ids.

        OpenAI receives only recorded scores, factor summaries and requirement titles through the configured provider;
        it never sets or changes a factor value. deterministic is the labelled template baseline.
        """
        return await api_request("POST", "/priorities/explain", payload=_present(
            vehicle=vehicle, market=market, requirement_ids=requirement_ids, limit=limit, provider=provider, actor=actor))
