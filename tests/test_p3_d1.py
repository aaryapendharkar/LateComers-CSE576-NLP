"""Tests for D1. Expected outcomes live in the fixture file and were derived by hand."""

import json
from pathlib import Path

import pytest

from src.defenses.d1_input import DetectorInputError, page_from_markdown, page_from_record
from src.defenses.reconcile import CHECKS_PASSED, CONTRADICTION, UNCHECKABLE, D1Config, diagnose, reconcile

FIXTURES = json.loads((Path(__file__).parent / "fixtures/synthetic/d1_cases.json").read_text())
CASES = {c["case_id"]: c for c in FIXTURES["cases"]}


def page(case_id):
    return page_from_record(CASES[case_id]["detector_input"], input_kind="synthetic_fixture")


@pytest.mark.parametrize("case_id", sorted(CASES))
def test_fixture_expectations(case_id):
    exp = CASES[case_id]["expected"]
    result = diagnose(page(case_id))
    record = result.eval_record()
    public = result.public()

    assert result.status == exp["status"]
    assert public["flag"] is exp["flag"]
    assert record["n_checks"] == exp["n_checks"]
    assert record["n_failed"] == exp["n_failed"]
    codes = {s["code"] for s in record["skipped"]}
    assert set(exp.get("skip_codes_include", [])) <= codes
    joined = "\n".join(public["reasons"])
    for fragment in exp.get("reason_contains", []):
        assert fragment in joined, f"{fragment!r} not in reasons:\n{joined}"


def test_public_contract_shape():
    for case_id in CASES:
        out = reconcile(page(case_id))
        assert set(out) == {"flag", "reasons"}
        assert isinstance(out["flag"], bool)
        assert out["reasons"] and all(isinstance(r, str) for r in out["reasons"])


def test_three_outcomes_are_distinguishable():
    statuses = {diagnose(page(c)).status for c in ("01_valid_table", "02_naive_edit_breaks_total", "15_ragged_parse_uncheckable")}
    assert statuses == {CHECKS_PASSED, CONTRADICTION, UNCHECKABLE}
    assert reconcile(page("15_ragged_parse_uncheckable"))["reasons"][0].startswith("NOT_CHECKABLE")
    assert reconcile(page("01_valid_table"))["reasons"][0].startswith("NO_CONTRADICTION_FOUND")


def test_nested_total_counts_subtotal_once():
    checks = diagnose(page("10_nested_subtotals_valid")).checks
    total_assets = next(c for c in checks if c.relationship.startswith("row 'Total assets'"))
    assert "nested" in total_assets.relationship
    assert "Cash" not in total_assets.relationship and "Total current assets" in total_assets.relationship
    assert total_assets.expected == "900"


def test_naive_edit_explanation_names_cells_and_tolerance():
    failed = diagnose(page("02_naive_edit_breaks_total")).failed
    assert len(failed) == 1
    c = failed[0]
    assert c.expected == "1,622" and c.observed == "1,514" and c.discrepancy == "108" and c.tolerance == "1.5"
    assert "Product revenue|2019=1,312" in c.cells and "Total revenue|2019=1,514" in c.cells


def test_dash_as_zero_is_explicit_opt_in():
    default = diagnose(page("09_missing_value_not_zero"))
    opted = diagnose(page("09_missing_value_not_zero"), D1Config(dash_as_zero=True))
    assert len(default.checks) == 1
    assert len(opted.checks) == 2 and opted.eval_record()["config"]["dash_as_zero"] is True


def test_ablation_configs():
    arith_only = D1Config(check_prose=False)
    prose_only = D1Config(check_arithmetic=False)
    # The consistent edit is only caught by prose.
    assert reconcile(page("04_consistent_edit_contradicted_by_prose"), arith_only)["flag"] is False
    assert reconcile(page("04_consistent_edit_contradicted_by_prose"), prose_only)["flag"] is True
    # The naive edit without prose is only caught by arithmetic.
    assert diagnose(page("02_naive_edit_breaks_total"), prose_only).status == UNCHECKABLE


