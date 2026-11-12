"""Image-text consistency checker for Gap 2.

OWNER: Person 5 (Disha). Brief task 1.

  1. a VLM (reuse the generator model) reads the page IMAGE -> table JSON (charts: value list)
  2. parse the page's TEXT layer (Docling output P1 uses) into the same format
  3. align rows/cols by label, compare numbers with tolerance, flag any mismatch
Cheaper mode (configs: img_text_check.only_question_rows): compare only rows
whose label appears in the question.

Expected: catches text_only / image_only, ~0% on propagate (both layers agree on
the wrong value) -> the key blind spot.
"""

from __future__ import annotations

from typing import Any, Optional, TypedDict


class CheckResult(TypedDict):
    flag: bool
    mismatches: list[list[Any]]   # [[row_label, col_label, img_val, text_val], ...]


def compare_tables(img_table: dict[str, Any], text_table: dict[str, Any], rel_tol: float = 0.01,
                   only_rows: Optional[list[str]] = None) -> CheckResult:
    """Pure comparison logic (build + test this first on mock JSON pairs, Thursday)."""
    raise NotImplementedError("Person 5: compare_tables")


def extract_table_from_image(image_path: str, generator: Any) -> dict[str, Any]:
    """VLM prompt -> table JSON. Save the prompt in configs/prompts/ (e.g. img_extract_v1.txt)."""
    raise NotImplementedError("Person 5: extract_table_from_image")


def check_page(page_id: str, question: Optional[str] = None, cfg: Optional[dict] = None) -> CheckResult:
    raise NotImplementedError("Person 5: check_page")
