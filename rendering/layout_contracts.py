"""Pure HTML helpers for the two supported analytical layout contracts.

This module deliberately has no Streamlit dependency so the card markup can be
validated in a real browser without importing the application runtime.
"""

from __future__ import annotations

import html
from collections.abc import Sequence


def normalize_summary_item(item: Sequence[object]) -> tuple[object, object, object | None, object | None]:
    """Return ``label, value, note, help_text`` from a 3- or 4-field item."""
    if len(item) == 3:
        label, value, note = item
        help_text = None
    elif len(item) == 4:
        label, value, note, help_text = item
    else:
        raise ValueError("summary items must contain 3 or 4 values")
    return label, value, note, help_text


def summary_card_html(
    *,
    label: object,
    value: object,
    note: object | None,
    namespace: str,
    index: int,
    mode: str,
    help_text: object | None = None,
) -> str:
    """Build an accessible, content-driven summary card.

    ``mode`` is restricted to ``row`` and ``rail`` so a third visual layout
    cannot quietly enter the shared component layer.
    """
    if mode not in {"row", "rail"}:
        raise ValueError("summary card mode must be 'row' or 'rail'")
    classes = f"rm-summary-card rm-summary-card--{mode}"
    title_attr = (
        f' title="{html.escape(str(help_text), quote=True)}"'
        if help_text not in (None, "")
        else ""
    )
    note_html = (
        f'<div class="rm-summary-note">{html.escape(str(note))}</div>'
        if note not in (None, "")
        else ""
    )
    return (
        f'<article class="{classes}" '
        f'data-rm-card="{html.escape(namespace, quote=True)}-{int(index)}">'
        f'<div class="rm-summary-label"{title_attr}>{html.escape(str(label).upper())}</div>'
        f'<div class="rm-summary-value">{html.escape(str(value))}</div>'
        f'{note_html}'
        '</article>'
    )


def summary_row_html(cards: Sequence[str], *, namespace: str) -> str:
    """Wrap summary readings in one responsive segmented stat rail."""
    if not cards:
        return ""
    clean_namespace = html.escape(str(namespace), quote=True)
    return (
        f'<div class="rm-summary-row rm-summary-row--{len(cards)}" '
        f'data-rm-summary-row="{clean_namespace}">'
        + "".join(cards)
        + '</div>'
    )


def summary_stack_html(cards: Sequence[str], *, namespace: str) -> str:
    """Wrap chart-side readings in one equal-height segmented sidecar."""
    if not cards:
        return ""
    clean_namespace = html.escape(str(namespace), quote=True)
    return (
        f'<div class="rm-summary-stack" data-rm-summary-stack="{clean_namespace}" '
        f'style="--rm-card-count:{len(cards)}">'
        + "".join(cards)
        + '</div>'
    )


def signal_rail_html(
    rows: Sequence[Sequence[object]],
    *,
    namespace: str,
) -> str:
    """Build a flat categorical signal rail for cross-sectional findings."""
    if not rows:
        return ""
    clean_namespace = html.escape(str(namespace), quote=True)
    items: list[str] = []
    for index, row in enumerate(rows):
        label, value, note, help_text = normalize_summary_item(row)
        title_attr = (
            f' title="{html.escape(str(help_text), quote=True)}"'
            if help_text not in (None, "")
            else ""
        )
        note_html = (
            f'<div class="rm-signal-note">{html.escape(str(note))}</div>'
            if note not in (None, "")
            else ""
        )
        items.append(
            f'<article class="rm-signal-item" data-rm-signal="{clean_namespace}-{index}">'
            f'<div class="rm-signal-label"{title_attr}>{html.escape(str(label).upper())}</div>'
            f'<div class="rm-signal-value">{html.escape(str(value))}</div>'
            f'{note_html}'
            '</article>'
        )
    return (
        f'<div class="rm-signal-rail rm-signal-rail--{len(items)}" '
        f'data-rm-signal-rail="{clean_namespace}">'
        + "".join(items)
        + '</div>'
    )



