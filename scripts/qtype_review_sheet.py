"""Person 3 (Vatsal): propose question-type labels and build a manual-review sheet.

    python scripts/qtype_review_sheet.py --examples data/examples.jsonl --out-dir results/qtypes
    python scripts/qtype_review_sheet.py --examples tests/fixtures/synthetic/qtype_examples.jsonl \
        --out-dir results/synthetic/qtypes --synthetic

Reads only qid/source/question/program. Writes:
  proposed_labels.jsonl   one proposal per question (never edits examples.jsonl)
  manual_review_sheet.csv a seeded random sample for the agreement check
                          (sample_type=random_agreement_sample) plus every other
                          rule-flagged item (sample_type=flagged_only, excluded
                          from the agreement estimate). Reviewer columns are blank.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.qtypes import QTYPES_VERSION, as_record, propose  # noqa: E402

SHEET_COLUMNS = ["qid", "source", "sample_type", "question", "program", "proposed_question_type", "rule",
                 "also_matched", "rule_flagged_for_review", "review_notes",
                 "reviewer_label", "reviewer_initials", "agrees_with_proposal", "reviewer_comment"]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--examples", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--review-sample", type=int, default=30)
    p.add_argument("--seed", type=int, default=576)
    p.add_argument("--synthetic", action="store_true", help="label outputs as synthetic demonstrations")
    args = p.parse_args(argv)

    examples = [json.loads(l) for l in args.examples.read_text().splitlines() if l.strip()]
    if args.examples.resolve().name == "examples.jsonl" and args.out_dir.resolve() == args.examples.resolve().parent:
        raise SystemExit("refusing to write next to the shared examples.jsonl; choose a results/ directory")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    proposals = []
    for ex in examples:
        prop = propose(ex["qid"], ex.get("question", ""), ex.get("program"))
        rec = as_record(prop, ex.get("source"))
        rec["data_label"] = "SYNTHETIC" if args.synthetic else "REAL"
        rec["manually_validated"] = False
        proposals.append((ex, rec))

    with (args.out_dir / "proposed_labels.jsonl").open("w") as f:
        for _, rec in proposals:
            f.write(json.dumps(rec) + "\n")

    rng = random.Random(args.seed)
    sample_idx = set(rng.sample(range(len(proposals)), min(args.review_sample, len(proposals))))
    with (args.out_dir / "manual_review_sheet.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SHEET_COLUMNS)
        w.writeheader()
        for i, (ex, rec) in enumerate(proposals):
            if i not in sample_idx and not rec["needs_review"]:
                continue
            w.writerow({
                "qid": rec["qid"], "source": rec["source"],
                "sample_type": "random_agreement_sample" if i in sample_idx else "flagged_only",
                "question": ex.get("question", ""), "program": ex.get("program") or "",
                "proposed_question_type": rec["proposed_question_type"], "rule": rec["rule"],
                "also_matched": ";".join(rec["also_matched"]),
                "rule_flagged_for_review": rec["needs_review"], "review_notes": " | ".join(rec["review_notes"]),
                "reviewer_label": "", "reviewer_initials": "", "agrees_with_proposal": "", "reviewer_comment": "",
            })

    summary = {
        "data_label": "SYNTHETIC demonstration of the format" if args.synthetic else "REAL questions (proposals only)",
        "manually_validated": False,
        "labeler_version": QTYPES_VERSION,
        "examples_path": str(args.examples),
        "n_questions": len(proposals),
        "label_counts": dict(Counter(r["proposed_question_type"] for _, r in proposals)),
        "n_rule_flagged_for_review": sum(r["needs_review"] for _, r in proposals),
        "review_sample_size": len(sample_idx),
        "seed": args.seed,
    }
    (args.out_dir / "qtypes_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
