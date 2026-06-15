import numpy as np

#from config.edgar_indicators import edgar_indicators


def load_edgar(tickers):

    edgar_data = {}

    for ticker in tickers.keys():

        try:

            edgar_data[ticker] = {

                "Revenue": np.nan,
                "Revenue Growth": np.nan,
                "Market Cap": np.nan

            }

            # later:
            # SEC filing logic

        except Exception:

            edgar_data[ticker] = {}

    return edgar_data