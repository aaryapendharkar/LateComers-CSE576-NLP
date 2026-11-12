"""Gap 1 edit generator: consistent_cell, naive_cell, unit, header.

OWNER: Person 2 (Janhavi) -- Gap 1 attacks. Brief tasks 5-7.

Output: Attack rows (src/common/schemas.Attack) with ``edit`` in the format of
src/common/edits.py, appended to data/attacks/g1.jsonl, plus the poisoned page
rendered with Person 4's render_table_page(image_table=text_table=edited table),
whose record goes to data/manifests/pages_g1.jsonl.

Page id: <doc_id>__G1_<attack_type>_<qid>  -> use schemas.poison_page_id().
Keep only edits whose target differs from gold by > 5% relative (or flips yes/no).
"""

from __future__ import annotations

import random
from typing import Any, Optional

from ...common.schemas import Attack, Doc, Example


def make_consistent_cell(ex: Example, doc: Doc, rng: random.Random) -> Optional[Attack]:
    """Change one cell the program reads by ±5-25% (same format) and propagate to every total."""
    raise NotImplementedError("Person 2: make_consistent_cell")


def make_naive_cell(consistent: Attack, doc: Doc) -> Attack:
    """B1 baseline: the IDENTICAL cell change as ``consistent``, totals left untouched."""
    raise NotImplementedError("Person 2: make_naive_cell")


def make_unit_edit(ex: Example, doc: Doc) -> Optional[Attack]:
    """'in thousands' -> 'in millions' etc.; target = answer rescaled when it is an amount."""
    raise NotImplementedError("Person 2: make_unit_edit")


def make_header_edit(ex: Example, doc: Doc) -> Optional[Attack]:
    """Swap two year column headers; target = program re-run on the swapped table."""
    raise NotImplementedError("Person 2: make_header_edit")


def keep_edit(gold: str, target: str, min_rel_diff: float = 0.05) -> bool:
    """True if the target differs enough from gold (>5% relative, or a yes/no flip)."""
    raise NotImplementedError("Person 2: keep_edit")


def generate_all(examples: dict[str, Example], docs: dict[str, Doc], cfg: dict[str, Any]) -> list[Attack]:
    raise NotImplementedError("Person 2: generate_all")
