# Person 4: Aaron (Gap 2: page renderer + representation attacks)

## 1. Progress & implementation (1 paragraph)

I built the page renderer that every pipeline reads from, the ChartQA corpus, and the Gap 2 **propagation** condition. The conflict conditions are Person 5's, built on the same renderer. A rendered page has three representations: a page image (PNG, 150 dpi), a PDF text layer and a caption. Following A4, one layout pass places the IMAGE version and the TEXT version of the page at shared coordinates. reportlab draws the image version, pdftoppm rasterizes it, and the final PDF is that PNG as a full-page background with the text version's strings drawn invisibly (text render mode 3). The two layers therefore line up exactly but can say different things. Table pages contain the pre-text, a caption, the table and the post-text. The caption is built from the data: title or first header cell, unit, and the first and total rows ("key figures"). An edit therefore reaches the caption whenever it touches either row or updates a total. Chart pages are re-rendered from the ChartQA CSV (matplotlib, value labels on every mark) with a caption title and a "Source data: label: value; ..." note. Charts replace the clean page in place and are never added as new pages. For propagation, the source data is edited and the image, text layer and caption are all re-rendered from it. Tables use Person 2's consistent-cell edits. Charts move the asked-about value by 15–30% in the cell's own format, and max/min questions move outward so the edited bar stays the extreme. Docling (OCR off), our P1 parser, returns the TEXT values on a conflict page and still rebuilds the table structure. pdfplumber does the same.

## 2. Results

| Output | Count | Notes |
|---|---|---|
| FinQA clean pages | 500 | all fit one Letter page, no prose cut; 383 at 10.5 pt, smallest 7 pt (1 page) |
| ChartQA corpus | 300 charts | 100 question charts + 200 distractors (test split); 124 horizontal bar, 101 bar, 75 line |
| ChartQA questions | 100 | from 1,250 `test_human` questions: 396 not a simple chart, 583 filtered (color/position/arithmetic/counting), 161 answer not exactly one cell, 6 no plausible edit → 102 eligible charts |
| `propagate_table` rows + pages | 38 | one per consistent-cell edit; caption shows the edit on 33/38 |
| `propagate_chart` rows + pages | 50 | median value change 23.2% (14.3–29.9%) |

Rendering takes about 0.8 s per page on one CPU core (500 pages in 27 s with 16 workers). No GPU is needed.

## Sample outputs (2)

1. **Conflict table page** (`report/figures/p4_aaron_conflict_table.png`, JPM 2010 p.281, text-only condition). The image shows Loans **214.8** and total **$450.1**. Docling reads Loans **250.4** and total **$485.7** from the text layer, including in the caption ("Totalassetspledged: $485.7 (2010)").
2. **Propagated chart page** (`report/figures/p4_aaron_propagate_chart.png`, ChartQA `multi_col_100787`, c0041 "percentage of casual wine consumers in 2000"). Gold 43.4% → target 30.7%. The bar, its value label, the visible note and the text layer all show 30.7%.

## Challenges & next steps (2 bullets)

- ChartQA questions often refer to colors or positions ("the blue bar", "first bar"), and ChartQA CSVs carry no chart titles. Re-rendering would break such questions, so they are filtered out. Titles come from the CSV header, which leaves 4 of the 100 question charts captioned only "Figure 1." Multi-series line charts had colliding value labels, so multi-series data is drawn as grouped bars.
- Next: run the propagate and conflict rows through P1/P2/P3 with stage logging. Re-parse all pages with Docling (CPU, about 3 s per page). If time allows, add a propagation variant whose prose is also edited, so the edit reaches every number on the page.

## Individual contributions (3–5 bullets, matching your commits)

- `[P4] renderer v1`: `src/render/pdfpage.py`, `render_table_page.py` (shared two-layer layout, font-fit loop, data-derived captions); Docling/pdfplumber verification.
- `[P4] chart renderer + ChartQA selection and chart edits`: `render_chart_page.py`, `src/attacks/representation/charts.py`, `scripts/prepare_chartqa.py`.
- `[P4] Gap 2 propagation rows`: `src/attacks/representation/propagate.py`, `scripts/make_g2_propagation.py`, shared question selection with Person 5's conflict rows, parallel `render_clean_pages.py`.
- `[P4] outputs`: clean-page manifests (FinQA + ChartQA), chart docs/questions, 38 + 50 propagate rows.
- Tests: `tests/test_p4_gap2.py` (layers line up, chart edits, propagation rows, chart pages); the two A4 acceptance tests now pass.
