"""Broad public-pension private equity disclosure ingestion and refresh."""

from __future__ import annotations

from datetime import date, datetime, timezone
from html.parser import HTMLParser
from io import BytesIO, StringIO
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pandas as pd
from pypdf import PdfReader

from analytics.private_capital import (
    build_private_capital_realization,
    validate_private_capital_snapshot,
    validate_broad_pe_snapshot,
)
from config.deployment import repository_writes_enabled
from helpers.atomic_io import atomic_write_bundle

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_CAPITAL_REFRESH_VERSION = "broad-pe-wsib-calpers-v3"
INDEX_URL = "https://www.sib.wa.gov/reports.html"
CSV_PATH = ROOT / "data/private_capital/wsib_fund_performance.csv"
METADATA_PATH = ROOT / "data/private_capital/wsib_metadata.json"
CALPERS_URL = "https://www.calpers.ca.gov/investments/about-investment-office/investment-organization/pep-fund-performance"
CALPERS_CSV_PATH = ROOT / "data/private_capital/calpers_fund_performance.csv"
CALPERS_METADATA_PATH = ROOT / "data/private_capital/calpers_metadata.json"
COLUMNS = ["Manager", "Fund", "Vintage", "Exposure Tier", "Capital Committed",
           "Paid In Capital", "Distributions", "NAV", "Net IRR", "Source As Of"]
PDF_PATH = re.compile(r"^/docs/reports/quarterly/ir(\d{6})\.pdf$", re.I)
DATE_IN_ROW = re.compile(r"^(?P<fund>.+?)\s+(?P<started>\d{1,2}/\d{1,2}/\d{4})\s+(?P<values>.+)$")
AMOUNT = r"(?:\(?-?\d[\d,]*(?:\.\d+)?\)?|-)"
ROW_VALUES = re.compile(
    rf"^(?P<committed>{AMOUNT})\s+(?P<paid>{AMOUNT})\s+"
    rf"(?P<unfunded>{AMOUNT})\s+(?P<nav>{AMOUNT})\s+"
    rf"(?P<distributed>{AMOUNT})\s+(?P<total>{AMOUNT})\s+"
    rf"(?P<multiple>\d+(?:\.\d+)?x|N/A)\s+(?P<gain>{AMOUNT})\s+"
    r"(?P<irr>\(?-?\d+(?:\.\d+)?%\)?|N/A)$",
    re.I,
)
MANAGERS = (
    (re.compile(r"^Francisco Partners\b", re.I), "Francisco Partners"),
    (re.compile(r"^Thoma Bravo\b", re.I), "Thoma Bravo"),
    (re.compile(r"^Silver Lake Partners\b", re.I), "Silver Lake"),
    (re.compile(r"^Insight (?:Venture Partners|Partners)\b", re.I), "Insight Partners"),
    (re.compile(r"^Sequoia (?:Capital )?Global Growth\b", re.I), "Sequoia"),
    (re.compile(r"^General Catalyst\b", re.I), "General Catalyst"),
    (re.compile(r"^Menlo (?:Ventures|Inflection|Olympic)\b", re.I), "Menlo Ventures"),
    (re.compile(r"^New Enterprise Associates\b", re.I), "NEA"),
)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self.hrefs.extend(value for key, value in attrs if key.lower() == "href" and value)


def latest_report(index_html: str, *, today: date | None = None) -> tuple[date, str]:
    links = _Links()
    links.feed(index_html)
    candidates = []
    for href in links.hrefs:
        url = urljoin(INDEX_URL, href)
        parsed = urlparse(url)
        match = PDF_PATH.fullmatch(parsed.path)
        if parsed.hostname != "www.sib.wa.gov" or not match:
            continue
        try:
            as_of = datetime.strptime(match.group(1), "%m%d%y").date()
        except ValueError:
            continue
        if as_of <= (today or date.today()):
            candidates.append((as_of, url))
    if not candidates:
        raise ValueError("WSIB index contains no dated Private Equity IRR PDF links")
    return max(candidates)


