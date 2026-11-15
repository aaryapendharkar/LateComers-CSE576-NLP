from __future__ import annotations

from typing import Any, Mapping, Optional

from ..common.metrics import _get, bootstrap_ci, fmt_rate, group_by, rate, rank_changes, which_version
from ..common.schemas import G2_ATTACK_TYPES

LABELS = ("text", "image", "both", "neither")


def _cond_idx(attack_type: str) -> int:
    return G2_ATTACK_TYPES.index(attack_type) if attack_type in G2_ATTACK_TYPES else len(G2_ATTACK_TYPES)


def _sort_key(kv):
    (pl, rr, at), _ = kv
    return pl, not rr, _cond_idx(at)


def _attack_field(attacks: Mapping[str, Any], attack_id: Optional[str], key: str) -> Any:
    a = attacks.get(attack_id) if attack_id else None
    return None if a is None else _get(a, key)


def label_runs(records: list[Mapping[str, Any]], attacks: Mapping[str, Any],
               rel_tol: float = 0.01) -> list[dict[str, Any]]:
    out = []
    for r in records:
        aid = _get(r, "attack_id")
        if _attack_field(attacks, aid, "gap") != "G2":
            continue
        img = _attack_field(attacks, aid, "image_answer")
        txt = _attack_field(attacks, aid, "text_answer")
        if img is None or txt is None:
            raise ValueError(f"{aid}: attack row needs image_answer and text_answer (schemas.layer_answers)")
        out.append({
            "qid": _get(r, "qid"), "attack_id": aid, "pipeline": _get(r, "pipeline"),
            "reranker": _get(r, "reranker"), "attack_type": _attack_field(attacks, aid, "attack_type"),
            "answer": _get(r, "answer"), "image_answer": img, "text_answer": txt,
            "label": which_version(_get(r, "answer"), img, txt, rel_tol=rel_tol),
        })
    return out


def which_wins_table(records: list[dict[str, Any]], attacks: dict[str, Any],
                     r2_correct: Optional[Mapping[str, set[str]]] = None,
                     rel_tol: float = 0.01, **ci_kw: Any) -> list[dict[str, Any]]:
    labelled = label_runs(records, attacks, rel_tol=rel_tol)
    if r2_correct is not None:
        labelled = [x for x in labelled if x["qid"] in r2_correct.get(x["pipeline"], set())]
    rows = []
    for (pl, rr, at), grp in sorted(group_by(labelled, "pipeline", "reranker", "attack_type").items(), key=_sort_key):
        row: dict[str, Any] = {"pipeline": pl, "reranker": rr, "attack_type": at, "n": len(grp)}
        for lab in LABELS:
            row[f"follows_{lab}"] = rate([x["label"] == lab for x in grp], **ci_kw)
        rows.append(row)
    return rows


def rank_shift_by_condition(attack_records: list[dict], clean_records: list[dict],
                            attacks: dict[str, Any], **ci_kw: Any) -> list[dict[str, Any]]:
    g2 = [{**r, "_attack_type": _attack_field(attacks, _get(r, "attack_id"), "attack_type")}
          for r in attack_records if _attack_field(attacks, _get(r, "attack_id"), "gap") == "G2"]
    rows = []
    for (pl, rr, at), grp in sorted(group_by(g2, "pipeline", "reranker", "_attack_type").items(), key=_sort_key):
        changes = rank_changes(grp, clean_records)
        point, lo, hi = bootstrap_ci(changes, **ci_kw) if changes else (float("nan"),) * 3
        rows.append({"pipeline": pl, "reranker": rr, "attack_type": at, "n": len(changes),
                     "mean_rank_change": point, "ci_low": lo, "ci_high": hi,
                     "share_moved": rate([c != 0 for c in changes], **ci_kw)})
    return rows


def to_markdown(rows: list[dict[str, Any]]) -> str:
    conds = sorted({r["attack_type"] for r in rows}, key=_cond_idx)
    lines = ["Cells: % follows text / % follows image / % both layers (propagate) / % neither  (n)", "",
             "| pipeline | " + " | ".join(conds) + " |", "|---|" + "---|" * len(conds)]
    by_key = {(r["pipeline"], r["reranker"], r["attack_type"]): r for r in rows}
    for pl, rr in sorted({(r["pipeline"], r["reranker"]) for r in rows}, key=lambda k: (k[0], not k[1])):
        cells = []
        for c in conds:
            r = by_key.get((pl, rr, c))
            cells.append("-" if r is None else " / ".join(
                f"{100 * r[f'follows_{lab}']['rate']:.0f}" for lab in LABELS) + f" (n={r['n']})")
        name = pl if rr else f"{pl} (no reranker)"
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += ["", "With 95% bootstrap CIs:", "",
              "| pipeline | reranker | condition | follows text | follows image | both | neither |",
              "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['pipeline']} | {'on' if r['reranker'] else 'off'} | {r['attack_type']} | "
                     + " | ".join(fmt_rate(r[f'follows_{lab}']) for lab in LABELS) + " |")
    return "\n".join(lines)


def rank_shift_markdown(rows: list[dict[str, Any]]) -> str:
    lines = ["| pipeline | reranker | condition | mean rank change [95% CI] | % pages moved |",
             "|---|---|---|---|---|"]
    for r in rows:
        mean = "n/a" if r["n"] == 0 else f"{r['mean_rank_change']:+.2f} [{r['ci_low']:+.2f}, {r['ci_high']:+.2f}]"
        lines.append(f"| {r['pipeline']} | {'on' if r['reranker'] else 'off'} | {r['attack_type']} | "
                     f"{mean} | {fmt_rate(r['share_moved'])} |")
    return "\n".join(lines)
