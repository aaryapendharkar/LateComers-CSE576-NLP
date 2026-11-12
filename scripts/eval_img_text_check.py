#!/usr/bin/env python
"""Person 5 (Disha): checker false-positive rate on 100 clean pages + detection per G2 condition.

Writes results/gap2/checker_flags.jsonl ({"page_id", "flag", "mismatches"}) for
scripts/run_attacks.py --drop-flags, and results/gap2/checker_table.md.
"""
import _bootstrap  # noqa: F401
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-clean", type=int, default=100)
    ap.parse_args()
    raise NotImplementedError("Person 5: run check_page over clean + G2 pages")


if __name__ == "__main__":
    main()
