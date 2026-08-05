from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.hhi_engine import normalize_hhi
from archive.archive_reader import load_yf_history


MARKET_LEDGER_VERSION = "1.2"
HISTORY_MIN_COVERAGE = 0.90
RETURN_MIN_COVERAGE = 0.90


def _numeric(values) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)


def build_market_universe(sector_data: dict[str, pd.DataFrame] | None) -> pd.DataFrame:
    frames = []
    for sector, frame in (sector_data or {}).items():
        if frame is None or frame.empty or "Ticker" not in frame.columns:
            continue
        current = frame.copy()
        current["Sector"] = str(sector)
        frames.append(current)

    if not frames:
        return pd.DataFrame()

    universe = pd.concat(frames, ignore_index=True, sort=False)
    universe["Ticker"] = universe["Ticker"].astype(str).str.upper().str.strip()
    universe = universe.loc[universe["Ticker"].ne("") & universe["Ticker"].ne("NAN")].copy()

    completeness_columns = [
        column
        for column in ("Market Cap", "1Y Return", "Revenue", "Forward EBIT", "Price")
        if column in universe.columns
    ]
    if completeness_columns:
        universe["_completeness"] = universe[completeness_columns].notna().sum(axis=1)
        universe = universe.sort_values(
            ["Ticker", "_completeness"], ascending=[True, False], kind="stable"
        )
    universe = universe.drop_duplicates("Ticker", keep="first")
    universe = universe.drop(columns=["_completeness"], errors="ignore")

    for column in ("Market Cap", "1Y Return", "YTD Return", "YTD Start Market Cap", "YTD Year", "Price"):
        if column in universe.columns:
            universe[column] = _numeric(universe[column])
    return universe.reset_index(drop=True)


def _concentration_snapshot(universe: pd.DataFrame) -> dict:
    company_count = int(universe["Ticker"].nunique()) if not universe.empty else 0
    if universe.empty or "Market Cap" not in universe.columns:
        return {
            "company_count": company_count,
            "valid_cap_count": 0,
            "cap_coverage": 0.0,
            "total_market_cap": np.nan,
            "raw_hhi": np.nan,
            "normalized_hhi": np.nan,
            "effective_firms": np.nan,
            "top_6_share": np.nan,
            "top_10_share": np.nan,
        }

    caps = universe[["Ticker", "Market Cap"]].copy()
    caps["Market Cap"] = _numeric(caps["Market Cap"])
    caps = caps.loc[caps["Market Cap"].gt(0)].sort_values("Market Cap", ascending=False)
    valid_count = int(len(caps))
    total = float(caps["Market Cap"].sum()) if valid_count else np.nan
    if not valid_count or not np.isfinite(total) or total <= 0:
        raw_hhi = np.nan
        shares = pd.Series(dtype=float)
    else:
        shares = caps["Market Cap"] / total
        raw_hhi = float(np.square(shares).sum())

    return {
        "company_count": company_count,
        "valid_cap_count": valid_count,
        "cap_coverage": float(valid_count / company_count) if company_count else 0.0,
        "total_market_cap": total,
        "raw_hhi": raw_hhi,
        "normalized_hhi": normalize_hhi(raw_hhi),
        "effective_firms": float(1.0 / raw_hhi) if pd.notna(raw_hhi) and raw_hhi > 0 else np.nan,
        "top_6_share": float(shares.iloc[:6].sum()) if len(shares) >= 6 else np.nan,
        "top_10_share": float(shares.iloc[:10].sum()) if len(shares) >= 10 else np.nan,
    }


def _company_ownership(universe: pd.DataFrame) -> pd.DataFrame:
    columns = ["Ticker", "Company", "Sector", "Market Cap", "Market Cap Share", "Rank"]
    if universe.empty or "Market Cap" not in universe.columns:
        return pd.DataFrame(columns=columns)
    frame = universe.copy()
    if "Company" not in frame.columns:
        frame["Company"] = frame["Ticker"]
    frame["Company"] = frame["Company"].fillna(frame["Ticker"]).astype(str)
    frame["Market Cap"] = _numeric(frame["Market Cap"])
    frame = frame.loc[frame["Market Cap"].gt(0)].copy()
    total = float(frame["Market Cap"].sum())
    frame["Market Cap Share"] = frame["Market Cap"] / total if total > 0 else np.nan
    frame = frame.sort_values("Market Cap", ascending=False, kind="stable").reset_index(drop=True)
    frame["Rank"] = np.arange(1, len(frame) + 1)
    frame["Cumulative Market Cap Share"] = frame["Market Cap Share"].cumsum()
    return frame


