from __future__ import annotations

import pandas as pd
import streamlit as st

from rendering.visual_system import render_plotly_chart
from rendering.charts_adaptation import adaptation_history, adaptation_sector_bars, consumer_adoption_history
from rendering.common import _render_floating_terms
from rendering.commercialization import filtered_ledger, metric_value
from rendering.dataframe import arrow_safe_dataframe
from rendering.components import (
    fmt_date,
    fmt_number,
    render_compact_chart_rail,
    render_domain_read,
    render_metric_stack,
    render_panel_heading,
    render_section,
    render_statline,
    render_summary_row,
    render_tab_header,
)


def _consumer_payload(adaptation_data: dict, key: str) -> dict:
    payload = (adaptation_data or {}).get(key, {})
    return payload if isinstance(payload, dict) else {}


def _adaptation_source_rows(adaptation_data):
    national = (adaptation_data or {}).get("national_history")
    rows = []
    if isinstance(national, pd.DataFrame) and not national.empty:
        latest = national.sort_values("Date").iloc[-1]
        for name, display_name in [
            ("Current AI Use", "Current Business AI Use"),
            ("Expected AI Use", "Expected Business AI Use"),
            ("Expected Adoption Gap", "Expected Business Adoption Gap"),
        ]:
            rows.append({
                "Series": display_name,
                "Reading": fmt_number(latest.get(name), 1, suffix=" percentage points" if name == "Expected Adoption Gap" else "%"),
                "Observation Date": fmt_date(latest.get("Date")),
                "Source": "U.S. Census BTOS",
            })

    for key, label in [
        ("consumer_overall", "Adult Generative-AI Use — Any Purpose"),
        ("consumer_personal", "Adult Generative-AI Use — Personal / Outside Work"),
        ("consumer_work", "Adult Generative-AI Use — Work"),
        ("consumer_active", "Adult Generative-AI Use — Used Last Week"),
        ("consumer_daily", "Adult Generative-AI Use — Daily"),
    ]:
        payload = _consumer_payload(adaptation_data or {}, key)
        rows.append({
            "Series": label,
            "Reading": fmt_number(payload.get("value"), 1, suffix="%"),
            "Observation Date": fmt_date(payload.get("date")),
            "Source": "Real-Time Population Survey via FRED",
        })
    return pd.DataFrame(rows)


def _societal_metrics(adaptation_data):
    overall = _consumer_payload(adaptation_data, "consumer_overall")
    personal = _consumer_payload(adaptation_data, "consumer_personal")
    active = _consumer_payload(adaptation_data, "consumer_active")
    daily = _consumer_payload(adaptation_data, "consumer_daily")
    return [
        ("Any-purpose use", fmt_number(overall.get("value"), 1, suffix="%"), f"adults age 18–64 · {fmt_date(overall.get('date'))}"),
        ("Personal / outside work", fmt_number(personal.get("value"), 1, suffix="%"), f"adults age 18–64 · {fmt_date(personal.get('date'))}"),
        ("Used last week", fmt_number(active.get("value"), 1, suffix="%"), f"adults age 18–64 · {fmt_date(active.get('date'))}"),
        ("Daily use", fmt_number(daily.get("value"), 1, suffix="%"), f"adults age 18–64 · {fmt_date(daily.get('date'))}"),
    ]


def _render_societal_summary(adaptation_data):
    render_statline(_societal_metrics(adaptation_data), key_prefix="adoption-societal-summary")


def _business_metrics(adaptation_data):
    current = pd.to_numeric((adaptation_data or {}).get("current_use"), errors="coerce")
    expected = pd.to_numeric((adaptation_data or {}).get("expected_use"), errors="coerce")
    expected_gap = pd.to_numeric((adaptation_data or {}).get("expected_adoption_gap"), errors="coerce")
    annual = pd.to_numeric((adaptation_data or {}).get("annual_change"), errors="coerce")
    return [
        ("Current business use", fmt_number(current, 1, suffix="%"), "used AI in any business function"),
        ("Expected business use", fmt_number(expected, 1, suffix="%"), "expected within six months"),
        ("Expected adoption gap", fmt_number(expected_gap, 1, signed=True, suffix=" pp"), "expected minus current use"),
        ("12-month change", fmt_number(annual, 1, signed=True, suffix=" pp"), fmt_date((adaptation_data or {}).get("snapshot_date"))),
    ]