def _amount(value: str) -> float:
    if value == "-":
        return 0.0
    value = value.replace(",", "")
    return -float(value[1:-1]) if value.startswith("(") else float(value)


def _manager(fund: str) -> str:
    """Approximate fund-family grouping; the exact reported Fund title is authoritative."""
    for pattern, name in MANAGERS:
        if pattern.search(fund):
            return name
    # The source has no distinct manager field. This is a grouping aid only.
    return " ".join(fund.split()[:2])


def parse_report(pdf_bytes: bytes, *, as_of: date) -> pd.DataFrame:
    if not pdf_bytes.startswith(b"%PDF") or len(pdf_bytes) > 12_000_000:
        raise ValueError("WSIB response is not a plausible report PDF")
    reader = PdfReader(BytesIO(pdf_bytes))
    if not 2 <= len(reader.pages) <= 25:
        raise ValueError("WSIB report page count changed")
    intro = reader.pages[0].extract_text() or ""
    expected = f"{as_of:%B} {as_of.day}, {as_of.year}"
    if expected.casefold() not in " ".join(intro.split()).casefold():
        raise ValueError("WSIB PDF date does not match the report link")

    rows = []
    for page in reader.pages[1:]:
        for raw in page.extract_text(extraction_mode="layout", layout_mode_space_vertically=False).splitlines():
            line = " ".join(raw.split())
            candidate = DATE_IN_ROW.fullmatch(line)
            if candidate is None:
                continue
            fund = candidate.group("fund")
            manager = _manager(fund)
            started = datetime.strptime(candidate.group("started"), "%m/%d/%Y").date()
            if started > as_of or started.year < 2012:
                continue
            values = ROW_VALUES.fullmatch(candidate.group("values"))
            if values is None:
                raise ValueError(f"Unrecognized WSIB fund row: {fund}")
            paid = _amount(values.group("paid"))
            if paid <= 0:
                continue
            nav = _amount(values.group("nav"))
            distributed = _amount(values.group("distributed"))
            total = _amount(values.group("total"))
            if nav < 0 or distributed < 0 or abs(nav + distributed - total) > 2:
                raise ValueError(f"WSIB fund cash-flow columns do not reconcile: {fund}")
            irr = values.group("irr")
            rows.append({
                "Manager": manager, "Fund": fund, "Vintage": started.year,
                "Exposure Tier": "Disclosed PE holding",
                "Capital Committed": _amount(values.group("committed")),
                "Paid In Capital": paid, "Distributions": distributed,
                "NAV": nav,
                "Net IRR": None if irr == "N/A" else _amount(irr.replace("%", "")),
                "Source As Of": as_of.isoformat(),
            })
    frame = pd.DataFrame(rows, columns=COLUMNS)
    validate_broad_pe_snapshot(frame, metadata={"cohort_scope": "broad_pe", "source_as_of": as_of.isoformat()})
    return frame.sort_values(["Vintage", "Manager", "Fund"], ascending=[False, True, True]).reset_index(drop=True)


CALSTRS_ROW = re.compile(
    rf"^(?P<fund>.+?)\s+(?P<year>(?:19|20)\d{{2}})\s+"
    rf"(?P<committed>{AMOUNT})\s+(?P<paid>{AMOUNT})\s+"
    rf"(?P<distributed>{AMOUNT})\s+(?P<nav>{AMOUNT})\s+"
    r"(?P<irr>\(?-?\d+(?:\.\d+)?\)?|N/A)$",
    re.I,
)
CALSTRS_NO_CASH = re.compile(
    rf"^.+?\s+(?:19|20)\d{{2}}\s+{AMOUNT}\s+-\s+-\s+0\.00$"
)


