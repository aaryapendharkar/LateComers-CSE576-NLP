#!/usr/bin/env python
"""Person 3 (Vatsal): score the filled-in question-type review sheet (the 30-label check).

    python scripts/qtype_review_score.py --sheet results/qtypes/manual_review_sheet.csv

Uses only the rows with sample_type=random_agreement_sample (the seeded random
30). Rows the rules flagged themselves (flagged_only) are listed but kept out of
the agreement estimate, because they are not a random sample. Reports raw
agreement and Cohen's kappa between the rule label and the reviewer label, and
lists every disagreement. Writes results/qtypes/review_agreement.json.
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

LABELS = ("lookup", "comparison", "arithmetic", "trend")


def cohen_kappa(a: list[str], b: list[str]) -> float:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[l] * cb[l] for l in set(a) | set(b)) / (n * n)
    return float("nan") if pe == 1 else (po - pe) / (1 - pe)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sheet", type=Path, default=Path("results/qtypes/manual_review_sheet.csv"))
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    with open(args.sheet, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    sample = [r for r in rows if r["sample_type"] == "random_agreement_sample"]
    todo = [r["qid"] for r in sample if not r["reviewer_label"].strip()]
    if todo:
        raise SystemExit(f"{len(todo)} of {len(sample)} sampled rows have no reviewer_label yet: {todo}")
    bad = [(r["qid"], r["reviewer_label"]) for r in sample if r["reviewer_label"].strip().lower() not in LABELS]
    if bad:
        raise SystemExit(f"reviewer_label must be one of {LABELS}; got {bad}")
    rule = [r["proposed_question_type"] for r in sample]
    human = [r["reviewer_label"].strip().lower() for r in sample]
    agree = sum(x == y for x, y in zip(rule, human))
    result = {
        "n_reviewed": len(sample), "n_agree": agree, "raw_agreement": agree / len(sample),
        "cohen_kappa": cohen_kappa(rule, human),
        "reviewers": sorted({r["reviewer_initials"].strip() for r in sample if r["reviewer_initials"].strip()}),
        "rule_label_counts": dict(Counter(rule)), "reviewer_label_counts": dict(Counter(human)),
        "disagreements": [{"qid": r["qid"], "rule": r["proposed_question_type"], "reviewer": h,
                           "question": r["question"], "comment": r["reviewer_comment"]}
                          for r, h in zip(sample, human) if r["proposed_question_type"] != h],
        "flagged_only_rows_reviewed": sum(1 for r in rows if r["sample_type"] == "flagged_only" and r["reviewer_label"].strip()),
    }
    out = args.out or args.sheet.with_name("review_agreement.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
