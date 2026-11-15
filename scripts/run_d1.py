"""Person 3 (Vatsal): run D1 on synthetic fixtures (demo) or on an A6 docs.jsonl (dry run).

Examples (from the repository root):

    python scripts/run_d1.py fixtures
    python scripts/run_d1.py docs --docs data/docs.jsonl --out-dir results/d1_docs_dryrun

`fixtures` mode writes per-case results and a summary labelled SYNTHETIC.
`docs` mode runs on clean structured JSON tables (Person 1's docs.jsonl); this is
a development proxy, NOT an evaluation of the parsing-and-RAG pipeline, which
requires the observed parsed pages.

Only table/pre_text/post_text are passed to the detector. Expected outcomes,
ids and any other metadata stay on the evaluator side of this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.defenses.d1_input import page_from_record  # noqa: E402
from src.defenses.reconcile import D1_VERSION, D1Config, diagnose  # noqa: E402

DEFAULT_FIXTURES = ROOT / "tests/fixtures/synthetic/d1_cases.json"
DETECTOR_FIELDS = ("table", "pre_text", "post_text")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _provenance(cfg: D1Config, source: Path, argv: list[str]) -> dict:
    return {
        "d1_version": D1_VERSION,
        "config": asdict(cfg),
        "source_path": str(source.relative_to(ROOT) if source.is_relative_to(ROOT) else source),
        "source_sha256": _sha256(source),
        "command": "python scripts/run_d1.py " + " ".join(argv),
        "python": platform.python_version(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _matches(expected: dict, rec: dict) -> list[str]:
    problems = []
    if rec["status"] != expected["status"]:
        problems.append(f"status {rec['status']} != {expected['status']}")
    if rec["flag"] is not expected["flag"]:
        problems.append(f"flag {rec['flag']} != {expected['flag']}")
    for key in ("n_checks", "n_failed"):
        if key in expected and rec[key] != expected[key]:
            problems.append(f"{key} {rec[key]} != {expected[key]}")
    missing = set(expected.get("skip_codes_include", [])) - {s["code"] for s in rec["skipped"]}
    if missing:
        problems.append(f"missing skip codes {sorted(missing)}")
    return problems


def run_fixtures(path: Path, out_dir: Path, cfg: D1Config, argv: list[str]) -> dict:
    data = json.loads(path.read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, mismatches = [], []
    for case in data["cases"]:
        page = page_from_record(case["detector_input"], input_kind="synthetic_fixture")
        result = diagnose(page, cfg)
        rec = result.eval_record()
        problems = _matches(case["expected"], rec) if cfg == D1Config() else []
        if problems:
            mismatches.append({"case_id": case["case_id"], "problems": problems})
        rows.append({
            "case_id": case["case_id"],
            "data_label": "SYNTHETIC",
            "description": case["description"],
            "public_output": result.public(),
            "status": rec["status"],
            "expected_status": case["expected"]["status"],
            "matches_expected": not problems if cfg == D1Config() else None,
            "diagnostics": rec,
        })
    cases_path = out_dir / "d1_demo_cases.jsonl"
    cases_path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    summary = {
        "data_label": "SYNTHETIC - demonstrates implementation behaviour only; NOT a detection-rate estimate",
        "fixture_set": data["fixture_set"],
        "fixture_provenance": data["provenance"],
        "n_cases": len(rows),
        "status_counts": dict(Counter(r["status"] for r in rows)),
        "flagged_case_ids": [r["case_id"] for r in rows if r["public_output"]["flag"]],
        "uncheckable_case_ids": [r["case_id"] for r in rows if r["status"] == "uncheckable"],
        "expectation_comparison": (
            {"n_match": len(rows) - len(mismatches), "mismatches": mismatches}
            if cfg == D1Config() else "skipped: expectations are defined for the default config only"
        ),
        "provenance": _provenance(cfg, path, argv),
        "outputs": [str(cases_path.relative_to(ROOT) if cases_path.is_relative_to(ROOT) else cases_path)],
    }
    (out_dir / "d1_demo_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def run_docs(path: Path, out_dir: Path, cfg: D1Config, argv: list[str]) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    with path.open() as f:
        for line in f:
            if not line.strip():
                continue
            doc = json.loads(line)
            detector_input = {k: doc.get(k) for k in DETECTOR_FIELDS}
            result = diagnose(page_from_record(detector_input, input_kind="clean_structured_json"), cfg)
            rows.append({"doc_id": doc.get("doc_id"), "input_kind": "clean_structured_json",
                         "public_output": result.public(), "diagnostics": result.eval_record()})
    (out_dir / "d1_docs_results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    codes = Counter(s["code"] for r in rows for s in r["diagnostics"]["skipped"])
    summary = {
        "data_label": "CLEAN STRUCTURED JSON (docs.jsonl) - development proxy, not the observed parsed page",
        "n_docs": len(rows),
        "status_counts": dict(Counter(r["diagnostics"]["status"] for r in rows)),
        "flag_rate_among_all_docs": (sum(r["public_output"]["flag"] for r in rows) / len(rows)) if rows else None,
        "skip_code_counts": dict(codes.most_common()),
        "provenance": _provenance(cfg, path, argv),
    }
    (out_dir / "d1_docs_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="mode", required=True)
    pf = sub.add_parser("fixtures", help="run the synthetic demonstration")
    pf.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    pf.add_argument("--out-dir", type=Path, default=ROOT / "results/synthetic")
    pd = sub.add_parser("docs", help="dry run on an A6 docs.jsonl (clean structured JSON)")
    pd.add_argument("--docs", type=Path, required=True)
    pd.add_argument("--out-dir", type=Path, required=True)
    for sp in (pf, pd):
        sp.add_argument("--no-arithmetic", action="store_true")
        sp.add_argument("--no-prose", action="store_true")
        sp.add_argument("--dash-as-zero", action="store_true")
    args = p.parse_args(argv)
    cfg = D1Config(check_arithmetic=not args.no_arithmetic, check_prose=not args.no_prose,
                   dash_as_zero=args.dash_as_zero)
    if args.mode == "fixtures":
        summary = run_fixtures(args.fixtures.resolve(), args.out_dir.resolve(), cfg, argv)
        print(json.dumps({k: summary[k] for k in ("data_label", "n_cases", "status_counts",
                                                  "flagged_case_ids", "expectation_comparison")}, indent=2))
        ok = not isinstance(summary["expectation_comparison"], dict) or not summary["expectation_comparison"]["mismatches"]
        return 0 if ok else 1
    summary = run_docs(args.docs.resolve(), args.out_dir.resolve(), cfg, argv)
    print(json.dumps({k: summary[k] for k in ("data_label", "n_docs", "status_counts")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
