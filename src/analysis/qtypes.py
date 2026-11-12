"""Question-type labels: lookup / comparison / arithmetic / trend.

OWNER: Person 3 (Vatsal). Brief task 3.

FinQA rules: no operation or a single table value -> lookup; greater -> comparison;
arithmetic ops -> arithmetic; questions about change/growth/increase/decrease
across periods -> trend. ChartQA: same rules on the question text (LLM for unclear).
Hand-check 30 labels and report agreement.

Labels are written to data/labels/qtypes.jsonl as {"qid", "question_type"};
src/common/io.load_examples() overlays them, so Person 1's examples.jsonl is
never rewritten by two people.
"""

from __future__ import annotations

from typing import Optional


def label_finqa(question: str, program: Optional[str]) -> str:
    raise NotImplementedError("Person 3: label_finqa")


def label_chartqa(question: str) -> str:
    raise NotImplementedError("Person 3: label_chartqa")
