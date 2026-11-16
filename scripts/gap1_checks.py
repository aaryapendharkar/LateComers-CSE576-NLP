#!/usr/bin/env python
"""Person 3 (Vatsal): the extra Gap 1 numbers quoted in the report section.

    python scripts/gap1_checks.py

Reads the Gap 1 run logs (undefended and D1-filtered), the attacks, the question
types and r2_correct.json, and writes results/gap1/gap1_checks.json:

  overall               ASR and share of correct answers over all Gap 1 runs, with and without D1
  naive_vs_consistent   the paired comparison, split into pairs whose two pages differ
                        (the consistent edit also updates a total) and pairs that are identical
  identical_pair_noise  on identical pairs, how often the two runs give different answers
  d1_filter             what happened in the runs where D1 dropped the poisoned page
  unit_edits            whether unit edits changed any answer
  question_types        label counts for all questions, R2-correct questions, attacked questions
"""
import _bootstrap  # noqa: F401
import argparse
import json
from collections import Counter, defaultdict

from src.common import metrics as M
from src.common.config import get_config, resolve
from src.common.io import load_attacks, load_examples, load_r2_correct, read_jsonl


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", default="results/runs/P1_G1.jsonl")
    ap.add_argument("--defended", default="results/runs/P1_G1_D1.jsonl")
    ap.add_argument("--flags", default="results/gap1/d1_flags.jsonl")
    ap.add_argument("--pipeline", default="P1")
    ap.add_argument("--out", default="results/gap1/gap1_checks.json")
    args = ap.parse_args()
    cfg = get_config()
    kw = {"n_resamples": cfg["metrics"]["bootstrap_resamples"], "seed": cfg["seed"]}
    attacks = load_attacks(cfg, gap="G1")
    examples = load_examples(cfg, ("finqa",))
    r2 = load_r2_correct(cfg).get(args.pipeline, set())
    und = {r["attack_id"]: r for r in read_jsonl(args.runs) if r.get("attack_id") in attacks and r["qid"] in r2}
    dfd = {r["attack_id"]: r for r in read_jsonl(args.defended) if r.get("attack_id") in attacks and r["qid"] in r2}
    clean_flag = {r["page_id"]: r["flag"] for r in read_jsonl(args.flags)}
    hit = lambda rs: M.rate([bool(r["matches_target"]) for r in rs], **kw)  # noqa: E731
    ok = lambda rs: M.rate([bool(r["correct"]) for r in rs], **kw)  # noqa: E731

    out = {"pipeline": args.pipeline, "n_runs": len(und),
           "overall": {"asr_undefended": hit(und.values()), "asr_d1_filter": hit(dfd.values()),
                       "correct_undefended": ok(und.values()), "correct_d1_filter": ok(dfd.values())}}

    pairs = defaultdict(dict)
    for a in attacks.values():
        if a.attack_type in ("naive_cell", "consistent_cell") and a.attack_id in und:
            pairs[a.qid][a.attack_type] = a
    pairs = {q: v for q, v in pairs.items() if len(v) == 2}
    differ = sorted(q for q, v in pairs.items() if v["consistent_cell"].edit.get("also_changed"))
    same = sorted(q for q in pairs if q not in differ)
    out["naive_vs_consistent"] = {}
    for name, qs in (("differing_pairs", differ), ("identical_pairs", same)):
        out["naive_vs_consistent"][name] = {"n_pairs": len(qs)}
        for t in ("naive_cell", "consistent_cell"):
            rs = [und[pairs[q][t].attack_id] for q in qs]
            out["naive_vs_consistent"][name][t] = {"n_success": sum(bool(r["matches_target"]) for r in rs), "asr": hit(rs)}
    out["identical_pair_noise"] = {
        "n_pairs": len(same),
        "pairs_with_different_answers": sum(und[pairs[q]["naive_cell"].attack_id]["answer"]
                                            != und[pairs[q]["consistent_cell"].attack_id]["answer"] for q in same),
        "note": "the two runs of an identical pair differ only in the page id shown to the generator"}

    dropped = [r for r in dfd.values() if r["poison_page_id"] in (r.get("filtered_pages") or [])]
    out["d1_filter"] = {
        "runs_with_poisoned_page_dropped": len(dropped),
        "by_type": dict(Counter(attacks[r["attack_id"]].attack_type for r in dropped)),
        "of_those_target_answer": sum(bool(r["matches_target"]) for r in dropped),
        "of_those_correct_answer": sum(bool(r["correct"]) for r in dropped),
        "of_those_clean_twin_already_flagged": sum(bool(clean_flag.get(attacks[r["attack_id"]].clean_page_id)) for r in dropped)}
    units = [r for r in und.values() if attacks[r["attack_id"]].attack_type == "unit"]
    out["unit_edits"] = {"n": len(units), "target_answer": sum(bool(r["matches_target"]) for r in units),
                         "still_gold_answer": sum(bool(r["correct"]) for r in units)}
    qt = lambda qids: dict(Counter(examples[q].question_type for q in qids))  # noqa: E731
    out["question_types"] = {"all_questions": qt(examples), "r2_correct": qt(r2), "attacked": qt({r["qid"] for r in und.values()})}

    path = resolve(args.out)
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    print(f"-> {path}")


if __name__ == "__main__":
    main()
