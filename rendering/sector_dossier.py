"""Deterministic narrative and structure logic for the Market sector dossier."""
from __future__ import annotations

import re
import numpy as np
import pandas as pd

from config.sector_config import SECTOR_CONFIG

FACTOR_LABELS = {
    "relative_performance": "relative return",
    "forward_ebit_yield_discount": "valuation support",
    "market_breadth": "market breadth",
}
COMPANY_NAMES = {
    "AAPL": "Apple", "ABBNY": "ABB", "AMD": "AMD", "ASML": "ASML",
    "AVGO": "Broadcom", "CRWD": "CrowdStrike", "CSCO": "Cisco",
    "DDOG": "Datadog", "DELL": "Dell", "GEV": "GE Vernova",
    "GOOG": "Alphabet", "GOOGL": "Alphabet", "INTU": "Intuit",
    "META": "Meta", "MSFT": "Microsoft", "MU": "Micron",
    "NTRA": "Natera", "NVDA": "Nvidia", "PANW": "Palo Alto Networks",
    "PLTR": "Palantir", "RTX": "RTX", "TSLA": "Tesla", "TSM": "TSMC",
    "UNH": "UnitedHealth", "UNP": "Union Pacific",
}


def _number(metrics: dict, key: str):
    value = pd.to_numeric((metrics or {}).get(key), errors="coerce")
    return float(value) if pd.notna(value) and np.isfinite(value) else np.nan


def _score_map(frame, name_column):
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return {}
    if name_column not in frame.columns or "Score" not in frame.columns:
        return {}
    out = {}
    for _, row in frame.iterrows():
        value = pd.to_numeric(row.get("Score"), errors="coerce")
        if pd.notna(value) and np.isfinite(value):
            out[str(row.get(name_column))] = float(value)
    return out


def _rank(peer_metrics: dict, sector: str, key: str, *, descending=True):
    rows = []
    for name, metrics in (peer_metrics or {}).items():
        value = _number(metrics, key)
        if pd.notna(value):
            rows.append((str(name), value))
    rows.sort(key=lambda item: item[1], reverse=descending)
    for index, (name, _) in enumerate(rows, start=1):
        if name == str(sector):
            return index, len(rows)
    return None, len(rows)


def _rank_phrase(rank, total, subject):
    if not rank or not total:
        return f"{subject.capitalize()} peer rank is unresolved"
    return f"{subject.capitalize()} ranks {rank} of {total}"


def _archetype(metrics: dict) -> str:
    equity = _number(metrics, "Sector Score")
    pressure = _number(metrics, "Sector Pressure")
    trailing = _number(metrics, "Avg Return")
    factors = _score_map(metrics.get("Scored Factors"), "Factor")
    breadth = factors.get("market_breadth", np.nan)
    dispersion = np.ptp(list(factors.values())) if len(factors) >= 2 else np.nan
    if pd.isna(equity) or pd.isna(pressure):
        return "Signal unresolved"
    if equity >= 65:
        if pressure >= 70:
            return "High-pressure leadership"
        if pd.notna(breadth) and breadth >= 65 and (pd.isna(dispersion) or dispersion <= 28):
            return "Broad-based leadership"
        return "Constructive leadership"
    if equity >= 48:
        if pressure >= 70 and trailing >= 0.10:
            return "Speculative momentum"
        if pressure < 50 and trailing >= 0.10:
            return "Constructive advance"
        if trailing < -0.10:
            return "Fading leadership"
        return "Uneven strength"
    if equity >= 32:
        if trailing >= 0.20 and pressure >= 60:
            return "Fragile rebound"
        if trailing >= 0.10 and pressure < 55:
            return "Early recovery"
        if pressure >= 65:
            return "Pressure without support"
        if trailing < -0.10:
            return "Underpowered and weakening"
        return "Mixed footing"
    if pressure >= 60:
        return "Crowded without confirmation"
    if trailing >= 0.10:
        return "Narrow rebound"
    if trailing < -0.10:
        return "Low-pressure weakness"
    return "Underpowered"


