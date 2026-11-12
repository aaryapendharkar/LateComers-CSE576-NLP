#!/usr/bin/env python
"""Person 4 (Aaron): render every clean page -> data/manifests/pages_clean.jsonl.

    python scripts/render_clean_pages.py --limit 3     # show the team 3 examples
    python scripts/render_clean_pages.py               # all 500 FinQA docs (Fri morning)
    python scripts/render_clean_pages.py --source chartqa
"""
import _bootstrap  # noqa: F401
import argparse

from _runlog import tqdm
from src.common.config import get_config
from src.common.io import load_docs, write_jsonl
from src.common.schemas import clean_page_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="finqa", choices=["finqa", "chartqa"])
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    cfg = get_config()
    docs = sorted(load_docs(cfg, (args.source,)).values(), key=lambda d: d.doc_id)[: args.limit]
    if args.source == "finqa":
        from src.render.render_table_page import render_table_page as render
    else:
        from src.render.render_chart_page import render_chart_page as render
    pages = []
    for d in tqdm(docs, desc="render"):
        doc = d.to_dict()
        pages.append(render(doc, clean_page_id(d.doc_id), cfg["paths"]["pages_dir"], doc["table"], doc["table"]))
    out = f"{cfg['paths']['manifests_dir']}/pages_clean{'' if args.source == 'finqa' else '_chartqa'}.jsonl"
    write_jsonl(out, pages)
    print(f"{len(pages)} pages -> {out}")


if __name__ == "__main__":
    main()
