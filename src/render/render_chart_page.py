"""Chart page renderer (ChartQA): re-render from the gold CSV, build the page.

OWNER: Person 4 (Aaron). Brief task 5.

Page = caption title ("Figure 1. <title>") + matplotlib chart (value labels on
the marks) + a "Source data: <label>: <value>; ..." note listing the values.
Same image + invisible-text construction as tables (``pdfpage.py``):
  IMAGE layer  = caption title + chart drawn from image_table + note from image_table
  TEXT layer   = caption title + note from text_table (invisible, render mode 3)
So in a text_only page the chart AND the visible note show the clean values,
while a parser (Docling / pdfplumber) reads the poisoned note.

The note format is what Person 5's checker parses: ``Source data: a: 1; b: 2``
(multi-series: ``a - Series: 1``). Commas, colons and semicolons inside labels
are replaced by spaces so the label/value pairs stay unambiguous.
"""

from __future__ import annotations

import re
import tempfile
import textwrap
from pathlib import Path
from typing import Any

from ..common.config import resolve
from .pdfpage import BOLD, PAGE_SIZES, Picture, TwinFlow, render_cfg, sanitize, write_page
from .render_table_page import _norm_table, _pp, same_table

# Categorical slots 1-3 of the reference palette (validated all-pairs for CVD).
SERIES_COLORS = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100")
INK, INK_2, GRID, AXIS = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"
CHART_W_IN, CHART_H_IN = 7.0, 4.0

_TIME = re.compile(r"^(?:(?:FY|Q[1-4])\s*)?'?\d{2,4}(?:[/-]\d{1,4})?(?:\s*Q[1-4])?\*{0,2}$|"
                   r"^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*'?\d{0,4}$", re.I)
_GENERIC = {"", "value", "values", "characteristic", "entity", "country", "category", "label"}


def _num(s: str) -> float:
    from ..attacks.representation.charts import parse_cell
    v = parse_cell(s)
    if v is None:
        raise ValueError(f"chart cell {s!r} is not a number")
    return v


def chart_kind(table: dict[str, Any]) -> str:
    """'line' for ONE series over time-like categories (>= 4 points); grouped
    'bar' if all bars fit side by side (<= 12 bars, short labels); else 'hbar'.
    Multi-series data never becomes a line chart: point labels would collide."""
    labels = [sanitize(r[0]) for r in table["rows"]]
    n_series = len(table["header"]) - 1
    if n_series == 1 and len(labels) >= 4 and all(_TIME.match(l) for l in labels):
        return "line"
    if max((len(l) for l in labels), default=0) > 14 or len(labels) * n_series > 12:
        return "hbar"
    return "bar"


def chart_size(table: dict[str, Any]) -> tuple[float, float]:
    """Figure size in inches; horizontal bar charts grow with the number of bars."""
    if chart_kind(table) != "hbar":
        return CHART_W_IN, CHART_H_IN
    bars = len(table["rows"]) * (len(table["header"]) - 1)
    return CHART_W_IN, min(7.0, max(CHART_H_IN, 0.9 + 0.2 * bars + 0.08 * len(table["rows"])))


def _chronological(labels: list[str]) -> bool:
    """True if year-like labels run newest-first (Statista CSVs often do)."""
    years = []
    for l in labels:
        m = re.search(r"(\d{4})", l)
        if not m:
            return False
        years.append(int(m.group(1)))
    return len(years) > 1 and years == sorted(years, reverse=True) and years[0] != years[-1]


