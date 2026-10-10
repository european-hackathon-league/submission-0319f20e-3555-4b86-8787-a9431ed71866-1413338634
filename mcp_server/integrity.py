import json

from mcp_server.errors import EvidenceError
from mcp_server.models import canonicalize_url, digest


def valid_candidate(candidate) -> bool:
    """Check cached snapshot consistency; hashes do not authenticate the publisher."""
    try:
        if not isinstance(candidate, dict):
            return False
        identity = {key: value for key, value in candidate.items() if key != "candidate_id"}
        valid = (
            candidate["candidate_id"] == "exa:" + digest(json.dumps(identity, sort_keys=True, allow_nan=False))
            and digest(candidate["supporting_excerpt"]) == candidate["excerpt_hash"]
            and canonicalize_url(candidate["canonical_url"]) == candidate["canonical_url"]
            and digest(candidate["canonical_url"]) == candidate["url_hash"]
            and candidate["provider"] == "exa"
            and candidate["persisted"] is False
            and candidate["review_status"] == "unreviewed"
        )
        if candidate.get("content_status") == "fetched":
            valid = valid and isinstance(candidate["content"], str) and digest(candidate["content"]) == candidate["content_hash"]
        return valid
    except (KeyError, TypeError, ValueError, AttributeError, EvidenceError):
        return False
