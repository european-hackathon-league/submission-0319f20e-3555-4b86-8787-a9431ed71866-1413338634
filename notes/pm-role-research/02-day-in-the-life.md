# 2. A BMW PM's day, week and year

> **Composite persona [Inference].** No public source documents a BMW PM's schedule. This persona combines BMW job postings, the BMW NA product-management interview, the hackathon keynote and mentor guidance, and cross-OEM research. Use it to design features and the demo story, not as a quoted fact.

## 2.1 Persona

**Lena, Product Manager, BMW 5 Series successor (G60 → next generation), Munich.**

- Owns the customer requirement set for the successor, about 3–5 years before launch, across Europe, the US and China.
- Also supports the current G60's model updates and its mid-cycle update.
- Works with product line leadership, the vehicle project, engineering departments (interior, infotainment and digital, powertrain and charging, chassis, driver assistance), design, brand, regional PMs (BMW NA, BMW China, European markets), sales and marketing, market research and quality.
- Tools [Inference, consistent with job ads and the Codebeamer announcement]: Excel, PowerPoint, email, Teams-style meetings, market-research portals, and the requirements system (Codebeamer since 2026).

## 2.2 Recurring rhythms

| Cadence | Activity | Evidence |
| --- | --- | --- |
| **Daily** | Scan the market: dealer feedback, customer and intender signals, competitor news, own research | "Our daily routine is to scan the market." BMW NA VP Product Management [BMW-public] |
| Daily | Answer questions from departments about what a requirement means and how important it is | Requirements maintained "across all departments" [BMW-public]; [Inference] on volume |
| **Weekly** | Standing meetings (*jour fixe*) per department: interior, digital, charging, etc. | [Inference] |
| Weekly | Align equipment and packages with other series' PMs (cross-series offer logic) | *baureihenübergreifend* alignment [BMW-public] |
| **Monthly** | Market calls with regional PMs: market potential, requests, competitor moves | BMW NA VP: each market is asked about its potential before a special model is offered (paraphrase) [BMW-public] |
| Monthly | Status reporting to product line / vehicle project | [Inference] |
| **Quarterly / per wave** | New customer studies, clinics and quality-survey waves (e.g. J.D. Power IQS in the first 90 days of ownership, APEAL, dependability) | [Industry]; BMW receives J.D. Power awards annually [BMW-public] |
| **Twice a year** | Spring and summer model updates for the current range | BMW press "model updates spring 2026" [BMW-public] |
| **Annually** | Portfolio and cycle-plan review; gap analysis vs customers and competitors | CAR: annual cycle-plan update with gap analysis [Industry] |
| **Per gate** | Prepare decision packs for G0 project approval and G1 concept freeze (BMW internal names differ) | [BMW-hackathon], [Industry] |
| **Over ~2 years** | Continuous re-prioritisation of the requirement set as evidence arrives | [BMW-hackathon] |

## 2.3 A representative week

> **[Inference]** Each block lists what agents could take over.

**Monday: inbox and signal triage**

- 40+ unread items: new verbatim batch from the current G60, a China market request for more rear-seat space, a competitor launch (a Chinese EV with a large in-car screen and voice assistant), and a question from interior engineering about "seat comfort" targets.
- Manual today: open Excel exports, filter, read hundreds of verbatims, copy quotes into slides.
- **Agent opportunity:** a morning change brief listing what is new, which findings it moved, which approved requirements it touches and what needs a decision. Already backed by `assess_updates` / `list_reviews`.

**Tuesday: department alignment**

- Infotainment jour fixe: engineering asks whether "fewer menus" means a menu-depth target or a task-completion-time target. Lena has to find the original complaints again.
- Charging team: the US wants a public-charging planning experience; Europe's complaints are about home and AC charging.
- **Agent opportunity:** a requirement-clarification pack showing the requirement, its SMART target, the 5 most representative verbatims per market, and conflicting evidence. One click, not an afternoon.

**Wednesday: cross-series and market alignment**

- Call with the 7 Series and X5 PMs on package logic (comfort seats, ventilation).
- Call with BMW NA: a US request for a performance derivative backed by dealer petitions. Per the BMW NA VP, such a proposal needs a detailed requirement definition plus volume and price analysis before Munich considers it (paraphrase) [BMW-public].
- **Agent opportunity:** a market-request triage agent. It structures the request, attaches internal and public evidence, compares it with other markets and drafts a response with rationale. Pricing and volume are flagged as owned by others.

**Thursday: decision pack**

- Build the slide deck for the product line's concept round: top-20 requirements, rationale, risks, what changed since the last round, and open conflicts.
- Typically 1–2 days of copy, paste and reformatting [Inference].
- **Agent opportunity:** generate the gate pack from the live, audited record (the frozen planning brief already exists). Every number and quote stays linked to its source.

**Friday: documentation and follow-ups**

- Update the requirement records (system of record), write meeting minutes, send decisions back to markets and departments, and log why a request was declined.
- **Agent opportunity:** draft stakeholder-specific outbound messages from the decisions in the audit trail. The PM reviews and sends; nothing is auto-sent.

## 2.4 Where the time goes

| Activity | Share of effort today | Basis |
| --- | --- | --- |
| Finding, reading and clustering feedback across sources and markets | High | Keynote funnel "1 billion findings" [BMW-hackathon]; mentor pain point "access early customer feedback" [BMW-hackathon] |
| Reconciling conflicting market and department requests | High | "A ton of communication and negotiation" [BMW-public]; balancing markets [BMW-hackathon] |
| Turning vague needs into measurable targets | Medium–High | SMART guidance and "600 or 700 mi?" examples [BMW-hackathon] |
| Building decks and reports for gates and status | High | Excel and PowerPoint emphasised in job ads [BMW-public]; McKinsey: content-heavy PM tasks ~40% faster with GenAI [Industry] |
| Re-explaining rationale for earlier decisions | Medium | Two-year process with changing people and evidence [BMW-hackathon]; [Inference] |
| Re-work after evidence changes | Medium | Requirements evolve over ~2 years [BMW-hackathon] |
| Strategic judgement: vision, trade-offs, brand | Should be high; often squeezed | A Pragmatic Institute survey: PMs want ~53% strategic time, few achieve it [Industry, weak] |

The shares are relative judgements, not measurements. Do not quote percentages for BMW on stage. Use the McKinsey task-level figures, attributed, and offer a measurement plan (see [06-pitch-and-demo.md](06-pitch-and-demo.md)).

## 2.5 Moments of truth

These are the moments where the PM is most exposed, and where our product should shine.

1. **"Where does this come from?"** A board member or engineer challenges a requirement. The PM needs the original evidence in seconds.
2. **"What changed since last time?"** At every gate and status round.
3. **"Why did you say no to my market?"** A regional PM asks why their request was postponed.
4. **"Is this target realistic?"** The engineer pushes back on "seat ventilation cools in X minutes".
5. **"Are we losing what customers love?"** Brand and design check that the successor keeps its DNA.
6. **"Who decided this, when, and on what basis?"** Audit, handover to a new PM, or a post-launch review.
