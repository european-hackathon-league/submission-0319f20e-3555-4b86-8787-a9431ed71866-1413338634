"""Pod E BMW data and market context tools: import, sales weights, "must not lose" attributes, coverage.

Every operation here is deterministic and audited (A0); none is a human decision gate. BMW files are read
only from the API's DATA_DIR and BMW text goes only to the configured OpenAI provider through the API,
never to Exa or any other service. Tools call the API through the injected
api_request(method, path, *, params=None, payload=None) and use identifier(value) for path segments.
"""

from typing import Literal

Provider = Literal["openai", "deterministic"]
ContextCategory = Literal["regional_sales", "series_deliveries", "ev_adoption", "digital_services", "neue_klasse",
                          "rd_priorities"]


def _present(**values) -> dict:
    return {key: value for key, value in values.items() if value is not None}


def register_market_data_tools(mcp, api_request, identifier):
    @mcp.tool()
    async def import_bmw_data(directory: str = "BMW-Data", paths: list[str] | None = None,
                              document_scopes: list[dict] | None = None, actor: str = "ai:mcp") -> dict:
        """Import every vehicle × market scope of the BMW files under the API's DATA_DIR (idempotent dedup).

        Reads local files only; nothing is sent to an external service. document_scopes ([{vehicle, market}])
        places files that declare neither vehicle nor market, such as the annual report.
        """
        return await api_request("POST", "/market-data/import-bmw", payload=_present(
            directory=directory, paths=paths, document_scopes=document_scopes, actor=actor))

    @mcp.tool()
    async def derive_sales_weights(vehicle: str | None = None, actor: str = "ai:mcp") -> dict:
        """Derive sales-share-v1 market weights (units and share per vehicle × market × period) from sales evidence."""
        return await api_request("POST", "/market-data/weights/derive", payload=_present(vehicle=vehicle, actor=actor))

    @mcp.tool()
    async def list_sales_weights(vehicle: str | None = None, market: str | None = None, period: str | None = None,
                                 status: Literal["current", "superseded", "all"] = "current",
                                 limit: int = 200, offset: int = 0) -> dict:
        """List recorded sales-share weights with their evidence ids, source cells, run and projection flag."""
        return await api_request("GET", "/market-data/weights", params=_present(
            vehicle=vehicle, market=market, period=period, status=status, limit=limit, offset=offset))

    @mcp.tool()
    async def derive_preserve_attributes(vehicle: str = "G60", market: str | None = None,
                                         provider: Provider = "openai", actor: str = "ai:mcp") -> dict:
        """Derive preserve-v1 'what customers love' attributes; strength is a deterministic count.

        provider=openai only names and summarises attributes with grounded quotes through the configured
        OpenAI provider; deterministic is the labelled offline baseline. Never falls back silently.
        """
        return await api_request("POST", "/market-data/preserve/derive", payload=_present(
            vehicle=vehicle, market=market, provider=provider, actor=actor))

    @mcp.tool()
    async def list_preserve_attributes(vehicle: str | None = None, market: str | None = None, topic: str | None = None,
                                       source_type: Literal["feedback", "study"] | None = None,
                                       status: Literal["current", "retired", "all"] = "current",
                                       limit: int = 200, offset: int = 0) -> dict:
        """List 'must not lose' attributes with strength, evidence ids, metrics and any AI label provenance."""
        return await api_request("GET", "/market-data/preserve", params=_present(
            vehicle=vehicle, market=market, topic=topic, source_type=source_type, status=status,
            limit=limit, offset=offset))

    @mcp.tool()
    async def derive_coverage_reports(vehicle: str = "G60", market: str | None = None, actor: str = "ai:mcp") -> dict:
        """Write coverage-v1 representativeness reports: source shares, dating, topic counts, dominance, gaps."""
        return await api_request("POST", "/market-data/coverage", payload=_present(
            vehicle=vehicle, market=market, actor=actor))

    @mcp.tool()
    async def list_coverage_reports(vehicle: str | None = None, market: str | None = None,
                                    status: Literal["current", "superseded", "all"] = "current",
                                    limit: int = 100, offset: int = 0) -> dict:
        """Read coverage reports and their warnings (e.g. single-source dominance, markets without evidence)."""
        return await api_request("GET", "/market-data/coverage", params=_present(
            vehicle=vehicle, market=market, status=status, limit=limit, offset=offset))

    @mcp.tool()
    async def extract_report_context(source_id: str, provider: Provider = "openai", max_pages: int = 12,
                                     actor: str = "ai:mcp") -> dict:
        """Locate (deterministic) or draft (OpenAI) market and strategy context from document pages.

        Every statement cites a page with an exact, locally grounded quote. Pricing, earnings and business
        cases are excluded.
        """
        return await api_request("POST", "/market-data/context/extract", payload=_present(
            source_id=source_id, provider=provider, max_pages=max_pages, actor=actor))

    @mcp.tool()
    async def list_market_context(vehicle: str | None = None, market: str | None = None, source_id: str | None = None,
                                  category: ContextCategory | None = None, limit: int = 200, offset: int = 0) -> dict:
        """List cited annual-report context statements, labelled when AI-generated."""
        return await api_request("GET", "/market-data/context", params=_present(
            vehicle=vehicle, market=market, source_id=source_id, category=category, limit=limit, offset=offset))

    @mcp.tool()
    async def list_data_scopes(vehicle: str | None = None) -> dict:
        """Evidence counts per vehicle × market × record type, with unique feedback IDs and the sales region."""
        return await api_request("GET", "/market-data/scopes", params=_present(vehicle=vehicle))

    @mcp.tool()
    async def list_public_source_connectors(vehicle: str = "G60", market: str = "US") -> dict:
        """Data connectors for a scope (BMW files, NHTSA, public web research), their availability and last run."""
        return await api_request("GET", "/public-sources/catalog", params={"vehicle": vehicle, "market": market})

    @mcp.tool()
    async def import_nhtsa_records(vehicle: str = "G60", market: str = "US", model_years: list[int] | None = None,
                                   include_recalls: bool = True, actor: str = "ai:mcp") -> dict:
        """Import new NHTSA owner complaints and safety recalls (US only) as dated public evidence.

        Sends only make, model and model year to api.nhtsa.gov; records already imported are skipped.
        """
        return await api_request("POST", "/public-sources/nhtsa/import", payload=_present(
            vehicle=vehicle, market=market, model_years=model_years, include_recalls=include_recalls, actor=actor))

    @mcp.tool()
    async def import_public_web_research(vehicle: str = "G60", market: str = "US", topics: list[str] | None = None,
                                         max_per_topic: int = 5, since_year: int = 2024, actor: str = "ai:mcp") -> dict:
        """Find owner forums and press reviews per topic with OpenAI web search and import grounded paraphrases.

        Sends only public model, market and topic names. Pages the search did not return are rejected.
        """
        return await api_request("POST", "/public-sources/web-research/import", payload=_present(
            vehicle=vehicle, market=market, topics=topics, max_per_topic=max_per_topic, since_year=since_year,
            actor=actor))

    @mcp.tool()
    async def get_source_mix(vehicle: str = "G60", market: str = "US") -> dict:
        """Per-source records, dates, origin (BMW internal, public official, public web), role and linked requirements."""
        return await api_request("GET", "/public-sources/mix", params={"vehicle": vehicle, "market": market})
