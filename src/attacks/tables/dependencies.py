"""Find totals/subtotals and which cells depend on which.

OWNER: Person 2 (Janhavi) -- Gap 1 attacks. Brief task 4.

Two ways to spot a total: by label (total, net, sum, subtotal) and by
arithmetic (a row equals the sum of the rows above it, within rounding). The
result is a graph cell -> cells that must change if it changes, including
totals of totals. Log how many tables have >= 1 detectable total (report stat).

Note: Person 3's D1 defense also finds totals, independently, on the PARSED
text. Keep the two implementations separate (the defense shouldn't share the
attacker's code), but feel free to compare results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Cell = tuple[int, int]  # GRID (row, col), row 0 = header


@dataclass
class TotalRelation:
    total: Cell
    parts: list[Cell]
    axis: str            # "column" (rows sum down a column) or "row" (cols sum across)
    found_by: str        # "label" | "arithmetic" | "both"
    sign: list[int] = field(default_factory=list)  # +1/-1 per part (e.g. net = income - expense)


def find_totals(table: dict[str, Any], rel_tol: float = 0.005, abs_tol: float = 1.0) -> list[TotalRelation]:
    raise NotImplementedError("Person 2: find_totals")


def dependents(cell: Cell, relations: list[TotalRelation]) -> list[Cell]:
    """All cells that must change if ``cell`` changes (transitively: totals of totals)."""
    raise NotImplementedError("Person 2: dependents")
