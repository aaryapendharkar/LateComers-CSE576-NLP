"""Mock backend: no GPU, no downloads. OWNER: Person 1.

Lets every teammate run the full flow (retrieve -> rerank -> generate -> log)
on a laptop or in CI, and lets tests check the swap mechanism. Numbers from the
mock backend are meaningless; never report them.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from typing import Any

from .base import Retriever
from .generate import GenerationResult, PageInput

_TOK = re.compile(r"[a-z]+|\d+(?:[.,]\d+)*")


def _tokens(text: str) -> list[str]:
    return _TOK.findall(text.lower())


class MockRetriever(Retriever):
    """Bag-of-words cosine over page text. ``name`` lets P1/P2 mocks coexist."""

    def __init__(self, store, name: str = "mock"):
        self.name = name
        super().__init__(store, cache_dir=None)

    def embed_pages(self, page_ids: list[str]) -> list[Any]:
        return [Counter(_tokens(self.store.get(p).text)) for p in page_ids]

    def embed_query(self, query: str) -> Any:
        return Counter(_tokens(query))

    def score(self, q_emb: Any, page_embs: list[Any]) -> list[float]:
        qn = math.sqrt(sum(v * v for v in q_emb.values())) or 1.0
        out = []
        for e in page_embs:
            dot = sum(q_emb[t] * e.get(t, 0) for t in q_emb)
            en = math.sqrt(sum(v * v for v in e.values())) or 1.0
            out.append(dot / (qn * en))
        return out


class MockReranker:
    name = "mock-reranker"

    def rerank(self, question: str, pages: list[PageInput], k: int) -> list[str]:
        q = set(_tokens(question))
        scored = [(len(q & set(_tokens(p.text or ""))), -i, p.page_id) for i, p in enumerate(pages)]
        return [pid for *_, pid in sorted(scored, reverse=True)[:k]]


class MockGenerator:
    """Answers with the first number in the first page's table; cites that page."""

    name = "mock-generator"

    def generate(self, question: str, pages: list[PageInput]) -> GenerationResult:
        if not pages:
            raw = json.dumps({"answer": "0", "cited_pages": []})
            return GenerationResult(raw, "0", [])
        text = pages[0].text or ""
        table_part = text[text.find("|"):] if "|" in text else text
        nums = re.findall(r"\(?-?\d[\d,]*\.?\d*\)?", table_part)
        ans = nums[0] if nums else "0"
        raw = json.dumps({"answer": ans, "cited_pages": [pages[0].page_id]})
        return GenerationResult(raw, ans, [pages[0].page_id])
