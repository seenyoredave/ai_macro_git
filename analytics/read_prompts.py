"""Prompts for the two-call AI Macro language-layer pipeline."""

from __future__ import annotations

import json
from typing import Any

DOMAIN_PROMPT_VERSION = "domain-language-layer-1.3"
MACRO_PROMPT_VERSION = "macro-rollup-2.2"


DOMAIN_OUTPUT_RULES = {
    "membership": "Return exactly one Read for each of the 11 supplied domains. Do not add, omit, or duplicate a domain.",
    "headline": "At most 12 words. State the domain conclusion rather than a label or metric recap.",
    "analysis": "Write 3-4 sentences and at most 95 words. Let the evidence determine the sequence of analytical jobs; do not force every Read into the same progression.",
    "sentence_shape": "At most 32 words and 3 commas per sentence. Do not use semicolons. Prefer one governing relationship per sentence.",
    "sound": "Do not use a run of 3 or more words beginning with the same letter. Articles, conjunctions, and short prepositions do not make such a run acceptable.",
    "neutral_scope": "Do not introduce race, ethnicity, religion, sexuality, gender identity, partisan affiliation, or ideological identity. Do not use minority or majority as a proportional label; use the measured percentage, fewer than half, or most when that distinction matters.",
    "numerical_discipline": "Use at most 3 displayed quantities in a Read. Include a quantity only when its magnitude is necessary to the conclusion.",
    "grounding": "Every sentence must cite one or more supplied fact_ids. Every displayed factual detail must be supported exactly.",
    "domain_scope": "A domain Read may cite only fact_ids from its own evidence packet.",
}


MACRO_OUTPUT_RULES = {
    "headline": "At most 16 words. State one system-level thesis rather than listing domains or repeating a domain headline.",
    "paragraphs": "Write 3 paragraphs by default and a fourth only when the argument genuinely needs it. Use 2-4 sentences per paragraph. Aim for 150-225 words overall and never exceed 250 words. There is no minimum word count.",
    "reader": "Write for a brilliant, widely read adult who may know little about the subject. Assume strong reasoning ability, not specialized vocabulary. Supply context without adopting a classroom tone.",
    "contextual_sufficiency": "On first reference, identify any unfamiliar cohort, metric, proxy, institution, or lifecycle stage clearly enough for the sentence to stand alone. Never write covered issuers, covered companies, or covered cohort without identifying who is covered.",
    "explanatory_restraint": "Explain only relationships that are not self-evident. Do not announce the argument's structure, narrate a domain sequence, define ordinary financial or economic reasoning, or restate the thesis merely to fill space.",
    "sentence_shape": "At most 28 words and 3 commas per sentence. Do not use semicolons. Give each sentence one principal claim and enough context to understand why it matters.",
    "sound": "Do not use a run of 3 or more words beginning with the same letter. Articles, conjunctions, and short prepositions do not make such a run acceptable.",
    "neutral_scope": "Keep the Read nonpartisan and outside social-identity debates. Do not introduce race, ethnicity, religion, sexuality, gender identity, partisan affiliation, or ideological identity. Do not use minority or majority as a proportional label; state the measured share or use unambiguous language such as fewer than half or most.",
    "numerical_discipline": "Use at most 5 displayed quantities. Identify each ratio's population and denominator. Translate it only when doing so improves comprehension; do not turn an already intelligible ratio into a remedial arithmetic lesson.",
    "selected_domains": "Select 3-5 distinct domains spanning at least three of capital/markets, physical buildout, adoption, and workforce/economic outcomes. Do not add a domain merely to fill the extra space.",
    "synthesis": "Build one causal or conversion chain across the selected domains. At least three sentences must integrate evidence from two domains; no sentence may rely on more than two domains.",
    "grounding": "Every sentence must cite supplied fact_ids from selected domains. Every selected domain must support at least one claim.",
    "rollup": "Use the completed domain Reads as the analytical foundation. Synthesize them; do not copy their wording or tour them one by one.",
}


