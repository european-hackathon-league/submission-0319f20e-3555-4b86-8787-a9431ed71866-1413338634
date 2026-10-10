# 3. Stakeholders and communications

The PM is a communication hub. Keynote slide 2 names five forces: Engineering, Markets/Sales, Customer, Brand, Competition [BMW-hackathon]. Below, each is expanded into concrete stakeholders, then into every inbound and outbound flow we could identify. Rows marked [Inference] are typical for an OEM PM and consistent with the sources, but not documented by BMW.

## 3.1 Stakeholder map

| Stakeholder | Relationship to PM | What they need from the PM | What the PM needs from them | Tag |
| --- | --- | --- | --- | --- |
| **Customers and intenders** | Ultimate source of needs | A car that solves pains and keeps what they love | Verbatims, ratings, clinic reactions | [BMW-public], [BMW-hackathon] |
| **Dealers** | Front-line signal | Sellable product, fixes for recurring complaints | Feedback, lost-sale reasons, petitions | [BMW-public] (BMW NA VP) |
| **Regional / market PMs** (BMW NA, China, Europe NSCs) | Advocates for market potential | Their market's requirements accepted, or clear reasons why not | Market requests, market potential, local competitor view | [BMW-public] |
| **Product line / vehicle project leadership** | Owns the whole vehicle project | Stable, prioritised requirements at gates; impact of changes | Decisions, budget envelope, timing | [BMW-public], [Inference] |
| **Engineering departments** (interior, infotainment/digital, powertrain and charging, chassis, driver assistance) | Turn requirements into specifications | Unambiguous, measurable requirements; acceptance criteria; priority | Feasibility, rough effort, technical constraints | [BMW-hackathon] (domain split on process slide), [Inference] |
| **Design** | Exterior and interior design | Customer perception of design; what to keep | Concepts to test with customers | [BMW-hackathon] ("I love the design", "ugly kidney grille") |
| **Brand management / brand product management** | Brand DNA and positioning | Requirements consistent with brand values | Brand guardrails | [BMW-public] |
| **Other series PMs** | Cross-series offer logic | Consistent package and option structure | Alignment on shared options | [BMW-public] (*baureihenübergreifend*) |
| **Sales and marketing** | Sell the car | "Why buy" stories, differentiators, offer structure | Sales volumes, take rates, positioning | [BMW-public], [Industry] |
| **Aftersales / service** | Service requirements | Serviceability considered | Field issues | [BMW-public] (service requirements in BMW M ad) |
| **Market research** | Studies and clinics | Research questions | Customer studies, clinic results, J.D. Power data | [Industry] |
| **Quality** | Field quality, warranty | Quality issues addressed in the successor | Warranty and field data, IQS | [BMW-hackathon] (step 13), [Industry] |
| **Controlling / finance** | Business case | Feature list for costing | Cost envelopes (out of challenge scope) | [Industry] |
| **Strategy / R&D strategy** | Technology roadmap (Neue Klasse, digital) | Customer pull for technologies | Platform capabilities, ConnectedDrive and My BMW App data | [BMW-hackathon] (annual report guidance) |
| **Board / committees** | Approve at gates | Concise decision packs with risk and evidence | Strategic direction | [Industry], [Inference] |

## 3.2 Inbound communications (what lands on the PM's desk)

| # | Inbound item | From | Typical format | Frequency | What the PM must do | Agent support |
| --- | --- | --- | --- | --- | --- | --- |
| I1 | Customer verbatims on the current car | Market research, surveys, dealers | Excel exports, survey portals | Continuous, in batches | Read, cluster, find pains, wants and loves | **Autonomous** extraction and clustering with exact source spans |
| I2 | Customer study ratings (e.g. comfort, design, infotainment) | Market research | Excel / study reports | Per wave | Compare with competitors and predecessor | Autonomous comparison; assisted interpretation |
| I3 | Quality and satisfaction studies (IQS, APEAL, dependability) | External (J.D. Power) via quality / research | Reports | Annual | Identify problem areas and differentiators | Assisted: map to findings |
| I4 | Sales volumes by powertrain and region | Sales | Excel | Monthly / annual | Where the car sells, which powertrains matter | Autonomous context for market weighting |
| I5 | Option take rates (target vs actual) | Sales / product management | Excel | Periodic | Package and offer decisions | Assisted (pricing out of scope) |
| I6 | **Market requests** (e.g. US: manual or performance variants; China: rear-seat space, long wheelbase, autonomous driving) | Regional PMs | Email, decks, calls | Ad hoc, constant | Evaluate, negotiate, decide or escalate | **Assisted triage:** structure, attach evidence, cross-market conflict check, draft reply |
| I7 | Dealer feedback and petitions | Dealers via NSCs | Email, reports | Ad hoc | Weigh against representative evidence | Assisted: flag selection bias |
| I8 | Competitor launches and features | Market intelligence, press | Articles, teardown reports, configurators | Weekly | Check competitive gaps | **Autonomous** web monitoring with public sources only, then PM selects what to import |
| I9 | Technology and trend reports | Strategy / R&D, external | Reports | Periodic | Forward assumptions (3–5 years) | Assisted: label as forward-looking assumptions |
| I10 | Feasibility and effort feedback | Engineering | Meetings, email, system comments | Weekly | Adjust targets, rough effort factor | Assisted: attach to requirement as a dated input |
| I11 | Clarification questions on requirements | Engineering | Email, chat, meetings | Daily | Explain intent and evidence | **Autonomous** answer pack (trace + exemplars); PM confirms |
| I12 | Brand guardrails | Brand management | Guidelines | Rare | Check consistency | Assisted check |
| I13 | Strategy and portfolio targets | Board / strategy | Decks | Annual / per gate | Align requirements | Human |
| I14 | Regulatory outlook | Regulatory affairs | Reports | Periodic | Context only (out of scope) | Flag dependency only |
| I15 | Annual report and market data | Corporate | PDF | Annual | Market context (regions, EV adoption) | Autonomous context extraction |

