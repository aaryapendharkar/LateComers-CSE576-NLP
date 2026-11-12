"""Table <-> text helpers shared by the data loader and the stand-in P1 pipeline.

OWNER: Person 1. (Cell-level number parsing that preserves formatting for
edits lives in Person 2's ``src/attacks/tables/numbers.py``.)
"""

from __future__ import annotations

import re
from typing import Any

_UNIT_RE = re.compile(
    r"\(?\s*(?:dollars\s+|amounts\s+)?in\s+(thousands|millions|billions)(?:\s+of\s+dollars)?"
    r"(?:\s*,?\s*except[^)]*)?\s*\)?",
    re.IGNORECASE,
)


def table_to_markdown(table: dict[str, Any]) -> str:
    header = [str(h) for h in table["header"]]
    lines = []
    if table.get("title"):
        lines.append(table["title"])
    if table.get("unit_note"):
        lines.append(f"({table['unit_note']})")
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join("---" for _ in header) + "|")
    for row in table["rows"]:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def doc_to_text(doc: dict[str, Any]) -> str:
    """Stand-in page text (Day 1, before rendered pages exist): pre_text + table + post_text."""
    parts = [doc.get("pre_text", ""), table_to_markdown(doc["table"]), doc.get("post_text", "")]
    return "\n\n".join(p for p in parts if p)


def _split_md_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_sep_row(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in cells if c) and any(cells)


def split_markdown_context(context: str) -> tuple[str, list[list[str]], str]:
    """Split a T2-RAGBench style context into (pre_text, table_rows, post_text).

    Takes the FIRST contiguous block of ``|``-lines as the table. Table rows
    include the header row first; the markdown separator row is dropped.
    """
    lines = context.splitlines()
    start = end = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith("|"):
            if start is None:
                start = i
            end = i
        elif start is not None:
            break
    if start is None:
        return context.strip(), [], ""
    rows = [_split_md_row(ln) for ln in lines[start:end + 1]]
    rows = [r for r in rows if not _is_sep_row(r)]
    pre = "\n".join(lines[:start]).strip()
    post = "\n".join(lines[end + 1:]).strip()
    return pre, rows, post


def rows_to_table(rows: list[list[str]], pre_text: str = "", title: str = "") -> dict[str, Any]:
    """Normalise a list of rows (header first) into the A6 table dict."""
    if not rows:
        return {"title": title, "unit_note": "", "header": [], "rows": []}
    width = max(len(r) for r in rows)
    norm = [list(r) + [""] * (width - len(r)) for r in rows]
    return {
        "title": title,
        "unit_note": guess_unit_note(pre_text),
        "header": [str(c) for c in norm[0]],
        "rows": [[str(c) for c in r] for r in norm[1:]],
    }


def guess_unit_note(text: str) -> str:
    """Find 'in millions' etc. in the text right before a table (last match wins)."""
    matches = list(_UNIT_RE.finditer(text[-600:] if text else ""))
    return f"in {matches[-1].group(1).lower()}" if matches else ""
