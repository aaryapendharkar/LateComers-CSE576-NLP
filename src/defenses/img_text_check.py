"""Image-text consistency checker for Gap 2.

OWNER: Person 5 (Disha). Brief task 1.

  1. a VLM (reuse the generator model) reads the page IMAGE -> table JSON (charts: value list)
  2. parse the page's TEXT layer (Docling output P1 uses) into the same format
  3. align rows/cols by label, compare numbers with tolerance, flag any mismatch
Cheaper mode (configs: img_text_check.only_question_rows): compare only rows
whose label appears in the question.

Expected: catches text_only / image_only, ~0% on propagate (both layers agree on
the wrong value) -> the key blind spot.

Both tables use the shared Table format (src/common/schemas.py):
  {"title": str, "unit_note": str, "header": ["", "2019", "2018"],
   "rows": [["Revenue", "1,204", "1,090"], ...]}
Charts use the same shape: header = ["", "<series>"], rows = [["<bar label>", "<value>"], ...].
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, NotRequired, Optional, TypedDict

from ..common.answer_match import parse_number

LABEL_MATCH = 0.80   # how alike two labels must look to be paired (0-1); absorbs OCR/VLM typos


class CheckResult(TypedDict):
    flag: bool
    mismatches: list[list[Any]]   # [[row_label, col_label, img_val, text_val], ...]
    unmatched: NotRequired[dict[str, list[str]]]   # rows/cols seen on one side only (info, never flags)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def norm_label(label: Any) -> str:
    """' Net  Income*' -> 'net income' (lowercase, letters/digits only, single spaces)."""
    s = re.sub(r"[^a-z0-9]+", " ", str(label or "").lower())
    return " ".join(s.split())


def label_similarity(a: Any, b: Any) -> float:
    """0-1 score for how alike two labels look."""
    a, b = norm_label(a), norm_label(b)
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def cells_equal(img_cell: Any, text_cell: Any, rel_tol: float = 0.01) -> bool:
    """Same value? Numbers with relative tolerance (uses the shared parser), text after normalising."""
    a, b = parse_number(img_cell), parse_number(text_cell)
    if a is not None and b is not None:
        return a == b or abs(a - b) <= rel_tol * max(abs(a), abs(b))
    if a is None and b is None:
        return norm_label(img_cell) == norm_label(text_cell)
    return False


def align(labels_a: list[Any], labels_b: list[Any], threshold: float = LABEL_MATCH) -> list[tuple[int, int]]:
    """Pair two label lists IN ORDER (rows or columns). Returns [(i, j), ...].

    Order-preserving alignment (dynamic programming), so repeated labels such
    as two "Total" rows pair with the right partner, and fuzzy similarity
    tolerates OCR/VLM typos ("Reveune" ~ "Revenue").
    """
    n, m = len(labels_a), len(labels_b)
    sim = [[label_similarity(labels_a[i], labels_b[j]) for j in range(m)] for i in range(n)]
    best = [[0.0] * (m + 1) for _ in range(n + 1)]   # best[i][j]: score using a[i:], b[j:]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            take = sim[i][j] + best[i + 1][j + 1] if sim[i][j] >= threshold else -1.0
            best[i][j] = max(best[i + 1][j], best[i][j + 1], take)
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        if sim[i][j] >= threshold and abs(best[i][j] - (sim[i][j] + best[i + 1][j + 1])) < 1e-9:
            pairs.append((i, j))
            i, j = i + 1, j + 1
        elif best[i + 1][j] >= best[i][j + 1]:
            i += 1
        else:
            j += 1
    return pairs


def rows_named_in_question(table: dict[str, Any], question: str) -> list[str]:
    """Row labels that appear in the question (for the cheaper only_question_rows mode)."""
    q = norm_label(question)
    labels = [r[0] for r in table.get("rows") or [] if r]
    return [lab for lab in labels if len(norm_label(lab)) >= 3 and norm_label(lab) in q]


# ---------------------------------------------------------------------------
# Step 3: compare (pure logic, no model)
# ---------------------------------------------------------------------------
def compare_tables(img_table: dict[str, Any], text_table: dict[str, Any], rel_tol: float = 0.01,
                   only_rows: Optional[list[str]] = None) -> CheckResult:
    """Compare the table read from the image with the table from the text layer.

    only_rows: if given, compare only rows whose label matches one of these
    (falls back to all rows if none match, so the check never silently does nothing).
    """
    mismatches: list[list[Any]] = []
    unmatched: dict[str, list[str]] = {}

    # 1. Unit note ("in millions" vs "in thousands"): cheap, strong signal
    u_img, u_txt = img_table.get("unit_note") or "", text_table.get("unit_note") or ""
    if norm_label(u_img) and norm_label(u_txt) and norm_label(u_img) != norm_label(u_txt):
        mismatches.append(["<unit_note>", None, u_img, u_txt])

    # 2. Columns: pair by header (header[0] is the row-label column)
    h_img = list(img_table.get("header") or [])[1:]
    h_txt = list(text_table.get("header") or [])[1:]
    col_pairs = align(h_img, h_txt)
    if not col_pairs and len(h_img) == len(h_txt):           # headers unreadable -> by position
        col_pairs = [(k, k) for k in range(len(h_img))]
    used_a, used_b = {a for a, _ in col_pairs}, {b for _, b in col_pairs}
    unmatched["cols_img_only"] = [h for k, h in enumerate(h_img) if k not in used_a]
    unmatched["cols_text_only"] = [h for k, h in enumerate(h_txt) if k not in used_b]

    # 3. Rows: pair by label
    r_img = [r for r in img_table.get("rows") or [] if r]
    r_txt = [r for r in text_table.get("rows") or [] if r]
    row_pairs = align([r[0] for r in r_img], [r[0] for r in r_txt])
    used_a, used_b = {a for a, _ in row_pairs}, {b for _, b in row_pairs}
    unmatched["rows_img_only"] = [r_img[a][0] for a in range(len(r_img)) if a not in used_a]
    unmatched["rows_text_only"] = [r_txt[b][0] for b in range(len(r_txt)) if b not in used_b]

    if only_rows:
        wanted = [norm_label(x) for x in only_rows]
        focused = [(a, b) for a, b in row_pairs
                   if any(label_similarity(r_img[a][0], w) >= LABEL_MATCH for w in wanted)]
        row_pairs = focused or row_pairs

    # 4. Compare every paired cell
    for a, b in row_pairs:
        row_i, row_t = r_img[a], r_txt[b]
        for ci, ct in col_pairs:
            v_img = row_i[ci + 1] if ci + 1 < len(row_i) else None
            v_txt = row_t[ct + 1] if ct + 1 < len(row_t) else None
            if not cells_equal(v_img, v_txt, rel_tol):
                mismatches.append([row_i[0], h_img[ci], v_img, v_txt])

    return {"flag": bool(mismatches), "mismatches": mismatches, "unmatched": unmatched}


# ---------------------------------------------------------------------------
# Shared cleanup for anything that should become a table
# ---------------------------------------------------------------------------
def _normalise_table(t: dict[str, Any]) -> dict[str, Any]:
    """Coerce to the shared Table shape: strings everywhere, rows padded to header width."""
    header = [str(h if h is not None else "") for h in (t.get("header") or [])]
    rows = [[str(c if c is not None else "") for c in r] for r in (t.get("rows") or []) if r]
    width = max([len(header)] + [len(r) for r in rows]) if (header or rows) else 0
    header = header + [""] * (width - len(header))
    rows = [r + [""] * (width - len(r)) for r in rows]
    return {"title": str(t.get("title") or ""), "unit_note": str(t.get("unit_note") or ""),
            "header": header, "rows": rows}


_NUM_TOKEN = re.compile(r"^\(?[-−$]?\$?\d[\d,]*\.?\d*%?\)?\*?$")


def _is_num_token(tok: str) -> bool:
    return bool(_NUM_TOKEN.match(tok)) or tok in {"-", "—", "–"}


# ---------------------------------------------------------------------------
# Step 1: page IMAGE -> table (VLM)
# ---------------------------------------------------------------------------
def _vlm_complete(generator: Any, image_path: str, prompt: str, max_new_tokens: int = 1024) -> str:
    """Run one image + prompt through the model and return the raw reply.

    ``generator`` is Person 1's VLMGenerator (same model as the pipelines, so no
    extra setup), OR any callable ``f(image_path, prompt) -> str`` -- used by
    tests, and the hook for a backup reader (OCR / hosted API) if the GPU is out.
    """
    if not hasattr(generator, "_load"):
        if callable(generator):
            return generator(image_path, prompt)
        raise TypeError("generator must be a VLMGenerator or a callable(image_path, prompt) -> str")
    import torch
    from PIL import Image

    model, proc = generator._load()
    messages = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": prompt}]}]
    text = proc.apply_chat_template(messages, add_generation_prompt=True, tokenize=False,
                                    enable_thinking=False)
    image = Image.open(image_path).convert("RGB")
    inputs = proc(text=[text], images=[image], return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    return proc.batch_decode(out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0]


def parse_table_reply(raw: str) -> dict[str, Any]:
    """Model reply -> table. Accepts JSON (with code fences / <think> / extra prose) or a markdown table."""
    from ..common.tables import rows_to_table, split_markdown_context

    text = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL)
    text = re.sub(r"^.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"```(?:json)?", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        import json
        for candidate in (text[start:end + 1], text[start:end + 1].replace("'", '"')):
            try:
                obj = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and ("rows" in obj or "header" in obj):
                return _normalise_table(obj)
    pre, rows, _ = split_markdown_context(text)
    if rows:
        return _normalise_table(rows_to_table(rows, pre_text=pre))
    raise ValueError(f"could not read a table from the model reply: {raw[:200]!r}")


def extract_table_from_image(image_path: str, generator: Any, prompt_file: Optional[str] = None,
                             max_new_tokens: int = 1024) -> dict[str, Any]:
    """VLM prompt -> table JSON. Save the prompt in configs/prompts/ (e.g. img_extract_v1.txt)."""
    from ..common.config import resolve

    prompt = resolve(prompt_file or "configs/prompts/img_extract_v1.txt").read_text(encoding="utf-8")
    return parse_table_reply(_vlm_complete(generator, image_path, prompt, max_new_tokens))


# ---------------------------------------------------------------------------
# Step 2: page TEXT layer -> table
# ---------------------------------------------------------------------------
_PAIR = re.compile(r"([^,;:]+?)\s*[:=]\s*(\(?[-−]?\$?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?\)?)")


def parse_text_layer(text: str) -> dict[str, Any]:
    """Text the pipeline sees (Docling markdown or pdfplumber plain text) -> table.

    Tries, in order:
      1. a markdown table (Docling exports tables this way)
      2. a chart "Source data: <label>: <value>, ..." note
      3. plain-text rows "<label> <num> <num> ..." (pdfplumber fallback)
    """
    from ..common.tables import guess_unit_note, rows_to_table, split_markdown_context

    pre, rows, post = split_markdown_context(text or "")
    if rows:
        t = rows_to_table(rows, pre_text=pre)
        if not t["unit_note"]:
            t["unit_note"] = guess_unit_note(text)
        return _normalise_table(t)

    m = re.search(r"source data\s*:\s*(.+)", text or "", flags=re.IGNORECASE)
    if m:
        pairs = _PAIR.findall(m.group(1))
        if pairs:
            return _normalise_table({"header": ["", "value"], "rows": [[k.strip(), v] for k, v in pairs],
                                     "unit_note": guess_unit_note(text)})

    return _normalise_table(_plain_text_rows(text or ""))


def _plain_text_rows(text: str) -> dict[str, Any]:
    from collections import Counter

    from ..common.tables import guess_unit_note

    parsed = []   # (line_no, label, values)
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        toks = ln.split()
        k = len(toks)
        while k > 0 and _is_num_token(toks[k - 1]):
            k -= 1
        vals = toks[k:]
        if vals and k > 0:
            parsed.append((i, " ".join(toks[:k]), vals))
    if not parsed:
        return {"header": [], "rows": [], "unit_note": guess_unit_note(text)}
    width = Counter(len(v) for _, _, v in parsed).most_common(1)[0][0]
    body = [(i, lab, v) for i, lab, v in parsed if len(v) == width]
    header = [""] + [f"col{j + 1}" for j in range(width)]
    first = body[0][0]
    if first > 0:                       # header line right above the first row, e.g. "2019 2018"
        htoks = lines[first - 1].split()
        if len(htoks) >= width:
            header = [" ".join(htoks[:-width])] + htoks[-width:]
    return {"header": header, "rows": [[lab] + v for _, lab, v in body],
            "unit_note": guess_unit_note(text)}


# ---------------------------------------------------------------------------
# Page-level entry point
# ---------------------------------------------------------------------------
def _settings(cfg: dict) -> dict[str, Any]:
    s = {"rel_tol": 0.01, "only_question_rows": False, "prompt_file": "configs/prompts/img_extract_v1.txt",
         "max_new_tokens": 1024, "text_source": None, "cache_dir": "data/parsed/img_tables"}
    s.update(cfg.get("img_text_check") or {})
    if not s["text_source"]:
        src = (cfg.get("pipelines") or {}).get("p1_text_source")
        s["text_source"] = src if src in ("docling", "pdfplumber") else "docling"
    return s


def page_text(page_id: str, cfg: dict) -> str:
    """The text layer exactly as P1 sees it: data/parsed/<text_source>/<page_id>.txt."""
    from ..common.config import resolve

    s = _settings(cfg)
    path = resolve(cfg["paths"].get("parsed_dir", "data/parsed")) / s["text_source"] / f"{page_id}.txt"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: run scripts/build_indexes.py --parse {s['text_source']}")
    return path.read_text(encoding="utf-8")


def image_table(page_id: str, image_path: str, cfg: dict, generator: Any = None,
                use_cache: bool = True) -> dict[str, Any]:
    """Step 1 with a cache: each page image is read by the model only once."""
    import json

    from ..common.config import resolve

    s = _settings(cfg)
    cache = resolve(s["cache_dir"]) / f"{page_id}.json"
    if use_cache and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    if generator is None:
        from ..pipelines.run import get_system
        generator = get_system().generator
    table = extract_table_from_image(str(resolve(image_path)), generator, s["prompt_file"],
                                     s["max_new_tokens"])
    if use_cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(table), encoding="utf-8")
    return table


def check_page(page_id: str, question: Optional[str] = None, cfg: Optional[dict] = None,
               generator: Any = None, pages: Optional[dict] = None, use_cache: bool = True) -> CheckResult:
    """Full checker for one rendered page: image -> table, text layer -> table, compare.

    generator: VLMGenerator or callable(image_path, prompt) -> str (default: the pipelines' generator).
    pages: preloaded io.load_pages(cfg) (pass it when checking many pages).
    use_cache: False for test readers (e.g. the oracle) so they never overwrite real VLM reads.
    """
    from ..common import io
    from ..common.config import get_config

    cfg = cfg or get_config()
    s = _settings(cfg)
    pages = pages if pages is not None else io.load_pages(cfg)
    if page_id not in pages:
        raise KeyError(f"page {page_id!r} is not in data/manifests/pages_*.jsonl")
    img_t = image_table(page_id, pages[page_id].image_path, cfg, generator, use_cache)
    txt_t = parse_text_layer(page_text(page_id, cfg))
    only = rows_named_in_question(txt_t, question) if (question and s["only_question_rows"]) else None
    return compare_tables(img_t, txt_t, rel_tol=s["rel_tol"], only_rows=only)


# ---------------------------------------------------------------------------
# Evaluation (brief task 2): false-positive rate on clean pages, detection per G2 condition
# ---------------------------------------------------------------------------
def oracle_reader(cfg: dict, pages: dict) -> Any:
    """A 'perfect eyes' reader: returns the table the renderer actually drew in each image.

    Not a defense result. Use it (a) to dry-run the whole evaluation before the GPU
    is set up, and (b) as an upper bound: with perfect image reading, any remaining
    misses or false alarms come from text-layer parsing alone.
    """
    from ..common import io
    from ..common.config import resolve
    from ..common.edits import apply_edit
    from ..common.schemas import doc_id_of_page

    docs = io.load_docs(cfg)
    by_poison_page = {a.poison_page_id: a for a in io.load_attacks(cfg).values()}
    by_image: dict[str, dict] = {}
    for pid, p in pages.items():
        doc = docs[doc_id_of_page(pid)].to_dict()
        table = doc["table"]
        if p.image_version == "poison" and pid in by_poison_page:
            table = apply_edit(doc, by_poison_page[pid].edit)["table"]
        by_image[str(resolve(p.image_path))] = table

    def read(image_path: str, prompt: str) -> str:
        import json
        return json.dumps(by_image[str(resolve(image_path))])
    return read


def evaluate(cfg: dict, n_clean: Optional[int] = None, generator: Any = None, oracle: bool = False,
             out_dir: str = "results/gap2", overwrite: bool = False, seed: int = 576) -> list[dict[str, Any]]:
    """Run the checker on n clean pages per source + every Gap 2 poisoned page.

    Writes (suffix _oracle in oracle mode, so real results are never overwritten):
      checker_flags.jsonl  {"page_id", "flag", "mismatches", "kind", "attack_id", "error"}
                           -> scripts/run_attacks.py --drop-flags for the P3 filter run
      checker_table.md / .csv  false-positive rate (clean) and detection rate per condition, 95% CIs
    Resumable: pages already in checker_flags.jsonl are skipped unless overwrite=True.
    """
    import csv
    import random

    from ..common import io
    from ..common.config import resolve
    from ..common.metrics import fmt_rate, rate
    from ..common.schemas import doc_id_of_page

    s = _settings(cfg)
    n_clean = n_clean or s.get("n_clean", 100)
    pages = io.load_pages(cfg)
    docs = io.load_docs(cfg)
    try:
        questions = {q: e.question for q, e in io.load_examples(cfg).items()}
    except FileNotFoundError:
        questions = {}

    # what to check: (page_id, kind, attack_id, qid)
    items: list[tuple[str, str, Optional[str], Optional[str]]] = []
    rng = random.Random(seed)
    for source, kind in (("finqa", "clean_table"), ("chartqa", "clean_chart")):
        ids = sorted(pid for pid, p in pages.items() if p.variant == "clean"
                     and doc_id_of_page(pid) in docs and docs[doc_id_of_page(pid)].source == source)
        items += [(pid, kind, None, None) for pid in sorted(rng.sample(ids, min(n_clean, len(ids))))]
    for a in sorted(io.load_attacks(cfg, gap="G2").values(), key=lambda a: a.attack_id):
        if a.poison_page_id in pages:
            items.append((a.poison_page_id, a.attack_type, a.attack_id, a.qid))

    suffix = "_oracle" if oracle else ""
    out = resolve(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    flags_path = out / f"checker_flags{suffix}.jsonl"
    done = {}
    if flags_path.exists() and not overwrite:
        done = {(r["page_id"], r.get("attack_id")): r for r in io.read_jsonl(flags_path)}
    elif flags_path.exists():
        flags_path.unlink()
    reader = oracle_reader(cfg, pages) if oracle else generator

    try:
        from tqdm import tqdm
    except ImportError:  # pragma: no cover
        def tqdm(it, **_):
            return it
    records = list(done.values())
    for pid, kind, aid, qid in tqdm([i for i in items if (i[0], i[2]) not in done], desc="checker"):
        rec: dict[str, Any] = {"page_id": pid, "kind": kind, "attack_id": aid, "flag": False,
                               "mismatches": [], "error": None}
        try:
            r = check_page(pid, questions.get(qid) if qid else None, cfg, reader, pages, use_cache=not oracle)
            rec.update(flag=r["flag"], mismatches=r["mismatches"])
        except Exception as e:  # one bad page must not stop a 300-page run
            rec["error"] = f"{type(e).__name__}: {e}"
        io.append_jsonl(flags_path, rec)
        records.append(rec)

    # summary table
    kinds = ["clean_table", "clean_chart"] + [k for k in G2_ORDER if any(r["kind"] == k for r in records)]
    rows = []
    for k in kinds:
        ok = [r for r in records if r["kind"] == k and not r["error"]]
        if not any(r["kind"] == k for r in records):
            continue
        metric = "false-positive rate" if k.startswith("clean") else "detection rate"
        rows.append({"kind": k, "metric": metric, "errors": sum(1 for r in records if r["kind"] == k and r["error"]),
                     **rate([r["flag"] for r in ok])})
    lines = [f"Image-text checker{' (ORACLE reader: upper bound, not a result)' if oracle else ''}", "",
             "| pages | metric | % flagged [95% CI] (n) | errors |", "|---|---|---|---|"]
    lines += [f"| {r['kind']} | {r['metric']} | {fmt_rate(r)} | {r['errors']} |" for r in rows]
    (out / f"checker_table{suffix}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with open(out / f"checker_table{suffix}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kind", "metric", "rate", "ci_low", "ci_high", "n", "errors"])
        for r in rows:
            w.writerow([r["kind"], r["metric"], r["rate"], r["ci_low"], r["ci_high"], r["n"], r["errors"]])
    return rows


G2_ORDER = ("propagate_table", "text_only_table", "image_only_table",
            "propagate_chart", "text_only_chart", "image_only_chart")
