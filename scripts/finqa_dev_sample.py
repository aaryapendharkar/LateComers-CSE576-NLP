"""Freeze the Person 3 FinQA development sample (does NOT run D1).

Selection is fixed before any D1 outcome is looked at:
  1. Unit = unique source page (FinQA `filename`, e.g. "ADI/2009/page_49.pdf").
     Several questions can share a page; their page content is checked to be
     identical, otherwise the page is excluded.
  2. Group = source report (ticker/year, e.g. "ADI/2009"). At most one page per
     report is taken so that the sample is not dominated by a few filings.
  3. Sorted unique pages are shuffled with random.Random(seed); pages are taken
     in that order, skipping later pages from an already-sampled report, until
     `n` pages are selected.

The manifest records the source commit, git blob SHA and SHA-256, the seed,
sample ids and every exclusion. These reports are a DEVELOPMENT set: later
held-out evaluation must exclude them (see docs/person3/FINQA_DEV_AUDIT.md).

    python scripts/finqa_dev_sample.py --source data/raw/finqa/train.json \
        --out results/dev_finqa/sample_manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SOURCE_URL = "https://github.com/czyssrs/FinQA"
SOURCE_COMMIT = "0f16e2867befa6840783e58be38c9efb9229d742"
SOURCE_PATH = "dataset/train.json"
EXPECTED_GIT_BLOB = "a6c2c5a60f9abe3fba5a793cc4d9e1dee2e09209"


def file_hashes(path: Path) -> dict:
    data = path.read_bytes()
    blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    return {"sha256": hashlib.sha256(data).hexdigest(), "git_blob_sha1": blob, "bytes": len(data)}


def page_content(entry: dict) -> str:
    return json.dumps([entry["table_ori"], entry["pre_text"], entry["post_text"]])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=576)
    ap.add_argument("--force", action="store_true", help="overwrite an existing frozen manifest")
    args = ap.parse_args()

    if args.out.exists() and not args.force:
        print(f"{args.out} exists; the sample is frozen. Use --force only to deliberately re-freeze.", file=sys.stderr)
        return 1
    hashes = file_hashes(args.source)
    if hashes["git_blob_sha1"] != EXPECTED_GIT_BLOB:
        print(f"source blob {hashes['git_blob_sha1']} != expected {EXPECTED_GIT_BLOB}", file=sys.stderr)
        return 1

    entries = json.loads(args.source.read_text())
    by_page: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_page[e["filename"]].append(e)

    exclusions = []
    eligible = []
    for page in sorted(by_page):
        recs = by_page[page]
        if len({page_content(r) for r in recs}) > 1:
            exclusions.append({"filename": page, "reason": "duplicate records disagree on page content"})
        elif not recs[0]["table_ori"]:
            exclusions.append({"filename": page, "reason": "empty table_ori"})
        else:
            eligible.append(page)

    order = eligible[:]
    random.Random(args.seed).shuffle(order)
    sample, seen_reports, skipped_same_report = [], set(), 0
    for page in order:
        report = page.rsplit("/", 1)[0]
        if report in seen_reports:
            skipped_same_report += 1
            continue
        seen_reports.add(report)
        sample.append({
            "sample_rank": len(sample) + 1,
            "filename": page,
            "report_id": report,
            "ticker": report.split("/")[0],
            "source_record_ids": sorted(r["id"] for r in by_page[page]),
        })
        if len(sample) == args.n:
            break

    manifest = {
        "data_label": "DEVELOPMENT SAMPLE - FinQA train split, original structured JSON",
        "purpose": "Person 3 D1 development audit; exclude these reports from later held-out evaluation.",
        "source": {"url": SOURCE_URL, "commit": SOURCE_COMMIT, "path": SOURCE_PATH, **hashes},
        "selection": {
            "unit": "unique FinQA page (filename)",
            "group": "source report = ticker/year; max one page per report",
            "method": "random.Random(seed).shuffle(sorted eligible pages); take in order, skipping repeated reports",
            "seed": args.seed,
            "n_requested": args.n,
            "n_records_in_source": len(entries),
            "n_unique_pages": len(by_page),
            "n_unique_reports": len({p.rsplit('/', 1)[0] for p in by_page}),
            "n_eligible_pages": len(eligible),
            "n_pages_skipped_same_report_before_quota": skipped_same_report,
        },
        "exclusions": exclusions,
        "sample": sample,
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": " ".join([Path(sys.executable).name, *sys.argv]),
        "d1_outcomes_inspected_before_freeze": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"froze {len(sample)} pages from {len(seen_reports)} reports -> {args.out}")
    return 0 if len(sample) == args.n else 1


if __name__ == "__main__":
    sys.exit(main())
