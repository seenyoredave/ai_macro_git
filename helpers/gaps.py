### These functions feed the gap tools that seek to merge the FRED data 
### of consumer sentiment, fed funds, and industrial production with market data
### to create a more robust picture of the direction of the AI sector 

import pandas as pd
import numpy as np

from helpers.macro_normalization import (
    normalize_fed_funds,
    normalize_industrial_production
)


def gap_score(investor_sentiment,consumer_sentiment):

    if pd.isna(investor_sentiment):
        return np.nan

    if pd.isna(consumer_sentiment):
        return np.nan

    return investor_sentiment - consumer_sentiment
    
def liquidity_gap(ai_temp, fed_funds):

    if pd.isna(ai_temp):
        return np.nan

    if pd.isna(fed_funds):
        return np.nan

    liquidity_score = normalize_fed_funds(fed_funds)


    return ai_temp - liquidity_score

def adoption_gap(ai_temp, industrial_production):

    if pd.isna(ai_temp):
        return np.nan

    if pd.isna(industrial_production):
        return np.nan

    economy_score = normalize_industrial_production(industrial_production)


    return ai_temp - economy_score