def _driver_sentence(metrics: dict, sector: str, sector_label: str, peer_metrics: dict) -> str:
    equity_rank, total = _rank(peer_metrics, sector, "Sector Score", descending=True)
    factors = _score_map(metrics.get("Scored Factors"), "Factor")
    prefix = _rank_phrase(equity_rank, total, "equity strength")
    if len(factors) < 2:
        return f"{sector_label}: {prefix.lower()}."
    ordered = sorted(factors.items(), key=lambda item: item[1], reverse=True)
    high_name, high = ordered[0]
    low_name, low = ordered[-1]
    high_label = FACTOR_LABELS.get(high_name, high_name.replace("_", " "))
    low_label = FACTOR_LABELS.get(low_name, low_name.replace("_", " "))
    if high - low < 12:
        return f"{sector_label} {prefix.lower()}, with a balanced signal across relative return and breadth."
    return f"{sector_label} {prefix.lower()}, with {high_label} doing most of the work while {low_label} trails."


def _pressure_structure_sentence(metrics: dict, sector: str, peer_metrics: dict, movement=None) -> str:
    pressure_rank, total = _rank(peer_metrics, sector, "Sector Pressure", descending=True)
    components = _score_map(metrics.get("Pressure Components"), "Component")
    pressure_text = _rank_phrase(pressure_rank, total, "trading pressure")
    delta = pd.to_numeric((movement or {}).get("Delta Pressure"), errors="coerce")
    if pd.notna(delta) and abs(float(delta)) > 1.0:
        pressure_text += " and has been expanding" if delta > 0 else " and has been easing"
    if components:
        ordered = sorted(components.items(), key=lambda item: item[1], reverse=True)
        top_name, top_value = ordered[0]
        median = float(np.median(list(components.values())))
        if top_value - median >= 9:
            pressure_text += f", with {top_name.lower()} the clearest driver"
    pressure_text += "."
    loss_share = _number(metrics, "Loss-Making EV Share")
    concentration = _number(metrics, "Sector Basket Concentration")
    multiple = _number(metrics, "Forward EV/EBIT")
    coverage = _number(metrics, "Sector Concentration Coverage")
    if pd.notna(coverage) and coverage < 0.60:
        structure = f"Market-cap data are available for {coverage * 100:.0f}% of included companies."
    elif pd.notna(loss_share) and loss_share >= 0.35:
        structure = f"Loss-making companies represent {loss_share * 100:.0f}% of valid enterprise value, leaving earnings support fragile."
    elif pd.notna(concentration) and concentration >= 40:
        structure = "Leadership is narrow enough that a small group of constituents can dominate the result."
    elif pd.notna(multiple) and multiple >= 40:
        structure = "The profitable operating base carries a demanding valuation."
    elif pd.notna(concentration) and concentration < 15:
        structure = "Leadership is comparatively broad."
    else:
        structure = "Leadership concentration is moderate."
    return pressure_text + " " + structure


def _company_label(row) -> str:
    ticker = str(row.get("Ticker") or "").upper().strip()
    if ticker in COMPANY_NAMES:
        return COMPANY_NAMES[ticker]
    company = " ".join(str(row.get("Company") or "").split()).strip()
    if company and company.upper() != ticker and len(company) > 2:
        company = re.sub(r",?\s+(Inc\.?|Corp\.?|Corporation|Ltd\.?|PLC)$", "", company, flags=re.I)
        return company
    return ticker


