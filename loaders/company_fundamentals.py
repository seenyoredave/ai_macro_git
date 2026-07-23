"""Company fundamental extraction for the market data pipeline.

This module owns statement parsing and company-level financial calculations.
It intentionally has no archive, Streamlit, or orchestration responsibilities.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


CAPEX_ROW_NAMES = [
    "Capital Expenditure",
    "Capital Expenditures",
    "CapitalExpenditures",
    "Capital Expenditure Reported",
    "Purchase Of Property Plant Equipment",
    "Purchase Of PPE",
    "Purchase of Property Plant and Equipment",
]


def safe_float(value):
    try:
        if value is None or pd.isna(value):
            return np.nan
        return float(value)
    except Exception:
        return np.nan


def get_statement_row(statement_df, possible_names):
    if statement_df is None or statement_df.empty:
        return None

    index_lookup = {str(idx).lower().strip(): idx for idx in statement_df.index}

    for name in possible_names:
        key = name.lower().strip()
        if key in index_lookup:
            return statement_df.loc[index_lookup[key]]

    return None


def _statement(ticker_obj, attr):
    try:
        value = getattr(ticker_obj, attr)
    except Exception:
        return pd.DataFrame()
    return value if isinstance(value, pd.DataFrame) else pd.DataFrame()


def calc_capex_metrics(ticker_obj):
    """Return absolute latest CapEx and comparable growth as decimals."""
    quarterly = _statement(ticker_obj, "quarterly_cashflow")
    row = get_statement_row(quarterly, CAPEX_ROW_NAMES)

    if row is not None:
        values = pd.to_numeric(row, errors="coerce").dropna()
        if len(values) >= 8:
            current = abs(float(values.iloc[:4].sum()))
            prior = abs(float(values.iloc[4:8].sum()))
            return current, (current / prior) - 1 if prior > 0 else np.nan

    annual = _statement(ticker_obj, "cashflow")
    row = get_statement_row(annual, CAPEX_ROW_NAMES)

    if row is not None:
        values = pd.to_numeric(row, errors="coerce").dropna()
        if len(values) >= 2:
            current = abs(float(values.iloc[0]))
            prior = abs(float(values.iloc[1]))
            return current, (current / prior) - 1 if prior > 0 else np.nan

    return np.nan, np.nan


def calc_revenue_growth(ticker_obj, info):
    direct = safe_float((info or {}).get("revenueGrowth"))
    if pd.notna(direct):
        return direct

    row = get_statement_row(
        _statement(ticker_obj, "quarterly_income_stmt"),
        ["Total Revenue", "Operating Revenue", "Revenue"],
    )
    if row is None:
        return np.nan

    values = pd.to_numeric(row, errors="coerce").dropna()
    if len(values) < 8:
        return np.nan

    current = float(values.iloc[:4].sum())
    prior = float(values.iloc[4:8].sum())
    return (current / prior) - 1 if prior != 0 else np.nan


def _safe_info_number(info, *keys):
    info = info or {}
    for key in keys:
        value = safe_float(info.get(key))
        if pd.notna(value):
            return value
    return np.nan


def _latest_statement_value(ticker_obj, statement_attrs, row_names, *, ttm=False):
    for attr in statement_attrs:
        row = get_statement_row(_statement(ticker_obj, attr), row_names)
        if row is None:
            continue

        values = pd.to_numeric(row, errors="coerce").dropna()
        if values.empty:
            continue

        if ttm and attr.startswith("quarterly") and len(values) >= 4:
            return float(values.iloc[:4].sum())
        return float(values.iloc[0])

    return np.nan


def _statement_flow_pair(ticker_obj, statement_attrs, row_names):
    """Return current and prior comparable flow values.

    Quarterly data uses current TTM versus prior TTM when eight quarters exist.
    Annual data is the explicit fallback because Yahoo often exposes only five
    standardized quarters.
    """
    for attr in statement_attrs:
        row = get_statement_row(_statement(ticker_obj, attr), row_names)
        if row is None:
            continue

        values = pd.to_numeric(row, errors="coerce").dropna()
        if attr.startswith("quarterly") and len(values) >= 8:
            return float(values.iloc[:4].sum()), float(values.iloc[4:8].sum())
        if not attr.startswith("quarterly") and len(values) >= 2:
            return float(values.iloc[0]), float(values.iloc[1])

    return np.nan, np.nan


def _statement_point_pair(ticker_obj, statement_attrs, row_names):
    for attr in statement_attrs:
        row = get_statement_row(_statement(ticker_obj, attr), row_names)
        if row is None:
            continue

        values = pd.to_numeric(row, errors="coerce").dropna()
        if attr.startswith("quarterly") and len(values) >= 5:
            return float(values.iloc[0]), float(values.iloc[4])
        if not attr.startswith("quarterly") and len(values) >= 2:
            return float(values.iloc[0]), float(values.iloc[1])

    return np.nan, np.nan


def _safe_ratio(numerator, denominator):
    numerator = safe_float(numerator)
    denominator = safe_float(denominator)
    if pd.isna(numerator) or pd.isna(denominator) or denominator <= 0:
        return np.nan
    return numerator / denominator


def calc_financial_deterioration_fields(ticker_obj):
    """Calculate latest-fiscal-year versus prior-fiscal-year changes."""
    revenue_current, revenue_prior = _statement_flow_pair(
        ticker_obj,
        ["income_stmt"],
        ["Total Revenue", "Operating Revenue", "Revenue"],
    )
    ocf_current, ocf_prior = _statement_flow_pair(
        ticker_obj,
        ["cashflow"],
        [
            "Operating Cash Flow",
            "Total Cash From Operating Activities",
            "Net Cash Provided By Operating Activities",
            "Cash Flow From Continuing Operating Activities",
        ],
    )
    capex_current, capex_prior = _statement_flow_pair(
        ticker_obj,
        ["cashflow"],
        CAPEX_ROW_NAMES,
    )
    fcf_current, fcf_prior = _statement_flow_pair(
        ticker_obj,
        ["cashflow"],
        ["Free Cash Flow", "FreeCashFlow"],
    )
    ebitda_current, ebitda_prior = _statement_flow_pair(
        ticker_obj,
        ["income_stmt"],
        ["EBITDA", "Normalized EBITDA"],
    )
    debt_current, debt_prior = _statement_point_pair(
        ticker_obj,
        ["balance_sheet"],
        [
            "Total Debt",
            "TotalDebt",
            "Long Term Debt And Capital Lease Obligation",
            "Long Term Debt",
        ],
    )
    cash_current, cash_prior = _statement_point_pair(
        ticker_obj,
        ["balance_sheet"],
        [
            "Cash And Cash Equivalents",
            "Cash Cash Equivalents And Short Term Investments",
            "Cash Equivalents",
        ],
    )

    capex_current = abs(capex_current) if pd.notna(capex_current) else np.nan
    capex_prior = abs(capex_prior) if pd.notna(capex_prior) else np.nan

    if pd.isna(fcf_current) and pd.notna(ocf_current) and pd.notna(capex_current):
        fcf_current = ocf_current - capex_current
    if pd.isna(fcf_prior) and pd.notna(ocf_prior) and pd.notna(capex_prior):
        fcf_prior = ocf_prior - capex_prior

    net_debt_current = (
        debt_current - cash_current
        if pd.notna(debt_current) and pd.notna(cash_current)
        else np.nan
    )
    net_debt_prior = (
        debt_prior - cash_prior
        if pd.notna(debt_prior) and pd.notna(cash_prior)
        else np.nan
    )

    fcf_margin_current = _safe_ratio(fcf_current, revenue_current)
    fcf_margin_prior = _safe_ratio(fcf_prior, revenue_prior)
    leverage_current = _safe_ratio(net_debt_current, ebitda_current)
    leverage_prior = _safe_ratio(net_debt_prior, ebitda_prior)
    reinvestment_current = _safe_ratio(capex_current, ocf_current)
    reinvestment_prior = _safe_ratio(capex_prior, ocf_prior)

    return {
        "FCF Margin YoY Change": (
            fcf_margin_current - fcf_margin_prior
            if pd.notna(fcf_margin_current) and pd.notna(fcf_margin_prior)
            else np.nan
        ),
        "Net Debt / EBITDA YoY Change": (
            leverage_current - leverage_prior
            if pd.notna(leverage_current) and pd.notna(leverage_prior)
            else np.nan
        ),
        "CapEx / OCF YoY Change": (
            reinvestment_current - reinvestment_prior
            if pd.notna(reinvestment_current) and pd.notna(reinvestment_prior)
            else np.nan
        ),
    }


def calc_financial_strain_fields(ticker_obj, info, capex_value=np.nan):
    info = info or {}

    operating_cash_flow = _safe_info_number(info, "operatingCashflow", "operating_cashflow")
    if pd.isna(operating_cash_flow):
        operating_cash_flow = _latest_statement_value(
            ticker_obj,
            ["quarterly_cashflow", "cashflow"],
            [
                "Operating Cash Flow",
                "Total Cash From Operating Activities",
                "Net Cash Provided By Operating Activities",
                "Cash Flow From Continuing Operating Activities",
            ],
            ttm=True,
        )

    free_cash_flow = _safe_info_number(info, "freeCashflow", "free_cashflow")
    if pd.isna(free_cash_flow):
        free_cash_flow = _latest_statement_value(
            ticker_obj,
            ["quarterly_cashflow", "cashflow"],
            ["Free Cash Flow", "FreeCashFlow"],
            ttm=True,
        )
    if pd.isna(free_cash_flow) and pd.notna(operating_cash_flow) and pd.notna(capex_value):
        free_cash_flow = operating_cash_flow - abs(float(capex_value))

    net_income = _safe_info_number(info, "netIncomeToCommon", "netIncome")
    if pd.isna(net_income):
        net_income = _latest_statement_value(
            ticker_obj,
            ["quarterly_income_stmt", "income_stmt"],
            ["Net Income", "Net Income Common Stockholders"],
            ttm=True,
        )

    ebitda = _safe_info_number(info, "ebitda")
    if pd.isna(ebitda):
        ebitda = _latest_statement_value(
            ticker_obj,
            ["quarterly_income_stmt", "income_stmt"],
            ["EBITDA", "Normalized EBITDA"],
            ttm=True,
        )

    total_debt = _safe_info_number(info, "totalDebt")
    if pd.isna(total_debt):
        total_debt = _latest_statement_value(
            ticker_obj,
            ["balance_sheet", "quarterly_balance_sheet"],
            [
                "Total Debt",
                "TotalDebt",
                "Long Term Debt And Capital Lease Obligation",
                "Long Term Debt",
            ],
        )

    cash = _safe_info_number(info, "totalCash")
    if pd.isna(cash):
        cash = _latest_statement_value(
            ticker_obj,
            ["balance_sheet", "quarterly_balance_sheet"],
            [
                "Cash And Cash Equivalents",
                "Cash Cash Equivalents And Short Term Investments",
                "Cash Equivalents",
            ],
        )

    net_debt = total_debt - cash if pd.notna(total_debt) and pd.notna(cash) else np.nan

    return {
        "Operating Cash Flow": operating_cash_flow,
        "Free Cash Flow": free_cash_flow,
        "Net Income": net_income,
        "EBITDA": ebitda,
        "Total Debt": total_debt,
        "Cash": cash,
        "Net Debt": net_debt,
        **calc_financial_deterioration_fields(ticker_obj),
    }


def extract_fundamental_fields(ticker_obj, info):
    """Return the complete fundamental payload consumed by market_loader."""
    capex, capex_growth = calc_capex_metrics(ticker_obj)
    return {
        "Revenue Growth": calc_revenue_growth(ticker_obj, info),
        "CapEx": capex,
        "CapEx Growth": capex_growth,
        **calc_financial_strain_fields(ticker_obj, info, capex_value=capex),
    }
