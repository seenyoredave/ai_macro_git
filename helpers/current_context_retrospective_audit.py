"""Replay the saved Current Context candidate audit under the current policy.

The replay is network-free.  It measures policy changes against the exact
candidate inventory already retained in the package; new targeted searches are
validated separately with fixtures/live developer refreshes.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from loaders.current_context_discovery import evaluate_item  # noqa: E402
from loaders.current_context_loader import DOMAIN_KEYS  # noqa: E402

SOURCE = PROJECT_ROOT / "audit" / "current_context_retrospective" / "candidate_audit_pre_source_grounding.csv"
OUT_DIR = PROJECT_ROOT / "audit" / "current_context_clump_c"
OUT_CSV = OUT_DIR / "retrospective_replay.csv"
OUT_MD = OUT_DIR / "RETROSPECTIVE_SUMMARY.md"


def _stamp(value) -> pd.Timestamp | None:
    if pd.isna(value) or not str(value).strip():
        return None
    try:
        return pd.Timestamp(value)
    except (TypeError, ValueError):
        return None


def main() -> None:
    frame = pd.read_csv(SOURCE)
    frame = frame.loc[frame["domain_query"].isin(DOMAIN_KEYS)].copy()
    rows: list[dict] = []
    for _, row in frame.iterrows():
        item = {
            "title": row.get("title", ""),
            "source_name": row.get("source_name", ""),
            "source_url": row.get("publisher_url", ""),
            "link": row.get("article_url", ""),
            "published": _stamp(row.get("published")),
            # Older audit rows did not retain the complete feed description.
            # The replay therefore intentionally understates candidates whose
            # relevance exists only in the description.
            "description": "",
            "provider": row.get("provider", "retained_audit"),
        }
        domain = str(row.get("domain_query") or "")
        _, audit = evaluate_item(
            item,
            domain=domain,
            current=pd.Timestamp(row.get("as_of")),
            provider="retrospective_replay",
        )
        rows.append({
            "domain": domain,
            "title": row.get("title", ""),
            "source_name": row.get("source_name", ""),
            "old_decision": row.get("decision", ""),
            "old_reason": row.get("reason", ""),
            "new_decision": audit.get("decision", ""),
            "new_reason": audit.get("reason", ""),
            "new_rank_score": audit.get("rank_score", 0),
            "new_materiality_score": audit.get("materiality_score", 0),
            "new_relevance_terms": audit.get("relevance_terms", ""),
            "new_topic_anchor_terms": audit.get("topic_anchor_terms", ""),
            "article_url": row.get("article_url", ""),
        })

    replay = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    replay.to_csv(OUT_CSV, index=False)

    lines = [
        "# Current Context Clump C — retained-candidate replay",
        "",
        "This replay uses the saved candidate set only. It evaluates the new all-domain seven-day, domain-anchor, domain-materiality policy without making network calls. It does not measure the additional inventory expected from the new targeted query sets.",
        "",
    ]
    for domain in DOMAIN_KEYS:
        part = replay.loc[replay["domain"] == domain]
        if part.empty:
            lines += [f"## {domain.replace('_', ' ').title()}", "", "No saved candidates were available for replay.", ""]
            continue
        old_accept = int(part["old_decision"].astype(str).str.startswith("accepted").sum())
        new_accept = int((part["new_decision"] == "metadata_qualified").sum())
        lines += [
            f"## {domain.replace('_', ' ').title()}",
            "",
            f"- Saved candidates: **{len(part)}**",
            f"- Previously accepted: **{old_accept}**",
            f"- Accepted under current policy: **{new_accept}**",
            "",
        ]
        accepted = part.loc[part["new_decision"] == "metadata_qualified"].sort_values("new_rank_score", ascending=False)
        for _, row in accepted.head(8).iterrows():
            lines.append(f"- **{row['source_name']}** — {row['title']}")
        if accepted.empty:
            lines.append("No saved candidate clears the current gates.")
        lines.append("")

    lines += [
        "## Interpretation",
        "",
        "The replay is not a quota. Zero remains valid. Clump C removes the old 106-point pass/fail gate from every domain and replaces it with explicit source, recency, domain-anchor, relevance, and materiality checks. The live proof still comes from a developer Current Context refresh because the new query inventory is broader than the saved audit corpus.",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT_MD.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
