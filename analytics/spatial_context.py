from __future__ import annotations

import re

import numpy as np
import pandas as pd


def _county_key(value) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()
    for suffix in (" county", " parish", " borough", " census area", " municipality", " city and borough"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
            break
    return text


def attach_water_context(infrastructure_data: dict, water_data: dict) -> tuple[dict, dict]:
    infrastructure = dict(infrastructure_data or {})
    water = dict(water_data or {})
    registry = infrastructure.get("facility_registry")
    counties = water.get("usgs_counties")
    if not isinstance(registry, pd.DataFrame):
        registry = pd.DataFrame()
    if not isinstance(counties, pd.DataFrame):
        counties = pd.DataFrame()
    registry = registry.copy()
    if registry.empty:
        water["facility_context"] = pd.DataFrame()
        water["facility_context_summary"] = {}
        return infrastructure, water

    registry["_state_key"] = registry.get("State", "").fillna("").astype(str).str.upper().str.strip()
    registry["_county_key"] = registry.get("County", "").map(_county_key)
    if not counties.empty and {"State", "County"}.issubset(counties.columns):
        context = counties.copy()
        context["_state_key"] = context["State"].fillna("").astype(str).str.upper().str.strip()
        context["_county_key"] = context["County"].map(_county_key)
        keep = [
            "_state_key", "_county_key", "FIPS", "Year", "Groundwater Withdrawal Mgal/d",
            "Surface Water Withdrawal Mgal/d", "Freshwater Withdrawal Mgal/d",
            "Saline Withdrawal Mgal/d", "Total Withdrawal Mgal/d", "Partial Consumptive Use Mgal/d",
        ]
        context = context[[column for column in keep if column in context.columns]].drop_duplicates(["_state_key", "_county_key"], keep="last")
        registry = registry.merge(context, on=["_state_key", "_county_key"], how="left")
    registry = registry.drop(columns=["_state_key", "_county_key"], errors="ignore")

    direct_fields = [
        "Water Withdrawal Gallons/Year", "Water Consumption Gallons/Year", "Site WUE L/kWh",
        "Water Permit or Utility Record", "Cooling System", "Water Source",
    ]
    direct_mask = pd.Series(False, index=registry.index)
    for field in direct_fields:
        if field not in registry.columns:
            continue
        if field in {"Water Withdrawal Gallons/Year", "Water Consumption Gallons/Year", "Site WUE L/kWh"}:
            direct_mask |= pd.to_numeric(registry[field], errors="coerce").notna()
        else:
            values = registry[field].fillna("").astype(str).str.casefold().str.strip()
            direct_mask |= values.ne("") & ~values.str.contains("not disclosed|unknown|unavailable", regex=True)
    registry["Direct Water Evidence"] = direct_mask
    registry["County Water Context Available"] = pd.to_numeric(registry.get("Total Withdrawal Mgal/d"), errors="coerce").notna()

    infrastructure["facility_registry"] = registry
    water["facility_context"] = registry
    water["facility_context_summary"] = {
        "facilities": int(len(registry)),
        "states": int(registry.get("State", pd.Series(dtype=object)).replace("", np.nan).nunique()),
        "state_identified_records": int(registry.get("State", pd.Series("", index=registry.index)).fillna("").astype(str).str.strip().ne("").sum()),
        "county_context_records": int(registry["County Water Context Available"].sum()),
        "direct_water_evidence_records": int(registry["Direct Water Evidence"].sum()),
        "quantified_withdrawal_records": int(pd.to_numeric(registry.get("Water Withdrawal Gallons/Year"), errors="coerce").notna().sum()),
        "quantified_consumption_records": int(pd.to_numeric(registry.get("Water Consumption Gallons/Year"), errors="coerce").notna().sum()),
    }
    return infrastructure, water


def infrastructure_attribution(history: pd.DataFrame | None) -> dict:
    """Compare enabling-system construction with lagged channel baselines.

    Private channels are benchmarked against the relevant broad private
    construction denominator. Public water, roads, and transit are benchmarked
    against their lagged share of the selected public-system construction mix.
    The result is a statistical alignment diagnostic, not AI attribution.
    """
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return {"history": pd.DataFrame(), "latest": {}, "components": pd.DataFrame()}
    frame = history.copy()
    frame["Observation Date"] = pd.to_datetime(frame.get("Observation Date"), errors="coerce", format="mixed")
    required = [
        "Data Center Construction",
        "Computer, Electronic & Electrical Manufacturing Construction",
        "Private Manufacturing Construction",
        "Electric Power Construction",
        "Communication Construction",
        "Private Nonresidential Construction",
        "Public Water Supply Construction",
        "Public Highway and Street Construction",
        "Public Transportation Construction",
    ]
    for column in required:
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
    frame = frame.dropna(subset=["Observation Date"]).sort_values("Observation Date", kind="stable")
    if frame.empty:
        return {"history": pd.DataFrame(), "latest": {}, "components": pd.DataFrame()}

    frame["Selected Public System Construction"] = frame[[
        "Public Water Supply Construction",
        "Public Highway and Street Construction",
        "Public Transportation Construction",
    ]].sum(axis=1, min_count=3)

    specs = [
        {
            "label": "Compute manufacturing",
            "observed": "Computer, Electronic & Electrical Manufacturing Construction",
            "denominator": "Private Manufacturing Construction",
            "group": "Direct support",
            "method": "Lagged 60-month median share of private manufacturing",
        },
        {
            "label": "Electric power",
            "observed": "Electric Power Construction",
            "denominator": "Private Nonresidential Construction",
            "group": "Direct support",
            "method": "Lagged 60-month median share of private nonresidential construction",
        },
        {
            "label": "Communications",
            "observed": "Communication Construction",
            "denominator": "Private Nonresidential Construction",
            "group": "Direct support",
            "method": "Lagged 60-month median share of private nonresidential construction",
        },
        {
            "label": "Public water",
            "observed": "Public Water Supply Construction",
            "denominator": "Selected Public System Construction",
            "group": "Public-system mix",
            "method": "Lagged 60-month median share of selected public water, roads, and transit construction",
        },
        {
            "label": "Roads & highways",
            "observed": "Public Highway and Street Construction",
            "denominator": "Selected Public System Construction",
            "group": "Public-system mix",
            "method": "Lagged 60-month median share of selected public water, roads, and transit construction",
        },
        {
            "label": "Public transit",
            "observed": "Public Transportation Construction",
            "denominator": "Selected Public System Construction",
            "group": "Public-system mix",
            "method": "Lagged 60-month median share of selected public water, roads, and transit construction",
        },
    ]

    expected_columns = []
    excess_columns = []
    component_rows = []
    for spec in specs:
        label = spec["label"]
        observed_column = spec["observed"]
        denominator_column = spec["denominator"]
        share = frame[observed_column] / frame[denominator_column].where(frame[denominator_column].gt(0))
        normal_share = share.shift(12).rolling(60, min_periods=36).median()
        expected_column = f"Expected {label}"
        excess_column = f"Excess {label}"
        deviation_column = f"Deviation {label}"
        frame[expected_column] = normal_share * frame[denominator_column]
        frame[deviation_column] = frame[observed_column] - frame[expected_column]
        frame[excess_column] = frame[deviation_column].clip(lower=0)
        expected_columns.append(expected_column)
        excess_columns.append(excess_column)
        valid = frame[["Observation Date", observed_column, expected_column, deviation_column, excess_column]].dropna().tail(1)
        if not valid.empty:
            row = valid.iloc[0]
            component_rows.append({
                "Component": label,
                "Group": spec["group"],
                "Date": row["Observation Date"],
                "Observed": row[observed_column],
                "Expected Baseline": row[expected_column],
                "Deviation from Baseline": row[deviation_column],
                "Excess Above Baseline": row[excess_column],
                "Baseline Method": spec["method"],
            })

    observed_columns = [spec["observed"] for spec in specs]
    broader_support = frame[observed_columns].sum(axis=1, min_count=len(observed_columns))
    expected_support = frame[expected_columns].sum(axis=1, min_count=len(expected_columns))
    output = pd.DataFrame({
        "Date": frame["Observation Date"],
        "Direct AI Construction": frame["Data Center Construction"],
        "Broader Supporting Construction": broader_support,
        "Expected Baseline": expected_support,
        "Excess Above Baseline": frame[excess_columns].sum(axis=1, min_count=len(excess_columns)),
        "Net Support Balance": broader_support - expected_support,
    }).dropna(subset=["Date"])
    valid_latest = output.dropna(subset=["Direct AI Construction"])
    latest = valid_latest.iloc[-1] if not valid_latest.empty else pd.Series(dtype=float)
    return {
        "history": output,
        "components": pd.DataFrame(component_rows),
        "latest": {
            "date": latest.get("Date"),
            "direct_ai_construction": pd.to_numeric(latest.get("Direct AI Construction"), errors="coerce"),
            "supporting_construction": pd.to_numeric(latest.get("Broader Supporting Construction"), errors="coerce"),
            "expected_baseline": pd.to_numeric(latest.get("Expected Baseline"), errors="coerce"),
            "excess_above_baseline": pd.to_numeric(latest.get("Excess Above Baseline"), errors="coerce"),
            "net_support_balance": pd.to_numeric(latest.get("Net Support Balance"), errors="coerce"),
        },
    }
