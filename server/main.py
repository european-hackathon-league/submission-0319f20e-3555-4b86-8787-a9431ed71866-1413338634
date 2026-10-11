import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, model_validator

from database.store import create_source, get_source, init_database, list_sources, ping_database
from server import agent_runtime
from server.analysis_engine import AnalysisError, ProviderUnavailable
from server.decision_briefs import router as decision_briefs_router
from server.evaluation import router as evaluation_router
from server.evidence import ImportRoute, scope_filters
from server.evidence import router as evidence_router
from server.exa_research import router as exa_research_router
from server.intake import router as intake_router
from server.llm import LLMOutputInvalid
from server.market_data import router as market_data_router
from server.markets import router as markets_router
from server.models import Scope, json_size
from server.pipeline import router as pipeline_router
from server.platform import HUMAN_REQUIRED
from server.prioritization import router as prioritization_router
from server.public_sources import router as public_sources_router
from server.requirements import router as requirements_router
from server.signals import router as signals_router
from server.web_fetch import router as web_fetch_router
from server.workflows import router as workflows_router


class SourceCreate(Scope):
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["feedback", "study", "sales", "document", "other", "web"]
    reference: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def serializable_source(self):
        json_size(self.model_dump())
        return self


class Source(SourceCreate):
    id: str
    created_at: str
    metadata: dict = Field(default_factory=dict)
    content_hash: str | None = None
    observed_at: str | None = None
    original_path: str | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield


app = FastAPI(title="BMW Product Evidence API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"
    ).split(",") if origin.strip()],
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)
app.include_router(evidence_router)
app.include_router(exa_research_router)
app.include_router(pipeline_router)
app.include_router(requirements_router)
app.include_router(web_fetch_router)
app.include_router(evaluation_router)
app.include_router(workflows_router)
app.include_router(decision_briefs_router)
# Platform pods (PLATFORM_BUILD_PLAN.md); each module owns the routes under its prefix.
app.include_router(signals_router)
app.include_router(markets_router)
app.include_router(intake_router)
app.include_router(prioritization_router)
app.include_router(market_data_router)
app.include_router(public_sources_router)
for runtime_router in agent_runtime.routers:
    app.include_router(runtime_router)
app.router.route_class = ImportRoute


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc):
    # Invalid input itself may contain NaN or broken Unicode, which cannot be
    # echoed in a JSON response. Return the actionable validation locations.
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": [part.encode("utf-8", "backslashreplace").decode("utf-8")
                 if isinstance(part, str) else part for part in error["loc"]], "type": error["type"],
         "msg": str(error["msg"]).encode("utf-8", "replace").decode("utf-8")}
        for error in exc.errors()
    ]})


@app.exception_handler(sqlite3.IntegrityError)
async def governance_error_handler(request, exc):
    # Transactions have already rolled back before a database denial reaches
    # this handler. Only named actor gates are client permission failures;
    # unrelated integrity errors must remain visible as server failures.
    detail = str(exc)
    if detail in {"inactive actor", "decisions require a human actor", "approve and reject require a PM role",
                  HUMAN_REQUIRED}:
        return JSONResponse(status_code=403, content={"detail": detail})
    raise exc


@app.exception_handler(ProviderUnavailable)
async def provider_error_handler(request, exc):
    # The selected AI provider is unavailable; never substitute another method.
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(AnalysisError)
async def analysis_error_handler(request, exc):
    # Model output that failed strict JSON, schema or grounding checks is rejected, not stored.
    return JSONResponse(status_code=502 if isinstance(exc, LLMOutputInvalid) else 422, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict[str, str]:
    ping_database()
    return {"status": "ok"}


@app.get("/sources", response_model=list[Source])
def sources(
    vehicle: str | None = Query(default=None),
    market: str | None = Query(default=None),
) -> list[dict]:
    vehicle, market = scope_filters(vehicle, market)
    return list_sources(vehicle=vehicle, market=market)


@app.post("/sources", response_model=Source, status_code=201)
def add_source(source: SourceCreate) -> dict:
    return create_source(source.model_dump())


@app.get("/sources/{source_id}", response_model=Source)
def source(source_id: str) -> dict:
    result = get_source(source_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return result


app.mount("/pm", StaticFiles(directory=Path(__file__).parent / "pm_static", html=True), name="pm")
