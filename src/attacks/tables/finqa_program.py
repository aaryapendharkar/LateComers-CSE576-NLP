"""FinQA program executor + argument-to-cell mapping.

OWNER: Person 2 (Janhavi) -- Gap 1 attacks. Brief task 3.

Program syntax (FinQA), e.g. ``subtract(1204, 1090), divide(#0, 1090)``:
  ops: add, subtract, multiply, divide, exp, greater,
       table_max, table_min, table_sum, table_average   (table_* take a ROW LABEL)
  args: numbers, #n (result of step n), const_* (e.g. const_100, const_m1 = -1)

Done when: executing every program on its clean table reproduces gold for >= 95%
of questions (drop the rest and report the drop rate).

Cell coordinates everywhere here are GRID coordinates: GRID = [header] + rows,
so row 0 is the header row and row 1 is the first body row (matches A6 / the
row/col convention ``src/common/edits.py`` uses for ``attack["edit"]``).

``table_*`` ops select an entire ROW by its label (column 0 of a body row,
matched case-insensitively, whitespace-trimmed) and reduce over every OTHER
column in that row. The second argument to a ``table_*`` call is always the
literal ``none`` in FinQA and carries no information; we ignore it.

``map_arguments`` classifies every numeric program argument as one of:
  "const"     a literal constant (``const_100``, ``const_m1``)
  "step_ref"  a reference to an earlier step's result (``#0``)
  "table"     a literal number that matches EXACTLY ONE table cell
  "text"      a literal number that matches zero, or more than one, table
              cell -- so it is either not in the table at all (it came from
              the surrounding pre/post text) or is ambiguous between several
              cells. We don't have a separate "ambiguous" bucket (the kind
              vocabulary is fixed to these four), so an ambiguous number is
              lumped into "text": either way, it is NOT a cell we can safely
              edit, which is the only thing that distinction is used for.
A ``table_*`` op's row-label argument also gets one ArgSource (kind="table",
cell=None, row_label=<the matched row's label>, value=the step's own
computed result), since it reads a whole row rather than one cell. Its
"none" argument is skipped entirely -- it isn't a numeric argument.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional, Union

from .numbers import parse_cell

Value = Union[float, bool]

_ARITH_OPS = {"add", "subtract", "multiply", "divide", "exp", "greater"}
_TABLE_OPS = {"table_max", "table_min", "table_sum", "table_average"}
_NUM_RE = re.compile(r"^\d[\d,]*(?:\.\d+)?$")


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


def _literal_to_number(arg: str) -> float:
    """A plain program-literal number: strip $ , % and commas; no percent scaling
    (FinQA writes an already-percent-scale argument as e.g. "5.2%" meaning 5.2,
    not 0.052)."""
    t = arg.strip()
    for ch in ("$", "%", " "):
        t = t.replace(ch, "")
    return float(t.replace(",", ""))


def _split_step_text(text: str) -> list[tuple[str, str]]:
    """Split 'op(args), op(args), ...' into [(op, arg_string), ...], respecting
    nested parens (there aren't any in FinQA, but this is cheap safety)."""
    out = []
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i] in " ,":
            i += 1
        if i >= n:
            break
        j = text.index("(", i)
        op = text[i:j].strip()
        depth, k = 0, j
        while k < n:
            if text[k] == "(":
                depth += 1
            elif text[k] == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        out.append((op, text[j + 1:k]))
        i = k + 1
    return out


def parse_program(program: str) -> list[Step]:
    """'subtract(1204, 1090), divide(#0, 1090)' -> [Step('subtract', ['1204','1090']), ...].

    For table_* ops the row label may itself contain commas, so only the
    LAST comma in the argument string is treated as the separator before the
    trailing "none".
    """
    steps = []
    for op, arg_str in _split_step_text(program):
        if op in _TABLE_OPS:
            label, _, last = arg_str.rpartition(",")
            args = [label.strip(), last.strip()]
        else:
            args = [a.strip() for a in arg_str.split(",")]
        steps.append(Step(op=op, args=args))
    return steps


