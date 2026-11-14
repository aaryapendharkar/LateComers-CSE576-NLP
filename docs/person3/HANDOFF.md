# Person 3 integration handoff

Status as of 2026-11-14. Current state and results: [STATUS.md](STATUS.md).

Person 3 work is on `p3-table-defense` (pull request into `main`). It changes
only Person 3's files and adds Person 3 helper files; no teammate file is
modified, and the team acceptance tests in `tests/test_p3_defense_analysis.py`
pass unchanged.

## Found while evaluating D1 (please read)

* **Person 1, `docs.jsonl`:** 42 of 500 documents have their first data row
  stored as the table header (example: `finqa_AMT_2014_p160`, header
  `['2015', '$574,438']`), and 18 documents have "2013" or "2014" in cells where
  the report prints a dash (example: `finqa_ABMD_2006_p43`). Lists are in
  `results/gap1/d1_diagnostics.json`.
* **Person 2, `g1.jsonl`:** in 25 of the 38 naive/consistent pairs the two
  edits are identical (`also_changed` is empty). On headerless tables the total
  is not detected, so 5 `consistent_cell` edits (q0005, q0095, q0098, q0167,
  q0194) leave the table inconsistent.
* **Person 1, D1 filter run:** `results/gap1/d1_flags.jsonl` is ready for
  `scripts/run_attacks.py --drop-flags`. Note that the flags would also drop the
  gold page for 8 of the 72 R2-correct questions on the clean run.

**Departures from the skeleton's Person 3 stubs (please confirm):**

| Skeleton | Implemented | Why |
|---|---|---|
| `reconcile.D1Result` TypedDict | Renamed to `D1Output`; `D1Result` is the diagnostics dataclass | No teammate code imports it; the richer result is needed by the evaluator |
| `sum_check(table, rel_tol=0.005, abs_tol=1.0)` | `sum_check(table)`, using the printed-precision rounding bound | A fixed tolerance of 1.0 hides edits on tables printed in billions; 0.5% hides small naive edits |
| `reconcile:` config keys `sum_rel_tol`, `sum_abs_tol`, `total_keywords: [.., net, sum, ..]` | `check_arithmetic`, `check_prose`, `dash_as_zero`; unknown keys raise | Tolerance is derived, not tuned; `net` rows are differences and are reported as not checked |
| `stealth.analyze(annotations)` with `annotator/item/label: edited/normal` | `analyze(ratings, key)` with `rater_id/item_id/rating: looks_edited/looks_normal` | Accuracy needs the private answer key; truth in rater rows would leak |
| `stealth.sample_pages()` with no inputs | `sample_pages(..., attacks=None, clean_doc_ids=None)`; defaults load the project data | Lets the selection be tested without the real attack file |
| `funnel.funnel_by(records, keys, r2_correct)` | Same, plus `annotate()`, `asr_with_defense()`; `r2_correct` may be a set or `{pipeline: set}` | Run logs carry no attack or question type; the D1 filter run needs the same fixed denominator |
| `scripts/label_qtypes.py` writes `data/labels/qtypes.jsonl` directly (README step 3) | Unchanged; it now works. `scripts/qtype_review_sheet.py` makes the review sheet | Labels written there are **unreviewed proposals** until the 30-label check is done |

## What runs today

* D1 on clean pages and Gap 1 edits: `python scripts/eval_reconcile.py`
* D1 diagnostics and filter cost: `python scripts/d1_diagnostics.py`
* Question-type labels: `python scripts/label_qtypes.py`; review sheet:
  `python scripts/qtype_review_sheet.py --examples data/examples.jsonl --out-dir results/qtypes`;
  agreement after the sheet is filled: `python scripts/qtype_review_score.py`
* Gap 1 stage analysis, once run logs exist: `python scripts/gap1_analysis.py --runs ... --clean ...`
* Stealth pilot: `python scripts/stealth_study.py build` (needs rendered pages for the images)
* D1 on synthetic fixtures: `python scripts/run_d1.py fixtures`

## Needed from Person 1 (pipelines / repo)

1. **Observed parsed-page format for P1.** D1 must run on what the generator
   sees, not on the clean JSON. Please decide and document one of:
   (a) the Docling markdown export (`page_from_markdown()` parses the first pipe
   table and treats the line above it as the title), or (b) a structured table
   JSON derived from Docling's `TableItem`, in A6 shape
   (`{"title","unit_note","header","rows"}`) plus the page's non-table text.
   Either way, **parsing errors must be preserved, not cleaned**.
   Also say where the unit note ("in millions") ends up in the parse.
