from __future__ import annotations

ENERGY_DATA_VERSION = "1.2"

ENERGY_PUBLIC_SERIES = {
    "Natural Gas Price": {
        "series_id": "WHHNGSP",
        "display_name": "Henry Hub Natural Gas",
        "unit": "$/MMBtu",
        "frequency": "weekly",
        "change_months": None,
        "change_days": 28,
        "source": "FRED / EIA",
    },
    "WTI Crude Oil": {
        "series_id": "WCOILWTICO",
        "display_name": "WTI Crude Oil",
        "unit": "$/bbl",
        "frequency": "weekly",
        "change_months": None,
        "change_days": 28,
        "source": "FRED / EIA",
    },
    "Coal Production": {
        "series_id": "IPN2121S",
        "display_name": "Coal Production",
        "unit": "index",
        "frequency": "monthly",
        "change_months": 3,
        "change_days": None,
        "source": "FRED",
    },
    "Renewable Power Output": {
        "series_id": "IPN221114T8S",
        "display_name": "Renewable Power Output",
        "unit": "index",
        "frequency": "monthly",
        "change_months": 3,
        "change_days": None,
        "source": "FRED",
    },
}

ENERGY_RETAIL_PRICE_SERIES = {
    "Commercial Electricity Price": {
        "display_name": "Commercial Electricity Price",
        "unit": "¢/kWh",
        "frequency": "monthly",
        "change_months": 12,
        "change_days": None,
        "source": "EIA Electric Power Monthly",
        "table_column": "Commercial",
    },
    "Industrial Electricity Price": {
        "display_name": "Industrial Electricity Price",
        "unit": "¢/kWh",
        "frequency": "monthly",
        "change_months": 12,
        "change_days": None,
        "source": "EIA Electric Power Monthly",
        "table_column": "Industrial",
    },
}

ENERGY_POWER_SERIES = {
    "Electric Power Output": {
        "fred_name": "Electric Power Output",
        "history_column": "Electric Power Output",
        "display_name": "Electric Power Output",
        "unit": "index",
        "frequency": "monthly",
        "change_months": 12,
        "change_days": None,
        "source": "FRED",
    },
    "Electric Power Capacity": {
        "fred_name": "Electric Power Capacity",
        "history_column": "Electric Power Capacity",
        "display_name": "Sustainable Potential Output",
        "unit": "index",
        "frequency": "monthly",
        "change_months": 12,
        "change_days": None,
        "source": "FRED",
    },
    "Electric Power Utilization": {
        "fred_name": "Electric Power Capacity Utilization",
        "history_column": "Electric Power Capacity Utilization",
        "display_name": "Electric Power Utilization",
        "unit": "%",
        "frequency": "monthly",
        "change_months": 12,
        "change_days": None,
        "source": "FRED",
    },
}

ENERGY_REFRESH_SERIES = {**ENERGY_PUBLIC_SERIES, **ENERGY_RETAIL_PRICE_SERIES}
ENERGY_SERIES = {**ENERGY_REFRESH_SERIES, **ENERGY_POWER_SERIES}

ENERGY_FRED_CSV_URL = (
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
    + ",".join(item["series_id"] for item in ENERGY_PUBLIC_SERIES.values())
    + "&cosd=2015-01-01"
)
ENERGY_RETAIL_PRICE_XLSX_URL = (
    "https://www.eia.gov/electricity/monthly/xls/table_5_03.xlsx"
)

ENERGY_WEEKLY_CUTOFF_WEEKDAY = 4
ENERGY_WEEKLY_CUTOFF_HOUR = 16
