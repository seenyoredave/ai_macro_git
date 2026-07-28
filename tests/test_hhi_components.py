import pandas as pd

from analytics.hhi_engine import hhi_component_breakdown


def test_hhi_breakdown_is_additive_and_groups_the_remainder():
    sector_data = {
        "A": pd.DataFrame({
            "Ticker": ["AAA", "BBB", "CCC", "DDD"],
            "Market Cap": [50.0, 30.0, 15.0, 5.0],
        })
    }
    result = hhi_component_breakdown(sector_data, top_n=2)
    assert result["Company"].tolist() == ["AAA", "BBB", "Other"]
    assert result["HHI Contribution Share"].sum() == pytest.approx(100.0)
    assert result["Market Cap Share"].sum() == pytest.approx(1.0)


import pytest
