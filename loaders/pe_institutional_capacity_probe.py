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
START_YEAR = 2015
END_YEAR = date.today().year
MAX_BYTES = 8_000_000
STAGING = Path("pe_probe_output/institutional_capacity")
DETAIL_FIELDS = ("fiscal_year", "ppd_id", "plan_name", "actual_pe_pct", "target_pe_pct", "gap_pp", "allocation_status", "source_url")
ANNUAL_FIELDS = ("fiscal_year", "plans_with_both", "over_target", "at_target", "under_target", "over_target_pct", "median_gap_pp", "median_actual_pct", "median_target_pct", "paired_plans", "paired_prior_over_pct", "paired_current_over_pct", "paired_change_pp", "source_url")


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
    if not math.isfinite(x) or not (0 <= x <= 100):
        raise SourceRejected(f"Allocation percentage out of range: {value!r}")
    return x


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
        status = "over" if gap > THRESHOLD_PP else "under" if gap < -THRESHOLD_PP else "at"
        rows.append({"fiscal_year": year, "ppd_id": plan_id, "plan_name": str(source.get("PlanName") or "").strip(),
                     "actual_pe_pct": actual, "target_pe_pct": target, "gap_pp": gap,
                     "allocation_status": status, "source_url": source_url})
    rows.sort(key=lambda row: (row["fiscal_year"], row["ppd_id"]))
    if not rows:
        raise SourceRejected("No plans report both actual and target PE allocation")
    return rows, {"api_plan_years": len(records), "matched_plan_years": len(rows), "missing_actual_or_target": missing}


def summarize(rows: list[dict], source_url: str) -> list[dict]:
    groups: dict[int, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["fiscal_year"], []).append(row)
    out = []
    for year, members in sorted(groups.items()):
        previous = {r["ppd_id"]: r for r in groups.get(year - 1, [])}
        paired = [(previous[r["ppd_id"]], r) for r in members if r["ppd_id"] in previous]
        over = sum(x["allocation_status"] == "over" for x in members)
        def percent(num: int, denominator: int) -> float:
            return round(100 * num / denominator, 2)
        old_pct = percent(sum(a["allocation_status"] == "over" for a, _ in paired), len(paired)) if paired else ""
        new_pct = percent(sum(b["allocation_status"] == "over" for _, b in paired), len(paired)) if paired else ""
        out.append({
            "fiscal_year": year, "plans_with_both": len(members),
            "over_target": over, "at_target": sum(x["allocation_status"] == "at" for x in members),
            "under_target": sum(x["allocation_status"] == "under" for x in members),
            "over_target_pct": percent(over, len(members)),
            "median_gap_pp": round(median(x["gap_pp"] for x in members), 3),
            "median_actual_pct": round(median(x["actual_pe_pct"] for x in members), 3),
            "median_target_pct": round(median(x["target_pe_pct"] for x in members), 3),
            "paired_plans": len(paired), "paired_prior_over_pct": old_pct,
            "paired_current_over_pct": new_pct,
            "paired_change_pp": round(new_pct - old_pct, 2) if paired else "",
            "source_url": source_url,
        })
    return out


def validate_sample(detail: list[dict], annual: list[dict], *, min_plans: int = 30) -> None:
    substantial_years = [r for r in annual if r["plans_with_both"] >= min_plans]
    if len(substantial_years) < 2:
        raise SourceRejected("Insufficient multi-year comparable pension sample")
    if sum(x["plans_with_both"] for x in annual) != len(detail):
        raise SourceRejected("Annual plan counts do not reconcile")
    for r in annual:
        if r["over_target"] + r["at_target"] + r["under_target"] != r["plans_with_both"]:
            raise SourceRejected("Allocation classification does not reconcile")
        if r["paired_plans"] > r["plans_with_both"]:
            raise SourceRejected("Invalid matched-panel sample")


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
