"""Candidate CalPERS private-equity cash-flow extractor; staging output only.

The Investment Transaction Summary contains *period* contributions/distributions,
not cumulative fund-level performance.  Only tables that balance are accepted.
Missing months remain missing; quarterly observations require all three months.
"""

from __future__ import annotations

import argparse
import calendar
import csv
from datetime import date
from io import BytesIO
from pathlib import Path
import re
import sys
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from pypdf import PdfReader

HOST = 'www.calpers.ca.gov'
BOARD_HOME = 'https://www.calpers.ca.gov/about/board/board-meetings'
BOARD_PAGES = (
    'https://www.calpers.ca.gov/about/board/board-meetings/invest-202609',
    'https://www.calpers.ca.gov/about/board/board-meetings/invest-202606',
    'https://www.calpers.ca.gov/about/board/board-meetings/invest-202603',
    'https://www.calpers.ca.gov/about/board/board-meetings/invest-202511',
    'https://www.calpers.ca.gov/about/board/board-meetings/invest-202506',
)
# Independently indexed source documents; used if meeting-page discovery fails.
SEED_PDFS = (
    'https://www.calpers.ca.gov/documents/202411-invest-agenda-item04d-01-a/download',
    'https://www.calpers.ca.gov/documents/202506-invest-agenda-item04d-01/download',
    'https://www.calpers.ca.gov/documents/202511-invest-agenda-item04d-01-a-0/download',
    'https://www.calpers.ca.gov/documents/202606-invest-agenda-item04d-01-a/download',
)
MONTH_PATTERN = re.compile(r'Investment\s+Transaction\s+Summary\s+for\s+the\s+Month\s+Ended\s+([A-Za-z]+)\s+(20\d{2})', re.I)
MONEY = re.compile(r'\(?-?\$?\d{1,3}(?:,\d{3})+(?:\.\d{2})?\)?|\(?-?\$?\d{7,}(?:\.\d{2})?\)?')
ROW_PATTERNS = {
    'beginning_value': re.compile(r'^\s*Beginning\s+Market\s+Value\b', re.I),
    'contributions': re.compile(r'^\s*\+?\s*Contributions\b', re.I),
    'distributions': re.compile(r'^\s*-?\s*Distributions\b', re.I),
    'other_changes': re.compile(r'^\s*(?:\+\s*/\s*-\s*)?Other\s+Changes\s+in\s+MV\b', re.I),
    'ending_value': re.compile(r'^\s*Ending\s+Market\s+Value\b', re.I),
}
MONTHLY_FIELDS = ('period_end', 'contributions_usd', 'distributions_usd', 'net_cash_to_lps_usd',
                  'beginning_value_usd', 'other_changes_usd', 'ending_value_usd', 'source_url')
QUARTERLY_FIELDS = ('period_end', 'months', 'contributions_usd', 'distributions_usd',
                    'net_cash_to_lps_usd', 'distribution_to_call_ratio', 'source_urls')


class SourceRejected(ValueError):
    pass


def allowed(url: str) -> bool:
    u = urlparse(url)
    return u.scheme == 'https' and u.hostname == HOST and not u.username and not u.password


def fetch(url: str, *, max_bytes: int = 15_000_000) -> bytes:
    if not allowed(url):
        raise SourceRejected('Non-CalPERS URL')
    request = Request(url, headers={'User-Agent': 'AI Macro PE liquidity research (public CalPERS reports)',
                                    'Accept': 'text/html,application/pdf,*/*'})
    with urlopen(request, timeout=25) as response:
        if not allowed(response.geturl()):
            raise SourceRejected('Unexpected download redirect')
        data = response.read(max_bytes + 1)
    if not (200 <= len(data) <= max_bytes):
        raise SourceRejected('Truncated or oversized response')
    return data


def discover_documents(html: bytes, base_url: str) -> list[str]:
    """Only the Investment Controls attachment, never unrelated PE slide decks."""
    soup = BeautifulSoup(html, 'html.parser')
    out = []
    for link in soup.find_all('a', href=True):
        label = ' '.join(link.get_text(' ', strip=True).split())
        if not re.search(r'Quarterly Update\s*[-–]\s*Investment Controls', label, re.I):
            continue
        li = link.find_parent('li')
        if li is None:
            continue
        for candidate in li.find_all('a', href=True):
            url = urljoin(base_url, candidate['href'])
            path = urlparse(url).path
            if (allowed(url) and re.search(r'/documents/20\d{4}-invest-agenda-item\d+[a-z]-01(?:-a(?:-\d+)?)?/download$', path, re.I)):
                out.append(url)
    return list(dict.fromkeys(out))


