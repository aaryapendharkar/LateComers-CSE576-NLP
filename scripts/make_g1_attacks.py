#!/usr/bin/env python
"""Person 2 (Janhavi): Gap 1 attacks -> data/attacks/g1.jsonl + data/manifests/pages_g1.jsonl.

    python scripts/make_g1_attacks.py --limit 5            # small first
    python scripts/make_g1_attacks.py --no-render          # before Person 4's renderer exists
    python scripts/make_g1_attacks.py --only-r2-correct P1 # after Person 1 sends r2_correct.json
"""
import _bootstrap  # noqa: F401
import argparse

from src.attacks.tables.edits import generate_all
from src.common.config import get_config
from src.common.io import load_docs, load_examples, load_r2_correct, write_jsonl
from src.common.schemas import doc_id_of_page


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--only-r2-correct", metavar="PIPELINE")
    args = ap.parse_args()
    cfg = get_config()
    docs, examples = load_docs(cfg, ("finqa",)), load_examples(cfg, ("finqa",))
    if args.only_r2_correct:
        keep = load_r2_correct(cfg)[args.only_r2_correct]
        examples = {q: e for q, e in examples.items() if q in keep}
    examples = dict(sorted(examples.items())[: args.limit])

    attacks = generate_all(examples, docs, cfg)
    write_jsonl(f"{cfg['paths']['attacks_dir']}/g1.jsonl", attacks)
    print(f"{len(attacks)} Gap 1 attacks -> data/attacks/g1.jsonl")

    if not args.no_render:
        from src.common.edits import apply_edit
        from src.render.render_table_page import render_table_page

        pages = []
        for a in attacks:
            doc = docs[doc_id_of_page(a.clean_page_id)].to_dict()
            ed = apply_edit(doc, a.edit)
            pre_post = (ed["pre_text"], ed["post_text"])
            pages.append(render_table_page(doc, a.poison_page_id, cfg["paths"]["pages_dir"],
                                           ed["table"], ed["table"], pre_post, pre_post))
        write_jsonl(f"{cfg['paths']['manifests_dir']}/pages_g1.jsonl", pages)
        print(f"{len(pages)} pages -> data/manifests/pages_g1.jsonl")


if __name__ == "__main__":
    main()
