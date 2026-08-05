"""Small stop-the-line integrity gate for the platform's critical data contracts.

This is intentionally not a general test suite. It covers only contradictions
that can materially change a headline metric or double-count a large project.
"""

from __future__ import annotations

import hashlib
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
    _check(pd.isna(m3["derived_artifacts"]), "M3 manifest claims an absent retained artifact")


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
    # This contract concerns six named campuses, not the full national
    # registry. Restrict the fixture to records capable of matching those
    # campuses so the check stays bounded while exercising the same canonical
    # deduplication path.
    pattern = "Homer|Rowan|Colossus|Caprock|CoreWeave|Gregory"
    relevant = pd.Series(False, index=supplemental.index)
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


def main():
    checks = (
        ("SEC-equivalent funding", check_finance_contract),
        ("Four-pillar lender strain", check_lender_four_pillars),
        ("Queue reconciliation", check_queue_reconciliation),
        ("Manifest contracts", check_manifest_contracts),
        ("Archive identifiers", check_archive_wiring),
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
