import pandas as pd

from helpers.dataframe_display import arrow_safe_dataframe

def test_mixed_object_columns_become_text():
    frame = pd.DataFrame(
        {
            "Required Universe": [4, "company cohort", "commitment ledger"],
            "Nested": [{"a": 1}, ["x", "y"], None],
        }
    )

    safe = arrow_safe_dataframe(frame)

    assert str(safe["Required Universe"].dtype) == "string"
    assert safe["Required Universe"].tolist() == ["4", "company cohort", "commitment ledger"]
    assert str(safe["Nested"].dtype) == "string"
    assert safe["Nested"].iloc[0] == '{"a": 1}'
    assert safe["Nested"].iloc[1] == "x, y"


def test_numeric_object_columns_remain_numeric():
    frame = pd.DataFrame({"Count": pd.Series([1, 2, None], dtype="object")})
    safe = arrow_safe_dataframe(frame)
    assert str(safe["Count"].dtype) == "Int64"

