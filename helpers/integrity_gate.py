"""Small stop-the-line integrity gate for the platform's critical data contracts.

This is intentionally not a general test suite. It covers only contradictions
that can materially change a headline metric or double-count a large project.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import types

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _check(condition, message):
    if not condition:
        raise AssertionError(message)


def check_finance_contract():
    from analytics.deployment_funding_mix import calculate_deployment_funding_mix
    from analytics.borrower_strain_history import DEBT_GROUPS, instant_group_fact

    result = calculate_deployment_funding_mix({})
    current = result["current"]
    _check(current["internal_funding_companies"] >= 2, "Internal funding cohort unavailable")
    _check(current["cash_reserve_companies"] >= 2, "Cash runway cohort unavailable")
    _check(current["debt_financing_companies"] >= 2, "Matched debt cohort unavailable")
    _check(current["measurement_date"] is not None, "SEC measurement date unavailable")
    _check(
        np.isfinite(current["debt_financing_pulse"]),
        "Debt pulse failed matched-period calculation",
    )
    expected = (
        current["total_debt"] - current["prior_year_total_debt"]
    ) / current["debt_financing_capex_total"]
    _check(
        np.isclose(expected, current["debt_financing_pulse"]),
        "Debt pulse numerator and denominator do not share the matched cohort",
    )

    series = result.get("series", {})
    common_history = result.get("history")
    _check(
        isinstance(common_history, pd.DataFrame) and not common_history.empty,
        "Common funding history unavailable",
    )
    common_columns = {
        "internal_funding_coverage": "Internal Funding Coverage",
        "cash_reserve_coverage_years": "Cash Reserve Coverage",
        "debt_financing_pulse": "Debt Financing Pulse",
        "forward_commitment_load": "Forward Commitment Load",
    }
    for key in (
        "internal_funding_coverage",
        "cash_reserve_coverage_years",
        "debt_financing_pulse",
        "forward_commitment_load",
    ):
        history = series.get(key)
        _check(
            isinstance(history, pd.DataFrame) and not history.empty,
            f"Funding sparkline unavailable: {key}",
        )
        history = history.copy()
        history["Date"] = pd.to_datetime(history["Date"], errors="coerce")
        history["Value"] = pd.to_numeric(history["Value"], errors="coerce")
        history = history.dropna(subset=["Date", "Value"]).sort_values("Date")
        cutoff = history["Date"].max() - pd.DateOffset(years=5)
        trailing = history.loc[history["Date"] >= cutoff]
        _check(len(trailing) >= 2, f"Five-year funding sparkline has no line: {key}")

        common = common_history[["Date", common_columns[key]]].copy()
        common["Date"] = pd.to_datetime(common["Date"], errors="coerce")
        common[common_columns[key]] = pd.to_numeric(
            common[common_columns[key]], errors="coerce"
        )
        common = common.dropna(subset=["Date", common_columns[key]]).sort_values("Date")
        common_cutoff = common["Date"].max() - pd.DateOffset(years=5)
        _check(
            len(common.loc[common["Date"] >= common_cutoff]) >= 2,
            f"Common funding history cannot render a line: {key}",
        )

    for key in ("debt_financing_pulse", "forward_commitment_load"):
        history = series[key].sort_values("Date")
        _check(
            np.isclose(float(history.iloc[-1]["Value"]), float(current[key])),
            f"Funding sparkline endpoint does not match headline: {key}",
        )

    finance_source = (PROJECT_ROOT / "rendering" / "finance.py").read_text(
        encoding="utf-8"
    )
    funding_section = finance_source.split("def _render_funding_section", 1)[1].split(
        "def _fmt_dollars", 1
    )[0]
    _check("years=5" in funding_section, "Funding cards are not limited to five years")

    partial = {
        "facts": {
            "us-gaap": {
                "LongTermDebtCurrent": {
                    "units": {
                        "USD": [
                            {
                                "end": "2026-03-31",
                                "filed": "2026-04-30",
                                "form": "10-Q",
                                "val": 10.0,
                            }
                        ]
                    }
                }
            }
        }
    }
    _check(
        pd.isna(instant_group_fact(partial, DEBT_GROUPS, "2026-06-30").value),
        "Debt extractor accepted one leg of a multi-part definition",
    )


def check_lender_four_pillars():
    from analytics.lender_strain_engine import _score_snapshot

    dates = pd.to_datetime(["2025-03-31", "2025-06-30"])
    bank = pd.DataFrame({"Date": dates, "Tightening Percent": [5.0, 10.0]})
    capital = pd.DataFrame({"Date": dates, "Tier 1 Capital Ratio (%)": [13.0, 12.5]})
    pe = pd.DataFrame(
        {
            "Date": dates,
            "High-Leverage Portfolio Share (%)": [30.0, 35.0],
            "PIK Mean (%)": [15.0, 18.0],
        }
    )
    snapshot = _score_snapshot(
        bank.iloc[-1],
        capital.iloc[-1],
        None,
        pe.iloc[-1],
        bank_history=bank,
        bank_capital_history=capital,
        bdc_history=pd.DataFrame(),
        pe_history=pe,
        observation_date=dates[-1],
    )
    _check(snapshot["valid_components"] == 3, "Missing-pillar fixture is malformed")
    _check(pd.isna(snapshot["score"]), "Lender Strain accepted fewer than four pillars")


def check_lender_history_and_dynamics():
    from analytics.lender_strain_engine import calculate_lender_strain
    from analytics.trend_engine import calc_metric_trend

    result = calculate_lender_strain({})
    history = result.get("history")
    _check(history is not None and not history.empty, "Lender Strain history unavailable")
    _check(
        (history["Date"].max() - history["Date"].min()).days >= 3650,
        "Lender Strain does not span ten years",
    )
    _check(
        set(history["Valid Components"].astype(int)) == {4},
        "Lender Strain historical bridge weakened the four-pillar contract",
    )
    trend = calc_metric_trend(
        history,
        "Lender Strain",
        distinct_observations=True,
        repeat_tolerance=1e-8,
        dynamics_window_days=365,
        dynamics_min_observations=3,
        dynamics_min_span_days=120,
    )
    _check(np.isfinite(trend["velocity"]), "Lender Strain velocity unavailable")
    _check(np.isfinite(trend["acceleration"]), "Lender Strain acceleration unavailable")


def check_queue_reconciliation():
    summary = pd.read_csv(PROJECT_ROOT / "data" / "energy_interconnection_queue_summary.csv")
    queue = pd.read_csv(PROJECT_ROOT / "data" / "energy_interconnection_queue.csv")
    required = {"Generation MW", "Storage MW", "Queue MW", "Queue Accounting"}
    _check(required.issubset(queue.columns), "Queue component columns are missing")
    total = pd.to_numeric(summary["Queue GW"], errors="coerce").sum(min_count=1)
    _check(abs(float(total) - 2061.3275) <= 0.5, "Queue headline does not reconcile")
    technologies = set(summary["Technology Group"].astype(str))
    _check({"Solar", "Battery storage"}.issubset(technologies), "Queue technology legs missing")
    chart_source = (PROJECT_ROOT / "rendering" / "charts_energy.py").read_text(encoding="utf-8")
    _check(
        'if "Technology Group" not in clean.columns:' in chart_source,
        "Queue chart lacks the missing-summary schema guard",
    )


def check_manifest_contracts():
    manifest = pd.read_csv(PROJECT_ROOT / "data" / "infrastructure" / "source_manifest.csv")
    for _, row in manifest.iterrows():
        artifacts = str(row.get("derived_artifacts") or "").strip()
        hashes = str(row.get("derived_sha256") or "").strip()
        if artifacts.lower() == "nan" or not artifacts:
            continue
        paths = artifacts.split(";")
        expected = hashes.split(";")
        _check(len(paths) == len(expected), f"Manifest hash count mismatch: {row['source_id']}")
        for relative, digest in zip(paths, expected):
            path = PROJECT_ROOT / relative
            _check(path.exists(), f"Claimed artifact missing: {relative}")
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            _check(actual == digest, f"Artifact checksum mismatch: {relative}")
    m3 = manifest.loc[manifest["source_id"].eq("census-m3-compute")].iloc[0]
    m3_artifact = str(m3.get("derived_artifacts") or "").strip()
    _check(
        m3_artifact == "data/infrastructure/derived/compute_m3_history.csv",
        "M3 retained history is not registered",
    )
    m3_history = pd.read_csv(PROJECT_ROOT / m3_artifact)
    m3_dates = pd.to_datetime(m3_history["Observation Date"], errors="coerce")
    _check(
        m3_dates.notna().all() and (m3_dates.max() - m3_dates.min()).days >= 3650,
        "M3 retained history cannot support the ten-year display",
    )


def check_release_manifest():
    path = PROJECT_ROOT / "data" / "release_manifest.json"
    _check(path.exists(), "Release manifest is missing")
    payload = json.loads(path.read_text(encoding="utf-8"))
    _check(payload.get("manifest_version") == "1.0", "Release manifest version changed")
    files = payload.get("files") or {}
    _check(len(files) >= 15, "Release manifest omits critical contracts")
    material = []
    for relative, metadata in sorted(files.items()):
        source = PROJECT_ROOT / relative
        _check(source.exists(), f"Release input missing: {relative}")
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        _check(actual == metadata.get("sha256"), f"Stale release fingerprint: {relative}")
        material.append(f"{relative}:{actual}")
    release_id = hashlib.sha256("\n".join(material).encode("utf-8")).hexdigest()[:20]
    _check(release_id == payload.get("release_id"), "Release identifier does not reconcile")


def check_archive_wiring():
    source = "\n".join(
        [
            (PROJECT_ROOT / "archive" / "archive.py").read_text(encoding="utf-8"),
            (PROJECT_ROOT / "helpers" / "rebuild_derived_history.py").read_text(encoding="utf-8"),
        ]
    )
    for identifier in (
        "Commercial-vs-Residential Output Pressure",
        "Power-System Utilization Pressure",
        "Potential-Output Response Gap",
        "Sustainable Capacity Growth",
    ):
        _check(identifier in source, f"Archive identifier missing: {identifier}")


def check_universal_aei_backfill():
    """Protect the one-formula, full-universe market-history contract."""
    from config.factor_config import DEFAULT_FACTORS, FACTOR_CONFIG
    from config.benchmark_config import (
        BENCHMARK_VERSION,
        QQQ_WEIGHTS,
        QQQ_WEIGHTS_EFFECTIVE_DATE,
    )
    from config.sector_config import (
        EXPECTED_SECTOR_COUNT,
        EXPECTED_TICKER_COUNT,
        SECTOR_CONFIG,
    )

    required_factors = ("relative_performance", "market_breadth")
    _check(
        tuple(DEFAULT_FACTORS) == required_factors,
        "AEI default factor definition changed",
    )
    _check(
        set(FACTOR_CONFIG) == set(SECTOR_CONFIG),
        "AEI factor coverage does not match the configured sectors",
    )
    _check(
        all(tuple(factors) == required_factors for factors in FACTOR_CONFIG.values()),
        "AEI contains a sector-specific factor exception",
    )

    yf = pd.read_csv(PROJECT_ROOT / "archive" / "yf_history.csv")
    sector = pd.read_csv(PROJECT_ROOT / "archive" / "sector_history.csv")
    macro = pd.read_csv(PROJECT_ROOT / "archive" / "macro_history.csv")
    configured = {
        (sector_name, ticker)
        for sector_name, definition in SECTOR_CONFIG.items()
        for ticker in definition["basket"]
    }
    _check(len(configured) == EXPECTED_TICKER_COUNT, "Configured ticker count changed")
    _check(len(SECTOR_CONFIG) == EXPECTED_SECTOR_COUNT, "Configured sector count changed")

    yf["Date"] = pd.to_datetime(yf["Date"], errors="coerce").dt.normalize()
    _check(yf["Date"].notna().all(), "Raw market history contains an invalid date")
    _check(
        yf["Date"].dt.weekday.lt(5).all(),
        "Raw market history contains a weekend observation date",
    )
    _check(
        not set(pd.to_datetime(["2026-06-19", "2026-07-03"])).intersection(set(yf["Date"])),
        "Raw market history contains a demonstrated NYSE holiday misdate",
    )
    _check(
        not yf.duplicated(["Date", "Sector", "Ticker"]).any(),
        "Raw market history contains duplicate security observations",
    )
    required_market_columns = (
        "1Y Return",
        "Price Extension 200D",
        "Momentum Acceleration",
        "Volatility Expansion",
        "Volume Activity",
    )
    for column in required_market_columns:
        values = pd.to_numeric(yf[column], errors="coerce")
        _check(
            np.isfinite(values).all(),
            f"Raw market history has incomplete {column} backfill",
        )
    for observation_date, rows in yf.groupby("Date", sort=False):
        observed = set(zip(rows["Sector"], rows["Ticker"]))
        _check(
            len(rows) == EXPECTED_TICKER_COUNT and observed == configured,
            f"Raw market membership is incomplete on {observation_date.date()}",
        )

    raw_dates = set(yf["Date"])
    sector["Date"] = pd.to_datetime(sector["Date"], errors="coerce").dt.normalize()
    _check(set(sector["Date"]) == raw_dates, "Sector history is not date-aligned to raw market history")
    _check(
        sector.groupby("Date")["Sector"].nunique().eq(EXPECTED_SECTOR_COUNT).all(),
        "Sector history is incomplete on at least one market date",
    )
    _check(
        set(pd.to_numeric(sector["AEI Version"], errors="coerce")) == {4.0}
        and set(pd.to_numeric(sector["Pressure Version"], errors="coerce")) == {4.0},
        "Sector history contains pre-unification AEI or pressure rows",
    )
    _check(
        set(sector["Benchmark Version"].astype(str)) == {str(BENCHMARK_VERSION)}
        and set(sector["Benchmark Weight Date"].astype(str))
        == {str(QQQ_WEIGHTS_EFFECTIVE_DATE)},
        "Sector history contains mixed benchmark contracts",
    )

    benchmark = pd.read_csv(PROJECT_ROOT / "archive" / "benchmark_history.csv")
    benchmark = benchmark.loc[
        benchmark["Benchmark"].astype(str).str.upper().eq("QQQ")
    ].copy()
    benchmark["Date"] = pd.to_datetime(benchmark["Date"], errors="coerce").dt.normalize()
    benchmark["Avg Return"] = pd.to_numeric(benchmark["Avg Return"], errors="coerce")
    benchmark = benchmark.dropna(subset=["Date", "Avg Return"]).sort_values("Date")
    _check(set(benchmark["Date"]) == raw_dates, "QQQ history is not aligned to market dates")
    _check(
        set(benchmark["Benchmark Version"].astype(str)) == {str(BENCHMARK_VERSION)},
        "QQQ history contains mixed benchmark versions",
    )
    _check(
        set(benchmark["Weight Effective Date"].astype(str))
        == {str(QQQ_WEIGHTS_EFFECTIVE_DATE)},
        "QQQ history contains mixed weight contracts",
    )
    for observation_date, market_rows in yf.groupby("Date", sort=False):
        by_ticker = market_rows.groupby("Ticker", sort=False)["1Y Return"].first()
        # The retained 204-name archive contains Alphabet Class C but not Class
        # A. This documented legacy alias is limited to fixed-reference history.
        if "GOOGL" not in by_ticker.index and "GOOG" in by_ticker.index:
            by_ticker.loc["GOOGL"] = by_ticker.loc["GOOG"]
        expected_benchmark = sum(
            float(by_ticker.loc[ticker]) * float(weight)
            for ticker, weight in QQQ_WEIGHTS.items()
        )
        archived_benchmark = float(
            benchmark.loc[benchmark["Date"].eq(observation_date), "Avg Return"].iloc[-1]
        )
        _check(
            np.isclose(archived_benchmark, expected_benchmark, atol=1e-12),
            f"QQQ fixed reference does not recalculate: {observation_date.date()}",
        )
    retained = sector.set_index(["Date", "Sector"])
    expected_sector_scores: dict[pd.Timestamp, list[float]] = {}
    expected_pressures: dict[pd.Timestamp, list[float]] = {}
    pressure_specs = (
        ("Price Extension 200D", 0.20, 0.30),
        ("Momentum Acceleration", 0.15, 0.25),
        ("Volatility Expansion", 0.60, 0.25),
        ("Volume Activity", 0.75, 0.20),
    )
    for (observation_date, sector_name), rows in yf.groupby(["Date", "Sector"], sort=False):
        benchmark_rows = benchmark.loc[benchmark["Date"].le(observation_date)]
        _check(not benchmark_rows.empty, f"QQQ benchmark unavailable on {observation_date.date()}")
        benchmark_return = float(benchmark_rows.iloc[-1]["Avg Return"])
        sector_return = float(pd.to_numeric(rows["1Y Return"], errors="coerce").mean())
        breadth = float(
            pd.to_numeric(rows["Price Extension 200D"], errors="coerce").gt(0).mean()
        )
        relative_score = 50.0 + 50.0 * np.tanh((sector_return - benchmark_return) / 0.30)
        breadth_score = 50.0 + 50.0 * np.clip((breadth - 0.50) / 0.50, -1.0, 1.0)
        expected_score = 0.60 * relative_score + 0.40 * breadth_score
        expected_pressure = 0.0
        for column, scale, weight in pressure_specs:
            raw = float(pd.to_numeric(rows[column], errors="coerce").median())
            expected_pressure += weight * (50.0 + 50.0 * np.tanh(raw / scale))

        archived = retained.loc[(observation_date, sector_name)]
        _check(
            np.isclose(float(archived["Sector Score"]), expected_score, atol=1e-8),
            f"AEI sector score does not recalculate: {sector_name} {observation_date.date()}",
        )
        _check(
            np.isclose(float(archived["Pressure"]), expected_pressure, atol=1e-8),
            f"Trading Pressure does not recalculate: {sector_name} {observation_date.date()}",
        )
        expected_sector_scores.setdefault(observation_date, []).append(expected_score)
        expected_pressures.setdefault(observation_date, []).append(expected_pressure)

    macro["Date"] = pd.to_datetime(macro["Date"], errors="coerce").dt.normalize()
    market_dates = pd.to_datetime(
        macro["Market Data Date"], errors="coerce"
    ).dt.normalize()
    _check(set(macro["Date"]) == raw_dates, "Macro history contains a non-market observation date")
    _check(market_dates.equals(macro["Date"]), "Macro rows are not owned by their market snapshot date")
    _check(
        set(pd.to_numeric(macro["AEI Version"], errors="coerce")) == {4.0}
        and set(pd.to_numeric(macro["Pressure Version"], errors="coerce")) == {4.0},
        "Macro history contains pre-unification AEI or pressure rows",
    )
    _check(
        set(macro["Benchmark Version"].astype(str)) == {str(BENCHMARK_VERSION)}
        and set(macro["Benchmark Weight Date"].astype(str))
        == {str(QQQ_WEIGHTS_EFFECTIVE_DATE)},
        "Macro history contains mixed benchmark contracts",
    )
    macro_by_date = macro.set_index("Date")
    for observation_date in sorted(raw_dates):
        archived = macro_by_date.loc[observation_date]
        _check(
            np.isclose(
                float(archived["AI Equity Index"]),
                float(np.mean(expected_sector_scores[observation_date])),
                atol=1e-8,
            ),
            f"Macro AEI does not reconcile to sector history: {observation_date.date()}",
        )
        _check(
            np.isclose(
                float(archived["Avg Sector Pressure"]),
                float(np.mean(expected_pressures[observation_date])),
                atol=1e-8,
            ),
            f"Macro pressure does not reconcile to sector history: {observation_date.date()}",
        )


def check_named_campus_deduplication():
    # The loader imports requests for optional refreshes; no network is used here.
    if "requests" not in sys.modules:
        try:
            __import__("requests")
        except ModuleNotFoundError:
            sys.modules["requests"] = types.ModuleType("requests")
    from loaders.facility_registry_loader import (
        build_campus_registry,
        build_facility_observations,
        canonicalize_facility_observations,
        load_fractracker_facility_records,
        load_gigawatt_facility_records,
    )

    supplemental = pd.concat(
        [load_fractracker_facility_records(), load_gigawatt_facility_records()],
        ignore_index=True,
        sort=False,
    )
    decisions = pd.read_csv(PROJECT_ROOT / "data" / "facility_identity_decisions.csv", dtype=str).fillna("")
    decision_ids = set(decisions["Source Record ID"].astype(str))
    # Restrict the fixture to reviewed identities and the original six named
    # collisions so the gate stays bounded while using the production path.
    pattern = "Homer|Rowan|Colossus|Caprock|CoreWeave|Gregory"
    relevant = supplemental["Source Record ID"].astype(str).isin(decision_ids)
    for column in ("Facility", "Operator", "Developer", "Address", "City", "Notes"):
        if column in supplemental.columns:
            relevant |= supplemental[column].astype(str).str.contains(
                pattern, case=False, na=False
            )
    supplemental = supplemental.loc[relevant].copy()
    observations = build_facility_observations(pd.DataFrame(), supplemental)
    campuses = build_campus_registry(canonicalize_facility_observations(observations))
    needles = (
        "Homer City",
        "Rowan Digital",
        "Colossus 2",
        "Caprock",
        "CoreWeave Plano",
        "Gregory Road",
    )
    for needle in needles:
        matches = campuses["Facility"].str.contains(needle, case=False, na=False)
        _check(int(matches.sum()) == 1, f"Named campus did not resolve once: {needle}")

    campus_source_sets = campuses["Source Record ID"].map(
        lambda value: {item.strip() for item in str(value).split("|") if item.strip()}
    )
    for decision_group, rows in decisions.groupby("Decision Group", sort=False):
        source_ids = set(rows["Source Record ID"].astype(str))
        member_rows = [
            index for index, observed in campus_source_sets.items()
            if observed.intersection(source_ids)
        ]
        decision = str(rows["Decision"].iloc[0]).casefold()
        if decision == "merge":
            _check(
                len(set(member_rows)) == 1
                and source_ids.issubset(campus_source_sets.loc[member_rows[0]]),
                f"Reviewed campus merge failed: {decision_group}",
            )
        elif decision == "separate":
            _check(
                len(member_rows) == len(source_ids)
                and len(set(member_rows)) == len(source_ids),
                f"Reviewed distinct campuses were combined: {decision_group}",
            )


def main():
    checks = (
        ("SEC-equivalent funding", check_finance_contract),
        ("Four-pillar lender strain", check_lender_four_pillars),
        ("Ten-year lender dynamics", check_lender_history_and_dynamics),
        ("Queue reconciliation", check_queue_reconciliation),
        ("Manifest contracts", check_manifest_contracts),
        ("Release fingerprint", check_release_manifest),
        ("Archive identifiers", check_archive_wiring),
        ("Universal AEI backfill", check_universal_aei_backfill),
        ("Named-campus deduplication", check_named_campus_deduplication),
    )
    failures = []
    for label, function in checks:
        try:
            function()
            print(f"PASS  {label}")
        except Exception as exc:
            failures.append((label, exc))
            print(f"FAIL  {label}: {exc}")
    if failures:
        return 1
    print(f"PASS  {len(checks)} critical integrity contracts")
    return 0


if __name__ == "__main__":
    exit_code = main()
    # Some optional data libraries leave background workers alive after the
    # checks finish. Flush output and terminate explicitly so a successful
    # integrity run always returns control to the caller.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
