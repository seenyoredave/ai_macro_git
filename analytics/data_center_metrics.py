"""Universal data-center metric grain and campus rollup contract."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class MetricSpec:
    metric: str
    unit: str
    aggregation: str


METRIC_SPECS = {
    "Square Feet": MetricSpec("Square Feet", "sq ft", "sum"),
    "Published Capacity Estimate MW": MetricSpec("Published Capacity Estimate MW", "MW", "sum"),
    "Planned Data Center Capacity MW": MetricSpec("Planned Data Center Capacity MW", "MW", "sum"),
    "Contracted Utility Capacity MW": MetricSpec("Contracted Utility Capacity MW", "MW", "sum"),
    "Energized Capacity MW": MetricSpec("Energized Capacity MW", "MW", "sum"),
    "Annual Electricity Consumption MWh": MetricSpec("Annual Electricity Consumption MWh", "MWh/year", "sum"),
    "Planned Onsite Generation MW": MetricSpec("Planned Onsite Generation MW", "MW", "sum"),
    "Water Withdrawal Gallons/Year": MetricSpec("Water Withdrawal Gallons/Year", "gal/year", "sum"),
    "Water Consumption Gallons/Year": MetricSpec("Water Consumption Gallons/Year", "gal/year", "sum"),
    "Site WUE L/kWh": MetricSpec("Site WUE L/kWh", "L/kWh", "weighted_mean"),
}

FACT_COLUMNS = [
    "Campus ID", "Entity ID", "Entity Level", "Parent Entity ID", "Metric", "Value", "Unit",
    "Measurement Scope", "Aggregation Method", "Source", "Source Date", "Evidence Grade",
]


def normalize_metric_facts(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=FACT_COLUMNS)
    output = frame.copy()
    for column in FACT_COLUMNS:
        if column not in output.columns:
            output[column] = np.nan if column == "Value" else ""
    output["Value"] = pd.to_numeric(output["Value"], errors="coerce")
    for column in set(FACT_COLUMNS) - {"Value"}:
        output[column] = output[column].fillna("").astype(str).str.strip()
    output["Entity Level"] = output["Entity Level"].str.casefold()
    return output[FACT_COLUMNS].reset_index(drop=True)


def validate_metric_facts(frame: pd.DataFrame | None, campuses: pd.DataFrame) -> pd.DataFrame:
    facts = normalize_metric_facts(frame)
    if facts.empty:
        return facts
    canonical = set(campuses.get("Campus ID", pd.Series(dtype=str)).dropna().astype(str))
    unknown = set(facts["Campus ID"].dropna().astype(str)) - {""} - canonical
    if unknown:
        raise ValueError(f"Data-center metric facts reference {len(unknown)} unknown Campus IDs")
    missing_scope = facts["Measurement Scope"].eq("")
    if missing_scope.any():
        raise ValueError("Every data-center metric fact must declare Measurement Scope")
    child = facts["Entity Level"].isin({"facility", "building"})
    if (child & facts["Parent Entity ID"].eq("")).any():
        raise ValueError("Facility and building metric facts must declare Parent Entity ID")
    return facts


def _direct_fact(facts: pd.DataFrame, level: str) -> pd.Series | None:
    rows = facts.loc[facts["Entity Level"].eq(level) & facts["Value"].notna()].copy()
    if rows.empty:
        return None
    grade = rows["Evidence Grade"].map({"A": 5, "B": 4, "C": 3, "D": 2}).fillna(0)
    dates = pd.to_datetime(rows["Source Date"], errors="coerce").rank(method="dense", pct=True).fillna(0)
    rows["_priority"] = grade * 10 + dates
    return rows.sort_values("_priority", ascending=False, kind="stable").iloc[0]


def rollup_campus_metric(
    facts: pd.DataFrame | None,
    *,
    campus_id: str,
    metric: str,
    weight_metric: str = "Annual Electricity Consumption MWh",
) -> dict:
    clean = normalize_metric_facts(facts)
    clean = clean.loc[clean["Campus ID"].eq(str(campus_id)) & clean["Metric"].eq(metric)].copy()
    spec = METRIC_SPECS.get(metric, MetricSpec(metric, "", "sum"))
    if clean.empty:
        return {"Campus ID": campus_id, "Metric": metric, "Value": np.nan, "Unit": spec.unit, "Measurement Scope": "campus", "Aggregation Method": spec.aggregation, "Source": "", "Source Date": "", "Evidence Grade": ""}

    # A direct campus measurement is the campus total. Child measurements are detail, not additions to it.
    direct = _direct_fact(clean, "campus")
    if direct is not None:
        return {**direct.to_dict(), "Entity ID": campus_id, "Entity Level": "campus", "Measurement Scope": "campus", "Aggregation Method": "direct_total"}

    child = clean.loc[clean["Entity Level"].isin({"facility", "building"}) & clean["Value"].notna()].copy()
    if child.empty:
        return {"Campus ID": campus_id, "Metric": metric, "Value": np.nan, "Unit": spec.unit, "Measurement Scope": "campus", "Aggregation Method": spec.aggregation, "Source": "", "Source Date": "", "Evidence Grade": ""}

    # Facility totals supersede only their own building children. Buildings attached
    # directly to the campus remain additive because no facility-level total covers them.
    facilities = child.loc[child["Entity Level"].eq("facility")].copy()
    buildings = child.loc[child["Entity Level"].eq("building")].copy()
    if not facilities.empty:
        direct_buildings = buildings.loc[buildings["Parent Entity ID"].eq(str(campus_id))]
        selected = pd.concat([facilities, direct_buildings], ignore_index=True, sort=False)
    else:
        selected = buildings
    if spec.aggregation == "max":
        value = selected["Value"].max()
    elif spec.aggregation == "mean":
        value = selected["Value"].mean()
    elif spec.aggregation == "weighted_mean":
        # Weight must be supplied as facts at the same selected entity grain.
        weights = normalize_metric_facts(facts)
        weights = weights.loc[
            weights["Campus ID"].eq(str(campus_id))
            & weights["Metric"].eq(weight_metric)
            & weights["Entity ID"].isin(selected["Entity ID"])
        ][["Entity ID", "Value"]].rename(columns={"Value": "_weight"})
        weighted = selected.merge(weights, on="Entity ID", how="left")
        valid = weighted["Value"].notna() & weighted["_weight"].gt(0)
        value = float(np.average(weighted.loc[valid, "Value"], weights=weighted.loc[valid, "_weight"])) if valid.any() else np.nan
    else:
        # One fact per child entity. Duplicate source observations for the same entity do not multiply the total.
        entity_values = selected.sort_values("Source Date", kind="stable").drop_duplicates("Entity ID", keep="last")
        value = entity_values["Value"].sum(min_count=1)

    return {
        "Campus ID": campus_id,
        "Entity ID": campus_id,
        "Entity Level": "campus",
        "Metric": metric,
        "Value": float(value) if pd.notna(value) else np.nan,
        "Unit": spec.unit,
        "Measurement Scope": "campus",
        "Aggregation Method": spec.aggregation,
        "Source": "derived from canonical child entities",
        "Source Date": "",
        "Evidence Grade": "",
    }


def rollup_all_campuses(facts: pd.DataFrame | None, campuses: pd.DataFrame, *, metric: str) -> pd.DataFrame:
    clean = validate_metric_facts(facts, campuses)
    rows = [rollup_campus_metric(clean, campus_id=campus_id, metric=metric) for campus_id in campuses.get("Campus ID", pd.Series(dtype=str)).astype(str)]
    return pd.DataFrame(rows)


__all__ = ["MetricSpec", "METRIC_SPECS", "FACT_COLUMNS", "normalize_metric_facts", "validate_metric_facts", "rollup_campus_metric", "rollup_all_campuses"]
