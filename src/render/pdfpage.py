"""Shared page machinery for the table and chart renderers. OWNER: Person 4 (Aaron).

A rendered page is built in three steps (A4), identical for clean and poisoned pages:

  (a) draw the IMAGE version (visible text, table rules, chart picture) with reportlab
  (b) rasterize that PDF to PNG with pdftoppm (cfg render.dpi, default 150)
  (c) final PDF = the PNG as a full-page background + the TEXT version's strings
      drawn at the same coordinates with text render mode 3 (invisible)

Steps (a) and (c) take lists of :class:`TextItem` produced by ONE layout pass
that sees both versions (``TwinFlow``), so every block sits at the same place
in both layers even when the two versions have different strings.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from reportlab.lib.pagesizes import A4, letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from ..common.config import get_config, rel, resolve
from ..common.schemas import Page

RENDERER_VERSION = "p4-v1"

PAGE_SIZES = {"letter": letter, "a4": A4}

# reportlab's built-in fonts (no embedding, reliable text extraction).
BOLD = {"Times-Roman": "Times-Bold", "Helvetica": "Helvetica-Bold", "Courier": "Courier-Bold"}
ITALIC = {"Times-Roman": "Times-Italic", "Helvetica": "Helvetica-Oblique", "Courier": "Courier-Oblique"}

RENDER_DEFAULTS = {"dpi": 150, "page_size": "letter", "font": "Times-Roman", "font_size": 10.5,
                   "margin_pt": 54, "min_font_size": 7.0}


def render_cfg(cfg: Optional[dict] = None) -> dict[str, Any]:
    return {**RENDER_DEFAULTS, **((cfg or get_config()).get("render") or {})}


# ---------------------------------------------------------------------------
# Text clean-up (applied identically to both versions)
# ---------------------------------------------------------------------------

_FALLBACK = {"−": "-", "‐": "-", "‑": "-", " ": " ", " ": " ", " ": " "}
_TAG = re.compile(r"<[^>]+>")


def sanitize(s: Any) -> str:
    """Strip HTML tags, unescape entities, and map characters the built-in fonts
    (cp1252) cannot draw. Keeps the string otherwise unchanged."""
    s = html.unescape(_TAG.sub(" ", str(s if s is not None else "")))
    s = "".join(_FALLBACK.get(ch, ch) for ch in s)
    s = s.encode("cp1252", errors="replace").decode("cp1252")
    return re.sub(r"[ \t\r\n]+", " ", s).strip()


_DETOK = [
    (re.compile(r"\s+([.,;:!?%)\]])"), r"\1"),     # "word ." -> "word."
    (re.compile(r"([(\[$])\s+"), r"\1"),           # "( 1" -> "(1", "$ 683" -> "$683"
    (re.compile(r"\s+'s\b"), "'s"),
    (re.compile(r"\s+n't\b"), "n't"),
]


def detokenize(s: str) -> str:
    """FinQA prose is tokenized ("$ 683 million , net ."); undo the spacing so the
    page reads like a filing. Words and numbers are not changed."""
    s = sanitize(s)
    for pat, rep in _DETOK:
        s = pat.sub(rep, s)
    return s


# ---------------------------------------------------------------------------
# Measuring and wrapping
# ---------------------------------------------------------------------------

def width(text: str, font: str, size: float) -> float:
    return stringWidth(text, font, size)


def wrap(text: str, font: str, size: float, max_w: float) -> list[str]:
    """Greedy word wrap; words wider than the column are split by characters."""
    text = text.strip()
    if not text:
        return [""]
    lines: list[str] = []
    cur = ""
    for word in text.split(" "):
        cand = f"{cur} {word}" if cur else word
        if width(cand, font, size) <= max_w:
            cur = cand
            continue
        if cur:
            lines.append(cur)
        while width(word, font, size) > max_w and len(word) > 1:
            k = len(word)
            while k > 1 and width(word[:k], font, size) > max_w:
                k -= 1
            lines.append(word[:k])
            word = word[k:]
        cur = word
    lines.append(cur)
    return lines


def max_word_width(text: str, font: str, size: float) -> float:
    return max((width(w, font, size) for w in text.split()), default=0.0)


# ---------------------------------------------------------------------------
# Layout primitives
# ---------------------------------------------------------------------------

@dataclass
class TextItem:
    x: float
    y: float          # baseline, PDF points from the bottom
    font: str
    size: float
    text: str


@dataclass
class Rule:
    x0: float
    y0: float
    x1: float
    y1: float
    width: float = 0.6
    gray: float = 0.35


@dataclass
class Picture:
    path: str
    x: float
    y: float
    w: float
    h: float


@dataclass
class TwinPage:
    """Everything needed to draw one page in both versions."""
    page_w: float
    page_h: float
    image_items: list[TextItem] = field(default_factory=list)
    text_items: list[TextItem] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    pictures: list[Picture] = field(default_factory=list)


class TwinFlow:
    """Top-to-bottom flow that places the IMAGE and TEXT version of each block
    at the same position. A block takes the height of the taller version."""

    def __init__(self, page_w: float, page_h: float, margin: float):
        self.page = TwinPage(page_w, page_h)
        self.margin = margin
        self.x0, self.x1 = margin, page_w - margin
        self.y = page_h - margin          # top of the next block
        self.truncated: list[str] = []

    @property
    def avail_w(self) -> float:
        return self.x1 - self.x0

    @property
    def overflow(self) -> float:
        """Points by which the content runs past the bottom margin (0 if it fits)."""
        return max(0.0, self.margin - self.y)

    def gap(self, h: float) -> None:
        self.y -= h

    def lines_block(self, img_lines: list[str], txt_lines: list[str], font: str, size: float,
                    leading: float, x: Optional[float] = None, align: str = "left",
                    right: Optional[float] = None) -> None:
        x = self.x0 if x is None else x
        right = self.x1 if right is None else right
        n = max(len(img_lines), len(txt_lines))
        for k in range(n):
            base = self.y - size - k * leading
            for lines, out in ((img_lines, self.page.image_items), (txt_lines, self.page.text_items)):
                if k < len(lines) and lines[k]:
                    lx = right - width(lines[k], font, size) if align == "right" else x
                    out.append(TextItem(lx, base, font, size, lines[k]))
        self.y -= n * leading

    def paragraph(self, img_text: str, txt_text: str, font: str, size: float, leading: float,
                  max_lines: Optional[int] = None, name: str = "", max_w: Optional[float] = None,
                  x: Optional[float] = None) -> int:
        """Wrap both versions to the same width; returns the block's line count."""
        if not img_text and not txt_text:
            return 0
        w = self.avail_w if max_w is None else max_w
        img_lines = wrap(img_text, font, size, w) if img_text else []
        txt_lines = wrap(txt_text, font, size, w) if txt_text else []
        if max_lines is not None and max(len(img_lines), len(txt_lines)) > max_lines:
            img_lines, txt_lines = _cut(img_lines, max_lines), _cut(txt_lines, max_lines)
            self.truncated.append(name)
        self.lines_block(img_lines, txt_lines, font, size, leading, x=x)
        return max(len(img_lines), len(txt_lines))


