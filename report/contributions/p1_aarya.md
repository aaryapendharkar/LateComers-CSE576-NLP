# Person 1: Aarya (pipelines, evaluation harness, repo, report integration)

Draft. Replace every `[...]` with real values once the runs finish.

## 1. Progress & implementation

We built three victim RAG pipelines that share one evaluation harness. **P1 (text-parsed)** extracts each page's text layer with Docling (OCR off) [or: pdfplumber, because Docling did not recover the invisible-layer table] and retrieves with dense BGE-M3 embeddings (cosine similarity). **P2 (vision-native)** retrieves page images with ColPali ([checkpoint]) using late-interaction scoring over per-page multi-vector embeddings. **P3 (hybrid)** fuses the P1 and P2 rankings with reciprocal rank fusion (k = 60). Every pipeline retrieves the top 20 pages, reranks them to the top 5 with [Qwen3-VL-Reranker-2B / no reranker, see Changes], and passes those 5 pages to one vision-language generator (Qwen3-VL-4B-Instruct, see Changes) with greedy decoding. The generator sees parsed text (P1), page images (P2) or both (P3). It must answer in JSON with the pages it cited; the exact prompt is in `configs/prompts/generator_v1.txt`. Poisoned pages are evaluated by "index once, swap one page": clean pages are embedded once, and an attack run replaces only the target page's embedding and content, so every other page keeps its exact score. We checked that swapping a page with itself leaves the outputs unchanged. Every run logs the gold and poisoned page ranks after retrieval and after reranking, the citations, and the answer, so each failure can be traced to a stage (RQ4). Answers count as correct under a shared numeric match (1% relative tolerance; handles %, $, commas, accounting negatives, yes/no, and percent-vs-fraction). All rates come with 95% bootstrap confidence intervals (1,000 resamples over questions).

**Data.** 200 questions from the T2-RAGBench FinQA test split (context-independent rewrites of FinQA questions), a 500-document corpus (all gold documents plus 1 distractors; the test split has only 380 unique documents, so [120] distractors come from the dev split), and FinQA reasoning programs joined to [joined]/200 questions. Tables use FinQA's original-format table (`table_ori`) where it is rectangular, so rendered pages keep real formatting such as "$(4,614)" and "—".

**Hardware / runtime.** Google Colab, 1x NVIDIA T4 (15 GB). Embedding the 500 pages with BGE-M3: about 1 min. P1 on 200 questions: R1 6 min (~1.8 s/question), R2 63 min (~19 s/question, 5 pages), R3 18 min (~5 s/question, 1 page).

## 2. Results: Table 1 (clean baselines, FinQA, n = 200)

<!-- paste results/baselines/table1_finqa.md here -->

Accuracy and gold-page recall in %, with 95% bootstrap CIs (1,000 resamples over questions). Generator: Qwen3-VL-4B-Instruct; reranker off; P1 page text from the document text (Docling-parsed PDFs pending the renderer).

| Pipeline | R1 closed-book | R2 clean RAG | R3 oracle | Recall@5 | Recall@20 |
|---|---|---|---|---|---|
| P1 | 9.0 [5.5, 13.0] | 36.0 [29.5, 42.0] | 49.5 [43.0, 56.0] | 88.5 [84.0, 92.5] | 94.5 [91.0, 97.5] |
| P2 | [pending renderer] | | | | |

Reading the table: retrieval is not the bottleneck (the gold page is in the top 5 for 88.5% of questions), but the generator answers only 36% correctly with retrieval and 49.5% even when handed the right page, so most errors are reasoning/arithmetic errors of the 4B model, consistent with T2-RAGBench being hard for open models. R1 (9%) is above zero mainly because ~30 of the 200 rewritten questions state the needed numbers in the question itself. 72 questions are R2-correct for P1; ASR is computed over these.

Figure 1: stage funnel (retrieved@20 → top-5 → cited → attack success) for each gap's main attack, P1 vs P2: `report/figures/p1_funnel.png` (from `results/gap*/funnel.csv`).

## Changes from the proposal (implementation)
- Generator: Qwen3.5-9B (proposal) replaced by Qwen3-VL-4B-Instruct [or -8B on an A100], same Qwen family. Qwen3.5's hybrid Gated-DeltaNet layers need optimized kernels (flash-linear-attention, causal-conv1d) that were not available on our Colab T4 GPU (15 GB); without them a single question took ~5 minutes, and the 5-page prompt ran out of GPU memory. Qwen3-VL uses standard attention and answers in seconds. Thinking mode is off; greedy decoding.
- Reranker off for the intermediate report (Qwen3-VL-Reranker-2B planned for the final report); top-5 = retriever's top-5. The brief allows this.
- To fit the T4's 15 GB, each page's text is capped at 2,000 characters (median page ≈ 3,900; at 4,000 every 5-page prompt ran out of memory): the table is always kept whole and only the surrounding prose is trimmed. Page images are downscaled to ≤ 300k pixels. A page that still runs out of memory is retried at half size; this happened on [N] of 200 questions (count "shrunk" in the run logs).
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
