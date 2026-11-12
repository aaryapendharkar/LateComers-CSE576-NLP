# Small Edits, Wrong Answers

**Structured visual evidence poisoning of tables and charts in multimodal RAG.**
CSE 576 NLP, Fall 2026, Project #12 (mentor: Prof. Vivek Gupta).

We study an attacker who **edits a page that already exists**: one table cell (with totals kept consistent), a unit, a header, or the text layer behind a page image. Nothing new is added to the collection. Two research gaps:

| | Gap 1: consistent in-place table edits (RQ1) | Gap 2: image vs. text-layer disagreement (RQ3) |
|---|---|---|
| Attack | consistent vs. naive cell edits, unit, header | 2×2: image clean/poisoned × text layer clean/poisoned |
| Defense | D1 reconciliation filter (sums + table–text) | image–text consistency checker |
| Data | T2-RAGBench (FinQA) + FinQA programs | same FinQA pages + ChartQA |

Every run is logged by stage (retriever → reranker → generator), which answers RQ4.

## Team

| # | Name | Role |
|---|------|------|
| 1 | Aarya | Pipelines, evaluation harness, repo, report integration |
| 2 | Janhavi | Gap 1: table edit attacks |
| 3 | Vatsal | Gap 1: reconciliation defense, question types, stealth study, analysis |
| 4 | Aaron | Gap 2: page renderer + representation attacks |
| 5 | Disha | Gap 2: image–text consistency check, "which version wins" analysis |

**Before you write any code, read [CONTRIBUTING.md](CONTRIBUTING.md)**: file ownership, branches, and how to build against mock data.

## Quick start

```bash
git clone https://github.com/<org-or-user>/cse576-structured-poisoning.git
cd cse576-structured-poisoning
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-core.txt                    # light deps: enough for tests + mocks
pip install -r requirements.txt                         # full stack (GPU machine)
python scripts/check_env.py
pytest -rs                                              # your tests show as "skipped" until implemented
```

Dry-run the whole flow on hand-made mock data (no GPU, no downloads):

```bash
export CSE576_CONFIG=tests/fixtures/config.yaml
python scripts/run_baselines.py --pipelines P1 P3
python scripts/run_attacks.py --pipeline P1 --gap G1
python scripts/summarize.py --runs /tmp/cse576_test_runs/P1_G1.jsonl --out /tmp/cse576_test_runs/funnel.csv
unset CSE576_CONFIG
```

Mock numbers are meaningless; they only show that the plumbing works.

## Pipelines (victim systems)

| ID | Retriever sees | Generator sees |
|----|----------------|----------------|
| P1 text-parsed | PDF text layer via Docling (OCR off), BGE-M3 | parsed text of top-5 pages |
| P2 vision-native | page images, ColPali | page images of top-5 pages |
| P3 hybrid | RRF (k=60) of P1 + P2 | image + parsed text of each top-5 page |

All: top-20 retrieval → multimodal reranker (or off) → top-5 → one VLM generator, greedy decoding. Prompts are in `configs/prompts/`. **Index once, swap one page:** a poisoned run swaps a single clean page's embedding/content for the poisoned one (`run_query(..., swap={clean_id: poison_id})`).

## Reproducing the intermediate report (command sequence)

| Step | Owner | Command | Output |
|------|-------|---------|--------|
| 1 | P1 | `python scripts/prepare_finqa.py --inspect`, then `python scripts/prepare_finqa.py [--finqa-json data/raw/FinQA/test.json]` | `data/docs.jsonl`, `data/examples.jsonl` |
| 2 | P4 | `python scripts/render_clean_pages.py` | `data/pages/`, `data/manifests/pages_clean.jsonl` |
| 3 | P3 | `python scripts/label_qtypes.py` | `data/labels/qtypes.jsonl` |
| 4 | P1 | `python scripts/build_indexes.py --parse docling` then `--index P1 P2` | `data/parsed/`, `data/indexes/` |
| 5 | P1 | `python scripts/run_baselines.py --pipelines P1 P2` | `results/runs/*_R{1,2,3}_finqa.jsonl`, `results/r2_correct.json`, `results/baselines/table1_finqa.md` |
| 6 | P2 | `python scripts/make_g1_attacks.py` | `data/attacks/g1.jsonl`, `data/manifests/pages_g1.jsonl` |
| 7 | P4 | `python scripts/prepare_chartqa.py --chartqa-dir ...`, `python scripts/render_clean_pages.py --source chartqa`, `python scripts/make_g2_attacks.py` | chart docs/pages, `data/attacks/g2.jsonl` |
| 8 | P1 | `python scripts/build_indexes.py --parse docling` (new pages), `python scripts/run_attacks.py --pipeline P1 --gap G1` (and P2, G2) | `results/runs/P*_G*.jsonl` |
| 9 | P1 | `python scripts/summarize.py --runs results/runs/*_G1.jsonl --out results/gap1/funnel.csv` | funnel tables |
| 10 | P3 | `python scripts/eval_reconcile.py`, then `run_attacks.py ... --drop-flags results/gap1/d1_flags.jsonl --run-name G1_D1` | D1 tables |
| 11 | P5 | `python scripts/eval_img_text_check.py`, `python scripts/which_wins.py --runs results/runs/*_G2.jsonl` | checker + which-wins tables |

Hardware / runtime: *(Person 1 fills in on Saturday.)*

## Repository layout

```
configs/default.yaml      shared config (one section per owner); configs/local.yaml = your machine only
configs/prompts/          exact generator prompts (versioned, never edited in place)
data/                     small JSONL contract files (committed); raw/ pages/ parsed/ indexes/ gitignored
src/common/               schemas, io, answer_match, metrics, edits, tables, config      (P1)
src/data/                 FinQA / T2-RAGBench loading                                    (P1)
src/pipelines/            p1_text, p2_colpali, p3_hybrid, rerank, generate, run, mock    (P1)
src/render/               render_table_page, render_chart_page                           (P4)
src/attacks/tables/       numbers, finqa_program, dependencies, edits                    (P2)
src/attacks/representation/ conflict, charts                                             (P4)
src/defenses/             reconcile (P3), img_text_check (P5)
src/analysis/             qtypes, stealth, funnel (P3), which_wins (P5)
scripts/                  one runnable script per step (owner in each docstring)
results/                  small CSV/JSON results for the report (committed)
report/                   figures/ and contributions/ (one file per person)
tests/                    tests/common (P1), tests/test_p#_*.py (each person), fixtures/
```

## Shared formats and metrics

- JSONL formats (A6): `src/common/schemas.py`. Edit format: `src/common/edits.py`.
- Answer matching: `src/common/answer_match.numbers_match` (1% relative tolerance; `$ , %` stripped; `(x)` = −x; yes/no = 1/0; 12.4 ≡ 0.124).
- Metrics (A8) and 95% bootstrap CIs (1,000 resamples over questions): `src/common/metrics.py`.

## Changes from the proposal

See the "What changed" paragraph in the task briefs (A9). Model substitutions and the reranker status go here as they happen:

- *(e.g. "Generator: Qwen3.5-9B replaced by … because …")*
