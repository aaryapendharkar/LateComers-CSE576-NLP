#!/usr/bin/env python
"""Person 5 (Disha): checker false-positive rate on 100 clean pages + detection per G2 condition.

Writes results/gap2/checker_flags.jsonl ({"page_id", "flag", "mismatches"}) for
scripts/run_attacks.py --drop-flags, and results/gap2/checker_table.md.

    python scripts/eval_img_text_check.py --oracle            # dry run, no GPU (perfect image reader)
    python scripts/eval_img_text_check.py --n-clean 5         # first real check on 5 clean pages (GPU)
    python scripts/eval_img_text_check.py                     # full run (resumable)

Then the filter run (ASR with the checker):
    python scripts/run_attacks.py --pipeline P3 --gap G2 --drop-flags results/gap2/checker_flags.jsonl --run-name G2_checker
"""
import _bootstrap  # noqa: F401
import argparse

from src.common.config import get_config
from src.common.metrics import fmt_rate
from src.defenses.img_text_check import evaluate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-clean", type=int, default=None, help="clean pages per source (default: config, 100)")
    ap.add_argument("--oracle", action="store_true",
                    help="perfect image reader (dry run / upper bound; writes *_oracle files)")
    ap.add_argument("--out-dir", default="results/gap2")
    ap.add_argument("--overwrite", action="store_true", help="start over instead of resuming")
    args = ap.parse_args()

    rows = evaluate(get_config(), n_clean=args.n_clean, oracle=args.oracle,
                    out_dir=args.out_dir, overwrite=args.overwrite)
    for r in rows:
        print(f"{r['kind']:18s} {r['metric']:20s} {fmt_rate(r)}  errors={r['errors']}")
    print(f"wrote {args.out_dir}/checker_table{'_oracle' if args.oracle else ''}.md")


if __name__ == "__main__":
    main()
