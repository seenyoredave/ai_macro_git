#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analytics.data_center_metrics import rollup_campus_metric  # noqa: E402


def main() -> int:
    facts = pd.DataFrame([
        {"Campus ID":"campus:x","Entity ID":"campus:x","Entity Level":"campus","Metric":"Planned Data Center Capacity MW","Value":100,"Measurement Scope":"campus","Aggregation Method":"direct_total","Evidence Grade":"B"},
        {"Campus ID":"campus:x","Entity ID":"building:1","Entity Level":"building","Parent Entity ID":"campus:x","Metric":"Planned Data Center Capacity MW","Value":18,"Measurement Scope":"building","Aggregation Method":"sum"},
        {"Campus ID":"campus:x","Entity ID":"building:2","Entity Level":"building","Parent Entity ID":"campus:x","Metric":"Planned Data Center Capacity MW","Value":21,"Measurement Scope":"building","Aggregation Method":"sum"},
    ])
    direct = rollup_campus_metric(facts, campus_id="campus:x", metric="Planned Data Center Capacity MW")
    assert direct["Value"] == 100 and direct["Aggregation Method"] == "direct_total"

    member_only = facts.loc[~facts["Entity Level"].eq("campus")]
    rolled = rollup_campus_metric(member_only, campus_id="campus:x", metric="Planned Data Center Capacity MW")
    assert rolled["Value"] == 39
    print("PASS  metric grain · campus direct total supersedes members · member-only sum = 39 MW")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
