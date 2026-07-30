from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.borrower_financial_condition_history import (
    build_company_snapshot,
    combine_borrower_financial_condition_history,
    historical_observation_dates,
    ttm_fact,
)
from tools.backfill_borrower_financial_condition import Filing, accepted_ledger, extract_commitment_candidates


def _duration(val, start, end, filed, *, form="10-Q", fp="Q1", fy=2024, frame=None):
    row = {
        "val": val,
        "start": start,
        "end": end,
        "filed": filed,
        "form": form,
        "fp": fp,
        "fy": fy,
    }
    if frame:
        row["frame"] = frame
    return row


def _instant(val, end, filed, *, form="10-Q"):
    return {"val": val, "end": end, "filed": filed, "form": form}


def _facts_payload():
    revenue = [
        _duration(100, "2024-01-01", "2024-03-31", "2024-05-01"),
        _duration(210, "2024-01-01", "2024-06-30", "2024-08-01", fp="Q2"),
        _duration(330, "2024-01-01", "2024-09-30", "2024-11-01", fp="Q3"),
        _duration(460, "2024-01-01", "2024-12-31", "2025-02-01", form="10-K", fp="FY"),
    ]
    ocf = [
        _duration(20, "2024-01-01", "2024-03-31", "2024-05-01"),
        _duration(45, "2024-01-01", "2024-06-30", "2024-08-01", fp="Q2"),
        _duration(75, "2024-01-01", "2024-09-30", "2024-11-01", fp="Q3"),
        _duration(110, "2024-01-01", "2024-12-31", "2025-02-01", form="10-K", fp="FY"),
    ]
    capex = [
        _duration(5, "2024-01-01", "2024-03-31", "2024-05-01"),
        _duration(12, "2024-01-01", "2024-06-30", "2024-08-01", fp="Q2"),
        _duration(21, "2024-01-01", "2024-09-30", "2024-11-01", fp="Q3"),
        _duration(32, "2024-01-01", "2024-12-31", "2025-02-01", form="10-K", fp="FY"),
    ]
    op_income = [
        _duration(12, "2024-01-01", "2024-03-31", "2024-05-01"),
        _duration(26, "2024-01-01", "2024-06-30", "2024-08-01", fp="Q2"),
        _duration(42, "2024-01-01", "2024-09-30", "2024-11-01", fp="Q3"),
        _duration(60, "2024-01-01", "2024-12-31", "2025-02-01", form="10-K", fp="FY"),
    ]
    da = [
        _duration(3, "2024-01-01", "2024-03-31", "2024-05-01"),
        _duration(6, "2024-01-01", "2024-06-30", "2024-08-01", fp="Q2"),
        _duration(9, "2024-01-01", "2024-09-30", "2024-11-01", fp="Q3"),
        _duration(12, "2024-01-01", "2024-12-31", "2025-02-01", form="10-K", fp="FY"),
    ]
    return {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": revenue}},
                "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": ocf}},
                "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": capex}},
                "OperatingIncomeLoss": {"units": {"USD": op_income}},
                "DepreciationDepletionAndAmortization": {"units": {"USD": da}},
                "LongTermDebtCurrent": {"units": {"USD": [_instant(10, "2024-12-31", "2025-02-01", form="10-K")]}},
                "LongTermDebtNoncurrent": {"units": {"USD": [_instant(40, "2024-12-31", "2025-02-01", form="10-K")]}},
                "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": [_instant(30, "2024-12-31", "2025-02-01", form="10-K")]}},
                "ShortTermInvestments": {"units": {"USD": [_instant(5, "2024-12-31", "2025-02-01", form="10-K")]}},
            }
        }
    }


def test_observation_schedule_has_annual_and_quarterly_bridge():
    dates = historical_observation_dates()
    assert dates[0] == (pd.Timestamp("2014-12-31"), "Historical Annual")
    assert (pd.Timestamp("2024-12-31"), "Historical Annual") in dates
    assert (pd.Timestamp("2025-03-31"), "Quarterly Bridge") in dates
    assert dates[-1] == (pd.Timestamp("2026-06-13"), "Quarterly Bridge")


def test_ttm_fact_derives_discrete_quarters_from_ytd_facts():
    fact = ttm_fact(
        _facts_payload(),
        ("RevenueFromContractWithCustomerExcludingAssessedTax",),
        "2025-03-01",
    )
    assert fact.value == 460
    assert fact.quarters == 4
    assert fact.method == "Trailing four fiscal quarters"


