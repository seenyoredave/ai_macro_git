"""Point-in-time comparison controls and reader-facing change surfaces."""

from __future__ import annotations

from datetime import date, timedelta
import html
from typing import Any

import pandas as pd
import streamlit as st

from analytics.change_engine import COVERAGE_CHANGE_CLASSES, ChangeSet, build_change_set
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
    "material_movement": 1,
    "categorical_change": 2,
    "incremental_change": 3,
    "quality_changed": 4,
    "metric_new": 5,
    "metric_unavailable": 5,
    "metric_restored": 5,
    "unchanged": 9,
}

_LEDGER_VIEW_ALL = "All changes"
_LEDGER_VIEW_COMPARABLE = "Comparable changes"
_LEDGER_VIEW_MATERIAL = "Material comparable changes"
_LEDGER_VIEW_COVERAGE = "Coverage changes"
_LEDGER_VIEWS = (
    _LEDGER_VIEW_ALL,
    _LEDGER_VIEW_COMPARABLE,
    _LEDGER_VIEW_MATERIAL,
    _LEDGER_VIEW_COVERAGE,
)

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


def _comparison_value_html(label: str, value: str) -> str:
    return (
        '<div class="rm-comparison-segment">'
        f'<div class="rm-comparison-segment-label">{html.escape(str(label))}</div>'
        f'<div class="rm-comparison-segment-value">{html.escape(str(value))}</div>'
        '</div>'
    )


def _selection_request(
    *,
    canonical_snapshot_id: str,
    current_state: ComparisonState | None,
) -> ComparisonRequest:
    head_snapshot_id = str(canonical_snapshot_id or "").strip()
    head = getattr(current_state, "head", None)
    if not head_snapshot_id and head is not None:
        head_snapshot_id = str(head.snapshot_id or "")

    option = str(
        st.session_state.get("comparison-baseline-option", _COMPARISON_OPTION_PREVIOUS)
        or _COMPARISON_OPTION_PREVIOUS
    )
    if option not in _COMPARISON_OPTIONS:
        option = _COMPARISON_OPTION_PREVIOUS

    custom_date = None
    if option == _COMPARISON_OPTION_CUSTOM:
        custom_date = st.session_state.get("comparison-custom-date")
        if custom_date is None:
            custom_date = _default_custom_date(current_state)

    return comparison_request_for_option(
        option,
        head_snapshot_id=head_snapshot_id,
        custom_date=custom_date,
    )


def resolve_comparison_selection(
    *,
    canonical_snapshot_id: str,
    current_state: ComparisonState | None = None,
    current_change_set: ChangeSet | None = None,
) -> tuple[ComparisonState | None, ChangeSet | None]:
    """Resolve the persisted reader selection without rendering controls."""
    request = _selection_request(
        canonical_snapshot_id=canonical_snapshot_id,
        current_state=current_state,
    )
    try:
        return _resolve_reader_comparison(request)
    except Exception:
        return current_state, current_change_set


def _comparison_period_text(state: ComparisonState | None) -> str:
    if state is None:
        return "Comparison unavailable"
    if state.mode == ComparisonMode.CURRENT_ONLY.value:
        return "Current publication only"
    baseline = getattr(state, "baseline", None)
    if baseline is None:
        return "No comparison baseline"
    baseline_date = _date_label(getattr(baseline, "observation_date", ""))
    return f"Since {baseline_date}" if baseline_date else "Selected comparison"


def _point_in_time_text(state: ComparisonState | None, change_set: ChangeSet | None) -> str:
    if state is None or change_set is None:
        return "Comparison unavailable"
    if state.mode == ComparisonMode.CURRENT_ONLY.value:
        return "Current publication only"
    if not getattr(state, "comparison_available", False) or getattr(state, "baseline", None) is None:
        return "Comparison history unavailable"

    counts = _presentation_counts(change_set)
    parts = [
        f"{counts['comparable']} comparable",
        f"{counts['material']} material",
    ]
    if counts["coverage"]:
        parts.append(f"{counts['coverage']} coverage")
    return " · ".join(parts)


