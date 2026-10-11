"""Public data connectors that add dated, non-BMW evidence to a vehicle and market scope.

Two connectors sit next to the BMW file imports and feed the same import → analysis → requirement →
score chain:

- ``nhtsa``: owner complaints and safety recalls from the U.S. National Highway Traffic Safety
  Administration's public API (api.nhtsa.gov). Official, dated records; US market only. Only the make,
  model and model year leave the system.
- ``web_research``: public owner discussions and press reviews found by OpenAI's web_search tool. The
  model paraphrases each page; a page is kept only when the search itself returned or opened its URL.
  Only the public model name, market name and topic label leave the system, never BMW records.

Every import is a recorded run with an audit event, archives the raw response as the source original,
and skips records already imported for the scope, so a repeat call adds only what is new and can drive
an ongoing update. Importing evidence is not a PM decision.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from database.store import connect, decode, encode, now
from server.analysis_engine import TOPICS, ProviderUnavailable
from server.evidence import import_records, scope_filters
from server.llm import llm_client
from server.models import RecordsImport, Scope, Text
from server.platform import Capability, record_run, register_capability
from server.sentiment import TopicKey

router = APIRouter(prefix="/public-sources", tags=["public-sources"])

NHTSA_METHOD = "nhtsa-public-api-v1"
NHTSA_API = "https://api.nhtsa.gov"
NHTSA_TIMEOUT = 30
WEB_PROMPT = "public-web-research-v1"
USER_AGENT = "bmw-product-evidence/0.2 (hackathon prototype; public data only)"

# Public model names per BMW development code. NHTSA lists models per model year; a model counts when its
# name matches the pattern and the year falls in the generation's range.
NHTSA_MODELS = {
    "G60": {"label": "BMW 5 Series / i5 (G60)", "years": (2024, 2025, 2026),
            "pattern": r"^(I5\b|5\d0[IE]\b|5 SERIES|M5\b)"},
    "G70": {"label": "BMW 7 Series / i7 (G70)", "years": (2023, 2024, 2025, 2026),
            "pattern": r"^(I7\b|7\d0I\b|7 SERIES|760I)"},
}
PUBLIC_MODEL_NAMES = {"G60": "BMW 5 Series (G60) and BMW i5", "G70": "BMW 7 Series (G70) and BMW i7",
                      "F70": "BMW 1 Series (F70)"}
PUBLIC_MARKET_NAMES = {"US": "the United States", "EU": "Europe", "CN": "China", "DE": "Germany", "UK": "the United Kingdom"}
# NHTSA component names → the customer-facing topics the analysis already uses.
COMPONENT_TOPICS = (
    (r"FORWARD COLLISION|LANE DEPARTURE|ADAS|BACK OVER|PARKING|CRUISE|BLIND SPOT|DRIVER MONITORING", "driver-assistance"),
    (r"TRACTION BATTERY|CHARG", "charging"),
    (r"STEERING|SERVICE BRAKES|SUSPENSION|POWER TRAIN|ENGINE|ELECTRONIC STABILITY|WHEELS|TIRES|PROPULSION", "driving-experience"),
    (r"SEAT|AIR BAG|SEAT BELT|CLIMATE|HEATER", "comfort"),
    (r"LATCHES|LOCKS|LINKAGES|DOOR", "access-storage"),
    (r"BACK ?UP CAMERA|INFOTAINMENT|NAVIGATION|COMMUNICATION|EQUIPMENT", "connectivity"),
)
DEFAULT_WEB_TOPICS = ("charging", "range", "driver-assistance", "connectivity", "controls", "comfort")

Origin = Literal["bmw_internal", "public_official", "public_web"]


class NhtsaImport(Scope):
    model_years: list[int] | None = Field(default=None, min_length=1, max_length=6)
    include_recalls: bool = True
    actor: Text = Field(default="system:public-sources", max_length=200)


class WebResearchImport(Scope):
    topics: list[TopicKey] = Field(default_factory=lambda: list(DEFAULT_WEB_TOPICS), min_length=1, max_length=8)
    max_per_topic: int = Field(default=5, ge=1, le=8)
    since_year: int = Field(default=2024, ge=2015, le=2030)
    actor: Text = Field(default="system:public-sources", max_length=200)


class _Page(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    title: str
    published_date: str | None
    publisher_type: Literal["owner_forum", "press_review", "social", "video", "consumer_survey", "other"]
    paraphrase: str
    sentiment: Literal["positive", "negative", "mixed"]


class _Pages(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pages: list[_Page]


# Shared ---------------------------------------------------------------------------------------------

def _get_json(path: str, params: dict, warnings: list | None = None) -> dict:
    """GET an NHTSA endpoint. With a warnings list, a 4xx (NHTSA answers 400 for a model without data) is
    recorded there and read as no results; without one, every failure fails the import."""
    url = f"{NHTSA_API}{path}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=NHTSA_TIMEOUT) as response:
            return json.loads(response.read(5_000_000))
    except urllib.error.HTTPError as exc:
        if warnings is not None and 400 <= exc.code < 500:
            warnings.append(f"NHTSA {path} answered HTTP {exc.code} for {params.get('modelYear')} {params.get('model')}")
            return {"results": []}
        raise HTTPException(502, f"NHTSA public API request failed with HTTP {exc.code}") from None
    except (OSError, ValueError) as exc:
        raise HTTPException(502, f"NHTSA public API request failed: {type(exc).__name__}") from None


def _iso(value: str | None, day_first: bool = False) -> str | None:
    """ISO date, or None when missing, invalid or in the future. NHTSA complaints use MM/DD/YYYY, recalls DD/MM/YYYY."""
    if not value:
        return None
    for pattern in ("%d/%m/%Y" if day_first else "%m/%d/%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value.strip()[:10], pattern).date()
        except ValueError:
            continue
        return parsed.isoformat() if parsed <= date.today() else None
    return None


def _component_topic(components: str) -> str | None:
    for pattern, topic in COMPONENT_TOPICS:
        if re.search(pattern, components.upper()):
            return topic
    return None


def _existing(connection, vehicle: str, market: str, connector: str, key: str) -> set[str]:
    rows = connection.execute(
        "SELECT json_extract(e.location, ?) FROM evidence e JOIN sources s ON s.id=e.source_id "
        "WHERE e.vehicle=? AND e.market=? AND json_extract(s.metadata, '$.connector')=?",
        (f"$.{key}", vehicle, market, connector))
    return {str(row[0]) for row in rows if row[0] is not None}


def origin(source: dict) -> Origin:
    metadata = source.get("metadata") or {}
    if metadata.get("connector") == "nhtsa":
        return "public_official"
    return "public_web" if source["kind"] == "web" else "bmw_internal"


# How each kind of source enters the pipeline: customer voice becomes findings and requirement support;
# studies and sales feed the scoring context (market weights, preserve list, coverage); documents describe the product.
ROLES = {"feedback": "customer_voice", "web": "customer_voice", "study": "scoring_context",
         "sales": "scoring_context", "document": "product_context", "other": "product_context"}


# NHTSA ----------------------------------------------------------------------------------------------

def nhtsa_models(vehicle: str, years: list[int] | None) -> list[tuple[int, str]]:
    config = NHTSA_MODELS.get(vehicle)
    if config is None:
        raise HTTPException(422, f"No NHTSA model mapping for {vehicle}; configured: {', '.join(NHTSA_MODELS)}")
    selected = [year for year in (years or config["years"]) if year in config["years"]]
    if not selected:
        raise HTTPException(422, f"{vehicle} model years are {', '.join(map(str, config['years']))}")
    models = []
    for year in selected:
        names = set()
        for issue in ("c", "r"):
            payload = _get_json("/products/vehicle/models", {"modelYear": year, "make": "BMW", "issueType": issue})
            names |= {row.get("model", "") for row in payload.get("results", [])}
        models += [(year, name) for name in sorted(names) if re.search(config["pattern"], name)]
    return models


def _complaint_record(row: dict, year: int, model: str) -> dict | None:
    summary = " ".join(str(row.get("summary") or "").split())
    if not summary or not row.get("odiNumber"):
        return None
    components = str(row.get("components") or "")
    topic = _component_topic(components)
    return {"content": f"Components: {components.title()}. Owner complaint: {summary}",
            "observed_at": _iso(row.get("dateComplaintFiled")),
            "location": {"dataset": "NHTSA complaints", "odi_number": str(row["odiNumber"]), "model": model,
                         "model_year": year,
                         "url": f"https://www.nhtsa.gov/vehicle/{year}/BMW/{urllib.parse.quote(model.title())}"},
            "metadata": {"connector": "nhtsa", "source_type": "public_complaint", "provenance": "NHTSA ODI complaints",
                         "sentiment": "problem", "components": components,
                         **({"topic": TOPICS[topic][0]} if topic else {}),
                         "crash": bool(row.get("crash")), "fire": bool(row.get("fire")),
                         "incident_date": _iso(row.get("dateOfIncident"))}}


def _recall_record(row: dict, models: list[str]) -> dict | None:
    campaign = str(row.get("NHTSACampaignNumber") or "")
    summary = " ".join(str(row.get("Summary") or "").split())
    if not campaign or not summary:
        return None
    component = str(row.get("Component") or "")
    topic = _component_topic(component)
    consequence = " ".join(str(row.get("Consequence") or "").split())
    return {"content": f"Safety recall {campaign} ({component.title()}): {summary} Consequence: {consequence}",
            "observed_at": _iso(row.get("ReportReceivedDate"), day_first=True),
            "location": {"dataset": "NHTSA recalls", "campaign": campaign, "models": models,
                         "url": f"https://www.nhtsa.gov/recalls?nhtsaId={campaign}"},
            "metadata": {"connector": "nhtsa", "source_type": "public_recall", "provenance": "NHTSA recalls",
                         "sentiment": "problem", "components": component,
                         **({"topic": TOPICS[topic][0]} if topic else {})}}


def import_nhtsa(command: NhtsaImport, actor: str | None = None) -> dict:
    actor = actor or command.actor
    if command.market != "US":
        raise HTTPException(422, "NHTSA covers the US market only")
    with record_run(None, "public_sources.import_nhtsa", actor, NHTSA_METHOD, command.model_dump(),
                    vehicle=command.vehicle, market=command.market) as run:
        models = nhtsa_models(command.vehicle, command.model_years)
        complaints, recalls, raw, warnings = {}, {}, {"complaints": [], "recalls": []}, []
        for year, model in models:
            payload = _get_json("/complaints/complaintsByVehicle", {"make": "BMW", "model": model, "modelYear": year},
                                warnings)
            raw["complaints"].append({"model": model, "model_year": year, "results": payload.get("results", [])})
            for row in payload.get("results", []):
                record = _complaint_record(row, year, model)
                if record:
                    complaints.setdefault(record["location"]["odi_number"], record)
            if command.include_recalls:
                payload = _get_json("/recalls/recallsByVehicle", {"make": "BMW", "model": model, "modelYear": year},
                                    warnings)
                raw["recalls"].append({"model": model, "model_year": year, "results": payload.get("results", [])})
                for row in payload.get("results", []):
                    campaign = str(row.get("NHTSACampaignNumber") or "")
                    recalls.setdefault(campaign, {"row": row, "models": []})["models"].append(f"{year} {model}")
        with closing(connect()) as connection:
            seen_complaints = _existing(connection, command.vehicle, command.market, "nhtsa", "odi_number")
            seen_recalls = _existing(connection, command.vehicle, command.market, "nhtsa", "campaign")
        sources = []
        new_complaints = [r for key, r in sorted(complaints.items()) if key not in seen_complaints]
        new_recalls = [r for r in (_recall_record(v["row"], sorted(set(v["models"])))
                                   for key, v in sorted(recalls.items()) if key and key not in seen_recalls) if r]
        retrieved = now()
        for label, records, dataset in (("complaints", new_complaints, "Owner complaints"),
                                        ("recalls", new_recalls, "Safety recalls")):
            if not records:
                continue
            result = import_records(RecordsImport(
                title=f"NHTSA {dataset.lower()} · {NHTSA_MODELS[command.vehicle]['label']}", kind="web",
                reference=f"{NHTSA_API}/{label}?make=BMW&vehicle={command.vehicle}&retrieved={retrieved[:10]}",
                vehicle=command.vehicle, market=command.market, actor=actor, records=records,
                metadata={"connector": "nhtsa", "dataset": dataset, "publisher": "U.S. National Highway Traffic Safety Administration",
                          "origin": "public_official", "retrieved_at": retrieved, "method_version": NHTSA_METHOD,
                          "models": [f"{year} {model}" for year, model in models], "run_id": run.id}),
                original=encode({"retrieved_at": retrieved, label: raw[label]}).encode(), filename=f"nhtsa-{label}.json")
            sources.append({**result, "dataset": dataset, "title": f"NHTSA {dataset.lower()}"})
        run.metrics.update(api_calls=len(models) * (3 if command.include_recalls else 2) + 2,
                           complaints=len(complaints), recalls=len(recalls))
        run.outputs.update(models=[f"{year} {model}" for year, model in models], complaints_found=len(complaints),
                           recalls_found=len(recalls), new_complaints=len(new_complaints), new_recalls=len(new_recalls),
                           sources=sources, warnings=warnings)
    return {**run.outputs, "run_id": run.id, "method_version": NHTSA_METHOD}


# Web research ---------------------------------------------------------------------------------------

def _normal_url(url: str) -> tuple[str, str] | None:
    parts = urllib.parse.urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        return None
    host = parts.hostname.lower().removeprefix("www.")
    return host, parts.path.rstrip("/").lower()


def grounded(url: str, seen: list[str]) -> bool:
    """True when the search returned or opened this page (same host; one path is a prefix of the other)."""
    target = _normal_url(url)
    if target is None or not target[1]:
        return False
    for other in filter(None, map(_normal_url, seen)):
        if other[0] == target[0] and other[1] and (target[1].startswith(other[1]) or other[1].startswith(target[1])):
            return True
    return False


INSTRUCTIONS = (
    "You are a market researcher collecting public customer voice for automotive product planning. Use web search "
    "to find individual public pages: owner forum threads, owner reviews, press road tests and consumer reports. "
    "Return only pages you actually found with the search tool, with their exact URL. Paraphrase in at most two "
    "sentences what owners or reviewers report about the requested topic; never copy long passages. Use the page's "
    "publication date as YYYY-MM-DD, or null when it is not shown. Prefer first-hand owner experience, include "
    "praise as well as problems, and skip manufacturer marketing pages and dealer advertisements.")


def _question(command: WebResearchImport, topic: str) -> str:
    label, outcome, _ = TOPICS[topic]
    return (f"Find up to {command.max_per_topic} public pages published since {command.since_year} where owners or "
            f"reviewers of the {PUBLIC_MODEL_NAMES.get(command.vehicle, 'BMW ' + command.vehicle)} in "
            f"{PUBLIC_MARKET_NAMES.get(command.market, command.market)} discuss {label.lower()} "
            f"(whether drivers can {outcome}).")


def import_web_research(command: WebResearchImport, actor: str | None = None) -> dict:
    actor = actor or command.actor
    try:
        client = llm_client()
    except ProviderUnavailable as exc:
        raise HTTPException(503, f"Web research needs the OpenAI provider: {exc}") from None
    method = client.method_version(WEB_PROMPT)
    with record_run(None, "public_sources.web_research", actor, method, command.model_dump(),
                    vehicle=command.vehicle, market=command.market) as run:
        topics = list(dict.fromkeys(command.topics))
        answers = client.web_search(task="public_web_research", prompt_version=WEB_PROMPT, instructions=INSTRUCTIONS,
                                    inputs=[_question(command, topic) for topic in topics], schema=_Pages, run=run)
        with closing(connect()) as connection:
            seen_urls = {_normal_url(url) for url in _existing(connection, command.vehicle, command.market,
                                                                "web_research", "url")}
        records, rejected, per_topic, kept_urls = [], [], {}, set()
        for topic, (answer, search_urls) in zip(topics, answers):
            counts = per_topic.setdefault(topic, {"found": len(answer.pages), "kept": 0, "already_imported": 0,
                                                  "rejected": 0, "search_results": len(search_urls)})
            for page in answer.pages[:command.max_per_topic]:
                key = _normal_url(page.url)
                reason = ("not_returned_by_search" if not grounded(page.url, search_urls) else
                          "empty_paraphrase" if not page.paraphrase.strip() else None)
                if reason:
                    counts["rejected"] += 1
                    rejected.append({"topic": topic, "url": page.url[:500], "reason": reason})
                    continue
                if key in seen_urls or key in kept_urls:
                    counts["already_imported"] += 1
                    continue
                kept_urls.add(key)
                counts["kept"] += 1
                published = _iso(page.published_date)
                records.append({
                    "content": " ".join(page.paraphrase.split())[:1500],
                    "observed_at": published,
                    "location": {"url": page.url.strip()[:2000], "title": page.title.strip()[:300]},
                    "metadata": {"connector": "web_research", "source_type": "public_web_paraphrase",
                                 "provenance": key[0], "publisher_type": page.publisher_type, "topic": TOPICS[topic][0],
                                 "sentiment": {"positive": "positive", "negative": "problem"}.get(page.sentiment, "mixed"),
                                 "ai_paraphrase": True, "model": client.model, "prompt_version": WEB_PROMPT,
                                 "date_basis": "published" if published else "undated"}})
        result = None
        if records:
            retrieved = now()
            result = import_records(RecordsImport(
                title=f"Public web research · {', '.join(TOPICS[t][0].lower() for t in topics)}"[:200], kind="web",
                reference=f"openai-web-search:{command.vehicle}:{command.market}:{retrieved}",
                vehicle=command.vehicle, market=command.market, actor=actor, records=records,
                metadata={"connector": "web_research", "origin": "public_web", "provider": "openai",
                          "model": client.model, "prompt_version": WEB_PROMPT, "method_version": method,
                          "topics": topics, "retrieved_at": retrieved, "run_id": run.id,
                          "note": "AI paraphrases of public pages; each URL was returned by the web search itself"}),
                original=encode({"retrieved_at": retrieved, "questions": {t: _question(command, t) for t in topics},
                                 "answers": [{"topic": t, "pages": a.model_dump()["pages"], "search_urls": s}
                                             for t, (a, s) in zip(topics, answers)]}).encode(),
                filename="web-research.json")
        run.metrics.update(pages=len(records), rejected=len(rejected))
        run.outputs.update(per_topic=per_topic, imported=len(records), rejected=rejected,
                           source=result, provider="openai", model=client.model)
    return {**run.outputs, "run_id": run.id, "method_version": method}


# Source mix -----------------------------------------------------------------------------------------

def source_mix(vehicle: str, market: str) -> dict:
    with closing(connect()) as connection:
        sources = [decode(row, ("metadata",)) for row in connection.execute(
            "SELECT * FROM sources WHERE vehicle=? AND market=? ORDER BY created_at, id", (vehicle, market))]
        stats = {row["source_id"]: dict(row) for row in connection.execute(
            "SELECT source_id, count(*) AS records, count(observed_at) AS dated, min(substr(observed_at,1,10)) AS first, "
            "max(substr(observed_at,1,10)) AS last FROM evidence WHERE vehicle=? AND market=? GROUP BY source_id",
            (vehicle, market))}
        links = {row["source_id"]: dict(row) for row in connection.execute(
            "SELECT e.source_id, count(DISTINCT r.id) AS requirements, count(DISTINCT fe.finding_id) AS findings, "
            "count(DISTINCT e.id) AS linked_records "
            "FROM requirements r JOIN requirement_findings rf ON rf.version_id=r.current_version_id "
            "JOIN finding_evidence fe ON fe.finding_id=rf.finding_id AND fe.relation='supports' "
            "JOIN evidence e ON e.id=fe.evidence_id WHERE r.vehicle=? AND r.market=? GROUP BY e.source_id",
            (vehicle, market))}
        requirements = connection.execute("SELECT count(*) FROM requirements WHERE vehicle=? AND market=?",
                                          (vehicle, market)).fetchone()[0]
        public_requirements = connection.execute(
            "SELECT count(DISTINCT r.id) FROM requirements r JOIN requirement_findings rf ON rf.version_id=r.current_version_id "
            "JOIN finding_evidence fe ON fe.finding_id=rf.finding_id AND fe.relation='supports' "
            "JOIN evidence e ON e.id=fe.evidence_id JOIN sources s ON s.id=e.source_id "
            "WHERE r.vehicle=? AND r.market=? AND s.kind='web'", (vehicle, market)).fetchone()[0]
    items = []
    for source in sources:
        stat, link = stats.get(source["id"], {}), links.get(source["id"], {})
        meta = source["metadata"] or {}
        items.append({"source_id": source["id"], "title": source["title"], "kind": source["kind"],
                      "origin": origin(source), "role": ROLES.get(source["kind"], "product_context"),
                      "connector": meta.get("connector"),
                      "publisher": meta.get("publisher") or meta.get("model") and f"OpenAI web search ({meta['model']})",
                      "reference": source["reference"], "imported_at": source["created_at"],
                      "records": stat.get("records", 0), "dated_records": stat.get("dated", 0),
                      "first_observed": stat.get("first"), "last_observed": stat.get("last"),
                      "linked_records": link.get("linked_records", 0), "linked_findings": link.get("findings", 0),
                      "linked_requirements": link.get("requirements", 0)})
    by_origin = {}
    for item in items:
        group = by_origin.setdefault(item["origin"], {"sources": 0, "records": 0, "dated_records": 0, "linked_records": 0})
        for key in ("records", "dated_records", "linked_records"):
            group[key] += item[key]
        group["sources"] += 1
    return {"vehicle": vehicle, "market": market, "sources": items, "by_origin": by_origin,
            "totals": {"sources": len(items), "records": sum(i["records"] for i in items),
                       "dated_records": sum(i["dated_records"] for i in items), "requirements": requirements,
                       "requirements_with_public_evidence": public_requirements}}


def catalog(vehicle: str, market: str) -> dict:
    try:
        llm_client()
        web_ready, web_reason = True, None
    except ProviderUnavailable as exc:
        web_ready, web_reason = False, str(exc)
    nhtsa_ready = vehicle in NHTSA_MODELS and market == "US"
    with closing(connect()) as connection:
        last = {row["capability"]: dict(row) for row in connection.execute(
            "SELECT capability, id, status, finished_at, outputs FROM runs WHERE capability IN "
            "('public_sources.import_nhtsa','public_sources.web_research') AND vehicle=? AND market=? "
            "ORDER BY started_at", (vehicle, market))}
    def run_info(name):
        row = last.get(name)
        return row and {"run_id": row["id"], "status": row["status"], "finished_at": row["finished_at"]}
    return {"vehicle": vehicle, "market": market, "connectors": [
        {"key": "bmw_files", "label": "BMW customer feedback, studies, sales and option lists", "origin": "bmw_internal",
         "publisher": "BMW Group (supplied files)", "available": True, "reason": None,
         "endpoint": "POST /market-data/import-bmw", "last_run": None},
        {"key": "nhtsa", "label": "NHTSA owner complaints and safety recalls", "origin": "public_official",
         "publisher": "U.S. National Highway Traffic Safety Administration", "available": nhtsa_ready,
         "reason": None if nhtsa_ready else "US market and a mapped model (G60, G70) only",
         "endpoint": "POST /public-sources/nhtsa/import", "last_run": run_info("public_sources.import_nhtsa")},
        {"key": "web_research", "label": "Public owner forums and press reviews", "origin": "public_web",
         "publisher": "OpenAI web search, grounded to returned URLs", "available": web_ready, "reason": web_reason,
         "endpoint": "POST /public-sources/web-research/import", "last_run": run_info("public_sources.web_research")},
    ]}


@router.get("/catalog")
def get_catalog(vehicle: str = "G60", market: str = "US"):
    vehicle, market = scope_filters(vehicle, market)
    return catalog(vehicle, market)


@router.get("/mix")
def get_mix(vehicle: str = "G60", market: str = "US"):
    vehicle, market = scope_filters(vehicle, market)
    return source_mix(vehicle, market)


@router.post("/nhtsa/import", status_code=201)
def post_nhtsa(command: NhtsaImport):
    return import_nhtsa(command)


@router.post("/web-research/import", status_code=201)
def post_web_research(command: WebResearchImport):
    return import_web_research(command)


register_capability(Capability(
    "public_sources.import_nhtsa", "Import new NHTSA owner complaints and safety recalls for the scope's public "
    "models (US only) as dated public evidence. Sends only make, model and model year.",
    NhtsaImport, import_nhtsa, "A0", ("sources", "evidence", "imports")))
register_capability(Capability(
    "public_sources.web_research", "Find public owner discussions and press reviews per topic with OpenAI web search "
    "and import grounded paraphrases with their URLs as public evidence. Sends only public model, market and topic names.",
    WebResearchImport, import_web_research, "A1", ("sources", "evidence", "imports")))
