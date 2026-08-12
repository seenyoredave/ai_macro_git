# AI Macro Corpus & Editorial Framework Project
## Canonical Purpose, Architecture, Methodology, and Handoff Statement

**Document version:** 1.1  
**Document role:** Project-level source of truth for mission, architecture, methodology, and handoff  
**Progress reporting:** Deliberately excluded. Domain progress belongs in the latest domain corpus JSON checkpoint, not in this document.  
**Intended use:** Hand this document to a successor chatbot/researcher together with the current AI Macro codebase and the latest domain JSON artifacts. The successor should be able to understand the mission and continue from the JSON state without relying on prior chat history.

---

# 1. Executive purpose

AI Macro is a largely deterministic research platform designed to track the U.S. AI economy from capital and public markets through compute and physical infrastructure, adoption, labor-market transmission, and broader economic outcomes. Its OpenAI component is intentionally narrow. The deterministic application acquires and structures evidence, performs calculations, preserves provenance, defines domain boundaries, validates generated commentary, and controls publication. The model is used only to reason over a bounded evidence packet and express that reasoning as concise analytical prose.

The purpose of the **AI Macro Corpus & Editorial Framework Project** is to improve the fluency, precision, analytical articulation, and evidentiary discipline of those model-generated summaries **without weakening that bounded architecture**.

The project is deliberately isolated from the production application. During corpus construction, the stable AI Macro code, production prompts, validators, publication workflow, and factual evidence pipeline are not to be modified merely because corpus research is underway. Academic literature is studied outside the application to build eleven independent domain language corpora. Each completed corpus is a durable research asset containing the language and reasoning knowledge extracted from its literature. Only after all eleven domain corpora are complete will the project derive a cross-domain editorial framework, construct evaluation material, test candidate implementations, and determine the final mechanism for integrating that framework into AI Macro.

The governing idea is:

> **Deterministic machinery builds the case. The model reads the case. The corpus teaches the model how a careful analyst should express what the case supports.**

---

# 2. Source-of-truth hierarchy for any successor

A successor must keep three different kinds of state separate.

## 2.1 This document: mission and invariant research rules

This document defines:

- what the corpus project is for;
- what the corpus is and is not;
- how academic works are admitted and analyzed;
- what "complete" means;
- why the eleven domains are built independently;
- what must remain outside the language model's factual authority;
- what is deferred until all eleven domain corpora are finished;
- how a handoff should be resumed.

This document intentionally contains **no domain-progress status**.

## 2.2 The supplied AI Macro codebase: current production behavior

The codebase is authoritative for the implementation that actually exists at the time of handoff. If a later code snapshot differs from implementation details described here, inspect the code and preserve the architectural principle rather than blindly restoring a constant that no longer matches the supplied code.

Especially important code areas in the supplied stable snapshot include:

- `analytics/read_evidence.py` — deterministic evidence extraction, domain boundaries, and model-facing evidence projection;
- `analytics/read_models.py` — structured model-output contracts;
- `analytics/read_prompts.py` — versioned Domain and Macro instructions;
- `analytics/read_generation.py` — OpenAI Responses API boundary;
- `analytics/read_validation.py` — deterministic validation/publication gate;
- `analytics/read_store.py` — attempt persistence and validated artifact promotion;
- `analytics/read_service.py` — orchestration;
- `analytics/read_context.py` — independent Current Context attachment;
- `analytics/reader_snapshot.py` — final Reader assembly;
- `developer/` — owner-only operations, diagnostics, and generation controls;
- `automation/` — bounded headless refresh, paid-call controls, run ledger, and publication decisions;
- `docs/COMMENTARY_ARCHITECTURE.md` — production commentary design;
- `docs/EDITORIAL_STYLE.md` — current Reader language contract.

## 2.3 Latest domain JSON artifacts: research progress

The latest JSON for each domain is authoritative for:

- what has been screened;
- what has been admitted;
- which sources have completed rhetoric extraction;
- atomic observations already captured;
- candidate queues;
- unresolved issues;
- next actions;
- version/integrity metadata.

**Do not infer project progress from this purpose document.** Read the latest domain JSON.

---

# 3. What AI Macro is

The supplied stable application describes AI Macro as a Streamlit research platform for tracking the U.S. AI economy from capital investment and public markets through physical buildout, adoption, labor markets, and broader economic outcomes.

The public/deployed application is designed around a **Reader mode**. Reader users inspect the retained research product; they do not refresh sources, write research state, or invoke OpenAI. Owner-only **Developer mode** contains refresh, diagnostic, commentary-generation, and maintenance controls.

The application is intended to remain useful when commentary is absent. The deterministic dashboard, retained evidence, and source provenance remain the product foundation.

---

# 4. The eleven analytical domains

The stable commentary evidence architecture contains exactly eleven domains, ordered along the AI-economy lifecycle:

1. **Market** (`market`)
2. **Finance** (`finance`)
3. **Compute** (`compute`)
4. **Data Centers** (`data_center`)
5. **Connectivity** (`connectivity`)
6. **Power** (`power`)
7. **Grid & Storage** (`grid_storage`)
8. **Water** (`water`)
9. **Adoption** (`adoption`)
10. **Workforce** (`workforce`)
11. **Economic Outcomes** (`economic_impact`)

The cross-domain product synthesis is labeled **AI Macro**.

The corpus research program mirrors these eleven domains. Each domain is completed independently before the project advances to framework construction.

---

# 5. Production commentary architecture that must be preserved

The current system separates deterministic research from probabilistic interpretation.

## 5.1 Deterministic responsibilities

AI Macro, not the language model, owns:

- source acquisition and refresh logic;
- historical and current retained data;
- source provenance and source labels;
- calculations and metric construction;
- deterministic domain context;
- evidence selection;
- fact construction and `fact_id` assignment;
- evidence boundaries;
- raw numeric values;
- evidence snapshot identity/hashing;
- numerical support checks;
- scope validation;
- generated-artifact state;
- publication eligibility and leases;
- Current Context/news discovery and source grounding;
- Reader visibility.

These responsibilities are **not** to be moved into the model as part of the corpus project.

## 5.2 EvidencePacket and model-facing projection

The deterministic layer builds a full `EvidencePacket` for each domain. Full packets retain raw values, source URLs, versions, and audit information used by deterministic validation and provenance.

Before a paid model request, each packet is projected into a smaller model-facing packet. In the supplied stable snapshot, the model receives the human-readable/display form of a fact plus its label, non-empty context, boundaries, importance, and source labels. Raw numeric values, source URLs, empty context fields, and packet versions are deliberately omitted from the model-facing projection.

