# Person 3 (Vatsal) project status

Last updated: 2026-11-11.

* Milestone 1 (local D1 prototype): complete.
* Milestone 2 (review fixes, repo branch, FinQA development audit): complete.
* Observed-parse and attack evaluation: pending, waiting on teammates.

## Scope

Person 3 owns the D1 reconciliation defense, question-type labeling, the
stealth-study analysis, and the Gap 1 stage analysis. Teammates' pipelines,
attacks and renderer are out of scope.

## Where things are

**Repository.** `https://github.com/aaryapendharkar/LateComers-CSE576-NLP`
is reachable with this machine's credentials.
* At the first check on 2026-11-11 it was empty: `git ls-remote` returned no
  refs, and the GitHub API returned `409 Git Repository is empty`.
* Person 1 then pushed the team skeleton to `main`: commits `2b90224` and
  `11662e7`, 2026-11-11 18:34–18:39 MST.
* (An earlier version of these notes said the repo "did not exist". That claim
  was unsupported.)

**Branches (local only; nothing pushed or merged).**
* `p3-table-defense` (the branch named in CONTRIBUTING.md) is based on
  `origin/main` `11662e7`. It adds Person 3 work in Person 3's owned files plus
  new Person 3 helper files only:
  * Owned stubs `src/defenses/reconcile.py` and `src/analysis/{qtypes,stealth}.py`
    are replaced. Their skeleton function names are kept and implemented,
    except as noted below.
  * New helpers: `src/defenses/{d1_numbers,d1_input}.py`,
    `scripts/{run_d1,qtype_review_sheet,finqa_dev_sample,finqa_dev_audit}.py`,
    `tests/test_p3_{d1,d1_numbers,analysis}.py`, `tests/fixtures/synthetic/`,
    `docs/person3/`, `results/{dev_finqa,synthetic}/`.
  * Person 3's `reconcile:` section in `configs/default.yaml` is updated.
  * No teammate file is modified. The team acceptance tests
    `tests/test_p3_defense_analysis.py` are unchanged, and both pass.
* `p3-defense-analysis` is the earlier transfer branch, created while `main` was
  empty. It records the history: the unchanged import (`af110f2`), the review
  fixes with failing-first regression tests (`cd8208f`), the FinQA sample frozen
  **before** D1 was run (`f1e7771`), and the audit (`11005fe`). It is kept for
  provenance and should not be merged.
* The original prototype folder `../cse576-structured-poisoning/` is unchanged
  (the D1 0.1.0 baseline).

**Remaining integration step:** push `p3-table-defense` and open a PR to `main`
(CONTRIBUTING.md workflow). This needs Vatsal's go-ahead; I did not push.

`.venv/`, caches and `data/raw/` are excluded locally (in `.git/info/exclude`;
the skeleton has no `.gitignore` yet) and are not committed.

## Commands (run from this folder)

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements-core.txt     # team light deps (CPU)
./.venv/bin/python -m pytest -q          # 176 passed, 8 skipped (teammates' stubs); P3: 129 + 2 acceptance
./.venv/bin/python scripts/run_d1.py fixtures                                  # -> results/synthetic/d1_demo_*.json*
./.venv/bin/python scripts/qtype_review_sheet.py --examples tests/fixtures/synthetic/qtype_examples.jsonl \
    --out-dir results/synthetic/qtypes --review-sample 5 --synthetic
# When Person 1's data exists (dev proxy only, not pipeline evaluation):
./.venv/bin/python scripts/run_d1.py docs --docs data/docs.jsonl --out-dir results/d1_docs_dryrun
# FinQA development audit (see FINQA_DEV_AUDIT.md for the download command):
./.venv/bin/python scripts/finqa_dev_audit.py --source data/raw/finqa/train.json \
    --manifest results/dev_finqa/sample_manifest.json --out-dir results/dev_finqa \
    --proposals results/dev_finqa/proposed_explanations.json
