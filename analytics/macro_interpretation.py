"""Deterministic interpretation layer for the AI Macro Snapshot.

The module translates measured platform state into a compact headline,
expansion factors, constraints, and a weekly context rollup. It does not use a
language model, random phrasing, or ungrounded causal claims.
"""

from __future__ import annotations

from collections import Counter
import math

import numpy as np
import pandas as pd

from analytics.financial_conditions import nfci_snapshot


MACRO_INTERPRETATION_VERSION = "2.0"


MACRO_STATE_HEADLINES = frozenset(
    {
        "Partial snapshot",
        "Broad expansion",
        "Expansion continuing",
        "Uneven expansion",
        "Expansion with emerging constraints",
        "Expansion with material constraints",
        "Constraints broadening",
        "Financing constrained",
        "Broad contraction",
        "Stabilizing",
        "Expansion reaccelerating",
    }
)


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
    return _series_frame(frame[["Date", value_column]].rename(columns={value_column: "Value"}))


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


def _previous_completed_friday(as_of=None) -> pd.Timestamp:
    current = pd.Timestamp(as_of or pd.Timestamp.now()).normalize()
    days_since_friday = (current.weekday() - 4) % 7
    if days_since_friday == 0:
        days_since_friday = 7
    return current - pd.Timedelta(days=days_since_friday)


def _weekly_delta(series, current, *, as_of=None):
    """Compare a current reading with the last observation at/before prior Friday.

    A metric only enters the weekly rollup when its newest observation arrived
    after that Friday. Slow-moving series therefore do not repeat annual or
    monthly changes every week merely because the level remains noteworthy.
    """
    current = _number(current)
    frame = _series_frame(series)
    if pd.isna(current) or frame.empty:
        return np.nan
    current_date = frame.iloc[-1]["Date"]
    if not math.isclose(float(frame.iloc[-1]["Value"]), current, rel_tol=0.0, abs_tol=1e-10):
        current_date = pd.Timestamp(as_of or pd.Timestamp.now()).normalize()
    baseline_date = _previous_completed_friday(as_of)
    if pd.Timestamp(current_date).normalize() <= baseline_date:
        return np.nan
    prior = frame.loc[frame["Date"] <= baseline_date]
    if prior.empty:
        return np.nan
    return current - float(prior.iloc[-1]["Value"])


def _consecutive_direction(series, current, *, adverse_when_higher=True, tolerance=0.0):
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
    *, key, domain, kind, severity, direction, statement, score=0.0
):
    return {
        "key": key,
        "domain": domain,
        "kind": kind,
        "severity": int(max(0, severity)),
        "direction": direction,
        "statement": statement,
        "score": float(score),
    }


def _select_diverse(factors, limit=3):
    ranked = sorted(
        [factor for factor in factors if factor.get("statement")],
        key=lambda item: (int(item.get("severity", 0)), float(item.get("score", 0.0))),
        reverse=True,
    )
    chosen, used_domains = [], set()
    for factor in ranked:
        if factor["domain"] in used_domains:
            continue
        chosen.append(factor)
        used_domains.add(factor["domain"])
        if len(chosen) >= limit:
            return chosen
    for factor in ranked:
        if factor not in chosen:
            chosen.append(factor)
        if len(chosen) >= limit:
            break
    return chosen


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


def _metric_change(changes, *, key, label, current, delta, threshold, unit="points", score_scale=None):
    current, delta = _number(current), _number(delta)
    if pd.isna(current) or pd.isna(delta) or abs(delta) < threshold:
        return
    if unit == "%":
        statement = f"{label} {'increased' if delta > 0 else 'decreased'} {abs(delta):.1f}%."
    elif unit == "x":
        verb = "rose" if delta > 0 else "fell"
        statement = f"{label} {verb} to {current:.2f} times annual capital spending."
    elif unit == "percentage points":
        statement = f"{label} {'increased' if delta > 0 else 'decreased'} {abs(delta):.1f} percentage points."
    else:
        statement = f"{label} {'increased' if delta > 0 else 'decreased'} by {abs(delta):.1f} points."
    changes.append(
        {
            "key": key,
            "statement": statement,
            "score": abs(delta) / max(float(score_scale or threshold), 1e-9),
        }
    )


