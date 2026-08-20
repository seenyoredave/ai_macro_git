from __future__ import annotations

import pandas as pd
import streamlit as st

from rendering.visual_system import render_plotly_chart
from rendering.charts_adoption import (
    adoption_depth_bars,
    adoption_function_bars,
    adoption_history,
    adoption_sector_bars,
    consumer_adoption_history,
)
from rendering.common import _render_floating_terms
from rendering.commercialization import filtered_ledger, metric_value
from rendering.dataframe import arrow_safe_dataframe
from rendering.components import (
    fmt_date,
    fmt_number,
    render_domain_read,
    render_panel_heading,
    render_section,
    render_summary_row,
    render_tab_header,
)


def _consumer_payload(adoption_data: dict, key: str) -> dict:
    payload = (adoption_data or {}).get(key, {})
    return payload if isinstance(payload, dict) else {}


def _depth(adoption_data: dict) -> dict:
    payload = ((adoption_data or {}).get("depth") or {}).get("snapshot")
    return payload if isinstance(payload, dict) else {}


def _adoption_source_rows(adoption_data):
    national = (adoption_data or {}).get("national_history")
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

    depth = _depth(adoption_data or {})
    reference_end = str(depth.get("reference_end") or "")
    functions = depth.get("functions")
    if isinstance(functions, pd.DataFrame) and not functions.empty:
        for _, row in functions.iterrows():
            rows.append({
                "Series": f"Business function — {row.get('Function', '')}",
                "Reading": fmt_number(row.get("Share"), 1, suffix="%"),
                "Observation Date": reference_end,
                "Source": "U.S. Census BTOS AI Supplement",
            })
    tasks = depth.get("worker_tasks")
    if isinstance(tasks, pd.DataFrame) and not tasks.empty:
        for _, row in tasks.iterrows():
            rows.append({
                "Series": f"Employee GenAI task — {row.get('Task', '')}",
                "Reading": fmt_number(row.get("Share"), 1, suffix="%"),
                "Observation Date": reference_end,
                "Source": "U.S. Census BTOS AI Supplement",
            })

    for key, label in [
        ("consumer_overall", "Adult Generative-AI Use — Any Purpose"),
        ("consumer_personal", "Adult Generative-AI Use — Personal / Outside Work"),
        ("consumer_work", "Adult Generative-AI Use — Work"),
        ("consumer_active", "Adult Generative-AI Use — Used Last Week"),
        ("consumer_daily", "Adult Generative-AI Use — Daily"),
    ]:
        payload = _consumer_payload(adoption_data or {}, key)
        rows.append({
            "Series": label,
            "Reading": fmt_number(payload.get("value"), 1, suffix="%"),
            "Observation Date": fmt_date(payload.get("date")),
            "Source": "Real-Time Population Survey via FRED",
        })
    return pd.DataFrame(rows)

def _societal_metrics(adoption_data):
    overall = _consumer_payload(adoption_data, "consumer_overall")
    personal = _consumer_payload(adoption_data, "consumer_personal")
    active = _consumer_payload(adoption_data, "consumer_active")
    daily = _consumer_payload(adoption_data, "consumer_daily")
    return [
        ("Any-purpose use", fmt_number(overall.get("value"), 1, suffix="%"), f"adults age 18–64 · {fmt_date(overall.get('date'))}"),
        ("Personal / outside work", fmt_number(personal.get("value"), 1, suffix="%"), f"adults age 18–64 · {fmt_date(personal.get('date'))}"),
        ("Used last week", fmt_number(active.get("value"), 1, suffix="%"), f"adults age 18–64 · {fmt_date(active.get('date'))}"),
        ("Daily use", fmt_number(daily.get("value"), 1, suffix="%"), f"adults age 18–64 · {fmt_date(daily.get('date'))}"),
    ]


def _business_metrics(adoption_data):
    current = pd.to_numeric((adoption_data or {}).get("current_use"), errors="coerce")
    expected = pd.to_numeric((adoption_data or {}).get("expected_use"), errors="coerce")
    expected_gap = pd.to_numeric((adoption_data or {}).get("expected_adoption_gap"), errors="coerce")
    annual = pd.to_numeric((adoption_data or {}).get("annual_change"), errors="coerce")
    return [
        ("Current business use", fmt_number(current, 1, suffix="%"), "used AI in any business function"),
        ("Expected business use", fmt_number(expected, 1, suffix="%"), "expected within six months"),
        ("Expected adoption gap", fmt_number(expected_gap, 1, signed=True, suffix=" pp"), "expected minus current use"),
        ("12-month change", fmt_number(annual, 1, signed=True, suffix=" pp"), fmt_date((adoption_data or {}).get("snapshot_date"))),
    ]


