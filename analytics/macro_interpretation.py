"""Deterministic interpretation layer for the AI Macro view.

The module translates the platform's measured state into a compact headline,
summary, pressure factors, resilience factors, and material changes. It does not
use a language model, random phrasing, or ungrounded causal claims.
"""

from __future__ import annotations

from collections import Counter
import math

import numpy as np
import pandas as pd

from analytics.financial_conditions import nfci_snapshot


MACRO_INTERPRETATION_VERSION = "1.0"


def _number(value) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric) or not np.isfinite(numeric):
        return np.nan
    return float(numeric)


def _fmt(value, digits=1, *, signed=False, suffix="") -> str:
    numeric = _number(value)
    if pd.isna(numeric):
        return "n/a"
    spec = f"+.{digits}f" if signed else f".{digits}f"
    return f"{numeric:{spec}}{suffix}"


def _series_frame(payload) -> pd.DataFrame:
    if not isinstance(payload, pd.DataFrame) or payload.empty:
        return pd.DataFrame(columns=["Date", "Value"])
    if not {"Date", "Value"}.issubset(payload.columns):
        return pd.DataFrame(columns=["Date", "Value"])
    frame = payload[["Date", "Value"]].copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce", format="mixed")
    frame["Value"] = pd.to_numeric(frame["Value"], errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    return (
        frame.dropna(subset=["Date", "Value"])
        .sort_values("Date", kind="stable")
        .drop_duplicates("Date", keep="last")
        .reset_index(drop=True)
    )


def _history_frame(history, value_column, *, version_column=None, required_version=None):
    if not isinstance(history, pd.DataFrame) or history.empty:
        return pd.DataFrame(columns=["Date", "Value"])
    if "Date" not in history.columns or value_column not in history.columns:
        return pd.DataFrame(columns=["Date", "Value"])

    frame = history.copy()
    if version_column and required_version is not None:
        if version_column not in frame.columns:
            return pd.DataFrame(columns=["Date", "Value"])
        frame = frame[frame[version_column].astype(str) == str(required_version)].copy()

    frame = frame[["Date", value_column]].rename(columns={value_column: "Value"})
    return _series_frame(frame)


def _prior_delta(series, current, *, lookback=1):
    current = _number(current)
    frame = _series_frame(series)
    if pd.isna(current) or frame.empty:
        return np.nan

    values = frame["Value"].tolist()
    if values and math.isclose(values[-1], current, rel_tol=0.0, abs_tol=1e-10):
        values = values[:-1]
    if len(values) < lookback:
        return np.nan
    return current - float(values[-lookback])


def _consecutive_direction(series, current, *, adverse_when_higher=True, tolerance=0.0):
    """Count consecutive adverse or favorable moves ending at current."""
    current = _number(current)
    frame = _series_frame(series)
    if pd.isna(current):
        return 0

    values = frame["Value"].tolist()
    if not values or not math.isclose(values[-1], current, rel_tol=0.0, abs_tol=1e-10):
        values.append(current)
    if len(values) < 2:
        return 0

    streak = 0
    for index in range(len(values) - 1, 0, -1):
        change = values[index] - values[index - 1]
        adverse = change > tolerance if adverse_when_higher else change < -tolerance
        if not adverse:
            break
        streak += 1
    return streak


def _direction(delta, *, threshold, adverse_when_higher=True):
    delta = _number(delta)
    if pd.isna(delta):
        return "unknown"
    adverse_delta = delta if adverse_when_higher else -delta
    if adverse_delta >= threshold:
        return "rising"
    if adverse_delta <= -threshold:
        return "easing"
    return "stable"


def _level(value, thresholds):
    value = _number(value)
    if pd.isna(value):
        return 0
    return int(sum(value >= threshold for threshold in thresholds))


def _factor(
    *,
    key,
    domain,
    kind,
    severity,
    direction,
    statement,
    summary_clause,
    score=0.0,
):
    return {
        "key": key,
        "domain": domain,
        "kind": kind,
        "severity": int(max(0, severity)),
        "direction": direction,
        "statement": statement,
        "summary_clause": summary_clause,
        "score": float(score),
    }


def _select_diverse(factors, limit=3):
    ranked = sorted(
        [factor for factor in factors if factor.get("statement")],
        key=lambda item: (
            int(item.get("severity", 0)),
            float(item.get("score", 0.0)),
        ),
        reverse=True,
    )
    chosen = []
    used_domains = set()
    for factor in ranked:
        if factor["domain"] in used_domains:
            continue
        chosen.append(factor)
        used_domains.add(factor["domain"])
        if len(chosen) >= limit:
            return chosen
    for factor in ranked:
        if factor in chosen:
            continue
        chosen.append(factor)
        if len(chosen) >= limit:
            break
    return chosen


def _join_clauses(clauses):
    clean = [str(item).strip().rstrip(".") for item in clauses if str(item).strip()]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} and {clean[1]}"
    return f"{', '.join(clean[:-1])}, and {clean[-1]}"


