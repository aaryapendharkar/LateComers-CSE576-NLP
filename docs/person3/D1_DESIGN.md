# D1 reconciliation defense: design notes (Person 3)

Version 0.2.0 (2026-11-11). It fixes four problems found in an independent review
of 0.1.0: sign loss in prose comparisons, currency identity loss,
value-dependent total scope, and duplicate stealth ratings. Regression evidence
is in [evidence/](evidence/). The real-data development audit is in
[FINQA_DEV_AUDIT.md](FINQA_DEV_AUDIT.md).

Code: [src/defenses/reconcile.py](../../src/defenses/reconcile.py),
[d1_numbers.py](../../src/defenses/d1_numbers.py),
[d1_input.py](../../src/defenses/d1_input.py) (provisional adapter).

## What D1 does and does not claim

D1 looks for **internal contradictions** on one page: totals that do not add
up, and prose numbers that disagree with the table. A page that passes has
**no detected contradiction**. That does not show the page is correct. A
consistently edited table, with or without coordinated prose, passes by
construction (fixture cases 03 and 05).

## Public contract and outcomes

`reconcile(page) -> {"flag": bool, "reasons": [str, ...]}` (agreed in the brief).

| `D1Result.status` | `flag` | first reason starts with |
|---|---|---|
| `contradiction`: at least one check failed | `True` | `CONTRADICTION [arithmetic\|prose]` |
| `checks_passed`: at least one check ran, none failed | `False` | `NO_CONTRADICTION_FOUND` |
| `uncheckable`: no check could run | `False` | `NOT_CHECKABLE` |

`D1Result.eval_record()` returns per-check diagnostics for the evaluator:
relationship, cells, expected, observed, discrepancy, tolerance, and the
skipped items with reason codes. This is separate from the public contract.

Uncheckable pages are **not flagged**, so a filter keeps them. This is a policy
choice for the team to confirm (see HANDOFF.md). Evaluations must report the
uncheckable rate separately so that "not flagged" is never read as "verified".

## Numeric normalization (`d1_numbers.py`)

* Commas must form valid thousands groups. Anything else is unparseable.
* Precision is the number of printed decimals.
* Currency markers (`$`, `US$`, `€`, `£`, `¥`, and the codes `USD/EUR/GBP/JPY`
  as prefix or suffix) do not change the value. The cell keeps a canonical
  currency identity. Two different currencies in one cell make it unparseable.
  `$` and `USD` (and `¥`/`JPY`) are **ambiguous**, not equal. Nothing is ever
  converted between currencies.
* `(x)` and a leading minus mean negative. `(-x)` is rejected.
* `%` keeps percent-point values and marks the cell as a percentage.
* `thousand/million/billion` inside a cell is kept as the cell's own scale.
* `"" - — – n/a nm` are **missing**, never zero. `D1Config(dash_as_zero=True)`
  is an explicit opt-in for dashes only, and it is recorded in the output config.
* Table scale comes only from table-local text: title, unit note, header cells,
  and blank separator-row labels. Two different declared scales make the scale
  `ambiguous`. With no declaration it is `absent`. Both block scaled prose
  comparisons.

## Arithmetic checks

1. **Discovery is value-blind.** A row is a candidate total only when its label
   starts with `total`/`subtotal` or ends with `total`. Labels containing
   percent, per share, average, return, ratio, margin, `%` or "as a" are
   excluded. A column is a total when its header satisfies the same rule.
2. **Components** of a total row come from position:
   * H1 (contiguous): the non-total data rows directly above, up to the
     previous total, a blank separator row, a label ending in `:`, or the top.
   * H2 (nested): walking up, an earlier subtotal counts as one item and the
     rows it covers are skipped. This avoids counting a subtotal and its
     components twice.
   **The choice is made from layout and labels only, never from values**
   (`_TableView.scope`). Version 0.1.0 picked whichever hypothesis made more
   columns pass. Changing a grand total could therefore switch it to a
   narrower relationship that still added up (review finding 3).
   * No earlier subtotal above → H1.
   * The total directly follows a subtotal (no rows in between) → H2, the only
     structural reading.
   * Otherwise compare label "cores": the words left after dropping
     total/subtotal/and/of/the, with plural `s` stripped.
     * The total's core is contained in each subtotal's core ("assets" ⊂
       "current assets"), or either core is empty ("Subtotal", "Total"):
       **nested**, so H2.
     * The cores share no word ("services" vs "products"): **sibling groups**,
       so H1, and it must have ≥ 2 rows.
     * Anything else, or an earlier subtotal whose own scope is unresolved:
       skipped as **`total_scope_ambiguous`**. The skip appears in the public
       reasons, so a valid subtotal elsewhere cannot hide an unchecked grand
       total.
3. **Unsupported relationships are skipped, not passed.** Examples: `Less:` or
   `net of` components (sign convention), fewer than two components, missing or
   unparseable component cells, cells that mix percentages and scale words,
   cells marked with different or ambiguous currencies (`currency_mismatch`,
   `currency_ambiguous`), and
   labels starting with `net` (a difference, recorded as
   `net_relationship_not_checked`).
