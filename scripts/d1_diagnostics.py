#!/usr/bin/env python
"""Person 3 (Vatsal): why D1 flags clean pages, and what D1 costs as a filter.

    python scripts/d1_diagnostics.py [--attacks /tmp/g1.jsonl] [--clean-run results/runs/P1_R2_finqa.jsonl]

Three diagnostics, written to results/gap1/d1_diagnostics.{json,md}:

1. Clean-flag triage. Every clean page D1 flags is put into one bucket by a
   simple automatic rule (NOT a human review):
     headerless_table   the table's header row holds formatted data values, i.e.
                        the first data row was stored as the header, so D1 sums
                        a column that is missing its first row
     dash_artifact      a component cell is exactly "2013" or "2014" where the
                        report prints an en/em dash (unicode escape artifact in
                        the FinQA source) and the discrepancy equals that value
     non_additive       the checked column is an average, price, rate or percentage
     other              none of the above (label scope errors, products, ...)
2. Input-repair what-if. D1 is re-run with the two input problems repaired in
   the evaluator (header row moved back into the rows; dash artifacts treated
   as dashes). This is a post-hoc diagnostic on the same pages, not a tuned
   result: it shows how much of the false-positive rate is caused by the input.
3. Filter cost on the clean run. Using the top-5 lists of the undefended R2
   run, how often would dropping D1-flagged pages remove the gold page?
"""
import _bootstrap  # noqa: F401
import argparse
import copy
import json
import re
from collections import Counter
from pathlib import Path

from src.common import metrics as M
from src.common.config import get_config, resolve
from src.common.edits import apply_edit
from src.common.io import load_docs, load_examples, load_r2_correct, read_jsonl
from src.common.schemas import clean_page_id
from src.common.tables import doc_to_text
from src.defenses.d1_input import page_from_markdown
from src.defenses.d1_numbers import parse_number
from src.defenses.reconcile import D1_VERSION, config_from_dict, diagnose

YEAR = re.compile(r"(?:19|20)\d\d")
DASH_ARTIFACTS = ("2013", "2014")
NON_ADDITIVE = re.compile(r"average|price|rate|%|percent|per share|yield|remaining|may yet", re.I)


def header_holds_data(table: dict) -> bool:
    cells = [parse_number(h) for h in table["header"][1:]]
    return any(c.kind == "number" and (c.currency or "," in c.raw or "." in c.raw or c.percent) for c in cells)


def repair(table: dict, header: bool, dash: bool) -> dict:
    t = copy.deepcopy(table)
    if header and header_holds_data(t):
        t["rows"] = [list(t["header"])] + t["rows"]
        t["header"] = [""] + [f"col{i}" for i in range(1, len(t["header"]))]
    if dash:
        for row in t["rows"]:
            for i in range(1, len(row)):
                if row[i].strip() in DASH_ARTIFACTS and not YEAR.fullmatch(row[0].strip()):
                    row[i] = "—"
    return t


def run(doc: dict, d1, header=False, dash=False):
    d = dict(doc, table=repair(doc["table"], header, dash)) if (header or dash) else doc
    return diagnose(page_from_markdown(doc_to_text(d)), d1)


