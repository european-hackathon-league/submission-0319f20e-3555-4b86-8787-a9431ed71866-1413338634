from typing import Literal
from urllib.parse import quote, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from mcp_server.errors import EvidenceError
from mcp_server.http import request_json


class Source(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["feedback", "study", "sales", "document", "other", "web"]
    reference: str = Field(min_length=1, max_length=2000)
    vehicle: str = Field(min_length=1, max_length=50)
    market: str = Field(min_length=1, max_length=50)
    created_at: str = Field(min_length=1)


class BackendClient:
    def __init__(self, base_url: str, client: httpx.Client | None = None):
        parts = urlsplit(base_url)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise EvidenceError("API_CONFIGURATION_ERROR", "API_BASE_URL must be an HTTP(S) service URL without credentials.")
        if parts.query or parts.fragment:
            raise EvidenceError("API_CONFIGURATION_ERROR", "API_BASE_URL must not contain query parameters or fragments.")
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=httpx.Timeout(15, connect=5), trust_env=False)

    def list_sources(self, vehicle: str | None = None, market: str | None = None) -> list[dict]:
        params = {}
        for key, value in {"vehicle": vehicle, "market": market}.items():
            if value is not None:
                if not 1 <= len(value.strip()) <= 50:
                    raise EvidenceError("INVALID_ARGUMENT", "Source scope values must contain 1 to 50 characters.")
                params[key] = value
        result = request_json(self.client, "GET", self.base_url + "/sources", service="API", params=params)
        try:
            return [source.model_dump() for source in TypeAdapter(list[Source]).validate_python(result, strict=True)]
        except ValidationError:
            raise EvidenceError("API_INVALID_RESPONSE", "API source list did not match the agreed source schema.") from None

    def get_source(self, source_id: str) -> dict:
        if not source_id or len(source_id) > 200 or source_id in {".", ".."} or any(c in source_id for c in "/\\\r\n\x00"):
            raise EvidenceError("INVALID_ARGUMENT", "Use a single source identifier returned by list_sources.")
        result = request_json(self.client, "GET", self.base_url + "/sources/" + quote(source_id, safe=""), service="API")
        try:
            return Source.model_validate(result, strict=True).model_dump()
        except ValidationError:
            raise EvidenceError("API_INVALID_RESPONSE", "API source did not match the agreed source schema.") from None

    def import_records(self, payload: dict) -> dict:
        result = request_json(self.client, "POST", self.base_url + "/imports/records", service="API", json=payload)
        required = {"source_id": str, "import_id": str, "record_count": int, "deduplicated": bool, "sha256": str}
        if not isinstance(result, dict) or any(type(result.get(key)) is not kind for key, kind in required.items()):
            raise EvidenceError("API_INVALID_RESPONSE", "API import response did not match the agreed import schema; inspect backend state before retrying.")
        if not result["source_id"] or not result["import_id"] or result["record_count"] != 1:
            raise EvidenceError("API_INVALID_RESPONSE", "API import did not confirm the selected source record; inspect backend state before retrying.")
        return result
