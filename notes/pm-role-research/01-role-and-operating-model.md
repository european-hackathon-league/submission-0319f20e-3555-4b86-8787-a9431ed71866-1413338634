# 1. Role and operating model

## 1.1 What "product management" means at BMW

BMW uses "product management" for the function that decides **what the customer gets** in a vehicle: features, equipment, variants, packages, and the customer-relevant attributes of the car. It does not cover how engineering builds it. The hackathon keynote defines a customer requirement as a "Customer Relevant Attribute of a Car" [BMW-hackathon].

Keynote slide 2, "The Product Management Universe", places the PM between five forces [BMW-hackathon]:

```text
                 Brand
                   │
  Competition ── PRODUCT ── Customer
                MANAGEMENT
                   │
      Engineering ─┴─ Markets / Sales
```

Keynote slide 3 states the PM's core transformation: **1 billion findings → 1,000 requirements → one car** [BMW-hackathon]. Its sample inputs mix complaints, wishes and praise: "Charging takes too long.", "Too many menus.", "I love the design.", "Uncomfortable seats.", plus competitor mentions ("The new XPENG", "Tesla and Grok").

## 1.2 Responsibilities (evidence from BMW job postings)

BMW postings for product management roles describe the following responsibilities. Internship and working-student ads describe the team's work, so they are a reasonable proxy for the full-time role.

| Responsibility | Evidence | Tag |
| --- | --- | --- |
| Define product requirements from customer and market needs, the competitive situation and future trends | BMW M product management internship | [BMW-public] |
| Maintain those requirements across all departments (*Fachbereiche*) and the whole product lifecycle | Same posting | [BMW-public] |
| Build customer-oriented offer structures; align equipment offers **across model series** (*baureihenübergreifend*) | Same posting | [BMW-public] |
| Help create sales and marketing concepts that account for brand, sales and service requirements | Same posting | [BMW-public] |
| Create product requirement profiles (*Produktanforderungsprofile*); run market, segment and competitor analyses; support price and option planning | BMW M Automobile internship (2024) | [BMW-public] |
| Strategic planning of the optional-equipment (*Sonderausstattung*) offer; market-side price and volume planning for a model series | BMW Produktmanagement Oberklasse working student (March 2026, via search snippet; posting now closed) | [BMW-public] |
| Look after the current *and next* generation of the model portfolio; analyse product and price data for European markets and competitors | BMW Produktmanagement Europa working student | [BMW-public] |
| Define and elaborate market requirements for the product content of BMW model series | BMW product management internship (search snippet) | [BMW-public] |
| Compare target and actual option take rates by market and segment | BMW optional-equipment internship (2019) | [BMW-public] |

Recurring skill asks are Excel and PowerPoint, German and English, analytical thinking and cross-functional teamwork [BMW-public]. **[Inference]:** much of the work today lives in spreadsheets, slide decks and meetings, which is exactly the surface agents can compress.

## 1.3 Where the PM sits in the organisation

What is public:

- **Product lines.** In 2000 BMW moved from a strictly model-series organisation to cross-cutting product lines that bundle development responsibility under one person [BMW-public, older source]. A product-line head is responsible for development and concept across a segment, for example "all BMW vehicles of the middle and upper classes and Rolls-Royce" (2023) [BMW-public]. The current mid-size product line coordinates interior and exterior scope for 3, 4, 5 Series, X3 and X4 vehicle projects [BMW-public].
- **Vehicle projects and derivatives.** A vehicle project brings business, engineering, purchasing and production together and steers them. A central unit manages derivatives [BMW-public, project-management internship].
- **Brand product management** is a named function. In 2023 Bernd Körber, head of BMW brand product management, also took over BMW brand management [BMW-public].
- **Regional product management.** National sales companies have their own product management. BMW of North America has a VP of Product Management who pushes market-specific needs to Munich [BMW-public].
- **Neue Klasse** has its own leadership (Mike Reichelt, Head of Neue Klasse since 2020) [BMW-public]. Development is led on the Board by Joachim Post since mid-2025 [BMW-public].

