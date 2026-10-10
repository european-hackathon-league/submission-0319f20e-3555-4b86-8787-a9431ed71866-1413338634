# 4. Pain points and where AI earns its keep

## 4.1 Pain points ranked by evidence strength

| # | Pain point | Evidence | Tag |
| --- | --- | --- | --- |
| P1 | **Balancing requirements across markets** with different climate, usage and culture | Named by BMW mentors as a common PM pain point; China values rear-seat space and long wheelbase, the US large engines and performance, Europe EVs | [BMW-hackathon], [BMW-public] |
| P2 | **Getting at early customer feedback** (e.g. on the predecessor) and turning it into *future* requirements | Named by BMW mentors | [BMW-hackathon] |
| P3 | **Scale of the funnel:** billions of findings → ~1,000 requirements → one car | Keynote slide 3 | [BMW-hackathon] |
| P4 | **Continuous re-prioritisation over ~2 years** as evidence and people change | Mentor: process over approximately two years | [BMW-hackathon] |
| P5 | **Vague needs → measurable targets** ("a lot of space" is not specific; "100 bottles" is not realistic) | SMART guidance and examples | [BMW-hackathon] |
| P6 | **Negotiation load** with markets and Munich, plus a stringent business-case discipline | "a ton of communication and negotiation" (BMW NA VP) | [BMW-public] |
| P7 | **Customers are "rear-view" people**: VOC describes the past; forward needs require judgement and trends | CAR study | [Industry] |
| P8 | **Trade-offs under budget:** being No. 1 on one attribute means settling for No. 2–3 on others; "givens" crowd out new features | CAR study | [Industry] |
| P9 | **Fragmented tools and traceability:** BMW consolidated legacy requirements tools into Codebeamer to improve traceability | PTC / BMW announcement, April 2026 | [BMW-public] |
| P10 | **Representativeness of evidence:** selected, undated feedback; 72.7% of G60/US feedback IDs come from one source | Our data analysis ([demo proposal](../winning-demo-proposal.md)) | [BMW-hackathon] data |
| P11 | **Deck and report production** consumes time that should go to strategy | Excel/PowerPoint-heavy job ads; McKinsey content-heavy tasks; Pragmatic Institute survey | [BMW-public], [Industry] |
| P12 | **Losing what customers love** while fixing complaints | Mentor: preserve positive attributes | [BMW-hackathon] |

## 4.2 Automation boundary per PM job

Columns follow BMW's required workflow distinction: autonomous AI work, AI-assisted work, mandatory human review [BMW-hackathon].

| PM job | Autonomous (agent does it, logged) | Assisted (agent proposes, PM edits) | Human only (gate) |
| --- | --- | --- | --- |
| Ingest sources | Hashing, dedup, exact location, provenance | Choosing which public web candidates to import | Approving new source types or data boundaries |
| Read and cluster feedback | Extraction of likes, defects, wants, difficulties with exact spans; deterministic counts | Naming themes and merging clusters | — |
| Market comparison | Per-market breakdowns, conflict detection | Interpreting why markets differ | Deciding market weighting |
| Competitor and trend scan | Public-web search, summarise candidates | Choosing relevant candidates | Forward-looking assumptions sign-off |
| Draft requirement | SMART draft with need, response and acceptance test separated; target labelled "PM assumption" | Wording, scope, target values | **Approve / reject / postpone** |
| Score and prioritise | Deterministic score with recorded weights and inputs | Explaining the score | Changing weights; final priority |
| Challenge | Red-team: missing evidence, conflicting signals, over-reach | — | Accepting or overruling the challenge |
| Change assessment | Detect affected approved requirements; diff | Proposed revision | Accepting the revision |
| Gate pack | Assemble from the frozen record | Narrative and emphasis | Presenting and owning it |
| Stakeholder messages | Draft per audience from recorded decisions | Tone, content | **Sending** |
| Audit and handover | Complete trail, hash chain, reconstruction | — | — |

Design rule: **LLMs interpret and draft, deterministic code counts and scores, humans decide.** This is already the backend principle ([research review](../../research/RESEARCH.md)). The agent layer must not blur it.

## 4.3 Time-saving hypotheses (to measure, not claim)

External anchors [Industry]:

- McKinsey (n≈40 PMs): content-heavy tasks such as requirement documents and backlogs took about **40% less time** with GenAI; content-light tasks, such as gathering and summarising data for presentations, about **15% less**. Time-to-market gain about 5% only when surrounding roles are rewired.
- arXiv 2510.02504 (2025 PM survey): 81% of individual contributors agree GenAI often saves them time, mostly when writing documents and presentations. The title states the accountability principle: "Accountability must not be delegated to non-human actors".

Our hypotheses, labelled [Inference]. Measure each on the G60/US slice before quoting any number:

| Task | Manual baseline (estimate to validate) | With agents | Metric to show live |
| --- | --- | --- | --- |
| Read and cluster a batch of 4,000+ verbatims for one market | Days of reading and spreadsheet work | Minutes, plus spot-check time | Records processed; % with exact source span; PM spot-check agreement |
| Answer "where does this requirement come from?" | 30–60 min hunting through files | One click | Time-to-trace in the demo |
| Triage a market request with evidence | Hours to days of back-and-forth | Minutes for the evidence pack | Evidence items attached; conflicts found |
| Prepare a "what changed" update | Half a day | Generated | Requirements flagged vs unchanged; false-alarm rate |
| Build a gate pack | 1–2 days | Draft in minutes; PM edits | % of claims with a source link (target 100%) |
| Draft 4 audience-specific messages for one decision | 1–2 hours | Drafts in seconds | Consistency: all drafts cite the same version and score IDs |

**Pitch framing:** "We remove the reading, reconciling and reformatting, the content-heavy work where McKinsey measured ~40% savings. We keep the deciding. And we measure it: here is our evaluation of grounding, coverage and review effort." The backend already has `server/evaluation.py` metrics; extend these rather than inventing numbers.

## 4.4 Anti-patterns to avoid (and to say we avoid)

- Auto-approving requirements, or letting an agent "decide" by changing status. Decisions require a human actor with the exact version and score IDs.
- Presenting sample counts as market prevalence. Feedback is selected and undated.
- Fabricated targets. Every number has a source or carries a `PM assumption` label.
- Pricing, cost or business-case calculation (out of scope). Flag the dependency only.
- Sending BMW-internal text to public research tools.
- "Agent theatre": many agents with no distinct job. Each agent must map to a PM job in this table and to concrete tools.
