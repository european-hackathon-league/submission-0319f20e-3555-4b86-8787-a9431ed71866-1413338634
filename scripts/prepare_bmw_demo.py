"""Prepare and check a disposable G60 / US presentation database.

Run against an isolated API and database copy. Original BMW files and snapshots stay
local; this script commits only the proposed wording and a synthetic update record.
"""

import argparse
import json
import urllib.error
import urllib.request

from database.snapshot import create_snapshot

HERO_KEY = "REQ-G60-US-001"
ACTOR = "System:reference"
SCOPE = {"vehicle": "G60", "market": "US"}
PROPOSALS = {
    HERO_KEY: {
        "title": "Enable confident public-charging trip planning for US drivers",
        "customer_need": (
            "Selected G60 / US feedback describes difficulty finding public chargers and uncertainty "
            "about availability and connector compatibility. Positive charging experiences also exist. "
            "The undated sample does not establish prevalence."
        ),
        "statement": (
            "For the G60 successor in the US, help drivers identify a compatible, available public "
            "charger and add it to a planned trip in the vehicle interface. This integrated journey "
            "is a PM solution hypothesis for validation, not a claim stated end to end by one source."
        ),
        "acceptance_criteria": [{
            "metric": "Success finding a compatible, available public charger and adding it to a route in a moderated US trip-planning test",
            "target": 80,
            "unit": "% of participants",
            "basis": "PM assumption",
            "source_ids": [],
        }],
        "assumptions": [
            "BMW navigation integration and the first-time driver journey are PM synthesis requiring validation.",
            "Availability and connector data access must be validated with the responsible system owner.",
            "The selected feedback is undated and cannot estimate market prevalence.",
        ],
    },
    "REQ-G60-US-008": {
        "title": "Preserve valued handling feel for US drivers",
        "customer_need": "Some G60 / US feedback explicitly praises handling and driving feel.",
        "statement": (
            "Preserve the handling feel that drivers value while planning the G60 successor. "
            "Treat this as a positive attribute to protect, not a defect to repair."
        ),
        "acceptance_criteria": [{
            "metric": "Handling-feel preference in a blinded successor-versus-G60 customer evaluation",
            "target": "No material decline",
            "basis": "PM assumption",
            "source_ids": [],
        }],
        "assumptions": ["The evaluation protocol and threshold require PM and research-owner agreement."],
    },
    "REQ-G60-US-010": {
        "title": "Preserve valued vehicle design appeal",
        "customer_need": "Positive design feedback is a preserve signal, subject to source review.",
        "statement": "Protect the vehicle-design attributes praised in G60 / US feedback when defining the successor.",
        "acceptance_criteria": [{
            "metric": "Design appeal in a successor-versus-G60 customer evaluation",
            "target": "No material decline",
            "basis": "PM assumption",
            "source_ids": [],
        }],
        "assumptions": ["The exact design attributes and evaluation threshold need PM source review."],
    },
}


def request(base: str, method: str, path: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base.rstrip("/") + path, data=body, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:500]
        raise RuntimeError(f"{method} {path}: HTTP {exc.code}: {detail}") from exc


def by_key(base: str, key: str) -> dict:
    rows = request(base, "GET", "/requirements?vehicle=G60&market=US&limit=30")["items"]
    matches = [row for row in rows if row["key"] == key]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one {key}; found {len(matches)}")
    return request(base, "GET", f"/requirements/{matches[0]['id']}")


def prepare(base: str) -> None:
    for key, content in PROPOSALS.items():
        detail = by_key(base, key)
        if detail["approved_version_id"]:
            raise RuntimeError(f"{key} has an approved version; use an unused database copy")
        current = detail["current_version"]
        if all(current[field] == value for field, value in content.items()):
            print(f"{key}: already prepared")
            continue
        if current["version"] != 1:
            raise RuntimeError(f"{key} has an unexpected edit; use an unused database copy")
        edited = request(base, "PATCH", f"/requirements/{detail['id']}", {
            "expected_version_id": current["id"], "actor": ACTOR,
            "rationale": "Presentation blocker: source-checked proposal with explicit PM assumptions",
            **content,
        })
        if edited["current_version"]["score"]["total"] != current["score"]["total"]:
            raise RuntimeError(f"{key}: unchanged scoring factors produced a different score")
        print(f"{key}: prepared version {edited['current_version']['version']}")
    snapshot = create_snapshot(label="bmw-predecision")
    print(f"Pre-decision snapshot: {snapshot}")


def simulate_update(base: str) -> None:
    hero = by_key(base, HERO_KEY)
    if not hero["approved_version_id"]:
        raise RuntimeError("Approve the exact hero version and score as a PM before importing an update")
    baseline = hero["approved_version_id"]
    request(base, "POST", "/imports/records", {
        **SCOPE, "title": "Simulated charging update for demonstration",
        "reference": "simulated-g60-us-charging-update-v1", "kind": "feedback", "actor": ACTOR,
        "metadata": {"simulated": True, "usage": "presentation-only"},
        "records": [{
            "content": "Simulated: A US driver found a compatible public charger, but the route did not show current availability.",
            "location": {"synthetic_record": "charging-update-v1"},
            "metadata": {"topic": "charging", "sentiment": "problem", "simulated": True,
                         "provenance": "simulated-demo-v1"},
        }],
    })
    result = request(base, "POST", "/updates", {**SCOPE, "provider": "deterministic", "actor": ACTOR})
    hero_after = by_key(base, HERO_KEY)
    reviews = request(base, "GET", "/reviews?vehicle=G60&market=US&status=open")
    if result["generation"]["updated"] != [hero["id"]]:
        raise RuntimeError("Update regenerated a requirement outside the charging proposal")
    if hero_after["approved_version_id"] != baseline:
        raise RuntimeError("Update changed the approved hero baseline")
    if {item["requirement_id"] for item in reviews} != {hero["id"]}:
        raise RuntimeError("Update did not leave exactly the charging requirement needing review")
    print(f"Update reviewed: analysis={result['analysis']['id']} reviews={len(reviews)}")
    snapshot = create_snapshot(label="bmw-after-update")
    print(f"Post-update snapshot: {snapshot}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "simulate-update"))
    parser.add_argument("--api-url", default="http://127.0.0.1:18200")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.api_url)
    else:
        simulate_update(args.api_url)


if __name__ == "__main__":
    main()
