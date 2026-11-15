import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.analysis.qtypes import LABELS, propose
from src.analysis.stealth import analyze, binom_sf, critical_k, fleiss_kappa

ROOT = Path(__file__).resolve().parents[1]
QTYPE_EXAMPLES = [json.loads(l) for l in (ROOT / "tests/fixtures/synthetic/qtype_examples.jsonl").read_text().splitlines()]


@pytest.mark.parametrize("ex", QTYPE_EXAMPLES, ids=lambda e: e["qid"])
def test_qtype_rules(ex):
    p = propose(ex["qid"], ex["question"], ex["program"])
    assert p.proposed_question_type == ex["expected_by_rules"]
    assert p.proposed_question_type in LABELS
    assert p.needs_review is ex["expected_needs_review"], p.review_notes


def test_trend_needs_two_periods():
    assert propose("a", "what was the increase in revenue in 2019?", "subtract(5, 3)").proposed_question_type == "arithmetic"
    assert propose("b", "what was the increase in revenue from 2018 to 2019?", "subtract(5, 3)").proposed_question_type == "trend"


def test_label_script_writes_separate_outputs(tmp_path):
    out = tmp_path / "qt"
    r = subprocess.run([sys.executable, str(ROOT / "scripts/qtype_review_sheet.py"), "--examples",
                        str(ROOT / "tests/fixtures/synthetic/qtype_examples.jsonl"), "--out-dir", str(out),
                        "--review-sample", "5", "--synthetic"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    props = [json.loads(l) for l in (out / "proposed_labels.jsonl").read_text().splitlines()]
    assert len(props) == len(QTYPE_EXAMPLES)
    assert all(p["data_label"] == "SYNTHETIC" and p["manually_validated"] is False for p in props)
    sheet = (out / "manual_review_sheet.csv").read_text().splitlines()
    assert sum("random_agreement_sample" in l for l in sheet) == 5
    assert sheet[0].endswith("reviewer_label,reviewer_initials,agrees_with_proposal,reviewer_comment")


def test_fleiss_kappa_reference_example():
    # Worked example from Fleiss (1971) as reproduced on Wikipedia "Fleiss' kappa":
    # 10 subjects, 14 raters, 5 categories, kappa = 0.210. Cross-checked with
    # statsmodels.stats.inter_rater.fleiss_kappa (outside this repo): 0.20993.
    table = [[0, 0, 0, 0, 14], [0, 2, 6, 4, 2], [0, 0, 3, 5, 6], [0, 3, 9, 2, 0], [2, 2, 8, 1, 1],
             [7, 7, 0, 0, 0], [3, 2, 6, 3, 0], [2, 5, 3, 2, 2], [6, 5, 2, 1, 0], [0, 2, 2, 3, 7]]
    assert fleiss_kappa(table) == pytest.approx(0.20993, abs=5e-5)


def test_binomial_tail():
    assert binom_sf(2, 3) == pytest.approx(0.5)  # P(X>=2 | n=3) = 4/8
    assert binom_sf(0, 40) == pytest.approx(1.0)
    k = critical_k(40)
    assert binom_sf(k, 40) <= 0.05 < binom_sf(k - 1, 40)


def test_analyze_uses_pages_not_ratings():
    # Tiny synthetic sheet: 2 poisoned and 2 clean pages, 3 raters.
    key = [{"item_id": f"i{i}", "is_poisoned": i < 2, "condition": "x", "doc_id": f"d{i}"} for i in range(4)]
    votes = {"i0": ["looks_edited"] * 3, "i1": ["looks_normal"] * 3,
             "i2": ["looks_normal"] * 3, "i3": ["looks_normal", "looks_normal", "looks_edited"]}
    ratings = [{"rater_id": f"r{j}", "item_id": i, "rating": v[j]} for i, v in votes.items() for j in range(3)]
    out = analyze(ratings, key)
    assert out["n_pages_rated"] == 4 and out["n_ratings"] == 12
    assert out["page_majority_correct"] == 3
    assert out["per_rater"]["r2"] == {"tp": 1, "fn": 1, "tn": 1, "fp": 1, "sensitivity": 0.5, "specificity": 0.5}


# Regressions for the 2026-11-11 review (finding 4): validate stealth input.

def _sheet(n_items=2, raters=("r1", "r2", "r3")):
    key = [{"item_id": f"i{i}", "is_poisoned": i % 2 == 0, "condition": "c", "doc_id": f"d{i}"} for i in range(n_items)]
    ratings = [{"rater_id": r, "item_id": k["item_id"],
                "rating": "looks_edited" if k["is_poisoned"] else "looks_normal"} for k in key for r in raters]
    return ratings, key


def test_stealth_valid_sheet_is_accepted():
    ratings, key = _sheet()
    assert analyze(ratings, key)["n_pages_rated"] == 2


@pytest.mark.parametrize("mutate,message", [
    (lambda r, k: (r + [dict(r[0])], k), "duplicate rating"),
    (lambda r, k: ([dict(x, rater_id="r1") for x in r], k), "distinct raters"),
    (lambda r, k: (r, k + [dict(k[0])]), "duplicate item_id in answer key"),
    (lambda r, k: ([x for x in r if x["item_id"] != "i1"], k), "no ratings"),
    (lambda r, k: ([x for x in r if not (x["item_id"] == "i1" and x["rater_id"] == "r3")], k), "distinct raters"),
    (lambda r, k: ([], k), "empty"),
    (lambda r, k: (r, []), "empty"),
    (lambda r, k: ([{kk: v for kk, v in x.items() if kk != "rater_id"} for x in r], k), "missing field"),
    (lambda r, k: (r, [dict(x, is_poisoned="yes") for x in k]), "is_poisoned"),
    (lambda r, k: ([dict(x, rating="unsure") for x in r], k), "invalid rating"),
])
def test_stealth_rejects_invalid_input(mutate, message):
    ratings, key = mutate(*_sheet())
    with pytest.raises(ValueError, match=message):
        analyze(ratings, key)
