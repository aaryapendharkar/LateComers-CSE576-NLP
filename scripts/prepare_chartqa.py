#!/usr/bin/env python
"""Person 4 (Aaron): ChartQA corpus -> data/chart_docs.jsonl + data/chart_examples.jsonl.

    git clone --filter=blob:none --sparse https://github.com/vis-nlp/ChartQA.git data/raw/ChartQA
    git -C data/raw/ChartQA sparse-checkout set --no-cone "/ChartQA Dataset/test/"
    python scripts/prepare_chartqa.py --chartqa-dir data/raw/ChartQA

100 human-written test questions whose answer is one value in the chart CSV
(simple 1-3 series bar/line charts; filters in src/attacks/representation/charts.py)
+ 200 distractor charts from the rest of the test split = 300-page corpus.
Docs use the A6 format with source="chartqa" and the CSV as the table.
"""
import _bootstrap  # noqa: F401
import argparse
import json

from src.attacks.representation.charts import select_chartqa_questions, select_distractor_docs
from src.common.config import get_config
from src.common.io import write_jsonl


def main():
    cfg = get_config()
    cq = (cfg.get("data") or {}).get("chartqa") or {}
    ap = argparse.ArgumentParser()
    ap.add_argument("--chartqa-dir", default="data/raw/ChartQA", help="clone of github.com/vis-nlp/ChartQA")
    ap.add_argument("--n-questions", type=int, default=cq.get("n_questions", 100))
    ap.add_argument("--n-corpus", type=int, default=cq.get("n_corpus", 300))
    ap.add_argument("--seed", type=int, default=cfg.get("seed", 576))
    args = ap.parse_args()

    examples, docs, stats = select_chartqa_questions(args.n_questions, args.chartqa_dir, seed=args.seed,
                                                     return_docs=True)
    distractors = select_distractor_docs(args.n_corpus - len(docs), {d.doc_id for d in docs},
                                         args.chartqa_dir, seed=args.seed)
    all_docs = sorted(docs + distractors, key=lambda d: d.doc_id)
    write_jsonl(cfg["paths"]["chart_docs"], all_docs)
    write_jsonl(cfg["paths"]["chart_examples"], examples)
    print(json.dumps(stats))
    print(f"{len(examples)} questions -> {cfg['paths']['chart_examples']}; "
          f"{len(all_docs)} chart docs ({len(docs)} answer charts + {len(distractors)} distractors) "
          f"-> {cfg['paths']['chart_docs']}")


if __name__ == "__main__":
    main()
