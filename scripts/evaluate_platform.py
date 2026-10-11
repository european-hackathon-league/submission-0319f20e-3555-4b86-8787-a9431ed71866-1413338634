"""Measure the platform capabilities on labelled synthetic scenarios through the public HTTP API.

Run against a running API (default: the local Compose API):

    uv run python scripts/evaluate_platform.py --base-url http://127.0.0.1:8000 \\
        --providers deterministic,openai --json-out platform-eval.json --markdown-out platform-eval.md

Every scenario runs once per provider in its own fresh synthetic vehicle scope
(EVAL-<token>-<scenario>-<D|O>), loaded from tests/fixtures/eval/ through the public endpoints, so
results never mix with BMW data or with each other. Setup always uses the deterministic reference
pipeline; only the capability under test changes provider. A missing endpoint (404/405) or an
unavailable provider (503) marks that metric not_available with the reason, any other API error marks
it failed, and the run continues. Nothing is estimated, substituted or retried with another provider.
Deterministic code without a provider (ranking v1 and v2, sensitivity, coverage) is measured once, in
the deterministic pass, and reported not_applicable for openai; Pod D's provider step is the ranking
explanation, which runs in both passes and must leave the ranks unchanged. The report lists every endpoint it calls and
whether its contract was verified against merged pod code or assumed from PLATFORM_BUILD_PLAN.md §5.3.
Fixture records stay in the database afterwards as auditable simulated records (rows are never deleted).

Gold labels are written by the evaluation pod; notes/platform-evaluation.md explains what each metric
shows and what it does not.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
import uuid
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database.integrity import verify_audit_chain  # noqa: E402
from database.store import AUDIT_HASH_FIELDS, encode  # noqa: E402

EVALUATION = "platform-eval-v1"
FIXTURES = ROOT / "tests" / "fixtures" / "eval"
FIXTURE_FILES = {"sentiment": "sentiment.json", "market_conflicts": "market_conflicts.json",
                 "requests": "requests.json", "ranking": "ranking.json", "coverage": "coverage.json"}
ACTOR = "Synthetic evaluator"   # a human actor: the evaluator stands in for a PM on simulated scopes only
FIXTURE_DATE = "2026-09-01"
PROVIDERS = ("deterministic", "openai")
SENTIMENT_LABELS = ("positive", "negative", "neutral", "mixed")
SCOPE_FLAGS = ("pricing", "business_case", "homologation", "engineering_spec", "supplier")   # server/intake.py SCOPE_FLAGS
RUBRIC_V2 = "customer-priority-v2"
FLAG_SYNONYMS = {"price": "pricing", "prices": "pricing", "discount": "pricing", "type_approval": "homologation",
                 "regulatory": "homologation", "engineering": "engineering_spec", "engineering_specification": "engineering_spec",
                 "engineering_component_spec": "engineering_spec", "component_spec": "engineering_spec",
                 "technical_spec": "engineering_spec", "suppliers": "supplier"}
PERTURBATION = 0.2              # Pod D: one-at-a-time +/-20 % of each weight, renormalised
STABLE_RANK_RANGE = 2           # Pod D: stable = rank range <= 2
PAGE = 100
PLATFORM_PREFIXES = ("/signals", "/markets", "/requests", "/priorities", "/market-data", "/agents",
                     "/capabilities", "/tasks", "/runs", "/threads")
OUTCOME_ACTIONS = ("run.succeeded", "run.failed")
# Link fields that make a new record traceable, per record family. Each entry lists alternative dotted paths.
TRACE_LINKS = {
    "sentiment_scores": (("run_id",), ("subject_id",)),
    "market_conflicts": (("run_id",), ("evidence_ids",), ("requirement_ids",)),
    "request_triage": (("run_id",), ("request_id",), ("factors",)),
    "priority_inputs": (("run_id",), ("version_id", "requirement_id"), ("derivation",)),
}
# Every endpoint the evaluation calls. 'verified' = read in the pod code (core API and Pods A-F);
# 'assumed' = coded against PLATFORM_BUILD_PLAN.md §5.3/§8 only.
ENDPOINTS = {
    "setup": [("GET /health", "verified"), ("GET /workspace", "verified"), ("POST /imports/records", "verified"),
              ("GET /evidence", "verified"), ("POST /pipeline/run", "verified"), ("GET /requirements", "verified"),
              ("GET|PATCH /requirements/{id}", "verified"), ("GET /metrics", "verified"), ("GET /audit", "verified")],
    "sentiment": [("POST /signals/sentiment/score", "verified"), ("GET /signals/sentiment/scores", "verified")],
    "conflicts": [("POST /markets/conflicts/detect", "verified"), ("GET /markets/conflicts", "verified")],
    "requests": [("POST /requests", "verified"), ("POST /requests/classify", "verified"),
                 ("POST /requests/cluster", "verified"), ("POST /requests/triage", "verified"), ("GET /requests", "verified")],
    "ranking_v2": [("POST /priorities/inputs/derive", "verified"), ("GET /priorities/inputs", "verified"),
                   ("POST /priorities/rubric", "verified"), ("GET /priorities/ranking", "verified"),
                   ("POST /priorities/explain", "verified"), ("POST /priorities/sensitivity", "verified")],
    "coverage": [("POST /market-data/coverage", "verified")],
    "run_audit": [("GET /runs", "verified"), ("GET /runs/{id}", "verified")],
}
LIMITATIONS = (
    "Fixtures are small synthetic sets written by the evaluation pod (40 sentences, 3 gold conflicts, 30 requests, "
    "8 ranked requirements, 20 coverage records); gold labels are ours, not BMW's, and results do not establish performance on BMW or real customer data.",
    "Small n: one sentence changes sentiment accuracy by 2.5 points; precision/recall over 3 conflicts move in thirds.",
    "Scenarios exercise the specified rules (thresholds, tension pairs, keyword tables); passing shows the rules are implemented as "
    "specified on designed inputs, not that the rules are the right product decisions.",
    "OpenAI results depend on the configured model and prompt version recorded in each run's method_version; reruns may differ.",
    "Trace coverage checks that link fields are present, not that the linked evidence supports the record.",
    "Clustering is measured downstream of the same provider's classification (clusters form within a topic and exclude "
    "flagged requests), so a topic or flag error also costs cluster pairs.",
    "Ranking v1 and v2, sensitivity and coverage are deterministic code without a provider; they are measured once, "
    "in the deterministic pass. Coverage is checked on two simulated markets only (one dominated, one not).",
    "The evaluator acts as a human PM (PATCH factors, rubric switch) only on its own simulated EVAL-* scopes.",
)


# Metric functions: pure, tested in tests/test_platform_eval.py ----------------------------------------------

def ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def accuracy(gold: Sequence, predicted: Sequence) -> float | None:
    """Share of positions where the prediction equals the gold label (None for an empty set)."""
    if len(gold) != len(predicted):
        raise ValueError("gold and predicted must have the same length")
    return ratio(sum(g == p for g, p in zip(gold, predicted)), len(gold))


def classification_report(gold: Sequence, predicted: Sequence, labels: Sequence | None = None) -> dict:
    """Per-class precision, recall, F1 and their unweighted (macro) mean.

    Classes are `labels` that occur in gold or predictions (all observed values without `labels`). A class
    that occurs on neither side is undefined and left out of the macro mean; a class that occurs on one side
    only scores F1 0, because it is an error, not a missing value. A prediction outside `labels` (e.g. None
    for an item the system did not score) counts as a miss of the gold class.
    """
    if len(gold) != len(predicted):
        raise ValueError("gold and predicted must have the same length")
    observed = set(gold) | set(predicted)
    classes = [label for label in labels if label in observed] if labels is not None else sorted(observed, key=str)
    report = {}
    for label in classes:
        tp = sum(g == label and p == label for g, p in zip(gold, predicted))
        fp = sum(g != label and p == label for g, p in zip(gold, predicted))
        fn = sum(g == label and p != label for g, p in zip(gold, predicted))
        report[label] = {"support": tp + fn, "predicted": tp + fp, "precision": ratio(tp, tp + fp),
                         "recall": ratio(tp, tp + fn), "f1": ratio(2 * tp, 2 * tp + fp + fn) or 0.0}
    return {"classes": report, "macro_f1": ratio(sum(row["f1"] for row in report.values()), len(report))}


def confusion(gold: Sequence, predicted: Sequence) -> dict:
    matrix: dict[str, Counter] = defaultdict(Counter)
    for g, p in zip(gold, predicted):
        matrix[str(g)][str(p)] += 1
    return {g: dict(row) for g, row in sorted(matrix.items())}


def precision_recall(gold: Iterable, predicted: Iterable) -> dict:
    """Set precision/recall/F1. Undefined values are None: precision without predictions, recall without gold."""
    gold, predicted = set(gold), set(predicted)
    tp, fp, fn = len(gold & predicted), len(predicted - gold), len(gold - predicted)
    return {"true_positive": tp, "false_positive": fp, "false_negative": fn, "precision": ratio(tp, tp + fp),
            "recall": ratio(tp, tp + fn), "f1": ratio(2 * tp, 2 * tp + fp + fn)}


def cluster_pairs(assignment: Mapping[Any, Any]) -> set[frozenset]:
    """Unordered pairs of items that share a cluster; a None cluster is a singleton."""
    groups = defaultdict(list)
    for item, cluster in assignment.items():
        if cluster is not None:
            groups[cluster].append(item)
    return {frozenset(pair) for members in groups.values() for pair in combinations(sorted(members, key=str), 2)}


def pairwise_clustering(gold: Mapping[Any, Any], predicted: Mapping[Any, Any]) -> dict:
    """Pairwise precision/recall over gold items: a pair is positive when both items share a cluster.

    Items missing from `predicted` count as singletons (and are listed); predicted items without gold are ignored.
    """
    scoped = {item: predicted.get(item) for item in gold}
    gold_pairs, predicted_pairs = cluster_pairs(gold), cluster_pairs(scoped)
    return {**precision_recall(gold_pairs, predicted_pairs), "items": len(gold), "gold_pairs": len(gold_pairs),
            "predicted_pairs": len(predicted_pairs), "missing_items": sorted(item for item in gold if item not in predicted)}


def order_by_score(scores: Mapping[str, float]) -> list[str]:
    """Items by descending score; ties by item id, so orders are total and reproducible."""
    return sorted(scores, key=lambda item: (-scores[item], item))


def weighted_totals(factors: Mapping[str, Mapping[str, float]], weights: Mapping[str, float]) -> dict[str, float]:
    """The v1 rubric total: sum of factor x weight x 20 (0-100), as server/requirements.score_version computes it."""
    return {item: round(sum(values[name] * weight * 20 for name, weight in weights.items()), 4)
            for item, values in factors.items()}


def perturbed_weights(weights: Mapping[str, float], delta: float = PERTURBATION) -> list[dict[str, float]]:
    """One-at-a-time -delta/+delta change of each weight, renormalised to sum to 1."""
    variants = []
    for name in sorted(weights):
        for sign in (-1, 1):
            changed = {**weights, name: weights[name] * (1 + sign * delta)}
            total = sum(changed.values())
            variants.append({key: value / total for key, value in changed.items()})
    return variants


def rank_ranges(orders: Sequence[Sequence[str]]) -> dict[str, dict]:
    """Best (min) and worst (max) 1-based rank of every item across several orders."""
    seen: dict[str, tuple[int, int]] = {}
    for order in orders:
        for rank, item in enumerate(order, 1):
            low, high = seen.get(item, (rank, rank))
            seen[item] = (min(low, rank), max(high, rank))
    return {item: {"min_rank": low, "max_rank": high, "range": high - low} for item, (low, high) in seen.items()}


def top_k_overlap(gold: Sequence, predicted: Sequence, k: int) -> float | None:
    """Share of the gold top k found anywhere in the predicted top k (order-insensitive)."""
    return ratio(len(set(gold[:k]) & set(predicted[:k])), min(k, len(gold)))


def kendall_tau(first: Sequence, second: Sequence) -> float | None:
    """Kendall's tau-a over items present in both orders (None with fewer than two shared items)."""
    position = {item: index for index, item in enumerate(second)}
    shared = [item for item in first if item in position]
    pairs = list(combinations(shared, 2))
    return ratio(sum(1 if position[a] < position[b] else -1 for a, b in pairs), len(pairs)) if pairs else None


