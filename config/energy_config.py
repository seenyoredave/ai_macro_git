"""Configuration for the weekly Energy tab and its source series."""

from __future__ import annotations


ENERGY_DATA_VERSION = "1.1"

# The Energy refresh fetches only the four series that are not already owned by
# the application's primary FRED loader. Power output, capacity, and utilization
# are reused from the existing FRED payload and power-series history.
ENERGY_PUBLIC_SERIES = {
    "Natural Gas Price": {
        "series_id": "WHHNGSP",
        "display_name": "Henry Hub Natural Gas",
        "unit": "$/MMBtu",
        "frequency": "weekly",
        "change_months": None,
        "change_days": 28,
    },
    "WTI Crude Oil": {
        "series_id": "WCOILWTICO",
        "display_name": "WTI Crude Oil",
        "unit": "$/bbl",
        "frequency": "weekly",
        "change_months": None,
        "change_days": 28,
    },
    "Coal Production": {
        "series_id": "IPN2121S",
        "display_name": "Coal Production",
        "unit": "index",
        "frequency": "monthly",
        "change_months": 3,
        "change_days": None,
    },
    "Renewable Power Output": {
        "series_id": "IPN221114T8S",
        "display_name": "Renewable Power Output",
        "unit": "index",
        "frequency": "monthly",
        "change_months": 3,
        "change_days": None,
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
    },
    "Electric Power Capacity": {
        "fred_name": "Electric Power Capacity",
        "history_column": "Electric Power Capacity",
        "display_name": "Electric Power Capacity",
        "unit": "index",
        "frequency": "monthly",
        "change_months": 12,
        "change_days": None,
    },
    "Electric Power Utilization": {
        "fred_name": "Electric Power Capacity Utilization",
        "history_column": "Electric Power Capacity Utilization",
        "display_name": "Electric Power Utilization",
        "unit": "%",
        "frequency": "monthly",
        "change_months": 12,
        "change_days": None,
    },
}

ENERGY_SERIES = {**ENERGY_PUBLIC_SERIES, **ENERGY_POWER_SERIES}

ENERGY_FRED_CSV_URL = (
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
    + ",".join(item["series_id"] for item in ENERGY_PUBLIC_SERIES.values())
    + "&cosd=2015-01-01"
)

# The weekly refresh date advances after Friday's regular U.S. market close.
# Before that cutoff, the prior Friday remains the current completed week.
# Manual Refresh Energy always bypasses this policy.
ENERGY_WEEKLY_CUTOFF_WEEKDAY = 4  # Friday
ENERGY_WEEKLY_CUTOFF_HOUR = 16
