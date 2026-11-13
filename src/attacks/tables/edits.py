"""Gap 1 edit generator: consistent_cell, naive_cell, unit, header.

OWNER: Person 2 (Janhavi) -- Gap 1 attacks. Brief tasks 5-7.

Output: Attack rows (src/common/schemas.Attack) with ``edit`` in the format of
src/common/edits.py, appended to data/attacks/g1.jsonl, plus the poisoned page
rendered with Person 4's render_table_page(image_table=text_table=edited table),
whose record goes to data/manifests/pages_g1.jsonl.

Page id: <doc_id>__G1_<attack_type>_<qid>  -> use schemas.poison_page_id().
Keep only edits whose target differs from gold by > 5% relative (or flips yes/no).

Design notes (so the "why" survives a re-read later):

* ``make_consistent_cell`` edits ONE cell the program actually reads, then
  walks ``dependencies.dependents()`` to push the same change through every
  total/subtotal that cell feeds (possibly on both axes, possibly totals of
  totals). The target answer is computed by re-running the ORIGINAL program
  against the fully-edited table: every table-sourced argument is refreshed
  to whatever value now sits at that cell (``_refresh_program``), and
  ``table_*`` ops automatically pick up the new numbers because they read
  the row straight out of whichever table ``execute()`` is given. This is
  also how a "cancelling" edit is caught and rejected: if the program's net
  effect is unchanged (e.g. it reads both a part and the total that just
  absorbed the same change), the refreshed execution reproduces the old
  answer and ``keep_edit`` correctly says no.

* ``make_naive_cell`` is the B1 baseline: the identical cell edit, but
  ``also_changed`` is dropped, so every total on the page stays stale and
  the page's own arithmetic no longer reconciles. Its stub signature has no
  access to the original ``Example``/program, so ``make_consistent_cell``
  stashes the program text in the consistent Attack's ``extra`` field
  (an optional, additive field the shared schema explicitly allows) purely
  so the naive counterpart can independently recompute an accurate target
  answer instead of assuming it is identical to the consistent one -- the
  two CAN differ when the program itself reads one of the totals that only
  the consistent edit keeps correct.

* ``make_header_edit`` only touches the header TEXT (swapping two year
  labels), because that is what ``common/edits.py``'s "header" field edit
  actually does -- the body data never moves. The deceptive effect of a
  label swap is identical to swapping the data: whichever column is now
  mislabeled "2019" physically holds the old 2018 numbers. To compute the
  target answer we build a throwaway SCRATCH table with the data swapped
  instead (headers untouched) and re-run the original program's cell
  coordinates against that -- this is only ever used for the target-answer
  calculation, never written into the actual ``edit`` record.
"""

from __future__ import annotations

import random
import re
from typing import Any, Optional

from ...common.answer_match import numbers_match
from ...common.edits import apply_edit
from ...common.schemas import Attack, Doc, Example, attack_id, clean_page_id, poison_page_id
from .dependencies import Cell, TotalRelation, dependents, find_totals
from .finqa_program import Step, answer_to_str, execute, map_arguments, parse_program
from .numbers import format_like, parse_cell

_SCALE = {"thousand": 1e3, "million": 1e6, "billion": 1e9}
_SCALE_ORDER = ["thousand", "million", "billion"]


# --------------------------------------------------------------------------- #
# helpers shared by the four generators
# --------------------------------------------------------------------------- #

def _refresh_program(program: str | list[Step], arg_sources, table: dict[str, Any]) -> list[Step]:
    """Rebuild the program, replacing every table-sourced argument's literal
    text with whatever value now sits at that same cell in ``table``.
    const_/#n arguments pass through untouched. table_* ops need no
    substitution here: they read their row straight out of ``table`` at
    execution time."""
    steps = parse_program(program) if isinstance(program, str) else list(program)
    by_step: dict[int, dict[int, Cell]] = {}
    for a in arg_sources:
        if a.kind == "table" and a.cell is not None:
            by_step.setdefault(a.step, {})[a.arg_index] = a.cell

    new_steps: list[Step] = []
    for i, step in enumerate(steps):
        args = list(step.args)
        for j, cell in by_step.get(i, {}).items():
            r, c = cell
            p = parse_cell(table["rows"][r - 1][c])
            if p is not None:
                args[j] = repr(p.value)
        new_steps.append(Step(op=step.op, args=args))
    return new_steps


