"""Call POST /tasks/run-due on the API every SCHEDULER_INTERVAL_SECONDS (default 900).

Runs as the optional Compose `scheduler` profile (off by default) or by hand. Standard library only, so it
runs in the API image. Repeated or overlapping calls are safe: the API claims each due task with a
revision-guarded update, recovers stale running tasks and records every execution as runs and audit events.

    python scripts/run_scheduler.py           # loop
    python scripts/run_scheduler.py --once    # one call; exit code 1 if the API call failed
"""

import argparse
import json
import logging
import math
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_INTERVAL_SECONDS = 900
MIN_INTERVAL_SECONDS = 10
REQUEST_TIMEOUT_SECONDS = 900  # one call may run several capabilities (including model calls)
ACTOR = "system:scheduler"
logger = logging.getLogger("scheduler")


def interval_seconds(raw: str | None = None) -> float:
    raw = os.getenv("SCHEDULER_INTERVAL_SECONDS", str(DEFAULT_INTERVAL_SECONDS)) if raw is None else raw
    try:
        seconds = float(raw)
    except ValueError:
        seconds = math.nan
    if not math.isfinite(seconds) or seconds < MIN_INTERVAL_SECONDS:
        raise ValueError(f"SCHEDULER_INTERVAL_SECONDS must be a finite number of seconds >= {MIN_INTERVAL_SECONDS}")
    return seconds


def run_once(base_url: str, *, limit: int = 10, opener=urlopen) -> dict:
    request = Request(f"{base_url.rstrip('/')}/tasks/run-due", method="POST",
                      data=json.dumps({"actor": ACTOR, "limit": limit}).encode(),
                      headers={"Content-Type": "application/json"})
    with opener(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        result = json.loads(response.read())
    if not isinstance(result, dict) or "executed" not in result:
        raise ValueError("API returned an unexpected run-due response")
    return result


def summary(result: dict) -> str:
    executed = ", ".join(f"{item['task_id']}={item['status']}" for item in result["executed"]) or "none"
    return (f"run-due at {result.get('now')}: executed {result['count']} ({executed}); "
            f"skipped {len(result.get('skipped', []))}; recovered {len(result.get('recovered', []))}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--once", action="store_true", help="call run-due once and exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
    interval = interval_seconds()
    while True:
        try:
            logger.info(summary(run_once(base_url)))
            failed = False
        except HTTPError as exc:
            logger.error("run-due failed with HTTP %s", exc.code)
            failed = True
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            logger.error("run-due failed: %s", type(exc).__name__)
            failed = True
        if args.once:
            return 1 if failed else 0
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
