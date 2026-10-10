# BMW challenge: authoritative requirements

Sources: [BMW channel](https://discord.com/channels/1553151744047976549/1553306479019429939), the two-page `BMW_Hackathon_Briefing_Short.pdf`, the four-slide `261010_BMW_Product_Management_Key_Note.pptx`, and seven channel images. Originals and searchable derivatives are in `archive/`; the full channel transcript is retained separately.

## Mission

Help product managers derive, explain, and prioritize customer-facing requirements for the successor to a BMW 1 Series, 5 Series, or 7 Series. Focus on Europe, China, the United States, or a useful subset. Think three to five years ahead; explicitly distinguish current evidence from forward-looking assumptions.

Demonstrate at least one derivative in one market, while keeping the approach adaptable. Teams may choose which capabilities to develop most deeply and are free to choose architecture, scoring logic, and user experience.

The application should:

1. Ingest heterogeneous BMW data and enrich it with structured web knowledge.
2. Extract recurring complaints, unmet needs, competitor advantages, and market trends with source links.
3. Derive clear, actionable, realistic customer requirements.
4. Prioritize them using an explainable method.
5. Let the PM approve, reject, edit, or challenge requirements, evidence, and rationale.
6. Record actions, changes, and relevant access events in a chronological audit trail.

## Scope

In scope: features and equipment, comfort, space, usability, infotainment and digital services, design and quality perception, driving experience, customer experience of range and charging, variants and packages.

Out of scope: regulatory/homologation requirements, technical component specifications and engineering architecture, supplier topics, pricing, business cases, and detailed cost calculations. Rough cost or effort may be a prioritization factor.

The automotive lifecycle diagram is context: the challenge focuses on its steps 1 and 2, market research/needs analysis and product planning. Its later engineering, testing, homologation, manufacturing, and launch stages do not expand the challenge scope.

## Deliverables

- A concept and demonstrable AI prototype for deriving and prioritizing requirements with human review.
- A representative structured requirement list: unique ID; actionable description; linked findings and sources; priority/score; scoring rationale; evidence level; future assumptions and uncertainties; current decision status.
- An end-to-end workflow identifying autonomous AI work, AI-assisted work, mandatory human review, roles, and decision gates.
- A reconstructable audit trail from source evidence through consolidation, scoring, prioritization, and decisions. Preserve changes to content, scores, priorities, evidence, and status, including actor, timestamp, and rationale. Include approvals, modifications, postponements, and rejections.

## Judging criteria

Transcribed from Sebastian_BMW's [16:26 image](https://discord.com/channels/1553151744047976549/1553306479019429939/1558485916383969380); no criterion weights were supplied.

| Criterion | What judges evaluate |
| --- | --- |
| Decision and Scoring Logic | Quality, consistency, and explainability of deriving, evaluating, scoring, and prioritizing requirements; factors influencing decisions; evidence/source weighting and combination; handling trade-offs, uncertainty, and conflicting signals. |
| Workflow and Human Decision-Making | Quality and completeness from heterogeneous findings to priorities; clear roles, decision gates, review steps, and boundaries between assisted, autonomous, and human decisions. |
| Traceability and Auditability | Trace every requirement, score, modification, and decision to its originating evidence and sources; complete reconstructable history of approvals, modifications, postponements, and rejections. |
| Solution Quality, Usability, and Feasibility | Concept/prototype quality, useful requirements, ease of use for PMs and engineering teams, realistic applicability to enterprise product development. |
| Innovation, Scalability, and Business Impact | Originality and effectiveness; scaling across products, markets, and data volumes; less manual effort/rework, shorter decision cycles, better requirements and decisions. |

The rubric explicitly rewards honesty: surface missing evidence, conflicting signals, uncertain conclusions, and limitations to the PM.

## Mentor clarifications

- This is an ongoing requirements process over approximately two years, rather than a single generated list. Requirements and priorities evolve.
- PM pain points include balancing markets with different climates, usage, and cultures, and turning early feedback on predecessors into future requirements.
- Requirements should be SMART: specific, measurable, attainable, relevant, and timely. Define targets and acceptance criteria. A fridge for 100 bottles is unrealistic; a fridge with “a lot of space” is unspecific. Example numbers in slides are prompts for discussion, not approved targets.
- Preserve what customers love as well as identifying problems. The data-source image explicitly includes positive attributes that must not be lost.
- Use the annual report for market/sales context (regions, series, EV adoption) and product/R&D strategy (ConnectedDrive, My BMW App, Neue Klasse). This does not override the explicit exclusions on engineering and detailed business cases.
- Product management combines customer, brand, competition, market/sales, and engineering perspectives. The illustrative process is situation analysis → structure/context → requirement definition → prioritization → documentation/tracking.
- BMW requested that every Google Drive input file be added to `.gitignore`.

## Unanswered at capture time

At 17:17, Abbi asked whether the pitch is three or five minutes and how long Q&A lasts. No answer was present in the BMW channel at final verification. Do not treat either duration as confirmed.
