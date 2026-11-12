"""FinQA program executor + argument-to-cell mapping.

OWNER: Person 2 (Janhavi) -- Gap 1 attacks. Brief task 3.

Program syntax (FinQA), e.g. ``subtract(1204, 1090), divide(#0, 1090)``:
  ops: add, subtract, multiply, divide, exp, greater,
       table_max, table_min, table_sum, table_average   (table_* take a ROW LABEL)
  args: numbers, #n (result of step n), const_* (e.g. const_100, const_m1 = -1)

Done when: executing every program on its clean table reproduces gold for >= 95%
of questions (drop the rest and report the drop rate).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Union

Value = Union[float, bool]


@dataclass
class Step:
    op: str
    args: list[str]


@dataclass
class ArgSource:
    """Where a numeric argument came from."""
    step: int
    arg_index: int
    value: float
    kind: str                                   # "table" | "text" | "const" | "step_ref"
    cell: Optional[tuple[int, int]] = None      # GRID (row, col) if kind == "table" (row 0 = header)
    row_label: Optional[str] = None             # for table_* ops: the whole row


@dataclass
class ExecResult:
    value: Value
    steps: list[Value] = field(default_factory=list)


def parse_program(program: str) -> list[Step]:
    """'subtract(1204, 1090), divide(#0, 1090)' -> [Step('subtract', ['1204','1090']), ...]."""
    raise NotImplementedError("Person 2: parse_program")


def execute(program: str | list[Step], table: dict[str, Any]) -> ExecResult:
    """Run the program. ``table`` (A6 format) is needed for table_* ops."""
    raise NotImplementedError("Person 2: execute")


def map_arguments(program: str | list[Step], doc: dict[str, Any]) -> list[ArgSource]:
    """For each numeric argument find the table cell it came from (or mark it text/const)."""
    raise NotImplementedError("Person 2: map_arguments")


def answer_to_str(value: Value) -> str:
    """Format an executed value like the gold answers ('yes'/'no' for greater)."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return f"{value:.6g}"