def _render_business_integration(adoption_data):
    depth = _depth(adoption_data)
    functions = depth.get("functions")
    if not isinstance(functions, pd.DataFrame) or functions.empty:
        return

    render_section("Business integration", "AI deployment across business functions and organizational changes.")
    integration_metrics = []
    function_le3 = pd.to_numeric(depth.get("function_le3_share_pct"), errors="coerce")
    if pd.notna(function_le3):
        integration_metrics.append(("≤3 business functions", fmt_number(function_le3, 1, suffix="%"), "functional adopters"))
    top_function = str(depth.get("top_function") or "").strip()
    top_function_use = pd.to_numeric(depth.get("top_function_use_pct"), errors="coerce")
    if top_function and pd.notna(top_function_use):
        integration_metrics.append(("Leading function", top_function, f"{fmt_number(top_function_use, 1, suffix="%")} of functional adopters"))
    organizational_change = pd.to_numeric(depth.get("organizational_change_share_pct"), errors="coerce")
    if pd.notna(organizational_change):
        integration_metrics.append(("Organizational change", fmt_number(organizational_change, 1, suffix="%"), "AI-using businesses"))
    if integration_metrics:
        render_summary_row(integration_metrics, key_prefix="adoption-business-integration")

    with st.container(border=True, key="adoption-panel-functions"):
        render_panel_heading("AI deployment by business function", "Last six months · functional adopters · Census BTOS AI Supplement")
        render_plotly_chart(
            adoption_function_bars(functions),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="adoption-function-depth",
        )

    adjustments = depth.get("organizational_adjustments")
    if isinstance(adjustments, pd.DataFrame) and not adjustments.empty:
        with st.container(border=True, key="adoption-panel-organizational-adjustments"):
            render_panel_heading("Organizational changes accompanying AI use", "Training, workflows, data, infrastructure, and external support")
            render_plotly_chart(
                adoption_depth_bars(adjustments, category="Adjustment", value="Share", height=430),
                width="stretch",
                config={"displayModeBar": True, "responsive": True},
                key="adoption-organizational-depth",
            )


def _render_worker_integration(adoption_data):
    depth = _depth(adoption_data)
    tasks = depth.get("worker_tasks")
    labor = depth.get("labor_interaction")
    worker_ai = pd.to_numeric(depth.get("worker_ai_use_pct"), errors="coerce")
    worker_genai = pd.to_numeric(depth.get("worker_genai_use_pct"), errors="coerce")
    if (not isinstance(tasks, pd.DataFrame) or tasks.empty) and pd.isna(worker_ai) and pd.isna(worker_genai):
        return

    render_section("Worker use", "Employee AI use, Generative AI task mix, and reported labor interaction.")
    worker_metrics = []
    if pd.notna(worker_ai):
        worker_metrics.append(("Employee AI use", fmt_number(worker_ai, 1, suffix="%"), "share of employer businesses"))
    if pd.notna(worker_genai):
        worker_metrics.append(("Employee GenAI use", fmt_number(worker_genai, 1, suffix="%"), "share of employer businesses"))
    task_le3 = pd.to_numeric(depth.get("task_le3_share_pct"), errors="coerce")
    if pd.notna(task_le3):
        worker_metrics.append(("≤3 GenAI task types", fmt_number(task_le3, 1, suffix="%"), "businesses reporting GenAI task use"))
    top_task = str(depth.get("top_task") or "").strip()
    top_task_use = pd.to_numeric(depth.get("top_task_use_pct"), errors="coerce")
    if top_task and pd.notna(top_task_use):
        worker_metrics.append(("Leading task", top_task, f"{fmt_number(top_task_use, 1, suffix="%")} of GenAI-task users"))
    if worker_metrics:
        render_summary_row(worker_metrics, key_prefix="adoption-worker-integration")

    if isinstance(tasks, pd.DataFrame) and not tasks.empty:
        with st.container(border=True, key="adoption-panel-worker-tasks"):
            render_panel_heading("Employee Generative AI tasks", "Last six months · businesses reporting employee GenAI use · Census BTOS AI Supplement")
            render_plotly_chart(
                adoption_depth_bars(tasks, category="Task", value="Share", height=470),
                width="stretch",
                config={"displayModeBar": True, "responsive": True},
                key="adoption-worker-task-depth",
            )

    if isinstance(labor, pd.DataFrame) and not labor.empty:
        render_summary_row([
            ("Task augmentation", fmt_number(depth.get("task_augmentation_pct"), 1, suffix="%"), "AI-using businesses"),
            ("Task substitution", fmt_number(depth.get("task_substitution_pct"), 1, suffix="%"), "AI-using businesses"),
            ("Task creation", fmt_number(depth.get("task_creation_pct"), 1, suffix="%"), "AI-using businesses"),
            ("Employment decrease", fmt_number(depth.get("employment_decrease_pct"), 1, suffix="%"), "businesses reporting AI-related change"),
        ], key_prefix="adoption-labor-interaction")


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


