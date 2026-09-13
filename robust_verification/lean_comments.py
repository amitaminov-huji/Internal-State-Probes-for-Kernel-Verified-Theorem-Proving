"""Remove Lean 4 comments from a source string, so a text-level check can be run on code alone.

Provided for the step-1 recommendation in README.md. Nothing here changes `verify_lean_robust.py`;
it is an optional helper you compose with it.

Lean 4 has four comment forms, and all four are handled:

    -- line                 to end of line
    /- block -/             nestable
    /-- docstring -/        a block comment carrying documentation
    /-! module doc -/       a block comment carrying section documentation

String literals are **preserved, never removed**. That asymmetry is deliberate. Removing a comment can
only delete text the compiler ignores, so at worst it hides a `sorry` from an early text check and the
kernel catches it at steps 3-4 anyway. Removing a *string* is not safe in the same way: a generated file
can contain an unbalanced `"`, and a scanner that treats it as an opening delimiter swallows the rest of
the file, including real tactics. We hit exactly that case once in 59,181 attempts. Strings are still
*tracked* here, so that `--` or `/-` inside a literal is not mistaken for a comment opener; their
contents are simply copied through.

Character literals are deliberately not tracked: `'` is ordinary in Lean identifiers (`h'`, `n'`), so
treating it as a delimiter would corrupt far more than it protects.
"""
import re

__all__ = ["strip_lean_comments", "contains_sorry_outside_comments", "SORRY_RE"]

SORRY_RE = re.compile(r"\bsorry\b")


def strip_lean_comments(source: str) -> str:
    """Return `source` with every Lean 4 comment removed and everything else intact.

    Nested block comments are handled to any depth. An unterminated comment of either kind consumes
    the rest of the input, which is what the Lean lexer does too.

    >>> strip_lean_comments("theorem t : True := by -- sorry\\n  trivial")
    'theorem t : True := by \\n  trivial'
    >>> strip_lean_comments('#eval "a -- b"')
    '#eval "a -- b"'
    """
    out = []
    i, n = 0, len(source)
    while i < n:
        c = source[i]

        # A string literal: copy it through verbatim, so `--` and `/-` inside it stay put.
        if c == '"':
            out.append(c)
            i += 1
            while i < n:
                ch = source[i]
                if ch == "\\":                      # escape: take this and the next char as-is
                    out.append(source[i:i + 2])
                    i += 2
                    continue
                out.append(ch)
                i += 1
                if ch == '"':
                    break
            continue

        # Block comment, including the `/--` docstring and `/-!` module-doc forms. Nestable.
        if source.startswith("/-", i):
            depth, i = 1, i + 2
            while i < n and depth:
                if source.startswith("/-", i):
                    depth += 1
                    i += 2
                elif source.startswith("-/", i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
            continue

        # Line comment: drop to the newline, but keep the newline so line numbers survive. Under CRLF
        # the `\r` is a line ending too, not comment text, so stop before it.
        if source.startswith("--", i):
            j = source.find("\n", i)
            if j < 0:
                i = n
            else:
                i = j - 1 if j > i and source[j - 1] == "\r" else j
            continue

        out.append(c)
        i += 1
    return "".join(out)


def contains_sorry_outside_comments(source: str) -> bool:
    """True when `sorry` appears in `source` as code rather than only inside a comment.

    Drop-in replacement for the bare `re.search(r'\\bsorry\\b', source)` in step 1 of the protocol.
    It still matches a `sorry` inside a string literal, which stays a known limitation: see README.md,
    "Recommended change to step 1".
    """
    return bool(SORRY_RE.search(strip_lean_comments(source)))