def _cut(lines: list[str], n: int) -> list[str]:
    if len(lines) <= n:
        return lines
    out = lines[:n]
    if out:
        out[-1] = out[-1].rstrip() + " ..."
    return out


def paragraph_lines(text: str, font: str, size: float, max_w: float) -> int:
    return len(wrap(text, font, size, max_w)) if text else 0


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def draw_image_pdf(page: TwinPage, path: Path) -> None:
    """Step (a): the IMAGE version as a normal (visible) PDF."""
    c = canvas.Canvas(str(path), pagesize=(page.page_w, page.page_h), pageCompression=1)
    c.setFillGray(1)
    c.rect(0, 0, page.page_w, page.page_h, stroke=0, fill=1)
    for p in page.pictures:
        c.drawImage(p.path, p.x, p.y, width=p.w, height=p.h)
    for r in page.rules:
        c.setStrokeGray(r.gray)
        c.setLineWidth(r.width)
        c.line(r.x0, r.y0, r.x1, r.y1)
    c.setFillGray(0)
    for it in page.image_items:
        c.setFont(it.font, it.size)
        c.drawString(it.x, it.y, it.text)
    c.showPage()
    c.save()


def rasterize(pdf_path: Path, png_path: Path, dpi: int) -> None:
    """Step (b): pdftoppm -> PNG (single page)."""
    exe = shutil.which("pdftoppm")
    if exe is None:
        raise RuntimeError("pdftoppm not found: install poppler-utils (apt) / poppler (conda, brew)")
    prefix = str(png_path)[: -len(".png")]
    subprocess.run([exe, "-r", str(dpi), "-png", "-singlefile", str(pdf_path), prefix],
                   check=True, capture_output=True)


