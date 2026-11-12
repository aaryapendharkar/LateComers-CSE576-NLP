"""Numeric normalization for the D1 reconciliation defense (Person 3).

Rules (see docs/person3/D1_DESIGN.md for the reasoning):

* Thousands separators: commas are accepted only in valid 3-digit groups
  ("1,204", "12,345.6"). "1,20" is rejected as unparseable rather than guessed.
* Decimal precision: the number of digits after the decimal point is kept so
  rounding tolerances can be derived from what was actually printed.
* Currency markers ($, US$, €, £, ¥ and the codes USD/EUR/GBP/JPY) do not
  change the value, but their identity is kept on the Cell. Different
  currencies are never treated as equivalent and nothing is converted; a bare
  "$" and "USD" (or "¥" and "JPY") are reported as ambiguous, not equal.
* Parentheses mean negative: "(1,200)", "$ (150)", "( 75 )". A leading minus
  sign also means negative. Both together ("(-5)") is rejected as ambiguous.
* Percentages keep their percent-point value (12.4% -> 12.4, percent=True).
* Scale words inside a cell ("1.2 billion") are recorded separately; they are
  never silently merged with a table-level unit note.
* Missing markers ("", "-", "—", "n/a", ...) are MISSING, never zero.
* Anything else (text, merged cells, footnote digits) is TEXT (unparseable).

Values are Decimal so that sums are exact and rounding is explicit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

NUMBER = "number"
MISSING = "missing"
TEXT = "text"

# Dash-like tokens are kept distinct from blank cells because some reports use a
# dash to mean zero; D1 only treats them as zero under an explicit config flag.
DASH_TOKENS = {"-", "—", "–", "−", "--"}
MISSING_TOKENS = {"", "n/a", "na", "nm", "n.m.", "none"} | DASH_TOKENS

SCALE_WORDS = {
    "thousand": Decimal(10) ** 3,
    "million": Decimal(10) ** 6,
    "billion": Decimal(10) ** 9,
}

_NUM_RE = re.compile(r"^(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")
_LETTER_FOOTNOTE_RE = re.compile(r"(?:\s*\([a-z]\)|\s*\*+|\s*†)+$")
_SCALE_SUFFIX_RE = re.compile(r"(thousand|million|billion)s?$")


@dataclass(frozen=True)
class Cell:
    """A normalized table cell or prose number."""

    raw: str
    kind: str  # NUMBER, MISSING or TEXT
    value: Decimal | None = None
    decimals: int = 0
    percent: bool = False
    scale_word: str | None = None  # e.g. "million" when written inside the cell
    is_dash: bool = False
    currency: str | None = None  # canonical identity, see CURRENCY_ALIASES

    @property
    def half_unit(self) -> Decimal:
        """Largest rounding error implied by the printed precision."""
        return Decimal(5) * Decimal(10) ** (-(self.decimals + 1))

    @property
    def unit_signature(self) -> tuple[bool, str | None]:
        return (self.percent, self.scale_word)


# Canonical identities. "$" is kept distinct from "USD": a bare dollar sign may
# denote another dollar currency, so the pair is ambiguous rather than equal.
CURRENCY_ALIASES = {
    "$": "$", "us$": "USD", "usd": "USD",
    "€": "EUR", "eur": "EUR",
    "£": "GBP", "gbp": "GBP",
    "¥": "¥", "jpy": "JPY",
}
_AMBIGUOUS_CURRENCY_GROUPS = (frozenset({"$", "USD"}), frozenset({"¥", "JPY"}))
_CUR_PREFIX_RE = re.compile(r"^(us\$|usd|eur|gbp|jpy|[$€£¥])")
_CUR_SUFFIX_RE = re.compile(r"(usd|eur|gbp|jpy)$")


def currency_relation(currencies) -> str:
    """'same', 'ambiguous' or 'mismatch' for a collection of canonical currencies (None ignored)."""
    found = frozenset(c for c in currencies if c)
    if len(found) <= 1:
        return "same"
    if any(found <= g for g in _AMBIGUOUS_CURRENCY_GROUPS):
        return "ambiguous"
    return "mismatch"


def parse_number(raw: str) -> Cell:
    """Normalize one table cell / number string. Never raises."""
    if raw is None:
        return Cell(raw="", kind=MISSING)
    text = str(raw).strip()
    lowered = text.lower()
    if lowered in MISSING_TOKENS:
        return Cell(raw=text, kind=MISSING, is_dash=lowered in DASH_TOKENS)

    s = _LETTER_FOOTNOTE_RE.sub("", lowered)
    s = re.sub(r"\s+", "", s)

    percent = False
    if s.endswith("%"):
        percent, s = True, s[:-1]

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
    if s.endswith("%") and not percent:  # "(12.4%)"
        percent, s = True, s[:-1]

    currencies: list[str] = []

    def take_currency(s: str) -> str:
        m = _CUR_PREFIX_RE.match(s)
        if m:
            currencies.append(CURRENCY_ALIASES[m.group(1)])
            return s[m.end():]
        return s

    s = take_currency(s)
    if s.startswith("(") and s.endswith(")"):  # "$(150)"
        if negative:
            return Cell(raw=text, kind=TEXT)
        negative, s = True, s[1:-1]

    if s[:1] in {"-", "−", "–"}:
        if negative:
            return Cell(raw=text, kind=TEXT)
        negative, s = True, s[1:]
    s = take_currency(s)
    m = _CUR_SUFFIX_RE.search(s)
    if m:
        currencies.append(CURRENCY_ALIASES[m.group(1)])
        s = s[: m.start()]
    if len(set(currencies)) > 1:
        return Cell(raw=text, kind=TEXT)

    scale_word = None
    m = _SCALE_SUFFIX_RE.search(s)
    if m:
        scale_word, s = m.group(1), s[: m.start()]

    if not _NUM_RE.match(s):
        return Cell(raw=text, kind=TEXT)

    value = Decimal(s.replace(",", ""))
    decimals = len(s.split(".")[1]) if "." in s else 0
    return Cell(
        raw=text,
        kind=NUMBER,
        value=-value if negative else value,
        decimals=decimals,
        percent=percent,
        scale_word=scale_word,
        currency=currencies[0] if currencies else None,
    )


_UNIT_RE = re.compile(
    r"\b(?:in|dollars in|amounts in|\$ in)\s+(thousands|millions|billions)\b"
)
_UNIT_SHORT_RE = re.compile(r"\(\s*\$?\s*(000s|000)\s*\)")


@dataclass(frozen=True)
class TableScale:
    """Scale declared for a table. multiplier is None when unknown/ambiguous."""

    multiplier: Decimal | None
    status: str  # "declared", "absent" or "ambiguous"
    evidence: tuple[str, ...] = ()
    per_share_exception: bool = False


def detect_table_scale(texts: list[str]) -> TableScale:
    """Find the unit declaration (e.g. "in millions") in table-local text only.

    `texts` should be the table title, unit note, header cells, and labels of
    blank separator rows -- not the surrounding prose, which may mention other
    scales. Two different declared scales make the scale ambiguous.
    """
    found: dict[str, Decimal] = {}
    evidence: list[str] = []
    per_share = False
    for t in texts:
        if not t:
            continue
        low = t.lower()
        for m in _UNIT_RE.finditer(low):
            word = m.group(1).rstrip("s")
            found[word] = SCALE_WORDS[word]
            evidence.append(t.strip())
        if _UNIT_SHORT_RE.search(low):
            found["thousand"] = SCALE_WORDS["thousand"]
            evidence.append(t.strip())
        if "except per share" in low or "except per-share" in low:
            per_share = True
    if not found:
        return TableScale(None, "absent")
    if len(found) > 1:
        return TableScale(None, "ambiguous", tuple(evidence), per_share)
    return TableScale(next(iter(found.values())), "declared", tuple(evidence), per_share)


# Order matters: specific forms are removed before the generic "dollars".
_TABLE_CURRENCY_PATTERNS = (
    (re.compile(r"\bu\.\s?s\.\s?dollars?\b|\bus dollars?\b|\busd\b|\bus\$"), "USD"),
    (re.compile(r"\beuros?\b|\beur\b|€"), "EUR"),
    (re.compile(r"\bpounds? sterling\b|\bgbp\b|£"), "GBP"),
    (re.compile(r"\bjapanese yen\b|\byen\b|\bjpy\b"), "JPY"),
    (re.compile(r"¥"), "¥"),
    (re.compile(r"\bdollars?\b|\$"), "$"),
)


def detect_table_currencies(texts: list[str]) -> frozenset[str]:
    """Currencies declared in table-local text (title, unit note, header, separator labels)."""
    found = set()
    for t in texts:
        low = (t or "").lower()
        for pattern, cur in _TABLE_CURRENCY_PATTERNS:
            if pattern.search(low):
                found.add(cur)
                low = pattern.sub(" ", low)
    return frozenset(found)


def fmt(d: Decimal | None) -> str:
    """Readable rendering of a Decimal for explanations."""
    if d is None:
        return "None"
    text = format(d.normalize(), ",f")
    return "0" if text in {"-0", ""} else text