def _sector_ownership(companies: pd.DataFrame) -> pd.DataFrame:
    if companies.empty:
        return pd.DataFrame(columns=["Sector", "Market Cap", "Market Cap Share", "Company Count"])
    total = float(companies["Market Cap"].sum())
    out = (
        companies.groupby("Sector", as_index=False)
        .agg(Market_Cap=("Market Cap", "sum"), Company_Count=("Ticker", "nunique"))
        .rename(columns={"Market_Cap": "Market Cap", "Company_Count": "Company Count"})
    )
    out["Market Cap Share"] = out["Market Cap"] / total if total > 0 else np.nan
    return out.sort_values("Market Cap", ascending=False, kind="stable").reset_index(drop=True)


def _breadth_snapshot(universe: pd.DataFrame) -> dict:
    if universe.empty or "1Y Return" not in universe.columns:
        return {
            "return_count": 0,
            "return_coverage": 0.0,
            "positive_breadth": np.nan,
            "median_return": np.nan,
            "equal_weight_return": np.nan,
        }
    returns = _numeric(universe["1Y Return"]).dropna()
    count = int(len(returns))
    company_count = int(universe["Ticker"].nunique())
    return {
        "return_count": count,
        "return_coverage": float(count / company_count) if company_count else 0.0,
        "positive_breadth": float(returns.gt(0).mean()) if count else np.nan,
        "median_return": float(returns.median()) if count else np.nan,
        "equal_weight_return": float(returns.mean()) if count else np.nan,
    }


def _archive_frame(tickers: set[str]) -> pd.DataFrame:
    history = load_yf_history()
    required = {"Date", "Ticker", "Market Cap", "Price"}
    if history is None or history.empty or not required.issubset(history.columns):
        return pd.DataFrame()
    frame = history.copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce", format="mixed")
    frame["Ticker"] = frame["Ticker"].astype(str).str.upper().str.strip()
    frame = frame.loc[frame["Ticker"].isin(tickers) & frame["Date"].notna()].copy()
    for column in ("Market Cap", "Price"):
        frame[column] = _numeric(frame[column])
    frame = frame.sort_values(["Date", "Ticker"], kind="stable")
    return frame.drop_duplicates(["Date", "Ticker"], keep="last")


def _fixed_history_cohort(history: pd.DataFrame, universe_size: int) -> tuple[pd.Timestamp | None, list[str]]:
    if history.empty or universe_size <= 0:
        return None, []
    counts = (
        history.loc[history["Market Cap"].gt(0) & history["Price"].gt(0)]
        .groupby("Date")["Ticker"]
        .nunique()
        .sort_index()
    )
    eligible = counts.loc[counts.ge(int(np.ceil(universe_size * HISTORY_MIN_COVERAGE)))]
    if eligible.empty:
        return None, []
    start_date = pd.Timestamp(eligible.index[0])
    start = history.loc[
        history["Date"].eq(start_date)
        & history["Market Cap"].gt(0)
        & history["Price"].gt(0)
    ]
    return start_date, sorted(start["Ticker"].unique().tolist())


