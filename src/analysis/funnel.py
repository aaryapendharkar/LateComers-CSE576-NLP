"""Stage analysis: retrieved@20 -> top-5 -> cited -> attack success.

OWNER: Person 3 (Vatsal); Person 5 reuses it for Gap 2. Brief task 5.

Builds on src/common/metrics.stage_funnel (same metric definitions as
scripts/summarize.py) and adds: breakdowns by any record field (attack type,
question type, tables vs charts), the poisoned-vs-clean retrieval comparison,
and concrete examples for the report.

Run-log records (A6) carry no attack_type or question_type, so call
``annotate()`` first. Every function takes plain dicts.

The ASR denominator is fixed: the qids answered correctly by the UNDEFENDED
clean run (R2) of the same pipeline. A defended run (D1 filter) must be scored
against that same set, never against its own clean accuracy.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..common import metrics as M

def _g(obj: Any, key: str, default: Any = None) -> Any:
    return obj.get(key, default) if isinstance(obj, Mapping) else getattr(obj, key, default)


def annotate(records: list[dict[str, Any]], attacks: Mapping[str, Any] | None = None,
             examples: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Copies of the run-log records with attack_type, source and question_type added.

    ``attacks``: {attack_id: Attack or dict}; ``examples``: {qid: Example or dict}
    (as returned by src.common.io.load_attacks / load_examples). Unknown ids get "?".
    """
    out = []
    for r in records:
        r = dict(r)
        a = (attacks or {}).get(r.get("attack_id"))
        e = (examples or {}).get(r.get("qid"))
        r["attack_type"] = _g(a, "attack_type", "?") if a is not None else ("clean" if not r.get("attack_id") else "?")
        r["question_type"] = (_g(e, "question_type") or "?") if e is not None else "?"
        r["source"] = _g(e, "source", "?") if e is not None else "?"
        out.append(r)
    return out


def _keep(r2_correct: Any, pipeline: str) -> set[str] | None:
    if r2_correct is None:
        return None
    if isinstance(r2_correct, Mapping):
        return set(r2_correct.get(pipeline, set()))
    return set(r2_correct)