The model therefore does not browse for facts and does not independently retrieve, clean, calculate, repair, or replace the deterministic evidence.

## 5.3 Domain Read request

All eleven model-facing domain packets are sent in one Structured Outputs request. For each domain, the model returns:

- one supported headline;
- three to four supported analytical sentences;
- one or more `fact_id` values supporting every generated sentence;
- an inference classification of `observation` or `interpretation`.

In the supplied stable snapshot, the Domain prompt version is `domain-read-3.0`.

## 5.4 Deterministic Domain Read validation

Generated Domain Reads do not automatically become publication material. Local validation checks include:

- required domain membership;
- sentence-level `fact_id` support;
- numerical grounding against model-visible evidence;
- unsupported numerical claims;
- domain-scope violations;
- schema requirements;
- word and sentence limits;
- punctuation/style gates;
- prohibited sentence shapes and prose patterns.

A critical rule is that hidden raw values are not valid support merely because the deterministic platform possesses them. A generated number must be grounded in evidence fields actually visible to the model.

## 5.5 Macro Read request

After Domain Reads validate, a second independent Structured Outputs request creates the cross-domain **AI Macro Read**.

The Macro request receives:

- the same underlying model-facing evidence packets; and
- compact domain orientation consisting of each validated domain thesis/headline and the fact IDs used by that Domain Read.

It does **not** receive the Domain Read prose paragraphs for reuse.

In the supplied stable snapshot, the Macro prompt version is `macro-read-4.0`.

The current Macro contract requires:

- selection of **4–6 distinct domains**;
- representation of at least **three lifecycle stages**;
- exactly **four analytical sentences**;
- rendering as **two short paragraphs**;
- a system-level thesis rather than a stitched domain catalog;
- at least two sentences integrating evidence from more than one selected domain;
- every selected domain contributing support;
- independent wording rather than recycled Domain Read prose.

The lifecycle stages currently described by the prompt are:

- capital/markets;
- physical buildout;
- adoption;
- workforce/economic outcomes.

## 5.6 Model configuration in the supplied stable snapshot

The supplied stable snapshot defaults to:

- model: `gpt-5.6-sol`;
- reasoning effort: `medium`.

These are implementation details, not corpus-methodology requirements. A successor working from a later codebase should inspect the current configuration rather than assuming these values remain fixed.

## 5.7 Artifact persistence and publication

Paid-generation attempts are persisted before validation in `openai_artifacts/attempts/`. Rejected attempts remain audit/debug material and do not become Reader publication material.

Only a fully validated result may be promoted to `openai_artifacts/current.json`.

The supplied stable architecture uses a 24-hour publication lease. Owner tooling can reapply the most recent validated Read for another lease period without another OpenAI call. Reapplication changes publication metadata only; it does not rewrite prose, retarget fact support, or change the original evidence snapshot.

Reader sessions do not call OpenAI.

## 5.8 Current Context/news is a separate layer

**Current Context is not model evidence for the Domain or Macro Read in the supplied architecture.**

It is an independently discovered and source-grounded recent-development layer attached after commentary generation. Its presence does not cause an OpenAI commentary call.

A successor must preserve this distinction:

- Domain/Macro commentary is synthesized from bounded analytical evidence;
- Current Context is recent sourced context at the presentation layer;
- a news development must not silently become causal evidence for a quantitative conclusion.

---

# 6. Existing production editorial contract

The production prompt and deterministic validator already impose a substantial editorial contract. The corpus project is intended to improve and empirically ground the language behavior **without discarding these safety properties**.

Current principles include:

- state a thesis rather than reciting dashboard metrics;
- interpret relationships among supplied facts;
- distinguish observation from interpretation;
- do not introduce new factual material;
- do not alter supplied values or dates;
- do not imply causality merely from association or coexistence;
- respect domain boundaries;
- use concrete subjects and strong verbs;
- prefer ordinary language when it preserves analytical meaning;
- keep one main analytical job per sentence;
- preserve logical hierarchy among funding, investment, construction, operating capacity, adoption, and outcomes;
- use contrast words only when the compared concepts are genuinely peers;
- use numbers selectively as evidence rather than as the organizing structure of the prose;
- avoid hype, trading-terminal language, catalyst language, rhetorical questions, monitoring instructions, and "what to watch" copy;
- use calibrated uncertainty only when evidence requires it;
- avoid semicolons;
- keep sentence complexity bounded;
- maintain sentence-level fact support.

The supplied stable style contract also targets readable analytical compression: Domain Reads usually occupy roughly 55–85 words and must remain at or below 95; the Macro normally occupies roughly 85–110 words and must remain at or below 120; individual analysis sentences are capped at 32 words; four or more commas in a Reader commentary sentence fail the style gate.

These production rules are a **baseline**, not the final corpus-derived framework. They remain insulated from corpus construction.

---

# 7. Why the corpus project exists

The bounded system is already capable of generating defensible, source-supported commentary. The next problem is higher-order editorial quality.

Tight safety constraints can produce prose that is correct yet formulaic: repeated contrast structures, repeated hedging formulas, repeated verbs, and a relatively narrow repertoire for expressing relationships among evidence.

The corpus project asks:

> **How do strong academic writers express findings, comparisons, magnitude, uncertainty, heterogeneity, mechanisms, nulls, boundary conditions, limitations, and implications when the evidence supports different levels of confidence?**

The project does **not** seek to make AI Macro sound like a journal article. Academic literature is being used to learn disciplined reasoning and rhetorical behavior. The final AI Macro voice must remain concise, readable, publication-appropriate, and adapted to the short Domain and Macro Read formats.

---

# 8. Project sequencing: eleven independent corpora first, framework second

The research program is intentionally split into **eleven independent domain corpora**.

Only one domain is actively completed at a time.

A domain is researched, audited, frozen, and delivered as a self-contained transfer artifact before the project advances to the next domain. This is a deliberate interruption-resilience strategy. A conversation interruption, model failure, tool failure, or future handoff must not compromise completed research or production code.

The required sequence is:

**Domain 1 complete → freeze/preserve → Domain 2 complete → freeze/preserve → … → Domain 11 complete → cross-domain framework construction → evaluation → production integration.**

The purpose of separating the domains is **not** to create eleven unrelated writing styles. Each domain supplies a distinct subject-matter environment in which the same underlying analytical-language machinery can be observed. Repetition across domains reveals general structure; variation across domains reveals topical and evidentiary conditioning.

