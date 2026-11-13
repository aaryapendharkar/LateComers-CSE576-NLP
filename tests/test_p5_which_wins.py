"""Person 5 (Disha): which-version-wins analysis on hand-made run records."""
import pytest

from src.analysis.which_wins import (label_runs, rank_shift_by_condition, to_markdown,
                                     which_wins_table)
from src.common.schemas import layer_answers

GOLD, TARGET = "10.5", "20.4"


def _attack(at, qid):
    img, txt = layer_answers(at, GOLD, TARGET)
    return {"attack_id": f"G2_{at}_{qid}", "qid": qid, "gap": "G2", "attack_type": at,
            "image_answer": img, "text_answer": txt, "gold_answer": GOLD, "target_answer": TARGET}


def _run(at, qid, pl, answer, poison_rank=1):
    return {"qid": qid, "attack_id": f"G2_{at}_{qid}", "pipeline": pl, "reranker": True,
            "answer": answer, "poison_rank_retr": poison_rank}


ATTACKS = {a["attack_id"]: a for a in
           [_attack(t, q) for t in ("text_only_table", "image_only_table", "propagate_table")
            for q in ("q1", "q2")]}

RUNS = [
    # P1 sees only text -> follows text on both conflict types
    _run("text_only_table", "q1", "P1", TARGET), _run("text_only_table", "q2", "P1", TARGET),
    _run("image_only_table", "q1", "P1", GOLD), _run("image_only_table", "q2", "P1", "99"),
    # P2 sees only the image -> follows image
    _run("text_only_table", "q1", "P2", GOLD), _run("image_only_table", "q1", "P2", TARGET),
    # propagate: both layers poisoned -> "both" if fooled
    _run("propagate_table", "q1", "P1", TARGET), _run("propagate_table", "q2", "P1", GOLD),
    {"qid": "q9", "attack_id": None, "pipeline": "P1", "reranker": True, "answer": "1"},  # clean run, skipped
]


def test_labels():
    lab = {(x["pipeline"], x["attack_id"]): x["label"] for x in label_runs(RUNS, ATTACKS)}
    assert lab[("P1", "G2_text_only_table_q1")] == "text"
    assert lab[("P1", "G2_image_only_table_q1")] == "text"      # gold is what P1's text layer shows
    assert lab[("P1", "G2_image_only_table_q2")] == "neither"
    assert lab[("P2", "G2_text_only_table_q1")] == "image"
    assert lab[("P2", "G2_image_only_table_q1")] == "image"
    assert lab[("P1", "G2_propagate_table_q1")] == "both"
    assert lab[("P1", "G2_propagate_table_q2")] == "neither"
    assert len(lab) == 8                                          # clean run skipped


def test_table_rates_and_r2_filter():
    rows = {(r["pipeline"], r["attack_type"]): r for r in which_wins_table(RUNS, ATTACKS)}
    assert rows[("P1", "text_only_table")]["follows_text"]["rate"] == 1.0
    assert rows[("P1", "image_only_table")]["follows_text"]["rate"] == 0.5
    assert rows[("P1", "image_only_table")]["follows_neither"]["rate"] == 0.5
    assert rows[("P2", "image_only_table")]["follows_image"]["rate"] == 1.0
    only_q1 = which_wins_table(RUNS, ATTACKS, r2_correct={"P1": {"q1"}, "P2": {"q1"}})
    assert all(r["n"] == 1 for r in only_q1)
    md = to_markdown(which_wins_table(RUNS, ATTACKS))
    assert "| P1 |" in md and "text_only_table" in md


def test_missing_layer_answers_is_a_clear_error():
    bad = {k: {**v, "image_answer": None} for k, v in ATTACKS.items()}
    with pytest.raises(ValueError, match="image_answer"):
        label_runs(RUNS, bad)


def test_rank_shift():
    clean = [{"qid": q, "attack_id": None, "pipeline": "P1", "reranker": True, "gold_rank_retr": 1}
             for q in ("q1", "q2")]
    attack_runs = [_run("text_only_table", "q1", "P1", TARGET, poison_rank=3),
                   _run("text_only_table", "q2", "P1", TARGET, poison_rank=1)]
    rows = rank_shift_by_condition(attack_runs, clean, ATTACKS, n_resamples=50)
    assert rows[0]["mean_rank_change"] == 1.0
    assert rows[0]["share_moved"]["rate"] == 0.5
    assert "_attack_type" not in attack_runs[0]
