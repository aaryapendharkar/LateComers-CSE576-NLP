"""Person 3: funnel analysis and the D1 evaluation script (synthetic records and repo fixtures only)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.analysis import funnel as F

ROOT = Path(__file__).resolve().parents[1]


def _atk(qid, aid, pr, prr, cited=(), mt=False, pipeline="P1", filtered=()):
    pid = f"doc_{qid}__{aid}"
    return {"qid": qid, "attack_id": aid, "pipeline": pipeline, "reranker": False, "poison_page_id": pid,
            "poison_rank_retr": pr, "poison_rank_rerank": prr, "cited": [pid] if cited else [],
            "matches_target": mt, "answer": "1", "filtered_pages": [pid] if filtered else []}


def _clean(qid, gr, grr, pipeline="P1"):
    return {"qid": qid, "attack_id": None, "pipeline": pipeline, "reranker": False,
            "gold_rank_retr": gr, "gold_rank_rerank": grr}


ATTACKS = {"A1": {"attack_type": "naive_cell", "target_answer": "9", "edit": {"row": 0, "col": 1}},
           "A2": {"attack_type": "consistent_cell", "target_answer": "9", "edit": {"row": 0, "col": 1}},
           "A3": {"attack_type": "naive_cell", "target_answer": "9", "edit": {"row": 0, "col": 1}},
           "A4": {"attack_type": "consistent_cell", "target_answer": "9", "edit": {"row": 0, "col": 1}}}
EXAMPLES = {"q1": {"question": "Q1?", "gold_answer": "1", "question_type": "arithmetic", "source": "finqa"},
            "q2": {"question": "Q2?", "gold_answer": "2", "question_type": "trend", "source": "finqa"},
            "q3": {"question": "Q3?", "gold_answer": "3", "question_type": None, "source": "finqa"}}
RUNS = [_atk("q1", "A1", 1, 1, cited=True, mt=True), _atk("q1", "A2", 1, 1, cited=False, mt=True),
        _atk("q2", "A3", 3, None), _atk("q3", "A4", None, None)]


def test_annotate_adds_types_without_mutating():
    recs = F.annotate(RUNS + [_clean("q1", 1, 1)], ATTACKS, EXAMPLES)
    assert [r["attack_type"] for r in recs] == ["naive_cell", "consistent_cell", "naive_cell", "consistent_cell", "clean"]
    assert [r["question_type"] for r in recs] == ["arithmetic", "arithmetic", "trend", "?", "arithmetic"]
    assert "attack_type" not in RUNS[0]


def test_funnel_by_uses_fixed_r2_denominator():
    recs = F.annotate(RUNS, ATTACKS, EXAMPLES)
    f = F.funnel_by(recs, ("pipeline", "attack_type"), {"P1": {"q1", "q2"}}, n_resamples=50)
    naive = f[("P1", "naive_cell")]
    assert naive["attack_success"]["n"] == 2 and naive["attack_success"]["rate"] == 0.5
    assert naive["retrieved@20"]["rate"] == 1.0 and naive["top5"]["rate"] == 0.5
    cons = f[("P1", "consistent_cell")]          # q3 is not R2-correct, so only the q1 run counts
    assert cons["attack_success"]["n"] == 1
    assert cons["target_without_citation"]["rate"] == 1.0   # target answer given, poisoned page not cited
    assert cons["adoption|top5"]["rate"] == 0.0
    by_q = F.funnel_by(recs, ("question_type",), {"q1", "q2", "q3"}, n_resamples=50)
    assert set(by_q) == {("arithmetic",), ("trend",), ("?",)}


def test_retrieval_poison_vs_clean_pairs_on_question():
    clean = [_clean("q1", 1, 1), _clean("q2", 2, 2)]
    r = F.retrieval_poison_vs_clean(RUNS, clean, n_resamples=50)
    assert r["n_pairs"] == 3 and r["n_attack_runs_without_clean_run"] == 1
    assert r["poison_retrieved@20"]["rate"] == 1.0 and r["clean_retrieved@20"]["rate"] == 1.0
    assert r["mean_rank_change"]["mean"] == pytest.approx((0 + 0 + 1) / 3)
    assert r["poison_top5"]["rate"] == pytest.approx(2 / 3)


def test_asr_with_defense_keeps_denominator():
    defended = [_atk("q1", "A1", 1, 1, mt=False, filtered=True), _atk("q1", "A2", 1, 1, mt=True)]
    r = F.asr_with_defense(RUNS, defended, {"q1", "q2"}, n_resamples=50)
    assert r["asr_undefended"]["n"] == 3 and r["asr_undefended"]["rate"] == pytest.approx(2 / 3)
    assert r["asr_defended"]["rate"] == 0.5 and r["poison_page_dropped"]["rate"] == 0.5


def test_pick_examples_prefers_cited_and_distinct_types():
    ex = F.pick_examples(F.annotate(RUNS, ATTACKS, EXAMPLES), 2, ATTACKS, EXAMPLES)
    assert [e["attack_id"] for e in ex] == ["A1", "A2"]
    assert ex[0]["cited_poisoned_page"] is True and ex[0]["question"] == "Q1?" and ex[0]["target_answer"] == "9"
    assert F.pick_examples([_atk("q2", "A3", 3, None)], 2) == []


def test_eval_reconcile_script_on_fixtures(tmp_path):
    env = {**os.environ, "CSE576_CONFIG": str(ROOT / "tests/fixtures/config.yaml")}
    r = subprocess.run([sys.executable, str(ROOT / "scripts/eval_reconcile.py"), "--out-dir", str(tmp_path)],
                       capture_output=True, text=True, env=env, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    flags = {j["page_id"]: j for j in map(json.loads, (tmp_path / "d1_flags.jsonl").read_text().splitlines())}
    assert flags["finqa_ACME_2019_p12__clean"]["flag"] is False
    assert flags["finqa_ACME_2019_p12__G1_naive_cell_q0001"]["flag"] is True
    assert flags["finqa_ACME_2019_p12__G1_consistent_cell_q0001"]["flag"] is False
    s = json.loads((tmp_path / "d1_summary.json").read_text())
    assert s["clean"]["false_positive_rate"]["rate"] == 0.0
    assert s["attacks"]["naive_cell"]["newly_flagged"]["rate"] == 1.0
    assert s["pairs"]["n_differing_pairs"] == 1 and s["pairs"]["discordant_naive_only"] == 1
    assert "| naive_cell |" in (tmp_path / "d1_table.md").read_text()


def _cell_attacks(n_docs=12, stale=(0, 1, 2)):
    out = {}
    for i in range(n_docs):
        for kind in ("naive_cell", "consistent_cell"):
            also = [[3, 1, "1", "2"]] if kind == "consistent_cell" and i in stale else []
            out[f"G1_{kind}_q{i}"] = {"attack_type": kind, "qid": f"q{i}", "clean_page_id": f"d{i}__clean",
                                      "poison_page_id": f"d{i}__G1_{kind}_q{i}", "edit": {"also_changed": also}}
    return out


def test_sample_pages_no_twins_and_balanced():
    from src.analysis.stealth import StealthInputError, sample_pages
    docs = [f"d{i}" for i in range(30)]
    items = sample_pages(6, 6, seed=1, attacks=_cell_attacks(), clean_doc_ids=docs)
    assert [i["item"] for i in items] == [f"S{k:02d}" for k in range(1, 13)]
    assert len({i["doc_id"] for i in items}) == 12                      # no document appears twice
    conds = [i["condition"] for i in items]
    assert conds.count("naive_cell") == 3 and conds.count("consistent_cell") == 3 and conds.count("clean") == 6
    naive_docs = {i["doc_id"] for i in items if i["condition"] == "naive_cell"}
    assert naive_docs == {"d0", "d1", "d2"}                            # stale-total pairs are used first
    assert items == sample_pages(6, 6, seed=1, attacks=_cell_attacks(), clean_doc_ids=docs)
    with pytest.raises(StealthInputError):
        sample_pages(6, 40, seed=1, attacks=_cell_attacks(), clean_doc_ids=docs)


def test_stealth_script_analyzes_a_forms_export(tmp_path):
    key = tmp_path / "key.csv"
    key.write_text("item,page_id,doc_id,is_poisoned,condition\n"
                   "S01,a__x,a,True,naive_cell\nS02,b__clean,b,False,clean\n")
    resp = tmp_path / "responses.csv"
    resp.write_text("Timestamp,Your name,Page S01,Page S02\n"
                    "t,Ann,Looks edited,Looks normal\nt,Bo,Looks edited,Looks normal\nt,Cy,Looks normal,Looks normal\n")
    out = tmp_path / "stealth_summary.json"
    r = subprocess.run([sys.executable, str(ROOT / "scripts/stealth_study.py"), "analyze", "--responses", str(resp),
                        "--key", str(key), "--out", str(out)], capture_output=True, text=True, cwd=ROOT,
                       env={**os.environ, "CSE576_CONFIG": str(ROOT / "tests/fixtures/config.yaml")})
    assert r.returncode == 0, r.stderr
    s = json.loads(out.read_text())
    assert s["n_pages_rated"] == 2 and s["n_distinct_raters"] == 3 and s["page_majority_correct"] == 2
    assert s["by_condition_descriptive"]["naive_cell"]["share_rated_looks_edited"] == pytest.approx(2 / 3)
