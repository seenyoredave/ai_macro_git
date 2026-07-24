import pandas as pd

from analytics.deployment_funding_mix import calculate_deployment_funding_mix


def test_deployment_funding_mix_uses_orthogonal_funding_ratios():
    today = pd.Timestamp.today().normalize()
    prior_year = today - pd.DateOffset(years=1)
    two_years_prior = today - pd.DateOffset(years=2)

    sector_data = {
        "Software": pd.DataFrame(
            {
                "Ticker": ["MSFT", "AMZN"],
                "Operating Cash Flow": [120.0, 80.0],
                "CapEx": [100.0, 60.0],
                "Cash": [90.0, 30.0],
                "Total Debt": [50.0, 40.0],
            }
        )
    }
    commitments_df = pd.DataFrame(
        {
            "Ticker": ["MSFT", "AMZN"],
            "As Of Date": [prior_year, prior_year],
            "Filing Date": [prior_year + pd.Timedelta(days=30)] * 2,
            "Uncommenced Leases": [20.0, 10.0],
            "Purchase or Contractual Commitments": [30.0, 10.0],
            "Contingent Exposure": [0.0, 0.0],
            "Source URL": ["", ""],
            "Notes": ["", ""],
        }
    )
    fundamentals_history = pd.DataFrame(
        {
            "Date": [two_years_prior, two_years_prior, prior_year, prior_year],
            "Ticker": ["MSFT", "AMZN", "MSFT", "AMZN"],
            "Operating Cash Flow": [90.0, 60.0, 100.0, 70.0],
            "CapEx": [80.0, 40.0, 90.0, 50.0],
            "Cash": [70.0, 20.0, 80.0, 20.0],
            "Total Debt": [30.0, 25.0, 40.0, 30.0],
        }
    )
    commitments_history = pd.DataFrame(
        {
            "Ticker": ["MSFT", "AMZN"],
            "As Of Date": [two_years_prior, two_years_prior],
            "Filing Date": [two_years_prior + pd.Timedelta(days=30)] * 2,
            "Uncommenced Leases": [15.0, 5.0],
            "Purchase or Contractual Commitments": [25.0, 15.0],
        }
    )

    result = calculate_deployment_funding_mix(
        sector_data,
        commitments_df=commitments_df,
        fundamentals_history=fundamentals_history,
        commitments_history=commitments_history,
    )

    current = result["current"]
    assert round(current["internal_funding_coverage"], 4) == 1.25
    assert round(current["cash_reserve_coverage_years"], 4) == 0.75
    assert round(current["debt_financing_pulse"], 4) == 0.125
    assert round(current["forward_commitment_load"], 4) == 0.4375

    history = result["history"]
    prior_row = history.loc[history["Date"] == prior_year].iloc[0]
    assert round(prior_row["Debt Financing Pulse"], 4) == 0.1071
    assert round(prior_row["Forward Commitment Load"], 4) == 0.4286

    assert set(result["series"].keys()) == {
        "internal_funding_coverage",
        "cash_reserve_coverage_years",
        "debt_financing_pulse",
        "forward_commitment_load",
    }
