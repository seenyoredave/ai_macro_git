import sys
import types

import pandas as pd


streamlit = types.ModuleType("streamlit")
streamlit.cache_data = lambda *args, **kwargs: (lambda func: func)
streamlit.secrets = {}
sys.modules.setdefault("streamlit", streamlit)

fredapi = types.ModuleType("fredapi")
fredapi.Fred = object
sys.modules.setdefault("fredapi", fredapi)

from loaders.nfci_loader import _normalize_nfci_history


def test_nfci_loader_normalizes_nfci_and_anfci_together():
    raw = pd.DataFrame({
        "observation_date": ["2026-01-02", "2026-01-09"],
        "NFCI": ["-0.50", "-0.45"],
        "ANFCI": ["-0.20", "-0.15"],
    })
    clean = _normalize_nfci_history(raw)
    assert list(clean.columns) == ["Date", "Value", "ANFCI"]
    assert clean["Value"].tolist() == [-0.50, -0.45]
    assert clean["ANFCI"].tolist() == [-0.20, -0.15]
