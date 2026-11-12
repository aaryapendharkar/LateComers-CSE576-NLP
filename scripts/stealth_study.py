#!/usr/bin/env python
"""Person 3 (Vatsal): build the stealth pilot (40 images + answer key) and analyse responses.

    python scripts/stealth_study.py build      # -> report/stealth/ images + key.csv (key stays private!)
    python scripts/stealth_study.py analyze --responses responses.csv
"""
import _bootstrap  # noqa: F401
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "analyze"])
    ap.add_argument("--responses")
    ap.parse_args()
    raise NotImplementedError("Person 3: src/analysis/stealth.py")


if __name__ == "__main__":
    main()
