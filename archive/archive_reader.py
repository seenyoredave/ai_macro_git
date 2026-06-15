import pandas as pd 

def load_benchmark_history():
    return pd.read_csv(
        "archive/benchmark_history.csv"
    )
    
def load_edgar_history():
    return pd.read_csv(
        "archive/edgar_history.csv"
    )    
    
def load_fred_history():
    return pd.read_csv(
        "archive/fred_history.csv"
    )    
    
def load_macro_history():
    return pd.read_csv(
        "archive/macro_history.csv"
    )    
    
def load_put_call_history():
    return pd.read_csv(
        "archive/put_call_history.csv"
    )    
    
def load_sector_history():
    return pd.read_csv(
        "archive/sector_history.csv"
    )    
    
def load_yf_history():
    return pd.read_csv(
        "archive/yf_history.csv"
    )  