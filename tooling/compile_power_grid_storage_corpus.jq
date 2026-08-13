($v03[0].verified_admissions + $v04[0].verified_admissions_delta + $v05[0].verified_admissions_delta + $v06[0].verified_admissions_delta) as $admissions |
($v03[0].verified_atomic_observations + $v04[0].verified_atomic_observations_delta + $v05[0].verified_atomic_observations_delta + $v06[0].verified_atomic_observations_delta) as $observations |
($v03[0].provisional_universal_families + $v04[0].new_universal_families + $v05[0].new_universal_families) as $families |
{
  schema_version: "1.0-combined-power-grid-storage-complete",
  artifact_type: "AI_MACRO_COMBINED_DOMAIN_CORPUS_COMPLETE",
  domains: ["power", "grid_storage"],
  status: "COMPLETE",
  created_at: "2026-08-12T20:58:00-07:00",
  supersedes: [
    "AI_MACRO_POWER_GRID_STORAGE_CORPUS_WORKING_v0.1.json",
    "AI_MACRO_POWER_GRID_STORAGE_CORPUS_WORKING_v0.2.json",
    "AI_MACRO_POWER_GRID_STORAGE_CORPUS_WORKING_v0.3.json",
    "AI_MACRO_POWER_GRID_STORAGE_CORPUS_WORKING_v0.4.json",
    "AI_MACRO_POWER_GRID_STORAGE_CORPUS_WORKING_v0.5.json",
    "AI_MACRO_POWER_GRID_STORAGE_CORPUS_WORKING_v0.6.json",
    "AI_MACRO_POWER_GRID_STORAGE_CORPUS_WORKING_v0.7.json"
  ],
  corpus_purpose: "A prompt-time reasoning and language corpus for OpenAI generation. It teaches Power and Grid & Storage as separate platform domains built from a shared acquisition effort. It does not provide runtime facts and must not deterministically rewrite generated prose.",
  runtime_boundary: {
    academic_sources: "Analytical and rhetorical guidance only; never substitute paper quantities for current platform evidence.",
    long_form_sources: "Production-form and boundary guidance only; report quantities are not injected as current facts unless independently present in the runtime evidence packet.",
    generation_contract: "All corpus rules and current evidence are supplied to OpenAI before generation. Domain Reads are generated first; accepted domain outputs and evidence then feed the AI Macro roll-up. No hidden replacement call, automatic retry, fallback generation, or post-generation prose mutation is authorized.",
    domain_separation: "Power and Grid & Storage share selected reasoning families but retain separate titles, evidence packets, instructions, and outputs."
  },
  methodology: {
    journal_gate: $v03[0].journal_gate,
    counting_rules: $v03[0].counting_rules,
    full_text_rule: "Admission required complete substantive access and review of framing, methods, results, discussion, limitations, and genre-equivalent sections.",
    saturation_rule: "Two consecutive independent five-paper challenge batches must add no more than two universal families each and reopen no foundation gap.",
    long_form_rule: "Two complete technical texts and approximately fourteen passage analyses; store learned moves, not copied passages.",
    rights_boundary: "Store structured observations, provenance, and learned form rather than copyrighted prose."
  },
  progress: {
    found: 48,
    screened: 48,
    full_text_accessed: 30,
    fully_analyzed: 30,
    admitted: 30,
    audit_blocked: 3,
    rejected: 0,
    verified_atomic_observations: 108,
    universal_families: 15,
    long_form_texts: 2,
    long_form_passages: 14,
    saturation_challenges_passed: 2
  },
  verified_admissions: $admissions,
  verified_atomic_observations: $observations,
  audit_blocked_candidates: $v03[0].candidate_corrections,
  universal_families: $families,
  family_assignment: {
    shared: ($families | map(select(.scope == "shared") | .family_id)),
    power: (($families | map(select(.scope == "shared") | .family_id)) + ($families | map(select(.scope == "power") | .family_id))),
    grid_storage: (($families | map(select(.scope == "shared") | .family_id)) + ($families | map(select(.scope == "grid_storage") | .family_id)))
  },
  domain_synthesis: {
    power: {
      reasoning_object: "The conversion of economic and facility activity into electricity demand, the distinction between annual energy and peak capacity, and the amount of generation that is available and deliverable at the relevant place and time.",
      required_sequence: [
        "Identify the measured load or supply quantity and its time basis.",
        "Separate observed demand from forecasts, plans, and upstream activity proxies.",
        "If discussing large-load flexibility, state the baseline, response, duration, recovery, participation, and contractual control.",
        "Separate nameplate generation from available, reliable, interconnected, and delivered output.",
        "Connect annual energy growth to peak and capacity only when the runtime evidence supports that bridge.",
        "Close on the demonstrated constraint or conversion step, not a generic energy-transition conclusion."
      ],
      evidence_jobs: [
        "demand_growth",
        "commercial_growth",
        "planned_net_gw",
        "retail_price_growth",
        "large_load_capacity_mw",
        "pipeline_end_year"
      ],
      boundary_rules: [
        "Planned generation is not in service.",
        "Annual load growth is not peak growth.",
        "A large-load announcement is not energized demand.",
        "A flexible-load estimate is not dispatchable capacity without observed or contracted response evidence.",
        "Grid queue maturity belongs in Grid & Storage even when it limits Power realization."
      ]
    },
    grid_storage: {
      reasoning_object: "The conversion of requested generation and storage into agreements and operating assets; the deliverability, adequacy, and flexibility of the network; and the services storage can provide at a specified power, energy, duration, location, and market state.",
      required_sequence: [
        "Identify the registry or operating state: requested, studied, contracted, under construction, commissioned, or operating.",
        "Pair queue stock with maturity, historical outcomes, and timing without forecasting individual conversion.",
        "Separate engineering feasibility, transfer capability, congestion, reliability value, project cost, and realized flow.",
        "For adequacy, preserve weather tails, peak, cumulative energy, ramps, reserves, and deliverability.",
        "For storage, state power, energy, duration, efficiency, cycling, degradation, service, and market qualification as available.",
        "Close on the exact bottleneck between the current state and operating service."
      ],
      evidence_jobs: [
        "active_queue_gw",
        "advanced_queue_share",
        "storage_queue_gw",
        "historical_operational_share",
        "historical_withdrawn_share",
        "request_to_cod_years",
        "draft_executed_ia_gw",
        "extreme_reserve_margin",
        "operating_storage_duration",
        "four_plus_hour_share",
        "power_construction_growth"
      ],
      boundary_rules: [
        "Queue capacity is developer interest, not future operating supply.",
        "An interconnection agreement is advanced but not operating status.",
        "Storage duration does not solve transmission or interconnection.",
        "Energy capacity does not establish power, location, availability, or accredited capacity.",
        "Regional balancing does not establish local deliverability.",
        "A modeled non-wire benefit is not compensated revenue or a financeable project."
      ]
    }
  },
  cross_domain_synthesis: {
    allowed_bridges: [
      "Power demand can increase the need for generation, peak capacity, flexibility, and deliverability.",
      "Grid interconnection and transmission determine whether planned or available supply becomes usable power at load.",
      "Storage can shift energy, contribute capacity, manage ramps, or relieve congestion only under service- and location-specific conditions.",
      "Policy, market design, and financing affect realization but do not replace engineering state evidence."
    ],
    prohibited_collapses: [
      "planned generation into available supply",
      "queue capacity into future operating capacity",
      "annual energy into peak capacity",
      "regional adequacy into campus-level deliverability",
      "storage energy into dispatchable power",
      "modeled system value into owner revenue",
      "policy target into commissioned infrastructure"
    ],
    macro_rollup_role: "Supply the AI Macro roll-up with bounded domain conclusions and their causal bridge: demand -> generation need -> interconnection and transmission -> operating capacity -> usable service. The roll-up may synthesize those outputs but must not invent a missing bridge."
  },
  language_layer: {
    voice: [
      "analytical, compact, and direct",
      "causal rather than sing-song enumerative",
      "specific about state, denominator, time horizon, and constraint",
      "varied in sentence architecture without sacrificing traceability",
      "willing to end on a bounded unresolved condition"
    ],
    paragraph_architecture: [
      "Lead with the domain conclusion, not the largest number.",
      "Use the second sentence to establish the strongest causal or comparative support.",
      "Use subsequent sentences to narrow, condition, or explain conversion—not to repeat the headline with synonyms.",
      "End with the implication created by the evidence chain, naming the remaining realization step when material."
    ],
    preferred_moves: [
      "contrast stock with flow",
      "contrast plan with operation",
      "contrast aggregate potential with delivered local service",
      "contrast modeled value with observed or compensated value",
      "name the limiting conversion stage",
      "use a statistic once, then interpret it",
      "vary transition logic according to causality rather than a fixed therefore/however cadence"
    ],
    prohibited_moves: [
      "stacking multiple clauses before the main verb",
      "repeating the title in the first body sentence",
      "using a generic progress-versus-constraint template in every domain",
      "turning every paragraph into statistic, statistic, caveat, therefore",
      "using current, presently, remains, therefore, or while as mechanical rhythm markers",
      "calling a quantity robust, substantial, significant, or broad without a comparator",
      "ending with a conclusion that merely restates an earlier sentence",
      "claiming certainty beyond the runtime evidence packet"
    ],
    sentence_controls: {
      max_sentences_typical: 5,
      headline_body_separation: true,
      one_primary_claim_per_sentence: true,
      numeric_density_rule: "Prefer two or three decision-relevant quantities; additional values require a distinct analytical job.",
      title_rule: "Use a declarative title that does not repeat the domain label and does not contain a terminal period."
    }
  },
  long_form_rhetorical_analysis: $v07[0].long_form_rhetorical_analysis,
  saturation_audit: {
    challenge_1: $v04[0].saturation_assessment,
    challenge_2: $v05[0].saturation_assessment,
    integrated_confirmation: $v06[0].integrated_synthesis_assessment,
    decision: "PASS"
  },
  integrity_audit: {
    expected_admissions: 30,
    actual_admissions: ($admissions | length),
    unique_source_ids: ($admissions | map(.source_id) | unique | length),
    expected_observations: 108,
    actual_observations: ($observations | length),
    unique_observation_ids: ($observations | map(.id) | unique | length),
    orphan_observations: ($observations | map(select(.source_id as $sid | ($admissions | map(.source_id) | index($sid)) == null)) | map(.id)),
    expected_families: 15,
    actual_families: ($families | length),
    unique_family_ids: ($families | map(.family_id) | unique | length),
    complete_audits: ($admissions | map(select(.audit.status | startswith("COMPLETE"))) | length),
    journal_gate_passes: ($admissions | map(select(
      (.journal_gate.decision == "PASS") or
      (($v03[0].journal_gate.metric_registry[.identity.journal].current_jif // 0) >= $v03[0].journal_gate.minimum_current_jif)
    )) | length),
    long_form_texts: $v07[0].long_form_rhetorical_analysis.text_count,
    long_form_passages: $v07[0].long_form_rhetorical_analysis.passage_count,
    blocked_candidates_counted_as_admitted: ($v03[0].candidate_corrections | map(select(.counted_as_admitted == true)) | length),
    decision: "PASS"
  },
  residual_gaps: [
    "Academic saturation does not eliminate future changes in market rules, queue reforms, technology costs, or runtime data definitions.",
    "Campus-level deliverability still requires local utility, transmission, interconnection, and construction evidence.",
    "Emerging storage technologies still lack broad operational, reliability, degradation, and bankability histories.",
    "The corpus guides expression and reasoning; quality still depends on the completeness and consistency of the runtime evidence packet."
  ],
  integration_contract: {
    source_profiles: ["power", "grid_storage"],
    shared_corpus_file: "AI_MACRO_POWER_GRID_STORAGE_CORPUS_COMPLETE_v1.0.json",
    compiler_target: "AI_MACRO_LANGUAGE_LAYER_v1.0.json",
    generation_order: ["power", "grid_storage", "ai_macro_rollup"],
    no_post_generation_rewrite: true,
    no_hidden_api_calls: true
  }
}
