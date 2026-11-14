"""Person 3 D1 development audit on the frozen FinQA sample.

DATA LABEL: development results on ORIGINAL FinQA STRUCTURED JSON (train
split). Not an observed-parser (Docling) result, not an attack detection rate,
not a downstream RAG result.

For every sampled page D1 sees only record_from_finqa(entry): table_ori plus
FinQA's tokenized pre_text/post_text. Question, answer, program, gold_inds,
ids and filenames stay here, in the evaluator.

Outputs (in --out-dir):
  d1_dev_results.jsonl   one row per sampled page, all three configurations
  d1_dev_summary.json    counts per configuration; every page accounted for
  d1_dev_review_sheet.csv  every flagged page, every wholly uncheckable page and
                           a seeded sample of passing pages, with blank reviewer fields

    python scripts/finqa_dev_audit.py --source data/raw/finqa/train.json \
        --manifest results/dev_finqa/sample_manifest.json --out-dir results/dev_finqa \
        --proposals results/dev_finqa/proposed_explanations.json
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import random
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from finqa_dev_sample import file_hashes  # noqa: E402
from src.defenses.d1_input import page_from_record, record_from_finqa  # noqa: E402
from src.defenses.reconcile import (  # noqa: E402
    CHECKS_PASSED, CONTRADICTION, D1_VERSION, UNCHECKABLE, D1Config, diagnose, is_total_label)

DATA_LABEL = ("DEVELOPMENT RESULTS ON ORIGINAL FINQA STRUCTURED JSON (train split; table_ori + tokenized "
              "pre/post text). Not observed-parser results, not attack detection rates, not RAG results.")
CONFIGS = {
    "arithmetic_only": D1Config(check_prose=False),
    "prose_only": D1Config(check_arithmetic=False),
    "combined": D1Config(),
}
REVIEWER_FIELDS = ["reviewer_initials", "reviewed_on", "reviewer_relationship_correct (y/n/unclear)",
                   "reviewer_units_correct (y/n/unclear)",
                   "reviewer_verdict (true_inconsistency/source_or_layout_issue/d1_rule_error/correct_pass/"
                   "correctly_uncheckable/should_be_checkable/unclear)",
                   "reviewer_notes"]


def render_table(rows: list[list[str]]) -> str:
    return "\n".join(f"r{i}: " + " | ".join(row) for i, row in enumerate(rows))


def summarize(rows: list[dict], cfg: str) -> dict:
    recs = [r["configs"][cfg] for r in rows]
    status = Counter(r["status"] for r in recs)
    assert sum(status.values()) == len(rows)
    skip_items, skip_pages = Counter(), Counter()
    for r in recs:
        codes = [s["code"] for s in r["skipped"]]
        skip_items.update(codes)
        skip_pages.update(set(codes))
    return {
        "n_pages": len(rows),
        "n_pages_with_applicable_arithmetic_check": sum(r["n_checks"]["arithmetic"] > 0 for r in recs),
        "n_pages_with_applicable_prose_check": sum(r["n_checks"]["prose"] > 0 for r in recs),
        "n_flagged": status[CONTRADICTION],
        "n_checks_passed": status[CHECKS_PASSED],
        "n_wholly_uncheckable": status[UNCHECKABLE],
        "accounted_for": status[CONTRADICTION] + status[CHECKS_PASSED] + status[UNCHECKABLE],
        "n_checks": {k: sum(r["n_checks"][k] for r in recs) for k in ("arithmetic", "prose")},
        "n_failed_checks": {k: sum(r["n_failed"][k] for r in recs) for k in ("arithmetic", "prose")},
        "unaligned_prose_numbers": sum(r["unaligned_prose_numbers"] for r in recs),
        "skipped_or_ambiguous_items_by_code": dict(skip_items.most_common()),
        "pages_with_skip_code": dict(skip_pages.most_common()),
        "flagged_pages": [r2["filename"] for r2, r in zip(rows, recs) if r["status"] == CONTRADICTION],
        "wholly_uncheckable_pages": [r2["filename"] for r2, r in zip(rows, recs) if r["status"] == UNCHECKABLE],
    }


def units_text(units: dict) -> str:
    if not units:
        return "no table view (see skip codes)"
    ev = "; ".join(units["scale_evidence"]) or "none"
    return (f"table scale: {units['scale_status']} (multiplier {units['scale_multiplier']}, evidence: {ev}); "
            f"declared currencies {units['declared_currencies'] or 'none'}; "
            f"cell currencies {units['cell_currencies'] or 'none'}")


def skip_text(skipped: list[dict]) -> str:
    return "\n".join(f"[{s['kind']}] {s['code']}: {s['detail']}" for s in skipped)


def auto_uncheckable_reason(row: dict, rec: dict) -> str:
    """Rule-derived hypothesis for why nothing was checkable (prefixed AUTO)."""
    codes = {s["code"] for s in rec["skipped"]}
    table = row["table_ori"]
    if "ragged_table" in codes:
        widths = sorted({len(r) for r in table})
        return (f"AUTO: rows have different widths {widths}; the first row looks like a spanning/multi-row "
                "header, which the adapter does not merge, so no table check ran.")
    has_total = any(is_total_label(r[0]) for r in table[1:]) or any(is_total_label(h) for h in table[0][1:])
    prose = "; prose numbers did not align with exactly one row label and year" if "prose" not in \
        {c["kind"] for c in rec["checks"]} else ""
    if not has_total:
        return "AUTO: no row or column is labelled as a total, so no arithmetic relationship is declared" + prose + "."
    return f"AUTO: total-labelled row/column present but skipped ({', '.join(sorted(codes))})" + prose + "."


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--passing-sample", type=int, default=10)
    ap.add_argument("--seed", type=int, default=576)
    ap.add_argument("--proposals", type=Path, help="JSON {filename: proposed explanation} (not human-reviewed)")
    args = ap.parse_args()
    proposals = json.loads(args.proposals.read_text()) if args.proposals else {}

    manifest = json.loads(args.manifest.read_text())
    hashes = file_hashes(args.source)
    if hashes["sha256"] != manifest["source"]["sha256"]:
        print("source file does not match the frozen manifest hash", file=sys.stderr)
        return 1
    by_page: dict[str, list[dict]] = {}
    for e in json.loads(args.source.read_text()):
        by_page.setdefault(e["filename"], []).append(e)

    rows = []
    for s in manifest["sample"]:
        entry = sorted(by_page[s["filename"]], key=lambda e: e["id"])[0]
        page = page_from_record(record_from_finqa(entry), input_kind="clean_structured_json")
        row = {**s, "input_kind": page.input_kind, "configs": {},
               "text_before_table": (entry["pre_text"] or [""])[-1],
               "table_ori": entry["table_ori"]}
        for name, cfg in CONFIGS.items():
            res = diagnose(page, cfg)
            row["configs"][name] = {**res.eval_record(), "public_output": res.public()}
        rows.append(row)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    with (args.out_dir / "d1_dev_results.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps({"data_label": "DEVELOPMENT / ORIGINAL STRUCTURED JSON", **r}) + "\n")

    summary = {
        "data_label": DATA_LABEL,
        "d1_version": D1_VERSION,
        "configs": {name: {"config": vars(cfg), **summarize(rows, name)} for name, cfg in CONFIGS.items()},
        "provenance": {
            "manifest": str(args.manifest), "source": manifest["source"], "seed_for_passing_sample": args.seed,
            "command": " ".join([Path(sys.executable).name, *sys.argv]), "python": platform.python_version(),
            "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "notes": [
            "A flag means D1 found an internal inconsistency in the source JSON as given; it has not been "
            "reviewed and is not evidence of an error in the filing or of an attack.",
            "checks_passed means no contradiction was found among the checks that applied; it does not "
            "establish correctness.",
            "FinQA provides no table title or unit note; no unit was inferred from prose.",
        ],
    }
    (args.out_dir / "d1_dev_summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    comb = {r["filename"]: r["configs"]["combined"] for r in rows}
    passing = sorted(f for f, c in comb.items() if c["status"] == CHECKS_PASSED)
    passing_sample = sorted(random.Random(args.seed).sample(passing, min(args.passing_sample, len(passing))))
    header = ["review_id", "review_category", "sample_rank", "filename", "report_id", "source_record_ids",
              "status_combined", "status_arithmetic_only", "status_prose_only", "check_kind",
              "relationship_checked", "cells", "expected_from_components_or_text", "observed_in_table",
              "discrepancy", "tolerance", "units", "d1_explanation", "skipped_or_ambiguous_relationships",
              "text_immediately_before_table", "table_ori", "proposed_explanation (assistant; NOT human-reviewed)",
              *REVIEWER_FIELDS]
    sheet = []
    for r in rows:
        c = r["configs"]["combined"]
        base = {"sample_rank": r["sample_rank"], "filename": r["filename"], "report_id": r["report_id"],
                "source_record_ids": " ".join(r["source_record_ids"]), "status_combined": c["status"],
                "status_arithmetic_only": r["configs"]["arithmetic_only"]["status"],
                "status_prose_only": r["configs"]["prose_only"]["status"], "units": units_text(c["table_units"]),
                "skipped_or_ambiguous_relationships": skip_text(c["skipped"]),
                "text_immediately_before_table": r["text_before_table"], "table_ori": render_table(r["table_ori"]),
                "proposed_explanation (assistant; NOT human-reviewed)": proposals.get(r["filename"], "")}
        if c["status"] == CONTRADICTION:
            for chk in (x for x in c["checks"] if not x["passed"]):
                sheet.append({**base, "review_category": "flagged", "check_kind": chk["kind"],
                              "relationship_checked": chk["relationship"], "cells": "\n".join(chk["cells"]),
                              "expected_from_components_or_text": chk["expected"], "observed_in_table": chk["observed"],
                              "discrepancy": chk["discrepancy"], "tolerance": chk["tolerance"],
                              "d1_explanation": chk["explanation"]})
        elif c["status"] == UNCHECKABLE:
            if not base["proposed_explanation (assistant; NOT human-reviewed)"]:
                base["proposed_explanation (assistant; NOT human-reviewed)"] = auto_uncheckable_reason(r, c)
            sheet.append({**base, "review_category": "wholly_uncheckable", "check_kind": "none",
                          "relationship_checked": "no applicable relationship",
                          "d1_explanation": c["public_output"]["reasons"][0]})
        elif r["filename"] in passing_sample:
            sheet.append({**base, "review_category": "passing_sample", "check_kind": "all passed",
                          "relationship_checked": "\n".join(x["relationship"] for x in c["checks"]),
                          "cells": "\n".join("; ".join(x["cells"]) for x in c["checks"]),
                          "d1_explanation": "\n".join(x["explanation"] for x in c["checks"])})
    order = {"flagged": 0, "wholly_uncheckable": 1, "passing_sample": 2}
    sheet.sort(key=lambda x: (order[x["review_category"]], x["sample_rank"]))
    for i, x in enumerate(sheet, 1):
        x["review_id"] = f"R{i:03d}"
    with (args.out_dir / "d1_dev_review_sheet.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, restval="")
        w.writeheader()
        w.writerows(sheet)

    for name in CONFIGS:
        s = summary["configs"][name]
        print(f"{name:16s} pages={s['n_pages']} arith_pages={s['n_pages_with_applicable_arithmetic_check']} "
              f"prose_pages={s['n_pages_with_applicable_prose_check']} flagged={s['n_flagged']} "
              f"passed={s['n_checks_passed']} uncheckable={s['n_wholly_uncheckable']}")
    print(f"review sheet rows: {len(sheet)} -> {args.out_dir / 'd1_dev_review_sheet.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
