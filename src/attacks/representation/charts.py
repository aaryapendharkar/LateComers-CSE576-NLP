"""Gap 2 chart attacks: change the asked-about value by a visible but plausible amount.

OWNER: Person 4 (Aaron). Brief task 5. target_answer = the new value.

Conditions: propagate_chart (chart + note + text layer all re-rendered from the
edited CSV), text_only_chart (chart + note image clean, text layer poisoned),
image_only_chart. Edit format: a cell edit (src/common/edits.py), grid row 0 =
header. The SAME edit (``chart_edit``) is used for every condition of a
question, so conditions are comparable.

Selection (``select_chartqa_questions``), from ChartQA test_human.json:
  * simple chart: 1-3 numeric series (2-4 CSV columns), 2-12 rows, no empty/nan cells
  * the gold answer equals exactly ONE value cell in the CSV
  * the question survives re-rendering: no colors / positions / pie / legend
    references, no counting, no arithmetic, no ordinals (an edit could re-rank)
  * a plausible edit exists (see ``chart_edit``)
Charts are re-rendered from the CSV, so they replace the clean page in place
(``run_query(swap={clean: poison})``), never added as new pages.
"""

from __future__ import annotations

import csv
import json
import math
import random
import re
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from ...common.edits import apply_edit
from ...common.schemas import ATTACK_LAYERS, Attack, Doc, Example, attack_id, clean_page_id, \
    layer_answers, poison_page_id

CHART_CONDITIONS = ("propagate_chart", "text_only_chart", "image_only_chart")

MIN_REL, MAX_REL = 0.15, 0.30        # edit size: visible but plausible
SEED = 576

# --------------------------------------------------------------------------
# Number cells: parse and re-format keeping the cell's own style
# --------------------------------------------------------------------------

_NUM = re.compile(r"^(?P<pre>[$€£]?)\s*(?P<sign>[-−]?)(?P<num>\d[\d,]*(?:\.\d+)?|\.\d+)\s*(?P<suf>%?)\*{0,2}$")


def parse_cell(s: Any) -> Optional[float]:
    m = _NUM.match(str(s).strip())
    if not m:
        return None
    v = float(m.group("num").replace(",", ""))
    return -v if m.group("sign") else v


def tidy_cell(s: str) -> str:
    """CSV number -> display string: '62.0' -> '62' (keeps %, $, commas, other decimals)."""
    s = s.strip()
    m = _NUM.match(s)
    if not m:
        return s
    num = m.group("num")
    if re.fullmatch(r"\d+\.0+", num):
        num = num.split(".")[0]
    return f"{m.group('pre')}{m.group('sign')}{num}{m.group('suf')}"


def _decimals(s: str) -> int:
    m = _NUM.match(s.strip())
    num = m.group("num") if m else s
    return len(num.split(".")[1]) if "." in num else 0


def format_like(value: float, template: str) -> str:
    """Write ``value`` in the style of ``template`` (decimals, commas, $, %)."""
    m = _NUM.match(template.strip())
    d = _decimals(template)
    body = f"{abs(value):,.{d}f}" if (m and "," in m.group("num")) else f"{abs(value):.{d}f}"
    sign = "-" if value < 0 else ""
    if not m:
        return sign + body
    return f"{m.group('pre')}{sign}{body}{m.group('suf')}"


def plain_number(s: str) -> str:
    """'1,027.5%' -> '1027.5' (answers are compared by numbers_match anyway)."""
    v = parse_cell(s)
    return format_like(v, re.sub(r"[$€£%,]", "", s.strip())) if v is not None else s


# --------------------------------------------------------------------------
# Question filters
# --------------------------------------------------------------------------

_VISUAL = re.compile(
    r"\b(colou?rs?|blue|red|green|orange|gr[ae]y|yellow|purple|pink|brown|black|white|violet|navy|"
    r"dark|light|pie|legend|line|lines|graph line|bars?\s+(?:are|is)\s+there|leftmost|rightmost|left|right|"
    r"middle|top|bottom|first|last|second|2nd|third|3rd|fourth|rank|segments?|slices?|portion|section)\b",
    re.IGNORECASE)
