# Person 3 (Vatsal) status

Last updated: 2026-11-14.

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
| Review sheet for the 30-label check | `scripts/qtype_review_sheet.py` -> `results/qtypes/manual_review_sheet.csv` | sheet generated, reviewer columns empty |
| Stealth pilot selection and statistics | `src/analysis/stealth.py`, `scripts/stealth_study.py` | code and tests only |
| Gap 1 stage analysis | `src/analysis/funnel.py`, `scripts/gap1_analysis.py` | code and tests only |
| FinQA development audit (50 train pages) | `docs/person3/FINQA_DEV_AUDIT.md`, `results/dev_finqa/` | done; review sheet not human-reviewed |

All D1 numbers are on the P1 stand-in page text (`p1_text_source: standin`),
the same text the P1 baselines used. Nothing here is a result on rendered,
Docling-parsed pages, and D1 has not been run for P2.

## Not done

| Item | Blocked on | Command once unblocked |
|---|---|---|
| 30-label hand check | me (fill `reviewer_label` in the sheet) | `python scripts/qtype_review_score.py` |
| ASR by question type, funnel, 2 system examples | Gap 1 attack run logs (Person 1) | `python scripts/gap1_analysis.py --runs results/runs/P1_G1.jsonl --clean results/runs/P1_R2_finqa.jsonl` |
| ASR with D1 as a filter | attack run with `--drop-flags results/gap1/d1_flags.jsonl` (Person 1) | add `--defended results/runs/P1_G1_D1.jsonl` to the command above |
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
python -m pytest -q                                   # 184 passed, 8 skipped (teammates' stubs)
python scripts/label_qtypes.py
python scripts/qtype_review_sheet.py --examples data/examples.jsonl --out-dir results/qtypes
python scripts/eval_reconcile.py                      # add --attacks <g1.jsonl> until data/attacks/g1.jsonl is on main
python scripts/d1_diagnostics.py                      # same --attacks option
```

The committed results were produced with the Gap 1 attacks at commit
`504e5ddfef4e878e1f6ffb09baff4f27cf960d1b` (`origin/p2-table-attacks`), exported with
`git show origin/p2-table-attacks:data/attacks/g1.jsonl > /tmp/g1.jsonl`.
