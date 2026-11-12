"""Shared data formats (Part A, section A6 of the task briefs).

OWNER: Person 1 (Aarya). These dataclasses are the CONTRACT between teammates.
Do not rename or remove fields without telling the whole group first.
Adding a new *optional* field (with a default) is fine; mention it in your PR.

Every record is stored as one JSON object per line (JSONL). Use
``Record.from_dict(d)`` to validate a dict you read, and ``record.to_dict()``
before writing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, ClassVar, Optional

# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------

PIPELINES = ("P1", "P2", "P3")
SOURCES = ("finqa", "chartqa")
GAPS = ("G1", "G2")

G1_ATTACK_TYPES = ("consistent_cell", "naive_cell", "unit", "header")
G2_ATTACK_TYPES = (
    "propagate_table",
    "text_only_table",
    "image_only_table",
    "propagate_chart",
    "text_only_chart",
    "image_only_chart",
)
ATTACK_TYPES = G1_ATTACK_TYPES + G2_ATTACK_TYPES

QUESTION_TYPES = ("lookup", "comparison", "arithmetic", "trend")
LAYER_VERSIONS = ("clean", "poison")

# Which (image_version, text_version) each attack type must have (A4).
ATTACK_LAYERS: dict[str, tuple[str, str]] = {
    **{t: ("poison", "poison") for t in G1_ATTACK_TYPES},
    "propagate_table": ("poison", "poison"),
    "text_only_table": ("clean", "poison"),
    "image_only_table": ("poison", "clean"),
    "propagate_chart": ("poison", "poison"),
    "text_only_chart": ("clean", "poison"),
    "image_only_chart": ("poison", "clean"),
}


class SchemaError(ValueError):
    """Raised when a record does not match the shared format."""


# ---------------------------------------------------------------------------
# ID helpers: use these instead of formatting ids by hand
# ---------------------------------------------------------------------------

def clean_page_id(doc_id: str) -> str:
    """``finqa_ABC_2019_p12`` -> ``finqa_ABC_2019_p12__clean``."""
    return f"{doc_id}__clean"


def attack_id(gap: str, attack_type: str, qid: str) -> str:
    """``attack_id("G1", "consistent_cell", "q0001")`` -> ``G1_consistent_cell_q0001``."""
    if gap not in GAPS:
        raise SchemaError(f"unknown gap {gap!r}")
    if attack_type not in ATTACK_TYPES:
        raise SchemaError(f"unknown attack_type {attack_type!r}")
    return f"{gap}_{attack_type}_{qid}"


def poison_page_id(doc_id: str, gap: str, attack_type: str, qid: str) -> str:
    """Page id of a poisoned page: ``<doc_id>__<attack_id>``."""
    return f"{doc_id}__{attack_id(gap, attack_type, qid)}"


def doc_id_of_page(page_id: str) -> str:
    """Inverse of the page id helpers: everything before the first ``__``."""
    return page_id.split("__", 1)[0]


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class _Record:
    """Mixin giving dataclasses dict round-tripping + light validation."""

    REQUIRED: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def from_dict(cls, d: dict[str, Any], strict: bool = False):
        missing = [k for k in cls.REQUIRED if k not in d]
        if missing:
            raise SchemaError(f"{cls.__name__} missing required fields {missing}: {str(d)[:200]}")
        known = {f.name for f in fields(cls)}  # type: ignore[arg-type]
        unknown = set(d) - known
        if unknown and strict:
            raise SchemaError(f"{cls.__name__} has unknown fields {sorted(unknown)}")
        obj = cls(**{k: v for k, v in d.items() if k in known})  # type: ignore[call-arg]
        if unknown:
            obj.extra = {k: d[k] for k in unknown}  # type: ignore[attr-defined]
        obj.validate()
        return obj

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)  # type: ignore[call-overload]
        extra = d.pop("extra", None) or {}
        d.update(extra)
        return d

    def validate(self) -> None:  # overridden where useful
        return None


# ---------------------------------------------------------------------------
# data/docs.jsonl  (Person 1 writes for FinQA; Person 4 writes chart docs)
# ---------------------------------------------------------------------------

@dataclass
class Table(_Record):
    header: list[str]
    rows: list[list[str]]
    title: str = ""
    unit_note: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    REQUIRED: ClassVar[tuple[str, ...]] = ("header", "rows")

    def validate(self) -> None:
        width = len(self.header)
        for i, r in enumerate(self.rows):
            if len(r) != width:
                raise SchemaError(f"table row {i} has {len(r)} cells, header has {width}")

    @property
    def n_rows(self) -> int:
        return len(self.rows)

    @property
    def n_cols(self) -> int:
        return len(self.header)


@dataclass
class Doc(_Record):
    doc_id: str
    source: str
    table: dict[str, Any]
    pre_text: str = ""
    post_text: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    REQUIRED: ClassVar[tuple[str, ...]] = ("doc_id", "source", "table")

    def validate(self) -> None:
        if self.source not in SOURCES:
            raise SchemaError(f"doc {self.doc_id}: unknown source {self.source!r}")
        Table.from_dict(self.table)

    def table_obj(self) -> Table:
        return Table.from_dict(self.table)


# ---------------------------------------------------------------------------
# data/examples.jsonl  (Person 1 writes; question_type overlay by Person 3)
# ---------------------------------------------------------------------------

@dataclass
class Example(_Record):
    qid: str
    source: str
    question: str
    gold_answer: str
    doc_id: str
    program: Optional[str] = None
    question_type: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)

    REQUIRED: ClassVar[tuple[str, ...]] = ("qid", "source", "question", "gold_answer", "doc_id")

    def validate(self) -> None:
        if self.question_type is not None and self.question_type not in QUESTION_TYPES:
            raise SchemaError(f"{self.qid}: bad question_type {self.question_type!r}")


# ---------------------------------------------------------------------------
# data/manifests/pages_*.jsonl  (written via Person 4's renderer)
# ---------------------------------------------------------------------------

@dataclass
class Page(_Record):
    page_id: str
    doc_id: str
    variant: str              # "clean" or the attack_id
    image_version: str        # "clean" | "poison"
    text_version: str         # "clean" | "poison"
    pdf_path: str
    image_path: str
    text_path: str            # renderer's text-layer strings in reading order (debug)
    caption: str = ""
    table_json_path: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    REQUIRED: ClassVar[tuple[str, ...]] = (
        "page_id", "doc_id", "variant", "image_version", "text_version",
        "pdf_path", "image_path", "text_path",
    )

    def validate(self) -> None:
        for v in (self.image_version, self.text_version):
            if v not in LAYER_VERSIONS:
                raise SchemaError(f"page {self.page_id}: bad layer version {v!r}")


# ---------------------------------------------------------------------------
# data/attacks/g1.jsonl (Person 2) and data/attacks/g2.jsonl (Person 4)
# ---------------------------------------------------------------------------

@dataclass
class Attack(_Record):
    attack_id: str
    qid: str
    gap: str
    attack_type: str
    clean_page_id: str
    poison_page_id: str
    edit: dict[str, Any]
    target_answer: str
    image_version: str
    text_version: str
    # Optional (needed by Gap 2 "which version wins"; Person 4 fills them):
    gold_answer: Optional[str] = None
    image_answer: Optional[str] = None   # answer implied by the IMAGE layer
    text_answer: Optional[str] = None    # answer implied by the TEXT layer
    extra: dict[str, Any] = field(default_factory=dict)

    REQUIRED: ClassVar[tuple[str, ...]] = (
        "attack_id", "qid", "gap", "attack_type", "clean_page_id",
        "poison_page_id", "edit", "target_answer", "image_version", "text_version",
    )

    def validate(self) -> None:
        if self.gap not in GAPS:
            raise SchemaError(f"{self.attack_id}: bad gap {self.gap!r}")
        if self.attack_type not in ATTACK_TYPES:
            raise SchemaError(f"{self.attack_id}: bad attack_type {self.attack_type!r}")
        expected = ATTACK_LAYERS[self.attack_type]
        if (self.image_version, self.text_version) != expected:
            raise SchemaError(
                f"{self.attack_id}: {self.attack_type} needs (image, text) = {expected}, "
                f"got {(self.image_version, self.text_version)}"
            )


def layer_answers(attack_type: str, gold: str, target: str) -> tuple[str, str]:
    """Return (image_answer, text_answer) for an attack type, given gold and target."""
    img_v, txt_v = ATTACK_LAYERS[attack_type]
    return (target if img_v == "poison" else gold, target if txt_v == "poison" else gold)


# ---------------------------------------------------------------------------
# results/runs/<pipeline>_<run_name>.jsonl  (Person 1's runner writes)
# ---------------------------------------------------------------------------

@dataclass
class RunRecord(_Record):
    qid: str
    attack_id: Optional[str]
    pipeline: str
    reranker: bool
    generator: str
    top20: list[str]
    top5: list[str]
    gold_rank_retr: Optional[int]
    gold_rank_rerank: Optional[int]
    poison_rank_retr: Optional[int]
    poison_rank_rerank: Optional[int]
    answer_raw: str
    answer: Optional[str]
    cited: list[str]
    correct: bool
    matches_target: Optional[bool]
    latency_s: float
    # Optional additions (not in A6, but useful for analysis):
    mode: str = "rag"                    # "rag" (R2/attacks) | "closed_book" (R1) | "oracle" (R3)
    run_name: str = ""
    poison_page_id: Optional[str] = None
    filtered_pages: list[str] = field(default_factory=list)  # pages a defense dropped
    extra: dict[str, Any] = field(default_factory=dict)

    REQUIRED: ClassVar[tuple[str, ...]] = (
        "qid", "attack_id", "pipeline", "reranker", "generator", "top20", "top5",
        "gold_rank_retr", "gold_rank_rerank", "poison_rank_retr", "poison_rank_rerank",
        "answer_raw", "answer", "cited", "correct", "matches_target", "latency_s",
    )

    def validate(self) -> None:
        if self.pipeline not in PIPELINES:
            raise SchemaError(f"bad pipeline {self.pipeline!r}")
