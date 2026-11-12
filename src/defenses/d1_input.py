"""PROVISIONAL detector-input adapter for D1 (Person 3).

Why this module exists
----------------------
D1 must see only what the pipeline sees at its position (after reranking,
before generation): the observed parsed page. Person 1 has not yet published
the parsed-page interface (the A6 brief defines pages.jsonl with a text_path,
but not the parsed-table format Docling output will be converted to). Until
that is agreed, this module isolates the assumption in one place:

    ParsedPage = optional parsed table (header, rows, title, unit note)
                 + the surrounding prose that the parser produced.

Two adapters are provided:

* page_from_record(): from an A6-style dict {"table", "pre_text", "post_text"}.
  Used for hand-written development fixtures and for docs.jsonl dry runs.
  This is CLEAN STRUCTURED JSON, not an observed parse -- results from it
  must never be reported as pipeline evaluation.
* page_from_markdown(): a minimal parser for a markdown pipe table plus prose
  (the shape of Docling's markdown export). Provisional until Person 1 confirms
  the real format.

Leakage guard: a ParsedPage carries no page_id, doc_id, variant or attack
fields (page ids like "<doc>__G1_consistent_q0001" encode the attack label).
page_from_record() rejects records that contain any key outside the allowlist,
so attack metadata or answers cannot be passed to the detector by accident.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ALLOWED_RECORD_KEYS = {"table", "pre_text", "post_text", "text"}
ALLOWED_TABLE_KEYS = {"title", "unit_note", "header", "rows"}

# Fields that must never reach the detector (documented for reviewers; the
# allowlist above is what actually enforces it).
FORBIDDEN_EXAMPLES = (
    "page_id", "doc_id", "variant", "attack_id", "attack_type", "edit",
    "also_changed", "target_answer", "gold_answer", "clean_page_id",
    "poison_page_id", "program", "qid", "image_version", "text_version",
)


class DetectorInputError(ValueError):
    """Raised when a record offered to D1 contains non-permitted fields."""


@dataclass(frozen=True)
class ParsedTable:
    header: list[str]
    rows: list[list[str]]
    title: str = ""
    unit_note: str = ""


@dataclass(frozen=True)
class ParsedPage:
    """Everything D1 is allowed to look at for one page."""

    table: ParsedTable | None
    prose: str = ""
    input_kind: str = "unspecified"  # "observed_parse" | "clean_structured_json" | "synthetic_fixture"
    notes: tuple[str, ...] = field(default_factory=tuple)


def page_from_record(record: dict, input_kind: str) -> ParsedPage:
    """Build a ParsedPage from an A6-style table record, enforcing the allowlist."""
    extra = set(record) - ALLOWED_RECORD_KEYS
    if extra:
        raise DetectorInputError(
            f"D1 input contains non-permitted keys {sorted(extra)}; "
            "pass only table/pre_text/post_text (attack metadata, ids and answers "
            "belong to the evaluator)."
        )
    table = None
    raw_table = record.get("table")
    if raw_table is not None:
        extra_t = set(raw_table) - ALLOWED_TABLE_KEYS
        if extra_t:
            raise DetectorInputError(f"table contains non-permitted keys {sorted(extra_t)}")
        table = ParsedTable(
            header=[str(h) for h in raw_table.get("header", [])],
            rows=[[str(c) for c in row] for row in raw_table.get("rows", [])],
            title=str(raw_table.get("title") or ""),
            unit_note=str(raw_table.get("unit_note") or ""),
        )
    prose = " ".join(
        part for part in (record.get("pre_text"), record.get("text"), record.get("post_text")) if part
    )
    return ParsedPage(table=table, prose=prose, input_kind=input_kind)


_PIPE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def page_from_markdown(markdown: str) -> ParsedPage:
    """PROVISIONAL: parse the first markdown pipe table; other lines are prose.

    The line directly above the table (if any) is treated as the table title,
    which is where unit notes such as "(in millions)" usually appear. Only the
    first table is used; additional tables are reported in `notes` so the page
    is not silently treated as fully checked.
    """
    lines = markdown.splitlines()
    blocks: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        if _PIPE_ROW.match(lines[i]):
            j = i
            while j < len(lines) and _PIPE_ROW.match(lines[j]):
                j += 1
            blocks.append((i, j))
            i = j
        else:
            i += 1
    if not blocks:
        return ParsedPage(table=None, prose=" ".join(l.strip() for l in lines if l.strip()),
                          input_kind="observed_parse", notes=("no_markdown_table",))

    start, end = blocks[0]
    table_lines = [l for l in lines[start:end] if not _SEPARATOR.match(l)]
    cells = [[c.strip() for c in l.strip().strip("|").split("|")] for l in table_lines]
    header, rows = cells[0], cells[1:]

    title = ""
    prose_lines = []
    for k, line in enumerate(lines):
        if start <= k < end:
            continue
        if any(s <= k < e for s, e in blocks[1:]):
            continue
        if k == start - 1 and line.strip():
            title = line.strip()  # also kept as prose: it may be a paragraph
        if line.strip():
            prose_lines.append(line.strip())
    notes = ("additional_tables_ignored",) if len(blocks) > 1 else ()
    return ParsedPage(
        table=ParsedTable(header=header, rows=rows, title=title),
        prose=" ".join(prose_lines),
        input_kind="observed_parse",
        notes=notes,
    )


# Fields of a FinQA source record that D1 may see. Everything else (id,
# filename, qa: question/answer/program/gold_inds, retrieval scores, the
# normalized `table`) stays with the evaluator.
FINQA_DETECTOR_FIELDS = ("table_ori", "pre_text", "post_text")


def record_from_finqa(entry: dict) -> dict:
    """Project one FinQA source record onto the D1 record allowlist.

    * table_ori (original formatting, e.g. "$(23,158)") is used, not the
      normalized `table`; its first row is taken as the header (FinQA has no
      separate header field).
    * pre_text/post_text are FinQA's own lowercased, tokenized sentences,
      joined with spaces and otherwise unchanged.
    * No title or unit note is added: FinQA has none, and a unit is never
      inferred from the surrounding prose.
    """
    rows = [[str(c) for c in row] for row in entry["table_ori"]]
    return {
        "table": {"header": rows[0], "rows": rows[1:]} if rows else None,
        "pre_text": " ".join(entry.get("pre_text") or []),
        "post_text": " ".join(entry.get("post_text") or []),
    }
