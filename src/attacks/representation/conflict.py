"""Gap 2 table conditions built on Person 2's consistent edits.

OWNER: Person 4 (Aaron). Brief task 4.

  propagate_table  = Person 2's consistent_cell page (image + text poisoned):
                     just add a G2 row pointing at the existing page
  text_only_table  : image = clean, text = poisoned
  image_only_table : image = poisoned, text = clean

Every row records gold_answer, image_answer, text_answer
(use schemas.layer_answers) so Person 5 can tell which layer the system followed.
Rows go to data/attacks/g2.jsonl, pages to data/manifests/pages_g2.jsonl.
"""

from __future__ import annotations

from ...common.schemas import Attack, Doc


def make_table_conditions(g1_consistent: Attack, doc: Doc, gold_answer: str, pages_dir: str) -> list[Attack]:
    """Three G2 rows (propagate / text_only / image_only) from one consistent_cell attack."""
    raise NotImplementedError("Person 4: make_table_conditions")
