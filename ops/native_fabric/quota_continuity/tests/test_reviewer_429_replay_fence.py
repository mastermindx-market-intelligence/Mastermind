"""Exact 429 reviewer replay fences for the incumbent Fabric foreground owner.

Inert fault injection only.  This module never opens a provider session, sends
SSH, accepts a review, or mutates the selected native generation.  It reuses the
existing ledger/broker fixtures and tests the real continuation implementation.
"""
import json
import unittest

import test_foreground_continuation as existing
import fabric_continuation as continuation


PACKET = b"immutable independent reviewer packet\n"


class Reviewer429Safety(unittest.TestCase):
    def setUp(self):
        # Use the established isolated-broker fixture without subclassing its
        # own test methods (which would unintentionally rerun existing cases).
        self.owner = existing.Foreground(
            "test_quota_then_success_keeps_exact_attempt_and_effective_identity")
        self.owner.setUp()
        self.addCleanup(self.owner.doCleanups)

    def review(self, name):
        return continuation.foreground(
            self.owner.api, name, "review", cwd="~", packet=None,
            stdin_bytes=PACKET, root_id="root", parent_run_id="parent",
            task_complexity="C0_MECHANICAL")

    def assert_no_replay(self, run_id, expected_rc):
        self.assertEqual(len(self.owner.calls), 1)
        self.assertEqual(self.owner.calls[0][1], "review")
        self.assertEqual(self.owner.path(run_id, ".request.packet").read_bytes(), PACKET)
        self.assertFalse(self.owner.path(run_id, ".successor.json").exists())
        self.assertEqual(self.owner.inspect(run_id)["rc"], expected_rc)
        view = continuation.resolve(self.owner.api, run_id)
        self.assertEqual(view["effective_run_id"], run_id)
        self.assertEqual(view["prior_attempts"], [])
        self.assertEqual(view["controller_return"], "RECORDED")
        self.assertEqual(view["controller_reason"], "continuation_evidence_unqualified")
        # Multiple readbacks can never create another controller/provider call.
        continuation.resolve(self.owner.api, run_id)
        self.assertEqual(len(self.owner.calls), 1)

    def test_typed_proven_pre_task_429_can_continue_without_accepting_review(self):
        self.assertEqual(self.review("review-proven-pre-task"), 0)
        self.assertEqual(len(self.owner.calls), 2)
        first, second = self.owner.calls
        self.assertEqual([first[1], second[1]], ["review", "review"])
        self.assertEqual([first[2]["root_id"], second[2]["root_id"]], ["root", "root"])
        self.assertEqual([first[2]["parent_run_id"], second[2]["parent_run_id"]],
                         ["parent", "parent"])
        view = continuation.resolve(self.owner.api, "review-proven-pre-task")
        self.assertEqual(len(view["prior_attempts"]), 1)
        self.assertEqual(view["effective_status"]["rc"], 0)
        self.assertIs(view["effective_status"]["accepted"], False)
        self.assertEqual(
            self.owner.path(view["effective_run_id"], ".request.packet").read_bytes(),
            PACKET)

    def test_qwen_unconfirmed_final_429_is_not_proof_of_pre_task_rejection(self):
        original = self.owner.api.request

        def qwen_mid_task(run_id, task_class, **kwargs):
            original(run_id, task_class, **kwargs)
            # Qwen's partial/missing-final stream is an inferred 429, not a
            # provider-authenticated initial preflight.  It may have run work.
            f = self.owner.path(run_id, ".provider.json")
            row = json.loads(f.read_text())
            row.update(kind="unknown", command_rc=1, initial_rejection=False)
            row.pop("pre_task_evidence", None)
            f.write_text(json.dumps(row))
            self.owner.path(run_id, ".provider-observed.json").write_text(
                json.dumps({"recorded": True, "kind": "unknown"}))
            self.owner.path(run_id, ".log").write_text(
                "QWEN_FINAL_RESPONSE_UNCONFIRMED; wrapper inferred HTTP 429\n")
            self.owner.statuses[run_id]["rc"] = 1
            return 1

        self.owner.api.request = qwen_mid_task
        self.assertEqual(self.review("review-qwen-final-unconfirmed"), 1)
        self.assert_no_replay("review-qwen-final-unconfirmed", 1)

    def test_task_cli_started_true_blocks_even_typed_429_and_released_lease(self):
        original = self.owner.api.request

        def started(run_id, task_class, **kwargs):
            rc = original(run_id, task_class, **kwargs)
            f = self.owner.path(run_id, ".provider.json")
            row = json.loads(f.read_text())
            row["pre_task_evidence"]["task_cli_started"] = True
            f.write_text(json.dumps(row))
            return rc

        self.owner.api.request = started
        self.assertEqual(self.review("review-cli-started"), 75)
        self.assert_no_replay("review-cli-started", 75)


if __name__ == "__main__":
    unittest.main()
