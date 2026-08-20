"""Validate BTOS AI supplement transcription, Adoption Depth analytics, and integration."""

from __future__ import annotations

import argparse
import re
from io import BytesIO
from pathlib import Path
import sys

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.adoption_depth import QUESTION_CONTRACTS, adoption_depth_contract_report, build_adoption_depth_snapshot
from loaders.adoption_depth_loader import BTOS_AI_SUPPLEMENT_URL, BTOS_REQUEST_HEADERS, parse_btos_ai_supplement_workbook
from rendering.charts_adoption import adoption_depth_bars, adoption_function_bars


def _check(condition, message):
    if not condition:
        raise AssertionError(message)


def _key(value) -> str:
    text = str(value or "").casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _tokens(value) -> set[str]:
    return set(_key(value).split())


def _fixture() -> bytes:
    response_rows = []
    error_rows = []

    def add(scope, qid, question, answer_id, answer, estimate=None, estimate_yes=None, se=None, se_yes=None):
        response_rows.append({
            "Scope (see data dictionary)": scope,
            "Question ID": qid,
            "Question": question,
            "Answer ID": answer_id,
            "Answer": answer,
            "Estimate": estimate,
            "Estimate - Yes": estimate_yes,
        })
        error_rows.append({
            "Scope (see data dictionary)": scope,
            "Question ID": qid,
            "Question": question,
            "Answer ID": answer_id,
            "Answer": answer,
            "SE": se,
            "SE - Yes": se_yes,
        })

    q23 = "In the last two weeks, did this business use Artificial Intelligence (AI) in any of its business functions?"
    for answer_id, answer, share in [(1, "Yes", "17.9%"), (2, "No", "71.3%"), (3, "Do not know", "10.8%")]:
        add(1, 1, q23, answer_id, answer, estimate=share, se="0.13%")

    q24 = "In the last six months, did this business use Artificial Intelligence (AI) in any of the following business functions?"
    function_rows = [
        (7, "Production of goods", "2.0%"),
        (1, "Provision of services, products, or merchandise", "6.5%"),
        (15, "Strategy and business development", "12.4%"),
        (3, "Finance and accounting", "10.8%"),
        (12, "Sales & Marketing", "14.3%"),
        (6, "Customer service", "8.0%"),
        (9, "Research and development", "11.2%"),
        (2, "Information technology", "11.4%"),
        (14, "Human resources", "4.3%"),
        (5, "Public relations and communication", "9.4%"),
        (11, "Management and administration", "8.4%"),
        (4, "Sourcing, supply chains, and purchasing", "2.7%"),
        (13, "Quality management and control", "2.8%"),
        (8, "Distribution", "0.9%"),
        (10, "Legal and compliance", "7.0%"),
    ]
    for answer_id, label, share in function_rows:
        add(1, 2, q24, answer_id, label, estimate_yes=share, se_yes="0.11%" if "Sales" in label else "0.03%")
    add(2, 2, q24, 1, "Wrong-scope sentinel", estimate="999%", se="1%")

    q25 = "In the last six months, did this business use Artificial Intelligence (AI) to do any of the following?"
    for answer_id, answer, share in [
        (4, "None of the above", "52%"),
        (2, "Supplement or enhance a task performed by an employee", "44%"),
        (1, "Perform a task previously done by an employee", "13%"),
        (3, "Introduce a new task not previously done by an employee", "8%"),
    ]:
        add(2, 3, q25, answer_id, answer, estimate=share, se="0.5%")
    add(1, 3, q25, 1, "Wrong-scope sentinel", estimate="999%", se="1%")

    q28 = "In the last six months, how did the use of Artificial Intelligence (AI) affect this business's total employment?"
    for answer_id, answer, share in [(3, "No change", "95.7%"), (1, "Increased", "2.3%"), (2, "Decreased", "2.0%")]:
        add(2, 6, q28, answer_id, answer, estimate=share, se="0.2%")
    add(1, 6, q28, 1, "Wrong-scope sentinel", estimate="999%", se="1%")

    q29 = "In the last six months, to use Artificial Intelligence (AI), what changes did this business make?"
    adjustments = [
        (7, "Used vendors or consulting services to install or integrate AI", "8%"),
        (2, "Hired staff trained in AI", "5%"),
        (9, "This business did not make any changes to use AI", "64%"),
        (1, "Trained current staff to use AI", "15%"),
        (8, "Other (please describe:)", "S"),
        (4, "Purchased cloud services or cloud storage", "12%"),
        (6, "Developed new workflows", "15%"),
        (3, "Purchased computing power or specialized equipment or software", "11%"),
        (5, "Changed data collection or data management practices", "10%"),
    ]
    for answer_id, answer, share in adjustments:
        add(2, 7, q29, answer_id, answer, estimate=share, se="0.5%" if share != "S" else "S")
    add(1, 7, q29, 1, "Wrong-scope sentinel", estimate="999%", se="1%")

    q30 = "In the last six months, did this business's employees use Artificial Intelligence (AI) to assist in any work-related tasks that support business functions?"
    for answer_id, answer, share in [(3, "Do not know", "11.7%"), (1, "Yes", "22.6%"), (2, "No", "65.8%")]:
        add(1, 8, q30, answer_id, answer, estimate=share, se="0.2%")
    add(2, 8, q30, 1, "Wrong-scope sentinel", estimate="999%", se="1%")

    q31 = "In the last six months, did this business's employees use Generative AI to assist in any work-related tasks?"
    for answer_id, answer, share in [(2, "No", "66.9%"), (3, "Do not know", "12.4%"), (1, "Yes", "20.8%")]:
        add(1, 9, q31, answer_id, answer, estimate=share, se="0.2%")
    add(2, 9, q31, 1, "Wrong-scope sentinel", estimate="999%", se="1%")

    q32 = "In the last six months, what work-related tasks did this business's employees use Generative AI to assist with?"
    tasks = [
        (6, "Information processing, paperwork, or filing", "42%"),
        (8, "Writing or editing documents, emails, or communications", "85%"),
        (2, "Interpreting, analyzing, translating, or summarizing documents", "46%"),
        (9, "Customer support", "23%"),
        (1, "Developing or researching new projects, processes, or products", "31%"),
        (7, "Searching for information or technical help", "50%"),
        (3, "Software coding or debugging", "21%"),
        (10, "Data analysis or visualization", "26%"),
        (5, "Tutoring, training, or learning", "18%"),
        (4, "Other tasks (please describe:)", "S"),
    ]
    for answer_id, answer, share in tasks:
        add(4, 10, q32, answer_id, answer, estimate=share, se="0.5%" if share != "S" else "S")
    add(1, 10, q32, 1, "Wrong-scope sentinel", estimate="999%", se="1%")

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(response_rows).to_excel(writer, sheet_name="National Response Estimates", index=False)
        pd.DataFrame(error_rows).to_excel(writer, sheet_name="National Standard Errors", index=False)
    return buffer.getvalue()

