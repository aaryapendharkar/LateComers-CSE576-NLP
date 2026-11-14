"""Evaluate D1 on the team's fixed G1 records and matched structured source pages."""

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys


def read_rows(data):
    return [json.loads(line) for line in data.splitlines() if line.strip()]


def index_rows(rows, key):
    result = {row[key]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"Duplicate {key} in input")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--attacks-rev", default="504e5ddfef4e878e1f6ffb09baff4f27cf960d1b")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    sys.path.insert(0, str(repo))
    from src.common.edits import apply_edit
    from src.defenses.d1_input import page_from_record
    from src.defenses.reconcile import D1_VERSION, D1Config, diagnose

    def git(*parts):
        return subprocess.check_output(["git", "-C", str(repo), *parts], text=True).strip()

    def project(doc):
        evidence = {key: doc[key] for key in ("table", "pre_text", "post_text")}
        return page_from_record(evidence, "structured_json_development")

    revision = git("rev-parse", "HEAD")
    p2 = git("rev-parse", args.attacks_rev)
    docs_blob = git("rev-parse", revision + ":data/docs.jsonl")
    if docs_blob != git("rev-parse", p2 + ":data/docs.jsonl"):
        raise ValueError("The two revisions have different source documents")
    docs = index_rows(read_rows(git("show", revision + ":data/docs.jsonl")), "doc_id")
    examples = index_rows(read_rows(git("show", revision + ":data/examples.jsonl")), "qid")
    attacks = index_rows(read_rows(git("show", p2 + ":data/attacks/g1.jsonl")), "attack_id")
    config = D1Config()
    clean = {}
    results = []
    variants = defaultdict(dict)
    for aid, attack in attacks.items():
        qid = attack["qid"]
        doc_id = examples[qid]["doc_id"]
        if attack["clean_page_id"] != doc_id + "__clean":
            raise ValueError(f"Source mismatch for {aid}")
        doc = docs[doc_id]
        if doc_id not in clean:
            clean[doc_id] = diagnose(project(doc), config).status
        page = project(apply_edit(doc, attack["edit"], check_old=True))
        result = diagnose(page, config)
        kind = attack["attack_type"]
        if kind in ("naive_cell", "consistent_cell"):
            if kind in variants[qid]:
                raise ValueError(f"Duplicate {kind} for {qid}")
            variants[qid][kind] = page
        results.append(dict(attack_id=aid, qid=qid, doc_id=doc_id, attack_type=kind,
                            original_status=clean[doc_id], edited_status=result.status,
                            checks_run=len(result.checks), failed_checks=len(result.failed)))

    by_type = defaultdict(Counter)
    for row in results:
        counts = by_type[row["attack_type"]]
        counts[row["edited_status"]] += 1
        if row["edited_status"] == "contradiction" and row["original_status"] != "contradiction":
            counts["newly_flagged"] += 1
    identical = sum(pair["naive_cell"] == pair["consistent_cell"] for pair in variants.values())
    summary = dict(input="Structured source tables and prose, before rendering or parsing",
                   d1_checkout=revision, d1_version=D1_VERSION, config=asdict(config),
                   attacks_commit=p2, source_docs_blob=docs_blob, edited_records=len(results),
                   distinct_questions=len({row["qid"] for row in results}), distinct_originals=len(clean),
                   original_status_counts=Counter(clean.values()), edited_status_counts_by_type=by_type,
                   cell_pairs=len(variants), identical_inputs_in_cell_pairs=identical)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    (args.out / "outcomes.jsonl").write_text("".join(json.dumps(row) + "\n" for row in results))


if __name__ == "__main__":
    main()