def draw_final_pdf(page: TwinPage, png_path: Path, path: Path) -> None:
    """Step (c): PNG background + TEXT version as invisible text (render mode 3)."""
    c = canvas.Canvas(str(path), pagesize=(page.page_w, page.page_h), pageCompression=1)
    c.drawImage(str(png_path), 0, 0, width=page.page_w, height=page.page_h)
    for it in page.text_items:
        t = c.beginText()
        t.setTextRenderMode(3)
        t.setFont(it.font, it.size)
        t.setTextOrigin(it.x, it.y)
        t.textOut(it.text)
        c.drawText(t)
    c.showPage()
    c.save()


def reading_order_text(items: list[TextItem], sep: str = " | ") -> str:
    """Debug dump of a layer: items grouped into visual lines, top to bottom."""
    lines: list[tuple[float, list[TextItem]]] = []
    for it in items:
        for y, group in lines:
            if abs(y - it.y) < 0.5:
                group.append(it)
                break
        else:
            lines.append((it.y, [it]))
    lines.sort(key=lambda t: -t[0])
    return "\n".join(sep.join(i.text for i in sorted(g, key=lambda i: i.x)) for _, g in lines) + "\n"


# ---------------------------------------------------------------------------
# Writing one page + its manifest record
# ---------------------------------------------------------------------------

def variant_of(page_id: str) -> str:
    """'clean' for <doc>__clean, else the attack id after the first '__'."""
    tail = page_id.split("__", 1)[1] if "__" in page_id else "clean"
    return "clean" if tail == "clean" else tail


def write_page(page: TwinPage, page_id: str, doc_id: str, out_dir: str, image_version: str,
               text_version: str, caption: str, table_json: dict[str, Any], dpi: int,
               extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Draw, rasterize and save <page_id>.pdf/.png/.txt/.table.json; return the Page record."""
    out = resolve(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pdf, png = out / f"{page_id}.pdf", out / f"{page_id}.png"
    txt, tj = out / f"{page_id}.txt", out / f"{page_id}.table.json"
    with tempfile.TemporaryDirectory(dir=out, prefix=".render_") as tmp:
        image_pdf = Path(tmp) / "image.pdf"
        tmp_png = Path(tmp) / "page.png"
        draw_image_pdf(page, image_pdf)
        rasterize(image_pdf, tmp_png, dpi)
        draw_final_pdf(page, tmp_png, Path(tmp) / "final.pdf")
        os.replace(tmp_png, png)
        os.replace(Path(tmp) / "final.pdf", pdf)
    txt.write_text(reading_order_text(page.text_items), encoding="utf-8")
    tj.write_text(json.dumps(table_json, ensure_ascii=False, indent=1), encoding="utf-8")
    rec = Page(page_id=page_id, doc_id=doc_id, variant=variant_of(page_id),
               image_version=image_version, text_version=text_version,
               pdf_path=rel(pdf), image_path=rel(png), text_path=rel(txt),
               caption=caption, table_json_path=rel(tj),
               extra={"renderer": RENDERER_VERSION, **(extra or {})})
    rec.validate()
    return rec.to_dict()


def layout_dump(page: TwinPage) -> dict[str, Any]:
    """JSON-able copy of a layout (for debugging alignment)."""
    return {"image_items": [asdict(i) for i in page.image_items],
            "text_items": [asdict(i) for i in page.text_items]}
