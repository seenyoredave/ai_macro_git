"""Discover new BDC 10-Q/10-K filings and retain validated consolidated facts."""
from __future__ import annotations

from pathlib import Path
import re
import time
import numpy as np
import pandas as pd
import requests
from lxml import etree

from config.deployment import PROJECT_ROOT, repository_writes_enabled
from helpers.atomic_io import atomic_write_csv
from loaders.edgar_client import sec_headers, sec_ticker_headers, load_ticker_cik_map

HISTORY_PATH = PROJECT_ROOT / "data" / "private_credit_bdc_history.csv"
TICKERS = ("ARCC", "OBDC", "FSK", "GBDC", "CION")


def _local(tag):
    return str(tag).split("}")[-1].split(":")[-1].lower()


def parse_bdc_filing(content, *, period, ticker, source_url, filed):
    """Accept only explicit, unsegmented instant cost and nonaccrual ratios.

    Unknown concepts remain unparsed rather than guessing from adjacent tables,
    fair values, comparative columns, or scaled narrative amounts.
    """
    period_date = pd.to_datetime(period, errors="coerce")
    filed_date = pd.to_datetime(filed, errors="coerce")
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    if pd.isna(period_date) or pd.isna(filed_date) or period_date > filed_date or filed_date > today:
        raise ValueError("Invalid SEC period or filing date")
    root = etree.fromstring(content, etree.HTMLParser(recover=True))
    contexts, units = {}, {}
    for node in root.iter():
        if _local(node.tag) == "context":
            children = list(node.iter())
            if any(_local(child.tag) in {"segment", "scenario", "explicitmember", "typedmember"} for child in children):
                continue
            instants = [str(child.text).strip() for child in children if _local(child.tag) == "instant"]
            if instants == [str(period)]:
                contexts[node.get("id")] = True
        elif _local(node.tag) == "unit":
            units[node.get("id")] = " ".join(str(child.text or "") for child in node.iter() if _local(child.tag) == "measure").lower()
    candidates = {"cost": [], "nonaccrual": []}
    for node in root.iter():
        if _local(node.tag) != "nonfraction" or node.get("contextref") not in contexts:
            continue
        concept = _local(node.get("name", ""))
        unit = units.get(node.get("unitref"), "")
        text = "".join(node.itertext()).replace(",", "").replace("%", "").strip()
        if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
            continue
        value = float(text) * 10 ** int(node.get("scale", "0"))
        if node.get("sign") == "-":
            value = -value
        if concept in {"investmentsownedatcost", "investmentownedatcost", "investmentsatamortizedcost", "totalinvestmentsatamortizedcost", "investmentsatcost"} and "usd" in unit:
            candidates["cost"].append(value / 1e6)
        if ("nonaccrual" in concept and ("percentage" in concept or "percent" in concept) and ("amortizedcost" in concept or "atcost" in concept) and "fairvalue" not in concept and "debt" not in concept and "loan" not in concept and "pure" in unit):
            # XBRL pure ratios are fractions even when the rendered text is %.
            candidates["nonaccrual"].append(100 * value)
    values = {}
    for field, items in candidates.items():
        unique = {round(value, 8) for value in items if np.isfinite(value)}
        if len(unique) != 1:
            raise ValueError(f"No unambiguous consolidated {field} fact for {period}")
        values[field] = unique.pop()
    if not 0 < values["cost"] < 1e6 or not 0 <= values["nonaccrual"] <= 100:
        raise ValueError("BDC fact outside valid bounds")
    return {"Date": str(period), "Ticker": ticker, "Portfolio Cost ($mm)": values["cost"],
            "Nonaccrual at Cost (%)": values["nonaccrual"], "Source URL": source_url,
            "Filing Date": str(filed), "Retrieved At": pd.Timestamp.now(tz="UTC").isoformat(),
            "Source Type": "SEC 10-Q/10-K", "Extraction Status": "validated consolidated inline XBRL"}


def refresh_bdc_filings(*, force_refresh=False, allow_live=False, path=None):
    target = Path(path or HISTORY_PATH)
    report = {"source_mode": "retained", "errors": {}, "updated_tickers": []}
    if not (force_refresh and allow_live and repository_writes_enabled()):
        return report
    retained = pd.read_csv(target) if target.exists() else pd.DataFrame()
    history = retained.copy()
    try:
        cik_map = load_ticker_cik_map()
    except Exception as exc:
        report.update(source_mode="retained_fallback", errors={"discovery": type(exc).__name__})
        return report
    for ticker in TICKERS:
        try:
            cik = int(cik_map[ticker])
            time.sleep(0.15)
            response = requests.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=sec_headers(), timeout=20)
            response.raise_for_status()
            filings = pd.DataFrame(response.json()["filings"]["recent"])
            filings = filings[filings["form"].isin(["10-Q", "10-K"])].sort_values(["reportDate", "filingDate"], ascending=False)
            if filings.empty:
                raise ValueError("No recent 10-Q/10-K found")
            row = filings.iloc[0]
            existing = history[history["Ticker"].eq(ticker)] if not history.empty else pd.DataFrame()
            if not existing.empty and pd.to_datetime(existing["Date"]).max() >= pd.Timestamp(row["reportDate"]):
                continue
            accession = row["accessionNumber"].replace("-", "")
            document = str(row["primaryDocument"])
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", document):
                raise ValueError("Unrecognized SEC primary document name")
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
            time.sleep(0.15)
            response = requests.get(url, headers=sec_ticker_headers(), timeout=30)
            response.raise_for_status()
            parsed = parse_bdc_filing(response.content, period=row["reportDate"], ticker=ticker, source_url=url, filed=row["filingDate"])
            history = pd.concat([history, pd.DataFrame([parsed])], ignore_index=True)
            report["updated_tickers"].append(ticker)
        except Exception as exc:
            report["errors"][ticker] = f"{type(exc).__name__}: {exc}"
    if report["updated_tickers"]:
        history = history.sort_values(["Date", "Ticker"]).drop_duplicates(["Date", "Ticker"], keep="last")
        atomic_write_csv(history, target)
    report["source_mode"] = "partial_refresh" if report["errors"] else "live"
    return report
