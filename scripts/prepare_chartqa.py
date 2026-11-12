#!/usr/bin/env python
"""Person 4 (Aaron): ChartQA corpus -> data/chart_docs.jsonl + data/chart_examples.jsonl (Fri night).

100 human-written test questions whose answer is one value in the chart CSV
(simple bar/line charts) + 200 distractor charts = 300-page corpus.
Docs use the A6 format with source="chartqa" and the CSV as the table.
"""
import _bootstrap  # noqa: F401
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chartqa-dir", required=True, help="clone of github.com/vis-nlp/ChartQA")
    ap.parse_args()
    raise NotImplementedError("Person 4: build chart docs/examples (see src/attacks/representation/charts.py)")


if __name__ == "__main__":
    main()
