#!/usr/bin/env python
import _bootstrap  # noqa: F401
import argparse
import csv

from src.analysis.which_wins import (LABELS, label_runs, rank_shift_by_condition, rank_shift_markdown,
                                     to_markdown, which_wins_table)
from src.common.config import get_config, resolve
from src.common.io import load_attacks, load_r2_correct, read_jsonl, write_jsonl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True, help="Gap 2 attack run logs")
    ap.add_argument("--clean-runs", nargs="*", default=[], help="clean R2 run logs, for the rank-shift table")
    ap.add_argument("--only-r2-correct", action="store_true")
    ap.add_argument("--out-dir", default="results/gap2")
    args = ap.parse_args()

    cfg = get_config()
    tol = cfg.get("metrics", {}).get("rel_tol", 0.01)
    attacks = load_attacks(cfg, gap="G2")
    records = [r for p in args.runs for r in read_jsonl(resolve(p))]
    r2 = load_r2_correct(cfg) if args.only_r2_correct else None

    out = resolve(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    rows = which_wins_table(records, attacks, r2_correct=r2, rel_tol=tol)
    if not rows:
        raise SystemExit("no Gap 2 runs found in --runs")
    md = to_markdown(rows)
    (out / "which_wins.md").write_text(md + "\n", encoding="utf-8")
    with open(out / "which_wins.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pipeline", "reranker", "attack_type", "n"]
                   + [f"follows_{lab}{s}" for lab in LABELS for s in ("", "_ci_low", "_ci_high")])
        for r in rows:
            w.writerow([r["pipeline"], r["reranker"], r["attack_type"], r["n"]]
                       + [r[f"follows_{lab}"][k] for lab in LABELS for k in ("rate", "ci_low", "ci_high")])
    write_jsonl(out / "which_wins_labels.jsonl", label_runs(records, attacks, rel_tol=tol))
    print(md)

    if args.clean_runs:
        clean = [r for p in args.clean_runs for r in read_jsonl(resolve(p)) if r.get("attack_id") is None]
        shift_md = rank_shift_markdown(rank_shift_by_condition(records, clean, attacks))
        (out / "rank_shift.md").write_text(shift_md + "\n", encoding="utf-8")
        print("\nRank shift:\n" + shift_md)
    print(f"\nwrote {out}/which_wins.md, which_wins.csv, which_wins_labels.jsonl")


if __name__ == "__main__":
    main()
