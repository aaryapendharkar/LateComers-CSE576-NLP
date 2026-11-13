from src.attacks.representation.conflict import make_table_conditions
from src.common import io
from src.common.schemas import Attack, Page


def _g1(cfg):
    g2 = io.load_attacks(cfg)["G2_text_only_table_q0001"]
    return Attack.from_dict({**g2.to_dict(), "attack_id": "G1_consistent_cell_q0001", "gap": "G1",
                             "attack_type": "consistent_cell", "image_version": "poison",
                             "text_version": "poison",
                             "poison_page_id": "finqa_ACME_2019_p12__G1_consistent_cell_q0001"})


def test_three_conditions(cfg, tmp_path):
    doc = io.load_docs(cfg)["finqa_ACME_2019_p12"]
    calls, sink = [], []

    def fake_render(d, page_id, out_dir, image_table, text_table, image_pre_post=None, text_pre_post=None):
        calls.append((page_id, image_table, text_table))
        iv = "clean" if image_table == d["table"] else "poison"
        tv = "clean" if text_table == d["table"] else "poison"
        return {"page_id": page_id, "doc_id": d["doc_id"], "variant": page_id.split("__")[1],
                "image_version": iv, "text_version": tv, "pdf_path": "a.pdf",
                "image_path": "a.png", "text_path": "a.txt"}

    rows = make_table_conditions(_g1(cfg), doc, "10.5", str(tmp_path), render=fake_render, page_sink=sink)
    by = {a.attack_type: a for a in rows}
    assert set(by) == {"propagate_table", "text_only_table", "image_only_table"}
    assert by["propagate_table"].poison_page_id.endswith("G1_consistent_cell_q0001")
    assert len(calls) == 2 and len(sink) == 2
    for rec in sink:
        page = Page.from_dict(rec)
        a = next(r for r in rows if r.poison_page_id == page.page_id)
        assert (page.image_version, page.text_version) == (a.image_version, a.text_version)
    assert (by["text_only_table"].image_answer, by["text_only_table"].text_answer) == ("10.5", "20.4")
    assert (by["image_only_table"].image_answer, by["image_only_table"].text_answer) == ("20.4", "10.5")
    assert by["propagate_table"].image_answer == by["propagate_table"].text_answer == "20.4"
