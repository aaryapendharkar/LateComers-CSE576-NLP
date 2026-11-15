from __future__ import annotations

from typing import Any, Callable, Optional

from ...common.edits import apply_edit
from ...common.schemas import ATTACK_LAYERS, Attack, Doc, attack_id, layer_answers, poison_page_id

TABLE_CONFLICTS = ("text_only_table", "image_only_table")
CHART_CONFLICTS = ("text_only_chart", "image_only_chart")


def _pre_post(doc: dict[str, Any]) -> tuple[str, str]:
    return doc.get("pre_text", ""), doc.get("post_text", "")


def make_table_conditions(g1_consistent: Attack, doc: Doc, gold_answer: str, pages_dir: str,
                          render: Optional[Callable[..., dict]] = None,
                          page_sink: Optional[list[dict]] = None) -> list[Attack]:
    if g1_consistent.attack_type != "consistent_cell":
        raise ValueError(f"{g1_consistent.attack_id}: Gap 2 builds on consistent_cell edits only")
    if render is None:
        from ...render.render_table_page import render_table_page as render

    d = doc.to_dict()
    poisoned = apply_edit(d, g1_consistent.edit)
    layers = {"clean": (d["table"], _pre_post(d)), "poison": (poisoned["table"], _pre_post(poisoned))}
    qid, target = g1_consistent.qid, g1_consistent.target_answer

    out = []
    for at in TABLE_CONFLICTS:
        img_v, txt_v = ATTACK_LAYERS[at]
        (img_t, img_pp), (txt_t, txt_pp) = layers[img_v], layers[txt_v]
        pid = poison_page_id(d["doc_id"], "G2", at, qid)
        rec = render(d, pid, pages_dir, image_table=img_t, text_table=txt_t,
                     image_pre_post=img_pp, text_pre_post=txt_pp)
        if page_sink is not None:
            page_sink.append(rec)
        img_a, txt_a = layer_answers(at, gold_answer, target)
        a = Attack(attack_id=attack_id("G2", at, qid), qid=qid, gap="G2", attack_type=at,
                   clean_page_id=g1_consistent.clean_page_id, poison_page_id=pid,
                   edit=g1_consistent.edit, target_answer=target,
                   image_version=img_v, text_version=txt_v,
                   gold_answer=gold_answer, image_answer=img_a, text_answer=txt_a,
                   extra={"source_attack": g1_consistent.attack_id})
        a.validate()
        out.append(a)
    return out