def lookup(record: Any, path: str) -> Any:
    for part in path.split("."):
        if not isinstance(record, dict):
            return None
        record = record.get(part)
    return record


def present(value: Any) -> bool:
    """A link is present when it holds at least one non-empty id (nested lists/dicts are searched)."""
    if isinstance(value, dict):
        return any(present(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(present(item) for item in value)
    return value is not None and value != ""


def link_coverage(records: Sequence[Mapping], required: Sequence[Sequence[str]]) -> dict:
    """Share of records carrying every required link; each requirement lists alternative dotted paths."""
    traced, missing = 0, Counter()
    for record in records:
        gaps = ["|".join(paths) for paths in required if not any(present(lookup(record, path)) for path in paths)]
        traced += not gaps
        missing.update(gaps)
    return {"records": len(records), "traced": traced, "coverage": ratio(traced, len(records)), "missing": dict(missing)}


def run_audit_completeness(run_ids: Sequence[str], events_by_run: Mapping[str, Sequence[Mapping]]) -> dict:
    """Share of runs with an outcome audit event (run.succeeded / run.failed), as server.platform.record_run writes."""
    audited = [run for run in run_ids if any(event.get("action") in OUTCOME_ACTIONS for event in events_by_run.get(run, ()))]
    return {"runs": len(run_ids), "with_outcome_audit": len(audited), "completeness": ratio(len(audited), len(run_ids)),
            "missing": sorted(set(run_ids) - set(audited))[:20]}


def verify_chain(events: Sequence[Mapping]) -> dict:
    """Re-verify the audit hash chain from GET /audit rows with database.integrity's own walk.

    The API decodes the stored JSON columns; store.encode restores the exact stored text before hashing.
    """
    columns = ("sequence", *AUDIT_HASH_FIELDS, "event_hash")
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute(f"CREATE TABLE audit_events ({', '.join(columns)})")
        for event in events:
            row = dict(event)
            for name in ("before_state", "after_state", "metadata"):
                if row.get(name) is not None:
                    row[name] = encode(row[name])
            connection.execute(f"INSERT INTO audit_events VALUES ({','.join('?' * len(columns))})",
                               [row.get(column) for column in columns])
        return verify_audit_chain(connection)


def conflict_key(conflict: Mapping) -> tuple[str, tuple[str, ...]]:
    """(conflict_type, sorted topics): attributes after '/' are ignored, topic order does not matter."""
    topics = {str(topic).split("/")[0] for topic in (conflict.get("topic"), conflict.get("related_topic")) if topic}
    topics |= {str(topic).split("/")[0] for topic in conflict.get("topics", ()) if topic}
    return str(conflict.get("conflict_type")), tuple(sorted(topics))


def key_label(key: tuple[str, tuple[str, ...]]) -> str:
    return f"{key[0]}:{'+'.join(key[1])}"


def score_conflicts(gold: Sequence[Mapping], predicted: Sequence[Mapping], control_topic: str) -> dict:
    """Precision/recall over conflict keys, plus market coverage, recommendation agreement and the control topic.

    Several predicted rows with one key (e.g. one per market pair) count once; their markets are united.
    """
    gold_by_key = {conflict_key(item): item for item in gold}
    predicted_by_key = defaultdict(list)
    for item in predicted:
        predicted_by_key[conflict_key(item)].append(item)
    result = precision_recall(gold_by_key, predicted_by_key)
    matched = [key for key in gold_by_key if key in predicted_by_key]
    markets_ok = [key for key in matched if set(gold_by_key[key]["markets"])
                  <= {market for item in predicted_by_key[key] for market in item.get("markets") or ()}]
    recommendation_ok = [key for key in matched if any(item.get("recommendation") in gold_by_key[key]["acceptable_recommendations"]
                                                       for item in predicted_by_key[key])]
    linked = [item for item in predicted if isinstance(item.get("evidence_ids"), dict)
              and all(item["evidence_ids"].get(market) for market in item.get("markets") or ())]
    return {**result, "predicted_conflicts": len(predicted), "market_coverage": ratio(len(markets_ok), len(matched)),
            "recommendation_agreement": ratio(len(recommendation_ok), len(matched)),
            "evidence_per_market": ratio(len(linked), len(predicted)),
            "control_topic_clean": not any(control_topic in key[1] for key in predicted_by_key),
            "matched": sorted(map(key_label, matched)),
            "false_positive_keys": sorted(key_label(key) for key in predicted_by_key if key not in gold_by_key),
            "false_negative_keys": sorted(key_label(key) for key in gold_by_key if key not in predicted_by_key)}


def normalise_flags(flags: Iterable | None) -> frozenset[str] | None:
    """Scope flags as canonical names (lowercase, '_' separated, known synonyms mapped); None stays None."""
    if flags is None:
        return None
    names = set()
    for flag in flags:
        if isinstance(flag, Mapping):
            flag = flag.get("flag") or flag.get("name") or flag.get("code")
        key = re.sub(r"[^a-z0-9]+", "_", str(flag).lower()).strip("_")
        names.add(FLAG_SYNONYMS.get(key, key))
    return frozenset(names)


def score_scope_flags(gold: Mapping[str, Sequence[str]], predicted: Mapping[str, Iterable | None]) -> dict:
    """Exact flag-set accuracy, binary out-of-scope accuracy and per-flag precision/recall. Missing requests are wrong."""
    ids = sorted(gold)
    expected = {item: frozenset(gold[item]) for item in ids}
    actual = {item: normalise_flags(predicted.get(item)) for item in ids}
    pairs = precision_recall({(item, flag) for item in ids for flag in expected[item]},
                             {(item, flag) for item in ids for flag in actual[item] or ()})
    return {"n": len(ids), "exact_match_accuracy": accuracy([expected[i] for i in ids], [actual[i] for i in ids]),
            "out_of_scope_accuracy": accuracy([bool(expected[i]) for i in ids],
                                              [None if actual[i] is None else bool(actual[i]) for i in ids]),
            "flag_precision": pairs["precision"], "flag_recall": pairs["recall"],
            "per_flag": {flag: precision_recall({i for i in ids if flag in expected[i]}, {i for i in ids if flag in (actual[i] or ())})
                         for flag in SCOPE_FLAGS},
            "unknown_flags": sorted({flag for i in ids for flag in actual[i] or () if flag not in SCOPE_FLAGS}),
            "errors": [i for i in ids if actual[i] != expected[i]]}


def score_topics(gold: Mapping[str, str | None], predicted: Mapping[str, str | None]) -> dict:
    """Topic accuracy over requests with a gold topic (out-of-scope requests have none)."""
    ids = sorted(item for item, topic in gold.items() if topic is not None)
    return {"n": len(ids), "accuracy": accuracy([gold[i] for i in ids], [predicted.get(i) for i in ids]),
            "errors": {i: {"gold": gold[i], "predicted": predicted.get(i)} for i in ids if predicted.get(i) != gold[i]}}


def run_ids_in(value: Any) -> set[str]:
    """Every run id a platform response mentions ('run_id' strings and 'run_ids' lists, at any depth)."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "run_id" and isinstance(item, str):
                found.add(item)
            elif key == "run_ids" and isinstance(item, list):
                found.update(run for run in item if isinstance(run, str))
            else:
                found |= run_ids_in(item)
    elif isinstance(value, list):
        for item in value:
            found |= run_ids_in(item)
    return found


def records_in(payload: Any, *keys: str) -> list[dict]:
    """The first list of objects under one of `keys` (or the payload itself when it is a list)."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in keys:
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, dict)]
    return []


