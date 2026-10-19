"""Source-validated, automation-only U.S. PE five-year net investment returns.

Cambridge's pooled horizon IRR is not a distribution yield, cumulative ROI,
or a time-weighted stock index return. Public comparisons are publisher mPME.
"""
from __future__ import annotations

from datetime import date
from io import BytesIO, StringIO
from pathlib import Path
import csv
import json
import os
import re
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from helpers.atomic_io import atomic_write_bundle
from config.deployment import repository_writes_enabled

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / 'data' / 'private_capital'
NAME = 'us_pe_returns_annual.csv'
PDF_URLS = {
    2024: 'https://www.cambridgeassociates.com/wp-content/uploads/2025/07/2025-07-US-PE-VC-Benchmark-Commentary-CY-2024-PUBLIC.pdf',
    2025: 'https://www.cambridgeassociates.com/wp-content/uploads/2026/07/2026-07-US-PE-VC-Benchmark-Commentary-CY2025-Data-PUBLIC.pdf',
}
FIELDS = ('year', 'period_end', 'pe_5y_annualized_net_pct', 'pe_1y_net_pct',
          'sp500_5y_mpme_pct', 'russell2000_5y_mpme_pct', 'source_url', 'population')
HOSTS = {'cambridgeassociates.com', 'www.cambridgeassociates.com'}
POPULATION = 'Cambridge U.S. Private Equity Index: buyout and growth-equity pooled horizon net IRR'


class ReturnSourceRejected(ValueError):
    pass


def _allowed(url: str) -> bool:
    p = urlparse(url)
    return p.scheme == 'https' and p.hostname in HOSTS and not p.username and not p.password


def _fetch(url: str, *, pdf: bool) -> bytes:
    if not _allowed(url):
        raise ReturnSourceRejected('Unapproved return data URL')
    req = Request(url, headers={'User-Agent': 'AI Macro public PE research/1.0',
                                'Accept': 'application/pdf' if pdf else 'text/html'})
    with urlopen(req, timeout=30) as response:
        if not _allowed(response.geturl()):
            raise ReturnSourceRejected('Return data redirected off publisher')
        ctype = response.headers.get('Content-Type', '').lower()
        if ('pdf' if pdf else 'html') not in ctype:
            raise ReturnSourceRejected('Unexpected published report format')
        body = response.read(7_000_001)
    if len(body) > 7_000_000 or len(body) < 500:
        raise ReturnSourceRejected('Unexpected published report size')
    if pdf and not body.startswith(b'%PDF'):
        raise ReturnSourceRejected('Missing PDF signature')
    return body


def _pdf_url(year: int) -> str:
    if year in PDF_URLS:
        return PDF_URLS[year]
    # Discover later annual publications from the publisher, not a speculative PDF path.
    from bs4 import BeautifulSoup
    landing = f'https://www.cambridgeassociates.com/insight/us-pe-vc-benchmark-commentary-calendar-year-{year}/'
    page = _fetch(landing, pdf=False).decode('utf-8-sig')
    links = []
    for anchor in BeautifulSoup(page, 'html.parser').select('a[href]'):
        candidate = urljoin(landing, anchor.get('href', ''))
        if (_allowed(candidate) and urlparse(candidate).path.lower().endswith('.pdf')
            and re.search(rf'(?:cy[-_]?{year}|calendar[-_]?year[-_]?{year})', candidate, re.I)):
            links.append(candidate)
    unique = list(dict.fromkeys(links))
    if len(unique) != 1:
        raise ReturnSourceRejected('Annual return PDF not unambiguously discoverable')
    return unique[0]


def extract_first_page(pdf: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(pdf), strict=True)
    if not reader.pages or len(reader.pages) > 30:
        raise ReturnSourceRejected('Unexpected Cambridge report length')
    return reader.pages[0].extract_text(extraction_mode='layout') or ''


