"""P1 (text-parsed): BGE-M3 dense retrieval over page text. OWNER: Person 1.

Text source (configs: pipelines.p1_text_source):
  standin    -> pre_text + table-as-markdown + post_text from docs.jsonl (Day 1)
  docling    -> Docling, OCR off, on the rendered PDF (main setting)
  pdfplumber -> fallback if Docling can't see the invisible-text table
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import numpy as np

from .base import Retriever
from .pages import PageStore


class BGEM3Retriever(Retriever):
    name = "p1_bge_m3"

    def __init__(self, store: PageStore, model_name: str = "BAAI/bge-m3", use_fp16: bool = True,
                 max_length: int = 2048, batch_size: int = 8, cache_dir: Optional[Path] = None):
        self.model_name, self.use_fp16, self.max_length, self.bs = model_name, use_fp16, max_length, batch_size
        self._model = None
        self.name = f"p1_bge_m3_{store.text_source}"
        super().__init__(store, cache_dir)

    @property
    def model(self):
        """BGE-M3 dense embeddings. sentence-transformers is the default (fewer version
        conflicts); FlagEmbedding gives the same dense vectors if you prefer it."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                m = SentenceTransformer(self.model_name)
                m.max_seq_length = self.max_length
                if self.use_fp16:
                    m = m.half()
                self._model, self._kind = m, "st"
            except ImportError:
                from FlagEmbedding import BGEM3FlagModel

                self._model, self._kind = BGEM3FlagModel(self.model_name, use_fp16=self.use_fp16), "flag"
        return self._model

    def _encode(self, texts: list[str]) -> np.ndarray:
        m = self.model
        if self._kind == "st":
            out = m.encode(texts, batch_size=self.bs, normalize_embeddings=True)
        else:
            out = m.encode(texts, batch_size=self.bs, max_length=self.max_length)["dense_vecs"]
        v = np.asarray(out, dtype=np.float32)
        return v / np.linalg.norm(v, axis=1, keepdims=True).clip(min=1e-12)

    def embed_pages(self, page_ids: list[str]) -> list[Any]:
        return list(self._encode([self.store.get(p).text for p in page_ids]))

    def embed_query(self, query: str) -> Any:
        return self._encode([query])[0]

    def score(self, q_emb: Any, page_embs: list[Any]) -> list[float]:
        return (np.stack(page_embs) @ q_emb).tolist()  # cosine (vectors are normalised)


# ---------------------------------------------------------------------------
# PDF -> text (run once per page by scripts/build_indexes.py --parse ...)
# ---------------------------------------------------------------------------

_docling_converter = None


def parse_pdf_docling(pdf_path: str) -> str:
    """Docling with OCR OFF, exported as markdown (tables become markdown tables)."""
    global _docling_converter
    if _docling_converter is None:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        opts = PdfPipelineOptions()
        opts.do_ocr = False
        _docling_converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
    return _docling_converter.convert(pdf_path).document.export_to_markdown()


def parse_pdf_pdfplumber(pdf_path: str) -> str:
    """Plain text layer (reads invisible render-mode-3 text reliably)."""
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


PARSERS = {"docling": parse_pdf_docling, "pdfplumber": parse_pdf_pdfplumber}