def _apply_consistent_edit(
    table: dict[str, Any], cell: Cell, new_value: float, relations: list[TotalRelation]
) -> tuple[str, list[list[Any]]]:
    """Format the edited cell's new text, then cascade the same change
    through every total that depends on it (``dependents()`` already
    returns them in a valid order: a total only appears after every part of
    it that will change has already been resolved). Returns
    (new_cell_str, also_changed) where also_changed is a list of
    [row, col, old_str, new_str] -- the shape ``common/edits.py`` expects."""
    row, col = cell
    old_str = table["rows"][row - 1][col]
    template = parse_cell(old_str)
    new_str = format_like(new_value, template)

    current_value: dict[Cell, float] = {cell: new_value}
    also_changed: list[list[Any]] = []

    by_total = {rel.total: rel for rel in relations}
    for total_cell in dependents(cell, relations):
        rel = by_total[total_cell]
        tr, tc = total_cell
        total_old_str = table["rows"][tr - 1][tc]
        total_template = parse_cell(total_old_str)
        if total_template is None:
            continue

        part_vals = []
        ok = True
        for pr, pc in rel.parts:
            if (pr, pc) in current_value:
                part_vals.append(current_value[(pr, pc)])
                continue
            p = parse_cell(table["rows"][pr - 1][pc])
            if p is None:
                ok = False
                break
            part_vals.append(p.value)
        if not ok:
            continue

        signs = rel.sign if rel.sign else [1] * len(part_vals)
        new_total_val = sum(v * s for v, s in zip(part_vals, signs))
        new_total_str = format_like(new_total_val, total_template)
        current_value[total_cell] = new_total_val
        also_changed.append([tr, tc, total_old_str, new_total_str])

    return new_str, also_changed


def _detect_scale(text: str) -> Optional[str]:
    low = (text or "").lower()
    for word in _SCALE_ORDER:
        if word in low:
            return word
    return None


def _find_year_columns(header: list[str]) -> dict[int, str]:
    years: dict[int, str] = {}
    for i, cell in enumerate(header):
        t = str(cell).strip()
        if t.isdigit() and len(t) == 4:
            years[i] = t
    return years


# --------------------------------------------------------------------------- #
# the four generators
# --------------------------------------------------------------------------- #

def make_consistent_cell(ex: Example, doc: Doc, rng: random.Random) -> Optional[Attack]:
    """Change one cell the program reads by ±5-25% (same format) and propagate to every total."""
    if not ex.program:
        return None
    try:
        arg_sources = map_arguments(ex.program, doc.to_dict())
    except Exception:
        return None

    relations = find_totals(doc.table)
    total_cells = {rel.total for rel in relations}

    seen: set[Cell] = set()
    candidates = []
    for a in arg_sources:
        if a.kind == "table" and a.cell is not None and a.cell not in total_cells and a.cell not in seen:
            seen.add(a.cell)
            candidates.append(a)
    if not candidates:
        return None

    order = list(range(len(candidates)))
    rng.shuffle(order)

    for idx in order:
        cell = candidates[idx].cell
        row, col = cell
        old_str = doc.table["rows"][row - 1][col]
        template = parse_cell(old_str)
        if template is None:
            continue

        factor = 1 + rng.choice([-1, 1]) * rng.uniform(0.05, 0.25)
        new_val = template.value * factor

        new_str, also_changed = _apply_consistent_edit(doc.table, cell, new_val, relations)
        edit = {"row": row, "col": col, "old": old_str, "new": new_str, "also_changed": also_changed}

        try:
            edited_table = apply_edit(doc.table, edit)
            refreshed = _refresh_program(ex.program, arg_sources, edited_table)
            target_val = execute(refreshed, edited_table).value
        except Exception:
            continue
        target_str = answer_to_str(target_val)

        if not keep_edit(ex.gold_answer, target_str):
            continue

        return Attack(
            attack_id=attack_id("G1", "consistent_cell", ex.qid),
            qid=ex.qid,
            gap="G1",
            attack_type="consistent_cell",
            clean_page_id=clean_page_id(doc.doc_id),
            poison_page_id=poison_page_id(doc.doc_id, "G1", "consistent_cell", ex.qid),
            edit=edit,
            target_answer=target_str,
            image_version="poison",
            text_version="poison",
            gold_answer=ex.gold_answer,
            extra={"program": ex.program},
        )

    return None


def make_naive_cell(consistent: Attack, doc: Doc) -> Attack:
    """B1 baseline: the IDENTICAL cell change as ``consistent``, totals left untouched."""
    edit = {**consistent.edit, "also_changed": []}
    program = consistent.extra.get("program") if consistent.extra else None

    target_str = consistent.target_answer
    if program:
        try:
            arg_sources = map_arguments(program, doc.to_dict())
            edited_table = apply_edit(doc.table, edit)
            refreshed = _refresh_program(program, arg_sources, edited_table)
            target_str = answer_to_str(execute(refreshed, edited_table).value)
        except Exception:
            target_str = consistent.target_answer

    return Attack(
        attack_id=attack_id("G1", "naive_cell", consistent.qid),
        qid=consistent.qid,
        gap="G1",
        attack_type="naive_cell",
        clean_page_id=consistent.clean_page_id,
        poison_page_id=poison_page_id(doc.doc_id, "G1", "naive_cell", consistent.qid),
        edit=edit,
        target_answer=target_str,
        image_version="poison",
        text_version="poison",
        gold_answer=consistent.gold_answer,
        extra={"program": program} if program else {},
    )


