"""Gap 2 "which version wins": does each pipeline follow the image or the text layer?

OWNER: Person 5 (Disha). Brief task 3.

Per run: answer matches image_answer / text_answer / neither
(use src/common/metrics.which_version). Table: rows P1, P2, P3; columns
text_only, image_only, propagate; cells % follows-text / % follows-image / % neither.
Also: does a text-only edit change P1's rank? an image-only edit P2's?
"""

from __future__ import annotations

from typing import Any


def which_wins_table(records: list[dict[str, Any]], attacks: dict[str, Any]) -> list[dict[str, Any]]:
    raise NotImplementedError("Person 5: which_wins_table")


def rank_shift_by_condition(attack_records: list[dict], clean_records: list[dict],
                            attacks: dict[str, Any]) -> list[dict[str, Any]]:
    raise NotImplementedError("Person 5: rank_shift_by_condition")