No cross-domain editorial framework is to be finalized while domain research remains incomplete.

---

# 9. What “corpus” means in this project

This definition is essential.

The corpus is **not a repository of journal PDFs, books, or scraped text files**.

Academic works are **research inputs**.

The durable corpus is the **structured body of language, rhetoric, reasoning, evidence-calibration, and anti-pattern knowledge extracted from those works**.

Conceptually:

**academic literature → full-text analysis → atomic rhetorical observations → structured domain knowledge → completed domain corpus**

The final corpus should preserve enough durable provenance to identify and audit the underlying works, but the intellectual asset is the extracted knowledge—not copied source documents.

This design has four purposes:

1. it creates a compact artifact that another model can load directly;
2. it protects against conversation loss;
3. it avoids requiring the production model to reread an entire academic library;
4. it avoids turning the project into a redistribution archive for copyrighted literature.

---

# 10. Academic research population and admission requirements

Corpus construction is governed by **coverage and saturation**, not by a fixed paper quota.

For each domain, research begins with a deliberately diverse population of qualifying academic work and proceeds in small batches until the domain has adequate conceptual coverage and additional sources cease to produce materially new rhetorical or reasoning information.

A typical domain should begin with a planned minimum of approximately **25 carefully selected qualifying academic articles** and will commonly reach saturation in the range of **25–40 articles**. These numbers are planning guides, not automatic completion thresholds. A domain may require more if new evidence types or meaningful rhetorical structures continue to appear. A later domain may require fewer additional papers only when its own domain-specific coverage is adequate and the universal analytical machinery is already strongly reinforced across completed domains.

The article population should deliberately include:

- strong primary research;
- systematic reviews and literature reviews;
- meta-analyses where available and substantively appropriate;
- methodological diversity sufficient to expose differences in justified language strength.

The quality floor is:

- **Journal Impact Factor (JIF) ≥ 2.0**.

JIF is a **binary admission gate only**.

A paper in a JIF 20 journal receives no stylistic or intellectual preference over a paper in a JIF 2.1 journal merely because the journal score is higher. Once the threshold is cleared, inclusion is governed by:

- direct domain relevance;
- study design;
- methodological usefulness;
- full-text access;
- contribution to conceptual coverage;
- contribution to rhetorical or reasoning saturation.

The project must not inflate source volume with prestigious but substantively adjacent material.

## 10.1 Within-domain saturation

Within-domain saturation asks:

> **Are additional qualifying sources still teaching materially new domain-specific or generalizable analytical-language behavior?**

Research should be reviewed in batches, normally **five papers at a time** after the initial foundation is established. Each batch should be assessed for genuinely new atomic observations rather than raw word or phrase novelty.

A useful working saturation signal is reached when:

- the domain's core evidence concepts have substantive coverage;
- relevant study-design types are represented;
- no major domain-specific language problem remains thinly sampled; and
- **two consecutive batches of five qualifying papers each produce no more than two genuinely new generalizable atomic observations per batch**.

This is a decision rule, not a mechanical shortcut. If a later batch exposes an important new evidence structure, contradiction, boundary condition, or domain-specific rhetorical behavior, research continues until that novelty is understood and saturation is re-established.

## 10.2 Cross-domain saturation

Cross-domain saturation asks:

> **Are new domains still adding new universal analytical-language structures, or are they primarily reinforcing structures already observed elsewhere while adding domain-specific variation?**

The project must distinguish between:

- **new universal machinery** — a genuinely new general rule of analytical reasoning or grammatical structure;
- **cross-domain reinforcement** — independent evidence that an existing pattern persists in another subject-matter environment;
- **domain-conditioned variation** — topical vocabulary, relationship structures, and stylistic behavior specific to the domain;
- **evidence-conditioned variation** — wording that changes because the underlying evidence type or identification strength changes.

As domains accumulate, increasing reinforcement and decreasing universal novelty are expected signs that the framework's general analytical grammar is stabilizing. This does not remove the need for each domain to achieve its own conceptual and rhetorical coverage.

---

# 11. Domain relevance is a hard requirement

An article counts toward a domain only when its substantive research question is relevant to the evidence and relationships that the corresponding AI Macro domain actually asks the model to interpret.

A paper may be an excellent **rhetoric anchor** without qualifying as a core domain source.

For example, an algorithmic stock-prediction paper may contain useful language about model comparison but still fail the Market domain's core relevance test if its actual research question is forecasting-system accuracy rather than breadth, concentration, cross-sectional structure, crowding, participation, or market-pressure/volatility relationships.

Candidate states used by the corpus process may include:

- `core_candidate` — substantively close enough to potentially be admitted after all gates;
- `supporting_candidate` — useful and relevant but indirect;
- `rhetoric_anchor` — useful language/method example but not substantively central to domain coverage;
- `exclude_core` — not appropriate for the completed domain corpus.

Rhetoric anchors may contribute to general language learning, but they must not substitute for adequate coverage of the domain's actual evidence concepts.

No inherited item is grandfathered into a final corpus merely because an earlier model labeled it admitted.

---

# 12. Full-text requirement and honesty states

Abstract-only records do not count.

Search snippets do not count.

Publisher previews do not count.

A citation does not count as ingestion.

A qualifying article counts only when the accessible version permits review of all substantive prose needed to understand how the authors construct, support, qualify, and limit their argument.

The normalized full-text audit standard is:

> **For an article to count, the accessible version must permit review of all substantive prose sections: abstract/introduction or framing, theory/literature where present, methods/design, results, discussion/implications, and limitations/conclusion. References, equations, tables, figures, and appendices are inspected when needed to understand claims, but are not themselves treated as language-learning prose.**

The project distinguishes five honesty states:

1. **found**
2. **screened**
3. **full text accessed**
4. **fully analyzed**
5. **admitted**

These terms are not interchangeable.

A successor must never say “ingested,” “read,” or “analyzed” merely because a work was discovered, cited, indexed, or previewed.

---

# 13. Academic texts/books

Each domain should normally include **1–2 excellent academic texts** chosen for sustained analytical prose rather than for citation prestige.

The purpose of longer-form texts is different from the purpose of journal articles. They provide extended examples of how a rigorous writer:

- introduces an analytical problem;
- develops an argument across paragraphs;
- explains quantitative or technical relationships;
- compares competing explanations;
- qualifies uncertainty;
- synthesizes multiple findings;
- handles contradictory evidence;
- distinguishes result from mechanism;
- translates evidence into significance;
- closes an argument without overstating it.

