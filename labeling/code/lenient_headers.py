"""The ONE shared per-(LABELING_MODE, cls) verify-header builder for hard/soft lenient labeling (plan §3,
§13-E). Both the train re-verify (relabel_lenient) and the val intervention contest MUST call this — no
duplicated header logic. The PROMPT/statement is always the natural `formal_statement` (untouched); the
`__us`-renamed `formal_statement_verify` is used for the compiled file in both modes (rename avoids the
collision). Only the HEADER attributes differ by mode/cls:

    soft (any cls)          : header + namespace                              (rename only)
    hard NONCOLLIDER        : header + namespace                              (full_name absent — no erase)
    hard COLLIDER_NONAESOP  : header + [-simp] full_name + namespace
    hard COLLIDER_AESOP     : header + [-simp] full_name + [-aesop] full_name + namespace

`cls` comes from `theorem_classification.json`; a missing key FAILS LOUD (never silently NONCOLLIDER).
"""
from __future__ import annotations
import json

VALID_CLS = {"NONCOLLIDER", "COLLIDER_NONAESOP", "COLLIDER_AESOP"}


def build_verify_header(header: str, namespace: str, full_name: str, mode: str, cls: str) -> str:
    """`header` = natural base header (import/set_option/open), `namespace` = rt.namespace (may be '')."""
    if mode not in ("hard", "soft"):
        raise ValueError(f"unknown LABELING_MODE {mode!r}")
    if cls not in VALID_CLS:
        raise ValueError(f"unknown/missing cls {cls!r} — classification must cover every labeled theorem (fail-loud)")
    ns_open = f"namespace {namespace}\n" if namespace else ""
    if mode == "soft" or cls == "NONCOLLIDER":
        attr = ""
    elif cls == "COLLIDER_NONAESOP":
        attr = f"attribute [-simp] {full_name}\n"
    else:  # COLLIDER_AESOP
        attr = f"attribute [-simp] {full_name}\nattribute [-aesop] {full_name}\n"
    return header + attr + ns_open


class Classification:
    """Fail-loud lookup over theorem_classification.json (full_name -> cls)."""

    def __init__(self, path: str):
        obj = json.load(open(path))
        self._cls = obj["classification"]

    def cls_of(self, full_name: str) -> str:
        if full_name not in self._cls:
            raise KeyError(f"no classification for {full_name!r} — Phase-0 classify must cover every CLEAN theorem")
        return self._cls[full_name]

    def header_for(self, rt, mode: str) -> str:
        """rt = ReconstructedTheorem (has .header, .namespace, .full_name)."""
        return build_verify_header(rt.header, rt.namespace, rt.full_name, mode, self.cls_of(rt.full_name))
