"""P2 (vision-native): ColPali late-interaction retrieval over page images. OWNER: Person 1.

Stores one multi-vector embedding (tensor [n_tokens, dim]) per page so a single
page can be swapped without touching the others.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .base import Retriever
from .pages import PageStore


class ColPaliRetriever(Retriever):
    name = "p2_colpali"

    def __init__(self, store: PageStore, model_name: str = "vidore/colpali-v1.3", device: str = "cuda",
                 dtype: str = "bfloat16", batch_size: int = 4, cache_dir: Optional[Path] = None):
        self.model_name, self.device, self.dtype, self.bs = model_name, device, dtype, batch_size
        self._model = self._proc = None
        super().__init__(store, cache_dir)

    def _load(self):
        if self._model is None:
            import torch
            from colpali_engine.models import ColPali, ColPaliProcessor

            self._model = ColPali.from_pretrained(
                self.model_name, torch_dtype=getattr(torch, self.dtype), device_map=self.device).eval()
            self._proc = ColPaliProcessor.from_pretrained(self.model_name)
        return self._model, self._proc

    def embed_pages(self, page_ids: list[str]) -> list[Any]:
        import torch
        from PIL import Image

        model, proc = self._load()
        images = []
        for p in page_ids:
            path = self.store.get(p).image_path
            if path is None:
                raise RuntimeError(f"P2 needs a rendered page image for {p} (virtual pages have none)")
            images.append(Image.open(path).convert("RGB"))
        batch = proc.process_images(images).to(model.device)
        with torch.no_grad():
            embs = model(**batch)
        return [e.detach().to("cpu", dtype=torch.float32) for e in embs]

    def embed_query(self, query: str) -> Any:
        import torch

        model, proc = self._load()
        batch = proc.process_queries([query]).to(model.device)
        with torch.no_grad():
            return model(**batch)[0].detach().to("cpu", dtype=torch.float32)

    def score(self, q_emb: Any, page_embs: list[Any]) -> list[float]:
        _, proc = self._load()
        return proc.score_multi_vector([q_emb], page_embs)[0].tolist()
