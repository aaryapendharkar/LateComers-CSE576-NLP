# Person 3 integration handoff

Status as of 2026-11-11.

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

**Departures from the skeleton's Person 3 stubs (please confirm):**

| Skeleton | Implemented | Why |
|---|---|---|
| `reconcile.D1Result` TypedDict | Renamed to `D1Output`; `D1Result` is the diagnostics dataclass | No teammate code imports it; the richer result is needed by the evaluator |
| `sum_check(table, rel_tol=0.005, abs_tol=1.0)` | `sum_check(table)`, using the printed-precision rounding bound | A fixed ±1.0 hides edits on tables printed in billions; 0.5% hides small naive edits |
| `reconcile:` config keys `sum_rel_tol`, `sum_abs_tol`, `total_keywords: [.., net, sum, ..]` | `check_arithmetic`, `check_prose`, `dash_as_zero`; unknown keys raise | Tolerance is derived, not tuned; `net` rows are differences and are reported as not checked |
| `stealth.analyze(annotations)` with `annotator/item/label: edited/normal` | `analyze(ratings, key)` with `rater_id/item_id/rating: looks_edited/looks_normal` | Accuracy needs the private answer key; truth in rater rows would leak |
| `stealth.sample_pages`, `funnel.*`, `scripts/{eval_reconcile,stealth_study}.py` | Left as stubs (skipped tests) | Blocked on parsed pages, attacks, rendered pages and run logs |
| `scripts/label_qtypes.py` writes `data/labels/qtypes.jsonl` directly (README step 3) | Unchanged; it now works. `scripts/qtype_review_sheet.py` makes the review sheet | Labels written there are **unreviewed proposals** until the 30-label check is done |

## Smallest next handoffs (unblock the next stage)

* **Person 1:** about 10 **observed parsed pages** (Docling output, errors
  intact) from the clean corpus, plus a short note on the format: where the
  header row(s), the unit note ("in millions") and the surrounding text end up.
  With that I can replace the provisional adapter and measure D1 on observed
  parses instead of source JSON.
* **Person 2:** about 5 **matched triples** (clean / `naive_cell` /
  `consistent_cell` of the same cell edit, ideally plus one `unit` and one
  `header` attack) as A6 `docs.jsonl` rows, with the `attacks.jsonl` rows that
  link them. The link rows stay evaluator-only.

## Runs today without any teammate input

* D1 on synthetic fixtures: `python scripts/run_d1.py fixtures`
* D1 dry run on any A6 `docs.jsonl`: `python scripts/run_d1.py docs --docs <path> --out-dir <dir>`
  (clean structured JSON only: a development proxy)
* Question-type labels: `python scripts/label_qtypes.py` (team step 3, writes `data/labels/qtypes.jsonl`).
  Proposals and review sheet: `python scripts/qtype_review_sheet.py --examples <examples.jsonl> --out-dir <dir>`
* Stealth statistics functions in `src/analysis/stealth.py`. Input validation
  rejects duplicate (rater, item) votes, missing coverage and an incomplete
  key. No ratings exist yet.
* FinQA development audit (original train JSON, not observed parses):
  see [FINQA_DEV_AUDIT.md](FINQA_DEV_AUDIT.md).

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

## Results that are blocked until handoffs arrive

| Result | Blocked on |
|---|---|
| D1 false-positive rate on 500 clean pages (observed parse) | P1 parsed pages |
| D1 detection rate by attack type | P2 attacks + P4 rendering + P1 parse |
| Arithmetic-only / prose-only / combined comparison | same as above |
| ASR with D1 as a filter | P1 runner hook + the decisions above |
| ASR by question type | P1 run logs + r2_correct.json + reviewed labels |
| Stealth pilot kappa / accuracy | rendered pages + three teammates' ratings |
| Stage funnel for Gap 1 | P1 run logs |

## D1 on P2 (vision-only)

**Not done and not claimed.** P2 has no text layer. Running D1 on P2 would need
an agreed extraction step (e.g. a VLM reading the table from the image), and
D1's results would then depend on that extractor's errors. The brief lists this
as an after-Nov-15 item. Do not describe D1 as evaluated on P2 until the input
and extraction procedure are agreed.

## Where my implementation departs from the brief (please confirm)

| Brief says | What I did | Why |
|---|---|---|
| Write labels into `examples.jsonl` | Write `proposed_labels.jsonl` + review sheet | Do not overwrite shared annotations before review. Merge after the 30-label check |
| ChartQA: "ask an LLM for unclear ones" | Flag `needs_review` for a person | No paid APIs or models in this milestone. Avoid an unvalidated labeller |
| "If accuracy isn't better than chance, the edits are stealthy" | Report the result as inconclusive, together with power | With n=40 pages, power is only 0.57 if raters are truly 65% accurate |
| Google Form, sent Sat 10 am | Spec only (ANALYSIS_PLAN.md). No form created | Requires the team's go-ahead and real pages |
| Attack parser: dashes = 0/blank | D1: dashes = missing (opt-in flag to treat as 0) | Avoid silently assuming values |
