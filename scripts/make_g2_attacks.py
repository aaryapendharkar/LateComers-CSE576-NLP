#!/usr/bin/env python
import _bootstrap  # noqa: F401
import argparse

from _runlog import tqdm
from src.attacks.representation.conflict import make_table_conditions
from src.common.config import get_config, resolve
from src.common.io import load_attacks, load_docs, load_examples, load_r2_correct, write_jsonl
from src.common.schemas import doc_id_of_page


def make_tables(cfg, limit, only_r2_correct):
    g1 = sorted((a for a in load_attacks(cfg, gap="G1").values() if a.attack_type == "consistent_cell"),
                key=lambda a: a.attack_id)
    if only_r2_correct:
        r2 = load_r2_correct(cfg)
        keep = set().union(*r2.values()) if r2 else set()
        g1 = [a for a in g1 if a.qid in keep]
    g1 = g1[: limit or cfg.get("attacks_g2", {}).get("n_table_questions", 50)]
    docs, examples = load_docs(cfg), load_examples(cfg)
    pages_dir = str(resolve(cfg["paths"]["pages_dir"]))
    rows, pages, failed = [], [], []
    for a in tqdm(g1, desc="G2 tables"):
        try:
            rows += make_table_conditions(a, docs[doc_id_of_page(a.clean_page_id)],
                                          examples[a.qid].gold_answer, pages_dir, page_sink=pages)
        except Exception as e:
            failed.append((a.attack_id, f"{type(e).__name__}: {e}"))
    write_jsonl(resolve(cfg["paths"]["attacks_dir"]) / "g2_tables.jsonl", rows)
    write_jsonl(resolve(cfg["paths"]["manifests_dir"]) / "pages_g2_tables.jsonl", pages)
    print(f"{len(rows)} G2 table rows ({len(rows) // 3} questions x 3), {len(pages)} pages rendered")
    for aid, err in failed:
        print(f"  FAILED {aid}: {err}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["table", "chart", "both"], default="both")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only-r2-correct", action="store_true")
    args = ap.parse_args()
    cfg = get_config()
    if args.kind in ("table", "both"):
        make_tables(cfg, args.limit, args.only_r2_correct)
    if args.kind in ("chart", "both"):
        raise NotImplementedError("chart conditions: charts.make_chart_conditions")


if __name__ == "__main__":
    main()