def ranking_order(items: Sequence[Mapping], names: Mapping[str, str]) -> list[str]:
    """Topics in ranking order: by integer `rank` when every item has one, else by descending score."""
    def score(item):
        return next((item[key] for key in ("total", "score", "priority") if isinstance(item.get(key), (int, float))), 0)

    def ident(item):
        return str(item.get("requirement_id") or item.get("id"))

    if items and all(isinstance(item.get("rank"), int) for item in items):
        ordered = sorted(items, key=lambda item: (item["rank"], ident(item)))
    else:
        ordered = sorted(items, key=lambda item: (-score(item), ident(item)))
    return [names.get(ident(item), ident(item)) for item in ordered]


# HTTP layer: the only code that knows endpoint shapes ------------------------------------------------------

class Unavailable(Exception):
    """The endpoint is missing (404/405) or the provider is unavailable (503): the metric is not_available."""


class Failed(Exception):
    """The API answered with another error (or the scenario could not be set up): the metric failed."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail", response.text)
    except (ValueError, AttributeError):
        detail = response.text
    return (detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False))[:300]


class Api:
    """One HTTP client per provider pass. Remembers every platform run id its responses mention."""

    def __init__(self, client: httpx.Client):
        self.client = client
        self.run_ids: set[str] = set()

    def __call__(self, method: str, path: str, **kwargs) -> Any:
        response = self.client.request(method, path, **kwargs)
        if response.status_code in (404, 405):
            raise Unavailable(f"{method} {path} is not available ({response.status_code}: {_detail(response)})")
        if response.status_code == 503:
            raise Unavailable(f"{method} {path}: provider unavailable (503: {_detail(response)})")
        if not response.is_success:
            raise Failed(f"{method} {path} returned {response.status_code}: {_detail(response)}", response.status_code)
        try:
            body = response.json() if response.content else None
        except ValueError:
            raise Failed(f"{method} {path} returned a non-JSON body", response.status_code) from None
        if path.startswith(PLATFORM_PREFIXES):
            self.run_ids |= run_ids_in(body)
        return body


def all_items(api: Api, path: str, **params) -> list[dict]:
    """Every item of a paginated list endpoint ({items, total, limit, offset}); a plain list is returned as is."""
    items: list[dict] = []
    while True:
        page = api("GET", path, params={**params, "limit": PAGE, "offset": len(items)})
        if isinstance(page, list):
            return page
        batch = records_in(page, "items")
        items.extend(batch)
        if not batch or len(items) >= int(page.get("total") or 0):
            return items


def import_records(api: Api, vehicle: str, market: str, title: str, records: Sequence[Mapping]) -> dict:
    """POST /imports/records. Each record is located by its fixture id; gold labels are never sent."""
    rows = [{"content": record["text"], "location": {"fixture_id": record["id"], "row": row}, "observed_at": FIXTURE_DATE,
             "metadata": {"simulated": True, "fixture_id": record["id"],
                          **{key: record[key] for key in ("topic", "sentiment", "record_type", "provenance") if key in record}}}
            for row, record in enumerate(records, 2)]
    return api("POST", "/imports/records", json={
        "vehicle": vehicle, "market": market, "title": f"{title} (simulated)", "kind": "feedback", "actor": ACTOR,
        "reference": f"{EVALUATION}:{vehicle}:{market}", "metadata": {"simulated": True, "evaluation": EVALUATION}, "records": rows})


def fixture_evidence(api: Api, vehicle: str, market: str) -> dict[str, str]:
    """GET /evidence: evidence id -> fixture id for one scope."""
    return {row["id"]: row["location"]["fixture_id"] for row in all_items(api, "/evidence", vehicle=vehicle, market=market)
            if isinstance(row.get("location"), dict) and "fixture_id" in row["location"]}


def run_pipeline(api: Api, vehicle: str, market: str) -> dict:
    """POST /pipeline/run with the deterministic reference provider: scenario setup, not under test."""
    return api("POST", "/pipeline/run", json={"vehicle": vehicle, "market": market, "provider": "deterministic", "actor": ACTOR})


def requirement_rows(api: Api, vehicle: str, market: str) -> list[dict]:
    """GET /requirements: the scope's requirements in v1 priority order (server sorts by priority, then id)."""
    return all_items(api, "/requirements", vehicle=vehicle, market=market)


