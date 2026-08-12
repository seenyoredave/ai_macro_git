# Current Context source grounding — 2026-08-09

## Purpose

Current Context is a research-context layer, not a headline summarizer. Discovery
metadata nominates an event. Automated Reader-facing prose requires eligible source
text that actually establishes that event; the initially discovered URL is only the
first evidence route, not a mandatory endpoint.

## Canonical path

1. Discover a candidate through an approved discovery sensor.
2. Apply source, seven-day freshness, domain-anchor, relevance, and materiality
   gates to metadata only to decide whether the event is worth researching.
3. Try the nominated evidence route first. Google News wrappers must resolve through
   the canonical decode flow, and a trusted publisher label cannot bless an unrelated
   redirect.
4. If that route is inaccessible or insufficient for a non-disqualifying reason,
   research the **same event** through a bounded event-level lookup. Alternate evidence
   must be an eligible primary/company record or approved independent publication,
   must not simply retry the same publisher, and must match the nominated event in
   subject, timing, and factual signature.
5. Fetch and parse the evidence page that will actually establish the event. Prefer
   structured `articleBody`; otherwise extract substantive article/main-body paragraphs.
6. Use that evidence page's publication date as the recency authority when present. A
   stale page resurfaced by search/RSS is rejected. `dateModified` is only a fallback
   when no publication date is available.
7. Establish a concrete development from source-body text. Topic pieces, previews,
   interviews/opinion without new evidence, globally interesting but AI-Macro-
   irrelevant projects, and unsupported analytical leaps are rejected.
8. Produce compact Reader copy in the established grammar: **what happened → why
   it matters**. Publisher identity stays in the numbered citation. Generic
   `The development changes...` boilerplate is prohibited.
9. Persist only derived prose and provenance. Preserve the original event identity and,
   when alternate evidence was needed, retain the discovery/evidence lineage. Never
   persist the fetched article body.

## Failure rule

No eligible evidence path that establishes the event means no automated Recent
Development. One inaccessible publisher is not a veto on the event; exhausting the
bounded eligible evidence search is. Zero remains preferable to a headline paraphrase,
a source-policy downgrade, or a plausible inference that retrieved evidence does not
establish.

## Persistence / reload

Automated retained rows must carry `grounded` status, a resolved evidence URL,
substantive source-text provenance, and an evidence hash. The grounding/discovery
version is provenance, not an expiration control: once a row clears this durable
source-grounded evidence contract, it remains eligible until its domain freshness
window expires or a newer row explicitly supersedes/revokes it. When the same
`event_id` is rediscovered, the current registry is upserted with the most recent
vetted row; historical candidate/gate trace belongs in the audit file. Pre-grounding
headline-derived automated rows remain ineligible because they lack these evidence
fields. Curated primary records remain governed by their explicit curated evidence
contract.

## High-bar exclusions

- Routine policymaker commentary, outlook remarks, interviews, and `week ahead`
  previews are not developments unless the source establishes an implemented
  policy action or a new quantified empirical release.
- Nonbinding roadmaps, explainers, guidance pages, and topic essays are context,
  not developments merely because they contain domain vocabulary.
- Workforce, Adoption, and Economic Outcomes automated items require a quantified
  observed result; pundit takes and task-level speculation do not qualify.
- Connectivity projects must be tied in the source fact itself to a major
  AI/cloud compute market or a strategic U.S. route. Generic international cable
  growth does not qualify.
- Headline shorthand for people is discovery metadata only. Where a person is
  material to an accepted fact, Reader copy uses the full identity established
  by the source body on first reference.
