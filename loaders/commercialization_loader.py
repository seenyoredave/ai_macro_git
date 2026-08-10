"""Primary-disclosure commercialization ledger for AI products and services.

Refreshes validate a fixed set of retained primary disclosures. They do not
claim to discover each provider's newest earnings release automatically.
"""

from __future__ import annotations

from pathlib import Path
import re

import numpy as np
import pandas as pd
import requests
import streamlit as st

from config.deployment import repository_writes_enabled
from helpers.atomic_io import atomic_write_csv
from config.debug_config import debug_print

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "commercialization"
LEDGER_PATH = DATA_DIR / "commercialization_ledger.csv"
MANIFEST_PATH = DATA_DIR / "source_manifest.csv"

KEY_COLUMNS = ["Provider","Product / Scope","Pillar","Metric"]

PARSER_CONTRACTS: dict[str, tuple[tuple[str, str, str, str], ...]] = {
    "openai_scale": (
        ("OpenAI","ChatGPT","Reach","Weekly active users"),
        ("OpenAI","ChatGPT","Paid demand","Consumer subscribers"),
        ("OpenAI","ChatGPT for Work","Paid demand","Paying business users"),
    ),
    "openai_economics": (
        ("OpenAI","Company","Revenue realization","Annualized revenue run rate"),
        ("OpenAI","Company","Compute economics","Available compute"),
    ),
    "microsoft_ai_arr": (
        ("Microsoft","AI business","Revenue realization","Annual revenue run rate"),
        ("Microsoft","AI business","Revenue realization","Annual revenue run-rate growth"),
    ),
    "alphabet_q2": (
        ("Alphabet","Google Cloud","Revenue realization","Backlog"),
        ("Alphabet","Google Cloud","Revenue realization","Revenue growth"),
        ("Alphabet","Gemini Enterprise","Enterprise adoption","Fortune 100 using product"),
    ),
    "alphabet_q4": (
        ("Alphabet","Gemini App","Reach","Monthly active users"),
        ("Alphabet","Gemini Enterprise","Paid demand","Paid seats"),
        ("Alphabet","Gemini","Compute economics","Serving unit-cost reduction"),
        ("Alphabet","Company","Capital burden","2026 CapEx midpoint"),
    ),
}


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception as exc:
        debug_print(f"Commercialization retained load failed {path.name} -> {exc}")
        return pd.DataFrame()


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    columns = ["Provider","Product / Scope","Pillar","Metric","Value","Unit","Observation Date","Metric Type","Comparability Group","Source URL","Notes","Evidence Grade","Source Label","Retrieved"]
    if frame is None or frame.empty:
        return pd.DataFrame(columns=columns)
    output = frame.copy()
    for column in columns:
        if column not in output.columns:
            output[column] = np.nan
    output["Value"] = pd.to_numeric(output["Value"], errors="coerce")
    output["Observation Date"] = pd.to_datetime(output["Observation Date"], errors="coerce", format="mixed").dt.date.astype("string")
    return output[columns].dropna(subset=["Provider","Metric"]).drop_duplicates(KEY_COLUMNS, keep="last").sort_values(["Pillar","Provider","Product / Scope","Metric"], kind="stable").reset_index(drop=True)


