import json

from src.common import io
from src.common.edits import apply_edit
from src.common.schemas import Page
from src.common.tables import doc_to_text
from src.defenses.img_text_check import (check_page, compare_with_text, extract_table_from_image,
                                         parse_source_note, parse_table_reply)


def test_parse_reply_json_with_noise():
    raw = ('<think>let me read</think>Here you go:\n```json\n{"title": "T", "unit_note": "in millions", '
           '"header": ["", "2019", "2018"], "rows": [["Products", "1,204", "1,090"], ["Total", 1716]]}\n```')
    t = parse_table_reply(raw)
    assert t["header"] == ["", "2019", "2018"]
    assert t["rows"][1] == ["Total", "1716", ""]


def test_parse_reply_markdown_fallback():
    t = parse_table_reply("| | 2019 |\n|---|---|\n| Products | 1,204 |")
    assert t["rows"] == [["Products", "1,204"]]


def test_markdown_text_layer(cfg):
    doc = io.load_docs(cfg)["finqa_ACME_2019_p12"].to_dict()
    assert compare_with_text(doc["table"], doc_to_text(doc))["flag"] is False
    poisoned = apply_edit(doc, io.load_attacks(cfg)["G2_text_only_table_q0001"].edit)
    assert len(compare_with_text(doc["table"], doc_to_text(poisoned))["mismatches"]) == 2


def test_source_note():
    chart = "Figure 1. E-bike sales.\nSource data: 2016: 1,120; 2017: 145; 2018: 19.5."
    assert parse_source_note(chart)["rows"] == [["2016", "1,120"], ["2017", "145"], ["2018", "19.5"]]
    multi = ("Figure 1. A vs B.\nSource data: 65+ - Health: 49; 65+ - Money: 32; Ages 18-29 -\n"
             "Health: 26; Ages 18-29 - Money: 40.")
    t = parse_source_note(multi)
    assert t["header"] == ["", "Health", "Money"]
    assert t["rows"] == [["65+", "49", "32"], ["Ages 18-29", "26", "40"]]


def test_compare_with_plain_text_layer():
    img = {"title": "", "unit_note": "in billions", "header": ["December 31, (in billions)", "2010", "2009"],
           "rows": [["Securities", "$112.1", "$155.3"], ["Loans", "214.8", "285.5"], ["Total", "$450.1", "$525.4"]]}
    text = ("Table 1. December 31. Key figures: Securities: $112.1 (2010), $155.3\n(2009); Total: $450.1 (2010).\n"
            "December 31, (in billions) 2010 2009\nSecurities $112.1 $155.3\nLoans 250.4 285.5\n"
            "Total $485.7 $525.4\nprose about total assets pledged in 2010 was 3.")
    r = compare_with_text(img, text)
    assert r["mismatches"] == [["Loans", "2010", "214.8", "250.4"], ["Total", "2010", "$450.1", "$485.7"]]
    clean = text.replace("250.4", "214.8").replace("$485.7", "$450.1")
    assert compare_with_text(img, clean)["flag"] is False


def test_extract_with_fake_vlm(cfg, tmp_path):
    table = io.load_docs(cfg)["finqa_ACME_2019_p12"].to_dict()["table"]
    def fake_vlm(image_path, prompt):
        return json.dumps(table)
    assert extract_table_from_image("unused.png", fake_vlm)["rows"] == table["rows"]


def test_check_page_end_to_end(cfg, tmp_path):
    doc = io.load_docs(cfg)["finqa_ACME_2019_p12"].to_dict()
    atk = io.load_attacks(cfg)["G2_text_only_table_q0001"]
    poisoned_doc = apply_edit(doc, atk.edit)
    clean_id, poison_id = atk.clean_page_id, atk.poison_page_id

    parsed = tmp_path / "parsed" / "docling"
    parsed.mkdir(parents=True)
    (parsed / f"{clean_id}.txt").write_text(doc_to_text(doc))
    (parsed / f"{poison_id}.txt").write_text(doc_to_text(poisoned_doc))
    pages = {pid: Page.from_dict({"page_id": pid, "doc_id": doc["doc_id"], "variant": v,
                                  "image_version": "clean", "text_version": tv,
                                  "pdf_path": "x.pdf", "image_path": f"{pid}.png", "text_path": "x.txt"})
             for pid, v, tv in [(clean_id, "clean", "clean"), (poison_id, atk.attack_id, "poison")]}
    run_cfg = {**cfg, "paths": {**cfg["paths"], "parsed_dir": str(tmp_path / "parsed")},
               "img_text_check": {"cache_dir": str(tmp_path / "cache"), "text_source": "docling"}}
    def fake_vlm(image_path, prompt):
        return json.dumps(doc["table"])

    assert check_page(clean_id, cfg=run_cfg, generator=fake_vlm, pages=pages)["flag"] is False
    r = check_page(poison_id, cfg=run_cfg, generator=fake_vlm, pages=pages)
    assert r["flag"] is True and len(r["mismatches"]) == 2
    assert len(list((tmp_path / "cache").glob("*.json"))) == 2


def test_chart_read_sideways_or_padded():
    padded = {"header": ["", "Mortality 2000", ""], "rows": [["Mali", "27.5", ""], ["Kenya", "17.3", ""]]}
    assert compare_with_text(padded, "Source data: Mali: 33.1; Kenya: 17.3.")["mismatches"] == [
        ["Mali", "value", "27.5", "33.1"]]
    sideways = {"header": ["", "Use SNS", "Do not go online"], "rows": [["27", "41", ""]]}
    assert compare_with_text(sideways, "Source data: Use SNS: 27; Do not go online: 47.")["mismatches"] == [
        ["Do not go online", "value", "41", "47"]]
    assert compare_with_text(sideways, "Source data: Use SNS: 27; Do not go online: 41.")["flag"] is False
