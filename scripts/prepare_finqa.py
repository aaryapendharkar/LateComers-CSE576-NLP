#!/usr/bin/env python
"""Step 1 (Person 1, Thu noon): sample 500 FinQA docs + 200 questions.

    python scripts/prepare_finqa.py --inspect            # print real column names first!
    python scripts/prepare_finqa.py                      # writes data/docs.jsonl, data/examples.jsonl
    python scripts/prepare_finqa.py --finqa-json data/raw/FinQA/dataset/test.json data/raw/FinQA/dataset/dev.json \
        --distractor-split dev     # test split has < 500 docs -> fill the corpus from dev

Then tell Person 2 whether programs are present (printed at the end).
"""
import _bootstrap  # noqa: F401
import argparse
import json

from src.common.config import load_config
from src.common.io import write_jsonl
from src.data.finqa import build, inspect_rows, load_finqa_json, load_rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inspect", action="store_true", help="print columns + one row and exit")
    ap.add_argument("--local-jsonl", help="read rows from a downloaded JSONL instead of the HF hub")
    ap.add_argument("--finqa-json", nargs="+", help="original FinQA JSON(s) (test.json [dev.json ...]) to join programs/tables")
    ap.add_argument("--distractor-split", help="extra split (e.g. dev or train) used ONLY to fill the corpus to n_docs")
    ap.add_argument("--distractor-jsonl", help="local JSONL for the distractor split")
    args = ap.parse_args()

    cfg = load_config()
    dc = cfg["data"]["finqa"]
    rows = load_rows(dc["hf_dataset"], dc.get("hf_config"), dc["split"], args.local_jsonl)
    if args.inspect:
        print(inspect_rows(rows))
        print("\nNow check configs/default.yaml -> data.finqa.fields matches these names.")
        return

    finqa = {}
    for p in args.finqa_json or []:
        finqa.update(load_finqa_json(p))
    extra = None
    if args.distractor_split or args.distractor_jsonl:
        extra = load_rows(dc["hf_dataset"], dc.get("hf_config"), args.distractor_split, args.distractor_jsonl)
    docs, examples, stats = build(rows, dc["fields"], dc["n_docs"], dc["n_questions"], cfg["seed"],
                                  finqa or None, extra)
    write_jsonl(cfg["paths"]["docs"], docs)
    write_jsonl(cfg["paths"]["examples"], examples)
    print(json.dumps(stats, indent=2))
    n = max(1, stats["n_examples"])
    print(f"\nPrograms present for {stats['with_program']}/{stats['n_examples']} "
          f"({100 * stats['with_program'] / n:.0f}%) questions  <- tell Person 2")


if __name__ == "__main__":
    main()
