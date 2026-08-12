# Editorial style

This is the public-language contract for AI Macro. The platform should read like a careful research product, not like a pitch deck or a generated summary.

## Core rule

Use the simplest language that preserves the analytical meaning.

A title should tell the reader what the object shows. A subtitle should tell the reader what is being compared, measured, or bounded. Neither should exist just to make the product sound sophisticated.

The masthead subheader and platform Purpose Statement are protected identity copy. Do not include them in general language-cleanup passes; change them only when the owner explicitly requests new wording.

## Reader-facing language

Prefer concrete nouns and verbs. Avoid generic research-product jargon when a literal phrase works better.

Words such as **pulse, trajectory, transmission, realization, validation, diffusion, pathway, screen, anatomy, workbench, signature, ecosystem, unlock, leverage, constructive, durable,** and **meaningful** should not be used as decorative labels. They are acceptable only when they carry a specific technical meaning that cannot be stated more plainly.

Examples:

- `Commercial realization` -> `Reported AI revenue and demand`
- `Workforce transmission pulse` -> `Current labor-market conditions`
- `Campus Water Exposure Dossier` -> `Campus Water Profile`
- `Grid Delivery Pathway` -> `Grid Connection Conditions`
- `Outcomes pulse` -> `From AI revenue to economic results`

Do not rename a formal metric or source field merely for style if doing so changes its definition or breaks analytical continuity. When a formal metric name is jargon-heavy, keep the internal name and use a plain display label with the formal definition available in Terms.

## Titles and subtitles

- Titles say what the reader is looking at.
- Subtitles explain the comparison, population, period, or analytical purpose.
- Do not use a subtitle to restate the title in more ornate language.
- Avoid vague labels such as `Current divergence`, `Signal anatomy`, or `Signature view` when the underlying comparison can be named.
- A reader should understand the purpose of a chart from its title and subtitle without needing to inspect the code or surrounding prose.
- Do not begin a title, subtitle, or explanatory sentence with **Who, What, When, Where, Why, How,** or **Whether**. Rewrite it as a direct statement of the subject or comparison.
- Avoid question-form headings when a declarative label is clearer. `Are the gains reaching workers?` becomes `Worker outcomes`; `Where data centers are concentrated` becomes `Data-center geography`.

## The Read

The Read is interpretation, not a KPI recap.

Each domain Read should usually do three things:

1. State the main conclusion in plain language.
2. Explain the evidence behind that conclusion.
3. State why the relationship matters now without adding a forecast or monitoring instruction.

Do not add a separate **Why it matters** block. The subject is already important enough to be in the platform; the Read should spend its limited space on interpretation.

Statistics support those points; they are not the points themselves. Avoid strings of sentences that amount to `X is 12%, Y is 4%, Z is 8%` when those values are already visible in the state rail or chart.

Use one or two numbers when they sharpen an interpretation. Prefer comparisons and implications over recitation.

The readability target is expert-valid, non-specialist-readable. A domain expert should agree with the substance, while a smart reader outside the field should be able to follow the argument without learning a new vocabulary first. Simplify words and sentence structure rather than inserting definitions. Do not turn the Read into a glossary, add parenthetical mini-lessons, or define technical terms mid-sentence; if a specialist term is unnecessary, state the underlying idea in ordinary language instead.

Elegance comes from logical order, not compression. Each sentence should do one main analytical job. Prefer concrete subjects and verbs, and allow a short sentence when it gives the paragraph shape. Reuse the correct noun instead of reaching for a synonym merely to vary the prose.

Preserve analytical hierarchy. Investment, construction, operating capacity, adoption, and economic outcomes may belong in the same argument without being peers. Use **but, while, yet, whereas,** and similar contrast words only when the concepts are genuinely comparable. When one concept funds, enables, constrains, produces, or translates into another, state that relationship directly.

Prefer zero to two commas in a Read sentence. Three is a warning that the sentence may be carrying too much. Four or more fails the publication style gate. Semicolons are not used in Reader commentary. Domain Reads should usually be 55–85 words and must stay at or below 95. AI Macro should usually be 85–110 words and must stay at or below 120. Individual analysis sentences must stay at or below 32 words.

Examples of the intended distinction:

- A large interconnection queue measures developer interest; it is not the same as near-term grid capacity.
- High LLM task exposure identifies work that could be affected; it is not observed job displacement.
- Provider AI revenue shows that customers are paying for AI services; it does not by itself establish an economy-wide return on AI investment.
- National water withdrawals provide context; local campus supply, cooling design, drought, and permitting determine site-level constraints.
- Broad consumer use is different from paid use and sustained business adoption.

