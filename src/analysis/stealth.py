"""Stealth study (pilot): 20 clean + 20 poisoned page images, "looks edited" vs "looks normal".

OWNER: Person 3 (Vatsal). Brief task 4.
Annotators: Persons 1, 4, 5 (they didn't create the edits). Form out Sat 10 am.
Report Fleiss' kappa (statsmodels.stats.inter_rater.fleiss_kappa) and detection
accuracy vs chance (binomial test).
"""

from __future__ import annotations

from typing import Any


def sample_pages(n_clean: int = 20, n_poison: int = 20, seed: int = 576) -> list[dict[str, Any]]:
    """Shuffled list of {"item", "page_id", "is_poisoned"}; no clean twin of a poisoned page."""
    raise NotImplementedError("Person 3: sample_pages")


def analyze(annotations: list[dict[str, Any]]) -> dict[str, float]:
    """annotations: {"annotator", "item", "label": "edited"|"normal"} -> kappa, accuracy, p-value."""
    raise NotImplementedError("Person 3: analyze")
