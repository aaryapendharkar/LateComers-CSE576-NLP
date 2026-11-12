"""JSONL helpers and loaders for the shared files. OWNER: Person 1.

Why several files instead of one ``pages.jsonl`` / ``attacks.jsonl``?
So two people never write to the same file. Each producer owns its file and
the loaders below merge them:

    data/docs.jsonl                 Person 1   FinQA docs
    data/examples.jsonl             Person 1   FinQA questions
    data/chart_docs.jsonl           Person 4   ChartQA docs
    data/chart_examples.jsonl       Person 4   ChartQA questions
    data/labels/qtypes.jsonl        Person 3   {"qid", "question_type"} overlay
    data/manifests/pages_clean.jsonl  Person 4 clean pages
    data/manifests/pages_g1.jsonl     Person 2 Gap 1 poisoned pages
    data/manifests/pages_g2.jsonl     Person 4 Gap 2 poisoned pages
    data/attacks/g1.jsonl           Person 2   Gap 1 attack rows
    data/attacks/g2.jsonl           Person 4   Gap 2 attack rows

``load_pages()`` / ``load_attacks()`` read every file in their folder, so
adding a new producer file needs no code change.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Iterator

from .config import get_config, resolve
from .schemas import Attack, Doc, Example, Page, RunRecord, SchemaError

# ---------------------------------------------------------------------------
# Generic JSONL
# ---------------------------------------------------------------------------


def iter_jsonl(path: str | os.PathLike) -> Iterator[dict[str, Any]]:
    path = resolve(path)
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{lineno}: bad JSON ({e})") from e


def read_jsonl(path: str | os.PathLike) -> list[dict[str, Any]]:
    return list(iter_jsonl(path))


def _to_dict(obj: Any) -> dict[str, Any]:
    return obj.to_dict() if hasattr(obj, "to_dict") else obj


def write_jsonl(path: str | os.PathLike, records: Iterable[Any]) -> int:
    """Atomically (re)write a JSONL file. Returns the number of records."""
    path = resolve(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(_to_dict(r), ensure_ascii=False) + "\n")
                n += 1
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return n


def append_jsonl(path: str | os.PathLike, record: Any) -> None:
    path = resolve(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(_to_dict(record), ensure_ascii=False) + "\n")


def _read_many(paths: Iterable[Path]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in sorted(paths):
        if p.exists():
            out.extend(read_jsonl(p))
    return out


def _index_unique(records: list[dict], key: str, what: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in records:
        k = r[key]
        if k in out and out[k] != r:
            raise SchemaError(f"duplicate {what} {key}={k!r} with different content")
        out[k] = r
    return out


# ---------------------------------------------------------------------------
# Typed loaders
# ---------------------------------------------------------------------------


def _paths(cfg: dict | None) -> dict[str, str]:
    return (cfg or get_config())["paths"]


def load_docs(cfg: dict | None = None, sources: tuple[str, ...] = ("finqa", "chartqa")) -> dict[str, Doc]:
    p = _paths(cfg)
    files = []
    if "finqa" in sources:
        files.append(resolve(p["docs"]))
    if "chartqa" in sources:
        files.append(resolve(p["chart_docs"]))
    recs = _index_unique(_read_many(files), "doc_id", "doc")
    return {k: Doc.from_dict(v) for k, v in recs.items()}


def load_examples(cfg: dict | None = None, sources: tuple[str, ...] = ("finqa", "chartqa"),
                  with_qtypes: bool = True) -> dict[str, Example]:
    """Questions keyed by qid, with Person 3's question_type labels overlaid."""
    p = _paths(cfg)
    files = []
    if "finqa" in sources:
        files.append(resolve(p["examples"]))
    if "chartqa" in sources:
        files.append(resolve(p["chart_examples"]))
    recs = _index_unique(_read_many(files), "qid", "example")
    if with_qtypes and resolve(p["qtypes"]).exists():
        for lab in read_jsonl(p["qtypes"]):
            if lab["qid"] in recs:
                recs[lab["qid"]] = {**recs[lab["qid"]], "question_type": lab["question_type"]}
    return {k: Example.from_dict(v) for k, v in recs.items()}


def load_pages(cfg: dict | None = None) -> dict[str, Page]:
    d = resolve(_paths(cfg)["manifests_dir"])
    recs = _index_unique(_read_many(d.glob("pages_*.jsonl")), "page_id", "page")
    return {k: Page.from_dict(v) for k, v in recs.items()}


def load_attacks(cfg: dict | None = None, gap: str | None = None) -> dict[str, Attack]:
    d = resolve(_paths(cfg)["attacks_dir"])
    recs = _index_unique(_read_many(d.glob("*.jsonl")), "attack_id", "attack")
    out = {k: Attack.from_dict(v) for k, v in recs.items()}
    if gap:
        out = {k: v for k, v in out.items() if v.gap == gap}
    return out


def load_runs(path: str | os.PathLike) -> list[RunRecord]:
    return [RunRecord.from_dict(r) for r in iter_jsonl(path)]


def load_r2_correct(cfg: dict | None = None) -> dict[str, set[str]]:
    """``results/r2_correct.json``: {pipeline: [qids correct under R2]}."""
    path = resolve(_paths(cfg)["r2_correct"])
    with open(path, encoding="utf-8") as f:
        return {k: set(v) for k, v in json.load(f).items()}


def read_text(path: str | os.PathLike) -> str:
    return resolve(path).read_text(encoding="utf-8")
