from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from rendering.charts_data_center import FACILITY_SIZE_METRICS, data_center_map, data_center_state_detail_map, facility_map_legend_items
from rendering.components import render_panel_heading
from rendering.dataframe import arrow_safe_dataframe


LAYER_FILTERS = {
    "Known footprint": "footprint",
    "Operating projects": "operating",
    "Active pipeline": "pipeline",
    "Planned / announced": "planned",
    "Capacity evidence": "capacity",
    "Power evidence": "power",
    "Direct water evidence": "water_direct",
}


def _registry(infrastructure_data: dict | None) -> pd.DataFrame:
    frame = (infrastructure_data or {}).get("facility_registry")
    if not isinstance(frame, pd.DataFrame):
        return pd.DataFrame()
    return frame.copy()


def _layer_mask(frame: pd.DataFrame, layer: str) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=bool)
    record_type = frame.get("Record Type", pd.Series("", index=frame.index)).fillna("").astype(str).str.casefold()
    status = frame.get("Status", pd.Series("", index=frame.index)).fillna("").astype(str).str.casefold()
    if layer == "footprint":
        return pd.Series(True, index=frame.index)
    if layer == "operating":
        return record_type.eq("project") & status.isin({"operational", "operating", "online"})
    if layer == "pipeline":
        return record_type.eq("project") & status.isin({"approved / permitted / under construction", "under construction", "construction", "announced", "planned", "proposed", "expanding"})
    if layer == "planned":
        return record_type.eq("project") & status.isin({"announced", "planned", "proposed"})
    if layer == "capacity":
        fields = [
            "Published Capacity Estimate MW", "Planned Data Center Capacity MW",
            "Contracted Utility Capacity MW", "Energized Capacity MW",
        ]
        mask = pd.Series(False, index=frame.index)
        for field in fields:
            if field in frame.columns:
                mask |= pd.to_numeric(frame[field], errors="coerce").gt(0)
        return mask
    if layer == "power":
        fields = [
            "Contracted Utility Capacity MW", "Energized Capacity MW",
            "Annual Electricity Consumption MWh", "Planned Onsite Generation MW",
        ]
        mask = pd.Series(False, index=frame.index)
        for field in fields:
            if field in frame.columns:
                mask |= pd.to_numeric(frame[field], errors="coerce").gt(0)
        return mask
    if layer == "water_direct":
        return frame.get("Direct Water Evidence", pd.Series(False, index=frame.index)).fillna(False).astype(bool)
    return pd.Series(True, index=frame.index)


def _size_options(frame: pd.DataFrame) -> list[str]:
    options = ["Facility count"]
    for label, field in FACILITY_SIZE_METRICS.items():
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



def _render_map_key(frame: pd.DataFrame, *, size_by: str) -> None:
    status_items = facility_map_legend_items(frame)
    if not status_items:
        return
    status_html = "".join(
        f'<span class="rm-map-key-item"><span class="rm-map-key-dot" style="background:{html.escape(color, quote=True)}"></span>{html.escape(label)}</span>'
        for label, color in status_items
    )
    metric_html = ""
    if size_by != "Facility count":
        metric_html = (
            '<span class="rm-map-key-divider"></span>'
            '<span class="rm-map-key-item"><span class="rm-map-key-dot rm-map-key-dot-filled"></span>Value reported</span>'
            '<span class="rm-map-key-item"><span class="rm-map-key-dot rm-map-key-dot-outline"></span>Value unavailable</span>'
        )
    st.markdown(
        '<div class="rm-map-key">'
        '<span class="rm-map-key-label">Facility status</span>'
        f'{status_html}{metric_html}'
        '</div>',
        unsafe_allow_html=True,
    )

def render_spatial_explorer(
    infrastructure_data: dict | None,
    *,
    key_prefix: str = "national-ai-landscape",
    title: str = "National AI development landscape",
    subtitle: str = "Facility geography with linked power, water, and infrastructure evidence.",
    default_layer: str = "Known footprint",
    show_table: bool = True,
) -> None:
    registry = _registry(infrastructure_data)
    render_panel_heading(title, subtitle)
    if registry.empty:
        st.info("No mapped facility records are available.")
        return

    layer_names = list(LAYER_FILTERS)
    default_index = layer_names.index(default_layer) if default_layer in layer_names else 0
    controls = st.columns([1.25, 1, 1.25])
    with controls[0]:
        layer_name = st.selectbox("Map layer", layer_names, index=default_index, key=f"{key_prefix}-layer")
    layer_frame = registry.loc[_layer_mask(registry, LAYER_FILTERS[layer_name])].copy()
    with controls[1]:
        state_name = st.selectbox("Geography", _state_options(layer_frame), key=f"{key_prefix}-state")
    size_options = _size_options(layer_frame)
    with controls[2]:
        size_by = st.selectbox("Marker size", size_options, key=f"{key_prefix}-size")

    if state_name != "United States":
        plotted = layer_frame.loc[layer_frame.get("State", pd.Series(index=layer_frame.index, dtype=object)).fillna("").astype(str).str.upper().eq(state_name)]
    else:
        plotted = layer_frame

    _render_map_key(plotted, size_by=size_by)
    with st.container(border=True):
        if state_name == "United States":
            figure = data_center_map(plotted, size_by=size_by, height=550)
        else:
            figure = data_center_state_detail_map(pd.DataFrame(), plotted, state_code=state_name, size_by=size_by, height=550)
        st.plotly_chart(
            figure,
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key=f"{key_prefix}-map",
        )

    if not show_table:
        return
    columns = [
        "Facility", "Operator", "State", "County", "Status", "Record Type",
        "Published Capacity Estimate MW", "Planned Data Center Capacity MW",
        "Contracted Utility Capacity MW", "Energized Capacity MW",
        "Evidence Grade", "Evidence Type", "Source URL",
    ]
    available = [column for column in columns if column in plotted.columns]
    table = plotted[available].copy() if available else pd.DataFrame()
    if "Published Capacity Estimate MW" in table.columns:
        table = table.sort_values("Published Capacity Estimate MW", ascending=False, na_position="last", kind="stable")
    with st.expander(f"Mapped records · {len(table):,}", expanded=False):
        st.dataframe(arrow_safe_dataframe(table), width="stretch", hide_index=True)
