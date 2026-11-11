"""Discriminating tests for the prospective ci_poll_identity helper.

Run with: python3 -m unittest test_ci_poll_identity -v
"""

import unittest

from scripts import ci_poll_identity as cpi

REPO_A = "owner/one"
REPO_B = "other/two"


class RepoScopingTests(unittest.TestCase):
    def test_same_number_cross_repo_does_not_collide(self):
        a = cpi.ci_pr_poll_identity(
            f"gh pr view 12 --json title -R {REPO_A}", cwd="/w/a"
        )
        b = cpi.ci_pr_poll_identity(
            f"gh pr view 12 --json title -R {REPO_B}", cwd="/w/a"
        )
        self.assertTrue(a and b and a != b)
        self.assertIn("repo:owner/one", a)
        self.assertIn("repo:other/two", b)

    def test_repo_value_case_is_normalized(self):
        upper = cpi.ci_pr_poll_identity(
            "gh pr checks 7 -R Owner/One", cwd="/w/a"
        )
        lower = cpi.ci_pr_poll_identity(
            "gh pr checks 7 --repo owner/one", cwd="/elsewhere"
        )
        self.assertEqual(upper, lower)
        self.assertIn("repo:owner/one", upper)

    def test_explicit_repo_argument_variants_share_key(self):
        variants = [
            f"gh pr view 12 --json title -R {REPO_A}",
            f"gh pr view 12 --json title -R={REPO_A}",
            f"gh pr view 12 --json title -R{REPO_A}",
            f"gh pr view 12 --json title --repo {REPO_A}",
            f"gh pr view 12 --json title --repo={REPO_A}",
            f"gh -R {REPO_A} pr view 12 --json title",
            f"gh --repo {REPO_A} pr view 12 --json title",
            f"gh -R{REPO_A} pr view 12 --json title",
            f"gh --repo '{REPO_A}' pr view 12 --json title",
            f"gh pr view 12 -R '{REPO_A}' --json title",
        ]
        keys = {
            cpi.ci_pr_poll_identity(v, cwd="/ignored/when/repo/explicit")
            for v in variants
        }
        self.assertEqual(len(keys), 1, keys)
        key = keys.pop()
        self.assertTrue(key.startswith("pr-view:12|repo:owner/one|src=title"))

    def test_unknown_scope_is_fenced(self):
        self.assertIsNone(cpi.ci_pr_poll_identity("gh pr view 5", cwd=""))
        self.assertIsNone(cpi.ci_pr_poll_identity("gh pr view 5"))
        self.assertIsNone(cpi.ci_pr_poll_identity("gh pr view 5", cwd="   "))
        self.assertIsNone(cpi.ci_pr_poll_identity("gh pr checks 9", cwd="rel/only"))
        # explicit repo rescues an otherwise fenced invocation (checks are
        # always classifiable; a plain view still needs a status/source signal)
        self.assertIsNotNone(
            cpi.ci_pr_poll_identity("gh pr checks 5 -R owner/one", cwd="")
        )
        self.assertIsNone(
            cpi.ci_pr_poll_identity("gh pr view 5 -R owner/one", cwd="")
        )

    def test_cwd_scope_is_canonical_and_discriminating(self):
        a = cpi.ci_pr_poll_identity("gh pr view 3 --json title", cwd="/w/a/")
        b = cpi.ci_pr_poll_identity("gh pr view 3 --json title", cwd="/w/a")
        c = cpi.ci_pr_poll_identity("gh pr view 3 --json title", cwd="/w/b")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertTrue(a.startswith("pr-view:3|cwd:/w/a|src=title"))


