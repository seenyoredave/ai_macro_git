"""Safe, deterministic HTML markup for the platform read component."""

from __future__ import annotations

import html
from typing import Any


def _reference_links(references: list[dict[str, Any]], *, limit: int = 6) -> str:
    links: list[str] = []
    for index, reference in enumerate(references, start=1):
        if not isinstance(reference, dict):
            continue
        try:
            number = int(reference.get("reference_number") or index)
        except (TypeError, ValueError):
            number = index
        source = str(
            reference.get("source_label")
            or reference.get("source_name")
            or "Source"
        ).strip()
        if not source:
            continue
        label = f"[{number}] {html.escape(source)}"
        url = str(reference.get("source_url") or "").strip()
        if url.startswith("https://"):
            links.append(
                '<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>'.format(
                    url=html.escape(url, quote=True),
                    label=label,
                )
            )
        else:
            links.append(f'<span class="rm-domain-read-reference-text">{label}</span>')
    return " · ".join(links[: max(int(limit), 1)])


def _context_items_html(payload: dict) -> str:
    items = [item for item in payload.get("current_context_items", []) or [] if isinstance(item, dict)][:2]
    if not items:
        recent_context = str(payload.get("recent_context") or "").strip()
        if not recent_context:
            return ""
        items = [{"text": recent_context, "reference_number": None, "source_url": ""}]

    rendered: list[str] = []
    for item in items:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        reference_number = item.get("reference_number")
        source_url = str(item.get("source_url") or "").strip()
        citation = ""
        if reference_number:
            label = f"[{html.escape(str(reference_number))}]"
            if source_url.startswith("https://"):
                citation = (
                    ' <a class="rm-domain-read-context-citation" href="{url}" '
                    'target="_blank" rel="noopener noreferrer">{label}</a>'
                ).format(url=html.escape(source_url, quote=True), label=label)
            else:
                citation = f' <span class="rm-domain-read-context-citation">{label}</span>'
        rendered.append(
            f'<span class="rm-domain-read-context-item">{html.escape(text)}{citation}</span>'
        )
    if not rendered:
        return ""
    joined = '<span class="rm-domain-read-context-separator">•</span>'.join(rendered)
    return (
        '<div class="rm-domain-read-context-row rm-domain-read-recent">'
        '<span>Current context</span>'
        f'<div class="rm-domain-read-context-items">{joined}</div>'
        '</div>'
    )


def build_domain_read_html(
    read: dict | None,
    *,
    label: str | None,
    accent_color: str,
    macro: bool = False,
) -> str:
    """Return compact one-line markup so Streamlit never exposes nested tags."""
    payload = read or {}
    headline = str(payload.get("headline") or "Read unavailable").strip()
    summary = str(payload.get("summary") or payload.get("body") or "").strip()
    confidence = str(payload.get("confidence") or "limited").strip()
    domain_label = str(label or payload.get("label") or "Domain read").strip()
    references = payload.get("references") or payload.get("weekly_references") or []

    context_html = _context_items_html(payload)
    reference_links = _reference_links(list(references))
    refs_html = (
        '<div class="rm-domain-read-refs">'
        '<span>References</span>'
        f'{reference_links}'
        '</div>'
        if reference_links else ""
    )

    classes = "rm-domain-read macro" if macro else "rm-domain-read"
    summary_html = (
        f'<div class="rm-domain-read-copy">{html.escape(summary)}</div>'
        if summary else ""
    )
    return "".join([
        f'<div class="{classes}" style="--rm-read-accent:{html.escape(accent_color, quote=True)};">',
        f'<div class="rm-domain-read-kicker">{html.escape(domain_label)} · {html.escape(confidence)} confidence</div>',
        f'<div class="rm-domain-read-title">{html.escape(headline)}</div>',
        summary_html,
        context_html,
        refs_html,
        "</div>",
    ])