def discover_meetings(html: bytes, base_url: str = BOARD_HOME) -> list[str]:
    """Refresh the set of board meetings without assuming future meeting dates."""
    soup = BeautifulSoup(html, 'html.parser')
    links = []
    for tag in soup.find_all('a', href=True):
        url = urljoin(base_url, tag['href'])
        if allowed(url) and re.fullmatch(r'/about/board/board-meetings/invest-20\d{4}(?:-\d+)?', urlparse(url).path):
            links.append(url)
    return sorted(set(links), reverse=True)[:12]


def number(raw: str) -> float:
    s = raw.strip().replace('$', '').replace(',', '')
    negative = s.startswith('(') and s.endswith(')')
    s = s.strip('()')
    try:
        value = float(s)
    except ValueError as exc:
        raise SourceRejected('Invalid financial number') from exc
    return -value if negative else value


def parse_month_page(text: str, source_url: str) -> dict | None:
    marker = MONTH_PATTERN.search(text)
    if not marker:
        return None
    try:
        month = list(calendar.month_name).index(marker.group(1).capitalize())
        if not month:
            raise ValueError('Not a month')
        year = int(marker.group(2))
    except ValueError as exc:
        raise SourceRejected('Invalid month header') from exc
    period = date(year, month, calendar.monthrange(year, month)[1]).isoformat()

    # Restrict the search to the *private-markets* block on the same PDF page.
    anchors = list(re.finditer(r'Private\s+Debt\s*\(\$\)\s+Private\s+Equity\s*\(\$\)', text, re.I))
    if len(anchors) != 1:
        raise SourceRejected(f'{period}: expected one private debt/equity table header, found {len(anchors)}')
    section = text[anchors[0].end():]
    # Ending Market Value terminates the table. Do not wander into fund totals.
    end = re.search(r'^\s*Ending\s+Market\s+Value\b[^\n]*', section, re.I | re.M)
    if end is None:
        raise SourceRejected(f'{period}: incomplete private equity table')
    section = section[:end.end()]
    items = {}
    for line in section.splitlines():
        for key, regex in ROW_PATTERNS.items():
            match = regex.match(line)
            if match is None:
                continue
            if key in items:
                raise SourceRejected(f'{period}: duplicated {key}')
            figures = [number(m.group()) for m in MONEY.finditer(line[match.end():])]
            if len(figures) < 2:
                raise SourceRejected(f'{period}: no complete private equity column in {key}')
            # Private Debt is column one; Private Equity is column two.
            items[key] = figures[1]
    if set(items) != set(ROW_PATTERNS):
        raise SourceRejected(f'{period}: missing private-equity cash-flow fields: {set(ROW_PATTERNS) - set(items)}')
    if items['contributions'] < 0 or items['distributions'] > 0:
        raise SourceRejected(f'{period}: unexpected contribution/distribution signs')
    if not (1e9 < items['beginning_value'] < 1e13 and 1e9 < items['ending_value'] < 1e13):
        raise SourceRejected(f'{period}: implausible pension PE NAV')
    reconcile = (items['beginning_value'] + items['contributions'] + items['distributions']
                 + items['other_changes'] - items['ending_value'])
    if abs(reconcile) > 2.00:
        raise SourceRejected(f'{period}: cash-flow table fails value reconciliation ({reconcile:,.2f} USD)')
    return {
        'period_end': period, 'contributions_usd': round(items['contributions'], 2),
        'distributions_usd': round(-items['distributions'], 2),
        'net_cash_to_lps_usd': round(-items['distributions'] - items['contributions'], 2),
        'beginning_value_usd': round(items['beginning_value'], 2),
        'other_changes_usd': round(items['other_changes'], 2),
        'ending_value_usd': round(items['ending_value'], 2), 'source_url': source_url,
    }


