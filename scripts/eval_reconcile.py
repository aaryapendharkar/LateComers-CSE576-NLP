#!/usr/bin/env python
"""Person 3 (Vatsal): D1 false-positive rate on clean pages + detection per edit type.

Writes results/gap1/d1_flags.jsonl ({"page_id", "flag", "reasons"}) -- this file
is what scripts/run_attacks.py --drop-flags consumes -- and results/gap1/d1_table.md.
"""
import _bootstrap  # noqa: F401
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text-source", default="docling", choices=["docling", "pdfplumber", "standin"])
    ap.parse_args()
    raise NotImplementedError("Person 3: run reconcile_page over clean + G1 poisoned pages")


if __name__ == "__main__":
    main()