def transmission_board_html(
    *,
    headline: object,
    breakpoints: Sequence[object],
    measurement_gaps: Sequence[object],
    stages: Sequence[Sequence[object]],
    namespace: str,
) -> str:
    """Build the flagship six-stage AI economic transmission board."""
    if len(stages) != 6:
        raise ValueError("transmission board requires exactly six stages")
    clean_namespace = html.escape(str(namespace), quote=True)

    breakpoint_text = " · ".join(str(item) for item in breakpoints if item not in (None, "")) or "No measured breakpoint"
    gap_text = " · ".join(str(item) for item in measurement_gaps if item not in (None, "")) or "None"

    items: list[str] = []
    for index, stage in enumerate(stages, start=1):
        if len(stage) != 3:
            raise ValueError("transmission stages must contain label, value, and note")
        label, value, note = stage
        items.append(
            '<li class="rm-transmission-stage">'
            f'<div class="rm-transmission-index">{index:02d}</div>'
            '<div class="rm-transmission-stage-copy">'
            f'<div class="rm-transmission-label">{html.escape(str(label).upper())}</div>'
            f'<div class="rm-transmission-value">{html.escape(str(value))}</div>'
            f'<div class="rm-transmission-note">{html.escape(str(note))}</div>'
            '</div>'
            '</li>'
        )

    return (
        f'<section class="rm-transmission-board" data-rm-transmission="{clean_namespace}">'
        '<header class="rm-transmission-header">'
        '<div class="rm-transmission-kicker">AI ECONOMIC TRANSMISSION</div>'
        f'<div class="rm-transmission-headline">{html.escape(str(headline))}</div>'
        '<div class="rm-transmission-meta">'
        f'<span><b>Measured breakpoints</b> {html.escape(breakpoint_text)}</span>'
        f'<span><b>Measurement gap</b> {html.escape(gap_text)}</span>'
        '</div>'
        '</header>'
        '<ol class="rm-transmission-track">'
        + ''.join(items)
        + '</ol>'
        '</section>'
    )


def deliverability_screen_html(
    stages: Sequence[Sequence[object]],
    *,
    namespace: str,
) -> str:
    """Build a connected five-stage delivery pathway proof primitive.

    Each stage is ``label, value, note``.  The object is intentionally shallow:
    it establishes the causal sequence before the reader enters the charts.
    """
    if not stages:
        return ""
    clean_namespace = html.escape(str(namespace), quote=True)
    items: list[str] = []
    for index, stage in enumerate(stages, start=1):
        if len(stage) != 3:
            raise ValueError("deliverability stages must contain label, value, and note")
        label, value, note = stage
        items.append(
            '<li class="rm-deliverability-stage">'
            f'<div class="rm-deliverability-index">{index:02d}</div>'
            '<div class="rm-deliverability-copy">'
            f'<div class="rm-deliverability-label">{html.escape(str(label).upper())}</div>'
            f'<div class="rm-deliverability-value">{html.escape(str(value))}</div>'
            f'<div class="rm-deliverability-note">{html.escape(str(note))}</div>'
            '</div>'
            '</li>'
        )
    return (
        f'<ol class="rm-deliverability-screen" data-rm-deliverability="{clean_namespace}">'
        + ''.join(items)
        + '</ol>'
    )

def delivery_pathway_stage_html(
    stage: Sequence[object],
    *,
    index: int,
    namespace: str,
) -> str:
    """Build one grid-delivery condition stage for placement in a native Streamlit column."""
    if len(stage) != 3:
        raise ValueError("delivery pathway stages must contain label, value, and note")
    if index < 1:
        raise ValueError("delivery pathway stage index must be positive")
    label, value, note = stage
    clean_namespace = html.escape(str(namespace), quote=True)
    return (
        f'<div class="rm-deliverability-stage-card" data-rm-delivery-stage="{clean_namespace}-{index}">'
        f'<div class="rm-deliverability-index">{index:02d}</div>'
        '<div class="rm-deliverability-copy">'
        f'<div class="rm-deliverability-label">{html.escape(str(label).upper())}</div>'
        f'<div class="rm-deliverability-value">{html.escape(str(value))}</div>'
        f'<div class="rm-deliverability-note">{html.escape(str(note))}</div>'
        '</div>'
        '</div>'
    )


