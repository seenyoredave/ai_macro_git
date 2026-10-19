"""Read-only candidate: U.S. public-pension PE allocation pressure via Public Plans Data.

This probe writes staging CSVs only; it is not connected to Reader publication.
PPD's plan-level sample covers U.S. state/local public pensions, not all PE LPs.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date
from io import StringIO
import json
import math
import os
from pathlib import Path
from statistics import median
import sys
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

API = "https://publicplansdata.org/api/"
FIELDS = ("fy", "ppd_id", "PlanName", "PETotal_Actl", "PETotal_Trgt")
THRESHOLD_PP = 0.5
COMPLETENESS_FLOOR = 0.85
SHARED_SIGNATURE_YEARS = 3
MAX_TARGET_FOR_SIGNAL_PP = 75.0
START_YEAR = 2015
END_YEAR = date.today().year
MAX_BYTES = 8_000_000
STAGING = Path("pe_probe_output/institutional_capacity")
DETAIL_FIELDS = ("fiscal_year", "ppd_id", "plan_name", "actual_pe_pct", "target_pe_pct", "gap_pp",
                 "allocation_status", "portfolio_unit_id", "portfolio_basis", "source_url")
ANNUAL_FIELDS = ("fiscal_year", "plans_with_both", "pe_targeted_plans", "zero_exposure_zero_target",
                 "positive_exposure_zero_target", "unverified_high_pe_target", "over_target", "at_target", "under_target",
                 "over_target_pct", "median_gap_pp", "median_actual_pct", "median_target_pct",
                 "portfolio_proxy_units", "portfolio_proxy_collapsed_plans", "portfolio_proxy_over_target_pct",
                 "paired_plans", "paired_prior_over_pct", "paired_current_over_pct", "paired_change_pp",
                 "paired_portfolio_units", "paired_portfolio_prior_over_pct", "paired_portfolio_current_over_pct",
                 "paired_portfolio_change_pp", "reporting_coverage_ratio", "coverage_status", "signal_eligible", "source_url")


class SourceRejected(ValueError):
    """Unexpected or economically unusable API result."""


def query_url(start_year: int, end_year: int) -> str:
    if not (2001 <= start_year <= end_year <= date.today().year + 1):
        raise SourceRejected("Invalid fiscal-year query range")
    params = {
        "q": "QVariables", "variables": ",".join(FIELDS),
        "filterfystart": start_year, "filterfyend": end_year,
        "filtertierid": 0, "filtereegroupid": 0, "format": "json",
    }
    return API + "?" + urlencode(params)


def download(url: str) -> bytes:
    address = urlparse(url)
    if address.scheme != "https" or address.hostname not in {"publicplansdata.org", "www.publicplansdata.org"}:
        raise SourceRejected("API address is not an approved Public Plans Data host")
    request = Request(url, headers={"User-Agent": "AI-Macro-PE-Institutional-Capacity/1.0 (public research)", "Accept": "application/json"})
    with urlopen(request, timeout=35) as response:
        location = urlparse(response.geturl())
        if location.scheme != "https" or location.hostname not in {"publicplansdata.org", "www.publicplansdata.org"}:
            raise SourceRejected("Unexpected API redirect destination")
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or len(data) < 15:
        raise SourceRejected("Truncated or oversized API response")
    return data


def decode_api(payload: bytes) -> list[dict]:
    try:
        decoded = json.loads(payload.decode("utf-8-sig"))
    except (ValueError, UnicodeError) as exc:
        raise SourceRejected("API did not return valid JSON") from exc
    if not isinstance(decoded, list) or not decoded or not isinstance(decoded[0], dict):
        raise SourceRejected("Unexpected API JSON structure")
    meta, *records = decoded
    if str(meta.get("status", "")).upper() != "OK":
        problem = next((r.get("Error") for r in records if isinstance(r, dict) and "Error" in r), None)
        raise SourceRejected(f"Public Plans Data API rejected query: {problem or meta.get('status')}")
    if str(meta.get("q", "")).lower() != "qvariables":
        raise SourceRejected("Unexpected API query response type")
    try:
        expected = int(meta["recordcount"])
    except (KeyError, ValueError, TypeError) as exc:
        raise SourceRejected("Missing API record count") from exc
    if expected != len(records) or expected == 0:
        raise SourceRejected(f"Incomplete API result: expected {expected}, returned {len(records)}")
    if not all(isinstance(r, dict) and set(FIELDS).issubset(r) for r in records):
        raise SourceRejected("Missing required allocation variables in API data")
    return records


def _pct(value: object) -> float | None:
    if value is None or str(value).strip().casefold() in {"", "null", "none", "na", "n/a"}:
        return None
    try:
        x = float(str(value).strip().replace(",", ""))
    except (ValueError, TypeError) as exc:
        raise SourceRejected(f"Unexpected allocation value: {value!r}") from exc
    # PPD encodes these two asset-allocation variables as fractions (0.12 = 12%).
    # Do not silently guess whether another provider has supplied percentage points.
    if not math.isfinite(x) or not (0 <= x <= 1):
        raise SourceRejected(f"Expected fractional PE allocation in [0, 1]: {value!r}")
    return round(x * 100, 6)


def normalize(records: list[dict], source_url: str, *, start_year: int, end_year: int) -> tuple[list[dict], dict]:
    rows = []
    observed_keys = set()
    missing = 0
    for source in records:
        try:
            year, plan_id = int(source["fy"]), int(source["ppd_id"])
        except (KeyError, ValueError, TypeError) as exc:
            raise SourceRejected("Unidentifiable plan-year") from exc
        if not (start_year <= year <= end_year and plan_id > 0):
            raise SourceRejected("Unexpected plan identifier or fiscal year")
        key = (year, plan_id)
        if key in observed_keys:
            raise SourceRejected(f"Duplicate pension plan/year: {key}")
        observed_keys.add(key)
        actual, target = _pct(source["PETotal_Actl"]), _pct(source["PETotal_Trgt"])
        if actual is None or target is None:
            missing += 1
            continue
        gap = round(actual - target, 5)
        if target > MAX_TARGET_FOR_SIGNAL_PP:
            # Retain outlier in plan-level evidence, but do not treat its policy
            # target as a verified indication of ordinary PE commitment capacity.
            status = "unverified_high_pe_target"
        elif target == 0:
            status = "zero_target_positive_exposure" if actual > 0 else "zero_target_zero_exposure"
        else:
            status = "over" if gap > THRESHOLD_PP else "under" if gap < -THRESHOLD_PP else "at"
        rows.append({"fiscal_year": year, "ppd_id": plan_id, "plan_name": str(source.get("PlanName") or "").strip(),
                     "actual_pe_pct": actual, "target_pe_pct": target, "gap_pp": gap,
                     "allocation_status": status, "portfolio_unit_id": f"plan:{plan_id}",
                     "portfolio_basis": "individual_plan", "source_url": source_url})
    rows.sort(key=lambda row: (row["fiscal_year"], row["ppd_id"]))
    if not rows:
        raise SourceRejected("No plans report both actual and target PE allocation")
    return rows, {"api_plan_years": len(records), "matched_plan_years": len(rows), "missing_actual_or_target": missing}


def _targeted(row: dict) -> bool:
    """A positive PE policy target is necessary for a meaningful target gap."""
    return 0 < row["target_pe_pct"] <= MAX_TARGET_FOR_SIGNAL_PP


def identify_portfolio_proxies(rows: list[dict]) -> None:
    """Group only unusually strong *candidate* common-investment exposures.

    Three consecutive years must have EXACTLY matching nonzero-target PE
    allocation pairs, and plan names must share a sponsor prefix. This is not
    evidence of legal common ownership. The raw, plan-weighted reading remains
    available next to the deliberately conservative sensitivity reading.
    """
    for row in rows:
        row["portfolio_unit_id"] = f"plan:{row['ppd_id']}"
        row["portfolio_basis"] = "individual_plan"
    index = {(r["fiscal_year"], r["ppd_id"]): r for r in rows}
    years = sorted({r["fiscal_year"] for r in rows})
    for year in years:
        signatures = {}
        for row in (r for r in rows if r["fiscal_year"] == year and _targeted(r)):
            history = [index.get((year - k, row["ppd_id"])) for k in range(SHARED_SIGNATURE_YEARS)]
            if any(r is None or not _targeted(r) for r in history):
                continue
            sponsor_prefix = row["plan_name"].strip().split(" ", 1)[0].casefold()
            if not sponsor_prefix:
                continue
            fingerprint = (sponsor_prefix, tuple((r["actual_pe_pct"], r["target_pe_pct"]) for r in history))
            signatures.setdefault(fingerprint, []).append(row)
        for members in signatures.values():
            if len(members) < 2:
                continue
            representative = min(member["ppd_id"] for member in members)
            for member in members:
                member["portfolio_unit_id"] = f"signature3:{representative}"
                member["portfolio_basis"] = "identical_three_year_exposure"


def _portfolio_units(members: list[dict]) -> list[dict]:
    unique = {}
    for row in sorted(members, key=lambda r: r["ppd_id"]):
        unique.setdefault(row["portfolio_unit_id"], row)
    return list(unique.values())


def summarize(rows: list[dict], source_url: str) -> list[dict]:
    identify_portfolio_proxies(rows)
    groups: dict[int, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["fiscal_year"], []).append(row)
    out = []

    def percent(num: int, denominator: int) -> float:
        return round(100 * num / denominator, 2)

    def above(items: list[dict]) -> int:
        return sum(x["allocation_status"] == "over" for x in items)

    for year, members in sorted(groups.items()):
        active = [x for x in members if _targeted(x)]
        units = _portfolio_units(active)
        previous = {r["ppd_id"]: r for r in groups.get(year - 1, []) if _targeted(r)}
        paired = [(previous[r["ppd_id"]], r) for r in active if r["ppd_id"] in previous]
        # Same-portfolio sensitivity for the matched plan panel: current-year
        # three-year signatures include both current and prior observations.
        unit_pairs = {}
        for before, after in sorted(paired, key=lambda pair: pair[1]["ppd_id"]):
            unit_pairs.setdefault(after["portfolio_unit_id"], (before, after))
        paired_units = list(unit_pairs.values())

        old_pct = percent(sum(a["allocation_status"] == "over" for a, _ in paired), len(paired)) if paired else ""
        new_pct = percent(sum(b["allocation_status"] == "over" for _, b in paired), len(paired)) if paired else ""
        pool_prior = percent(sum(a["allocation_status"] == "over" for a, _ in paired_units), len(paired_units)) if paired_units else ""
        pool_current = percent(sum(b["allocation_status"] == "over" for _, b in paired_units), len(paired_units)) if paired_units else ""
        prior_counts = [len(groups[p]) for p in (year - 1, year - 2, year - 3) if p in groups]
        coverage_ratio = round(len(members) / median(prior_counts), 3) if prior_counts else ""
        coverage_status = ("baseline" if not prior_counts else
                           "incomplete" if coverage_ratio < COMPLETENESS_FLOOR else "adequate")

        out.append({
            "fiscal_year": year, "plans_with_both": len(members), "pe_targeted_plans": len(active),
            "zero_exposure_zero_target": sum(x["allocation_status"] == "zero_target_zero_exposure" for x in members),
            "positive_exposure_zero_target": sum(x["allocation_status"] == "zero_target_positive_exposure" for x in members),
            "unverified_high_pe_target": sum(x["allocation_status"] == "unverified_high_pe_target" for x in members),
            "over_target": above(active), "at_target": sum(x["allocation_status"] == "at" for x in active),
            "under_target": sum(x["allocation_status"] == "under" for x in active),
            "over_target_pct": percent(above(active), len(active)) if active else "",
            "median_gap_pp": round(median(x["gap_pp"] for x in active), 3) if active else "",
            "median_actual_pct": round(median(x["actual_pe_pct"] for x in active), 3) if active else "",
            "median_target_pct": round(median(x["target_pe_pct"] for x in active), 3) if active else "",
            "portfolio_proxy_units": len(units),
            "portfolio_proxy_collapsed_plans": len(active) - len(units),
            "portfolio_proxy_over_target_pct": percent(above(units), len(units)) if units else "",
            "paired_plans": len(paired), "paired_prior_over_pct": old_pct,
            "paired_current_over_pct": new_pct,
            "paired_change_pp": round(new_pct - old_pct, 2) if paired else "",
            "paired_portfolio_units": len(paired_units),
            "paired_portfolio_prior_over_pct": pool_prior,
            "paired_portfolio_current_over_pct": pool_current,
            "paired_portfolio_change_pp": round(pool_current - pool_prior, 2) if paired_units else "",
            "reporting_coverage_ratio": coverage_ratio, "coverage_status": coverage_status,
            "signal_eligible": int(coverage_status == "adequate" and len(paired) >= 30
                                   and len(paired_units) >= 30),
            "source_url": source_url,
        })
    return out


def validate_sample(detail: list[dict], annual: list[dict], *, min_plans: int = 30) -> None:
    substantial_years = [r for r in annual if r["pe_targeted_plans"] >= min_plans]
    if len(substantial_years) < 2:
        raise SourceRejected("Insufficient multi-year comparable PE-targeted pension sample")
    if sum(x["plans_with_both"] for x in annual) != len(detail):
        raise SourceRejected("Annual plan counts do not reconcile")
    for r in annual:
        if (r["over_target"] + r["at_target"] + r["under_target"] != r["pe_targeted_plans"]
                or r["pe_targeted_plans"] + r["zero_exposure_zero_target"]
                + r["positive_exposure_zero_target"] + r["unverified_high_pe_target"] != r["plans_with_both"]):
            raise SourceRejected("Allocation classification does not reconcile")
        if (r["paired_plans"] > r["pe_targeted_plans"]
                or r["portfolio_proxy_units"] > r["pe_targeted_plans"]
                or r["paired_portfolio_units"] > r["paired_plans"]):
            raise SourceRejected("Invalid matched-panel or portfolio-proxy sample")
        if (r["coverage_status"] == "incomplete" and
                (not isinstance(r["reporting_coverage_ratio"], (int, float))
                 or r["reporting_coverage_ratio"] >= COMPLETENESS_FLOOR)):
            raise SourceRejected("Inconsistent reporting coverage status")
        if r["signal_eligible"] and r["coverage_status"] != "adequate":
            raise SourceRejected("Incomplete reporting year cannot be used as a signal")


def csv_bytes(rows: list[dict], columns: tuple[str, ...]) -> bytes:
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def run(*, out_dir: Path = STAGING, start_year: int = START_YEAR, end_year: int = END_YEAR) -> dict:
    url = query_url(start_year, end_year)
    detail, coverage = normalize(decode_api(download(url)), url, start_year=start_year, end_year=end_year)
    annual = summarize(detail, url)
    validate_sample(detail, annual)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, rows, columns in (
        ("public_pension_pe_allocation_plan_year.csv", detail, DETAIL_FIELDS),
        ("public_pension_pe_allocation_annual.csv", annual, ANNUAL_FIELDS),
    ):
        path = out_dir / name
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_bytes(csv_bytes(rows, columns))
        os.replace(temporary, path)
    result = {**coverage, "annual_years": len(annual),
              "latest_year": max(x["fiscal_year"] for x in annual),
              "latest_sample": annual[-1]["plans_with_both"],
              "last_year_paired_plans": annual[-1]["paired_plans"],
              "latest_pe_targeted_plans": annual[-1]["pe_targeted_plans"],
              "latest_portfolio_proxy_units": annual[-1]["portfolio_proxy_units"],
              "latest_coverage_status": annual[-1]["coverage_status"],
              "latest_signal_eligible_year": max((r["fiscal_year"] for r in annual if r["signal_eligible"]), default=None),
              "source": "Public Plans Data — PensionInvestmentPerformance",
              "scope": "U.S. state and local public pensions with both PE allocation fields"}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=STAGING)
    parser.add_argument("--start-year", type=int, default=START_YEAR)
    parser.add_argument("--end-year", type=int, default=END_YEAR)
    args = parser.parse_args(argv)
    try:
        result = run(out_dir=args.out_dir, start_year=args.start_year, end_year=args.end_year)
        print(json.dumps({"status": "candidate_extracted", **result}, sort_keys=True), flush=True)
        return 0
    except Exception as exc:
        print(json.dumps({"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