2. **Stable ids:** `page_id` for clean and poisoned pages and `doc_id`, kept
   outside the detector input. The evaluator joins on them.
3. **Run logs** in the A6 `results/runs/*.jsonl` format with `top20`, `top5`,
   `gold_rank_*`, `poison_rank_*`, `cited`, `answer`, `correct`,
   `matches_target`, and the run configuration (generator, reranker on/off).
4. **`results/r2_correct.json`:** qids answered correctly under the undefended
   clean R2 baseline, per pipeline. This fixed set is the ASR denominator,
   with and without D1.
5. **Defense hook in the runner.** The proposal is to drop flagged pages after
   reranking and before generation:
   `d1_filter(top5_pages) -> (kept, dropped, d1_records)`. **Decisions the team
   must make (I have not chosen them):**
   * Backfill: replace a dropped page with rank 6 (and onward) from the
     reranked list, or generate from fewer than 5 pages?
   * Empty evidence (all top-5 flagged): abstain, answer closed-book, or keep
     the original top-5? This affects both ASR and clean accuracy.
   * Uncheckable pages: kept (current D1 behaviour: `flag=False`) or treated
     differently?
   * Is D1 applied to every top-5 page, or only to pages that contain a table?
   * Log `d1_records` (the `eval_record()` per page) alongside the run log.
6. **Shared utilities.** I will reuse `metrics.bootstrap_ci()` and
   `answer_match.numbers_match()` when they exist and will not re-implement them.
7. Confirm the package/import convention (`from src....`) and test runner (pytest).

## Needed from Person 2 (Gap 1 attacks)

* `attacks.jsonl` G1 rows (A6) that link `clean_page_id` ↔ `poison_page_id`,
  with `attack_type` in {`consistent_cell`, `naive_cell`, `unit`, `header`} and
  the `edit` record. **These are evaluator inputs only**. D1 never receives them.
* For each `naive_cell` attack, the id of its paired `consistent_cell` attack (the
  same cell change), so detection can be compared in pairs.
* Confirmation of how dashes are written back. The brief lists
  "dashes = 0/blank" for the attack parser, while D1 treats dashes as missing
  by default. A mismatch will appear as `missing_value` skips, not as false flags.
* The detectable-total statistic from `dependencies.py`, for comparison with
  D1's coverage (`n_checks.arithmetic > 0`).

## Needed from Persons 4 and 5

* Person 4: rendered poisoned pages and confirmation that Docling extracts the
  text layer as a table (or the pdfplumber fallback), which determines the D1
  input format.
* Person 5: `funnel.py` is shared. Agree on per-stage column names before
  either of us writes it.

## Results that are still blocked

| Result | Blocked on |
|---|---|
| D1 on observed parses (Docling or pdfplumber text) | P4 rendered pages + P1 parse |
| ASR with D1 as a filter | P1 attack run with `--drop-flags` |
| ASR by question type, stage funnel for Gap 1 | P1 attack run logs |
| Stealth pilot kappa and accuracy | P4 rendered pages + three teammates' ratings |

## D1 on P2 (vision-only)

**Not done and not claimed.** P2 has no text layer. Running D1 on P2 would need
an agreed extraction step (e.g. a VLM reading the table from the image), and
D1's results would then depend on that extractor's errors. The brief lists this
as an after-Nov-15 item. Do not describe D1 as evaluated on P2 until the input
and extraction procedure are agreed.

## Where my implementation departs from the brief (please confirm)

| Brief says | What I did | Why |
|---|---|---|
| Write labels into `examples.jsonl` | Labels go to `data/labels/qtypes.jsonl`, which `io.load_examples()` overlays (repo convention) | `examples.jsonl` is Person 1's file |
| ChartQA: "ask an LLM for unclear ones" | Flag `needs_review` for a person | No paid APIs or models in this milestone. Avoid an unvalidated labeller |
| "If accuracy isn't better than chance, the edits are stealthy" | Report the result as inconclusive, together with power | With n=40 pages, power is only 0.57 if raters are truly 65% accurate |
| Google Form, sent Sat 10 am | Selection, key and analysis are scripted (`scripts/stealth_study.py`). No form sent | The form needs rendered page images, which do not exist yet |
| Attack parser: dashes = 0/blank | D1: dashes = missing (opt-in flag to treat as 0) | Avoid silently assuming values |