def _historical_ledger(
    history: pd.DataFrame,
    companies: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    history_columns = [
        "Date", "Top 6 Share", "Top 10 Share", "Raw HHI", "Normalized HHI",
        "Effective Firms", "Cap-Weighted Return", "Equal-Weighted Return",
        "Median Return", "Positive Breadth", "Company Count",
    ]
    contribution_columns = [
        "Ticker", "Company", "Sector", "Start Weight", "Price Return", "Contribution",
    ]
    empty_meta = {
        "start_date": None,
        "end_date": None,
        "cohort_count": 0,
        "universe_count": int(len(companies)),
    }
    if history.empty or companies.empty:
        return pd.DataFrame(columns=history_columns), pd.DataFrame(columns=contribution_columns), empty_meta

    start_date, cohort = _fixed_history_cohort(history, int(len(companies)))
    if start_date is None or not cohort:
        return pd.DataFrame(columns=history_columns), pd.DataFrame(columns=contribution_columns), empty_meta

    cohort_history = history.loc[history["Ticker"].isin(cohort) & history["Date"].ge(start_date)].copy()
    cap_pivot = cohort_history.pivot(index="Date", columns="Ticker", values="Market Cap").sort_index().ffill()
    price_pivot = cohort_history.pivot(index="Date", columns="Ticker", values="Price").sort_index().ffill()
    common_dates = cap_pivot.index.intersection(price_pivot.index)
    cap_pivot = cap_pivot.reindex(common_dates)
    price_pivot = price_pivot.reindex(common_dates)
    if cap_pivot.empty or price_pivot.empty:
        return pd.DataFrame(columns=history_columns), pd.DataFrame(columns=contribution_columns), empty_meta

    start_caps = cap_pivot.iloc[0].where(lambda values: values.gt(0))
    start_prices = price_pivot.iloc[0].where(lambda values: values.gt(0))
    valid_start = start_caps.notna() & start_prices.notna()
    start_caps = start_caps.loc[valid_start]
    start_prices = start_prices.loc[valid_start]
    if len(start_caps) < 2 or float(start_caps.sum()) <= 0:
        return pd.DataFrame(columns=history_columns), pd.DataFrame(columns=contribution_columns), empty_meta
    weights = start_caps / float(start_caps.sum())

    rows = []
    for date_value in common_dates:
        caps = cap_pivot.loc[date_value, start_caps.index]
        prices = price_pivot.loc[date_value, start_prices.index]
        cap_valid = caps.gt(0) & caps.notna()
        price_returns = prices / start_prices - 1.0
        return_valid = price_returns.notna() & np.isfinite(price_returns)

        if cap_valid.sum() >= 2:
            cap_shares = caps.loc[cap_valid] / float(caps.loc[cap_valid].sum())
            raw_hhi = float(np.square(cap_shares).sum())
            sorted_shares = cap_shares.sort_values(ascending=False)
        else:
            raw_hhi = np.nan
            sorted_shares = pd.Series(dtype=float)

        active_weights = weights.loc[return_valid]
        active_weights = active_weights / float(active_weights.sum()) if float(active_weights.sum()) > 0 else active_weights
        active_returns = price_returns.loc[return_valid]
        rows.append({
            "Date": date_value,
            "Top 6 Share": float(sorted_shares.iloc[:6].sum()) if len(sorted_shares) >= 6 else np.nan,
            "Top 10 Share": float(sorted_shares.iloc[:10].sum()) if len(sorted_shares) >= 10 else np.nan,
            "Raw HHI": raw_hhi,
            "Normalized HHI": normalize_hhi(raw_hhi),
            "Effective Firms": float(1.0 / raw_hhi) if pd.notna(raw_hhi) and raw_hhi > 0 else np.nan,
            "Cap-Weighted Return": float((active_weights * active_returns).sum()) if len(active_returns) else np.nan,
            "Equal-Weighted Return": float(active_returns.mean()) if len(active_returns) else np.nan,
            "Median Return": float(active_returns.median()) if len(active_returns) else np.nan,
            "Positive Breadth": float(active_returns.gt(0).mean()) if len(active_returns) else np.nan,
            "Company Count": int(cap_valid.sum()),
        })

    ledger_history = pd.DataFrame(rows, columns=history_columns)
    end_date = pd.Timestamp(common_dates[-1])
    end_prices = price_pivot.iloc[-1].reindex(start_prices.index)
    price_returns = end_prices / start_prices - 1.0
    valid = price_returns.notna() & np.isfinite(price_returns)
    end_weights = weights.loc[valid]
    end_weights = end_weights / float(end_weights.sum()) if float(end_weights.sum()) > 0 else end_weights
    contributions = pd.DataFrame({
        "Ticker": price_returns.loc[valid].index,
        "Start Weight": end_weights,
        "Price Return": price_returns.loc[valid],
        "Contribution": end_weights * price_returns.loc[valid],
    }).reset_index(drop=True)
    identity = companies[["Ticker", "Company", "Sector"]].drop_duplicates("Ticker")
    contributions = contributions.merge(identity, on="Ticker", how="left")
    contributions["Company"] = contributions["Company"].fillna(contributions["Ticker"])
    contributions = contributions[contribution_columns].sort_values(
        "Contribution", ascending=False, kind="stable"
    )

    metadata = {
        "start_date": start_date.date().isoformat(),
        "end_date": end_date.date().isoformat(),
        "cohort_count": int(len(start_caps)),
        "universe_count": int(len(companies)),
    }
    return ledger_history, contributions.reset_index(drop=True), metadata



def _one_year_contributions(universe: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Build trailing one-year return contributions using implied start weights.

    The implied opening market cap mirrors the existing YTD methodology: current
    market cap divided by one plus the price return. This keeps the portfolio
    contribution identity internally coherent without another shares-outstanding
    request.
    """
    columns = [
        "Ticker", "Company", "Sector", "Start Weight", "Price Return", "Contribution",
    ]
    universe_dates = (
        pd.to_datetime(universe.get("Date"), errors="coerce", format="mixed").dropna()
        if "Date" in universe.columns
        else pd.Series(dtype="datetime64[ns]")
    )
    as_of_date = universe_dates.max().date().isoformat() if not universe_dates.empty else None
    metadata = {
        "period": "1Y",
        "as_of_date": as_of_date,
        "company_count": 0,
        "universe_count": int(len(universe)),
        "coverage": 0.0,
    }
    required = {"Ticker", "Market Cap", "1Y Return"}
    if universe.empty or not required.issubset(universe.columns):
        return pd.DataFrame(columns=columns), metadata

    frame = universe.copy()
    if "Company" not in frame.columns:
        frame["Company"] = frame["Ticker"]
    if "Sector" not in frame.columns:
        frame["Sector"] = ""
    for column in ("Market Cap", "1Y Return"):
        frame[column] = _numeric(frame[column])

    frame = frame.loc[
        frame["Market Cap"].gt(0)
        & frame["1Y Return"].notna()
        & np.isfinite(frame["1Y Return"])
        & frame["1Y Return"].gt(-1.0)
    ].copy()
    coverage = float(len(frame) / len(universe)) if len(universe) else 0.0
    metadata["company_count"] = int(len(frame))
    metadata["coverage"] = coverage
    if frame.empty or coverage < RETURN_MIN_COVERAGE:
        return pd.DataFrame(columns=columns), metadata

    frame["Start Market Cap"] = frame["Market Cap"] / (1.0 + frame["1Y Return"])
    frame = frame.loc[frame["Start Market Cap"].gt(0)].copy()
    start_total = float(frame["Start Market Cap"].sum())
    if not np.isfinite(start_total) or start_total <= 0:
        return pd.DataFrame(columns=columns), metadata

    frame["Start Weight"] = frame["Start Market Cap"] / start_total
    frame["Price Return"] = frame["1Y Return"]
    frame["Contribution"] = frame["Start Weight"] * frame["Price Return"]
    frame["Company"] = frame["Company"].fillna(frame["Ticker"]).astype(str)
    frame = frame[columns].sort_values("Contribution", ascending=False, kind="stable")

    metadata = {
        "period": "1Y",
        "as_of_date": as_of_date,
        "company_count": int(len(frame)),
        "universe_count": int(len(universe)),
        "coverage": float(len(frame) / len(universe)) if len(universe) else 0.0,
    }
    return frame.reset_index(drop=True), metadata

def build_market_ledger(sector_data: dict[str, pd.DataFrame] | None) -> dict:
    universe = build_market_universe(sector_data)
    companies = _company_ownership(universe)
    metrics = {
        **_concentration_snapshot(universe),
        **_breadth_snapshot(universe),
        "sector_count": int(universe["Sector"].nunique()) if not universe.empty else 0,
        "version": MARKET_LEDGER_VERSION,
    }
    archive = _archive_frame(set(universe["Ticker"].tolist())) if not universe.empty else pd.DataFrame()
    history, _historical_contributions, history_meta = _historical_ledger(archive, companies)
    contributions, return_meta = _one_year_contributions(universe)
    return {
        "metrics": metrics,
        "companies": companies,
        "sectors": _sector_ownership(companies),
        "history": history,
        "contributions": contributions,
        "history_metadata": history_meta,
        "return_metadata": return_meta,
    }
