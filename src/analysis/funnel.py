"""Stage analysis: retrieved@20 -> top-5 -> cited -> attack success.

OWNER: Person 3 (Vatsal); Person 5 reuses it for Gap 2. Brief task 5.

Build on src/common/metrics.stage_funnel (same metric definitions as
scripts/summarize.py); add breakdowns per attack type AND question type, the
poisoned-vs-clean retrieval comparison, and pulling concrete examples.
"""

from __future__ import annotations

from typing import Any


def funnel_by(records: list[dict[str, Any]], keys: tuple[str, ...], r2_correct: set[str] | None = None):
    """{group: stage_funnel(...)} grouped by e.g. ("pipeline", "attack_type", "question_type")."""
    raise NotImplementedError("Person 3: funnel_by")


def retrieval_poison_vs_clean(attack_records: list[dict], clean_records: list[dict]) -> dict[str, Any]:
    """Poisoned page's retrieval rate vs the clean page's for the same questions (expect ~equal)."""
    raise NotImplementedError("Person 3: retrieval_poison_vs_clean")


def pick_examples(records: list[dict], n: int = 2) -> list[dict]:
    """Concrete successful attacks: question, edit, system answer, citation."""
    raise NotImplementedError("Person 3: pick_examples")
