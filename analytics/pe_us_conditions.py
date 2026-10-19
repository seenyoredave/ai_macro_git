"""Read retained U.S. PE market signals for Finance and its existing Read engine."""
from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT / 'data' / 'private_capital'
SEED = PROJECT_ROOT / 'seeds' / 'pe_conditions'
LP_NAME = 'us_pe_lp_flows_annual.csv'
EXIT_NAME = 'us_pe_exits_h1.csv'
RETURN_NAME = 'us_pe_returns_annual.csv'
FIELDS = {
    'cambridge': ('year', 'period_end', 'distributions_usd_bn', 'capital_calls_usd_bn',
                  'distributions_to_calls', 'publisher_distribution_yoy_pct', 'source_url', 'population'),
    'kpmg': ('year', 'period_end', 'exit_value_usd_bn', 'exit_count',
             'cross_report_exit_value_change_pct', 'cross_report_exit_count_change_pct',
             'source_url', 'population'),
}
HOSTS = {'cambridge': {'www.cambridgeassociates.com', 'cambridgeassociates.com'},
         'kpmg': {'kpmg.com', 'www.kpmg.com'}}


class InvalidPEObservation(ValueError):
    pass


def _float(value, name: str, lo: float, hi: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidPEObservation(f'{name} is not numeric') from exc
    if not lo <= number <= hi:
        raise InvalidPEObservation(f'{name} outside source range')
    return number


def validated_rows(path: Path, source: str) -> list[dict]:
    """Fail closed on malformed retained state; never contact providers in public runtime."""
    if source not in FIELDS:
        raise InvalidPEObservation('Unknown source')
    if not path.exists():
        return []
    with path.open(newline='', encoding='utf-8') as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != FIELDS[source]:
            raise InvalidPEObservation('Unexpected retained PE schema')
        records = list(reader)
    if not records:
        return []
    rows, seen = [], set()
    for record in records:
        try:
            year = int(record['year'])
            period = date.fromisoformat(record['period_end'])
        except (TypeError, ValueError) as exc:
            raise InvalidPEObservation('Invalid reported PE year or period') from exc
        if year in seen or not 2020 <= year <= date.today().year or period.year != year or period > date.today():
            raise InvalidPEObservation('Duplicated, future, or inconsistent PE period')
        seen.add(year)
        if (source == 'cambridge' and (period.month, period.day) != (12, 31)) or (source == 'kpmg' and (period.month, period.day) != (6, 30)):
            raise InvalidPEObservation('Unexpected reporting period')
        url = urlparse(record['source_url'])
        if url.scheme != 'https' or url.hostname not in HOSTS[source] or url.username or url.password:
            raise InvalidPEObservation('PE observation lacks validated source provenance')
        if not record['population'].strip().startswith(('Cambridge U.S. PE benchmark:' if source == 'cambridge' else 'KPMG U.S. private-equity exits,')):
            raise InvalidPEObservation('Unexpected reported population')
        r = {'year': year, 'period_end': record['period_end'], 'source_url': record['source_url'],
             'population': record['population']}
        if source == 'cambridge':
            r['distributions_usd_bn'] = _float(record['distributions_usd_bn'], 'LP distributions', 1, 1000)
            r['capital_calls_usd_bn'] = _float(record['capital_calls_usd_bn'], 'LP capital calls', 1, 1000)
            r['distributions_to_calls'] = _float(record['distributions_to_calls'], 'LP recycling', 0.001, 100)
            if abs(r['distributions_to_calls'] - r['distributions_usd_bn'] / r['capital_calls_usd_bn']) > 0.00011:
                raise InvalidPEObservation('LP distributions/calls reconciliation failed')
            r['publisher_distribution_yoy_pct'] = (_float(record['publisher_distribution_yoy_pct'], 'publisher reported change', -100, 200)
                                                     if record['publisher_distribution_yoy_pct'] else None)
        else:
            r['exit_value_usd_bn'] = _float(record['exit_value_usd_bn'], 'US exit value', 10, 3000)
            r['exit_count'] = int(_float(record['exit_count'], 'US exit count', 100, 10000))
            if str(r['exit_count']) != record['exit_count'].strip():
                raise InvalidPEObservation('Exit counts must be integer observations')
            r['cross_report_exit_value_change_pct'] = (_float(record['cross_report_exit_value_change_pct'], 'exit-value change', -100, 500)
                                                       if record['cross_report_exit_value_change_pct'] else None)
            r['cross_report_exit_count_change_pct'] = (_float(record['cross_report_exit_count_change_pct'], 'exit-count change', -100, 500)
                                                       if record['cross_report_exit_count_change_pct'] else None)
        rows.append(r)
    rows.sort(key=lambda item: item['year'])
    return rows


def validated_return_rows(path: Path) -> list[dict]:
    """Strictly validate the Cambridge pooled PE net IRR and matched public-market returns."""
    from loaders.pe_us_returns_retained import FIELDS, POPULATION
    if not path.exists():
        return []
    with path.open(newline='', encoding='utf-8') as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise InvalidPEObservation('Unexpected PE returns schema')
        observations = list(reader)
    out, seen = [], set()
    for row in observations:
        try:
            year = int(row['year'])
            end = date.fromisoformat(row['period_end'])
        except (ValueError, TypeError) as exc:
            raise InvalidPEObservation('Invalid PE return period') from exc
        if year in seen or year < 2020 or year > date.today().year or end != date(year, 12, 31) or end > date.today():
            raise InvalidPEObservation('Inconsistent PE return year')
        seen.add(year)
        url = urlparse(row['source_url'])
        if (url.scheme != 'https' or url.hostname not in HOSTS['cambridge'] or
            not url.path.lower().endswith('.pdf') or url.username or url.password):
            raise InvalidPEObservation('Unapproved PE return report')
        if row['population'] != POPULATION:
            raise InvalidPEObservation('Wrong PE return population')
        record = {'year': year, 'period_end': row['period_end'],
                  'source_url': row['source_url'], 'population': row['population']}
        for name in FIELDS[2:6]:
            record[name] = _float(row[name], name, -75, 100)
        out.append(record)
    return sorted(out, key=lambda r: r['year'])


def _read_source(base: Path, name: str, source: str) -> list[dict]:
    production = base / name
    return validated_rows(production if production.exists() else SEED / name, source)


def _entry_pricing(base: Path) -> dict:
    path = base / 'pe_industry_acg.csv'
    if not path.exists():
        path = SEED / 'pe_industry_acg.csv'
    if not path.exists():
        return {}
    with path.open(encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        required = {'source', 'metric', 'period', 'period_end', 'value', 'unit', 'population', 'sample_count', 'precision', 'source_url'}
        if not required.issubset(reader.fieldnames or ()):
            return {}
        rows = [r for r in reader if r['metric'] == 'entry_ev_ebitda_ttm_adjusted']
    items = []
    for r in rows:
        try:
            end = date.fromisoformat(r['period_end'])
            val = _float(r['value'], 'entry pricing', 2, 35)
            if end > date.today() or not r['period'].startswith(str(end.year)):
                continue
            if r['unit'] != 'EV/EBITDA multiple' or r['precision'] != 'mean':
                continue
            url = urlparse(r['source_url'])
            if url.scheme != 'https' or url.hostname not in {'www.acg.org','acg.org'}:
                continue
            if not r['population'].startswith('GF Data contributing PE-sponsored transactions ('):
                continue
            items.append({'value': val, 'period': r['period'], 'period_end': r['period_end'],
                          'population': r['population'], 'sample_count': int(r['sample_count']),
                          'source_url': r['source_url']})
        except (ValueError, TypeError):
            continue
    items.sort(key=lambda r: r['period_end'])
    if not items:
        return {}
    current = dict(items[-1])
    if len(items) >= 2:
        prior = items[-2]
        first, second = int(prior['period_end'][:4])*4 + (int(prior['period_end'][5:7])-1)//3, int(current['period_end'][:4])*4 + (int(current['period_end'][5:7])-1)//3
        if second-first == 1 and prior['population'] == current['population']:
            current['prior_value'] = prior['value']
            current['quarter_change'] = round(current['value'] - prior['value'], 2)
    return current


def _fund_net_assets(base: Path) -> dict:
    """SEC-reported net assets of PE funds, not liquid cash or investable dry powder."""
    path = base / 'pe_industry_sec.csv'
    if not path.exists():
        path = SEED / 'pe_industry_sec.csv'
    if not path.exists():
        return {}
    with path.open(newline='', encoding='utf-8') as handle:
        reader = csv.DictReader(handle)
        required = {'source', 'metric', 'period', 'period_end', 'geography', 'value',
                    'unit', 'population', 'precision', 'source_url'}
        if not required.issubset(reader.fieldnames or ()):
            return {}
        rows = list(reader)
    candidates = []
    for row in rows:
        if row['metric'] != 'net_assets_usd_bn':
            continue
        try:
            end = date.fromisoformat(row['period_end'])
            amount = _float(row['value'], 'SEC PE net assets', 200, 50000)
            url = urlparse(row['source_url'])
            if (end > date.today() or end != date(end.year, 12, 31) or
                row['period'] != f'{end.year}Q4' or row['source'] != 'SEC Form PF' or
                row['unit'] != 'USD billions' or row['precision'] != 'reported' or
                row['population'] != 'SEC Form PF-reported private equity funds' or
                url.scheme != 'https' or url.hostname not in {'sec.gov', 'www.sec.gov'} or
                url.username or url.password):
                continue
            candidates.append({'value_usd_bn': amount, 'year': end.year,
                               'period_end': row['period_end'], 'source_url': row['source_url']})
        except (TypeError, ValueError):
            continue
    candidates.sort(key=lambda r:r['period_end'])
    return candidates[-1] if candidates else {}


def last_pe_retrieval_date(
    graph_path: Path = PROJECT_ROOT / 'data' / 'refresh_graph_state.json',
) -> str | None:
    """Date of the latest successful PE source retrieval in published automation state.

    Never substitute the source observation period, CSV file modification time,
    today's date, or an unsuccessful attempted refresh.
    """
    try:
        state = json.loads(graph_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(state, dict):
        return None
    nodes = state.get('nodes') or {}
    if not isinstance(nodes, dict):
        return None
    successful = []
    for name in ('pe_us_liquidity', 'pe_industry'):
        record = nodes.get(name) or {}
        if not isinstance(record, dict):
            continue
        # Older published graph versions have the completed-success boundary
        # but not the finer-grained partial-retrieval timestamp.
        for stamp in (record.get('last_retrieval_at_utc'), record.get('last_success_at_utc')):
            try:
                when = datetime.fromisoformat(str(stamp).replace('Z', '+00:00'))
            except (TypeError, ValueError):
                continue
            if when.tzinfo is None:
                continue
            when = when.astimezone(timezone.utc)
            if when.date() <= datetime.now(timezone.utc).date():
                successful.append(when)
    return max(successful).strftime('%m.%d.%Y') if successful else None


def build_pe_us_conditions(base: Path = ROOT, *, include_valuation: bool = True) -> dict:
    result: dict = {'lp': {}, 'exits': {}, 'valuation': {}, 'returns': {}, 'scale': {}}
    try:
        lp = _read_source(base, LP_NAME, 'cambridge')
        if lp:
            latest = dict(lp[-1])
            if len(lp) >= 2 and lp[-1]['year'] == lp[-2]['year'] + 1:
                latest['prior_year'] = lp[-2]['year']
                latest['prior_distributions_to_calls'] = lp[-2]['distributions_to_calls']
            result['lp'] = latest
    except (OSError, InvalidPEObservation):
        pass
    try:
        exits = _read_source(base, EXIT_NAME, 'kpmg')
        if len(exits) >= 2 and exits[-1]['year'] == exits[-2]['year'] + 1:
            prior, current = exits[-2], dict(exits[-1])
            # Calculate from the retained values; cross-report changes remain indicative.
            value_change = round(100 * (current['exit_value_usd_bn'] / prior['exit_value_usd_bn'] - 1), 2)
            count_change = round(100 * (current['exit_count'] / prior['exit_count'] - 1), 2)
            if (current['cross_report_exit_value_change_pct'] is not None
                and abs(current['cross_report_exit_value_change_pct'] - value_change) > 0.02):
                raise InvalidPEObservation('Exit-value change does not reconcile')
            if (current['cross_report_exit_count_change_pct'] is not None
                and abs(current['cross_report_exit_count_change_pct'] - count_change) > 0.02):
                raise InvalidPEObservation('Exit-count change does not reconcile')
            current.update({'exit_value_change_pct': value_change, 'exit_count_change_pct': count_change,
                            'prior_year': prior['year']})
            result['exits'] = current
    except (OSError, InvalidPEObservation):
        pass
    try:
        return_path = base / RETURN_NAME
        returns = validated_return_rows(return_path if return_path.exists() else SEED / RETURN_NAME)
        if returns:
            current = dict(returns[-1])
            if len(returns) >= 2 and returns[-1]['year'] - returns[-2]['year'] == 1:
                current['prior_year'] = returns[-2]['year']
                current['prior_pe_5y_annualized_net_pct'] = returns[-2]['pe_5y_annualized_net_pct']
            result['returns'] = current
    except (OSError, InvalidPEObservation):
        pass
    try:
        result['scale'] = _fund_net_assets(base)
    except (OSError, InvalidPEObservation):
        pass
    if include_valuation:
        try:
            result['valuation'] = _entry_pricing(base)
        except (OSError, InvalidPEObservation):
            pass
    return result