_ARITH = re.compile(
    r"\b(difference|differ|sum|add|added|plus|minus|subtract|average|mean|median|mode|ratio|times|twice|"
    r"half|product|divided|percentage points?|gap|combined|together|total of|more than|less than|greater|"
    r"smaller than|larger than|higher than|lower than|exceed|above|below|compare|change|increase|decrease|"
    r"grow|growth|drop|how many|count|number of (?:bars|years|countries|categories|values|items))\b",
    re.IGNORECASE)
_MAX = re.compile(r"\b(highest|largest|biggest|maximum|max|most|peak|longest|tallest|greatest)\b", re.I)
_MIN = re.compile(r"\b(lowest|smallest|least|minimum|min|shortest|fewest|tiniest)\b", re.I)


def question_ok(q: str) -> bool:
    return not (_VISUAL.search(q) or _ARITH.search(q))


def question_kind(q: str) -> str:
    """'max' / 'min' (edit direction is forced so the answer stays the extreme) or 'lookup'."""
    if _MAX.search(q):
        return "max"
    if _MIN.search(q):
        return "min"
    return "lookup"


# --------------------------------------------------------------------------
# ChartQA CSV -> A6 doc
# --------------------------------------------------------------------------

GENERIC_HEADERS = {"", "value", "values", "characteristic", "entity", "country", "year", "category",
                   "label", "series", "data"}


def chart_title(header: list[str]) -> str:
    """Best-effort title from the CSV header (ChartQA CSVs carry no chart title)."""
    if len(header) == 2 and header[1].strip().lower() not in GENERIC_HEADERS:
        return header[1].strip()
    if header and header[0].strip().lower() not in GENERIC_HEADERS:
        return header[0].strip()
    if len(header) > 2:
        return " vs. ".join(h.strip() for h in header[1:4])
    return ""


def read_chart_csv(path: str | Path) -> Optional[dict[str, Any]]:
    with open(path, encoding="utf-8", newline="") as f:
        rows = [[c.strip() for c in r] for r in csv.reader(f)]
    rows = [r for r in rows if any(r)]
    if len(rows) < 2:
        return None
    width = len(rows[0])
    if any(len(r) != width for r in rows):
        return None
    header = rows[0]
    body = [[r[0]] + [tidy_cell(c) for c in r[1:]] for r in rows[1:]]
    return {"title": chart_title(header), "unit_note": "", "header": header, "rows": body}


def simple_chart(table: dict[str, Any], max_series: int = 3, max_rows: int = 12) -> bool:
    n_series, rows = len(table["header"]) - 1, table["rows"]
    if not (1 <= n_series <= max_series and 2 <= len(rows) <= max_rows):
        return False
    if any(not r[0] for r in rows):
        return False
    return all(parse_cell(c) is not None for r in rows for c in r[1:])


def chart_doc(stem: str, table: dict[str, Any]) -> Doc:
    return Doc(doc_id=f"chartqa_{stem}", source="chartqa", table=table, pre_text="", post_text="",
               extra={"chartqa_image": f"{stem}.png"})


def _answer_cells(table: dict[str, Any], label: str) -> list[tuple[int, int]]:
    """Grid cells (row 0 = header) whose value equals the gold label."""
    gold = parse_cell(str(label).strip())
    if gold is None:
        return []
    return [(i + 1, j) for i, r in enumerate(table["rows"]) for j, c in enumerate(r)
            if j > 0 and parse_cell(c) is not None and math.isclose(parse_cell(c), gold, rel_tol=0, abs_tol=1e-9)]


# --------------------------------------------------------------------------
# The edit
# --------------------------------------------------------------------------

def _is_percent(table: dict[str, Any], j: int) -> bool:
    head = (table["header"][j] if j < len(table["header"]) else "").lower()
    col = [r[j] for r in table["rows"]]
    return any(c.endswith("%") for c in col) or any(w in head for w in ("%", "percent", "share"))


