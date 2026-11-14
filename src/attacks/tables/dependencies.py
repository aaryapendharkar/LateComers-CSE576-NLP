"""Find totals/subtotals and which cells depend on which.

OWNER: Person 2 (Janhavi) -- Gap 1 attacks. Brief task 4.

Two ways to spot a total: by label (total, net, sum, subtotal) and by
arithmetic (a row equals the sum of the rows above it, within rounding). The
result is a graph cell -> cells that must change if it changes, including
totals of totals. Log how many tables have >= 1 detectable total (report stat).

Real FinQA tables total on BOTH axes, sometimes in the same table:
  "column" totals: a row (e.g. "Total revenue") equals the sum of the body
      rows above it, within ONE column (2019's total, 2018's total, ...).
  "row" totals: one column (often literally headed "total") equals the sum
      of the OTHER columns, within ONE row (e.g. a maturity schedule where
      "total" = "<1yr" + "1-3yr" + "3-5yr" + ">5yr", checked per row).

Design decision: we only ever return a relation whose arithmetic actually
verifies (within rel_tol/abs_tol). A row whose label contains a total
keyword ("total", "net", "sum", "subtotal") but whose value does NOT
reconcile with anything we can find is NOT returned -- a label alone isn't
enough to safely rewrite that cell later (edits.py uses these relations to
literally update the poisoned table's totals, so a wrong "part" set would
produce an inconsistent page, defeating the whole point of a consistent
edit). ``found_by`` records whether the label's keyword also matched, which
is useful for the report (how often does a reconciling row also look like a
labeled total, vs. an unlabeled subtotal we only found by arithmetic).

For the row axis specifically: we only treat a column as a genuine "total
column" if the arithmetic holds for at least two rows, OR the column header
itself contains a total keyword. A single row that happens to reconcile by
coincidence (small tables, many zero cells) is not enough evidence on its
own, since that relation gets used later to rewrite the page.

Known limitation: a column can coincidentally reconcile for a BLOCK of rows
where some other column is zero (e.g. a share reconciliation table where
"In Treasury" trivially equals "Issued + Outstanding" on every row where
"Issued" happens to be a dash), even though the table's real structure sums
a different column. We accept this risk since Gap 1 only ever edits cells
that are actual FinQA program operands, not arbitrary table cells, which
makes this coincidence very unlikely to matter in practice -- flagged here
rather than engineered around, given the deadline.

Note: Person 3's D1 defense also finds totals, independently, on the PARSED
text. Keep the two implementations separate (the defense shouldn't share the
attacker's code), but feel free to compare results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from .numbers import parse_cell

Cell = tuple[int, int]  # GRID (row, col), row 0 = header

_KEYWORDS = ("total", "net", "sum", "subtotal")
_MAX_GROUP = 6  # cap on combinatorial subset search for labeled-but-unverified totals


@dataclass
class TotalRelation:
    total: Cell
    parts: list[Cell]
    axis: str            # "column" (rows sum down a column) or "row" (cols sum across)
    found_by: str        # "label" | "arithmetic" | "both"
    sign: list[int] = field(default_factory=list)  # +1/-1 per part (e.g. net = income - expense)


def _has_keyword(text: str) -> bool:
    low = text.lower()
    return any(k in low for k in _KEYWORDS)


def _grid_values(grid: list[list[str]]) -> list[list[float | None]]:
    """Parsed numeric value of every grid cell (None where not numeric)."""
    out = []
    for row in grid:
        parsed = []
        for cell in row:
            p = parse_cell(cell)
            parsed.append(p.value if p is not None else None)
        out.append(parsed)
    return out


def _close(a: float, b: float, rel_tol: float, abs_tol: float) -> bool:
    return abs(a - b) <= max(rel_tol * abs(b), abs_tol)


def _find_column_totals(grid: list[list[str]], values: list[list[float | None]],
                         rel_tol: float, abs_tol: float) -> list[TotalRelation]:
    n_rows, n_cols = len(grid), max((len(r) for r in grid), default=0)
    found: list[TotalRelation] = []

    for col in range(1, n_cols):
        for total_row in range(2, n_rows):  # need >=1 body row above it
            total_val = values[total_row][col] if col < len(values[total_row]) else None
            if total_val is None:
                continue
            candidates = [r for r in range(1, total_row)
                          if col < len(values[r]) and values[r][col] is not None]
            if not candidates:
                continue

            label_match = _has_keyword(grid[total_row][0])

            # cheapest case: every body row above it sums to the total
            if _close(sum(values[r][col] for r in candidates), total_val, rel_tol, abs_tol):
                found.append(TotalRelation(
                    total=(total_row, col), parts=[(r, col) for r in candidates],
                    axis="column", found_by="both" if label_match else "arithmetic",
                    sign=[1] * len(candidates),
                ))
                continue

            # only worth a combinatorial search if the label actually suggests a total
            if label_match and len(candidates) <= _MAX_GROUP:
                for size in range(2, len(candidates) + 1):
                    hit = None
                    for combo in combinations(candidates, size):
                        if _close(sum(values[r][col] for r in combo), total_val, rel_tol, abs_tol):
                            hit = combo
                            break
                    if hit:
                        found.append(TotalRelation(
                            total=(total_row, col), parts=[(r, col) for r in hit],
                            axis="column", found_by="both", sign=[1] * len(hit),
                        ))
                        break
                # if no subset reconciles, we deliberately report nothing for this
                # (total_row, col): a keyword alone isn't enough to rewrite it later.
    return found


def _find_row_totals(grid: list[list[str]], values: list[list[float | None]],
                      rel_tol: float, abs_tol: float) -> list[TotalRelation]:
    n_rows, n_cols = len(grid), max((len(r) for r in grid), default=0)
    found: list[TotalRelation] = []

    for col in range(1, n_cols):
        header_match = _has_keyword(grid[0][col]) if col < len(grid[0]) else False
        per_row: list[tuple[int, list[int]]] = []  # (row, other numeric cols) where it holds

        for row in range(1, n_rows):
            total_val = values[row][col] if col < len(values[row]) else None
            if total_val is None:
                continue
            others = [c for c in range(1, len(values[row])) if c != col and values[row][c] is not None]
            if len(others) < 2:  # need at least 2 parts for this to mean anything
                continue
            if _close(sum(values[row][c] for c in others), total_val, rel_tol, abs_tol):
                per_row.append((row, others))

        if not per_row:
            continue
        if not header_match and len(per_row) < 2:
            continue  # one coincidental row isn't enough evidence without a labeled column

        for row, others in per_row:
            found.append(TotalRelation(
                total=(row, col), parts=[(row, c) for c in others],
                axis="row", found_by="both" if header_match else "arithmetic",
                sign=[1] * len(others),
            ))
    return found


def find_totals(table: dict[str, Any], rel_tol: float = 0.005, abs_tol: float = 1.0) -> list[TotalRelation]:
    grid = [table["header"]] + table["rows"]
    values = _grid_values(grid)
    return (_find_column_totals(grid, values, rel_tol, abs_tol)
            + _find_row_totals(grid, values, rel_tol, abs_tol))


def dependents(cell: Cell, relations: list[TotalRelation]) -> list[Cell]:
    """All cells that must change if ``cell`` changes (transitively: totals of
    totals, and totals that cascade across axes)."""
    changed = {cell}
    result: list[Cell] = []
    progress = True
    while progress:
        progress = False
        for rel in relations:
            if rel.total in changed:
                continue
            if any(p in changed for p in rel.parts):
                result.append(rel.total)
                changed.add(rel.total)
                progress = True
    return result