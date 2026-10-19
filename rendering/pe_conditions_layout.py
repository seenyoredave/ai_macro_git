"""Compact, consistently formatted U.S. PE financial observations.

Presentation only: the validated data and Read narrative remain independent.
"""

from __future__ import annotations

from html import escape
import re


def _h(value: object) -> str:
    return escape(str(value), quote=True)


def _change(value: float | None, *, suffix: str, comparison: str) -> str:
    if value is None:
        return ""
    symbol = "↑" if value > 0 else "↓" if value < 0 else "→"
    return f'<span class="rm-pe-shift">{symbol} {abs(float(value)):.1f}{_h(suffix)} {_h(comparison)}</span>'


def _metric(label: str, value: str, *, detail: str = "") -> str:
    return (
        '<div class="rm-pe-measure">'
        f'<div class="rm-pe-measure-label">{_h(label)}</div>'
        f'<div class="rm-pe-measure-value">{_h(value)}</div>'
        + (f'<div class="rm-pe-measure-detail">{detail}</div>' if detail else '')
        + '</div>'
    )


def _stage(heading: str, period: str, contents: str) -> str:
    return (
        f'<section class="rm-pe-stage" aria-label="{_h(heading)}">'
        '<div class="rm-pe-stage-top">'
        f'<h3 class="rm-pe-stage-heading">{_h(heading)}</h3>'
        f'<span class="rm-pe-stage-period">{_h(period)}</span>'
        '</div>'
        f'<div class="rm-pe-stage-measures">{contents}</div>'
        '</section>'
    )


def _scale(scale: dict) -> str:
    if not scale:
        return ''
    total = float(scale['value_usd_bn']) / 1000
    year = int(scale['year'])
    return (
        '<section class="rm-pe-scale" aria-label="U.S. PE fund net assets (SEC Form PF)">'
        '<div class="rm-pe-scale-top">'
        '<span class="rm-pe-scale-label">U.S. PE fund net assets</span>'
        f'<span class="rm-pe-stage-period">{year}</span>'
        '</div>'
        f'<strong class="rm-pe-scale-amount">${total:,.2f}T</strong>'
        '</section>'
    )


def _buying(valuation: dict) -> str:
    if not valuation:
        return _stage('Valuations', 'Latest quarter',
                      '<p class="rm-pe-unavailable">Valuation unavailable</p>')
    period = str(valuation['period'])
    match = re.fullmatch(r'(20\d{2})Q([1-4])', period)
    when = f'Q{match[2]} {match[1]}' if match else period
    prior = f'Q{int(match[2]) - 1} {match[1]}' if match and match[2] != '1' else 'prior quarter'
    delta = valuation.get('quarter_change')
    measures = _metric('Average valuation', f'{float(valuation["value"]):.1f}× EBITDA')
    if delta is not None:
        change = float(delta)
        measures += _metric('Quarterly change', f'{change:+.1f}×', detail=f'vs {prior}')
    else:
        measures += _metric('Quarterly change', 'n/a')
    return _stage('Valuations', when, measures)


def _selling(exits: dict) -> str:
    if not exits:
        return _stage('Selling companies', 'Latest half-year',
                      '<p class="rm-pe-unavailable">Exit data unavailable</p>')
    year = int(exits['year'])
    previous = exits.get('prior_year')
    compare = f'vs H1 {int(previous)}' if previous is not None else 'vs prior H1'
    first = _metric('Exit transaction value', f'${float(exits["exit_value_usd_bn"]):,.1f}B',
                    detail=_change(exits.get('exit_value_change_pct'), suffix='%', comparison=compare))
    second = _metric('Number of exits', f'{int(exits["exit_count"]):,}',
                     detail=_change(exits.get('exit_count_change_pct'), suffix='%', comparison=compare))
    return _stage('Selling companies', f'H1 {year}', first + second)


def _investor_cash(lp: dict) -> str:
    if not lp:
        return _stage('Cash to investors', 'Latest year',
                      '<p class="rm-pe-unavailable">Investor cash-flow data unavailable</p>')
    first = _metric('Paid to investors', f'${float(lp["distributions_usd_bn"]):,.0f}B')
    second = _metric('Paid by investors', f'${float(lp["capital_calls_usd_bn"]):,.0f}B')
    return _stage('Cash to investors', str(int(lp['year'])), first + second)


def _investment_returns(returns: dict) -> str:
    if not returns:
        return _stage('Investor returns', 'Latest year',
                      '<p class="rm-pe-unavailable">Investment-return data unavailable</p>')
    year = int(returns['year'])
    first = _metric('Five-year annualized net return', f'{float(returns["pe_5y_annualized_net_pct"]):+.1f}%',
                    detail=f'{year-4}–{year}')
    second = _metric(f'{year} net return', f'{float(returns["pe_1y_net_pct"]):+.1f}%')
    return _stage('Investor returns', f'Through {year}', first + second)


def build_pe_conditions_markup(context: dict) -> str:
    """One leading scale card plus four uniformly styled metric cards."""
    context = context or {}
    lp = context.get('lp') or {}
    exits = context.get('exits') or {}
    valuation = context.get('valuation') or {}
    returns = context.get('returns') or {}
    scale = context.get('scale') or {}
    if not any((lp, exits, valuation, returns, scale)):
        return ''
    return ('<div class="rm-pe-capital-flow">'
            + _scale(scale) + '<div class="rm-pe-journey">'
            + _buying(valuation) + _selling(exits) + _investor_cash(lp) + _investment_returns(returns)
            + '</div></div>')
