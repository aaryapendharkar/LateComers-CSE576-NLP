"""Person 2 (Janhavi) acceptance tests. Skipped until the stubs are implemented."""
import random

from src.attacks.tables import dependencies, edits, finqa_program, numbers
from src.common import io
from src.common.answer_match import numbers_match
from src.common.edits import apply_edit
from src.common.schemas import Attack


def test_parse_and_format_keep_style():
    c = numbers.parse_cell("1,204")
    assert c.value == 1204 and numbers.format_like(1312, c) == "1,312"
    c = numbers.parse_cell("(45.2)")
    assert c.value == -45.2 and numbers.format_like(-50.0, c) == "(50.0)"
    assert numbers.parse_cell("3.4%").value == 3.4
    assert numbers.parse_cell("Revenue") is None


def test_executor_reproduces_fixture_gold(cfg):
    docs, exs = io.load_docs(cfg), io.load_examples(cfg, ("finqa",))
    for ex in exs.values():
        res = finqa_program.execute(ex.program, docs[ex.doc_id].table)
        assert numbers_match(finqa_program.answer_to_str(res.value), ex.gold_answer), ex.qid


def test_argument_mapping(cfg):
    doc = io.load_docs(cfg)["finqa_ACME_2019_p12"].to_dict()
    srcs = finqa_program.map_arguments("subtract(1204, 1090), divide(#0, 1090)", doc)
    table_args = [s for s in srcs if s.kind == "table"]
    assert (1, 1) in [s.cell for s in table_args] and (1, 2) in [s.cell for s in table_args]


def test_finds_totals(cfg):
    t = io.load_docs(cfg)["finqa_ACME_2019_p12"].table
    rels = dependencies.find_totals(t)
    assert any(r.total == (3, 1) for r in rels)
    assert (3, 1) in dependencies.dependents((1, 1), rels)


def test_consistent_passes_and_naive_fails_sum(cfg):
    docs, exs = io.load_docs(cfg), io.load_examples(cfg, ("finqa",))
    a = edits.make_consistent_cell(exs["q0001"], docs["finqa_ACME_2019_p12"], random.Random(0))
    assert a is not None
    Attack.from_dict(a.to_dict())
    new = apply_edit(docs["finqa_ACME_2019_p12"].table, a.edit)
    col = [float(r[1].replace(",", "")) for r in new["rows"]]
    assert abs(col[0] + col[1] - col[2]) < 1.0, "consistent edit must keep the total right"
    naive = edits.make_naive_cell(a, docs["finqa_ACME_2019_p12"])
    new = apply_edit(docs["finqa_ACME_2019_p12"].table, naive.edit)
    col = [float(r[1].replace(",", "")) for r in new["rows"]]
    assert abs(col[0] + col[1] - col[2]) >= 1.0, "naive edit must break the total"
    assert not numbers_match(a.target_answer, exs["q0001"].gold_answer, rel_tol=0.05)
