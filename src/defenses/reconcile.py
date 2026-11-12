"""D1 reconciliation filter: do totals add up, and does the table agree with the text?

OWNER: Person 3 (Vatsal). Brief task 1.

Input is what the PIPELINE sees: the page's parsed text (Docling output,
data/parsed/docling/<page_id>.txt), not the clean JSON. Start Thursday on clean
tables from docs.jsonl (src/common/tables.table_to_markdown gives the same
markdown shape Docling produces) plus a few hand-made edits.

Expected: catches naive_cell, misses consistent_cell (passes the sum check by
construction) unless the table-text check fires -> supports RQ1.
"""

from __future__ import annotations

from typing import Any, TypedDict


class D1Result(TypedDict):
    flag: bool
    reasons: list[str]


def parse_markdown_table(page_text: str) -> dict[str, Any]:
    """Pull the table (A6 format) and the surrounding text out of parsed page text."""
    raise NotImplementedError("Person 3: parse_markdown_table")


def sum_check(table: dict[str, Any], rel_tol: float = 0.005, abs_tol: float = 1.0) -> list[str]:
    """Find total/subtotal rows and columns (label + arithmetic); return a reason per violation."""
    raise NotImplementedError("Person 3: sum_check")


def table_text_check(table: dict[str, Any], pre_text: str, post_text: str) -> list[str]:
    """Numbers in the text with a matching row label and year must equal the table cell."""
    raise NotImplementedError("Person 3: table_text_check")


def reconcile_page(page_text: str, cfg: dict | None = None) -> D1Result:
    """Run both checks on one page -> {"flag": bool, "reasons": [...]}."""
    raise NotImplementedError("Person 3: reconcile_page")
