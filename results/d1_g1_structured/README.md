# D1 on the fixed Gap 1 edits — automated evaluation on structured source tables

**Label:** automated evaluation on structured source tables (FinQA table + prose
from `data/docs.jsonl`, before rendering or parsing). Human review is partial
(see below). This is not an observed-parser result and not an end-to-end
RAG/pipeline result.

## Inputs
- Edits: 99 Gap 1 records from `data/attacks/g1.jsonl` at Person 2 commit
  `504e5ddfef4e878e1f6ffb09baff4f27cf960d1b` (`origin/p2-table-attacks`).
- Source pages: `data/docs.jsonl` (blob `175010bca4e091f4b4e73c06120faf6a2be5e0ef`,
  identical at the D1 checkout and the attacks commit); 43 distinct originals,
  46 distinct questions.
- Detector: D1 0.2.0, default config (arithmetic + prose checks, dashes are missing).
- Edits applied with `src/common/edits.apply_edit(..., check_old=True)`.

## Command (from repository root)
```
python3 scripts/d1_g1_structured.py --out results/d1_g1_structured
```
The summary records the checkout used for this run. Rerunning at the recorded
revision reproduced both output files exactly. The generated `outcomes.jsonl` and `summary.json` were byte-identical to the
previously verified copies (99/99 records match).

## Outcomes (99 edited records)
| Outcome | Count | Meaning |
|---|---|---|
| New warning | 4 | edited page flagged; original page was not |
| Pre-existing warning | 14 | edited page flagged; original page was already flagged |
| Checks passed | 11 | applicable checks ran and passed |
| Uncheckable | 70 | no applicable D1 check |

New warnings (all `naive_cell`, original `checks_passed`): `G1_naive_cell_q0039`
(FBHS 2017 p22), `G1_naive_cell_q0058` (FIS 2016 p9), `G1_naive_cell_q0067`
(SNA 2013 p84), `G1_naive_cell_q0171` (CMCSA 2015 p67).

Pre-existing warnings are flags on pages D1 already flagged before editing, so
they are not evidence that D1 detected the edit. Of the 38 naive/consistent cell
pairs, 25 produce identical inputs to D1. See `summary.json` for per-type counts.

## Human review
Manually confirmed all 4 newly triggered warnings among the 99 edited records.

- `G1_naive_cell_q0039` (FBHS 2017 p22), reviewed by Vatsal Patel (Person 3) on
  2026-11-14: **D1 warning confirmed.** I checked the four segment sales figures
  in the `2017Net Sales(in millions)` column myself. The original sum was
  $5,283.3 million and matched the printed total. After the Cabinets edit
  ($2,467.1 → $2,720.3), the sum was $5,536.5 million while the printed total
  stayed at $5,283.3 million.
- `G1_naive_cell_q0058` (FIS 2016 p9), reviewed by Vatsal Patel (Person 3) on
  2026-11-14: **D1 warning confirmed.** The original 2015 values (IFS, GFS,
  Corporate & Other) summed to 6,596, matching the printed total. After GFS
  changed from 2,360 to 1,808, the sum was 6,044, so the printed total of
  6,596 was 552 too high.
- `G1_naive_cell_q0067` (SNA 2013 p84), reviewed by Vatsal Patel (Person 3) on
  2026-11-14: **D1 warning confirmed.** After the edit to 2013 trade and other
  accounts receivable ($546.5 → $660.8), the edited figures give a net of
  645.9 million (660.8 less the 14.9 allowance). The table still prints
  531.6 million, which is 114.3 million too low.
- `G1_naive_cell_q0171` (CMCSA 2015 p67), reviewed by Vatsal Patel (Person 3)
  on 2026-11-14: **D1 warning confirmed.** After the edit to 2015 cable
  distribution system ($2,424 → $2,904), the edited figures sum to 7,514
  million. The table still prints 7,034 million, which is 480 million too low.

## Pending
- Human review of the other 95 edited-record outcomes (pre-existing warnings,
  checks passed, uncheckable).
- Human review of the separate 50-page development audit
  (`results/dev_finqa/d1_dev_review_sheet.csv`); still pending.
- End-to-end pipeline evaluation (rendered/parsed tables, downstream RAG).