def test_company_snapshot_builds_fcf_ebitda_and_net_debt():
    row = build_company_snapshot("MSFT", _facts_payload(), "2025-03-01", "Quarterly Bridge")
    assert row["Revenue"] == 460
    assert row["Operating Cash Flow"] == 110
    assert row["CapEx"] == 32
    assert row["Free Cash Flow"] == 78
    assert row["EBITDA"] == 72
    assert row["Total Debt"] == 50
    assert row["Cash"] == 35
    assert row["Net Debt"] == 15


def test_commitment_extractor_accepts_explicit_total_table():
    filing = Filing(
        ticker="TEST",
        cik="0000000001",
        accession="0000000001-25-000001",
        filing_date=pd.Timestamp("2025-02-15"),
        report_date=pd.Timestamp("2024-12-31"),
        form="10-K",
        primary_document="test.htm",
    )
    html = """
    <html><body><p>Contractual commitments (in millions)</p>
      <table>
        <tr><th>Obligation</th><th>Total</th><th>Less than one year</th></tr>
        <tr><td>Purchase commitments</td><td>$ 2,500</td><td>$ 500</td></tr>
      </table>
    </body></html>
    """
    candidates = extract_commitment_candidates(filing, html)
    assert len(candidates) == 1
    assert candidates[0]["Category"] == "Purchase or Contractual Commitments"
    assert candidates[0]["Amount"] == 2_500_000_000
    assert candidates[0]["Accepted"] is True

    ledger = accepted_ledger(pd.DataFrame(candidates))
    assert ledger.iloc[0]["Purchase or Contractual Commitments"] == 2_500_000_000


def test_combine_history_prefers_live_row_on_duplicate_date():
    backfill = pd.DataFrame(
        {
            "Date": ["2026-06-13"],
            "Borrower Financial Condition": [10.0],
            "Borrower Financial Condition Version": ["3.0"],
        }
    )
    live = pd.DataFrame(
        {
            "Date": ["2026-06-13"],
            "Borrower Financial Condition": [12.0],
            "Borrower Financial Condition Version": ["3.0"],
        }
    )
    result = combine_borrower_financial_condition_history(live, backfill)
    assert len(result) == 1
    assert result.iloc[0]["Borrower Financial Condition"] == 12.0


def test_backfill_history_constitutes_with_three_components():
    from tools.backfill_borrower_financial_condition import build_history

    fundamentals = pd.DataFrame(
        [
            {
                "Date": "2024-12-31",
                "Observation Frequency": "Historical Annual",
                "Ticker": "MSFT",
                "Revenue": 1000.0,
                "Operating Cash Flow": 300.0,
                "CapEx": 100.0,
                "Free Cash Flow": 200.0,
                "EBITDA": 250.0,
                "Total Debt": 100.0,
                "Cash": 200.0,
                "Net Debt": -100.0,
                "Financial Filing Date": "2024-10-01",
            },
            {
                "Date": "2024-12-31",
                "Observation Frequency": "Historical Annual",
                "Ticker": "AMZN",
                "Revenue": 1200.0,
                "Operating Cash Flow": 250.0,
                "CapEx": 120.0,
                "Free Cash Flow": 130.0,
                "EBITDA": 200.0,
                "Total Debt": 180.0,
                "Cash": 100.0,
                "Net Debt": 80.0,
                "Financial Filing Date": "2024-11-01",
            },
        ]
    )
    ledger = pd.DataFrame(
        [
            {
                "Ticker": "MSFT",
                "As Of Date": "2024-06-30",
                "Filing Date": "2024-07-30",
                "Uncommenced Leases": np.nan,
                "Purchase or Contractual Commitments": 300.0,
                "Contingent Exposure": np.nan,
                "Source URL": "https://example.com/msft",
                "Notes": "fixture",
                "Extraction Confidence": "High",
                "Extraction Status": "fixture",
            },
            {
                "Ticker": "AMZN",
                "As Of Date": "2024-09-30",
                "Filing Date": "2024-10-31",
                "Uncommenced Leases": np.nan,
                "Purchase or Contractual Commitments": 400.0,
                "Contingent Exposure": np.nan,
                "Source URL": "https://example.com/amzn",
                "Notes": "fixture",
                "Extraction Confidence": "High",
                "Extraction Status": "fixture",
            },
        ]
    )
    history = build_history(
        fundamentals,
        ledger,
        [(pd.Timestamp("2024-12-31"), "Historical Annual")],
    )
    assert len(history) == 1
    assert history.iloc[0]["Valid Components"] == 3
    assert pd.notna(history.iloc[0]["Borrower Financial Condition"])
    assert history.iloc[0]["Backfill Status"] == "Accepted"
