"""P3 (hybrid): reciprocal-rank fusion of the P1 and P2 rankings. OWNER: Person 1."""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence


def rrf(rankings: Sequence[Sequence[str]], k: int = 60, top: int | None = None) -> list[tuple[str, float]]:
    """Reciprocal rank fusion: score(d) = sum_r 1 / (k + rank_r(d)), ranks 1-based."""
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for i, pid in enumerate(ranking, start=1):
            scores[pid] += 1.0 / (k + i)
    fused = sorted(scores.items(), key=lambda t: (-t[1], t[0]))
    return fused[:top] if top else fused
