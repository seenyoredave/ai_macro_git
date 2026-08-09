from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
import time as time_module
from urllib.parse import urljoin

import numpy as np
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

from config.deployment import repository_writes_enabled
from config.market_clock import market_date, utc_now
from helpers.atomic_io import atomic_write_csv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
REQUEST_TIMEOUT = 60

PATHS = {
    "retail_history": DATA_DIR / "energy_retail_market_history.csv",
    "generation_history": DATA_DIR / "energy_generation_history.csv",
    "operating_generators": DATA_DIR / "energy_operating_generators.csv",
    "capacity_snapshot": DATA_DIR / "energy_capacity_snapshot.csv",
    "generator_pipeline": DATA_DIR / "energy_generator_pipeline.csv",
    "capacity_changes": DATA_DIR / "energy_capacity_changes_2026.csv",
    "interconnection_queue": DATA_DIR / "energy_interconnection_queue.csv",
    "interconnection_queue_summary": DATA_DIR / "energy_interconnection_queue_summary.csv",
    "wholesale_prices": DATA_DIR / "energy_wholesale_prices.csv",
    "gas_pipeline_projects": DATA_DIR / "energy_natural_gas_pipeline_projects.csv",
    "gas_pipeline_canonical": DATA_DIR / "energy_natural_gas_pipeline_canonical.csv",
    "lng_projects": DATA_DIR / "energy_lng_projects.csv",
    "gas_storage_projects": DATA_DIR / "energy_natural_gas_storage_projects.csv",
}

URLS = {
    "retail": "https://www.eia.gov/electricity/data/eia861m/xls/sales_revenue.xlsx",
    "generation": "https://www.eia.gov/electricity/monthly/xls/table_1_01.xlsx",
    "capacity_additions": "https://www.eia.gov/electricity/monthly/xls/table_6_03.xlsx",
    "capacity_retirements": "https://www.eia.gov/electricity/monthly/xls/table_6_04.xlsx",
    "lng": "https://www.eia.gov/naturalgas/importsexports/liquefactioncapacity/U.S.liquefactioncapacity.xlsx",
    "gas_storage": "https://www.eia.gov/naturalgas/storage/EIA-StoragePlan.xlsx",
}

EIA_860M_PAGE_URL = "https://www.eia.gov/electricity/data/eia860m/"
EIA_NATURAL_GAS_DATA_URL = "https://www.eia.gov/naturalgas/data.php"
LBNL_QUEUE_PAGE_URL = "https://emp.lbl.gov/queues"


REFRESH_SCOPES = {
    "power": {
        "retail_history",
        "generation_history",
        "generators",
        "capacity_changes",
        "wholesale_prices",
        "gas_pipeline",
        "lng_projects",
        "gas_storage_projects",
    },
    "grid_storage": {
        "generators",
        "capacity_changes",
        "interconnection_queue",
    },
}
REFRESH_SCOPES["all"] = set().union(*REFRESH_SCOPES.values())


def _number(values):
    return pd.to_numeric(values, errors="coerce")


def _text(values):
    return values.fillna("").astype(str).str.strip()


def _technology_group(value):
    text = str(value or "").lower()
    if "solar" in text:
        return "Solar"
    if "wind" in text:
        return "Wind"
    if "batter" in text or "storage" in text:
        return "Battery storage"
    if "natural gas" in text or text.strip() == "gas":
        return "Natural gas"
    if "coal" in text:
        return "Coal"
    if "nuclear" in text:
        return "Nuclear"
    if "hydro" in text:
        return "Hydro"
    if any(token in text for token in ("biomass", "landfill", "geothermal", "waste")):
        return "Other renewables"
    if any(token in text for token in ("petroleum", "diesel", "oil", "other gases")):
        return "Other thermal"
    return "Other"


def _get(url):
    response = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "ai-macro-energy/2.0"})
    response.raise_for_status()
    return response.content


def _discover_download_url(page_url: str, pattern: str) -> str:
    """Resolve the first matching official download exposed by a release page.

    EIA and Berkeley Lab list newest releases first. Resolving the link at click
    time keeps the manual refresh useful after monthly, quarterly, or annual
    filenames roll forward without guessing the next filename.
    """
    response = requests.get(
        page_url,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": "ai-macro-energy/2.0"},
    )
    response.raise_for_status()
    matcher = re.compile(pattern, re.I)
    soup = BeautifulSoup(response.text, "html.parser")
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if matcher.search(href):
            return urljoin(page_url, href)
    raise ValueError(f"Official release page exposed no matching download: {page_url}")


