"""Gap 2 PROPAGATION condition for tables (Person 4; conflicts are Person 5's).

Propagation = edit the source data, then re-render the image, the text layer
and the caption from it. For tables the edit is Person 2's consistent_cell
edit (dependent totals updated). The page is rendered under its own G2 id
(``<doc>__G2_propagate_table_<qid>``) into Person 4's manifest, so it does not
depend on Person 2 rendering pages_g1.jsonl; its content equals the G1
consistent_cell page (same renderer, same edit).

Charts: ``charts.make_chart_conditions(..., conditions=("propagate_chart",))``.
"""

from __future__ import annotations

from typing import Callable, Optional

from ...common.edits import apply_edit
from ...common.schemas import ATTACK_LAYERS, Attack, Doc, attack_id, layer_answers, poison_page_id


def select_table_attack_sources(cfg: dict, limit: Optional[int] = None,
                                only_r2_correct: bool = False) -> list[Attack]:
    """Person 2's consistent_cell attacks that get G2 rows, in a fixed order.

    Same rule as Person 5's make_g2_attacks.make_tables (sorted by attack_id,
    optional union-of-pipelines R2 filter, first ``attacks_g2.n_table_questions``)
    so propagate and conflict rows cover the same questions."""
    from ...common.io import load_attacks, load_r2_correct

    g1 = sorted((a for a in load_attacks(cfg, gap="G1").values() if a.attack_type == "consistent_cell"),
                key=lambda a: a.attack_id)
    if only_r2_correct:
        r2 = load_r2_correct(cfg)
        keep = set().union(*r2.values()) if r2 else set()
        g1 = [a for a in g1 if a.qid in keep]
    return g1[: limit or (cfg.get("attacks_g2") or {}).get("n_table_questions", 50)]


def make_table_propagation(g1_consistent: Attack, doc: Doc, gold_answer: str, pages_dir: str,
                           render: Optional[Callable[..., dict]] = None,
                           page_sink: Optional[list[dict]] = None) -> Attack:
    """One propagate_table row (+ its rendered page) from one consistent_cell attack."""
    if g1_consistent.attack_type != "consistent_cell":
        raise ValueError(f"{g1_consistent.attack_id}: Gap 2 builds on consistent_cell edits only")
    if render is None:
        from ...render.render_table_page import render_table_page as render
    at = "propagate_table"
    d = doc.to_dict()
    poisoned = apply_edit(d, g1_consistent.edit)
    pp = (poisoned.get("pre_text", ""), poisoned.get("post_text", ""))
    pid = poison_page_id(d["doc_id"], "G2", at, g1_consistent.qid)
    rec = render(d, pid, pages_dir, image_table=poisoned["table"], text_table=poisoned["table"],
                 image_pre_post=pp, text_pre_post=pp)
    if page_sink is not None:
        page_sink.append(rec)
    img_v, txt_v = ATTACK_LAYERS[at]
    target = g1_consistent.target_answer
    img_a, txt_a = layer_answers(at, gold_answer, target)
    from ...render.render_table_page import table_caption
    a = Attack(attack_id=attack_id("G2", at, g1_consistent.qid), qid=g1_consistent.qid, gap="G2",
               attack_type=at, clean_page_id=g1_consistent.clean_page_id, poison_page_id=pid,
               edit=g1_consistent.edit, target_answer=target, image_version=img_v, text_version=txt_v,
               gold_answer=gold_answer, image_answer=img_a, text_answer=txt_a,
               extra={"source_attack": g1_consistent.attack_id,
                      "caption_shows_edit": table_caption(poisoned["table"]) != table_caption(d["table"])})
    a.validate()
    return a
