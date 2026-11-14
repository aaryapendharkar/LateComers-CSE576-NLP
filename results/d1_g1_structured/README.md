# D1 on the fixed Gap 1 edits — automated evaluation on structured source tables

**Label:** automated evaluation on structured source tables (FinQA table + prose
from `data/docs.jsonl`, before rendering or parsing). This is not a human-reviewed
result, not an observed-parser result, and not an end-to-end RAG/pipeline result.

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

## Pending
- Human review of these outcomes (none of the warnings has been inspected).
- End-to-end pipeline evaluation (rendered/parsed tables, downstream RAG).
