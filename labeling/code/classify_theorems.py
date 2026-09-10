"""Phase-0 classification (plan §2.3): for each unique `full_name` among the retained training and validation theorems,
classify into NONCOLLIDER / COLLIDER_NONAESOP / COLLIDER_AESOP by compiling a single probe:

    import Mathlib
    attribute [-aesop] <full_name>

- compiles (exit 0, no error)                       ⇒ COLLIDER_AESOP   (full_name exists AND is an aesop rule)
- error "not registered ... in any rule set"        ⇒ COLLIDER_NONAESOP (exists, not an aesop rule)
- error "unknown identifier"/"unknown constant"     ⇒ NONCOLLIDER      (full_name absent from Mathlib)
- anything else                                      ⇒ UNKNOWN (flag; must be 0 before use)

This is the §2.3 "fallback" per-lemma probe-compile (authoritative — same `attribute [-aesop]` semantics the
labeling deploys). `cls` gates which erases HARD emits (§1/§4). Output:
`new_results/data/leandojo_filtered/theorem_classification.json`. RUN UNCONTENDED (few workers) — a COMPUTE step
gated on approval; the classification of the 333 CLEAN theorems is what runs, not all 1399.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, "<REPO>")
from probe_pipeline.labeling.lean_compile import compile_lean

DATA = "<REPO>/new_results/data/leandojo_filtered"


def classify_one(full_name: str) -> str:
    rc, out = compile_lean(f"import Mathlib\nattribute [-aesop] {full_name}\n")
    if out == "TIMEOUT":
        return "TIMEOUT"
    low = out.lower()
    if rc == 0 and "error:" not in low:
        return "COLLIDER_AESOP"
    if "not registered" in low and "rule set" in low:
        return "COLLIDER_NONAESOP"
    if "unknown identifier" in low or "unknown constant" in low:
        return "NONCOLLIDER"
    return "UNKNOWN"


def _classify(full_name):
    return full_name, classify_one(full_name)


def retry_bad_serial(cls: dict, classify_fn=classify_one):
    """Contention (many workers cold-loading Mathlib at once) can inflate a trivial ~10s `attribute [-aesop]`
    compile past the cap → a FALSE TIMEOUT. Re-run every TIMEOUT/UNKNOWN name SERIALLY (uncontended) — they
    resolve in ~10s — before the strict 0-bad assert. Mirrors the dataset-filter reverify_timeouts fix.
    Returns (merged cls, the retried names)."""
    bad = sorted(fn for fn, c in cls.items() if c in ("TIMEOUT", "UNKNOWN"))
    for fn in bad:
        cls[fn] = classify_fn(fn)
    return cls, bad


def full_names_from_keeplists():
    ids = json.load(open(f"{DATA}/clean_keep_train.json")) + json.load(open(f"{DATA}/clean_keep_val.json"))
    return sorted({tid.split("@")[0] for tid in ids})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=int(os.environ.get("WORKERS", "8")))
    ap.add_argument("--out", default=f"{DATA}/theorem_classification.json")
    a = ap.parse_args()
    names = full_names_from_keeplists()
    print(f"[classify] {len(names)} unique full_names (CLEAN 243+90), {a.workers} workers", flush=True)
    cls = {}
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for i, (fn, c) in enumerate(ex.map(_classify, names)):
            cls[fn] = c
            if (i + 1) % 25 == 0:
                print(f"[classify] {i+1}/{len(names)}", flush=True)
    cls, retried = retry_bad_serial(cls)                       # self-heal contention false-timeouts (uncontended serial)
    if retried:
        print(f"[classify] retried {len(retried)} TIMEOUT/UNKNOWN serially uncontended: {retried[:5]}"
              f"{'...' if len(retried) > 5 else ''}", flush=True)
    counts = dict(Counter(cls.values()))
    aesop_rules = sorted(fn for fn, c in cls.items() if c == "COLLIDER_AESOP")
    json.dump({"n": len(cls), "counts": counts, "classification": cls, "aesop_rules": aesop_rules},
              open(a.out, "w"), indent=2)
    print(f"[classify] DONE {counts} -> {a.out}", flush=True)
    assert counts.get("UNKNOWN", 0) == 0 and counts.get("TIMEOUT", 0) == 0, f"UNKNOWN/TIMEOUT present: {counts}"


if __name__ == "__main__":
    main()