def parse_calstrs_pdf(pdf_bytes: bytes, *, as_of: date) -> pd.DataFrame:
    """Rebuild the bundled CalSTRS broad-cohort CSV from its original PDF."""
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("CalSTRS source is not a PDF")
    reader = PdfReader(BytesIO(pdf_bytes))
    if not 2 <= len(reader.pages) <= 25:
        raise ValueError("CalSTRS PDF page count changed")
    expected = f"As of {as_of:%B} {as_of.day}, {as_of.year}"
    if expected.lower() not in " ".join((reader.pages[0].extract_text() or "").split()).lower():
        raise ValueError("CalSTRS report observation date mismatch")
    rows = []
    observed = 0
    for page in reader.pages:
        for raw in (page.extract_text(extraction_mode="layout", layout_mode_space_vertically=False) or "").splitlines():
            line = " ".join(raw.split())
            if not re.match(r"^.+?\s+(?:19|20)\d{2}\s", line):
                continue
            observed += 1
            match = CALSTRS_ROW.fullmatch(line)
            if match is None:
                if CALSTRS_NO_CASH.fullmatch(line):
                    continue
                raise ValueError(f"Unrecognized CalSTRS holding: {line}")
            details = match.groupdict()
            year = int(details["year"])
            paid = _amount(details["paid"])
            if year < 2012 or paid <= 0:
                continue
            irr = details["irr"]
            rows.append({
                "Manager": _manager(details["fund"]), "Fund": details["fund"],
                "Vintage": year, "Exposure Tier": "Disclosed PE holding",
                "Capital Committed": _amount(details["committed"]),
                "Paid In Capital": paid, "Distributions": _amount(details["distributed"]),
                "NAV": _amount(details["nav"]),
                "Net IRR": None if irr.upper() == "N/A" else _amount(irr),
                "Source As Of": as_of.isoformat(),
            })
    if observed < 150:
        raise ValueError("CalSTRS PDF extraction omitted too many holdings")
    frame = pd.DataFrame(rows, columns=COLUMNS)
    validate_broad_pe_snapshot(frame, metadata={"cohort_scope": "broad_pe", "source_as_of": as_of.isoformat()})
    return frame.sort_values(["Vintage", "Manager", "Fund"], ascending=[False, True, True]).reset_index(drop=True)


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, value):
        self.parts.append(value)


def _financial_number(value, *, missing_ok=False) -> float | None:
    raw = str(value).strip().replace("$", "").replace(",", "").replace("%", "").replace("−", "-")
    if raw.upper() in {"N/M", "N/A", "NM", "NA", "", "NAN"}:
        if missing_ok:
            return None
        raise ValueError("CalPERS is missing a required cash-flow amount")
    if raw in {"-", "—", "–"}:
        return 0.0
    if not re.fullmatch(r"\(?-?\d+(?:\.\d+)?\)?", raw):
        raise ValueError(f"Unrecognized CalPERS number: {value}")
    return _amount(raw)


