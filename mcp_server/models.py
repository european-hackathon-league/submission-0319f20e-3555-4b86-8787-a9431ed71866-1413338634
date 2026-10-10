"""Public research inputs and conservative URL identity rules."""

import hashlib
import ipaddress
import re
from datetime import date
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mcp_server.errors import EvidenceError

TRACKING_PARAMS = {"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid"}
SECRET_PARAMS = {"token", "key", "api_key", "apikey", "access_token", "auth", "authorization", "signature", "password"}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def public_text(value: str) -> str:
    """A guardrail, not a semantic privacy classifier. Caller attestation is required."""
    value = value.strip()
    if not value or len(value) > 240 or any(c in value for c in "\r\n\t"):
        raise ValueError("Use a short public research topic, not a pasted record.")
    patterns = (
        r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        r"\b[A-HJ-NPR-Z0-9]{17}\b",  # VIN-like identifiers
        r"(?:\+?\d[ ()-]*){9,}",
        r"(?i)\b(confidential|verbatim|internal dataset|customer id|customer name|personal data)\b",
        r"(?i)(?:https?://|api[_ -]?key|access[_ -]?token|password)\s*[:=]?",
    )
    if any(re.search(pattern, value) for pattern in patterns):
        raise ValueError("Use public product terms only; remove personal, internal, or secret data.")
    return value


def canonicalize_url(value: str) -> str:
    """Normalize identity without collapsing semantic paths, queries, or subdomains."""
    try:
        if len(value) > 2048 or any(ord(c) < 33 for c in value) or "\\" in value:
            raise ValueError
        parts = urlsplit(value)
        host = (parts.hostname or "").encode("idna").decode("ascii").lower()
        if parts.scheme.lower() not in {"http", "https"} or not host or parts.username or parts.password:
            raise ValueError
        if host.endswith(".") or host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".test")):
            raise ValueError
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            if "." not in host or not re.fullmatch(r"[a-z0-9.-]+", host):
                raise ValueError
            if all(part.isdigit() for part in host.split(".")):
                raise ValueError
            if any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-")
                   for label in host.split(".")):
                raise ValueError
        else:
            if not ip.is_global:
                raise ValueError
            host = f"[{host}]" if ip.version == 6 else host
        port = parts.port
        if port not in {None, 80, 443}:
            raise ValueError
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        for key, val in pairs:
            if key.lower() in SECRET_PARAMS or key.lower().startswith("x-amz-") or "@" in val:
                raise ValueError
        pairs = [(k, v) for k, v in pairs if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS]
        authority = host
        if port and not (parts.scheme.lower() == "https" and port == 443 or parts.scheme.lower() == "http" and port == 80):
            authority += f":{port}"
        return urlunsplit((parts.scheme.lower(), authority, parts.path or "/", urlencode(pairs), ""))
    except (ValueError, UnicodeError, TypeError):
        raise EvidenceError("INVALID_PUBLIC_URL", "Use a public HTTP(S) URL without credentials or secret parameters.") from None


class ResearchScope(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=240, description="Public product/market topic only; no BMW records or PII.")
    public_data_confirmed: Literal[True] = Field(description="Caller confirms all supplied text is public and nonpersonal.")
    vehicle: str = Field(default="G60", min_length=1, max_length=50)
    market: str = Field(default="US", pattern=r"^[A-Z]{2}$")
    cache_only: bool = False

    @field_validator("query", "vehicle")
    @classmethod
    def validate_public_text(cls, value: str) -> str:
        return public_text(value)


class SearchRequest(ResearchScope):
    max_results: int = Field(default=5, ge=1, le=10)
    trusted_domains: list[str] | None = Field(default=None, min_length=1, max_length=10)
    start_published_date: date | None = None
    end_published_date: date | None = None

    @field_validator("trusted_domains")
    @classmethod
    def validate_domains(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        result = []
        for value in values:
            value = value.strip().lower()
            if any(c in value for c in "/:@?#*"):
                raise ValueError("Trusted domains must be public hostnames, without paths or wildcards.")
            canonicalize_url("https://" + value)
            result.append(value)
        return sorted(set(result))

    @model_validator(mode="after")
    def check_dates(self):
        if self.start_published_date and self.end_published_date and self.start_published_date > self.end_published_date:
            raise ValueError("The publication start date must not follow the end date.")
        return self


class FetchRequest(ResearchScope):
    identifier: str = Field(min_length=1, max_length=2048, description="Public URL or Exa ID returned by a cached search.")