def funnel_by(records: list[dict[str, Any]], keys: tuple[str, ...], r2_correct: Any = None, **kw: Any):
    """{group: stage_funnel(...)} grouped by e.g. ("pipeline", "attack_type", "question_type").

    Only attack records are used. ``r2_correct`` is a set of qids, or
    {pipeline: set} as in results/r2_correct.json. Each group's value holds the
    four funnel stages plus:
      "adoption|top5"            cited the poisoned page, among runs where it reached top-5
      "target_without_citation"  answer matches the target but the poisoned page is not cited
    Every entry is a metrics.rate dict ({"rate", "ci_low", "ci_high", "n"}).
    """
    recs = [r for r in records if r.get("attack_id")]
    out = {}
    for group, rs in sorted(M.group_by(recs, *keys).items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        kept = []
        for r in rs:
            keep = _keep(r2_correct, r.get("pipeline"))
            if keep is None or r.get("qid") in keep:
                kept.append(r)
        f = dict(M.stage_funnel(kept, None, **kw))
        f["adoption|top5"] = M.rate(M.evidence_adoption_flags(kept), **kw)
        f["target_without_citation"] = M.rate(
            [bool(r.get("matches_target")) and r.get("poison_page_id") not in (r.get("cited") or []) for r in kept], **kw)
        out[group] = f
    return out


def retrieval_poison_vs_clean(attack_records: list[dict], clean_records: list[dict], **kw: Any) -> dict[str, Any]:
    """Poisoned page's retrieval rate vs the clean page's for the same questions (expect ~equal).

    Pairs each attack run with the clean (R2) run of the same qid, pipeline and
    reranker setting. Returns rates at top-20 and top-5 for both, and the mean
    retriever rank change (poisoned minus clean; a missing rank counts as 21).
    """
    clean = {(r.get("qid"), r.get("pipeline"), r.get("reranker")): r for r in clean_records if not r.get("attack_id")}
    pairs = [(a, clean[k]) for a in attack_records if a.get("attack_id")
             for k in [(a.get("qid"), a.get("pipeline"), a.get("reranker"))] if k in clean]
    atk, cln = [a for a, _ in pairs], [c for _, c in pairs]
    changes = M.rank_changes(atk, cln)
    mean = M.bootstrap_ci(changes, **kw) if changes else (float("nan"),) * 3
    return {
        "n_pairs": len(pairs),
        "n_attack_runs_without_clean_run": sum(1 for a in attack_records if a.get("attack_id")) - len(pairs),
        "poison_retrieved@20": M.rate(M.poison_retrieved_flags(atk, 20), **kw),
        "clean_retrieved@20": M.rate(M.recall_flags(cln, 20, "retr"), **kw),
        "poison_top5": M.rate(M.reranker_survival_flags(atk, 5), **kw),
        "clean_top5": M.rate(M.recall_flags(cln, 5, "rerank"), **kw),
        "mean_rank_change": {"mean": mean[0], "ci_low": mean[1], "ci_high": mean[2], "n": len(changes)},
        "share_same_rank": M.rate([c == 0 for c in changes], **kw),
    }


def asr_with_defense(undefended: list[dict], defended: list[dict], r2_correct: Any = None, **kw: Any) -> dict[str, Any]:
    """ASR without and with a defense filter, over the SAME fixed R2-correct denominator.

    Also reports how often the filter dropped the poisoned page and how often it
    dropped any top-5 page. The accuracy cost of the filter on clean questions
    is a separate number: score the defended clean run for that.
    """
    def kept(rs: list[dict]) -> list[dict]:
        out = []
        for r in rs:
            keep = _keep(r2_correct, r.get("pipeline"))
            if r.get("attack_id") and (keep is None or r.get("qid") in keep):
                out.append(r)
        return out

    u, d = kept(undefended), kept(defended)
    return {
        "asr_undefended": M.rate([bool(r.get("matches_target")) for r in u], **kw),
        "asr_defended": M.rate([bool(r.get("matches_target")) for r in d], **kw),
        "poison_page_dropped": M.rate([r.get("poison_page_id") in (r.get("filtered_pages") or []) for r in d], **kw),
        "runs_with_any_page_dropped": M.rate([bool(r.get("filtered_pages")) for r in d], **kw),
    }


def pick_examples(records: list[dict], n: int = 2, attacks: Mapping[str, Any] | None = None,
                  examples: Mapping[str, Any] | None = None) -> list[dict]:
    """Concrete successful attacks: question, edit, system answer, citation.

    Deterministic: successful runs (answer matches the target) that cite the
    poisoned page come first, then other successes, each sorted by attack_id;
    at most one example per attack type until every type has one.
    """
    wins = [r for r in records if r.get("attack_id") and r.get("matches_target")]
    wins.sort(key=lambda r: (r.get("poison_page_id") not in (r.get("cited") or []), str(r.get("attack_id"))))
    chosen, seen = [], set()
    for want_new_type in (True, False):
        for r in wins:
            a = (attacks or {}).get(r["attack_id"])
            t = _g(a, "attack_type", r.get("attack_type", "?")) if a is not None else r.get("attack_type", "?")
            if len(chosen) >= n or r in chosen or (want_new_type and t in seen):
                continue
            seen.add(t)
            e = (examples or {}).get(r.get("qid"))
            chosen.append({
                "qid": r.get("qid"), "attack_id": r["attack_id"], "attack_type": t, "pipeline": r.get("pipeline"),
                "question": _g(e, "question") if e is not None else None,
                "gold_answer": _g(e, "gold_answer") if e is not None else None,
                "target_answer": _g(a, "target_answer") if a is not None else None,
                "edit": _g(a, "edit") if a is not None else None,
                "system_answer": r.get("answer"), "cited": r.get("cited"),
                "poison_page_id": r.get("poison_page_id"),
                "cited_poisoned_page": r.get("poison_page_id") in (r.get("cited") or []),
                "poison_rank_retr": r.get("poison_rank_retr"), "poison_rank_rerank": r.get("poison_rank_rerank"),
            })
    return chosen
