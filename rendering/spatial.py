from __future__ import annotations

import pandas as pd
import streamlit as st

from rendering.charts_data_center import ACTIVE_CAMPUS_STATUSES, CAMPUS_SIZE_METRICS, data_center_map
from rendering.components import fmt_number, render_panel_heading, render_statline
from rendering.dataframe import arrow_safe_dataframe
from rendering.visual_system import render_plotly_chart, selection_points


LAYER_FILTERS = {
    "All campuses": "all",
    "Operational": "operational",
    "Development": "development",
    "Published capacity": "capacity",
    "Power evidence": "power",
    "Water evidence": "water",
}


def _registry(infrastructure_data: dict | None) -> pd.DataFrame:
    frame = (infrastructure_data or {}).get("data_center_registry")
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("Spatial explorer requires the Universal Data Center Registry")
    if "Campus ID" not in frame.columns:
        raise ValueError("Universal Data Center Registry is missing Campus ID")
    if frame["Campus ID"].astype(str).duplicated().any():
        raise ValueError("Universal Data Center Registry contains duplicate Campus IDs")
    return frame.copy()


def _layer_mask(frame: pd.DataFrame, layer: str) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=bool)
    status = frame.get("Status", pd.Series("", index=frame.index)).fillna("").astype(str)
    if layer == "operational":
        return status.eq("Operational")
    if layer == "development":
        return status.isin(ACTIVE_CAMPUS_STATUSES - {"Operational"})
    if layer == "capacity":
        fields = (
            "Published Capacity Estimate MW",
            "Planned Data Center Capacity MW",
            "Contracted Utility Capacity MW",
            "Energized Capacity MW",
        )
    elif layer == "power":
        fields = (
            "Contracted Utility Capacity MW",
            "Energized Capacity MW",
            "Annual Electricity Consumption MWh",
            "Planned Onsite Generation MW",
        )
    elif layer == "water":
        numeric_fields = ("Water Withdrawal Gallons/Year", "Water Consumption Gallons/Year", "Site WUE L/kWh")
        text_fields = ("Water Permit or Utility Record", "Water Source", "Cooling System")
        mask = pd.Series(False, index=frame.index)
        for field in numeric_fields:
            if field in frame.columns:
                mask |= pd.to_numeric(frame[field], errors="coerce").notna()
        for field in text_fields:
            if field in frame.columns:
                mask |= frame[field].fillna("").astype(str).str.strip().ne("")
        return mask
    else:
        return pd.Series(True, index=frame.index)

    mask = pd.Series(False, index=frame.index)
    for field in fields:
        if field in frame.columns:
            mask |= pd.to_numeric(frame[field], errors="coerce").gt(0)
    return mask


def _size_options(frame: pd.DataFrame) -> list[str]:
    options = ["Campus count"]
    for label, field in CAMPUS_SIZE_METRICS.items():
        if field is None or field not in frame.columns:
            continue
        if pd.to_numeric(frame[field], errors="coerce").gt(0).any():
            options.append(label)
    return list(dict.fromkeys(options))


def _state_options(frame: pd.DataFrame) -> list[str]:
    if frame.empty or "State" not in frame.columns:
        return ["United States"]
    states = sorted({str(value).strip().upper() for value in frame["State"].dropna() if len(str(value).strip()) == 2})
    return ["United States", *states]


def _selected_campus_id(points: list[dict]) -> str:
    if not points:
        return ""
    point = points[0]
    custom = point.get("customdata")
    if isinstance(custom, (list, tuple)) and custom:
        return str(custom[0] or "").strip()
    return ""


def _selected_row(registry: pd.DataFrame, campus_id: str) -> pd.Series | None:
    if not campus_id or registry.empty:
        return None
    matched = registry.loc[registry["Campus ID"].astype(str).eq(str(campus_id))]
    return matched.iloc[0] if len(matched) == 1 else None