The normal sampling target is **5–10 substantial analytical passages per text**, with approximately **10–15 passages per domain**. A passage should ordinarily contain enough continuous prose to expose sustained rhetorical structure—roughly **500–1,500 words** where legitimate access permits it.

These passages are **analysis units, not corpus deliverables**. The durable corpus stores the structured observations learned from them, not copied copyrighted text.

Long-form sampling is complete when the domain has adequate coverage of sustained explanatory and argumentative behavior and additional passages cease to add materially new language structures.

The same honesty rule applies. Locating a book, table of contents, excerpt, preview, abstract, or review is not equivalent to analyzing the relevant passage. A proprietary or paywalled academic text may be included only to the extent that legitimate access is actually available for analysis.

---

# 14. What is extracted from each admitted work

Each admitted work is analyzed for **language and reasoning behavior**, not merely for its substantive conclusion.

The normalized rhetoric schema should capture at least:

- `summary_architecture`
- `evidence_order`
- `finding_language`
- `quantitative_presentation`
- `causal_calibration`
- `uncertainty_and_modality`
- `heterogeneity_and_regime`
- `null_result_language`
- `boundary_conditions`
- `limitations`
- `implications`
- `sentence_relations`
- `anti_patterns`
- `atomic_observations`

The analysis should ask questions such as:

- What deserves the lead?
- How is the principal finding separated from supporting magnitude?
- Which verbs are used for directly observed findings?
- Which verbs signal interpretation rather than observation?
- When does wording shift from description to association, prediction, quasi-causal inference, or causal claim?
- How are mechanisms introduced?
- How are untested mechanisms distinguished from demonstrated results?
- How are null results stated?
- How are mixed or contradictory results preserved?
- How is heterogeneity handled?
- How are regime, horizon, subgroup, geography, or method boundaries integrated into the main claim?
- When is statistical significance distinguished from economic/material significance?
- How many numbers are necessary before prose becomes a metric recital?
- How are limitations attached to the claims they constrain?
- How do authors move from finding to implication?
- How do systematic reviews differ rhetorically from primary papers?
- How do meta-analyses distinguish pooled results from heterogeneity and study-quality limitations?
- Which rhetorical behaviors are strong examples?
- Which are anti-patterns that should explicitly not be copied?

---

# 15. Atomic observations are preserved; premature rules are not

The corpus must retain observations at a granular enough level that a later framework can be audited.

A successor must resist turning the first recurring pattern into a universal instruction.

A completed domain may reveal, for example, that:

- one evidence-ordering pattern is typical for causal studies;
- another is stronger for descriptive work;
- another is needed when heterogeneity is the principal finding;
- a different formulation is appropriate for null evidence;
- the strength of a mechanism statement depends on identification design.

Collapsing those distinctions prematurely into “always do X” destroys information.

Therefore:

- **atomic observations** are the primary stored knowledge;
- **working domain syntheses** may describe recurring patterns;
- those syntheses remain descriptive while the domain is under construction;
- observations should record the conditions under which a language behavior is appropriate;
- frequency alone is not treated as proof that a rhetorical behavior is desirable;
- prescriptive framework rules are deferred until all eleven corpora are complete.

## 15.1 The three learning layers

The corpus program is designed to separate three forms of learned behavior.

### Universal analytical language

This is the general machinery that survives across subject matter. Examples include:

- result → evidence → interpretation ordering;
- observation versus inference;
- causal calibration;
- null-result precision;
- qualification and modality;
- conditionality and boundary conditions;
- heterogeneity handling;
- statistical versus material significance;
- mechanism separation;
- evidence hierarchy;
- numerical economy;
- comparison structure;
- limitation placement;
- implication discipline;
- sentence and paragraph architecture;
- synthesis rather than enumeration.

A pattern earns consideration as universal when it recurs independently across domains and remains appropriate after study design and evidentiary strength are taken into account.

### Domain-conditioned language

Each domain supplies topical vocabulary and characteristic analytical relationships. Domain-conditioned language determines which nouns, verbs, comparisons, mechanisms, and conceptual structures are natural for the evidence being summarized.

This layer creates topical fluency without creating eleven unrelated personalities.

### Evidence-conditioned expression

Wording must also respond to the kind and strength of evidence actually available. Descriptive evidence, observational associations, predictive relationships, quasi-experimental estimates, causal designs, benchmarks, systematic reviews, and meta-analyses do not justify identical predicates or interpretive strength.

The eventual model behavior can therefore be understood conceptually as:

> **universal analytical grammar × domain-conditioned language × evidence-conditioned expression = appropriate analytical prose**

The corpus should preserve enough structure to allow the final framework to implement this interaction rather than relying on phrase frequency or generic academic imitation.

---

# 16. Anti-patterns are part of the corpus

An admitted academic paper is not assumed to be rhetorically perfect.

A paper can contain valuable evidence and strong analytical writing while also overstating causality, overgeneralizing a mechanism, flattening heterogeneity, mishandling a null, or drawing an implication stronger than the design supports.

Those cases are useful research material and should be retained as **negative language/reasoning observations**.

Examples of the types of anti-pattern the project is designed to recognize include:

- converting predictive/Granger temporal evidence into structural causal wording;
- allowing an observational mediation pattern to become a fully identified causal mechanism;
- confusing behavior during an event with evidence of triggering the event;
- rewriting “no evidence of X” as “evidence that not-X is true”;
- using model complexity as justification for stronger causal language;
- allowing a subgroup, horizon, geography, or regime result to become a universal claim;
- allowing policy or business implications to exceed the certainty of the empirical design.

The final framework should learn from disciplined examples **and** from explicit rejection of language that outruns the evidence.

---

# 17. Domain completion standard

“Complete” is intentionally strict and is determined by **coverage plus saturation**, not by reaching a predetermined paper count.

A domain may be labeled **COMPLETE** only when:

- the domain's core evidence concepts have substantive representation;
- the admitted population contains deliberate study-design diversity, including primary research and appropriate synthesis literature;
- the domain has normally drawn from at least approximately 25 carefully selected qualifying articles unless the available literature genuinely cannot support that breadth;
- within-domain rhetorical saturation has been demonstrated through batch-level novelty tracking;
- no major domain-specific language or reasoning problem remains materially under-sampled;
- 1–2 qualifying academic texts have contributed approximately 10–15 substantial long-form analytical passages where legitimate access permits;
- every counted article clears JIF ≥ 2.0;
- every counted article is directly relevant to the domain or is explicitly classified as a non-core rhetoric anchor;
- every counted article has verified whole-text access;
- every admitted article has a completed normalized rhetoric extraction;
- durable provenance is preserved;
- duplicates and metadata inconsistencies are audited;
- source-derived observations are stored at sufficient granularity for later audit;
- working observations have been aggregated into a domain-level descriptive synthesis;
- unresolved or contested rhetorical patterns are preserved rather than falsely harmonized;
- the domain records which observations appear domain-specific and which reinforce emerging cross-domain analytical machinery;
- the package is internally auditable;
- a successor can load the artifact and understand what was done without relying on the original conversation;
- integrity/completeness checks pass;
- the word `COMPLETE` is used only after those conditions actually hold.

A partial checkpoint may be valuable, but it must remain clearly labeled **working**, **in progress**, or equivalent.

---

# 18. Handoff and interruption-resilience strategy

This project is explicitly designed for realistic interruption.

During work on a domain, versioned JSON checkpoints should be created periodically. A checkpoint should contain enough state that a successor can continue without reconstructing previous reasoning from chat history.

A checkpoint should preserve, at minimum:

- mission boundaries relevant to the corpus;
- domain scope;
- completion contract;
- normalized extraction schema;
- source registry/candidates and their screening states;
- inherited material and its provenance status where applicable;
- official admissions;
- atomic rhetoric observations;
- anti-pattern observations;
- working descriptive synthesis;
- candidate queue;
- unresolved verification issues;
- progress counts;
- explicit next action;
- explicit prohibitions;
- artifact version;
- integrity metadata such as a checksum where useful.

When a domain becomes complete, the completed version should be frozen. Later corrections should create a new version rather than silently rewriting the historical artifact.

The JSON files are therefore the **continuity layer** of the research project.

---

# 19. Research scopes for the eleven domains

The following scopes are derived from the stable evidence architecture. They define what each corpus ultimately needs to teach the model to reason about. They are not intended as rigid search strings; academic discovery should expand intelligently within these substantive boundaries.

## 19.1 Market

### Production evidence concepts

- AI Equity Index;
- average sector trading pressure;
- share of covered companies with positive one-year returns;
- median one-year return;
- equal-weight one-year return;
- top-ten share of covered market value;
- effective firm count;
- count of strong sectors;
- count of high-pressure/crowded sectors.

### Core corpus themes

- market breadth and participation;
- concentration and leadership;
- equal-weight versus concentrated/capitalization-weighted performance;
- cross-sectional return dispersion;
- crowding/herding;
- sector breadth;
- volatility, volume, momentum/pressure, and regime dependence;
- investor participation/attention where it informs these relationships.

### Production boundaries

- covered-company market measures are not the entire U.S. equity market;
- concentration and breadth describe participation; they do not establish causality;
- forecasting/trading-model accuracy is not by itself a core Market research question.

## 19.2 Finance

### Production evidence concepts

- borrower strain;
- lender strain;
- operating cash-flow coverage of current CapEx;
- cash reserves relative to current CapEx;
- forward commitments relative to current CapEx;
- debt-financing pulse;
- Chicago Fed National Financial Conditions Index and its recent change;
- corporate-bond market distress;
- mature technology-fund DPI, RVPI, TVPI, and realized share;
- mature fund records;
- provider AI revenue/run-rate and backlog disclosures.

### Core corpus themes

- funding capacity;
- internal versus external financing;
- capital commitments;
- cost and availability of capital;
- borrower/lender conditions;
- debt and credit conditions;
- project and infrastructure finance;
- private-capital realization;
- financing constraints on large-scale investment;
- commercialization evidence as financing support without equating provider revenue to economy-wide AI ROI.

### Production boundaries

- covered issuer funding metrics do not represent all AI investment;
- private-fund NAV is not realized cash;
- provider revenue demonstrates paid demand but not economy-wide return on AI investment.

## 19.3 Compute

### Production evidence concepts

- computer/peripheral equipment output growth;
- semiconductor/electronic-component output growth;
- manufacturing capacity utilization;
- information-processing investment growth;
- announced U.S. compute-manufacturing project capex and sites;
- critical AI supply-chain layers covered by domestic projects;
- core-AI manufacturing sites and investment;
- reported available compute;
- reported serving-unit-cost reductions.

### Core corpus themes

- semiconductor and compute manufacturing;
- industrial capacity and utilization;
- bottlenecks and supply-chain layers;
- manufacturing investment;
- announced versus operational capacity;
- compute availability;
- performance/cost/efficiency when tied to macro-industrial buildout;
- scaling economics.

### Production boundaries

- announced projects are commitments, not current operating capacity;
- provider serving-cost disclosures must not be generalized to the entire market.

## 19.4 Data Centers

### Production evidence concepts

- operating sites in available project records;
- development sites;
- development-to-operating ratio;
- tracked active pipeline sites;
- published capacity associated with development sites;
- published capacity associated with operating sites;
- share of active campus records with canonical published capacity.

### Core corpus themes

- data-center buildout;
- development pipelines;
- campus scale;
- siting;
- construction and commissioning;
- disclosed versus energized capacity;
- geographic concentration;
- project-pipeline interpretation.

### Production boundaries

- the project registry is not a national census of the U.S. data-center fleet;
- published MW describes disclosed project scale, not energized load.

## 19.5 Connectivity

### Production evidence concepts

- active U.S. internet exchange points;
- reported IXP membership;
- U.S. international submarine cable systems and catalog entries;
- future/current-year cable entries;
- public interconnection facilities/coverage;
- federally supported middle-mile fiber;
- states with data-center development but limited visible public interconnection depth;
- campuses screened for connectivity context;
- large population centers with an IXP.

### Core corpus themes

- interconnection;
- internet exchange points;
- peering;
- submarine cable connectivity;
- middle-mile networks;
- data-center network access;
- route diversity;
- public versus private connectivity visibility;
- local usable capacity versus national route totals.

### Production boundaries

- public IXP and cable records do not capture every private route or bilateral connection;
- national route totals do not establish usable capacity at a specific campus.

## 19.6 Power

### Production evidence concepts

- total retail electricity-demand growth;
- commercial electricity-demand growth;
- net planned generation additions through the pipeline horizon;
- retail electricity-price growth;
- published capacity associated with large-load campus records;
- planned-generation pipeline end year.

### Core corpus themes

- electricity demand from large loads;
- commercial and total demand growth;
- generation buildout;
- supply additions;
- electricity prices;
- large-load integration;
- planned versus operating generation;
- power supply as an infrastructure constraint.