def company_contribution_shoutout(companies: pd.DataFrame):
    """Return a brief material company aside, or None when no name earns it."""
    required = {"Ticker", "Market Cap", "1Y Return"}
    if companies is None or companies.empty or not required.issubset(companies.columns):
        return None
    frame = companies.copy()
    frame["Market Cap"] = pd.to_numeric(frame["Market Cap"], errors="coerce")
    frame["1Y Return"] = pd.to_numeric(frame["1Y Return"], errors="coerce")
    frame = frame.loc[
        frame["Market Cap"].gt(0)
        & frame["1Y Return"].notna()
        & frame["1Y Return"].gt(-0.95)
    ].copy()
    if len(frame) < 5:
        return None
    frame["Start Cap"] = frame["Market Cap"] / (1.0 + frame["1Y Return"])
    frame = frame.loc[frame["Start Cap"].gt(0)].copy()
    if frame.empty:
        return None
    frame["Start Weight"] = frame["Start Cap"] / frame["Start Cap"].sum()
    frame["Contribution"] = frame["Start Weight"] * frame["1Y Return"]
    pool = float(frame["Contribution"].abs().sum())
    if not np.isfinite(pool) or pool <= 0:
        return None
    frame["Abs Share"] = frame["Contribution"].abs() / pool
    positive = frame.loc[frame["Contribution"].gt(0)].sort_values("Contribution", ascending=False)
    negative = frame.loc[frame["Contribution"].lt(0)].sort_values("Contribution")
    total = float(frame["Contribution"].sum())

    # Two-sided offset: both names explain why the sector-level result is muted or contested.
    if not positive.empty and not negative.empty:
        up, down = positive.iloc[0], negative.iloc[0]
        if (
            up["Contribution"] >= 0.05 and abs(down["Contribution"]) >= 0.05
            and up["Abs Share"] >= 0.28 and down["Abs Share"] >= 0.28
            and up["Abs Share"] + down["Abs Share"] >= 0.60
        ):
            return {
                "text": f"On a market-cap-weighted basis, {_company_label(up)} is the clearest positive contributor, while {_company_label(down)} has been a meaningful offset.",
                "tickers": [str(up["Ticker"]), str(down["Ticker"])],
                "role": "offset",
            }

    direction = positive if total >= 0 else negative
    if direction.empty:
        return None
    first = direction.iloc[0]
    second = direction.iloc[1] if len(direction) > 1 else None
    first_abs = abs(float(first["Contribution"]))
    first_share = float(first["Abs Share"])
    second_abs = abs(float(second["Contribution"])) if second is not None else 0.0
    second_share = float(second["Abs Share"]) if second is not None else 0.0
    ratio = first_abs / max(second_abs, 1e-9)

    # Closely paired leaders can earn a joint mention; otherwise the lead name must stand out.
    if (
        second is not None and first_abs >= 0.04 and second_abs >= 0.04
        and first_share >= 0.24 and second_share >= 0.24
        and first_share + second_share >= 0.60 and ratio <= 1.65
    ):
        verb = "have done much of the market-cap-weighted heavy lifting" if total >= 0 else "have accounted for much of the market-cap-weighted drag"
        return {
            "text": f"{_company_label(first)} and {_company_label(second)} {verb}.",
            "tickers": [str(first["Ticker"]), str(second["Ticker"])],
            "role": "pair",
        }
    if first_abs >= 0.05 and first_share >= 0.45 and (ratio >= 1.50 or first_share >= 0.55):
        text = (
            f"{_company_label(first)} has done most of the market-cap-weighted heavy lifting."
            if total >= 0 else
            f"{_company_label(first)} has been the clearest market-cap-weighted drag."
        )
        return {"text": text, "tickers": [str(first["Ticker"])], "role": "single"}
    return None


def _watchpoint(metrics: dict) -> str:
    factors = _score_map(metrics.get("Scored Factors"), "Factor")
    components = _score_map(metrics.get("Pressure Components"), "Component")
    loss_share = _number(metrics, "Loss-Making EV Share")
    concentration = _number(metrics, "Sector Basket Concentration")
    equity = _number(metrics, "Sector Score")
    pressure = _number(metrics, "Sector Pressure")
    if pd.notna(loss_share) and loss_share >= 0.35:
        return "Durability now depends on profitable participation broadening."
    if pd.notna(concentration) and concentration >= 40:
        return "The read is most sensitive to a reversal among the largest constituents."
    if factors and min(factors, key=factors.get) == "market_breadth" and equity >= 50:
        return "Breadth now needs to catch up with the headline return signal."
    if components and max(components, key=components.get) == "Volatility Expansion" and pressure >= 55:
        return "The setup improves if volatility pressure eases without a loss of breadth."
    if equity < 45:
        return "A sustained improvement in relative return and breadth would be the clearest confirmation."
    return "The signal remains constructive while breadth holds and pressure stays contained."


def select_sector_weekly_event(weekly_context: dict, sector: str, tickers=None):
    del tickers  # News belongs to the selected sector, not to a narrative shout-out.
    basket = {
        str(value).upper()
        for value in (SECTOR_CONFIG.get(str(sector), {}) or {}).get("basket", [])
    }
    candidates = []
    for event in list((weekly_context or {}).get("events", []) or []):
        verification = str(
            event.get("verification_status") or event.get("status") or ""
        ).strip().lower()
        if verification == "no_match":
            continue
        sectors = {str(value) for value in event.get("sectors", [])}
        if str(sector) not in sectors:
            continue
        event_tickers = {
            str(value).upper()
            for value in event.get("tickers", [])
            if str(value).strip()
        }
        if event_tickers and not event_tickers.intersection(basket):
            continue
        candidates.append(event)
    if not candidates:
        return None
    candidates.sort(
        key=lambda event: (
            float(event.get("priority", 0) or 0),
            str(event.get("event_date", "")),
        ),
        reverse=True,
    )
    return candidates[0]