def requirement_version(api: Api, requirement_id: str) -> dict:
    return api("GET", f"/requirements/{requirement_id}")["current_version"]


def set_factors(api: Api, requirement_id: str, factors: Mapping[str, float]) -> dict:
    """PATCH /requirements/{id}: a PM edit of the 0-5 factors, which rescores the new version."""
    current = api("GET", f"/requirements/{requirement_id}")
    return api("PATCH", f"/requirements/{requirement_id}", json={
        "expected_version_id": current["current_version_id"], "actor": ACTOR, "factors": dict(factors),
        "rationale": "Simulated evaluation ranking case: PM-set factors"})


def requirement_traceability(api: Api, vehicle: str, market: str) -> dict:
    """GET /metrics: the server's own requirement-to-source link coverage for one scope."""
    return api("GET", "/metrics", params={"vehicle": vehicle, "market": market})["traceability"]


def score_sentiment(api: Api, vehicle: str, market: str, provider: str) -> list[dict]:
    """POST /signals/sentiment/score {vehicle, market, provider, subject_type: evidence} (Pod A, verified).

    `items` holds one row per subject (created and reused): {subject_type, subject_id, label, method_version,
    run_id}. If the response carries none, GET /signals/sentiment/scores lists the scope's stored scores.
    """
    body = api("POST", "/signals/sentiment/score", json={"vehicle": vehicle, "market": market, "provider": provider,
                                                          "subject_type": "evidence", "actor": ACTOR})
    return records_in(body, "items") or all_items(api, "/signals/sentiment/scores", vehicle=vehicle, market=market)


def detect_conflicts(api: Api, vehicle: str, provider: str) -> dict:
    """POST /markets/conflicts/detect (Pod B, verified): {items, direction_method_version, warnings, run_id, ...}.

    `items` are exactly the conflicts this detection created or confirmed; markets default to every market
    with data for the vehicle. GET /markets/conflicts is the fallback for a response without items.
    """
    body = api("POST", "/markets/conflicts/detect", json={"vehicle": vehicle, "provider": provider, "actor": ACTOR})
    if not isinstance(body, dict):
        raise Failed("POST /markets/conflicts/detect returned no object")
    if "items" not in body:
        body = {**body, "items": [row for row in all_items(api, "/markets/conflicts", vehicle=vehicle)
                                  if row.get("status") == "open"]}
    return body


def request_payload(vehicle: str, request: Mapping) -> dict:
    return {"vehicle": vehicle, "simulated": True,
            **{key: request[key] for key in ("market", "origin_type", "origin_name", "title", "body", "requested_at")}}


def create_requests(api: Api, vehicle: str, requests: Sequence[Mapping]) -> dict:
    """POST /requests as one batch ({requests, actor}); intake records the keyword classification. Gold is never sent."""
    return api("POST", "/requests", json={"requests": [request_payload(vehicle, request) for request in requests],
                                         "actor": ACTOR})


def classify_requests(api: Api, vehicle: str, provider: str) -> dict:
    """POST /requests/classify {vehicle, provider}: topic, attribute and scope flags for every request in scope."""
    return api("POST", "/requests/classify", json={"vehicle": vehicle, "provider": provider, "actor": ACTOR})


def cluster_requests(api: Api, vehicle: str, provider: str) -> dict:
    """POST /requests/cluster {vehicle, provider}: within vehicle + topic, across markets; flagged requests excluded."""
    return api("POST", "/requests/cluster", json={"vehicle": vehicle, "provider": provider, "actor": ACTOR})


def triage_requests(api: Api, vehicle: str) -> list[dict]:
    """POST /requests/triage {vehicle}: deterministic request-triage-v1 (no provider); returns request summaries."""
    return records_in(api("POST", "/requests/triage", json={"vehicle": vehicle, "actor": ACTOR}), "items")


def list_requests(api: Api, vehicle: str) -> list[dict]:
    return all_items(api, "/requests", vehicle=vehicle)


def derive_priority_inputs(api: Api, vehicle: str, market: str) -> dict:
    """POST /priorities/inputs/derive {vehicle, market} (Pod D, verified): per-requirement summaries plus run_id."""
    return api("POST", "/priorities/inputs/derive", json={"vehicle": vehicle, "market": market, "actor": ACTOR})


def priority_inputs(api: Api, vehicle: str, market: str) -> list[dict]:
    """GET /priorities/inputs (Pod D, verified): the stored priority_inputs rows (run_id, version_id, derivation)."""
    return all_items(api, "/priorities/inputs", vehicle=vehicle, market=market)


def switch_rubric(api: Api, vehicle: str, market: str) -> dict:
    """POST /priorities/rubric (Pod D, verified): the human rubric switch, on the evaluation's own simulated scope only."""
    return api("POST", "/priorities/rubric", json={
        "vehicle": vehicle, "market": market, "rubric_version": RUBRIC_V2, "actor": ACTOR,
        "rationale": "Simulated evaluation scope: measure the v2 ranking on the labelled ranking case"})


def priority_ranking(api: Api, vehicle: str, market: str) -> dict:
    """GET /priorities/ranking?vehicle&market (Pod D, verified): {rubric, items: [{requirement_id, rank, total, ...}]}.

    Deterministic; it takes no provider. Pod D's AI step is POST /priorities/explain.
    """
    body = api("GET", "/priorities/ranking", params={"vehicle": vehicle, "market": market, "limit": 1000})
    items = records_in(body, "items")
    versions = {str(item.get("rubric_version")) for item in items if item.get("rubric_version")}
    rubric = body.get("rubric") if isinstance(body, dict) else None
    if isinstance(rubric, dict) and rubric.get("rubric_version"):
        versions.add(str(rubric["rubric_version"]))
    return {"items": items, "rubric_versions": sorted(versions)}


def explain_ranking(api: Api, vehicle: str, market: str, provider: str) -> dict:
    """POST /priorities/explain {vehicle, market, provider, limit} (Pod D, verified): OpenAI or the labelled template."""
    return api("POST", "/priorities/explain", json={"vehicle": vehicle, "market": market, "provider": provider,
                                                     "limit": 25, "actor": ACTOR})


