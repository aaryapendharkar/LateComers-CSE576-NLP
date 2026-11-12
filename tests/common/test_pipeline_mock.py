"""End-to-end runner on fixtures with the mock backend (no GPU)."""

import pytest

from src.common.schemas import RunRecord
from src.pipelines.generate import parse_generation
from src.pipelines.p3_hybrid import rrf
from src.pipelines.run import RAGSystem


@pytest.fixture(scope="module")
def system(cfg):
    return RAGSystem(cfg)


def test_record_has_all_a6_fields(system):
    rec = system.run_query("q0001", "P1", reranker=True)
    RunRecord.from_dict(rec)  # raises if a field is missing
    assert rec["gold_rank_retr"] == 1 and rec["attack_id"] is None


def test_self_swap_changes_nothing(system):
    a = system.run_query("q0001", "P1", True)
    b = system.run_query("q0001", "P1", True, swap={"finqa_ACME_2019_p12__clean": "finqa_ACME_2019_p12__clean"})
    for k in ("top20", "top5", "answer", "cited", "gold_rank_retr", "correct"):
        assert a[k] == b[k]


def test_poison_swap_only_changes_that_page(system):
    atk = system.attacks["G1_consistent_cell_q0001"]
    clean = system.run_query("q0001", "P1", True)
    pois = system.run_query("q0001", "P1", True, attack=atk)
    assert pois["poison_page_id"] == atk.poison_page_id
    assert pois["poison_rank_retr"] is not None and pois["gold_rank_retr"] is None
    others = lambda r: [p for p in r["top20"] if not p.startswith("finqa_ACME_2019_p12")]
    assert others(clean) == others(pois)
    assert pois["matches_target"] is not None


@pytest.mark.parametrize("mode", ["closed_book", "oracle"])
def test_r1_r3_modes(system, mode):
    rec = system.run_query("q0002", "P1", False, mode=mode)
    assert rec["mode"] == mode and (rec["top5"] == [] if mode == "closed_book" else len(rec["top5"]) == 1)


def test_drop_pages_filter(system):
    rec = system.run_query("q0001", "P1", True, drop_pages={"finqa_ACME_2019_p12__clean"})
    assert rec["filtered_pages"] == ["finqa_ACME_2019_p12__clean"]


def test_parse_generation_robust():
    r = parse_generation('```json\n{"answer": "12.4", "cited_pages": ["p1"]}\n```')
    assert r.answer == "12.4" and r.cited == ["p1"]
    r = parse_generation("Sure! {'answer': '-45', 'cited_pages': ['a']} hope that helps", ["a"])
    assert r.answer == "-45" and r.cited == ["a"]
    r = parse_generation("answer: 7.53 based on [PAGE b]")
    assert r.answer == "7.53" and r.cited == ["b"]


def test_rrf():
    fused = rrf([["a", "b", "c"], ["b", "a", "d"]], k=60)
    assert [p for p, _ in fused][:2] in (["a", "b"], ["b", "a"]) and fused[-1][0] in ("c", "d")
