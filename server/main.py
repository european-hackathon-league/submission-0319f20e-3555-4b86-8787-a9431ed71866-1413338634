from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from database.store import create_source, get_source, init_database, list_sources, ping_database


class SourceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["feedback", "study", "sales", "document", "other"]
    reference: str = Field(min_length=1, max_length=500)
    vehicle: str = Field(default="G60", min_length=1, max_length=50)
    market: str = Field(default="US", min_length=1, max_length=50)


class Source(SourceCreate):
    id: str
    created_at: str


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield


app = FastAPI(title="BMW Product Evidence API", version="0.1.0", lifespan=lifespan)


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