def _row_lookup(table: dict[str, Any]) -> dict[str, list[str]]:
    """label (lowercased, trimmed) -> that row's cells AFTER the label column."""
    return {row[0].strip().lower(): row[1:] for row in table["rows"] if row}


def _table_op_value(op: str, cells: list[str]) -> float:
    nums = [p.value for p in (parse_cell(c) for c in cells) if p is not None]
    if not nums:
        raise ValueError(f"{op}: no numeric cells in the selected row")
    if op == "table_max":
        return max(nums)
    if op == "table_min":
        return min(nums)
    if op == "table_sum":
        return sum(nums)
    return sum(nums) / len(nums)  # table_average


def _resolve(arg: str, results: list[Value]) -> Value:
    if arg.startswith("#"):
        return results[int(arg[1:])]
    if arg.startswith("const_"):
        tail = arg[len("const_"):]
        return -1.0 if tail == "m1" else float(tail)
    return _literal_to_number(arg)


def execute(program: str | list[Step], table: dict[str, Any]) -> ExecResult:
    """Run the program. ``table`` (A6 format) is needed for table_* ops."""
    steps = parse_program(program) if isinstance(program, str) else program
    rows_by_label = _row_lookup(table)
    results: list[Value] = []

    for step in steps:
        if step.op in _TABLE_OPS:
            label = step.args[0].strip().lower()
            if label not in rows_by_label:
                raise KeyError(f"table op {step.op}: no row labelled {step.args[0]!r}")
            value: Value = _table_op_value(step.op, rows_by_label[label])
        elif step.op in _ARITH_OPS:
            a = _resolve(step.args[0], results)
            b = _resolve(step.args[1], results)
            if step.op == "add":
                value = a + b
            elif step.op == "subtract":
                value = a - b
            elif step.op == "multiply":
                value = a * b
            elif step.op == "divide":
                value = a / b
            elif step.op == "exp":
                value = a ** b
            else:  # greater
                value = bool(a > b)
        else:
            raise ValueError(f"unknown FinQA op {step.op!r}")

        if isinstance(value, float):
            value = round(value, 6)
        results.append(value)

    return ExecResult(value=results[-1], steps=results)


def _find_cell(table: dict[str, Any], target: float, rel_tol: float = 1e-4) -> Optional[tuple[int, int]]:
    """GRID (row, col) of the single body cell matching ``target`` (row 0 = header).
    Returns None if zero or more than one cell matches (ambiguous -> "text")."""
    hits: list[tuple[int, int]] = []
    for i, row in enumerate(table["rows"]):
        for c in range(1, len(row)):  # skip the label column
            p = parse_cell(row[c])
            if p is not None and abs(p.value - target) <= max(rel_tol * abs(target), 1e-6):
                hits.append((i + 1, c))  # +1: GRID row 0 is the header
    return hits[0] if len(hits) == 1 else None


def map_arguments(program: str | list[Step], doc: dict[str, Any]) -> list[ArgSource]:
    """For each numeric argument find the table cell it came from (or mark it text/const)."""
    steps = parse_program(program) if isinstance(program, str) else program
    table = doc["table"]
    exec_result = execute(steps, table)
    out: list[ArgSource] = []

    for i, step in enumerate(steps):
        if step.op in _TABLE_OPS:
            label_text = step.args[0]
            out.append(ArgSource(step=i, arg_index=0, value=float(exec_result.steps[i]),
                                  kind="table", cell=None, row_label=label_text))
            continue  # the "none" second argument carries no information

        for j, arg in enumerate(step.args):
            if arg.startswith("#"):
                out.append(ArgSource(step=i, arg_index=j, value=float(exec_result.steps[int(arg[1:])]),
                                      kind="step_ref"))
            elif arg.startswith("const_"):
                out.append(ArgSource(step=i, arg_index=j, value=float(_resolve(arg, exec_result.steps)),
                                      kind="const"))
            else:
                value = _literal_to_number(arg)
                cell = _find_cell(table, value)
                out.append(ArgSource(step=i, arg_index=j, value=value,
                                      kind="table" if cell else "text", cell=cell))
    return out


def answer_to_str(value: Value) -> str:
    """Format an executed value like the gold answers ('yes'/'no' for greater)."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return f"{value:.6g}"