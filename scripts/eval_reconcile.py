#!/usr/bin/env python
"""Person 3 (Vatsal): D1 false-positive rate on clean pages + detection per edit type.

    python scripts/eval_reconcile.py                              # clean pages + data/attacks/g1.jsonl
    python scripts/eval_reconcile.py --attacks /tmp/g1.jsonl      # attacks file from another branch
    python scripts/eval_reconcile.py --text-source docling        # once parsed pages exist

Writes (results/gap1/ by default):
  d1_flags.jsonl   {"page_id", "flag", "status", "reasons"} for every clean and G1
                   poisoned page. scripts/run_attacks.py --drop-flags consumes it.
  d1_summary.json  every count behind the table.
  d1_table.md      the report table (rates as "62.0 [55.1, 68.4] (n=200)").

D1 sees only the page text the P1 generator sees (--text-source). Attack
metadata is used here, in the evaluator, to join pages; it never reaches D1.

Two detection rates are reported per edit type:
  flagged        poisoned page is flagged (the A8 definition).
  newly flagged  poisoned page is flagged AND its clean twin is not. This is the
                 rate that can be attributed to the edit; "flagged" also counts
                 pages D1 already flagged before anyone edited them.
"""
import _bootstrap  # noqa: F401
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from math import comb
from pathlib import Path

from src.common import metrics as M
from src.common.config import get_config, resolve
from src.common.edits import apply_edit
from src.common.io import load_attacks, load_docs, read_jsonl, write_jsonl
from src.common.schemas import Attack, clean_page_id
from src.common.tables import doc_to_text
from src.defenses.d1_input import page_from_markdown
from src.defenses.reconcile import D1_VERSION, D1Config, config_from_dict, diagnose

CELL_TYPES = ("naive_cell", "consistent_cell")
TYPE_ORDER = ("naive_cell", "consistent_cell", "unit", "header")


def page_text(page_id: str, doc: dict, attack: Attack | None, source: str, parsed_dir: Path) -> str:
    """The text P1's generator sees for this page."""
    if source == "standin":
        return doc_to_text(apply_edit(doc, attack.edit) if attack else doc)
    path = parsed_dir / source / f"{page_id}.txt"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: run scripts/build_indexes.py --parse {source} first")
    return path.read_text(encoding="utf-8")


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from the two discordant counts."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(0, min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def evaluate(docs: dict, attacks: list[Attack], cfg_d1: D1Config, source: str, parsed_dir: Path, kw: dict) -> tuple[list, dict]:
    """Run D1 on every clean page and every poisoned page. Returns (flag rows, summary)."""
    rows, clean, texts = [], {}, {}

    def run(page_id, doc, attack):
        text = page_text(page_id, doc, attack, source, parsed_dir)
        res = diagnose(page_from_markdown(text), cfg_d1)
        texts[page_id] = text
        rows.append({"page_id": page_id, "flag": bool(res.failed), "status": res.status,
                     "reasons": res.public()["reasons"]})
        return res

    for doc_id in sorted(docs):
        clean[doc_id] = run(clean_page_id(doc_id), docs[doc_id], None)
    n_clean = len(clean)
    summary = {
        "d1_version": D1_VERSION, "config": asdict(cfg_d1), "text_source": source,
        "clean": {
            "n_pages": n_clean,
            "status_counts": dict(Counter(r.status for r in clean.values())),
            "false_positive_rate": M.rate([bool(r.failed) for r in clean.values()], **kw),
            "coverage_at_least_one_check": M.rate([bool(r.checks) for r in clean.values()], **kw),
            "false_positive_rate_among_checkable": M.rate([bool(r.failed) for r in clean.values() if r.checks], **kw),
        },
        "attacks": {}, "pairs": {},
    }

    by_type, by_qid = defaultdict(list), defaultdict(dict)
    for a in sorted(attacks, key=lambda a: a.attack_id):
        doc_id = a.clean_page_id.split("__", 1)[0]
        res = run(a.poison_page_id, docs[doc_id], a)
        rec = {"attack_id": a.attack_id, "qid": a.qid, "flag": bool(res.failed), "status": res.status,
               "clean_flag": bool(clean[doc_id].failed), "clean_status": clean[doc_id].status,
               "new_flag": bool(res.failed) and not clean[doc_id].failed,
               "same_text_as_clean": texts[a.poison_page_id] == texts[clean_page_id(doc_id)]}
        by_type[a.attack_type].append(rec)
        if a.attack_type in CELL_TYPES:
            by_qid[a.qid][a.attack_type] = (rec, texts[a.poison_page_id])

    for t in [t for t in TYPE_ORDER if t in by_type] + sorted(set(by_type) - set(TYPE_ORDER)):
        recs = by_type[t]
        summary["attacks"][t] = {
            "n": len(recs),
            "flagged": M.rate([r["flag"] for r in recs], **kw),
            "newly_flagged": M.rate([r["new_flag"] for r in recs], **kw),
            "clean_twin_already_flagged": sum(r["clean_flag"] for r in recs),
            "status_counts": dict(Counter(r["status"] for r in recs)),
            "newly_flagged_ids": [r["attack_id"] for r in recs if r["new_flag"]],
        }

    pairs = [v for v in by_qid.values() if len(v) == 2]
    differ = [v for v in pairs if v["naive_cell"][1] != v["consistent_cell"][1]]
    if pairs:
        b = sum(v["naive_cell"][0]["new_flag"] and not v["consistent_cell"][0]["new_flag"] for v in differ)
        c = sum(v["consistent_cell"][0]["new_flag"] and not v["naive_cell"][0]["new_flag"] for v in differ)
        summary["pairs"] = {
            "n_pairs": len(pairs),
            "identical_pages": len(pairs) - len(differ),
            "n_differing_pairs": len(differ),
            "naive_newly_flagged_on_differing": M.rate([v["naive_cell"][0]["new_flag"] for v in differ], **kw),
            "consistent_newly_flagged_on_differing": M.rate([v["consistent_cell"][0]["new_flag"] for v in differ], **kw),
            "discordant_naive_only": b, "discordant_consistent_only": c,
            "mcnemar_exact_p": mcnemar_exact(b, c),
        }
    return rows, summary


