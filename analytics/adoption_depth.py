from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

SCOPE_ALL_BUSINESSES = 1
SCOPE_AI_USERS = 2
SCOPE_GENAI_TASK_USERS = 4

FIRM_CURRENT_USE_QID = 1
FUNCTION_DEPLOYMENT_QID = 2
TASK_INTERACTION_QID = 3
EMPLOYMENT_EFFECT_QID = 6
ORGANIZATIONAL_ADJUSTMENT_QID = 7
WORKER_AI_QID = 8
WORKER_GENAI_QID = 9
WORKER_TASK_QID = 10


@dataclass(frozen=True, slots=True)
class QuestionContract:
    question_id: int
    scope: int
    required_answer_ids: frozenset[int]


QUESTION_CONTRACTS = {
    FIRM_CURRENT_USE_QID: QuestionContract(FIRM_CURRENT_USE_QID, SCOPE_ALL_BUSINESSES, frozenset({1, 2, 3})),
    FUNCTION_DEPLOYMENT_QID: QuestionContract(FUNCTION_DEPLOYMENT_QID, SCOPE_ALL_BUSINESSES, frozenset(range(1, 16))),
    TASK_INTERACTION_QID: QuestionContract(TASK_INTERACTION_QID, SCOPE_AI_USERS, frozenset({1, 2, 3, 4})),
    EMPLOYMENT_EFFECT_QID: QuestionContract(EMPLOYMENT_EFFECT_QID, SCOPE_AI_USERS, frozenset({1, 2, 3})),
    ORGANIZATIONAL_ADJUSTMENT_QID: QuestionContract(ORGANIZATIONAL_ADJUSTMENT_QID, SCOPE_AI_USERS, frozenset(range(1, 10))),
    WORKER_AI_QID: QuestionContract(WORKER_AI_QID, SCOPE_ALL_BUSINESSES, frozenset({1, 2, 3})),
    WORKER_GENAI_QID: QuestionContract(WORKER_GENAI_QID, SCOPE_ALL_BUSINESSES, frozenset({1, 2, 3})),
    WORKER_TASK_QID: QuestionContract(WORKER_TASK_QID, SCOPE_GENAI_TASK_USERS, frozenset(range(1, 11))),
}


@dataclass(frozen=True, slots=True)
class PublishedBenchmark:
    value: float
    source: str


PUBLISHED_DEPTH_BENCHMARKS = {
    "functional_use_pct": PublishedBenchmark(27.7, "Census CES-26-25 Table C.7"),
    "function_le3_share_pct": PublishedBenchmark(57.0, "Census CES-26-25"),
    "task_le3_share_pct": PublishedBenchmark(65.0, "Census CES-26-25"),
}


def _num(value) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    return float(numeric) if pd.notna(numeric) and np.isfinite(numeric) else np.nan



def _empty_snapshot() -> dict:
    return {
        "functions": pd.DataFrame(columns=["Function", "Share", "SE"]),
        "worker_tasks": pd.DataFrame(columns=["Task", "Share", "SE"]),
        "organizational_adjustments": pd.DataFrame(columns=["Adjustment", "Share", "SE"]),
        "labor_interaction": pd.DataFrame(columns=["Interaction", "Share", "SE"]),
    }


def _question_rows(source: pd.DataFrame, contract: QuestionContract) -> pd.DataFrame:
    qids = pd.to_numeric(source.get("Question ID"), errors="coerce")
    scopes = pd.to_numeric(source.get("Scope"), errors="coerce")
    rows = source.loc[qids.eq(contract.question_id) & scopes.eq(contract.scope)].copy()
    if rows.empty:
        available = sorted({int(value) for value in scopes[qids.eq(contract.question_id)].dropna().tolist()})
        raise ValueError(
            f"BTOS QID {contract.question_id} missing required scope {contract.scope}; "
            f"published scopes={available}"
        )
    rows["Answer ID"] = pd.to_numeric(rows["Answer ID"], errors="coerce").astype("Int64")
    rows["Answer"] = rows.get("Answer", pd.Series("", index=rows.index)).fillna("").astype(str).str.strip()
    observed = {int(value) for value in rows["Answer ID"].dropna().tolist()}
    missing = sorted(set(contract.required_answer_ids) - observed)
    if missing:
        raise ValueError(
            f"BTOS QID {contract.question_id} missing answer IDs {missing}; observed={sorted(observed)}"
        )
    return rows.sort_values("Answer ID", kind="stable").reset_index(drop=True)


