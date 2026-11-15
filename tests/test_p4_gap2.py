"""Person 4 (Aaron): chart renderer, chart edits, propagation rows, layer alignment.

Needs reportlab + pdftoppm (poppler) + pdfplumber + matplotlib.
"""
import json

import pytest

from src.attacks.representation.charts import (chart_edit, format_like, make_chart_conditions, question_kind,
                                               question_ok, read_chart_csv, tidy_cell)
from src.attacks.representation.propagate import make_table_propagation
from src.common import io
from src.common.config import resolve
from src.common.edits import apply_edit
from src.common.schemas import ATTACK_LAYERS, Example, Page
from src.render.pdfpage import width
from src.render.render_table_page import plan_table_page


def _pdf_text(rec):
    pdfplumber = pytest.importorskip("pdfplumber")
    with pdfplumber.open(resolve(rec["pdf_path"])) as pdf:
        return pdf.pages[0].extract_text()


# ---------------------------------------------------------------- number formats

def test_number_formats():
    assert tidy_cell("62.0") == "62" and tidy_cell("0.96") == "0.96" and tidy_cell("77%") == "77%"
    assert format_like(1312.4, "1,204.5") == "1,312.4"
    assert format_like(33.1, "27.5%") == "33.1%"
    assert format_like(-7.0, "$12") == "$-7"


def test_question_filters():
    assert not question_ok("What is the value of the blue bar?")
    assert not question_ok("What is the difference between Asians and Whites?")
    assert not question_ok("How many bars are there?")
    assert question_ok("What was the risk index score in 2017?")
    assert question_kind("Which year had the highest sales?") == "max"
    assert question_kind("What is the smallest value?") == "min"


def test_read_chart_csv(tmp_path):
    p = tmp_path / "two_col_1.csv"
    p.write_text('Characteristic,Number of stores\n2019,47.0\n2020,"1,204"\n', encoding="utf-8")
    t = read_chart_csv(p)
    assert t["header"] == ["Characteristic", "Number of stores"]
    assert t["rows"] == [["2019", "47"], ["2020", "1,204"]]
    assert t["title"] == "Number of stores"


# ---------------------------------------------------------------- chart edits

def test_chart_edit_plausible_and_deterministic(cfg):
    doc = io.load_docs(cfg)["chartqa_00001"]
    ex = io.load_examples(cfg)["c0001"]                  # 2019 -> 240
    edit, target = chart_edit(ex, doc)
    assert (edit["row"], edit["col"], edit["old"]) == (4, 1, "240")
    rel = abs(float(edit["new"]) / 240 - 1)
    assert 0.14 <= rel <= 0.31 and edit["also_changed"] == []
    assert target == edit["new"]
    assert chart_edit(ex, doc) == (edit, target)            # same seed -> same edit
    others = {r[1] for r in doc.table["rows"]} - {"240"}
    assert edit["new"] not in others


def test_max_question_stays_max(cfg):
    doc = io.load_docs(cfg)["chartqa_00001"]
    ex = Example(qid="cmax", source="chartqa", question="In which year were sales the highest?",
                 gold_answer="310", doc_id=doc.doc_id)
    edit, _ = chart_edit(ex, doc)
    assert float(edit["new"]) > 310


# ---------------------------------------------------------------- chart pages

def test_chart_conditions_layers(cfg, tmp_path):
    doc = io.load_docs(cfg)["chartqa_00001"]
    ex = io.load_examples(cfg)["c0001"]
    pages = []
    rows = make_chart_conditions(ex, doc, str(tmp_path), page_sink=pages)
    assert [r.attack_type for r in rows] == ["propagate_chart", "text_only_chart", "image_only_chart"]
    new = rows[0].edit["new"]
    for atk, rec in zip(rows, pages):
        page = Page.from_dict(rec)
        assert (page.image_version, page.text_version) == ATTACK_LAYERS[atk.attack_type]
        assert atk.poison_page_id == page.page_id and resolve(page.image_path).exists()
        text = _pdf_text(rec)
        text_value = new if page.text_version == "poison" else "240"
        other = "240" if text_value == new else new
        assert f"2019: {text_value}" in text and f"2019: {other}" not in text
        tj = json.loads(resolve(page.table_json_path).read_text())
        img_value = tj["image_table"]["rows"][3][1]
        assert img_value == (new if page.image_version == "poison" else "240")
        assert atk.image_answer == (atk.target_answer if page.image_version == "poison" else ex.gold_answer)


def test_clean_chart_page(cfg, tmp_path):
    from src.render.render_chart_page import render_chart_page

    doc = io.load_docs(cfg)["chartqa_00001"].to_dict()
    rec = render_chart_page(doc, "chartqa_00001__clean", str(tmp_path), doc["table"], doc["table"])
    assert rec["variant"] == "clean" and rec["image_version"] == rec["text_version"] == "clean"
    assert rec["caption"].startswith("Figure 1. E-bike sales") and "Source data: 2016: 120;" in rec["caption"]


# ---------------------------------------------------------------- table propagation

def test_table_propagation(cfg, tmp_path):
    doc = io.load_docs(cfg)["finqa_ACME_2019_p12"]
    g1 = io.load_attacks(cfg)["G1_consistent_cell_q0001"]
    pages = []
    atk = make_table_propagation(g1, doc, "10.5", str(tmp_path), page_sink=pages)
    assert atk.attack_id == "G2_propagate_table_q0001"
    assert atk.poison_page_id == "finqa_ACME_2019_p12__G2_propagate_table_q0001"
    assert (atk.image_answer, atk.text_answer, atk.gold_answer) == ("20.4", "20.4", "10.5")
    assert atk.extra["caption_shows_edit"] is True
    rec = pages[0]
    assert (rec["image_version"], rec["text_version"]) == ("poison", "poison")
    text = _pdf_text(rec)
    assert "1,312" in text and "1,824" in text and "1,204" not in text and "1,716" not in text
    assert "Total revenue: 1,824 (2019)" in rec["caption"]


# ---------------------------------------------------------------- the two layers line up

def test_layers_share_geometry(cfg):
    """Strings of different widths (980 vs 1,050) still sit in the same cell:
    same baseline, same right edge for right-aligned numbers."""
    doc = io.load_docs(cfg)["finqa_ACME_2019_p12"].to_dict()
    edit = {"row": 2, "col": 1, "old": "512", "new": "10,512", "also_changed": [[3, 1, "1,716", "11,716"]]}
    pois = apply_edit(doc, edit)["table"]
    pp = (doc["pre_text"], doc["post_text"])
    flow, _ = plan_table_page(doc["table"], pois, pp, pp)
    img, txt = flow.page.image_items, flow.page.text_items
    for old, new in (("512", "10,512"), ("1,716", "11,716")):
        a = next(i for i in img if i.text == old)
        b = next(i for i in txt if i.text == new)
        assert abs(a.y - b.y) < 1e-6
        assert abs((a.x + width(a.text, a.font, a.size)) - (b.x + width(b.text, b.font, b.size))) < 1e-6
    # everything else (prose, header, other cells) is identical; the caption (italic)
    # is re-rendered from each version's table, so it may differ but sits on the same lines
    rest_img = sorted((i.x, i.y, i.text) for i in img if i.text not in ("512", "1,716") and "Italic" not in i.font)
    rest_txt = sorted((i.x, i.y, i.text) for i in txt if i.text not in ("10,512", "11,716") and "Italic" not in i.font)
    assert rest_img == rest_txt
    assert sorted({i.y for i in img if "Italic" in i.font}) == sorted({i.y for i in txt if "Italic" in i.font})
