"""Table-cell number parsing that keeps the original formatting.

OWNER: Person 2 (Janhavi) -- Gap 1 attacks. Brief task 2.

Unlike ``src/common/answer_match.parse_number`` (which only needs a value),
this module must remember HOW a number was written so an edited value can be
written back in the same style: same decimals, thousands commas, parentheses
for negatives, $ and % signs, footnote marks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class CellNumber:
    value: float
    decimals: int          # digits after the decimal point as written
    commas: bool           # thousands separators used
    parens: bool           # negative written as (123)
    prefix: str = ""       # e.g. "$"
    suffix: str = ""       # e.g. "%", footnote mark "(a)", "*"
    raw: str = ""


def parse_cell(cell: str) -> Optional[CellNumber]:
    """Parse '1,204', '$(12.5)', '3.4%', '—' (dash = blank/0), '1,090 (a)'. None if not numeric.

    TODO(Person 2): implement. Decide and document how dashes are treated.
    """
    raise NotImplementedError("Person 2: parse_cell")


def format_like(value: float, template: CellNumber) -> str:
    """Write ``value`` in the same style as ``template`` (e.g. 1312.0 like '1,204' -> '1,312')."""
    raise NotImplementedError("Person 2: format_like")