def render_chart_png(table: dict[str, Any], out_png: str, title: str = "", dpi: int = 150) -> str:
    """matplotlib bar/line chart from the A6 table (header + rows from the CSV).

    The title is NOT drawn inside the chart (the page caption carries it)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    header = [sanitize(h) for h in table["header"]]
    rows = [[sanitize(c) for c in r] for r in table["rows"]]
    kind = chart_kind(table)
    if kind == "line" and _chronological([r[0] for r in rows]):
        rows = rows[::-1]
    labels = [r[0] for r in rows]
    series = header[1:]
    vals = [[_num(r[j + 1]) for r in rows] for j in range(len(series))]
    texts = [[r[j + 1] for r in rows] for j in range(len(series))]
    multi = len(series) > 1

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})
    fig, ax = plt.subplots(figsize=chart_size(table), dpi=dpi)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.tick_params(colors=INK_2, length=0)
    lo = min(min(v) for v in vals)
    hi = max(max(v) for v in vals)
    span = (hi - min(lo, 0)) or abs(hi) or 1.0
    n, k = len(labels), len(series)

    if kind == "line":
        xs = list(range(n))
        for j in range(k):
            ax.plot(xs, vals[j], color=SERIES_COLORS[j], linewidth=2, marker="o", markersize=5,
                    label=series[j], zorder=3)
            for x, v, t in zip(xs, vals[j], texts[j]):
                ax.annotate(t, (x, v), textcoords="offset points", xytext=(0, 7), ha="center",
                            fontsize=8, color=INK, zorder=4,
                            bbox={"boxstyle": "round,pad=0.12", "fc": "white", "ec": "none", "alpha": 0.9})
        ax.set_xticks(xs, labels)
        ax.yaxis.grid(True, color=GRID, linewidth=0.8)
        ax.set_ylim(min(lo, 0) - 0.05 * span, hi + 0.15 * span)
    else:
        horiz = kind == "hbar"
        width = 0.8 / k
        pos = list(range(n))
        for j in range(k):
            off = [p - 0.4 + width * (j + 0.5) for p in pos]
            bars = (ax.barh if horiz else ax.bar)(off, vals[j], width * 0.92, color=SERIES_COLORS[j],
                                                  label=series[j], zorder=3)
            for b, v, t in zip(bars, vals[j], texts[j]):
                if horiz:
                    x = b.get_width()
                    ax.annotate(t, (x, b.get_y() + b.get_height() / 2), textcoords="offset points",
                                xytext=(4 if v >= 0 else -4, 0), ha="left" if v >= 0 else "right",
                                va="center", fontsize=8, color=INK)
                else:
                    y = b.get_height()
                    ax.annotate(t, (b.get_x() + b.get_width() / 2, y), textcoords="offset points",
                                xytext=(0, 3 if v >= 0 else -3), ha="center",
                                va="bottom" if v >= 0 else "top", fontsize=8, color=INK)
        wrapped = [textwrap.fill(l, 28 if horiz else 14) for l in labels]
        if horiz:
            ax.set_yticks(pos, wrapped)
            ax.invert_yaxis()
            ax.xaxis.grid(True, color=GRID, linewidth=0.8)
            ax.set_xlim(min(lo, 0) - (0.12 * span if lo < 0 else 0), hi + 0.15 * span)
        else:
            ax.set_xticks(pos, wrapped)
            ax.yaxis.grid(True, color=GRID, linewidth=0.8)
            ax.set_ylim(min(lo, 0) - (0.1 * span if lo < 0 else 0), hi + 0.12 * span)
        if horiz:
            ax.axvline(0, color=AXIS, linewidth=0.8)
        else:
            ax.axhline(0, color=AXIS, linewidth=0.8)
    ax.set_axisbelow(True)
    value_axis = series[0] if not multi and series[0].lower() not in _GENERIC else ""
    cat_axis = header[0] if header and header[0].lower() not in _GENERIC else ""
    if kind == "hbar":
        ax.set_xlabel(value_axis, color=INK_2)
        ax.set_ylabel(cat_axis, color=INK_2)
    else:
        ax.set_ylabel(textwrap.fill(value_axis, 40), color=INK_2)
        ax.set_xlabel(cat_axis, color=INK_2)
    if multi:
        ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=k, frameon=False, fontsize=8.5,
                  labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out_png, dpi=dpi, facecolor="white")
    plt.close(fig)
    return out_png


# ---------------------------------------------------------------------------
# Caption title + source-data note (both re-rendered from each version's table)
# ---------------------------------------------------------------------------

def _note_label(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[,;:=]", " ", sanitize(s))).strip()


def chart_caption(table: dict[str, Any]) -> str:
    title = sanitize(table.get("title", ""))
    unit = sanitize(table.get("unit_note", ""))
    cap = "Figure 1." + (f" {title}" if title else "") + (f" ({unit})" if unit else "")
    return cap if cap.endswith(".") else cap + "."


def source_note(table: dict[str, Any]) -> str:
    header = table["header"]
    multi = len(header) > 2
    parts = []
    for r in table["rows"]:
        for j in range(1, len(header)):
            lab = _note_label(r[0]) + (f" - {_note_label(header[j])}" if multi else "")
            parts.append(f"{lab}: {sanitize(r[j])}")
    return "Source data: " + "; ".join(parts) + "."


# ---------------------------------------------------------------------------
# A7-style interface
# ---------------------------------------------------------------------------

def render_chart_page(doc: dict, page_id: str, out_dir: str,
                      image_table: dict, text_table: dict,
                      image_pre_post=None, text_pre_post=None) -> dict:
    """Like render_table_page: returns one pages.jsonl record."""
    rc = render_cfg()
    dpi = int(rc["dpi"])
    page_w, page_h = PAGE_SIZES[rc["page_size"].lower()]
    font = rc["font"]
    bold = BOLD.get(font, font)
    size = float(rc["font_size"])
    lead = size * 1.25
    doc_pp = _pp(doc, None)
    img_pp, txt_pp = _pp(doc, image_pre_post), _pp(doc, text_pre_post)

    out = resolve(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out, prefix=".chart_") as tmp:
        chart_png = str(Path(tmp) / "chart.png")
        render_chart_png(image_table, chart_png, dpi=dpi)
        fig_w, fig_h = chart_size(image_table)

        def lay(scale: float) -> TwinFlow:
            flow = TwinFlow(page_w, page_h, float(rc["margin_pt"]))
            if flow.paragraph(sanitize(img_pp[0]), sanitize(txt_pp[0]), font, size, lead, name="pre_text"):
                flow.gap(size)
            flow.paragraph(chart_caption(image_table), chart_caption(text_table), bold, size + 1, lead + 1)
            flow.gap(size * 0.6)
            w = min(flow.avail_w, fig_w * 72) * scale
            h = w * fig_h / fig_w
            flow.page.pictures.append(Picture(chart_png, flow.x0 + (flow.avail_w - w) / 2, flow.y - h, w, h))
            flow.gap(h + size * 0.6)
            note_size = size - 1
            flow.paragraph(source_note(image_table), source_note(text_table), font, note_size,
                           note_size * 1.25)
            if img_pp[1] or txt_pp[1]:
                flow.gap(size)
                flow.paragraph(sanitize(img_pp[1]), sanitize(txt_pp[1]), font, size, lead, name="post_text")
            return flow

        flow = lay(1.0)
        if flow.overflow:                      # shrink the chart (not the text) until the page fits
            pic_h = flow.page.pictures[0].h
            flow = lay(max(0.5, (pic_h - flow.overflow) / pic_h))
        img_v = "clean" if same_table(image_table, doc["table"]) and img_pp == doc_pp else "poison"
        txt_v = "clean" if same_table(text_table, doc["table"]) and txt_pp == doc_pp else "poison"
        img_cap = f"{chart_caption(image_table)} {source_note(image_table)}"
        txt_cap = f"{chart_caption(text_table)} {source_note(text_table)}"
        table_json = {"kind": "chart", "chart_type": chart_kind(image_table),
                      "image_table": _norm_table(image_table), "text_table": _norm_table(text_table),
                      "image_caption": img_cap, "text_caption": txt_cap}
        extra = {"kind": "chart", "font_size": size, "truncated": [t for t in flow.truncated if t]}
        if flow.overflow:
            extra["truncated"].append("overflow")
        if img_cap != txt_cap:
            extra["image_caption"] = img_cap
        return write_page(flow.page, page_id, doc["doc_id"], out_dir, img_v, txt_v, txt_cap,
                          table_json, dpi, extra)
