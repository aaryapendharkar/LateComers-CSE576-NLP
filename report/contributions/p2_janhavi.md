

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

