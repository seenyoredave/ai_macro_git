from __future__ import annotations

from pathlib import Path
import tempfile
import sys
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import types

class _FakeCache:
    def __call__(self, *args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda function: function

class _FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = {}
        self.secrets = {}
        self.cache_data = _FakeCache()
        self.cache_resource = _FakeCache()

sys.modules.setdefault("streamlit", _FakeStreamlit())

from loaders import borrower_finance_refresh as refresh
from analytics.deployment_funding_mix import _matched_debt_pulse, calculate_deployment_funding_mix


def _snapshot(ticker: str, *, current: bool) -> dict:
    if current:
        period, filed, debt, capex = "2026-06-30", "2026-07-30", 120.0, 40.0
    else:
        period, filed, debt, capex = "2025-06-30", "2025-07-30", 100.0, 30.0
    return {
        "Date": "2026-08-09" if current else "2025-08-09",
        "Observation Frequency": "test",
        "Ticker": ticker,
        "Revenue": 1000.0,
        "Operating Cash Flow": 100.0,
        "CapEx": capex,
        "Free Cash Flow": 60.0,
        "EBITDA": 150.0,
        "Total Debt": debt,
        "Cash": 20.0,
        "Net Debt": debt - 20.0,
        "Financial Period End": period,
        "Financial Filing Date": filed,
        "OCF Period End": period,
        "CapEx Period End": period,
        "Debt Period End": period,
        "Cash Period End": period,
        "Debt Definition": "LongTermDebtCurrent;LongTermDebtNoncurrent",
        "Cash Definition": "CashAndCashEquivalentsAtCarryingValue",
        "Flow Method": "Trailing four fiscal quarters",
        "Revenue Quarters": 4,
        "OCF Quarters": 4,
        "CapEx Quarters": 4,
        "EBITDA Quarters": 4,
        "Source URL": f"https://data.sec.gov/{ticker}",
    }


def main() -> None:
    original_paths = refresh.FUNDAMENTALS_PATH, refresh.DEBT_OBSERVATIONS_PATH
    original_fetch = refresh.fetch_company_facts
    original_build = refresh.build_company_snapshot
    original_match = refresh._matched_debt_pair
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            refresh.FUNDAMENTALS_PATH = tmp / "fundamentals.csv"
            refresh.DEBT_OBSERVATIONS_PATH = tmp / "debt.csv"
            pd.DataFrame(columns=refresh.FUNDAMENTAL_COLUMNS).to_csv(refresh.FUNDAMENTALS_PATH, index=False)
            debt_seed = []
            for ticker in refresh.BORROWER_STRAIN_CIKS:
                if ticker in {"IREN", "ANET"}:
                    continue
                debt_seed.extend([
                    {"Ticker": ticker, "Period End": "2025-06-30", "Filing Date": "2025-07-30", "Debt": 100.0,
                     "Definition": f"retained {ticker}", "Source URL": "retained", "Evidence Note": "filing reviewed"},
                    {"Ticker": ticker, "Period End": "2026-06-30", "Filing Date": "2026-07-30", "Debt": 120.0,
                     "Definition": f"retained {ticker}", "Source URL": "retained", "Evidence Note": "filing reviewed"},
                ])
            pd.DataFrame(debt_seed).to_csv(refresh.DEBT_OBSERVATIONS_PATH, index=False)

            seen_tokens = []
            refresh.fetch_company_facts = lambda cik, refresh_token=0: seen_tokens.append(refresh_token) or {"cik": cik}
            def fake_build(ticker, facts, cutoff, frequency):
                return _snapshot(ticker, current=pd.Timestamp(cutoff).year == 2026)
            refresh.build_company_snapshot = fake_build

            def fake_match(*, ticker, debt_definition, **kwargs):
                if ticker == "SMCI":
                    return None, None, "issuer debt requires filing-reviewed components"
                current_fact = types.SimpleNamespace(value=120.0, period_end=pd.Timestamp("2026-06-30"), filed=pd.Timestamp("2026-07-30"), tags=("LongTermDebtCurrent", "LongTermDebtNoncurrent"))
                prior_fact = types.SimpleNamespace(value=100.0, period_end=pd.Timestamp("2025-06-30"), filed=pd.Timestamp("2025-07-30"), tags=("LongTermDebtCurrent", "LongTermDebtNoncurrent"))
                source = f"https://data.sec.gov/{ticker}"
                return (
                    refresh._debt_fact_row(ticker=ticker, fact=current_fact, debt_definition=debt_definition, source_url=source),
                    refresh._debt_fact_row(ticker=ticker, fact=prior_fact, debt_definition=debt_definition, source_url=source),
                    None,
                )
            refresh._matched_debt_pair = fake_match

            report = refresh.refresh_borrower_finance_derivatives(
                refresh_token=17, observation_date="2026-08-09"
            )
            if report.get("status") != "written" or report.get("fundamental_companies") != 10:
                raise AssertionError(report)
            if report.get("debt_companies") != 8:
                raise AssertionError(f"Definition-matched debt cohort changed: {report}")
            if report.get("debt_updated_tickers") != sorted(set(refresh.BORROWER_STRAIN_CIKS) - {"IREN", "ANET", "SMCI"}):
                raise AssertionError(f"Automatic debt diagnostics changed: {report}")
            if report.get("debt_reviewed_tickers") != ["SMCI"]:
                raise AssertionError(f"Reviewed fallback was not surfaced: {report}")
            if set(seen_tokens) != {17}:
                raise AssertionError(f"Refresh token did not reach Companyfacts cache key: {seen_tokens}")

            fundamentals = pd.read_csv(refresh.FUNDAMENTALS_PATH)
            current = fundamentals.loc[fundamentals["Date"].astype(str).eq("2026-08-09")]
            if current["Ticker"].nunique() != 10:
                raise AssertionError("Current 10-company fundamentals cohort was not persisted")
            matched_current = current.loc[~current["Ticker"].isin(["IREN", "ANET"])]
            if not matched_current["Total Debt"].eq(120.0).all():
                raise AssertionError("Generic Companyfacts debt was not reconciled to matched debt")
            if not matched_current["Debt Definition"].astype(str).str.startswith("retained " ).all():
                raise AssertionError("Matched debt definition was not written into Finance fundamentals")

            debt = pd.read_csv(refresh.DEBT_OBSERVATIONS_PATH)
            for ticker in set(refresh.BORROWER_STRAIN_CIKS) - {"IREN", "ANET"}:
                rows = debt.loc[debt["Ticker"].eq(ticker)]
                periods = set(rows["Period End"].astype(str))
                if not {"2025-06-30", "2026-06-30"}.issubset(periods):
                    raise AssertionError(f"{ticker} missing definition-matched prior/current pair: {periods}")
                if set(rows["Definition"].dropna()) != {f"retained {ticker}"}:
                    raise AssertionError(f"{ticker} matched debt definition was not preserved")

            if report.get("debt_unresolved_tickers"):
                raise AssertionError(f"Unexpected unresolved debt tickers: {report}")

        # Regression: a current filing may expose a newer high-priority debt tag
        # that was absent a year earlier.  The refresh must fall through to one
        # common complete definition instead of selecting each date separately
        # and collapsing the matched cohort.
        synthetic = {
            "facts": {
                "us-gaap": {
                    "DebtCurrent": {"units": {"USD": [
                        {"end": "2026-06-30", "filed": "2026-07-30", "form": "10-Q", "val": 5.0},
                    ]}},
                    "DebtNoncurrent": {"units": {"USD": [
                        {"end": "2026-06-30", "filed": "2026-07-30", "form": "10-Q", "val": 95.0},
                    ]}},
                    "LongTermDebtCurrent": {"units": {"USD": [
                        {"end": "2025-06-30", "filed": "2025-07-30", "form": "10-Q", "val": 10.0},
                        {"end": "2026-06-30", "filed": "2026-07-30", "form": "10-Q", "val": 12.0},
                    ]}},
                    "LongTermDebtNoncurrent": {"units": {"USD": [
                        {"end": "2025-06-30", "filed": "2025-07-30", "form": "10-Q", "val": 70.0},
                        {"end": "2026-06-30", "filed": "2026-07-30", "form": "10-Q", "val": 78.0},
                    ]}},
                }
            }
        }
        current_row, prior_row, error = original_match(
            ticker="GOOG",
            companyfacts=synthetic,
            debt_definition="Long-term debt, current plus non-current, net",
            current_cutoff=pd.Timestamp("2026-08-09"),
            prior_cutoff=pd.Timestamp("2025-08-09"),
            current_capex_period_end="2026-06-30",
        )
        if error or current_row is None or prior_row is None:
            raise AssertionError(f"Common XBRL debt definition was not recovered: {error}")
        if current_row.get("_tags") != "LongTermDebtCurrent;LongTermDebtNoncurrent":
            raise AssertionError(f"Wrong current debt definition selected: {current_row}")
        if prior_row.get("_tags") != current_row.get("_tags"):
            raise AssertionError("Current and prior debt were not definition-matched")
        if current_row.get("Debt") != 90.0 or prior_row.get("Debt") != 80.0:
            raise AssertionError(f"Wrong common-group values: {current_row}, {prior_row}")

        # Regression: a newer filing-reviewed debt row can arrive before the
        # TTM CapEx snapshot advances. The Finance card must select the debt
        # observation aligned to CapEx rather than blindly taking the newest row.
        meta_snapshot = pd.DataFrame([_snapshot("META", current=True)])
        meta_snapshot.loc[:, "Financial Period End"] = "2026-03-31"
        meta_snapshot.loc[:, "CapEx Period End"] = "2026-03-31"
        meta_history = meta_snapshot.copy()
        meta_debt = pd.DataFrame([
            {"Ticker":"META","Period End":"2025-03-31","Filing Date":"2025-05-01","Debt":28.0,"Definition":"retained META"},
            {"Ticker":"META","Period End":"2026-03-31","Filing Date":"2026-04-30","Debt":58.0,"Definition":"retained META"},
            {"Ticker":"META","Period End":"2026-06-30","Filing Date":"2026-07-24","Debt":84.0,"Definition":"retained META"},
        ])
        pulse, current_total, prior_total, _, count = _matched_debt_pulse(
            meta_history, meta_snapshot, debt_observations=meta_debt, min_companies=1
        )
        if count != 1 or current_total != 58.0 or prior_total != 28.0:
            raise AssertionError(
                f"Debt/CapEx period alignment regressed: count={count}, current={current_total}, prior={prior_total}, pulse={pulse}"
            )
    finally:
        refresh.FUNDAMENTALS_PATH, refresh.DEBT_OBSERVATIONS_PATH = original_paths
        refresh.fetch_company_facts = original_fetch
        refresh.build_company_snapshot = original_build
        refresh._matched_debt_pair = original_match

    print("PASS  EDGAR refresh rebuilds 10-company Finance fundamentals")
    print("PASS  definition-matched debt refresh preserves 8-company coverage with filing-reviewed fallback")
    print("PASS  matched debt reconciles generic Companyfacts debt fields in retained Finance fundamentals")
    print("PASS  EDGAR refresh token reaches Companyfacts cache key")
    print("PASS  debt refresh falls through to one common current/prior XBRL definition")
    retained_mix = calculate_deployment_funding_mix({})
    if int(retained_mix.get("current", {}).get("debt_financing_companies") or 0) != 8:
        raise AssertionError(f"Packaged retained debt cohort is not 8/8: {retained_mix.get('current', {})}")

    print("PASS  Finance debt selection prefers the observation aligned to the current CapEx period")
    print("PASS  packaged retained Finance debt cohort is 8/8")


if __name__ == "__main__":
    main()