def render_macro_comparison_toolbar(
    *,
    canonical_snapshot_id: str,
    current_state: ComparisonState | None = None,
    current_change_set: ChangeSet | None = None,
) -> tuple[ComparisonState | None, ChangeSet | None]:
    """Render the point-in-time controls in the Macro comparison section."""
    state, change_set = resolve_comparison_selection(
        canonical_snapshot_id=canonical_snapshot_id,
        current_state=current_state,
        current_change_set=current_change_set,
    )
    head = getattr(state, "head", None) or getattr(current_state, "head", None)
    head_date = _date_label(getattr(head, "observation_date", "")) or "Latest retained publication"

    with st.container(key="macro-comparison-toolbar"):
        title_col, current_col, select_col, status_col = st.columns(
            [1.25, 1.0, 1.35, 1.75],
            vertical_alignment="center",
        )
        with title_col:
            st.markdown(
                _comparison_value_html("What changed", _comparison_period_text(state)),
                unsafe_allow_html=True,
            )

        with current_col:
            st.markdown(
                _comparison_value_html("Current publication", head_date),
                unsafe_allow_html=True,
            )

        with select_col:
            option = st.selectbox(
                "Compare with",
                _COMPARISON_OPTIONS,
                key="comparison-baseline-option",
                label_visibility="visible",
            )
            if option == _COMPARISON_OPTION_CUSTOM:
                if "comparison-custom-date" not in st.session_state:
                    st.session_state["comparison-custom-date"] = _default_custom_date(state or current_state)
                head_date_value = pd.to_datetime(
                    getattr(head, "observation_date", ""),
                    errors="coerce",
                    format="mixed",
                )
                max_value = head_date_value.date() if pd.notna(head_date_value) else date.today()
                stored_custom = pd.to_datetime(
                    st.session_state.get("comparison-custom-date"),
                    errors="coerce",
                    format="mixed",
                )
                if pd.notna(stored_custom) and stored_custom.date() > max_value:
                    st.session_state["comparison-custom-date"] = max_value
                st.date_input(
                    "Comparison date",
                    max_value=max_value,
                    key="comparison-custom-date",
                )

        # The selection is already present in session state on a widget-triggered
        # rerun. Resolve once more here so the Macro surface remains correct if a
        # caller invokes it outside the normal app orchestration path.
        state, change_set = resolve_comparison_selection(
            canonical_snapshot_id=canonical_snapshot_id,
            current_state=state or current_state,
            current_change_set=change_set or current_change_set,
        )

        with status_col:
            st.markdown(
                _comparison_value_html("Point-in-time view", _point_in_time_text(state, change_set)),
                unsafe_allow_html=True,
            )

    st.session_state.comparison_state = state
    st.session_state.comparison_change_set = change_set
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


def _coverage_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=getattr(frame, "columns", None))
    return frame.loc[frame["classification"].astype(str).isin(COVERAGE_CHANGE_CLASSES)].copy()


def _comparable_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=getattr(frame, "columns", None))
    return frame.loc[~frame["classification"].astype(str).isin(COVERAGE_CHANGE_CLASSES)].copy()


def _presentation_counts(change_set: ChangeSet | None) -> dict[str, int]:
    """Derive reader counts from the actual classified frame.

    This intentionally does not trust persisted/older summary dictionaries so a
    rendering upgrade remains accurate when a retained ChangeSet predates newer
    summary keys.
    """
    changed = _changed_frame(change_set)
    comparable = _comparable_frame(changed)
    coverage = _coverage_frame(changed)
    material = (
        int(comparable["material"].fillna(False).astype(bool).sum())
        if not comparable.empty and "material" in comparable.columns
        else 0
    )
    crossings = (
        int(comparable["classification"].astype(str).eq("regime_threshold_crossed").sum())
        if not comparable.empty and "classification" in comparable.columns
        else 0
    )
    return {
        "changed": int(len(changed)),
        "comparable": int(len(comparable)),
        "material": material,
        "coverage": int(len(coverage)),
        "crossings": crossings,
    }