def priority_sensitivity(api: Api, vehicle: str, market: str) -> dict[str, dict]:
    """POST /priorities/sensitivity (Pod D, verified) -> {results: {requirement_id: {rank, min_rank, max_rank, stable}}}."""
    body = api("POST", "/priorities/sensitivity", json={"vehicle": vehicle, "market": market, "actor": ACTOR})
    results = body.get("results") if isinstance(body, dict) else body
    if isinstance(results, list):
        results = {str(row.get("requirement_id")): row for row in results if isinstance(row, dict)}
    if not isinstance(results, dict) or not results:
        raise Failed("POST /priorities/sensitivity returned no per-requirement results")
    return results


def coverage_report(api: Api, vehicle: str, market: str) -> dict:
    """POST /market-data/coverage {vehicle, market} (Pod E, read in codex/platform-market-data).

    Returns the capability outputs {run_id, method_version, items: [{market, metrics, warnings: [{code, ...}]}]};
    dominance is computed over evidence with metadata.record_type 'customer_feedback', grouped by metadata.provenance.
    """
    body = api("POST", "/market-data/coverage", json={"vehicle": vehicle, "market": market, "actor": ACTOR})
    if not isinstance(body, dict):
        raise Failed("POST /market-data/coverage returned no object")
    return body


def platform_runs(api: Api, vehicle: str) -> list[dict]:
    return all_items(api, "/runs", vehicle=vehicle)


def run_detail(api: Api, run_id: str) -> dict:
    """GET /runs/{id} (Pod F, verified): the run with metrics.llm and its own audit_events."""
    return api("GET", f"/runs/{run_id}")


def audit_events(api: Api, entity_id: str | None = None) -> list[dict]:
    """GET /audit, every page from the start (optionally one entity's events)."""
    events, after = [], 0
    while True:
        params = {"after": after, "limit": 1000, **({"entity_id": entity_id} if entity_id else {})}
        page = api("GET", "/audit", params=params)
        if not page["items"]:
            return events
        events += page["items"]
        after = page["next_after"]


# Scenarios ---------------------------------------------------------------------------------------------------

def measured(**values) -> dict:
    return {"status": "measured", "reason": None, **values}


def outcome(exc: BaseException) -> dict:
    return {"status": "not_available" if isinstance(exc, Unavailable) else "failed", "reason": str(exc)}


def not_applicable(reason: str) -> dict:
    return {"status": "not_applicable", "reason": reason}


def method_provider(method_version: Any) -> str | None:
    """'openai' for 'openai:<model>:<prompt>' method versions, 'deterministic' for any other label, None without one."""
    if not method_version:
        return None
    return "openai" if str(method_version).startswith("openai:") else "deterministic"


def require_provider(method_version: Any, provider: str, where: str) -> str:
    """A result produced by another method is never reported as this provider's."""
    if method_provider(method_version) != provider:
        raise Failed(f"{where} answered with method_version {method_version!r}, not a {provider} method")
    return str(method_version)


@dataclass
class Context:
    """One provider pass: its HTTP client, the scopes it created and the new records it observed."""

    api: Api
    provider: str
    token: str
    vehicles: dict[str, list[str]] = field(default_factory=dict)
    trace: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    skipped: dict[str, str] = field(default_factory=dict)   # side steps that could not run (reported, never hidden)

    def fresh_scope(self, scenario: str, markets: Sequence[str]) -> str:
        vehicle = f"EVAL-{self.token}-{scenario}-{self.provider[0].upper()}"
        for market in markets:
            if self.api("GET", "/workspace", params={"vehicle": vehicle, "market": market})["evidence_count"]:
                raise Failed(f"synthetic scope {vehicle}/{market} already has evidence; rerun with a new token")
        self.vehicles[vehicle] = list(markets)
        return vehicle


def evaluate_sentiment(ctx: Context, fixture: Mapping) -> dict:
    items = fixture["items"]
    markets = sorted({item["market"] for item in items})
    vehicle = ctx.fresh_scope("SEN", markets)
    predicted, versions, mismatched = {}, Counter(), 0
    for market in markets:
        import_records(ctx.api, vehicle, market, "Sentiment sentences", [item for item in items if item["market"] == market])
        fixture_ids = fixture_evidence(ctx.api, vehicle, market)
        for score in score_sentiment(ctx.api, vehicle, market, ctx.provider):
            fixture_id = fixture_ids.get(score.get("subject_id"))
            if fixture_id is None or score.get("subject_type", "evidence") != "evidence":
                continue
            ctx.trace["sentiment_scores"].append(score)
            version = str(score.get("method_version") or "")
            versions[version] += 1
            if version.startswith("openai:") != (ctx.provider == "openai"):
                mismatched += 1     # a result from another method is never scored as this provider's
                continue
            predicted[fixture_id] = score.get("label")
    if not predicted:
        reason = (f"every score carries another method's version {sorted(versions)}" if mismatched
                  else "no sentiment scores were returned for the fixture evidence")
        raise Failed(f"sentiment ({ctx.provider}): {reason}")
    gold = [item["label"] for item in items]
    labels = [predicted.get(item["id"]) for item in items]
    report = classification_report(gold, labels, SENTIMENT_LABELS)
    categories = sorted({category for item in items for category in item["categories"]})
    by_category = {}
    for category in categories:
        chosen = [index for index, item in enumerate(items) if category in item["categories"]]
        by_category[category] = {"n": len(chosen), "accuracy": accuracy([gold[i] for i in chosen], [labels[i] for i in chosen])}
    return {"sentiment": measured(
        n=len(items), scored=len(predicted), accuracy=accuracy(gold, labels), macro_f1=report["macro_f1"],
        per_class=report["classes"], by_category=by_category, confusion=confusion(gold, labels),
        method_versions=dict(versions), provider_mismatch=mismatched,
        errors={item["id"]: {"gold": item["label"], "predicted": predicted.get(item["id"])}
                for item in items if predicted.get(item["id"]) != item["label"]}, vehicle=vehicle)}


def setup_markets(ctx: Context, fixture: Mapping) -> tuple[str, dict[str, list[str]]]:
    """Import each market's evidence and run the reference pipeline; returns the vehicle and v1 topic order per market."""
    markets = fixture["markets"]
    vehicle = ctx.fresh_scope("MKT", markets)
    for market in markets:
        import_records(ctx.api, vehicle, market, "Market evidence", [row for row in fixture["records"] if row["market"] == market])
        run_pipeline(ctx.api, vehicle, market)
    return vehicle, {market: [row["topic"] for row in requirement_rows(ctx.api, vehicle, market)] for market in markets}


def evaluate_conflicts(ctx: Context, fixture: Mapping) -> dict:
    vehicle, ranks = setup_markets(ctx, fixture)
    body = detect_conflicts(ctx.api, vehicle, ctx.provider)
    # Detection rules are deterministic (market-balance-v1); the provider extracts the attribute directions.
    direction_method = require_provider(body.get("direction_method_version"), ctx.provider, "POST /markets/conflicts/detect")
    current = [row for row in records_in(body, "items") if row.get("status", "open") == "open"]
    ctx.trace["market_conflicts"].extend(current)
    return {"conflicts": measured(
        **score_conflicts(fixture["gold_conflicts"], current, fixture["control_topic"]), gold_conflicts=len(fixture["gold_conflicts"]),
        setup_ranks=ranks, setup_matches_design=ranks == fixture["design"]["intended_ranks"],
        recommendations={key_label(conflict_key(row)): row.get("recommendation") for row in current},
        severities={key_label(conflict_key(row)): row.get("severity") for row in current},
        method_version=body.get("method_version"), direction_method_version=direction_method,
        warnings=body.get("warnings") or [], vehicle=vehicle)}


