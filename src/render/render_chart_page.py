"""Chart page renderer (ChartQA): re-render from the gold CSV, build the page.

OWNER: Person 4 (Aaron). Brief task 5.

Page = caption title + matplotlib chart (value labels on bars) + a one-line
"Source data: ..." note listing the values. Same image + invisible-text
construction as tables, so the image and the text layer can disagree.
"""

from __future__ import annotations

from typing import Any


def render_chart_png(table: dict[str, Any], out_png: str, title: str = "") -> str:
    """matplotlib bar/line chart from the A6 table (header + rows from the CSV)."""
    raise NotImplementedError("Person 4: render_chart_png")


def render_chart_page(doc: dict, page_id: str, out_dir: str,
                      image_table: dict, text_table: dict) -> dict:
    """Like render_table_page: returns one pages.jsonl record."""
    raise NotImplementedError("Person 4: render_chart_page")