def _text(url: str) -> str:
    response = requests.get(url, timeout=30, headers={"User-Agent":"ai-macro-commercialization/1.1"})
    response.raise_for_status()
    return re.sub(r"\s+", " ", response.text.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-"))


def _number(text: str, pattern: str, *, scale: float = 1.0) -> float | None:
    match = re.search(pattern, text, flags=re.I)
    if not match:
        return None
    return float(match.group(1).replace(",", "")) * scale


def _parse_contract(key: str, text: str) -> dict[tuple[str, str, str, str], float | None]:
    if key == "openai_scale":
        return {
            ("OpenAI","ChatGPT","Reach","Weekly active users"): _number(text, r"more than\s+([\d,.]+)\s+million weekly active users"),
            ("OpenAI","ChatGPT","Paid demand","Consumer subscribers"): _number(text, r"(?:over|more than)\s+([\d,.]+)\s+million (?:consumer )?subscribers"),
            ("OpenAI","ChatGPT for Work","Paid demand","Paying business users"): _number(text, r"more than\s+([\d,.]+)\s+million paying business users"),
        }
    if key == "openai_economics":
        return {
            ("OpenAI","Company","Revenue realization","Annualized revenue run rate"): _number(text, r"\$([\d,.]+)B\+?\s+in 2025"),
            ("OpenAI","Company","Compute economics","Available compute"): _number(text, r"~?([\d.]+)\s+GW in 2025"),
        }
    if key == "microsoft_ai_arr":
        return {
            ("Microsoft","AI business","Revenue realization","Annual revenue run rate"): _number(text, r"annual revenue run rate (?:of )?\$?([\d,.]+)\s+billion"),
            ("Microsoft","AI business","Revenue realization","Annual revenue run-rate growth"): _number(text, r"growing\s+([\d,.]+)%\s+year-over-year"),
        }
    if key == "alphabet_q2":
        return {
            ("Alphabet","Google Cloud","Revenue realization","Backlog"): _number(text, r"backlog grew to \$([\d,.]+)\s+billion"),
            ("Alphabet","Google Cloud","Revenue realization","Revenue growth"): _number(text, r"Cloud revenue grew\s+([\d,.]+)%"),
            ("Alphabet","Gemini Enterprise","Enterprise adoption","Fortune 100 using product"): _number(text, r"nearly\s+([\d,.]+)%\s+of the Fortune 100"),
        }
    if key == "alphabet_q4":
        parsed = {
            ("Alphabet","Gemini App","Reach","Monthly active users"): _number(text, r"over\s+([\d,.]+)\s+million monthly active users"),
            ("Alphabet","Gemini Enterprise","Paid demand","Paid seats"): _number(text, r"more than\s+([\d,.]+)\s+million paid seats"),
            ("Alphabet","Gemini","Compute economics","Serving unit-cost reduction"): _number(text, r"lower Gemini serving unit costs by\s+([\d,.]+)%"),
        }
        low = _number(text, r"range of \$([\d,.]+)\s+billion to \$[\d,.]+\s+billion")
        high = _number(text, r"range of \$[\d,.]+\s+billion to \$([\d,.]+)\s+billion")
        parsed[("Alphabet","Company","Capital burden","2026 CapEx midpoint")] = (low + high) / 2.0 if low is not None and high is not None else None
        return parsed
    return {}


def _refresh_values(manifest: pd.DataFrame) -> tuple[dict[tuple[str,str,str,str], float], dict[str,str], dict[str,dict]]:
    values: dict[tuple[str,str,str,str], float] = {}
    errors: dict[str,str] = {}
    parser_reports: dict[str,dict] = {}
    active_rows = manifest.loc[manifest.get("Status", pd.Series("active", index=manifest.index)).astype(str).str.casefold().eq("active")] if isinstance(manifest, pd.DataFrame) else pd.DataFrame()
    for row in active_rows.to_dict(orient="records"):
        key = str(row.get("Parser Key") or "").strip()
        url = str(row.get("Source URL") or "").strip()
        expected = tuple(PARSER_CONTRACTS.get(key, ()))
        report = {"source_url": url, "expected": len(expected), "parsed": 0, "missing_metrics": [], "status": "not_run"}
        if not key or not url.startswith("https://"):
            report["status"] = "invalid_manifest"
            errors[key or "missing_parser_key"] = "Active source is missing a parser key or HTTPS URL."
            parser_reports[key or "missing_parser_key"] = report
            continue
        if not expected:
            report["status"] = "missing_contract"
            errors[key] = "No expected-metric contract is defined for this parser."
            parser_reports[key] = report
            continue
        try:
            parsed = _parse_contract(key, _text(url))
            missing = [metric for metric in expected if parsed.get(metric) is None]
            valid = {metric: float(parsed[metric]) for metric in expected if parsed.get(metric) is not None}
            values.update(valid)
            report.update({
                "parsed": len(valid),
                "missing_metrics": [" / ".join(metric) for metric in missing],
                "status": "complete" if not missing else "partial",
            })
            if missing:
                errors[key] = f"Parsed {len(valid)} of {len(expected)} required metrics; missing: " + "; ".join(metric[-1] for metric in missing)
        except Exception as exc:
            report["status"] = "failed"
            errors[key] = f"{type(exc).__name__}: {exc}"
        parser_reports[key] = report
    return values, errors, parser_reports


def _summary(ledger: pd.DataFrame) -> dict:
    def value(provider: str, metric: str):
        rows = ledger.loc[ledger["Provider"].eq(provider) & ledger["Metric"].eq(metric), "Value"]
        return float(rows.iloc[-1]) if not rows.empty and pd.notna(rows.iloc[-1]) else np.nan
    return {
        "openai_weekly_users_m": value("OpenAI","Weekly active users"),
        "openai_subscribers_m": value("OpenAI","Consumer subscribers"),
        "openai_subscriber_share_pct": value("OpenAI","Implied subscriber share"),
        "openai_arr_b": value("OpenAI","Annualized revenue run rate"),
        "microsoft_ai_arr_b": value("Microsoft","Annual revenue run rate"),
        "microsoft_ai_arr_growth_pct": value("Microsoft","Annual revenue run-rate growth"),
        "alphabet_gemini_mau_m": value("Alphabet","Monthly active users"),
        "alphabet_cloud_backlog_b": value("Alphabet","Backlog"),
        "alphabet_serving_cost_reduction_pct": value("Alphabet","Serving unit-cost reduction"),
        "providers": int(ledger["Provider"].nunique()) if not ledger.empty else 0,
        "metrics": int(len(ledger)),
        "latest_date": str(ledger["Observation Date"].dropna().max()) if not ledger.empty and ledger["Observation Date"].notna().any() else None,
    }


def _retained_only_metrics(ledger: pd.DataFrame) -> list[str]:
    refreshable = {key for contract in PARSER_CONTRACTS.values() for key in contract}
    retained = set(tuple(row[column] for column in KEY_COLUMNS) for row in ledger.to_dict(orient="records")) if not ledger.empty else set()
    return [" / ".join(map(str, key)) for key in sorted(retained - refreshable)]


@st.cache_data(ttl=86400)
def load_commercialization_data(*, force_refresh: bool = False, refresh_token: int = 0) -> dict:
    del refresh_token
    ledger = _normalize(_load_csv(LEDGER_PATH))
    manifest = _load_csv(MANIFEST_PATH)
    source_mode = "retained"
    errors: dict[str,str] = {}
    parser_reports: dict[str,dict] = {}
    updated = 0
    if force_refresh:
        values, errors, parser_reports = _refresh_values(manifest)
        if values and not ledger.empty:
            indexed = ledger.set_index(KEY_COLUMNS).sort_index()
            unknown_keys = [key for key in values if key not in indexed.index]
            if unknown_keys:
                errors["ledger_contract"] = "Parsed metrics are missing from the retained ledger: " + "; ".join(key[-1] for key in unknown_keys)
            for key, value in values.items():
                if key in indexed.index:
                    indexed.loc[key, "Value"] = value
                    indexed.loc[key, "Retrieved"] = pd.Timestamp.utcnow().date().isoformat()
                    updated += 1
            ledger = _normalize(indexed.reset_index())
            weekly = ledger.loc[(ledger["Provider"].eq("OpenAI")) & ledger["Metric"].eq("Weekly active users"), "Value"]
            paid = ledger.loc[(ledger["Provider"].eq("OpenAI")) & ledger["Metric"].eq("Consumer subscribers"), "Value"]
            ratio_mask = (ledger["Provider"].eq("OpenAI")) & ledger["Metric"].eq("Implied subscriber share")
            if not weekly.empty and not paid.empty and float(weekly.iloc[-1]) > 0:
                ledger.loc[ratio_mask, "Value"] = float(paid.iloc[-1]) / float(weekly.iloc[-1]) * 100.0
            if repository_writes_enabled():
                atomic_write_csv(ledger, LEDGER_PATH)
            source_mode = "live_refresh" if not errors and all(report.get("status") == "complete" for report in parser_reports.values()) else "partial_refresh"
        else:
            source_mode = "retained_fallback"
            if not errors:
                errors["refresh"] = "No contracted metrics were parsed; retained values remain in use."
    return {
        "source_mode": source_mode,
        "load_report": {
            "source_mode":source_mode,
            "requested":force_refresh,
            "refresh_contract":"fixed_page_validation",
            "latest_release_discovery":False,
            "updated_metrics":updated,
            "expected_refreshable_metrics":sum(len(contract) for contract in PARSER_CONTRACTS.values()),
            "retained_only_metrics":_retained_only_metrics(ledger),
            "parser_reports":parser_reports,
            "errors":errors,
        },
        "ledger": ledger,
        "source_manifest": manifest,
        "summary": _summary(ledger),
        "boundary": "Commercialization metrics are selective primary company disclosures with non-standard definitions. Refresh validates fixed retained source pages; it does not discover every provider's newest release. Reach, paid demand, revenue, backlog, capex, and margins remain separate and are not combined into a universal ROI score.",
    }
