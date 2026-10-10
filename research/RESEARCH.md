# Internal research: BMW product requirements

Research date: **10 October 2026**. This is a targeted research review, not an exhaustive systematic review or proof of patent novelty. Quantitative literature results, measurements on the supplied BMW files, and proposed experiments are identified separately.


**Current implementation scope:** the [implementation plan](../IMPLEMENTATION_PLAN.md) defines the agreed product: evidence-backed customer requirements, understandable priorities, and targeted review when new evidence affects a decision. This document is background for the development team, not BMW-facing product copy.

The review explored a broader set of possibilities before the product was narrowed. Adaptive research selection, synthetic-user experiments, advanced scenario analysis, and outcome learning are research options, not implementation commitments. The relevant foundations for the current scope are evidence extraction, source traceability, explicit prioritization, change assessment, and evaluation of quality alongside review effort.

**The broader research opportunity is a continuous customer-learning system: identify needs from evidence, determine which priorities withstand uncertainty, choose the next investigation, and learn from what customers subsequently experience.** A requirement becomes a testable proposition with a history, an owner, and a customer outcome.

The language model supports interpretation, retrieval, and drafting. Explicit statistical models support uncertainty and question selection. Deterministic calculations produce counts and scores. Product managers own strategic preferences and commitments. Customer experiments establish whether proposed improvements work.

## 1. What already exists