### Production boundaries

- planned generation is not equivalent to capacity placed in service;
- interconnection-queue maturity belongs to Grid & Storage rather than Power.

## 19.7 Grid & Storage

### Production evidence concepts

- active interconnection queue;
- advanced-stage queue share;
- storage capacity in the active queue;
- historical operational and withdrawal shares;
- request-to-commercial-operation time;
- queue capacity with draft/executed interconnection agreements;
- extreme-conditions reserve margins;
- operating storage duration and four-hour-plus share;
- electric-power construction growth.

### Core corpus themes

- interconnection queues;
- project attrition;
- connection delays;
- transmission constraints;
- reserve margins;
- grid reliability;
- storage duration;
- deliverability;
- developer interest versus usable near-term capacity.

### Production boundaries

- queue capacity measures developer interest, not near-term supply;
- storage duration can address short peaks but does not remove transmission or interconnection constraints.

## 19.8 Water

### Production evidence concepts

- national withdrawals by major use;
- thermoelectric withdrawals and consumption;
- mapped data-center facilities;
- facilities with direct water evidence;
- facilities with quantified withdrawal/consumption records;
- direct-evidence coverage;
- states with drought exposure;
- published data-center capacity in drought-exposed mapped states.

### Core corpus themes

- water withdrawal versus consumption;
- cooling requirements;
- data-center water use;
- local versus state/national water conditions;
- drought;
- water rights and supply constraints;
- facility disclosure gaps;
- competition among major water uses.

### Production boundaries

- state drought conditions do not establish campus-level water availability;
- sparse facility disclosure prevents a national estimate of data-center water use.

## 19.9 Adoption

### Production evidence concepts

- businesses reporting current AI use;
- businesses expecting AI use within six months;
- expected-minus-current business-use gap;
- change in current business AI use;
- consumer overall, personal, work, active-week, and daily use;
- change in consumer use;
- sector coverage and leading-sector use;
- reported consumer subscribers;
- implied subscriber share;
- reported paying business users and enterprise seats.

### Core corpus themes

- diffusion and adoption;
- stated intent versus deployed use;
- consumer versus work/business use;
- frequency and intensity of use;
- sector heterogeneity;
- paid versus unpaid adoption;
- enterprise adoption;
- diffusion curves and persistence.

### Production boundaries

- expected business use is stated intent, not deployed use;
- provider subscriber counts are not a national paid-adoption rate.

## 19.10 Workforce

### Production evidence concepts

- breadth of positive employment growth across tracked AI-linked channels;
- breadth of positive real-earnings growth;
- strongest and weakest tracked employment channels;
- layoff and opening rates;
- occupation count in the static exposure benchmark;
- median software-adjusted LLM task exposure;
- share of benchmark occupations with high exposure.

### Core corpus themes

- task exposure;
- employment adjustment;
- job creation and loss;
- vacancies and layoffs;
- wages and real earnings;
- occupational heterogeneity;
- technology exposure versus realized labor-market outcomes;
- substitution and complementarity when evidence identifies them.

### Production boundaries

- task-exposure estimates describe work AI could affect; they do not measure jobs lost or automated;
- tracked AI-linked channels are not the entire labor market.

## 19.11 Economic Outcomes

### Production evidence concepts

- nonfarm-business productivity growth;
- real output growth;
- real hourly compensation growth;
- unit labor-cost growth;
- information-processing investment growth;
- productivity and real-compensation changes since 2020;
- productivity-minus-compensation gap;
- labor-share change;
- median real weekly earnings growth;
- cross-group real-earnings growth spread;
- provider AI/cloud commercialization measures.

### Core corpus themes

- productivity;
- output;
- labor compensation;
- labor share;
- unit labor costs;
- information/technology investment;
- distributional effects;
- realized commercial value;
- firm/provider commercialization versus economy-wide impact.

### Production boundaries

- economy-wide productivity/output measures do not identify AI as the cause;
- provider revenue does not establish economy-wide return on AI investment.

---

# 20. What happens after all eleven corpora are complete

Only after all eleven domain corpora are completed and frozen should the project enter framework construction.

The framework phase should treat the completed corpus as evidence of a layered learning system rather than as eleven separate style manuals.

It should:

1. compare the eleven completed corpora;
2. identify analytical-language behaviors that recur independently across domains;
3. use cross-domain recurrence to determine the **universal analytical grammar**;
4. identify **domain-conditioned language** that provides topical vocabulary, relationship structures, and stylistic flux without altering the common reasoning discipline;
5. identify **evidence-conditioned expression** that maps study design and evidentiary strength to justified wording strength;
6. distinguish universal principles from domain-specific or evidence-specific exceptions;
7. map evidentiary strength to finding verbs, mechanism language, qualification, and implication strength;
8. define acceptable causal vocabulary and prohibited causal upgrades;
9. define uncertainty and qualification behavior;
10. define handling of nulls, mixed evidence, and contradictory evidence;
11. define quantitative-evidence ordering and numerical economy;
12. define heterogeneity, regime, subgroup, horizon, and boundary-condition behavior;
13. define implication language;
14. define sentence and paragraph architectures appropriate to AI Macro's short-form Reads;
15. define domain-conditioned lexical and relational guidance;
16. define anti-patterns;
17. construct owner-approved gold-standard examples;
18. construct rejected examples with explicit failure reasons;
19. build an evaluation/regression suite;
20. test candidate prompt/framework revisions against fixed representative AI Macro evidence packets;
21. integrate only after the new framework improves fluency without weakening factual grounding, scope discipline, or deterministic validation performance.

The framework should emerge from **convergence and conditional variation**. A behavior that appears frequently is not automatically a rule; the project must understand whether its appropriateness depends on evidence design, domain, horizon, subgroup, or rhetorical function.

Academic style is therefore an **input to the editorial framework**, not the final Reader voice.

---

# 21. Final integration intent

The ultimate objective is to give the AI Macro model a tested editorial framework that reflects the accumulated lessons of all eleven corpora while leaving factual authority bounded by the deterministic application.

The final implementation mechanism is deliberately **not fixed yet**. Depending on what the completed research supports, it may include some combination of:

- a distilled system/developer prompt specification;
- structured editorial rules;
- evidence-strength-to-language mappings;
- curated positive/negative examples;
- a compact machine-readable editorial corpus;
- retrieval of domain-specific language guidance;
- deterministic style/evidence validators;
- offline evaluation datasets.

