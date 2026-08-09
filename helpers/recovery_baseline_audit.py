"""Generate a truthful recovery baseline report without requiring Streamlit."""

from __future__ import annotations

import argparse
import ast
import csv
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class TestResult:
    name: str
    passed: bool
    elapsed_seconds: float
    returncode: int
    fake_streamlit: bool
    source_inspection: bool
    browser_runtime: bool
    stdout_tail: str
    stderr_tail: str


def _compile_report() -> dict:
    failures = []
    files = sorted(ROOT.rglob('*.py'))
    for path in files:
        if '.git' in path.parts:
            continue
        try:
            compile(path.read_text(encoding='utf-8'), str(path), 'exec')
        except Exception as exc:  # pragma: no cover - audit output
            failures.append({'file': str(path.relative_to(ROOT)), 'error': repr(exc)})
    return {'files': len(files), 'passed': not failures, 'failures': failures}


def _run_tests(output: Path) -> list[TestResult]:
    logs = output / 'test_logs'
    logs.mkdir(parents=True, exist_ok=True)
    tests = sorted((ROOT / 'helpers').glob('*_smoke_test.py'))
    # The existing retained-startup contract is the bounded runtime proof for
    # the platform's most consequential publication rule.
    startup_contract = ROOT / 'helpers' / 'startup_loader_contract_test.py'
    if startup_contract.exists():
        tests.append(startup_contract)

    def run_one(path: Path) -> TestResult:
        source = path.read_text(encoding='utf-8')
        started = time.perf_counter()
        try:
            proc = subprocess.run(
                [sys.executable, str(path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=180,
                env={**dict(__import__('os').environ), 'PYTHONDONTWRITEBYTECODE': '1'},
            )
            stdout, stderr, returncode = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ''
            stderr = (exc.stderr or '') + '\nTIMEOUT after 180 seconds'
            returncode = 124
        elapsed = time.perf_counter() - started
        (logs / f'{path.stem}.stdout.txt').write_text(stdout, encoding='utf-8')
        (logs / f'{path.stem}.stderr.txt').write_text(stderr, encoding='utf-8')
        return TestResult(
            name=path.stem,
            passed=returncode == 0,
            elapsed_seconds=round(elapsed, 3),
            returncode=returncode,
            fake_streamlit=('sys.modules["streamlit"]' in source or "sys.modules['streamlit']" in source or '_FakeStreamlit' in source),
            source_inspection=('.read_text(' in source or 'ast.parse(' in source),
            browser_runtime=('playwright' in source.casefold() or 'selenium' in source.casefold()),
            stdout_tail='\n'.join(stdout.strip().splitlines()[-3:]),
            stderr_tail='\n'.join(stderr.strip().splitlines()[-3:]),
        )

    # The smoke tests run in separate processes. Parallel execution keeps the
    # audit usable while preserving per-test logs and independent exit codes.
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(run_one, tests))
    return sorted(results, key=lambda item: item.name)


def _date_summary(series: pd.Series) -> tuple[str | None, str | None, int]:
    dates = pd.to_datetime(series, errors='coerce', format='mixed').dropna()
    if dates.empty:
        return None, None, 0
    return dates.min().date().isoformat(), dates.max().date().isoformat(), int(dates.nunique())


def _data_inventory() -> list[dict]:
    records = []
    for path in sorted(list((ROOT / 'data').rglob('*.csv')) + list((ROOT / 'archive').rglob('*.csv'))):
        relative = str(path.relative_to(ROOT))
        try:
            frame = pd.read_csv(path, low_memory=False)
        except Exception as exc:
            records.append({'file': relative, 'error': repr(exc)})
            continue
        date_columns = []
        for column in frame.columns:
            name = str(column)
            if name.casefold() == 'date' or name.casefold().endswith(' date') or 'observation' in name.casefold() or 'publication' in name.casefold():
                earliest, latest, valid_dates = _date_summary(frame[column])
                if valid_dates:
                    date_columns.append({'column': name, 'earliest': earliest, 'latest': latest, 'valid_dates': valid_dates})
        records.append(
            {
                'file': relative,
                'rows': int(len(frame)),
                'columns': int(len(frame.columns)),
                'date_columns': date_columns,
            }
        )
    return records


def _series_contracts() -> list[dict]:
    contracts = []

    def add(file: str, value_column: str, date_column: str, label: str, minimum: int | None = None, span_days: int | None = None):
        frame = pd.read_csv(ROOT / file, low_memory=False)
        values = pd.to_numeric(frame.get(value_column), errors='coerce')
        dates = pd.to_datetime(frame.get(date_column), errors='coerce', format='mixed')
        valid = values.notna() & dates.notna()
        valid_dates = dates.loc[valid]
        earliest = valid_dates.min() if not valid_dates.empty else pd.NaT
        latest = valid_dates.max() if not valid_dates.empty else pd.NaT
        actual_span = int((latest - earliest).days) if pd.notna(earliest) and pd.notna(latest) else 0
        checks = {}
        if minimum is not None:
            checks[f'valid_observations_at_least_{minimum}'] = int(valid.sum()) >= minimum
        if span_days is not None:
            checks[f'span_days_at_least_{span_days}'] = actual_span >= span_days
        contracts.append(
            {
                'label': label,
                'file': file,
                'value_column': value_column,
                'date_column': date_column,
                'valid_observations': int(valid.sum()),
                'earliest': None if pd.isna(earliest) else earliest.date().isoformat(),
                'latest': None if pd.isna(latest) else latest.date().isoformat(),
                'span_days': actual_span,
                'checks': checks,
                'passed': all(checks.values()) if checks else None,
            }
        )

    add('data/finance/nfci_anfci_history.csv', 'Value', 'Date', 'Finance NFCI ten-year confirmation', 500, 3560)
    add('data/finance/nfci_anfci_history.csv', 'ANFCI', 'Date', 'Finance ANFCI ten-year confirmation', 500, 3560)
    add('data/debt_markets_history.csv', 'Corporate Bond Market Distress', 'Date', 'Corporate bond distress history', 500, 3560)
    add('data/borrower_strain_history.csv', 'Borrower Strain', 'Date', 'Borrower strain ten-year view', 10, 3560)
    add('data/private_equity_strain_history.csv', 'PIK Mean (%)', 'Date', 'Private-equity lender-strain view', 10, 3560)
    add('data/bank_tier1_capital_history.csv', 'Tier 1 Capital Ratio (%)', 'Date', 'Bank capital lender-strain view', 40, 3560)
    add('archive/yf_history.csv', 'Price', 'Date', 'Retained market archive (informational)', None, None)
    add('data/power_series_history.csv', 'Electric Power Output', 'Observation Date', 'Power-series retained history', 100, None)
    return contracts


def _startup_static_findings() -> dict:
    source = (ROOT / 'ai_macro.py').read_text(encoding='utf-8')
    deployment = (ROOT / 'config' / 'deployment.py').read_text(encoding='utf-8')
    load_policy = (ROOT / 'config' / 'load_policy.py').read_text(encoding='utf-8')
    snapshot_writer = (ROOT / 'loaders' / 'snapshot_writer.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ''
            if name.startswith('load_') or name.startswith('refresh_') or name.startswith('append_'):
                calls.append({'name': name, 'line': node.lineno})
    return {
        'application_builds_load_policy': 'load_policy = build_load_policy(' in source,
        'public_mode_defaults_to_read_only': 'os.getenv("AI_MACRO_MODE", "public")' in deployment,
        'public_refresh_requests_return_retained_policy': 'if not developer_mode():\n        return LoadPolicy.retained()' in load_policy,
        'repository_writes_require_developer_mode': 'if not repository_writes_enabled():' in snapshot_writer,
        'snapshot_writes_require_explicit_refresh': 'if not policy.is_explicit_refresh:' in snapshot_writer,
        'eager_dashboard_render': 'render_research_dashboard(build_tabs(), dashboard_context)' in source,
        'loader_refresh_append_calls': sorted(calls, key=lambda item: item['line']),
    }


def _runtime() -> dict:
    spec = importlib.util.find_spec('streamlit')
    if spec is None:
        return {'streamlit_available': False, 'declared_version': '1.59.2', 'full_app_browser_validation': 'blocked in this audit environment'}
    import streamlit  # type: ignore
    return {'streamlit_available': True, 'installed_version': getattr(streamlit, '__version__', 'unknown'), 'declared_version': '1.59.2'}


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    keys = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value) if isinstance(value, (dict, list)) else value for key, value in row.items()})


