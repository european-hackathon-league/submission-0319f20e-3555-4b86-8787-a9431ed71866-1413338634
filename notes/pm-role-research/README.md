# BMW product manager: role research

Research date: **11 October 2026**. Purpose: understand what a BMW vehicle product manager (PM) actually does, so the agentic layer, demo and pitch target real work rather than a generic "AI requirements tool".

This complements the [Product Management Factory](../pm-factory.md) agent vision, the [challenge requirements](../challenge.md), [BMW team guidance](../bmw-guidance.md), [PM workflows](../pm-workflows.md) and the [technical research review](../../research/RESEARCH.md). Those cover *what BMW asked for* and *how we built it*. This folder covers *who we are building it for*.

## Files

| File | Question it answers |
| --- | --- |
| [01-role-and-operating-model.md](01-role-and-operating-model.md) | Where the PM sits at BMW, what they own, which lifecycle phases and gates they work in |
| [02-day-in-the-life.md](02-day-in-the-life.md) | Daily, weekly, quarterly and gate-driven rhythms; where the time goes |
| [03-stakeholders-and-communications.md](03-stakeholders-and-communications.md) | Who the PM deals with; every inbound and outbound communication, artefact and format |
| [04-pain-points-and-ai-leverage.md](04-pain-points-and-ai-leverage.md) | Pain points ranked by evidence, and which are worth automating, assisting or leaving to the human |
| [05-agentic-layer-design.md](05-agentic-layer-design.md) | Agent roster mapped to PM jobs and existing API/MCP tools; autonomy boundaries |
| [06-pitch-and-demo.md](06-pitch-and-demo.md) | Features to showcase, 3-minute narrative, judging-criteria map, Q&A bank |
| [sources.md](sources.md) | All external sources with reliability notes |

## Evidence labels

Claims carry one of these tags so the pitch never overstates what we know:

- **[BMW-hackathon]**: BMW mentors, keynote, briefing or channel posts for this challenge. Strongest signal of what the judges care about.
- **[BMW-public]**: BMW press releases, BMW job postings, interviews with BMW executives.
- **[Industry]**: Cross-OEM research (Center for Automotive Research, McKinsey, J.D. Power, academic papers).
- **[Inference]**: Our synthesis. Plausible and consistent with the sources, but not stated by BMW. Do not present as fact on stage.

No public source documents a BMW PM's day hour by hour. The "day in the life" is a **composite** built from job postings, an executive interview, the BMW keynote and industry research. It is labelled as such.

## Ten takeaways that should drive the build and the pitch

1. **The PM is an integrator, not an author.** BMW's own keynote frames PM as the centre of a universe of *Engineering, Markets/Sales, Customer, Brand, Competition* [BMW-hackathon]. BMW job ads describe defining requirements from customer and market needs, competition and future trends, then *maintaining them across all departments and the full product lifecycle* [BMW-public]. Most PM hours go into reconciling those five perspectives, not into typing requirements.
2. **The funnel is the job:** "1 billion findings → 1,000 requirements → one car" [BMW-hackathon]. Anything that shrinks the reading-and-clustering stage without losing traceability is directly valuable.
3. **It is a two-year rolling process, not a one-off list** [BMW-hackathon]. The killer feature is *change management*: what changed since the last approved baseline, and which decisions it touches.
4. **Markets pull in different directions.** The US VP of Product Management describes "a ton of communication and negotiation" with Munich and per-market potential checks [BMW-public]. BMW mentors name balancing markets as pain point #1 [BMW-hackathon]. Market-conflict detection and a market-request triage flow are high-value demo moments.
5. **Customers are "rear-view" people** [Industry]: verbatims describe the predecessor, not the successor in 3–5 years. The system must separate *current evidence* from *forward assumptions*, which BMW explicitly asks for [BMW-hackathon].
6. **Requirements must be SMART and quantified.** BMW's examples: "Range: 600 or 700 mi?", "Cooler for how many bottles?", "Seat ventilation: fast enough?" [BMW-hackathon]. An agent that proposes a target *and* labels it as a PM assumption until validated fits their mental model exactly.
7. **Preserve what customers love** [BMW-hackathon]. Requirements are not only fixes; "must-not-lose" attributes (driving dynamics, design) protect brand DNA. The CAR study calls these "givens" [Industry].
8. **Outputs flow to an enterprise requirements system.** BMW standardised group-wide on PTC Codebeamer in April 2026, replacing fragmented legacy tools [BMW-public]. Our pitch: we sit *upstream* of Codebeamer and feed it traceable, decided customer requirements.
9. **BMW already runs multi-agent systems, under governance.** The AIconic Agent in Purchasing (10 agents, 1,800+ users) and the BMW Group AI Assistant platform (60,000+ users, vendor-reported) show the pattern: agents retrieve, analyse and draft, while people stay accountable [BMW-public]. Presenting our agents as "AIconic for Product Management" speaks their language.
10. **Accountability stays human.** McKinsey measured ~40% time savings on content-heavy PM tasks such as requirement documents, and ~15% on content-light ones [Industry]. A 2025 PM study is titled "Accountability must not be delegated to non-human actors" [Industry]. Pitch line: *agents do the reading, counting, drafting and defending; the PM does the deciding.*

## What this means in one sentence

Show a BMW PM's **week compressed into minutes**: the morning change brief, a market request triaged with evidence, a SMART requirement drafted and challenged, a gate pack generated, and stakeholder messages drafted (never sent). Every claim must be one click from its source and every decision must sit in the audit trail.
