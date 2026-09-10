"""Citation-channel filter (v2 collision-fix follow-up).

A recovered LeanDojo `__us` success is a *citation* when its proof body cites the target's REAL
Mathlib lemma (`exact X` / `apply X` / `simp [.. X ..]` / `rw [.. X ..]` / `:= X`) instead of
proving it from scratch. Such a success is LEAKY: a novel deployment theorem (MathOlympiadBench)
has no such lemma in scope, so the citation would not transfer. These citation successes are
EXCLUDED from every label consumer (probe training, intervention/arm selection, K-fold AUROC).
They are DROPPED, never relabelled as failures -- a citation is a valid Lean proof, just not a
representative one, so counting it as a negative would be as wrong as counting it as a positive.

`is_citation` is meaningful only for a *successful* attempt; a citing *failure* stays a genuine
negative (the consumer applies the filter as `success and is_citation`).

Real name: `reconstruct.py` sets `theorem_id = f"{full_name}@{file_path}"`, and the `__us` suffix
is added only to the declared `theorem` head, so the pre-`@` segment of `theorem_id` is the
original Mathlib full-name. The predicate mirrors the audited citation investigation so filtered
counts reconcile with it; it distinguishes an unambiguous full-name cite ("full") from a
short-name-only match ("short", conservatively also filtered) and reports the two separately.
"""
from __future__ import annotations

import re

from probe_pipeline.data.dataset_mode import clean_dataset_mode

_BY_SPLIT = re.compile(r":=\s*by\b")


def proof_body(full_code: str) -> str:
    """The proof text after the first `:= by` (fallback: after the first `:=`)."""
    parts = _BY_SPLIT.split(full_code, maxsplit=1)
    if len(parts) > 1:
        return parts[1]
    return re.split(r":=", full_code, maxsplit=1)[-1]


def real_full_name(theorem_id: str) -> str:
    """Original Mathlib full-name of a renamed `__us` theorem (the pre-`@` segment)."""
    return theorem_id.split("@")[0]


def _cites(body: str, name: str) -> bool:
    """True iff the proof body cites `name`. Because `name` is the target theorem's OWN original
    Mathlib name, any citation-position mention is leaky (a genuine proof never cites itself), so
    the match is deliberately broad: a term position after exact/apply/refine (incl. inside an
    anon-constructor `⟨…⟩`) or `:=`/`using`/`▸`, OR the name inside ANY `[…]` lemma bracket
    (simp / simp_all / simpa / rw / rewrite / unfold / linarith / nlinarith / aesop / positivity /
    gcongr / norm_num …). Stops at `;`/newline so a later unrelated tactic on the same line does
    not over-match. The `__us` self-reference never matches (word boundary can't fall before `__`).

    KNOWN GAP, left as it ran because the labels are frozen: the `:=` and `using` patterns require the
    name immediately after the keyword, so Lean's explicit-argument prefix defeats them and
    `have h := @X …` is not flagged, while exact/apply/refine and the bracket form survive `@`. Three
    real citations of that shape occur in the corpus, all in FAILING attempts, where this predicate is
    never consulted. See ../README.md and the characterisation tests in ../tests/."""
    e = re.escape(name)
    return bool(
        re.search(rf"\b(?:exact|apply|refine)\b[^\n;]*?\b{e}\b", body)   # exact/apply/refine … X (incl. ⟨X…⟩)
        or re.search(rf":=\s*{e}\b", body)                               # := X   (have / term-mode)
        or re.search(rf"\busing\s+{e}\b", body)                          # simpa using X, … using X
        or re.search(rf"\b{e}\b\s*▸", body)                              # X ▸ …  (rewrite-by-term)
        or re.search(rf"\[[^\]]*\b{e}\b[^\]]*\]", body)                  # ANY [ … X … ] lemma bracket
    )