| Approach | What it contributes | Where it falls short for this challenge |
| --- | --- | --- |
| Voice of the Customer and Quality Function Deployment | Organize customer needs and connect them to product decisions. Retain the distinction between an underlying need and a proposed solution. | Human interpretation and ongoing maintenance remain demanding. The engineering translation part of QFD extends beyond the challenge scope. [Griffin & Hauser, 1993](https://pubsonline.informs.org/doi/10.1287/mksc.12.1.1) |
| Kano analysis | Distinguishes expected capabilities, performance improvements, and attractive features. Useful for protecting basics while discovering opportunities. | Requires customer elicitation; an LLM assigning Kano labels from complaints is a hypothesis, not a validated Kano study. [Kano et al., 1984](https://www.jstage.jst.go.jp/article/quality/14/2/14_KJ00002952366/_article) |
| RICE and related scoring rules | Cheap, understandable prioritization using reach, impact, confidence, and effort. | Input estimates can dominate results. Complaint counts do not establish population reach; confidence percentages are not automatically calibrated. Rough effort is permitted by the challenge, but detailed business cases are excluded. [Intercom’s original method](https://www.intercom.com/blog/rice-simple-prioritization-for-product-managers/) |
| Classical NLP and embeddings | Filter uninformative text, classify feedback, cluster similar needs, and reduce repetitive analyst work. | A topic such as “seats” is too broad to be a useful requirement. [Timoshenko & Hauser, 2019](https://pubsonline.informs.org/doi/abs/10.1287/mksc.2018.1123) evaluated informative/diverse sampling using 12,000 annotated UGC sentences. |
| LLM extraction and requirement drafting | Interpret implicit needs, separate multiple statements in a comment, normalize terminology, and draft customer-facing requirements. | Fluent output can lack specificity or invent targets. Domain examples and professional evaluation matter. [Timoshenko, Mao & Hauser, 2026 revision](https://arxiv.org/abs/2503.01870v2) |
| Retrieval, evidence graphs, and traceability | Connect claims to original records and navigate relationships among needs, markets, assumptions, and decisions. Graph-based summarization can help answer corpus-wide questions. | Retrieved passages and graph edges can be wrong. Citations require verification; graph construction adds cost. [GraphRAG](https://arxiv.org/abs/2404.16130), [ALCE](https://aclanthology.org/2023.emnlp-main.398/) |
| Robust multicriteria decision analysis | Explore plausible criteria weights and uncertain evidence instead of relying on a single exact score. | Robustness depends on the uncertainty set and preference model. Stable rankings can still reflect a biased model. [Tervonen & Lahdelma, 2007](https://www.sciencedirect.com/science/article/abs/pii/S0377221706000506) |
| Adaptive preference elicitation and value of information | Choose questions or tests that resolve consequential uncertainty efficiently. | Requires a meaningful model of preferences/outcomes and real answers. AI-generated respondents cannot substitute for validation. [Dzyabura & Hauser, 2011](https://pages.stern.nyu.edu/~ddzyabur/index_files/ActiveLearning.pdf), [Guo & Sanner, 2010](https://openresearch-repository.anu.edu.au/items/2160b9e7-1473-4015-ac72-4d56ee030fcb) |
| Continuous requirements and change-impact analysis | Identify which existing decisions need reconsideration when evidence or requirements change. | Relevance is not the same as an actual dependency. False alerts and missed changes must both be measured. [Etezadi et al., 2026](https://arxiv.org/html/2511.00262v6) |

Commercial precedent matters. Productboard described continuous linking of incoming feedback to feature ideas in 2024. IBM published a requirements-question-answering demonstrator for DOORS Next in 2025; IBM explicitly described that artifact as a demonstrator rather than a product. Automatic summarization, source links, and requirement chat alone would therefore be weak novelty claims. These are vendor descriptions of capabilities, not independent estimates of business impact. [Productboard](https://www.productboard.com/blog/productboard-ai-2/), [IBM](https://community.ibm.com/community/user/blogs/daniel-moul/2025/02/13/requirements-ai-assistant-for-doors-next).

## 2. The papers most useful for this project

Published percentages below describe their authors’ experiments. They are not measured performance of our proposed BMW application.

| Paper and evidence status | Result or contribution worth using | Interpretation and limitation |
| --- | --- | --- |
| **Transforming the Voice of the Customer**, Timoshenko, Mao & Hauser; working paper, revised April 2026 | In the 90-verbatim subset of its wood-stain evaluation, source grounding was judged at **98% for the fine-tuned model, 91% for professional analysts, and 90% for the base model**. Training used 1,549 matched need/verbatim examples across ten categories. | Strong motivation to collect expert corrections and evaluate formulation, detail, and grounding separately. Limited professional raters and category-specific evaluation; this does not establish performance of current frontier models or automotive deployment. [Paper](https://arxiv.org/pdf/2503.01870v2), Appendix E. |
| **From Online User Feedback to Requirements**, Mallya et al.; 2025 preprint | Five lightweight models obtained roughly **0.47–0.68 F1** across classification settings and approximately **3/5** mean specification quality. | “Use an LLM” is not enough. Benchmark models and prompts on the precise task. App-review classification does not directly measure automotive customer-need quality. [Paper](https://prompt-me.github.io/manuscripts/REFSQ_26_preprint.pdf). |
| **Large Language Models for Requirements Engineering: A Cross-Task Empirical Evaluation**, Dąbrowski et al.; August 2026 preprint | Evaluates five RE activities; reports task-dependent performance with no universally best model. | Supports separate model selection for extraction, linking, and drafting. Overlaps with the preceding authors’ feedback study and should not be counted as independent replication of it. [Paper](https://arxiv.org/abs/2608.21531). |
| **LLM-Driven Cost-Effective Requirements Change Impact Analysis**, Etezadi et al.; September 2026 manuscript lists an ACM TOSEM DOI | Reports **95.8% mean recall** with domain retrieval while surfacing **3.4%** of requirements for review. Test setting: 192 satellite-system requirements and 11 held-out change rationales. | “Cost” means review fraction, not measured labor-time savings. Same-domain, small industrial test. Table 9 includes 30 TP, 3 FN and 35 FP: the result must not be described as 95.8% precision. [Paper](https://arxiv.org/html/2511.00262v6), sections 4.6 and 4.9. |
| **Active Machine Learning for Consideration Heuristics**, Dzyabura & Hauser; Marketing Science, 2011 | Automotive study with **872 respondents and 53 feature levels**. For heuristic models, adaptive questions reduced validation KL divergence from **0.512 to 0.475**, p<0.001. | Direct automotive precedent for selecting informative questions. Benefits depended on the response model; adaptive questions were not best under every estimation method. [Paper](https://pages.stern.nyu.edu/~ddzyabur/index_files/ActiveLearning.pdf), Table 2. |
| **Enabling Large Language Models to Generate Text with Citations**, Gao et al.; EMNLP 2023 | Introduced ALCE; in its ELI5 evaluation even the best tested models lacked complete citation support about **50%** of the time. | Source presence and source support are distinct metrics. This is an older QA benchmark, not an estimate of today’s model performance. [Paper](https://aclanthology.org/2023.emnlp-main.398/). |
| **When combinations of humans and AI are useful**, Vaccaro et al.; Nature Human Behaviour, 2024 | Across **106 experiments / 370 effect sizes**, human+AI improved over humans alone (g=0.64) but underperformed the better standalone human or AI baseline (g=−0.23). | Measure the combined workflow, not just model accuracy or user satisfaction. Diverse tasks and older systems limit direct transfer to BMW. [Paper](https://www.nature.com/articles/s41562-024-02024-1). |
| **Human-AI Collaboration in Requirements Engineering: Evidence of the Negative Effect of LLMs on Requirements Inspection**, Broccia et al.; August 2026 preprint | Crossover study with **34 students**. No significant duration change; the paper reports roughly 8% higher detection F1 without ChatGPT, with overlapping uncertainty intervals. | Relevant caution about automation bias. Student inspectors, simplified game requirements, and 2025 models are not equivalent to experienced BMW PMs. [Paper](https://arxiv.org/html/2608.21298v1). |
| **To Trust or to Think**, Buçinca et al.; ACM CSCW, 2021 | Experiment with **199 participants** found cognitive-forcing interventions reduced overreliance, with a usability trade-off. | Selective review prompts may help; forcing every user through extra steps could reduce usefulness. [Paper](https://arxiv.org/abs/2102.09692). |
| **Mining novel customer needs … LLM-enabled data augmentation and ensemble learning**, Huang, Qin & Wang; International Journal of Production Research, 2026 | Uses generated training examples and BERT ensembles to identify rare novel needs in laptop reviews. Evaluates precision, recall, and F1; augmentation was restricted to training data. | Detecting rare needs already has direct prior art. Synthetic training examples are different from treating generated comments as customer evidence. [Paper](https://www.tandfonline.com/doi/full/10.1080/00207543.2026.2625971). |
| **Continuous Data-driven Personas Generation**, Sugiyama et al.; IEEE RE, 2025 | Publisher abstract reports outperforming a clustering baseline in approximately **86% of QA cases** using an LLM-generated knowledge graph over support calls. | Continuous persona/evidence graphs are not new. Only publisher abstract and authors’ presentation were accessible here; the number is not evidence of better product outcomes. [Publisher](https://ieeexplore.ieee.org/document/11190348/). |
| **RAG or Learning? … Continuous Knowledge Drift**, Liu, Cao & Li; Findings of ACL, 2026 | Evaluates evolving facts and proposes Chronos, a time-aware evidence graph without additional model training. | Useful precedent for dated evidence and supersession. News/event knowledge is different from evolving customer preferences. [Paper](https://aclanthology.org/2026.findings-acl.546/). |
| **When Synthetic Users Fail**, Chen, Zhu & Zheng; October 2026 revision, preprint | Across GSS/WVS domains and four models, demographic simulation inflated between-segment gaps **2–4×**; larger models did not resolve the failure. | Restricts confidence in imagined customer panels. This concerns tested demographic survey simulation, not every possible hybrid statistical use of LLMs. [Paper](https://arxiv.org/abs/2607.26348v2). |
| **LLMs for Requirements Engineering: A Systematic Literature Review**, Zadenoori et al.; 2025 preprint | Reviews **74 studies from 2023–2024**, noting limited industrial integration and evaluation. | Establishes a broad prior-art landscape, not coverage of all 2026 work. [Review](https://arxiv.org/abs/2509.11446). |

## 3. What the supplied BMW data supports

The following are direct counts from the untouched supplied workbooks, not literature results or validated model predictions.

| Workbook | Classification rows | Distinct feedback IDs | IDs with at least one “Likes” label |
| --- | ---: | ---: | ---: |
| F70 | 4,076 | 2,128 | 1,284 |
| G60 | 5,005 | 4,000 | 1,791 |
| G70 | 4,690 | 4,000 | 1,786 |
| Total | 13,771 | 10,128 | 4,861 |

A feedback ID may have multiple classification rows. IDs do not necessarily identify independent people. Positive and negative sets overlap; 490 IDs have both kinds of labels. Existing labels are useful baseline annotations, not unquestionable gold-standard truth.

G60/US has 4,365 classification rows and 3,610 distinct IDs. Source B contributes 2,626 IDs, or 72.7%. This is a reason to examine evidence coverage and dependence, not a reason to declare Source B unreliable. Removing that source also changes the observed sample composition. Raw count drops are partly mechanical, and even within-source rates remain rates in a selected feedback sample.

The files contain no individual feedback timestamp column and no CN feedback records. China is represented in the customer studies and sales workbook. We cannot validate historical trend detection from these undated comments, infer Chinese complaint prevalence, or infer the probability that an arbitrary BMW customer has a problem. Controlled replay can test software behavior, but it is not a historical backtest.

No experiment outcomes linking implemented product changes to customer benefits are supplied. No feature-level effort estimates or individual-level conjoint responses are supplied. The study sheets contain different layouts and scales; aggregate means and percentages must not be pooled as if they were interchangeable respondent observations. Future sales columns are inputs, not realized outcomes.

These limitations suggest that our first validated capability should be faithful evidence synthesis and decision support. Claims about causal customer benefit need subsequent research.

## 4. Research-informed system design

**Separate the customer need, the proposed response, and the measurable test.** For example, a customer may need confidence that a long trip will be completed comfortably. Better range, better charging reliability, and better planning are alternative responses. A proposed range target needs its own justification. The application should preserve this separation throughout the decision history.

Store a small, explicit record of each source, extracted claim, customer need, proposed requirement, market, vehicle generation, assumption, decision, and outcome. Edges identify support, disagreement, applicability, dependence, and supersession. These relationships can initially live in ordinary database tables; a dedicated graph database is an implementation choice. The [GraphRAG paper](https://arxiv.org/abs/2404.16130) motivates corpus-wide synthesis, but does not prove a graph will outperform simpler retrieval on BMW’s dataset.

Use AI for tasks that benefit from language understanding:

- Split multi-issue comments while preserving exact source spans and all classifications.
- Extract the underlying desired customer outcome and distinguish praise, failure reports, suggestions, and irrelevant content.
- Connect equivalent needs across wording while preserving market/context differences.
- Retrieve supporting and potentially conflicting evidence, classifying whether it actually conflicts under comparable conditions.
- Draft actionable requirement candidates and mark unsupported target values as proposed assumptions.
- Map a new piece of evidence to potentially affected requirements and explain the proposed update.
- Suggest neutral research questions and candidate prototype tests.

Use explicit algorithms for ID deduplication, cohort filters, counts, scoring, scenario sampling, version comparisons, and experiment statistics. Do not ask a language model to count the corpus or invent a probability of customer demand.

Human approval should cover the interpretation of material ambiguities, strategic preference weights, acceptance criteria, and commitment to a requirement. Good explanations should be checkable evidence and calculations, rather than a long model-generated reasoning narrative.

## 5. Underexplored combinations worth testing

I did not find an evaluated BMW-like end-to-end system that demonstrates all the following benefits together. That is a bounded observation about this review, not a claim that no researcher or company has built one. Each component has prior art.

**A. Recommend the next investigation that could change a product decision.**

The application asks what uncertainty is preventing a defensible decision, then suggests the research with the highest expected decision benefit. Candidate actions include reading a neglected source, asking a PM to resolve an ambiguity, conducting a customer interview, testing a prototype interaction, or comparing concepts with real customers.

A possible algorithm ranks research actions by expected reduction in decision loss per unit of research effort. This extends adaptive preference elicitation to a portfolio of heterogeneous BMW evidence and requirement decisions. Information gain alone can waste effort on interesting but decision-irrelevant uncertainty. [Adaptive automotive research](https://pages.stern.nyu.edu/~ddzyabur/index_files/ActiveLearning.pdf) and [Bayesian query selection](https://openresearch-repository.anu.edu.au/items/2160b9e7-1473-4015-ac72-4d56ee030fcb) are the relevant foundations.

The proposed innovation is the integration of grounded language interpretation, uncertainty-aware priorities, and targeted real-world evidence acquisition. Test it against random research selection, uncertainty-only selection, and a PM’s normal choice under the same evidence budget.

**Metrics:** held-out decision loss after each research round; number of questions or research minutes to reach a specified quality level; accuracy of predicted versus realized decision improvement. A calibrated utility model and real answers are prerequisites for strong claims.

**B. Requirements that specify when their justification no longer holds.**

Each requirement carries applicability conditions and assumptions: market, model generation, user task, evidence date, and the observation that would require reconsideration. New evidence creates a targeted review request and a proposed diff. Approval remains a separate action.

The novel research question is whether combining explicit conditions, semantic impact retrieval, and decision history can catch important changes with less review burden than a static requirements list. [Change-impact analysis](https://arxiv.org/html/2511.00262v6) and [time-aware retrieval](https://aclanthology.org/2026.findings-acl.546/) are established neighboring work.

**Metrics:** recall of genuinely affected requirements; false-alert rate; share of requirements requiring review; median time to a correct revision; stale-decision duration. Evaluate harmless updates as well as meaningful ones so the system cannot score well simply by reopening everything.

**C. Discover emerging needs while protecting attributes customers already value.**

Maintain explicit evidence for positive attributes alongside unmet needs. Surface rare, specific, potentially valuable needs for investigation, even when frequent complaints dominate the main ranking. A proposed change should show any supported benefits it could undermine.

Novel-need detection has prior art, including [Huang et al., 2026](https://www.tandfonline.com/doi/full/10.1080/00207543.2026.2625971). The research opportunity is to combine discovery and preservation in a measurable requirement-review process. Without dated data, call these “rare or previously unrepresented needs,” not demonstrated emerging trends.

**Metrics:** expert-validated novel needs per 100 candidates; rare-need recall at a fixed review budget; diversity of distinct validated needs; recall of customer-valued attributes put at risk. Textual dissimilarity alone is not innovation quality.

**D. Priorities that remain useful across plausible future conditions.**

Represent uncertain evidence and PM preferences as ranges. Explore changes in source availability, market mix, customer usage, and future assumptions. Show priority intervals, the conditions in which the ranking changes, and requirements that perform acceptably across scenarios. [SMAA](https://www.sciencedirect.com/science/article/abs/pii/S0377221706000506) and [RAND’s robust decision-making framework](https://www.rand.org/pubs/tools/TL320/tool/robust-decision-making.html) already provide this foundation.

An 80% top-five scenario frequency means 80% under the chosen scenario distribution; it is not an 80% probability of real-world success. Market weights are strategic inputs, not a correction for unknown survey selection bias.

**Metrics:** top-k acceptability; preference-weight ranges that reverse a decision; worst-case and average decision loss under declared scenarios; invariance to duplicate records; responsiveness to genuinely decisive counter-evidence. Stability alone is insufficient: a system that never changes would be stable but unhelpful.

The broader research recommendation was **A supported by B and D**, with C protecting discovery from degenerating into a leaderboard of complaints. The agreed implementation concentrates on grounded requirements and targeted reconsideration from B. The other directions remain available for later evaluation.

## 6. How this creates lasting value for BMW

BMW already describes using feedback, data from **more than 10 million connected vehicles**, and usability studies involving **more than 3,000 customers** to develop Panoramic iDrive. These are company-reported development inputs; they are not datasets supplied to us. The proposed system should fit that existing capability by connecting evidence to decisions and subsequent outcomes. [BMW primary source](https://www.bmwgroup.com/content/grpw/websites/bmwgroup_com/en/unternehmen/neue-klasse/details-bmw-panoramic-idrive.html).

The durable asset would be a BMW-owned history of which needs were discovered, what the team believed, why it acted, and what happened afterward. That can support:

- Reuse across model generations without losing the original market and usage context.
- Faster research selection and fewer repeated investigations.
- Better allocation of PM attention when inputs change.
- Earlier detection of valuable weak signals and unnecessary loss of appreciated features.
- Evaluation datasets built from professional corrections, enabling prompt improvement, task-specific model selection, and possibly later fine-tuning.
- Forecast calibration: whether predicted customer benefits actually appeared, and where the system was systematically overconfident.

An approval is evidence of a PM decision, not proof that customers benefited. Preserve the distinction between reviewer preference, source truth, and measured customer outcome. Otherwise a learning system can amplify existing organizational preferences.

Use replaceable model components and a stable evidence schema. Re-run frozen evaluations when changing models, prompts, retrieval, or extraction logic. The same evidence snapshot and configuration should reproduce the same deterministic counts and scores. New model capability is useful only if it improves measured quality, cost, or latency on the relevant task.

A simple lifecycle illustrates the intended benefit: a reported charging frustration becomes a need hypothesis; the system identifies whether charging reliability or planning is the unresolved issue; a targeted test distinguishes the alternatives; the PM records a requirement and expected benefit; later usability or field evidence measures whether the benefit occurred. The resulting evidence updates future vehicle decisions.

## 7. Metrics that distinguish technical quality from customer value

The metrics below are proposed evaluation measures. No performance target has yet been achieved by this project.

| Layer | Metric | Definition and interpretation |
| --- | --- | --- |
| Extraction | Need precision, recall, macro-F1 | Compare distinct extracted needs and evidence spans against adjudicated annotations; report per market/source and rare classes. |
| Coverage | Distinct validated needs per reviewer-hour | Rewards discovery and efficient review, rather than generating many near-duplicates. |
| Grounding | Claim support precision | Fraction of material claims actually supported by their cited evidence; source links merely existing is not enough. |
| Grounding | Citation completeness | Fraction of material empirical claims with adequate evidence; explicitly proposed assumptions are counted separately. |
| Contradictions | Counter-evidence precision and recall | Judge whether retrieved evidence genuinely challenges the same claim in a comparable context. Different users preferring different things may represent segmentation, not logical contradiction. |
| Requirements | Specificity/testability pass rate | Human rubric for customer outcome, applicability, meaningful acceptance test, and unsupported invented targets. |
| Ranking | NDCG@k and pairwise preference agreement | Agreement with an independently elicited PM/customer reference; report rater disagreement because priorities are not universal ground truth. |
| Robustness | Top-k acceptability and source dependence | Rank frequency across declared assumptions; share of supporting IDs associated with each source. These describe the model and sample, not population truth. |
| Calibration | Brier score and calibration curves | Applicable only to a defined predicted event with later observed outcomes; do not calibrate a vague “confidence” label. |
| Active research | Decision-loss reduction per research-minute | Benefit of acquired evidence under a declared utility model; compare at the same budget. |
| Change detection | Impact recall and review fraction | Affected requirements recovered versus all affected; requirements surfaced versus all requirements. Report both together. |
| Change detection | False alerts and stale-decision time | Cost of irrelevant reviews and time a material decision remains based on invalid evidence. |
| Human workflow | Time to an adequate decision | Time to a rubric-qualified decision, including reading, verification, editing, and corrections. |
| Human workflow | Unsupported approvals and missed critical evidence | Guardrails against gaining speed by accepting incorrect recommendations. |
| Operations | Cost per accepted grounded requirement; p95 latency | Include inference and review effort separately; cache hits or fast draft generation do not automatically lower total effort. |
| Customer outcome | Task success, task duration, errors, perceived effort | Use actual prototype tasks chosen for the requirement. For controls, completion and error counts are concrete outcomes. |
| Customer outcome | Attribute satisfaction and problem incidence | Measure the targeted attribute and define an exposure denominator; unnormalized complaint volume can move with sales and reporting changes. |
| Portfolio learning | Benefits realized and research avoided | Compare preregistered expected customer benefits to measured effects; log documented reuse, not speculative hours saved. |

For illustration, a range-related need might be evaluated using successful trip planning and confidence in arrival, whereas a control-access need might use task completion time, errors, and perceived effort. The correct measures depend on the actual customer outcome. A generic satisfaction score alone would hide the mechanism.

Causal customer-value claims require controlled concept/prototype tests, a randomized rollout where feasible, or a justified quasi-experimental design. Pre/post improvement alone is confounded by changes in customer mix, season, software, and reporting. Revenue gains and detailed business cases are outside the challenge and cannot be inferred from these files.

## 8. An evaluation program we could actually run

1. **Create independent reference material.** Start with a proposed 300 distinct feedback records, sampled across vehicles, source labels, feedback types, and available markets. Add a separate rare-need challenge set. Two trained annotators label needs and spans independently, then adjudicate; report agreement and residual disagreement. Keep sampling weights explicit if estimating corpus-level quality.
2. **Prevent leakage.** Split by feedback ID and near-duplicate text, not classification row. Keep test records out of examples, tuning, and synthetic augmentation. Use another vehicle/source as a transfer check; acknowledge sparse markets rather than manufacturing balance.
3. **Compare meaningful baselines.** B0: existing taxonomy, deterministic counts, and spreadsheet review. B1: a strong simple retrieval-and-drafting pipeline with the same model and inputs. B2: structured claims, explicit scoring, and source verification. B3: B2 plus uncertainty exploration and next-investigation selection. All get comparable input and compute/review budgets.
4. **Use ablations.** Remove provenance verification, duplicate handling, counter-evidence retrieval, or adaptive question selection one at a time. This identifies what creates value beyond model choice.
5. **Assess human decisions.** For the initial implementation, use independent team reviewers with a documented rubric. Counterbalance comparable, disjoint tasks across conditions, include verification time, and blind quality scoring. Record participant counts and roles in the internal evaluation. A later domain-practitioner study can test transfer to PM workflows; it is not a prerequisite for implementation.
6. **Test updates.** Prepare independently annotated meaningful changes and harmless controls. For the current undated data, use clearly labeled controlled replay. Do not portray it as historical forecast validation. Measure impact recall and review burden at multiple thresholds.
7. **Test active research with real answers.** Randomize or counterbalance research-selection policies under a fixed number of customer questions. Use held-out choice or task outcomes for assessment. Simulations can debug the policy, but simulator performance alone does not demonstrate customer value.
8. **Quantify uncertainty.** Report numerator/denominator, confidence intervals, effect sizes, and participant counts. Bootstrap at the independent feedback/participant level rather than treating correlated classification rows or judgments as independent.

A useful initial engineering aspiration is at least 95% supported material claims on a sufficiently sized held-out sample, alongside strong need recall. This is a proposed release criterion, not a published universal standard or an achieved result. Set an initial team-owned error budget and measure the speed/quality trade-off; later domain evaluation can refine it. Zero observed failures in 30 checks is still weak evidence for a very low production error rate.

We should optimize the combined process for **adequate decisions per PM-hour**, with explicit lower bounds on evidence quality and coverage. Later, the principal success criterion becomes **measured improvement in customer tasks and experiences attributable to decisions supported by the system**.

## 9. What deserves skepticism

- A source-exclusion button by itself is conventional sensitivity analysis. It becomes useful when it identifies a consequential uncertainty and the next action to resolve it.
- Prompting several AI personas to debate does not create independent evidence. If explored, compare it with one strong model at the same cost and judge the outputs against real sources.
- Synthetic customers can generate hypotheses and test questionnaire wording; their responses should not be counted as BMW demand. Empirical validation is necessary before any specialized simulation use.
- Fine-tuning is a possible later benefit of accumulated expert labels, not a prerequisite. First establish whether careful examples and verification meet requirements.
- A knowledge graph is not automatically correct or necessary. Evaluate it against filtered keyword/vector retrieval and relational provenance.
- Forecast-looking prose is not a forecast. Keep dates, forecast horizons, scenarios, and assumptions explicit.
- The absence of complaints is not evidence that an attribute is unimportant. Current owners are also a selected population; acquisition and lost-customer research require additional data.
- Faster drafting, agreeable PMs, stable rankings, or more generated ideas alone do not establish better products.

The research supports a precise direction: **use AI to turn BMW’s evidence into testable customer-need hypotheses, expose the decisions that depend on weak assumptions, and guide the next real investigation. Preserve what was learned so it compounds across vehicle generations.**