The academic corpus must **not** become a new source of live factual claims about the current AI economy. Its role is to teach language and reasoning discipline. Runtime factual content must still come from the bounded AI Macro evidence packet.

The intended final architecture remains:

**deterministic current evidence → bounded model reasoning guided by corpus-derived editorial framework → deterministic validation → publication**

with **Current Context** remaining a separately grounded recent-development layer unless the owner explicitly redesigns that architecture later.

---

# 22. What the final framework must not do

A successor must not interpret “improve the model” to mean “give the model more factual authority.”

The final framework must not:

- ask the model to browse for missing evidence;
- ask the model to clean bad upstream data;
- ask the model to calculate facts that belong in deterministic code;
- let the model repair unsupported numbers by inventing alternatives;
- let academic literature become a substitute for current-source evidence;
- allow news to become hidden analytical evidence;
- remove sentence-level evidence support;
- weaken domain boundaries;
- allow stylistic elegance to outrank factual discipline;
- make a model judge the sole production publication gate;
- require live access to the full academic literature in order to generate each Read.

If a proposed corpus/framework change requires any of the above, it violates the core project mission unless the owner explicitly changes that mission.

---

# 23. Successor startup protocol

A new chatbot/researcher receiving the project should proceed in this order.

## Step 1 — Read this document completely

Do not begin research based only on filenames or a previous chatbot's status message.

## Step 2 — Inspect the supplied codebase

Confirm the current production architecture, especially:

- domain order;
- current evidence facts and boundaries;
- model-facing projection;
- current prompt versions;
- current validator behavior;
- Current Context separation;
- any material code changes relative to the implementation described here.

Do not modify production code merely to continue corpus research.

## Step 3 — Locate the latest domain JSON checkpoint(s)

Use filename/version plus internal metadata/checksum where available. The latest JSON is the authoritative progress record.

Read its:

- `status`;
- completion contract;
- schema version;
- official admissions;
- candidates;
- legacy-provenance warnings;
- working synthesis;
- `handoff.next_action` or equivalent;
- explicit `do_not_do` instructions.

## Step 4 — Determine the single active domain

Continue that domain only unless the latest artifact explicitly states it is complete and the next domain should begin.

Do not create parallel half-finished domain corpora.

## Step 5 — Preserve admission discipline

For every new article, keep the states separate:

**found → screened → full text accessed → fully analyzed → admitted**.

Verify direct domain fit, JIF ≥ 2.0, whole-text access, durable provenance, and normalized rhetoric extraction before formal admission.

## Step 6 — Track coverage and novelty

Maintain explicit coverage of the active domain's evidence concepts and study-design types. After the initial foundation, analyze new literature in batches, normally five papers at a time, and record how many genuinely new atomic observations each batch contributes.

Do not count mere synonyms, repeated phrasing, or topic-specific nouns as new analytical machinery.

## Step 7 — Preserve raw observations

Append atomic rhetorical observations and anti-patterns with the conditions that make them appropriate or inappropriate. Do not prematurely rewrite accumulated observations into universal framework rules.

## Step 8 — Test within-domain saturation

A domain approaches saturation when core conceptual coverage is adequate and two consecutive five-paper batches each yield no more than two genuinely new generalizable atomic observations. If a later batch exposes an important new structure or contradiction, continue until the novelty is resolved and saturation is restored.

## Step 9 — Create periodic versioned checkpoints

Update the working JSON sufficiently often that a conversation failure does not erase meaningful work. Never label a checkpoint COMPLETE before it satisfies the full completion contract.

## Step 10 — When a domain is complete, freeze it

Produce the independent completed corpus artifact, record integrity metadata, and do not silently rewrite it afterward. Corrections require a version increment.

## Step 11 — Advance to the next domain and track cross-domain saturation

Repeat the same process for the next domain. Record whether newly observed structures are:

- genuinely new universal analytical machinery;
- reinforcement of an existing cross-domain pattern;
- domain-conditioned language;
- evidence-conditioned variation.

Do not reduce a later domain's research solely because the universal layer is mature; its own topical and evidentiary coverage must still be adequate.

## Step 12 — Build the framework only after all eleven are complete

Do not progressively mutate production prompts during corpus acquisition.

---

# 24. Non-negotiable honesty protocol

This project requires unusually explicit state labeling because the research scope is too large for vague claims.

A successor must be able to answer precisely:

- Was the work merely found?
- Was it screened for domain relevance?
- Was JIF verified?
- Was whole text genuinely accessible?
- Was the whole substantive article reviewed?
- Was rhetoric extraction completed?
- Was the item formally admitted?
- Is an observation independently verified in the current research session or merely inherited from an earlier chatbot?

Inherited work is useful, but inherited claims must remain labeled as inherited until independently verified if verification matters to the current decision.

Never use “complete,” “ingested,” “verified,” or “read” as convenience language when the corresponding condition has not been met.

---

# 25. Research-quality principles

The following principles govern corpus construction across all domains.

## 25.1 Relevance before volume

Source count never outranks domain fit. A smaller set of directly relevant, deeply analyzed works is preferable to a larger set padded with adjacent literature.

## 25.2 Saturation before accumulation

Continue research while additional sources produce meaningful new analytical-language knowledge. Stop accumulating for its own sake once conceptual coverage is adequate and novelty has stabilized under the saturation protocol.

## 25.3 Cross-domain recurrence is evidence

Repeated analytical structures observed independently across domains are candidates for universal grammar. Domain-specific vocabulary or evidence-specific wording should remain conditioned rather than being flattened into universal rules.

## 25.4 JIF is a floor, not a ranking

Once JIF ≥ 2.0 is satisfied, selection should be based on fit and analytical usefulness.

## 25.5 Whole argument, not abstract prose

The point of the project is to learn how careful writers move from framing through evidence to interpretation and qualification. Abstract-only analysis cannot supply that.

## 25.6 Study-design diversity matters

Primary studies, systematic reviews, and meta-analyses teach different rhetorical disciplines and should not be flattened into one pool.

## 25.7 Methods constrain language

Language strength should be studied in relation to what the research design actually identifies.

## 25.8 Heterogeneity is information

Do not treat subgroup, regime, horizon, or geographic variation as noise merely because it complicates a simple thesis.

## 25.9 Nulls require precision

“No evidence of X” and “evidence that X is absent” are not interchangeable.

## 25.10 Materiality differs from significance

Statistical significance should not automatically become economic or practical importance.

## 25.11 Mechanisms must earn their verbs

