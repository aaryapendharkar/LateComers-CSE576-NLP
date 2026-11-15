#!/usr/bin/env python
"""Person 4 (Aaron): render every clean page -> data/manifests/pages_clean*.jsonl.

    python scripts/render_clean_pages.py --limit 3            # show the team 3 examples
    python scripts/render_clean_pages.py --workers 8          # all 500 FinQA docs (~1 s/page/worker)
    python scripts/render_clean_pages.py --source chartqa     # after scripts/prepare_chartqa.py

Pages (PDF/PNG/TXT/table.json) go to paths.pages_dir (gitignored, share via the
team drive); the manifest (repo-relative paths) is committed.
"""
import _bootstrap  # noqa: F401
import argparse
from multiprocessing import Pool

from _runlog import tqdm
from src.common.config import get_config
from src.common.io import load_docs, write_jsonl
from src.common.schemas import clean_page_id


def _render(job):
    source, doc, pages_dir = job
    if source == "finqa":
        from src.render.render_table_page import render_table_page as render
    else:
        from src.render.render_chart_page import render_chart_page as render
    return render(doc, clean_page_id(doc["doc_id"]), pages_dir, doc["table"], doc["table"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="finqa", choices=["finqa", "chartqa"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args()
    cfg = get_config()
    docs = sorted(load_docs(cfg, (args.source,)).values(), key=lambda d: d.doc_id)[: args.limit]
    jobs = [(args.source, d.to_dict(), cfg["paths"]["pages_dir"]) for d in docs]
    if args.workers > 1:
        with Pool(args.workers) as pool:
            pages = list(tqdm(pool.imap(_render, jobs, chunksize=4), total=len(jobs), desc="render"))
    else:
        pages = [_render(j) for j in tqdm(jobs, desc="render")]
    out = f"{cfg['paths']['manifests_dir']}/pages_clean{'' if args.source == 'finqa' else '_chartqa'}.jsonl"
    write_jsonl(out, pages)
    small = sum(1 for p in pages if p.get("font_size", 99) < float(cfg.get("render", {}).get("font_size", 10.5)))
    cut = [p["page_id"] for p in pages if p.get("truncated")]
    print(f"{len(pages)} pages -> {out}  (smaller font: {small}, prose cut: {len(cut)} {cut[:5]})")


if __name__ == "__main__":
    main()
