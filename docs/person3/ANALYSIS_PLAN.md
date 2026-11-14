# Person 3 analysis plan

This file is the plan, written before any real data existed. No numbers in it
are results. Results and what has been run so far are in [STATUS.md](STATUS.md)
and `report/contributions/p3_vatsal.md`.

## Shared conventions

* Unit of resampling: the **question** for ASR and the **page** for detection,
  following the brief (1,000 bootstrap resamples, 95% CI via Person 1's
  `metrics.bootstrap_ci()`). Keep `doc_id` in every row. A document can be
  the source of several questions and paired variants, so also report a
  doc-clustered bootstrap as a sensitivity check when a document contributes more
  than one item.
* Every D1 row records `input_kind` (`observed_parse` vs `clean_structured_json`)
  and the full `D1Config`. Only `observed_parse` rows are reported as pipeline
  results.
* Report three D1 outcomes everywhere (contradiction / checks_passed /
  uncheckable), not only flag rates.

## 1. False-positive rate on 500 clean FinQA pages

* Input: P1's observed parse of each clean page.
* FPR = flagged / 500, with CI. Also report the uncheckable rate and the
  rate at which at least one check ran (coverage).
* Hand-inspect every clean flag and categorize it: rounding beyond the bound,
  parse error, label heuristic wrong (e.g. a "total" that is not a sum),
  misaligned prose, or a genuine inconsistency in the source report. Report the counts.
* The `clean_structured_json` dry run (docs.jsonl) can be reported only as a
  development proxy that isolates parse-induced FPs from heuristic FPs.

## 2. Detection by attack type

* For each `attack_type` (`naive_cell`, `consistent_cell`, `unit`, `header`):
  detection rate = flagged poisoned pages / attacked pages, with CI.
* Paired view: for each naive/consistent pair (the same cell change), a 2×2 of
  flagged/not flagged. Use McNemar's exact test on the discordant pairs.
* Report detection **among pages where a relevant check ran** and among all
  pages, because the denominators differ.
* Expected pattern (a hypothesis, not a result): naive is caught by arithmetic
  when the edited cell feeds a labelled total. Consistent edits are missed unless
  the prose contradicts them. Unit and header edits are caught only through the prose.

## 3. Arithmetic-only vs prose-only vs combined

Run `D1Config(check_prose=False)`, `D1Config(check_arithmetic=False)`, and the
default on the same pages (`--no-prose` / `--no-arithmetic` in `scripts/run_d1.py`).
Report detection and FPR for each. Same pages and same denominators.

## 4. Question-type breakdowns

1. Run `scripts/qtype_review_sheet.py` on the real `examples.jsonl` (200 FinQA, 100 ChartQA).
   (`scripts/label_qtypes.py` writes the same rule labels to `data/labels/qtypes.jsonl`;
   treat them as unreviewed until this check is done.)
2. Two teammates fill `reviewer_label` on the 30-item `random_agreement_sample`
   rows independently. Report raw agreement and Cohen's kappa against the rules,
   and each reviewer against the other if both review. Resolve `flagged_only` rows,
   but exclude them from the agreement estimate.
3. Only after review, hand the labels to Person 1 to merge into `examples.jsonl`.
4. ASR by question type × pipeline, with CIs. Expect some cells to be small.
   Report n and do not interpret cells with n < 10.

## 5. Stealth pilot (40 page images: 20 clean, 20 poisoned)

**Selection.** 20 poisoned pages (10 `consistent_cell`, 10 `naive_cell`, from
distinct documents) and 20 clean pages from **other** documents, so that no
clean twin is shown. Seeded shuffle.

**Rating sheet (shown to raters):** `item_id` (random opaque id such as
`S07`), image only. No filenames, page ids or conditions. One question:
"Does this page look edited?" → `looks_edited` / `looks_normal`. Optional free
text "what looked off". Raters are Persons 1, 4, 5 (who did not create the edits),
rating independently without discussion.

**Answer key (kept by Person 3, never shared):** `item_id, page_id, doc_id,
is_poisoned, condition`.

**Collected ratings file:** `rater_id, item_id, rating, comment`.

**Input validation (runs before any statistic; raises `StealthInputError`):**
the ratings and key must be non-empty, with all fields present and
`is_poisoned` a boolean. Each answer-key `item_id` must be unique. Every rated
item must be in the key, and every rating must be `looks_edited`/`looks_normal`.
Each (rater, item) pair may appear **once**: a repeated vote is rejected, never
counted twice. Every key item must be rated, and by exactly `raters_per_item`
distinct raters (default 3). The output records `raters_per_item` and
`n_distinct_raters`.

**Analysis (`src/analysis/stealth.analyze`):**
* Fleiss' kappa across the three raters (agreement, not accuracy).
* Primary test: one majority-vote decision per **page** (n = 40), exact one-sided
  binomial against 0.5. The 120 ratings are not independent.
* Per-rater sensitivity (poisoned called edited) and specificity, because
  "looks edited" bias can inflate or deflate accuracy.
* Split by consistent vs naive (10 each). Descriptive only, since n is tiny.
* **Power** (computed with `stealth.power`): significance needs ≥ 26/40 correct.
  If raters are truly 65% accurate, the test detects it with probability ≈ 0.57.
  At 75%, ≈ 0.95. A non-significant result is therefore **inconclusive**. Write
  "we found no evidence that raters could distinguish..." and never "the edits
  are undetectable".

## 6. Gap 1 stage analysis (funnel; shared with Person 5)

From P1's run logs, for each pipeline × attack_type (and × question type):

| Stage | Definition (A8) | Denominator |
|---|---|---|
| retrieved@20 | poisoned page in `top20` | attacked questions |
| reranked@5 | poisoned page in `top5` | attacked questions |
| cited | poisoned page in `cited` | questions where it reached top-5 |
| target answer | `matches_target` | **R2-correct set** (fixed) |

* Keep the stages separate. A target answer can occur **without** a citation
  (the generator may not cite, or may cite another page). Report
  `matches_target ∧ ¬cited` explicitly.
* Compare the poisoned page's retrieval rank with the clean page's rank for the
  same question (rank change, A8).
* ASR denominator is fixed to the undefended clean R2-correct qids per pipeline
  (`r2_correct.json`). With D1 as a filter, use the **same** denominator. Do not
  recompute it on the defended system. Report the change in clean accuracy
  caused by D1 separately.
* Pick 2 concrete examples (question, edit, answer, citation) after the run, not
  before.

## Contribution framing (for the report)

* **Established techniques** (not our contribution): footing / cross-footing
  checks of financial tables, numeric fact verification against text, and
  rule-based question typing.
* **Our experimental questions:** do consistency-preserving in-place edits
  evade a reconciliation check that catches naive edits, and at which RAG
  stage do Gap 1 attacks succeed?
* **Potential contributions, still needing evidence and a literature review:** a
  measured detection gap between naive and consistent edits under the observed
  parse, and a stage-level account of where in-place table edits succeed. No
  novelty claims are made until the related-work search is done.