def _energy_item(energy_data, name):
    return (((energy_data or {}).get("series", {}) or {}).get(name, {}) or {})


def build_macro_interpretation(
    *,
    regime_metrics,
    macro_history,
    debt_markets_data=None,
    energy_data=None,
    fred_data=None,
    nfci_history=None,
    infrastructure_data=None,
    adaptation_data=None,
    weekly_context=None,
):
    """Build a compact, deterministic Snapshot from measured platform domains."""
    regime = regime_metrics or {}
    macro_history = macro_history if isinstance(macro_history, pd.DataFrame) else pd.DataFrame()
    debt_markets_data = debt_markets_data or {}
    energy_data = energy_data or {}
    infrastructure_data = infrastructure_data or {}
    adaptation_data = adaptation_data or {}
    weekly_context = weekly_context or {}
    funding = (regime.get("Deployment Funding Mix", {}) or {}).get("current", {}) or {}
    funding_series = (regime.get("Deployment Funding Mix", {}) or {}).get("series", {}) or {}

    borrower = _number(regime.get("Borrower Strain"))
    lender = _number(regime.get("Lender Strain"))
    power_stress = _number(regime.get("Power Stress Index"))
    capacity_gap = _number(regime.get("Power Capacity Gap"))
    validation_gap = _number(regime.get("Economic Validation Gap"))
    speculation_gap = _number(regime.get("Speculation Gap"))
    aei = _number(regime.get("AI Equity Index"))
    adi = _number(regime.get("AI Development Intensity"))

    infrastructure_series = (infrastructure_data.get("series", {}) or {})
    construction_item = (infrastructure_series.get("Data Center Construction", {}) or {})
    construction_yoy = _number(construction_item.get("yoy_growth"))
    construction_date = construction_item.get("date")
    construction_history = _series_frame(construction_item.get("history"))

    current_use = _number(adaptation_data.get("current_use"))
    expected_use = _number(adaptation_data.get("expected_use"))
    expected_adoption_gap = _number(
        adaptation_data.get("expected_adoption_gap", adaptation_data.get("adoption" + "_pipeline"))
    )
    adaptation_annual_change = _number(adaptation_data.get("annual_change"))
    adaptation_date = adaptation_data.get("snapshot_date")
    adaptation_history = _history_frame(
        adaptation_data.get("national_history"), "Current AI Use"
    )

    metric_specs = {
        "borrower": ("Borrower Strain", "Borrower Strain Version", "Borrower Strain Version"),
        "lender": ("Lender Strain", "Lender Strain Version", "Lender Strain Version"),
        "power": ("Power Stress Index", "Power Stress Version", "Power Stress Version"),
        "capacity": ("Power Capacity Gap", "Power Capacity Gap Version", "Power Capacity Gap Version"),
        "validation": ("Economic Validation Gap", "EVG Version", "EVG Version"),
        "aei": ("AI Equity Index", "AEI Version", "AEI Version"),
        "adi": ("AI Development Intensity", "ADI Version", "ADI Version"),
    }
    histories = {
        key: _history_frame(
            macro_history,
            value_column,
            version_column=version_column,
            required_version=regime.get(required_key),
        )
        for key, (value_column, version_column, required_key) in metric_specs.items()
    }
    deltas = {
        "borrower": _prior_delta(histories["borrower"], borrower),
        "lender": _prior_delta(histories["lender"], lender),
        "power": _prior_delta(histories["power"], power_stress),
        "capacity": _prior_delta(histories["capacity"], capacity_gap),
        "validation": _prior_delta(histories["validation"], validation_gap),
        "aei": _prior_delta(histories["aei"], aei),
        "adi": _prior_delta(histories["adi"], adi),
    }

    constraints, expansion = [], []

    # Market and development establish whether observable activity is expanding.
    if pd.notna(adi):
        if adi >= 55:
            expansion.append(_factor(
                key="development", domain="development", kind="expansion",
                severity=3 if adi >= 75 else 2, direction="rising" if deltas["adi"] > 1.5 else "stable",
                statement="AI investment and infrastructure development remain elevated.",
                score=adi / 20,
            ))
        elif adi <= 35:
            constraints.append(_factor(
                key="development", domain="development", kind="constraint",
                severity=2, direction="rising", statement="AI investment and infrastructure development remain subdued.",
                score=(35-adi)/10,
            ))
    if pd.notna(aei):
        if aei >= 55:
            expansion.append(_factor(
                key="market", domain="market", kind="expansion",
                severity=3 if aei >= 70 else 2, direction="rising" if deltas["aei"] > 1 else "stable",
                statement="AI equity fundamentals and market performance remain healthy.",
                score=aei/20,
            ))
        elif aei <= 35:
            constraints.append(_factor(
                key="market", domain="market", kind="constraint", severity=2,
                direction="rising" if deltas["aei"] < -1 else "stable",
                statement="AI equity fundamentals and market performance remain weak.",
                score=(35-aei)/10,
            ))

    # Funding capacity and contractual burden.
    internal = _number(funding.get("internal_funding_coverage"))
    runway = _number(funding.get("cash_reserve_coverage_years"))
    debt_pulse = _number(funding.get("debt_financing_pulse"))
    commitments = _number(funding.get("forward_commitment_load"))
    funding_level, funding_strength = _funding_state(funding)

    if pd.notna(internal):
        if internal >= 1.0:
            expansion.append(_factor(
                key="internal-funding", domain="funding", kind="expansion",
                severity=3 if internal >= 1.5 else 2, direction="stable",
                statement=f"Operating cash flow covers {_fmt(internal, 2)} times current capital spending.",
                score=internal,
            ))
        else:
            constraints.append(_factor(
                key="internal-funding", domain="funding", kind="constraint",
                severity=3 if internal < .75 else 2, direction="rising",
                statement=f"Operating cash flow covers only {_fmt(internal, 2)} times current capital spending.",
                score=1-internal,
            ))
    if pd.notna(runway):
        if runway >= 1.0:
            expansion.append(_factor(
                key="cash-runway", domain="liquidity", kind="expansion",
                severity=3 if runway >= 2 else 2, direction="stable",
                statement=f"Cash reserves cover about {_fmt(runway, 2)} years of current capital spending.",
                score=runway,
            ))
        else:
            constraints.append(_factor(
                key="cash-runway", domain="liquidity", kind="constraint",
                severity=3 if runway < .5 else 2, direction="rising",
                statement=f"Cash reserves cover {_fmt(runway, 2)} years of current capital spending.",
                score=1-runway,
            ))
    if pd.notna(commitments) and commitments >= 1.5:
        constraints.append(_factor(
            key="commitments", domain="commitments", kind="constraint",
            severity=4 if commitments >= 3 else 3 if commitments >= 2 else 2,
            direction="stable", statement=f"Forward commitments are {_fmt(commitments, 2)} times the past year's capital spending.",
            score=commitments,
        ))
    if pd.notna(debt_pulse) and debt_pulse >= .5:
        constraints.append(_factor(
            key="debt-pulse", domain="funding", kind="constraint", severity=3 if debt_pulse >= 1 else 2,
            direction="rising", statement=f"New debt over the past year equals {_fmt(debt_pulse, 2)} times current capital spending.",
            score=debt_pulse,
        ))

    # Borrower and lender condition.
    for key, label, value, delta, series in (
        ("borrower-strain", "Borrower strain", borrower, deltas["borrower"], histories["borrower"]),
        ("lender-strain", "Lender strain", lender, deltas["lender"], histories["lender"]),
    ):
        if pd.isna(value):
            continue
        severity = _level(value, (10, 25, 50))
        direction = _direction(delta, threshold=1)
        streak = _consecutive_direction(series, value, tolerance=.75)
        if severity >= 1 or direction == "rising":
            movement = f"has increased for {streak} consecutive observations" if streak >= 2 else "is rising" if direction == "rising" else "remains above neutral"
            constraints.append(_factor(
                key=key, domain="credit", kind="constraint", severity=max(1, severity), direction=direction,
                statement=f"{label} {movement}.",
                score=abs(value) + (abs(delta) if pd.notna(delta) else 0),
            ))
        elif value <= -10:
            expansion.append(_factor(
                key=key, domain="credit", kind="expansion", severity=3 if value <= -25 else 2,
                direction=direction, statement=f"{label} remains below neutral.",
                score=abs(value),
            ))

    # Corporate bond market functioning.
    debt_items = []
    for name in ("Corporate Bond Market Distress", "Investment-Grade Bond Distress", "High-Yield Bond Distress"):
        item = ((debt_markets_data.get("series", {}) or {}).get(name, {}) or {})
        value = _number(item.get("value"))
        history = _series_frame(item.get("history"))
        delta = _prior_delta(history, value, lookback=min(4, max(1, len(history))))
        debt_items.append((name, value, delta))
    valid_debt = [item for item in debt_items if pd.notna(item[1])]
    if valid_debt:
        dominant_name, dominant_value, dominant_delta = max(valid_debt, key=lambda item: item[1])
        severity = _level(dominant_value, (.15, .30, .50))
        direction = _direction(dominant_delta, threshold=.03)
        short = dominant_name.replace(" Bond Distress", "")
        short = {
            "Investment-Grade": "Investment-grade",
            "High-Yield": "High-yield",
            "Corporate Bond Market Distress": "Corporate",
        }.get(short, short)
        if severity >= 1 or direction == "rising":
            constraints.append(_factor(
                key="debt-markets", domain="credit", kind="constraint", severity=max(1, severity), direction=direction,
                statement=f"{short} credit shows the most stress in corporate bond markets.",
                score=dominant_value*10,
            ))
        else:
            expansion.append(_factor(
                key="debt-markets", domain="credit", kind="expansion", severity=2, direction=direction,
                statement="Corporate bond markets remain broadly functional.",
                score=1-dominant_value,
            ))

    # Broad financial conditions.
    nfci = nfci_snapshot(fred_data or {}, nfci_history)
    nfci_value = _number(nfci.get("value"))
    nfci_change = _number(nfci.get("three_month_change"))
    if pd.notna(nfci_value):
        direction = _direction(nfci_change, threshold=.10)
        if nfci_value > .10 or direction == "rising":
            constraints.append(_factor(
                key="nfci", domain="financial-conditions", kind="constraint",
                severity=3 if nfci_value >= .50 else 2 if nfci_value > .10 else 1,
                direction=direction,
                statement="Broad financial conditions are tightening." if direction == "rising" else "Broad financial conditions are tighter than average.",
                score=max(nfci_value, 0) + max(nfci_change, 0) if pd.notna(nfci_change) else max(nfci_value, 0),
            ))
        elif nfci_value < -.10:
            expansion.append(_factor(
                key="nfci", domain="financial-conditions", kind="expansion", severity=3 if nfci_value <= -.50 else 2,
                direction=direction, statement="Broad financial conditions remain looser than average.",
                score=abs(nfci_value),
            ))

    # Energy costs and physical power response.
    oil_change = _number(_energy_item(energy_data, "WTI Crude Oil").get("change_pct"))
    gas_change = _number(_energy_item(energy_data, "Natural Gas Price").get("change_pct"))
    commercial_price_change = _number(_energy_item(energy_data, "Commercial Electricity Price").get("change_pct"))
    industrial_price_change = _number(_energy_item(energy_data, "Industrial Electricity Price").get("change_pct"))
    retail_changes = [v for v in (commercial_price_change, industrial_price_change) if pd.notna(v)]
    if retail_changes and max(retail_changes) >= 8:
        constraints.append(_factor(
            key="electricity-cost", domain="energy", kind="constraint", severity=2,
            direction="rising", statement="Average U.S. retail electricity prices are substantially higher than a year ago.",
            score=max(retail_changes)/8,
        ))
    if pd.notna(oil_change) and oil_change >= 15:
        constraints.append(_factor(
            key="oil", domain="energy", kind="constraint", severity=3 if oil_change >= 25 else 2,
            direction="rising", statement=f"WTI crude oil is up {_fmt(oil_change, 1, suffix='%')} over four weeks.",
            score=oil_change/10,
        ))
    if pd.notna(gas_change) and gas_change >= 20:
        constraints.append(_factor(
            key="gas", domain="energy", kind="constraint", severity=3 if gas_change >= 35 else 2,
            direction="rising", statement=f"Henry Hub natural gas is up {_fmt(gas_change, 1, suffix='%')} over four weeks.",
            score=gas_change/15,
        ))

    if pd.notna(capacity_gap):
        direction = _direction(deltas["capacity"], threshold=2)
        if capacity_gap >= 15:
            constraints.append(_factor(
                key="capacity-gap", domain="energy", kind="constraint",
                severity=3 if capacity_gap >= 40 else 2, direction=direction,
                statement="Measured power supply is not expanding as quickly as AI deployment.",
                score=max(capacity_gap,0)/10,
            ))
        elif capacity_gap <= -20:
            expansion.append(_factor(
                key="capacity-gap", domain="energy", kind="expansion", severity=3 if capacity_gap <= -40 else 2,
                direction=direction, statement="Measured power supply is expanding faster than AI deployment.",
                score=abs(capacity_gap),
            ))
    if pd.notna(power_stress):
        severity = _level(power_stress, (15,35,60))
        direction = _direction(deltas["power"], threshold=2)
        if severity >= 1 or direction == "rising":
            constraints.append(_factor(
                key="power-stress", domain="energy", kind="constraint", severity=max(1,severity), direction=direction,
                statement="National power conditions remain above the constraint reference." if direction != "rising" else "Power-system constraints are increasing.",
                score=max(power_stress,0)/10,
            ))
        elif power_stress <= -10:
            expansion.append(_factor(
                key="power-stress", domain="energy", kind="expansion", severity=2, direction=direction,
                statement="National power conditions remain below the constraint reference.",
                score=abs(power_stress),
            ))

    # Infrastructure is expansion evidence on its own, and a constraint only
    # when a separate power-response measure corroborates the interaction.
    if pd.notna(construction_yoy):
        if construction_yoy >= .10:
            expansion.append(_factor(
                key="data-center-construction", domain="infrastructure", kind="expansion",
                severity=3 if construction_yoy >= .40 else 2 if construction_yoy >= .20 else 1,
                direction="rising", statement=f"Data-center construction is up {_fmt(construction_yoy*100, 1, suffix='%')} year over year.",
                score=construction_yoy*5,
            ))
        elif construction_yoy <= -.10:
            constraints.append(_factor(
                key="data-center-construction", domain="infrastructure", kind="constraint",
                severity=2, direction="rising", statement=f"Data-center construction is down {_fmt(abs(construction_yoy)*100, 1, suffix='%')} year over year.",
                score=abs(construction_yoy)*5,
            ))
    if pd.notna(construction_yoy) and construction_yoy >= .20 and pd.notna(capacity_gap) and capacity_gap >= 20:
        constraints.append(_factor(
            key="buildout-power-interaction", domain="infrastructure", kind="constraint",
            severity=3 if construction_yoy >= .40 and capacity_gap >= 40 else 2,
            direction="rising",
            statement=(f"Rapid data-center construction is outpacing measured power-system growth."),
            score=construction_yoy*5 + max(capacity_gap,0)/20,
        ))

    # Business adaptation is descriptive diffusion evidence, not productivity.
    if pd.notna(adaptation_annual_change):
        if adaptation_annual_change >= 1:
            expansion.append(_factor(
                key="business-adaptation", domain="adaptation", kind="expansion",
                severity=2 if adaptation_annual_change >= 3 else 1, direction="rising",
                statement=f"Business AI use rose {_fmt(adaptation_annual_change, 1)} percentage points over the past year.",
                score=adaptation_annual_change,
            ))
        elif adaptation_annual_change <= -1:
            constraints.append(_factor(
                key="business-adaptation", domain="adaptation", kind="constraint",
                severity=2 if adaptation_annual_change <= -3 else 1, direction="rising",
                statement=f"Business AI use fell {_fmt(abs(adaptation_annual_change), 1)} percentage points over the past year.",
                score=abs(adaptation_annual_change),
            ))
    elif pd.notna(current_use):
        expansion.append(_factor(
            key="business-adaptation", domain="adaptation", kind="expansion", severity=1,
            direction="stable", statement=f"Businesses report current AI use at {_fmt(current_use, 1, suffix='%')}.",
            score=current_use/20,
        ))

    # Economic validation and relative market/development positioning.
    if pd.notna(validation_gap):
        direction = _direction(deltas["validation"], threshold=3)
        if validation_gap >= 15:
            constraints.append(_factor(
                key="validation-gap", domain="validation", kind="constraint", severity=3 if validation_gap >= 35 else 2,
                direction=direction, statement="AI deployment is growing faster than measured economic activity.",
                score=validation_gap/10,
            ))
        elif validation_gap <= -15:
            expansion.append(_factor(
                key="validation-gap", domain="validation", kind="expansion", severity=3 if validation_gap <= -35 else 2,
                direction=direction, statement="Measured economic activity is keeping pace with AI deployment.",
                score=abs(validation_gap)/10,
            ))
    if pd.notna(speculation_gap):
        if speculation_gap >= 20:
            constraints.append(_factor(
                key="speculation-gap", domain="market", kind="constraint", severity=3 if speculation_gap >= 40 else 2,
                direction="rising" if _prior_delta(_history_frame(macro_history, "Speculation Gap"), speculation_gap) > 2 else "stable",
                statement="AI equity pricing is growing faster than observable development.",
                score=speculation_gap/10,
            ))
        elif speculation_gap <= -20:
            expansion.append(_factor(
                key="speculation-gap", domain="market", kind="expansion", severity=2, direction="stable",
                statement="AI equity pricing is not outpacing observable development.",
                score=abs(speculation_gap)/10,
            ))

    # Weekly changes use the previous completed Friday as the baseline and only
    # include observations that arrived after it.
    changes = []
    for key, label, value, threshold in (
        ("aei", "AI equity conditions", aei, 1.0),
        ("adi", "AI development intensity", adi, 1.5),
        ("borrower", "Borrower strain", borrower, 1.0),
        ("lender", "Lender strain", lender, 1.0),
        ("power", "Power-system conditions", power_stress, 2.0),
        ("capacity", "Power Capacity Gap", capacity_gap, 2.0),
        ("validation", "Economic Validation Gap", validation_gap, 3.0),
    ):
        _metric_change(changes, key=key, label=label, current=value, delta=_weekly_delta(histories[key], value), threshold=threshold)

    commitment_series = _series_frame(funding_series.get("forward_commitment_load"))
    _metric_change(
        changes, key="commitments", label="Forward commitments", current=commitments,
        delta=_weekly_delta(commitment_series, commitments), threshold=.15, unit="x",
    )
    _metric_change(
        changes, key="business-adaptation", label="Reported business AI use", current=current_use,
        delta=_weekly_delta(adaptation_history, current_use), threshold=.5, unit="percentage points",
    )
    if not construction_history.empty:
        current_construction = _number(construction_history.iloc[-1]["Value"])
        _metric_change(
            changes, key="data-center-construction", label="Data-center construction", current=current_construction,
            delta=_weekly_delta(construction_history, current_construction), threshold=.5,
        )

    selected_constraints = _select_diverse(constraints, limit=3)
    selected_expansion = _select_diverse(expansion, limit=3)
    selected_changes = sorted(changes, key=lambda item: item["score"], reverse=True)[:3]

    domain_names = (
        "market", "development", "funding", "liquidity", "commitments", "credit",
        "financial-conditions", "energy", "infrastructure", "adaptation", "validation",
    )
    domain_states = {}
    for domain in domain_names:
        domain_constraints = [item for item in constraints if item["domain"] == domain]
        domain_expansion = [item for item in expansion if item["domain"] == domain]
        severity = max([item["severity"] for item in domain_constraints], default=0)
        strength = max([item["severity"] for item in domain_expansion], default=0)
        directions = Counter(item["direction"] for item in domain_constraints)
        direction = "rising" if directions["rising"] else "easing" if directions["easing"] else "stable"
        if severity >= 3:
            level = "material constraint"
        elif severity >= 2:
            level = "emerging constraint"
        elif severity >= 1:
            level = "limited constraint"
        elif strength >= 3:
            level = "strong expansion"
        elif strength >= 1:
            level = "expanding"
        else:
            level = "neutral"
        domain_states[domain] = {
            "level": level,
            "direction": direction,
            "constraint_severity": severity,
            "expansion_strength": strength,
            # Compatibility fields retained for existing archives and downstream readers.
            "pressure_severity": severity,
            "support_strength": strength,
        }

    constraint_domains = {item["domain"] for item in constraints if item["severity"] >= 2}
    expansion_domains = {item["domain"] for item in expansion if item["severity"] >= 2}
    rising_constraint_domains = {item["domain"] for item in constraints if item["direction"] == "rising"}
    max_constraint = max([item["severity"] for item in constraints], default=0)
    max_expansion = max([item["severity"] for item in expansion], default=0)

    core_values = [aei, adi, borrower, lender, power_stress, capacity_gap, internal, runway, commitments]
    supplemental_values = [construction_yoy, current_use]
    core_available = sum(pd.notna(value) for value in core_values)
    supplemental_available = sum(pd.notna(value) for value in supplemental_values)
    available = core_available + supplemental_available
    tracked = len(core_values) + len(supplemental_values)
    confidence = "high" if core_available >= 8 and supplemental_available == 2 else "moderate" if ((core_available >= 6 and supplemental_available >= 1) or core_available >= 8) else "low"

    if confidence == "low":
        headline = "Partial snapshot"
    elif funding_level == "weak" and ({"credit", "financial-conditions"} & constraint_domains):
        headline = "Financing constrained"
    elif max_constraint >= 3 and len(constraint_domains) >= 3 and len(expansion_domains) <= 1:
        headline = "Broad contraction"
    elif constraint_domains and not rising_constraint_domains and any(item["direction"] == "easing" for item in constraints):
        headline = "Stabilizing"
    elif len(constraint_domains) >= 3:
        headline = "Expansion with material constraints" if expansion_domains else "Constraints broadening"
    elif constraint_domains and expansion_domains:
        headline = "Expansion with emerging constraints" if max_constraint <= 2 else "Uneven expansion"
    elif constraint_domains:
        headline = "Constraints broadening"
    elif len(expansion_domains) >= 3:
        headline = "Broad expansion"
    elif expansion_domains:
        positive_changes = [item for item in selected_changes if "increased" in item["statement"]]
        headline = "Expansion reaccelerating" if len(positive_changes) >= 2 else "Expansion continuing"
    else:
        headline = "Uneven expansion"

    # Primary-source events lead the weekly rollup. Material platform changes
    # fill any unused slots. Events report a verified fact followed by a
    # restrained relevance statement; neither layer asserts causation.
    weekly_items = []
    weekly_references = []
    for event in list(weekly_context.get("events", []) or [])[:3]:
        display = str(event.get("display") or "").strip()
        reference_number = int(event.get("reference_number") or 0)
        if not display:
            continue
        statement = f"{display} [{reference_number}]" if reference_number else display
        weekly_items.append(statement)
        if reference_number:
            weekly_references.append(
                {
                    "reference_number": reference_number,
                    "event_id": str(event.get("event_id") or ""),
                    "source_name": str(event.get("source_name") or ""),
                    "source_label": str(event.get("source_label") or ""),
                    "source_url": str(event.get("source_url") or ""),
                    "event_date": str(event.get("event_date") or ""),
                }
            )
    for item in selected_changes:
        if len(weekly_items) >= 3:
            break
        weekly_items.append(item["statement"])
    if not weekly_items:
        weekly_items = ["No material development this week."]
    if headline not in MACRO_STATE_HEADLINES:
        raise RuntimeError(f"Unapproved Macro state headline: {headline}")

    expansion_statements = [item["statement"] for item in selected_expansion]
    constraint_statements = [item["statement"] for item in selected_constraints]
    return {
        "headline": headline,
        "summary": "",  # Deprecated: the three-column Snapshot is the summary.
        "expansion_factors": expansion_statements,
        "constraint_factors": constraint_statements,
        "changes": weekly_items,
        "metric_changes": [item["statement"] for item in selected_changes],
        "weekly_references": weekly_references,
        "weekly_context": {
            "as_of": weekly_context.get("as_of"),
            "window_start": weekly_context.get("window_start"),
            "source": weekly_context.get("source"),
            "version": weekly_context.get("version"),
        },
        # Compatibility aliases retained for archive schema continuity.
        "resilience_factors": expansion_statements,
        "pressure_factors": constraint_statements,
        "domains": domain_states,
        "snapshot_context": {
            "infrastructure": {
                "data_center_construction_yoy": construction_yoy,
                "observation_date": construction_date,
            },
            "adaptation": {
                "current_use": current_use,
                "expected_use": expected_use,
                "expected_adoption_gap": expected_adoption_gap,
                "annual_change": adaptation_annual_change,
                "observation_date": adaptation_date,
            },
            "coverage": {
                "available": available,
                "tracked": tracked,
                "core_available": core_available,
                "supplemental_available": supplemental_available,
            },
        },
        "confidence": confidence,
        "version": MACRO_INTERPRETATION_VERSION,
    }
