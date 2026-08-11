"""Deterministic market-structure helpers for the Market sector dossier.

These helpers format measured structure; they do not generate Reader commentary.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _number(metrics: dict, key: str):
    value = pd.to_numeric((metrics or {}).get(key), errors="coerce")
    return float(value) if pd.notna(value) and np.isfinite(value) else np.nan


def build_structure_interpretation(metrics: dict) -> str:
    """Describe measured concentration/earnings structure without forecasting."""
    concentration = _number(metrics, "Sector Basket Concentration")
    effective_firms = _number(metrics, "Sector Effective Firms")
    loss_share = _number(metrics, "Loss-Making EV Share")
    coverage = _number(metrics, "Sector Concentration Coverage")
    if pd.notna(coverage) and coverage < 0.60:
        breadth = f"Market-cap data are available for {coverage * 100:.0f}% of included companies."
    elif pd.notna(concentration) and pd.notna(effective_firms):
        descriptor = (
            "narrow leadership"
            if concentration >= 40
            else "moderate leadership concentration"
            if concentration >= 15
            else "relatively broad leadership"
        )
        breadth = (
            f"The market-cap distribution behaves like {effective_firms:.1f} effective firms, "
            f"indicating {descriptor}."
        )
    else:
        breadth = "Leadership breadth is n/a."
    earnings = (
        f" Loss-making companies represent {loss_share * 100:.1f}% of valid enterprise value."
        if pd.notna(loss_share)
        else " Loss-making enterprise value is n/a."
    )
    return breadth + earnings


def build_structure_snapshot(metrics: dict, company_count: int) -> list[tuple[str, str]]:
    """Return compact measured values for the Market structure panel."""
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