def _latest_generator_url() -> str:
    return _discover_download_url(
        EIA_860M_PAGE_URL,
        r"/eia860m/xls/[a-z]+_generator\d{4}\.xlsx(?:$|\?)",
    )


def _latest_pipeline_url() -> str:
    return _discover_download_url(
        EIA_NATURAL_GAS_DATA_URL,
        r"NaturalGasPipelineProjects[^/]*\.xlsx(?:$|\?)",
    )


def _latest_queue_url() -> str:
    return _discover_download_url(
        LBNL_QUEUE_PAGE_URL,
        r"lbnl_ix_queue_data_file_thru\d{4}\.xlsx(?:$|\?)",
    )


def _wholesale_urls() -> list[tuple[str, int]]:
    year = int(market_date().year)
    prior = year - 1
    return [
        (
            f"https://www.eia.gov/electricity/wholesale/xls/archive/ice_electric-{prior}final.xlsx",
            prior,
        ),
        (
            f"https://www.eia.gov/electricity/wholesale/xls/ice_electric-{year}.xlsx",
            year,
        ),
    ]


def _write(frame, path):
    if not repository_writes_enabled():
        return
    atomic_write_csv(frame, path)


def _read(path, dates=()):
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    frame = pd.read_csv(path)
    for column in dates:
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce", format="mixed")
    return frame


def _parse_retail(content):
    raw = pd.read_excel(BytesIO(content), sheet_name="Monthly-States", header=2, engine="openpyxl")
    raw["Year"] = _number(raw["Year"])
    raw["Month"] = _number(raw["Month"])
    raw = raw.loc[raw["Year"].between(2015, 2100) & raw["Month"].between(1, 12)].copy()
    raw["Date"] = pd.to_datetime(dict(year=raw["Year"].astype(int), month=raw["Month"].astype(int), day=1))
    raw["State"] = _text(raw["State"])
    raw["Data Status"] = _text(raw["Data Status"])
    specs = {
        "Residential": ("Thousand Dollars", "Megawatthours", "Count", "Cents/kWh"),
        "Commercial": ("Thousand Dollars.1", "Megawatthours.1", "Count.1", "Cents/kWh.1"),
        "Industrial": ("Thousand Dollars.2", "Megawatthours.2", "Count.2", "Cents/kWh.2"),
        "Transportation": ("Thousand Dollars.3", "Megawatthours.3", "Count.3", "Cents/kWh.3"),
        "Total": ("Thousand Dollars.4", "Megawatthours.4", "Count.4", "Cents/kWh.4"),
    }
    rows = []
    for sector, (revenue, sales, customers, price) in specs.items():
        rows.append(pd.DataFrame({
            "Date": raw["Date"],
            "Geography": raw["State"],
            "Sector": sector,
            "Sales MWh": _number(raw[sales]),
            "Revenue Thousand Dollars": _number(raw[revenue]),
            "Customers": _number(raw[customers]),
            "Price Cents per kWh": _number(raw[price]),
            "Data Status": raw["Data Status"],
        }))
    states = pd.concat(rows, ignore_index=True)
    national = states.groupby(["Date", "Sector"], as_index=False).agg({
        "Sales MWh": "sum",
        "Revenue Thousand Dollars": "sum",
        "Customers": "sum",
    })
    national["Price Cents per kWh"] = national["Revenue Thousand Dollars"] * 100.0 / national["Sales MWh"]
    national["Geography"] = "United States"
    national["Data Status"] = np.where(national["Date"].dt.year >= 2025, "Preliminary", "Final")
    return pd.concat([states, national[states.columns]], ignore_index=True)