def _funding_state(funding_current):
    internal = _number((funding_current or {}).get("internal_funding_coverage"))
    runway = _number((funding_current or {}).get("cash_reserve_coverage_years"))
    if pd.isna(internal) and pd.isna(runway):
        return "unknown", 0

    score = 0
    if pd.notna(internal):
        score += 2 if internal >= 1.5 else 1 if internal >= 1.0 else -1 if internal >= 0.75 else -2
    if pd.notna(runway):
        score += 2 if runway >= 2.0 else 1 if runway >= 1.0 else -1 if runway >= 0.5 else -2

    if score >= 3:
        return "strong", 3
    if score >= 1:
        return "adequate", 2
    if score >= -1:
        return "thin", 1
    return "weak", 0


def _metric_change(
    changes,
    *,
    key,
    label,
    current,
    delta,
    threshold,
    unit="points",
    adverse_when_higher=True,
    score_scale=None,
):
    current = _number(current)
    delta = _number(delta)
    if pd.isna(current) or pd.isna(delta) or abs(delta) < threshold:
        return
    direction = "increased" if delta > 0 else "decreased"
    if not adverse_when_higher:
        direction = "improved" if delta > 0 else "weakened"
    if unit == "%":
        statement = f"{label} {direction} {abs(delta):.1f}%."
    elif unit == "x":
        statement = f"{label} {direction} to {current:.2f}×."
    else:
        statement = f"{label} {direction} by {abs(delta):.1f} points."
    scale = score_scale or threshold
    changes.append(
        {
            "key": key,
            "statement": statement,
            "score": abs(delta) / max(float(scale), 1e-9),
        }
    )


