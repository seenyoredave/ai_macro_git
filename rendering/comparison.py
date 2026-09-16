"""Point-in-time comparison controls and reader-facing change surfaces."""

from __future__ import annotations

from datetime import date, timedelta
import html
from typing import Any

import pandas as pd
import streamlit as st

from analytics.change_engine import ChangeSet, build_change_set
from analytics.comparison_state import (
    ComparisonMode,
    ComparisonRequest,
    ComparisonState,
    resolve_comparison_state,
)
from analytics.read_evidence import DOMAIN_LABELS


_COMPARISON_OPTION_PREVIOUS = "Previous publication"
_COMPARISON_OPTION_7D = "7 days earlier"
_COMPARISON_OPTION_30D = "30 days earlier"
_COMPARISON_OPTION_CUSTOM = "Custom date"
_COMPARISON_OPTION_CURRENT = "Current publication only"
_COMPARISON_OPTIONS = (
    _COMPARISON_OPTION_PREVIOUS,
    _COMPARISON_OPTION_7D,
    _COMPARISON_OPTION_30D,
    _COMPARISON_OPTION_CUSTOM,
    _COMPARISON_OPTION_CURRENT,
)

_DOMAIN_TITLE_KEYS = {
    "Market": "market",
    "Finance": "finance",
    "Compute": "compute",
    "Data Centers": "data_center",
    "Connectivity": "connectivity",
    "Power": "power",
    "Grid & Storage": "grid_storage",
    "Water": "water",
    "Adoption": "adoption",
    "Workforce": "workforce",
    "Economic Outcomes": "economic_impact",
}

_CLASS_LABELS = {
    "regime_threshold_crossed": "Threshold crossed",
    "metric_new": "New metric",
    "metric_unavailable": "Unavailable",
    "metric_restored": "Restored",
    "material_movement": "Material move",
    "categorical_change": "Category changed",
    "incremental_change": "Incremental move",
    "quality_changed": "Quality changed",
    "unchanged": "Unchanged",
}

_CLASS_ORDER = {
    "regime_threshold_crossed": 0,
    "metric_new": 1,
    "metric_unavailable": 1,
    "metric_restored": 1,
    "material_movement": 2,
    "categorical_change": 3,
    "incremental_change": 4,
    "quality_changed": 5,
    "unchanged": 9,
}

_SOURCE_REPORT_KEYS = {
    "market": "market",
    "finance": "finance",
    "compute": "infrastructure",
    "data_center": "infrastructure",
    "connectivity": "connectivity",
    "power": "power_grid",
    "grid_storage": "power_grid",
    "water": "water",
    "adoption": "adoption",
    "workforce": "workforce",
    "economic_impact": "economic_outcomes",
}


def _safe_int(value: Any) -> int:
    numeric = pd.to_numeric(value, errors="coerce")
    return int(numeric) if pd.notna(numeric) else 0


def _date_label(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="coerce", format="mixed")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%b %d, %Y").replace(" 0", " ")



def comparison_ready(change_set: ChangeSet | None) -> bool:
    if change_set is None:
        return False
    comparison = getattr(change_set, "comparison", None)
    return bool(
        comparison is not None
        and getattr(comparison, "comparison_available", False)
        and getattr(comparison, "head", None) is not None
        and getattr(comparison, "baseline", None) is not None
    )


def comparison_subtitle(change_set: ChangeSet | None) -> str:
    if not comparison_ready(change_set):
        return ""
    comparison = change_set.comparison
    baseline_date = _date_label(comparison.baseline.observation_date)
    return f"Changes since the {baseline_date} publication." if baseline_date else "Changes since the comparison publication."


def comparison_request_for_option(
    option: str,
    *,
    head_snapshot_id: str,
    custom_date: Any = None,
) -> ComparisonRequest:
    """Translate one reader selection into the analytical comparison contract."""
    selected = str(option or _COMPARISON_OPTION_PREVIOUS)
    common = {"head_snapshot_id": str(head_snapshot_id or "")}
    if selected == _COMPARISON_OPTION_CURRENT:
        return ComparisonRequest(mode=ComparisonMode.CURRENT_ONLY, **common)
    if selected == _COMPARISON_OPTION_7D:
        return ComparisonRequest(mode=ComparisonMode.LOOKBACK_DAYS, lookback_days=7, **common)
    if selected == _COMPARISON_OPTION_30D:
        return ComparisonRequest(mode=ComparisonMode.LOOKBACK_DAYS, lookback_days=30, **common)
    if selected == _COMPARISON_OPTION_CUSTOM:
        return ComparisonRequest(mode=ComparisonMode.AS_OF, baseline_as_of=custom_date, **common)
    return ComparisonRequest(mode=ComparisonMode.PREVIOUS_PUBLICATION, **common)


