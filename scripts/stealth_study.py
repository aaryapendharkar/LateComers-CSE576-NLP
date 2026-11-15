#!/usr/bin/env python
"""Person 3 (Vatsal): build the stealth pilot (40 images + answer key) and analyse responses.

    python scripts/stealth_study.py build      # -> report/stealth/ images + key.csv (key stays private!)
    python scripts/stealth_study.py analyze --responses responses.csv

build    picks 20 clean + 20 poisoned pages (10 naive, 10 consistent), writes
         report/stealth/key.csv (gitignored, never share it) and
         report/stealth/items.csv (item ids only, safe to share), and copies each
         page image to report/stealth/images/<item>.png. If the rendered pages
         are not on disk yet it still writes the key and lists what is missing.
analyze  accepts either a long sheet (rater_id,item_id,rating) or a Google
         Forms export (one row per rater, one column per item whose header
         contains the item id, e.g. "S07"). Writes results/gap1/stealth_summary.json.
"""
import _bootstrap  # noqa: F401
import argparse
import csv
import json
import re
import shutil

from src.analysis import stealth as S
from src.common.config import get_config, resolve
from src.common.io import load_pages

KEY = "report/stealth/key.csv"
KEY_FIELDS = ["item", "page_id", "doc_id", "is_poisoned", "condition"]


def build(args, cfg):
    items = S.sample_pages(args.n_clean, args.n_poison, cfg["seed"], cfg)
    out = resolve("report/stealth")
    (out / "images").mkdir(parents=True, exist_ok=True)
    with open(resolve(KEY), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=KEY_FIELDS)
        w.writeheader()
        w.writerows(items)
    with open(out / "items.csv", "w", newline="") as f:
        f.write("item\n" + "".join(f"{i['item']}\n" for i in items))
    pages = load_pages(cfg) if resolve(cfg["paths"]["manifests_dir"]).exists() else {}
    missing = []
    for i in items:
        page = pages.get(i["page_id"])
        src = resolve(page.image_path) if page else None
        if src is None or not src.exists():
            missing.append(i["page_id"])
            continue
        shutil.copyfile(src, out / "images" / f"{i['item']}.png")
    print(f"{len(items)} items -> {resolve(KEY)} (private) and {out / 'items.csv'}")
    if missing:
        print(f"{len(missing)} of {len(items)} page images are not rendered yet (Person 4's renderer + pages_g1 manifest):")
        for m in missing:
            print("  ", m)
        return 1
    print(f"images -> {out / 'images'}; upload them to the form in items.csv order")
    return 0


def read_ratings(path) -> list[dict]:
    with open(resolve(path), newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return []
    if {"rater_id", "item_id", "rating"} <= set(rows[0]):
        return [{k: r[k].strip() for k in ("rater_id", "item_id", "rating")} for r in rows]
    cols = {c: m.group(0) for c in rows[0] if (m := re.search(r"\bS\d{2}\b", c))}
    who = next((c for c in rows[0] if re.search(r"name|email|rater", c, re.I)), None)
    out = []
    for n, r in enumerate(rows, 1):
        rater = (r.get(who) or "").strip() if who else ""
        for col, item in cols.items():
            v = re.sub(r"[^a-z]+", "_", r[col].strip().lower()).strip("_")
            out.append({"rater_id": rater or f"rater{n}", "item_id": item, "rating": v})
    return out


def analyze(args, cfg):
    with open(resolve(args.key), newline="") as f:
        key = [{"item_id": r["item"], "is_poisoned": r["is_poisoned"] == "True", "condition": r["condition"],
                "doc_id": r["doc_id"]} for r in csv.DictReader(f)]
    ratings = read_ratings(args.responses)
    result = S.analyze(ratings, key, args.raters_per_item)
    cond = {k["item_id"]: k["condition"] for k in key}
    by_cond = {}
    for c in sorted(set(cond.values())):
        votes = [r["rating"] == S.EDITED for r in ratings if cond[r["item_id"]] == c]
        by_cond[c] = {"n_ratings": len(votes), "share_rated_looks_edited": sum(votes) / len(votes) if votes else None}
    result["by_condition_descriptive"] = by_cond
    out = resolve(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    print(f"-> {out}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build", "analyze"])
    ap.add_argument("--responses")
    ap.add_argument("--key", default=KEY)
    ap.add_argument("--out", default="results/gap1/stealth_summary.json")
    ap.add_argument("--n-clean", type=int, default=20)
    ap.add_argument("--n-poison", type=int, default=20)
    ap.add_argument("--raters-per-item", type=int, default=S.PILOT_RATERS_PER_ITEM)
    args = ap.parse_args()
    cfg = get_config()
    if args.cmd == "analyze" and not args.responses:
        ap.error("analyze needs --responses")
    raise SystemExit(build(args, cfg) if args.cmd == "build" else analyze(args, cfg))


if __name__ == "__main__":
    main()