def chart_edit(ex: Example, doc: Doc, seed: int = SEED) -> Optional[tuple[dict[str, Any], str]]:
    """(edit, target_answer) for one question, or None if no plausible edit exists.

    The answer cell moves by 15-30% (direction random, except max/min questions,
    which move further out so the edited cell stays the extreme). The new value
    keeps the cell's format, keeps its sign, stays <= 100 for percentages, and
    does not equal any other value of the chart.
    """
    table = doc.table
    cells = _answer_cells(table, ex.gold_answer)
    if len(cells) != 1:
        return None
    r, c = cells[0]
    old = table["rows"][r - 1][c]
    v = parse_cell(old)
    if v is None or v == 0:
        return None
    rng = random.Random(f"{seed}:{ex.qid}")
    kind = question_kind(ex.question)
    others = {parse_cell(x) for i, row in enumerate(table["rows"]) for j, x in enumerate(row)
              if j > 0 and (i + 1, j) != (r, c)}
    unit = 10 ** -_decimals(old)
    pct = _is_percent(table, c)
    series = [parse_cell(row[c]) for row in table["rows"]]
    for attempt in range(12):
        rel = rng.uniform(MIN_REL, MAX_REL)
        up = rng.random() < 0.5 if kind == "lookup" else (kind == "max") == (v > 0)
        if attempt >= 6 and kind == "lookup":
            up = not up
        new = v * (1 + rel) if up else v * (1 - rel)
        new = round(new / unit) * unit
        if abs(new - v) < max(unit, 0.1 * abs(v)) or (new > 0) != (v > 0):
            continue
        if pct and abs(new) > 100:
            continue
        if any(o is not None and math.isclose(o, new, abs_tol=unit / 2) for o in others):
            continue
        rest = [s for i, s in enumerate(series) if i != r - 1]
        if kind == "max" and rest and new <= max(rest):
            continue
        if kind == "min" and rest and new >= min(rest):
            continue
        new_s = format_like(new, old)
        edit = {"row": r, "col": c, "old": old, "new": new_s, "also_changed": []}
        return edit, plain_number(new_s)
    return None


# --------------------------------------------------------------------------
# Selection from a ChartQA clone
# --------------------------------------------------------------------------

def _test_dir(chartqa_dir: str | Path) -> Path:
    d = Path(chartqa_dir)
    for cand in (d / "ChartQA Dataset" / "test", d / "test", d):
        if (cand / "test_human.json").exists():
            return cand
    raise FileNotFoundError(f"no test_human.json under {d} (expected '<clone>/ChartQA Dataset/test')")


def load_chartqa_tables(chartqa_dir: str | Path, stems: Iterable[str]) -> dict[str, dict]:
    tdir = _test_dir(chartqa_dir) / "tables"
    out = {}
    for s in stems:
        p = tdir / f"{s}.csv"
        if p.exists():
            t = read_chart_csv(p)
            if t is not None:
                out[s] = t
    return out


def select_chartqa_questions(n: int = 100, chartqa_dir: str | Path = "data/raw/ChartQA",
                             seed: int = SEED, return_docs: bool = False):
    """Human-written test questions whose answer equals one value in the chart CSV.

    Returns ``list[Example]`` (qids c0001...), or ``(examples, docs, stats)`` with
    ``return_docs=True``. One question per chart. Deterministic for a given seed.
    """
    tdir = _test_dir(chartqa_dir)
    human = json.loads((tdir / "test_human.json").read_text(encoding="utf-8"))
    stems = sorted({h["imgname"].rsplit(".", 1)[0] for h in human})
    tables = load_chartqa_tables(chartqa_dir, stems)
    stats = {"questions": len(human), "charts": len(stems)}
    cands: dict[str, list[tuple[dict, Doc]]] = {}
    for h in human:
        stem = h["imgname"].rsplit(".", 1)[0]
        t = tables.get(stem)
        if t is None or not simple_chart(t):
            stats["not_simple_chart"] = stats.get("not_simple_chart", 0) + 1
            continue
        if not question_ok(h["query"]):
            stats["question_filtered"] = stats.get("question_filtered", 0) + 1
            continue
        doc = chart_doc(stem, t)
        if len(_answer_cells(t, h["label"])) != 1:
            stats["answer_not_one_cell"] = stats.get("answer_not_one_cell", 0) + 1
            continue
        probe = Example(qid=f"probe_{stem}", source="chartqa", question=h["query"],
                        gold_answer=str(h["label"]).strip(), doc_id=doc.doc_id)
        if chart_edit(probe, doc, seed) is None:
            stats["no_plausible_edit"] = stats.get("no_plausible_edit", 0) + 1
            continue
        cands.setdefault(stem, []).append((h, doc))
    rng = random.Random(seed)
    chosen_stems = sorted(cands)
    rng.shuffle(chosen_stems)
    chosen_stems = sorted(chosen_stems[:n])
    stats["eligible_charts"] = len(cands)
    examples, docs = [], []
    for k, stem in enumerate(chosen_stems, 1):
        h, doc = sorted(cands[stem], key=lambda t: t[0]["query"])[0]
        examples.append(Example(qid=f"c{k:04d}", source="chartqa", question=h["query"].strip(),
                                gold_answer=str(h["label"]).strip(), doc_id=doc.doc_id,
                                extra={"chartqa_image": h["imgname"], "chartqa_split": "test_human",
                                       "chart_question_kind": question_kind(h["query"])}))
        docs.append(doc)
    stats["selected"] = len(examples)
    return (examples, docs, stats) if return_docs else examples


