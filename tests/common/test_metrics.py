import math

import numpy as np

from src.common import metrics as M


def test_bootstrap_ci_brackets_mean():
    x = np.array([1] * 60 + [0] * 40)
    p, lo, hi = M.bootstrap_ci(x, n_resamples=500, seed=1)
    assert p == 0.6 and lo < 0.6 < hi and 0.45 < lo and hi < 0.75


def test_bootstrap_empty():
    assert all(math.isnan(v) for v in M.bootstrap_ci([]))


def _rec(qid, pr=None, prr=None, cited=(), mt=False, pid="X"):
    return {"qid": qid, "poison_rank_retr": pr, "poison_rank_rerank": prr, "cited": list(cited),
            "matches_target": mt, "poison_page_id": pid, "pipeline": "P1", "reranker": True}


def test_stage_funnel_and_asr():
    recs = [_rec("a", 1, 1, ["X"], True), _rec("b", 3, 2, [], False), _rec("c", None, None),
            _rec("d", 15, None)]
    f = M.stage_funnel(recs, n_resamples=50)
    assert f["retrieved@20"]["rate"] == 0.75
    assert f["top5"]["rate"] == 0.5
    assert f["cited"]["rate"] == 0.25
    assert f["attack_success"]["rate"] == 0.25
    assert M.asr_flags(recs, r2_correct={"a", "b"}) == [True, False]
    assert M.evidence_adoption_flags(recs) == [True, False]


def test_rank_change_and_which_version():
    clean = [{"qid": "a", "pipeline": "P1", "reranker": True, "gold_rank_retr": 2}]
    atk = [{"qid": "a", "pipeline": "P1", "reranker": True, "poison_rank_retr": 5}]
    assert M.rank_changes(atk, clean) == [3.0]
    assert M.which_version("20.4", "10.5", "20.4") == "text"
    assert M.which_version("10.5", "10.5", "20.4") == "image"
    assert M.which_version("20.4", "20.4", "20.4") == "both"
    assert M.which_version("7", "10.5", "20.4") == "neither"
