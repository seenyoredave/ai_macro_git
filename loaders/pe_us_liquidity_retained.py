"""Authorized publication of separately validated U.S. PE cash-flow and exit series."""
from __future__ import annotations

from datetime import date
import json
import os
from pathlib import Path

from analytics.pe_us_conditions import EXIT_NAME, LP_NAME, validated_rows
from config.deployment import repository_writes_enabled
from helpers.atomic_io import atomic_write_bundle
from loaders import pe_us_liquidity_probe as probe

PRODUCTION = Path(__file__).resolve().parents[1] / 'data' / 'private_capital'
NAMES = {'cambridge': LP_NAME, 'kpmg': EXIT_NAME}


def refresh(*, out_dir: Path = PRODUCTION, current_year: int | None = None) -> list[dict]:
    if out_dir.resolve() == PRODUCTION.resolve() and not repository_writes_enabled():
        raise PermissionError('PE source publication requires authorized automation mode')
    now = current_year or date.today().year
    results = []
    for source, name in NAMES.items():
        destination = out_dir / name
        try:
            end = (now - 1 if source == 'cambridge' else (now if date.today().month >= 7 else now - 1))
            start = max(2024 if source == 'cambridge' else 2025, end - 1)
            if start == end:
                raise probe.SourceRejected('Source lacks two complete reporting periods')
            observations = []
            for year in (start, end):
                url = probe.source_url(source, year)
                body = probe.fetch(url, source=source)
                observations.append(probe.parse_cambridge(body, year=year, url=url) if source == 'cambridge'
                                    else probe.parse_kpmg(body, year=year, url=url))
            observed = probe.comparisons(observations, source=source)
            previous = validated_rows(destination, source)
            seen = {r['year']: r for r in previous}
            # A revised historical benchmark must be reviewed rather than silently
            # changing the time series used by Read.
            for row in observed:
                old = seen.get(row['year'])
                if old:
                    for key in probe.CAMBRIDGE_FIELDS if source == 'cambridge' else probe.KPMG_FIELDS:
                        if key in {'source_url', 'population', 'publisher_distribution_yoy_pct',
                                   'cross_report_exit_value_change_pct', 'cross_report_exit_count_change_pct'}:
                            continue
                        if str(old.get(key)) != str(row.get(key)):
                            if key in {'distributions_usd_bn', 'capital_calls_usd_bn', 'exit_value_usd_bn', 'distributions_to_calls'}:
                                if abs(float(old[key]) - float(row[key])) < 0.00011:
                                    continue
                            raise probe.SourceRejected(f'{source} {row["year"]}: source revision held for review ({key})')
                seen[row['year']] = row
            if previous:
                rows = []
                for row in previous:
                    row = dict(row)
                    # The original CSV schema has unmodified source-publisher fields.
                    if source == 'kpmg':
                        row['cross_report_exit_value_change_pct'] = row.pop('cross_report_exit_value_change_pct')
                        row['cross_report_exit_count_change_pct'] = row.pop('cross_report_exit_count_change_pct')
                    rows.append(row)
                all_rows = {r['year']: r for r in rows}
                for row in observed:
                    all_rows[row['year']] = row
                observed = [all_rows[y] for y in sorted(all_rows)]
            fields = probe.CAMBRIDGE_FIELDS if source == 'cambridge' else probe.KPMG_FIELDS
            # Normalize values through the exact same CSV format used by the probe.
            encoded = probe._csv_bytes(observed, fields)
            changed = not destination.exists() or destination.read_bytes() != encoded
            if changed:
                out_dir.mkdir(parents=True, exist_ok=True)
                atomic_write_bundle({destination: encoded}, transaction_key=destination)
            result = {'source': source, 'status': 'updated' if changed else 'unchanged',
                      'latest_year': end, 'rows': len(observed), 'file': str(destination)}
        except Exception as exc:
            result = {'source': source, 'status': 'retained_on_failure' if destination.exists() else 'unavailable',
                      'error': f'{type(exc).__name__}: {exc}', 'file': str(destination)}
        results.append(result)
        print(json.dumps(result, sort_keys=True), flush=True)
    return results
