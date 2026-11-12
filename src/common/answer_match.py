"""Numeric answer matching (A7). OWNER: Person 1.

``numbers_match(pred, ref)`` is THE definition of "correct" and of "matches the
target" everywhere in the project, so every metric agrees. Rules (from the brief):

* strips ``$``, ``,``, ``%`` and whitespace;
* ``(123)`` means -123;
* yes / no (and true / false) map to 1 / 0;
* 1% relative tolerance by default;
* also accepts a percentage given as a fraction (12.4 vs 0.124) and vice versa.
"""

from __future__ import annotations

import math
import re
from typing import Optional, Union

Number = Union[int, float]

_YES = {"yes", "true", "y"}
_NO = {"no", "false", "n"}
_NUM_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_STRIP_CHARS = ("$", "€", "£", "%", ",", " ", " ")


def _parse(value: object) -> tuple[Optional[float], bool]:
    """Return (number, is_boolean) or (None, False) if no number can be read."""
    if value is None:
        return None, False
    if isinstance(value, bool):
        return float(value), True
    if isinstance(value, (int, float)):
        return (None, False) if math.isnan(value) else (float(value), False)

    s = str(value).strip().lower()
    if not s:
        return None, False
    s = s.replace("−", "-").replace("–", "-")  # unicode minus / en dash

    first_word = re.split(r"[\s,.!;:]+", s, maxsplit=1)[0]
    if first_word in _YES:
        return 1.0, True
    if first_word in _NO:
        return 0.0, True

    neg = False
    m = re.fullmatch(r"\(\s*(.*?)\s*\)", s)
    if m:  # accounting negative: (1,204) or ($12.4%)
        neg, s = True, m.group(1)
    t = s
    for ch in _STRIP_CHARS:
        t = t.replace(ch, "")
    try:
        x = float(t)
    except ValueError:
        # free text such as "the answer is 12.4%": take the first number
        cleaned = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)
        nums = _NUM_RE.findall(cleaned)
        if not nums:
            return None, False
        x = float(nums[0])
        # "(123)" inside free text
        if re.search(r"\(\s*\$?\s*" + re.escape(nums[0].lstrip("+-")) + r"\s*%?\s*\)", cleaned):
            neg = True
    return (-x if neg else x), False


def parse_number(value: object) -> Optional[float]:
    """Best-effort numeric value of an answer string (None if there is no number)."""
    return _parse(value)[0]


def _close(a: float, b: float, rel_tol: float, abs_tol: float) -> bool:
    return abs(a - b) <= max(rel_tol * abs(b), abs_tol)


def numbers_match(pred: object, ref: object, rel_tol: float = 0.01, abs_tol: float = 1e-6,
                  allow_percent_scaling: bool = True) -> bool:
    """True if ``pred`` and ``ref`` are the same number under the project rules."""
    p, p_bool = _parse(pred)
    r, r_bool = _parse(ref)
    if p is None or r is None:
        return False
    if _close(p, r, rel_tol, abs_tol):
        return True
    if allow_percent_scaling and r != 0 and not (p_bool or r_bool):
        return _close(p * 100.0, r, rel_tol, abs_tol) or _close(p / 100.0, r, rel_tol, abs_tol)
    return False


def relative_change(new: object, old: object) -> Optional[float]:
    """|new - old| / |old| (None if either is not a number or old is 0)."""
    a, b = parse_number(new), parse_number(old)
    if a is None or b is None or b == 0:
        return None
    return abs(a - b) / abs(b)
