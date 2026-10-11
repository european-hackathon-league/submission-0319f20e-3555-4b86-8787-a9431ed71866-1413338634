"""Request preparation over the shared API. Human decisions and curation are deliberately absent."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

Provider = Literal["openai", "deterministic"]


class IntakeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vehicle: str = "G60"
    market: str = "US"
    origin_type: Literal["market_org", "dealer", "engineering", "sales", "board", "customer_channel", "other"]
    origin_name: str
    title: str
    body: str
    requested_at: str | None = None
    simulated: bool = False
    external_ref: str | None = None


def register_intake_tools(mcp, api_request, identifier):
    def present(**values):
        return {key: value for key, value in values.items() if value is not None}

    @mcp.tool()
    async def create_requests(requests: list[IntakeRequest], actor: str = "ai:request-intake") -> dict:
        """Receive one or more stakeholder asks. external_ref makes retries idempotent; simulated data must be labelled.

        Requests are not customer evidence. This does not decide requests or approve requirements.
        """
        return await api_request("POST", "/requests", payload={
            "requests": [item.model_dump(exclude_none=True) for item in requests], "actor": actor})

    @mcp.tool()
    async def list_requests(vehicle: str | None = None, market: str | None = None, topic: str | None = None,
                            status: str | None = None, origin_type: str | None = None, cluster_id: str | None = None,
                            simulated: bool | None = None, flagged: bool | None = None, q: str | None = None,
                            sort: Literal["triage", "requested_at", "key"] = "triage",
                            limit: int = 100, offset: int = 0) -> dict:
        """Read the request inbox with factor scores, scope flags, cluster sizes and triage SLA breaches."""
        return await api_request("GET", "/requests", params=present(
            vehicle=vehicle, market=market, topic=topic, status=status, origin_type=origin_type, cluster_id=cluster_id,
            simulated=simulated, flagged=flagged, q=q, sort=sort, limit=limit, offset=offset))

    @mcp.tool()
    async def get_request(request_id: str, actor: str = "ai:request-intake") -> dict:
        """Read request text, classifications, evidence spans, triage history, PM decisions and position drafts."""
        return await api_request("GET", f"/requests/{identifier(request_id)}", params={"actor": actor})

    @mcp.tool()
    async def classify_requests(vehicle: str = "G60", market: str | None = None, request_ids: list[str] | None = None,
                                provider: Provider = "openai", actor: str = "ai:request-intake") -> dict:
        """Classify topic, customer attribute and excluded scope using OpenAI or the explicit keyword baseline.

        Request text goes only to the configured OpenAI provider. Never send BMW records to public research tools.
        """
        return await api_request("POST", "/requests/classify", payload=present(
            vehicle=vehicle, market=market, request_ids=request_ids, provider=provider, actor=actor))

    @mcp.tool()
    async def cluster_requests(vehicle: str = "G60", topic: str | None = None, provider: Provider = "openai",
                               actor: str = "ai:request-intake") -> dict:
        """Group in-scope requests within vehicle and topic using OpenAI embeddings or explicit Jaccard baseline.

        PM placements stay fixed. Request text goes only to OpenAI, never to public research tools.
        """
        return await api_request("POST", "/requests/cluster", payload=present(
            vehicle=vehicle, topic=topic, provider=provider, actor=actor))

    @mcp.tool()
    async def list_request_clusters(vehicle: str = "G60", topic: str | None = None, market: str | None = None,
                                    include_empty: bool = False,
                                    limit: int = 100, offset: int = 0) -> dict:
        """Read request clusters, member keys and markets, labelled by clustering method."""
        return await api_request("GET", "/requests/clusters", params=present(
            vehicle=vehicle, topic=topic, market=market, include_empty=include_empty, limit=limit, offset=offset))

    @mcp.tool()
    async def propose_request_evidence(vehicle: str = "G60", market: str | None = None,
                                       request_ids: list[str] | None = None, provider: Provider = "openai",
                                       actor: str = "ai:request-intake") -> dict:
        """Propose supporting/conflicting evidence with validated quotes for human curation.

        BMW evidence goes only to OpenAI; never send it to Exa or other public research services.
        """
        return await api_request("POST", "/requests/links/propose", payload=present(
            vehicle=vehicle, market=market, request_ids=request_ids, provider=provider, actor=actor))

    @mcp.tool()
    async def triage_requests(vehicle: str = "G60", market: str | None = None, request_ids: list[str] | None = None,
                              link_provider: Literal["openai", "deterministic", "none"] = "none",
                              actor: str = "ai:request-intake") -> dict:
        """Compute request-triage-v1 scores and explanations; unknown inputs stay flagged and neutral.

        Scoring is deterministic. Optional link proposals use only OpenAI or the explicit offline baseline.
        Human weight changes and decisions are unavailable through this tool.
        """
        return await api_request("POST", "/requests/triage", payload=present(
            vehicle=vehicle, market=market, request_ids=request_ids, link_provider=link_provider, actor=actor))

    @mcp.tool()
    async def draft_request_positions(vehicle: str = "G60", market: str | None = None,
                                      request_ids: list[str] | None = None, provider: Provider = "openai",
                                      actor: str = "ai:request-intake") -> dict:
        """Draft the PM's case for/against and open questions in request threads, with grounded evidence spans.

        Drafts do not decide. BMW evidence goes only to OpenAI, never to public research tools.
        """
        return await api_request("POST", "/requests/positions", payload=present(
            vehicle=vehicle, market=market, request_ids=request_ids, provider=provider, actor=actor))

    @mcp.tool()
    async def get_request_aggregates(vehicle: str = "G60", market: str | None = None, as_of: str | None = None) -> dict:
        """Read demand by market/topic/status/origin, sales-weight inputs, median age and overdue untriaged requests."""
        return await api_request("GET", "/requests/aggregates", params=present(vehicle=vehicle, market=market, as_of=as_of))

    @mcp.tool()
    async def load_simulated_requests(actor: str = "ai:request-intake") -> dict:
        """Load the six clearly labelled synthetic examples idempotently; these are not BMW customer evidence."""
        return await api_request("POST", "/requests/fixtures/simulated", payload={"actor": actor})