def evaluate_requests(ctx: Context, fixture: Mapping) -> dict:
    requests = fixture["requests"]
    vehicle = ctx.fresh_scope("REQ", sorted({request["market"] for request in requests}))
    create_requests(ctx.api, vehicle, requests)
    results: dict[str, dict] = {}
    classified_by = None
    try:   # topic, attribute and scope flags by the provider under test (intake already applied the keyword baseline)
        classified_by = require_provider(classify_requests(ctx.api, vehicle, ctx.provider).get("method_version"),
                                         ctx.provider, "POST /requests/classify")
    except (Unavailable, Failed) as exc:
        results["scope_flags"] = results["request_topics"] = outcome(exc)
    cluster_method = None
    try:
        cluster_method = require_provider(cluster_requests(ctx.api, vehicle, ctx.provider).get("method_version"),
                                          ctx.provider, "POST /requests/cluster")
    except (Unavailable, Failed) as exc:
        results["clustering"] = outcome(exc)
    try:   # deterministic request-triage-v1: not a metric here, but its records count towards trace coverage
        triaged = triage_requests(ctx.api, vehicle)
        ctx.trace["request_triage"].extend({"run_id": row["triage"].get("run_id"), "request_id": row.get("id"),
                                            "factors": row["triage"].get("factors")}
                                           for row in triaged if isinstance(row.get("triage"), dict))
    except (Unavailable, Failed) as exc:
        ctx.skipped["request_triage"] = str(exc)
    rows = {row.get("title"): row for row in list_requests(ctx.api, vehicle)}
    found = {request["id"]: rows[request["title"]] for request in requests if request["title"] in rows}
    if cluster_method:
        assignment = {item: row.get("cluster_id") for item, row in found.items()}
        results["clustering"] = measured(
            **pairwise_clustering({request["id"]: request["gold"]["cluster"] for request in requests}, assignment),
            predicted_clusters=len({cluster for cluster in assignment.values() if cluster is not None}),
            unclustered=sorted(item for item, cluster in assignment.items() if cluster is None),
            gold_clusters=len({request["gold"]["cluster"] for request in requests}), method_version=cluster_method,
            topic_source=classified_by or "intake keyword baseline (provider classification did not run)", vehicle=vehicle)
    if classified_by:
        results["scope_flags"] = measured(
            **score_scope_flags({r["id"]: r["gold"]["scope_flags"] for r in requests},
                                {item: row.get("scope_flags") for item, row in found.items()}),
            method_version=classified_by, vehicle=vehicle)
        results["request_topics"] = measured(
            **score_topics({r["id"]: r["gold"]["topic"] for r in requests}, {item: row.get("topic") for item, row in found.items()}),
            method_version=classified_by, vehicle=vehicle)
    return results


def evaluate_ranking(ctx: Context, fixture: Mapping) -> dict:
    market, gold = fixture["market"], fixture["gold"]
    expected = [row["topic"] for row in fixture["requirements"]]
    vehicle = ctx.fresh_scope("RNK", [market])
    import_records(ctx.api, vehicle, market, "Ranking case",
                   [{**row, "id": f"K-{row['topic']}"} for row in fixture["requirements"]])
    run_pipeline(ctx.api, vehicle, market)
    ids = {row["topic"]: row["id"] for row in requirement_rows(ctx.api, vehicle, market)}
    if sorted(ids) != sorted(expected):
        raise Failed(f"ranking setup produced requirements for {sorted(ids)}, expected {sorted(expected)}")
    for row in fixture["requirements"]:
        set_factors(ctx.api, ids[row["topic"]], row["factors"])
    names = {requirement_id: topic for topic, requirement_id in ids.items()}
    order = [names[row["id"]] for row in requirement_rows(ctx.api, vehicle, market)]
    deterministic = ctx.provider == "deterministic"
    no_provider = "deterministic code without a provider; measured in the deterministic pass"
    results = {}
    if deterministic:
        versions = {names[requirement_id]: requirement_version(ctx.api, requirement_id) for requirement_id in names}
        factors = {topic: version["factors"] for topic, version in versions.items()}
        weights = versions[order[0]]["score"]["weights"]
        perturbed = [order_by_score(weighted_totals(factors, variant)) for variant in perturbed_weights(weights)]
        ranges = rank_ranges([order, *perturbed])
        results["ranking_v1"] = measured(
            method="customer-priority-v1 order from GET /requirements; stability recomputed locally from the recorded factors "
                   f"with one-at-a-time +/-{PERTURBATION:.0%} weight changes",
            order=order, top3_exact=order[:3] == gold["top3"], top3_overlap=top_k_overlap(gold["top3"], order, 3),
            recomputed_matches_api=order_by_score(weighted_totals(factors, weights)) == order,
            top3_stable=all(ranges[topic]["range"] <= STABLE_RANK_RANGE for topic in gold["stable"]),
            top3_max_rank_range=max(ranges[topic]["range"] for topic in gold["top3"]), rank_ranges=ranges,
            perturbations=len(perturbed), vehicle=vehicle)
    else:
        results["ranking_v1"] = not_applicable(f"customer-priority-v1 is {no_provider}")
    try:   # every pass needs the v2 scope: the explanation under test explains the v2 ranking
        derive_priority_inputs(ctx.api, vehicle, market)
        switch_rubric(ctx.api, vehicle, market)
        ctx.trace["priority_inputs"].extend(priority_inputs(ctx.api, vehicle, market))
        first = priority_ranking(ctx.api, vehicle, market)
        ordered = ranking_order(first["items"], names)
        if not ordered:
            raise Failed("GET /priorities/ranking returned no ranked requirements")
    except (Unavailable, Failed) as exc:
        failed = outcome(exc)
        return {**results, "ranking_v2": failed if deterministic else not_applicable(f"Ranking v2 is {no_provider}"),
                "ranking_explanation": failed,
                "ranking_v2_stability": failed if deterministic else not_applicable(f"Sensitivity is {no_provider}")}
    if deterministic:
        again = ranking_order(priority_ranking(ctx.api, vehicle, market)["items"], names)
        not_measured = sorted({flag for item in first["items"] for flag in item.get("not_measured") or []})
        results["ranking_v2"] = measured(
            order=ordered, top3_exact=ordered[:3] == gold["top3"], top3_overlap=top_k_overlap(gold["top3"], ordered, 3),
            repeat_identical=ordered == again, kendall_tau_vs_v1=kendall_tau(order, ordered),
            rubric_versions=first["rubric_versions"], not_measured_factors=not_measured, vehicle=vehicle)
    else:
        results["ranking_v2"] = not_applicable(f"Ranking v2 is {no_provider}")
    try:   # the provider drafts explanations only; the ranks must be identical before and after
        body = explain_ranking(ctx.api, vehicle, market, ctx.provider)
        method = require_provider(body.get("method_version"), ctx.provider, "POST /priorities/explain")
        explained = records_in(body, "items")
        after = ranking_order(priority_ranking(ctx.api, vehicle, market)["items"], names)
        results["ranking_explanation"] = measured(
            explained_share=ratio(len({row.get("requirement_id") for row in explained}), len(ordered)),
            cites_score_share=ratio(sum(row.get("score_id") in (row.get("cited_ids") or []) for row in explained),
                                    len(explained)),
            ranks_unchanged=after == ordered, method_version=method, ai_generated=body.get("ai_generated"),
            model=body.get("model"), vehicle=vehicle)
    except (Unavailable, Failed) as exc:
        results["ranking_explanation"] = outcome(exc)
    if not deterministic:
        return {**results, "ranking_v2_stability": not_applicable(f"Sensitivity is {no_provider}")}
    try:
        sensitivity = {names.get(key, key): value for key, value in priority_sensitivity(ctx.api, vehicle, market).items()}
        results["ranking_v2_stability"] = measured(
            top3_stable=all(sensitivity.get(topic, {}).get("stable") is True for topic in gold["stable"]),
            top3={topic: sensitivity.get(topic) for topic in gold["top3"]},
            stable_share=ratio(sum(row.get("stable") is True for row in sensitivity.values()), len(sensitivity)), vehicle=vehicle)
    except (Unavailable, Failed) as exc:
        results["ranking_v2_stability"] = outcome(exc)
    return results


