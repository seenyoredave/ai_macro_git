import pandas as pd

from research_overlay.visuals import (
    component_bars,
    current_gap_bars,
    single_history,
)


def _assert_no_title(fig):
    layout = fig.to_plotly_json().get("layout", {})
    assert "title" not in layout


def test_titleless_overlay_figures_omit_plotly_title_property():
    history = pd.DataFrame(
        {"Date": pd.to_datetime(["2025-01-01", "2026-01-01"]), "Value": [-1.0, 1.0]}
    )
    _assert_no_title(single_history(history))
    _assert_no_title(current_gap_bars({"A": -10, "B": 20}))
    _assert_no_title(component_bars({"A": {"score": 10}, "B": {"score": -20}}, signed=True))


def test_sector_scatter_points_use_hover_only_labels_and_cross_linked_colorbars():
    from research_overlay.visuals import earnings_support_map, speculative_load_matrix

    frame = pd.DataFrame(
        {
            "Sector": ["COMPUTE", "SECURITY"],
            "Sector Score": [75.0, 55.0],
            "Pressure": [40.0, 70.0],
            "Avg Return": [0.25, -0.10],
            "Forward EV/EBIT": [20.0, 76.25],
            "Loss-Making EV Share": [0.10, 0.36],
        }
    )
    support = earnings_support_map(frame)
    load = speculative_load_matrix(frame)
    assert support.data[0].mode == "markers"
    assert load.data[0].mode == "markers"
    assert support.data[0].marker.colorbar.title.text == "AEI"
    assert load.data[0].marker.colorbar.title.text == "FWD EV/EBIT"
    assert load.data[0].marker.cmin == 0.0
    assert load.data[0].marker.cmax == 1.0
    assert not getattr(load.layout, "annotations", [])
    assert "<b>%{customdata[0]}</b>" in support.data[0].hovertemplate
    assert "<b>%{customdata[0]}</b>" in load.data[0].hovertemplate
    assert support.data[0].customdata[0][1] == "20.00x"
    assert support.data[0].customdata[0][2] == "+25.00%"
    assert support.data[0].customdata[0][4].endswith(" bp")
    assert load.data[0].customdata[0][1] == "0.53x"
    assert load.data[0].customdata[0][2] == "+25.00%"
    assert load.data[0].customdata[0][3] == "20.00x"
    assert float(support.data[0].marker.size[1]) > float(support.data[0].marker.size[0])
    assert float(load.data[0].marker.size[1]) > float(load.data[0].marker.size[0])


def test_forward_ev_ebit_display_normalization_contains_extreme_profitable_multiple():
    from research_overlay.visuals import earnings_support_map, speculative_load_matrix

    frame = pd.DataFrame(
        {
            "Sector": ["COMPUTE", "SECURITY", "DATA_AI_INFRASTRUCTURE"],
            "Sector Score": [75.0, 55.0, 42.0],
            "Pressure": [40.0, 70.0, 61.0],
            "Avg Return": [0.25, -0.10, 0.08],
            "Forward EV/EBIT": [20.0, 76.25, 5000.0],
            "Loss-Making EV Share": [0.10, 0.36, 0.72],
        }
    )

    support = earnings_support_map(frame)
    load = speculative_load_matrix(frame)

    assert max(float(value) for value in support.data[0].x) == 5000.0
    assert min(float(value) for value in support.data[0].x) == 20.0
    assert list(support.layout.xaxis.range) == [0.0, 5400.0]
    assert max(float(value) for value in load.data[0].marker.color) <= 1.0
    assert min(float(value) for value in load.data[0].marker.color) >= 0.0
    assert support.data[0].customdata[2][2] == "+8.00%"
    assert load.data[0].customdata[2][3] == "5000.00x"



def test_finance_history_plots_use_ten_year_moving_windows_when_requested():
    from research_overlay.visuals import funding_history, single_history

    dates = pd.to_datetime(["2010-01-01", "2015-01-01", "2025-01-01"])
    single = single_history(
        pd.DataFrame({"Date": dates, "Value": [1.0, 2.0, 3.0]}),
        years=10,
    )
    assert list(pd.to_datetime(single.data[0].x)) == list(pd.to_datetime(["2015-01-01", "2025-01-01"]))

    funding = funding_history(
        pd.DataFrame(
            {
                "Date": dates,
                "Internal Funding Coverage": [0.5, 0.8, 1.1],
            }
        ),
        years=10,
    )
    assert list(pd.to_datetime(funding.data[0].x)) == list(pd.to_datetime(["2015-01-01", "2025-01-01"]))
    assert funding.layout.showlegend is False