def _render_business_summary(adaptation_data):
    render_statline(_business_metrics(adaptation_data), key_prefix="adoption-business-summary")


def _render_paid_adoption(commercialization_data):
    chatgpt_subscribers = metric_value(commercialization_data, "OpenAI", "Consumer subscribers")
    subscriber_share = metric_value(commercialization_data, "OpenAI", "Implied subscriber share")
    openai_business = metric_value(commercialization_data, "OpenAI", "Paying business users")
    gemini_enterprise = metric_value(commercialization_data, "Alphabet", "Paid seats")
    if all(pd.isna(value) for value in [chatgpt_subscribers, subscriber_share, openai_business, gemini_enterprise]):
        return
    render_section("Paid use", "Provider disclosures on paid consumer and enterprise use.")
    render_summary_row([
        ("ChatGPT subscribers", fmt_number(chatgpt_subscribers, 0, suffix="M+"), "consumer subscriptions"),
        ("Subscriber share", fmt_number(subscriber_share, 1, suffix="%"), "rough share of weekly users"),
        ("OpenAI business users", fmt_number(openai_business, 0, suffix="M"), "paid business-account users"),
        ("Gemini Enterprise", fmt_number(gemini_enterprise, 0, suffix="M"), "paid seats"),
    ], key_prefix="adoption-paid")

def _render_adoption_ledger(adaptation_data, commercialization_data):
    datasets = {
        "People history": (adaptation_data or {}).get("consumer_history"),
        "Business history": (adaptation_data or {}).get("national_history"),
        "Industry snapshot": (adaptation_data or {}).get("sector_snapshot"),
        "Paid disclosures": filtered_ledger(commercialization_data, pillars=["Paid demand", "Enterprise adoption", "Reach"]),
    }
    with st.expander("Adoption data", expanded=False):
        view = st.radio("Dataset", list(datasets), horizontal=True, key="adoption-ledger-view")
        st.dataframe(arrow_safe_dataframe(datasets.get(view)), width="stretch", hide_index=True, height=440)

def render_adaptation_tab(adaptation_data, commercialization_data=None, tab_read=None):
    render_tab_header("Adoption", "Personal AI use, business adoption, paid use, and industry differences.", "RPS / U.S. Census BTOS / primary provider disclosures")
    _render_floating_terms("adaptation")
    render_domain_read(tab_read, label="Read", domain="adoption")

    render_section("Current use", "Current personal and business use, shown together before the longer history.", first=True, compact=True)
    societal = _societal_metrics(adaptation_data)
    business = _business_metrics(adaptation_data)
    render_summary_row([societal[0], societal[2], business[0], business[2]], key_prefix="adoption-diffusion-state")

    render_section("Use over time", "Survey estimates of personal use or business use over time, one view at a time.")
    with st.container(key="full-width-layout-adoption-trajectory"):
        with st.container(border=True, key="adoption-panel-trajectory"):
            view = st.radio("Use view", ["People", "Business"], horizontal=True, label_visibility="collapsed", key="adoption-trajectory-view")
            if view == "Business":
                render_panel_heading("Business AI use over time", "Census BTOS / employer businesses / 95% confidence intervals")
                figure, key = adaptation_history((adaptation_data or {}).get("national_history")), "adaptation-national-history"
                render_summary_row(_business_metrics(adaptation_data), key_prefix="adoption-business-summary")
            else:
                render_panel_heading("Personal AI use over time", "Real-Time Population Survey · quarterly · adults age 18–64")
                figure, key = consumer_adoption_history((adaptation_data or {}).get("consumer_history")), "adoption-consumer-history"
                render_summary_row(_societal_metrics(adaptation_data), key_prefix="adoption-societal-summary")
            render_plotly_chart(figure, width="stretch", config={"displayModeBar": True, "responsive": True}, key=key)

    _render_paid_adoption(commercialization_data)
    render_section("AI use by industry", "Current and expected AI use across major U.S. industries.")
    with st.container(key="full-width-layout-adoption-industry-breadth"):
        with st.container(border=True, key="adoption-panel-industry-breadth"):
            render_panel_heading("AI use by industry", "Latest published observation / 95% confidence intervals")
            render_plotly_chart(adaptation_sector_bars((adaptation_data or {}).get("sector_snapshot")), width="stretch", config={"displayModeBar": True, "responsive": True}, key="adaptation-sector-breadth")
    _render_adoption_ledger(adaptation_data, commercialization_data)