def parse_calpers(html: str) -> tuple[date, pd.DataFrame]:
    """Read the dated PE table, ignoring superscript footnotes and other tables."""
    clean = re.sub(r"<(script|style|sup)\b[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    text = _Text()
    text.feed(clean)
    visible = " ".join(" ".join(text.parts).split())
    dated = re.search(
        r"table below reflects.{0,240}?as of\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})",
        visible, flags=re.I,
    )
    if dated is None:
        raise ValueError("CalPERS PE table observation date was not found")
    as_of = datetime.strptime(re.sub(r",\s*", ", ", dated.group(1)), "%B %d, %Y").date()
    required = {"fund", "vintageyear", "capitalcommitted", "cashin", "cashout", "cashoutremainingvalue", "netirr"}
    tables = pd.read_html(StringIO(clean), keep_default_na=False)
    matching = []
    for table in tables:
        names = [re.sub(r"[^a-z0-9]", "", str(column).lower()) for column in table.columns]
        if required.issubset(names):
            table.columns = names
            matching.append(table)
    if len(matching) != 1:
        raise ValueError("CalPERS did not return one recognizable PE cash-flow table")
    rows = []
    for _, record in matching[0].iterrows():
        fund = str(record["fund"]).strip()
        if not fund or fund.casefold().startswith(("total", "subtotal")):
            continue
        manager = _manager(fund)
        year = _financial_number(record["vintageyear"])
        if year < 2012:
            continue
        paid = _financial_number(record["cashin"])
        if paid <= 0:
            continue
        distributed = _financial_number(record["cashout"])
        total_value = _financial_number(record["cashoutremainingvalue"])
        nav = total_value - distributed
        if nav < -2:
            raise ValueError(f"CalPERS distributions exceed total fund value: {fund}")
        rows.append({
            "Manager": manager, "Fund": fund, "Vintage": year,
            "Exposure Tier": "Disclosed PE holding",
            "Capital Committed": _financial_number(record["capitalcommitted"]),
            "Paid In Capital": paid, "Distributions": distributed,
            "NAV": max(0.0, nav), "Net IRR": _financial_number(record["netirr"], missing_ok=True),
            "Source As Of": as_of.isoformat(),
        })
    frame = pd.DataFrame(rows, columns=COLUMNS)
    validate_broad_pe_snapshot(frame, metadata={"cohort_scope": "broad_pe", "source_as_of": as_of.isoformat()})
    return as_of, frame.sort_values(["Vintage", "Manager", "Fund"], ascending=[False, True, True]).reset_index(drop=True)


def _fetch(url: str, *, timeout=25, limit=12_000_000) -> bytes:
    request = Request(url, headers={"User-Agent": "AI Macro research refresh (public investment disclosures)"})
    with urlopen(request, timeout=timeout) as response:
        content = response.read(limit + 1)
    if len(content) > limit:
        raise ValueError("Private-fund disclosure response exceeds the expected size")
    return content


def _existing(data_path: Path, metadata_path: Path) -> tuple[pd.DataFrame, dict]:
    try:
        metadata = json.loads(metadata_path.read_text())
        frame = pd.read_csv(data_path)
        validate_broad_pe_snapshot(frame, metadata=metadata)
        return frame, metadata
    except (OSError, ValueError, KeyError, TypeError):
        return pd.DataFrame(), {}


def _save_snapshot(frame, metadata, *, data_path, metadata_path) -> dict:
    as_of = validate_broad_pe_snapshot(frame, metadata=metadata)
    prior, prior_meta = _existing(data_path, metadata_path)
    if not prior.empty:
        if as_of < pd.Timestamp(prior_meta["source_as_of"]):
            raise ValueError("Rejected a regressed private-fund report; retained newer records")
        if len(frame) < len(prior) * 0.6:
            raise ValueError("Private-fund coverage fell by more than 40%; retained prior records")
        if frame[COLUMNS].reset_index(drop=True).equals(prior[COLUMNS].reset_index(drop=True)):
            return {"status": "checked_current", "source_as_of": metadata["source_as_of"], "rows": len(frame)}
    atomic_write_bundle(
        {data_path: frame[COLUMNS].to_csv(index=False).encode(),
         metadata_path: (json.dumps(metadata, indent=2) + "\n").encode()},
        transaction_key=data_path,
    )
    return {"status": "updated", "source_as_of": metadata["source_as_of"], "rows": len(frame)}


def _metadata(*, source_short, source_url, as_of) -> dict:
    return {
        "source": "Washington State Investment Board Private Equity IRR" if source_short == "WSIB" else "CalPERS Private Equity Program Fund Performance Review",
        "source_short": source_short, "source_url": source_url,
        "source_as_of": as_of.isoformat(), "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "cohort_scope": "broad_pe", "year_basis": "initial investment year",
        "selection_method": f"All reported {source_short} private-equity fund holdings with an initial investment year of 2012 or later and positive paid-in capital; no manager- or sector-based filter.",
        "important_limitations": [
            "These are one pension investor's holdings, not an industry-wide fund-return estimate.",
            "Valuations are reported fund NAV, not transaction valuation multiples.",
            "Investment year reflects the reporting LP's first investment and may differ from fund vintage.",
        ] + (["CalPERS lists active partnerships; exited partnerships are excluded."] if source_short == "CalPERS" else []),
    }


def _refresh_wsib() -> dict:
    as_of, url = latest_report(_fetch(INDEX_URL).decode("utf-8"))
    content = _fetch(url, timeout=50)
    checksum = hashlib.sha256(content).hexdigest()
    prior, prior_meta = _existing(CSV_PATH, METADATA_PATH)
    if not prior.empty and prior_meta.get("source_pdf_sha256") == checksum and prior_meta["source_as_of"] == as_of.isoformat():
        return {"status": "checked_current", "source_as_of": as_of.isoformat(), "rows": len(prior)}
    frame = parse_report(content, as_of=as_of)
    metadata = _metadata(source_short="WSIB", source_url=url, as_of=as_of)
    metadata.update(index_url=INDEX_URL, source_pdf_sha256=checksum, fund_count=len(frame), manager_count=int(frame["Manager"].nunique()))
    return _save_snapshot(frame, metadata, data_path=CSV_PATH, metadata_path=METADATA_PATH)


def _refresh_calpers() -> dict:
    as_of, frame = parse_calpers(_fetch(CALPERS_URL).decode("utf-8"))
    metadata = _metadata(source_short="CalPERS", source_url=CALPERS_URL, as_of=as_of)
    metadata.update(fund_count=len(frame), manager_count=int(frame["Manager"].nunique()))
    return _save_snapshot(frame, metadata, data_path=CALPERS_CSV_PATH, metadata_path=CALPERS_METADATA_PATH)


def _retained_status() -> dict:
    try:
        realization = build_private_capital_realization()
    except (OSError, ValueError, KeyError, TypeError):
        return {"source": "", "source_url": "", "source_as_of": "", "rows": 0, "snapshot_signature": ""}
    funds = realization["funds"]
    metadata = realization["metadata"]
    return {
        "source": metadata.get("source_short", ""), "source_url": metadata.get("source_url", ""),
        "source_as_of": funds["Source As Of"].max().date().isoformat() if not funds.empty else "",
        "rows": len(funds),
        "snapshot_signature": hashlib.sha256(funds[COLUMNS].to_csv(index=False, date_format="%Y-%m-%d").encode()).hexdigest() if not funds.empty else "",
    }


def refresh_private_capital(*, force_refresh: bool = False, allow_live: bool = False) -> dict:
    """Check each provider independently; a blocked optional provider cannot discard good data."""
    report = {"source_mode": "retained", **_retained_status()}
    if not (force_refresh and allow_live and repository_writes_enabled()):
        return report
    providers = {}
    for name, refresh in (("WSIB", _refresh_wsib), ("CalPERS", _refresh_calpers)):
        try:
            providers[name] = refresh()
        except HTTPError as exc:
            providers[name] = {"status": "blocked" if exc.code in {401, 403} else "failed", "http_status": exc.code, "detail": f"{name}: HTTP {exc.code} {exc.reason}; retained prior records"}
        except Exception as exc:
            providers[name] = {"status": "failed", "detail": f"{name}: {type(exc).__name__}: {exc}"}
    successful = [row for row in providers.values() if row["status"] in {"updated", "checked_current"}]
    warnings = [row["detail"] for row in providers.values() if row.get("detail")]
    report.update(_retained_status())
    report.update(providers=providers, provider_warnings=warnings,
                  source_mode="live_refresh" if any(row["status"] == "updated" for row in successful) else "checked_current" if successful else "retained_fallback")
    if not successful:
        report["error"] = "; ".join(warnings)
    return report