class ViewFieldIdentityTests(unittest.TestCase):
    def test_field_order_and_case_irrelevant(self):
        a = cpi.ci_pr_poll_identity(
            "gh pr view 12 --json title,body -R owner/one", cwd="/w/a"
        )
        b = cpi.ci_pr_poll_identity(
            "gh pr view 12 --json body,title -R owner/one", cwd="/w/a"
        )
        c = cpi.ci_pr_poll_identity(
            "gh pr view 12 --json TITLE,Body -R owner/one", cwd="/w/a"
        )
        self.assertEqual(a, b)
        self.assertEqual(a, c)
        self.assertEqual(a, "pr-view:12|repo:owner/one|src=body,title")

    def test_new_source_fact_changes_key(self):
        one = cpi.ci_pr_poll_identity(
            "gh pr view 12 --json title -R owner/one", cwd="/w/a"
        )
        two = cpi.ci_pr_poll_identity(
            "gh pr view 12 --json title,files -R owner/one", cwd="/w/a"
        )
        self.assertNotEqual(one, two)
        self.assertIn("src=title", one)
        self.assertIn("src=files,title", two)

    def test_status_fields_rotate_without_changing_key(self):
        combos = [
            "gh pr view 12 --json statusCheckRollup -R owner/one",
            "gh pr view 12 --json reviewDecision -R owner/one",
            "gh pr view 12 --json mergeStateStatus,mergedAt -R owner/one",
            "gh pr view 12 --json isDraft,mergeCommit,state -R owner/one",
            "gh pr view 12 --json state -R owner/one",
            "gh pr view 12 -R owner/one --jq .state",
        ]
        keys = {cpi.ci_pr_poll_identity(c, cwd="/w/a") for c in combos}
        self.assertEqual(len(keys), 1, keys)
        self.assertEqual(keys.pop(), "pr-view:12|repo:owner/one")

    def test_source_identity_independent_of_mixed_status(self):
        pure = cpi.ci_pr_poll_identity(
            "gh pr view 12 --json title -R owner/one", cwd="/w/a"
        )
        mixed = cpi.ci_pr_poll_identity(
            "gh pr view 12 --json title,statusCheckRollup,reviewDecision"
            " -R owner/one",
            cwd="/w/a",
        )
        repeated = cpi.ci_pr_poll_identity(
            "gh pr view 12 --json title,statusCheckRollup -R owner/one",
            cwd="/w/a",
        )
        self.assertEqual(pure, mixed)
        self.assertEqual(mixed, repeated)

    def test_metadata_only_and_plain_view_are_unclassified(self):
        self.assertIsNone(
            cpi.ci_pr_poll_identity("gh pr view 12 --json number", cwd="/w/a")
        )
        self.assertIsNone(
            cpi.ci_pr_poll_identity("gh pr view 12", cwd="/w/a")
        )
        self.assertIsNone(
            cpi.ci_pr_poll_identity(
                "gh pr view 12 --json labels,url -R owner/one", cwd="/w/a"
            )
        )
        self.assertIsNone(
            cpi.ci_pr_poll_identity(
                "git status && make test", cwd="/w/a"
            )
        )

    def test_quoted_jq_state_is_not_a_requested_field(self):
        self.assertIsNone(
            cpi.ci_pr_poll_identity(
                "gh pr view 12 --jq '.state' -R owner/one", cwd="/w/a"
            )
        )
        keyed = cpi.ci_pr_poll_identity(
            "gh pr view 12 --json title --jq '.state' -R owner/one", cwd="/w/a"
        )
        clean = cpi.ci_pr_poll_identity(
            "gh pr view 12 --json title -R owner/one", cwd="/w/a"
        )
        self.assertEqual(keyed, clean)

    def test_metadata_plus_quoted_state_repeated_is_stable(self):
        cmd = "gh pr view 12 --json number --jq '.state' -R owner/one"
        first = cpi.ci_pr_poll_identity(cmd, cwd="/w/a")
        second = cpi.ci_pr_poll_identity(cmd, cwd="/w/a")
        self.assertEqual(first, second)
        self.assertIsNone(first)

    def test_unquoted_jq_does_not_override_explicit_json_fields(self):
        self.assertIsNone(cpi.ci_pr_poll_identity(
            'gh pr view 12 --json url --jq .state -R owner/one', cwd='/w/a'
        ))


