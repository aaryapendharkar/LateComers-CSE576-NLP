"""Table page renderer: realistic PDF page whose IMAGE and TEXT layer can differ.

OWNER: Person 4 (Aaron).

Construction (A4), identical for clean and poisoned pages (see ``pdfpage.py``):
  (a) lay out the IMAGE version with reportlab; record every text item's
      (x, y, font, size, string)
  (b) rasterize that PDF to PNG at 150 dpi (pdftoppm)
  (c) final PDF = PNG as full-page background + TEXT-version strings drawn at
      the same coordinates with text render mode 3 (invisible)
ONE layout pass sees both versions, so column positions, row heights and
paragraph blocks are shared and the two layers line up even when strings differ.

Page content, top to bottom (Letter, Times 10.5 pt by default):
  pre_text paragraph, caption, table, post_text paragraph.
The caption is built from the table data (``table_caption``): title or the
first header cell, the unit note, and "key figures" = the first body row and
the total row (last row starting with total/net, else the last row). It is
re-rendered from each version's table, so an edit to either row, or to a cell
whose total gets updated, also shows up in that layer's caption (33 of the 38
current consistent_cell edits).

If a page does not fit, the font shrinks in 0.5 pt steps down to
``render.min_font_size`` (7 pt); only then is prose cut (post_text first, then
pre_text). Tables are never cut. The record says which (``font_size``,
``truncated``).

Output files (under out_dir):  <page_id>.pdf / .png / .txt / .table.json
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional, Sequence

from .pdfpage import (BOLD, ITALIC, PAGE_SIZES, TextItem, TwinFlow, Rule, detokenize, max_word_width,
                      render_cfg, sanitize, width, wrap, write_page)

__all__ = ["TextItem", "layout_page", "render_table_page", "table_caption", "plan_table_page"]

TOTAL_RE = re.compile(r"^\s*(total|net)\b", re.IGNORECASE)
HEADER_WRAP_PT = 64.0      # value-column headers wider than this wrap onto more lines
ABS_MIN_FONT = 5.0         # only very wide tables go below render.min_font_size


# ---------------------------------------------------------------------------
# Caption (data-derived, so it follows each version's table)
# ---------------------------------------------------------------------------

def _cap_first(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _title_of(table: dict[str, Any]) -> str:
    title = sanitize(table.get("title", ""))
    if title:
        return title
    h0 = sanitize((table.get("header") or [""])[0])
    h0 = re.sub(r"\(?\s*(?:dollars\s+|amounts\s+)?in\s+(?:thousands|millions|billions)[^)]*\)?", "", h0,
                flags=re.IGNORECASE).strip(" :;,-")
    if re.search(r"[A-Za-z]{3}", h0):
        return _cap_first(h0)
    return "Selected financial data"


def key_figures_rows(table: dict[str, Any]) -> list[int]:
    """Rows (indices into table['rows']) the caption summarises: the first body
    row and the summary row (the last row whose label starts with total/net,
    else the last row). Depends only on the table, never on an edit, so a clean
    and a poisoned page differ in the caption only where the edit is."""
    rows = table.get("rows") or []
    if not rows:
        return []
    summary = len(rows) - 1
    for i in range(len(rows) - 1, -1, -1):
        if rows[i] and TOTAL_RE.match(sanitize(rows[i][0])):
            summary = i
            break
    return sorted({0, summary})


def _row_summary(row: list[str], header: list[str], max_cols: int) -> str:
    parts = []
    for j in range(1, min(len(row), max_cols + 1)):
        v = sanitize(row[j])
        if not v:
            continue
        h = sanitize(header[j]) if j < len(header) else ""
        parts.append(f"{v} ({h})" if h else v)
    if not parts:
        return ""
    label = sanitize(row[0]) or "Row"
    return f"{label}: {', '.join(parts)}"


def table_caption(table: dict[str, Any], max_cols: int = 6) -> str:
    """'Table 1. <title> (<unit>). Key figures: <first row>; <total row>.'"""
    unit = sanitize(table.get("unit_note", ""))
    cap = f"Table 1. {_title_of(table)}" + (f" ({unit})" if unit else "") + "."
    header = table.get("header") or []
    parts = [_row_summary(table["rows"][i], header, max_cols) for i in key_figures_rows(table)]
    parts = [p for p in parts if p]
    return f"{cap} Key figures: {'; '.join(parts)}." if parts else cap


# ---------------------------------------------------------------------------
# Table geometry shared by both versions
# ---------------------------------------------------------------------------

def _grid(table: dict[str, Any]) -> list[list[str]]:
    return [[sanitize(c) for c in table.get("header") or []]] + \
           [[sanitize(c) for c in r] for r in table.get("rows") or []]


def _pad(grids: Sequence[list[list[str]]]) -> list[list[list[str]]]:
    n_rows = max(len(g) for g in grids)
    n_cols = max((len(r) for g in grids for r in g), default=0)
    return [[(g[i] if i < len(g) else []) + [""] * (n_cols - len(g[i] if i < len(g) else []))
             for i in range(n_rows)] for g in grids]


def _row_font(grid_img: list[list[str]], i: int, font: str, bold: str) -> str:
    if i == 0:
        return bold
    return bold if TOTAL_RE.match(grid_img[i][0] or "") else font


def _col_widths(grids, font, bold, size, avail_w, gap) -> Optional[list[float]]:
    """Column widths (label column first) or None if the table cannot fit at this size."""
    n_cols = len(grids[0][0])
    nat, mn = [], []
    for j in range(n_cols):
        body_full = body_word = head_full = head_word = 0.0
        for g in grids:
            for i, row in enumerate(g):
                f = _row_font(grids[0], i, font, bold)
                w_full, w_word = width(row[j], f, size), max_word_width(row[j], f, size)
                if i == 0:
                    head_full, head_word = max(head_full, w_full), max(head_word, w_word)
                else:
                    body_full, body_word = max(body_full, w_full), max(body_word, w_word)
        if j == 0:
            natural = max(body_full, head_full)
            minimum = max(body_word, head_word, min(natural, size * 8))
        else:
            natural = max(body_full, head_word, min(head_full, max(body_full, HEADER_WRAP_PT)), size * 2)
            minimum = max(body_word, head_word, size * 2)
        nat.append(natural)
        mn.append(min(minimum, natural))
    room = avail_w - gap * (n_cols - 1)
    total = sum(nat)
    if total <= room:
        extra = room - total
        widths = list(nat)
        widths[0] += min(extra, 48.0)
        extra -= min(extra, 48.0)
        if n_cols > 1:
            add = min(extra / (n_cols - 1), 16.0)
            widths = [widths[0]] + [w + add for w in widths[1:]]
        return widths
    slack = [n - m for n, m in zip(nat, mn)]
    need = total - room
    if sum(slack) < need:
        return None
    return [n - need * s / sum(slack) for n, s in zip(nat, slack)]


def _table_geometry(img_t: dict, txt_t: dict, flow: TwinFlow, font: str, bold: str, size: float):
    """(grids, column x positions, widths, left, table width), or None if it cannot fit."""
    grids = _pad([_grid(img_t), _grid(txt_t)])
    if not grids[0] or not grids[0][0]:
        return grids, [], [], flow.x0, 0.0
    gap = size * 0.9
    widths = _col_widths(grids, font, bold, size, flow.avail_w, gap)
    if widths is None:
        return None
    table_w = sum(widths) + gap * (len(widths) - 1)
    left = flow.x0 + (flow.avail_w - table_w) / 2
    xs, x = [], left
    for w in widths:
        xs.append(x)
        x += w + gap
    return grids, xs, widths, left, table_w


def _place_table(flow: TwinFlow, geom, font: str, bold: str, size: float) -> None:
    grids, xs, widths, left, table_w = geom
    if not widths:
        return
    leading = size * 1.2
    rule_pad = size * 0.35

    flow.page.rules.append(Rule(left, flow.y, left + table_w, flow.y, width=0.9, gray=0.15))
    flow.gap(rule_pad)
    for i in range(len(grids[0])):
        f = _row_font(grids[0], i, font, bold)
        cells = [[wrap(g[i][j], f, size, widths[j]) for j in range(len(widths))] for g in grids]
        n = max(len(c) for version in cells for c in version)
        for v, out in enumerate((flow.page.image_items, flow.page.text_items)):
            for j, lines in enumerate(cells[v]):
                shift = n - len(lines) if i == 0 else 0          # header cells sit on the rule
                for k, line in enumerate(lines):
                    if not line:
                        continue
                    base = flow.y - size - (k + shift) * leading
                    lx = xs[j] if j == 0 else xs[j] + widths[j] - width(line, f, size)
                    out.append(TextItem(lx, base, f, size, line))
        flow.gap(n * leading + (rule_pad if i == 0 else size * 0.18))
        if i == 0:
            flow.page.rules.append(Rule(left, flow.y, left + table_w, flow.y, width=0.5, gray=0.35))
            flow.gap(rule_pad)
    flow.gap(rule_pad * 0.5)
    flow.page.rules.append(Rule(left, flow.y, left + table_w, flow.y, width=0.9, gray=0.15))


# ---------------------------------------------------------------------------
# Whole-page layout
# ---------------------------------------------------------------------------

def _layout(img_t, txt_t, img_pp, txt_pp, rc, size, max_pre=None, max_post=None) -> Optional[TwinFlow]:
    page_w, page_h = PAGE_SIZES[rc["page_size"].lower()]
    flow = TwinFlow(page_w, page_h, float(rc["margin_pt"]))
    font = rc["font"]
    bold, ital = BOLD.get(font, font), ITALIC.get(font, font)
    lead = size * 1.25
    pre_i, pre_t = detokenize(img_pp[0]), detokenize(txt_pp[0])
    post_i, post_t = detokenize(img_pp[1]), detokenize(txt_pp[1])
    if flow.paragraph(pre_i, pre_t, font, size, lead, max_lines=max_pre, name="pre_text"):
        flow.gap(size * 0.9)
    geom = _table_geometry(img_t, txt_t, flow, font, bold, size)
    if geom is None:
        return None
    # caption: a box over the table (at least ~60% of the text width), clamped to the margins
    _, _, _, left, table_w = geom
    cap_w = min(flow.avail_w, max(table_w, 0.62 * flow.avail_w))
    cap_x = min(max(left + table_w / 2 - cap_w / 2, flow.x0), flow.x1 - cap_w)
    flow.paragraph(table_caption(img_t), table_caption(txt_t), ital, size, lead, max_w=cap_w, x=cap_x)
    flow.gap(size * 0.5)
    _place_table(flow, geom, font, bold, size)
    if post_i or post_t:
        flow.gap(size * 1.1)
        flow.paragraph(post_i, post_t, font, size, lead, max_lines=max_post, name="post_text")
    return flow


def _sizes(hi: float, lo: float, step: float = 0.5) -> list[float]:
    out, s = [], hi
    while s >= lo - 1e-9:
        out.append(round(s, 2))
        s -= step
    return out


def plan_table_page(image_table, text_table, image_pre_post, text_pre_post,
                    cfg: Optional[dict] = None) -> tuple[TwinFlow, float]:
    """Find the largest font size at which both versions fit on one page."""
    rc = render_cfg(cfg)
    hi, lo = float(rc["font_size"]), float(rc["min_font_size"])
    args = (image_table, text_table, image_pre_post, text_pre_post, rc)
    for s in _sizes(hi, lo):
        flow = _layout(*args, s)
        if flow is not None and flow.overflow == 0:
            return flow, s
    # Prose does not fit even at min size (or the table is very wide): cut prose.
    for s in _sizes(lo, ABS_MIN_FONT):
        flow = _layout(*args, s)
        if flow is None:
            continue                                  # table too wide: go smaller
        lead = s * 1.25
        max_pre = max_post = None
        for _ in range(4):
            if flow.overflow == 0:
                return flow, s
            over = math.ceil(flow.overflow / lead) + 1
            n_post = _n_lines(image_pre_post[1], text_pre_post[1], rc, s, flow.avail_w)
            n_pre = _n_lines(image_pre_post[0], text_pre_post[0], rc, s, flow.avail_w)
            cur_post = n_post if max_post is None else max_post
            cur_pre = n_pre if max_pre is None else max_pre
            if cur_post > 0:
                max_post = max(0, cur_post - over)
            else:
                max_pre = max(0, cur_pre - over)
            flow = _layout(*args, s, max_pre=max_pre, max_post=max_post)
        if flow.overflow == 0:
            return flow, s
    # Give up gracefully: smallest size, prose removed; may still run off the page.
    flow = _layout(*args, ABS_MIN_FONT, max_pre=0, max_post=0) or _layout(*args, ABS_MIN_FONT)
    if flow is None:
        raise ValueError("table is too wide to render even at the smallest font size")
    flow.truncated.append("overflow" if flow.overflow else "")
    return flow, ABS_MIN_FONT


def _n_lines(img_text: str, txt_text: str, rc: dict, size: float, w: float) -> int:
    f = rc["font"]
    return max(len(wrap(detokenize(t), f, size, w)) if t else 0 for t in (img_text, txt_text))


def layout_page(doc: dict[str, Any], table: dict[str, Any], pre_post: Optional[tuple[str, str]] = None,
                cfg: Optional[dict] = None) -> list[TextItem]:
    """Title/caption, pre_text, table (fixed column x, right-aligned numbers, light
    rules), post_text for ONE version. Returns every text item with coordinates."""
    pp = tuple(pre_post) if pre_post is not None else (doc.get("pre_text", ""), doc.get("post_text", ""))
    flow, _ = plan_table_page(table, table, pp, pp, cfg)
    return flow.page.image_items


# ---------------------------------------------------------------------------
# A7 interface
# ---------------------------------------------------------------------------

_TABLE_KEYS = ("title", "unit_note", "header", "rows")


def _norm_table(t: dict[str, Any]) -> dict[str, Any]:
    return {"title": str(t.get("title") or ""), "unit_note": str(t.get("unit_note") or ""),
            "header": [str(c) for c in t.get("header") or []],
            "rows": [[str(c) for c in r] for r in t.get("rows") or []]}


def same_table(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return _norm_table(a) == _norm_table(b)


def _pp(doc: dict, pre_post) -> tuple[str, str]:
    if pre_post is None:
        return doc.get("pre_text", "") or "", doc.get("post_text", "") or ""
    pre, post = pre_post
    return pre or "", post or ""


def render_table_page(doc: dict, page_id: str, out_dir: str,
                      image_table: dict, text_table: dict,
                      image_pre_post=None, text_pre_post=None) -> dict:
    """A7 interface. Returns ONE pages.jsonl record (src/common/schemas.Page as dict).

    image_version / text_version in the record: "clean" if that table equals
    doc["table"] (and pre/post unchanged), else "poison". Paths are repo-relative.
    The caller appends the record to its own manifest
    (pages_clean.jsonl / pages_g1.jsonl / pages_g2*.jsonl).
    """
    rc = render_cfg()
    doc_pp = _pp(doc, None)
    img_pp, txt_pp = _pp(doc, image_pre_post), _pp(doc, text_pre_post)
    flow, size = plan_table_page(image_table, text_table, img_pp, txt_pp)
    img_v = "clean" if same_table(image_table, doc["table"]) and img_pp == doc_pp else "poison"
    txt_v = "clean" if same_table(text_table, doc["table"]) and txt_pp == doc_pp else "poison"
    img_cap, txt_cap = table_caption(image_table), table_caption(text_table)
    table_json = {
        "kind": "table",
        "image_table": _norm_table(image_table), "text_table": _norm_table(text_table),
        "image_caption": img_cap, "text_caption": txt_cap,
        "image_pre_post": list(img_pp) if img_pp != doc_pp else None,   # None = same as the doc
        "text_pre_post": list(txt_pp) if txt_pp != doc_pp else None,
    }
    extra = {"kind": "table", "font_size": size, "truncated": [t for t in flow.truncated if t]}
    if img_cap != txt_cap:
        extra["image_caption"] = img_cap
    return write_page(flow.page, page_id, doc["doc_id"], out_dir, img_v, txt_v, txt_cap,
                      table_json, int(rc["dpi"]), extra)