def cite_kind(full_code: str, theorem_id: str) -> str:
    """Classify how (if at all) the proof cites the real lemma.

    Returns 'full' (the exact `Namespace.lemma` full-name is cited -- unambiguous), 'short'
    (only the bare short name is cited -- ambiguous: may name a different lemma) or 'none'.
    The `__us` self-reference never matches: a word boundary cannot fall between the real
    name and the `__us` suffix, so `Real.foo` does not match `Real.foo__us`.
    """
    # CLEAN_DATASET_MODE (POC toggle): the pool is prefiltered to non-colliders, so X is absent
    # from the environment and the citation channel cannot occur — nothing to filter. This single
    # gate no-ops is_citation / should_filter / summarize_citations / neutralize_citation_solves.
    # Default OFF → full citation classification below runs exactly as before.
    if clean_dataset_mode():
        return "none"
    if not full_code:
        return "none"
    real = real_full_name(theorem_id)
    short = real.rsplit(".", 1)[-1]
    body = proof_body(full_code)
    if _cites(body, real):
        return "full"
    if short != real and _cites(body, short):
        return "short"
    return "none"


def is_citation(full_code: str, theorem_id: str) -> bool:
    """True iff the proof cites the real lemma (full- or short-name). Apply only to successes."""
    return cite_kind(full_code, theorem_id) != "none"


# --- consumer-facing helpers (used by training / validation / AUROC to drop & report) ---------

def should_filter(attempt: dict, label_field: str = "success") -> bool:
    """True iff `attempt` is a citation SUCCESS to EXCLUDE from label consumers.

    A citation is dropped only when it is a *positive* (the pass flag `label_field` is truthy);
    a citing FAILURE is a genuine negative and is kept. Reads `full_code` and `theorem_id`.
    """
    if not attempt.get(label_field):
        return False
    return is_citation(attempt.get("full_code") or "", attempt.get("theorem_id") or "")


def summarize_citations(attempts, label_field: str = "success", n_examples: int = 25) -> dict:
    """Count citation SUCCESSES (by kind) over an iterable of attempt dicts, with a few examples.

    Returns {n_success, n_filtered, full, short, examples:[{theorem_id, kind, proof}]}. Used to
    report how many positives each consumer excluded (training total; per-arm in validation) and
    to surface example proofs for the paper.
    """
    full = short = n_success = 0
    examples = []
    for a in attempts:
        if not a.get(label_field):
            continue
        n_success += 1
        kind = cite_kind(a.get("full_code") or "", a.get("theorem_id") or "")
        if kind == "none":
            continue
        if kind == "full":
            full += 1
        else:
            short += 1
        if len(examples) < n_examples:
            body = " ".join(proof_body(a.get("full_code") or "").split())[:300]
            examples.append({"theorem_id": a.get("theorem_id"), "seed": a.get("seed"),
                             "kind": kind, "proof": body})
    return {"n_success": n_success, "n_filtered": full + short,
            "full": full, "short": short, "filtered": examples}


def filter_arm_rows(rows, label_field: str = "success"):
    """For a contest arm: neutralize citing successes (so they don't count as solves/passes) AND
    build the COMPLETE report of what was filtered (every citation saved, uncapped).

    Returns (rows_eval, report): rows_eval for pass@k/solved counting; report =
    {n_success, n_filtered, full, short, filtered:[...]} for the arm's citation_filter.json.
    """
    rows_eval, _ = neutralize_citation_solves(rows, label_field)
    report = summarize_citations(rows, label_field, n_examples=10 ** 9)
    return rows_eval, report


def neutralize_citation_solves(rows, label_field: str = "success"):
    """For arm selection / pass@k: flip each citing SUCCESS' pass flag to False so it does not
    count as a genuine solve, WITHOUT dropping the row (the attempt still counts toward the
    k-budget) and WITHOUT relabelling it a training negative (the contest trains nothing).

    Returns (rows_eval, n_citation): a new list with citing successes neutralized, and the count
    of neutralized attempts (for per-arm reporting).
    """
    out, n = [], 0
    for r in rows:
        if should_filter(r, label_field):
            n += 1
            out.append({**r, label_field: False})
        else:
            out.append(r)
    return out, n
