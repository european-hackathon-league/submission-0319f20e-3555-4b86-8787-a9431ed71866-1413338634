"""Validated commands shared by HTTP and MCP clients."""

import json
import re
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Factor = Annotated[float, Field(ge=0, le=5, allow_inf_nan=False)]
MAX_IMPORT_BYTES = 25 * 1024 * 1024
MAX_IMPORT_TEXT = 5_000_000


def json_size(value) -> int:
    """Reject non-JSON values, nonfinite numbers, and invalid Unicode early."""
    try:
        return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("Source locations and metadata must contain valid JSON") from exc


def observed_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            date.fromisoformat(value)
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?", value):
            datetime.fromisoformat(value)
        else:
            raise ValueError
    except ValueError as exc:
        raise ValueError("observed_at must be an ISO date or timestamp") from exc
    return value


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

    _validate_observed_at = field_validator("observed_at")(observed_date)

    @field_validator("location", "metadata")
    @classmethod
    def bounded_json(cls, value):
        if json_size(value) > 128 * 1024:
            raise ValueError("Source locations and metadata must be at most 128 KiB")
        return value


class RecordsImport(Scope):
    title: Text = Field(max_length=200)
    kind: Literal["feedback", "study", "sales", "document", "other", "web"] = "feedback"
    reference: Text = Field(max_length=2000)
    records: list[EvidenceRecord] = Field(min_length=1, max_length=30_000)
    actor: Text = Field(default="PM", max_length=200)
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def inherit_record_scope(cls, value):
        if isinstance(value, dict):
            value = dict(value)
            records = value.get("records")
            if not isinstance(records, list):
                return value
            if len(records) > 30_000:
                raise ValueError("Import exceeds the 30,000 record limit")
            value["records"] = [
                {"vehicle": value.get("vehicle", "G60"), "market": value.get("market", "US"), **record}
                if isinstance(record, dict) else record for record in records
            ]
        return value

    @model_validator(mode="after")
    def bounded_import(self):
        if sum(len(record.content) for record in self.records) > MAX_IMPORT_TEXT:
            raise ValueError("Import exceeds the extracted text limit")
        if json_size(self.metadata) > 128 * 1024:
            raise ValueError("Source metadata must be at most 128 KiB")
        if json_size(self.model_dump()) > MAX_IMPORT_BYTES:
            raise ValueError("Import exceeds the 25 MiB limit")
        return self


class LocalImport(Scope):
    path: Text = Field(max_length=4096, pattern=r"^[^\x00]+$")
    title: Text | None = Field(default=None, max_length=200)
    kind: Literal["feedback", "study", "sales", "document", "other"] = "document"
    actor: Text = Field(default="PM", max_length=200)


class WebImport(Scope):
    url: Text = Field(max_length=2000)
    title: Text = Field(max_length=200)
    # Preserve the selected snapshot exactly, including leading/trailing spaces.
    content: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(min_length=1, max_length=500_000)
    observed_at: str | None = None
    actor: Text = Field(default="PM", max_length=200)

    _validate_observed_at = field_validator("observed_at")(observed_date)

    @model_validator(mode="after")
    def serializable_snapshot(self):
        json_size(self.model_dump())
        return self


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
