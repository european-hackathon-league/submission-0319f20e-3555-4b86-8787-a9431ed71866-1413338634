"""Signals adapter. PM gates are available only in the human API/workspace, never agent tools."""

from typing import Literal


def register_signals_tools(mcp, api_request, identifier):
    @mcp.tool()
    async def list_signal_watchlists(vehicle: str = "G60", market: str = "US", topic: str | None = None,
                                    limit: int = 100, offset: int = 0) -> dict:
        """List PM-authorised public monitoring templates. Never send BMW records, verbatims or personal data to Exa."""
        return await api_request("GET", "/signals/watchlists", params={"vehicle": vehicle, "market": market,
                                "topic": topic, "limit": limit, "offset": offset})

    @mcp.tool()
    async def get_signal_watchlist(watchlist_id: str) -> dict:
        """Read a PM-authorised public template; its existence is the standing search authorisation."""
        return await api_request("GET", f"/signals/watchlists/{identifier(watchlist_id)}")

    @mcp.tool()
    async def refresh_signal_watchlist(watchlist_id: str, actor: str, cache_only: bool = False) -> dict:
        """Refresh a public template. Exa receives only approved public product terms, never BMW records, verbatims or personal data. Results are unreviewed leads, not evidence."""
        return await api_request("POST", f"/signals/watchlists/{identifier(watchlist_id)}/refresh",
                                 payload={"actor": actor, "cache_only": cache_only})

    @mcp.tool()
    async def backfill_signal_watchlist(watchlist_id: str, actor: str, weeks: int = 12, cache_only: bool = False) -> dict:
        """Search up to 12 weekly windows. Exa queries use only public templates, never BMW records, verbatims or personal data. Import remains a human gate."""
        return await api_request("POST", f"/signals/watchlists/{identifier(watchlist_id)}/backfill",
                                 payload={"actor": actor, "weeks": weeks, "cache_only": cache_only})

    @mcp.tool()
    async def list_signal_items(vehicle: str = "G60", market: str = "US", topic: str | None = None,
                                watchlist_id: str | None = None, review_status: str | None = None,
                                limit: int = 100, offset: int = 0) -> dict:
        """Read public monitoring leads with dates and URLs; they are not BMW customer evidence."""
        return await api_request("GET", "/signals/items", params={"vehicle": vehicle, "market": market,
                                 "topic": topic, "watchlist_id": watchlist_id, "review_status": review_status,
                                 "limit": limit, "offset": offset})

    @mcp.tool()
    async def get_signal_item(item_id: str) -> dict:
        """Read the exact public excerpt, search provenance and human review status of a monitoring lead."""
        return await api_request("GET", f"/signals/items/{identifier(item_id)}")

    @mcp.tool()
    async def score_signal_sentiment(vehicle: str, market: str, actor: str,
                                      provider: Literal["openai", "deterministic"] = "openai",
                                      subject_type: Literal["all", "evidence", "signal_item"] = "all",
                                      subject_ids: list[str] | None = None, topic: str | None = None,
                                      limit: int = 1000) -> dict:
        """Interpret sentiment with grounded OpenAI or the explicit offline lexicon. BMW evidence goes only through the configured OpenAI provider, never Exa. No decisions are made."""
        return await api_request("POST", "/signals/sentiment/score", payload={"vehicle": vehicle, "market": market,
                                 "actor": actor, "provider": provider, "subject_type": subject_type,
                                 "subject_ids": subject_ids, "topic": topic, "limit": limit})

    @mcp.tool()
    async def list_sentiment_scores(vehicle: str = "G60", market: str = "US", topic: str | None = None,
                                   method_version: str | None = None, limit: int = 100, offset: int = 0) -> dict:
        """Read versioned sentiment scores with grounded spans, provider and run traceability."""
        return await api_request("GET", "/signals/sentiment/scores", params={"vehicle": vehicle, "market": market,
                                 "topic": topic, "method_version": method_version, "limit": limit, "offset": offset})

    @mcp.tool()
    async def get_sentiment_timeseries(vehicle: str = "G60", market: str = "US", topic: str | None = None,
                                      source_class: str | None = None, method_version: str | None = None,
                                      limit: int = 1000, offset: int = 0) -> dict:
        """Read weekly sentiment counts, polarity, sample ids and low-n flags. Never combine methods or source classes."""
        return await api_request("GET", "/signals/sentiment/timeseries", params={"vehicle": vehicle, "market": market,
                                 "topic": topic, "source_class": source_class, "method_version": method_version,
                                 "limit": limit, "offset": offset})

    @mcp.tool()
    async def get_signal_summary(vehicle: str = "G60", market: str = "US", topic: str | None = None,
                                  source_class: str | None = None, method_version: str | None = None) -> dict:
        """Read deterministic per-topic counts, sentiment and n-weighted eight-week momentum, separated by source and method."""
        return await api_request("GET", "/signals/summary", params={"vehicle": vehicle, "market": market,
                                 "topic": topic, "source_class": source_class, "method_version": method_version})

    @mcp.tool()
    async def summarise_signals(vehicle: str, market: str, actor: str,
                               provider: Literal["openai", "deterministic"] = "openai", topic: str | None = None,
                               source_class: str | None = None, method_version: str | None = None) -> dict:
        """Draft grounded observations from recorded series through configured OpenAI; deterministic returns metrics only. BMW texts never go to Exa. Outputs are proposals, not decisions."""
        return await api_request("POST", "/signals/summary", payload={"vehicle": vehicle, "market": market,
                                 "actor": actor, "provider": provider, "topic": topic,
                                 "source_class": source_class, "method_version": method_version})
