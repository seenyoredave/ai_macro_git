"""Strict source-to-observation parsing for public PE statistics.

No inference from unspecified numbers: only known table names, populations,
periods and report-level statements are admitted.
"""

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
import re

from bs4 import BeautifulSoup
import openpyxl


class SourceFormatError(ValueError):
    """A source changed format or does not support the claimed observation."""


def visible_text(data: bytes) -> str:
    soup = BeautifulSoup(data.decode("utf-8", errors="replace"), "html.parser")
    for node in soup(("script", "style", "noscript", "svg")):
        node.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())


def _numeric(value) -> float:
    if isinstance(value, bool) or value is None:
        raise SourceFormatError("Missing financial value")
    if isinstance(value, (int, float)):
        n = float(value)
    else:
        txt = str(value).strip().replace(",", "").replace("$", "")
        if not re.fullmatch(r"-?\d+(?:\.\d+)?", txt):
            raise SourceFormatError(f"Non-numeric source cell: {value!r}")
        n = float(txt)
    if not (n > 0 and n < 1e8):
        raise SourceFormatError(f"Out-of-range financial value: {value!r}")
    return n


def _qtr(value) -> str | None:
    match = re.fullmatch(r"(20\d{2})\s*Q([1-4])", str(value or "").strip(), re.I)
    return f"{match.group(1)}Q{match.group(2)}" if match else None


def _pe_row(value) -> bool:
    return bool(re.fullmatch(r"private\s+equity\s+funds?\s*[*¹²³]?", str(value or "").strip(), re.I))


SEC_SHEETS = {
    "fund_count": ("Tab.1.1", "funds"),
    "gross_assets_usd_bn": ("Tab.2.1", "USD billions"),
    "net_assets_usd_bn": ("Tab.2.3", "USD billions"),
}


def parse_sec_tables(data: bytes, *, source_url: str, published_on: str) -> list[dict]:
    if not data.startswith(b"PK\x03\x04"):
        raise SourceFormatError("SEC response is not an XLSX workbook")
    book = openpyxl.load_workbook(BytesIO(data), read_only=True, data_only=True)
    try:
        observations = []
        for metric, (sheet_name, unit) in SEC_SHEETS.items():
            if sheet_name not in book.sheetnames:
                raise SourceFormatError(f"Missing SEC table {sheet_name}")
            rows = list(book[sheet_name].iter_rows(max_row=100, values_only=True))
            candidates = []
            for i, cells in enumerate(rows):
                for j, value in enumerate(cells):
                    if not _pe_row(value):
                        continue
                    periods = []
                    # Tables may carry title, footnote and unit rows above the
                    # numeric grid. Bind to the *nearest* quarter-bearing header.
                    for prev in range(i - 1, max(-1, i - 13), -1):
                        periods = [(_qtr(c), k) for k, c in enumerate(rows[prev])]
                        periods = [(p, k) for p, k in periods if p]
                        if len(periods) >= 4:
                            break
                    if len(periods) < 4:
                        continue
                    values = {}
                    for period, column in periods:
                        if column <= j or column >= len(cells) or period in values:
                            raise SourceFormatError(f"Ambiguous SEC {sheet_name} period columns")
                        values[period] = _numeric(cells[column])
                    if len(values) >= 4:
                        candidates.append(values)
            if len(candidates) != 1:
                raise SourceFormatError(f"Expected one PE row in {sheet_name}, found {len(candidates)}")
            for period, value in candidates[0].items():
                year, quarter = int(period[:4]), int(period[-1])
                end_month = quarter * 3
                end_day = (date(year + 1, 1, 1) if end_month == 12 else date(year, end_month + 1, 1)).toordinal() - 1
                period_end = date.fromordinal(end_day).isoformat()
                observations.append({"source": "SEC Form PF", "metric": metric, "period": period,
                    "period_end": period_end, "geography": "United States", "value": value,
                    "unit": unit, "population": "SEC Form PF-reported private equity funds",
                    "sample_count": "", "precision": "reported", "source_url": source_url,
                    "published_on": published_on, "definition": f"SEC Private Fund Statistics {sheet_name}, Private Equity Fund row"})
        by_key = {(o["metric"], o["period"]): o["value"] for o in observations}
        latest = max(o["period"] for o in observations)
        if latest < "2025Q4" or any((key, latest) not in by_key for key in SEC_SHEETS):
            raise SourceFormatError("SEC workbook does not include a complete 2025Q4-or-newer snapshot")
        for period in {o["period"] for o in observations}:
            if not all((key, period) in by_key for key in SEC_SHEETS):
                raise SourceFormatError(f"SEC table coverage differs in {period}")
            funds = by_key["fund_count", period]
            gross = by_key["gross_assets_usd_bn", period]
            net = by_key["net_assets_usd_bn", period]
            if not (1000 <= funds <= 100000 and funds.is_integer() and 500 <= gross <= 100000
                    and 200 <= net <= gross * 1.02):
                raise SourceFormatError(f"Implausible SEC PE observations in {period}")
        return sorted(observations, key=lambda o: (o["period_end"], o["metric"]))
    finally:
        book.close()


def _release_year_quarter(text: str) -> tuple[int, int]:
    matches = re.findall(r"\bQ([1-4])\s*['’]?\s*(20\d\d|\d\d)\b", text[:2500], re.I)
    if not matches:
        raise SourceFormatError("Release quarter not found in beginning of article")
    q, year = matches[0]
    year = int(year)
    if year < 100:
        year += 2000
    return year, int(q)


