# Person 1: Aarya (pipelines, evaluation harness, repo, report integration)

Draft. Replace every `[...]` with real values once the runs finish.

## 1. Progress & implementation

We built three victim RAG pipelines that share one evaluation harness. **P1 (text-parsed)** extracts each page's text layer with Docling (OCR off) [or: pdfplumber, because Docling did not recover the invisible-layer table] and retrieves with dense BGE-M3 embeddings (cosine similarity). **P2 (vision-native)** retrieves page images with ColPali ([checkpoint]) using late-interaction scoring over per-page multi-vector embeddings. **P3 (hybrid)** fuses the P1 and P2 rankings with reciprocal rank fusion (k = 60). Every pipeline retrieves the top 20 pages, reranks them to the top 5 with [Qwen3-VL-Reranker-2B / no reranker, see Changes], and passes those 5 pages to one vision-language generator ([model]) with greedy decoding. The generator sees parsed text (P1), page images (P2) or both (P3). It must answer in JSON with the pages it cited; the exact prompt is in `configs/prompts/generator_v1.txt`. Poisoned pages are evaluated by "index once, swap one page": clean pages are embedded once, and an attack run replaces only the target page's embedding and content, so every other page keeps its exact score. We checked that swapping a page with itself leaves the outputs unchanged. Every run logs the gold and poisoned page ranks after retrieval and after reranking, the citations, and the answer, so each failure can be traced to a stage (RQ4). Answers count as correct under a shared numeric match (1% relative tolerance; handles %, $, commas, accounting negatives, yes/no, and percent-vs-fraction). All rates come with 95% bootstrap confidence intervals (1,000 resamples over questions).

**Data.** 200 questions from the T2-RAGBench FinQA test split (context-independent rewrites of FinQA questions), a 500-document corpus (all gold documents plus [N] distractors; the test split has only 380 unique documents, so [120] distractors come from the dev split), and FinQA reasoning programs joined to [joined]/200 questions. Tables use FinQA's original-format table (`table_ori`) where it is rectangular, so rendered pages keep real formatting such as "$(4,614)" and "—".

**Hardware / runtime.** [GPU type, e.g. 1x A100 80GB on ASU Sol]; indexing [x] min; R2 on 200 questions [x] min per pipeline.

## 2. Results: Table 1 (clean baselines, FinQA, n = 200)

<!-- paste results/baselines/table1_finqa.md here -->

| Pipeline | R1 closed-book | R2 clean RAG | R3 oracle | Recall@5 | Recall@20 |
|---|---|---|---|---|---|
| P1 | [...] | [...] | [...] | [...] | [...] |
| P2 | [...] | [...] | [...] | [...] | [...] |

Figure 1: stage funnel (retrieved@20 → top-5 → cited → attack success) for each gap's main attack, P1 vs P2: `report/figures/p1_funnel.png` (from `results/gap*/funnel.csv`).

## Changes from the proposal (implementation)
- [Generator: Qwen3.5-9B replaced by ..., because ...]
- [Reranker off for the intermediate report, because ...]
- Corpus distractors drawn partly from the FinQA dev split (test split has 380 documents).

## Challenges & next steps
- [e.g. Docling and invisible-text tables / GPU memory for the 9B VLM]
- Next: second open model on a stratified subset; P3 for all runs; reranker on/off ablation.

## Individual contributions
- Designed and set up the GitHub repository: shared data formats (`src/common/schemas.py`), file-ownership workflow, CI, and mock fixtures so all five members could develop in parallel
- Built the evaluation harness: numeric answer matching, all A8 metrics with bootstrap CIs, resumable run logging with per-stage ranks
- Implemented the P1 (BGE-M3), P2 (ColPali) and P3 (RRF) pipelines, generator prompting/parsing, and the single-page swap mechanism
- Built the 500-doc / 200-question FinQA subset with joined reasoning programs; ran clean baselines R1–R3 [and the attack runs]
- Assembled the intermediate report and README
