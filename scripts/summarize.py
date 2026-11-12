#!/usr/bin/env python
"""Step 9b (Person 1, Sat): stage funnel per pipeline x attack_type, with 95% CIs.

    python scripts/summarize.py --runs results/runs/P1_G1.jsonl results/runs/P2_G1.jsonl
    python scripts/summarize.py --runs results/runs/*_G2.jsonl --out results/gap2/funnel.csv

Columns: retrieved@20 -> top5 -> cited -> attack_success (all over R2-correct
questions of that pipeline), plus ASR and evidence adoption.
"""
import _bootstrap  # noqa: F401
import argparse
import csv

from src.common import metrics as M
from src.common.config import get_config, resolve
from src.common.io import load_attacks, load_r2_correct, read_jsonl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--out", default="results/funnel.csv")
    args = ap.parse_args()
    cfg = get_config()
    kw = {"n_resamples": cfg["metrics"]["bootstrap_resamples"], "seed": cfg["seed"]}
    attacks = load_attacks(cfg)
    try:
        r2 = load_r2_correct(cfg)
    except FileNotFoundError:
        print("WARNING: no r2_correct.json -> rates over ALL attacked questions")
        r2 = {}

    recs = []
    for p in args.runs:
        for r in read_jsonl(p):
            if r.get("attack_id"):
                r["attack_type"] = attacks[r["attack_id"]].attack_type if r["attack_id"] in attacks else "?"
                recs.append(r)

    rows = []
    for (pl, rr, at), group in sorted(M.group_by(recs, "pipeline", "reranker", "attack_type").items()):
        keep = r2.get(pl)
        f = M.stage_funnel(group, keep, **kw)
        adopt = M.rate(M.evidence_adoption_flags([g for g in group if keep is None or g["qid"] in keep]), **kw)
        row = {"pipeline": pl, "reranker": rr, "attack_type": at}
        for stage, v in f.items():
            row[stage] = M.fmt_rate(v)
        row["adoption|top5"] = M.fmt_rate(adopt)
        rows.append(row)

    out = resolve(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["pipeline"])
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(r)
    print(f"-> {out}")


if __name__ == "__main__":
    main()