def parse_pdf(payload: bytes, source_url: str) -> list[dict]:
    if not payload.startswith(b'%PDF-'):
        raise SourceRejected('Not a PDF')
    reader = PdfReader(BytesIO(payload))
    if not (3 <= len(reader.pages) <= 80):
        raise SourceRejected('Unexpected PDF page count')
    found = []
    for page in reader.pages:
        page_text = page.extract_text(extraction_mode='layout') or ''
        if 'Investment Transaction Summary for the Month Ended' not in ' '.join(page_text.split()):
            continue
        record = parse_month_page(page_text, source_url)
        if record is not None:
            found.append(record)
    if not found:
        raise SourceRejected('No validated monthly PE transaction tables found')
    keys = [x['period_end'] for x in found]
    if len(keys) != len(set(keys)):
        raise SourceRejected('Duplicated monthly tables in PDF')
    return found


def merge_months(documents: list[list[dict]]) -> list[dict]:
    by_period = {}
    for document in documents:
        for row in document:
            key = row['period_end']
            if key in by_period:
                prior = {k: v for k, v in by_period[key].items() if k != 'source_url'}
                current = {k: v for k, v in row.items() if k != 'source_url'}
                if prior != current:
                    raise SourceRejected(f'Conflicting monthly observations for {key}')
                continue
            by_period[key] = row
    return [by_period[k] for k in sorted(by_period)]


def complete_quarters(months: list[dict]) -> list[dict]:
    by_q = {}
    for x in months:
        d = date.fromisoformat(x['period_end'])
        key = (d.year, (d.month - 1) // 3 + 1)
        by_q.setdefault(key, []).append(x)
    result = []
    for (year, q), group in sorted(by_q.items()):
        expected_months = set(range((q - 1) * 3 + 1, q * 3 + 1))
        if {date.fromisoformat(x['period_end']).month for x in group} != expected_months:
            continue
        calls = round(sum(x['contributions_usd'] for x in group), 2)
        paid = round(sum(x['distributions_usd'] for x in group), 2)
        last_month = q * 3
        result.append({'period_end': date(year, last_month, calendar.monthrange(year, last_month)[1]).isoformat(),
                       'months': 3, 'contributions_usd': calls, 'distributions_usd': paid,
                       'net_cash_to_lps_usd': round(paid - calls, 2),
                       'distribution_to_call_ratio': round(paid / calls, 5) if calls > 0 else '',
                       'source_urls': ';'.join(sorted({x['source_url'] for x in group}))})
    return result


def write_csv(path: Path, rows: list[dict], fields: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(out_dir: Path, *, board_pages=BOARD_PAGES, seeds=SEED_PDFS) -> tuple[list[dict], list[dict]]:
    candidates = list(seeds)
    try:
        newest = discover_meetings(fetch(BOARD_HOME))
        print(f'Board meeting index: {len(newest)} investment committee pages', flush=True)
    except Exception as exc:
        newest = []
        print(f'Board meeting index unavailable: {type(exc).__name__}: {exc}', flush=True)
    for page in dict.fromkeys((*newest, *board_pages)):
        try:
            discovered = discover_documents(fetch(page), page)
            print(f'Meeting discovery: {page} -> {len(discovered)} PDF(s)', flush=True)
            candidates.extend(discovered)
        except Exception as exc:
            print(f'Meeting unavailable: {page} -> {type(exc).__name__}: {exc}', flush=True)
    documents = []
    for url in list(dict.fromkeys(candidates))[:16]:
        try:
            obs = parse_pdf(fetch(url), url)
            documents.append(obs)
            print(f'PDF validated: {url} -> {len(obs)} month(s)', flush=True)
        except Exception as exc:
            print(f'PDF rejected: {url} -> {type(exc).__name__}: {exc}', flush=True)
    monthly = merge_months(documents)
    quarterly = complete_quarters(monthly)
    if monthly:
        write_csv(out_dir / 'calpers_pe_monthly.csv', monthly, MONTHLY_FIELDS)
    if quarterly:
        write_csv(out_dir / 'calpers_pe_quarterly.csv', quarterly, QUARTERLY_FIELDS)
    print(f'Validated {len(monthly)} monthly observations, {len(quarterly)} complete quarters', flush=True)
    return monthly, quarterly


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, default=Path('pe_probe_output/liquidity'))
    args = parser.parse_args(argv)
    months, _ = run(args.out_dir)
    return 0 if months else 1


if __name__ == '__main__':
    sys.exit(main())
