from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import Field

from database.store import create_source, get_source, init_database, list_sources, ping_database
from server.evidence import router as evidence_router
from server.models import Scope
from server.pipeline import router as pipeline_router
from server.requirements import router as requirements_router


class SourceCreate(Scope):
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["feedback", "study", "sales", "document", "other", "web"]
    reference: str = Field(min_length=1, max_length=2000)


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
app.include_router(evidence_router)
app.include_router(pipeline_router)
app.include_router(requirements_router)


@app.get("/health")
def health() -> dict[str, str]:
    ping_database()
    return {"status": "ok"}


@app.get("/sources", response_model=list[Source])
def sources(
    vehicle: str | None = Query(default=None),
    market: str | None = Query(default=None),
) -> list[dict]:
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