**[Inference] Working model for our design:**

| Layer | Who | What they want from our system |
| --- | --- | --- |
| Central PM (Munich), per series or derivative | Owns the customer requirement set for, e.g., the G60 successor | Evidence-backed, prioritised, traceable requirements; change alerts; gate packs |
| Regional / market PM (e.g. BMW NA, China, Europe) | Represents market potential and requests | A way to submit requests with evidence and see their status and rationale |
| Product line / vehicle project leadership | Owns the whole vehicle project, cost, timing | Stable, decided requirements at gates; impact of late changes |
| Engineering departments | Turn requirements into specifications | Clear, measurable, unambiguous requirements with acceptance criteria |
| Brand, sales and marketing | Positioning, "why buy", offer structure | What customers love, differentiators, package logic |

## 1.4 Lifecycle position and gates

BMW's challenge scope is **steps 1–2** of the automotive lifecycle diagram [BMW-hackathon]:

| Step | Activities | Deliverables | Gate |
| --- | --- | --- | --- |
| 1. Market research and needs analysis | Market research, customer insights, competitor analysis, regulatory outlook, technology trends | Market opportunity report, customer needs document, target segments | **G0 Project Approval** |
| 2. Product planning | Product vision, segment and positioning, feature prioritisation, business case, financial targets | Product plan, project charter, financial targets | **G1 Concept Freeze** |
| 13. Market feedback and continuous improvement | Customer feedback, field data, warranty monitoring, next-generation planning | Feedback reports, lessons learned | Feeds the next generation's step 1 |

That diagram is generic, not BMW-specific. Public traces of BMW's own process (*Produktentstehungsprozess*, PEP) mention a *Zielvereinbarung* (target agreement), *Produktlinie*, *Initialphase* and *Konzeptentscheid* (concept decision). One low-reliability source puts the concept decision at about 33 months before start of production (SOP) [BMW-public, weak].

Cross-OEM timing [Industry, CAR 2007]:

- Building the business case starts **about 30 months** before launch; the best OEMs manage 24.
- An "intent" gate about **6 months** in releases limited funds for development work.
- Full program approval comes **about 24 months** before launch and releases the major capital.
- The first 6–12 months of strategy development are "critical": segment, volume, price and key attributes are set there.

**[Inference] Implications for us:**

- The requirement set must be **stable and defensible at gates**, yet **change-aware between gates**. That is our approved-baseline plus change-assessment model.
- BMW mentors say the process runs **about two years** [BMW-hackathon], which fits CAR's 24–30-month window. Our "update run" story maps to real gate preparation.
- After concept freeze, changes get expensive. The PM needs to know *early* when new evidence threatens a decided requirement.

## 1.5 Product cadence the PM also serves

- **Model updates twice a year.** BMW announces spring and summer model updates, e.g. "BMW model updates spring 2026": iX1/iX2 range gains from new SiC power electronics, standard two-zone climate control on 1 and 2 Series [BMW-public]. The PM also manages the *current* generation's content, not just the successor.
- **Mid-cycle facelift (LCI) and successor.** Industry norm is a ~7-year cycle with a mid-cycle update [Industry/Inference]. A former OEM PM describes this as "constant plate spinning" across the current model, facelifts, new products and future programmes [Industry, Fleet News profile, via search summary].
- **Feedback loop.** Customer feedback, field data and warranty from the current car (step 13) feed the successor (step 1) [BMW-hackathon]. The provided G60, G70 and F70 feedback workbooks are exactly this input.

## 1.6 What the PM does *not* own (challenge boundaries)

Out of scope per BMW [BMW-hackathon]: regulatory and homologation requirements, technical specs and architecture, supplier topics, pricing, business case and cost calculation. Rough cost or effort may be a prioritisation factor.

**[Inference]:** in reality the PM *contributes* to price and volume planning, as the job ads show, but the challenge deliberately cuts that out. Our agents should **acknowledge** those dependencies by flagging "needs cost estimate from engineering" or "price positioning owned by sales", never compute them.
