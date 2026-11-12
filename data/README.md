# data/

Committed (small contract files, one writer each; see CONTRIBUTING.md §3):
`docs.jsonl`, `examples.jsonl` (P1) · `chart_docs.jsonl`, `chart_examples.jsonl` (P4) ·
`labels/qtypes.jsonl` (P3) · `manifests/pages_*.jsonl` (P2, P4) · `attacks/g1.jsonl` (P2), `attacks/g2.jsonl` (P4)

Gitignored (heavy; share via the team drive): `raw/` (downloads), `pages/` (rendered PDF/PNG/TXT),
`parsed/<docling|pdfplumber>/` (P1's parsed page text), `indexes/` (embeddings).

All paths stored inside JSONL records are repo-relative, so records work on every machine.