def make_unit_edit(ex: Example, doc: Doc) -> Optional[Attack]:
    """'in thousands' -> 'in millions' etc.; target = answer rescaled when it is an amount."""
    if not ex.program:
        return None

    old_unit = doc.table.get("unit_note", "") or ""
    word = _detect_scale(old_unit)
    if word is None:
        return None

    try:
        steps = parse_program(ex.program)
    except Exception:
        return None
    if any(s.op == "divide" for s in steps):
        return None  # a ratio of two amounts in the same unit is unaffected by a unit edit

    try:
        gold_val = execute(steps, doc.table).value
    except Exception:
        return None
    if isinstance(gold_val, bool):
        return None  # yes/no answers have no "amount" to rescale

    i = _SCALE_ORDER.index(word)
    new_word = _SCALE_ORDER[i + 1] if i < len(_SCALE_ORDER) - 1 else _SCALE_ORDER[i - 1]
    new_unit = re.sub(word, new_word, old_unit, count=1, flags=re.IGNORECASE)
    target_val = gold_val * _SCALE[new_word] / _SCALE[word]
    target_str = answer_to_str(round(target_val, 6))

    if not keep_edit(ex.gold_answer, target_str):
        return None

    edit = {"field": "unit_note", "old": old_unit, "new": new_unit}
    return Attack(
        attack_id=attack_id("G1", "unit", ex.qid),
        qid=ex.qid,
        gap="G1",
        attack_type="unit",
        clean_page_id=clean_page_id(doc.doc_id),
        poison_page_id=poison_page_id(doc.doc_id, "G1", "unit", ex.qid),
        edit=edit,
        target_answer=target_str,
        image_version="poison",
        text_version="poison",
        gold_answer=ex.gold_answer,
    )


def make_header_edit(ex: Example, doc: Doc) -> Optional[Attack]:
    """Swap two year column headers; target = program re-run on the swapped table."""
    if not ex.program:
        return None

    header = doc.table["header"]
    years = _find_year_columns(header)
    if len(years) < 2:
        return None
    (col_a, year_a), (col_b, year_b) = list(years.items())[:2]
    if year_a not in ex.question and year_b not in ex.question:
        return None

    try:
        arg_sources = map_arguments(ex.program, doc.to_dict())
    except Exception:
        return None

    # scratch-only table (headers untouched) used purely to compute what a
    # reader misled by the swapped labels would read off the page
    swapped_rows = []
    for row in doc.table["rows"]:
        r = list(row)
        if col_a < len(r) and col_b < len(r):
            r[col_a], r[col_b] = r[col_b], r[col_a]
        swapped_rows.append(r)
    swapped_table = {**doc.table, "rows": swapped_rows}

    try:
        refreshed = _refresh_program(ex.program, arg_sources, swapped_table)
        target_val = execute(refreshed, swapped_table).value
    except Exception:
        return None
    target_str = answer_to_str(target_val)

    if not keep_edit(ex.gold_answer, target_str):
        return None

    new_header = list(header)
    new_header[col_a], new_header[col_b] = new_header[col_b], new_header[col_a]
    edit = {"field": "header", "old": list(header), "new": new_header}

    return Attack(
        attack_id=attack_id("G1", "header", ex.qid),
        qid=ex.qid,
        gap="G1",
        attack_type="header",
        clean_page_id=clean_page_id(doc.doc_id),
        poison_page_id=poison_page_id(doc.doc_id, "G1", "header", ex.qid),
        edit=edit,
        target_answer=target_str,
        image_version="poison",
        text_version="poison",
        gold_answer=ex.gold_answer,
    )


def keep_edit(gold: str, target: str, min_rel_diff: float = 0.05) -> bool:
    """True if the target differs enough from gold (>5% relative, or a yes/no flip).

    Reuses the project's one official "same answer" definition
    (``numbers_match``, with its yes/no and percent-scaling handling) rather
    than reimplementing it: keep the edit exactly when gold and target do
    NOT count as matching at this (widened) tolerance.
    """
    if gold is None or target is None:
        return False
    return not numbers_match(target, gold, rel_tol=min_rel_diff, abs_tol=1e-6)


def generate_all(examples: dict[str, Example], docs: dict[str, Doc], cfg: dict[str, Any]) -> list[Attack]:
    g1_cfg = (cfg or {}).get("attacks_g1", {})
    n_per_type = g1_cfg.get("n_per_type", 50)
    seed = (cfg or {}).get("seed", 0)

    attacks: list[Attack] = []
    n_consistent = n_unit = n_header = 0

    for qid in sorted(examples):
        ex = examples[qid]
        if ex.source != "finqa" or ex.doc_id not in docs:
            continue
        doc = docs[ex.doc_id]

        if n_consistent < n_per_type:
            rng = random.Random(f"{seed}-{qid}")
            consistent = make_consistent_cell(ex, doc, rng)
            if consistent is not None:
                attacks.append(consistent)
                attacks.append(make_naive_cell(consistent, doc))
                n_consistent += 1

        if n_unit < n_per_type:
            unit = make_unit_edit(ex, doc)
            if unit is not None:
                attacks.append(unit)
                n_unit += 1

        if n_header < n_per_type:
            header = make_header_edit(ex, doc)
            if header is not None:
                attacks.append(header)
                n_header += 1

    return attacks