def bucket(doc: dict, res) -> str:
    kinds = set()
    for f in res.failed:
        raw = [c.split("=", 1)[1].strip() for c in f.cells if "=" in c]
        disc = float(f.discrepancy.replace(",", ""))
        n_dash = sum(r in DASH_ARTIFACTS for r in raw)
        column = f.relationship.split(" in column ")[-1] if " in column " in f.relationship else ""
        if n_dash and any(abs(disc - (a * 2013 + b * 2014)) < 1 for a in range(6) for b in range(6) if 0 < a + b <= n_dash):
            kinds.add("dash_artifact")
        elif header_holds_data(doc["table"]):
            kinds.add("headerless_table")
        elif f.kind == "arithmetic" and NON_ADDITIVE.search(column):
            kinds.add("non_additive")
        else:
            kinds.add("other")
    for k in ("headerless_table", "dash_artifact", "non_additive", "other"):
        if k in kinds:
            return k
    return "other"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--attacks", help="G1 attacks JSONL for the what-if detection counts")
    ap.add_argument("--clean-run", default="results/runs/P1_R2_finqa.jsonl")
    ap.add_argument("--out-dir", default="results/gap1")
    args = ap.parse_args()
    cfg = get_config()
    kw = {"n_resamples": cfg["metrics"]["bootstrap_resamples"], "seed": cfg["seed"]}
    d1 = config_from_dict(cfg)
    docs = {k: d.to_dict() for k, d in sorted(load_docs(cfg, ("finqa",)).items())}
    examples = load_examples(cfg, ("finqa",), with_qtypes=False)
    gold_docs = {e.doc_id for e in examples.values()}
    attacks = [a for a in read_jsonl(args.attacks) if a.get("gap") == "G1"] if args.attacks else []

    clean = {k: run(d, d1) for k, d in docs.items()}
    flagged = {k: bucket(docs[k], r) for k, r in clean.items() if r.failed}
    hdr = {k for k, d in docs.items() if header_holds_data(d["table"])}
    dash = {k for k, d in docs.items() if any(c.strip() in DASH_ARTIFACTS and not YEAR.fullmatch(r[0].strip())
                                              for r in d["table"]["rows"] for c in r[1:])}
    atk_docs = [a["clean_page_id"].split("__", 1)[0] for a in attacks]
    result = {
        "d1_version": D1_VERSION,
        "clean_flag_triage": {"note": "automatic buckets, not human-reviewed", "n_flagged": len(flagged),
                              "buckets": dict(Counter(flagged.values()).most_common()),
                              "pages": {b: sorted(k for k, v in flagged.items() if v == b) for b in sorted(set(flagged.values()))}},
        "input_problems": {
            "headerless_table": {"docs": len(hdr), "gold_docs": len(hdr & gold_docs), "attacks": sum(d in hdr for d in atk_docs),
                                 "examples": sorted(hdr)[:5]},
            "dash_artifact": {"docs": len(dash), "gold_docs": len(dash & gold_docs), "attacks": sum(d in dash for d in atk_docs),
                              "cells": sum(c.strip() in DASH_ARTIFACTS and not YEAR.fullmatch(r[0].strip())
                                           for k in dash for r in docs[k]["table"]["rows"] for c in r[1:]),
                              "examples": sorted(dash)[:5]},
        },
        "what_if_input_repair": {},
    }
    for name, (h, da) in {"as_is": (False, False), "header_repair": (True, False),
                          "dash_repair": (False, True), "both_repairs": (True, True)}.items():
        c = {k: run(d, d1, h, da) for k, d in docs.items()}
        entry = {"clean_fpr": M.rate([bool(r.failed) for r in c.values()], **kw),
                 "coverage": M.rate([bool(r.checks) for r in c.values()], **kw), "newly_flagged": {}}
        new, tot = Counter(), Counter()
        for a in attacks:
            doc_id = a["clean_page_id"].split("__", 1)[0]
            r = run(apply_edit(docs[doc_id], a["edit"]), d1, h, da)
            tot[a["attack_type"]] += 1
            new[a["attack_type"]] += bool(r.failed) and not c[doc_id].failed
            if name == "both_repairs" and a["attack_type"] == "consistent_cell" and r.failed and not c[doc_id].failed:
                entry.setdefault("consistent_edits_that_break_a_total", []).append(a["attack_id"])
        entry["newly_flagged"] = {t: f"{new[t]}/{tot[t]}" for t in sorted(tot)}
        result["what_if_input_repair"][name] = entry

    run_path = resolve(args.clean_run)
    if run_path.exists():
        flag = {clean_page_id(k): bool(r.failed) for k, r in clean.items()}
        try:
            r2 = load_r2_correct(cfg)
        except FileNotFoundError:
            r2 = {}
        runs = [r for r in read_jsonl(run_path) if not r.get("attack_id")]
        gold = lambda r: clean_page_id(examples[r["qid"]].doc_id)  # noqa: E731
        lost = [(gold(r) in r["top5"]) and flag.get(gold(r), False) for r in runs]
        keep = r2.get(runs[0]["pipeline"], set()) if runs else set()
        lost_correct = [x for x, r in zip(lost, runs) if r["qid"] in keep]
        result["filter_cost_on_clean_run"] = {
            "run": Path(args.clean_run).name, "n_questions": len(runs),
            "any_top5_page_dropped": M.rate([any(flag.get(p, False) for p in r["top5"]) for r in runs], **kw),
            "mean_pages_dropped_per_question": sum(sum(flag.get(p, False) for p in r["top5"]) for r in runs) / max(len(runs), 1),
            "gold_page_dropped_all_questions": M.rate(lost, **kw),
            "gold_page_dropped_r2_correct_questions": M.rate(lost_correct, **kw),
            "n_r2_correct_questions_losing_gold_page": sum(lost_correct),
        }

    out = resolve(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "d1_diagnostics.json").write_text(json.dumps(result, indent=2) + "\n")
    t, ip, w = result["clean_flag_triage"], result["input_problems"], result["what_if_input_repair"]
    md = [f"D1 {D1_VERSION} diagnostics. Buckets are assigned by an automatic rule and are not human-reviewed.", "",
          "| Cause of a clean flag (automatic bucket) | Pages |", "|---|---|"]
    md += [f"| {b} | {n} |" for b, n in t["buckets"].items()] + [f"| total flagged | {t['n_flagged']} |", ""]
    md += ["| Input problem in docs.jsonl | Docs (of 500) | Gold docs | G1 attacks on such docs |", "|---|---|---|---|"]
    md += [f"| {k} | {v['docs']} | {v['gold_docs']} | {v['attacks']} |" for k, v in ip.items()] + [""]
    types = sorted({t_ for e in w.values() for t_ in e["newly_flagged"]})
    md += ["| D1 input (post-hoc diagnostic) | Clean FPR | Coverage | " + " | ".join(f"{x} newly flagged" for x in types) + " |",
           "|---|---|---|" + "---|" * len(types)]
    md += [f"| {k} | {M.fmt_rate(e['clean_fpr'])} | {M.fmt_rate(e['coverage'])} | "
           + " | ".join(e["newly_flagged"].get(x, "") for x in types) + " |" for k, e in w.items()]
    fc = result.get("filter_cost_on_clean_run")
    if fc:
        md += ["", f"Filter cost on the clean run ({fc['run']}, n={fc['n_questions']}): D1 would drop at least one top-5 page for "
                   f"{M.fmt_rate(fc['any_top5_page_dropped'])} of questions, and would drop the gold page for "
                   f"{M.fmt_rate(fc['gold_page_dropped_all_questions'])} of all questions and "
                   f"{M.fmt_rate(fc['gold_page_dropped_r2_correct_questions'])} of the questions the undefended system answers correctly."]
    (out / "d1_diagnostics.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
