#!/usr/bin/env python
"""Person 4 (Aaron): Gap 2 rows -> data/attacks/g2.jsonl + data/manifests/pages_g2.jsonl.

Tables: 3 conditions on Person 2's consistent_cell attacks (data/attacks/g1.jsonl).
Charts: 3 conditions per selected ChartQA question.
"""
import _bootstrap  # noqa: F401
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["table", "chart", "both"], default="both")
    ap.add_argument("--limit", type=int)
    ap.parse_args()
    raise NotImplementedError("Person 4: loop over conflict.make_table_conditions / charts.make_chart_conditions")


if __name__ == "__main__":
    main()
