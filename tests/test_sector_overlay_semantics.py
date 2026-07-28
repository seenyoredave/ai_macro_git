import pandas as pd

from research_overlay.tables import _company_table
from research_overlay.visuals import sector_factor_chart


def test_company_table_converts_large_dollar_values_to_millions():
    frame = pd.DataFrame({
        "Ticker": ["A"],
        "Company": ["Alpha"],
        "1Y Return": [0.1234],
        "Market Cap": [2_500_000_000],
        "Revenue": [345_600_000],
        "Revenue Growth": [0.0765],
        "CapEx": [12_300_000],
        "CapEx Growth": [0.101],
        "Beta": [1.234],
    })
    table = _company_table(frame)
    assert table.loc[0, "Market Cap ($M)"] == 2500.0
    assert table.loc[0, "Revenue ($M)"] == 345.6
    assert table.loc[0, "CapEx ($M)"] == 12.3
    assert table.loc[0, "1Y Return (%)"] == 12.34


def test_factor_chart_preserves_hundredths_for_floor_scores():
    frame = pd.DataFrame({
        "Factor": ["1Y Relative Return"],
        "Score": [0.0847],
        "Raw Value": [-1.0613],
    })
    fig = sector_factor_chart(frame)
    assert fig.data[0].text[0] == "0.08"
    assert fig.data[0].customdata[0][0] == "-106.13 pp"