def evaluate_coverage(ctx: Context, fixture: Mapping) -> dict:
    """Pod E coverage-v1 on two simulated markets: single-source dominance must be flagged where gold says so."""
    if ctx.provider != "deterministic":
        return {"coverage": not_applicable("Coverage is deterministic code without a provider; measured in the "
                                           "deterministic pass")}
    markets = sorted({row["market"] for row in fixture["records"]})
    vehicle = ctx.fresh_scope("COV", markets)
    for market in markets:
        import_records(ctx.api, vehicle, market, "Coverage case", [row for row in fixture["records"] if row["market"] == market])
    flagged, shares, codes, method = set(), {}, {}, None
    for market in markets:
        body = coverage_report(ctx.api, vehicle, market)
        method = body.get("method_version") or method
        for item in records_in(body, "items"):
            if item.get("market") != market:
                continue
            warnings = [w for w in item.get("warnings") or [] if isinstance(w, dict)]
            codes[market] = sorted({str(w.get("code")) for w in warnings})
            dominance = [w for w in warnings if w.get("code") == "single_source_dominance"]
            if dominance:
                flagged.add(market)
                shares[market] = dominance[0].get("share")
    if not codes:
        raise Failed("POST /market-data/coverage returned no report for the simulated markets")
    gold = set(fixture["gold"]["dominance_markets"])
    return {"coverage": measured(**precision_recall(gold, flagged), dominance_correct=flagged == gold,
                                 flagged_markets=sorted(flagged), gold_markets=sorted(gold), dominant_shares=shares,
                                 warning_codes=codes, method_version=method, vehicle=vehicle)}


def evaluate_trace(ctx: Context) -> dict:
    families = {family: link_coverage(ctx.trace[family], links) for family, links in TRACE_LINKS.items() if ctx.trace.get(family)}
    traced = total = 0
    for vehicle, markets in ctx.vehicles.items():
        for market in markets:
            row = requirement_traceability(ctx.api, vehicle, market)
            traced, total = traced + row["requirements_with_source_links"], total + row["requirements"]
    if total:
        families["requirements"] = {"records": total, "traced": traced, "coverage": ratio(traced, total),
                                    "missing": {"in-scope source link": total - traced} if traced < total else {}}
    records = sum(row["records"] for row in families.values())
    if not records:
        return {"status": "not_available", "reason": "no new records with link fields were observed"}
    return measured(coverage=ratio(sum(row["traced"] for row in families.values()), records), records=records,
                    families=families, families_not_observed=[family for family in TRACE_LINKS if family not in families],
                    skipped=dict(ctx.skipped))


def evaluate_run_audit(ctx: Context) -> dict:
    run_ids, listing = set(ctx.api.run_ids), "GET /runs?vehicle=<scope> plus run ids in responses"
    try:
        for vehicle in ctx.vehicles:
            run_ids |= {row["id"] for row in platform_runs(ctx.api, vehicle) if row.get("id")}
    except Unavailable as exc:
        listing = f"run ids from responses only; {exc}"
    if not run_ids:
        return {"status": "not_available", "reason": f"no platform runs were observed ({listing})"}
    ordered, details, events = sorted(run_ids), [], {}
    for run_id in ordered:
        try:
            detail = run_detail(ctx.api, run_id)
        except Unavailable:
            detail = None
        if isinstance(detail, dict):
            details.append(detail)
        if isinstance(detail, dict) and isinstance(detail.get("audit_events"), list):
            events[run_id] = detail["audit_events"]
        else:
            events[run_id] = audit_events(ctx.api, run_id)
    llm = Counter()
    for row in details:
        usage = (row.get("metrics") or {}).get("llm") if isinstance(row.get("metrics"), dict) else None
        for key in ("calls", "cache_hits", "input_tokens", "output_tokens", "total_tokens"):
            if isinstance(usage, dict) and isinstance(usage.get(key), (int, float)):
                llm[key] += usage[key]
    return measured(**run_audit_completeness(ordered, events), listing=listing, details=len(details),
                    finished=ratio(sum(row.get("status") in ("succeeded", "failed") for row in details), len(details)),
                    statuses=dict(Counter(row.get("status") for row in details)),
                    capabilities=dict(Counter(row.get("capability") for row in details)),
                    method_versions=dict(Counter(row.get("method_version") for row in details)), llm=dict(llm),
                    llm_calls=llm["calls"], llm_total_tokens=llm["total_tokens"])


SCENARIOS: tuple[tuple[str, Callable[[Context, Mapping], dict], tuple[str, ...]], ...] = (
    ("sentiment", evaluate_sentiment, ("sentiment",)),
    ("market_conflicts", evaluate_conflicts, ("conflicts",)),
    ("requests", evaluate_requests, ("clustering", "scope_flags", "request_topics")),
    ("ranking", evaluate_ranking, ("ranking_v1", "ranking_v2", "ranking_explanation", "ranking_v2_stability")),
    ("coverage", evaluate_coverage, ("coverage",)),
)


def guarded(groups: Sequence[str], function: Callable[..., dict], *args) -> dict:
    """Run one scenario; an unavailable endpoint/provider or an API error marks all its metrics, never aborts."""
    try:
        return function(*args)
    except (Unavailable, Failed) as exc:
        return {group: outcome(exc) for group in groups}
    except httpx.TransportError as exc:
        return {group: {"status": "failed", "reason": f"transport error: {exc!r}"[:300]} for group in groups}


def load_fixtures(directory: Path = FIXTURES) -> dict[str, dict]:
    return {name: json.loads((directory / filename).read_text(encoding="utf-8")) for name, filename in FIXTURE_FILES.items()}


def fixture_summary(directory: Path = FIXTURES) -> dict:
    summary = {}
    for name, filename in FIXTURE_FILES.items():
        raw = (directory / filename).read_bytes()
        data = json.loads(raw)
        records = next(len(data[key]) for key in ("items", "records", "requests", "requirements") if key in data)
        summary[name] = {"fixture": data["fixture"], "records": records, "sha256": hashlib.sha256(raw).hexdigest()}
    return summary


def evaluate(client: httpx.Client, providers: Sequence[str] = PROVIDERS, token: str | None = None) -> dict:
    started, started_at = time.perf_counter(), datetime.now(timezone.utc).isoformat(timespec="seconds")
    health = Api(client)("GET", "/health")
    if not isinstance(health, dict) or health.get("status") != "ok":
        raise Failed(f"API health check failed: {health}")
    fixtures, token = load_fixtures(), token or uuid.uuid4().hex[:8].upper()
    metrics: dict[str, dict] = defaultdict(dict)
    scopes = {}
    for provider in providers:
        ctx = Context(Api(client), provider, token)
        for name, scenario, groups in SCENARIOS:
            for group, result in guarded(groups, scenario, ctx, fixtures[name]).items():
                metrics[group][provider] = result
        for group, check in (("trace_coverage", evaluate_trace), ("run_audit", evaluate_run_audit)):
            metrics[group][provider] = guarded((group,), lambda check=check, group=group: {group: check(ctx)})[group]
        scopes[provider] = ctx.vehicles
    chain = guarded(("audit_chain",), lambda: {"audit_chain": measured(**verify_chain(audit_events(Api(client))))})["audit_chain"]
    measured_explanations = [metrics["ranking_explanation"][p] for p in providers
                             if metrics["ranking_explanation"].get(p, {}).get("status") == "measured"]
    comparison = {"ranks_unchanged_by_every_explanation": all(row["ranks_unchanged"] for row in measured_explanations)
                  if measured_explanations else None}
    return {"evaluation": EVALUATION, "simulated": True,
            "description": "Labelled synthetic scenarios measured through the public API; not a BMW validation.",
            "base_url": str(client.base_url), "token": token, "providers": list(providers), "started_at": started_at,
            "elapsed_seconds": round(time.perf_counter() - started, 2), "fixtures": fixture_summary(), "scopes": scopes,
            "metrics": dict(metrics), "comparison": comparison, "audit_chain": chain,
            "endpoints": {group: [{"endpoint": endpoint, "contract": status} for endpoint, status in calls]
                          for group, calls in ENDPOINTS.items()},
            "limitations": list(LIMITATIONS)}


