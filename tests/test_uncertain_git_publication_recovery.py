"""Regression specification for proposed safe forward-only Git publication.

These tests use isolated bare Git repositories. They never touch a connected
publisher, real branch, credential or production installation.
"""
from __future__ import annotations

import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RULE = ROOT / "docs/sol_skills/RECONCILE_STATE.md"
RUNBOOK = ROOT / "docs/runbooks/uncertain-git-publication-recovery.md"


def git(where: pathlib.Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(where), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


class ForwardGitPublicationContracts(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="mmx-safe-push-")
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.remote = root / "remote.git"
        self.a = root / "a"
        self.b = root / "b"
        git(root, "init", "--bare", str(self.remote))
        git(root, "clone", str(self.remote), str(self.a))
        git(self.a, "config", "user.name", "Regression Author")
        git(self.a, "config", "user.email", "regression@example.invalid")
        git(self.a, "checkout", "-b", "feature")
        self.commit(self.a, "base")
        git(self.a, "push", "origin", "HEAD:refs/heads/feature")
        git(root, "clone", "-b", "feature", str(self.remote), str(self.b))
        git(self.b, "config", "user.name", "Regression Author")
        git(self.b, "config", "user.email", "regression@example.invalid")

    def commit(self, where: pathlib.Path, label: str) -> str:
        with (where / (label + ".txt")).open("w", encoding="utf-8") as f:
            f.write(label + "\n")
        git(where, "add", label + ".txt")
        git(where, "commit", "-m", label)
        return git(where, "rev-parse", "HEAD").stdout.strip()

    def remote_sha(self) -> str:
        return git(self.remote, "rev-parse", "refs/heads/feature").stdout.strip()

    def test_lost_response_after_success_cannot_create_second_git_update(self) -> None:
        """A confirmed present-state match is a no-push disposition."""
        desired = self.commit(self.a, "success")
        git(self.a, "push", "origin", "HEAD:refs/heads/feature")
        observed = self.remote_sha()
        self.assertEqual(desired, observed)
        self.assertEqual(observed, self.remote_sha())

    def test_stale_nonforced_push_rejected_after_concurrent_writer(self) -> None:
        """Server ref CAS plus normal non-FF semantics prevents silent overwrite."""
        competing = self.commit(self.b, "competing")
        git(self.b, "push", "origin", "HEAD:refs/heads/feature")
        old_candidate = self.commit(self.a, "stale")
        self.assertNotEqual(old_candidate, competing)
        attempt = git(self.a, "push", "origin", "HEAD:refs/heads/feature", check=False)
        self.assertNotEqual(attempt.returncode, 0)
        self.assertEqual(self.remote_sha(), competing)

    def test_late_original_process_cannot_overwrite_newer_remote_descendant(self) -> None:
        """A delayed old push cannot roll the branch backward."""
        old = self.commit(self.a, "old")
        git(self.a, "push", "origin", "HEAD:refs/heads/feature")
        git(self.b, "fetch", "origin", "feature")
        git(self.b, "merge", "--ff-only", "origin/feature")
        new = self.commit(self.b, "new")
        git(self.b, "push", "origin", "HEAD:refs/heads/feature")
        self.assertNotEqual(new, old)
        stale_attempt = git(self.a, "push", "origin", "HEAD:refs/heads/feature", check=False)
        self.assertNotEqual(stale_attempt.returncode, 0)
        self.assertEqual(self.remote_sha(), new)

    def test_new_candidate_must_include_observed_remote_head(self) -> None:
        old = self.remote_sha()
        competing = self.commit(self.b, "other")
        git(self.b, "push", "origin", "HEAD:refs/heads/feature")
        result = git(self.a, "merge-base", "--is-ancestor", competing, "HEAD", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotEqual(old, competing)
        git(self.a, "fetch", "origin", "feature")
        git(self.a, "merge", "--ff-only", "origin/feature")
        candidate = self.commit(self.a, "candidate")
        result = git(self.a, "merge-base", "--is-ancestor", competing, candidate, check=False)
        self.assertEqual(result.returncode, 0)
        git(self.a, "push", "origin", "HEAD:refs/heads/feature")
        self.assertEqual(self.remote_sha(), candidate)

    def test_server_permission_refusal_does_not_alter_target(self) -> None:
        """Pre-receive denial is terminal for that effect."""
        hook = self.remote / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\necho 'permission denied' >&2\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        before = self.remote_sha()
        self.commit(self.a, "denied")
        result = git(self.a, "push", "origin", "HEAD:refs/heads/feature", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.remote_sha(), before)

    def test_wrong_target_has_no_effect_on_intended_branch(self) -> None:
        before = self.remote_sha()
        self.commit(self.a, "unrelated")
        git(self.a, "push", "origin", "HEAD:refs/heads/another-feature")
        self.assertEqual(self.remote_sha(), before)


class SourceLawContracts(unittest.TestCase):
    def test_procedure_exists_and_keeps_irreversible_effects_blocked(self) -> None:
        law = RULE.read_text(encoding="utf-8")
        self.assertIn("## Step 4C — Safe forward progress", law)
        self.assertIn("original action and its historical `EFFECT_UNKNOWN`", law)
        self.assertIn("non-force fast-forward", law)
        self.assertIn("Explicit permission/safety refusal", law)
        self.assertIn("No force, force-with-lease", law)
        self.assertIn("## Step 4A", law)

    def test_release_and_installation_not_inferred(self) -> None:
        runbook = RUNBOOK.read_text(encoding="utf-8")
        for needle in (
            "historical result", "CI", "production deployment",
            "installed advertised catalog", "Draft/HOLD",
            "not a current authorization to push",
        ):
            self.assertIn(needle, runbook)


if __name__ == "__main__":
    unittest.main()
