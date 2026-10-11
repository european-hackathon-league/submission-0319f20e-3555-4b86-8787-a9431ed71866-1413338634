"""The web workspace's topic options mirror the shared taxonomy (§5.5) instead of inventing a parallel list."""

import re
from pathlib import Path

from server.analysis_engine import TOPICS

PLATFORM_TYPES = Path(__file__).resolve().parents[1] / "web" / "lib" / "platform-types.ts"


def test_web_topic_keys_match_server_taxonomy():
    source = PLATFORM_TYPES.read_text(encoding="utf-8")
    block = re.search(r"export const TOPICS = \[(.*?)\] as const;", source, re.S)
    assert block, "web/lib/platform-types.ts must define TOPICS"
    keys = re.findall(r'\[\s*"([a-z-]+)",\s*"[^"]+"\s*\]', block.group(1))
    assert keys == list(TOPICS)
