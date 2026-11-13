"""The experiment runner: one question -> one run-log record (A6). OWNER: Person 1.

    from src.pipelines.run import run_query
    rec = run_query("q0001", pipeline="P1", reranker=True)                      # R2
    rec = run_query("q0001", "P1", True, swap={clean_id: poison_id}, attack=atk)  # attack
    rec = run_query("q0001", "P1", True, mode="closed_book")                    # R1
    rec = run_query("q0001", "P1", True, mode="oracle")                         # R3

Swap = "index once, swap one page": the corpus is the list of clean page ids
with ``clean_id`` replaced by ``poison_id``. Retrievers score only those ids
(cached embeddings), so nothing else changes. ``drop_pages`` lets a defense
remove flagged pages from the top-5 before generation (D1 / checker filters).
"""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Any, Optional

from ..common import io
from ..common.answer_match import numbers_match
from ..common.config import get_config, resolve
from ..common.schemas import Attack, Example, RunRecord, clean_page_id
from .generate import PageInput
from .p3_hybrid import rrf
from .pages import PageStore
from .rerank import NoReranker


def _rank(page_id: Optional[str], ranking: list[str]) -> Optional[int]:
    if page_id is None or page_id not in ranking:
        return None
    return ranking.index(page_id) + 1


class RAGSystem:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        pc = cfg["pipelines"]
        self.k_retr, self.k_final, self.rrf_k = pc["top_k_retrieve"], pc["top_k_final"], pc["rrf_k"]
        self.docs = io.load_docs(cfg)
        self.examples = io.load_examples(cfg)
        self.attacks = io.load_attacks(cfg) if resolve(cfg["paths"]["attacks_dir"]).exists() else {}
        pages = io.load_pages(cfg) if resolve(cfg["paths"]["manifests_dir"]).exists() else {}
        self.store = PageStore(self.docs, pages, self.attacks,
                               text_source=pc["p1_text_source"], parsed_dir=cfg["paths"]["parsed_dir"])
        self.backend = pc["backend"]
        self._p1 = self._p2 = self._reranker = self._generator = None

    # -- lazily built components ------------------------------------------
    @property
    def p1(self):
        if self._p1 is None:
            if self.backend == "mock":
                from .mock import MockRetriever
                self._p1 = MockRetriever(self.store, "mock_p1")
            else:
                from .p1_text import BGEM3Retriever
                m = self.cfg["models"]
                self._p1 = BGEM3Retriever(self.store, m["embedder"], batch_size=m["batch_size"],
                                          cache_dir=resolve(self.cfg["paths"]["indexes_dir"]))
        return self._p1

    @property
    def p2(self):
        if self._p2 is None:
            if self.backend == "mock":
                from .mock import MockRetriever
                self._p2 = MockRetriever(self.store, "mock_p2")
            else:
                from .p2_colpali import ColPaliRetriever
                m = self.cfg["models"]
                self._p2 = ColPaliRetriever(self.store, m["colpali"], m["device"], m["dtype"],
                                            cache_dir=resolve(self.cfg["paths"]["indexes_dir"]))
        return self._p2

    @property
    def reranker(self):
        if self._reranker is None:
            name = self.cfg["models"].get("reranker")
            if self.backend == "mock":
                from .mock import MockReranker
                self._reranker = MockReranker()
            elif name:
                from .rerank import QwenVLReranker
                m = self.cfg["models"]
                self._reranker = QwenVLReranker(name, m["device"], m["dtype"])
            else:
                self._reranker = NoReranker()
        return self._reranker

    @property
    def generator(self):
        if self._generator is None:
            if self.backend == "mock":
                from .mock import MockGenerator
                self._generator = MockGenerator()
            else:
                from .generate import VLMGenerator
                m, g = self.cfg["models"], self.cfg["generation"]
                self._generator = VLMGenerator(
                    m.get("generator_fallback") or m["generator"], g["prompt_file"],
                    g["closed_book_prompt_file"], m["device"], m["dtype"], g["max_new_tokens"],
                    g.get("max_page_chars", 0), g.get("max_image_pixels", 0))
        return self._generator

    # -- one query ----------------------------------------------------------
    def page_input(self, page_id: str, pipeline: str) -> PageInput:
        c = self.store.get(page_id)
        if pipeline == "P1":
            return PageInput(page_id, text=c.text)
        if pipeline == "P2":
            return PageInput(page_id, image_path=c.image_path)
        return PageInput(page_id, text=c.text, image_path=c.image_path)

    def retrieve(self, question: str, pipeline: str, corpus: list[str]) -> list[str]:
        if pipeline == "P1":
            return [p for p, _ in self.p1.search(question, corpus, self.k_retr)]
        if pipeline == "P2":
            return [p for p, _ in self.p2.search(question, corpus, self.k_retr)]
        if pipeline == "P3":
            r1 = [p for p, _ in self.p1.search(question, corpus, self.k_retr)]
            r2 = [p for p, _ in self.p2.search(question, corpus, self.k_retr)]
            return [p for p, _ in rrf([r1, r2], k=self.rrf_k, top=self.k_retr)]
        raise ValueError(f"unknown pipeline {pipeline!r}")

    def run_query(self, qid: str, pipeline: str, reranker: bool, swap: Optional[dict[str, str]] = None,
                  attack: Optional[Attack | dict] = None, mode: str = "rag",
                  drop_pages: Optional[set[str]] = None, run_name: str = "") -> dict[str, Any]:
        ex: Example = self.examples[qid]
        if isinstance(attack, dict):
            attack = Attack.from_dict(attack)
        if attack is not None and swap is None:
            swap = {attack.clean_page_id: attack.poison_page_id}
        swap = swap or {}
        gold_pid = clean_page_id(ex.doc_id)
        poison_pid = next(iter(swap.values()), None) if swap else None
        if poison_pid == gold_pid:  # self-swap sanity check: not a poisoned page
            poison_pid = None

        t0 = time.perf_counter()
        corpus = [swap.get(p, p) for p in self.store.clean_corpus(ex.source)]
        if mode == "closed_book":
            top20, top5 = [], []
        elif mode == "oracle":
            top20 = top5 = [swap.get(gold_pid, gold_pid)]
        elif mode == "rag":
            top20 = self.retrieve(ex.question, pipeline, corpus)
            cands = [self.page_input(p, pipeline) for p in top20]
            top5 = (self.reranker if reranker else NoReranker()).rerank(ex.question, cands, self.k_final)
        else:
            raise ValueError(f"unknown mode {mode!r}")

        dropped = [p for p in top5 if drop_pages and p in drop_pages]
        gen_pages = [self.page_input(p, pipeline) for p in top5 if p not in dropped]
        res = self.generator.generate(ex.question, gen_pages)
        latency = time.perf_counter() - t0

        tol = self.cfg["metrics"]["rel_tol"]
        rec = RunRecord(
            qid=qid, attack_id=attack.attack_id if attack else None, pipeline=pipeline,
            reranker=bool(reranker), generator=getattr(self.generator, "name", "?"),
            top20=top20, top5=top5,
            gold_rank_retr=_rank(gold_pid, top20), gold_rank_rerank=_rank(gold_pid, top5),
            poison_rank_retr=_rank(poison_pid, top20), poison_rank_rerank=_rank(poison_pid, top5),
            answer_raw=res.answer_raw, answer=res.answer, cited=res.cited,
            correct=numbers_match(res.answer, ex.gold_answer, rel_tol=tol),
            matches_target=(numbers_match(res.answer, attack.target_answer, rel_tol=tol) if attack else None),
            latency_s=round(latency, 3), mode=mode, run_name=run_name,
            poison_page_id=poison_pid, filtered_pages=dropped,
        )
        return rec.to_dict()


@lru_cache(maxsize=1)
def get_system() -> RAGSystem:
    return RAGSystem(get_config())


def run_query(qid: str, pipeline: str, reranker: bool, swap: dict | None = None, **kw: Any) -> dict:
    """A7 interface. Extra keywords: attack=, mode=, drop_pages=, run_name=."""
    return get_system().run_query(qid, pipeline, reranker, swap=swap, **kw)
