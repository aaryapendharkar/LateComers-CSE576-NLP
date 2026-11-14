D1 0.2.0, page text source: `standin`. Rates in % with 95% bootstrap CIs.

| Pages | n | Flagged | Newly flagged (clean twin not flagged) | Clean twin already flagged | Uncheckable |
|---|---|---|---|---|---|
| clean (false positives) | 500 | 10.2 [7.8, 13.0] (n=500) | | | 328 |
| naive_cell | 38 | 28.9 [15.8, 44.7] (n=38) | 10.5 [2.6, 21.1] (n=38) | 7 | 25 |
| consistent_cell | 38 | 18.4 [7.9, 31.6] (n=38) | 0.0 [0.0, 0.0] (n=38) | 7 | 25 |
| unit | 8 | 0.0 [0.0, 0.0] (n=8) | 0.0 [0.0, 0.0] (n=8) | 0 | 8 |
| header | 15 | 0.0 [0.0, 0.0] (n=15) | 0.0 [0.0, 0.0] (n=15) | 0 | 12 |

Coverage: D1 can run at least one check on 34.4 [30.4, 38.2] (n=500) of clean pages; among those pages the false-positive rate is 29.7 [22.7, 36.6] (n=172).

A rate of 0 of n has a degenerate bootstrap interval. Exact one-sided 95% upper bounds: n=8: 31.2%, n=15: 18.1%, n=38: 7.6%.

Naive vs consistent: 38 pairs. In 25 the edited cell feeds no total that the attack generator found, so the two poisoned pages are the same text. On the 13 pairs that differ: naive newly flagged 30.8 [7.7, 53.8] (n=13), consistent newly flagged 0.0 [0.0, 0.0] (n=13) (exact McNemar p = 0.125).

| D1 checks | Clean flagged | naive_cell newly flagged | consistent_cell newly flagged | unit newly flagged | header newly flagged |
|---|---|---|---|---|---|
| arithmetic + prose (default) | 10.2 [7.8, 13.0] (n=500) | 10.5 [2.6, 21.1] (n=38) | 0.0 [0.0, 0.0] (n=38) | 0.0 [0.0, 0.0] (n=8) | 0.0 [0.0, 0.0] (n=15) |
| arithmetic only | 10.0 [7.6, 12.8] (n=500) | 10.5 [2.6, 21.1] (n=38) | 0.0 [0.0, 0.0] (n=38) | 0.0 [0.0, 0.0] (n=8) | 0.0 [0.0, 0.0] (n=15) |
| prose only | 0.2 [0.0, 0.8] (n=500) | 0.0 [0.0, 0.0] (n=38) | 0.0 [0.0, 0.0] (n=38) | 0.0 [0.0, 0.0] (n=8) | 0.0 [0.0, 0.0] (n=15) |
