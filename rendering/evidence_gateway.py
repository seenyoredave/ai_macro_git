from __future__ import annotations

import html

import streamlit as st

from rendering.components import render_section


EVIDENCE_TAB_LABEL = "EVIDENCE"

EVIDENCE_LOOKUP = {
    "market": {
        "label": "Market",
        "definition": "Equity performance, participation, concentration, and trading pressure across the configured 204-company AI market universe; not the entire stock market.",
        "datasets": "Retained market-price history · sector history · SEC filing-derived company records",
    },
    "finance": {
        "label": "Finance",
        "definition": "Funding capacity, credit conditions, borrower and lender stress, and cash realization in the covered company and fund records.",
        "datasets": "Retained market and SEC histories · Federal Reserve financial-condition series · private-capital fund records",
    },
    "compute": {
        "label": "Compute",
        "definition": "U.S. compute-manufacturing output, utilization, investment, and announced production projects; project announcements are not operating capacity.",
        "datasets": "Federal Reserve manufacturing history · BEA investment · Census construction · compute project ledger",
    },
    "data_center": {
        "label": "Data Centers",
        "definition": "Project stages, campus locations, and published capacity from the project registry; the registry is evidence of development activity, not a census of the national fleet.",
        "datasets": "Facility registry · campus registry · data-center project records · reviewed identity decisions",
    },
    "connectivity": {
        "label": "Connectivity",
        "definition": "Public evidence of network reach and interconnection depth, including cables, IXPs, facilities, middle-mile awards, and campus proximity; private routes are not fully observed.",
        "datasets": "Cable systems · IXP registry · interconnection facilities · NTIA middle-mile awards",
    },
    "power": {
        "label": "Power",
        "definition": "Electricity demand, operating and planned generation, prices, and large-load context; published data-center MW is not metered electricity demand.",
        "datasets": "EIA electricity records · FRED series · generator pipeline · data-center campus power records",
    },
    "grid_storage": {
        "label": "Grid & Storage",
        "definition": "Interconnection progress, historical queue outcomes, reserve margins, storage duration, and grid construction; queued capacity is not connected capacity.",
        "datasets": "Berkeley Lab grid-connection records · NERC reserve margins · EIA storage · electric-power construction history",
    },
    "water": {
        "label": "Water",
        "definition": "Regional water exposure and facility-level disclosure. State and national water totals provide context but cannot establish supply at a specific campus.",
        "datasets": "USGS water-use records · U.S. Drought Monitor / NOAA · EPA service areas · EIA thermoelectric records · facility water disclosures",
    },
    "adoption": {
        "label": "Adoption",
        "definition": "Reported consumer use and business adoption. Expected future use is intent, not completed deployment, and provider users are not a national adoption rate.",
        "datasets": "Consumer-use history · Census BTOS business adoption · provider commercialization disclosures",
    },
    "workforce": {
        "label": "Workforce",
        "definition": "Observed employment, real pay, openings, hires, quits, layoffs, and a separate task-exposure benchmark. Exposure is not observed displacement.",
        "datasets": "Occupation exposure benchmark · BLS employment and earnings · BLS JOLTS labor flows",
    },
    "economic_impact": {
        "label": "Economic Outcomes",
        "definition": "Economy-wide productivity, output, compensation, labor share, earnings, and investment. These outcomes do not identify AI as the sole cause.",
        "datasets": "BLS productivity and compensation · CPS earnings · BEA investment · FRED · provider commercialization disclosures",
    },
}


def route_to_evidence(domain: str) -> None:
    """Prime the domain-specific Evidence view before Streamlit reruns."""
    if domain not in EVIDENCE_LOOKUP:
        raise KeyError(f"Unknown evidence domain: {domain}")
    st.session_state["evidence-lookup-domain"] = domain
    st.session_state["domain-navigation"] = EVIDENCE_TAB_LABEL


def render_evidence_gateway(domain: str) -> None:
    """Render the common domain-to-Evidence handoff."""
    spec = EVIDENCE_LOOKUP.get(domain)
    if spec is None:
        raise KeyError(f"Unknown evidence domain: {domain}")

    render_section(
        "Evidence",
        "Source records, provenance, coverage, and technical detail for this domain.",
    )
    with st.container(border=True, key=f"evidence-gateway-{domain}"):
        copy_col, action_col = st.columns([4.6, 1.25], gap="large", vertical_alignment="center")
        with copy_col:
            st.markdown(
                (
                    '<div class="rm-evidence-gateway">'
                    '<div class="rm-evidence-gateway-kicker">Data foundation</div>'
                    f'<div class="rm-evidence-gateway-copy">{html.escape(spec["datasets"])}</div>'
                    '</div>'
                ),
                unsafe_allow_html=True,
            )
        with action_col:
            st.button(
                "Inspect evidence",
                key=f"open-evidence-{domain}",
                width="stretch",
                on_click=route_to_evidence,
                args=(domain,),
            )