class ChecksAndCompoundTests(unittest.TestCase):
    def test_checks_key_is_repository_aware(self):
        a = cpi.ci_pr_poll_identity("gh pr checks 7 -R owner/one", cwd="/w/a")
        b = cpi.ci_pr_poll_identity("gh pr checks 7 -R other/two", cwd="/w/a")
        c = cpi.ci_pr_poll_identity("gh pr checks 7", cwd="/w/c")
        c_again = cpi.ci_pr_poll_identity("gh pr checks 7", cwd="/w/c")
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertEqual(c, c_again)
        self.assertTrue(c.startswith("pr-checks:7|cwd:/w/c"))

    def test_checks_and_view_do_not_share_a_key(self):
        checks = cpi.ci_pr_poll_identity(
            "gh pr checks 12 -R owner/one", cwd="/w/a"
        )
        view = cpi.ci_pr_poll_identity(
            "gh pr view 12 --json statusCheckRollup -R owner/one", cwd="/w/a"
        )
        self.assertNotEqual(checks, view)

    def test_compound_uses_first_matching_invocation(self):
        a = cpi.ci_pr_poll_identity(
            "echo hi; gh pr view 12 --json title -R owner/one", cwd="/w/a"
        )
        self.assertIn("pr-view:12|", a)
        quoted_doc = cpi.ci_pr_poll_identity(
            'git commit -m "docs for gh pr view 99 --json title"'
            " && gh pr view 12 --json title -R owner/one",
            cwd="/w/a",
        )
        self.assertIsNotNone(quoted_doc)
        self.assertIn("pr-view:12|", quoted_doc)
        self.assertNotIn("99", quoted_doc.split("|", 1)[0])

    def test_repo_before_subcommand_in_compound(self):
        key = cpi.ci_pr_poll_identity(
            "cd /w && gh -R other/two pr checks 4", cwd="/w/a"
        )
        self.assertEqual(key, "pr-checks:4|repo:other/two")


class MalformedInputTests(unittest.TestCase):
    def test_non_string_and_empty_inputs_are_harmless(self):
        for bad in (None, 12, 4.5, b"gh pr view 12", ["gh pr view 12"], ""):
            self.assertIsNone(cpi.ci_pr_poll_identity(bad, cwd="/w/a"))

    def test_unbalanced_quotes_and_broken_flags_are_harmless(self):
        # invocation swallowed by an unterminated quote is not classified
        self.assertIsNone(
            cpi.ci_pr_poll_identity("echo 'note: gh pr view 12", cwd="/w/a")
        )
        # unterminated --json value: no exception and a stable repeat
        odd = "gh pr view 12 --json 'title -R owner/one"
        self.assertEqual(
            cpi.ci_pr_poll_identity(odd, cwd="/w/a"),
            cpi.ci_pr_poll_identity(odd, cwd="/w/a"),
        )
        self.assertIsNone(
            cpi.ci_pr_poll_identity("gh pr view 12 -R --json", cwd="/w/a")
        )
        self.assertIsNone(
            cpi.ci_pr_poll_identity("gh pr view 12 -R", cwd="/w/a")
        )
        # non-string cwd with explicit repo still keys (repo scope wins)
        self.assertIsNotNone(
            cpi.ci_pr_poll_identity(
                "gh pr view 12 --json title -R owner/one", cwd=None
            )
        )

    def test_non_numeric_and_non_pr_targets_are_not_classified(self):
        self.assertIsNone(
            cpi.ci_pr_poll_identity("gh pr view https://x.io/1 -R o/r", cwd="/w")
        )
        self.assertIsNone(
            cpi.ci_pr_poll_identity("gh run view 12 --json title", cwd="/w")
        )
        self.assertIsNone(
            cpi.ci_pr_poll_identity("gh pr view 12x -R o/r", cwd="/w")
        )


if __name__ == "__main__":
    unittest.main()