def build_sector_narrative(metrics: dict, sector: str, sector_label: str, companies: pd.DataFrame, peer_metrics: dict, weekly_context=None, movement=None):
    shoutout = company_contribution_shoutout(companies)
    driver = _driver_sentence(metrics, sector, sector_label, peer_metrics)
    pressure = _pressure_structure_sentence(metrics, sector, peer_metrics, movement)
    watch = _watchpoint(metrics)
    body_parts = [driver, pressure]
    if shoutout:
        company_text = shoutout["text"].rstrip(".")
        watch_text = watch[0].lower() + watch[1:] if watch else ""
        body_parts.append(f"{company_text}; {watch_text}")
    else:
        body_parts.append(watch)
    event = select_sector_weekly_event(weekly_context or {}, sector, (shoutout or {}).get("tickers", []))
    reference = None
    weekly_note = None
    if event:
        weekly_note = str(event.get('display') or '').strip() or f"{event.get('verified_fact', '').strip()} {event.get('platform_relevance', '').strip()}".strip()
        reference = {
            "reference_number": 1,
            "source_name": event.get("source_name", ""),
            "source_label": event.get("source_label", ""),
            "source_url": event.get("source_url", ""),
            "event_date": event.get("event_date", ""),
        }
    core_values = [_number(metrics, "Sector Score"), _number(metrics, "Sector Pressure"), _number(metrics, "Avg Return")]
    confidence = "high" if all(pd.notna(v) for v in core_values) and len(_score_map(metrics.get("Scored Factors"), "Factor")) >= 2 else "moderate"
    return {
        "headline": _archetype(metrics),
        "body": " ".join(body_parts),
        "company_shoutout": shoutout,
        "weekly_note": weekly_note,
        "reference": reference,
        "confidence": confidence,
    }


def build_sector_diagnosis(metrics: dict, sector_label: str) -> tuple[str, str]:
    """Compatibility wrapper for callers that do not provide peer/company context."""
    narrative = build_sector_narrative(metrics, sector_label, sector_label, pd.DataFrame(), {sector_label: metrics})
    return narrative["headline"], narrative["body"]


def build_structure_interpretation(metrics: dict) -> str:
    concentration = _number(metrics, "Sector Basket Concentration")
    effective_firms = _number(metrics, "Sector Effective Firms")
    loss_share = _number(metrics, "Loss-Making EV Share")
    coverage = _number(metrics, "Sector Concentration Coverage")
    if pd.notna(coverage) and coverage < 0.60:
        breadth = f"Market-cap data are available for {coverage * 100:.0f}% of included companies."
    elif pd.notna(concentration) and pd.notna(effective_firms):
        descriptor = "narrow leadership" if concentration >= 40 else "moderate leadership concentration" if concentration >= 15 else "relatively broad leadership"
        breadth = f"The market-cap distribution behaves like {effective_firms:.1f} effective firms, indicating {descriptor}."
    else:
        breadth = "Leadership breadth is n/a."
    earnings = f" Loss-making companies represent {loss_share * 100:.1f}% of valid enterprise value." if pd.notna(loss_share) else " Loss-making enterprise value is n/a."
    return breadth + earnings


def build_structure_snapshot(metrics: dict, company_count: int) -> list[tuple[str, str]]:
    concentration = _number(metrics, "Sector Basket Concentration")
    effective_firms = _number(metrics, "Sector Effective Firms")
    loss_share = _number(metrics, "Loss-Making EV Share")
    profitable_value = _number(metrics, "Forward EV/EBIT Company Count")
    profitable_count = int(profitable_value) if pd.notna(profitable_value) else None
    coverage = _number(metrics, "Sector Concentration Coverage")
    def number(value, digits=1, suffix=""):
        return "n/a" if pd.isna(value) else f"{value:.{digits}f}{suffix}"
    return [
        ("Constituents", str(int(company_count))),
        ("Effective firms", number(effective_firms, 1)),
        ("Adjusted HHI", number(concentration, 1)),
        ("Loss-making EV", number(loss_share * 100.0 if pd.notna(loss_share) else np.nan, 1, "%")),
        ("Profitable cohort", str(profitable_count) if profitable_count is not None else "n/a"),
        ("Market-cap data", number(coverage * 100.0 if pd.notna(coverage) else np.nan, 0, "%")),
    ]
