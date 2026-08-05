from __future__ import annotations

import html
from collections.abc import Iterable

import numpy as np
import pandas as pd
import streamlit as st

from rendering.dataframe import arrow_safe_dataframe
from rendering.charts_common import compact_sparkline
from rendering.read_markup import build_domain_read_html

ACCENTS = {
    "violet": "#a78bfa",
    "blue": "#60a5fa",
    "slate": "#94a3b8",
    "amber": "#fbbf24",
    "red": "#fb7185",
    "green": "#34d399",
}

def fmt_number(value, digits=1, signed=False, suffix="") -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric) or not np.isfinite(numeric):
        return "n/a"
    spec = f"+.{digits}f" if signed else f".{digits}f"
    return f"{numeric:{spec}}{suffix}"

def fmt_date(value) -> str:
    ts = pd.to_datetime(value, errors="coerce", format="mixed")
    return "n/a" if pd.isna(ts) else ts.strftime("%Y-%m-%d")

def render_masthead(title: str, subtitle: str, meta: Iterable[tuple[str, str]] | None = None) -> None:
    meta_html = "".join(
        f"<div><b>{html.escape(str(label))}</b> {html.escape(str(value))}</div>"
        for label, value in (meta or [])
        if value not in (None, "")
    )
    st.markdown(
        f"""
        <div class="rm-masthead">
            <div>
                <div class="rm-kicker">Independent macroeconomic research</div>
                <h1 class="rm-title">{html.escape(title)}</h1>
                <div class="rm-subtitle">{html.escape(subtitle)}</div>
            </div>
            {f'<div class="rm-mast-meta">{meta_html}</div>' if meta_html else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )

def render_tab_header(title: str, subtitle: str, meta: str | None = None) -> None:
    meta_html = f'<div class="rm-tabmeta">{html.escape(meta)}</div>' if meta else ""
    st.markdown(
        f"""
        <div class="rm-tabhead">
            <div>
                <div class="rm-tabtitle">{html.escape(title)}</div>
                <div class="rm-tabcopy">{html.escape(subtitle)}</div>
            </div>
            {meta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

def render_line_break() -> None:
    st.markdown("<br>", unsafe_allow_html=True)

def render_section(
    title: str,
    subtitle: str | None = None,
    *,
    first: bool = False,
    compact: bool = False,
) -> None:
    body = f'<div class="rm-section-copy">{html.escape(subtitle)}</div>' if subtitle else ""
    classes = ["rm-section"]
    if first:
        classes.append("first")
    if compact:
        classes.append("compact")
    class_name = " ".join(classes)
    st.markdown(
        f"""
        <div class="{class_name}">
            <div class="rm-section-title">{html.escape(title)}</div>
            {body}
        </div>
        """,
        unsafe_allow_html=True,
    )

def _rail_position(value, scale):
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric) or not np.isfinite(numeric):
        return None
    lower, upper = scale
    if upper <= lower:
        return None
    return float(np.clip((numeric - lower) / (upper - lower) * 100.0, 0, 100))

def _latest_history_date(history):
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return None
    if "Date" not in history.columns:
        return None
    dates = pd.to_datetime(history["Date"], errors="coerce", format="mixed").dropna()
    return dates.max() if not dates.empty else None

def metric_card(
    *,
    key: str,
    label: str,
    value,
    value_text: str,
    context: str,
    history=None,
    scale=(0, 100),
    source: str,
    fallback_date=None,
    accent="violet",
    reference=None,
    years=5,
) -> None:
    accent_color = ACCENTS.get(accent, ACCENTS["violet"])
    position = _rail_position(value, scale)
    zero = scale[0] < 0 < scale[1]
    latest_date = _latest_history_date(history)
    date_text = fmt_date(fallback_date or latest_date)
    source_text = str(source or "").strip()
    invalid_source_labels = {
        "current", "current data", "live", "live data", "archive", "archived",
        "retained", "local history", "archive fallback", "live refresh",
    }
    if not source_text or source_text.lower() in invalid_source_labels:
        raise ValueError(f"metric_card requires an institutional or dataset source, received {source!r}")

    st.markdown(
        f"""
        <style>
        .st-key-{key} {{
            border: 1px solid rgba(148, 163, 184, 0.17) !important;
            border-top: 3px solid {accent_color} !important;
            border-radius: 14px !important;
            background: rgba(17, 24, 39, 0.82) !important;
            padding: 0.9rem 1rem 0.35rem 1rem !important;
            min-height: 245px;
        }}
        .st-key-{key} [data-testid="stPlotlyChart"] {{ margin-top: -0.3rem; }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container(key=key):
        marker = (
            f'<span class="rm-rail-marker" style="left:{position:.2f}%;background:{accent_color};"></span>'
            if position is not None else ""
        )
        zero_line = '<span class="rm-rail-zero"></span>' if zero else ""
        st.markdown(
            f"""
            <div class="rm-card-label">{html.escape(label)}</div>
            <div class="rm-card-value">{html.escape(value_text)}</div>
            <div class="rm-card-context">{html.escape(context)}</div>
            <div class="rm-rail">{zero_line}{marker}</div>
            <div class="rm-card-meta">
                <span>{html.escape(source_text)}</span>
                <span>{html.escape(date_text)}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.plotly_chart(
            compact_sparkline(
                history,
                color=accent_color,
                reference=reference,
                years=years,
                height=74,
            ),
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key=f"{key}-sparkline",
        )

def render_statline(
    stats: Iterable[tuple[str, str, str | None]],
    *,
    key_prefix: str,
) -> None:
    items = list(stats)
    if not items:
        return

    namespace = str(key_prefix).strip().lower().replace(" ", "-")
    if not namespace:
        raise ValueError("render_statline requires a non-empty key_prefix")

    columns = st.columns(len(items))
    for index, (column, item) in enumerate(zip(columns, items)):
        if len(item) == 3:
            label, value, note = item
            help_text = None
        elif len(item) == 4:
            label, value, note, help_text = item
        else:
            raise ValueError("render_statline items must contain 3 or 4 values")
        key = f"statline-{namespace}-{index}"
        with column:
            with st.container(key=key):
                st.markdown(f"**{str(label).upper()}**", help=help_text)
                st.markdown(f"### {str(value)}")
                if note:
                    st.caption(str(note))


def render_domain_read(read: dict | None, *, label: str | None = None, accent: str = "violet", macro: bool = False) -> None:
    accent_color = ACCENTS.get(accent, ACCENTS["violet"])
    st.markdown(
        build_domain_read_html(
            read,
            label=label,
            accent_color=accent_color,
            macro=macro,
        ),
        unsafe_allow_html=True,
    )

def inject_panel_height_rules(rules: dict[str, int]) -> None:
    """Apply restrained minimum heights to named side-by-side panels.

    Rules are keyed by Streamlit container key.  This avoids brittle global DOM
    stretching while keeping paired analytical windows aligned.
    """
    declarations = []
    for key, height in (rules or {}).items():
        clean_key = str(key).strip()
        if not clean_key:
            continue
        declarations.append(
            f'div[class*="st-key-{html.escape(clean_key)}"] {{ min-height: {max(int(height), 0)}px; }}'
        )
    if declarations:
        st.markdown(f"<style>{''.join(declarations)}</style>", unsafe_allow_html=True)


def render_panel_heading(title: str, meta: str | None = None) -> None:
    meta_html = f'<div class="rm-panel-meta">{html.escape(meta)}</div>' if meta else ""
    st.markdown(
        f"""
        <div class="rm-panel-head">
            <div class="rm-panel-title">{html.escape(title)}</div>
            {meta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

def render_static_table(frame: pd.DataFrame | None, *, empty_message: str = "No rows available.") -> None:
    safe = arrow_safe_dataframe(frame)
    if safe.empty:
        st.caption(empty_message)
        return

    header = "".join(
        f"<th>{html.escape(str(column))}</th>"
        for column in safe.columns
    )
    body_rows = []
    for _, row in safe.iterrows():
        cells = "".join(
            f"<td>{html.escape('' if pd.isna(value) else str(value))}</td>"
            for value in row.tolist()
        )
        body_rows.append(f"<tr>{cells}</tr>")

    table_html = (
        '<div class="rm-table-wrap"><table class="rm-table">'
        f'<thead><tr>{header}</tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody>'
        '</table></div>'
    )
    st.markdown(table_html, unsafe_allow_html=True)

def render_definition(text: str) -> None:
    with st.container(border=True):
        st.markdown(text)
