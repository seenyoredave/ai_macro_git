"""Typographic readings for Finance exhibits."""

from __future__ import annotations

import html
from collections.abc import Iterable

import streamlit as st

from rendering.layout_contracts import normalize_summary_item


def render_finance_section(title: str, subtitle: str, *, sources: str | None = None) -> None:
    # Other Finance sections retain their existing one-column header treatment.
    layout = " rm-finance-section--sourced" if sources else ""
    sources_html = (
        f'<div class="rm-finance-section-sources">{html.escape(sources)}</div>'
        if sources else ""
    )
    st.markdown(
        f'<div class="rm-finance-section{layout}">'
        '<div class="rm-finance-section-copy">'
        f'<h2>{html.escape(title)}</h2><p>{html.escape(subtitle)}</p>'
        '</div>'
        f'{sources_html}</div>',
        unsafe_allow_html=True,
    )


def render_finance_strain_heading(title: str, source_date: str) -> None:
    st.markdown(
        '<div class="rm-finance-strain-heading">'
        f'<div class="rm-finance-strain-title">{html.escape(title)}</div>'
        f'<div class="rm-finance-strain-source">{html.escape(source_date)}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def render_finance_facts(
    facts: Iterable[tuple], *, columns: int = 1, treatment: str = "detail",
) -> None:
    items = list(facts)
    if not items:
        return
    if treatment not in {"detail", "lead", "index", "comparison", "private", "funding", "strain"}:
        raise ValueError(f"Unknown Finance reading treatment: {treatment}")
    if columns not in {1, 2, 3, 4}:
        raise ValueError("Finance readings support one to four columns")
    rows = []
    for item in items:
        label, value, source_date, context = normalize_summary_item(item)
        meta_parts = [html.escape(str(part)) for part in (source_date, context) if part not in (None, "")]
        detail = f'<div class="rm-finance-fact-meta">{" · ".join(meta_parts)}</div>' if meta_parts else ""
        rows.append(
            '<div class="rm-finance-fact">'
            f'<dt>{html.escape(str(label))}</dt>'
            f'<dd>{html.escape(str(value))}</dd>'
            f'{detail}</div>'
        )
    st.markdown(
        f'<dl class="rm-finance-facts rm-finance-facts--{treatment} rm-finance-facts--{columns}">'
        f'{"".join(rows)}</dl>',
        unsafe_allow_html=True,
    )
