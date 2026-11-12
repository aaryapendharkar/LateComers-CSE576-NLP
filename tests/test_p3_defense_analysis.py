"""Person 3 (Vatsal) acceptance tests. Skipped until the stubs are implemented."""
from src.analysis import qtypes
from src.common import io
from src.common.edits import apply_edit
from src.common.tables import doc_to_text
from src.defenses import reconcile


def test_qtype_rules(cfg):
    exs = io.load_examples(cfg, ("finqa",), with_qtypes=False)
    assert qtypes.label_finqa(exs["q0003"].question, exs["q0003"].program) == "comparison"
    assert qtypes.label_finqa(exs["q0002"].question, exs["q0002"].program) == "arithmetic"
    assert qtypes.label_finqa(exs["q0005"].question, exs["q0005"].program) == "trend"
    assert qtypes.label_chartqa("How many thousand e-bikes were sold in 2019?") == "lookup"


def test_d1_clean_not_flagged_naive_flagged_consistent_passes(cfg):
    docs, atk = io.load_docs(cfg), io.load_attacks(cfg)
    doc = docs["finqa_ACME_2019_p12"].to_dict()
    assert reconcile.reconcile_page(doc_to_text(doc))["flag"] is False
    naive = apply_edit(doc, atk["G1_naive_cell_q0001"].edit)
    r = reconcile.reconcile_page(doc_to_text(naive))
    assert r["flag"] is True and r["reasons"]
    consistent = apply_edit(doc, atk["G1_consistent_cell_q0001"].edit)
    assert reconcile.reconcile_page(doc_to_text(consistent))["flag"] is False
