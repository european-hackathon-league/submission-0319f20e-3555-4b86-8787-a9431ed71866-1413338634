"""Market comparison and proposals through the API. Resolutions remain human-only HTTP actions."""

from typing import Literal


def register_markets_tools(mcp, api_request, identifier):
    @mcp.tool()
    async def compare_markets(vehicle: str = "G60", markets: list[str] | None = None,
                              topics: list[str] | None = None, period: str | None = None,
                              actor: str = "ai:mcp") -> dict:
        """Compare market evidence, sentiment, ranks, targets and demand; missing weights are visibly flagged."""
        return await api_request("POST", "/markets/compare", payload={
            "vehicle": vehicle, "markets": markets, "topics": topics, "period": period, "actor": actor})

    @mcp.tool()
    async def detect_market_conflicts(vehicle: str = "G60", markets: list[str] | None = None,
                                      topics: list[str] | None = None, period: str | None = None,
                                      provider: Literal["openai", "deterministic"] = "openai",
                                      max_texts: int = 1000, actor: str = "ai:mcp") -> dict:
        """Propose grounded cross-market conflicts with deterministic rules. Only a human can resolve them.

        BMW text goes only through the configured OpenAI provider; deterministic is an explicit offline baseline.
        """
        return await api_request("POST", "/markets/conflicts/detect", payload={
            "vehicle": vehicle, "markets": markets, "topics": topics, "period": period,
            "provider": provider, "max_texts": max_texts, "actor": actor})

    @mcp.tool()
    async def extract_market_directions(vehicle: str = "G60", markets: list[str] | None = None,
                                        topics: list[str] | None = None, period: str | None = None,
                                        provider: Literal["openai", "deterministic"] = "openai",
                                        max_texts: int = 1000, actor: str = "ai:mcp") -> dict:
        """Extract cited customer directions through configured OpenAI or the labelled offline term baseline."""
        return await api_request("POST", "/markets/directions", payload={
            "vehicle": vehicle, "markets": markets, "topics": topics, "period": period,
            "provider": provider, "max_texts": max_texts, "actor": actor})

    @mcp.tool()
    async def list_market_conflicts(vehicle: str | None = None, market: str | None = None,
                                    topic: str | None = None, status: str | None = None,
                                    conflict_type: str | None = None, limit: int = 100, offset: int = 0) -> dict:
        """List paginated conflicts and their latest human resolutions, including historical statuses."""
        return await api_request("GET", "/markets/conflicts", params={
            "vehicle": vehicle, "market": market, "topic": topic, "status": status,
            "conflict_type": conflict_type, "limit": limit, "offset": offset})

    @mcp.tool()
    async def get_market_conflict(conflict_id: str) -> dict:
        """Read per-market evidence, exact direction spans, requirements, resolutions and conflict history."""
        return await api_request("GET", f"/markets/conflicts/{identifier(conflict_id)}")

    @mcp.tool()
    async def draft_market_conflict_brief(conflict_id: str, actor: str = "ai:mcp") -> dict:
        """Draft a cited OpenAI explanation alongside the authoritative rules; this never resolves a conflict."""
        return await api_request("POST", f"/markets/conflicts/{identifier(conflict_id)}/brief",
                                 payload={"provider": "openai", "actor": actor})

    @mcp.tool()
    async def list_market_weights(vehicle: str = "G60", market: str | None = None,
                                   period: str | None = None, limit: int = 100, offset: int = 0) -> dict:
        """Read sales-share weights with their evidence and runs, including missing-weight warnings."""
        return await api_request("GET", "/markets/weights", params={
            "vehicle": vehicle, "market": market, "period": period, "limit": limit, "offset": offset})

    @mcp.tool()
    async def get_market_balance_rules() -> dict:
        """Inspect versioned thresholds, attribute/tension tables and deterministic recommendation rules."""
        return await api_request("GET", "/markets/rules")