def _validate_source_adapter(content: bytes) -> pd.DataFrame:
    source = parse_btos_ai_supplement_workbook(content)
    _check({1, 2, 4}.issubset(set(pd.to_numeric(source["Scope"], errors="coerce").dropna().astype(int))), "Source adapter dropped scopes")
    _check(source["Measure 1 Header"].eq("Estimate").all(), "Source adapter changed the Estimate header")
    _check(source["Measure 2 Header"].eq("Estimate - Yes").all(), "Source adapter changed the Estimate - Yes header")
    q1 = source.loc[(source["Scope"] == 1) & (source["Question ID"] == 1) & (source["Answer ID"] == 1)].iloc[0]
    _check(q1["Measure 1"] == 17.9, "Source adapter changed the QID 1 last-two-weeks firm-use rate")
    _check(q1["Measure 1 Standard Error Header"] == "SE", "Source adapter changed the live SE header contract")
    q2 = source.loc[(source["Scope"] == 1) & (source["Question ID"] == 2)]
    _check(q2["Measure 1 Status"].eq("missing").all(), "Source adapter changed QID 2 missing Estimate handling")
    _check(q2["Measure 2 Status"].eq("observed").all(), "Source adapter changed QID 2 Estimate - Yes handling")
    distribution = q2.loc[q2["Answer"].eq("Distribution")].iloc[0]
    _check(distribution["Measure 2"] == 0.9, "Percent strings below one percentage point were rescaled")
    _check(distribution["Measure 2 Standard Error"] == 0.03, "Sub-one-percent standard errors were rescaled")
    other = source.loc[(source["Scope"] == 4) & (source["Question ID"] == 10) & source["Answer"].map(_key).str.startswith("other tasks")].iloc[0]
    _check(other["Measure 1 Status"] == "suppressed" and pd.isna(other["Measure 1"]), "Source adapter changed suppression handling")
    return source