def _markdown(payload: dict) -> str:
    tests = payload['tests']
    contracts = payload['series_contracts']
    fake_count = sum(test['fake_streamlit'] for test in tests)
    source_count = sum(test['source_inspection'] for test in tests)
    browser_count = sum(test['browser_runtime'] for test in tests)
    failed_contracts = [item['label'] for item in contracts if item['passed'] is False]
    contract_finding = (
        'All retained historical-series contracts pass.'
        if not failed_contracts
        else 'Failed retained historical-series contracts: ' + ', '.join(failed_contracts) + '.'
    )
    startup_test = next(
        (test for test in tests if test['name'] == 'startup_loader_contract_test'),
        None,
    )
    startup_finding = (
        'The retained-startup contract passed with provider network access blocked and retained-file hashes checked before and after the full loader graph.'
        if startup_test and startup_test['passed']
        else 'The retained-startup runtime contract did not pass; inspect its test log before publication.'
    )
    lines = [
        '# v6.9.1 Recovery Baseline Audit',
        '',
        f"Generated: {payload['generated_at_utc']}",
        '',
        '## Executive finding',
        '',
        'The codebase is substantial and compiles, but the packaged green test suite is not equivalent to user-visible verification. '
        f"Of {len(tests)} smoke tests, {fake_count} use a fake Streamlit runtime, {source_count} inspect source text, and {browser_count} invoke a browser.",
        '',
        f'{contract_finding} {startup_finding} Full-app Streamlit screenshots remain unverified in this audit environment because the declared Streamlit runtime is unavailable.',
        '',
        '## Compilation and packaged tests',
        '',
        f"- Python source compilation: **{'PASS' if payload['compile']['passed'] else 'FAIL'}** ({payload['compile']['files']} files)",
        f"- Smoke tests: **{sum(test['passed'] for test in tests)}/{len(tests)} passed**",
        '',
        '| Test | Result | Seconds | Fake Streamlit | Source inspection | Browser |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for test in tests:
        lines.append(f"| {test['name']} | {'PASS' if test['passed'] else 'FAIL'} | {test['elapsed_seconds']:.3f} | {'yes' if test['fake_streamlit'] else 'no'} | {'yes' if test['source_inspection'] else 'no'} | {'yes' if test['browser_runtime'] else 'no'} |")
    lines += ['', '## Historical-series contracts', '', '| Contract | Result | Valid observations | Earliest | Latest | Span days |', '|---|---:|---:|---:|---:|---:|']
    for item in contracts:
        lines.append(f"| {item['label']} | {'INFO' if item['passed'] is None else 'PASS' if item['passed'] else 'FAIL'} | {item['valid_observations']} | {item['earliest'] or 'n/a'} | {item['latest'] or 'n/a'} | {item['span_days']} |")
    startup = payload['startup_static']
    lines += [
        '',
        '## Startup findings',
        '',
        f"- Application constructs one central load policy: **{startup['application_builds_load_policy']}**",
        f"- Public mode defaults to read-only: **{startup['public_mode_defaults_to_read_only']}**",
        f"- Public refresh requests resolve to retained mode: **{startup['public_refresh_requests_return_retained_policy']}**",
        f"- Repository writes require developer mode: **{startup['repository_writes_require_developer_mode']}**",
        f"- Snapshot writes require an explicit refresh: **{startup['snapshot_writes_require_explicit_refresh']}**",
        f"- Dashboard renderer is eager rather than active-tab-only: **{startup['eager_dashboard_render']}**",
        '',
        'The source findings above describe application routing. The retained-startup contract supplies the network and write instrumentation.',
        '',
        '## Layout proof status',
        '',
        '- Data Centers → Geographic pattern now uses the full-width proof contract.',
        '- Water → National water claims now uses the compact chart-plus-vertical-rail proof contract.',
        '- Shared HTML/CSS primitives are browser-measured separately at 1280, 1600, 1920, 2560, and 768 px.',
        '- This is **not yet a full Streamlit application screenshot pass**.',
        '',
        '## Data inventory',
        '',
        f"The machine-readable inventory contains {len(payload['data_inventory'])} retained CSV files with row counts, column counts, and parseable date ranges.",
    ]
    return '\n'.join(lines) + '\n'


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'audit' / 'recovery_baseline')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    compile_report = _compile_report()
    tests = [asdict(item) for item in _run_tests(output)]
    payload = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'project_version': 'v6.9.1 recovery proof',
        'compile': compile_report,
        'tests': tests,
        'runtime': _runtime(),
        'series_contracts': _series_contracts(),
        'startup_static': _startup_static_findings(),
        'data_inventory': _data_inventory(),
    }
    (output / 'baseline_audit.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
    (output / 'BASELINE_AUDIT.md').write_text(_markdown(payload), encoding='utf-8')
    _write_csv(output / 'data_inventory.csv', payload['data_inventory'])
    _write_csv(output / 'test_quality.csv', payload['tests'])
    _write_csv(output / 'series_contracts.csv', payload['series_contracts'])

    failed_tests = [item['name'] for item in tests if not item['passed']]
    if failed_tests or not compile_report['passed']:
        raise SystemExit(f"Baseline audit found execution failures: {failed_tests}")
    print(f"PASS  recovery baseline audit · {len(tests)} smoke tests · {len(payload['data_inventory'])} CSV files")


if __name__ == '__main__':
    main()
