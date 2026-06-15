

import numpy as np 
import pandas as pd 

from config.debug_config import debug_print


def build_macro_dataframe(sector_metrics):

        rows = []

        for sector, metrics in sector_metrics.items():

            rows.append({

                "Sector": sector,

                "Cycle Score": metrics.get("Cycle Score", np.nan),

                "Heat": metrics.get("Sector Heat", np.nan),

                "Avg Return": metrics.get("Avg Return", np.nan),

                "Forward P/E": metrics.get("Forward P/E", np.nan),

                "Beta": metrics.get("Beta", np.nan)
            })
            
        macro_df = pd.DataFrame(rows)

        debug_print("\n=== MACRO DATAFRAME ===")
        debug_print(macro_df)

        return macro_df

        return pd.DataFrame(rows)
    