Cross-check against what BMW actually gave us [BMW-hackathon]: customer verbatims (I1), equipment / option lists (I5-ish, current offer and gaps), sales volumes (I4), customer study (I2), annual report (I15). Web enrichment covers I8 and I9. We currently have no direct simulation of **I6 market requests**, **I10 feasibility feedback** or **I11 clarification questions**. These are the most "real PM" flows and the cheapest to add as demo scenarios.

## 3.3 Outbound communications (what the PM produces)

| # | Outbound item | To | Typical format | When | Agent support |
| --- | --- | --- | --- | --- | --- |
| O1 | **Customer requirement list / requirement profiles** (*Produktanforderungsprofile*) | Engineering, vehicle project, requirements system (Codebeamer) | Requirement records with ID, text, target, acceptance criteria, priority | Continuous; frozen at gates | Drafted by agent; **PM approves**; export in a Codebeamer-ready structure |
| O2 | Prioritisation rationale | Product line, board | Slides, scoring tables | Per gate / round | Generated from deterministic score runs |
| O3 | **Gate / decision packs** (G0, G1 or BMW-internal equivalents) | Board, committees | PowerPoint | Per gate | **Autonomous draft** from the frozen record; PM edits |
| O4 | "What changed since last round" reports | Product line, departments | Slides, email | Monthly / per round | Autonomous from the change assessment |
| O5 | **Responses to market requests** (accept, postpone, reject with reasons) | Regional PMs | Email, decks | Ad hoc | Draft from the decision and audit trail; PM sends |
| O6 | Requirement clarifications and target rationale | Engineering | Email, meetings | Daily | Answer pack from the trace |
| O7 | Offer and package structure proposals | Sales, other series PMs | Excel, slides | Per planning round | Assisted (pricing out of scope) |
| O8 | "Why buy" and positioning input; what customers love | Sales, marketing, brand | Slides | Pre-launch phases | Assisted from "love" findings |
| O9 | Research briefs (what we still need to learn) | Market research | Brief | When evidence is weak | **Autonomous suggestion** from evidence gaps (low evidence grade, conflicts) |
| O10 | Meeting minutes and decision log | All | Docs | After meetings | Autonomous from audit events |
| O11 | Handover documentation | Successor PM, auditors | Docs | Role change, audits | Autonomous: full reconstructable history |

## 3.4 Communication patterns that matter for agent design

1. **Same decision, many audiences.** One PM decision (e.g. "approve CHG-001 with a 90% route-planning success target") needs four phrasings: an engineering spec, a market response, a board summary and an audit entry. This is the single best fit for a communications agent. It must draft from the *recorded* decision and never invent a new one.
2. **Negotiation, not broadcast.** Market requests and engineering pushback are dialogues. The useful agent prepares the PM's position (evidence for and against, cross-market impact) rather than replying itself.
3. **Formats are Excel and PowerPoint today** [BMW-public]. Exports to Markdown, slides and spreadsheets beat a new UI the stakeholders must learn. Only the PM uses our cockpit; everyone else receives artefacts.
4. **Provenance travels with the message.** Every outbound artefact should carry requirement IDs, version IDs and links back to the trace, so a recipient can click "why?".
5. **Nothing leaves without a human.** Sending a message is outward-facing and irreversible. This matches BMW governance messaging [BMW-public] and the challenge's human-review requirement [BMW-hackathon].
6. **Data boundary.** BMW verbatims and internal data never go to public research tools. Web research uses public queries only, and the PM explicitly selects what is imported. This is already enforced by the `bmw-evidence` MCP server instructions.