@pytest.mark.parametrize("leaky_key", ["target_answer", "attack_type", "edit", "gold_answer", "page_id", "variant"])
def test_attack_metadata_is_rejected(leaky_key):
    record = dict(CASES["03_consistent_edit_passes_arithmetic"]["detector_input"])
    record[leaky_key] = "x"
    with pytest.raises(DetectorInputError):
        page_from_record(record, input_kind="synthetic_fixture")


def test_attack_metadata_inside_table_is_rejected():
    record = json.loads(json.dumps(CASES["03_consistent_edit_passes_arithmetic"]["detector_input"]))
    record["table"]["also_changed"] = [[2, 1, "1,514", "1,622"]]
    with pytest.raises(DetectorInputError):
        page_from_record(record, input_kind="synthetic_fixture")


def test_markdown_adapter_matches_structured_input():
    md = (
        "ACME Corp revenue by type is shown below.\n\n"
        "Revenue (in millions)\n"
        "| | 2019 | 2018 |\n"
        "|---|---|---|\n"
        "| Product revenue | 1,312 | 1,090 |\n"
        "| Service revenue | 310 | 295 |\n"
        "| Total revenue | 1,622 | 1,385 |\n\n"
        "Total revenue was $1.5 billion in 2019. Product revenue was $1,204 million in 2019, "
        "compared to $1,090 million in 2018.\n"
    )
    parsed = page_from_markdown(md)
    assert parsed.input_kind == "observed_parse"
    assert parsed.table.rows[2] == ["Total revenue", "1,622", "1,385"]
    rec = diagnose(parsed).eval_record()
    assert rec["status"] == CONTRADICTION
    assert rec["n_checks"] == {"arithmetic": 2, "prose": 3}
    assert rec["n_failed"] == {"arithmetic": 0, "prose": 2}


def test_markdown_without_table_is_uncheckable():
    parsed = page_from_markdown("Total revenue was $1.5 billion in 2019.")
    assert parsed.table is None
    assert diagnose(parsed).status == UNCHECKABLE


