"""Where pipelines get a page's content (text / image) from. OWNER: Person 1.

Two kinds of pages:

* **Rendered pages** listed in ``data/manifests/pages_*.jsonl`` (Person 4's
  renderer). P1 text comes from Docling / pdfplumber output of the PDF, P2 uses
  the PNG.
* **Virtual pages** (Day 1 stand-in, and tests): built from ``docs.jsonl``.
  A poisoned virtual page is the clean doc with the attack's ``edit`` applied
  (``src/common/edits.py``). This lets everyone test the full flow before the
  renderer exists. Virtual pages have no image, so P2/P3 need rendered pages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..common.config import resolve
from ..common.edits import apply_edit
from ..common.schemas import Attack, Doc, Page, clean_page_id, doc_id_of_page
from ..common.tables import doc_to_text


@dataclass
class PageContent:
    page_id: str
    doc_id: str
    text: str
    image_path: Optional[str]  # None for virtual pages


class PageStore:
    def __init__(self, docs: dict[str, Doc], pages: dict[str, Page], attacks: dict[str, Attack],
                 text_source: str = "standin", parsed_dir: str = "data/parsed"):
        self.docs = docs
        self.pages = pages
        self.attacks_by_page = {a.poison_page_id: a for a in attacks.values()}
        self.text_source = text_source
        self.parsed_dir = parsed_dir
        self._cache: dict[str, PageContent] = {}

    # -- corpus -----------------------------------------------------------
    def clean_corpus(self, source: str) -> list[str]:
        """Clean page ids for one source ('finqa' or 'chartqa'), in a fixed order."""
        return sorted(clean_page_id(d.doc_id) for d in self.docs.values() if d.source == source)

    # -- content ----------------------------------------------------------
    def get(self, page_id: str) -> PageContent:
        if page_id not in self._cache:
            self._cache[page_id] = self._load(page_id)
        return self._cache[page_id]

    def _virtual_doc(self, page_id: str) -> dict:
        doc = self.docs[doc_id_of_page(page_id)].to_dict()
        if page_id == clean_page_id(doc["doc_id"]):
            return doc
        atk = self.attacks_by_page.get(page_id)
        if atk is None:
            raise KeyError(f"unknown page {page_id!r}: not rendered and not an attack's poison page")
        return apply_edit(doc, atk.edit)

    def _load(self, page_id: str) -> PageContent:
        doc_id = doc_id_of_page(page_id)
        if self.text_source == "standin" or page_id not in self.pages:
            if self.text_source != "standin" and page_id not in self.pages:
                raise KeyError(f"page {page_id!r} not in manifests (text_source={self.text_source})")
            return PageContent(page_id, doc_id, doc_to_text(self._virtual_doc(page_id)), None)
        page = self.pages[page_id]
        parsed = resolve(self.parsed_dir) / self.text_source / f"{page_id}.txt"
        if not parsed.exists():
            raise FileNotFoundError(
                f"{parsed} missing: run scripts/build_indexes.py --parse {self.text_source} first")
        return PageContent(page_id, doc_id, parsed.read_text(encoding="utf-8"),
                           str(resolve(page.image_path)))