def parse_report(text: str, *, year: int, source_url: str) -> dict:
    """Parse only Figure 1, by its published heading and fixed annualized columns."""
    if not _allowed(source_url) or not source_url.lower().split('?')[0].endswith('.pdf'):
        raise ReturnSourceRejected('Unapproved PDF provenance')
    flat = re.sub(r'[\u00a0\u200b]', ' ', text)
    if not re.search(r'US Private Equity\s*&\s*Venture|US Private Equity and Venture', flat, re.I):
        raise ReturnSourceRejected('Not a US PE/VC commentary')
    if not re.search(rf'Calendar Year\s*{year}\b', flat, re.I):
        raise ReturnSourceRejected('Wrong calendar-year report')
    if not re.search(rf'Periods?\s+Ended\s+December\s+31,?\s*{year}', flat, re.I):
        raise ReturnSourceRejected('Wrong Figure 1 end date')
    if not re.search(r'(?:Figure\s*1)\s+US\s+private\s+equity\s+and\s+venture', flat, re.I):
        raise ReturnSourceRejected('Missing benchmark return table')
    match_header = re.search(r'Index\s+6\s*[Mm]o\s+1\s*[Yy]r\s+3\s*[Yy]r\s+5\s*[Yy]r\s+10\s*[Yy]r', flat)
    if not match_header:
        raise ReturnSourceRejected('Horizon column order changed')
    # First benchmark cluster only. The figure repeats equity comparators for VC;
    # searching outside its first four rows would silently select the wrong sample.
    table = flat[match_header.end():]
    result = {}
    names = {
        'pe': r'CA\s+US\s+Private\s+Equity\s*\*?',
        'russell': r'Russell\s+2000\s*[^\n]*?mPME',
        'sp500': r'S\s*&\s*P\s*500\s*mPME',
    }
    number = r'[-+]?\d+(?:\.\d+)?'
    # Strict row boundary: each benchmark must provide exactly eight horizons.
    for key, pattern in names.items():
        found = re.search(rf'(?m)^\s*{pattern}\s+((?:{number}\s+){{7}}{number})\s*$', table, re.I)
        if not found:
            raise ReturnSourceRejected(f'Figure 1 missing or ambiguous {key} return row')
        nums = [float(x) for x in re.findall(number, found[1])]
        if len(nums) != 8 or any(abs(x) > 150 for x in nums):
            raise ReturnSourceRejected('Implausible annualized return')
        result[key] = (nums[1], nums[3])  # 1-year, 5-year (annualized)
    return {'year': year, 'period_end': f'{year}-12-31',
            'pe_5y_annualized_net_pct': result['pe'][1],
            'pe_1y_net_pct': result['pe'][0],
            'sp500_5y_mpme_pct': result['sp500'][1],
            'russell2000_5y_mpme_pct': result['russell'][1],
            'source_url': source_url, 'population': POPULATION}


def _csv_bytes(rows: list[dict]) -> bytes:
    writer_buffer = StringIO()
    writer = csv.DictWriter(writer_buffer, FIELDS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return writer_buffer.getvalue().encode('utf-8')


def refresh(*, out_dir: Path = PRODUCTION, current_year: int | None = None,
            current_month: int | None = None) -> dict:
    if out_dir.resolve() == PRODUCTION.resolve() and not repository_writes_enabled():
        raise PermissionError('PE return publication requires authorized automation mode')
    today = date.today()
    now = current_year or today.year
    month = current_month or today.month
    latest = now - (1 if month >= 8 else 2)
    dest = out_dir / NAME
    try:
        from analytics.pe_us_conditions import validated_return_rows
        existing = validated_return_rows(dest)
        rows = {r['year']: r for r in existing}
        for year in range(max(2024, latest-1), latest+1):
            pdf_url = _pdf_url(year)
            payload = _fetch(pdf_url, pdf=True)
            observation = parse_report(extract_first_page(payload), year=year, source_url=pdf_url)
            previous = rows.get(year)
            if previous:
                for field in FIELDS[2:6]:
                    if abs(float(previous[field])-float(observation[field])) > 0.00001:
                        raise ReturnSourceRejected(f'Historical benchmark revision requires review: {year}, {field}')
            rows[year] = observation
        if latest not in rows:
            raise ReturnSourceRejected('Most recent completed period missing')
        output = _csv_bytes([rows[year] for year in sorted(rows)])
        changed = not dest.exists() or dest.read_bytes() != output
        if changed:
            out_dir.mkdir(parents=True, exist_ok=True)
            atomic_write_bundle({dest: output}, transaction_key=dest)
        result = {'source': 'cambridge_return', 'status': 'updated' if changed else 'unchanged',
                  'latest_year': latest, 'rows': len(rows), 'file': str(dest)}
    except Exception as exc:
        result = {'source': 'cambridge_return',
                  'status': 'retained_on_failure' if dest.exists() else 'unavailable',
                  'error': f'{type(exc).__name__}: {exc}', 'file': str(dest)}
    print(json.dumps(result, sort_keys=True), flush=True)
    return result
