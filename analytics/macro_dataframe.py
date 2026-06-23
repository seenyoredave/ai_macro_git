

import numpy as np 
import pandas as pd 

from archive.archive_reader import load_macro_history

from analytics.trend_engine import calc_metric_trend
from analytics.regime_engine import build_regime_metrics

from config.debug_config import debug_print
from config.debug_config import DEBUG


def build_macro_dataframe(sector_metrics):

        rows = []

        for sector, metrics in sector_metrics.items():

            rows.append({

                "Sector": sector,

                "Sector Score": metrics.get("Sector Score", np.nan),

                "Pressure": metrics.get("Sector Pressure", np.nan),

                "Avg Return": metrics.get("Avg Return", np.nan),

                "Forward P/E": metrics.get("Forward P/E", np.nan),

                "Beta": metrics.get("Beta", np.nan)
            })
            
        macro_df = pd.DataFrame(rows)

        if DEBUG: 
            debug_print("\n=== MACRO DATAFRAME ===")
            debug_print(macro_df)

        return macro_df
    
def build_macro_dashboard_data(sector_metrics, sector_data=None):
    """
    Build macro dashboard data products.

    This function prepares macro-level data for rendering.
    It does not render anything.
    """

    macro_df = build_macro_dataframe(sector_metrics)

    macro_history = load_macro_history()

    regime_metrics = build_regime_metrics(
        sector_metrics=sector_metrics,
        sector_data=sector_data,
    )
    
    trends = {
        "cycle_trend": calc_metric_trend(
            macro_history,
            "Maturation Index"
        ),
        "divergence_trend": calc_metric_trend(
            macro_history,
            "Divergence"
        ),
        "power_stress_trend": calc_metric_trend(
            macro_history,
            "Power Stress Index"
        ),
        "concentration_trend": calc_metric_trend(
            macro_history,
            "Concentration HHI"
        ),
    }

    return {
        "macro_df": macro_df,
        "macro_history": macro_history,
        "trends": trends,
        "regime_metrics": regime_metrics,
    }

    

