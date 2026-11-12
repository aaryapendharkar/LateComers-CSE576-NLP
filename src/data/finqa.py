"""Build data/docs.jsonl + data/examples.jsonl from T2-RAGBench (FinQA subset). OWNER: Person 1.

Field names are NOT hard-coded: they come from ``data.finqa.fields`` in the
config. Run ``python scripts/prepare_finqa.py --inspect`` first and fix the
mapping if the dataset card uses different names.

If T2-RAGBench lacks the FinQA reasoning program, pass the original FinQA JSON
(github.com/czyssrs/FinQA, dataset/test.json) and we join on the FinQA id, or
on (source file, answer) when ids differ.
"""

from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Optional

from ..common.answer_match import numbers_match
from ..common.schemas import Doc, Example
from ..common.tables import rows_to_table, split_markdown_context


def make_doc_id(doc_key: str) -> str:
    """'ABC/2019/page_12.pdf' -> 'finqa_ABC_2019_p12' (falls back to a sanitised key)."""
    m = re.match(r"^([^/]+)/(\d{4})/page_(\d+)\.pdf", doc_key)
    if m:
        return f"finqa_{m.group(1)}_{m.group(2)}_p{m.group(3)}"
    return "finqa_" + re.sub(r"[^A-Za-z0-9]+", "_", doc_key).strip("_")


def load_rows(hf_dataset: str, hf_config: Optional[str], split: str,
              local_jsonl: Optional[str] = None) -> list[dict[str, Any]]:
    if local_jsonl:
        with open(local_jsonl, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]
    from datasets import load_dataset  # heavy import

    ds = load_dataset(hf_dataset, hf_config, split=split) if hf_config else load_dataset(hf_dataset, split=split)
    return [dict(r) for r in ds]


def inspect_rows(rows: list[dict[str, Any]], n: int = 1) -> str:
    out = [f"{len(rows)} rows; columns: {sorted(rows[0].keys()) if rows else []}"]
    for r in rows[:n]:
        out.append(json.dumps({k: (str(v)[:300] + "...") if len(str(v)) > 300 else v for k, v in r.items()},
                              indent=2, ensure_ascii=False, default=str))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Original FinQA join
# ---------------------------------------------------------------------------


def load_finqa_json(path: str) -> dict[str, dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {d["id"]: d for d in data}


def join_finqa(row_id: str, doc_key: str, answer: str, finqa: dict[str, dict]) -> Optional[dict]:
    if row_id in finqa:
        return finqa[row_id]
    cands = [d for k, d in finqa.items() if d.get("filename") == doc_key or k.startswith(doc_key)]
    cands = [d for d in cands if numbers_match(d["qa"].get("exe_ans"), answer)]
    return cands[0] if len(cands) == 1 else None


def _clean_cell(c: str) -> str:
    return re.sub(r"<sup>.*?</sup>", "", str(c)).strip()


def finqa_table_rows(fq: dict) -> tuple[list[list[str]], str]:
    """Prefer ``table_ori`` (original casing/formatting: "$(4,614)", "—") over ``table``
    (lowercased; FinQA's normaliser even turns "—" into "2014"). table_ori is only used
    when it is rectangular; multi-row headers make it ragged, then we fall back."""
    ori = fq.get("table_ori")
    if ori and len({len(r) for r in ori}) == 1:
        return [[_clean_cell(c) for c in r] for r in ori], "finqa_table_ori"
    return [[_clean_cell(c) for c in r] for r in fq["table"]], "finqa_table"


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def build(rows: Iterable[dict[str, Any]], fields: dict[str, Optional[str]], n_docs: int, n_questions: int,
          seed: int, finqa: Optional[dict[str, dict]] = None,
          distractor_rows: Optional[Iterable[dict[str, Any]]] = None) -> tuple[list[Doc], list[Example], dict[str, Any]]:
    """Questions come only from ``rows``. If ``rows`` has fewer than ``n_docs`` documents,
    the corpus is filled with distractor documents from ``distractor_rows`` (e.g. the dev split)."""
    f = fields
    by_doc: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_doc[str(r[f["doc_key"]])].append(r)
    doc_keys = sorted(by_doc)
    extra_docs: dict[str, list[dict]] = defaultdict(list)
    for r in distractor_rows or []:
        k = str(r[f["doc_key"]])
        if k not in by_doc:
            extra_docs[k].append(r)
    rng = random.Random(seed)

    # 1) sample questions, 2) their gold docs, 3) fill with distractor docs up to n_docs
    all_q = [(k, r) for k in doc_keys for r in by_doc[k]]
    rng.shuffle(all_q)
    picked, gold_keys = [], []
    for k, r in all_q:
        if len(picked) >= n_questions:
            break
        if k not in gold_keys and len(gold_keys) >= n_docs:
            continue
        picked.append((k, r))
        if k not in gold_keys:
            gold_keys.append(k)
    others = [k for k in doc_keys if k not in set(gold_keys)]
    rng.shuffle(others)
    extra = sorted(extra_docs)
    rng.shuffle(extra)
    corpus_keys = (gold_keys + others + extra)[:max(n_docs, len(gold_keys))]
    by_doc.update(extra_docs)

    stats = {"n_rows": len(all_q), "n_source_docs": len(doc_keys), "n_distractor_source_docs": len(extra_docs),
             "joined": 0, "with_program": 0,
             "table_from": defaultdict(int)}
    docs: list[Doc] = []
    for k in corpus_keys:
        r0 = by_doc[k][0]
        fq = finqa and join_finqa(str(r0.get(f["id"], "")), k, str(r0.get(f["answer"], "")), finqa)
        if fq:  # structured table straight from FinQA
            pre, post = " ".join(fq["pre_text"]), " ".join(fq["post_text"])
            rows, origin = finqa_table_rows(fq)
            table = rows_to_table(rows, pre)
            stats["table_from"][origin] += 1
        else:
            pre, rws, post = split_markdown_context(str(r0[f["context"]]))
            table = rows_to_table(rws, pre)
            stats["table_from"]["t2_markdown"] += 1
        if not table["header"]:
            continue  # no table found: not usable for this project
        docs.append(Doc(doc_id=make_doc_id(k), source="finqa", pre_text=pre, post_text=post, table=table))
    kept_doc_ids = {d.doc_id for d in docs}

    examples: list[Example] = []
    for i, (k, r) in enumerate(picked, 1):
        if make_doc_id(k) not in kept_doc_ids:
            continue
        answer = str(r[f["answer"]])
        program = r.get(f["program"]) if f.get("program") else None
        if program is None and finqa:
            fq = join_finqa(str(r.get(f["id"], "")), k, answer, finqa)
            if fq:
                stats["joined"] += 1
                program = fq["qa"].get("program")
        stats["with_program"] += program is not None
        examples.append(Example(qid=f"q{i:04d}", source="finqa", question=str(r[f["question"]]),
                                gold_answer=answer, doc_id=make_doc_id(k), program=program,
                                extra={"t2_id": r.get(f["id"])}))
    stats["n_docs"], stats["n_examples"] = len(docs), len(examples)
    stats["table_from"] = dict(stats["table_from"])
    return docs, examples, stats
