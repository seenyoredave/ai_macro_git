from copy import deepcopy


def get_sector_config():
    return deepcopy(SECTOR_CONFIG)


SECTOR_CONFIG = {

    "COMPUTE": {
        "basket": [
            "NVDA", "AMD", "AVGO", "MRVL", "ARM",
            "QCOM", "MU", "TSM", "INTC", "TXN",
            "ADI", "NXPI", "ON", "MCHP", "MPWR",
            "LSCC", "ALAB", "GFS"
        ],
        "ai_exposure_score": {
            "NVDA": 5,
            "AMD": 5,
            "AVGO": 5,
            "MRVL": 4,
            "ARM": 4,
            "QCOM": 3,
            "MU": 4,
            "TSM": 4,
            "INTC": 3,
            "TXN": 2,
            "ADI": 2,
            "NXPI": 2,
            "ON": 2,
            "MCHP": 2,
            "MPWR": 3,
            "LSCC": 3,
            "ALAB": 4,
            "GFS": 3,
        }
    },

    "SEMICAP_EQUIPMENT": {
        "basket": [
            "ASML", "AMAT", "LRCX", "KLAC", "TER",
            "ONTO", "ACLS", "COHU", "AEIS", "MKSI",
            "ICHR", "UCTT", "FORM", "VECO", "CAMT",
            "KLIC", "ENTG", "AMKR"
        ],
        "ai_exposure_score": {
            "ASML": 5,
            "AMAT": 5,
            "LRCX": 5,
            "KLAC": 5,
            "TER": 4,
            "ONTO": 4,
            "ACLS": 3,
            "COHU": 3,
            "AEIS": 3,
            "MKSI": 3,
            "ICHR": 3,
            "UCTT": 3,
            "FORM": 3,
            "VECO": 3,
            "CAMT": 4,
            "KLIC": 3,
            "ENTG": 4,
            "AMKR": 4,
        }
    },

    "CLOUD_HYPERSCALERS": {
        "basket": [
            "MSFT", "AMZN", "GOOG", "META", "ORCL",
            "IBM", "BABA", "TCEHY"
        ],
        "ai_exposure_score": {
            "MSFT": 5,
            "AMZN": 5,
            "GOOG": 5,
            "META": 4,
            "ORCL": 4,
            "IBM": 3,
            "BABA": 3,
            "TCEHY": 3,
        }
    },

    "DATA_AI_INFRASTRUCTURE": {
        "basket": [
            "SNOW", "DDOG", "MDB", "NET", "AKAM",
            "DOCN", "FSLY", "TWLO", "NTNX"
        ],
        "ai_exposure_score": {
            "SNOW": 5,
            "DDOG": 4,
            "MDB": 5,
            "NET": 4,
            "AKAM": 3,
            "DOCN": 3,
            "FSLY": 2,
            "TWLO": 3,
            "NTNX": 4,
        }
    },

    "DATA_CENTER_INFRASTRUCTURE": {
        "basket": [
            "VRT", "EQIX", "DLR", "ANET", "CSCO",
            "HPE", "DELL", "NTAP", "WDC", "STX",
            "SMCI", "P", "CIEN", "APLD", "IREN",
            "CORZ", "COHR"
        ],
        "ai_exposure_score": {
            "VRT": 5,
            "EQIX": 5,
            "DLR": 5,
            "ANET": 5,
            "CSCO": 3,
            "HPE": 4,
            "DELL": 4,
            "NTAP": 3,
            "WDC": 3,
            "STX": 3,
            "SMCI": 5,
            "P": 4,
            "CIEN": 4,
            "APLD": 4,
            "IREN": 4,
            "CORZ": 4,
            "COHR": 4,
        }
    },

    "POWER_GRID": {
        "basket": [
            "CEG", "VST", "TLN", "NEE", "DUK",
            "SO", "AEP", "ETR", "PWR", "ETN",
            "GEV", "NRG", "GNRC", "EME", "HUBB",
            "AYI", "BEPC", "FLNC"
        ],
        "ai_exposure_score": {
            "CEG": 5,
            "VST": 5,
            "TLN": 4,
            "NEE": 3,
            "DUK": 3,
            "SO": 3,
            "AEP": 3,
            "ETR": 4,
            "PWR": 5,
            "ETN": 5,
            "GEV": 5,
            "NRG": 3,
            "GNRC": 3,
            "EME": 4,
            "HUBB": 4,
            "AYI": 3,
            "BEPC": 3,
            "FLNC": 4,
        }
    },

    "ENTERPRISE_AI_SOFTWARE": {
        "basket": [
            "CRM", "NOW", "ADBE", "SAP",
            "TEAM", "HUBS", "DOCU", "ADSK",
            "WDAY", "INTU", "PATH", "AI"
        ],
        "ai_exposure_score": {
            "CRM": 4,
            "NOW": 5,
            "ADBE": 4,
            "SAP": 3,
            "TEAM": 3,
            "HUBS": 3,
            "DOCU": 2,
            "ADSK": 3,
            "WDAY": 3,
            "INTU": 4,
            "PATH": 4,
            "AI": 5,
        }
    },

    "CYBERSECURITY_AI_TRUST": {
        "basket": [
            "CRWD", "PANW", "ZS", "FTNT", "OKTA",
            "S", "TENB", "RPD", "QLYS", "VRNS",
            "CHKP", "SAIL", "RDWR", "RBRK", "OSPN"
        ],
        "ai_exposure_score": {
            "CRWD": 5,
            "PANW": 5,
            "ZS": 5,
            "FTNT": 4,
            "OKTA": 4,
            "S": 4,
            "TENB": 3,
            "RPD": 3,
            "QLYS": 3,
            "VRNS": 3,
            "CHKP": 3,
            "SAIL": 4,
            "RDWR": 2,
            "RBRK": 4,
            "OSPN": 2,
        }
    },

    "INDUSTRIAL_AUTOMATION": {
        "basket": [
            "ROK", "ABBNY", "FANUY", "OMRNY", "CGNX",
            "ZBRA", "SYM"
        ],
        "ai_exposure_score": {
            "ROK": 5,
            "ABBNY": 5,
            "FANUY": 5,
            "OMRNY": 5,
            "CGNX": 4,
            "ZBRA": 3,
            "SYM": 5,
        }
    },

    "ROBOTICS": {
        "basket": [
            "AVAV", "KTOS", "DE", "TXT", "HSAI",
            "SERV", "RR", "ISRG", "MDT"
        ],
        "ai_exposure_score": {
            "AVAV": 5,
            "KTOS": 5,
            "DE": 4,
            "TXT": 3,
            "HSAI": 4,
            "SERV": 5,
            "RR": 5,
            "ISRG": 5,
            "MDT": 3,
        }
    },

    "DEFENSE_NATIONAL_SECURITY": {
        "basket": [
            "PLTR", "LMT", "RTX", "NOC", "GD",
            "BA", "LDOS", "CACI", "HII", "MRCY",
            "BWXT", "RCAT", "LHX",
            "SAIC", "TDY"
        ],
        "ai_exposure_score": {
            "PLTR": 5,
            "LMT": 4,
            "RTX": 4,
            "NOC": 4,
            "GD": 3,
            "BA": 3,
            "LDOS": 4,
            "CACI": 4,
            "HII": 2,
            "MRCY": 4,
            "BWXT": 3,
            "RCAT": 5,
            "LHX": 4,
            "SAIC": 3,
            "TDY": 3,
        }
    },

    "CONSUMER_AI": {
        "basket": [
            "AAPL",
            "DUOL",
            "SPOT",
            "SNAP",
            "PINS",
            "RDDT",
            "MTCH",
            "APP",
            "SOUN",
            "SHOP",
            "ETSY",
            "EBAY"
        ],
        "ai_exposure_score": {
            "AAPL": 4,
            "DUOL": 5,
            "SPOT": 3,
            "SNAP": 4,
            "PINS": 4,
            "RDDT": 4,
            "MTCH": 3,
            "APP": 4,
            "SOUN": 5,
            "SHOP": 4,
            "ETSY": 3,
            "EBAY": 3,
        }
    }
}