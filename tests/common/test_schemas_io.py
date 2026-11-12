import pytest

from src.common import io
from src.common.edits import EditError, apply_edit
from src.common.schemas import Attack, SchemaError, attack_id, layer_answers, poison_page_id


def test_fixtures_load_and_validate(cfg):
    docs = io.load_docs(cfg)
    ex = io.load_examples(cfg)
    atk = io.load_attacks(cfg)
    assert len(docs) == 4 and len(ex) == 6 and len(atk) == 4
    assert ex["q0003"].question_type == "comparison"  # qtype overlay from Person 3's file
    for a in atk.values():
        assert a.qid in ex
        assert a.poison_page_id == poison_page_id(ex[a.qid].doc_id, a.gap, a.attack_type, a.qid)


def test_attack_layer_validation():
    good = dict(attack_id="x", qid="q", gap="G2", attack_type="text_only_table", clean_page_id="c",
                poison_page_id="p", edit={}, target_answer="1", image_version="clean", text_version="poison")
    Attack.from_dict(good)
    with pytest.raises(SchemaError):
        Attack.from_dict({**good, "image_version": "poison"})
    assert attack_id("G1", "unit", "q0007") == "G1_unit_q0007"
    assert layer_answers("image_only_chart", gold="5", target="7") == ("7", "5")


def test_apply_edit(cfg):
    doc = io.load_docs(cfg)["finqa_ACME_2019_p12"].to_dict()
    a = io.load_attacks(cfg)["G1_consistent_cell_q0001"]
    new = apply_edit(doc, a.edit)
    assert new["table"]["rows"][0][1] == "1,312" and new["table"]["rows"][2][1] == "1,824"
    assert doc["table"]["rows"][0][1] == "1,204"  # input untouched
    with pytest.raises(EditError):
        apply_edit(new, a.edit)  # old value no longer matches
    h = io.load_attacks(cfg)["G1_header_q0005"]
    gamma = io.load_docs(cfg)["finqa_GAMMA_2020_p7"].to_dict()
    assert apply_edit(gamma, h.edit)["table"]["header"][1] == "2019"


def test_write_read_roundtrip(tmp_path):
    p = tmp_path / "x.jsonl"
    io.write_jsonl(p, [{"a": 1}, {"a": 2}])
    io.append_jsonl(p, {"a": 3})
    assert [r["a"] for r in io.read_jsonl(p)] == [1, 2, 3]
