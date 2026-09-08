"""Phase-1 driver (plan §3, §1, §13-A/B/D/F): re-verify the CLEAN train attempts under HARD and SOFT
lenient headers and write the three label artifacts (hard, soft, cfhl) as CLEAN-only collection views.

Per attempt (theorem_id, seed, model) — 3-way join (§13-A): model_output from `attempts_chunk_*.jsonl`,
the original `metadata_labeled` row (row_ids/split/etc., COPIED per §13-B), and reconstruction from the pool.
`verify_attempt` reassembles HARD and SOFT `full_code` via the shared `lenient_headers` builder (§13-E) +
`assemble_full_code`, verifies BOTH via `verify_lean_robust.verify_one` (L1→L2 reopen, §13-D), runs the
citation filter (mechanism 3) on the HARD code, and guards attribute-line errors (§13-F). Set algebra (§1):
  HARD : success=hard_ok, DROP if hard_ok ∧ hard_cited
  SOFT : success=soft_ok, no drops
  CFHL : HARD minus (hard_ok==False ∧ soft_ok==True)
Each artifact row = the ORIGINAL metadata_labeled row with `success` overwritten; DROP = omit the row
(feature-auto-drops). RUN UNCONTENDED (`--exclusive`, §7). Sharded + resumable.
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import sys
from collections import defaultdict

REPO = "<REPO>"
sys.path.insert(0, REPO)
import verify_lean_robust as V
from probe_pipeline.data import reconstruct as R
from probe_pipeline.data import citation_filter as CF
from probe_pipeline.data.dataset_mode import clean_dataset_mode
from probe_pipeline.data.filtered_dataset import dead_theorem_ids
from probe_pipeline.inference.legacy_assembly import assemble_legacy  # == assemble_full_code, no heavy deps
from probe_pipeline.labeling.lenient_headers import Classification, build_verify_header

DATA = f"{REPO}/new_results/data/leandojo_filtered"
COLLECTIONS = {"8B": f"{REPO}/artifacts/collection/8B_train_scale2p5",
               "32B": f"{REPO}/artifacts/collection/32B_train_scale2p5"}
OUT = f"{DATA}/labels"
L1, L2 = 1800, 5400
_ATTR_MSGS = ("not registered", "unknown identifier", "unknown constant")


def _is_timeout(r: dict) -> bool:
    return r.get("exit_code") in (-1, -9) or "timeout" in str(r.get("reason", "")).lower()


def _verify(full_code: str) -> dict:
    """robust verify with an explicit L1→L2 reopen on TIMEOUT (§13-D). A verify that STILL times out / is
    signal-killed (exit -9) after L2 is annotated (`l2_residual_timeout`) so consolidate can SURFACE it
    rather than silently trusting the fail label."""
    r = V.verify_one("t", full_code, timeout=L1)
    if _is_timeout(r):
        r = V.verify_one("t", full_code, timeout=L2)           # reopen the timeout at L2
        r["l2_reopened"] = True
        r["l2_residual_timeout"] = _is_timeout(r)              # STILL timing out / OOM-killed after L2
    return r


def _err_on_attribute(r: dict, full_name: str) -> bool:
    """§13-F: did a PREPENDED `attribute [-simp]/[-aesop] <full_name>` line error (a classification/verify
    mismatch)? SCOPED to an error that names `full_name` AS A QUOTED IDENTIFIER (Lean quotes it: `'X'` /
    `` `X` ``) — so a genuine body failure naming a DIFFERENT id ("unknown identifier 'SomeOtherLemma'"), or
    a mere substring-superset ("'Nat.addfoo'" vs full_name "Nat.add"), is NOT misread as an attribute error
    and a real negative is not wrongly dropped from every label set (HIGH-2). Only consulted when a collider
    HARD header emitted the attribute line."""
    quoted = (f"'{full_name}'", f"`{full_name}`")
    for e in r.get("errors") or []:
        d = str(e.get("data", ""))
        if any(q in d for q in quoted) and any(m in d.lower() for m in _ATTR_MSGS):
            return True
    return False


def _slim(r: dict) -> dict:
    """Persist the raw verify signal per attempt so hard_ok/soft_ok/attr_err are RECOMPUTABLE at consolidate
    WITHOUT re-verifying (the expensive 24-shard step) — critic must-fix."""
    return {"valid": bool(r.get("valid")), "exit_code": r.get("exit_code"), "reason": r.get("reason"),
            "errors": r.get("errors") or [], "l2_reopened": bool(r.get("l2_reopened")),
            "l2_residual_timeout": bool(r.get("l2_residual_timeout"))}


def verify_attempt(model_output: str, rt, classif: Classification, compute_soft: bool = True) -> dict:
    """Core per-attempt: reassemble HARD (+ optionally SOFT) via the ONE shared header builder, verify,
    citation, attribute-error guard. Persists the raw hard/soft verify signal (`hr`/`sr`) for cheap recompute.
    Testable. `compute_soft=False` (contest scoring) SKIPS the 2nd (soft) compile — `soft_ok`/`sr` are None; the
    CFHL crutch-drop needs soft, but it is a no-op on positive-only counts so the contest defaults it OFF."""
    sv = rt.statement_verify or rt.statement
    cls = classif.cls_of(rt.full_name)
    hard_hdr = build_verify_header(rt.header, rt.namespace, rt.full_name, "hard", cls)
    hard_code = assemble_legacy(model_output, hard_hdr, sv)
    hr = _verify(hard_code)
    hard_ok = bool(hr.get("valid"))
    has_attr = cls in ("COLLIDER_NONAESOP", "COLLIDER_AESOP")  # only these HARD headers prepend attribute line(s)
    attr_err = (not hard_ok) and has_attr and _err_on_attribute(hr, rt.full_name)  # classification/verify mismatch
    hard_cited = CF.is_citation(hard_code, rt.theorem_id)
    if compute_soft:
        soft_hdr = build_verify_header(rt.header, rt.namespace, rt.full_name, "soft", cls)
        soft_code = assemble_legacy(model_output, soft_hdr, sv)
        sr = _verify(soft_code)
        soft_ok = bool(sr.get("valid"))
    else:
        sr, soft_ok = None, None
    return {"hard_ok": hard_ok, "soft_ok": soft_ok, "hard_cited": hard_cited, "attr_err": attr_err,
            "cls": cls, "hr": _slim(hr), "sr": _slim(sr) if sr is not None else None}


# ---- shard runner -------------------------------------------------------------------------------
def _load_attempts(model, keep_ids):
    """(theorem_id, seed) -> {model_output, orig_row} over the CLEAN keep set for one model."""
    mo, orig = {}, {}
    for f in glob.glob(f"{COLLECTIONS[model]}/shard_*/attempts_chunk_*.jsonl"):
        for l in open(f):
            d = json.loads(l)
            if d["theorem_id"] in keep_ids:
                mo[(d["theorem_id"], d["seed"])] = d["model_output"]
    for f in glob.glob(f"{COLLECTIONS[model]}/shard_*/metadata_labeled.jsonl"):
        for l in open(f):
            d = json.loads(l)
            if d["theorem_id"] in keep_ids:
                orig[(d["theorem_id"], d["seed"])] = d
    return mo, orig


def _assert_clean_preconditions():
    """L-a + L-d (critic): lenient labeling REQUIRES the `__us` rename + citation filter (so CLEAN_DATASET_MODE
    must be OFF) and the CLEAN-filtered dataset (dead_theorem_ids 1124/329). Fail LOUD at startup rather than
    silently mislabel every collider (rename dropped) or skip every citation drop."""
    assert not clean_dataset_mode(), (
        "CLEAN_DATASET_MODE/PREFILTER_COLLISIONS must be OFF: lenient labeling needs the __us rename + citation filter")
    ntr, nva = len(dead_theorem_ids("train")), len(dead_theorem_ids("validation"))
    assert (ntr, nva) == (1124, 329), f"CLEAN filter drifted: dead_theorem_ids train/val = {ntr}/{nva}, expected 1124/329"


def run_shard(rank, world):
    _assert_clean_preconditions()
    keep = set(json.load(open(f"{DATA}/clean_keep_train.json")))
    assert len(keep) == 243, f"clean_keep_train must be the CLEAN 243, got {len(keep)}"
    classif = Classification(f"{DATA}/theorem_classification.json")
    pool = {p["full_name"]: p for p in json.load(open(f"{REPO}/artifacts/splits/pool_scale2p5.json"))}
    os.makedirs(f"{OUT}/verdicts", exist_ok=True)
    for model in ("8B", "32B"):
        outp = f"{OUT}/verdicts/{model}_shard{rank}of{world}.jsonl"
        done = set()
        if os.path.exists(outp):
            for l in open(outp):
                try:
                    r = json.loads(l)
                except json.JSONDecodeError:
                    continue                                    # truncated final line from a crash mid-write; recompute it
                done.add((r["theorem_id"], r["seed"]))
        mo, orig = _load_attempts(model, keep)
        mine = sorted(mo)[rank::world]                          # STRIDE first (stable partition), THEN drop done —
        items = [k for k in mine if k not in done]              # a requeue never reassigns items across ranks (§P2)
        print(f"[relabel] {model} shard {rank}/{world}: {len(items)} attempts ({len(done)} resumed)", flush=True)
        with open(outp, "a") as fout:
            for (tid, seed) in items:
                rt = R.reconstruct(pool[tid.split("@")[0]])
                v = verify_attempt(mo[(tid, seed)], rt, classif)
                row = dict(orig[(tid, seed)])                  # COPY original row (row_ids/split preserved, §13-B)
                fout.write(json.dumps({"theorem_id": tid, "seed": seed, "model": model,
                                       **v, "orig": row}) + "\n")
                fout.flush()
    print(f"[relabel] shard {rank} DONE", flush=True)


# ---- consolidation into the 3 CLEAN-only label artifacts ----------------------------------------
def partition_verdicts(rows):
    """PURE set algebra (§1) → (hard, soft, cfhl, n_attr_err). Each label row = the ORIGINAL metadata row
    (row_ids/split preserved, §13-B) with `success` overwritten; a DROP is an omitted row. Testable."""
    hard, soft, cfhl = [], [], []
    n_attr_err = 0
    for v in rows:
        base = dict(v["orig"])
        if v["attr_err"]:
            n_attr_err += 1                                    # SURFACE, do not trust (§13-F): excluded from all
            continue
        soft.append({**base, "success": v["soft_ok"]})
        if v["hard_ok"] and v["hard_cited"]:                   # HARD mechanism-3 citation drop
            continue
        hrow = {**base, "success": v["hard_ok"]}
        hard.append(hrow)
        if v["hard_ok"] is False and v["soft_ok"] is True:     # CFHL crutch purge
            continue
        cfhl.append(hrow)
    return hard, soft, cfhl, n_attr_err


def consolidate():
    raw = defaultdict(list)
    for f in glob.glob(f"{OUT}/verdicts/*_shard*of*.jsonl"):
        for l in open(f):
            v = json.loads(l)
            raw[v["model"]].append(v)
    summary = {}
    for model, rlist in raw.items():
        dv = {}                                                # DEDUP (theorem_id, seed) — first wins (defensive)
        for v in rlist:
            dv.setdefault((v["theorem_id"], v["seed"]), v)
        rows = list(dv.values())
        hard, soft, cfhl, n_attr_err = partition_verdicts(rows)
        for tag, rows_ in (("hard_lenient", hard), ("soft_lenient", soft), ("cfhl", cfhl)):
            _write_view(model, tag, rows_)
        n_resid = sum(bool((r.get("hr") or {}).get("l2_residual_timeout"))
                      or bool((r.get("sr") or {}).get("l2_residual_timeout")) for r in rows)
        s = {"n_attempts": len(rows), "n_duplicates_dropped": len(rlist) - len(rows),
             "soft": len(soft), "hard": len(hard), "cfhl": len(cfhl),
             "attr_err_surfaced": n_attr_err, "l2_residual_timeout_surfaced": n_resid,
             # explicit per-cell drop counts (§6): citation drop (hard_ok∧hard_cited) and crutch drop (F,T)
             "dropped_citation": sum(1 for v in rows if not v["attr_err"] and v["hard_ok"] and v["hard_cited"]),
             "dropped_softcrutch": sum(1 for v in rows if not v["attr_err"] and v["hard_ok"] is False and v["soft_ok"] is True),
             "hard_pos": sum(bool(r["success"]) for r in hard),
             "cfhl_pos": sum(bool(r["success"]) for r in cfhl),
             "soft_pos_crutch_inflated": sum(bool(r["success"]) for r in soft)}  # soft passes are crutch-inflated, NOT genuine
        summary[model] = s
        json.dump(s, open(f"{OUT}/relabel_summary_{model}.json", "w"), indent=2)  # per-model (§6)
        if n_resid:
            print(f"[relabel] WARNING {model}: {n_resid} attempts STILL timed out / OOM-killed after L2 (surfaced)", flush=True)
        if n_attr_err:
            print(f"[relabel] WARNING {model}: {n_attr_err} attribute-line classification/verify MISMATCHES (attr_err) — "
                  f"expected 0; investigate before trusting these labels", flush=True)
    json.dump(summary, open(f"{OUT}/relabel_summary.json", "w"), indent=2)
    print(f"[relabel] consolidated: {summary}", flush=True)
    return summary


_TID2SHARD: dict = {}


def _tid_to_shard(model: str) -> dict:
    """{theorem_id -> original collection shard basename}. A theorem lives WHOLLY in one shard (theorem-level
    split), so the view can be rebuilt per source shard."""
    if model not in _TID2SHARD:
        m = {}
        for f in glob.glob(f"{COLLECTIONS[model]}/shard_*/metadata_labeled.jsonl"):
            sh = os.path.basename(os.path.dirname(f))
            for l in open(f):
                m[json.loads(l)["theorem_id"]] = sh
        _TID2SHARD[model] = m
    return _TID2SHARD[model]


def _write_view(model, tag, rows):
    """Write a CLEAN-only collection VIEW, PER ORIGINAL SHARD (features symlinked + this artifact's rows), §13-H.
    The loader (training_data.load_training_arrays) consumes each shard_* independently and joins a row's
    `row_ids` to THAT shard's feature manifest; dumping every row into shard_0 with only shard_0 features made
    the 8B rows whose theorems live in shard_1 unloadable (>10% missing-feature gate). Grouping by source shard
    fixes it (HIGH-1)."""
    t2s = _tid_to_shard(model)
    by_shard = defaultdict(list)
    for r in rows:
        by_shard[t2s[r["theorem_id"]]].append(r)               # KeyError if a row's theorem isn't in the collection (fail-loud)
    base = f"{OUT}/labels_{tag}/collection_{model}"
    for sh, srows in by_shard.items():
        vdir = f"{base}/{sh}"
        os.makedirs(vdir, exist_ok=True)
        src_feat = f"{DATA}/collection_{model}/{sh}/features"               # existing (symlinked) per-shard features
        link = f"{vdir}/features"
        if os.path.lexists(link):
            os.remove(link)
        if os.path.exists(src_feat):
            os.symlink(os.path.realpath(src_feat), link)
        with open(f"{vdir}/metadata_labeled.jsonl", "w") as f:
            for r in srows:
                f.write(json.dumps(r) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rank", type=int, default=int(os.environ.get("SLURM_ARRAY_TASK_ID", "0")))
    ap.add_argument("--world", type=int, default=int(os.environ.get("WORLD", "24")))
    ap.add_argument("--consolidate", action="store_true")
    a = ap.parse_args()
    if a.consolidate:
        consolidate()
    else:
        run_shard(a.rank, a.world)


if __name__ == "__main__":
    main()
