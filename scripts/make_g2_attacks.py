#!/usr/bin/env python
import _bootstrap  # noqa: F401
import argparse

from _runlog import tqdm
from src.attacks.representation.charts import make_chart_conditions, select_chart_attack_examples
from src.attacks.representation.conflict import CHART_CONFLICTS, make_table_conditions
from src.attacks.representation.propagate import select_table_attack_sources
from src.common.config import get_config, resolve
from src.common.io import load_docs, load_examples, write_jsonl
from src.common.schemas import doc_id_of_page


def _write(cfg, name, rows, pages, failed):
    write_jsonl(resolve(cfg["paths"]["attacks_dir"]) / f"g2_conflict_{name}.jsonl", rows)
    write_jsonl(resolve(cfg["paths"]["manifests_dir"]) / f"pages_g2_conflict_{name}.jsonl", pages)
    print(f"{len(rows)} conflict {name} rows ({len(rows) // 2} questions x 2), {len(pages)} pages rendered")
    for key, err in failed:
        print(f"  FAILED {key}: {err}")


def make_tables(cfg, limit, only_r2_correct):
    sources = select_table_attack_sources(cfg, limit, only_r2_correct)
    docs, examples = load_docs(cfg), load_examples(cfg)
    pages_dir = cfg["paths"]["pages_dir"]
    rows, pages, failed = [], [], []
    for a in tqdm(sources, desc="G2 conflict tables"):
        try:
            rows += make_table_conditions(a, docs[doc_id_of_page(a.clean_page_id)],
                                          examples[a.qid].gold_answer, pages_dir, page_sink=pages)
        except Exception as e:
            failed.append((a.attack_id, f"{type(e).__name__}: {e}"))
    _write(cfg, "tables", rows, pages, failed)


def make_charts(cfg, limit, r2_pipeline):
    exs = select_chart_attack_examples(cfg, limit, r2_pipeline)
    docs = load_docs(cfg, ("chartqa",))
    pages_dir = cfg["paths"]["pages_dir"]
    rows, pages, failed = [], [], []
    for ex in tqdm(exs, desc="G2 conflict charts"):
        try:
            rows += make_chart_conditions(ex, docs[ex.doc_id], pages_dir, conditions=CHART_CONFLICTS,
                                          page_sink=pages)
        except Exception as e:
            failed.append((ex.qid, f"{type(e).__name__}: {e}"))
    _write(cfg, "charts", rows, pages, failed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["table", "chart", "both"], default="both")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only-r2-correct", action="store_true", help="tables: same selection as propagation")
    ap.add_argument("--charts-r2-pipeline", help="charts: keep questions this pipeline got right under R2")
    args = ap.parse_args()
    cfg = get_config()
    if args.kind in ("table", "both"):
        make_tables(cfg, args.limit, args.only_r2_correct)
    if args.kind in ("chart", "both"):
        make_charts(cfg, args.limit, args.charts_r2_pipeline)


if __name__ == "__main__":
    main()