def _default_custom_date(state: ComparisonState | None) -> date:
    head = getattr(state, "head", None)
    parsed = pd.to_datetime(getattr(head, "observation_date", ""), errors="coerce", format="mixed")
    if pd.isna(parsed):
        return date.today() - timedelta(days=7)
    return parsed.date() - timedelta(days=7)


@st.cache_data(show_spinner=False)
def _resolve_comparison_cached(
    head_snapshot_id: str,
    mode: str,
    lookback_days: int,
    baseline_as_of: str,
) -> tuple[ComparisonState, ChangeSet]:
    request = ComparisonRequest(
        head_snapshot_id=str(head_snapshot_id or ""),
        mode=mode,
        lookback_days=max(1, int(lookback_days or 1)),
        baseline_as_of=str(baseline_as_of or ""),
    )
    state = resolve_comparison_state(request)
    return state, build_change_set(state)


def _resolve_reader_comparison(request: ComparisonRequest) -> tuple[ComparisonState, ChangeSet]:
    baseline_as_of = request.baseline_as_of
    if isinstance(baseline_as_of, date):
        baseline_text = baseline_as_of.isoformat()
    else:
        baseline_text = str(baseline_as_of or "")
    return _resolve_comparison_cached(
        str(request.head_snapshot_id or ""),
        str(request.mode),
        int(request.lookback_days or 1),
        baseline_text,
    )


def _control_summary_html(state: ComparisonState, change_set: ChangeSet) -> str:
    head = state.head
    baseline = state.baseline
    head_date = _date_label(head.observation_date if head else "") or "Current publication"
    if not state.comparison_available or baseline is None:
        detail = "Current publication only" if state.mode == ComparisonMode.CURRENT_ONLY.value else "Comparison history unavailable"
        return (
            '<div class="rm-comparison-status">'
            '<div class="rm-comparison-kicker">Point-in-time view</div>'
            f'<div class="rm-comparison-status-main">{html.escape(detail)}</div>'
            f'<div class="rm-comparison-status-sub">{html.escape(head_date)}</div>'
            '</div>'
        )

    summary = dict(change_set.summary or {})
    changed = _safe_int(summary.get("changed_metric_count"))
    material = _safe_int(summary.get("material_change_count"))
    crossings = _safe_int(summary.get("threshold_crossing_count"))
    baseline_date = _date_label(baseline.observation_date) or baseline.observation_date
    parts = [f"{changed} changed", f"{material} material"]
    if crossings:
        parts.append(f"{crossings} threshold crossing{'s' if crossings != 1 else ''}")
    return (
        '<div class="rm-comparison-status">'
        '<div class="rm-comparison-kicker">Point-in-time view</div>'
        f'<div class="rm-comparison-status-main">{html.escape(" · ".join(parts))}</div>'
        f'<div class="rm-comparison-status-sub">Current {html.escape(head_date)} · baseline {html.escape(baseline_date)}</div>'
        '</div>'
    )