DOMAIN_INSTRUCTIONS = """
You write the eleven domain Reads for AI Macro, a research platform tracking the U.S. AI economy.

The evidence packets are the exclusive factual record. The language layer is editorial guidance, not evidence. Never introduce, repair, estimate, update, or infer a factual value that the evidence does not supply. Preserve observation and interpretation as distinct inference types, and never turn association into causation.

Plan the complete Read set before writing. For each domain, identify the most decision-relevant relationship in its packet and choose a compatible architecture from the language layer. Across the set, vary the opening move, sentence jobs, syntax, rhythm, and ending. Do not use one architecture more than twice. Do not make every headline a two-part contrast. Avoid serial endings built from participles such as "showing," "placing," "leaving," or "limiting." These are set-level composition rules, not permission to sacrifice clarity.

Write for a highly intelligent adult who may have no specialized knowledge of the domain. Assume the reader can follow complexity from context. Identify an unfamiliar cohort, measure, proxy, or institution on first reference, but do not explain ordinary reasoning or adopt a classroom tone.

Keep the Read outside partisan and social-identity framing. Never introduce race, ethnicity, religion, sexuality, gender identity, partisan affiliation, or ideological identity. When describing a proportion, do not call people, workers, consumers, businesses, users, or adoption a minority or majority; state the measured share or use an unambiguous phrase such as fewer than half or most.

Write the final prose once. Silently edit it before returning the structured answer: make the subject concrete, make the main verb carry the relationship, remove abstract noun stacks, resolve pronouns, split overloaded sentences, and remove conspicuous alliteration. Return only the final structured Read set. Do not return a draft, editorial notes, scores, or alternatives.
""".strip()


MACRO_INSTRUCTIONS = """
You write the AI Macro roll-up after the eleven domain Reads have been completed.

The evidence packets are the exclusive factual record. The language layer is editorial guidance, not evidence. The supplied domain Reads are the analytical components of the roll-up and retain their cited fact_ids; they do not authorize facts outside those packets. Never introduce, repair, estimate, update, or infer a factual value that the evidence does not supply. Preserve observation and interpretation as distinct inference types, and never turn association into causation.

Read every completed domain Read before choosing the system thesis. Select the smallest set of domains that establishes one meaningful chain from financing or markets through physical delivery and use to outcomes. Explain the dependency between stages instead of placing unlike stages on opposite sides of a contrast. Add analytical value by identifying the conversion, bottleneck, timing mismatch, or distributional boundary that emerges only when the domain Reads are considered together.

Write for a highly intelligent, widely read, operationally experienced adult who may have no specialized knowledge of macroeconomics, infrastructure, power markets, or finance. Assume the reader can understand complex relationships from context. Introduce unfamiliar entities and measures clearly, but never explain ordinary reasoning, announce the structure of the argument, or adopt a classroom tone. Preserve useful technical language when it carries analytical meaning. Replace it only when it obscures the point.

Every sentence must stand on its own for that reader. On first reference, name the population, object, institution, metric, proxy, or process clearly enough to identify what it represents. Do not use internal labels such as covered issuers, covered companies, or covered cohort as though the reader already knows the platform's scope. Explain a ratio when its denominator or consequence would otherwise be unclear, not merely because it is a ratio.

Keep the Read outside partisan and social-identity framing. Never introduce race, ethnicity, religion, sexuality, gender identity, partisan affiliation, or ideological identity. When describing a proportion, do not call people, workers, consumers, businesses, users, or adoption a minority or majority; state the measured share or use an unambiguous phrase such as fewer than half or most.

Write the final prose once. Silently edit it before returning the structured answer: keep the subject concrete, make the main verb carry the relationship, remove undefined internal labels, remove conspicuous alliteration, avoid sing-song repetition, and close with a sharpened present implication rather than a forecast, slogan, or repeated thesis. Return only the final structured Macro Read. Do not return a draft, editorial notes, scores, or alternatives.
""".strip()


def domain_read_input(packets: dict[str, Any], language_layer: dict[str, Any]) -> str:
    return json.dumps(
        {
            "task": "Generate the complete final eleven-domain Read set in one response.",
            "output_rules": DOMAIN_OUTPUT_RULES,
            "language_layer": language_layer,
            "evidence_packets": packets,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def macro_read_input(
    packets: dict[str, Any],
    domain_reads: dict[str, Any],
    language_layer: dict[str, Any],
) -> str:
    return json.dumps(
        {
            "task": "Generate the final AI Macro Read from the completed domain Reads and their bounded evidence.",
            "output_rules": MACRO_OUTPUT_RULES,
            "language_layer": language_layer,
            "completed_domain_reads": domain_reads,
            "evidence_packets": packets,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
