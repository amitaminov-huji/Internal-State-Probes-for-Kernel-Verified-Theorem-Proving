"""Robust Lean-proof verifier.

Protocol:
  1. Parse the theorem name(s) from the code.
  2. Reject if the stored "code" isn't a real Lean file (empty, "None", "**Error**", etc.).
  3. Append `#print axioms <name>` for each detected theorem.
  4. Compile with `lake env lean` at the toolchain pinned by mathlib4/lean-toolchain (v4.9.0-rc1).
  5. Reject on:
     - exit_code != 0
     - "error:" in output
     - "declaration uses 'sorry'" in output   (proof has a sorry)
     - "sorry" in the source code itself       (belt-and-braces)
     - axioms used are not a subset of {propext, Classical.choice, Quot.sound}
       (any other axiom → possible unsoundness; flag it)
"""
import json, os, re, subprocess, sys, tempfile

# Locations of the Lean toolchain, mathlib, and the Goedel-Prover-V2 checkout.
# The defaults are the standard Linux install layout: elan puts `lake` in
# ~/.elan/bin, and the prover checkout is assumed to sit in the home directory.
# Override any of them with the environment variable of the same name.
GOEDEL_PROVER_V2 = os.environ.get(
    'GOEDEL_PROVER_V2', os.path.expanduser('~/Goedel-Prover-V2'))
LEAN_COMPILER_DIR = os.environ.get(
    'LEAN_COMPILER_DIR', os.path.join(GOEDEL_PROVER_V2, 'lean_compiler'))
LEAN_WORKSPACE = os.environ.get(
    'LEAN_WORKSPACE', os.path.join(GOEDEL_PROVER_V2, 'mathlib4'))
LAKE = os.environ.get('LAKE', os.path.expanduser('~/.elan/bin/lake'))

sys.path.insert(0, LEAN_COMPILER_DIR)
from repl_scheduler_rule_based import _build_lean_path, _get_lean_sysroot

DEFAULT_LEAN_SYSROOT = _get_lean_sysroot()
LEAN_PATH = _build_lean_path(LEAN_WORKSPACE)

TRUSTED_AXIOMS = {'propext', 'Classical.choice', 'Quot.sound'}

THEOREM_RE = re.compile(r'^\s*theorem\s+([A-Za-z_][A-Za-z0-9_\'\.]*)', re.M)

# Lean/lake diagnostics: "<path>:<line>:<col>: error|warning: <message>", the
# message spanning subsequent lines until the next such marker or EOF.
_DIAG_RE = re.compile(
    r'^.*?:(\d+):(\d+):\s*(error|warning):\s*(.*?)'
    r'(?=^.*?:\d+:\d+:\s*(?:error|warning):|\Z)',
    re.M | re.S)


def parse_lean_errors(out: str) -> list:
    """Parse `lake env lean` output into REPL-shaped error dicts that
    `src_async/utils.py get_error_str` consumes: {severity, pos{line,column},
    endPos, data}. Only `error` severities are returned (warnings are not
    actionable self-correction feedback). Positions are 1-indexed lines /
    0-indexed columns, matching the REPL and the original code's line numbers
    (the `#print axioms` lines are appended *after* the code, so error line
    numbers still index the proof)."""
    errors = []
    for m in _DIAG_RE.finditer(out or ''):
        if m.group(3) != 'error':
            continue
        # Drop the `#print axioms` diagnostics that live past the proof body.
        data = m.group(4).strip()
        if data.startswith("declaration uses 'sorry'"):
            # keep — it is a real signal the proof is incomplete
            pass
        errors.append({
            'severity': 'error',
            'pos': {'line': int(m.group(1)), 'column': int(m.group(2))},
            'endPos': None,
            'data': data,
        })
    return errors


def looks_like_lean(code: str) -> tuple[bool, str]:
    s = (code or '').strip()
    if not s or s == 'None':
        return False, 'placeholder: empty or "None"'
    if s.startswith('**Error**'):
        return False, 'placeholder: **Error** prefix'
    if 'can not find' in s[:200]:
        return False, 'placeholder: "can not find" prefix'
    if not THEOREM_RE.search(s):
        return False, 'no `theorem` declaration found'
    if re.search(r'\bsorry\b', s):
        return False, 'source contains `sorry`'
    return True, 'ok'