def render_domain_change_line(title: str, change_set: ChangeSet | None) -> None:
    """Render a quiet comparison line under an existing domain header."""
    domain = _DOMAIN_TITLE_KEYS.get(str(title))
    if not domain or not comparison_ready(change_set):
        return
    frame = _changed_frame(change_set, domain=domain)
    comparable = _comparable_frame(frame)
    coverage = _coverage_frame(frame)
    material = int(comparable["material"].fillna(False).astype(bool).sum()) if not comparable.empty and "material" in comparable.columns else 0
    crossings = int(comparable["classification"].astype(str).eq("regime_threshold_crossed").sum()) if not comparable.empty else 0
    baseline = change_set.comparison.baseline
    baseline_date = _date_label(baseline.observation_date if baseline else "")
    if frame.empty:
        copy = f"No metric changes since {baseline_date}." if baseline_date else "No metric changes in the selected comparison."
    else:
        pieces = []
        if len(comparable):
            pieces.append(f"{len(comparable)} comparable change{'s' if len(comparable) != 1 else ''}")
        if material:
            pieces.append(f"{material} material")
        if len(coverage):
            pieces.append(f"{len(coverage)} coverage change{'s' if len(coverage) != 1 else ''}")
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
    ranked["_coverage_order"] = ranked["classification"].astype(str).isin(COVERAGE_CHANGE_CLASSES).astype(int)
    ranked["_class_order"] = ranked["classification"].map(_CLASS_ORDER).fillna(8).astype(int)
    ranked["_material_order"] = (~ranked.get("material", False).fillna(False).astype(bool)).astype(int)
    ratio = pd.to_numeric(ranked.get("materiality_ratio"), errors="coerce")
    ranked["_ratio"] = ratio.fillna(-1.0)
    return ranked.sort_values(
        ["_coverage_order", "_material_order", "_class_order", "_ratio", "domain", "label"],
        ascending=[True, True, True, False, True, True],
        kind="stable",
    ).drop(columns=["_coverage_order", "_class_order", "_material_order", "_ratio"])


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


def _delta_text(row: pd.Series) -> str:
    value = pd.to_numeric(row.get("delta_display"), errors="coerce")
    if pd.isna(value):
        return "—"
    digits_value = pd.to_numeric(row.get("display_digits"), errors="coerce")
    digits = int(digits_value) if pd.notna(digits_value) else 1
    digits = max(0, min(digits, 6))
    unit = str(row.get("unit") or "").strip()
    suffix = "%" if unit == "%" else (f" {unit}" if unit else "")
    return f"{float(value):+,.{digits}f}{suffix}"


def _ledger_frame(change_set: ChangeSet | None, view: str) -> pd.DataFrame:
    frame = _rank_changes(_changed_frame(change_set))
    if frame.empty:
        return pd.DataFrame()
    if view == _LEDGER_VIEW_COMPARABLE:
        frame = _comparable_frame(frame)
    elif view == _LEDGER_VIEW_MATERIAL:
        frame = _comparable_frame(frame)
        frame = frame.loc[frame["material"].fillna(False).astype(bool)].copy()
    elif view == _LEDGER_VIEW_COVERAGE:
        frame = _coverage_frame(frame)

    rows = []
    for _, row in frame.iterrows():
        domain = str(row.get("domain") or "")
        classification = str(row.get("classification") or "")
        material_value = row.get("material")
        material = bool(material_value) if pd.notna(material_value) else False
        rows.append({
            "Domain": DOMAIN_LABELS.get(domain, domain.replace("_", " ").title()),
            "Metric": str(row.get("label") or row.get("metric_id") or "Metric"),
            "Baseline": str(row.get("base_display") or "n/a"),
            "Current": str(row.get("head_display") or "n/a"),
            "Change": _delta_text(row),
            "Classification": _CLASS_LABELS.get(classification, classification.replace("_", " ").title()),
            "Group": "Coverage" if classification in COVERAGE_CHANGE_CLASSES else "Comparable",
            "Material": "Yes" if material else "No",
        })
    return pd.DataFrame(rows)


def render_all_changed_metrics(change_set: ChangeSet | None) -> None:
    """Expose the complete deterministic change ledger without leaving the Macro tab."""
    if not comparison_ready(change_set):
        return
    total = len(_changed_frame(change_set))
    if not total:
        return
    with st.expander(f"All changed metrics ({total})", expanded=False):
        view = st.selectbox(
            "Show",
            _LEDGER_VIEWS,
            key="macro-change-ledger-view",
            label_visibility="collapsed",
        )
        ledger = _ledger_frame(change_set, view)
        if ledger.empty:
            st.caption("No metrics match this view.")
        else:
            st.dataframe(ledger, width="stretch", hide_index=True, height=460)


