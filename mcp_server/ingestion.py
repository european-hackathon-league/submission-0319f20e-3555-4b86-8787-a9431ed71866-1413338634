"""Explicit selection of cached web snapshots via Jakob's published API contract."""

import copy

from mcp_server.backend_client import BackendClient
from mcp_server.cache import FileCache
from mcp_server.errors import EvidenceError
from mcp_server.integrity import valid_candidate


def import_candidate(cache: FileCache, backend: BackendClient, candidate_id: str,
                     actor: str, rationale: str, selection_confirmed: bool) -> dict:
    if selection_confirmed is not True or not 1 <= len(actor.strip()) <= 200 or not 1 <= len(rationale.strip()) <= 2000:
        raise EvidenceError("SELECTION_REQUIRED", "Explicit selection, caller identity, and a selection rationale are required.")
    candidate = next((copy.deepcopy(c) for c in cache.candidates() if c.get("candidate_id") == candidate_id), None)
    if candidate is None:
        raise EvidenceError("CANDIDATE_NOT_FOUND", "Select a candidate returned by fetch_web_source in this local cache.")
    if (candidate.get("content_status") != "fetched" or not isinstance(candidate.get("content"), str)
            or not candidate["content"].strip() or candidate.get("review_status") != "unreviewed"
            or candidate.get("persisted") is not False):
        raise EvidenceError("FETCH_REQUIRED", "Fetch the selected source first; search leads cannot be imported.")
    # Reject a damaged cache instead of silently losing or altering provenance.
    if not valid_candidate(candidate):
        raise EvidenceError("INVALID_CANDIDATE", "The cached snapshot failed provenance validation; fetch the source again.")
    if len(candidate["canonical_url"]) > 2000:
        raise EvidenceError("IMPORT_CONTRACT_LIMIT", "The backend supports source URLs up to 2000 characters.")
    # The record metadata participates in the backend snapshot hash; changing only
    # source metadata would not preserve a distinct version of this evidence.
    record_metadata = {"record_type": "document_context", "source_type": "web", "snapshot": True,
                       "review_status": "unreviewed", "web_evidence": candidate}
    payload = {
        "title": candidate["title"][:200], "kind": "web", "reference": candidate["canonical_url"],
        "vehicle": candidate["vehicle"], "market": candidate["market"], "actor": actor.strip(),
        "metadata": {"web_evidence": candidate, "selection": {"actor": actor.strip(), "rationale": rationale.strip()},
                     "review_status": "unreviewed"},
        "records": [{"content": candidate["content"], "location": {"url": candidate["canonical_url"],
                     "text_offset": 0, "text_offset_basis": "returned_exa_text"}, "metadata": record_metadata,
                     "observed_at": None, "vehicle": candidate["vehicle"], "market": candidate["market"]}],
    }
    result = backend.import_records(payload)
    try:
        saved = backend.get_source(result["source_id"])
    except EvidenceError:
        return {**result, "persisted": True, "review_status": "unreviewed", "provenance_verified": False,
                "warnings": ["Backend confirmed import, but provenance readback failed. Inspect this source before use."]}
    if saved.get("metadata", {}).get("web_evidence") != candidate:
        raise EvidenceError("PROVENANCE_MISMATCH", "Backend confirmed import but did not return the complete provenance; inspect the source before use.")
    return {**result, "candidate_id": candidate_id, "persisted": True,
            "review_status": "unreviewed", "provenance_verified": True,
            "warnings": ["Import preserves an unreviewed snapshot; it does not approve evidence or requirements.",
                         "Caller identity is supplied, not authenticated by the current backend.",
                         "A new import creates backend source.imported history; the API does not return an audit event ID."
                         if not result["deduplicated"] else
                         "Existing snapshot reused; its original selection and audit history remain unchanged."]}
