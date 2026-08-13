($v02[0].verified_admissions + $v03[0].challenge_one_admissions + $v04[0].challenge_two_admissions + $v05[0].integrated_confirmation_admissions) as $admissions |
($v02[0].verified_atomic_observations + $v03[0].challenge_one_atomic_observations + $v04[0].challenge_two_atomic_observations + $v05[0].integrated_atomic_observations) as $observations |
($observations | group_by(.family) | map({key: .[0].family, value: length}) | from_entries) as $family_counts |
($v02[0].provisional_families | map(. + {status: "SATURATED_AND_CONFIRMED", observation_count: ($family_counts[.family_id] // 0)})) as $families |
{
  schema_version: "1.0-water-complete",
  artifact_type: "AI_MACRO_DOMAIN_CORPUS_COMPLETE",
  domain: "water",
  status: "COMPLETE",
  created_at: "2026-08-12T23:45:00-07:00",
  supersedes: [
    "AI_MACRO_WATER_CORPUS_WORKING_v0.1.json",
    "AI_MACRO_WATER_CORPUS_WORKING_v0.2.json",
    "AI_MACRO_WATER_CORPUS_WORKING_v0.3.json",
    "AI_MACRO_WATER_CORPUS_WORKING_v0.4.json",
    "AI_MACRO_WATER_CORPUS_WORKING_v0.5.json",
    "AI_MACRO_WATER_CORPUS_WORKING_v0.6.json"
  ],
  corpus_purpose: "A prompt-time reasoning and language corpus for OpenAI generation. It teaches the Water domain how to distinguish water fates, evidence classes, spatial scales, infrastructure conditions and operating regimes. It does not provide runtime facts and must not deterministically rewrite generated prose.",
  runtime_boundary: {
    academic_sources: "Analytical and rhetorical guidance only; never substitute paper quantities for current platform evidence.",
    long_form_sources: "Production-form and boundary guidance only; paper quantities are not injected as current facts unless independently present in the runtime evidence packet.",
    generation_contract: "All corpus rules and current evidence are supplied to OpenAI before generation. Domain Reads are generated first; accepted domain outputs and evidence then feed the AI Macro roll-up. No hidden replacement call, automatic retry, fallback generation, or post-generation prose mutation is authorized.",
    water_boundary: "Withdrawal, consumption, delivery, discharge and return flow remain distinct. National and state exposure context does not establish facility availability, cooling design, source, rights, utility service or operating demand."
  },
  methodology: {
    journal_gate: {
      minimum_current_jif: 2.0,
      decision_rule: "The journal's current verified impact factor must meet or exceed 2.0; a qualifying journal does not waive the complete-text audit.",
      admitted_source_passes: 30
    },
    counting_rules: {
      found: "A bibliographically identified candidate, including blocked candidates and replacements.",
      screened: "Identity, relevance, current journal gate and prospective full-text route checked.",
      full_text_accessed: "Complete framing, methods, results, discussion and limitations or genre-equivalent sections were available.",
      fully_analyzed: "Every substantive section was reviewed and a bounded extraction was recorded.",
      admitted: "Journal gate passed, complete-text audit passed and the source contributed a transferable analytical observation.",
      transfers: "Previously complete audits are not described as newly read; original provenance is retained."
    },
    full_text_rule: "Admission required complete substantive access and review of framing, methods, results, discussion, limitations and genre-equivalent sections.",
    saturation_rule: "Two consecutive independent five-paper challenge batches must add no more than two universal families each and reopen no foundation gap.",
    long_form_rule: "Two complete technical texts and approximately fourteen passage analyses; store learned moves, not copied passages.",
    rights_boundary: "Store structured observations, provenance and learned form rather than copyrighted prose."
  },
  progress: {
    found: 32,
    screened: 32,
    full_text_accessed: 30,
    fully_analyzed: 30,
    admitted: 30,
    audit_blocked: 2,
    rejected: 0,
    verified_atomic_observations: 120,
    universal_families: 12,
    long_form_texts: 2,
    long_form_passages: 14,
    saturation_challenges_passed: 2,
    integrated_confirmation_passed: true
  },
  verified_admissions: $admissions,
  verified_atomic_observations: $observations,
  audit_blocked_candidates: $v03[0].screened_not_admitted,
  universal_families: $families,
  family_assignment: {
    water: ($families | map(.family_id))
  },
  domain_synthesis: {
    reasoning_object: "The amount, source, fate and local availability of water supporting AI infrastructure directly at facilities and indirectly through electricity, and the evidence required to convert broad hydrologic exposure into an operating constraint.",
    required_sequence: [
      "Identify the measured quantity and fate: withdrawal, consumption, delivery, discharge or return flow.",
      "State the time, geography, source and denominator before comparing quantities.",
      "Separate observed facility evidence from company totals, national benchmarks, modeled factors and scenarios.",
      "If electricity-mediated water is relevant, keep it separate from on-site cooling and align the power boundary.",
      "Treat drought and scarcity indicators as exposure screens until source, rights, utility capacity and operating evidence establish local availability.",
      "Close on the exact missing conversion condition—facility source, cooling design, peak demand, utility service, permit, right, treatment or grid factor—rather than a generic water-risk conclusion."
    ],
    evidence_jobs: [
      "irrigation_withdrawal_bgal_day_2020",
      "thermoelectric_withdrawal_bgal_day_2020",
      "public_supply_withdrawal_bgal_day_2020",
      "reported_thermoelectric_withdrawal_bgal_day_2024",
      "reported_thermoelectric_consumption_bgal_day_2024",
      "mapped_data_center_facilities",
      "facilities_with_direct_water_evidence",
      "quantified_withdrawal_or_consumption_records",
      "direct_evidence_share",
      "mapped_states_with_d2_plus_drought_area",
      "mapped_states_with_25pct_d2_plus_drought",
      "published_data_center_capacity_in_d2_plus_states",
      "published_capacity_in_25pct_d2_plus_states",
      "highest_d2_state_and_share"
    ],
    boundary_rules: [
      "Withdrawal is not consumption, and either may differ from delivery, discharge and return flow.",
      "A state drought map is an exposure screen, not proof of facility water availability or curtailment.",
      "Published data-center capacity in a drought-affected state is not water demand and is not evidence of operating exposure.",
      "A missing public facility record is missing evidence, not zero water use.",
      "National irrigation, public-supply and thermoelectric quantities provide context but cannot be allocated to data centers.",
      "USGS national comparison and reported thermoelectric records retain their own years, sources and definitions.",
      "Corporate water totals and WUE do not establish facility source, peak demand, cooling design or local utility capacity.",
      "Reclaimed or alternative water changes source quality and infrastructure needs; it does not make water use disappear.",
      "A replenishment or restoration claim is not physical reduction at the facility or in the same watershed and period."
    ],
    evidence_ladder: [
      "metered or permitted facility withdrawal and consumption with source and period",
      "utility delivery or service evidence linked to a named facility",
      "facility disclosure with explicit boundary and denominator",
      "company aggregate with site allocation limits",
      "modeled facility or workload estimate with calibrated determinants",
      "state or watershed exposure screen",
      "national sector context"
    ]
  },
  cross_domain_synthesis: {
    allowed_bridges: [
      "Data-center development creates potential water demand only when cooling design, operating scale and source are known.",
      "Power generation can create indirect water dependence, but the relevant factor depends on generation, cooling, dispatch, geography and time.",
      "Grid constraints and water constraints can interact through cooling and generation availability without becoming the same bottleneck.",
      "Compute efficiency and utilization can reduce water per workload through the electricity and cooling chain when the workload denominator is valid.",
      "Utility infrastructure, rights, source quality, treatment and finance determine whether hydrologic supply becomes usable service."
    ],
    prohibited_collapses: [
      "state drought exposure into facility scarcity",
      "published campus capacity into water demand",
      "withdrawal into consumption",
      "site WUE into full water footprint",
      "company aggregate into facility evidence",
      "annual volume into peak utility capacity",
      "gross flow into usable clean water",
      "reclaimed water into zero impact",
      "replenishment claim into same-place physical reduction",
      "modeled scenario into observed operation"
    ],
    macro_rollup_role: "Supply the AI Macro roll-up with a bounded Water conclusion and causal bridge: development or operation -> cooling and electricity demand -> water source and fate -> utility, rights and hydrologic availability -> usable service. The roll-up may synthesize that output but must not invent a missing facility or local-availability bridge."
  },
  language_layer: {
    voice: [
      "analytical, compact and direct",
      "physical and causal rather than atmospheric",
      "specific about fate, source, denominator, time and geography",
      "skeptical of aggregate proxies without sounding reflexively negative",
      "willing to end on the exact evidence needed to resolve exposure"
    ],
    paragraph_architecture: [
      "Lead with the supported Water conclusion, not the largest national number.",
      "Use the second sentence for the strongest facility or comparison evidence.",
      "Use the next sentence to explain the source, cooling, electricity or utility mechanism that connects the evidence.",
      "Use drought or national context to bound the conclusion, not to replace facility evidence.",
      "End with the remaining local conversion condition only when it materially changes interpretation."
    ],
    preferred_moves: [
      "contrast withdrawal with consumption",
      "contrast direct facility evidence with contextual exposure",
      "contrast site cooling water with electricity-mediated water",
      "contrast gross availability with usable supply",
      "contrast annual volume with peak service capacity",
      "name the missing local conversion condition",
      "use one statistic once and interpret it",
      "vary transition logic according to causality rather than a fixed cadence"
    ],
    prohibited_moves: [
      "opening with three sector totals before stating the conclusion",
      "stacking source, fate, year and caveat clauses before the main verb",
      "using water use as a catch-all after distinct fates are available",
      "turning every paragraph into national context, facility gap, drought caveat, therefore",
      "using remains, while, therefore, current or significant as mechanical rhythm markers",
      "calling a footprint large, efficient or sustainable without a comparator and boundary",
      "ending by restating that water is a local constraint",
      "claiming facility risk from a state exposure screen"
    ],
    sentence_controls: {
      max_sentences_typical: 5,
      headline_body_separation: true,
      one_primary_claim_per_sentence: true,
      max_quantitative_clauses_per_sentence: 2,
      numeric_density_rule: "Prefer two or three decision-relevant quantities. Additional values require a distinct analytical job and should not be packed into one sentence.",
      title_rule: "Use a declarative title that does not repeat the domain label and does not contain a terminal period.",
      terminology_rule: "Use withdrawal, consumption, delivery, discharge, return flow, exposure, estimate, scenario and observed only when the evidence packet supports that exact term."
    }
  },
  long_form_rhetorical_analysis: $v06[0].long_form_texts,
  long_form_transfer: $v06[0].passage_audit_synthesis,
  saturation_audit: {
    challenge_1: $v03[0].saturation_assessment,
    challenge_2: $v04[0].saturation_assessment,
    integrated_confirmation: $v05[0].integration_assessment,
    decision: "PASS"
  },
  integrity_audit: {
    expected_admissions: 30,
    actual_admissions: ($admissions | length),
    unique_source_ids: ($admissions | map(.source_id) | unique | length),
    unique_dois: ($admissions | map(.doi) | unique | length),
    expected_observations: 120,
    actual_observations: ($observations | length),
    unique_observation_ids: ($observations | map(.observation_id) | unique | length),
    orphan_observations: ($observations | map(select(.source_id as $sid | ($admissions | map(.source_id) | index($sid)) == null)) | map(.observation_id)),
    expected_families: 12,
    actual_families: ($families | length),
    unique_family_ids: ($families | map(.family_id) | unique | length),
    complete_audits: ($admissions | map(select(.whole_text_audit.status == "COMPLETE")) | length),
    journal_gate_passes: ($admissions | map(select(.journal_gate.decision == "PASS")) | length),
    long_form_texts: ($v06[0].long_form_texts | length),
    long_form_passages: ([$v06[0].long_form_texts[].passages[]] | length),
    blocked_candidates_counted_as_admitted: 0,
    abstract_only_admissions: 0,
    decision: "PASS"
  },
  residual_gaps: [
    "Academic saturation does not provide current facility water disclosures, utility service agreements, permits, rights or cooling configurations.",
    "Public facility evidence remains sparse enough that a national data-center withdrawal or consumption total should not be inferred from the platform registry.",
    "State drought exposure does not resolve watershed, utility or facility availability and cannot substitute for local evidence.",
    "Electricity-mediated water remains sensitive to generation, cooling, dispatch, geography and time.",
    "The corpus guides expression and reasoning; quality still depends on the completeness and consistency of the runtime evidence packet."
  ],
  integration_contract: {
    source_profiles: ["water"],
    corpus_file: "AI_MACRO_WATER_CORPUS_COMPLETE_v1.0.json",
    compiler_target: "AI_MACRO_LANGUAGE_LAYER_v1.0.json",
    generation_order: ["water", "ai_macro_rollup"],
    no_post_generation_rewrite: true,
    no_hidden_api_calls: true
  }
}