def _render_selection(row: pd.Series) -> None:
    label = str(row.get("Campus Label") or row.get("Campus Name") or "Selected campus").strip()
    operator = str(row.get("Operator") or "Unreported operator").strip()
    county = str(row.get("County") or "").strip()
    state = str(row.get("State") or "").strip()
    status = str(row.get("Status") or "Status unknown").strip()
    capacity = pd.to_numeric(row.get("Planned Data Center Capacity MW"), errors="coerce")
    if pd.isna(capacity) or capacity <= 0:
        capacity = pd.to_numeric(row.get("Published Capacity Estimate MW"), errors="coerce")
    buildings = pd.to_numeric(row.get("Building Count"), errors="coerce")
    confidence = str(row.get("Identity Confidence") or "n/a").strip()
    render_panel_heading(label, " · ".join(part for part in (operator, f"{county}, {state}".strip(", ")) if part))
    render_statline(
        [
            ("Status", status, "campus record"),
            ("Published / planned capacity", fmt_number(capacity, 0, suffix=" MW") if pd.notna(capacity) else "n/a", "campus grain"),
            ("Buildings", f"{int(buildings):,}" if pd.notna(buildings) else "n/a", "facility/building records"),
            ("Identity confidence", confidence.title(), str(row.get("Identity Basis") or "registry resolution")),
        ],
        key_prefix=f"spatial-selected-{str(row.get('Campus ID') or '')[-10:]}",
    )


def render_spatial_explorer(
    infrastructure_data: dict | None,
    *,
    key_prefix: str = "national-ai-landscape",
    title: str = "Project locations",
    subtitle: str = "Data-center campuses with published infrastructure evidence.",
    default_layer: str = "All campuses",
    show_table: bool = True,
    show_heading: bool = True,
    height: int = 575,
) -> None:
    registry = _registry(infrastructure_data)
    if show_heading:
        render_panel_heading(title, subtitle)
    if registry.empty:
        st.info("No campus records are available.")
        return

    state_key = f"{key_prefix}-state"
    pending_state_key = f"{key_prefix}-pending-state"
    selected_key = f"{key_prefix}-selected-campus-id"
    pending_state = str(st.session_state.pop(pending_state_key, "") or "").strip().upper()
    if pending_state:
        st.session_state[state_key] = pending_state

    layer_names = list(LAYER_FILTERS)
    default_index = layer_names.index(default_layer) if default_layer in layer_names else 0
    controls = st.columns([1.15, 0.9, 1.15], gap="medium")
    with controls[0]:
        layer_name = st.selectbox("Map layer", layer_names, index=default_index, key=f"{key_prefix}-layer")
    layer_frame = registry.loc[_layer_mask(registry, LAYER_FILTERS[layer_name])].copy()
    with controls[1]:
        geography = st.selectbox("Geography", _state_options(layer_frame), key=state_key)
    with controls[2]:
        size_by = st.selectbox("Marker size", _size_options(layer_frame), key=f"{key_prefix}-size")

    state = "" if geography == "United States" else geography
    plotted = layer_frame
    if state:
        state_series = layer_frame.get("State", pd.Series("", index=layer_frame.index)).fillna("").astype(str).str.upper().str.strip()
        plotted = layer_frame.loc[state_series.eq(state)].copy()

    selected_id = str(st.session_state.get(selected_key) or "").strip()
    if selected_id and selected_id not in set(registry["Campus ID"].astype(str)):
        st.session_state.pop(selected_key, None)
        selected_id = ""

    figure = data_center_map(
        plotted,
        state=state or None,
        size_by=size_by,
        selected_campus_id=selected_id,
        height=height,
    )
    event = render_plotly_chart(
        figure,
        width="stretch",
        key=f"{key_prefix}-map",
        role="map",
        on_select="rerun",
        selection_mode="points",
    )
    clicked_id = _selected_campus_id(selection_points(event))
    if clicked_id and clicked_id != selected_id:
        row = _selected_row(registry, clicked_id)
        if row is not None:
            st.session_state[selected_key] = clicked_id
            clicked_state = str(row.get("State") or "").strip().upper()
            if geography == "United States" and clicked_state:
                st.session_state[pending_state_key] = clicked_state
            st.rerun()

    row = _selected_row(registry, str(st.session_state.get(selected_key) or ""))
    if row is not None:
        _render_selection(row)

    if not show_table:
        return
    columns = [
        "Campus Label", "Campus ID", "Operator", "State", "County", "Status",
        "Identity Confidence", "Facility Count", "Building Count",
        "Published Capacity Estimate MW", "Planned Data Center Capacity MW",
        "Contracted Utility Capacity MW", "Energized Capacity MW",
    ]
    table = plotted[[column for column in columns if column in plotted.columns]].copy()
    if "Published Capacity Estimate MW" in table.columns:
        table = table.sort_values("Published Capacity Estimate MW", ascending=False, na_position="last", kind="stable")
    with st.expander(f"Mapped campuses · {len(table):,}", expanded=False):
        st.dataframe(arrow_safe_dataframe(table), width="stretch", hide_index=True)


__all__ = ["LAYER_FILTERS", "render_spatial_explorer"]
