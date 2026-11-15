# D1 development audit on FinQA source tables (Person 3)

**Data label: DEVELOPMENT results on the original FinQA structured JSON (train
split).** These are **not** observed-parser (Docling) results, **not** attack
detection rates, and **not** downstream RAG results. No poisoned pages are
involved. A flag here means D1 found an internal contradiction in an unedited
source page, which is either a D1/adapter error or a genuine source
inconsistency. Reviewing which one it is happens in the review sheet.

## Source and provenance

| Item | Value |
|---|---|
| Source | https://github.com/czyssrs/FinQA, `dataset/train.json` only. No training stack or models were installed |
| Pinned commit | `0f16e2867befa6840783e58be38c9efb9229d742` |
| File | 78,216,616 bytes; sha256 `49f237eb9779b569473b26b08048867d04635a7cc39ad6a7a5664c55bb428db6`; git blob `a6c2c5a60f9abe3fba5a793cc4d9e1dee2e09209` (matches GitHub) |
| Local path | `data/raw/finqa/train.json` (not committed; listed in `.git/info/exclude`) |

Download command:

```bash
mkdir -p data/raw/finqa && curl -sSfL -o data/raw/finqa/train.json \
  https://raw.githubusercontent.com/czyssrs/FinQA/0f16e2867befa6840783e58be38c9efb9229d742/dataset/train.json
shasum -a 256 data/raw/finqa/train.json
```

**Schema (inspected before writing the adapter).** There is one record per
question: 6,251 records over 2,110 unique pages (`filename`, e.g.
`AAPL/2015/page_68.pdf`), 741 reports (ticker/year) and 135 tickers. Detector
fields:
* `pre_text` and `post_text`: lists of lower-cased, tokenized sentences, e.g.
  `$ 1.5 billion`, `( 23158 )`.
* `table_ori`: the table as originally formatted, a list of rows.

Evaluation-only fields, **never passed to D1**: `qa` (question, answer,
program, gold_inds, exe_ans, steps), `id`, `filename`, `table` (FinQA's
normalized table) and the retrieval fields. Records that share a `filename`
were checked and have identical page content.

**Adapter** (`d1_input.record_from_finqa`): projects a record onto
`{"table": {"header": table_ori[0], "rows": table_ori[1:]}, "pre_text", "post_text"}`.
That projection then goes through the same allowlist (`page_from_record`) as
every other input. Values, signs, currency marks and prose are passed
unchanged. There is no title or unit note. FinQA's "( in millions )" usually
sits in the last `pre_text` sentence, and the adapter **does not** move it into
the table. As a result, unit declarations are never invented, and scaled prose
comparisons need the scale to be stated in the table itself.

## Frozen sample (frozen before any D1 outcome was looked at)

`results/dev_finqa/sample_manifest.json`, committed on its own (commit `f1e7771`
on the provenance branch `p3-defense-analysis`) before the audit script existed:

* Unit: a unique page. Grouping: **source report = ticker/year, with at most one
  page per report**, so the 50 pages come from 50 different reports.
* Method: `random.Random(576).shuffle(sorted eligible pages)`, then pages are
  taken in that order, skipping any whose report was already used (1 skipped).
* Exclusions: **0** (every page has `table_ori`, `pre_text` and `post_text`).
* The manifest lists all 50 filenames with their source record ids.
* Reproduce with `python scripts/finqa_dev_sample.py --source data/raw/finqa/train.json --out <path>`.
  The script refuses to overwrite an existing manifest without `--force`.

**Held-out separation.** These 50 **reports** (not only pages) are development
data. Exclude them from any later held-out D1 evaluation. A future rule change
must be checked on a **new** frozen sample drawn from other reports.

## Commands

```bash
./.venv/bin/python scripts/finqa_dev_sample.py --source data/raw/finqa/train.json \
    --out results/dev_finqa/sample_manifest.json
./.venv/bin/python scripts/finqa_dev_audit.py --source data/raw/finqa/train.json \
    --manifest results/dev_finqa/sample_manifest.json --out-dir results/dev_finqa \
    --proposals results/dev_finqa/proposed_explanations.json
```

Outputs:
* `d1_dev_summary.json`: the counts below.
* `d1_dev_results.jsonl`: one row per page, with the `eval_record` for all three
  configs.
* `d1_dev_review_sheet.csv`: the review sheet.

D1 version 0.2.0, default config (`dash_as_zero=False`).

## Results (50 pages; every page accounted for)

| Config | Pages | With ≥1 arithmetic check | With ≥1 prose check | Flagged | Checks passed | Wholly uncheckable |
|---|---|---|---|---|---|---|
| arithmetic-only | 50 | 13 | 0 | 5 | 8 | 37 |
| prose-only | 50 | 0 | 1 | 1 | 0 | 49 |
| combined | 50 | 13 | 1 | 6 | 7 | 37 |

Combined: 28 arithmetic checks (6 failed) and 2 prose checks (1 failed). 844
prose numbers were in sentences that name no table row, so they were not checked.

**Skipped or ambiguous relationships** (items, with the number of pages in brackets):