def _release_date(text: str, year: int) -> str:
    # ACG releases carry e.g. 'CHICAGO – August 27, 2026'. KPMG carries '27 July 2026'.
    for match in re.finditer(r"\b(?:\d{1,2}\s+[A-Z][a-z]+\s+20\d\d|[A-Z][a-z]+\s+\d{1,2},?\s+20\d\d)\b", text[:2500]):
        sample = match.group()
        for fmt in ("%d %B %Y", "%B %d, %Y", "%B %d %Y"):
            try:
                d = datetime.strptime(sample, fmt).date()
                if d.year == year:
                    return d.isoformat()
            except ValueError:
                continue
    raise SourceFormatError("Release publication date could not be verified")


def _amount(raw: str, unit: str) -> float:
    value = float(raw.replace(",", ""))
    if unit.lower().startswith("trillion"):
        value *= 1000
    return value


def _number_and_count(text: str, pattern: str) -> tuple[float, int]:
    match = re.search(pattern, text, re.I)
    if match is None:
        raise SourceFormatError("Definition-matched value and count not found")
    return _amount(match.group("amount"), match.group("unit")), int(match.group("count").replace(",", ""))


AMOUNT = r"\$\s*(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>trillion|billion)"
COUNT = r"(?P<count>\d[\d,]*)"


def parse_kpmg_h1(data: bytes, *, source_url: str) -> list[dict]:
    text = visible_text(data)
    if "private equity" not in text.lower() or "global" not in text.lower():
        raise SourceFormatError("Not a global PE report")
    year, q = _release_year_quarter(text)
    if q != 2 or not re.search(rf"\b(?:first half of|mid.year|first six months of)\s+{year}\b|\bmid.year\b", text[:4500], re.I):
        raise SourceFormatError("Not a verified H1/Q2 report")
    published = _release_date(text, year)
    # Only report-level *global* statements are acceptable, not US or sector figures.
    deal_patterns = [
        rf"global PE (?:deal value sat at|investment[^.]*?to)\s*{AMOUNT}\s+across\s+{COUNT}\s+deals",
        rf"mid.year total of PE investment to\s*{AMOUNT}\s+across\s+{COUNT}\s+deals",
    ]
    exit_patterns = [
        rf"global PE exit (?:value was at|flow was)\s*{AMOUNT}\s+across\s+{COUNT}\s+exits",
        rf"global exit flow was\s*{AMOUNT}\s+across\s+{COUNT}\s+exits",
    ]
    fundraising_patterns = [
        rf"(?:at mid.year,?\s*)?global (?:PE )?fundraising was (?:at )?{AMOUNT}\s+across\s+{COUNT}\s+funds",
    ]
    def find(patterns):
        for p in patterns:
            try:
                return _number_and_count(text, p)
            except SourceFormatError:
                continue
        raise SourceFormatError("No unambiguous global H1 value/count pair")
    deal = find(deal_patterns)
    exits = find(exit_patterns)
    fundraising = find(fundraising_patterns)
    period_end = f"{year}-06-30"
    records = []
    for metric, (value, count), entity in (
        ("deal_value", deal, "deals"), ("exit_value", exits, "exits"),
        ("fundraising", fundraising, "funds"),
    ):
        if not (0 < value < 20000 and 1 <= count <= 200000):
            raise SourceFormatError(f"Implausible {metric} in {year}")
        records.append({"source": "KPMG Pulse of Private Equity", "metric": metric,
            "period": f"H1 {year}", "period_end": period_end, "geography": "Global",
            "value": value, "unit": "USD billions", "population": "Global private equity",
            "sample_count": count, "precision": "rounded" if metric == "deal_value" and float(value) % 1000 == 0 else "reported",
            "source_url": source_url, "published_on": published,
            "definition": f"Global H1 {entity} value and count in KPMG Q2 {year} release"})
    return records


def parse_acg_quarter(data: bytes, *, source_url: str) -> list[dict]:
    text = visible_text(data)
    if "GF Data" not in text or "completed transactions" not in text:
        raise SourceFormatError("Not a GF Data transaction release")
    year, quarter = _release_year_quarter(text)
    published = _release_date(text, year)
    count_match = re.search(r"\breported\s+(\d[\d,]*)\s+completed transactions\s+(?:during|in)\s+(?:the\s+)?(?:first|second|third|fourth)\s+quarter", text, re.I)
    if not count_match:
        raise SourceFormatError("Same-quarter transaction count not found")
    count = int(count_match.group(1).replace(",", ""))
    valuation_patterns = [
        r"average valuation of\s+(\d+(?:\.\d+)?)x\s+trailing\s+12.month\s+\(TTM\)\s+adjusted EBITDA",
        r"average purchase price multiples (?:declined|rose|increased|fell)[^.]{0,110}?\bto\s+(\d+(?:\.\d+)?)x\s+trailing\s+12.month\s+\(TTM\)\s+adjusted EBITDA",
    ]
    values = [re.search(p, text, re.I) for p in valuation_patterns]
    match = next((x for x in values if x), None)
    if match is None:
        raise SourceFormatError("Same-quarter adjusted EBITDA entry multiple not found")
    value = float(match.group(1))
    if not (1 <= count <= 10000 and 2 <= value <= 30):
        raise SourceFormatError("GF Data sample or multiple implausible")
    month = quarter * 3
    end = date.fromordinal((date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)).toordinal() - 1)
    return [{"source": "GF Data / ACG", "metric": "entry_ev_ebitda_ttm_adjusted",
        "period": f"{year}Q{quarter}", "period_end": end.isoformat(),
        "geography": "Not specified", "value": value, "unit": "EV/EBITDA multiple",
        "population": "GF Data contributing PE-sponsored middle-market transactions ($1m-$500m EV)",
        "sample_count": count, "precision": "mean", "source_url": source_url,
        "published_on": published, "definition": "Mean purchase EV / trailing 12-month adjusted EBITDA, contributing-deal sample"}]
