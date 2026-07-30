"""Visual system for the research overlay."""

from __future__ import annotations

import streamlit as st


def inject_research_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --rm-bg: #090e1a;
            --rm-surface: #111827;
            --rm-surface-2: #0f172a;
            --rm-border: rgba(148, 163, 184, 0.17);
            --rm-border-strong: rgba(167, 139, 250, 0.30);
            --rm-text: #e5e7eb;
            --rm-muted: #94a3b8;
            --rm-violet: #a78bfa;
            --rm-violet-deep: #7c3aed;
            --rm-blue: #60a5fa;
            --rm-blue-deep: #2563eb;
            --rm-slate: #cbd5e1;
            --rm-amber: #fbbf24;
            --rm-red: #fb7185;
            --rm-green: #34d399;
        }

        .stApp {
            background:
                linear-gradient(180deg, rgba(124, 58, 237, 0.035), transparent 13rem),
                var(--rm-bg);
            color: var(--rm-text);
        }

        .block-container {
            max-width: 1560px;
            padding-top: 1.0rem;
            padding-bottom: 4rem;
        }

        [data-testid="stSidebar"] {
            background: #080d18;
            border-right: 1px solid var(--rm-border);
        }

        [data-testid="stSidebar"] hr {
            border-color: var(--rm-border);
        }

        .rm-developer-tools-header {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: 0.75rem;
            width: 100%;
        }

        .rm-developer-tools-title {
            color: #f8fafc;
            font-size: 1.25rem;
            line-height: 1.35;
            font-weight: 700;
            letter-spacing: -0.015em;
        }

        .rm-developer-tools-version {
            color: var(--rm-muted);
            font-size: 0.69rem;
            line-height: 1;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            white-space: nowrap;
        }

        .rm-developer-tools-divider {
            border-top: 1px solid var(--rm-border);
            margin: 0.55rem 0 0.75rem 0;
        }

        div[data-testid="stTabs"] [role="tablist"] {
            gap: 1.35rem;
            border-bottom: 1px solid var(--rm-border);
            margin-bottom: 1.1rem;
        }

        div[data-testid="stTabs"] button[role="tab"] {
            min-width: 0;
            padding: 0.72rem 0.05rem 0.8rem 0.05rem;
            color: #7f8ba1;
            background: transparent;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-size: 0.73rem;
            font-weight: 800;
            border-bottom: 2px solid transparent;
        }

        div[data-testid="stTabs"] button[aria-selected="true"] {
            color: #f8fafc;
            border-bottom-color: var(--rm-violet);
        }

        .rm-masthead {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto;
            align-items: end;
            gap: 1.2rem;
            padding: 0.85rem 0 1rem 0;
            border-bottom: 1px solid var(--rm-border);
            margin-bottom: 0.9rem;
        }

        .rm-kicker {
            color: var(--rm-violet);
            font-size: 0.69rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.16em;
            margin-bottom: 0.25rem;
        }

        .rm-title {
            color: #f8fafc;
            font-size: clamp(1.85rem, 3vw, 2.7rem);
            line-height: 1.0;
            letter-spacing: -0.035em;
            font-weight: 800;
            margin: 0;
        }

        .rm-subtitle {
            color: #aeb8c8;
            font-size: 0.98rem;
            line-height: 1.5;
            margin-top: 0.45rem;
            max-width: 1000px;
        }

        .rm-mast-meta {
            color: var(--rm-muted);
            font-size: 0.75rem;
            line-height: 1.7;
            text-align: right;
            white-space: nowrap;
        }

        .rm-mast-meta b {
            color: #dbe3ef;
            font-weight: 700;
        }

        .rm-tabhead {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto;
            gap: 1.2rem;
            align-items: end;
            margin: 0.2rem 0 1rem 0;
        }

        .rm-tabtitle {
            color: #f8fafc;
            font-size: 1.55rem;
            line-height: 1.1;
            letter-spacing: -0.02em;
            font-weight: 770;
        }

        .rm-tabcopy {
            color: var(--rm-muted);
            font-size: 0.91rem;
            line-height: 1.45;
            max-width: 900px;
            margin-top: 0.28rem;
        }

        .rm-tabmeta {
            color: #aab4c5;
            font-size: 0.73rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 700;
            text-align: right;
        }


        .rm-section {
            margin: 1.35rem 0 0.7rem 0;
            padding-top: 0.95rem;
            border-top: 1px solid var(--rm-border);
        }

        .rm-section.first {
            margin-top: 0;
            border-top: none;
            padding-top: 0;
        }

        .rm-section-title {
            color: #edf2f7;
            font-size: 1.05rem;
            font-weight: 760;
            letter-spacing: 0.01em;
        }

        .rm-section-copy {
            color: var(--rm-muted);
            font-size: 0.84rem;
            line-height: 1.45;
            margin-top: 0.18rem;
            max-width: 980px;
        }

        .rm-card {
            border: 1px solid var(--rm-border);
            border-radius: 14px;
            background: rgba(17, 24, 39, 0.82);
            padding: 0.95rem 1rem 0.75rem 1rem;
            min-height: 178px;
        }

        .rm-card.primary {
            border-top: 3px solid var(--rm-violet);
        }

        .rm-card.blue {
            border-top: 3px solid var(--rm-blue);
        }

        .rm-card.slate {
            border-top: 3px solid #94a3b8;
        }

        .rm-card-label {
            color: #aab4c5;
            font-size: 0.69rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.10em;
        }

        .rm-card-value {
            color: #f8fafc;
            font-size: 2.05rem;
            line-height: 1.05;
            font-weight: 770;
            letter-spacing: -0.035em;
            margin-top: 0.3rem;
        }

        .rm-card-context {
            color: #cbd5e1;
            font-size: 0.79rem;
            line-height: 1.35;
            margin-top: 0.3rem;
            min-height: 2.1rem;
        }

        .rm-card-meta {
            display: flex;
            justify-content: space-between;
            gap: 0.5rem;
            color: #7f8ba1;
            font-size: 0.69rem;
            line-height: 1.25;
            margin-top: 0.55rem;
        }

        .rm-rail {
            height: 5px;
            background: #202a3b;
            border-radius: 999px;
            position: relative;
            margin-top: 0.75rem;
        }

        .rm-rail-zero {
            position: absolute;
            width: 1px;
            height: 11px;
            top: -3px;
            left: 50%;
            background: rgba(203, 213, 225, 0.45);
        }

        .rm-rail-marker {
            position: absolute;
            width: 10px;
            height: 10px;
            top: -2.5px;
            transform: translateX(-50%);
            border-radius: 50%;
            background: var(--rm-violet);
            border: 2px solid #111827;
            box-shadow: 0 0 0 1px rgba(167, 139, 250, 0.40);
        }

        .rm-statline {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.65rem;
            margin-bottom: 0.85rem;
        }

        .rm-stat {
            border: 1px solid var(--rm-border);
            border-radius: 12px;
            background: rgba(15, 23, 42, 0.68);
            padding: 0.75rem 0.85rem;
        }

        .rm-stat-label {
            color: #8793a8;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.65rem;
            font-weight: 800;
        }

        .rm-stat-value {
            color: #edf2f7;
            font-size: 1.25rem;
            font-weight: 740;
            margin-top: 0.2rem;
        }

        .rm-stat-note {
            color: #8995a8;
            font-size: 0.69rem;
            margin-top: 0.12rem;
        }

        .rm-panel {
            border: 1px solid var(--rm-border);
            border-radius: 15px;
            background: rgba(17, 24, 39, 0.70);
            padding: 1rem 1rem 0.7rem 1rem;
            margin-bottom: 0.9rem;
        }

        .rm-panel-head {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            align-items: baseline;
            margin-bottom: 0.4rem;
        }

        .rm-panel-title {
            color: #f1f5f9;
            font-size: 1rem;
            font-weight: 760;
        }

        .rm-panel-meta {
            color: #8692a6;
            font-size: 0.72rem;
            text-align: right;
        }

        .rm-definition {
            border-left: 3px solid var(--rm-violet);
            background: rgba(17, 24, 39, 0.68);
            border-radius: 0 12px 12px 0;
            padding: 0.9rem 1rem;
            color: #cbd5e1;
            line-height: 1.5;
        }

        .rm-table-wrap {
            overflow-x: auto;
            border: 1px solid var(--rm-border);
            border-radius: 12px;
            background: rgba(15, 23, 42, 0.58);
        }

        .rm-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.78rem;
            color: #d7dee9;
        }

        .rm-table th {
            color: #9eabc0;
            background: rgba(30, 41, 59, 0.72);
            text-transform: uppercase;
            letter-spacing: 0.055em;
            font-size: 0.64rem;
            font-weight: 800;
            text-align: left;
            padding: 0.68rem 0.72rem;
            border-bottom: 1px solid var(--rm-border);
            white-space: nowrap;
        }

        .rm-table td {
            padding: 0.62rem 0.72rem;
            border-bottom: 1px solid rgba(148, 163, 184, 0.10);
            vertical-align: top;
            line-height: 1.35;
            white-space: nowrap;
        }

        .rm-table tbody tr:last-child td { border-bottom: none; }
        .rm-table tbody tr:hover { background: rgba(96, 165, 250, 0.035); }

        [data-testid="stMetric"] {
            background: transparent;
        }

        [data-testid="stDataFrame"] {
            border: 1px solid var(--rm-border);
            border-radius: 12px;
            overflow: hidden;
        }

        .stExpander {
            border: 1px solid var(--rm-border) !important;
            border-radius: 12px !important;
            background: rgba(15, 23, 42, 0.55) !important;
        }

        hr {
            border-color: var(--rm-border);
        }

        @media (max-width: 900px) {
            .rm-masthead, .rm-tabhead {
                grid-template-columns: 1fr;
            }
            .rm-mast-meta, .rm-tabmeta {
                text-align: left;
                white-space: normal;
            }
            .rm-statline {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
