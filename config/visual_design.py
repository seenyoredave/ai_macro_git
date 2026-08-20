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
        "Overview",
        "blue",
        "Investment, usable infrastructure, adoption, and broader economic gains.",
        ("macro_transmission_board", "buildout_leadership_rotation", "national_landscape_map"),
    ),
    DomainVisualProfile(
        "market",
        "Market",
        "Capital formation",
        "violet",
        "Public-market value concentration and breadth of gains.",
        ("market_sector_dossier", "market_ownership_map"),
    ),
    DomainVisualProfile(
        "finance",
        "Finance",
        "Capital formation",
        "violet",
        "Funding capacity, customer demand, and financing stress.",
        ("private_capital_realization_map",),
    ),
    DomainVisualProfile(
        "compute",
        "Compute",
        "Construction and infrastructure",
        "blue",
        "U.S. manufacturing capacity and critical supply-chain response to compute demand.",
        ("critical_supply_chain",),
    ),
    DomainVisualProfile(
        "data_centers",
        "Data Centers",
        "Construction and infrastructure",
        "blue",
        "Operating footprint, development pipeline, and published capacity.",
        ("data_center_pipeline_explorer",),
    ),
    DomainVisualProfile(
        "connectivity",
        "Connectivity",
        "Construction and infrastructure",
        "blue",
        "Network access and interconnection depth in major data-center markets.",
        ("connectivity_gateway_map",),
    ),
    DomainVisualProfile(
        "power",
        "Power",
        "Resource constraints",
        "amber",
        "Electricity supply growth, location, and cost.",
        ("power_demand_profile",),
    ),
    DomainVisualProfile(
        "grid_storage",
        "Grid & Storage",
        "Resource constraints",
        "amber",
        "Queue progress, connection times, reliability, storage duration, and grid investment.",
        ("grid_queue_deliverability",),
    ),
    DomainVisualProfile(
        "water",
        "Water",
        "Resource constraints",
        "amber",
        "Local data-center water exposure and facility-level disclosure.",
        ("water_campus_dossier", "water_evidence_ladder"),
    ),
    DomainVisualProfile(
        "adoption",
        "Adoption",
        "Adoption and use",
        "green",
        "Personal use, business adoption, and paid demand.",
        ("adoption_diffusion_history",),
    ),
    DomainVisualProfile(
        "workforce",
        "Workforce",
        "Economic and labor results",
        "green",
        "Employment, hiring, real pay, and task exposure in AI-linked industries.",
        ("workforce_outcomes_matrix",),
    ),
    DomainVisualProfile(
        "economic_outcomes",
        "Economic Outcomes",
        "Economic and labor results",
        "green",
        "Investment, provider revenue, productivity, worker compensation, and household earnings.",
        ("realized_value_transmission",),
    ),
    DomainVisualProfile(
        "evidence",
        "Evidence",
        "Methods and sources",
        "slate",
        "Data, calculations, and sources supporting each measure.",
        ("claim_source_lineage",),
    ),
)


SIGNATURE_TOOLS: tuple[SignatureTool, ...] = (
    SignatureTool(
        "macro_transmission_board",
        "macro",
        "AI Economic Transmission",
        "macro-transmission-pathway-*",
        "Follow market participation, funding, buildout, grid delivery, adoption, and economic outcomes.",
        protected=True,
    ),
    SignatureTool(
        "buildout_leadership_rotation",
        "macro",
        "Buildout Leadership Rotation",
        "macro-buildout-leadership-rotation",
        "Compare construction growth across the major physical infrastructure categories.",
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
        "Sector Profile",
        "sector-detail-*",
        "Show sector returns, breadth, valuation, company concentration, fundamentals, and trading pressure.",
    ),
    SignatureTool(
        "market_ownership_map",
        "market",
        "Public AI Market Ownership",
        "market-ownership-treemap-v3",
        "Compare public AI-equity market value across companies and sectors.",
    ),
    SignatureTool(
        "private_capital_realization_map",
        "finance",
        "Private-Fund Cash Returns",
        "finance-private-capital-map",
        "Compare paid-in capital, cash distributions, and remaining fund value.",
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
        "Data-Center Projects",
        "data-center-leading-pipelines",
        "Compare project status and published capacity across states.",
    ),
    SignatureTool(
        "connectivity_gateway_map",
        "connectivity",
        "Submarine Cable Gateways",
        "connectivity-gateway-map",
        "Map U.S.-connected submarine cable landings against major network and data-center markets.",
    ),
    SignatureTool(
        "power_demand_profile",
        "power",
        "Power Demand Profile",
        "power-demand-history",
        "Compare electricity demand across commercial, industrial, and system-wide measures.",
    ),
    SignatureTool(
        "grid_queue_deliverability",
        "grid_storage",
        "Grid Connection Conditions",
        "grid-storage-*",
        "Compare queue progress, regional conditions, summer reliability, storage duration, and grid construction.",
    ),
    SignatureTool(
        "water_campus_dossier",
        "water",
        "Campus Water Profile",
        "water-campus-dossier-*",
        "Summarize campus status, drought exposure, cooling, water source, and available public disclosure.",
    ),
    SignatureTool(
        "water_evidence_ladder",
        "water",
        "Water Disclosure Coverage",
        "water-evidence-ladder",
        "Compare facilities with no water disclosure, qualitative information, and quantified water data.",
    ),
    SignatureTool(
        "adoption_diffusion_history",
        "adoption",
        "AI Use Over Time",
        "adoption-consumer-history",
        "Compare personal and business AI use over time.",
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
        "From AI Revenue to Economic Results",
        "economic-impact-panel-value-transmission",
        "Compare provider AI revenue with productivity, worker compensation, median earnings, and participation.",
    ),
    SignatureTool(
        "claim_source_lineage",
        "evidence",
        "Claim Sources",
        "evidence-*",
        "Link each analytical claim to its calculation, source record, and date.",
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
