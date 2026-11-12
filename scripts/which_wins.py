#!/usr/bin/env python
"""Person 5 (Disha): which-version-wins table from Gap 2 run logs -> results/gap2/which_wins.md

    python scripts/which_wins.py --runs results/runs/P1_G2.jsonl results/runs/P2_G2.jsonl
"""
import _bootstrap  # noqa: F401
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True)
    ap.parse_args()
    raise NotImplementedError("Person 5: src/analysis/which_wins.py")


if __name__ == "__main__":
    main()