# Reporting ---------------------------------------------------------------------------------------------------

ROWS = (
    ("Sentiment accuracy (40 sentences)", "sentiment", "accuracy"),
    ("Sentiment macro-F1", "sentiment", "macro_f1"),
    ("Conflict precision (3 gold conflicts)", "conflicts", "precision"),
    ("Conflict recall", "conflicts", "recall"),
    ("Conflict markets covered", "conflicts", "market_coverage"),
    ("Control topic without conflict", "conflicts", "control_topic_clean"),
    ("Conflict scenario ranks as designed", "conflicts", "setup_matches_design"),
    ("Clustering pairwise precision (30 requests)", "clustering", "precision"),
    ("Clustering pairwise recall", "clustering", "recall"),
    ("Scope flags exact match", "scope_flags", "exact_match_accuracy"),
    ("Out-of-scope detection accuracy", "scope_flags", "out_of_scope_accuracy"),
    ("Request topic accuracy", "request_topics", "accuracy"),
    ("Ranking v1 top-3 exact (deterministic code)", "ranking_v1", "top3_exact"),
    ("Ranking v1 top-3 stable (+/-20% weights)", "ranking_v1", "top3_stable"),
    ("Ranking v2 top-3 exact", "ranking_v2", "top3_exact"),
    ("Ranking v2 repeat identical", "ranking_v2", "repeat_identical"),
    ("Ranking explanation covers every requirement", "ranking_explanation", "explained_share"),
    ("Ranking unchanged after explanation", "ranking_explanation", "ranks_unchanged"),
    ("Ranking v2 top-3 stable (sensitivity)", "ranking_v2_stability", "top3_stable"),
    ("Coverage dominance flags as gold (2 markets)", "coverage", "dominance_correct"),
    ("Trace coverage (new records)", "trace_coverage", "coverage"),
    ("Runs with outcome audit event", "run_audit", "completeness"),
    ("OpenAI calls recorded in runs", "run_audit", "llm_calls"),
    ("OpenAI tokens recorded in runs", "run_audit", "llm_total_tokens"),
)
STATUS_TEXT = {"not_available": "n/a", "failed": "failed", "not_applicable": "not applicable"}


def format_value(value: Any) -> str:
    if value is None:
        return "undefined"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def cell_detail(key: str, result: Mapping) -> str:
    """Counts behind a ratio, so small-n results are read as counts, not as precise rates."""
    tp = result.get("true_positive")
    if key == "precision" and tp is not None:
        return f" ({tp}/{tp + result['false_positive']})"
    if key == "recall" and tp is not None:
        return f" ({tp}/{tp + result['false_negative']})"
    if key == "accuracy" and "scored" in result:
        return f" ({result['scored']}/{result['n']} scored)"
    if key in ("accuracy", "exact_match_accuracy") and "errors" in result and result.get("n"):
        return f" ({result['n'] - len(result['errors'])}/{result['n']})"
    if key == "completeness":
        return f" ({result['with_outcome_audit']}/{result['runs']})"
    if key == "coverage" and "families" in result:
        return f" ({result['records']} records: {', '.join(sorted(result['families']))})"
    return ""


def render_markdown(report: Mapping) -> str:
    providers = report["providers"]
    lines = [f"| Metric | {' | '.join(providers)} |", "| --- |" + " --- |" * len(providers)]
    notes: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for label, group, key in ROWS:
        cells = []
        for provider in providers:
            result = report["metrics"].get(group, {}).get(provider, {"status": "not_available", "reason": "not run"})
            if result["status"] == "measured":
                cells.append(format_value(result.get(key)) + cell_detail(key, result))
            else:
                cells.append(STATUS_TEXT.get(result["status"], result["status"]))
                bucket = notes["Not applicable" if result["status"] == "not_applicable" else "Not measured"]
                if (f"{group} ({provider})", result["reason"]) not in bucket:
                    bucket.append((f"{group} ({provider})", result["reason"]))
        lines.append(f"| {label} | {' | '.join(cells)} |")
    chain = report["audit_chain"]
    lines.append("")
    for name, value in report.get("comparison", {}).items():
        if value is not None:
            lines.append(f"{name.replace('_', ' ').capitalize()}: {format_value(value)}.")
    if chain["status"] == "measured":
        lines.append(f"Audit hash chain: {'verified' if chain['ok'] else 'BROKEN at ' + str(chain.get('broken_at'))} "
                     f"({chain['events']} events).")
    else:
        lines.append(f"Audit hash chain: {STATUS_TEXT.get(chain['status'], chain['status'])} ({chain['reason']}).")
    for heading in ("Not measured", "Not applicable"):
        if notes.get(heading):
            lines += ["", f"{heading}:"] + [f"- {where}: {reason}" for where, reason in notes[heading]]
    lines += ["", f"Synthetic fixtures ({EVALUATION}, token {report['token']}); gold labels written by the evaluation pod. "
              "See notes/platform-evaluation.md for what these numbers do not show."]
    return "\n".join(lines)


def complete(report: Mapping) -> bool:
    statuses = [result["status"] for group in report["metrics"].values() for result in group.values()]
    return all(status in ("measured", "not_applicable") for status in statuses) and report["audit_chain"].get("ok") is True


def parse_providers(value: str) -> tuple[str, ...]:
    names = tuple(dict.fromkeys(name.strip() for name in value.split(",") if name.strip()))
    if not names or any(name not in PROVIDERS for name in names):
        raise argparse.ArgumentTypeError(f"providers must be a comma-separated subset of {', '.join(PROVIDERS)}")
    return names


def main(argv: Sequence[str] | None = None, transport: httpx.BaseTransport | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL (default: local Compose API)")
    parser.add_argument("--providers", type=parse_providers, default=PROVIDERS, help="comma-separated: deterministic,openai")
    parser.add_argument("--json-out", type=Path, help="write the JSON report here")
    parser.add_argument("--markdown-out", type=Path, help="write the Markdown table here")
    parser.add_argument("--timeout", type=float, default=600, help="seconds per HTTP request (OpenAI runs can be slow)")
    parser.add_argument("--strict", action="store_true", help="exit 1 unless every metric was measured and the audit chain verifies")
    args = parser.parse_args(argv)
    try:
        with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=args.timeout, follow_redirects=False,
                          transport=transport) as client:
            report = evaluate(client, args.providers)
    except (httpx.HTTPError, Unavailable, Failed) as exc:
        print(f"Evaluation could not start: API at {args.base_url} is not usable ({exc!r})", file=sys.stderr)
        return 2
    text, markdown = json.dumps(report, indent=2, ensure_ascii=False), render_markdown(report)
    if args.json_out:
        args.json_out.write_text(text + "\n", encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.write_text(markdown + "\n", encoding="utf-8")
    print(markdown if args.json_out or args.markdown_out else f"{text}\n\n{markdown}")
    return 1 if args.strict and not complete(report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
