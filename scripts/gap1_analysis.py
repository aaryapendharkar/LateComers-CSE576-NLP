#!/usr/bin/env python
"""Person 3 (Vatsal): Gap 1 stage analysis from Person 1's run logs (brief task 5).

    python scripts/gap1_analysis.py --runs results/runs/P1_G1.jsonl \\
        --clean results/runs/P1_R2_finqa.jsonl [--defended results/runs/P1_G1_D1.jsonl]

Writes to results/gap1/:
  funnel_by_attack_type.md / funnel_by_question_type.md   stage funnel with 95% CIs
  gap1_analysis.json                                       every number, the poisoned-vs-clean
                                                           retrieval comparison, ASR with D1,
                                                           and 2 concrete examples
All rates are over the fixed R2-correct set of each pipeline (results/r2_correct.json).
"""
import _bootstrap  # noqa: F401
import argparse
import json

from src.analysis import funnel as F
from src.common import metrics as M
from src.common.config import get_config, resolve
from src.common.io import load_attacks, load_examples, load_r2_correct, read_jsonl

STAGES = list(M.FUNNEL_STAGES) + ["adoption|top5", "target_without_citation"]


def clean_nan(x):
    """NaN (empty groups) -> null so the output is strict JSON."""
    if isinstance(x, float) and x != x:
        return None
    if isinstance(x, dict):
        return {k: clean_nan(v) for k, v in x.items()}
    if isinstance(x, list):
        return [clean_nan(v) for v in x]
    return x


def md_table(result: dict, keys: tuple[str, ...]) -> str:
    lines = ["| " + " | ".join(keys) + " | n | " + " | ".join(STAGES) + " |", "|" + "---|" * (len(keys) + 1 + len(STAGES))]
    for group, f in result.items():
        note = " (n < 10: do not interpret)" if f["attack_success"]["n"] < 10 else ""
        lines.append("| " + " | ".join(str(g) for g in group) + f" | {f['attack_success']['n']}{note} | "
                     + " | ".join(M.fmt_rate(f[s]) for s in STAGES) + " |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", nargs="+", required=True, help="attack run logs (undefended)")
    ap.add_argument("--clean", nargs="*", default=[], help="clean R2 run logs of the same pipelines")
    ap.add_argument("--defended", nargs="*", default=[], help="attack run logs with --drop-flags (D1 filter)")
    ap.add_argument("--gap", default="G1")
    ap.add_argument("--out-dir", default="results/gap1")
    args = ap.parse_args()

    cfg = get_config()
    kw = {"n_resamples": cfg["metrics"]["bootstrap_resamples"], "seed": cfg["seed"]}
    attacks, examples = load_attacks(cfg, gap=args.gap), load_examples(cfg)
    try:
        r2 = load_r2_correct(cfg)
    except FileNotFoundError:
        print("WARNING: no r2_correct.json -> rates over ALL attacked questions")
        r2 = None

    def load(paths):
        recs = [r for p in paths for r in read_jsonl(p)]
        return F.annotate(recs, attacks, examples)

    runs, clean, defended = load(args.runs), load(args.clean), load(args.defended)
    runs = [r for r in runs if r.get("attack_id") in attacks]
    out = resolve(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result = {"n_attack_runs": len(runs)}
    for name, keys in (("funnel_by_attack_type", ("pipeline", "attack_type")),
                       ("funnel_by_question_type", ("pipeline", "question_type"))):
        f = F.funnel_by(runs, keys, r2, **kw)
        result[name] = {" | ".join(str(g) for g in group): v for group, v in f.items()}
        (out / f"{name}.md").write_text(md_table(f, keys))
        print(md_table(f, keys))
    if clean:
        result["retrieval_poison_vs_clean"] = {
            pl: F.retrieval_poison_vs_clean([r for r in runs if r["pipeline"] == pl],
                                            [r for r in clean if r["pipeline"] == pl], **kw)
            for pl in sorted({r["pipeline"] for r in runs})}
    if defended:
        result["asr_with_d1"] = {
            f"{pl} | {at}": F.asr_with_defense([r for r in runs if (r["pipeline"], r["attack_type"]) == (pl, at)],
                                               [r for r in defended if (r["pipeline"], r["attack_type"]) == (pl, at)], r2, **kw)
            for pl, at in sorted({(r["pipeline"], r["attack_type"]) for r in runs})}
    result["examples"] = F.pick_examples(runs, 2, attacks, examples)
    result = clean_nan(result)
    (out / "gap1_analysis.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k in ("retrieval_poison_vs_clean", "asr_with_d1", "examples")},
                     indent=2, default=str))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
