"""Conservative quotation checks shared by AI analysis and persisted requirements."""
from __future__ import annotations

import re
from collections.abc import Iterable

_DESIRED_OUTCOME = re.compile(
    r"\b(target|goal|shall|must|require\w*|want\w*|wish\w*|need\w*|should)\b",
    re.I,
)
_PRESERVATION_REQUEST = re.compile(
    r"(?:^|:)\s*(?:please\s+)?(?:preserve|maintain|retain|keep)\b", re.I,
)
# Keep decimal points intact; sentence punctuation and independent semicolon
# clauses separate observed measurements from unrelated wishes. Commas between
# digits stay intact too. Split coordinated clauses with their own subject/verb,
# without separating desired lists such as "need 80% comfort and 90% quietness".
_BOUNDARY = re.compile(
    r"[!?;\n]+|(?<!\d)[.,]|[.,](?!\d)|"
    r"\b(?:and|but|yet|whereas|while)\s+(?="
    r"(?:i|we|they|customers?)\b|"
    r"(?:\w+\s+){0,4}(?:is|are|was|were|has|have|had|equals|measured|recorded|observed|reported)\b)",
    re.I,
)


def target_supported(target: str, source_texts: Iterable[str]) -> bool:
    """Require a complete quote in one source and local desired-outcome wording.

    Full sentences and passages keep their punctuation. A quoted explanation may
    follow a desired outcome, but every quoted numeric portion must belong to a
    desired-outcome sentence/clause, rather than a separate observed measurement.
    This textual check does not establish the target's suitability for a PM.
    """
    parts = target.strip().casefold().split()
    if not parts:
        return False
    # Numeric quotes cannot match only part of a decimal value. Other quotes
    # retain the existing whole-word boundary rule.
    left = r"(?<![\w.,])" if parts[0][0].isdigit() else r"(?<!\w)"
    right = r"(?!\w|[.,]\d)" if parts[-1][-1].isdigit() else r"(?!\w)"
    quote = re.compile(left + r"\s+".join(re.escape(part) for part in parts) + right)
    for source in source_texts:
        text = source.casefold()
        segments, start = [], 0
        for boundary in _BOUNDARY.finditer(text):
            segments.append((start, boundary.end()))
            start = boundary.end()
        segments.append((start, len(text)))
        for match in quote.finditer(text):
            desired_found, unsupported_number = False, False
            for start, end in segments:
                if start >= match.end() or end <= match.start():
                    continue
                segment = text[start:end]
                desired = bool(_DESIRED_OUTCOME.search(segment) or _PRESERVATION_REQUEST.search(segment))
                desired_found |= desired
                quoted_part = text[max(start, match.start()):min(end, match.end())]
                if re.search(r"\d", quoted_part) and not desired:
                    unsupported_number = True
                    break
            if desired_found and not unsupported_number:
                return True
    return False