def _measure_contract(rows: pd.DataFrame, question_id: int) -> tuple[str, str, str, str]:
    active = []
    for slot in (1, 2):
        status_column = f"Measure {slot} Status"
        value_column = f"Measure {slot}"
        error_column = f"Measure {slot} Standard Error"
        header_column = f"Measure {slot} Header"
        statuses = rows.get(status_column, pd.Series("missing", index=rows.index)).fillna("missing").astype(str)
        if statuses.isin({"observed", "suppressed"}).any():
            header_values = [str(value).strip() for value in rows.get(header_column, pd.Series("", index=rows.index)).dropna().unique()]
            header = header_values[0] if header_values else f"Measure {slot}"
            active.append((value_column, error_column, status_column, header))
    if len(active) != 1:
        details = {
            slot: {
                "header": str(rows.get(f"Measure {slot} Header", pd.Series([""])).iloc[0]),
                "observed": int(rows.get(f"Measure {slot} Status", pd.Series("missing", index=rows.index)).isin({"observed", "suppressed"}).sum()),
            }
            for slot in (1, 2)
        }
        raise ValueError(f"BTOS QID {question_id} expected one published measure slot; slots={details}")
    return active[0]


def _metric_frame(
    source: pd.DataFrame,
    *,
    contract: QuestionContract,
    category_column: str,
) -> pd.DataFrame:
    rows = _question_rows(source, contract)
    value_column, error_column, _, _ = _measure_contract(rows, contract.question_id)
    records = []
    for _, row in rows.iterrows():
        label = str(row.get("Answer") or "").strip()
        if not label:
            continue
        value = _num(row.get(value_column))
        if pd.isna(value):
            continue
        records.append({category_column: label, "Share": value, "SE": _num(row.get(error_column))})
    return pd.DataFrame(records, columns=[category_column, "Share", "SE"])


def _value_for_answer_id(source: pd.DataFrame, contract: QuestionContract, answer_id: int) -> float:
    rows = _question_rows(source, contract)
    value_column, _, _, _ = _measure_contract(rows, contract.question_id)
    matches = rows.loc[rows["Answer ID"].eq(answer_id)]
    if len(matches) != 1:
        observed = sorted(int(value) for value in rows["Answer ID"].dropna().tolist())
        raise ValueError(
            f"BTOS QID {contract.question_id} expected answer ID {answer_id} exactly once; "
            f"matches={len(matches)}; published answer IDs={observed}"
        )
    return _num(matches.iloc[0].get(value_column))





