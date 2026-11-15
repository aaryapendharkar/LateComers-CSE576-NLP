D1 0.2.0 diagnostics. Buckets are assigned by an automatic rule and are not human-reviewed.

| Cause of a clean flag (automatic bucket) | Pages |
|---|---|
| headerless_table | 17 |
| other | 16 |
| dash_artifact | 10 |
| non_additive | 8 |
| total flagged | 51 |

| Input problem in docs.jsonl | Docs (of 500) | Gold docs | G1 attacks on such docs |
|---|---|---|---|
| headerless_table | 42 | 15 | 17 |
| dash_artifact | 18 | 9 | 2 |

| D1 input (post-hoc diagnostic) | Clean FPR | Coverage | consistent_cell newly flagged | header newly flagged | naive_cell newly flagged | unit newly flagged |
|---|---|---|---|---|---|---|
| as_is | 10.2 [7.8, 13.0] (n=500) | 34.4 [30.4, 38.2] (n=500) | 0/38 | 0/15 | 4/38 | 0/8 |
| header_repair | 7.0 [4.8, 9.4] (n=500) | 34.8 [30.8, 39.0] (n=500) | 5/38 | 0/15 | 9/38 | 0/8 |
| dash_repair | 8.2 [6.0, 10.8] (n=500) | 34.4 [30.4, 38.2] (n=500) | 0/38 | 0/15 | 4/38 | 0/8 |
| both_repairs | 5.0 [3.2, 7.0] (n=500) | 34.8 [30.8, 39.0] (n=500) | 5/38 | 0/15 | 9/38 | 0/8 |

Filter cost on the clean run (P1_R2_finqa.jsonl, n=200): D1 would drop at least one top-5 page for 32.5 [26.0, 38.5] (n=200) of questions, and would drop the gold page for 9.5 [5.5, 13.0] (n=200) of all questions and 11.1 [4.2, 19.4] (n=72) of the questions the undefended system answers correctly.