def build_macro_interpretation(
    *,
    regime_metrics,
    macro_history,
    debt_markets_data=None,
    energy_data=None,
    fred_data=None,
    nfci_history=None,
):
    """Build a compact, deterministic interpretation of the current state."""
    regime = regime_metrics or {}
    macro_history = macro_history if isinstance(macro_history, pd.DataFrame) else pd.DataFrame()
    debt_markets_data = debt_markets_data or {}
    energy_data = energy_data or {}
    funding = (regime.get("Deployment Funding Mix", {}) or {}).get("current", {}) or {}
    funding_series = (regime.get("Deployment Funding Mix", {}) or {}).get("series", {}) or {}

    borrower = _number(regime.get("Borrower Strain"))
    lender = _number(regime.get("Lender Strain"))
    power_stress = _number(regime.get("Power Stress Index"))
    capacity_gap = _number(regime.get("Power Capacity Gap"))
    validation_gap = _number(regime.get("Economic Validation Gap"))
    speculation_gap = _number(regime.get("Speculation Gap"))
    concentration = _number(regime.get("Concentration HHI"))
    aei = _number(regime.get("AI Equity Index"))
    adi = _number(regime.get("AI Development Intensity"))

    borrower_series = _history_frame(
        macro_history,
        "Borrower Strain",
        version_column="Borrower Strain Version",
        required_version=regime.get("Borrower Strain Version"),
    )
    lender_series = _history_frame(
        macro_history,
        "Lender Strain",
        version_column="Lender Strain Version",
        required_version=regime.get("Lender Strain Version"),
    )
    power_series = _history_frame(
        macro_history,
        "Power Stress Index",
        version_column="Power Stress Version",
        required_version=regime.get("Power Stress Version"),
    )
    capacity_gap_series = _history_frame(
        macro_history,
        "Power Capacity Gap",
        version_column="Power Capacity Gap Version",
        required_version=regime.get("Power Capacity Gap Version"),
    )
    validation_series = _history_frame(
        macro_history,
        "Economic Validation Gap",
        version_column="EVG Version",
        required_version=regime.get("EVG Version"),
    )
    aei_series = _history_frame(
        macro_history,
        "AI Equity Index",
        version_column="AEI Version",
        required_version=regime.get("AEI Version"),
    )
    adi_series = _history_frame(
        macro_history,
        "AI Development Intensity",
        version_column="ADI Version",
        required_version=regime.get("ADI Version"),
    )
    concentration_series = _history_frame(macro_history, "Concentration HHI")

    borrower_delta = _prior_delta(borrower_series, borrower)
    lender_delta = _prior_delta(lender_series, lender)
    power_delta = _prior_delta(power_series, power_stress)
    capacity_gap_delta = _prior_delta(capacity_gap_series, capacity_gap)
    validation_delta = _prior_delta(validation_series, validation_gap)
    aei_delta = _prior_delta(aei_series, aei)
    adi_delta = _prior_delta(adi_series, adi)
    concentration_delta = _prior_delta(concentration_series, concentration)

    pressures = []
    resilience = []

    # Funding capacity and contractual burden.
    internal = _number(funding.get("internal_funding_coverage"))
    runway = _number(funding.get("cash_reserve_coverage_years"))
    debt_pulse = _number(funding.get("debt_financing_pulse"))
    commitments = _number(funding.get("forward_commitment_load"))
    funding_level, funding_strength = _funding_state(funding)

    if pd.notna(internal):
        if internal >= 1.0:
            severity = 3 if internal >= 1.5 else 2
            resilience.append(
                _factor(
                    key="internal-funding",
                    domain="funding",
                    kind="resilience",
                    severity=severity,
                    direction="stable",
                    statement=f"Operating cash flow covers {_fmt(internal, 2, suffix='×')} current CapEx.",
                    summary_clause="internal cash generation covers current capital spending",
                    score=internal,
                )
            )
        else:
            pressures.append(
                _factor(
                    key="internal-funding",
                    domain="funding",
                    kind="pressure",
                    severity=3 if internal < 0.75 else 2,
                    direction="rising",
                    statement=f"Operating cash flow covers only {_fmt(internal, 2, suffix='×')} current CapEx.",
                    summary_clause="internal cash generation no longer covers current capital spending",
                    score=1.0 - internal,
                )
            )

    if pd.notna(runway):
        if runway >= 1.0:
            resilience.append(
                _factor(
                    key="cash-runway",
                    domain="liquidity",
                    kind="resilience",
                    severity=3 if runway >= 2.0 else 2,
                    direction="stable",
                    statement=f"Cash reserves cover about {_fmt(runway, 2, suffix=' years')} of current CapEx.",
                    summary_clause="liquid reserves provide additional funding runway",
                    score=runway,
                )
            )
        else:
            pressures.append(
                _factor(
                    key="cash-runway",
                    domain="liquidity",
                    kind="pressure",
                    severity=3 if runway < 0.5 else 2,
                    direction="rising",
                    statement=f"Cash reserves cover less than one year of current CapEx ({_fmt(runway, 2, suffix=' years')}).",
                    summary_clause="cash reserves provide limited buildout runway",
                    score=1.0 - runway,
                )
            )

    if pd.notna(commitments) and commitments >= 1.5:
        severity = 4 if commitments >= 3.0 else 3 if commitments >= 2.0 else 2
        pressures.append(
            _factor(
                key="commitments",
                domain="commitments",
                kind="pressure",
                severity=severity,
                direction="stable",
                statement=f"Forward commitments equal {_fmt(commitments, 2, suffix='×')} trailing CapEx.",
                summary_clause="forward commitments are large relative to the current buildout rate",
                score=commitments,
            )
        )

    if pd.notna(debt_pulse) and debt_pulse >= 0.5:
        pressures.append(
            _factor(
                key="debt-pulse",
                domain="funding",
                kind="pressure",
                severity=3 if debt_pulse >= 1.0 else 2,
                direction="rising",
                statement=f"Debt expanded by {_fmt(debt_pulse, 2, suffix='×')} current CapEx over twelve months.",
                summary_clause="debt formation is contributing materially to current funding",
                score=debt_pulse,
            )
        )

    # Borrower and lender strain.
    for key, label, value, delta, series in (
        ("borrower-strain", "Borrower strain", borrower, borrower_delta, borrower_series),
        ("lender-strain", "Lender strain", lender, lender_delta, lender_series),
    ):
        if pd.isna(value):
            continue
        severity = _level(value, (10.0, 25.0, 50.0))
        direction = _direction(delta, threshold=1.0)
        streak = _consecutive_direction(series, value, tolerance=0.75)
        if severity >= 1 or direction == "rising":
            if streak >= 2:
                movement = f"has increased for {streak} consecutive observations"
            elif direction == "rising":
                movement = "is rising"
            elif direction == "easing":
                movement = "is easing but remains above neutral"
            else:
                movement = "remains above neutral"
            qualifier = " from a low level" if severity == 0 else ""
            pressures.append(
                _factor(
                    key=key,
                    domain="credit",
                    kind="pressure",
                    severity=max(1, severity),
                    direction=direction,
                    statement=f"{label} {movement}{qualifier}.",
                    summary_clause=f"{label.lower()} is moving higher" if direction == "rising" else f"{label.lower()} remains elevated",
                    score=abs(value) + (abs(delta) if pd.notna(delta) else 0),
                )
            )
        elif value <= -10:
            resilience.append(
                _factor(
                    key=key,
                    domain="credit",
                    kind="resilience",
                    severity=2 if value > -25 else 3,
                    direction=direction,
                    statement=f"{label} remains below neutral.",
                    summary_clause=f"{label.lower()} remains contained",
                    score=abs(value),
                )
            )

    # Corporate bond market functioning.
    debt_series = (debt_markets_data.get("series", {}) or {})
    debt_items = []
    for name in (
        "Corporate Bond Market Distress",
        "Investment-Grade Bond Distress",
        "High-Yield Bond Distress",
    ):
        item = debt_series.get(name, {}) or {}
        value = _number(item.get("value"))
        history = _series_frame(item.get("history"))
        delta = _prior_delta(history, value, lookback=min(4, max(1, len(history))))
        debt_items.append((name, value, delta, history))

    valid_debt = [item for item in debt_items if pd.notna(item[1])]
    if valid_debt:
        dominant_name, dominant_value, dominant_delta, dominant_history = max(
            valid_debt, key=lambda item: item[1]
        )
        debt_severity = _level(dominant_value, (0.15, 0.30, 0.50))
        debt_direction = _direction(dominant_delta, threshold=0.03)
        dominant_short = dominant_name.replace(" Bond Distress", "")
        if debt_severity >= 1 or debt_direction == "rising":
            if debt_direction == "rising":
                statement = f"Corporate bond-market distress is rising, led by {dominant_short.lower()} credit."
                clause = "corporate bond-market pressure is increasing"
            elif debt_direction == "easing":
                statement = f"Corporate bond-market distress is easing but remains most pronounced in {dominant_short.lower()} credit."
                clause = "corporate bond-market pressure remains elevated"
            else:
                statement = f"Corporate bond-market distress remains most pronounced in {dominant_short.lower()} credit."
                clause = "corporate bond-market pressure remains elevated"
            pressures.append(
                _factor(
                    key="debt-markets",
                    domain="credit",
                    kind="pressure",
                    severity=max(1, debt_severity),
                    direction=debt_direction,
                    statement=statement,
                    summary_clause=clause,
                    score=dominant_value * 10 + (abs(dominant_delta) if pd.notna(dominant_delta) else 0),
                )
            )
        else:
            resilience.append(
                _factor(
                    key="debt-markets",
                    domain="credit",
                    kind="resilience",
                    severity=2,
                    direction=debt_direction,
                    statement="Corporate bond markets remain broadly functional.",
                    summary_clause="public debt markets remain functional",
                    score=1.0 - dominant_value,
                )
            )

    # Broad financial conditions.
    nfci = nfci_snapshot(fred_data or {}, nfci_history)
    nfci_value = _number(nfci.get("value"))
    nfci_change = _number(nfci.get("three_month_change"))
    if pd.notna(nfci_value):
        nfci_direction = _direction(nfci_change, threshold=0.10)
        if nfci_value > 0.10 or nfci_direction == "rising":
            pressures.append(
                _factor(
                    key="nfci",
                    domain="financial-conditions",
                    kind="pressure",
                    severity=3 if nfci_value >= 0.50 else 2 if nfci_value > 0.10 else 1,
                    direction=nfci_direction,
                    statement=(
                        "Broad financial conditions are tightening."
                        if nfci_direction == "rising"
                        else "Broad financial conditions are tighter than average."
                    ),
                    summary_clause="broad financial conditions are tightening" if nfci_direction == "rising" else "broad financial conditions remain tight",
                    score=max(nfci_value, 0) + (max(nfci_change, 0) if pd.notna(nfci_change) else 0),
                )
            )
        elif nfci_value < -0.10:
            resilience.append(
                _factor(
                    key="nfci",
                    domain="financial-conditions",
                    kind="resilience",
                    severity=3 if nfci_value <= -0.50 else 2,
                    direction=nfci_direction,
                    statement="Broad financial conditions remain looser than their long-run average.",
                    summary_clause="broad financial conditions remain supportive",
                    score=abs(nfci_value),
                )
            )

    # Energy and power-system pressure.
    energy_series = (energy_data.get("series", {}) or {})
    gas_change = _number((energy_series.get("Natural Gas Price", {}) or {}).get("change_pct"))
    oil_change = _number((energy_series.get("WTI Crude Oil", {}) or {}).get("change_pct"))
    if pd.notna(oil_change) and oil_change >= 10:
        pressures.append(
            _factor(
                key="oil-price",
                domain="energy",
                kind="pressure",
                severity=3 if oil_change >= 25 else 2,
                direction="rising",
                statement=f"WTI crude oil is up {_fmt(oil_change, 1, suffix='%')} over four weeks.",
                summary_clause="oil prices have risen sharply",
                score=oil_change / 10,
            )
        )
    if pd.notna(gas_change) and gas_change >= 15:
        pressures.append(
            _factor(
                key="gas-price",
                domain="energy",
                kind="pressure",
                severity=3 if gas_change >= 35 else 2,
                direction="rising",
                statement=f"Henry Hub natural gas is up {_fmt(gas_change, 1, suffix='%')} over four weeks.",
                summary_clause="natural-gas prices are rising",
                score=gas_change / 15,
            )
        )

    if pd.notna(capacity_gap):
        capacity_severity = _level(capacity_gap, (20.0, 40.0, 65.0))
        capacity_direction = _direction(capacity_gap_delta, threshold=2.0)
        if capacity_severity >= 1 or capacity_direction == "rising":
            pressures.append(
                _factor(
                    key="capacity-gap",
                    domain="energy",
                    kind="pressure",
                    severity=max(1, capacity_severity),
                    direction=capacity_direction,
                    statement=(
                        "Deployment pressure is moving further ahead of measured power-system response."
                        if capacity_direction == "rising"
                        else "Deployment pressure remains ahead of measured power-system response."
                    ),
                    summary_clause="deployment is outpacing measured power-system response",
                    score=max(capacity_gap, 0) / 10 + (max(capacity_gap_delta, 0) if pd.notna(capacity_gap_delta) else 0),
                )
            )
        elif capacity_gap <= -20:
            resilience.append(
                _factor(
                    key="capacity-gap",
                    domain="energy",
                    kind="resilience",
                    severity=3 if capacity_gap <= -40 else 2,
                    direction=capacity_direction,
                    statement="Measured power-system response is advancing ahead of deployment pressure.",
                    summary_clause="measured power-system response is keeping pace",
                    score=abs(capacity_gap),
                )
            )

    if pd.notna(power_stress):
        power_severity = _level(power_stress, (15.0, 35.0, 60.0))
        power_direction = _direction(power_delta, threshold=2.0)
        if power_severity >= 1 or power_direction == "rising":
            pressures.append(
                _factor(
                    key="power-stress",
                    domain="energy",
                    kind="pressure",
                    severity=max(1, power_severity),
                    direction=power_direction,
                    statement=(
                        "Power-system pressure is increasing."
                        if power_direction == "rising"
                        else "Power-system pressure remains above reference."
                    ),
                    summary_clause="power-system pressure is increasing" if power_direction == "rising" else "power-system pressure remains elevated",
                    score=max(power_stress, 0) / 10,
                )
            )
        elif power_stress <= -10:
            resilience.append(
                _factor(
                    key="power-stress",
                    domain="energy",
                    kind="resilience",
                    severity=2,
                    direction=power_direction,
                    statement="The national power-system proxy remains below its pressure reference.",
                    summary_clause="the national power-system proxy retains headroom",
                    score=abs(power_stress),
                )
            )

    # Validation, equity expectations, and concentration.
    if pd.notna(validation_gap):
        validation_direction = _direction(validation_delta, threshold=3.0)
        if validation_gap >= 15:
            pressures.append(
                _factor(
                    key="validation-gap",
                    domain="validation",
                    kind="pressure",
                    severity=3 if validation_gap >= 35 else 2,
                    direction=validation_direction,
                    statement="AI deployment is running ahead of realized economic validation.",
                    summary_clause="deployment is running ahead of realized economic validation",
                    score=validation_gap / 10,
                )
            )
        elif validation_gap <= -15:
            resilience.append(
                _factor(
                    key="validation-gap",
                    domain="validation",
                    kind="resilience",
                    severity=3 if validation_gap <= -35 else 2,
                    direction=validation_direction,
                    statement="Realized economic validation is keeping pace with or exceeding deployment.",
                    summary_clause="realized economic validation is keeping pace with deployment",
                    score=abs(validation_gap) / 10,
                )
            )

    if pd.notna(speculation_gap):
        if speculation_gap >= 20:
            pressures.append(
                _factor(
                    key="speculation-gap",
                    domain="market",
                    kind="pressure",
                    severity=3 if speculation_gap >= 40 else 2,
                    direction="rising" if _prior_delta(_history_frame(macro_history, "Speculation Gap"), speculation_gap) > 2 else "stable",
                    statement="AI equity pricing is running ahead of observable development.",
                    summary_clause="equity pricing is running ahead of observable development",
                    score=speculation_gap / 10,
                )
            )
        elif speculation_gap <= -20:
            resilience.append(
                _factor(
                    key="speculation-gap",
                    domain="market",
                    kind="resilience",
                    severity=2,
                    direction="stable",
                    statement="AI equity pricing is not running ahead of observable development.",
                    summary_clause="equity pricing is not outrunning observable development",
                    score=abs(speculation_gap) / 10,
                )
            )

    if pd.notna(concentration) and concentration >= 30:
        pressures.append(
            _factor(
                key="concentration",
                domain="market",
                kind="pressure",
                severity=3 if concentration >= 50 else 2,
                direction=_direction(concentration_delta, threshold=0.75),
                statement="AI market value is concentrated in a small number of companies.",
                summary_clause="market resilience is concentrated among a small number of firms",
                score=concentration / 10,
            )
        )

    # Material changes: select mechanically, not editorially.
    changes = []
    _metric_change(changes, key="aei", label="AI equity conditions", current=aei, delta=aei_delta, threshold=1.0)
    _metric_change(changes, key="adi", label="AI development intensity", current=adi, delta=adi_delta, threshold=1.5)
    _metric_change(changes, key="borrower", label="Borrower strain", current=borrower, delta=borrower_delta, threshold=1.0)
    _metric_change(changes, key="lender", label="Lender strain", current=lender, delta=lender_delta, threshold=1.0)
    _metric_change(changes, key="power", label="Power-system pressure", current=power_stress, delta=power_delta, threshold=2.0)
    _metric_change(changes, key="capacity", label="Power Capacity Gap", current=capacity_gap, delta=capacity_gap_delta, threshold=2.0)
    _metric_change(changes, key="validation", label="Economic Validation Gap", current=validation_gap, delta=validation_delta, threshold=3.0)
    _metric_change(changes, key="concentration", label="Market concentration", current=concentration, delta=concentration_delta, threshold=0.75)

    commitment_series = _series_frame(funding_series.get("forward_commitment_load"))
    commitment_delta = _prior_delta(commitment_series, commitments)
    _metric_change(
        changes,
        key="commitments",
        label="Forward commitment load",
        current=commitments,
        delta=commitment_delta,
        threshold=0.15,
        unit="x",
    )

    if pd.notna(oil_change) and abs(oil_change) >= 10:
        changes.append(
            {
                "key": "oil",
                "statement": f"WTI crude oil {'rose' if oil_change > 0 else 'fell'} {abs(oil_change):.1f}% over four weeks.",
                "score": abs(oil_change) / 10,
            }
        )
    if pd.notna(gas_change) and abs(gas_change) >= 15:
        changes.append(
            {
                "key": "gas",
                "statement": f"Henry Hub natural gas {'rose' if gas_change > 0 else 'fell'} {abs(gas_change):.1f}% over four weeks.",
                "score": abs(gas_change) / 15,
            }
        )
    if pd.notna(nfci_change) and abs(nfci_change) >= 0.10:
        changes.append(
            {
                "key": "nfci",
                "statement": f"Broad financial conditions {'tightened' if nfci_change > 0 else 'eased'} over three months.",
                "score": abs(nfci_change) / 0.10,
            }
        )

    selected_pressure = _select_diverse(pressures, limit=3)
    selected_resilience = _select_diverse(resilience, limit=3)
    selected_changes = sorted(changes, key=lambda item: item["score"], reverse=True)[:3]

    # Domain states remain compact but are archived for later transition analysis.
    domain_names = ("funding", "credit", "financial-conditions", "energy", "validation", "market", "commitments", "liquidity")
    domain_states = {}
    for domain in domain_names:
        domain_pressures = [item for item in pressures if item["domain"] == domain]
        domain_resilience = [item for item in resilience if item["domain"] == domain]
        severity = max([item["severity"] for item in domain_pressures], default=0)
        support = max([item["severity"] for item in domain_resilience], default=0)
        directions = Counter(item["direction"] for item in domain_pressures)
        direction = "rising" if directions["rising"] else "easing" if directions["easing"] else "stable"
        if severity >= 3:
            level = "high pressure"
        elif severity >= 2:
            level = "elevated pressure"
        elif severity >= 1:
            level = "mild pressure"
        elif support >= 3:
            level = "strong support"
        elif support >= 1:
            level = "supportive"
        else:
            level = "neutral"
        domain_states[domain] = {
            "level": level,
            "direction": direction,
            "pressure_severity": severity,
            "support_strength": support,
        }

    pressure_domains = {
        item["domain"] for item in pressures if item["severity"] >= 2
    }
    rising_domains = {
        item["domain"] for item in pressures if item["direction"] == "rising"
    }
    max_pressure = max([item["severity"] for item in pressures], default=0)
    strong_resilience = len([item for item in resilience if item["severity"] >= 2])

    required_values = [
        aei,
        adi,
        borrower,
        lender,
        power_stress,
        capacity_gap,
        internal,
        runway,
        commitments,
    ]
    available = sum(pd.notna(value) for value in required_values)
    confidence = "high" if available >= 8 else "moderate" if available >= 6 else "low"

    if confidence == "low":
        headline = "Partial current-state view"
    elif funding_level == "weak" and ("credit" in pressure_domains or "financial-conditions" in pressure_domains):
        headline = "Funding-constrained"
    elif max_pressure >= 3 and len(pressure_domains) >= 3 and strong_resilience <= 1:
        headline = "Broad deterioration"
    elif pressure_domains and not rising_domains and any(item["direction"] == "easing" for item in pressures):
        headline = "Stabilizing after elevated pressure"
    elif funding_strength >= 2:
        if len(pressure_domains) >= 2:
            if rising_domains == {"credit"} or rising_domains == {"financial-conditions"}:
                headline = "Resilient, with rising financing pressure"
            elif rising_domains == {"energy"}:
                headline = "Resilient, with rising energy pressure"
            elif commitments >= 3 and len(rising_domains) <= 1:
                headline = "Resilient, with elevated commitments"
            else:
                headline = "Resilient, with broader pressure"
        elif pressure_domains:
            dominant = selected_pressure[0]["domain"] if selected_pressure else ""
            modifier = {
                "credit": "financing pressure",
                "financial-conditions": "tighter financial conditions",
                "energy": "energy pressure",
                "commitments": "elevated commitments",
                "validation": "a validation gap",
                "market": "concentrated market risk",
            }.get(dominant, "contained pressure")
            headline = f"Resilient, with {modifier}"
        else:
            headline = "Resilient"
    elif len(pressure_domains) >= 2:
        headline = "Pressure building"
    else:
        headline = "Mixed conditions"

    if funding_level == "strong":
        opening = "The buildout remains supported by strong internal funding capacity"
    elif funding_level == "adequate":
        opening = "The buildout remains financeable at the current operating and cash base"
    elif funding_level == "thin":
        opening = "The buildout remains funded, but financial headroom is narrowing"
    elif funding_level == "weak":
        opening = "The buildout is becoming more dependent on outside capital"
    else:
        opening = "The buildout's funding position is only partially observable"

    pressure_clauses = [item["summary_clause"] for item in selected_pressure[:2]]
    if pressure_clauses:
        summary = f"{opening}, while {_join_clauses(pressure_clauses)}."
    else:
        summary = f"{opening}, and the main financing and infrastructure pressure readings remain contained."
    summary_resilience = next(
        (
            item
            for item in selected_resilience
            if item.get("domain") not in {"funding", "liquidity"}
        ),
        None,
    )
    if summary_resilience:
        summary += f" {summary_resilience['statement']}"

    if not selected_changes:
        selected_changes = [
            {
                "key": "no-material-change",
                "statement": "No material change was detected across the tracked domains.",
                "score": 0.0,
            }
        ]

    return {
        "headline": headline,
        "summary": summary,
        "pressure_factors": [item["statement"] for item in selected_pressure],
        "resilience_factors": [item["statement"] for item in selected_resilience],
        "changes": [item["statement"] for item in selected_changes],
        "domains": domain_states,
        "confidence": confidence,
        "version": MACRO_INTERPRETATION_VERSION,
    }