def render_global_comparison_controls(
    *,
    canonical_snapshot_id: str,
    current_state: ComparisonState | None = None,
    current_change_set: ChangeSet | None = None,
) -> tuple[ComparisonState | None, ChangeSet | None]:
    """Render the global baseline selector and resolve the selected retained comparison."""
    head_snapshot_id = str(canonical_snapshot_id or "").strip()
    head = getattr(current_state, "head", None)
    if not head_snapshot_id and head is not None:
        head_snapshot_id = str(head.snapshot_id or "")

    with st.container(key="global-comparison-control"):
        current_col, select_col, status_col = st.columns([0.95, 1.15, 1.9], vertical_alignment="center")
        with current_col:
            head_date = _date_label(getattr(head, "observation_date", ""))
            detail = head_date or "Latest retained publication"
            st.markdown(
                '<div class="rm-comparison-current">'
                '<div class="rm-comparison-kicker">Current publication</div>'
                f'<div class="rm-comparison-current-value">{html.escape(detail)}</div>'
                '</div>',
                unsafe_allow_html=True,
            )

        with select_col:
            option = st.selectbox(
                "Compare with",
                _COMPARISON_OPTIONS,
                key="comparison-baseline-option",
                label_visibility="visible",
            )
            custom_date = None
            if option == _COMPARISON_OPTION_CUSTOM:
                if "comparison-custom-date" not in st.session_state:
                    st.session_state["comparison-custom-date"] = _default_custom_date(current_state)
                head_date_value = pd.to_datetime(
                    getattr(head, "observation_date", ""), errors="coerce", format="mixed"
                )
                max_value = head_date_value.date() if pd.notna(head_date_value) else date.today()
                stored_custom = pd.to_datetime(
                    st.session_state.get("comparison-custom-date"), errors="coerce", format="mixed"
                )
                if pd.notna(stored_custom) and stored_custom.date() > max_value:
                    st.session_state["comparison-custom-date"] = max_value
                custom_date = st.date_input(
                    "Comparison date",
                    max_value=max_value,
                    key="comparison-custom-date",
                )

        request = comparison_request_for_option(
            option,
            head_snapshot_id=head_snapshot_id,
            custom_date=custom_date,
        )
        try:
            state, change_set = _resolve_reader_comparison(request)
        except Exception:
            state = current_state
            change_set = current_change_set

        with status_col:
            if state is not None and change_set is not None:
                st.markdown(_control_summary_html(state, change_set), unsafe_allow_html=True)
            else:
                st.markdown(
                    '<div class="rm-comparison-status">'
                    '<div class="rm-comparison-kicker">Point-in-time view</div>'
                    '<div class="rm-comparison-status-main">Comparison unavailable</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )

    return state, change_set


def _changed_frame(change_set: ChangeSet | None, *, domain: str | None = None) -> pd.DataFrame:
    if change_set is None or not isinstance(getattr(change_set, "frame", None), pd.DataFrame):
        return pd.DataFrame()
    frame = change_set.frame.copy()
    if frame.empty or "classification" not in frame.columns:
        return pd.DataFrame()
    frame = frame.loc[frame["classification"].astype(str).ne("unchanged")].copy()
    if domain:
        frame = frame.loc[frame["domain"].astype(str).eq(domain)].copy()
    return frame.reset_index(drop=True)


def render_domain_change_line(title: str, change_set: ChangeSet | None) -> None:
    """Render a quiet comparison line under an existing domain header."""
    domain = _DOMAIN_TITLE_KEYS.get(str(title))
    if not domain or not comparison_ready(change_set):
        return
    frame = _changed_frame(change_set, domain=domain)
    material = int(frame["material"].fillna(False).astype(bool).sum()) if not frame.empty and "material" in frame.columns else 0
    crossings = int(frame["classification"].astype(str).eq("regime_threshold_crossed").sum()) if not frame.empty else 0
    baseline = change_set.comparison.baseline
    baseline_date = _date_label(baseline.observation_date if baseline else "")
    if frame.empty:
        copy = f"No metric changes since {baseline_date}." if baseline_date else "No metric changes in the selected comparison."
    else:
        pieces = [f"{len(frame)} metric{'s' if len(frame) != 1 else ''} changed"]
        if material:
            pieces.append(f"{material} material")
        if crossings:
            pieces.append(f"{crossings} threshold crossing{'s' if crossings != 1 else ''}")
        if baseline_date:
            pieces.append(f"since {baseline_date}")
        copy = " · ".join(pieces)
    st.markdown(
        f'<div class="rm-domain-change-line">{html.escape(copy)}</div>',
        unsafe_allow_html=True,
    )


def _rank_changes(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    ranked = frame.copy()
    ranked["_class_order"] = ranked["classification"].map(_CLASS_ORDER).fillna(8).astype(int)
    ranked["_material_order"] = (~ranked.get("material", False).fillna(False).astype(bool)).astype(int)
    ratio = pd.to_numeric(ranked.get("materiality_ratio"), errors="coerce")
    ranked["_ratio"] = ratio.fillna(-1.0)
    return ranked.sort_values(
        ["_material_order", "_class_order", "_ratio", "domain", "label"],
        ascending=[True, True, False, True, True],
        kind="stable",
    ).drop(columns=["_class_order", "_material_order", "_ratio"])


def _change_card_html(row: pd.Series) -> str:
    domain = DOMAIN_LABELS.get(str(row.get("domain") or ""), str(row.get("domain") or "").replace("_", " ").title())
    label = str(row.get("label") or row.get("metric_id") or "Metric")
    base = str(row.get("base_display") or "n/a")
    head = str(row.get("head_display") or "n/a")
    classification = _CLASS_LABELS.get(str(row.get("classification") or ""), "Changed")
    direction = str(row.get("direction") or "flat")
    arrow = "↑" if direction == "up" else "↓" if direction == "down" else "→"
    return (
        '<div class="rm-change-card">'
        f'<div class="rm-change-card-kicker">{html.escape(domain)} · {html.escape(classification)}</div>'
        f'<div class="rm-change-card-label">{html.escape(label)}</div>'
        f'<div class="rm-change-card-value">{html.escape(head)}</div>'
        f'<div class="rm-change-card-prior">{html.escape(base)} <span>{arrow}</span> {html.escape(head)}</div>'
        '</div>'
    )


def render_macro_change_overview(change_set: ChangeSet | None, *, limit: int = 6) -> None:
    """Render the deterministic cross-domain publication diff on the Macro tab."""
    if not comparison_ready(change_set):
        st.caption("A prior canonical publication is not available for comparison yet.")
        return
    frame = _rank_changes(_changed_frame(change_set))
    summary = dict(change_set.summary or {})
    if frame.empty:
        st.markdown(
            '<div class="rm-change-empty">No analytical metrics changed in the selected comparison.</div>',
            unsafe_allow_html=True,
        )
        return

    stats = (
        ("Changed metrics", _safe_int(summary.get("changed_metric_count"))),
        ("Material moves", _safe_int(summary.get("material_change_count"))),
        ("Threshold crossings", _safe_int(summary.get("threshold_crossing_count"))),
        ("Domains changed", len(summary.get("changed_domains") or [])),
    )
    stat_html = "".join(
        '<div class="rm-change-stat">'
        f'<div class="rm-change-stat-value">{value}</div>'
        f'<div class="rm-change-stat-label">{html.escape(label)}</div>'
        '</div>'
        for label, value in stats
    )
    cards = "".join(_change_card_html(row) for _, row in frame.head(max(1, int(limit))).iterrows())
    st.markdown(
        f'<div class="rm-change-stats">{stat_html}</div>'
        f'<div class="rm-change-grid">{cards}</div>',
        unsafe_allow_html=True,
    )


def _metric_option_label(row: pd.Series) -> str:
    label = str(row.get("label") or row.get("metric_id") or "Metric")
    head = str(row.get("head_display") or "n/a")
    base = str(row.get("base_display") or "n/a")
    return f"{label} · {base} → {head}"


def _read_claims_for_fact(read: dict[str, Any], fact_id: str) -> list[str]:
    claims: list[str] = []
    for support in read.get("claim_support", []) or []:
        if not isinstance(support, dict):
            continue
        ids = {str(item or "").strip() for item in support.get("fact_ids", []) or []}
        text = str(support.get("text") or "").strip()
        if fact_id in ids and text and text not in claims:
            claims.append(text)
    return claims


def _source_modes(payload: Any) -> list[str]:
    modes: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in {"source_mode", "refresh_status", "status"} and isinstance(value, str):
                text = value.strip().replace("_", " ")
                if text and text not in modes:
                    modes.append(text)
            elif isinstance(value, (dict, list, tuple)):
                for text in _source_modes(value):
                    if text not in modes:
                        modes.append(text)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            for text in _source_modes(item):
                if text not in modes:
                    modes.append(text)
    return modes


def _snapshot_source_modes(snapshot_id: str, domain: str) -> list[str]:
    try:
        from analytics.canonical_store import canonical_snapshot_source_status

        payload = canonical_snapshot_source_status(snapshot_id)
    except Exception:
        return []
    key = _SOURCE_REPORT_KEYS.get(domain, domain)
    report = payload.get(key, {}) if isinstance(payload, dict) else {}
    return _source_modes(report)[:4]


def _metric_sources(metric_id: str) -> pd.DataFrame:
    try:
        from analytics.canonical_store import canonical_metric_sources

        return canonical_metric_sources(metric_id)
    except Exception:
        return pd.DataFrame()


def _fact_context(evidence_packets: dict | None, domain: str, fact_id: str) -> str:
    packet = dict((evidence_packets or {}).get(domain) or {})
    for fact in packet.get("facts", []) or []:
        if isinstance(fact, dict) and str(fact.get("id") or "") == fact_id:
            return str(fact.get("context") or "").strip()
    return ""


def render_change_evidence(
    comparison_state: ComparisonState | None,
    change_set: ChangeSet | None,
    *,
    platform_reads: dict | None,
    evidence_packets: dict | None,
) -> None:
    """Drill from a deterministic metric change into sources and published commentary."""
    if not comparison_ready(change_set) or comparison_state is None:
        st.caption("A prior canonical publication is not available for change evidence yet.")
        return
    frame = _rank_changes(_changed_frame(change_set))
    if frame.empty:
        st.caption("No analytical metrics changed in the selected comparison.")
        return

    domains = list(dict.fromkeys(frame["domain"].dropna().astype(str)))
    domain = st.selectbox(
        "Changed domain",
        domains,
        format_func=lambda value: DOMAIN_LABELS.get(value, value.replace("_", " ").title()),
        key="change-evidence-domain",
    )
    domain_frame = frame.loc[frame["domain"].astype(str).eq(domain)].reset_index(drop=True)
    metric_ids = domain_frame["metric_id"].astype(str).tolist()
    row_index = {str(row.get("metric_id")): row for _, row in domain_frame.iterrows()}
    metric_id = st.selectbox(
        "Changed metric",
        metric_ids,
        format_func=lambda value: _metric_option_label(row_index[value]),
        key="change-evidence-metric",
    )
    row = row_index[metric_id]

    label = str(row.get("label") or metric_id)
    base = str(row.get("base_display") or "n/a")
    head = str(row.get("head_display") or "n/a")
    classification = _CLASS_LABELS.get(str(row.get("classification") or ""), "Changed")
    domain_label = DOMAIN_LABELS.get(domain, domain.replace("_", " ").title())
    context = _fact_context(evidence_packets, domain, metric_id)
    context_html = (
        f'<div class="rm-change-evidence-context">{html.escape(context)}</div>'
        if context
        else ""
    )
    st.markdown(
        '<div class="rm-change-evidence-hero">'
        f'<div class="rm-change-card-kicker">{html.escape(domain_label)} · {html.escape(classification)}</div>'
        f'<div class="rm-change-evidence-title">{html.escape(label)}</div>'
        '<div class="rm-change-evidence-values">'
        f'<span><b>{html.escape(base)}</b><small>Baseline</small></span>'
        '<span class="rm-change-evidence-arrow">→</span>'
        f'<span><b>{html.escape(head)}</b><small>Current</small></span>'
        '</div>'
        f'{context_html}'
        '</div>',
        unsafe_allow_html=True,
    )

    baseline = comparison_state.baseline
    head_ref = comparison_state.head
    meta_cols = st.columns(3)
    meta_items = (
        ("Baseline publication", _date_label(baseline.observation_date if baseline else "") or "n/a"),
        ("Current publication", _date_label(head_ref.observation_date if head_ref else "") or "n/a"),
        ("Data quality", str(row.get("head_quality") or "n/a").replace("_", " ")),
    )
    for col, (name, value) in zip(meta_cols, meta_items, strict=True):
        with col:
            st.markdown(
                '<div class="rm-change-meta-card">'
                f'<div class="rm-change-meta-label">{html.escape(name)}</div>'
                f'<div class="rm-change-meta-value">{html.escape(value)}</div>'
                '</div>',
                unsafe_allow_html=True,
            )

    sources = _metric_sources(metric_id)
    modes = _snapshot_source_modes(head_ref.snapshot_id if head_ref else "", domain)
    source_col, read_col = st.columns(2)
    with source_col:
        st.markdown("**Source register**")
        if sources is None or sources.empty:
            st.caption("No registered source links are available for this metric.")
        else:
            links = []
            for _, source in sources.iterrows():
                name = str(source.get("source_label") or "Source")
                url = str(source.get("source_url") or "").strip()
                if url.startswith("https://"):
                    links.append(f"[{name}]({url})")
                else:
                    links.append(name)
            st.markdown(" · ".join(links))
        if modes:
            st.caption("Current source state: " + " · ".join(modes))

    with read_col:
        st.markdown("**Published Read linkage**")
        reads = dict(platform_reads or {})
        claim_groups: list[tuple[str, str]] = []
        for key, display in ((domain, domain_label), ("macro", "AI Macro")):
            for claim in _read_claims_for_fact(dict(reads.get(key) or {}), metric_id):
                claim_groups.append((display, claim))
        if not claim_groups:
            st.caption("This metric is not cited in the current published Read.")
        else:
            for display, claim in claim_groups[:4]:
                st.markdown(
                    '<div class="rm-change-read-link">'
                    f'<div class="rm-change-read-label">{html.escape(display)}</div>'
                    f'<div class="rm-change-read-copy">{html.escape(claim)}</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )


__all__ = [
    "comparison_ready",
    "comparison_request_for_option",
    "comparison_subtitle",
    "render_change_evidence",
    "render_domain_change_line",
    "render_global_comparison_controls",
    "render_macro_change_overview",
]
