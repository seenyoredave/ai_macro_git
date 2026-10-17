"""Version 4 lender conditions, reconstructed with one formula throughout."""
from __future__ import annotations

import numpy as np
import pandas as pd

from loaders.credit_conditions_loader import WEEKLY_SERIES, series_history

VERSION = "4.0"
WEIGHTS = {"Credit conditions": 0.50, "Bank borrowing reliance": 0.25, "Bank cash buffer": 0.25}


def _rank_score(series, *, adverse_high=True):
    # Trailing five years, at least one year of weekly observations. Midrank
    # keeps an unchanged series neutral; each cutoff uses only earlier values.
    def score(values):
        value = values[-1]
        prior = values[:-1]
        rank = ((prior < value).sum() + 0.5 * (prior == value).sum()) / len(prior)
        return (200.0 * rank - 100.0) * (1 if adverse_high else -1)
    return series.rolling("1826D", min_periods=53).apply(score, raw=True)


def calculate_weekly_lender_conditions(data):
    inputs = {label: series_history(data, sid) for label, sid in WEEKLY_SERIES.items()}
    h8 = None
    for label in ("Borrowings", "Deposits", "Cash", "Assets", "Loans"):
        frame = inputs[label][["Date", "Value"]].rename(columns={"Value": label})
        # Loans supply descriptive momentum; their absence must not erase the
        # funding ratios, which require their own exact observation-date match.
        if label == "Loans":
            continue
        h8 = frame if h8 is None else h8.merge(frame, on="Date", how="inner")
    h8 = h8.sort_values("Date").reset_index(drop=True)
    h8["Bank borrowing reliance"] = 100 * (h8["Borrowings"] / 1000) / h8["Deposits"]
    h8["Bank cash buffer"] = 100 * h8["Cash"] / h8["Assets"]
    if not h8.empty:
        indexed = h8.set_index("Date")
        h8["Borrowing score"] = _rank_score(indexed["Bank borrowing reliance"]).to_numpy()
        h8["Cash score"] = _rank_score(indexed["Bank cash buffer"], adverse_high=False).to_numpy()
    else:
        h8["Borrowing score"] = np.nan
        h8["Cash score"] = np.nan
    h8["Funding observation"] = h8["Date"]
    credit = inputs["Credit conditions"][["Date", "Value"]].rename(columns={"Value": "Credit conditions"})
    credit["Credit observation"] = credit["Date"]
    dates = pd.DataFrame({"Date": pd.concat([h8["Date"], credit["Date"]]).drop_duplicates().sort_values()})
    frame = pd.merge_asof(dates, credit, on="Date", tolerance=pd.Timedelta(days=9))
    frame = pd.merge_asof(frame, h8, on="Date", tolerance=pd.Timedelta(days=9))
    frame["Credit score"] = 100 * np.tanh(frame["Credit conditions"])
    # Require every component; weights never shift because a source is missing.
    frame["Lender Strain"] = 0.50 * frame["Credit score"] + 0.25 * frame["Borrowing score"] + 0.25 * frame["Cash score"]
    frame["Lender Strain Version"] = VERSION
    valid = frame.dropna(subset=["Lender Strain"]).copy()
    latest = valid.iloc[-1] if not valid.empty else None
    components = {}
    for name, value_col, date_col, score_col, source_ids, units in (
        ("Credit conditions", "Credit conditions", "Credit observation", "Credit score", ("NFCICREDIT",), "index"),
        ("Bank borrowing reliance", "Bank borrowing reliance", "Funding observation", "Borrowing score", (WEEKLY_SERIES["Borrowings"], WEEKLY_SERIES["Deposits"]), "% of deposits"),
        ("Bank cash buffer", "Bank cash buffer", "Funding observation", "Cash score", (WEEKLY_SERIES["Cash"], WEEKLY_SERIES["Assets"]), "% of assets"),
    ):
        as_of = latest[date_col].date().isoformat() if latest is not None else None
        retrieved = [inputs[label].iloc[-1]["Retrieved At"] for label, sid in WEEKLY_SERIES.items() if sid in source_ids and not inputs[label].empty]
        components[name] = {"raw": float(latest[value_col]) if latest is not None else np.nan,
                            "score": float(latest[score_col]) if latest is not None else np.nan,
                            "weight": WEIGHTS[name], "active_weight": WEIGHTS[name],
                            "as_of": as_of, "retrieved_at": min(retrieved) if retrieved else None,
                            "units": units, "source": "Chicago Fed / FRED" if name == "Credit conditions" else "Federal Reserve H.8 / FRED",
                            "source_url": " | ".join(f"https://fred.stlouisfed.org/series/{sid}" for sid in source_ids),
                            "normalization": "100 × tanh(index)" if name == "Credit conditions" else "Trailing five-year midrank; minimum 53 weekly observations"}
    now = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    stale = latest is None or any(now - pd.Timestamp(item["as_of"]) > pd.Timedelta(days=21) for item in components.values())
    # No observations manufactured at today's date. Retain the actual last
    # measured score/date, and expose stale status independently.
    loans = inputs["Loans"]
    momentum = np.nan
    if len(loans) > 13:
        end = loans.iloc[-1]
        prior = loans[loans["Date"].le(end["Date"] - pd.Timedelta(weeks=13))]
        if not prior.empty:
            momentum = float(100 * (end["Value"] / prior.iloc[-1]["Value"] - 1))
    return {"score": float(latest["Lender Strain"]) if latest is not None else np.nan,
            "base_score": float((latest["Lender Strain"] + 100) / 2) if latest is not None else np.nan,
            "version": VERSION, "components": components, "history": valid,
            "as_of": latest["Date"].date().isoformat() if latest is not None else None,
            "stale": stale, "valid_components": 3 if latest is not None else 0,
            "coverage": 1.0 if latest is not None else 0.0,
            "bank_channel_score": float(latest["Lender Strain"]) if latest is not None else np.nan,
            "nonbank_channel_score": np.nan,
            "elevated_pillars": sum(pd.notna(item["score"]) and item["score"] > 0 for item in components.values()),
            "loan_momentum": {"13_week_change_pct": momentum, "as_of": loans.iloc[-1]["Date"].date().isoformat() if not loans.empty else None},
            "history_contract": {"version": VERSION, "display_years": 10, "formula": "50% credit conditions + 25% borrowing reliance + 25% cash buffer", "vintage": "Reconstructed from current-vintage source histories"}}
