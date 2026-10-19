"""Read-only U.S. PE liquidity candidates: Cambridge LP flows and KPMG exits.

Independent sources and populations remain separate; no composite or inferred LP
cash distributions from exit transaction values. Staging only, no publication.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
from html.parser import HTMLParser
from io import StringIO
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen

OUT = Path('pe_probe_output/us_liquidity')
MAX_BYTES = 5_000_000
CAMBRIDGE_HOST = 'www.cambridgeassociates.com'
KPMG_HOST = 'kpmg.com'
SOURCES = {
    'cambridge': {
        2024: 'https://www.cambridgeassociates.com/en-as/insight/us-pe-vc-benchmark-commentary-calendar-year-2024/',
        2025: 'https://www.cambridgeassociates.com/insight/us-pe-vc-benchmark-commentary-calendar-year-2025/',
    },
    'kpmg': {
        2025: 'https://kpmg.com/us/en/articles/2025/pulse-private-equity-global-investment-trends.html',
        2026: 'https://kpmg.com/us/en/articles/2026/q2-26-pulse-private-equity-us-global-investment-trends.html',
    },
}
CAMBRIDGE_FIELDS = ('year', 'period_end', 'distributions_usd_bn', 'capital_calls_usd_bn',
                    'distributions_to_calls', 'publisher_distribution_yoy_pct',
                    'source_url', 'population')
KPMG_FIELDS = ('year', 'period_end', 'exit_value_usd_bn', 'exit_count',
               'cross_report_exit_value_change_pct', 'cross_report_exit_count_change_pct',
               'source_url', 'population')


class SourceRejected(ValueError):
    pass


class _Blocks(HTMLParser):
    """Collect article paragraphs/headings while discarding scripts and styles."""
    TAGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str]] = []
        self.active: list[list] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style', 'svg', 'noscript'}:
            self.hidden += 1
        if not self.hidden and tag in self.TAGS:
            self.active.append([tag, []])

    def handle_data(self, data):
        if not self.hidden:
            for _, fragments in self.active:
                fragments.append(data)

    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'svg', 'noscript'}:
            self.hidden = max(0, self.hidden - 1)
        if not self.hidden and self.active and self.active[-1][0] == tag:
            _, data = self.active.pop()
            content = re.sub(r'\s+', ' ', ''.join(data)).strip()
            if content:
                self.blocks.append((tag, content))


def blocks(payload: bytes) -> list[tuple[str, str]]:
    try:
        text = payload.decode('utf-8-sig')
    except UnicodeError as exc:
        raise SourceRejected('Non-UTF8 HTML') from exc
    if '<html' not in text[:2000].lower():
        raise SourceRejected('Expected an HTML document')
    parser = _Blocks()
    parser.feed(text)
    if len(parser.blocks) < 5:
        raise SourceRejected('No usable HTML article blocks')
    return parser.blocks


def source_url(source: str, year: int) -> str:
    if source not in SOURCES or not (2024 <= year <= date.today().year + 2):
        raise SourceRejected('Invalid source/year')
    if year in SOURCES[source]:
        return SOURCES[source][year]
    if source == 'cambridge':
        return ('https://www.cambridgeassociates.com/insight/'
                f'us-pe-vc-benchmark-commentary-calendar-year-{year}/')
    return (f'https://kpmg.com/us/en/articles/{year}/'
            f'q2-{year % 100:02d}-pulse-private-equity-us-global-investment-trends.html')


def fetch(url: str, *, source: str) -> bytes:
    allowed_hosts = {'cambridge': {CAMBRIDGE_HOST, 'cambridgeassociates.com'},
                     'kpmg': {KPMG_HOST, 'www.kpmg.com'}}.get(source)
    u = urlparse(url)
    if not allowed_hosts or u.scheme != 'https' or u.hostname not in allowed_hosts or u.username or u.password:
        raise SourceRejected('Unapproved research source')
    req = Request(url, headers={'User-Agent': 'AI Macro PE public research/1.0',
                                'Accept': 'text/html,application/xhtml+xml'})
    with urlopen(req, timeout=30) as response:
        final = urlparse(response.geturl())
        if final.scheme != 'https' or final.hostname not in allowed_hosts:
            raise SourceRejected('Unexpected redirect')
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' not in content_type.lower():
            raise SourceRejected(f'Unexpected content type {content_type}')
        payload = response.read(MAX_BYTES + 1)
    if not 1_000 <= len(payload) <= MAX_BYTES:
        raise SourceRejected('Unexpected response size')
    return payload


def _pe_section(all_blocks: list[tuple[str, str]], *, source: str) -> list[str]:
    if source == 'cambridge':
        start = r'US private equity performance insights'
        stop = r'US venture capital performance insights'
    else:
        start = r'U\.?S\.? insights'
        stop = r'Global insights'
    selected = []
    capturing = False
    for tag, value in all_blocks:
        if tag.startswith('h') and re.fullmatch(start, value, re.I):
            capturing = True
            continue
        if capturing and tag.startswith('h') and re.fullmatch(stop, value, re.I):
            break
        if capturing and tag == 'p':
            selected.append(value)
    if not selected:
        raise SourceRejected(f'No scoped {source} U.S. private-equity article body')
    return selected


def _positive(value: float, *, lo: float, hi: float) -> float:
    if not lo <= value <= hi:
        raise SourceRejected(f'Out-of-range source observation: {value}')
    return value


def parse_cambridge(payload: bytes, *, year: int, url: str) -> dict:
    section = _pe_section(blocks(payload), source='cambridge')
    # Only PE LP cash-flow sentences within the U.S. PE article section.
    candidates = [p for p in section if re.search(r'\b(?:distributions?|distributed)\b', p, re.I)
                  and re.search(r'\b(?:contributions?|called|capital calls?)\b', p, re.I)
                  and re.search(rf'\b{year}\b', p)]
    matches = []
    for p in candidates:
        # 2024 style: "In 2024, LP distributions ($174 billion) outpaced contributions ($143 billion)"
        old = re.search(r'LP distributions\s*\(\s*\$([\d,.]+)\s*billion\)\s*'
                        r'outpaced\s+contributions\s*\(\s*\$([\d,.]+)\s*billion\)', p, re.I)
        # 2025 style: "In 2025, fund managers distributed $185 billion and called $145 billion"
        new = re.search(r'\bdistributed\s+\$([\d,.]+)\s+billion\s+and\s+'
                        r'called\s+\$([\d,.]+)\s+billion', p, re.I)
        found = old or new
        if found:
            matches.append((float(found[1].replace(',', '')), float(found[2].replace(',', ''))))
    if len(set(matches)) != 1:
        raise SourceRejected(f'{year} Cambridge PE cash-flow sentence missing or ambiguous')
    distributions, calls = matches[0]
    # When benchmark constituents/revisions change, do not calculate a precise
    # YoY rate from separate publication vintages. Use the publisher's own
    # same-publication comparison only when it is explicit and unqualified.
    reported = re.search(r'\b(?:Distributions rose|increase in capital returned to LPs)\b', ' '.join(candidates), re.I)
    yoy = ''
    if reported:
        prose = ' '.join(candidates)
        old = re.search(r'Distributions rose\s+(\d+(?:\.\d+)?)%\s+from', prose, re.I)
        new = re.search(r'(\d+(?:\.\d+)?)%\s+increase in capital returned to LPs', prose, re.I)
        source_yoy = old or new
        if source_yoy:
            yoy = float(source_yoy[1])
    _positive(distributions, lo=1, hi=1000)
    _positive(calls, lo=1, hi=1000)
    return {'year': year, 'period_end': f'{year}-12-31',
            'distributions_usd_bn': distributions, 'capital_calls_usd_bn': calls,
            'distributions_to_calls': round(distributions / calls, 4),
            'publisher_distribution_yoy_pct': yoy,
            'source_url': url,
            'population': 'Cambridge U.S. PE benchmark: buyout and growth equity funds'}


def parse_kpmg(payload: bytes, *, year: int, url: str) -> dict:
    section = _pe_section(blocks(payload), source='kpmg')
    matches = []
    for p in section:
        if not re.search(r'\b(?:H1|first half of)\s*' + str(year) + r'\b', p, re.I):
            continue
        if not re.search(r'\bexits?\b', p, re.I):
            continue
        # Source styles: "In the first half of 2025 ... $318.97 billion in exit value"
        # and "US PE exit value reached $273.1 billion at H1 2026".
        a = re.search(r'\$([\d,.]+)\s*billion\s+in\s+exit\s+value', p, re.I)
        b = re.search(r'exit\s+value\s+(?:reached|totaled|hit)\s*\$([\d,.]+)\s*billion', p, re.I)
        amount = a or b
        count = re.search(r'\b([\d,]+)\s+exits\b', p, re.I)
        if amount and count:
            matches.append((float(amount[1].replace(',', '')), int(count[1].replace(',', ''))))
    if len(set(matches)) != 1:
        raise SourceRejected(f'{year} KPMG U.S. H1 exit value/count missing or ambiguous')
    exit_value, exit_count = matches[0]
    _positive(exit_value, lo=10, hi=3000)
    _positive(exit_count, lo=100, hi=10000)
    return {'year': year, 'period_end': f'{year}-06-30',
            'exit_value_usd_bn': exit_value, 'exit_count': exit_count,
            'cross_report_exit_value_change_pct': '', 'cross_report_exit_count_change_pct': '',
            'source_url': url, 'population': 'KPMG U.S. private-equity exits, H1'}


def comparisons(records: list[dict], *, source: str) -> list[dict]:
    out = sorted((dict(r) for r in records), key=lambda r: r['year'])
    if source == 'kpmg':
        for prior, current in zip(out, out[1:]):
            if current['year'] - prior['year'] != 1:
                continue
            # This is an indicative cross-publication comparison, not a
            # publisher-restated same-vintage time series.
            current['cross_report_exit_value_change_pct'] = round(
                100 * (current['exit_value_usd_bn'] / prior['exit_value_usd_bn'] - 1), 2)
            current['cross_report_exit_count_change_pct'] = round(
                100 * (current['exit_count'] / prior['exit_count'] - 1), 2)
    return out


def _csv_bytes(rows: list[dict], fields: tuple[str, ...]) -> bytes:
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode()


def run(out_dir: Path = OUT, *, current_year: int | None = None) -> dict:
    today = date.today()
    now = current_year or today.year
    datasets = {}
    report = {}
    for source, earliest in (('cambridge', 2024), ('kpmg', 2025)):
        latest = now - 1 if source == 'cambridge' else (now if today.month >= 7 else now - 1)
        records = []
        errors = []
        for year in range(earliest, latest + 1):
            url = source_url(source, year)
            try:
                payload = fetch(url, source=source)
                record = (parse_cambridge(payload, year=year, url=url) if source == 'cambridge'
                          else parse_kpmg(payload, year=year, url=url))
                records.append(record)
                print(f'{source} {year}: validated', flush=True)
            except Exception as exc:
                errors.append(year)
                print(f'{source} {year}: unavailable {type(exc).__name__}: {exc}', flush=True)
        validated = comparisons(records, source=source)
        if len(validated) < 2 or validated[-1]['year'] - validated[-2]['year'] != 1:
            raise SourceRejected(f'{source}: fewer than two consecutive validated reporting years')
        datasets[source] = validated
        report[source] = {'validated_years': [r['year'] for r in validated],
                          'unavailable_years': errors, 'latest_year': validated[-1]['year']}
    out_dir.mkdir(parents=True, exist_ok=True)
    for source, fields, name in (
        ('cambridge', CAMBRIDGE_FIELDS, 'us_pe_lp_flows_annual.csv'),
        ('kpmg', KPMG_FIELDS, 'us_pe_exits_h1.csv'),
    ):
        dest = out_dir / name
        temporary = dest.with_name(dest.name + '.tmp')
        temporary.write_bytes(_csv_bytes(datasets[source], fields))
        os.replace(temporary, dest)
    return {'status': 'candidate_extracted', 'scope': 'U.S. PE; separate benchmark and transaction populations',
            'sources': report}


def main(argv=None) -> int:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('--out-dir', type=Path, default=OUT)
    params = args.parse_args(argv)
    try:
        print(json.dumps(run(params.out_dir), sort_keys=True), flush=True)
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'unavailable', 'error': f'{type(exc).__name__}: {exc}'}, sort_keys=True),
              file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
