from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Iterable


@dataclass(frozen=True)
class DomainVisualProfile:
    slug: str
    title: str
    stage: str
    accent: str
    central_question: str
    signature_tools: tuple[str, ...]


@dataclass(frozen=True)
class SignatureTool:
    tool_id: str
    domain: str
    title: str
    key_pattern: str
    analytical_job: str
    protected: bool = False
    status: str = "current"


# The stage labels create family resemblance without forcing every domain into
# the same chart vocabulary.  Accents are deliberately restrained to the
# platform palette already used by the application.
DOMAIN_VISUAL_PROFILES: tuple[DomainVisualProfile, ...] = (
    DomainVisualProfile(
        "macro",
        "AI Macro",
        "Platform synthesis",
        "blue",
        "Is capital and infrastructure buildout becoming durable use, broad participation, and realized value?",
        ("buildout_leadership_rotation", "national_landscape_map"),
    ),
    DomainVisualProfile(
        "market",
        "Market",
        "Capital formation",
        "violet",
        "How are public markets allocating capital, pricing expectations, and concentrating exposure across the AI economy?",
        ("market_sector_dossier", "market_ownership_map"),
    ),
    DomainVisualProfile(
        "finance",
        "Finance",
        "Capital formation",
        "violet",
        "Can the AI economy fund expansion, realize revenue, and absorb the resulting financial strain?",
        ("private_capital_realization_map",),
    ),
    DomainVisualProfile(
        "compute",
        "Compute",
        "Physical buildout",
        "blue",
        "Can the critical manufacturing and serving stack supply the compute being demanded?",
        ("critical_supply_chain",),
    ),
    DomainVisualProfile(
        "data_centers",
        "Data Centers",
        "Physical buildout",
        "blue",
        "Where is compute being deployed, at what scale and stage, and with what site evidence?",
        ("data_center_pipeline_explorer",),
    ),
    DomainVisualProfile(
        "connectivity",
        "Connectivity",
        "Physical buildout",
        "blue",
        "Can deployed compute exchange data with users, clouds, and other facilities at sufficient scale and resilience?",
        ("connectivity_gateway_map",),
    ),
    DomainVisualProfile(
        "power",
        "Power",
        "Resource constraints",
        "amber",
        "Can electricity supply arrive at the scale, time, and cost implied by the buildout?",
        ("power_demand_profile",),
    ),
    DomainVisualProfile(
        "grid_storage",
        "Grid & Storage",
        "Resource constraints",
        "amber",
        "Can requested generation and storage become deliverable capacity where and when large loads need it?",
        ("grid_queue_deliverability",),
    ),
    DomainVisualProfile(
        "water",
        "Water",
        "Resource constraints",
        "amber",
        "Where does AI infrastructure create material water exposure, and how well is that exposure disclosed?",
        ("water_campus_dossier", "water_evidence_ladder"),
    ),
    DomainVisualProfile(
        "adoption",
        "Adoption",
        "Use and diffusion",
        "green",
        "Is AI use broadening across people and businesses, and is engagement becoming durable?",
        ("adoption_diffusion_history",),
    ),
    DomainVisualProfile(
        "workforce",
        "Workforce",
        "Realized outcomes",
        "green",
        "How is AI-related investment and adoption transmitting into employment, hiring, compensation, and worker bargaining power?",
        ("workforce_outcomes_matrix",),
    ),
    DomainVisualProfile(
        "economic_outcomes",
        "Economic Outcomes",
        "Realized outcomes",
        "green",
        "Are productivity and output gains becoming broad, durable improvements in compensation, prices, profits, and household welfare?",
        ("realized_value_transmission",),
    ),
    DomainVisualProfile(
        "evidence",
        "Evidence",
        "Methods and provenance",
        "slate",
        "What observations, calculations, and sources support the platform's analytical claims?",
        ("claim_source_lineage",),
    ),
)


