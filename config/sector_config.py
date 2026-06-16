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
        ]
    },

    "SEMICAP_EQUIPMENT": {
        "basket": [
            "ASML", "AMAT", "LRCX", "KLAC", "TER",
            "ONTO", "ACLS", "COHU", "AEIS", "MKSI",
            "ICHR", "UCTT", "FORM", "VECO", "CAMT",
            "KLIC", "ENTG", "AMKR"
        ]
    },

    "CLOUD_HYPERSCALERS": {
        "basket": [
            "MSFT", "AMZN", "GOOG", "META", "ORCL",
            "IBM", "BABA", "TCEHY", "SAP", "CRM",
            "SNOW", "DDOG", "NET", "AKAM", "MDB",
            "DOCN", "FSLY", "TWLO"
        ]
    },

    "DATA_CENTER_INFRASTRUCTURE": {
        "basket": [
            "VRT", "EQIX", "DLR", "ANET", "CSCO",
            "HPE", "DELL", "NTAP", "WDC", "STX",
            "SMCI", "P", "CIEN", "APLD", "IREN",
            "CORZ", "NTNX", "COHR"
        ]
    },

    "POWER_GRID": {
        "basket": [
            "CEG", "VST", "TLN", "NEE", "DUK",
            "SO", "AEP", "ETR", "PWR", "ETN",
            "GEV", "NRG", "GNRC", "EME", "HUBB",
            "AYI", "BEPC", "FLNC"
        ]
    },

    "ENTERPRISE_AI_SOFTWARE": {
        "basket": [
            "CRM", "NOW", "SNOW", "PLTR", "ADBE",
            "SAP", "DDOG", "MDB", "TEAM", "HUBS",
            "DOCU", "ADSK", "WDAY", "INTU", "ORCL",
            "PATH", "AI", "APP"
        ]
    },

    "AI_SECURITY": {
        "basket": [
            "CRWD", "PANW", "ZS", "FTNT", "OKTA",
            "NET", "S", "TENB", "RPD", "QLYS",
            "VRNS", "CHKP", "GEN", "SAIL", "RDWR",
            "CYBR", "RBRK", "OSPN"
        ]
    },

    "PHYSICAL_AI_ROBOTICS": {
        "basket": [
            "ISRG", "SYM", "ROK", "ABBNY", "TER",
            "PATH", "AVAV", "KTOS", "DE", "TXT",
            "CGNX", "ZBRA", "HSAI", "MDT", "SERV",
            "RR", "FANUY", "OMRNY"
        ]
    },

    "DEFENSE_NATIONAL_SECURITY": {
        "basket": [
            "PLTR", "LMT", "RTX", "NOC", "GD",
            "BA", "LDOS", "CACI", "HII", "MRCY",
            "BWXT", "RCAT", "AVAV", "KTOS", "LHX",
            "SAIC", "TXT", "TDY"
        ]
    }
}