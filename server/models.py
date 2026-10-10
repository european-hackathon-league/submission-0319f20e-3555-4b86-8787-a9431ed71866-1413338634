"""Validated commands shared by HTTP and MCP clients."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Factor = Annotated[float, Field(ge=0, le=5, allow_inf_nan=False)]


def normalize_market(value: str) -> str:
    value = value.strip().upper()
    return {"USA": "US", "UNITED STATES": "US", "EUROPE": "EU", "CHINA": "CN"}.get(value, value)


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class Scope(Command):
    vehicle: Text = Field(default="G60", max_length=50)
    market: Text = Field(default="US", max_length=50)

    @field_validator("vehicle")
    @classmethod
    def vehicle_case(cls, value):
        return value.upper()

    @field_validator("market")
    @classmethod
    def market_case(cls, value):
        return normalize_market(value)


class EvidenceRecord(Scope):
    content: Text = Field(max_length=100_000)
    location: dict = Field(min_length=1)
    metadata: dict = Field(default_factory=dict)
    observed_at: str | None = None


class RecordsImport(Scope):
    title: Text = Field(max_length=200)
    kind: Literal["feedback", "study", "sales", "document", "other", "web"] = "feedback"
    reference: Text = Field(max_length=2000)
    records: list[EvidenceRecord] = Field(min_length=1, max_length=30_000)
    actor: Text = "PM"
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def inherit_record_scope(cls, value):
        if isinstance(value, dict):
            value = dict(value)
            value["records"] = [
                {"vehicle": value.get("vehicle", "G60"), "market": value.get("market", "US"), **record}
                if isinstance(record, dict) else record for record in value.get("records", [])
            ]
        return value


class LocalImport(Scope):
    path: Text
    title: Text | None = None
    kind: Literal["feedback", "study", "sales", "document", "other"] = "document"
    actor: Text = "PM"


class WebImport(Scope):
    url: Text = Field(max_length=2000)
    title: Text = Field(max_length=200)
    content: Text = Field(max_length=500_000)
    observed_at: str | None = None
    actor: Text = "PM"


class AnalysisRequest(Scope):
    provider: Literal["deterministic", "openai"] = "deterministic"
    source_ids: list[Text] | None = Field(default=None, min_length=1, max_length=1000)
    actor: Text = "PM"


class GenerateRequest(Command):
    run_id: Text
    actor: Text = "PM"


class Factors(Command):
    customer_impact: Factor
    market_relevance: Factor
    strategic_fit: Factor
    differentiation: Factor
    feasibility: Factor


class Weights(Command):
    customer_impact: Annotated[float, Field(ge=0, le=1)] = 0.35
    market_relevance: Annotated[float, Field(ge=0, le=1)] = 0.25
    strategic_fit: Annotated[float, Field(ge=0, le=1)] = 0.20
    differentiation: Annotated[float, Field(ge=0, le=1)] = 0.10
    feasibility: Annotated[float, Field(ge=0, le=1)] = 0.10

    @model_validator(mode="after")
    def sums_to_one(self):
        if abs(sum(self.model_dump().values()) - 1) > 1e-6:
            raise ValueError("Scoring weights must sum to 1")
        return self


class AcceptanceCriterion(Command):
    metric: Text
    target: Text | float
    unit: str | None = None
    basis: Literal["PM assumption", "source"]
    source_ids: list[Text] = Field(default_factory=list)

    @model_validator(mode="after")
    def source_basis_has_reference(self):
        if self.basis == "source" and not self.source_ids:
            raise ValueError("A source-based target must identify its sources")
        if self.basis == "PM assumption" and self.source_ids:
            raise ValueError("PM-assumed targets must not claim source citations")
        return self


class RequirementContent(Command):
    title: Text = Field(max_length=300)
    statement: Text = Field(max_length=10_000)
    customer_need: Text = Field(max_length=10_000)
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=1, max_length=30)
    assumptions: list[Text] = Field(default_factory=list, max_length=100)
    factors: Factors


class RequirementCreate(RequirementContent, Scope):
    topic: Text = Field(max_length=100)
    finding_ids: list[Text] = Field(min_length=1, max_length=1000)
    actor: Text = "PM"
    rationale: Text


class RequirementEdit(Command):
    expected_version_id: Text
    actor: Text
    rationale: Text
    title: Text | None = Field(default=None, max_length=300)
    statement: Text | None = Field(default=None, max_length=10_000)
    customer_need: Text | None = Field(default=None, max_length=10_000)
    acceptance_criteria: list[AcceptanceCriterion] | None = Field(default=None, min_length=1, max_length=30)
    assumptions: list[Text] | None = Field(default=None, max_length=100)
    factors: Factors | None = None
    finding_ids: list[Text] | None = Field(default=None, min_length=1, max_length=1000)


class ScoreRequest(Command):
    expected_version_id: Text
    expected_score_id: Text | None = None
    weights: Weights = Field(default_factory=Weights)
    actor: Text
    rationale: Text


class DecisionRequest(Command):
    version_id: Text
    score_id: Text
    action: Literal["approve", "reject", "postpone", "challenge"]
    actor: Text
    rationale: Text
