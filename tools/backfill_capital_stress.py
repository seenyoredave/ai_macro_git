#!/usr/bin/env python3
"""Build the retained Capital Stress history from public SEC filings.

This is an offline maintenance command, not part of Streamlit runtime.  It:

1. downloads/caches SEC CompanyFacts and filing metadata;
2. reconstructs point-in-time TTM fundamentals at annual and quarterly dates;
3. conservatively extracts commitment candidates from 10-K/10-Q filings;
4. accepts only high-confidence, explicitly labeled obligations;
5. calculates Capital Stress with the live v3 engine; and
6. writes retained raw inputs, an audit table, and the dashboard history file.

Run from the project root:

    python tools/backfill_capital_stress.py

The command resumes from ``.cache/capital_stress_backfill``.  Set
``SEC_USER_AGENT`` or place ``SEC_USER_AGENT`` in
``~/.streamlit/secrets.toml`` before running.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import tomllib
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analytics.capital_stress_engine import calculate_capital_stress
from analytics.capital_stress_history import (
    CAPITAL_STRESS_CIKS,
    DEFAULT_AUDIT_PATH,
    DEFAULT_COMMITMENTS_HISTORY_PATH,
    DEFAULT_FUNDAMENTALS_PATH,
    DEFAULT_HISTORY_PATH,
    DEFAULT_REVIEW_PATH,
    FUNDAMENTAL_COLUMNS,
    HISTORY_COLUMNS,
    LEDGER_COLUMNS,
    REVIEW_COLUMNS,
    build_company_snapshot,
    capital_result_to_history_row,
    historical_observation_dates,
    snapshot_to_sector_data,
)


CACHE_DIR = PROJECT_ROOT / ".cache" / "capital_stress_backfill"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_SUBMISSIONS_FILE = "https://data.sec.gov/submissions/{name}"
SEC_COMPANYFACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_FILING = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession}/{document}"

FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A"}
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}

PURCHASE_PATTERN = re.compile(
    r"(?:purchase|procurement|supply|supplier|manufactur|wafer|component|inventory|"
    r"cloud service|capacity|construction).{0,55}(?:commitment|obligation|agreement|order)",
    re.I,
)
LEASE_PATTERN = re.compile(
    r"(?:lease|leases).{0,40}(?:not yet commenced|not commenced|uncommenced)", re.I
)
CONTINGENT_PATTERN = re.compile(
    r"(?:guarantee|guaranty|maximum potential (?:amount|payments?)|letter[s]? of credit|"
    r"contingent obligation)",
    re.I,
)
EXCLUSION_PATTERN = re.compile(
    r"(?:total contractual obligations|long[- ]term debt|finance lease|operating lease obligations|"
    r"interest payments?|debt obligations?)",
    re.I,
)
AMOUNT_PATTERN = re.compile(
    r"\$?\s*\(?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*\)?\s*(billion|million|thousand|bn|mm|m|k)?",
    re.I,
)


@dataclass(frozen=True)
class Filing:
    ticker: str
    cik: str
    accession: str
    filing_date: pd.Timestamp
    report_date: pd.Timestamp | pd.NaT
    form: str
    primary_document: str

    @property
    def url(self) -> str:
        return SEC_FILING.format(
            cik_int=int(self.cik),
            accession=self.accession.replace("-", ""),
            document=self.primary_document,
        )


class SecClient:
    def __init__(self, user_agent: str, cache_dir: Path, *, offline: bool = False):
        self.user_agent = user_agent
        self.cache_dir = cache_dir
        self.offline = offline
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "application/json,text/html,application/xhtml+xml",
            }
        )
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_request = 0.0

    def _cache_path(self, url: str, suffix: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}{suffix}"

    def _request(self, url: str, suffix: str, *, binary: bool = False):
        path = self._cache_path(url, suffix)
        if path.exists() and path.stat().st_size > 0:
            return path.read_bytes() if binary else path.read_text(encoding="utf-8")
        if self.offline:
            raise FileNotFoundError(f"Offline cache miss: {url}")

        elapsed = time.monotonic() - self._last_request
        if elapsed < 0.12:
            time.sleep(0.12 - elapsed)
        response = None
        for attempt in range(5):
            response = self.session.get(url, timeout=60)
            self._last_request = time.monotonic()
            if response.status_code not in {429, 500, 502, 503, 504}:
                break
            time.sleep(min(2 ** attempt, 16))
        assert response is not None
        response.raise_for_status()
        if binary:
            path.write_bytes(response.content)
            return response.content
        path.write_text(response.text, encoding="utf-8")
        return response.text

    def json(self, url: str) -> Mapping:
        return json.loads(self._request(url, ".json"))

    def html(self, url: str) -> str:
        return self._request(url, ".html")


def _optional_toml_secret(path: Path, name: str):
    try:
        if not path.exists():
            return None
        with path.open("rb") as handle:
            return (tomllib.load(handle) or {}).get(name)
    except Exception:
        return None


def sec_user_agent() -> str:
    candidates = [
        os.getenv("SEC_USER_AGENT"),
        _optional_toml_secret(Path.home() / ".streamlit" / "secrets.toml", "SEC_USER_AGENT"),
        _optional_toml_secret(PROJECT_ROOT / ".streamlit" / "secrets.toml", "SEC_USER_AGENT"),
    ]
    value = next((str(item).strip() for item in candidates if item and str(item).strip()), "")
    if not value or "@" not in value:
        raise SystemExit(
            "SEC_USER_AGENT is required and should identify a name/app plus contact email. "
            "Set it in the environment or ~/.streamlit/secrets.toml."
        )
    return value


def _columnar_rows(payload: Mapping) -> list[dict]:
    if not payload:
        return []
    keys = list(payload.keys())
    lengths = [len(payload.get(key) or []) for key in keys]
    if not lengths:
        return []
    size = max(lengths)
    rows = []
    for index in range(size):
        row = {}
        for key in keys:
            values = payload.get(key) or []
            row[key] = values[index] if index < len(values) else None
        rows.append(row)
    return rows


def load_filings(client: SecClient, ticker: str, cik: str) -> list[Filing]:
    root = client.json(SEC_SUBMISSIONS.format(cik=cik))
    rows = _columnar_rows(((root.get("filings") or {}).get("recent") or {}))
    for item in ((root.get("filings") or {}).get("files") or []):
        name = item.get("name")
        if not name:
            continue
        payload = client.json(SEC_SUBMISSIONS_FILE.format(name=name))
        historical = ((payload.get("filings") or {}).get("recent") or payload)
        rows.extend(_columnar_rows(historical))

    filings: list[Filing] = []
    for row in rows:
        form = str(row.get("form") or "").strip()
        accession = str(row.get("accessionNumber") or "").strip()
        primary = str(row.get("primaryDocument") or "").strip()
        filing_date = pd.to_datetime(row.get("filingDate"), errors="coerce")
        report_date = pd.to_datetime(row.get("reportDate"), errors="coerce")
        if form not in FORMS or not accession or not primary or pd.isna(filing_date):
            continue
        filings.append(
            Filing(
                ticker=ticker,
                cik=cik,
                accession=accession,
                filing_date=filing_date.normalize(),
                report_date=report_date.normalize() if pd.notna(report_date) else pd.NaT,
                form=form,
                primary_document=primary,
            )
        )
    unique = {(f.accession, f.primary_document): f for f in filings}
    return sorted(unique.values(), key=lambda filing: filing.filing_date)


def select_relevant_filings(
    filings: Iterable[Filing],
    observations: list[tuple[pd.Timestamp, str]],
) -> list[Filing]:
    """Select latest annual filings for annual points and all bridge updates."""
    filings = sorted(filings, key=lambda filing: filing.filing_date)
    selected: dict[tuple[str, str], Filing] = {}
    for cutoff, frequency in observations:
        eligible = [filing for filing in filings if filing.filing_date <= cutoff]
        if not eligible:
            continue
        if frequency == "Historical Annual":
            annual = [filing for filing in eligible if filing.form in ANNUAL_FORMS]
            chosen = annual[-1:] if annual else []
        else:
            # Quarterly bridge uses the latest filing available by each cutoff.
            chosen = eligible[-1:]
        for filing in chosen:
            selected[(filing.accession, filing.primary_document)] = filing
    return sorted(selected.values(), key=lambda filing: filing.filing_date)


def _normalize_space(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _unit_multiplier(context: str) -> float:
    text = context.lower()
    if re.search(r"\b(in|amounts in)\s+billions\b", text):
        return 1e9
    if re.search(r"\b(in|amounts in)\s+millions\b", text):
        return 1e6
    if re.search(r"\b(in|amounts in)\s+thousands\b", text):
        return 1e3
    return 1.0


def _parse_amount(cell: str, context: str = "") -> float:
    text = _normalize_space(cell)
    if not text or text in {"—", "–", "-", "--", "N/A", "n/a"}:
        return np.nan
    # Remove common footnote markers while retaining decimal points and signs.
    cleaned = re.sub(r"\[[0-9a-z]+\]|\([a-z]\)|\*", "", text, flags=re.I)
    matches = list(AMOUNT_PATTERN.finditer(cleaned))
    if not matches:
        return np.nan
    match = matches[-1]
    try:
        number = float(match.group(1).replace(",", ""))
    except Exception:
        return np.nan
    suffix = (match.group(2) or "").lower()
    multiplier = {
        "billion": 1e9,
        "bn": 1e9,
        "million": 1e6,
        "mm": 1e6,
        "m": 1e6,
        "thousand": 1e3,
        "k": 1e3,
    }.get(suffix, _unit_multiplier(context))
    return number * multiplier


def _classify_label(label: str) -> str | None:
    normalized = _normalize_space(label)
    if LEASE_PATTERN.search(normalized):
        return "Uncommenced Leases"
    if CONTINGENT_PATTERN.search(normalized) and not re.search(r"lease", normalized, re.I):
        return "Contingent Exposure"
    if PURCHASE_PATTERN.search(normalized) and not EXCLUSION_PATTERN.search(normalized):
        return "Purchase or Contractual Commitments"
    return None


def _preceding_context(table) -> str:
    chunks = []
    cursor = table
    for _ in range(5):
        cursor = cursor.find_previous()
        if cursor is None:
            break
        if getattr(cursor, "name", None) in {"p", "div", "span", "strong", "b", "h3", "h4"}:
            text = _normalize_space(cursor.get_text(" ", strip=True))
            if text:
                chunks.append(text)
        if sum(len(chunk) for chunk in chunks) > 800:
            break
    return " ".join(reversed(chunks[-5:]))


def extract_table_candidates(filing: Filing, html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    candidates: list[dict] = []
    for table in soup.find_all("table"):
        parsed_rows = []
        for tr in table.find_all("tr"):
            cell_nodes = tr.find_all(["th", "td"])
            cells = [_normalize_space(cell.get_text(" ", strip=True)) for cell in cell_nodes]
            if cells:
                parsed_rows.append((cells, any(cell.name == "th" for cell in cell_nodes)))
        if not parsed_rows:
            continue
        context = _preceding_context(table)
        header_rows = [cells for cells, is_header in parsed_rows if is_header][:4]
        if not header_rows:
            header_rows = [parsed_rows[0][0]]
        max_columns = max(len(row) for row in header_rows)
        headers = [""] * max_columns
        for row in header_rows:
            for index, cell in enumerate(row):
                if cell:
                    headers[index] = f"{headers[index]} {cell}".strip()
        total_indexes = [index for index, value in enumerate(headers) if re.search(r"\btotal\b", value, re.I)]

        for cells, _ in parsed_rows:
            label = cells[0] if cells else ""
            category = _classify_label(label)
            if not category:
                continue
            amount = np.nan
            method = "Table row"
            confidence = "Medium"
            if total_indexes:
                for index in total_indexes:
                    if index < len(cells):
                        amount = _parse_amount(cells[index], f"{context} {' '.join(headers)}")
                        if pd.notna(amount):
                            confidence = "High"
                            method = "Explicit total column"
                            break
            if pd.isna(amount):
                numeric = [
                    _parse_amount(cell, f"{context} {' '.join(headers)}")
                    for cell in cells[1:]
                ]
                numeric = [value for value in numeric if pd.notna(value)]
                if len(numeric) == 1:
                    amount = numeric[0]
                    confidence = "High"
                    method = "Single explicit amount"
                elif numeric:
                    amount = numeric[0]
                    confidence = "Medium"
                    method = "First table amount; review required"
            if pd.isna(amount) or amount <= 0:
                continue
            candidates.append(
                {
                    "Ticker": filing.ticker,
                    "As Of Date": filing.report_date.date().isoformat() if pd.notna(filing.report_date) else filing.filing_date.date().isoformat(),
                    "Filing Date": filing.filing_date.date().isoformat(),
                    "Form": filing.form,
                    "Category": category,
                    "Amount": float(amount),
                    "Confidence": confidence,
                    "Accepted": confidence == "High",
                    "Source URL": filing.url,
                    "Label": label[:300],
                    "Excerpt": _normalize_space(f"{context} | {' | '.join(cells)}")[:1200],
                    "Method": method,
                }
            )
    return candidates


def _sentences(text: str) -> list[str]:
    cleaned = _normalize_space(text)
    return [item.strip() for item in re.split(r"(?<=[.;])\s+", cleaned) if item.strip()]


def extract_narrative_candidates(filing: Filing, html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "table"]):
        tag.decompose()
    candidates = []
    for sentence in _sentences(soup.get_text(" ", strip=True)):
        category = _classify_label(sentence)
        if not category or len(sentence) > 1600:
            continue
        explicit = re.findall(
            r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(billion|million|thousand|bn|mm)\b",
            sentence,
            re.I,
        )
        if len(explicit) != 1:
            continue
        number, suffix = explicit[0]
        amount = _parse_amount(f"${number} {suffix}")
        if pd.isna(amount) or amount <= 0:
            continue
        # Narrative extraction is accepted only when the category language and
        # one explicit currency amount occur in the same sentence.
        candidates.append(
            {
                "Ticker": filing.ticker,
                "As Of Date": filing.report_date.date().isoformat() if pd.notna(filing.report_date) else filing.filing_date.date().isoformat(),
                "Filing Date": filing.filing_date.date().isoformat(),
                "Form": filing.form,
                "Category": category,
                "Amount": float(amount),
                "Confidence": "High",
                "Accepted": True,
                "Source URL": filing.url,
                "Label": sentence[:300],
                "Excerpt": sentence[:1200],
                "Method": "Explicit narrative amount",
            }
        )
    return candidates


def extract_commitment_candidates(filing: Filing, html: str) -> list[dict]:
    candidates = extract_table_candidates(filing, html)
    candidates.extend(extract_narrative_candidates(filing, html))
    if not candidates:
        return []
    frame = pd.DataFrame(candidates)
    frame["_rounded"] = (pd.to_numeric(frame["Amount"], errors="coerce") / 1e6).round(0)
    frame["_label_key"] = frame["Label"].astype(str).str.lower().str.replace(r"\W+", " ", regex=True).str.strip()
    frame = frame.sort_values(["Confidence", "Method"], ascending=[True, True], kind="stable")
    frame = frame.drop_duplicates(["Category", "_rounded", "_label_key"], keep="last")
    return frame.drop(columns=["_rounded", "_label_key"]).to_dict("records")


def accepted_ledger(review: pd.DataFrame) -> pd.DataFrame:
    if review is None or review.empty:
        return pd.DataFrame(columns=LEDGER_COLUMNS)
    accepted_flag = review["Accepted"].map(
        lambda value: value if isinstance(value, bool) else str(value).strip().lower() in {"1", "true", "yes", "y"}
    )
    accepted = review.loc[
        accepted_flag
        & pd.to_numeric(review["Amount"], errors="coerce").gt(0)
    ].copy()
    if accepted.empty:
        return pd.DataFrame(columns=LEDGER_COLUMNS)

    rows = []
    group_cols = ["Ticker", "As Of Date", "Filing Date", "Source URL"]
    for keys, group in accepted.groupby(group_cols, dropna=False):
        values = {}
        notes = []
        for category, category_rows in group.groupby("Category", dropna=False):
            category_rows = category_rows.copy()
            labels = category_rows["Label"].astype(str)
            generic_total = labels.str.contains(r"\btotal\b", case=False, regex=True)
            generic_values = pd.to_numeric(category_rows.loc[generic_total, "Amount"], errors="coerce").dropna()
            specific = category_rows.loc[~generic_total].copy()
            specific = specific.drop_duplicates("Label")
            specific_sum = pd.to_numeric(specific["Amount"], errors="coerce").dropna().sum()
            candidates = [float(specific_sum)] if specific_sum > 0 else []
            if not generic_values.empty:
                candidates.append(float(generic_values.max()))
            values[str(category)] = max(candidates) if candidates else np.nan
            notes.extend(category_rows["Excerpt"].astype(str).head(4).tolist())
        ticker, as_of, filing_date, source_url = keys
        all_high = group["Confidence"].astype(str).eq("High").all()
        rows.append(
            {
                "Ticker": ticker,
                "As Of Date": as_of,
                "Filing Date": filing_date,
                "Uncommenced Leases": values.get("Uncommenced Leases", np.nan),
                "Purchase or Contractual Commitments": values.get("Purchase or Contractual Commitments", np.nan),
                "Contingent Exposure": values.get("Contingent Exposure", np.nan),
                "Source URL": source_url,
                "Notes": " || ".join(notes)[:4000],
                "Extraction Confidence": "High" if all_high else "Manual approval",
                "Extraction Status": (
                    "Auto-accepted; filing review recommended"
                    if all_high
                    else "Manually accepted from review ledger"
                ),
            }
        )
    return pd.DataFrame(rows, columns=LEDGER_COLUMNS).sort_values(
        ["Ticker", "Filing Date"], kind="stable"
    )


def _atomic_csv(frame: pd.DataFrame, path: Path, columns: list[str] | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    output = frame.copy()
    if columns:
        for column in columns:
            if column not in output.columns:
                output[column] = np.nan
        output = output.reindex(columns=columns)
    temp = path.with_suffix(path.suffix + ".tmp")
    output.to_csv(temp, index=False)
    pd.read_csv(temp)
    temp.replace(path)


def build_fundamentals(
    client: SecClient,
    observations: list[tuple[pd.Timestamp, str]],
) -> pd.DataFrame:
    rows = []
    for ticker, cik in CAPITAL_STRESS_CIKS.items():
        print(f"[companyfacts] {ticker}")
        companyfacts = client.json(SEC_COMPANYFACTS.format(cik=cik))
        for cutoff, frequency in observations:
            rows.append(build_company_snapshot(ticker, companyfacts, cutoff, frequency))
    return pd.DataFrame(rows, columns=FUNDAMENTAL_COLUMNS)


def build_commitments(
    client: SecClient,
    observations: list[tuple[pd.Timestamp, str]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    candidates = []
    for ticker, cik in CAPITAL_STRESS_CIKS.items():
        print(f"[filings] {ticker}")
        filings = load_filings(client, ticker, cik)
        relevant = select_relevant_filings(filings, observations)
        for filing in relevant:
            try:
                html = client.html(filing.url)
                extracted = extract_commitment_candidates(filing, html)
                candidates.extend(extracted)
                print(
                    f"  {filing.filing_date.date()} {filing.form}: "
                    f"{len(extracted)} candidate(s)"
                )
            except Exception as exc:
                print(f"  WARNING {filing.url}: {exc}")
    review = pd.DataFrame(candidates, columns=REVIEW_COLUMNS)
    ledger = accepted_ledger(review)
    return review, ledger


def build_history(
    fundamentals: pd.DataFrame,
    ledger: pd.DataFrame,
    observations: list[tuple[pd.Timestamp, str]],
) -> pd.DataFrame:
    rows = []
    for cutoff, frequency in observations:
        date_text = cutoff.date().isoformat()
        snapshot = fundamentals.loc[fundamentals["Date"].astype(str) == date_text].copy()
        # Companies with no usable financial inputs stay visible in the retained
        # raw file but are excluded from the calculation frame.
        usable = snapshot.loc[
            snapshot[["Revenue", "Operating Cash Flow", "CapEx", "EBITDA", "Net Debt"]]
            .notna()
            .any(axis=1)
        ].copy()
        sector_data = snapshot_to_sector_data(usable)
        result = calculate_capital_stress(
            sector_data,
            as_of_date=cutoff,
            commitments_df=ledger,
        )
        ledger_snapshot = ledger.copy()
        if not ledger_snapshot.empty:
            ledger_snapshot["Filing Date"] = pd.to_datetime(
                ledger_snapshot["Filing Date"], errors="coerce"
            )
            ledger_snapshot = ledger_snapshot.loc[
                ledger_snapshot["Filing Date"].notna()
                & (ledger_snapshot["Filing Date"] <= cutoff)
            ].copy()
            ledger_snapshot = (
                ledger_snapshot.sort_values(["Ticker", "As Of Date", "Filing Date"], kind="stable")
                .groupby("Ticker", as_index=False, dropna=False)
                .tail(1)
            )
        rows.append(
            capital_result_to_history_row(
                cutoff,
                frequency,
                result,
                usable,
                ledger_snapshot,
            )
        )
        print(
            f"[score] {date_text}: {result.get('score')} "
            f"({result.get('valid_components', 0)}/4 components)"
        )
    return pd.DataFrame(rows, columns=HISTORY_COLUMNS)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annual-start", type=int, default=2014)
    parser.add_argument("--annual-end", type=int, default=2024)
    parser.add_argument("--quarterly-start", default="2025-03-31")
    parser.add_argument("--end-date", default="2026-06-13")
    parser.add_argument("--offline", action="store_true", help="Use SEC cache only")
    parser.add_argument(
        "--reuse-raw",
        action="store_true",
        help="Rebuild scores from retained fundamentals/ledger without downloading",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    observations = historical_observation_dates(
        annual_start=args.annual_start,
        annual_end=args.annual_end,
        quarterly_start=args.quarterly_start,
        end_date=args.end_date,
    )

    if args.reuse_raw:
        fundamentals = (
            pd.read_csv(DEFAULT_FUNDAMENTALS_PATH)
            if DEFAULT_FUNDAMENTALS_PATH.exists()
            and DEFAULT_FUNDAMENTALS_PATH.stat().st_size > 0
            else pd.DataFrame(columns=FUNDAMENTAL_COLUMNS)
        )
        if fundamentals.empty:
            print("[restore] Fundamentals file is missing or empty; rebuilding from SEC cache")
            cached_client = SecClient(sec_user_agent(), CACHE_DIR, offline=True)
            fundamentals = build_fundamentals(cached_client, observations)
            if fundamentals.empty:
                raise RuntimeError(
                    "Capital Stress fundamentals could not be restored from the local SEC cache. "
                    "Run the backfill once without --reuse-raw to repopulate the cache."
                )
            _atomic_csv(fundamentals, DEFAULT_FUNDAMENTALS_PATH, FUNDAMENTAL_COLUMNS)

        review = (
            pd.read_csv(DEFAULT_REVIEW_PATH)
            if DEFAULT_REVIEW_PATH.exists()
            and DEFAULT_REVIEW_PATH.stat().st_size > 0
            else pd.DataFrame(columns=REVIEW_COLUMNS)
        )
        if not review.empty:
            ledger = accepted_ledger(review)
        elif (
            DEFAULT_COMMITMENTS_HISTORY_PATH.exists()
            and DEFAULT_COMMITMENTS_HISTORY_PATH.stat().st_size > 0
        ):
            ledger = pd.read_csv(DEFAULT_COMMITMENTS_HISTORY_PATH)
        else:
            raise RuntimeError(
                "No adjudicated commitment review or retained commitment history is available."
            )
        _atomic_csv(ledger, DEFAULT_COMMITMENTS_HISTORY_PATH, LEDGER_COLUMNS)
    else:
        client = SecClient(sec_user_agent(), CACHE_DIR, offline=args.offline)
        fundamentals = build_fundamentals(client, observations)

        retained_review = (
            pd.read_csv(DEFAULT_REVIEW_PATH)
            if DEFAULT_REVIEW_PATH.exists()
            and DEFAULT_REVIEW_PATH.stat().st_size > 0
            else pd.DataFrame(columns=REVIEW_COLUMNS)
        )
        adjudicated = (
            not retained_review.empty
            and {"Review Status", "Review Reason"}.issubset(retained_review.columns)
        )
        if adjudicated:
            print("[review] Reusing retained adjudicated commitment decisions")
            review = retained_review
            ledger = accepted_ledger(review)
        else:
            review, ledger = build_commitments(client, observations)

        _atomic_csv(fundamentals, DEFAULT_FUNDAMENTALS_PATH, FUNDAMENTAL_COLUMNS)
        _atomic_csv(review, DEFAULT_REVIEW_PATH, list(review.columns))
        _atomic_csv(ledger, DEFAULT_COMMITMENTS_HISTORY_PATH, LEDGER_COLUMNS)

    history = build_history(fundamentals, ledger, observations)
    _atomic_csv(history, DEFAULT_HISTORY_PATH, HISTORY_COLUMNS)
    _atomic_csv(history, DEFAULT_AUDIT_PATH, HISTORY_COLUMNS)

    accepted = int(history["Capital Stress"].notna().sum()) if not history.empty else 0
    print("\nCapital Stress backfill complete")
    print(f"  Observations requested: {len(observations)}")
    print(f"  Accepted scores:       {accepted}")
    print(f"  Fundamentals rows:     {len(fundamentals)}")
    print(f"  Commitment candidates: {len(review)}")
    print(f"  Accepted ledger rows:  {len(ledger)}")
    print(f"  History:               {DEFAULT_HISTORY_PATH}")
    print(f"  Audit:                 {DEFAULT_AUDIT_PATH}")
    if accepted < len(observations):
        print(
            "\nSome dates remain unconstituted. Review capital_commitments_review.csv, "
            "correct or approve filing-derived values, then rerun with --reuse-raw."
        )


if __name__ == "__main__":
    main()
