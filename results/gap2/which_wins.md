Cells: % follows text / % follows image / % both layers (propagate) / % neither  (n)

| pipeline | propagate_table | text_only_table | image_only_table |
|---|---|---|---|
| P1 | 0 / 0 / 55 / 45 (n=38) | 55 / 29 / 0 / 16 (n=38) | 92 / 0 / 0 / 8 (n=38) |

With 95% bootstrap CIs:

| pipeline | reranker | condition | follows text | follows image | both | neither |
|---|---|---|---|---|---|---|
| P1 | on | propagate_table | 0.0 [0.0, 0.0] (n=38) | 0.0 [0.0, 0.0] (n=38) | 55.3 [39.5, 71.1] (n=38) | 44.7 [28.9, 60.5] (n=38) |
| P1 | on | text_only_table | 55.3 [39.5, 71.1] (n=38) | 28.9 [15.8, 44.7] (n=38) | 0.0 [0.0, 0.0] (n=38) | 15.8 [5.3, 28.9] (n=38) |
| P1 | on | image_only_table | 92.1 [84.1, 100.0] (n=38) | 0.0 [0.0, 0.0] (n=38) | 0.0 [0.0, 0.0] (n=38) | 7.9 [0.0, 15.9] (n=38) |
