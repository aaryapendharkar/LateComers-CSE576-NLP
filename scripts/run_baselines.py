#!/usr/bin/env python
"""Step 4 (Person 1, Fri): clean baselines R1 / R2 / R3 + results/r2_correct.json.

    python scripts/run_baselines.py --pipelines P1 P2 --limit 5      # smoke test first
    python scripts/run_baselines.py --pipelines P1 P2 [P3] [--no-reranker]
    python scripts/run_baselines.py --source chartqa --pipelines P1 P2

Writes results/runs/<P>_<R1|R2|R3>[_norerank]_<source>.jsonl (resumable), then
results/r2_correct.json and results/baselines/table1_<source>.md.
"""
import _bootstrap  # noqa: F401
import argparse
import json



from _runlog import done_keys, log, run_path, tqdm
from src.common import metrics as M
from src.common.config import get_config, resolve
from src.common.io import read_jsonl, write_jsonl
from src.pipelines.run import get_system

MODES = {"R1": "closed_book", "R2": "rag", "R3": "oracle"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipelines", nargs="+", default=["P1", "P2"], choices=["P1", "P2", "P3"])
    ap.add_argument("--runs", nargs="+", default=["R1", "R2", "R3"], choices=list(MODES))
    ap.add_argument("--source", default="finqa", choices=["finqa", "chartqa"])
    ap.add_argument("--no-reranker", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    cfg = get_config()
    sys_ = get_system()
    qids = sorted(q for q, e in sys_.examples.items() if e.source == args.source)[: args.limit]
    rr = not args.no_reranker
    suffix = ("" if rr else "_norerank") + f"_{args.source}"
    table_rows, r2_correct = [], {}
    kw = {"n_resamples": cfg["metrics"]["bootstrap_resamples"], "seed": cfg["seed"]}

    for pl in args.pipelines:
        row = {"pipeline": pl}
        for run in args.runs:
            if run == "R1" and pl != args.pipelines[0]:
                continue  # closed-book does not depend on the pipeline: run once
            path = run_path(cfg, pl, run + suffix)
            done = done_keys(path)
            for q in tqdm([q for q in qids if (q, None) not in done], desc=f"{pl} {run}"):
                log(path, sys_.run_query(q, pl, rr, mode=MODES[run], run_name=run + suffix))
            recs = [r for r in read_jsonl(path) if r["qid"] in set(qids)]
            row[run] = M.fmt_rate(M.rate(M.accuracy_flags(recs), **kw))
            if run == "R2":
                row["Recall@5"] = M.fmt_rate(M.rate(M.recall_flags(recs, 5, "rerank"), **kw))
                row["Recall@20"] = M.fmt_rate(M.rate(M.recall_flags(recs, 20, "retr"), **kw))
                r2_correct[pl] = sorted(r["qid"] for r in recs if r["correct"])
        table_rows.append(row)

    if r2_correct:
        p = resolve(cfg["paths"]["r2_correct"])
        old = json.loads(p.read_text()) if p.exists() else {}
        old.update({f"{k}" if args.source == "finqa" else f"{k}_{args.source}": v for k, v in r2_correct.items()})
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(old, indent=1))
        print(f"wrote {p}  ->  send to Persons 2 and 4")

    cols = ["pipeline", "R1", "R2", "R3", "Recall@5", "Recall@20"]
    md = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    md += ["| " + " | ".join(r.get(c, "") for c in cols) + " |" for r in table_rows]
    out = resolve(cfg["paths"]["baselines_dir"]) / f"table1{suffix}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
