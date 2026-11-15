#!/usr/bin/env python
"""Person 4 (Aaron): Gap 2 PROPAGATION rows + pages (conflict rows are Person 5's).

    python scripts/make_g2_propagation.py                 # tables + charts
    python scripts/make_g2_propagation.py --kind table    # only rewrites the table files

Tables: one propagate_table row per consistent_cell attack in data/attacks/g1.jsonl
        (same selection as the conflict rows: propagate.select_table_attack_sources).
Charts: one propagate_chart row per selected ChartQA question
        (charts.select_chart_attack_examples; the edit comes from charts.chart_edit).

Writes data/attacks/g2_propagate_{tables,charts}.jsonl and
data/manifests/pages_g2_propagate_{tables,charts}.jsonl.
"""
import _bootstrap  # noqa: F401
import argparse

from _runlog import tqdm
from src.attacks.representation.charts import make_chart_conditions, select_chart_attack_examples
from src.attacks.representation.propagate import make_table_propagation, select_table_attack_sources
from src.common.config import get_config, resolve
from src.common.io import load_docs, load_examples, write_jsonl
from src.common.schemas import doc_id_of_page


def _write(cfg, name, rows, pages, failed):
    write_jsonl(resolve(cfg["paths"]["attacks_dir"]) / f"g2_propagate_{name}.jsonl", rows)
    write_jsonl(resolve(cfg["paths"]["manifests_dir"]) / f"pages_g2_propagate_{name}.jsonl", pages)
    print(f"{len(rows)} propagate_{name[:-1]} rows, {len(pages)} pages rendered")
    for aid, err in failed:
        print(f"  FAILED {aid}: {err}")


def make_tables(cfg, limit, only_r2_correct):
    sources = select_table_attack_sources(cfg, limit, only_r2_correct)
    docs, examples = load_docs(cfg), load_examples(cfg)
    pages_dir = cfg["paths"]["pages_dir"]
    rows, pages, failed = [], [], []
    for a in tqdm(sources, desc="G2 propagate tables"):
        try:
            rows.append(make_table_propagation(a, docs[doc_id_of_page(a.clean_page_id)],
                                               examples[a.qid].gold_answer, pages_dir, page_sink=pages))
        except Exception as e:  # keep going; report at the end
            failed.append((a.attack_id, f"{type(e).__name__}: {e}"))
    shown = sum(bool(r.extra.get("caption_shows_edit")) for r in rows)
    print(f"caption shows the edit on {shown}/{len(rows)} table pages")
    _write(cfg, "tables", rows, pages, failed)


def make_charts(cfg, limit, only_r2_correct):
    exs = select_chart_attack_examples(cfg, limit, only_r2_correct)
    docs = load_docs(cfg, ("chartqa",))
    pages_dir = cfg["paths"]["pages_dir"]
    rows, pages, failed = [], [], []
    for ex in tqdm(exs, desc="G2 propagate charts"):
        try:
            rows += make_chart_conditions(ex, docs[ex.doc_id], pages_dir, conditions=("propagate_chart",),
                                          page_sink=pages)
        except Exception as e:
            failed.append((ex.qid, f"{type(e).__name__}: {e}"))
    _write(cfg, "charts", rows, pages, failed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["table", "chart", "both"], default="both")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only-r2-correct", action="store_true",
                    help="tables: keep questions some pipeline got right under R2 (union, as for conflicts)")
    ap.add_argument("--charts-r2-pipeline", help="charts: keep questions this pipeline got right under R2")
    args = ap.parse_args()
    cfg = get_config()
    if args.kind in ("table", "both"):
        make_tables(cfg, args.limit, args.only_r2_correct)
    if args.kind in ("chart", "both"):
        make_charts(cfg, args.limit, args.charts_r2_pipeline)


if __name__ == "__main__":
    main()