def verify_one(name: str, code: str, timeout: int = 900) -> dict:
    ok, reason = looks_like_lean(code)
    if not ok:
        return {'name': name, 'valid': False, 'reason': reason,
                'exit_code': None, 'axioms': None,
                'errors': [{'severity': 'error', 'pos': {'line': 1, 'column': 0},
                            'endPos': None, 'data': f'invalid proof source: {reason}'}]}

    theorems = THEOREM_RE.findall(code)
    augmented = code + '\n\n' + '\n'.join(f'#print axioms {t}' for t in theorems) + '\n'

    with tempfile.NamedTemporaryFile(mode='w', suffix='.lean', delete=False,
                                     dir=LEAN_WORKSPACE) as f:
        f.write(augmented)
        path = f.name

    env = dict(os.environ)
    env['LEAN_PATH'] = LEAN_PATH
    if DEFAULT_LEAN_SYSROOT:
        env['LEAN_SYSROOT'] = DEFAULT_LEAN_SYSROOT
    try:
        r = subprocess.run(
            ['bash', '-c', f'ulimit -s unlimited; exec {LAKE} env lean {path}'],
            cwd=LEAN_WORKSPACE, env=env, capture_output=True, text=True, timeout=timeout,
        )
        stdout, stderr, exit_code = r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        stdout, stderr, exit_code = '', 'TIMEOUT', -1
    finally:
        os.unlink(path)

    out = (stdout or '') + '\n' + (stderr or '')
    has_error = ('error:' in out.lower())
    has_sorry_warn = ("declaration uses 'sorry'" in out) or ('uses "sorry"' in out)

    # Parse the `#print axioms` output blocks.
    # Lean prints: "'thm_name' depends on axioms: [ax1, ax2, ...]" (with newline flow).
    # Regex to be robust:
    axioms_seen = set()
    for m in re.finditer(r"depends on axioms\s*:\s*\[(.*?)\]", out, flags=re.S):
        for a in m.group(1).split(','):
            a = a.strip()
            if a:
                axioms_seen.add(a)
    axioms_ok = axioms_seen.issubset(TRUSTED_AXIOMS)

    valid = (exit_code == 0) and (not has_error) and (not has_sorry_warn) and axioms_ok
    reason_bits = []
    if exit_code != 0: reason_bits.append(f'exit_code={exit_code}')
    if has_error: reason_bits.append('lean emitted `error:`')
    if has_sorry_warn: reason_bits.append('proof uses `sorry` (compiler warning)')
    if axioms_seen and not axioms_ok:
        extra = axioms_seen - TRUSTED_AXIOMS
        reason_bits.append(f'uses non-trusted axioms: {sorted(extra)}')
    if not axioms_seen and valid:
        # No axioms output means #print axioms didn't run — probably error elsewhere
        pass

    # Structured errors for self-correction feedback. If the proof is invalid
    # but no diagnostic parsed (e.g. a timeout, or a non-`error:` failure),
    # synthesise one so the correction loader never drops the variant and the
    # model still gets a signal.
    errors = parse_lean_errors(out)
    if not valid and not errors:
        errors = [{
            'severity': 'error',
            'pos': {'line': 1, 'column': 0},
            'endPos': None,
            'data': ('compilation failed with no parsed diagnostic '
                     f'(exit_code={exit_code}; {"; ".join(reason_bits) or "unknown"})'),
        }]

    return {
        'name': name,
        'valid': valid,
        'reason': 'ok' if valid else '; '.join(reason_bits) or 'unknown',
        'exit_code': exit_code,
        'axioms': sorted(axioms_seen),
        'errors': errors,
        'stdout_head': stdout[:1500],
        'stderr_head': stderr[:1500],
    }


def main():
    in_path = sys.argv[1] if len(sys.argv) > 1 else 'hist_recompile_ceiling_union16.json'
    out_path = sys.argv[2] if len(sys.argv) > 2 else 'hist_recompile_ceiling_union16_verified.json'
    data = json.load(open(in_path))
    proofs = data['proofs']
    print(f'Verifying {len(proofs)} union-passing proofs under the robust protocol')
    print(f'Trusted axioms: {sorted(TRUSTED_AXIOMS)}')
    print()

    results = []
    for i, p in enumerate(proofs):
        print(f'[{i+1:2d}/{len(proofs)}] {p["name"]} (run {p["run"]}, {len(p["code"])} chars)...', flush=True)
        r = verify_one(p['name'], p['code'])
        r['run'] = p['run']
        r['n_chars'] = len(p['code'])
        results.append(r)
        status = 'VALID' if r['valid'] else 'INVALID'
        print(f'     {status:7s}  axioms={r["axioms"]}  reason={r["reason"]}', flush=True)

    valid = [r for r in results if r['valid']]
    print()
    print('===== SUMMARY =====')
    print(f'Robust-valid proofs: {len(valid)}/{len(results)}')
    for r in valid:
        print(f'  ✓ {r["name"]}  axioms={r["axioms"]}')
    print()
    for r in results:
        if not r['valid']:
            print(f'  ✗ {r["name"]}  ({r["reason"]})')

    with open(out_path, 'w') as f:
        json.dump({'results': results, 'valid_count': len(valid), 'total': len(results)}, f, indent=2)
    print(f'\nWrote {out_path}')


if __name__ == '__main__':
    main()