```

D1 and the scripts need only the Python standard library (tested with 3.13).

## Completed (local, synthetic)

* D1 with arithmetic (row/column totals, nested subtotals, rounding bound) and
  conservative prose checks. Public `{"flag","reasons"}` plus `eval_record()`
  diagnostics. Three outcomes: contradiction / checks_passed / uncheckable.
* Provisional input adapter with an allowlist leakage guard, and a provisional
  markdown-table adapter.
* 20 hand-derived synthetic D1 fixtures. All 20 match in the demo. 76 tests,
  each of 9 deliberate code mutations is caught by at least one test.
* `qtypes.py` rules with precedence, review flags, proposals file, and review
  sheet, demonstrated on 13 synthetic questions.
* `stealth.py`: Fleiss' kappa and exact binomial/power, cross-checked against
  statsmodels/scipy on a reference example.
* Docs: D1_DESIGN.md, HANDOFF.md, ANALYSIS_PLAN.md.

## Completed (milestone 2)

* Fixed four review findings (D1 0.2.0). Each has regression tests that failed
  before the fix: 48 of 51 new tests failed; the other 3 are guard tests that
  pass both before and after. Evidence is in `evidence/`.
  1. Signed prose comparison; sign/magnitude wording is reported as unsupported.
  2. Currency identity is kept in arithmetic and prose; mismatched or
     ambiguous currencies are skipped, never converted.
  3. Total scope (contiguous vs nested) is decided from labels and layout, not
     values; unresolved scope gives `total_scope_ambiguous`.
  4. Stealth input validation: unique (rater, item), 3 distinct raters per item,
     unique key, full coverage, no empty input.
* Person 3 tests (`tests/test_p3_{d1,d1_numbers,analysis}.py`, renamed from
  `test_reconcile/test_d1_numbers/test_analysis.py` to follow the repo
  convention): 76 original + 51 regression + 1 FinQA adapter + 1 config = 129.
  No original test was changed. The team acceptance tests
  `tests/test_p3_defense_analysis.py` (2) pass. The synthetic demo still
  matches 20/20. The files in `evidence/` were produced on `p3-defense-analysis`
  before the rename, so they show the old test paths.
* FinQA development audit (50 train pages from 50 reports, frozen before any
  outcome was seen). Results are in [FINQA_DEV_AUDIT.md](FINQA_DEV_AUDIT.md).
  The review sheet is awaiting Vatsal's manual review.

## Not done / not claimed

* The only real data processed is the 50-page FinQA **development** sample on
  original structured JSON. It gives no observed-parse FPR, no detection rate,
  no ASR and no labels on real questions. The review sheet has **not** been
  human-reviewed yet.
* No stealth form has been created and no ratings collected.
* `funnel.py` is not written (waiting on run logs and agreement with Person 5).
* D1 has not been run on the observed Docling parse or on P2.

## Pending dependencies

Person 1: parsed-page format, ids, run logs, `r2_correct.json`, runner hook,
and decisions on backfill/empty evidence. Person 2: linked attack metadata
(evaluator only). Person 4: rendered pages and Docling verification. Person 5:
funnel schema. See [HANDOFF.md](HANDOFF.md).

## Next steps (in order)

1. Vatsal completes the FinQA review sheet. Any rule or adapter change it
   motivates (header detection, non-additive column headers, table-level scope)
   is validated on a **new** frozen sample drawn from other reports.
   Then, as soon as `docs.jsonl` lands, run the `docs` dry run.
2. Run `qtype_review_sheet.py` on the real `examples.jsonl`. Two reviewers fill the
   sheet, then the labels are handed to Person 1.
3. Once the parsed-page format is agreed, connect D1 to the observed parse and
   compute the clean FPR with CIs.
4. Run D1 on Person 2's attacks: detection by type plus the three ablations.
5. Stealth pilot following the spec. Funnel analysis on the run logs.