def _validate_snapshot(source: pd.DataFrame) -> dict:
    snapshot = build_adoption_depth_snapshot(source)
    _check({qid: contract.scope for qid, contract in QUESTION_CONTRACTS.items()} == {1: 1, 2: 1, 3: 2, 6: 2, 7: 2, 8: 1, 9: 1, 10: 4}, "Adoption Depth QID scope contract changed")
    _check(snapshot["functional_use_pct"] == 27.7, "Six-month functional-use denominator changed")
    _check(snapshot["worker_ai_use_pct"] == 22.6, "Employee AI use mapping changed")
    _check(snapshot["worker_genai_use_pct"] == 20.8, "Employee Generative AI use mapping changed")
    _check(snapshot["function_le3_share_pct"] == 57.0, "Business-function breadth benchmark changed")
    _check(snapshot["task_le3_share_pct"] == 65.0, "Worker-task breadth benchmark changed")
    _check({"sales", "marketing"}.issubset(_tokens(snapshot["top_function"])), "Leading business function mapping changed")
    _check(abs(snapshot["top_function_use_pct"] - (14.3 / 27.7 * 100.0)) < 1e-9, "Business-function conditionalization changed")
    distribution = snapshot["functions"].loc[snapshot["functions"]["Function"].eq("Distribution")].iloc[0]
    _check(abs(distribution["Share"] - (0.9 / 27.7 * 100.0)) < 1e-9, "Low-incidence function conditionalization changed")
    _check(snapshot["functions"]["SE"].isna().all(), "Conditional function rates expose unsupported standard errors")
    _check({"writing", "editing"}.issubset(_tokens(snapshot["top_task"])), "Leading worker-task mapping changed")
    _check(snapshot["top_task_use_pct"] == 85.0, "Worker-task share changed")
    _check(snapshot["organizational_change_share_pct"] == 36.0, "Organizational-change calculation changed")
    _check(snapshot["task_augmentation_pct"] == 44.0, "Task-augmentation mapping changed")
    _check(snapshot["employment_increase_pct"] == 2.3, "Employment-increase mapping changed")
    _check(snapshot["employment_decrease_pct"] == 2.0, "Employment-decrease mapping changed")
    _check(snapshot["employment_unchanged_pct"] == 95.7, "Employment-no-change mapping changed")
    _check(len(snapshot["functions"]) == 15, "Business-function analytical contract changed")
    _check(len(snapshot["worker_tasks"]) == 9, "Suppressed worker-task category handling changed")
    return snapshot


def _validate_integration(snapshot: dict) -> None:
    function_figure = adoption_function_bars(snapshot["functions"])
    task_figure = adoption_depth_bars(snapshot["worker_tasks"], category="Task", value="Share")
    _check(len(function_figure.data) == 1, "Business-function chart contract changed")
    _check(len(task_figure.data) == 1, "Worker-task chart contract changed")



def _diagnostics(source: pd.DataFrame, snapshot: dict | None = None) -> str:
    report = adoption_depth_contract_report(source)
    relevant = report.loc[report["Question ID"].isin([1, 2, 3, 6, 7, 8, 9, 10])]
    parts = [relevant.to_string(index=False)]
    if snapshot:
        functions = snapshot.get("functions")
        tasks = snapshot.get("worker_tasks")
        if isinstance(functions, pd.DataFrame) and not functions.empty:
            parts.append("\nTop business functions:\n" + functions.sort_values("Share", ascending=False).head(5).to_string(index=False))
        if isinstance(tasks, pd.DataFrame) and not tasks.empty:
            parts.append("\nTop worker tasks:\n" + tasks.sort_values("Share", ascending=False).head(5).to_string(index=False))
    return "\n".join(parts)


