"""Table-cell number parsing that keeps the original formatting.

OWNER: Person 2 (Janhavi) -- Gap 1 attacks. Brief task 2.

Unlike ``src/common/answer_match.parse_number`` (which only needs a value),
this module must remember HOW a number was written so an edited value can be
written back in the same style: same decimals, thousands commas, parentheses
for negatives, $ and % signs, footnote marks.

Formats handled (found by scanning all 500 real tables in ``data/docs.jsonl``):

  plain            "1,204"          "187"            "12.5"
  dollar prefix     "$ 5735"         "$1,204.50"
  percent suffix    "12.5%"          "3.4%"
  paren-negative    "(30,463)"       "$(4,614)"       "(60.8)%"   (% may sit
                     either inside or outside the closing paren in the
                     source; we normalise to always writing it inside)
  dup-paren         "-12 ( 12 )"     "$ -27447 ( 27447 )"   "18.9% ( 18.9 % )"
                     FinQA sometimes writes a value, then repeats its own
                     magnitude in parentheses right after it. This is NOT a
                     footnote: the number in parens is numeric and (within
                     rounding) equal to the number before it. A leading '-'
                     outside the parens makes the value negative; several of
                     these (the percent ones) have no leading sign at all and
                     are just a stylistic repeat, so we only negate when a
                     '-' is actually present.
  footnote suffix   "135,696(a)"     a letter (or letters) in parentheses
                     glued directly onto a number with no separating space.
                     Kept as a literal suffix and reproduced unchanged no
                     matter what new value is written -- it is a citation
                     mark, not part of the number.
  dash              "\u2014" (em dash), "\u2013" (en dash), a bare "-", or an
                     empty cell -> treated as blank/zero (``is_dash=True``).
                     Decision: only the value 0 can round-trip back to a
                     dash; writing a nonzero edited value to a dash cell
                     falls back to a plain number, since there is no
                     sensible "dashed" way to show a real quantity.

Known simplification: when a paren-negative value's '%' sat OUTSIDE the
closing paren in the source (e.g. "(60.8)%"), ``format_like`` always writes
it back INSIDE ("(60.8%)"). Both read identically to a person skimming the
page; we do not chase an exact-character reproduction of that one cosmetic
placement.

Known gap: a handful of real cells (~6 of 7,284 numeric cells scanned) use a
number followed by a unit word instead of a symbol, e.g. "5.0 years",
"6 months". These return None rather than risk a looser pattern swallowing
real text labels elsewhere in the table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_DASH_CHARS = {"\u2014", "\u2013", "-", ""}
_NUM = r"\d[\d,]*(?:\.\d+)?"


@dataclass
class CellNumber:
    value: float
    decimals: int          # digits after the decimal point as written
    commas: bool            # thousands separators used
    parens: bool            # negative written as (123)
    prefix: str = ""         # e.g. "$", "$ "
    suffix: str = ""         # e.g. "%", footnote mark "(a)"
    raw: str = ""
    dup_paren: bool = False   # FinQA style "-12 ( 12 )": magnitude repeated in parens
    is_dash: bool = False     # cell was a dash/blank, standing for 0


def _decimals_in(num_text: str) -> int:
    return len(num_text.split(".")[1]) if "." in num_text else 0


def _to_float(num_text: str) -> float:
    return float(num_text.replace(",", ""))


def _strip_dollar(s: str) -> tuple[str, str]:
    """Split a leading '$' (with any following space) off ``s``."""
    m = re.match(r"\$\s*", s)
    return (m.group(0), s[m.end():]) if m else ("", s)


def parse_cell(cell: str) -> Optional[CellNumber]:
    """Parse a table cell into a value plus enough style to write it back.

    Returns None if the cell holds no number (e.g. a row label like "Revenue").
    """
    if cell is None:
        return None
    raw = str(cell)
    s = raw.strip()
    if not s:
        return None

    if s in _DASH_CHARS:
        return CellNumber(0.0, 0, False, False, raw=raw, is_dash=True)

    prefix, rest = _strip_dollar(s)
    rest = rest.strip()

    # dup-paren: a number, optionally repeated inside trailing parens, e.g.
    # "-12 ( 12 )" or "18.9% ( 18.9 % )". Only treated as dup-paren if the
    # two magnitudes actually match -- otherwise this isn't that pattern.
    m = re.fullmatch(rf"(-?)\s*({_NUM})(%?)\s*\(\s*({_NUM})\s*(%?)\s*\)", rest)
    if m:
        sign, num, pct1, num2, pct2 = m.groups()
        if abs(_to_float(num) - _to_float(num2)) < 1e-6:
            value = -_to_float(num) if sign else _to_float(num)
            return CellNumber(value, _decimals_in(num), "," in num, False,
                               prefix=prefix, suffix=(pct1 or pct2), raw=raw, dup_paren=True)

    # footnote glued directly onto a number, no space: "135,696(a)"
    m = re.fullmatch(rf"(-?)\s*({_NUM})(%?)(\([a-zA-Z]+\))", rest)
    if m:
        sign, num, pct, mark = m.groups()
        value = -_to_float(num) if sign else _to_float(num)
        return CellNumber(value, _decimals_in(num), "," in num, False,
                           prefix=prefix, suffix=(pct or "") + mark, raw=raw)

    # parenthesised negative; '%' may sit inside or just outside the ')'
    m = re.fullmatch(rf"\(\s*({_NUM})(%?)\s*\)(%?)", rest)
    if m:
        num, pct_in, pct_out = m.groups()
        return CellNumber(-_to_float(num), _decimals_in(num), "," in num, True,
                           prefix=prefix, suffix=(pct_in or pct_out), raw=raw)

    # plain signed number, optional '%'
    m = re.fullmatch(rf"(-?)\s*({_NUM})(%?)", rest)
    if m:
        sign, num, pct = m.groups()
        value = -_to_float(num) if sign else _to_float(num)
        return CellNumber(value, _decimals_in(num), "," in num, False,
                           prefix=prefix, suffix=pct, raw=raw)

    return None


def _body(value: float, template: CellNumber) -> str:
    mag = abs(value)
    return f"{mag:,.{template.decimals}f}" if template.commas else f"{mag:.{template.decimals}f}"


def format_like(value: float, template: CellNumber) -> str:
    """Write ``value`` in the same style as ``template``."""
    if template.is_dash:
        if value == 0:
            return template.raw
        template = CellNumber(value, 0, False, False)  # no sensible dash for a real quantity

    body = _body(value, template)
    neg = value < 0

    if template.dup_paren:
        return f"{template.prefix}{'-' if neg else ''}{body}{template.suffix} ( {body}{template.suffix} )"

    if template.parens:
        inner = f"{body}{template.suffix}"
        return f"{template.prefix}({inner})" if neg else f"{template.prefix}{inner}"

    return f"{template.prefix}{'-' if neg else ''}{body}{template.suffix}"