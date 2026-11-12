import pytest

from src.common.answer_match import numbers_match, parse_number


@pytest.mark.parametrize("s, v", [
    ("1,204", 1204.0), ("$1,204.5", 1204.5), ("12.4%", 12.4), ("(123)", -123.0),
    ("($1,204)", -1204.0), ("-7.5", -7.5), ("−3.2", -3.2), ("yes", 1.0), ("No", 0.0),
    ("The answer is 12.4%.", 12.4), ("", None), ("n/a", None), (None, None), (3, 3.0),
])
def test_parse_number(s, v):
    assert parse_number(s) == v


@pytest.mark.parametrize("pred, ref, ok", [
    ("12.4", "12.4", True),
    ("12.45", "12.4", True),        # within 1%
    ("12.6", "12.4", False),        # 1.6% off
    ("0.124", "12.4", True),        # percentage given as a fraction
    ("12.4", "0.124", True),
    ("$1,204", "1204", True),
    ("(45.2)", "-45.2", True),
    ("yes", "1", True), ("no", "0", True), ("yes", "no", False),
    ("100", "yes", False),          # no percent scaling for yes/no answers
    ("0", "0", True), ("0.0001", "0", False),
    ("abc", "12", False), (None, "12", False),
])
def test_numbers_match(pred, ref, ok):
    assert numbers_match(pred, ref) is ok