Use causal restraint in ordinary English. If the evidence is descriptive, say what it measures and what additional evidence would be needed rather than inserting a methodology lecture.

## Evidence standards

AI Macro treats source discovery and factual evidence as separate jobs.

- Secondary aggregators, blogs, newsletters, and specialist publications may identify a lead, but discovery does not make them evidence. Follow the lead to a primary record or an approved independent business source before using it in Reader-facing copy.
- Independent follow-up should seek primary records first: government and agency records, regulatory filings, official datasets, company filings or releases, and court or formal administrative records.
- Corroboration requires independent evidence. Multiple stories derived from the same filing, wire report, press release, or upstream article remain one evidentiary chain.
- For consequential claims, consider evidence that supports, qualifies, contradicts, or narrows the initial interpretation. Conclusions should reflect the available evidence rather than automatically adopt the interpretation of any individual source.
- Preserve institutional authority precisely. Statements, requests, proposals, directives, orders, rules, and enacted laws are not interchangeable.
- Social media is excluded entirely. Do not use Reddit, X/Twitter, Facebook, Instagram, Threads, TikTok, LinkedIn, YouTube, Bluesky, Mastodon, Truth Social, Telegram, Discord, Snapchat, or other social/user-generated platforms for discovery, corroboration, evidence, or citation.

## Recent Developments

Use a slightly more formal research-note style than the surrounding interface. Assume the reader has no prior knowledge of regional politics, agencies, utilities, or grid institutions.

- On first reference, identify public officials with jurisdiction, title, and full name: `Texas Governor Greg Abbott`, not `Governor Abbott`.
- Expand specialized agencies and regional institutions on first reference: `Public Utility Commission of Texas (PUCT)` and `Electric Reliability Council of Texas (ERCOT)`. Shorthand is fine afterward.
- State the action and its practical consequence directly. Avoid political shorthand, dramatic framing, and assumptions that the reader has followed the story.
- Do not lead Reader-facing copy with the publisher (`Reuters reports:`, `Morningstar reports:`, `Company statement via...`). The numbered citation carries source identity. The prose begins with the development itself.
- Use the same two-part grammar as the strongest retained items: **what happened → why it materially changes the interpretation of the domain evidence**. Do not append generic filler such as `The development may change market leadership...` or `The development may change financing conditions...`.
- If automated discovery cannot supply enough first-reference context, omit the item rather than publish ambiguous shorthand.
- Recent Developments is context, not a news feed. Display zero, one, or at most two qualified developments; never fill space with a weak item merely to make the section appear current.
- Week-ahead previews, calendars, listicles, generic market recaps, and adjacent-industry items are not completed developments. Reject them before ranking.
- For Market and Finance, materiality is domain-specific. Earnings, guidance, bookings, valuation changes, ratings, bond/loan financing, private credit, project finance, fund closes, refinancing, spreads, and similar economic events may qualify without a generic word such as `announced`.
- Finance still requires a concrete AI/technology/infrastructure connection unless the item changes a genuinely system-wide financing condition. The mere presence of words such as `private credit`, `fund`, or `debt` is not sufficient.
- Within the eligible set, materiality outranks trivial recency differences. A large financing, acquisition, guidance change, or rating action should not be displaced merely because a minor item was published later.

## Footnotes, captions, and helper text

Use these for units, coverage, source limitations, definitions, and necessary caveats. Do not use them to repeat the main argument or add promotional language.

Prefer:

`Published campus capacity; facilities without a disclosed MW value are excluded.`

Over:

`A comprehensive lens into the evolving scale and momentum of the data-center ecosystem.`

## Editing test

Before reader-facing copy ships, ask:

- Could this be said in fewer or more ordinary words without losing meaning?
- Does the title name the actual object or relationship?
- Is a statistic being repeated instead of interpreted?
- Does an adjective have a defined basis, or is it just tone?
- Is the prose clear about what the evidence measures and what remains uncertain?
- Does each sentence express one main relationship rather than compressing several into one?
- Are contrast words connecting true peers, or hiding an input/process/outcome relationship that should be stated directly?
- Would this sentence sound natural in a research note written by a person who understands the data?

If not, rewrite it.

### Tier-2 discovery boundary

Tier-2 curators are lead generators, not witnesses. If a curator points directly to a primary record or a company statement, the underlying record may qualify on its own terms. If it points to secondary journalism, AI Macro must also retrieve the same development through an independent non-Tier-2 path before unattended selection. No domain may display more than one Tier-2-origin development at a time.
