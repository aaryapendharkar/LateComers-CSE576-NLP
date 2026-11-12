"""Multimodal reranker: top-20 -> top-5. OWNER: Person 1.

Plan from the brief: Qwen3-VL-Reranker-2B. If it isn't working by Fri noon, run
with the reranker OFF (``NoReranker``) for the intermediate report and note it.
"""

from __future__ import annotations

from .generate import PageInput


class NoReranker:
    """Reranker off: keep the retriever's order and truncate."""

    name = "none"

    def rerank(self, question: str, pages: list[PageInput], k: int) -> list[str]:
        return [p.page_id for p in pages[:k]]


class QwenVLReranker:
    """TODO (Person 1, Thu/Fri): implement with the official usage snippet.

    Check the model card for Qwen/Qwen3-VL-Reranker-2B (exact id, loading
    class, input format for image+text documents, how the relevance score is
    read out). Implement ``score`` and keep ``rerank`` as is.
    """

    def __init__(self, model_name: str, device: str = "cuda", dtype: str = "bfloat16"):
        self.name = model_name
        self.device, self.dtype = device, dtype

    def score(self, question: str, pages: list[PageInput]) -> list[float]:
        raise NotImplementedError(
            "QwenVLReranker.score: follow the model card usage snippet, or set "
            "models.reranker: null to run with the reranker off")

    def rerank(self, question: str, pages: list[PageInput], k: int) -> list[str]:
        scores = self.score(question, pages)
        order = sorted(range(len(pages)), key=lambda i: (-scores[i], i))
        return [pages[i].page_id for i in order[:k]]
