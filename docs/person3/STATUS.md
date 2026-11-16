# Person 3 (Vatsal) status

Last updated: 2026-11-15.

Person 3 owns the D1 reconciliation defense, question-type labels, the stealth
pilot and the Gap 1 stage analysis. Branch: `p3-table-defense` (pull request
into `main`). The report section is `report/contributions/p3_vatsal.md`.

## Done

| Item | Where | Result |
|---|---|---|
| D1 filter 0.2.0 | `src/defenses/reconcile.py`, `d1_numbers.py`, `d1_input.py` | arithmetic + table-vs-text checks, three outcomes |
| D1 on 500 clean pages and 99 Gap 1 edits | `scripts/eval_reconcile.py` -> `results/gap1/d1_table.md`, `d1_summary.json`, `d1_flags.jsonl` | FPR 10.2%, coverage 34.4%, naive newly flagged 4/38, consistent 0/38 |
| Why D1 flags clean pages, filter cost | `scripts/d1_diagnostics.py` -> `results/gap1/d1_diagnostics.md` | two input defects in `docs.jsonl`; gold page dropped for 8 of 72 R2-correct questions |
| Question-type labels, 200 questions | `scripts/label_qtypes.py` -> `data/labels/qtypes.jsonl` | 142 arithmetic, 55 trend, 3 comparison, 0 lookup |
| 30-label hand check | `results/qtypes/manual_review_sheet.csv`, `review_agreement.json` | 28 of 30 agree, Cohen's kappa 0.85 |
| Stealth pilot selection and statistics | `src/analysis/stealth.py`, `scripts/stealth_study.py` | code and tests only |
| Gap 1 stage analysis on Person 1's attack runs (P1, 99 attacks) | `scripts/gap1_analysis.py` -> `results/gap1/gap1_analysis.json`, `funnel_by_*.md` | ASR 46.5%, with D1 filter 39.4%; poisoned page always at its clean twin's rank |
| FinQA development audit (50 train pages) | `docs/person3/FINQA_DEV_AUDIT.md`, `results/dev_finqa/` | done; review sheet not human-reviewed |

All D1 numbers are on the P1 stand-in page text (`p1_text_source: standin`),
the same text the P1 baselines used. Nothing here is a result on rendered,
Docling-parsed pages, and D1 has not been run for P2.

## Not done

| Item | Blocked on | Command once unblocked |
|---|---|---|
| Stealth pilot | rendered page images (Person 4) | `python scripts/stealth_study.py build`, then `analyze --responses <csv>` |
| D1 on observed parses | Docling or pdfplumber text in `data/parsed/` | `python scripts/eval_reconcile.py --text-source docling` |
| Human review of the 50-page development sheet | me | see FINQA_DEV_AUDIT.md |

## Known limitations

* Totals are found from labels only ("total", "subtotal"). A table whose total
  row has another label is uncheckable. Discovery by arithmetic was left out on
  purpose: a naive edit destroys the very relationship that discovery would look
  for. Near-miss discovery is the planned extension.
* Small edits can fit inside the rounding tolerance of integer tables (q0084).
* 27 of D1's 51 clean flags come from two defects in `docs.jsonl` (first data row
  stored as header; dashes stored as "2013"/"2014"). D1 was not changed to hide
  them; `d1_diagnostics.py` reports the effect of repairing the input.
* The naive versus consistent comparison rests on 13 pairs; the other 25 pairs
  are identical pages.

## Commands

```bash
python -m pytest -q tests/test_p3_*.py               # 139 passed
python scripts/label_qtypes.py
python scripts/qtype_review_sheet.py --examples data/examples.jsonl --out-dir results/qtypes
python scripts/eval_reconcile.py                      # results/gap1/d1_table.md, d1_summary.json, d1_flags.jsonl
python scripts/d1_diagnostics.py                      # results/gap1/d1_diagnostics.{md,json}
python scripts/gap1_analysis.py --runs results/runs/P1_G1.jsonl --clean results/runs/P1_R2_finqa.jsonl --defended results/runs/P1_G1_D1.jsonl
python scripts/gap1_checks.py                         # results/gap1/gap1_checks.json
```

The committed D1 results use `data/attacks/g1.jsonl` as merged into `main`
(same file as commit `504e5dd` of the attack branch; its sha256 is recorded in
`results/gap1/d1_summary.json`).
