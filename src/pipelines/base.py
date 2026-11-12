"""Retriever base class with the "index once, swap one page" mechanism. OWNER: Person 1.

Every retriever keeps an embedding per page id. Clean pages are embedded once
(``index``) and cached on disk. A poisoned page is embedded the first time it
is needed and cached too. ``search`` scores only the page ids it is given, so
a swap run simply passes the corpus with the clean id replaced by the poison id:
no re-indexing, and all other pages keep exactly the same scores.
"""

from __future__ import annotations

import pickle
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterable, Optional

from .pages import PageStore


class Retriever(ABC):
    name: str = "base"

    def __init__(self, store: PageStore, cache_dir: Optional[Path] = None):
        self.store = store
        self.cache_dir = cache_dir
        self._emb: dict[str, Any] = {}
        if cache_dir is not None:
            self._load_cache()

    # -- to implement -------------------------------------------------------
    @abstractmethod
    def embed_pages(self, page_ids: list[str]) -> list[Any]:
        """Embeddings for these pages (same order)."""

    @abstractmethod
    def embed_query(self, query: str) -> Any:
        ...

    @abstractmethod
    def score(self, q_emb: Any, page_embs: list[Any]) -> list[float]:
        """Similarity of the query to each page embedding (higher = better)."""

    # -- shared logic -------------------------------------------------------
    def index(self, page_ids: Iterable[str], batch_size: int = 16) -> None:
        todo = [p for p in page_ids if p not in self._emb]
        for i in range(0, len(todo), batch_size):
            chunk = todo[i:i + batch_size]
            for pid, e in zip(chunk, self.embed_pages(chunk)):
                self._emb[pid] = e
        if todo:
            self._save_cache()

    def search(self, query: str, page_ids: list[str], k: int) -> list[tuple[str, float]]:
        self.index(page_ids)
        q = self.embed_query(query)
        scores = self.score(q, [self._emb[p] for p in page_ids])
        ranked = sorted(zip(page_ids, scores), key=lambda t: (-t[1], t[0]))  # tie-break by id
        return ranked[:k]

    # -- disk cache ---------------------------------------------------------
    def _cache_file(self) -> Optional[Path]:
        return None if self.cache_dir is None else Path(self.cache_dir) / f"{self.name}.pkl"

    def _load_cache(self) -> None:
        f = self._cache_file()
        if f is not None and f.exists():
            with open(f, "rb") as fh:
                self._emb = pickle.load(fh)

    def _save_cache(self) -> None:
        f = self._cache_file()
        if f is None:
            return
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        with open(tmp, "wb") as fh:
            pickle.dump(self._emb, fh)
        tmp.replace(f)
