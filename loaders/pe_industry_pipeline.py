"""Fail-closed PE industry-source refresh, separate from Streamlit displays.

The default destination is a staging folder. Only an explicitly authorized
automation invocation should publish validated CSVs to data/private_capital/.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urljoin, urlparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
import pandas as pd

from loaders.pe_industry_parsers import (SourceFormatError, parse_acg_quarter,
                                         parse_kpmg_h1, parse_sec_tables)
from helpers.atomic_io import atomic_write_bundle

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "pe_probe_output" / "industry"
PRODUCTION = ROOT / "data" / "private_capital"
SEC_INDEX = "https://www.sec.gov/data-research/investment-management-data"
KPMG_INDEX = "https://kpmg.com/xx/en/media/press-releases.html"
ACG_INDEX = "https://www.acg.org/news-media-brands/press-releases-acg-news"
KPMG_SEEDS = (
    "https://kpmg.com/xx/en/media/press-releases/2026/07/global-pe-market-shows-resilience-with-over-1-trillion-in-pe-investment-in-first-half-of-2026.html",
    "https://kpmg.com/xx/en/media/press-releases/2025/07/global-pe-investment-slows-sharply-amid-rising-geopolitical-and-trade-uncertainty.html",
)
ACG_SEEDS = (
    "https://www.acg.org/news-trends/news/gf-data-reports-show-steady-middle-market-deal-flow-amid-more-selective",
    "https://www.acg.org/news-trends/news/gf-data-reports-show-stronger-financing-markets-fueled-ma-gains-q1",
    "https://www.acg.org/news-trends/news/gf-data-releases-q3-2025-ma-and-leverage-reports",
    "https://www.acg.org/news-trends/news/gf-data-releases-q2-2025-ma-and-leverage-reports",
)
COLUMNS = ("source", "metric", "period", "period_end", "geography", "value", "unit",
           "population", "sample_count", "precision", "source_url", "published_on", "definition")
HOSTS = {
    "sec": {"www.sec.gov", "sec.gov"},
    "kpmg": {"kpmg.com"},
    "acg": {"www.acg.org", "acg.org"},
}
SOURCES = ("sec", "kpmg", "acg")


def _safe_source_url(url: str, source: str) -> bool:
    p = urlparse(url)
    return p.scheme == "https" and p.hostname in HOSTS[source] and not p.username and not p.password


def fetch(url: str, source: str, *, limit=8_000_000) -> bytes:
    if not _safe_source_url(url, source):
        raise SourceFormatError(f"Disallowed {source} URL: {url}")
    user_agent = (os.environ.get("SEC_USER_AGENT") or "").strip() if source == "sec" else ""
    user_agent = user_agent or "AI Macro PE research (public disclosure retrieval)"
    req = Request(url, headers={"User-Agent": user_agent, "Accept": "text/html,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*"})
    try:
        response = urlopen(req, timeout=30)
    except HTTPError as exc:
        exc.close()
        if source == "sec" and exc.code in (403, 429):
            identity = "SEC_USER_AGENT is not set locally" if not os.environ.get("SEC_USER_AGENT", "").strip() else "SEC_USER_AGENT is set"
            raise SourceFormatError(f"SEC HTTP {exc.code}: request denied ({identity}); retain prior observations and verify on GitHub Actions") from exc
        raise
    with response:
        if not _safe_source_url(response.geturl(), source):
            raise SourceFormatError(f"Unexpected {source} redirect: {response.geturl()}")
        data = response.read(limit + 1)
        if len(data) > limit:
            raise SourceFormatError(f"Oversized {source} download")
        if len(data) < 200:
            raise SourceFormatError(f"Empty or truncated {source} response")
        return data


def links(body: bytes, index: str, source: str):
    soup = BeautifulSoup(body.decode("utf-8", errors="replace"), "html.parser")
    for tag in soup.select("a[href]"):
        url = urljoin(index, tag["href"])
        if _safe_source_url(url, source):
            yield " ".join(tag.get_text(" ", strip=True).split()), url


def discover_sec(body: bytes) -> str:
    choices = [url for label, url in links(body, SEC_INDEX, "sec")
               if "private fund statistics supporting data" in label.casefold()
               and urlparse(url).path.lower().endswith(".xlsx")]
    if len(choices) != 1:
        raise SourceFormatError(f"SEC latest supporting workbook discovery returned {len(choices)} candidates")
    return choices[0]


def discover_press(body: bytes, source: str) -> list[str]:
    index = KPMG_INDEX if source == "kpmg" else ACG_INDEX
    output = []
    for label, url in links(body, index, source):
        joined = (label + " " + url).casefold()
        if source == "kpmg":
            valid = "/media/press-releases/20" in url and bool(re.search(r"private.equity|(?:\bpe\b.{0,20}market)", joined))
        else:
            valid = "gf data" in joined or "gf-data" in joined
            valid &= "/news-trends/news/" in url
        if valid:
            output.append(url)
    return list(dict.fromkeys(output))[:12]


def validate_observations(rows: list[dict], source: str) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=COLUMNS)
    if frame.empty or frame.isna().any().any():
        raise SourceFormatError("Missing required source observations")
    if frame.duplicated(["metric", "period_end"]).any():
        raise SourceFormatError("Duplicate source metric-period keys")
    expected_metrics = {
        "sec": {"fund_count", "gross_assets_usd_bn", "net_assets_usd_bn"},
        "kpmg": {"deal_value", "exit_value", "fundraising"},
        "acg": {"entry_ev_ebitda_ttm_adjusted"},
    }[source]
    if set(frame.metric) != expected_metrics:
        raise SourceFormatError("Unexpected metric set")
    now = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    periods = pd.to_datetime(frame.period_end, errors="coerce")
    published = pd.to_datetime(frame.published_on.replace("", None), errors="coerce")
    if periods.isna().any() or (source != "sec" and published.isna().any()) or (periods > now).any() or (published > now).any():
        raise SourceFormatError("Invalid or future observation date")
    if (published < periods).any():
        raise SourceFormatError("Source publication precedes measured period")
    numeric = pd.to_numeric(frame.value, errors="coerce")
    if numeric.isna().any() or numeric.le(0).any() or numeric.gt(1e8).any():
        raise SourceFormatError("Invalid financial observation")
    for uri in frame.source_url:
        if not _safe_source_url(uri, source):
            raise SourceFormatError("Invalid source URL")
    if source == "sec":
        for period, group in frame.groupby("period_end"):
            if set(group.metric) != expected_metrics:
                raise SourceFormatError(f"Incomplete SEC {period}")
            if (group.period.nunique() != 1 or not group.period.iloc[0].endswith("Q4")
                    or group.geography.ne("SEC Form PF reporting population").any()):
                raise SourceFormatError("SEC annual period or reporting population mismatch")
        if len(frame.period_end.unique()) < 4:
            raise SourceFormatError("SEC annual history too short")
    if source == "kpmg":
        for period, group in frame.groupby("period_end"):
            year = int(str(period)[:4])
            present = set(group.metric)
            # The Q2 2025 public press release has a direct fundraising
            # observation and a recoverable Q1+Q2 deal pair, but does not
            # disclose a global H1 exit value/count pair. Keep the gap visible.
            required = expected_metrics if year >= 2026 else {"deal_value", "fundraising"}
            if (not required <= present or group.period.nunique() != 1 or
                    group.period.iloc[0] != f"H1 {year}" or group.geography.ne("Global").any()):
                raise SourceFormatError(f"Incomplete or mismatched global H1 observations for {period}")
    if source == "acg":
        if frame.geography.ne("Not specified").any():
            raise SourceFormatError("ACG sample geography mismatch")
        if not frame.population.isin({
                "GF Data contributing PE-sponsored transactions ($1m-$500m EV)",
                "GF Data contributing PE-sponsored transactions ($10m-$500m EV)"}).all():
            raise SourceFormatError("Unverified GF Data deal-size population")
    frame["value"] = numeric.astype(float)
    return frame.sort_values(["period_end", "metric"], kind="stable").reset_index(drop=True)


def source_candidate(source: str) -> tuple[list[dict], list[str]]:
    problems = []
    if source == "sec":
        url = discover_sec(fetch(SEC_INDEX, source))
        # Dates of individual observations come from workbook table columns;
        # the workbook release itself is dated by the latest completed quarter.
        filename = urlparse(url).path.lower()
        match = re.search(r"(20\d{2})-q([1-4])", filename)
        if not match:
            raise SourceFormatError("SEC workbook filename has no validated year/quarter")
        # SEC workbook URL identifies its observation period, but not the
        # publication day; preserve that uncertainty rather than invent one.
        return parse_sec_tables(fetch(url, source), source_url=url, published_on=""), problems
    index = KPMG_INDEX if source == "kpmg" else ACG_INDEX
    seeds = KPMG_SEEDS if source == "kpmg" else ACG_SEEDS
    try:
        discovered = discover_press(fetch(index, source), source)
        if not discovered:
            problems.append(f"{source} index accessible but no relevant releases discovered")
    except Exception as exc:
        discovered = []
        problems.append(f"{source} index: {type(exc).__name__}: {exc}")
    candidates = list(dict.fromkeys((*seeds, *discovered)))[:12]
    obs = {}
    for url in candidates:
        try:
            parsed = parse_kpmg_h1(fetch(url, source), source_url=url) if source == "kpmg" else parse_acg_quarter(fetch(url, source), source_url=url)
            for row in parsed:
                key = (row["metric"], row["period_end"])
                if key in obs and (obs[key]["value"] != row["value"] or obs[key]["sample_count"] != row["sample_count"]):
                    raise SourceFormatError(f"Conflicting {source} records for {key}")
                obs[key] = row
        except Exception as exc:
            problems.append(f"{url}: {type(exc).__name__}: {exc}")
    if not obs:
        raise SourceFormatError("No complete supported reports parsed: " + "; ".join(problems[:4]))
    return list(obs.values()), problems


def persist_source(source: str, new: pd.DataFrame, path: Path) -> dict:
    if path.exists():
        old = validate_observations(pd.read_csv(path, keep_default_na=False).to_dict("records"), source)
        if new.period_end.max() < old.period_end.max():
            raise SourceFormatError("New source is older than retained data")
        # Retain historical records when release index pagination changes.
        prior = old.set_index(["metric", "period_end"])
        incoming = new.set_index(["metric", "period_end"])
        for key in prior.index.intersection(incoming.index):
            previous, current = prior.loc[key], incoming.loc[key]
            if (previous["value"] != current["value"] or previous["sample_count"] != current["sample_count"]
                    or previous["population"] != current["population"]):
                raise SourceFormatError(f"Published {source} observation changed; review required: {key}")
        # Preserve the first validated source/provenance for unchanged periods.
        both = pd.concat([old, new], ignore_index=True)
        both = both.drop_duplicates(["metric", "period_end"], keep="first")
        validated = validate_observations(both.to_dict("records"), source)
        changed = not validated.to_csv(index=False).strip() == old.to_csv(index=False).strip()
    else:
        validated = new
        changed = True
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bundle({path: validated.to_csv(index=False).encode("utf-8")}, transaction_key=path)
    return {"source": source, "status": "updated" if changed else "unchanged", "rows": len(validated),
            "latest_period": str(validated.period_end.max()), "file": str(path)}


def run(*, out_dir: Path, selected=SOURCES) -> list[dict]:
    if out_dir.resolve() == PRODUCTION.resolve() and os.environ.get("AI_MACRO_MODE") != "automation":
        raise PermissionError("Publishing PE industry history requires authorized automation mode")
    results = []
    for source in selected:
        path = out_dir / f"pe_industry_{source}.csv"
        try:
            rows, warnings = source_candidate(source)
            frame = validate_observations(rows, source)
            result = persist_source(source, frame, path)
            result["unparsed_releases"] = len(warnings)
            result["sample_issues"] = warnings[:3]
        except Exception as exc:
            result = {"source": source, "status": "retained_on_failure" if path.exists() else "unavailable",
                      "error": f"{type(exc).__name__}: {exc}", "file": str(path)}
        results.append(result)
        print(json.dumps(result, sort_keys=True), flush=True)
    return results


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-dir", type=Path, default=STAGING)
    p.add_argument("--only", default=",".join(SOURCES))
    args = p.parse_args(argv)
    selected = tuple(x.strip().lower() for x in args.only.split(",") if x.strip())
    if not selected or len(set(selected)) != len(selected) or not set(selected) <= set(SOURCES):
        p.error(f"--only must contain unique sources from {SOURCES}")
    if args.out_dir.resolve() == PRODUCTION.resolve():
        p.error("Production publication requires the established authorized automation pipeline; staging only")
    results = run(out_dir=args.out_dir, selected=selected)
    return 0 if any(x["status"] in {"updated", "unchanged"} for x in results) else 1


if __name__ == "__main__":
    sys.exit(main())
