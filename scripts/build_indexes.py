#!/usr/bin/env python
"""Step 3 (Person 1, Fri): parse rendered PDFs and embed all clean pages once.

    python scripts/build_indexes.py --parse docling          # PDF -> data/parsed/docling/<page_id>.txt
    python scripts/build_indexes.py --parse pdfplumber       # fallback parser
    python scripts/build_indexes.py --index P1 P2            # embed every clean page (cached)
    python scripts/build_indexes.py --parse docling --limit 5   # check 5 pages by hand first
"""
import _bootstrap  # noqa: F401
import argparse

from _runlog import tqdm



from src.common.config import get_config, resolve
from src.common.io import load_pages
from src.pipelines.p1_text import PARSERS
from src.pipelines.run import get_system


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parse", choices=sorted(PARSERS))
    ap.add_argument("--index", nargs="*", choices=["P1", "P2"], default=[])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()
    cfg = get_config()

    if args.parse:
        out_dir = resolve(cfg["paths"]["parsed_dir"]) / args.parse
        out_dir.mkdir(parents=True, exist_ok=True)
        pages = list(load_pages(cfg).values())[: args.limit]
        for p in tqdm(pages, desc=f"parse:{args.parse}"):
            out = out_dir / f"{p.page_id}.txt"
            if out.exists() and not args.overwrite:
                continue
            out.write_text(PARSERS[args.parse](str(resolve(p.pdf_path))), encoding="utf-8")
        print(f"parsed {len(pages)} pages -> {out_dir}")

    if args.index:
        sys_ = get_system()
        for source in ("finqa", "chartqa"):
            corpus = sys_.store.clean_corpus(source)[: args.limit]
            for pl in args.index:
                if corpus:
                    (sys_.p1 if pl == "P1" else sys_.p2).index(corpus)
                    print(f"indexed {len(corpus)} {source} pages for {pl}")


if __name__ == "__main__":
    main()
