"""Stealth pilot analysis helpers (Person 3). Standard library only.

Design (see docs/person3/ANALYSIS_PLAN.md):
  * Ratings sheet (from annotators) and answer key (kept by Person 3) are
    separate files joined only here, so raters never see conditions.
  * The PAGE is the unit of analysis. Three ratings of one page are not three
    independent observations, so the primary test uses one majority-vote
    decision per page (40 pages), not 120 ratings.
  * A non-significant result means "no evidence that raters beat chance with
    this sample", NOT "the edits are undetectable". Report power alongside.
  * Input is validated before any statistic is computed: one rating per
    (rater, item), exactly `raters_per_item` distinct raters on every answer-key
    item (3 in the pilot design), unique answer-key items, allowed labels and
    required fields. Invalid sheets are rejected, never silently de-duplicated.

OWNER: Person 3 (Vatsal). Departure from the repo skeleton (documented in
docs/person3/HANDOFF.md): `analyze` takes the ratings AND the private answer key
as two arguments. Accuracy cannot be computed from annotations alone, and
putting the truth into rater rows would leak conditions. `sample_pages` picks
the pilot items from the G1 attacks; copying the page images needs Person 4's
rendered pages (scripts/stealth_study.py build).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from math import comb

EDITED, NORMAL = "looks_edited", "looks_normal"
CATEGORIES = (EDITED, NORMAL)


def fleiss_kappa(counts: list[list[int]]) -> float:
    """Fleiss' kappa. counts[i][j] = raters assigning item i to category j.

    Every item must have the same number of raters.
    """
    n_items = len(counts)
    n_raters = sum(counts[0])
    if n_items == 0 or n_raters < 2 or any(sum(row) != n_raters for row in counts):
        raise ValueError("each item needs the same number (>=2) of ratings")
    n_cat = len(counts[0])
    p_j = [sum(row[j] for row in counts) / (n_items * n_raters) for j in range(n_cat)]
    p_i = [(sum(c * c for c in row) - n_raters) / (n_raters * (n_raters - 1)) for row in counts]
    p_bar = sum(p_i) / n_items
    p_e = sum(p * p for p in p_j)
    if p_e == 1:
        return float("nan")  # everyone used one category: kappa undefined
    return (p_bar - p_e) / (1 - p_e)


def binom_sf(k: int, n: int, p: float = 0.5) -> float:
    """P(X >= k) for X ~ Binomial(n, p): one-sided exact p-value."""
    return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(max(k, 0), n + 1))


def critical_k(n: int, alpha: float = 0.05, p0: float = 0.5) -> int:
    """Smallest number correct that is significant at `alpha` (one-sided)."""
    return next(k for k in range(n + 2) if binom_sf(k, n, p0) <= alpha)


def power(n: int, p_true: float, alpha: float = 0.05, p0: float = 0.5) -> float:
    """Probability the one-sided exact test rejects when true accuracy is p_true."""
    k = critical_k(n, alpha, p0)
    return binom_sf(k, n, p_true) if k <= n else 0.0


RATING_FIELDS = ("rater_id", "item_id", "rating")
KEY_FIELDS = ("item_id", "is_poisoned")
PILOT_RATERS_PER_ITEM = 3


class StealthInputError(ValueError):
    """The ratings sheet or answer key cannot be analysed as designed."""


def validate(ratings: list[dict], key: list[dict], raters_per_item: int = PILOT_RATERS_PER_ITEM) -> None:
    """Raise StealthInputError listing every problem found."""
    problems: list[str] = []
    if not ratings:
        problems.append("ratings sheet is empty")
    if not key:
        problems.append("answer key is empty")
    for i, k in enumerate(key):
        missing = [f for f in KEY_FIELDS if f not in k or k[f] in (None, "")]
        if missing:
            problems.append(f"answer key row {i}: missing field(s) {missing}")
        elif not isinstance(k["is_poisoned"], bool):
            problems.append(f"answer key row {i}: is_poisoned must be true/false, got {k['is_poisoned']!r}")
    key_ids = Counter(k.get("item_id") for k in key)
    problems += [f"duplicate item_id in answer key: {i!r} x{n}" for i, n in key_ids.items() if n > 1]

    pairs: Counter = Counter()
    raters_by_item: dict[str, set] = defaultdict(set)
    for i, r in enumerate(ratings):
        missing = [f for f in RATING_FIELDS if f not in r or r[f] in (None, "")]
        if missing:
            problems.append(f"rating row {i}: missing field(s) {missing}")
            continue
        if r["item_id"] not in key_ids:
            problems.append(f"rating row {i}: rating for unknown item {r['item_id']!r}")
        if r["rating"] not in CATEGORIES:
            problems.append(f"rating row {i}: invalid rating {r['rating']!r} (allowed: {list(CATEGORIES)})")
        pairs[(r["rater_id"], r["item_id"])] += 1
        raters_by_item[r["item_id"]].add(r["rater_id"])
    problems += [f"duplicate rating: rater {rid!r} rated item {iid!r} {n} times"
                 for (rid, iid), n in pairs.items() if n > 1]
    for item in key_ids:
        n = len(raters_by_item.get(item, ()))
        if n == 0 and ratings:
            problems.append(f"item {item!r} has no ratings")
        elif n and n != raters_per_item:
            problems.append(f"item {item!r} has {n} distinct raters; the design requires {raters_per_item}")
    if problems:
        raise StealthInputError("invalid stealth input: " + "; ".join(problems))


def analyze(ratings: list[dict], key: list[dict], raters_per_item: int = PILOT_RATERS_PER_ITEM) -> dict:
    """ratings: {rater_id, item_id, rating}; key: {item_id, is_poisoned (bool), condition, doc_id}.

    raters_per_item other than 3 must be a documented change to the pilot design.
    """
    validate(ratings, key, raters_per_item)
    truth = {k["item_id"]: k for k in key}
    by_item: dict[str, list[str]] = defaultdict(list)
    for r in ratings:
        by_item[r["item_id"]].append(r["rating"])
    counts = [[Counter(v)[c] for c in CATEGORIES] for v in by_item.values()]

    page_correct = 0
    for item, votes in by_item.items():
        majority_edited = Counter(votes)[EDITED] * 2 > len(votes)
        page_correct += majority_edited == bool(truth[item]["is_poisoned"])
    n_pages = len(by_item)

    per_rater = defaultdict(lambda: {"tp": 0, "fn": 0, "tn": 0, "fp": 0})
    for r in ratings:
        poisoned, said_edited = bool(truth[r["item_id"]]["is_poisoned"]), r["rating"] == EDITED
        cell = ("tp" if said_edited else "fn") if poisoned else ("fp" if said_edited else "tn")
        per_rater[r["rater_id"]][cell] += 1

    return {
        "raters_per_item": raters_per_item,
        "n_distinct_raters": len(per_rater),
        "n_pages_rated": n_pages,
        "n_ratings": len(ratings),
        "fleiss_kappa": fleiss_kappa(counts),
        "page_majority_accuracy": page_correct / n_pages,
        "page_majority_correct": page_correct,
        "one_sided_binomial_p": binom_sf(page_correct, n_pages),
        "critical_correct_for_alpha_0.05": critical_k(n_pages),
        "power_if_true_accuracy_0.65": power(n_pages, 0.65),
        "power_if_true_accuracy_0.75": power(n_pages, 0.75),
        "per_rater": {
            rid: {**c,
                  "sensitivity": c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else None,
                  "specificity": c["tn"] / (c["tn"] + c["fp"]) if c["tn"] + c["fp"] else None}
            for rid, c in per_rater.items()
        },
        "interpretation_guardrail": "A non-significant result is inconclusive; it does not show the edits are undetectable.",
    }


def sample_pages(n_clean: int = 20, n_poison: int = 20, seed: int = 576, cfg: dict | None = None,
                 attacks: dict | None = None, clean_doc_ids: list[str] | None = None) -> list[dict]:
    """Shuffled pilot items; no page is shown together with its clean twin.

    Returns [{"item", "page_id", "doc_id", "is_poisoned", "condition"}] with
    opaque item ids ("S01", ...). Poisoned pages: half naive_cell, half
    consistent_cell, each from a different document. Naive edits are taken
    first from pairs whose consistent twin updates a total, because only those
    leave a stale total on the page (the other naive pages are identical to
    their consistent twin). Clean pages come from documents that contribute no
    poisoned page. ``attacks`` ({attack_id: Attack or dict}) and
    ``clean_doc_ids`` default to the project's G1 attacks and FinQA documents.
    """
    import random

    if attacks is None or clean_doc_ids is None:
        from ..common.io import load_attacks, load_docs
        attacks = load_attacks(cfg, gap="G1") if attacks is None else attacks
        clean_doc_ids = sorted(load_docs(cfg, ("finqa",))) if clean_doc_ids is None else clean_doc_ids

    def get(a, k):
        return a.get(k) if isinstance(a, dict) else getattr(a, k)

    rng = random.Random(seed)
    by_qid: dict[str, dict] = defaultdict(dict)
    for a in attacks.values():
        if get(a, "attack_type") in ("naive_cell", "consistent_cell"):
            by_qid[get(a, "qid")][get(a, "attack_type")] = a
    stale = {q for q, v in by_qid.items()
             if "consistent_cell" in v and (get(v["consistent_cell"], "edit") or {}).get("also_changed")}
    want = {"naive_cell": n_poison // 2, "consistent_cell": n_poison - n_poison // 2}
    chosen, used_docs = [], set()
    for kind in ("naive_cell", "consistent_cell"):
        pool = sorted(q for q, v in by_qid.items() if kind in v)
        rng.shuffle(pool)
        if kind == "naive_cell":
            pool.sort(key=lambda q: q not in stale)  # stable: stale-total pairs first
        for q in pool:
            a = by_qid[q][kind]
            doc_id = get(a, "clean_page_id").split("__", 1)[0]
            if want[kind] == 0 or doc_id in used_docs:
                continue
            used_docs.add(doc_id)
            want[kind] -= 1
            chosen.append({"page_id": get(a, "poison_page_id"), "doc_id": doc_id, "is_poisoned": True, "condition": kind})
    if any(want.values()):
        raise StealthInputError(f"not enough G1 cell attacks from distinct documents; still missing {want}")
    clean_pool = sorted(d for d in clean_doc_ids if d not in used_docs)
    if len(clean_pool) < n_clean:
        raise StealthInputError(f"need {n_clean} clean documents outside the poisoned set, found {len(clean_pool)}")
    for doc_id in rng.sample(clean_pool, n_clean):
        chosen.append({"page_id": f"{doc_id}__clean", "doc_id": doc_id, "is_poisoned": False, "condition": "clean"})
    rng.shuffle(chosen)
    return [{"item": f"S{i:02d}", **c} for i, c in enumerate(chosen, 1)]