def _live() -> None:
    response = requests.get(BTOS_AI_SUPPLEMENT_URL, timeout=60, headers=BTOS_REQUEST_HEADERS)
    response.raise_for_status()
    source = None
    snapshot = None
    try:
        source = parse_btos_ai_supplement_workbook(response.content)
        snapshot = build_adoption_depth_snapshot(source)
        functions = snapshot["functions"]
        tasks = snapshot["worker_tasks"]
        worker_ai = pd.to_numeric(snapshot.get("worker_ai_use_pct"), errors="coerce")
        worker_genai = pd.to_numeric(snapshot.get("worker_genai_use_pct"), errors="coerce")
        functional_use = pd.to_numeric(snapshot.get("functional_use_pct"), errors="coerce")
        top_function_use = pd.to_numeric(snapshot.get("top_function_use_pct"), errors="coerce")
        top_task_use = pd.to_numeric(snapshot.get("top_task_use_pct"), errors="coerce")
        employment_increase = pd.to_numeric(snapshot.get("employment_increase_pct"), errors="coerce")
        employment_decrease = pd.to_numeric(snapshot.get("employment_decrease_pct"), errors="coerce")
        employment_unchanged = pd.to_numeric(snapshot.get("employment_unchanged_pct"), errors="coerce")

        _check(len(functions) == 15, "Live Census business-function table changed")
        _check(pd.notna(functional_use) and abs(float(functional_use) - 27.7) <= 0.3, "Live Census six-month functional-use rate changed")
        _check(len(tasks) >= 9, "Live Census worker-task table changed")
        _check(pd.notna(worker_ai) and abs(float(worker_ai) - 22.6) <= 0.2, "Live Census employee-AI estimate changed")
        _check(pd.notna(worker_genai) and abs(float(worker_genai) - 20.8) <= 0.2, "Live Census employee-GenAI estimate changed")
        _check({"sales", "marketing"}.issubset(_tokens(snapshot.get("top_function"))), f"Live Census leading function changed: {snapshot.get('top_function')!r}")
        _check(pd.notna(top_function_use) and abs(float(top_function_use) - 52.0) <= 1.5, "Live Census business-function estimate changed")
        _check({"writing", "editing"}.issubset(_tokens(snapshot.get("top_task"))), f"Live Census leading task changed: {snapshot.get('top_task')!r}")
        _check(pd.notna(top_task_use) and float(top_task_use) >= 80.0, "Live Census leading task estimate changed")
        _check(pd.notna(employment_decrease) and abs(float(employment_decrease) - 2.0) <= 0.5, "Live Census employment-decrease estimate changed")
        employment_values = [employment_increase, employment_decrease, employment_unchanged]
        _check(all(pd.notna(value) for value in employment_values), "Live Census employment-effect responses are incomplete")
        _check(abs(sum(float(value) for value in employment_values) - 100.0) <= 1.0, "Live Census employment-effect distribution changed")
    except Exception:
        if isinstance(source, pd.DataFrame) and not source.empty:
            print(_diagnostics(source, snapshot), file=sys.stderr)
        raise

    print(
        "PASS  live Census BTOS AI supplement · "
        f"{len(snapshot['functions'])} business functions · {len(snapshot['worker_tasks'])} published worker-task categories · "
        f"functional use {float(functional_use):.1f}% · employee AI {float(worker_ai):.1f}% · employee GenAI {float(worker_genai):.1f}% · "
        f"leading function {snapshot['top_function']} {float(top_function_use):.1f}% · "
        f"leading task {float(top_task_use):.1f}%"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    source = _validate_source_adapter(_fixture())
    snapshot = _validate_snapshot(source)
    _validate_integration(snapshot)
    print("PASS  Adoption Depth · source transcription · deterministic interpretation · integration")
    if args.live:
        _live()


if __name__ == "__main__":
    main()
