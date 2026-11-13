"""Image-text consistency checker for Gap 2.

OWNER: Person 5 (Disha). Brief task 1.

  1. a VLM (reuse the generator model) reads the page IMAGE -> table JSON (charts: value list)
  2. parse the page's TEXT layer (Docling output P1 uses) into the same format
  3. align rows/cols by label, compare numbers with tolerance, flag any mismatch
Cheaper mode (configs: img_text_check.only_question_rows): compare only rows
whose label appears in the question.

Expected: catches text_only / image_only, ~0% on propagate (both layers agree on
the wrong value) -> the key blind spot.

Both tables use the shared Table format (src/common/schemas.py):
  {"title": str, "unit_note": str, "header": ["", "2019", "2018"],
   "rows": [["Revenue", "1,204", "1,090"], ...]}
Charts use the same shape: header = ["", "<series>"], rows = [["<bar label>", "<value>"], ...].
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, NotRequired, Optional, TypedDict

from ..common.answer_match import parse_number

LABEL_MATCH = 0.80   # how alike two labels must look to be paired (0-1); absorbs OCR/VLM typos


class CheckResult(TypedDict):
    flag: bool
    mismatches: list[list[Any]]   # [[row_label, col_label, img_val, text_val], ...]
    unmatched: NotRequired[dict[str, list[str]]]   # rows/cols seen on one side only (info, never flags)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def norm_label(label: Any) -> str:
    """' Net  Income*' -> 'net income' (lowercase, letters/digits only, single spaces)."""
    s = re.sub(r"[^a-z0-9]+", " ", str(label or "").lower())
    return " ".join(s.split())


def label_similarity(a: Any, b: Any) -> float:
    """0-1 score for how alike two labels look."""
    a, b = norm_label(a), norm_label(b)
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def cells_equal(img_cell: Any, text_cell: Any, rel_tol: float = 0.01) -> bool:
    """Same value? Numbers with relative tolerance (uses the shared parser), text after normalising."""
    a, b = parse_number(img_cell), parse_number(text_cell)
    if a is not None and b is not None:
        return a == b or abs(a - b) <= rel_tol * max(abs(a), abs(b))
    if a is None and b is None:
        return norm_label(img_cell) == norm_label(text_cell)
    return False


def align(labels_a: list[Any], labels_b: list[Any], threshold: float = LABEL_MATCH) -> list[tuple[int, int]]:
    """Pair two label lists IN ORDER (rows or columns). Returns [(i, j), ...].

    Order-preserving alignment (dynamic programming), so repeated labels such
    as two "Total" rows pair with the right partner, and fuzzy similarity
    tolerates OCR/VLM typos ("Reveune" ~ "Revenue").
    """
    n, m = len(labels_a), len(labels_b)
    sim = [[label_similarity(labels_a[i], labels_b[j]) for j in range(m)] for i in range(n)]
    best = [[0.0] * (m + 1) for _ in range(n + 1)]   # best[i][j]: score using a[i:], b[j:]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            take = sim[i][j] + best[i + 1][j + 1] if sim[i][j] >= threshold else -1.0
            best[i][j] = max(best[i + 1][j], best[i][j + 1], take)
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        if sim[i][j] >= threshold and abs(best[i][j] - (sim[i][j] + best[i + 1][j + 1])) < 1e-9:
            pairs.append((i, j))
            i, j = i + 1, j + 1
        elif best[i + 1][j] >= best[i][j + 1]:
            i += 1
        else:
            j += 1
    return pairs


def rows_named_in_question(table: dict[str, Any], question: str) -> list[str]:
    """Row labels that appear in the question (for the cheaper only_question_rows mode)."""
    q = norm_label(question)
    labels = [r[0] for r in table.get("rows") or [] if r]
    return [lab for lab in labels if len(norm_label(lab)) >= 3 and norm_label(lab) in q]


# ---------------------------------------------------------------------------
# Step 3: compare (pure logic, no model)
# ---------------------------------------------------------------------------
def compare_tables(img_table: dict[str, Any], text_table: dict[str, Any], rel_tol: float = 0.01,
                   only_rows: Optional[list[str]] = None) -> CheckResult:
    """Compare the table read from the image with the table from the text layer.

    only_rows: if given, compare only rows whose label matches one of these
    (falls back to all rows if none match, so the check never silently does nothing).
    """
    mismatches: list[list[Any]] = []
    unmatched: dict[str, list[str]] = {}

    # 1. Unit note ("in millions" vs "in thousands"): cheap, strong signal
    u_img, u_txt = img_table.get("unit_note") or "", text_table.get("unit_note") or ""
    if norm_label(u_img) and norm_label(u_txt) and norm_label(u_img) != norm_label(u_txt):
        mismatches.append(["<unit_note>", None, u_img, u_txt])

    # 2. Columns: pair by header (header[0] is the row-label column)
    h_img = list(img_table.get("header") or [])[1:]
    h_txt = list(text_table.get("header") or [])[1:]
    col_pairs = align(h_img, h_txt)
    if not col_pairs and len(h_img) == len(h_txt):           # headers unreadable -> by position
        col_pairs = [(k, k) for k in range(len(h_img))]
    used_a, used_b = {a for a, _ in col_pairs}, {b for _, b in col_pairs}
    unmatched["cols_img_only"] = [h for k, h in enumerate(h_img) if k not in used_a]
    unmatched["cols_text_only"] = [h for k, h in enumerate(h_txt) if k not in used_b]

    # 3. Rows: pair by label
    r_img = [r for r in img_table.get("rows") or [] if r]
    r_txt = [r for r in text_table.get("rows") or [] if r]
    row_pairs = align([r[0] for r in r_img], [r[0] for r in r_txt])
    used_a, used_b = {a for a, _ in row_pairs}, {b for _, b in row_pairs}
    unmatched["rows_img_only"] = [r_img[a][0] for a in range(len(r_img)) if a not in used_a]
    unmatched["rows_text_only"] = [r_txt[b][0] for b in range(len(r_txt)) if b not in used_b]

    if only_rows:
        wanted = [norm_label(x) for x in only_rows]
        focused = [(a, b) for a, b in row_pairs
                   if any(label_similarity(r_img[a][0], w) >= LABEL_MATCH for w in wanted)]
        row_pairs = focused or row_pairs

    # 4. Compare every paired cell
    for a, b in row_pairs:
        row_i, row_t = r_img[a], r_txt[b]
        for ci, ct in col_pairs:
            v_img = row_i[ci + 1] if ci + 1 < len(row_i) else None
            v_txt = row_t[ct + 1] if ct + 1 < len(row_t) else None
            if not cells_equal(v_img, v_txt, rel_tol):
                mismatches.append([row_i[0], h_img[ci], v_img, v_txt])

    return {"flag": bool(mismatches), "mismatches": mismatches, "unmatched": unmatched}


# ---------------------------------------------------------------------------
# Steps 1-2 and the page-level entry point (Friday, once real pages exist)
# ---------------------------------------------------------------------------
def extract_table_from_image(image_path: str, generator: Any) -> dict[str, Any]:
    """VLM prompt -> table JSON. Save the prompt in configs/prompts/ (e.g. img_extract_v1.txt)."""
    raise NotImplementedError("Person 5: extract_table_from_image")


def check_page(page_id: str, question: Optional[str] = None, cfg: Optional[dict] = None) -> CheckResult:
    raise NotImplementedError("Person 5: check_page")
