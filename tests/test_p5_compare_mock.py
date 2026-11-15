import pytest

from src.defenses.img_text_check import align, cells_equal, compare_tables


def T(rows, header=("", "2019", "2018"), unit="in millions"):
    return {"title": "t", "unit_note": unit, "header": list(header), "rows": [list(r) for r in rows]}


CLEAN = T([["Revenue", "1,204", "1,090"], ["Cost of sales", "(700)", "(650)"], ["Total", "504", "440"]])

CASES = [
    ("clean_identical", CLEAN, CLEAN, False, 0),
    ("text_only_edit_cell_and_total", CLEAN,
     T([["Revenue", "1,312", "1,090"], ["Cost of sales", "(700)", "(650)"], ["Total", "612", "440"]]), True, 2),
    ("format_only",
     T([["Operating cash", "$1,204", "$980"], ["Capex", "(90)", "(75)"], ["Free cash flow*", "1,114", "905"]],
       header=("", "2020", "2019"), unit="in thousands"),
     T([["Operating cash", "1204", "980"], ["Capex", "-90", "-75"], ["Free cash flow", "1114", "905*"]],
       header=("", "2020", "2019"), unit="In thousands"), False, 0),
    ("ocr_typo_and_duplicate_total",
     T([["Reveune - US", "800", "760"], ["Revenue - Intl", "404", "330"], ["Total", "1,204", "1,090"],
        ["Expenses - US", "500", "480"], ["Expenses - Intl", "200", "170"], ["Total", "700", "650"]]),
     T([["Revenue - US", "800", "760"], ["Revenue - Intl", "404", "330"], ["Total", "1,204", "1,090"],
        ["Expenses - US", "500", "480"], ["Expenses - Intl", "200", "170"], ["Total", "700", "720"]]), True, 1),
    ("unit_note_conflict", T([["Total assets", "5,400", "5,100"]], unit="in thousands"),
     T([["Total assets", "5,400", "5,100"]], unit="in millions"), True, 1),
    ("chart_text_only",
     T([["North", "42"], ["South", "35"], ["East", "28"]], header=("", "Sales"), unit=""),
     T([["North", "42"], ["South", "41"], ["East", "28"]], header=("", "Sales"), unit=""), True, 1),
]


@pytest.mark.parametrize("name,img,txt,flag,n", CASES, ids=[c[0] for c in CASES])
def test_mock_pairs(name, img, txt, flag, n):
    r = compare_tables(img, txt)
    assert r["flag"] is flag
    assert len(r["mismatches"]) == n


def test_duplicate_total_reports_the_right_row():
    _, img, txt, *_ = CASES[3]
    assert compare_tables(img, txt)["mismatches"] == [["Total", "2018", "650", "720"]]


def test_only_rows_mode():
    _, img, txt, *_ = CASES[1]
    r = compare_tables(img, txt, only_rows=["Revenue"])
    assert r["mismatches"] == [["Revenue", "2019", "1,204", "1,312"]]


def test_helpers():
    assert cells_equal("(1,090)", "-1090")
    assert not cells_equal("1,204", "1,312")
    assert align(["Total", "A", "Total"], ["Total", "A", "Total"]) == [(0, 0), (1, 1), (2, 2)]
