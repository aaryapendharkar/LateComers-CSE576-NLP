from decimal import Decimal

import pytest

from src.defenses.d1_numbers import MISSING, NUMBER, TEXT, detect_table_scale, parse_number


@pytest.mark.parametrize(
    "raw, value, decimals, percent",
    [
        ("1,204", "1204", 0, False),
        ("$ 1,204.50", "1204.50", 2, False),
        ("(1,200)", "-1200", 0, False),
        ("$ (150)", "-150", 0, False),
        ("( $ 75 )", "-75", 0, False),
        ("-3.5", "-3.5", 1, False),
        ("12.4%", "12.4", 1, True),
        ("( 12.4 % )", "-12.4", 1, True),
        ("100.0", "100.0", 1, False),
        ("1,204 (a)", "1204", 0, False),
    ],
)
def test_parse_number_values(raw, value, decimals, percent):
    cell = parse_number(raw)
    assert cell.kind == NUMBER
    assert cell.value == Decimal(value)
    assert cell.decimals == decimals
    assert cell.percent is percent


def test_scale_word_inside_cell_is_kept_separate():
    cell = parse_number("$1.2 billion")
    assert cell.value == Decimal("1.2") and cell.scale_word == "billion"


@pytest.mark.parametrize("raw", ["", "-", "—", "n/a"])
def test_missing_markers_are_missing_not_zero(raw):
    cell = parse_number(raw)
    assert cell.kind == MISSING and cell.value is None


@pytest.mark.parametrize("raw", ["1,20", "(-5)", "Total revenue 1,514", "12.4% ( 12.4 % )", "1.2.3"])
def test_ambiguous_or_garbled_cells_are_text(raw):
    assert parse_number(raw).kind == TEXT


def test_half_unit_follows_printed_precision():
    assert parse_number("100").half_unit == Decimal("0.5")
    assert parse_number("33.3").half_unit == Decimal("0.05")


def test_table_scale_detection():
    assert detect_table_scale(["(in millions)"]).multiplier == Decimal(10) ** 6
    assert detect_table_scale(["Dollars in thousands"]).multiplier == Decimal(10) ** 3
    assert detect_table_scale(["", "2019"]).status == "absent"
    amb = detect_table_scale(["Revenue (in thousands)", "in millions"])
    assert amb.status == "ambiguous" and amb.multiplier is None
    assert detect_table_scale(["in millions, except per share data"]).per_share_exception