def table_md(main: dict, ablations: dict) -> str:
    c = main["clean"]
    out = [f"D1 {main['d1_version']}, page text source: `{main['text_source']}`. Rates in % with 95% bootstrap CIs.",
           "",
           "| Pages | n | Flagged | Newly flagged (clean twin not flagged) | Clean twin already flagged | Uncheckable |",
           "|---|---|---|---|---|---|",
           f"| clean (false positives) | {c['n_pages']} | {M.fmt_rate(c['false_positive_rate'])} | | | "
           f"{c['status_counts'].get('uncheckable', 0)} |"]
    for t, a in main["attacks"].items():
        out.append(f"| {t} | {a['n']} | {M.fmt_rate(a['flagged'])} | {M.fmt_rate(a['newly_flagged'])} | "
                   f"{a['clean_twin_already_flagged']} | {a['status_counts'].get('uncheckable', 0)} |")
    out += ["", f"Coverage: D1 can run at least one check on {M.fmt_rate(c['coverage_at_least_one_check'])} of clean pages; "
                f"among those pages the false-positive rate is {M.fmt_rate(c['false_positive_rate_among_checkable'])}."]
    zeros = sorted({a["n"] for a in main["attacks"].values() if a["n"] and a["newly_flagged"]["rate"] == 0})
    if zeros:
        out += ["", "A rate of 0 of n has a degenerate bootstrap interval. Exact one-sided 95% upper bounds: "
                    + ", ".join(f"n={n}: {100 * (1 - 0.05 ** (1 / n)):.1f}%" for n in zeros) + "."]
    p = main.get("pairs")
    if p:
        out += ["", f"Naive vs consistent: {p['n_pairs']} pairs. In {p['identical_pages']} the edited cell feeds no total that the "
                    "attack generator found, so the two poisoned pages are the same text. On the "
                    f"{p['n_differing_pairs']} pairs that differ: naive newly flagged "
                    f"{M.fmt_rate(p['naive_newly_flagged_on_differing'])}, consistent newly flagged "
                    f"{M.fmt_rate(p['consistent_newly_flagged_on_differing'])} "
                    f"(exact McNemar p = {p['mcnemar_exact_p']:.3f})."]
    if ablations:
        out += ["", "| D1 checks | Clean flagged | " + " | ".join(f"{t} newly flagged" for t in main["attacks"]) + " |",
                "|---|---|" + "---|" * len(main["attacks"])]
        for name, s in ablations.items():
            out.append(f"| {name} | {M.fmt_rate(s['clean']['false_positive_rate'])} | "
                       + " | ".join(M.fmt_rate(s["attacks"][t]["newly_flagged"]) for t in main["attacks"]) + " |")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--text-source", default=None, choices=["docling", "pdfplumber", "standin"],
                    help="default: pipelines.p1_text_source from the config")
    ap.add_argument("--attacks", help="G1 attacks JSONL (default: data/attacks/ from the config)")
    ap.add_argument("--out-dir", default="results/gap1")
    args = ap.parse_args()

    cfg = get_config()
    source = args.text_source or cfg["pipelines"]["p1_text_source"]
    kw = {"n_resamples": cfg["metrics"]["bootstrap_resamples"], "seed": cfg["seed"]}
    docs = {k: d.to_dict() for k, d in load_docs(cfg, ("finqa",)).items()}
    if args.attacks:
        raw = Path(args.attacks).read_bytes()
        attacks = [Attack.from_dict(r) for r in read_jsonl(args.attacks) if r.get("gap") == "G1"]
        attacks_source = {"path": Path(args.attacks).name, "sha256": hashlib.sha256(raw).hexdigest()}
    else:
        attacks = list(load_attacks(cfg, gap="G1").values()) if resolve(cfg["paths"]["attacks_dir"]).exists() else []
        attacks_source = {"path": cfg["paths"]["attacks_dir"]}
    attacks = [a for a in attacks if a.clean_page_id.split("__", 1)[0] in docs]
    parsed_dir = resolve(cfg["paths"]["parsed_dir"])
    d1 = config_from_dict(cfg)

    rows, main_summary = evaluate(docs, attacks, d1, source, parsed_dir, kw)
    main_summary["attacks_source"] = attacks_source
    ablations = {}
    if attacks:
        for name, c in (("arithmetic + prose (default)", d1),
                        ("arithmetic only", D1Config(True, False, d1.dash_as_zero)),
                        ("prose only", D1Config(False, True, d1.dash_as_zero))):
            ablations[name] = main_summary if c == d1 else evaluate(docs, attacks, c, source, parsed_dir, kw)[1]

    out = resolve(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "d1_flags.jsonl", rows)
    main_summary["ablations"] = {k: {"clean_fpr": v["clean"]["false_positive_rate"],
                                     "newly_flagged": {t: a["newly_flagged"] for t, a in v["attacks"].items()}}
                                 for k, v in ablations.items()}
    (out / "d1_summary.json").write_text(json.dumps(main_summary, indent=2, sort_keys=True) + "\n")
    md = table_md(main_summary, ablations)
    (out / "d1_table.md").write_text(md)
    print(md)
    print(f"{len(rows)} pages ({sum(r['flag'] for r in rows)} flagged) -> {out / 'd1_flags.jsonl'}")


if __name__ == "__main__":
    main()
