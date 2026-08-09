from __future__ import annotations

import numpy as np
import pandas as pd


def _frame(value) -> pd.DataFrame:
    return value.copy() if isinstance(value, pd.DataFrame) else pd.DataFrame()


def queue_outcome_snapshot(frame: pd.DataFrame | None) -> dict:
    data = _frame(frame)
    if data.empty:
        return {}
    row = data.iloc[-1]
    result = {}
    for column, value in row.items():
        numeric = pd.to_numeric(value, errors="coerce")
        result[column] = float(numeric) if pd.notna(numeric) and np.isfinite(numeric) else value
    return result


def queue_region_profile(queue: pd.DataFrame | None, *, observation_date: str = "2025-12-31") -> pd.DataFrame:
    frame = _frame(queue)
    columns = [
        "Region", "Projects", "Queue GW", "Advanced GW", "Advanced Share Percent",
        "Median Queue Age Years", "Past Target GW", "Past Target Share Percent",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    status = frame.get("q_status", pd.Series("", index=frame.index)).fillna("").astype(str).str.casefold()
    frame = frame.loc[status.eq("active")].copy()
    frame["Queue MW"] = pd.to_numeric(frame.get("Queue MW"), errors="coerce")
    frame["q_date"] = pd.to_datetime(frame.get("q_date"), errors="coerce", format="mixed")
    frame["prop_year"] = pd.to_numeric(frame.get("prop_year"), errors="coerce")
    frame["region"] = frame.get("region", "Unspecified").fillna("Unspecified").astype(str).str.strip().replace("", "Unspecified")
    phase = frame.get("IA_phase_clean", pd.Series("", index=frame.index)).fillna("").astype(str)
    frame["_advanced_mw"] = frame["Queue MW"].where(phase.isin(["IA Executed", "Construction"]), 0.0)
    frame["_past_target_mw"] = frame["Queue MW"].where(frame["prop_year"].lt(pd.Timestamp(observation_date).year + 1), 0.0)
    date = pd.Timestamp(observation_date)
    frame["_age_years"] = (date - frame["q_date"]).dt.days / 365.25
    grouped = frame.groupby("region", dropna=False)
    out = grouped.agg(
        Projects=("Queue MW", "size"),
        Queue_MW=("Queue MW", "sum"),
        Advanced_MW=("_advanced_mw", "sum"),
        Median_Queue_Age_Years=("_age_years", "median"),
        Past_Target_MW=("_past_target_mw", "sum"),
    ).reset_index().rename(columns={
        "region": "Region", "Queue_MW": "Queue MW", "Advanced_MW": "Advanced MW",
        "Median_Queue_Age_Years": "Median Queue Age Years", "Past_Target_MW": "Past Target MW",
    })
    out["Queue GW"] = out.pop("Queue MW") / 1000.0
    out["Advanced GW"] = out.pop("Advanced MW") / 1000.0
    out["Past Target GW"] = out.pop("Past Target MW") / 1000.0
    out["Advanced Share Percent"] = out["Advanced GW"] / out["Queue GW"].where(out["Queue GW"].gt(0)) * 100.0
    out["Past Target Share Percent"] = out["Past Target GW"] / out["Queue GW"].where(out["Queue GW"].gt(0)) * 100.0
    return out[columns].sort_values("Queue GW", ascending=False, kind="stable").reset_index(drop=True)


def storage_duration_profile(operating_generators: pd.DataFrame | None) -> tuple[pd.DataFrame, dict]:
    frame = _frame(operating_generators)
    columns = ["Duration Band", "Generators", "Power GW", "Energy GWh", "Weighted Duration Hours"]
    if frame.empty:
        return pd.DataFrame(columns=columns), {}
    tech = frame.get("Technology Group", pd.Series("", index=frame.index)).fillna("").astype(str)
    status = frame.get("Status", pd.Series("", index=frame.index)).fillna("").astype(str)
    frame = frame.loc[tech.eq("Battery storage") & status.str.contains("Operating", case=False, na=False)].copy()
    frame["Power MW"] = pd.to_numeric(frame.get("Nameplate Capacity (MW)"), errors="coerce")
    frame["Energy MWh"] = pd.to_numeric(frame.get("Nameplate Energy Capacity (MWh)"), errors="coerce")
    frame = frame.loc[frame["Power MW"].gt(0) & frame["Energy MWh"].gt(0)].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns), {}
    frame["Duration Hours"] = frame["Energy MWh"] / frame["Power MW"]
    bins = [0, 2, 4, 8, np.inf]
    labels = ["Under 2 hours", "2–4 hours", "4–8 hours", "8+ hours"]
    frame["Duration Band"] = pd.cut(frame["Duration Hours"], bins=bins, labels=labels, right=False, include_lowest=True)
    out = frame.groupby("Duration Band", observed=False, as_index=False).agg(
        Generators=("Duration Hours", "size"),
        Power_MW=("Power MW", "sum"),
        Energy_MWh=("Energy MWh", "sum"),
    )
    out["Power GW"] = out.pop("Power_MW") / 1000.0
    out["Energy GWh"] = out.pop("Energy_MWh") / 1000.0
    out["Weighted Duration Hours"] = out["Energy GWh"] / out["Power GW"].where(out["Power GW"].gt(0))
    summary = {
        "generators": int(len(frame)),
        "power_gw": float(frame["Power MW"].sum() / 1000.0),
        "energy_gwh": float(frame["Energy MWh"].sum() / 1000.0),
        "weighted_duration_hours": float(frame["Energy MWh"].sum() / frame["Power MW"].sum()),
        "four_hour_plus_share": float(frame.loc[frame["Duration Hours"].ge(4), "Power MW"].sum() / frame["Power MW"].sum() * 100.0),
    }
    return out[columns], summary


def reserve_margin_profile(frame: pd.DataFrame | None) -> pd.DataFrame:
    data = _frame(frame)
    required = [
        "Assessment Area", "Anticipated Reserve Margin Percent",
        "Typical Conditions Margin Percent", "Extreme Conditions Margin Percent",
    ]
    if data.empty or not set(required).issubset(data.columns):
        return pd.DataFrame(columns=required + ["Stress Compression Points"])
    for column in required[1:]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data["Stress Compression Points"] = data["Anticipated Reserve Margin Percent"] - data["Extreme Conditions Margin Percent"]
    return data.dropna(subset=["Assessment Area", "Extreme Conditions Margin Percent"]).sort_values(
        "Extreme Conditions Margin Percent", ascending=True, kind="stable"
    ).reset_index(drop=True)
