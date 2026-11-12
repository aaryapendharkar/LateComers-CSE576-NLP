"""Person 5 (Disha) acceptance tests on mock JSON pairs. Skipped until implemented."""
from src.common import io
from src.common.edits import apply_edit
from src.defenses.img_text_check import compare_tables


def test_compare_tables(cfg):
    doc = io.load_docs(cfg)["finqa_ACME_2019_p12"].to_dict()
    atk = io.load_attacks(cfg)["G2_text_only_table_q0001"]
    poisoned = apply_edit(doc, atk.edit)["table"]
    assert compare_tables(doc["table"], doc["table"])["flag"] is False
    r = compare_tables(doc["table"], poisoned)
    assert r["flag"] is True and len(r["mismatches"]) == 2       # edited cell + its total
    # within-tolerance differences (VLM rounding) are not mismatches
    near = apply_edit(doc, {"row": 1, "col": 1, "old": "1,204", "new": "1,205"})["table"]
    assert compare_tables(doc["table"], near, rel_tol=0.01)["flag"] is False