def _functional_deployment_frame(source: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    # The public Q24 table publishes marginal Yes rates for each business function,
    # but not the joint "used AI in at least one function" rate needed to
    # conditionalize them. Census publishes that pooled firm-weighted Q24 rate
    # as 27.7% in CES-26-25 Table C.7 for this supplement reference period.
    functional_use = PUBLISHED_DEPTH_BENCHMARKS["functional_use_pct"].value
    if pd.isna(functional_use) or functional_use <= 0:
        raise ValueError(f"BTOS published functional-use denominator is invalid: {functional_use}")

    raw = _metric_frame(
        source,
        contract=QUESTION_CONTRACTS[FUNCTION_DEPLOYMENT_QID],
        category_column="Function",
    )
    if raw.empty:
        return raw, functional_use

    output = raw.rename(columns={"Share": "All-business Share", "SE": "All-business SE"}).copy()
    output["Share"] = 100.0 * pd.to_numeric(output["All-business Share"], errors="coerce") / functional_use
    output["SE"] = np.nan
    values = pd.to_numeric(output["Share"], errors="coerce")
    if values.dropna().gt(100.0 + 1e-9).any():
        bad = output.loc[values.gt(100.0 + 1e-9), ["Function", "All-business Share", "Share"]].to_dict("records")
        raise ValueError(f"BTOS QID {FUNCTION_DEPLOYMENT_QID} conditionalized function rate exceeds 100%; rows={bad[:5]}")
    return output[["Function", "Share", "SE", "All-business Share", "All-business SE"]], functional_use


def adoption_depth_contract_report(source: pd.DataFrame | None) -> pd.DataFrame:
    columns = [
        "Question ID", "Scope", "Rows", "Answer IDs",
        "Measure 1 Header", "Measure 1 Active",
        "Measure 2 Header", "Measure 2 Active",
    ]
    if not isinstance(source, pd.DataFrame) or source.empty:
        return pd.DataFrame(columns=columns)
    records = []
    frame = source.copy()
    frame["Question ID"] = pd.to_numeric(frame.get("Question ID"), errors="coerce")
    frame["Scope"] = pd.to_numeric(frame.get("Scope"), errors="coerce")
    for (qid, scope), rows in frame.dropna(subset=["Question ID", "Scope"]).groupby(["Question ID", "Scope"], sort=True):
        answer_ids = sorted({int(value) for value in pd.to_numeric(rows["Answer ID"], errors="coerce").dropna().tolist()})
        records.append({
            "Question ID": int(qid),
            "Scope": int(scope),
            "Rows": len(rows),
            "Answer IDs": ",".join(str(value) for value in answer_ids),
            "Measure 1 Header": str(rows.get("Measure 1 Header", pd.Series([""])).iloc[0]),
            "Measure 1 Active": int(rows.get("Measure 1 Status", pd.Series("missing", index=rows.index)).isin({"observed", "suppressed"}).sum()),
            "Measure 2 Header": str(rows.get("Measure 2 Header", pd.Series([""])).iloc[0]),
            "Measure 2 Active": int(rows.get("Measure 2 Status", pd.Series("missing", index=rows.index)).isin({"observed", "suppressed"}).sum()),
        })
    return pd.DataFrame(records, columns=columns)


def build_adoption_depth_snapshot(source: pd.DataFrame | None) -> dict:
    if not isinstance(source, pd.DataFrame) or source.empty:
        return _empty_snapshot()

    functions, functional_use = _functional_deployment_frame(source)
    tasks = _metric_frame(
        source,
        contract=QUESTION_CONTRACTS[WORKER_TASK_QID],
        category_column="Task",
    )
    adjustments = _metric_frame(
        source,
        contract=QUESTION_CONTRACTS[ORGANIZATIONAL_ADJUSTMENT_QID],
        category_column="Adjustment",
    )
    task_interaction = _metric_frame(
        source,
        contract=QUESTION_CONTRACTS[TASK_INTERACTION_QID],
        category_column="Interaction",
    )
    employment = _metric_frame(
        source,
        contract=QUESTION_CONTRACTS[EMPLOYMENT_EFFECT_QID],
        category_column="Interaction",
    )
    labor = pd.concat([task_interaction, employment], ignore_index=True)

    top_function = ""
    top_function_use = np.nan
    if not functions.empty:
        values = pd.to_numeric(functions["Share"], errors="coerce")
        if values.notna().any():
            idx = values.idxmax()
            top_function = str(functions.loc[idx, "Function"])
            top_function_use = _num(functions.loc[idx, "Share"])

    top_task = ""
    top_task_use = np.nan
    if not tasks.empty:
        values = pd.to_numeric(tasks["Share"], errors="coerce")
        if values.notna().any():
            idx = values.idxmax()
            top_task = str(tasks.loc[idx, "Task"])
            top_task_use = _num(tasks.loc[idx, "Share"])

    no_change = _value_for_answer_id(
        source,
        QUESTION_CONTRACTS[ORGANIZATIONAL_ADJUSTMENT_QID],
        9,
    )

    return {
        "functions": functions,
        "worker_tasks": tasks,
        "organizational_adjustments": adjustments,
        "labor_interaction": labor,
        "functional_use_pct": functional_use,
        "worker_ai_use_pct": _value_for_answer_id(source, QUESTION_CONTRACTS[WORKER_AI_QID], 1),
        "worker_genai_use_pct": _value_for_answer_id(source, QUESTION_CONTRACTS[WORKER_GENAI_QID], 1),
        "function_le3_share_pct": PUBLISHED_DEPTH_BENCHMARKS["function_le3_share_pct"].value,
        "task_le3_share_pct": PUBLISHED_DEPTH_BENCHMARKS["task_le3_share_pct"].value,
        "top_function": top_function,
        "top_function_use_pct": top_function_use,
        "top_task": top_task,
        "top_task_use_pct": top_task_use,
        "organizational_change_share_pct": 100.0 - no_change if pd.notna(no_change) else np.nan,
        "task_augmentation_pct": _value_for_answer_id(
            source,
            QUESTION_CONTRACTS[TASK_INTERACTION_QID],
            2,
        ),
        "task_substitution_pct": _value_for_answer_id(
            source,
            QUESTION_CONTRACTS[TASK_INTERACTION_QID],
            1,
        ),
        "task_creation_pct": _value_for_answer_id(
            source,
            QUESTION_CONTRACTS[TASK_INTERACTION_QID],
            3,
        ),
        "employment_increase_pct": _value_for_answer_id(
            source,
            QUESTION_CONTRACTS[EMPLOYMENT_EFFECT_QID],
            1,
        ),
        "employment_decrease_pct": _value_for_answer_id(
            source,
            QUESTION_CONTRACTS[EMPLOYMENT_EFFECT_QID],
            2,
        ),
        "employment_unchanged_pct": _value_for_answer_id(
            source,
            QUESTION_CONTRACTS[EMPLOYMENT_EFFECT_QID],
            3,
        ),
        "reference_start": str(source.get("Reference Start", pd.Series([""])).dropna().iloc[0]) if "Reference Start" in source else "",
        "reference_end": str(source.get("Reference End", pd.Series([""])).dropna().iloc[0]) if "Reference End" in source else "",
    }
