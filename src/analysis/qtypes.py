"""Rule-based question-type proposals (Person 3).

Labels (agreed): lookup, comparison, arithmetic, trend. No fifth label is ever
emitted; uncertainty goes into `needs_review` and `review_notes` instead.

Evidence used
  * FinQA (program available): operations in the reasoning program decide
    comparison (greater) and arithmetic (add, subtract, multiply, divide, exp,
    table_*). Question text decides trend.
  * ChartQA / no program: keyword cues in the question text decide all labels.

Precedence when several rules fire: trend > comparison > arithmetic > lookup.
  * trend before arithmetic: temporal change is almost always *computed* with
    subtract/divide, so arithmetic first would leave trend nearly empty.
  * comparison before arithmetic: FinQA comparison programs often contain
    arithmetic sub-steps before greater().
  * trend before comparison: "did X increase from 2018 to 2019?" is a temporal
    question; it is still flagged for review because both apply.
Trend requires a change cue AND evidence of two periods (two years, "from..to",
"between..and", "year over year", CAGR), so "what was the increase in 2019"
with one period is not trend. The word "trend" is not a cue inside "trend rate"
(0.1.1): "health care cost trend rate" is a row label, not a temporal question.

These are PROPOSALS. They must be reviewed by a person before being written to
the shared examples.jsonl; this module never edits shared files.

OWNER: Person 3 (Vatsal). Team entry points (repo skeleton): `label_finqa`,
`label_chartqa`. `scripts/label_qtypes.py` writes their output to
data/labels/qtypes.jsonl, which `src/common/io.load_examples()` overlays.
`scripts/qtype_review_sheet.py` builds the review sheet for the 30-label check.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

QTYPES_VERSION = "0.1.1"
LABELS = ("lookup", "comparison", "arithmetic", "trend")
PRECEDENCE = ("trend", "comparison", "arithmetic", "lookup")

ARITHMETIC_OPS = {"add", "subtract", "multiply", "divide", "exp",
                  "table_sum", "table_average", "table_max", "table_min"}
COMPARISON_OPS = {"greater"}

_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_TREND_CUE = re.compile(
    r"\b(?:change[sd]?|growth|grow|grew|increase[sd]?|decrease[sd]?|decline[sd]?|rise|rose|"
    r"fell|fall|drop(?:ped)?|trend(?!\s+rates?\b)|cagr)\b", re.I)
_TWO_PERIODS = re.compile(
    r"\bfrom\b.+\bto\b|\bbetween\b.+\band\b|year[- ]over[- ]year|\bcagr\b|\bover the (?:period|years)\b", re.I)
_COMPARISON_CUE = re.compile(
    r"\b(?:greater|higher|lower|larger|smaller|more than|less than|exceed(?:s|ed)?|versus|vs\.?|"
    r"highest|lowest|largest|smallest|maximum|minimum|most|least|tallest|shortest)\b", re.I)
_ARITHMETIC_CUE = re.compile(
    r"\b(?:sum|total of|difference|average|mean|ratio|percentage|percent|portion|proportion|"
    r"how (?:many|much) more|times|combined|median)\b", re.I)
_LOOKUP_CUE = re.compile(r"^\s*(?:what (?:is|was|were|are)|how (?:many|much))\b", re.I)


@dataclass
class QTypeProposal:
    qid: str
    proposed_question_type: str
    rule: str
    also_matched: list[str] = field(default_factory=list)
    needs_review: bool = False
    review_notes: list[str] = field(default_factory=list)
    labeler_version: str = QTYPES_VERSION


def program_ops(program: str | None) -> list[str]:
    return re.findall(r"([a-z_]+)\s*\(", (program or "").lower())


def propose(qid: str, question: str, program: str | None = None) -> QTypeProposal:
    fired: dict[str, str] = {}
    notes: list[str] = []
    q = question or ""
    years = set(_YEAR.findall(q))
    if _TREND_CUE.search(q) and (len(years) >= 2 or _TWO_PERIODS.search(q)):
        fired["trend"] = "change cue + two periods in question"

    ops = program_ops(program)
    if program:
        if COMPARISON_OPS & set(ops):
            fired["comparison"] = "program uses greater()"
        if ARITHMETIC_OPS & set(ops):
            fired["arithmetic"] = f"program uses {sorted(ARITHMETIC_OPS & set(ops))}"
        if _COMPARISON_CUE.search(q) and "comparison" not in fired:
            notes.append("question wording is comparative but the program has no greater()")
        if len(ops) == 1 and re.search(r"const_\d+", program or ""):
            notes.append("single operation with a constant: may be a unit conversion of a looked-up value")
    else:
        if _COMPARISON_CUE.search(q):
            fired["comparison"] = "comparative/superlative wording"
        if _ARITHMETIC_CUE.search(q):
            fired["arithmetic"] = "arithmetic wording"
        if "comparison" in fired and _LOOKUP_CUE.search(q):
            notes.append("superlative/comparative selection followed by a value read-out (comparison vs lookup)")

    if not fired:
        if program and ops:
            notes.append(f"program operations {ops} matched no rule")
        elif not program and not _LOOKUP_CUE.search(q):
            notes.append("no rule fired and no explicit lookup wording; defaulted to lookup")
        fired["lookup"] = "no comparison/arithmetic/trend evidence"

    label = next(l for l in PRECEDENCE if l in fired)
    also = [l for l in PRECEDENCE if l in fired and l != label]
    if label == "trend" and "comparison" in also:
        notes.append("both trend and comparison apply; trend chosen by precedence")
    return QTypeProposal(qid=qid, proposed_question_type=label, rule=fired[label], also_matched=also,
                         needs_review=bool(notes), review_notes=notes)


def as_record(p: QTypeProposal, source: str | None = None) -> dict:
    rec = asdict(p)
    rec["source"] = source
    return rec


def label_finqa(question: str, program: str | None) -> str:
    """Team interface: the proposed label for a FinQA question (program decides ops)."""
    return propose("", question, program).proposed_question_type


def label_chartqa(question: str) -> str:
    """Team interface: the proposed label for a ChartQA question (text cues only)."""
    return propose("", question, None).proposed_question_type
