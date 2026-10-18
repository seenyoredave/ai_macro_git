"""Strict source-to-observation parsing for public PE statistics.

No inference from unspecified numbers: only known table names, populations,
periods and report-level statements are admitted.
"""

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import openpyxl


class SourceFormatError(ValueError):
    """A source changed format or does not support the claimed observation."""


def visible_text(data: bytes) -> str:
    soup = BeautifulSoup(data.decode("utf-8", errors="replace"), "html.parser")
    for node in soup(("script", "style", "noscript", "svg")):
        node.decompose()
    text = " ".join(soup.get_text(" ", strip=True).split())
    # Publisher navigation, consent panels and site chrome can precede the
    # article by thousands of characters. Anchor period/number extraction to
    # the editorial headline, while preserving the article's downstream text.
    for header in soup.find_all("h1"):
        title = " ".join(header.get_text(" ", strip=True).split())
        if re.search(r"\b(?:GF Data|private equity|PE market|PE investment)\b", title, re.I):
            pos = text.find(title)
            if pos >= 0:
                return text[pos:]
    return text


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
                if not period.endswith("Q4"):
                    continue  # Form PF private-equity coverage is most comparable at year-end.
                year, quarter = int(period[:4]), int(period[-1])
                end_month = quarter * 3
                end_day = (date(year + 1, 1, 1) if end_month == 12 else date(year, end_month + 1, 1)).toordinal() - 1
                period_end = date.fromordinal(end_day).isoformat()
                observations.append({"source": "SEC Form PF", "metric": metric, "period": period,
                    "period_end": period_end, "geography": "SEC Form PF reporting population", "value": value,
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


def _kpmg_release_year(text: str, source_url: str) -> int:
    """Tie the H1 reporting period to the publisher's dated Q2 release.

    KPMG sites can prepend large navigation, modal and account blocks to the
    article. A fixed offset into flattened HTML is not an economic date.
    """
    match = re.search(r"/media/press-releases/(20\d{2})/(\d{2})/", source_url)
    if match is None:
        raise SourceFormatError("KPMG release URL has no dated reporting context")
    year, release_month = int(match.group(1)), int(match.group(2))
    if not 7 <= release_month <= 9:
        raise SourceFormatError("KPMG release does not belong to the H1 reporting window")
    q2 = rf"\bQ2\s*['’]?\s*(?:{year}|{year % 100:02d})\b"
    # Require an explicit *current* Q2 marker, not a Q1 reference in a
    # comparison. Key-highlights headings and report leads both qualify.
    marker = rf"(?:\b(?:in|during|of|end of)\s+{q2}|{q2}\s*[-—–:]?\s*(?:key highlights|pulse of private equity)|{q2}\s+(?:report|results))"
    if not re.search(marker, text, re.I):
        raise SourceFormatError(f"Current KPMG Q2 {year} report marker not found")
    return year


def _acg_release_period(data: bytes, text: str) -> tuple[int, int]:
    """Read the named GF Data report, not an unrelated comparison quarter."""
    soup = BeautifulSoup(data.decode("utf-8", errors="replace"), "html.parser")
    titles = [" ".join(h.get_text(" ", strip=True).split()) for h in soup.select("h1")]
    # 2025 report titles explicitly specify the quarter and year.
    headings = [title for title in titles if re.search(r"\bGF Data\b", title, re.I)]
    pattern = r"\bQ([1-4])\s*(20\d{2})\s*M\s*&\s*A\s+and\s+Leverage\s+Reports\b"
    matches = [re.search(pattern, title, re.I) for title in headings]
    matches = [m for m in matches if m]
    if len({(m.group(1), m.group(2)) for m in matches}) == 1 and matches:
        return int(matches[0].group(2)), int(matches[0].group(1))
    # 2026 releases identify the period in the dated report-announcement lead.
    report = re.search(r"\bGF Data.{0,125}?\b(?:released|releases)\s+(?:its\s+)?Q([1-4])\s*(20\d{2})\s*M\s*&\s*A\s+and\s+Leverage\s+Reports\b", text, re.I)
    if report:
        return int(report.group(2)), int(report.group(1))
    raise SourceFormatError("GF Data report quarter/year not identified in its title or announcement")


def _release_date(text: str, year: int) -> str:
    for match in re.finditer(r"\b(?:\d{1,2}\s+[A-Z][a-z]+\s+20\d\d|[A-Z][a-z]+\s+\d{1,2},?\s+20\d\d)\b", text):
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
    return round(value * (1000 if unit.lower() == "trillion" else 1), 5)


AMOUNT = r"\$\s*(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>trillion|billion)"
COUNT = r"(?P<count>\d[\d,]*)"


def _number_and_count(text: str, pattern: str) -> tuple[float, int]:
    match = re.search(pattern, text, re.I)
    if not match:
        raise SourceFormatError("Definition-matched value and count not found")
    return _amount(match.group("amount"), match.group("unit")), int(match.group("count").replace(",", ""))


def _first_pair(text: str, patterns: list[str]) -> tuple[float, int]:
    for pattern in patterns:
        try:
            return _number_and_count(text, pattern)
        except SourceFormatError:
            pass
    raise SourceFormatError("No unambiguous global H1 value/count pair")


def parse_kpmg_h1(data: bytes, *, source_url: str) -> list[dict]:
    source = urlparse(source_url)
    if source.scheme != "https" or source.hostname != "kpmg.com":
        raise SourceFormatError("Invalid source URL")
    text = visible_text(data)
    if not re.search(r"\bglobal\s+(?:private equity|PE)\b", text, re.I):
        raise SourceFormatError("Not a global PE release")
    year = _kpmg_release_year(text, source_url)
    h1_scope = bool(re.search(r"\b(?:mid.year|first half|first six months)\b", text, re.I))
    if year == 2025 and re.search(r"Global PE investment fell from", text, re.I):
        h1_scope = True  # Q1+Q2 global quarters explicitly available for a derived H1.
    if not h1_scope:
        raise SourceFormatError("Not an H1 report")
    published = _release_date(text, year)
    data_by_metric: dict[str, tuple[float, int]] = {}
    if year == 2025:
        # Q2'25 release supplies Q1 + Q2, not a separately stated H1 total.
        # Summation is permitted only with BOTH definition-matched global quarters.
        quarter_pair = re.search(
            r"Global PE investment fell from \$\s*(?P<q1>\d+(?:\.\d+)?)\s+billion across (?P<n1>\d[\d,]*) deals in Q1['’]?25"
            r"\s+to \$\s*(?P<q2>\d+(?:\.\d+)?)\s+billion across (?P<n2>\d[\d,]*) deals in Q2['’]?25",
            text, re.I)
        if quarter_pair is None:
            raise SourceFormatError("KPMG 2025 H1 global quarter pair unavailable")
        if quarter_pair:
            data_by_metric["deal_value"] = (
                round(float(quarter_pair['q1']) + float(quarter_pair['q2']), 5),
                int(quarter_pair['n1'].replace(',', '')) + int(quarter_pair['n2'].replace(',', '')))
        # The 2025 press release does NOT state a global H1 exit value/count
        # pair. Do not borrow the year-end figure or a regional exit subtotal.
        data_by_metric["fundraising"] = _first_pair(text, [
            rf"Global PE fundraising was {AMOUNT} across {COUNT} funds at the end of Q2['’]?25",
        ])
    else:
        data_by_metric["deal_value"] = _first_pair(text, [
            rf"(?:In the first half of {year},\s*)?global PE deal value sat at {AMOUNT} across {COUNT} deals",
            rf"mid.year total of PE investment to {AMOUNT} across {COUNT} deals",
        ])
        data_by_metric["exit_value"] = _first_pair(text, [
            rf"(?:As of the end of Q2['’]?(?:{year % 100:02d}|{year}),?\s*)?global (?:PE )?exit flow was {AMOUNT} across {COUNT} exits",
            rf"At mid.year, global PE exit value was at {AMOUNT} across {COUNT} exits",
        ])
        data_by_metric["fundraising"] = _first_pair(text, [
            rf"At mid.year, global fundraising was at {AMOUNT} across {COUNT} funds",
            rf"global (?:PE )?fundraising was at {AMOUNT} across {COUNT} funds",
        ])
    if not data_by_metric:
        raise SourceFormatError("No supported H1 measures")
    # A release with only some explicit measures is retained as partial history,
    # never filled by unrelated numbers or an annual/rolling-12-month total.
    observations = []
    for metric, (value, count) in data_by_metric.items():
        if not (0 < value < 20000 and 1 <= count <= 200000):
            raise SourceFormatError(f"Implausible {metric} in {year}")
        definition = ("Global H1 deal value/count, Q1 and Q2 reported totals"
                      if year == 2025 and metric == "deal_value" else
                      f"Global H1 {metric} value and count")
        observations.append({"source": "KPMG Pulse of Private Equity", "metric": metric,
            "period": f"H1 {year}", "period_end": f"{year}-06-30", "geography": "Global",
            "value": value, "unit": "USD billions", "population": "Global private equity",
            "sample_count": count, "precision": "derived from stated quarters" if year == 2025 and metric == "deal_value" else
            "rounded" if metric == "deal_value" and value % 1000 == 0 else "reported",
            "source_url": source_url, "published_on": published, "definition": definition})
    return observations


def _acg_coverage(text: str) -> str:
    # GF Data changed the range advertised in its public ACG releases.
    # Do not manufacture a comparable multi-year series across that change.
    matches = re.findall(r"\$\s*(1|10)\s+million\s*[–—-]\s*\$?\s*500\s+million", text, re.I)
    if len(set(matches)) != 1:
        raise SourceFormatError("GF Data enterprise-value population boundary is missing or ambiguous")
    return f"GF Data contributing PE-sponsored transactions (${matches[0]}m-$500m EV)"


def parse_acg_quarter(data: bytes, *, source_url: str) -> list[dict]:
    source = urlparse(source_url)
    if source.scheme != "https" or source.hostname not in {"www.acg.org", "acg.org"}:
        raise SourceFormatError("Invalid source URL")
    text = visible_text(data)
    if "GF Data" not in text or "completed" not in text or "transaction" not in text:
        raise SourceFormatError("Not a GF Data transaction release")
    year, quarter = _acg_release_period(data, text)
    published = _release_date(text, year)
    label = ("first", "second", "third", "fourth")[quarter - 1]
    period_token = rf"(?:{label} quarter|Q{quarter})"
    count_patterns = [
        # A same-quarter count can safely precede a separate YTD sentence;
        # don't inspect the next sentence for attribution.
        rf"(?:reported|reporting)\s+(\d[\d,]*)\s+completed (?:transactions|deals)\s+(?:during|in)\s+(?:the\s+)?{period_token}\b",
    ]
    match = next((hit for pattern in count_patterns
                  if (hit := re.search(pattern, text, re.I))), None)
    if match is None:
        # Some ACG releases describe the quarter *before* stating the count:
        # "... in the second quarter, with ... reporting 81 completed deals".
        for candidate in re.finditer(
                r"(?:reported|reporting)\s+(\d[\d,]*)\s+completed (?:transactions|deals)\b",
                text, re.I):
            prefix = text[max(0, candidate.start() - 240):candidate.start()]
            # Same sentence/paragraph only; full-year or YTD counts are never
            # admitted just because the headline mentions Q2.
            contextual = prefix.rsplit(".", 1)[-1]
            if (re.search(rf"\b{period_token}\b", contextual, re.I)
                    and not re.search(r"\b(?:year to date|year.to.date|full year|first half)\b", contextual, re.I)):
                match = candidate
                break
    if match is None:
        raise SourceFormatError("Same-quarter transaction count not found")
    count = int(match.group(1).replace(",", ""))
    val_patterns = [
        r"average valuation of\s+(\d+(?:\.\d+)?)x\s+trailing\s+12.month\s+\(TTM\)\s+adjusted EBITDA",
        rf"average purchase price multiples (?:declined|rose|increased|fell)[^.\n]{{0,100}}?\bto\s+(\d+(?:\.\d+)?)x\s+trailing\s+12.month\s+(?:\(TTM\)\s+)?adjusted EBITDA",
        rf"average purchase price multiples (?:rebounded|rose|increased)[^.\n]{{0,100}}?\bto\s+(\d+(?:\.\d+)?)x\s+trailing\s+12.month\s+(?:\(TTM\)\s+)?adjusted EBITDA",
        rf"average purchase price multiples fell sharply in Q{quarter} to\s+(\d+(?:\.\d+)?)x\s+trailing\s+12.month\s+(?:\(TTM\)\s+)?adjusted EBITDA",
    ]
    vmatch = next((m for p in val_patterns if (m := re.search(p, text, re.I))), None)
    if vmatch is None:
        raise SourceFormatError("Same-quarter adjusted EBITDA entry multiple not found")
    value = float(vmatch.group(1))
    if not (1 <= count <= 10000 and 2 <= value <= 30):
        raise SourceFormatError("GF Data sample or multiple implausible")
    ev_range = _acg_coverage(text)
    month = quarter * 3
    end = date.fromordinal((date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)).toordinal() - 1)
    return [{"source": "GF Data / ACG", "metric": "entry_ev_ebitda_ttm_adjusted",
        "period": f"{year}Q{quarter}", "period_end": end.isoformat(), "geography": "Not specified",
        "value": value, "unit": "EV/EBITDA multiple", "population": ev_range,
        "sample_count": count, "precision": "mean", "source_url": source_url,
        "published_on": published, "definition": "Mean purchase EV / trailing 12-month adjusted EBITDA, contributing-deal sample"}]


MERCER_Q4_2025 = (
    "https://mercercapital.com/insights/newsletters/"
    "middle-market-transaction-update-newsletter/"
    "middle-market-transaction-update-spring-2026/"
)


def parse_mercer_gf_q4_2025(data: bytes, *, source_url: str, verified_range: str) -> list[dict]:
    """Specific independently quoted GF Data Q4 reading, not its annual average.

    ACG's public Q4 release supplies *annual* counts and pricing. Mercer
    explicitly reports separate Q4 figures from GF Data. We require the ACG
    Q4 release to verify the deal-size universe independently before use.
    """
    if source_url != MERCER_Q4_2025:
        raise SourceFormatError("Unexpected Mercer report URL")
    if verified_range != "GF Data contributing PE-sponsored transactions ($10m-$500m EV)":
        raise SourceFormatError("ACG Q4 transaction-size scope not independently verified")
    soup = BeautifulSoup(data.decode("utf-8", errors="replace"), "html.parser")
    articles = [tag for tag in soup.select("h1")
                if "Middle Market Transaction Update Spring 2026" in tag.get_text(" ", strip=True)]
    if len(articles) != 1:
        raise SourceFormatError("Not the expected Mercer Q4 evidence article")
    title = " ".join(articles[0].get_text(" ", strip=True).split())
    text = " ".join(soup.get_text(" ", strip=True).split())
    text = text[text.index(title):]
    if not re.search(r"Middle Market Transaction Update Spring 2026", text[:900], re.I):
        raise SourceFormatError("Not the expected Mercer Q4 evidence article")
    published = _release_date(text, 2026)
    if published != "2026-03-20":
        raise SourceFormatError("Mercer Q4 release date changed")
    count = re.search(
        r"(?:Surveys conducted by\s+)?GF Data.{0,25}?captured\s+(\d[\d,]*)\s+transactions\s+in\s+4Q25\b",
        text, re.I)
    multiple = re.search(
        r"average all.industry EBITDA multiple\s+declining\s+(?:during the quarter\s+)?to\s+(\d+(?:\.\d+)?)x\s+from\s+(\d+(?:\.\d+)?)x\s+in\s+3Q25\b",
        text, re.I)
    if not count or not multiple:
        raise SourceFormatError("Mercer did not state explicit Q4 GF Data count and multiple")
    sample = int(count.group(1).replace(",", ""))
    value, earlier = float(multiple.group(1)), float(multiple.group(2))
    if not (1 <= sample <= 10000 and 2 <= value <= 30 and earlier == 7.5):
        raise SourceFormatError("Mercer Q4 figure or reference to Q3 is invalid")
    return [{"source": "GF Data via Mercer Capital", "metric": "entry_ev_ebitda_ttm_adjusted",
        "period": "2025Q4", "period_end": "2025-12-31", "geography": "Not specified",
        "value": value, "unit": "EV/EBITDA multiple", "population": verified_range,
        "sample_count": sample, "precision": "mean / secondary report",
        "source_url": source_url, "published_on": published,
        "definition": "GF Data Q4 2025 all-industry mean EBITDA multiple, quoted by Mercer Capital"}]
