"""The ``edit`` field of an attack row, and how to apply it. OWNER: Person 1.

This pins down the format of ``attack["edit"]`` (A6) so Person 2 (who writes
edits), Person 4 (who reuses them) and Person 1 (whose runner can simulate a
poisoned page before the renderer exists) all read it the same way.

Cell edits (consistent_cell / naive_cell, and the chart value edit)::

    {"row": 1, "col": 1, "old": "1,204", "new": "1,312",
     "also_changed": [[3, 1, "1,716", "1,824"]]}

  Row/col index the GRID = [header] + rows, so row 0 is the header row and
  row 1 is the first body row (this matches the A6 example). ``also_changed``
  lists every dependent total that was updated (empty for naive_cell).

Field edits (unit / header)::

    {"field": "unit_note", "old": "in millions", "new": "in thousands"}
    {"field": "header", "old": ["", "2019", "2018"], "new": ["", "2018", "2019"]}

Optional for any edit: ``"pre_text"`` / ``"post_text"`` replacement strings
(for the consistent_cell_text variant).
"""

from __future__ import annotations

import copy
from typing import Any


class EditError(ValueError):
    pass


def _set_cell(grid: list[list[str]], r: int, c: int, old: str, new: str, check: bool) -> None:
    try:
        cur = grid[r][c]
    except IndexError as e:
        raise EditError(f"cell ({r}, {c}) is outside the table") from e
    if check and str(cur) != str(old):
        raise EditError(f"cell ({r}, {c}) is {cur!r}, edit expected old value {old!r}")
    grid[r][c] = str(new)


def apply_edit(doc_or_table: dict[str, Any], edit: dict[str, Any], check_old: bool = True) -> dict[str, Any]:
    """Return a NEW doc (or table) with the edit applied. The input is not modified.

    Pass a doc (with a ``table`` key) to also apply pre/post text replacements.
    """
    is_doc = "table" in doc_or_table
    out = copy.deepcopy(doc_or_table)
    table = out["table"] if is_doc else out

    if "field" in edit:
        f = edit["field"]
        if f not in ("unit_note", "header", "title"):
            raise EditError(f"unsupported field edit {f!r}")
        if check_old and table.get(f) != edit["old"]:
            raise EditError(f"{f} is {table.get(f)!r}, edit expected {edit['old']!r}")
        table[f] = copy.deepcopy(edit["new"])
    if "row" in edit:
        grid = [list(table["header"])] + [list(r) for r in table["rows"]]
        _set_cell(grid, edit["row"], edit["col"], edit["old"], edit["new"], check_old)
        for r, c, old, new in edit.get("also_changed", []):
            _set_cell(grid, r, c, old, new, check_old)
        table["header"], table["rows"] = grid[0], grid[1:]

    if is_doc:
        for k in ("pre_text", "post_text"):
            if k in edit:
                out[k] = edit[k]
    return out


def edited_cells(edit: dict[str, Any]) -> list[tuple[int, int]]:
    """All (row, col) grid cells an edit touches (for highlighting figures)."""
    if "row" not in edit:
        return []
    return [(edit["row"], edit["col"])] + [(r, c) for r, c, *_ in edit.get("also_changed", [])]