A mechanism can be plausible, consistent with evidence, mediated statistically, or causally identified. Those states require different language.

## 25.12 Limitations belong near the claims they limit

Generic caveat paragraphs are less useful than claim-specific boundaries.

## 25.13 Strong research can contain weak rhetoric

Record overstatement as an anti-pattern rather than copying it because it appeared in a qualified journal.

---

# 26. Expected structure of a domain corpus JSON

Exact schemas may evolve, but a successor should preserve the following conceptual layers.

## 26.1 Identity and schema

- artifact type;
- domain;
- schema version;
- artifact version;
- status;
- timestamps;
- checksum/integrity metadata.

## 26.2 Mission boundary

- production code is not being modified;
- academic works are inputs, not deliverables;
- final framework is deferred;
- corpus is for language/reasoning behavior, not current factual evidence.

## 26.3 Domain scope

- production evidence concepts;
- boundaries;
- core research themes;
- explicit non-goals.

## 26.4 Completion contract

- conceptual coverage requirements;
- within-domain saturation protocol and batch novelty history;
- academic-text/passages coverage;
- JIF floor;
- required study-type diversity;
- full-text requirement;
- honesty states;
- cross-domain classification fields where applicable;
- definition of COMPLETE.

## 26.5 Source/candidate registry

- durable identifier/DOI;
- bibliographic metadata;
- study type;
- screening state;
- JIF status/source;
- full-text status/source;
- inclusion rationale;
- rejection or deferral reason where relevant.

## 26.6 Official admissions

Each admitted work should contain its complete normalized rhetoric extraction and durable provenance.

## 26.7 Atomic rhetoric knowledge

Preserve observations at a level that later allows aggregation by:

- evidence type;
- study design;
- rhetorical function;
- strength of finding;
- uncertainty;
- heterogeneity;
- boundary condition;
- positive pattern versus anti-pattern;
- universal candidate versus cross-domain reinforcement;
- domain-conditioned language;
- evidence-conditioned expression.

## 26.8 Working domain synthesis

This may describe repeated patterns but must remain explicitly **descriptive, not final framework** until all eleven corpora are completed.

## 26.9 Handoff instructions

State exactly what a successor should do next and what must not be done.

---

# 27. Relationship among corpus, framework, and production prompt

These three objects must remain conceptually distinct.

## Corpus

**Everything the academic research taught us**, preserved with enough structure and provenance to audit the lessons. The corpus contains atomic observations, conditions, anti-patterns, domain-specific language knowledge, and evidence about which analytical structures recur across domains.

## Framework

The **operational editorial standard** derived only after comparing the eleven completed corpora. It should encode the interaction of:

- universal analytical grammar;
- domain-conditioned language;
- evidence-conditioned expression.

## Production implementation

The mechanism by which the tested framework influences actual model generation inside AI Macro—prompt rules, examples, retrieval, validators, or another implementation chosen after evaluation.

A successor must not collapse these stages.

---

# 28. The final evaluation requirement

No framework revision should be promoted because it produces one attractive sample.

Before production integration, the project should create a stable evaluation set from representative historical AI Macro evidence packets and score candidate implementations for both **hard validity** and **editorial quality**.

Hard-validity dimensions should continue to include:

- factual/evidence support;
- number grounding;
- scope compliance;
- domain membership;
- causal discipline;
- schema/length/style gates.

Editorial dimensions should include, as supported by the completed corpora:

- thesis quality;
- evidence hierarchy;
- readability;
- sentence fluency;
- syntactic/vocabulary variation without forced synonymy;
- calibrated uncertainty;
- numerical economy;
- null precision;
- heterogeneity handling;
- mechanism separation;
- limitation placement;
- implication discipline;
- avoidance of formulaic contrast and repeated safe templates.

Evaluation should occur offline or in controlled development workflows. The project should not add an unnecessary live model-judge dependency to Reader publication simply to score style.

---

# 29. Security and artifact hygiene

A handoff archive should contain the code and research artifacts needed to continue the project, but it should not unnecessarily include credentials, local virtual environments, caches, or other machine-specific debris.

In particular:

- do not expose API keys in handoff documents or corpus files;
- do not persist credentials inside OpenAI artifacts;
- exclude `.streamlit/secrets.toml` from future research handoff packages even if Git ignores it;
- exclude `.venv` and caches from handoff archives unless there is a specific reproducibility reason to include them;
- preserve code version identity and corpus artifact checksums when possible.

---

# 30. Final statement of intent

The AI Macro Corpus & Editorial Framework Project exists to create a **durable, auditable editorial intelligence layer** for a bounded analytical system.

The academic literature is not being collected so the production model can quote it, retrieve facts from it, or behave like an autonomous researcher. It is being studied to learn how strong analytical writing calibrates language to evidence.

The project treats linguistic learning as layered:

- **cross-domain recurrence** reveals the general logic, grammar, evidence ordering, qualification, and rhetorical structures of disciplined analytical prose;
- **domain-conditioned variation** supplies the topical vocabulary, relationship structures, and stylistic flexibility required to speak naturally about each part of the AI economy;
- **evidence-conditioned variation** determines how strongly the model may state a finding, mechanism, null, implication, or boundary based on what the underlying evidence actually supports.

The eleven domain corpora preserve that learned knowledge independently and recoverably. Each domain is researched until conceptual and rhetorical saturation is demonstrated. The cross-domain framework is built only after the research base is complete and is then evaluated against the actual AI Macro evidence architecture.

The production model should ultimately receive **current facts from AI Macro and language intelligence from the framework**. The corpus must never become a competing factual authority.

Only after the framework proves that it can improve fluency and articulation **without increasing unsupported inference or weakening deterministic controls** should it be integrated into production.

The final product should therefore remain recognizably AI Macro:

- deterministic where facts, calculations, provenance, and publication authority matter;
- model-assisted where synthesis and language genuinely add value;
- governed by a general analytical grammar that is empirically supported across domains;
- fluent in the vocabulary and relational structures of the active domain;
- calibrated to the type and strength of evidence actually supplied;
- explicit about uncertainty and scope;
- concise enough for a Reader;
- analytically richer than a metric recap;
- resistant to hallucination, causal overreach, and fashionable prose;
- recoverable if any individual chatbot session fails.

If a successor remembers only one principle, it should be this:

> **AI Macro supplies the evidence. The corpus teaches how disciplined analytical language behaves. Cross-domain recurrence supplies the general grammar; domain and evidence conditions supply the appropriate variation.**