def _render_adoption_ledger(adoption_data, commercialization_data):
    datasets = {
        "People history": (adoption_data or {}).get("consumer_history"),
        "Business history": (adoption_data or {}).get("national_history"),
        "AI supplement": ((adoption_data or {}).get("depth") or {}).get("table"),
        "Industry snapshot": (adoption_data or {}).get("sector_snapshot"),
        "Paid disclosures": filtered_ledger(commercialization_data, pillars=["Paid demand", "Enterprise adoption", "Reach"]),
    }
    with st.expander("Adoption data", expanded=False):
        view = st.radio("Dataset", list(datasets), horizontal=True, key="adoption-ledger-view")
        st.dataframe(arrow_safe_dataframe(datasets.get(view)), width="stretch", hide_index=True, height=440)


def render_adoption_tab(adoption_data, commercialization_data=None, tab_read=None):
    render_tab_header(
        "Adoption",
        "Personal use, business adoption, workflow integration, worker tasks, and paid use.",
        "RPS / U.S. Census BTOS / primary provider disclosures",
    )
    _render_floating_terms("adoption")
    render_domain_read(tab_read, label="Read", domain="adoption")

    render_section("Current use", "Current personal and business use.", first=True, compact=True)
    societal = _societal_metrics(adoption_data)
    business = _business_metrics(adoption_data)
    render_summary_row([societal[0], societal[2], business[0], business[2]], key_prefix="adoption-diffusion-state")

    _render_business_integration(adoption_data)
    _render_worker_integration(adoption_data)

    render_section("Use over time", "Survey estimates of personal and business use over time.")
    with st.container(key="full-width-layout-adoption-trajectory"):
        with st.container(border=True, key="adoption-panel-trajectory"):
            view = st.radio("Use view", ["People", "Business"], horizontal=True, label_visibility="collapsed", key="adoption-trajectory-view")
            if view == "Business":
                render_panel_heading("Business AI use over time", "Census BTOS / employer businesses / 95% confidence intervals")
                figure, key = adoption_history((adoption_data or {}).get("national_history")), "adoption-national-history"
                render_summary_row(_business_metrics(adoption_data), key_prefix="adoption-business-summary")
            else:
                render_panel_heading("Personal AI use over time", "Real-Time Population Survey · quarterly · adults age 18–64")
                figure, key = consumer_adoption_history((adoption_data or {}).get("consumer_history")), "adoption-consumer-history"
                render_summary_row(_societal_metrics(adoption_data), key_prefix="adoption-societal-summary")
            render_plotly_chart(figure, width="stretch", config={"displayModeBar": True, "responsive": True}, key=key)

    render_section("AI use by industry", "Current and expected AI use across major U.S. industries.")
    with st.container(key="full-width-layout-adoption-industry-breadth"):
        with st.container(border=True, key="adoption-panel-industry-breadth"):
            render_panel_heading("AI use by industry", "Latest published observation / 95% confidence intervals")
            render_plotly_chart(
                adoption_sector_bars((adoption_data or {}).get("sector_snapshot")),
                width="stretch",
                config={"displayModeBar": True, "responsive": True},
                key="adoption-sector-breadth",
            )

    _render_paid_adoption(commercialization_data)
    _render_adoption_ledger(adoption_data, commercialization_data)
