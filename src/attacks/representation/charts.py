"""Gap 2 chart attacks: change the asked-about value by a visible but plausible amount.

OWNER: Person 4 (Aaron). Brief task 5. target_answer = the new value.
Conditions: propagate_chart, text_only_chart (chart + note image clean, text
layer poisoned), image_only_chart. Edit format: a cell edit (src/common/edits.py).
"""

from __future__ import annotations

from ...common.schemas import Attack, Doc, Example


def select_chartqa_questions(n: int = 100) -> list[Example]:
    """Human-written test questions whose answer equals one value in the chart CSV."""
    raise NotImplementedError("Person 4: select_chartqa_questions")


def make_chart_conditions(ex: Example, doc: Doc, pages_dir: str) -> list[Attack]:
    raise NotImplementedError("Person 4: make_chart_conditions")