def test_docs_dry_run_projects_only_detector_fields(tmp_path):
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    doc = {"doc_id": "syn_doc__G1_naive_cell_q0001", "source": "synthetic", "attack_type": "naive_cell",
           **CASES["02_naive_edit_breaks_total"]["detector_input"]}
    docs = tmp_path / "docs.jsonl"
    docs.write_text(json.dumps(doc) + "\n")
    r = subprocess.run([sys.executable, str(root / "scripts/run_d1.py"), "docs", "--docs", str(docs),
                        "--out-dir", str(tmp_path / "out")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    row = json.loads((tmp_path / "out/d1_docs_results.jsonl").read_text())
    assert row["input_kind"] == "clean_structured_json"
    assert row["public_output"]["flag"] is True
    summary = json.loads((tmp_path / "out/d1_docs_summary.json").read_text())
    assert summary["data_label"].startswith("CLEAN STRUCTURED JSON")


# --------------------------------------------------------------------------
# Regressions for the 2026-11-11 independent review (findings 1-3).

import random


def _page(header, rows, title="Amounts in millions", prose=""):
    record = {"table": {"title": title, "header": header, "rows": rows}, "post_text": prose}
    return page_from_record(record, input_kind="synthetic_fixture")


def _codes(result):
    return {s.code for s in result.skipped}


# Finding 1: signs must survive table-to-prose comparison.

@pytest.mark.parametrize("label,value", [("Revenue", "100"), ("Operating income", "2,340"), ("Segment profit", "57.5")])
def test_prose_sign_conflict_is_a_contradiction(label, value):
    res = diagnose(_page(["", "2021"], [[label, f"({value})"]], prose=f"{label} was ${value} million in 2021."))
    assert res.status == CONTRADICTION
    (check,) = [c for c in res.checks if c.kind == "prose"]
    assert check.observed.startswith("-") and not check.expected.startswith("-")


@pytest.mark.parametrize("prose_amount", ["$(75) million", "-$75 million", "$-75 million", "−$75 million"])
def test_prose_consistent_negative_passes_with_signed_values(prose_amount):
    res = diagnose(_page(["", "2020"], [["Other income", "(75)"]], prose=f"Other income was {prose_amount} in 2020."))
    assert res.status == CHECKS_PASSED
    (check,) = res.checks
    assert check.expected == check.observed == "-75,000,000"


def test_prose_explicit_negative_vs_positive_cell_is_a_contradiction():
    res = diagnose(_page(["", "2020"], [["Other income", "75"]], prose="Other income was $(75) million in 2020."))
    assert res.status == CONTRADICTION


@pytest.mark.parametrize("label,prose", [
    ("Foreign exchange loss", "Foreign exchange loss was $150 million in 2019."),
    ("Other items", "Other items reflected a loss of $150 million in 2019."),
    ("Cash flows from investing activities", "Cash flows from investing activities used $150 million in 2019."),
])
def test_unsigned_magnitude_wording_is_reported_not_compared(label, prose):
    res = diagnose(_page(["", "2019"], [[label, "(150)"]], prose=prose))
    assert not [c for c in res.checks if c.kind == "prose"]
    assert "sign_semantics_unsupported" in _codes(res)
    assert res.status == UNCHECKABLE


# Finding 2: currency identity must be preserved; no conversion.

@pytest.mark.parametrize("cur_a,cur_b,code", [
    ("$", "€", "currency_mismatch"), ("£", "$", "currency_mismatch"), ("€", "£", "currency_mismatch"),
    ("US$", "$", "currency_ambiguous"), ("EUR ", "€", None),
])
def test_arithmetic_respects_currency_identity(cur_a, cur_b, code):
    rows = [["Product revenue", f"{cur_a}120"], ["Service revenue", f"{cur_b}30"], ["Total revenue", f"{cur_a}150"]]
    res = diagnose(_page(["", "2019"], rows))
    if code is None:  # same currency written two ways
        assert res.status == CHECKS_PASSED and len(res.checks) == 1
    else:
        assert not res.checks and code in _codes(res)
        assert res.status == UNCHECKABLE


def test_currency_on_some_cells_only_is_still_checked():
    rows = [["A", "$ 10"], ["B", "20"], ["Total", "$ 30"]]
    assert diagnose(_page(["", "2019"], rows)).status == CHECKS_PASSED


@pytest.mark.parametrize("cell,prose,code", [
    ("€1,500", "Revenue was $1.5 billion in 2019.", "currency_mismatch"),
    ("$1,500", "Revenue was €1.5 billion in 2019.", "currency_mismatch"),
    ("1,500", "Revenue was £1.5 billion in 2019.", "currency_mismatch"),  # table title declares euros
    ("$1,500", "Revenue was 1.5 billion euros in 2019.", "currency_mismatch"),
    ("US$1,500", "Revenue was $1.5 billion in 2019.", "currency_ambiguous"),
])
def test_prose_respects_currency_identity(cell, prose, code):
    title = "Amounts in millions of euros" if cell == "1,500" else "Amounts in millions"
    res = diagnose(_page(["", "2019"], [["Revenue", cell]], title=title, prose=prose))
    assert not res.checks and code in _codes(res)


# Finding 3: the checked relationship must not depend on whether values pass.

def _nested_rows(rng, sub_label, grand_label):
    a, b, c, d = (rng.randint(1, 999) for _ in range(4))
    return [["Cash", str(a)], ["Receivables", str(b)], [sub_label, str(a + b)],
            ["Property and equipment", str(c)], ["Goodwill", str(d)], [grand_label, str(a + b + c + d)]]


@pytest.mark.parametrize("seed", range(5))
@pytest.mark.parametrize("sub_label,grand_label", [("Total current assets", "Total assets"),
                                                   ("Subtotal", "Total"),
                                                   ("Total current liabilities", "Total liabilities")])
def test_grand_total_scope_does_not_follow_values(seed, sub_label, grand_label):
    rows = _nested_rows(random.Random(seed), sub_label, grand_label)
    clean = diagnose(_page(["", "2019"], rows))
    # Change only the grand total so that it equals the rows after the subtotal.
    changed_rows = [r[:] for r in rows]
    changed_rows[5][1] = str(int(rows[3][1]) + int(rows[4][1]))
    changed = diagnose(_page(["", "2019"], changed_rows))

    def grand(res):
        return next(c for c in res.checks if c.relationship.startswith(f"row '{grand_label}'"))

    assert clean.status == CHECKS_PASSED
    assert grand(changed).relationship == grand(clean).relationship
    assert changed.status == CONTRADICTION and not grand(changed).passed


def test_sibling_subtotals_are_not_merged_to_make_a_sum_pass():
    # 'Total services' is a sibling group of 'Total products'; it must be checked against
    # its own rows even though adding the products subtotal would make it pass.
    rows = [["Hardware", "10"], ["Software", "20"], ["Total products", "30"],
            ["Consulting", "5"], ["Support", "25"], ["Total services", "60"]]
    res = diagnose(_page(["", "2019"], rows))
    assert res.status == CONTRADICTION
    (bad,) = res.failed
    assert bad.relationship.startswith("row 'Total services'") and "Total products" not in bad.relationship


@pytest.mark.parametrize("grand_value", ["100", "130"])
def test_unresolvable_total_scope_is_reported_as_ambiguous(grand_value):
    rows = [["Salaries", "40"], ["Rent", "60"], ["Total operating expenses", "100"],
            ["Interest", "10"], ["Fees", "20"], ["Total other expenses", grand_value]]
    res = diagnose(_page(["", "2019"], rows))
    assert not any(c.relationship.startswith("row 'Total other expenses'") for c in res.checks)
    assert "total_scope_ambiguous" in _codes(res)
    assert "total_scope_ambiguous" in reconcile(_page(["", "2019"], rows))["reasons"][0]


def test_finqa_projection_keeps_source_text_and_drops_evaluation_fields():
    from src.defenses.d1_input import record_from_finqa

    entry = {"id": "X/2019/page_1.pdf-1", "filename": "X/2019/page_1.pdf",
             "pre_text": ["revenue was $ 1.5 billion in 2019 ."], "post_text": ["( in millions )"],
             "table_ori": [["", "2019"], ["A", "$(1,204)"], ["B", "296"], ["Total", "$(908)"]],
             "table": [["", "2019"], ["a", "-1204"]],
             "qa": {"question": "q", "answer": "908", "program": "add(1, 2)", "gold_inds": {}}}
    record = record_from_finqa(entry)
    assert set(record) <= {"table", "pre_text", "post_text"}
    assert record["table"] == {"header": ["", "2019"], "rows": [["A", "$(1,204)"], ["B", "296"], ["Total", "$(908)"]]}
    assert "908" not in record["pre_text"] + record["post_text"]
    page = page_from_record(record, input_kind="clean_structured_json")
    assert page.table.title == "" and page.table.unit_note == ""
    assert diagnose(page).status == CHECKS_PASSED


def test_team_config_section_is_accepted_and_unknown_settings_are_rejected():
    from src.common.config import load_config
    from src.defenses.reconcile import config_from_dict, reconcile_page

    assert config_from_dict(load_config()) == D1Config()
    page = "| | 2019 |\n|---|---|\n| A | 10 |\n| B | 20 |\n| Total | 40 |"
    assert reconcile_page(page, {"reconcile": {"check_arithmetic": False}})["flag"] is False
    assert reconcile_page(page)["flag"] is True
    with pytest.raises(ValueError, match="sum_abs_tol"):
        reconcile_page(page, {"reconcile": {"sum_abs_tol": 1.0}})
