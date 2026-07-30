"""Corporate-bond market source contract."""

from __future__ import annotations


DEBT_MARKETS_DATA_VERSION = "1.0"
DEBT_MARKETS_SOURCE_URL = (
    "https://www.newyorkfed.org/medialibrary/research/interactives/"
    "cmdi/downloads/Market%20CMDI.xlsx"
)
DEBT_MARKETS_SOURCE_PAGE = "https://www.newyorkfed.org/research/policy/cmdi"
DEBT_MARKETS_REQUEST_TIMEOUT = 25

DEBT_MARKET_SERIES = {
    "Corporate Bond Market Distress": {
        "source_column": "Market CMDI",
        "display_name": "Corporate Bond Market Distress",
        "short_name": "Market CMDI",
    },
    "Investment-Grade Bond Distress": {
        "source_column": "IG CMDI",
        "display_name": "Investment-Grade Bond Distress",
        "short_name": "IG CMDI",
    },
    "High-Yield Bond Distress": {
        "source_column": "HY CMDI",
        "display_name": "High-Yield Bond Distress",
        "short_name": "HY CMDI",
    },
}
