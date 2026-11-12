"""Table page renderer: realistic PDF page whose IMAGE and TEXT layer can differ.

OWNER: Person 4 (Aaron). Renderer v1 due Thu Nov 12, 11 pm -- everyone depends on it.
Ship the simplest working version first; make it pretty later.

Construction (A4), identical for clean and poisoned pages:
  (a) lay out the IMAGE-version with reportlab; record every text item's
      (x, y, font, size, string)
  (b) rasterize that PDF to PNG at 150 dpi (pdftoppm)
  (c) final PDF = PNG as full-page background + TEXT-version strings drawn at
      the same coordinates with text render mode 3 (invisible)
Use ONE layout function for both versions so coordinates line up.

Verify (Thu night): Docling (OCR off) on a conflict page returns the TEXT values;
the PNG shows the IMAGE values. If Docling misses the invisible table, tell
Person 1 at once (fallback: pdfplumber).

Output files (under paths.pages_dir):  <page_id>.pdf / .png / .txt / .table.json
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class TextItem:
    x: float
    y: float
    font: str
    size: float
    text: str


def layout_page(doc: dict[str, Any], table: dict[str, Any], pre_post: Optional[tuple[str, str]] = None,
                cfg: Optional[dict] = None) -> list[TextItem]:
    """Title, pre_text paragraph(s), table (fixed column x, right-aligned numbers, light rules,
    unit note), post_text. Letter size, 10-11 pt. Returns every text item with coordinates."""
    raise NotImplementedError("Person 4: layout_page")


def render_table_page(doc: dict, page_id: str, out_dir: str,
                      image_table: dict, text_table: dict,
                      image_pre_post=None, text_pre_post=None) -> dict:
    """A7 interface. Returns ONE pages.jsonl record (src/common/schemas.Page as dict).

    image_version / text_version in the record: "clean" if that table equals
    doc["table"] (and pre/post unchanged), else "poison". Store paths repo-relative
    (src/common/config.rel). The caller appends the record to its own manifest
    (pages_clean.jsonl / pages_g1.jsonl / pages_g2.jsonl).
    """
    raise NotImplementedError("Person 4: render_table_page")
