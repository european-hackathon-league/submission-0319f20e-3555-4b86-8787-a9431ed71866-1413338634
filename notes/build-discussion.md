# Proposed direction for discussion

This is a proposal based on the archived brief, not a committed implementation plan.

Build a **product requirements workbench** that helps a PM decide what the next BMW should offer and explain every decision. The strongest demo follows a requirement from original evidence through a contested decision and a later revision.

## A focused demonstration

Start with the 5 Series / G60 in the US. That slice has substantial feedback, US study results, equipment documentation, and model-group sales context. Keep market and derivative as explicit dimensions so other slices can be added. An alternative is the F70 in Europe, particularly GB, for a tighter controls/usability story.

1. Select vehicle, market, and the successor's planning horizon.
2. Show an evidence overview with genuine coverage, duplicate handling, positive attributes, pain points, and contradictions.
3. Propose a small set of customer requirements. Each links to exact workbook sheet/row/ID or document page and separates evidence, interpretation, and future assumptions.
4. Open a requirement to inspect support, counter-evidence, confidence limits, and scoring factors. Changing weights should visibly change the ranking with an explanation.
5. Approve, modify, reject, postpone, or challenge it, with a reason. Export the structured requirement list.
6. Introduce a clearly labeled new evidence batch or changed planning assumption. Show which requirements need reconsideration and reconstruct the before/after history.

The compelling moment is a PM challenging an attractive recommendation and seeing why it is weak, how the evidence changes the proposal, and exactly what decision was recorded.

## What makes it credible

- Keep immutable source references and version the findings, requirements, scoring configuration, and decisions.
- Deduplicate evidence counts by feedback ID while preserving each classification row. State denominators and sampling limitations.
- Separate priority from evidence confidence. High-impact but weakly supported ideas should be marked for research, not disguised as certain recommendations.
- Preserve favorable attributes as explicit constraints or requirements so solving complaints does not erase what customers value.
- Treat SMART targets as proposed values unless a source supports them. Make the PM's acceptance criteria and assumptions explicit.
- Use an auditable scoring function with visible factors, weights, and contributions. The team defines the method; the challenge specifies no official weights.
- Add a small, carefully sourced external research layer once the core evidence chain works. Archive web evidence with retrieval times and model/market relevance.
- Demonstrate mandatory human decision gates and a complete history of meaningful edits, rescoring, and status changes.

## Choices to settle together

- G60/US for broader evidence coverage or F70/Europe for a tighter usability focus?
- Put the strongest effort into evidence synthesis, conflicting-signal review, or continuous change and decision history?
- How much hackathon time and team capacity remain, and what stack does the team already know?

The first implementation milestone should be one real requirement with source citations, an explainable score, a human decision, and a replayable change history.
