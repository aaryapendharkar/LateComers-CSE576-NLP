\# Person 2: Janhavi (Gap 1: table edit attacks)



\## 1. Progress \& implementation



Gap 1 attacks work by editing one already-retrieved page in place and asking whether the

victim system's answer follows the edit. Four pieces make that possible. \*\*`numbers.py`\*\*

parses every real table-cell format found by scanning all 500 documents (plain, `$` prefix,

`%` suffix, parenthesised negatives with the `%` inside or outside, FinQA's "value then

repeated magnitude in parentheses" footnote style, and dashes for blank cells) and can write

a new value back in the \*same\* style, so an edited cell still looks like it belongs on the

page. \*\*`finqa\_program.py`\*\* executes FinQA's reasoning programs (`add/subtract/multiply/

divide/exp/greater`, plus the row-reducing `table\_\*` ops) against a table, and maps every

numeric argument back to the exact table cell it came from (or marks it a constant,

a step reference, or unmatched/ambiguous "text") — this argument-to-cell map is what tells

an attack which cells are actually safe to edit. \*\*`dependencies.py`\*\* finds every

total/subtotal in a table by checking the arithmetic (not just the label), on \*both\* axes —

column totals ("Total revenue" = sum of the rows above it) and row totals (a "total" column

that sums the other columns in that row) — and builds the dependency graph used to keep an

edit internally consistent, including totals of totals and totals that cascade across axes.

\*\*`edits.py`\*\* uses all three to generate the four G1 attack types: `consistent\_cell` (edit

one program-read cell by ±5–25%, then propagate the same change through every dependent

total so the page's own arithmetic still reconciles — computed by re-running the \*original\*

program against the fully edited table, which also catches and discards edits that

mathematically cancel out), `naive\_cell` (the B1 baseline: the identical cell edit, but with

the totals left stale, so the page no longer reconciles — used to test whether a

reconciliation defense can tell the two apart), `unit` (rescale the table's unit note, e.g.

"in millions" → "in billions", keeping edits only where the program's answer is itself an

amount, not a ratio), and `header` (swap two year-column \*labels\* only, matching how

`common/edits.py`'s header edit actually works — the deceptive effect is computed with a

throwaway scratch table that swaps the \*data\* instead, since that is mathematically

identical to what a reader misled by the swapped labels would see). Every generated edit is

only kept if its target answer differs from gold by more than 5% relative (or flips a

yes/no), using the project's one shared `numbers\_match` definition of "same answer" rather

than a second copy of it.



\## 2. Results



\*\*Table 2a — data-layer validation (FinQA, full corpus, n = 500 docs / 200 questions).\*\*



| Component | Check | Result |

|---|---|---|

| `numbers.py` | round-trip parse → format → re-parse, every numeric cell | 7,284 / 7,284 cells match exactly (0 mismatches); 2,807 non-numeric cells (dashes, text); \~6 cells with a unit word glued on ("5.0 years") are not parsed (documented gap) |

| `finqa\_program.py` | re-executing each question's program on its clean table reproduces gold | 199 / 200 (99.5%); the one miss is `program: null` in the source data, not an executor error |

| `dependencies.py` | tables with ≥ 1 arithmetic-verified total/subtotal | 324 / 500 (64.8%); 862 column-axis + 271 row-axis relations found; cross-axis cascades (a total of totals, on the other axis) verified by hand on `finqa\_FIS\_2016\_p45` |



\*\*Table 2b — final Gap 1 attack set\*\* (filtered to the 72 / 200 questions pipeline P1

answers correctly on the clean page, `results/r2\_correct.json`, so a post-poison wrong

answer is attributable to the attack and not to baseline model error):



| Attack type | Eligible | Generated | Notes |

|---|---|---|---|

| `consistent\_cell` | 72 (all have a program) | 38 (52.8%) | median edit size 16.1% relative (range 5–25%, matching the configured band) |

| `naive\_cell` | — | 38 | paired 1:1 with `consistent\_cell`; in 8 / 38 pairs the independently-recomputed target \*differs\* from the consistent target, because the program itself reads a total that only the consistent edit keeps correct (see sample output below) |

| `header` | 27 (two year columns, question mentions one) | 15 (55.6%) | |

| `unit` | 9 (has a unit-scale word, program has no `divide` step) | 8 (88.9%) | |

| \*\*Total\*\* | | \*\*99\*\* | all round-trip through `Attack.validate()` and `apply\_edit()` cleanly against the real docs |



Unfiltered (all 200 questions, for comparison / sanity check only — not the set used for the

real experiment): 156 attacks (50 + 50 + 35 + 21), same per-type pattern.



\## Sample outputs



\*\*1. `consistent\_cell` vs. `naive\_cell` on the same edit — showing why they can disagree.\*\*

`q0014` (`finqa\_JPM\_2010\_p281`), program `divide(214.8, 450.1)`, gold `0.4772`. The edited

cell (214.8 → 250.4) also feeds a total the program reads directly (450.1 → 485.7):

```

consistent\_cell: edit.old=214.8 -> edit.new=250.4, also\_changed=\[\[4,1,"$450.1","$485.7"]]

&#x20;                 target\_answer = 0.515545   (divide(250.4, 485.7), the internally-consistent answer)

naive\_cell:       edit.old=214.8 -> edit.new=250.4, also\_changed=\[]   (total left stale at 450.1)

&#x20;                 target\_answer = 0.556321   (divide(250.4, 450.1), a different wrong answer)

```

This is exactly the case the design has to handle: the two attacks make the \*identical\* edit

to the page, but because the program reads both the edited cell and its dependent total, a

defense that only checks "does the page's own math still add up" would need the \*correct\*,

internally-consistent target (0.515545) to evaluate `consistent\_cell` fairly — reusing

`naive\_cell`'s or a cached target would silently grade it wrong.



\*\*2. `header` on `q0014`'s own page.\*\* Two year columns are swapped (data never moves, only

the label text, matching how `common/edits.py`'s header edit works):

```

edit = {"field": "header", "old": \["December 31, (in billions)", "2010", "2009"],

&#x20;                            "new": \["December 31, (in billions)", "2009", "2010"]}

target\_answer = 0.543396   (gold 0.477227 for the question, which names "2010")

```



\## Challenges \& next steps

\- A real, found-and-documented limitation in `dependencies.py`'s row-axis total detection:

&#x20; on `finqa\_SLB\_2012\_p56`, a "total column" is coincidentally flagged because one of its

&#x20; "other" columns happens to be zero/dash across a whole block of rows, producing a row total

&#x20; that reconciles by accident rather than by real structure. Flagged here rather than

&#x20; engineered around under the deadline; next step would be requiring the reconciling columns

&#x20; to be non-trivial (not all zero) across the matched rows.

\- The one gold-reproduction miss (`q0072`, `program: null`) and the \~6 unparsed unit-suffixed

&#x20; cells in `numbers.py` are both data gaps, not logic bugs — worth a one-line mention if the

&#x20; final report asks for an overall drop-rate number.



\## Individual contributions

\- Implemented `src/attacks/tables/numbers.py`: table-cell number parsing/formatting that

&#x20; preserves original style, validated to zero round-trip errors across all 7,284 real numeric

&#x20; cells in the corpus.

\- Implemented `src/attacks/tables/finqa\_program.py`: the FinQA program executor and the

&#x20; argument-to-table-cell mapper every attack builds on; 99.5% gold-answer reproduction on the

&#x20; real 200-question set.

\- Implemented `src/attacks/tables/dependencies.py`: total/subtotal detection on both table

&#x20; axes (by label and by arithmetic) and the cascading dependency graph used to keep a

&#x20; `consistent\_cell` edit's totals correct, including totals of totals; found and documented a

&#x20; row-axis false-positive edge case.

\- Implemented `src/attacks/tables/edits.py`: all four G1 attack generators

&#x20; (`consistent\_cell`, `naive\_cell`, `unit`, `header`), the shared `keep\_edit` filter, and

&#x20; `generate\_all`; ran the real generation producing the final 99-attack `data/attacks/g1.jsonl`

&#x20; filtered to `results/r2\_correct.json`.

\- Wrote `tests/test\_p2\_table\_attacks.py`'s acceptance tests to green and kept the full suite

&#x20; passing throughout (`50 passed, 5 skipped` — the skips are teammates' own not-yet-done work).

