#!/usr/bin/env python
"""Step 9 (Person 1, Sat): run attacks through a pipeline and log every stage.

    python scripts/run_attacks.py --pipeline P1 --gap G1 --limit 5
    python scripts/run_attacks.py --pipeline P2 --gap G2 --types text_only_table image_only_table
    python scripts/run_attacks.py --pipeline P1 --gap G1 --drop-flags results/gap1/d1_flags.jsonl --run-name G1_D1

--drop-flags: a JSONL of {"page_id": ..., "flag": true/false} written by a defense
(Person 3's D1 or Person 5's checker). Flagged pages are removed from the top-5
before generation -> "ASR with defense".
Output: results/runs/<P>_<run-name>.jsonl (resumable: finished attack_ids are skipped).
"""
import _bootstrap  # noqa: F401
import argparse



from _runlog import done_keys, log, run_path, tqdm
from src.common.config import get_config, resolve
from src.common.io import load_attacks, load_r2_correct, read_jsonl
from src.pipelines.run import get_system


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipeline", required=True, choices=["P1", "P2", "P3"])
    ap.add_argument("--gap", choices=["G1", "G2"])
    ap.add_argument("--types", nargs="*", help="attack_type filter")
    ap.add_argument("--no-reranker", action="store_true")
    ap.add_argument("--only-r2-correct", action="store_true",
                    help="skip questions the pipeline already gets wrong (ASR ignores them anyway)")
    ap.add_argument("--drop-flags", help="defense flags JSONL -> filter run")
    ap.add_argument("--run-name")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    cfg = get_config()
    sys_ = get_system()
    attacks = list(load_attacks(cfg, gap=args.gap).values())
    if args.types:
        attacks = [a for a in attacks if a.attack_type in set(args.types)]
    if args.only_r2_correct:
        keep = load_r2_correct(cfg).get(args.pipeline, set())
        attacks = [a for a in attacks if a.qid in keep]
    attacks = sorted(attacks, key=lambda a: a.attack_id)[: args.limit]

    drop = None
    if args.drop_flags:
        drop = {r["page_id"] for r in read_jsonl(resolve(args.drop_flags)) if r.get("flag")}
    rr = not args.no_reranker
    name = args.run_name or f"{args.gap or 'all'}{'' if rr else '_norerank'}"
    path = run_path(cfg, args.pipeline, name)
    done = done_keys(path)
    for a in tqdm([a for a in attacks if (a.qid, a.attack_id) not in done], desc=f"{args.pipeline} {name}"):
        log(path, sys_.run_query(a.qid, args.pipeline, rr, attack=a, drop_pages=drop, run_name=name))
    print(f"{len(attacks)} attacks -> {path}")


if __name__ == "__main__":
    main()