SIGNATURE_TOOLS: tuple[SignatureTool, ...] = (
    SignatureTool(
        "buildout_leadership_rotation",
        "macro",
        "Buildout Leadership Rotation",
        "macro-buildout-leadership-rotation",
        "Show how construction momentum rotates across the physical AI stack.",
        protected=True,
    ),
    SignatureTool(
        "national_landscape_map",
        "macro",
        "National Landscape Map",
        "macro-national-landscape-map",
        "Explore facility geography with linked capacity, power, water, and evidence layers.",
        protected=True,
    ),
    SignatureTool(
        "market_sector_dossier",
        "market",
        "Sector Dossier",
        "sector-detail-*",
        "Connect sector condition, structure, contribution, fundamentals, and pressure.",
    ),
    SignatureTool(
        "market_ownership_map",
        "market",
        "Ownership of the AI Universe",
        "market-ownership-treemap-v3",
        "Show the company and sector concentration of the public AI-equity universe.",
    ),
    SignatureTool(
        "private_capital_realization_map",
        "finance",
        "Private-Capital Realization Map",
        "finance-private-capital-map",
        "Separate paid-in capital, distributions, residual value, and realized performance.",
    ),
    SignatureTool(
        "critical_supply_chain",
        "compute",
        "Critical Supply Chain",
        "compute-critical-supply-chain",
        "Expose the project and concentration evidence across logic, memory, packaging, and interconnect.",
    ),
    SignatureTool(
        "data_center_pipeline_explorer",
        "data_centers",
        "Data-Center Pipeline Explorer",
        "data-center-leading-pipelines",
        "Compare facility stages and published capacity across state development pipelines.",
    ),
    SignatureTool(
        "connectivity_gateway_map",
        "connectivity",
        "Connectivity Gateway Map",
        "connectivity-gateway-map",
        "Connect submarine landing gateways to the national interconnection and compute geography.",
    ),
    SignatureTool(
        "power_demand_profile",
        "power",
        "Power Demand Profile",
        "power-demand-history",
        "Show how electricity demand is changing across commercial, industrial, and system-wide measures.",
    ),
    SignatureTool(
        "grid_queue_deliverability",
        "grid_storage",
        "Grid Delivery Pathway",
        "grid-storage-*",
        "Connect queue conversion, regional maturity, seasonal reliability, and operating storage duration.",
    ),
    SignatureTool(
        "water_campus_dossier",
        "water",
        "Campus Water Exposure Dossier",
        "water-campus-dossier-*",
        "Connect campus development with drought conditions, cooling evidence, water source, and disclosure depth.",
    ),
    SignatureTool(
        "water_evidence_ladder",
        "water",
        "Water Evidence Ladder",
        "water-evidence-ladder",
        "Distinguish absent, qualitative, and quantified facility water evidence.",
    ),
    SignatureTool(
        "adoption_diffusion_history",
        "adoption",
        "Adoption Diffusion History",
        "adoption-consumer-history",
        "Show whether reach, workplace use, and engagement are broadening over time.",
    ),
    SignatureTool(
        "workforce_outcomes_matrix",
        "workforce",
        "Workforce Outcomes Matrix",
        "workforce-outcomes-matrix",
        "Separate theoretical occupation-level task exposure from observed employment, real earnings, openings, hires, quits, and layoffs.",
    ),
    SignatureTool(
        "realized_value_transmission",
        "economic_outcomes",
        "Realized-Value Transmission Pathway",
        "economic-impact-panel-value-transmission",
        "Trace observed commercial demand through productivity, worker capture, median earnings, and broad participation.",
    ),
    SignatureTool(
        "claim_source_lineage",
        "evidence",
        "Claim-to-Source Lineage",
        "evidence-*",
        "Trace analytical claims through calculations, observations, and source dates.",
        status="planned",
    ),
)


CHART_ROLE_DEFAULTS: dict[str, dict[str, object]] = {
    "trend": {"height": 360, "legend": "horizontal", "zero_line": False},
    "ranking": {"height": 430, "legend": "none", "zero_line": True},
    "composition": {"height": 390, "legend": "horizontal", "zero_line": True},
    "pipeline": {"height": 430, "legend": "horizontal", "zero_line": True},
    "map": {"height": 520, "legend": "external", "zero_line": False},
    "relationship": {"height": 430, "legend": "horizontal", "zero_line": False},
    "coverage": {"height": 390, "legend": "none", "zero_line": True},
    "diagnostic": {"height": 360, "legend": "conditional", "zero_line": False},
}


_PROFILE_BY_TITLE = {profile.title.casefold(): profile for profile in DOMAIN_VISUAL_PROFILES}
_PROFILE_BY_SLUG = {profile.slug: profile for profile in DOMAIN_VISUAL_PROFILES}
_TOOL_BY_ID = {tool.tool_id: tool for tool in SIGNATURE_TOOLS}


def domain_profile(value: str | None) -> DomainVisualProfile | None:
    token = str(value or "").strip()
    if not token:
        return None
    return _PROFILE_BY_SLUG.get(token) or _PROFILE_BY_TITLE.get(token.casefold())


def signature_tool(tool_id: str) -> SignatureTool:
    return _TOOL_BY_ID[tool_id]


def matching_signature_tools(chart_key: str) -> tuple[SignatureTool, ...]:
    return tuple(
        tool for tool in SIGNATURE_TOOLS
        if tool.status == "current" and fnmatch(chart_key, tool.key_pattern)
    )


def protected_signature_tools() -> tuple[SignatureTool, ...]:
    return tuple(tool for tool in SIGNATURE_TOOLS if tool.protected)


def planned_signature_tools() -> tuple[SignatureTool, ...]:
    return tuple(tool for tool in SIGNATURE_TOOLS if tool.status == "planned")


def all_signature_ids() -> set[str]:
    return set(_TOOL_BY_ID)


def validate_visual_contract() -> list[str]:
    errors: list[str] = []
    profile_slugs = {profile.slug for profile in DOMAIN_VISUAL_PROFILES}
    if len(profile_slugs) != len(DOMAIN_VISUAL_PROFILES):
        errors.append("Domain visual profile slugs must be unique.")
    tool_ids = [tool.tool_id for tool in SIGNATURE_TOOLS]
    if len(tool_ids) != len(set(tool_ids)):
        errors.append("Signature-tool identifiers must be unique.")
    for profile in DOMAIN_VISUAL_PROFILES:
        if not 1 <= len(profile.signature_tools) <= 2:
            errors.append(f"{profile.title} must own one or two signature tools.")
        for tool_id in profile.signature_tools:
            tool = _TOOL_BY_ID.get(tool_id)
            if tool is None:
                errors.append(f"{profile.title} references unknown signature tool {tool_id!r}.")
            elif tool.domain != profile.slug:
                errors.append(f"{tool_id!r} is assigned to {tool.domain}, not {profile.slug}.")
    for tool in SIGNATURE_TOOLS:
        if tool.domain not in profile_slugs:
            errors.append(f"Signature tool {tool.tool_id!r} references unknown domain {tool.domain!r}.")
        if tool.status not in {"current", "planned"}:
            errors.append(f"Signature tool {tool.tool_id!r} has unsupported status {tool.status!r}.")
        if tool.protected and tool.status != "current":
            errors.append(f"Protected signature tool {tool.tool_id!r} must be current.")
    protected = {tool.tool_id for tool in protected_signature_tools()}
    required = {"buildout_leadership_rotation", "national_landscape_map"}
    if not required.issubset(protected):
        errors.append("Buildout Leadership Rotation and National Landscape Map must remain protected.")
    return errors
