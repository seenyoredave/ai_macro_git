($v02[0].foundation_admissions + $v03[0].verified_admissions_delta + $v04[0].verified_admissions_delta + $v05[0].verified_admissions_delta) as $admissions |
def normalize_observation:
  {
    id: (.id // .observation_id),
    source_id: .source_id,
    family_ids: (.family_ids // [(.family)]),
    observation: (.observation // .statement)
  };
($v02[0].verified_atomic_observations | map(normalize_observation)) as $foundation_observations |
(($v03[0].verified_atomic_observations_delta + $v04[0].verified_atomic_observations_delta + $v05[0].verified_atomic_observations_delta) | map(normalize_observation)) as $later_observations |
($foundation_observations + $later_observations) as $observations |
($v02[0].family_registry | to_entries | map({family_id: .key, label: .value, rule: .value})) as $foundation_families |
($foundation_families + $v03[0].new_universal_families + $v04[0].new_universal_families) as $families |
{
  schema_version: "1.0-diffusion-economic-transmission-complete",
  artifact_type: "AI_MACRO_COMBINED_DOMAIN_CORPUS_COMPLETE",
  corpus_name: "AI Diffusion and Economic Transmission",
  domains: ["adoption", "workforce", "economic_impact"],
  status: "COMPLETE",
  created_at: "2026-08-13T04:02:00-07:00",
  supersedes: [
    "AI_MACRO_DIFFUSION_ECONOMIC_TRANSMISSION_CORPUS_WORKING_v0.1.json",
    "AI_MACRO_DIFFUSION_ECONOMIC_TRANSMISSION_CORPUS_WORKING_v0.2.json",
    "AI_MACRO_DIFFUSION_ECONOMIC_TRANSMISSION_CORPUS_WORKING_v0.3.json",
    "AI_MACRO_DIFFUSION_ECONOMIC_TRANSMISSION_CORPUS_WORKING_v0.4.json",
    "AI_MACRO_DIFFUSION_ECONOMIC_TRANSMISSION_CORPUS_WORKING_v0.5.json",
    "AI_MACRO_DIFFUSION_ECONOMIC_TRANSMISSION_CORPUS_WORKING_v0.6.json"
  ],
  corpus_purpose: "A prompt-time reasoning and language corpus for OpenAI generation. It teaches Adoption, Workforce, and Economic Outcomes as separate platform domains built from one integrated acquisition effort spanning microeconomic use, organizational production, labor transmission, firm outcomes, and macroeconomic aggregation. It does not provide runtime facts and must not deterministically rewrite generated prose.",
  runtime_boundary: {
    academic_sources: "Analytical and rhetorical guidance only; never substitute paper quantities for current platform evidence.",
    long_form_sources: "Production-form and boundary guidance only; manuscript quantities are not injected as current facts unless independently present in the runtime evidence packet.",
    generation_contract: "All corpus rules and current evidence are supplied to OpenAI before generation. Domain Reads are generated first; the paid domain outputs and evidence then feed the paid AI Macro roll-up. No hidden replacement call, automatic retry, fallback generation, or post-generation prose mutation is authorized.",
    domain_separation: "Adoption, Workforce, and Economic Outcomes share a reasoning architecture but retain separate titles, evidence packets, instructions, and outputs."
  },
  methodology: {
    journal_gate: {
      rule: "Admit peer-reviewed journal articles that satisfy the project's journal-quality gate and complete-substantive-text requirement.",
      metric_registries: [$v02[0].journal_metric_registry, $v03[0].journal_metric_registry_delta, $v04[0].journal_metric_registry_delta, $v05[0].journal_metric_registry_delta] | add
    },
    counting_rules: {
      source: "One final peer-reviewed article with one verified identity counts once, even when multiple versions were reviewed.",
      observation: "One indivisible, source-bounded analytical proposition with a traceable source and family assignment counts once.",
      family: "One reusable reasoning rule that cannot be reduced to an existing family counts once."
    },
    full_text_rule: "Admission required complete substantive access and review of framing, methods, results, discussion, limitations, appendices, and genre-equivalent sections.",
    saturation_rule: "Two consecutive independent five-paper challenge batches must add no more than two universal families each and reopen no foundation gap; a five-paper integrated confirmation must fit the resulting framework without expansion.",
    long_form_rule: "Two complete long-form texts and approximately fourteen passage analyses; store learned analytical moves rather than copied passages.",
    rights_boundary: "Store structured observations, provenance, and learned form rather than copyrighted prose."
  },
  progress: {
    found: 30,
    screened: 30,
    full_text_accessed: 30,
    fully_analyzed: 30,
    admitted: 30,
    audit_blocked: 0,
    rejected: 0,
    verified_atomic_observations: 120,
    universal_families: 17,
    long_form_texts: 2,
    long_form_passages: 14,
    saturation_challenges_passed: 2,
    integrated_confirmations_passed: 1
  },
  verified_admissions: $admissions,
  verified_atomic_observations: $observations,
  audit_blocked_candidates: [],
  universal_families: $families,
  family_assignment: {
    shared: ($families | map(.family_id)),
    adoption: ["ADET-U01", "ADET-U02", "ADET-U03", "ADET-U04", "ADET-U06", "ADET-U08", "ADET-U10", "ADET-U12", "ADET-U14", "ADET-U15", "ADET-U16", "ADET-U17"],
    workforce: ["ADET-U03", "ADET-U04", "ADET-U05", "ADET-U06", "ADET-U07", "ADET-U08", "ADET-U09", "ADET-U10", "ADET-U12", "ADET-U13", "ADET-U14", "ADET-U16", "ADET-U17"],
    economic_impact: ["ADET-U03", "ADET-U04", "ADET-U05", "ADET-U06", "ADET-U07", "ADET-U09", "ADET-U10", "ADET-U11", "ADET-U12", "ADET-U13", "ADET-U14", "ADET-U15", "ADET-U17"]
  },
  domain_synthesis: {
    adoption: {
      reasoning_object: "The conversion of access and trial into repeated task use and organization-wide integration, preserving who uses AI, how often, for which tasks, under what firm rules, and at what depth.",
      required_sequence: [
        "Identify the measured population, date, use state, and denominator.",
        "Separate awareness and access from any use, recent use, work use, core-task use, and integrated deployment.",
        "Describe frequency, intensity, task breadth, and organizational depth before interpreting economic relevance.",
        "Test whether worker characteristics, firm policy, training, privacy, workflow, or capability boundaries explain uneven use.",
        "Keep potential exposure and reported usefulness below observed use, and keep observed use below realized outcome.",
        "Close on the specific barrier between the observed adoption state and routine productive integration."
      ],
      evidence_jobs: [
        "business_ai_use_rate",
        "worker_use_rate",
        "recent_or_core_task_use",
        "frequency_or_intensity",
        "firm_size_or_sector_dispersion",
        "training_or_policy_friction",
        "integration_depth"
      ],
      boundary_rules: [
        "Awareness and access are not adoption.",
        "Any use is not frequent, core-task, or organization-wide use.",
        "Worker use is not employer deployment.",
        "Exposure is not use, and use is not productivity.",
        "A firm average does not describe the typical firm when size-weighting and concentration differ."
      ]
    },
    workforce: {
      reasoning_object: "The movement from AI capability and task exposure through firm skill demand, human-AI work allocation, worker adaptation, employment, wages, job quality, and distributional incidence.",
      required_sequence: [
        "Identify whether the evidence measures tasks, postings, workers, jobs, employment stocks, flows, hours, wages, or job quality.",
        "Separate potential exposure from observed adoption, automation, augmentation, substitution, and new-task creation.",
        "State the task frontier, worker skill or experience condition, organizational setting, and comparison group.",
        "Keep speed, quality, output, employment, wages, autonomy, and satisfaction as separate outcomes.",
        "Trace heterogeneity by occupation, sector, geography, skill, experience, age, gender, and firm adoption intensity when supported.",
        "Close on the labor-market outcome that has actually registered and the transmission step still missing."
      ],
      evidence_jobs: [
        "ai_exposure",
        "ai_skill_demand",
        "job_postings",
        "employment_growth",
        "hours_or_task_reallocation",
        "wage_or_compensation_growth",
        "job_quality_or_satisfaction"
      ],
      boundary_rules: [
        "Task exposure is not worker displacement.",
        "Job postings are not employment or hiring.",
        "Automation, augmentation, substitution, and reallocation are not interchangeable.",
        "Released labor creates value only when productively reallocated.",
        "Task performance does not establish aggregate employment or wage effects."
      ]
    },
    economic_impact: {
      reasoning_object: "The conversion of AI investment and adoption into firm production, innovation, revenue, profit, measured productivity, output, income, consumer value, and economy-wide distribution over time.",
      required_sequence: [
        "Identify the observed outcome and its level: task, worker, firm, sector, or economy.",
        "Separate investment, capacity, exposure, use, time savings, and workflow change from realized economic output.",
        "State whether evidence is experimental, observational, model-implied, scenario-based, or an aggregate statistic.",
        "Preserve the bridge from affected share and task effect through economic weights, complements, reallocation, prices, competition, and capital response.",
        "Separate productivity, output, revenue, profit, wages, labor share, capital income, consumer surplus, and welfare.",
        "Close on the strongest demonstrated transmission result and the unobserved link preventing a broader claim."
      ],
      evidence_jobs: [
        "labor_productivity_growth",
        "total_factor_productivity",
        "real_output_growth",
        "firm_revenue_or_profit",
        "innovation_or_entry",
        "real_compensation_or_labor_share",
        "value_incidence"
      ],
      boundary_rules: [
        "Investment and adoption are not realized productivity.",
        "A task experiment is not firm or economy-wide productivity.",
        "Firm growth can reflect selection and business stealing rather than aggregate growth.",
        "Measured output does not establish worker, consumer, or social welfare.",
        "A calibrated scenario is not an observed forecast path.",
        "Concurrent AI activity and aggregate growth do not establish causal attribution."
      ]
    }
  },
  cross_domain_synthesis: {
    allowed_bridges: [
      "Access can become repeated use when capability, training, policy, data, and workflow conditions permit.",
      "Repeated task use can affect workforce outcomes through automation, augmentation, substitution, reallocation, and new-task creation.",
      "Task-level gains can affect firm and aggregate outcomes only through affected shares, economic weights, complementary investment, organizational change, prices, competition, capital response, and diffusion time.",
      "Economic value can accrue differently to workers, firms, capital owners, consumers, and society."
    ],
    prohibited_collapses: [
      "awareness or access into adoption",
      "any use into deep integration",
      "exposure into adoption or displacement",
      "task performance into firm productivity",
      "job postings into employment",
      "firm growth into aggregate growth",
      "productivity into wages, profit, or welfare",
      "modeled potential into observed outcome"
    ],
    macro_rollup_role: "Supply the AI Macro roll-up with three bounded conclusions and their verified bridge: access and integration -> task and workforce change -> firm production -> aggregate output and distribution. The roll-up may synthesize the paid domain outputs but must not invent a missing transmission link."
  },
  language_layer: {
    voice: [
      "analytical, compact, and direct",
      "causal rather than sing-song enumerative",
      "specific about population, denominator, evidence class, level of aggregation, horizon, and constraint",
      "varied in sentence architecture without sacrificing traceability",
      "comfortable reporting a narrow, heterogeneous, null, or adverse result"
    ],
    paragraph_architecture: [
      "Lead with the domain conclusion at the exact level supported by the runtime evidence.",
      "Use the next sentence to establish the most decision-relevant support or comparison.",
      "Use later sentences to explain mechanism, heterogeneity, timing, or the missing transmission link instead of listing metrics.",
      "End with the economic implication created by the evidence chain, not a restatement of the title."
    ],
    preferred_moves: [
      "move through an adoption ladder",
      "contrast exposure with use and use with outcome",
      "contrast task performance with organization or economy outcomes",
      "separate augmentation, automation, substitution, and reallocation",
      "contrast average effects with the distribution beneath them",
      "mark the observation-to-model boundary",
      "trace who captures value",
      "name the missing transmission stage"
    ],
    prohibited_moves: [
      "stacking multiple clauses before the main verb",
      "repeating the title in the first body sentence",
      "turning the paragraph into metric, metric, caveat, therefore",
      "using exposure, adoption, productivity, and economic impact as interchangeable abstractions",
      "using current, presently, remains, therefore, or while as mechanical rhythm markers",
      "calling a result broad, meaningful, significant, or transformative without a comparator and scope",
      "averaging away a negative, null, or heterogeneous result",
      "ending with a generic claim that gains have not spread broadly"
    ],
    sentence_controls: {
      max_sentences_typical: 5,
      headline_body_separation: true,
      one_primary_claim_per_sentence: true,
      numeric_density_rule: "Prefer two or three quantities that occupy different stages of the causal chain; additional values require a distinct analytical job.",
      title_rule: "Use a declarative title that states the measured condition or transmission result, does not repeat the domain label, and has no terminal period."
    }
  },
  long_form_rhetorical_analysis: $v06[0].long_form_rhetorical_analysis,
  saturation_audit: {
    challenge_1: $v03[0].saturation_assessment,
    challenge_2: $v04[0].saturation_assessment,
    integrated_confirmation: $v05[0].integrated_confirmation_assessment,
    decision: "PASS"
  },
  integrity_audit: {
    expected_admissions: 30,
    actual_admissions: ($admissions | length),
    unique_source_ids: ($admissions | map(.source_id) | unique | length),
    expected_observations: 120,
    actual_observations: ($observations | length),
    unique_observation_ids: ($observations | map(.id) | unique | length),
    orphan_observations: ($observations | map(select(.source_id as $sid | ($admissions | map(.source_id) | index($sid)) == null)) | map(.id)),
    expected_families: 17,
    actual_families: ($families | length),
    unique_family_ids: ($families | map(.family_id) | unique | length),
    complete_audits: ($admissions | map(select((.whole_text_audit.sections_reviewed | length) > 0)) | length),
    journal_gate_passes: ($admissions | map(select(.journal_gate | startswith("PASS"))) | length),
    long_form_texts: $v06[0].long_form_rhetorical_analysis.text_count,
    long_form_passages: $v06[0].long_form_rhetorical_analysis.passage_count,
    blocked_candidates_counted_as_admitted: 0,
    decision: "PASS"
  },
  residual_gaps: [
    "Academic saturation does not freeze a fast-moving technology, adoption regime, labor market, or macroeconomic environment.",
    "Long-run employment, wage, organization, and welfare effects remain less observed than short-run task outcomes and early-use surveys.",
    "Firm implementation evidence remains uneven across industries, company sizes, worker groups, and countries.",
    "The corpus disciplines reasoning and expression; runtime quality still depends on current evidence coverage and honest missingness."
  ],
  integration_contract: {
    source_profiles: ["adoption", "workforce", "economic_impact"],
    shared_corpus_file: "AI_MACRO_DIFFUSION_ECONOMIC_TRANSMISSION_CORPUS_COMPLETE_v1.0.json",
    compiler_target: "AI_MACRO_LANGUAGE_LAYER_v1.0.json",
    generation_order: ["adoption", "workforce", "economic_impact", "ai_macro_rollup"],
    no_post_generation_rewrite: true,
    no_hidden_api_calls: true
  }
}
