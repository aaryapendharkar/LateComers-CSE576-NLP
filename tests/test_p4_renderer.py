"""Person 4 (Aaron) acceptance tests. Skipped until the renderer is implemented.

Needs reportlab + pdftoppm (poppler) + pdfplumber installed.
"""
from pathlib import Path

import pytest

from src.common import io
from src.common.config import resolve
from src.common.edits import apply_edit
from src.common.schemas import Page
from src.render.render_table_page import render_table_page


def test_conflict_page_layers_differ(cfg, tmp_path):
    pdfplumber = pytest.importorskip("pdfplumber")
    doc = io.load_docs(cfg)["finqa_ACME_2019_p12"].to_dict()
    atk = io.load_attacks(cfg)["G2_text_only_table_q0001"]
    poisoned = apply_edit(doc, atk.edit)["table"]
    rec = render_table_page(doc, atk.poison_page_id, str(tmp_path), image_table=doc["table"], text_table=poisoned)
    page = Page.from_dict(rec)
    assert (page.image_version, page.text_version) == ("clean", "poison")
    for p in (page.pdf_path, page.image_path, page.text_path):
        assert resolve(p).exists()
    with pdfplumber.open(resolve(page.pdf_path)) as pdf:
        text = pdf.pages[0].extract_text()
    assert "1,312" in text and "1,204" not in text      # text layer = TEXT version


def test_clean_page_record(cfg, tmp_path):
    doc = io.load_docs(cfg)["finqa_BETA_2017_p45"].to_dict()
    rec = render_table_page(doc, "finqa_BETA_2017_p45__clean", str(tmp_path), doc["table"], doc["table"])
    assert rec["variant"] == "clean" and rec["image_version"] == rec["text_version"] == "clean"
