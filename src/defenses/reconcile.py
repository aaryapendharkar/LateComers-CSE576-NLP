"""D1 reconciliation defense (Person 3, Gap 1).

Public contract (agreed in the task brief):

    reconcile(page) -> {"flag": bool, "reasons": [str, ...]}

`flag` is True only when a contradiction was detected. Richer diagnostics,
including the three-way outcome below, are available from diagnose(page) and
D1Result.eval_record() for the evaluator.

Outcomes (D1Result.status):
  * "contradiction"  - at least one applicable check failed.
  * "checks_passed"  - at least one check ran and none failed. This is NOT
                       evidence of factual correctness: a consistently edited
                       table (and coordinated prose) passes by construction.
  * "uncheckable"    - no check could be performed (no table, unsupported
                       layout, no supported relationship, unaligned prose).

Two families of checks:
  1. Arithmetic: rows/columns whose LABEL marks them as totals are discovered
     from labels and position first, then their values are checked. Values
     never decide whether a relationship exists or which rows it covers: when
     earlier subtotals sit above a total, label semantics decide between the
     nested reading and the sibling-group reading, and anything unresolved is
     skipped as total_scope_ambiguous (a reported coverage limitation).
  2. Prose: a number in the surrounding text is compared with a table cell
     only when the sentence names exactly one row label (without a scope
     qualifier), the number's clause names exactly one year matching exactly
     one column, and both scales are known. Signs are compared as printed;
     when signs differ and the wording describes a magnitude (loss, used,
     expense, ...) the claim is skipped as sign_semantics_unsupported.
     Currencies must agree when both sides state one; a mismatch or an
     ambiguous pair ($ vs USD) is skipped, never converted.

Rounding rule: a printed value with d decimals may be off by 0.5*10^-d.
A sum of n printed components may therefore differ from a printed total by up
to the sum of all their half-units. Discrepancies within that bound pass.

D1 does not repair, rewrite or re-rank evidence.

OWNER: Person 3 (Vatsal). Team entry points (repo skeleton) are at the end of
this file: reconcile_page(page_text, cfg), parse_markdown_table, sum_check,
table_text_check. They are thin wrappers around reconcile/diagnose.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from decimal import Decimal
from typing import Any, TypedDict

from src.defenses.d1_input import ParsedPage, ParsedTable, page_from_markdown, page_from_record
from src.defenses.d1_numbers import (
    MISSING,
    NUMBER,
    CURRENCY_ALIASES,
    SCALE_WORDS,
    Cell,
    TableScale,
    currency_relation,
    detect_table_currencies,
    detect_table_scale,
    fmt,
    parse_number,
)

D1_VERSION = "0.2.0"

CONTRADICTION = "contradiction"
CHECKS_PASSED = "checks_passed"
UNCHECKABLE = "uncheckable"


@dataclass(frozen=True)
class D1Config:
    check_arithmetic: bool = True
    check_prose: bool = True
    # Off by default: a dash is MISSING. Turning this on must be reported.
    dash_as_zero: bool = False


@dataclass
class Check:
    kind: str  # "arithmetic" | "prose"
    passed: bool
    relationship: str
    cells: list[str]
    expected: str
    observed: str
    discrepancy: str
    tolerance: str
    explanation: str


@dataclass
class Skip:
    kind: str  # "table" | "arithmetic" | "prose"
    code: str
    detail: str


@dataclass
class D1Result:
    config: D1Config
    checks: list[Check] = field(default_factory=list)
    skipped: list[Skip] = field(default_factory=list)
    unaligned_prose_numbers: int = 0
    table_units: dict = field(default_factory=dict)

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    @property
    def status(self) -> str:
        if self.failed:
            return CONTRADICTION
        return CHECKS_PASSED if self.checks else UNCHECKABLE

    def _skip_summary(self) -> str:
        counts: dict[str, int] = {}
        for sk in self.skipped:
            counts[sk.code] = counts.get(sk.code, 0) + 1
        return ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))

    def public(self) -> dict:
        """The agreed output: {"flag": bool, "reasons": [...]}."""
        if self.failed:
            reasons = [f"CONTRADICTION [{c.kind}] {c.explanation}" for c in self.failed]
            if self.skipped:
                reasons.append(f"COVERAGE: {len(self.skipped)} items not checkable ({self._skip_summary()}).")
            return {"flag": True, "reasons": reasons}
        n_ar = sum(c.kind == "arithmetic" for c in self.checks)
        n_pr = sum(c.kind == "prose" for c in self.checks)
        if self.checks:
            not_checked = f" ({self._skip_summary()})" if self.skipped else ""
            return {"flag": False, "reasons": [
                f"NO_CONTRADICTION_FOUND: {n_ar} arithmetic and {n_pr} prose checks passed; "
                f"{len(self.skipped)} items not checkable{not_checked}. "
                "Passing does not establish factual correctness."
            ]}
        codes = sorted({s.code for s in self.skipped}) or ["nothing_to_check"]
        return {"flag": False, "reasons": [f"NOT_CHECKABLE: no check could be performed ({', '.join(codes)})."]}

    def eval_record(self) -> dict:
        """Diagnostics for the evaluator (not part of the public contract)."""
        return {
            "d1_version": D1_VERSION,
            "config": asdict(self.config),
            "status": self.status,
            "flag": bool(self.failed),
            "n_checks": {k: sum(c.kind == k for c in self.checks) for k in ("arithmetic", "prose")},
            "n_failed": {k: sum(c.kind == k for c in self.failed) for k in ("arithmetic", "prose")},
            "n_skipped": len(self.skipped),
            "unaligned_prose_numbers": self.unaligned_prose_numbers,
            "table_units": self.table_units,
            "checks": [asdict(c) for c in self.checks],
            "skipped": [asdict(s) for s in self.skipped],
        }


def reconcile(page: ParsedPage, config: D1Config = D1Config()) -> dict:
    """Public entry point. Takes only the observed page; returns flag + reasons."""
    return diagnose(page, config).public()


def diagnose(page: ParsedPage, config: D1Config = D1Config()) -> D1Result:
    result = D1Result(config=config)
    if page.table is None:
        result.skipped.append(Skip("table", "no_table", "no table was parsed from this page"))
        return result
    view = _TableView.build(page.table, result)
    if view is None:
        return result
    result.table_units = {
        "scale_status": view.scale.status,
        "scale_multiplier": fmt(view.scale.multiplier) if view.scale.multiplier is not None else None,
        "scale_evidence": list(view.scale.evidence),
        "per_share_exception": view.scale.per_share_exception,
        "declared_currencies": sorted(view.declared_currencies),
        "cell_currencies": sorted({c.currency for row in view.cells for c in row[1:] if c.currency}),
    }
    if config.check_arithmetic:
        _row_total_checks(view, config, result)
        _column_total_checks(view, config, result)
    if config.check_prose:
        _prose_checks(view, page.prose, result)
    return result


# --------------------------------------------------------------------------
# Table structure

_TOTAL_RE = re.compile(r"^(sub ?total|total)\b|\btotal$")
_NOT_A_SUM = ("percent", "per share", "average", "return", "ratio", "margin", "as a ")


def norm_label(label: str) -> str:
    s = label.lower()
    s = re.sub(r"\(\s*(?:\d|[a-z])\s*\)|[*†]", " ", s)  # footnote markers like (1), (a)
    s = re.sub(r"[^a-z0-9%]+", " ", s)
    return s.strip()


def is_total_label(label: str) -> bool:
    n = norm_label(label)
    return bool(_TOTAL_RE.search(n)) and "%" not in n and not any(w in n + " " for w in _NOT_A_SUM)


@dataclass
class _TableView:
    table: ParsedTable
    labels: list[str]
    cells: list[list[Cell]]  # cells[r][c] for value columns c >= 1
    scale: TableScale
    declared_currencies: frozenset = frozenset()
    _scope_cache: dict = field(default_factory=dict)

    @staticmethod
    def build(table: ParsedTable, result: D1Result) -> "_TableView | None":
        width = len(table.header)
        if width < 2 or not table.rows:
            result.skipped.append(Skip("table", "unsupported_layout", "table has no value columns or no rows"))
            return None
        ragged = [i for i, row in enumerate(table.rows) if len(row) != width]
        if ragged:
            result.skipped.append(Skip(
                "table", "ragged_table",
                f"rows {ragged} do not have {width} cells like the header; column alignment is "
                "unreliable (likely a parsing error), so no table check is attempted"))
            return None
        cells = [[parse_number(c) for c in row] for row in table.rows]
        if not any(cell.kind == NUMBER for row in cells for cell in row[1:]):
            result.skipped.append(Skip("table", "no_numeric_cells", "no value cell could be parsed as a number"))
            return None
        boundary_labels = [row[0] for row in table.rows if all(not c.strip() for c in row[1:])]
        local_text = [table.title, table.unit_note, *table.header, *boundary_labels]
        return _TableView(table, [row[0] for row in table.rows], cells, detect_table_scale(local_text),
                          detect_table_currencies(local_text))

    def currency_context(self) -> frozenset:
        """Currencies stated anywhere in the table (declarations and cell markers)."""
        cell_curs = {cell.currency for row in self.cells for cell in row[1:] if cell.currency}
        return frozenset(cell_curs) | self.declared_currencies

    @property
    def header(self) -> list[str]:
        return self.table.header

    def is_boundary(self, r: int) -> bool:
        row = self.table.rows[r]
        return all(not c.strip() for c in row[1:]) or row[0].strip().endswith(":")

    def is_total(self, r: int) -> bool:
        return is_total_label(self.labels[r]) and not self.is_boundary(r)

    def block_above(self, t: int) -> list[int]:
        """Hypothesis 1: contiguous non-total rows directly above row t."""
        rows, j = [], t - 1
        while j >= 0 and not self.is_boundary(j) and not self.is_total(j):
            rows.append(j)
            j -= 1
        return rows[::-1]

    def scope(self, t: int) -> tuple[str, list[int], str]:
        """Rows that total row t sums, decided from layout and labels only.

        Returns (kind, rows, how): kind is "contiguous", "nested" or
        "ambiguous" (rows empty). Values are never consulted, so editing a
        number cannot change which relationship is checked.
        """
        if t in self._scope_cache:
            return self._scope_cache[t]
        h1 = self.block_above(t)
        rows, subtotals, j = [], [], t - 1
        while j >= 0 and not self.is_boundary(j):
            rows.append(j)
            if self.is_total(j):
                subtotals.append(j)
                kind, covered, _ = self.scope(j)
                if kind == "ambiguous":
                    out = ("ambiguous", [], f"the scope of earlier subtotal '{self.labels[j]}' is itself unresolved")
                    self._scope_cache[t] = out
                    return out
                j = (covered[0] if covered else j) - 1
            else:
                j -= 1
        h2 = rows[::-1]
        if not subtotals:
            out = ("contiguous", h1, "no earlier subtotal above")
        elif not h1:
            out = ("nested", h2, "the total directly follows a subtotal, so it can only include it")
        else:
            rels = {_label_relation(self.labels[t], self.labels[s]) for s in subtotals}
            names = [self.labels[s] for s in subtotals[::-1]]
            if rels == {"nested"}:
                out = ("nested", h2, f"label '{self.labels[t]}' is broader than subtotal(s) {names}")
            elif rels == {"sibling"} and len(h1) >= 2:
                out = ("contiguous", h1, f"label '{self.labels[t]}' shares no head word with subtotal(s) {names}")
            else:
                out = ("ambiguous", [], f"labels do not show whether '{self.labels[t]}' includes subtotal(s) "
                                        f"{names} (nested) or only the {len(h1)} row(s) after them (sibling group)")
        self._scope_cache[t] = out
        return out


_CORE_STOP = {"total", "totals", "subtotal", "sub", "grand", "and", "of", "the"}


def _label_core(label: str) -> frozenset:
    tokens = [w for w in norm_label(label).split() if w not in _CORE_STOP]
    return frozenset(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in tokens)


def _label_relation(total_label: str, subtotal_label: str) -> str:
    """'nested' when the total's words are contained in the subtotal's ('assets' in 'current assets'),
    'sibling' when they share no word ('services' vs 'products'), else 'ambiguous'."""
    t, s = _label_core(total_label), _label_core(subtotal_label)
    if not t or not s or (t <= s and t != s):
        return "nested"
    if t.isdisjoint(s):
        return "sibling"
    return "ambiguous"


# --------------------------------------------------------------------------
# Arithmetic checks


def _sum_outcome(total: Cell, comps: list[Cell], cfg: D1Config):
    """Return ("check", sum, discrepancy, tolerance, passed) or ("skip", code, detail)."""
    if total.kind != NUMBER:
        return ("skip", "total_not_numeric", f"total cell '{total.raw}' is {total.kind}")
    values, tol, sigs = [], total.half_unit, {total.unit_signature}
    for c in comps:
        if c.kind == MISSING:
            if cfg.dash_as_zero and c.is_dash:
                values.append(Decimal(0))
                continue
            return ("skip", "missing_value", f"component cell '{c.raw}' is missing; not treated as zero")
        if c.kind != NUMBER:
            return ("skip", "unparseable_value", f"component cell '{c.raw}' is not a number")
        values.append(c.value)
        tol += c.half_unit
        sigs.add(c.unit_signature)
    if len(sigs) > 1:
        return ("skip", "mixed_units", "cells mix percentages/scale words")
    curs = sorted({c.currency for c in [total, *comps] if c.kind == NUMBER and c.currency})
    relation = currency_relation(curs)
    if relation != "same":
        return ("skip", f"currency_{relation}",
                f"cells are marked with different currencies {curs}; no conversion is attempted")
    s = sum(values, Decimal(0))
    disc = abs(s - total.value)
    return ("check", s, disc, tol, disc <= tol)


def _row_total_checks(view: _TableView, cfg: D1Config, result: D1Result) -> None:
    for t, label in enumerate(view.labels):
        if norm_label(label).startswith("net ") and not view.is_boundary(t):
            result.skipped.append(Skip("arithmetic", "net_relationship_not_checked",
                                       f"row '{label}' looks like a difference; sign conventions are not inferred"))
        if not view.is_total(t):
            continue
        kind, rows, how = view.scope(t)
        if kind == "ambiguous":
            result.skipped.append(Skip("arithmetic", "total_scope_ambiguous",
                                       f"total row '{label}' not checked: {how}"))
            continue
        if len(rows) < 2:
            result.skipped.append(Skip("arithmetic", "no_component_rows",
                                       f"total row '{label}' has fewer than two component rows ({how})"))
            continue
        if any(norm_label(view.labels[r]).startswith("less") or "net of" in norm_label(view.labels[r]) for r in rows):
            result.skipped.append(Skip("arithmetic", "sign_convention_ambiguous",
                                       f"components of '{label}' include a 'less'/'net of' row"))
            continue
        name = ("contiguous rows above" if kind == "contiguous"
                else "nested: earlier subtotals counted once, their components excluded")
        outcomes = {c: _sum_outcome(view.cells[t][c], [view.cells[r][c] for r in rows], cfg)
                    for c in range(1, len(view.header))}
        comp_labels = [view.labels[r] for r in rows]
        for c, o in outcomes.items():
            col = view.header[c] or f"col{c}"
            if o[0] == "skip":
                result.skipped.append(Skip("arithmetic", o[1], f"'{label}' in column '{col}': {o[2]}"))
                continue
            _, s, disc, tol, ok = o
            rel = f"row '{label}' = sum of rows {comp_labels} in column '{col}' [{name}]"
            verdict = "within" if ok else "exceeds"
            result.checks.append(Check(
                kind="arithmetic", passed=ok, relationship=rel,
                cells=[f"{view.labels[r]}|{col}={view.table.rows[r][c]}" for r in rows]
                + [f"{label}|{col}={view.table.rows[t][c]}"],
                expected=fmt(s), observed=fmt(view.cells[t][c].value), discrepancy=fmt(disc), tolerance=fmt(tol),
                explanation=(f"{rel}: components sum to {fmt(s)}; the table shows {view.table.rows[t][c]!r}; "
                             f"discrepancy {fmt(disc)} {verdict} rounding tolerance {fmt(tol)}."),
            ))


def _column_total_checks(view: _TableView, cfg: D1Config, result: D1Result) -> None:
    header = view.header
    for tc in range(1, len(header)):
        if not is_total_label(header[tc]):
            continue
        comps = []
        j = tc - 1
        while j >= 1 and not is_total_label(header[j]):
            comps.append(j)
            j -= 1
        comps.reverse()
        if len(comps) < 2:
            result.skipped.append(Skip("arithmetic", "no_component_columns",
                                       f"total column '{header[tc]}' has fewer than two component columns"))
            continue
        for r, label in enumerate(view.labels):
            if view.is_boundary(r):
                continue
            o = _sum_outcome(view.cells[r][tc], [view.cells[r][c] for c in comps], cfg)
            if o[0] == "skip":
                result.skipped.append(Skip("arithmetic", o[1], f"column '{header[tc]}' in row '{label}': {o[2]}"))
                continue
            _, s, disc, tol, ok = o
            rel = f"column '{header[tc]}' = sum of columns {[header[c] for c in comps]} in row '{label}'"
            verdict = "within" if ok else "exceeds"
            result.checks.append(Check(
                kind="arithmetic", passed=ok, relationship=rel,
                cells=[f"{label}|{header[c]}={view.table.rows[r][c]}" for c in comps + [tc]],
                expected=fmt(s), observed=fmt(view.cells[r][tc].value), discrepancy=fmt(disc), tolerance=fmt(tol),
                explanation=(f"{rel}: components sum to {fmt(s)}; the table shows {view.table.rows[r][tc]!r}; "
                             f"discrepancy {fmt(disc)} {verdict} rounding tolerance {fmt(tol)}."),
            ))


# --------------------------------------------------------------------------
# Prose checks

_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_PROSE_NUM_RE = re.compile(
    r"(?<![\w.,])(?P<neg1>[-−–]\s*)?(?P<cur>(?:US\$|USD|EUR|GBP|JPY|[$€£¥])\s*)?(?P<neg2>[-−–]\s*)?"
    r"(?P<open>\(\s*)?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?P<close>\s*\))?"
    r"(?:\s*(?P<pct>%|percent\b))?(?:\s*(?P<scale>thousand|million|billion)s?\b)?"
    r"(?:\s+(?P<curword>u\.\s?s\.\s?dollars?|us dollars?|dollars?|euros?|pounds sterling|yen)\b)?",
    re.IGNORECASE,
)
_PROSE_CURRENCY_WORDS = {"dollar": "$", "euro": "EUR", "pounds sterling": "GBP", "yen": "JPY"}
# When the table and the text disagree in sign, these words suggest the text
# may state a magnitude ("a loss of $150 million"), so the sign is not compared.
_MAGNITUDE_WORDING = re.compile(
    r"\b(?:loss(?:es)?|deficits?|outflows?|used|uses|using|paid|pays?|payments?|repurchase[sd]?|"
    r"expenses?|charges?|costs?|impairments?|write-?(?:downs?|offs?)|deductions?|withdrawals?|"
    r"negative|unfavorable|adverse|dividends?)\b",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_SEGMENT_SEP = re.compile(
    r";|,\s|\bcompared (?:to|with)\b|\bversus\b|\bvs\.?|\bfrom\b|\bto\b|\band\b|\bwhile\b|\bwhereas\b",
    re.IGNORECASE,
)
# Numbers near these words describe changes or bounds, not the level in a cell.
_CHANGE_OR_BOUND = re.compile(
    r"\b(?:increase[sd]?|decrease[sd]?|grew|grow(?:th|s)?|rose|rise[sn]?|fell|fall(?:en|s)?|"
    r"decline[sd]?|change[sd]?|higher|lower|up|down|by|improve(?:d|ment|s)?|reduc(?:ed|tion|es)|"
    r"more than|less than|over|under|at least|nearly|almost|exceed(?:ed|s)?|in excess of)\b",
    re.IGNORECASE,
)
_ALLOWED_PRECEDERS = {"the", "our", "its", "their", "consolidated", "company's", "companys"}
# "revenue from services", "revenue of segment A": the label is narrowed after it.
_SCOPE_FOLLOWERS = re.compile(
    r"^\s*(?:from|of|for|attributable|related|associated|generated|at|within|excluding|including)\b"
)


@dataclass
class _Mention:
    cell: Cell
    start: int
    end: int
    text: str


def _prose_numbers(sentence: str) -> tuple[list[_Mention], list[str]]:
    amounts, years = [], []
    for m in _PROSE_NUM_RE.finditer(sentence):
        num = m.group("num")
        if not (m.group("cur") or m.group("pct") or m.group("scale")) and re.fullmatch(r"(?:19|20)\d{2}", num):
            years.append(num)
            continue
        negative = bool(m.group("neg1") or m.group("neg2") or (m.group("open") and m.group("close")))
        value = Decimal(num.replace(",", ""))
        cell = Cell(
            raw=m.group(0).strip(), kind=NUMBER, value=-value if negative else value,
            decimals=len(num.split(".")[1]) if "." in num else 0,
            percent=bool(m.group("pct")),
            scale_word=(m.group("scale") or "").lower() or None,
            currency=_prose_currency(m.group("cur"), m.group("curword")),
        )
        amounts.append(_Mention(cell, m.start(), m.end(), m.group(0).strip()))
    return amounts, years


def _prose_currency(symbol: str | None, word: str | None) -> str | None:
    found = set()
    if symbol:
        found.add(CURRENCY_ALIASES[symbol.strip().lower()])
    if word:
        w = re.sub(r"\s+", " ", word.lower())
        if re.match(r"u\.\s?s\.|us ", w):
            found.add("USD")
        else:
            found.add(_PROSE_CURRENCY_WORDS[w.rstrip("s") if w.startswith(("dollar", "euro")) else w])
    if len(found) > 1:
        return "conflicting:" + "+".join(sorted(found))
    return next(iter(found), None)


def _segments(sentence: str) -> list[tuple[int, int]]:
    cuts = [0]
    for m in _SEGMENT_SEP.finditer(sentence):
        cuts += [m.start(), m.end()]
    cuts.append(len(sentence))
    return [(cuts[i], cuts[i + 1]) for i in range(0, len(cuts), 2)]


def _label_pattern(label: str) -> re.Pattern | None:
    tokens = norm_label(label).split()
    if not tokens:
        return None
    return re.compile(r"\b" + r"\W+".join(re.escape(t) for t in tokens) + r"\b")


def _prose_checks(view: _TableView, prose: str, result: D1Result) -> None:
    if not prose.strip():
        return
    year_cols: dict[str, list[int]] = {}
    for c in range(1, len(view.header)):
        ys = set(_YEAR_RE.findall(view.header[c]))
        if len(ys) == 1:
            year_cols.setdefault(ys.pop(), []).append(c)
    patterns = [(r, _label_pattern(l)) for r, l in enumerate(view.labels) if not view.is_boundary(r)]

    def skip(code, detail):
        result.skipped.append(Skip("prose", code, detail))

    for sentence in _SENTENCE_SPLIT.split(prose):
        amounts, sentence_years = _prose_numbers(sentence)
        if not amounts:
            continue
        low = sentence.lower()
        matches = [(r, m.start(), m.end()) for r, p in patterns if p for m in p.finditer(low)]
        # Longest match wins: "total revenue" hides the "revenue" inside it.
        matches = [m for m in matches
                   if not any(o[1] <= m[1] and m[2] <= o[2] and (o[2] - o[1]) > (m[2] - m[1]) for o in matches)]
        rows = sorted({m[0] for m in matches})
        if not rows:
            result.unaligned_prose_numbers += len(amounts)
            continue
        quoted = sentence.strip()
        if len(rows) > 1:
            skip("ambiguous_metric", f"sentence names several table rows {[view.labels[r] for r in rows]}: {quoted!r}")
            continue
        r = rows[0]
        label = view.labels[r]
        qualifiers = []
        for _, start, end in matches:
            before = low[:start].rstrip()
            if before and before[-1].isalnum():
                word = re.findall(r"[a-z0-9']+$", before)[0]
                if word not in _ALLOWED_PRECEDERS:
                    qualifiers.append(f"'{word} {norm_label(label)}'")
            follower = _SCOPE_FOLLOWERS.match(low[end:])
            if follower:
                qualifiers.append(f"'{norm_label(label)} {follower.group(0).strip()} ...'")
        if qualifiers:
            skip("scope_qualifier", f"{qualifiers[0]} may be a different metric/scope "
                                    f"than row '{label}': {quoted!r}")
            continue
        segs = _segments(sentence)
        for a in amounts:
            s0, s1 = next((s, e) for s, e in segs if s <= a.start < e)
            seg = sentence[s0:s1]
            where = f"{a.text!r} in {quoted!r}"
            if _CHANGE_OR_BOUND.search(seg):
                skip("change_or_bound_language", f"{where}: clause describes a change or a bound")
                continue
            if sum(s0 <= b.start < s1 for b in amounts) > 1:
                skip("multiple_amounts_in_clause", where)
                continue
            seg_years = set(_YEAR_RE.findall(seg))
            if not seg_years and len(set(sentence_years)) == 1 and len(amounts) == 1:
                seg_years = set(sentence_years)
            if len(seg_years) != 1:
                skip("no_period" if not seg_years else "ambiguous_period", where)
                continue
            year = seg_years.pop()
            if year not in year_cols:
                skip("period_not_in_table", f"{where}: year {year} is not a table column")
                continue
            if len(year_cols[year]) > 1:
                skip("ambiguous_period_columns", f"{where}: several columns refer to {year}")
                continue
            c = year_cols[year][0]
            _compare_claim(view, r, c, a, sentence, result)


def _compare_claim(view: _TableView, r: int, c: int, a: _Mention, sentence: str, result: D1Result) -> None:
    quoted = sentence.strip()
    label, col, raw = view.labels[r], view.header[c], view.table.rows[r][c]
    cell = view.cells[r][c]
    where = f"{a.text!r} vs cell [{label!r}, {col!r}]={raw!r}"

    def skip(code, detail):
        result.skipped.append(Skip("prose", code, f"{where}: {detail}"))

    if cell.kind != NUMBER:
        return skip("cell_not_numeric", f"cell is {cell.kind}")
    if a.cell.percent != cell.percent:
        return skip("unit_kind_mismatch", "one value is a percentage and the other is not")
    if a.cell.percent:
        pm = cm = Decimal(1)
        unit = "percentage points"
    else:
        if not a.cell.scale_word:
            return skip("prose_scale_unstated", "prose amount has no thousand/million/billion")
        pm = SCALE_WORDS[a.cell.scale_word]
        if cell.scale_word:
            cm = SCALE_WORDS[cell.scale_word]
        elif view.scale.status == "ambiguous":
            return skip("table_scale_ambiguous", f"conflicting unit declarations {list(view.scale.evidence)}")
        elif view.scale.multiplier is None:
            return skip("table_scale_unknown", "the table declares no unit (e.g. 'in millions')")
        elif view.scale.per_share_exception and "per share" in norm_label(label):
            return skip("per_share_scale", "table unit excludes per-share rows")
        else:
            cm = view.scale.multiplier
        unit = "absolute units"
    currency_note = ""
    if not a.cell.percent:
        prose_cur = a.cell.currency
        table_curs = {cell.currency} if cell.currency else set(view.currency_context())
        if prose_cur and prose_cur.startswith("conflicting:"):
            return skip("currency_ambiguous", f"the text marks this amount with several currencies ({prose_cur})")
        if prose_cur and table_curs:
            relation = currency_relation({prose_cur, *table_curs})
            if relation != "same":
                return skip(f"currency_{relation}", f"text currency {prose_cur} vs table currency "
                                                    f"{sorted(table_curs)}; no conversion is attempted")
        elif prose_cur or table_curs:
            stated = f"text ({prose_cur})" if prose_cur else f"table ({sorted(table_curs)})"
            currency_note = f" Currency is stated only in the {stated}."
    pv, cv = a.cell.value * pm, cell.value * cm
    if pv * cv < 0 and (_MAGNITUDE_WORDING.search(sentence) or _MAGNITUDE_WORDING.search(label)):
        return skip("sign_semantics_unsupported",
                    "signs differ, and the wording (e.g. loss/used/expense) may state a magnitude; "
                    "D1 does not infer sign conventions")
    tol = a.cell.half_unit * pm + cell.half_unit * cm
    disc = abs(pv - cv)
    ok = disc <= tol
    rel = f"prose claim for row '{label}', column '{col}'"
    result.checks.append(Check(
        kind="prose", passed=ok, relationship=rel, cells=[f"{label}|{col}={raw}", f"prose: {quoted}"],
        expected=fmt(pv), observed=fmt(cv), discrepancy=fmt(disc), tolerance=fmt(tol),
        explanation=(f"{rel}: text {a.text!r} = {fmt(pv)}; cell {raw!r} with table scale = {fmt(cv)} "
                     f"({unit}, signs as printed); discrepancy {fmt(disc)} {'within' if ok else 'exceeds'} "
                     f"tolerance {fmt(tol)}.{currency_note} Sentence: {quoted!r}"),
    ))


# --------------------------------------------------------------------------
# Team entry points (repo skeleton signatures). Thin wrappers; same rules.

class D1Output(TypedDict):
    """The public result, {"flag", "reasons"} (the skeleton's D1Result TypedDict)."""

    flag: bool
    reasons: list[str]


def config_from_dict(cfg: dict | None) -> D1Config:
    """D1Config from the `reconcile:` section of configs/default.yaml (or the full config).

    Unknown keys are rejected so that a setting D1 does not implement is never
    silently ignored.
    """
    if not cfg:
        return D1Config()
    section = cfg.get("reconcile", cfg) if "reconcile" in cfg else cfg
    known = {f.name for f in fields(D1Config)}
    unknown = set(section) - known
    if unknown:
        raise ValueError(f"unsupported reconcile settings {sorted(unknown)}; D1 accepts {sorted(known)}")
    return D1Config(**section)


def parse_markdown_table(page_text: str) -> dict[str, Any]:
    """First markdown table in the page text (A6 table dict) plus the remaining text."""
    page = page_from_markdown(page_text)
    t = page.table
    table = None if t is None else {"title": t.title, "unit_note": t.unit_note,
                                    "header": list(t.header), "rows": [list(r) for r in t.rows]}
    return {"table": table, "text": page.prose, "notes": list(page.notes)}


def sum_check(table: dict[str, Any]) -> list[str]:
    """Arithmetic checks only on an A6 table; one reason per contradiction.

    The skeleton's rel_tol/abs_tol parameters are not offered: D1 uses the
    printed-precision rounding bound (docs/person3/D1_DESIGN.md), and a fixed
    absolute tolerance of 1.0 would hide edits on tables printed in billions.
    """
    page = page_from_record({"table": table}, input_kind="unspecified")
    result = diagnose(page, D1Config(check_arithmetic=True, check_prose=False))
    return [f"CONTRADICTION [{c.kind}] {c.explanation}" for c in result.failed]


def table_text_check(table: dict[str, Any], pre_text: str, post_text: str) -> list[str]:
    """Prose-vs-table checks only; one reason per contradiction."""
    page = page_from_record({"table": table, "pre_text": pre_text, "post_text": post_text},
                            input_kind="unspecified")
    result = diagnose(page, D1Config(check_arithmetic=False, check_prose=True))
    return [f"CONTRADICTION [{c.kind}] {c.explanation}" for c in result.failed]


def reconcile_page(page_text: str, cfg: dict | None = None) -> D1Output:
    """Run D1 on one page's parsed text -> {"flag": bool, "reasons": [...]}."""
    return reconcile(page_from_markdown(page_text), config_from_dict(cfg))