def _parse_generation(content):
    raw = pd.read_excel(BytesIO(content), header=None, engine="openpyxl")
    headers = [str(value).replace("\n", " ").strip() for value in raw.iloc[3].tolist()]
    columns = {
        "Coal": "Coal",
        "Natural gas": "Natural Gas",
        "Nuclear": "Nuclear",
        "Hydro": "Hydroelectric Conventional",
        "Solar": "Estimated Total Solar",
        "Wind + other renewables": "Renewable Sources Excluding Hydroelectric and Solar",
        "Other": "Other",
    }
    annual = raw.iloc[5:15].copy()
    annual.columns = headers
    annual = annual.loc[_number(annual["Period"]).notna()].copy()
    annual["Year"] = _number(annual["Period"]).astype(int)
    rows = []
    for label, column in columns.items():
        rows.append(pd.DataFrame({
            "Period Type": "Annual",
            "Date": pd.to_datetime(annual["Year"].astype(str) + "-12-31"),
            "Source": label,
            "Generation GWh": _number(annual[column]),
        }))
    months = {"January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6, "July": 7, "August": 8, "Sept": 9, "October": 10, "November": 11, "December": 12}
    year = None
    for index in range(15, min(47, len(raw))):
        label = str(raw.iloc[index, 0]).strip()
        if label.startswith("Year "):
            year = int(label.split()[-1])
            continue
        if year is None or label not in months:
            continue
        for source, column in columns.items():
            value = pd.to_numeric(raw.iloc[index, headers.index(column)], errors="coerce")
            if pd.notna(value):
                rows.append(pd.DataFrame([{
                    "Period Type": "Monthly",
                    "Date": pd.Timestamp(year, months[label], 1),
                    "Source": source,
                    "Generation GWh": float(value),
                }]))
    return pd.concat(rows, ignore_index=True)


def _parse_generators(content):
    workbook = BytesIO(content)
    operating = pd.read_excel(workbook, sheet_name="Operating", header=2, engine="openpyxl")
    workbook.seek(0)
    planned = pd.read_excel(workbook, sheet_name="Planned", header=2, engine="openpyxl")
    numeric = ["Nameplate Capacity (MW)", "Net Summer Capacity (MW)", "Net Winter Capacity (MW)", "Nameplate Energy Capacity (MWh)", "DC Net Capacity (MW)", "Latitude", "Longitude"]
    for column in numeric:
        if column in operating:
            operating[column] = _number(operating[column])
    operating = operating.loc[
        _number(operating.get("Plant ID")).notna()
        & _text(operating.get("Generator ID", pd.Series("", index=operating.index))).ne("")
    ].copy()
    operating["Technology Group"] = operating["Technology"].map(_technology_group)
    operating["Plant State"] = _text(operating["Plant State"])
    operating["Status"] = _text(operating["Status"])
    operating_columns = ["Entity ID", "Entity Name", "Plant ID", "Plant Name", "Plant State", "County", "Balancing Authority Code", "Sector", "Generator ID", "Nameplate Capacity (MW)", "Net Summer Capacity (MW)", "Net Winter Capacity (MW)", "Technology", "Technology Group", "Energy Source Code", "Prime Mover Code", "Operating Month", "Operating Year", "Planned Retirement Month", "Planned Retirement Year", "Status", "Nameplate Energy Capacity (MWh)", "Latitude", "Longitude"]
    operating = operating.reindex(columns=operating_columns)
    capacity = operating.groupby("Technology Group", as_index=False).agg(
        Generators=("Generator ID", "size"),
        Plants=("Plant ID", "nunique"),
        **{
            "Net Summer Capacity MW": ("Net Summer Capacity (MW)", "sum"),
            "Nameplate Capacity MW": ("Nameplate Capacity (MW)", "sum"),
            "Storage Energy MWh": ("Nameplate Energy Capacity (MWh)", "sum"),
        },
    )
    for column in ["Nameplate Capacity (MW)", "Net Summer Capacity (MW)", "Net Winter Capacity (MW)", "Latitude", "Longitude", "Planned Operation Month", "Planned Operation Year"]:
        planned[column] = _number(planned[column])
    planned = planned.loc[
        _number(planned.get("Plant ID")).notna()
        & _text(planned.get("Generator ID", pd.Series("", index=planned.index))).ne("")
    ].copy()
    planned["Technology Group"] = planned["Technology"].map(_technology_group)
    planned["Pipeline Type"] = "Addition"
    planned["Expected Year"] = planned["Planned Operation Year"]
    planned["Expected Month"] = planned["Planned Operation Month"]
    planned["Plant State"] = _text(planned["Plant State"])
    planned["Status"] = _text(planned["Status"])
    retirements = operating.loc[_number(operating["Planned Retirement Year"]).notna()].copy()
    retirements["Pipeline Type"] = "Retirement"
    retirements["Expected Year"] = _number(retirements["Planned Retirement Year"])
    retirements["Expected Month"] = _number(retirements["Planned Retirement Month"])
    pipeline_columns = ["Pipeline Type", "Entity ID", "Entity Name", "Plant ID", "Plant Name", "Plant State", "County", "Balancing Authority Code", "Sector", "Generator ID", "Nameplate Capacity (MW)", "Net Summer Capacity (MW)", "Net Winter Capacity (MW)", "Technology", "Technology Group", "Energy Source Code", "Prime Mover Code", "Expected Month", "Expected Year", "Status", "Latitude", "Longitude"]
    pipeline = pd.concat([planned.reindex(columns=pipeline_columns), retirements.reindex(columns=pipeline_columns)], ignore_index=True)
    return {
        "operating_generators": operating,
        "capacity_snapshot": capacity,
        "generator_pipeline": pipeline,
    }


def _parse_capacity_changes(additions, retirements):
    rows = []
    for content, kind in ((additions, "Addition"), (retirements, "Retirement")):
        frame = pd.read_excel(BytesIO(content), header=1, engine="openpyxl")
        frame = frame.loc[_number(frame["Year"]).notna()].copy()
        frame["Pipeline Type"] = kind
        frame["Technology Group"] = frame["Technology"].map(_technology_group)
        frame["Date"] = pd.to_datetime(dict(year=_number(frame["Year"]).astype(int), month=_number(frame["Month"]).astype(int), day=1))
        rows.append(frame)
    return pd.concat(rows, ignore_index=True)


def _parse_queue(content):
    raw = pd.read_excel(BytesIO(content), sheet_name="03. Complete Queue Data", header=None, engine="openpyxl")
    frame = raw.iloc[2:].copy()
    frame.columns = raw.iloc[1].tolist()
    frame = frame.loc[frame["q_status"].isin(["active", "suspended"])].copy()
    for column in ["mw_1", "mw_2", "mw_3", "q_year", "prop_year"]:
        frame[column] = _number(frame[column])
    generation_parts = []
    storage_parts = []
    for index in (1, 2, 3):
        technology = _text(frame.get(f"type_{index}", pd.Series("", index=frame.index)))
        capacity = _number(frame.get(f"mw_{index}", pd.Series(np.nan, index=frame.index)))
        storage = technology.str.casefold().str.contains("battery|storage", regex=True)
        generation_parts.append(capacity.where(technology.ne("") & ~storage))
        storage_parts.append(capacity.where(storage))
    frame["Generation MW"] = pd.concat(generation_parts, axis=1).sum(axis=1, min_count=1)
    frame["Storage MW"] = pd.concat(storage_parts, axis=1).sum(axis=1, min_count=1)
    frame["Queue MW"] = frame[["Generation MW", "Storage MW"]].sum(axis=1, min_count=1)
    frame["Technology Group"] = frame["type_clean"].map(_technology_group)
    frame["Queue Accounting"] = "Submitted components; hybrid-storage imputation excluded"
    columns = [
        "q_id", "q_status", "q_date", "prop_date", "ia_date", "IA_phase_clean",
        "county", "state", "region", "project_name", "utility", "entity", "developer",
        "service", "project_type", "type_1", "type_2", "type_3", "type_clean",
        "Technology Group", "mw_1", "mw_2", "mw_3", "Generation MW", "Storage MW",
        "Queue MW", "Queue Accounting", "q_year", "prop_year",
    ]

    # Berkeley Lab's published headline table separately counts generation and
    # storage components and estimates missing hybrid-storage capacity. It is
    # the reconciliation authority for the national total and technology mix.
    summary_raw = pd.read_excel(
        BytesIO(content),
        sheet_name="08. Active Capacity by Type",
        header=None,
        engine="openpyxl",
    )
    header_rows = summary_raw.index[
        summary_raw.iloc[:, 0].fillna("").astype(str).str.strip().eq("Type")
        & summary_raw.iloc[:, 1].fillna("").astype(str).str.strip().eq("Year")
    ]
    if len(header_rows):
        summary = summary_raw.iloc[int(header_rows[0]) + 1 :, :4].copy()
        summary.columns = ["Technology Group", "As Of Year", "Configuration", "Capacity GW"]
        summary["As Of Year"] = _number(summary["As Of Year"])
        summary["Capacity GW"] = _number(summary["Capacity GW"])
        summary = summary.dropna(subset=["Technology Group", "As Of Year", "Capacity GW"])
        summary = summary.loc[summary["As Of Year"].eq(summary["As Of Year"].max())].copy()
        summary["Technology Group"] = summary["Technology Group"].replace(
            {"Storage": "Battery storage", "Gas": "Natural gas"}
        )
        summary["Configuration"] = summary["Configuration"].astype(str).str.strip().str.title()
        summary = (
            summary.pivot_table(
                index=["Technology Group", "As Of Year"],
                columns="Configuration",
                values="Capacity GW",
                aggfunc="sum",
                fill_value=0,
            )
            .reset_index()
        )
        for column in ("Standalone", "Hybrid"):
            if column not in summary:
                summary[column] = 0.0
        summary = summary.rename(
            columns={"Standalone": "Standalone GW", "Hybrid": "Hybrid GW"}
        )
        summary["Queue GW"] = summary["Standalone GW"] + summary["Hybrid GW"]
        summary["Capacity Method"] = (
            "Berkeley Lab active-capacity component accounting; hybrid storage may be estimated"
        )
        summary = summary[
            ["Technology Group", "Standalone GW", "Hybrid GW", "Queue GW", "As Of Year", "Capacity Method"]
        ].sort_values("Queue GW", ascending=False, kind="stable")
    else:
        summary = pd.DataFrame(
            columns=["Technology Group", "Standalone GW", "Hybrid GW", "Queue GW", "As Of Year", "Capacity Method"]
        )
    return {
        "interconnection_queue": frame.reindex(columns=columns),
        "interconnection_queue_summary": summary.reset_index(drop=True),
    }


def _parse_wholesale(contents):
    rows = []
    for content, year in contents:
        frame = pd.read_excel(BytesIO(content), sheet_name=str(year), header=0, engine="openpyxl")
        frame.columns = [str(column).replace("\n", " ").strip() for column in frame.columns]
        frame = frame.rename(columns={"Price hub": "Hub", "Trade date": "Trade Date", "Delivery start date": "Delivery Start", "Delivery  end date": "Delivery End", "Wtd avg price $/MWh": "Price $/MWh", "Daily volume MWh": "Volume MWh", "Number of trades": "Trades", "Number of counterparties": "Counterparties"})
        for column in ["Price $/MWh", "Volume MWh", "Trades", "Counterparties", "High price $/MWh", "Low price $/MWh"]:
            if column in frame:
                frame[column] = _number(frame[column].astype(str).str.replace(",", "", regex=False))
        for column in ["Trade Date", "Delivery Start", "Delivery End"]:
            if column in frame:
                frame[column] = pd.to_datetime(frame[column], errors="coerce")
        rows.append(frame)
    return pd.concat(rows, ignore_index=True)


def _parse_gas_pipeline(content):
    frame = pd.read_excel(BytesIO(content), sheet_name="Natural Gas Pipeline Projects", header=1, engine="openpyxl")
    frame.columns = [str(column).strip() for column in frame.columns]
    for column in ["Additional Capacity (MMcf/d)", "Cost (millions)", "Miles", "Pipeline Diameter (Inches)", "Year In Service Date"]:
        if column in frame:
            frame[column] = _number(frame[column].astype(str).str.replace(",", "", regex=False).replace({"na": np.nan, "nan": np.nan}))
    return frame


def _canonicalize_gas_pipeline(frame):
    clean = frame.copy()
    clean["Last Updated Date"] = pd.to_datetime(clean.get("Last Updated Date"), errors="coerce", format="mixed")
    clean["Additional Capacity (MMcf/d)"] = _number(clean.get("Additional Capacity (MMcf/d)"))
    docket = _text(clean.get("Docket Number", pd.Series("", index=clean.index))).str.casefold()
    name = _text(clean.get("Project Name", pd.Series("", index=clean.index))).str.casefold().str.replace(r"[^a-z0-9]+", " ", regex=True).str.strip()
    operator = _text(clean.get("Pipeline Operator Name", pd.Series("", index=clean.index))).str.casefold().str.replace(r"[^a-z0-9]+", " ", regex=True).str.strip()
    clean["_key"] = docket.where(docket.ne(""), operator + "|" + name)
    clean["_name"] = name
    rows = []
    for _, group in clean.groupby("_key", dropna=False, sort=False):
        group = group.sort_values("Last Updated Date", ascending=False, kind="stable")
        kept = []
        for _, row in group.iterrows():
            row_name = str(row.get("_name") or "")
            row_tokens = set(row_name.split())
            phase = any(token in row_tokens for token in {"phase", "ph", "stage", "train"})
            duplicate = None
            for index, existing in enumerate(kept):
                existing_name = str(existing.get("_name") or "")
                existing_tokens = set(existing_name.split())
                existing_phase = any(token in existing_tokens for token in {"phase", "ph", "stage", "train"})
                overlap = len(row_tokens & existing_tokens) / max(len(row_tokens | existing_tokens), 1)
                row_capacity = pd.to_numeric(row.get("Additional Capacity (MMcf/d)"), errors="coerce")
                existing_capacity = pd.to_numeric(existing.get("Additional Capacity (MMcf/d)"), errors="coerce")
                same_capacity = pd.notna(row_capacity) and pd.notna(existing_capacity) and abs(row_capacity - existing_capacity) <= max(abs(existing_capacity) * 0.01, 1.0)
                if not phase and not existing_phase and (overlap >= 0.55 or same_capacity):
                    duplicate = index
                    break
            if duplicate is None:
                row = row.copy()
                row["Source Records"] = 1
                kept.append(row)
            else:
                kept[duplicate]["Source Records"] = int(kept[duplicate].get("Source Records", 1)) + 1
        rows.extend(kept)
    output = pd.DataFrame(rows).drop(columns=["_key", "_name"], errors="ignore")
    return output.reset_index(drop=True)


def _parse_lng(content):
    book = BytesIO(content)
    existing = pd.read_excel(book, sheet_name="Existing & Under Construction", header=None, engine="openpyxl").iloc[3:].copy()
    existing.columns = ["Project", "Train", "Baseload Bcf/d", "Baseload MTPA", "Peak Bcf/d", "Peak MTPA", "Status", "In-service Date", "Commercial Service Date", "State", "FTA Bcf/d", "FTA MTPA", "FTA Docket", "Non-FTA Bcf/d", "Non-FTA MTPA", "Non-FTA Docket", "FERC Bcf/d", "FERC MTPA", "FERC Docket", "Project Type", "Operator"]
    existing["Pipeline Type"] = "Existing / construction"
    book.seek(0)
    approved = pd.read_excel(book, sheet_name="Approved", header=None, engine="openpyxl").iloc[4:].copy()
    approved.columns = ["Project", "Operator", "Design Bcf/d per train", "Design MTPA per train", "Trains", "Design Bcf/d", "Design MTPA", "Status", "State", "FTA Bcf/d", "FTA MTPA", "FTA Docket", "Non-FTA Bcf/d", "Non-FTA MTPA", "Non-FTA Docket", "FERC Bcf/d", "FERC MTPA", "FERC Docket", "Project Type"]
    approved["Pipeline Type"] = "Approved"
    for frame in (existing, approved):
        for column in frame.columns:
            if "Bcf/d" in column or column == "Trains":
                frame[column] = _number(frame[column].astype(str).str.extract(r"([-+]?\d*\.?\d+)")[0])
    output = pd.concat([existing, approved], ignore_index=True, sort=False)
    project = _text(output.get("Project", pd.Series("", index=output.index)))
    status = _text(output.get("Status", pd.Series("", index=output.index)))
    operator = _text(output.get("Operator", pd.Series("", index=output.index)))
    capacity_columns = [column for column in output.columns if "Bcf/d" in str(column)]
    capacity = output[capacity_columns].apply(pd.to_numeric, errors="coerce").max(axis=1) if capacity_columns else pd.Series(np.nan, index=output.index)
    valid = project.ne("") & ~project.str.casefold().eq("notes:") & ~project.str.startswith("+")
    valid &= capacity.gt(0) | status.ne("") | operator.ne("")
    return output.loc[valid].reset_index(drop=True)


def _parse_storage(content):
    frame = pd.read_excel(BytesIO(content), sheet_name="Facilities and Expansions", header=1, engine="openpyxl")
    for column in ["Year in Service", "Total Capacity (Bcf)", "Working Capacity (Bcf)", "Deliverability (MMcf/day)"]:
        frame[column] = _number(frame[column].astype(str).replace("-", np.nan))
    return frame.loc[_text(frame.get("Project Name", pd.Series("", index=frame.index))).ne("")].reset_index(drop=True)


def _load_local():
    dates = {
        "retail_history": ("Date",),
        "generation_history": ("Date",),
        "capacity_changes": ("Date",),
        "interconnection_queue": ("q_date", "prop_date", "ia_date"),
        "wholesale_prices": ("Trade Date", "Delivery Start", "Delivery End"),
        "gas_pipeline_projects": ("Last Updated Date", "Completed Date"),
        "lng_projects": ("In-service Date", "Commercial Service Date"),
    }
    return {name: _read(path, dates.get(name, ())) for name, path in PATHS.items()}


def _refresh(scope: str = "all"):
    frames = _load_local()
    errors = {}
    refreshed = []
    resolved_urls = {}
    selected = REFRESH_SCOPES.get(str(scope), REFRESH_SCOPES["all"])

    def fetched(label: str, url: str) -> bytes:
        resolved_urls[label] = url
        return _get(url)

    def apply(label, fetch, parse):
        if label not in selected:
            return
        try:
            result = parse(fetch())
            if result is None:
                raise ValueError(f"{label} parser returned no data")
            if isinstance(result, dict):
                updates = result
            else:
                updates = {label: result}
            for name, frame in updates.items():
                if not isinstance(frame, pd.DataFrame):
                    raise TypeError(
                        f"{name} parser returned {type(frame).__name__}, expected DataFrame"
                    )
                _write(frame, PATHS[name])
                frames[name] = frame
                refreshed.append(name)
        except Exception as exc:
            errors[label] = f"{type(exc).__name__}: {exc}"

    apply("retail_history", lambda: fetched("retail_history", URLS["retail"]), _parse_retail)
    apply("generation_history", lambda: fetched("generation_history", URLS["generation"]), _parse_generation)
    apply("generators", lambda: fetched("generators", _latest_generator_url()), _parse_generators)
    apply(
        "capacity_changes",
        lambda: (
            fetched("capacity_additions", URLS["capacity_additions"]),
            fetched("capacity_retirements", URLS["capacity_retirements"]),
        ),
        lambda content: _parse_capacity_changes(content[0], content[1]),
    )
    apply(
        "interconnection_queue",
        lambda: fetched("interconnection_queue", _latest_queue_url()),
        _parse_queue,
    )

    def fetch_wholesale():
        payloads = []
        for url, year in _wholesale_urls():
            payloads.append((fetched(f"wholesale_{year}", url), year))
        return payloads

    apply(
        "wholesale_prices",
        fetch_wholesale,
        _parse_wholesale,
    )

    def parse_gas(content):
        raw = _parse_gas_pipeline(content)
        return {
            "gas_pipeline_projects": raw,
            "gas_pipeline_canonical": _canonicalize_gas_pipeline(raw),
        }

    apply(
        "gas_pipeline",
        lambda: fetched("gas_pipeline", _latest_pipeline_url()),
        parse_gas,
    )
    apply("lng_projects", lambda: fetched("lng_projects", URLS["lng"]), _parse_lng)
    apply(
        "gas_storage_projects",
        lambda: fetched("gas_storage_projects", URLS["gas_storage"]),
        _parse_storage,
    )
    return _load_local(), errors, refreshed, resolved_urls


@st.cache_data(ttl=3600)
def load_energy_market_data(*, force_refresh=False, refresh_token=0, refresh_scope="all"):
    del refresh_token
    started = time_module.perf_counter()
    errors = {}
    refreshed = []
    resolved_urls = {}
    if force_refresh:
        frames, errors, refreshed, resolved_urls = _refresh(refresh_scope)
        if refreshed and not errors:
            source_mode = "refreshed"
        elif refreshed:
            source_mode = "partial_refresh"
        else:
            source_mode = "retained_fallback"
    else:
        frames = _load_local()
        source_mode = "retained"
    returned = {name: int(len(frame)) for name, frame in frames.items()}
    frames["market_load_report"] = {
        "source_mode": source_mode,
        "elapsed_sec": float(time_module.perf_counter() - started),
        "requested_at_utc": utc_now().isoformat(),
        "returned_rows": returned,
        "refreshed_datasets": refreshed,
        "refresh_scope": str(refresh_scope),
        "resolved_urls": resolved_urls,
        "errors": errors,
        "error": "; ".join(f"{name}: {message}" for name, message in errors.items()) or None,
    }
    return frames
