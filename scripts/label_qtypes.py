#!/usr/bin/env python
"""Person 3 (Vatsal): question-type labels -> data/labels/qtypes.jsonl (Fri)."""
import _bootstrap  # noqa: F401
from collections import Counter

from src.analysis.qtypes import label_chartqa, label_finqa
from src.common.config import get_config
from src.common.io import load_examples, write_jsonl


def main():
    cfg = get_config()
    labels = []
    for qid, ex in sorted(load_examples(cfg, with_qtypes=False).items()):
        qt = label_finqa(ex.question, ex.program) if ex.source == "finqa" else label_chartqa(ex.question)
        labels.append({"qid": qid, "question_type": qt})
    write_jsonl(cfg["paths"]["qtypes"], labels)
    print(Counter(l["question_type"] for l in labels), "->", cfg["paths"]["qtypes"])


if __name__ == "__main__":
    main()