| Code | Config | Items (pages) | Meaning |
|---|---|---|---|
| `ragged_table` | both | 10 (10) | Rows of different lengths (multi-row headers in `table_ori`); the whole table is skipped |
| `net_relationship_not_checked` | arith | 7 (7) | The total is a difference (`net ...`); sign convention unknown |
| `no_component_columns` | arith | 5 (3) | Total column with no component columns |
| `missing_value` | arith | 4 (2) | A component is blank or a dash; dashes are not treated as 0 |
| `total_scope_ambiguous` | arith | 1 (1) | PNC/2013 p.111: the same total is printed twice with alternative breakdowns, and labels cannot decide its scope |
| `no_component_rows` | arith | 1 (1) | Total row directly under the header |
| `total_not_numeric` | arith | 1 (1) | Total cell not parseable |
| `scope_qualifier` | prose | 33 (12) | Row label narrowed in the sentence ("net revenue", "revenue from ...") |
| `multiple_amounts_in_clause` | prose | 27 (4) | More than one amount in the clause |
| `no_period` | prose | 14 (7) | No single year that matches a column |
| `ambiguous_metric` | prose | 7 (6) | The sentence names several rows |
| `change_or_bound_language` | prose | 4 (2) | "increase of", "more than", ... |
| `table_scale_unknown` | prose | 1 (1) | Scaled prose, but no scale in the table |

**Wholly uncheckable (37, combined):**
* 25 have no total-labelled row or column and no aligned prose.
* 10 are ragged tables (multi-row headers).
* 1 has only a total with a missing component (BKR/2018).
* 1 has only a total directly under the header (GPN/2018).

Uncheckable pages are **not** flagged (`flag=False`). That policy is still to be
confirmed by the team.

**Flagged (6 pages, 7 failed checks). Proposed explanations, NOT human-reviewed:**

| Page | Check | Proposed cause |
|---|---|---|
| IPG/2016 p.24 | `Total` row = sum of monthly rows, in column "Average Price Paid per Share" | Non-additive column; D1 looks for non-additive words only in the total *row* label, not the column header |
| RSG/2005 p.26 (2 checks) | `Total` row in columns "(b) Average Price Paid per Share" and "(d) Maximum ... that May Yet Be Purchased" | Non-additive columns (an average and a running remaining balance), same cause |
| AAPL/2015 p.68 | `Total` row in column '$772' | `table_ori` has no header row; the adapter's first-row-as-header rule drops a data row, and the discrepancy equals that row |
| UAA/2016 p.82 | `Total future minimum lease payments` row in column '$114,857' | Same headerless-table cause |
| MMM/2005 p.81 | `Total` column in row '$492' | Same, and the table also has no label column |
| IP/2018 p.50 | prose "$1.4 billion in 2017" vs table $1,280M | The table excludes discontinued operations (stated in the sentence before it); D1's scope guard is sentence-local |

If confirmed, all six are **D1 or adapter errors on clean pages**, i.e. false
positives. They give **no** evidence of attack detection. The detector was
**not** tuned to remove them.

## Failure modes and unsupported cases surfaced

1. Header handling: headerless `table_ori` and multi-row headers (13/50 pages
   affected: 3 false flags + 10 ragged).
2. Non-additive columns are recognised by the total row's label only, not by
   column headers.
3. Prose scope is sentence-local: table-wide qualifiers are missed.
4. Prose coverage is very low (1/50 pages). Most of the cause is the deliberately
   conservative alignment and the unused "( in millions )" sentence in
   `pre_text`.
5. Totals without "total" in the label (25/50 pages have none) are not checked.
6. `$` vs `USD` is reported as ambiguous rather than equal; no currency
   conversion is done.
7. None of this measures behaviour on Docling parses, which may add parse
   errors.

## Completing the review sheet

Open `results/dev_finqa/d1_dev_review_sheet.csv` (51 rows):
* 7 `flagged` rows (one per failed check);
* 37 `wholly_uncheckable` rows;
* all 7 passing pages as `passing_sample` (fewer than the requested 10 passed;
  the selection is seeded with 576).

Each row shows:
* `table_ori`;
* the text immediately before the table, which is where the unit line usually is;
* the relationship and cells D1 used, with expected/observed/discrepancy/tolerance;
* the units diagnostic;
* the skip codes;
* a `proposed_explanation`, written by the assistant and **not reviewed**.

For each row:
1. Check the relationship against `table_ori`. Is the total really the sum of
   those cells? Is the header row the real header?
2. Check the units. Compare the table's scale and currency with the unit line
   in the preceding text and any prose number used.
3. Pick a `reviewer_verdict`: `true_inconsistency` / `source_or_layout_issue` /
   `d1_rule_error` / `correct_pass` / `correctly_uncheckable` /
   `should_be_checkable` / `unclear`. Then fill in the y/n/unclear columns, your
   initials, the date and notes.
4. Treat the proposed explanation as a hypothesis to accept or reject, not as
   the answer. If needed, look up the full record by `source_record_ids` in
   `train.json`.

The reviewer columns are empty in the delivered file. Nothing in it has been
human-reviewed.