def render_macro_change_overview(change_set: ChangeSet | None, *, limit: int = 6) -> None:
    """Render the deterministic cross-domain publication diff on the Macro tab."""
    if not comparison_ready(change_set):
        st.caption("A prior canonical publication is not available for comparison yet.")
        return
    changed = _changed_frame(change_set)
    comparable = _rank_changes(_comparable_frame(changed))
    coverage = _coverage_frame(changed)
    counts = _presentation_counts(change_set)
    if changed.empty:
        st.markdown(
            '<div class="rm-change-empty">No analytical metrics changed in the selected comparison.</div>',
            unsafe_allow_html=True,
        )
        return

    stats = (
        ("Comparable changes", counts["comparable"]),
        ("Material moves", counts["material"]),
        ("Coverage changes", counts["coverage"]),
        ("Threshold crossings", counts["crossings"]),
    )
    stat_html = "".join(
        '<div class="rm-change-stat">'
        f'<div class="rm-change-stat-value">{value}</div>'
        f'<div class="rm-change-stat-label">{html.escape(label)}</div>'
        '</div>'
        for label, value in stats
    )
    cards = "".join(_change_card_html(row) for _, row in comparable.head(max(1, int(limit))).iterrows())
    if not cards:
        cards = '<div class="rm-change-empty">No comparable analytical metrics moved in the selected comparison.</div>'
    st.markdown(
        f'<div class="rm-change-stats">{stat_html}</div>'
        f'<div class="rm-change-grid">{cards}</div>',
        unsafe_allow_html=True,
    )
    if len(coverage):
        new_count = int(coverage["classification"].astype(str).eq("metric_new").sum())
        unavailable_count = int(coverage["classification"].astype(str).eq("metric_unavailable").sum())
        restored_count = int(coverage["classification"].astype(str).eq("metric_restored").sum())
        parts = []
        if new_count:
            parts.append(f"{new_count} newly available")
        if unavailable_count:
            parts.append(f"{unavailable_count} unavailable")
        if restored_count:
            parts.append(f"{restored_count} restored")
        if parts:
            st.caption("Coverage changes: " + " · ".join(parts) + ".")
    render_all_changed_metrics(change_set)


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
    domain_filter: str | None = None,
) -> None:
    """Inspect one deterministic metric change with provenance and Read linkage."""
    if not comparison_ready(change_set) or comparison_state is None:
        st.caption("A prior canonical publication is not available for change evidence yet.")
        return
    frame = _rank_changes(_changed_frame(change_set))
    if domain_filter:
        frame = frame.loc[frame["domain"].astype(str).eq(str(domain_filter))].reset_index(drop=True)
    if frame.empty:
        st.caption("No analytical metrics changed in the selected comparison.")
        return

    with st.container(key="change-evidence-inspector"):
        domains = list(dict.fromkeys(frame["domain"].dropna().astype(str)))
        if domain_filter:
            domain = str(domain_filter)
            control_metric = st.container()
        else:
            control_domain, control_metric = st.columns([0.85, 2.15], vertical_alignment="bottom")
            with control_domain:
                if st.session_state.get("change-evidence-domain") not in domains:
                    st.session_state["change-evidence-domain"] = domains[0]
                domain = st.selectbox(
                    "Domain",
                    domains,
                    format_func=lambda value: DOMAIN_LABELS.get(value, value.replace("_", " ").title()),
                    key="change-evidence-domain",
                )
        domain_frame = frame.loc[frame["domain"].astype(str).eq(domain)].reset_index(drop=True)
        metric_ids = domain_frame["metric_id"].astype(str).tolist()
        row_index = {str(row.get("metric_id")): row for _, row in domain_frame.iterrows()}
        if st.session_state.get("change-evidence-metric") not in metric_ids:
            st.session_state["change-evidence-metric"] = metric_ids[0]
        with control_metric:
            metric_id = st.selectbox(
                "Metric",
                metric_ids,
                format_func=lambda value: _metric_option_label(row_index[value]),
                key="change-evidence-metric",
            )
        row = row_index[metric_id]

        label = str(row.get("label") or metric_id)
        base = str(row.get("base_display") or "n/a")
        head = str(row.get("head_display") or "n/a")
        classification_key = str(row.get("classification") or "")
        classification = _CLASS_LABELS.get(classification_key, "Changed")
        domain_label = DOMAIN_LABELS.get(domain, domain.replace("_", " ").title())
        delta = _delta_text(row)
        material_value = row.get("material")
        material = bool(material_value) if pd.notna(material_value) else False
        context = _fact_context(evidence_packets, domain, metric_id)
        context_html = (
            f'<div class="rm-change-evidence-context">{html.escape(context)}</div>'
            if context
            else ""
        )
        material_label = "Material" if material else "Recorded change"
        st.markdown(
            '<div class="rm-change-inspector-hero">'
            '<div class="rm-change-inspector-heading">'
            '<div>'
            f'<div class="rm-change-card-kicker">{html.escape(domain_label)} · {html.escape(classification)}</div>'
            f'<div class="rm-change-evidence-title">{html.escape(label)}</div>'
            '</div>'
            f'<div class="rm-change-inspector-badge">{html.escape(material_label)}</div>'
            '</div>'
            '<div class="rm-change-inspector-values">'
            f'<div><small>Baseline</small><b>{html.escape(base)}</b></div>'
            '<div class="rm-change-evidence-arrow">→</div>'
            f'<div><small>Current</small><b>{html.escape(head)}</b></div>'
            f'<div class="rm-change-inspector-delta"><small>Change</small><b>{html.escape(delta)}</b></div>'
            '</div>'
            f'{context_html}'
            '</div>',
            unsafe_allow_html=True,
        )

        baseline = comparison_state.baseline
        head_ref = comparison_state.head
        meta_items = (
            ("Baseline publication", _date_label(baseline.observation_date if baseline else "") or "n/a"),
            ("Current publication", _date_label(head_ref.observation_date if head_ref else "") or "n/a"),
            ("Data quality", str(row.get("head_quality") or "n/a").replace("_", " ")),
        )
        meta_html = "".join(
            '<div class="rm-change-meta-card">'
            f'<div class="rm-change-meta-label">{html.escape(name)}</div>'
            f'<div class="rm-change-meta-value">{html.escape(value)}</div>'
            '</div>'
            for name, value in meta_items
        )
        st.markdown(f'<div class="rm-change-meta-grid">{meta_html}</div>', unsafe_allow_html=True)

        sources = _metric_sources(metric_id)
        modes = _snapshot_source_modes(head_ref.snapshot_id if head_ref else "", domain)
        source_links: list[str] = []
        if sources is not None and not sources.empty:
            for _, source in sources.iterrows():
                name = str(source.get("source_label") or "Source")
                url = str(source.get("source_url") or "").strip()
                if url.startswith("https://"):
                    source_links.append(
                        f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(name)}</a>'
                    )
                else:
                    source_links.append(html.escape(name))
        source_body = " · ".join(source_links) if source_links else "No registered source links are available for this metric."
        source_state = (
            f'<div class="rm-change-panel-meta">Current source state: {html.escape(" · ".join(modes))}</div>'
            if modes
            else ""
        )

        reads = dict(platform_reads or {})
        claim_groups: list[tuple[str, str]] = []
        for key, display in ((domain, domain_label), ("macro", "AI Macro")):
            for claim in _read_claims_for_fact(dict(reads.get(key) or {}), metric_id):
                claim_groups.append((display, claim))
        if claim_groups:
            read_body = "".join(
                '<div class="rm-change-read-link">'
                f'<div class="rm-change-read-label">{html.escape(display)}</div>'
                f'<div class="rm-change-read-copy">{html.escape(claim)}</div>'
                '</div>'
                for display, claim in claim_groups[:4]
            )
        else:
            read_body = '<div class="rm-change-panel-empty">This metric is not cited in the current published Read.</div>'

        source_col, read_col = st.columns([0.9, 1.6], vertical_alignment="top")
        with source_col:
            st.markdown(
                '<div class="rm-change-inspector-panel">'
                '<div class="rm-change-inspector-panel-title">Source register</div>'
                f'<div class="rm-change-source-links">{source_body}</div>'
                f'{source_state}'
                '</div>',
                unsafe_allow_html=True,
            )
        with read_col:
            st.markdown(
                '<div class="rm-change-inspector-panel">'
                '<div class="rm-change-inspector-panel-title">Published Read linkage</div>'
                f'{read_body}'
                '</div>',
                unsafe_allow_html=True,
            )


__all__ = [
    "comparison_ready",
    "comparison_request_for_option",
    "comparison_subtitle",
    "render_all_changed_metrics",
    "render_change_evidence",
    "render_domain_change_line",
    "render_macro_comparison_toolbar",
    "resolve_comparison_selection",
    "render_macro_change_overview",
]
