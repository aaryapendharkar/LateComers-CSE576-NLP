"""Person 5 (Disha): image/text readers and the page-level checker, without a GPU.

A fake "VLM" (a plain function) stands in for the model, so these run anywhere.
"""
import json

from src.common import io
from src.common.edits import apply_edit
from src.common.schemas import Page
from src.common.tables import doc_to_text
from src.defenses.img_text_check import (check_page, extract_table_from_image, parse_table_reply,
                                         parse_text_layer)


def test_parse_reply_json_with_noise():
    raw = ('<think>let me read</think>Here you go:\n```json\n{"title": "T", "unit_note": "in millions", '
           '"header": ["", "2019", "2018"], "rows": [["Products", "1,204", "1,090"], ["Total", 1716]]}\n```')
    t = parse_table_reply(raw)
    assert t["header"] == ["", "2019", "2018"]
    assert t["rows"][1] == ["Total", "1716", ""]          # numbers -> strings, row padded


def test_parse_reply_markdown_fallback():
    t = parse_table_reply("| | 2019 |\n|---|---|\n| Products | 1,204 |")
    assert t["rows"] == [["Products", "1,204"]]


def test_text_layer_docling_markdown(cfg):
    doc = io.load_docs(cfg)["finqa_ACME_2019_p12"].to_dict()
    t = parse_text_layer(doc_to_text(doc))
    assert t["header"] == doc["table"]["header"] and t["rows"] == doc["table"]["rows"]


def test_text_layer_plain_text_and_chart_note():
    plain = "Revenue by segment\n(in millions)\n2019 2018\nProducts 1,204 1,090\nServices 512 488\nTotal revenue 1,716 1,578"
    t = parse_text_layer(plain)
    assert t["header"][1:] == ["2019", "2018"] and t["rows"][2] == ["Total revenue", "1,716", "1,578"]
    assert t["unit_note"] == "in millions"
    chart = "E-bike sales\nSource data: 2016: 120, 2017: 145, 2018: 190"
    assert parse_text_layer(chart)["rows"] == [["2016", "120"], ["2017", "145"], ["2018", "190"]]


def test_extract_with_fake_vlm(cfg, tmp_path):
    table = io.load_docs(cfg)["finqa_ACME_2019_p12"].to_dict()["table"]
    fake_vlm = lambda image_path, prompt: json.dumps(table)   # noqa: E731
    assert extract_table_from_image("unused.png", fake_vlm)["rows"] == table["rows"]


def test_check_page_end_to_end(cfg, tmp_path):
    """Clean page -> no flag; text_only page (text layer poisoned) -> flag on cell + total."""
    doc = io.load_docs(cfg)["finqa_ACME_2019_p12"].to_dict()
    atk = io.load_attacks(cfg)["G2_text_only_table_q0001"]
    poisoned_doc = apply_edit(doc, atk.edit)
    clean_id, poison_id = atk.clean_page_id, atk.poison_page_id

    parsed = tmp_path / "parsed" / "docling"
    parsed.mkdir(parents=True)
    (parsed / f"{clean_id}.txt").write_text(doc_to_text(doc))
    (parsed / f"{poison_id}.txt").write_text(doc_to_text(poisoned_doc))   # text layer = poisoned
    pages = {pid: Page.from_dict({"page_id": pid, "doc_id": doc["doc_id"], "variant": v,
                                  "image_version": "clean", "text_version": tv,
                                  "pdf_path": "x.pdf", "image_path": f"{pid}.png", "text_path": "x.txt"})
             for pid, v, tv in [(clean_id, "clean", "clean"), (poison_id, atk.attack_id, "poison")]}
    run_cfg = {**cfg, "paths": {**cfg["paths"], "parsed_dir": str(tmp_path / "parsed")},
               "img_text_check": {"cache_dir": str(tmp_path / "cache"), "text_source": "docling"}}
    fake_vlm = lambda image_path, prompt: json.dumps(doc["table"])        # image shows clean values # noqa: E731

    assert check_page(clean_id, cfg=run_cfg, generator=fake_vlm, pages=pages)["flag"] is False
    r = check_page(poison_id, cfg=run_cfg, generator=fake_vlm, pages=pages)
    assert r["flag"] is True and len(r["mismatches"]) == 2
    assert (tmp_path / "cache" / f"{poison_id}.json").exists()           # image read is cached
