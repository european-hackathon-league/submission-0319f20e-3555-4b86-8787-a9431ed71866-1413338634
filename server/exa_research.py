"""Opt-in Exa research through the application API, with explicit source selection."""

import os
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from database.store import get_source
from mcp_server.errors import EvidenceError
from mcp_server.exa_client import ExaClient
from mcp_server.ingestion import import_candidate
from mcp_server.models import FetchRequest, SearchRequest
from server.evidence import records_import
from server.models import RecordsImport

router = APIRouter(prefix="/research/exa", tags=["research"])


class CandidateSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    candidate_id: str = Field(min_length=1, max_length=80)
    actor: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=2000)
    selection_confirmed: Literal[True]


@lru_cache(maxsize=1)
def exa_client() -> ExaClient:
    return ExaClient()


def _error(exc: EvidenceError) -> HTTPException:
    status = 422
    if exc.code in {"EXA_CONFIGURATION_ERROR", "EXA_AUTHENTICATION_FAILED", "EXA_ACCESS_DENIED"}:
        status = 503
    elif exc.code == "EXA_CREDITS_EXHAUSTED":
        status = 402
    elif exc.code == "EXA_RATE_LIMITED":
        status = 429
    elif exc.code in {"CACHE_MISS", "CANDIDATE_NOT_FOUND", "UNKNOWN_EXA_RESULT"}:
        status = 404
    elif exc.code.startswith("EXA_"):
        status = 502
    return HTTPException(status_code=status, detail=f"{exc.code}: {exc.message}")


class LocalBackend:
    """Use the same import transaction as every other API client, without HTTP loopback."""

    @staticmethod
    def import_records(payload: dict) -> dict:
        return records_import(RecordsImport.model_validate(payload))

    @staticmethod
    def get_source(source_id: str) -> dict:
        source = get_source(source_id)
        if source is None:
            raise EvidenceError("API_NOT_FOUND", "The imported source could not be read back.")
        return source


@router.get("/status")
def exa_status() -> dict:
    """Configuration visibility only; this endpoint never contacts Exa."""
    return {"provider": "exa", "configured": bool(os.getenv("EXA_API_KEY", "").strip())}


@router.post("/search")
def search_exa(command: SearchRequest) -> dict:
    """Return unreviewed public leads; no evidence or decision is written."""
    try:
        return exa_client().search(command)
    except EvidenceError as exc:
        raise _error(exc) from None


@router.post("/fetch")
def fetch_exa(command: FetchRequest) -> dict:
    """Return a bounded public-text snapshot; importing remains a separate action."""
    try:
        return exa_client().fetch(command)
    except EvidenceError as exc:
        raise _error(exc) from None


@router.post("/import", status_code=201)
def import_exa(command: CandidateSelection) -> dict:
    """Persist one selected fetched candidate with its complete Exa provenance."""
    try:
        return import_candidate(exa_client().cache, LocalBackend(), command.candidate_id,
                                command.actor, command.rationale, command.selection_confirmed)
    except EvidenceError as exc:
        raise _error(exc) from None