4. **Rounding rule.** A value printed with *d* decimals may be off by 0.5·10^-d.
   The tolerance is the sum of the half-units of every component plus the total.
   This is the worst-case bound when each printed value was rounded
   independently from an exact value. Arithmetic uses `Decimal`, so it is exact.

Trade-off: a label-only rule leaves some totals unchecked. On the FinQA
development sample, PNC/2013 p.111 prints the same total twice as two
alternative breakdowns, and is skipped as ambiguous rather than guessed.
Fixture 11 shows the intended nested behaviour: a leaf edit under a subtotal
breaks the subtotal, while the grand total still passes because it uses the
printed subtotal.

## Prose checks (conservative)

A prose number is compared with a cell only if **all** of the following hold:

1. **Metric:** the sentence names exactly one table row label (as a phrase, and
   the longest match wins: "total revenue" beats "revenue"). Several distinct
   rows give `ambiguous_metric`.
2. **Scope:** the label is not narrowed. The previous word must be one of
   the/our/its/their/consolidated/company's, or a punctuation mark. The next
   word must not be from/of/for/attributable/related/... Otherwise the result
   is `scope_qualifier` ("net revenue", "revenue from services").
3. **Clause:** the sentence is split at `;`, `, `, compared to/with, versus,
   from, to, and, while, whereas. The number's clause must contain only that
   one amount and no change or bound words (increase, by, more than, nearly, ...).
4. **Period:** the clause names exactly one year. If it names none, the
   sentence may supply the year only when the sentence has exactly one year
   and one amount. The year must match exactly one column header.
5. **Unit:** percent is compared with percent. Amounts need a scale word in
   the prose and a known table scale (or a cell scale word). Per-share rows
   under "except per share" are skipped.
6. **Sign:** values are compared **with their printed signs**. Prose signs
   are `-$5`, `$-5`, `−$5`, `$(5)`, or `$ ( 5 )` in FinQA's tokenized text.
   If the two signs differ and the sentence or row label contains magnitude
   wording (loss, used, paid, expense, cost, charge, outflow, dividend, ...),
   the claim is skipped as `sign_semantics_unsupported`, because "a loss of
   $150 million" may describe a printed (150). Without such wording, differing
   signs are a contradiction. (0.1.0 compared absolute values: review
   finding 1.)
7. **Currency:** the prose currency (`$`, `US$`, `€`, `£`, `¥`, codes, or a
   trailing "dollars/euros/pounds sterling/yen") is compared with the cell's
   own currency or, if the cell has none, with every currency stated in the
   table (cell markers plus title/unit note/header declarations). A mismatch
   or an ambiguous pair is skipped (`currency_mismatch`/`currency_ambiguous`).
   If only one side states a currency, the check runs and the explanation
   says "Currency is stated only in the ...".
8. The tolerance is the prose half-unit times its scale plus the cell half-unit
   times its scale (e.g. "$1.5 billion" → ±$50M).

A shared number alone never counts as alignment. Numbers in sentences with no
row label are counted in `unaligned_prose_numbers` but not checked.

## Leakage controls

* `ParsedPage` has no id fields. Page ids such as `<doc>__G1_consistent_q0001`
  encode the attack type, so D1 never receives them.
* `page_from_record()` accepts only `table`, `pre_text`, `post_text` and `text`,
  and only `title/unit_note/header/rows` inside `table`. Any other key raises
  `DetectorInputError`, which is tested for `target_answer`, `attack_type`,
  `edit`, `gold_answer`, `page_id`, `variant` and `also_changed`.
* `scripts/run_d1.py` projects records onto those fields before calling D1.
  Expected outcomes stay on the evaluator side.

## Known limitations

* Cannot detect a consistent edit unless the prose contradicts it, and cannot
  detect coordinated table and prose edits at all.
* Recognizes totals by label only. Totals labelled "Revenue" (no "total") or
  net/difference rows are not checked.
* A sign flip is not checked against prose when the wording describes a
  magnitude (`sign_semantics_unsupported`). Arithmetic still catches it when
  a total depends on the cell.
* Non-additive columns are not recognised from their **header**. The exclusion
  list (average, per share, ratio, ...) applies only to the total row's label.
  Two of six FinQA development flags have this cause (an average price paid per
  share column, and a remaining-authorisation column).
* Prose scope qualifiers are detected only next to the row label in the same
  sentence. Table-wide qualifiers in the preceding sentence ("excluding
  discontinued operations") are missed (one FinQA development flag).
* Prose alignment is English and keyword-based, with no coreference ("it was
  $1.2 billion") and no multi-row phrasing.
* Multi-row headers, merged cells, and tables transposed so that years are rows
  are unsupported. Ragged rows make the whole table uncheckable (10/50 FinQA
  development pages).
* The FinQA adapter takes the first `table_ori` row as the header. FinQA tables
  without a header row (and one-row horizontal tables without a label column)
  are misread: three of six development flags have this cause.
* The markdown adapter is provisional and has not been tested on real Docling
  output.
* Behaviour on observed (Docling) parses is **unmeasured**. On 50 original FinQA
  train pages: 13 had an arithmetic check, 1 a prose check, 37 were wholly
  uncheckable, and 6 were flagged. The proposed explanations for all 6 flags are
  adapter/rule limitations, not inconsistencies, and are awaiting human review.
