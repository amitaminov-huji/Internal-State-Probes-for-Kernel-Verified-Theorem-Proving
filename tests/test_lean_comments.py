"""Tests for robust_verification/lean_comments.py: all four Lean comment forms, nesting, string
literals, and the `sorry`-outside-comments helper the README recommends for step 1."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "robust_verification"))

from lean_comments import contains_sorry_outside_comments, strip_lean_comments  # noqa: E402


class TestTheFourCommentForms(unittest.TestCase):
    def test_line_comment(self):
        self.assertEqual(strip_lean_comments("a -- b\nc"), "a \nc")

    def test_block_comment(self):
        self.assertEqual(strip_lean_comments("a /- b -/ c"), "a  c")

    def test_docstring_comment(self):
        self.assertEqual(strip_lean_comments("/-- doc -/\ntheorem t"), "\ntheorem t")

    def test_module_doc_comment(self):
        self.assertEqual(strip_lean_comments("/-! section -/\ntheorem t"), "\ntheorem t")

    def test_each_form_hides_a_sorry(self):
        for src in ("x -- sorry\n", "x /- sorry -/", "x /-- sorry -/", "x /-! sorry -/"):
            self.assertFalse(contains_sorry_outside_comments(src), src)


class TestNestingAndTermination(unittest.TestCase):
    def test_nested_block_comments(self):
        self.assertEqual(strip_lean_comments("a /- b /- c -/ d -/ e"), "a  e")

    def test_deeply_nested(self):
        self.assertEqual(strip_lean_comments("a /- /- /- sorry -/ -/ -/ b"), "a  b")

    def test_a_close_marker_inside_a_nested_comment_does_not_end_it_early(self):
        self.assertFalse(contains_sorry_outside_comments("/- /- -/ sorry -/"))

    def test_unterminated_block_comment_consumes_to_eof(self):
        self.assertEqual(strip_lean_comments("a /- b sorry"), "a ")
        self.assertFalse(contains_sorry_outside_comments("a /- b sorry"))

    def test_unterminated_line_comment_consumes_to_eof(self):
        self.assertEqual(strip_lean_comments("a -- sorry"), "a ")

    def test_line_comment_keeps_its_newline_so_line_numbers_survive(self):
        self.assertEqual(strip_lean_comments("a -- x\nb -- y\nc").count("\n"), 2)

    def test_block_opener_inside_a_line_comment_is_part_of_the_line_comment(self):
        self.assertEqual(strip_lean_comments("a -- /- b\nc"), "a \nc")

    def test_line_opener_inside_a_block_comment_is_part_of_the_block(self):
        self.assertEqual(strip_lean_comments("a /- -- b -/ c"), "a  c")

    def test_crlf_line_endings(self):
        self.assertEqual(strip_lean_comments("a -- sorry\r\nb"), "a \r\nb")


class TestStringLiteralsArePreserved(unittest.TestCase):
    def test_a_string_is_copied_through_verbatim(self):
        self.assertEqual(strip_lean_comments('#eval "hello"'), '#eval "hello"')

    def test_comment_markers_inside_a_string_are_not_comments(self):
        for s in ('#eval "a -- b"', '#eval "a /- b -/ c"', '#eval "/-- x -/"'):
            self.assertEqual(strip_lean_comments(s), s, s)

    def test_escaped_quote_does_not_end_the_string(self):
        src = r'#eval "a \" -- still in the string" -- gone'
        self.assertEqual(strip_lean_comments(src), r'#eval "a \" -- still in the string" ')

    def test_escaped_backslash_at_the_end_of_a_string(self):
        src = r'#eval "a\\" -- gone'
        self.assertEqual(strip_lean_comments(src), r'#eval "a\\" ')

    def test_sorry_inside_a_string_is_still_reported(self):
        """A known limitation, pinned so it cannot change silently: this helper removes comments
        only, so a `sorry` inside a string literal still counts as code. See README.md."""
        self.assertTrue(contains_sorry_outside_comments('#eval "sorry"'))

    def test_an_unbalanced_quote_never_eats_real_code(self):
        """The failure this module exists to avoid: one stray `"` must not swallow the tactics after
        it. Measured once in 59,181 attempts, where the swallowed span held a genuine `sorry`."""
        src = 'theorem t : False := by\n  -- a " stray quote\n  sorry\n'
        self.assertIn("sorry", strip_lean_comments(src))
        self.assertTrue(contains_sorry_outside_comments(src))


class TestSorryDetection(unittest.TestCase):
    def test_a_real_sorry_tactic_is_reported(self):
        self.assertTrue(contains_sorry_outside_comments("theorem t : True := by\n  sorry\n"))

    def test_a_commented_out_proof_body_is_not(self):
        src = ("**Error**, can not find 'theorem' and ':=' in\n\n"
               "-- theorem t : False := by\n--   have h : x = 0 := by sorry\n")
        self.assertFalse(contains_sorry_outside_comments(src))

    def test_word_boundaries(self):
        self.assertFalse(contains_sorry_outside_comments("theorem t := by exact sorryAx_free"))
        self.assertFalse(contains_sorry_outside_comments("theorem notsorry := by trivial"))
        self.assertTrue(contains_sorry_outside_comments("theorem t := by\n  exact (sorry)"))

    def test_sorry_as_a_term_not_just_a_tactic(self):
        self.assertTrue(contains_sorry_outside_comments("theorem t : True := sorry"))

    def test_empty_and_trivial_inputs(self):
        for s in ("", "\n", "theorem t : True := trivial"):
            self.assertFalse(contains_sorry_outside_comments(s))
        self.assertEqual(strip_lean_comments(""), "")

    def test_it_is_stricter_than_nothing_and_weaker_than_the_kernel(self):
        """The whole point: comment-stripping removes false rejections without weakening soundness,
        because a `sorry` it lets through is still caught at steps 3 and 4."""
        commented = "theorem t : True := by\n  -- sorry\n  trivial\n"
        real = "theorem t : True := by\n  sorry\n"
        self.assertTrue(bool(__import__("re").search(r"\bsorry\b", commented)),
                        "the current bare check rejects this valid proof")
        self.assertFalse(contains_sorry_outside_comments(commented),
                         "the recommended check accepts it")
        self.assertTrue(contains_sorry_outside_comments(real),
                        "and still rejects a genuine sorry")


class TestIdentifiersWithPrimes(unittest.TestCase):
    def test_a_prime_in_an_identifier_is_not_a_delimiter(self):
        """`'` is ordinary in Lean names, so it is deliberately not tracked as a char literal."""
        src = "theorem t (h' : p) : p := by\n  exact h'\n"
        self.assertEqual(strip_lean_comments(src), src)

    def test_primes_do_not_hide_a_following_sorry(self):
        self.assertTrue(contains_sorry_outside_comments("theorem t (h' : p) : q := by\n  sorry\n"))


if __name__ == "__main__":
    unittest.main()