def detail_dossier_html(
    *,
    title: object,
    subtitle: object | None,
    badge: object | None,
    headline_facts: Sequence[Sequence[object]],
    groups: Sequence[tuple[object, Sequence[Sequence[object]]]],
    namespace: str,
) -> str:
    """Build a cohesive dossier panel from identity, headline facts, and grouped fields.

    The dossier deliberately avoids a wall of equal-weight KPI cards.  Headline
    facts establish the record at a glance; grouped definition rows then present
    physical exposure and evidence in a calm, document-like hierarchy.
    """
    clean_namespace = html.escape(str(namespace), quote=True)
    subtitle_html = (
        f'<div class="rm-dossier-subtitle">{html.escape(str(subtitle))}</div>'
        if subtitle not in (None, "")
        else ""
    )
    badge_html = (
        f'<div class="rm-dossier-badge">{html.escape(str(badge))}</div>'
        if badge not in (None, "")
        else ""
    )

    fact_html: list[str] = []
    for item in headline_facts:
        if len(item) == 2:
            label, value = item
            note = None
        elif len(item) == 3:
            label, value, note = item
        else:
            raise ValueError("headline facts must contain 2 or 3 values")
        note_html = (
            f'<div class="rm-dossier-fact-note">{html.escape(str(note))}</div>'
            if note not in (None, "")
            else ""
        )
        fact_html.append(
            '<div class="rm-dossier-fact">'
            f'<div class="rm-dossier-fact-label">{html.escape(str(label).upper())}</div>'
            f'<div class="rm-dossier-fact-value">{html.escape(str(value))}</div>'
            f'{note_html}'
            '</div>'
        )

    group_html: list[str] = []
    for group_title, rows in groups:
        row_html: list[str] = []
        for row in rows:
            if len(row) == 2:
                label, value = row
                note = None
            elif len(row) == 3:
                label, value, note = row
            else:
                raise ValueError("dossier rows must contain 2 or 3 values")
            note_html = (
                f'<div class="rm-dossier-row-note">{html.escape(str(note))}</div>'
                if note not in (None, "")
                else ""
            )
            row_html.append(
                '<div class="rm-dossier-row">'
                f'<dt>{html.escape(str(label))}</dt>'
                '<dd>'
                f'<div class="rm-dossier-row-value">{html.escape(str(value))}</div>'
                f'{note_html}'
                '</dd>'
                '</div>'
            )
        group_html.append(
            '<section class="rm-dossier-group">'
            f'<h4>{html.escape(str(group_title))}</h4>'
            f'<dl>{"".join(row_html)}</dl>'
            '</section>'
        )

    return (
        f'<article class="rm-dossier" data-rm-dossier="{clean_namespace}">'
        '<header class="rm-dossier-header">'
        '<div class="rm-dossier-identity">'
        f'<div class="rm-dossier-title">{html.escape(str(title))}</div>'
        f'{subtitle_html}'
        '</div>'
        f'{badge_html}'
        '</header>'
        f'<div class="rm-dossier-facts">{"".join(fact_html)}</div>'
        f'<div class="rm-dossier-groups">{"".join(group_html)}</div>'
        '</article>'
    )


def value_realization_bridge_html(
    *,
    commercial_value: object,
    production_value: object,
    distribution_rows: Sequence[Sequence[object]],
    namespace: str,
) -> str:
    """Build the commercial-to-household outcomes bridge.

    The bridge uses three economic layers rather than presenting worker
    outcomes as a false five-step chronology. Compensation, labor share,
    median earnings, and participation are parallel distribution readings.
    """
    clean_namespace = html.escape(str(namespace), quote=True)
    distribution_html: list[str] = []
    for row in distribution_rows:
        if len(row) != 2:
            raise ValueError("distribution rows must contain label and value")
        label, value = row
        distribution_html.append(
            '<div class="rm-value-bridge-reading">'
            f'<div>{html.escape(str(label).upper())}</div>'
            f'<strong>{html.escape(str(value))}</strong>'
            '</div>'
        )

    return (
        f'<article class="rm-value-bridge" data-rm-value-bridge="{clean_namespace}">'
        '<header class="rm-value-bridge-header">'
        '<div>'
        '<div class="rm-value-bridge-title">From AI revenue to broader economic gains</div>'
        '<div class="rm-value-bridge-subtitle">Provider revenue, production response, and distribution to workers</div>'
        '</div>'
        '<div class="rm-value-bridge-period">2020 to latest observation</div>'
        '</header>'
        '<div class="rm-value-bridge-track">'
        '<section class="rm-value-bridge-layer rm-value-bridge-layer--commercial">'
        '<div class="rm-value-bridge-kicker">Provider revenue</div>'
        f'<div class="rm-value-bridge-primary">{html.escape(str(commercial_value))}</div>'
        '<div class="rm-value-bridge-note">Annualized provider revenue disclosures</div>'
        '</section>'
        '<section class="rm-value-bridge-layer rm-value-bridge-layer--production">'
        '<div class="rm-value-bridge-kicker">Productivity</div>'
        f'<div class="rm-value-bridge-primary">{html.escape(str(production_value))}</div>'
        '<div class="rm-value-bridge-note">Nonfarm-business productivity</div>'
        '</section>'
        '<section class="rm-value-bridge-layer rm-value-bridge-layer--distribution">'
        '<div class="rm-value-bridge-kicker">Worker outcomes</div>'
        f'<div class="rm-value-bridge-readings">{"".join(distribution_html)}</div>'
        '</section>'
        '</div>'
        '</article>'
    )