def select_distractor_docs(n: int, exclude: set[str], chartqa_dir: str | Path = "data/raw/ChartQA",
                           seed: int = SEED) -> list[Doc]:
    """Other simple test charts (human + augmented splits) to pad the corpus."""
    tdir = _test_dir(chartqa_dir)
    stems: set[str] = set()
    for split in ("test_human.json", "test_augmented.json"):
        p = tdir / split
        if p.exists():
            stems |= {h["imgname"].rsplit(".", 1)[0] for h in json.loads(p.read_text(encoding="utf-8"))}
    tables = load_chartqa_tables(chartqa_dir, sorted(stems))
    pool = sorted(s for s, t in tables.items() if simple_chart(t) and f"chartqa_{s}" not in exclude)
    rng = random.Random(f"{seed}:distractors")
    rng.shuffle(pool)
    return [chart_doc(s, tables[s]) for s in sorted(pool[:n])]


# --------------------------------------------------------------------------
# Attack rows
# --------------------------------------------------------------------------

def make_chart_conditions(ex: Example, doc: Doc, pages_dir: str,
                          conditions: Iterable[str] = CHART_CONDITIONS,
                          render: Optional[Callable[..., dict]] = None,
                          page_sink: Optional[list[dict]] = None, seed: int = SEED) -> list[Attack]:
    """G2 chart rows for one question (default: all three conditions).

    Person 4's script builds propagate_chart; Person 5 builds the two conflict
    conditions with ``conditions=("text_only_chart", "image_only_chart")``.
    Every condition uses the same edit, so the rows are comparable. Rendered
    page records are appended to ``page_sink``.
    """
    if render is None:
        from ...render.render_chart_page import render_chart_page as render
    got = chart_edit(ex, doc, seed)
    if got is None:
        raise ValueError(f"{ex.qid}: no plausible edit for this chart")
    edit, target = got
    d = doc.to_dict()
    clean_t, pois_t = d["table"], apply_edit(d, edit)["table"]
    out = []
    for at in conditions:
        if at not in CHART_CONDITIONS:
            raise ValueError(f"not a chart condition: {at!r}")
        img_v, txt_v = ATTACK_LAYERS[at]
        pid = poison_page_id(d["doc_id"], "G2", at, ex.qid)
        rec = render(d, pid, pages_dir,
                     image_table=pois_t if img_v == "poison" else clean_t,
                     text_table=pois_t if txt_v == "poison" else clean_t)
        if page_sink is not None:
            page_sink.append(rec)
        img_a, txt_a = layer_answers(at, ex.gold_answer, target)
        a = Attack(attack_id=attack_id("G2", at, ex.qid), qid=ex.qid, gap="G2", attack_type=at,
                   clean_page_id=clean_page_id(d["doc_id"]), poison_page_id=pid, edit=edit,
                   target_answer=target, image_version=img_v, text_version=txt_v,
                   gold_answer=ex.gold_answer, image_answer=img_a, text_answer=txt_a)
        a.validate()
        out.append(a)
    return out


def select_chart_attack_examples(cfg: dict, limit: Optional[int] = None,
                                 only_r2_correct: Optional[str] = None) -> list[Example]:
    """The chart questions that get G2 rows: chart_examples.jsonl sorted by qid,
    optionally only those a pipeline answered correctly under R2, first
    ``attacks_g2.n_charts``. Person 4 (propagate) and Person 5 (conflicts) both
    call this, so all three conditions cover the same questions."""
    from ...common.io import load_examples, load_r2_correct

    exs = sorted(load_examples(cfg, ("chartqa",)).values(), key=lambda e: e.qid)
    if only_r2_correct:
        keep = load_r2_correct(cfg).get(only_r2_correct, set())
        exs = [e for e in exs if e.qid in keep]
    return exs[: limit or (cfg.get("attacks_g2") or {}).get("n_charts", 50)]
