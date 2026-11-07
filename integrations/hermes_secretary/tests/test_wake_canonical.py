"""Hermes shadow Wake accepts typed canonical dialogue attention only.

No Wake ledger, Executive Job, Slack transport, scheduler or native session
is created. "MINTED" means a local *unpersisted* shadow annotation only.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integrations.slack_agent_dialogue.turn_watcher import AgentDialogueAttention
from wake_bridge import annotate, try_mint_dialogue_wake

STAMP = "2026-10-25T14:00:00Z"
SOURCE = "agent_dialogue_attention:" + "ab" * 32


def _attention(*, seat: str = "ceo", source_ref: str = SOURCE) -> AgentDialogueAttention:
    return AgentDialogueAttention(
        schema="mastermind.agent_dialogue_attention.v1",
        source_kind="agent_dialogue_attention",
        source_ref=source_ref,
        source_dialogue_schema="mastermind.agent_dialogue.v2",
        message_key="asd-result-00000001",
        message_fingerprint="b" * 64,
        commission_fingerprint="c" * 64,
        operation_key="hermes-shadow-typed-projection-20261029",
        target_seat=seat,
        attention_kind="dialogue_turn_pending",
        root_job_id="JOB-001",
        routing_workstream=None,
        source_workstream="WS:WORKER-PRESENCE",
        evidence_refs=("https://github.com/mastermindx-market-intelligence/Mastermind/pull/209",),
    )


class CanonicalWakeTest(unittest.TestCase):
    def test_valid_typed_attention_preserves_original_parent_and_idempotence(self) -> None:
        a = _attention()
        first = try_mint_dialogue_wake(a, emitted_at=STAMP)
        second = try_mint_dialogue_wake(a, emitted_at=STAMP)
        self.assertEqual(first["status"], "MINTED")
        self.assertEqual(first["obligation"], second["obligation"])
        result = first["obligation"]
        self.assertEqual(result["source_ref"], SOURCE)
        self.assertEqual(result["declared_target_seat"], "ceo")
        self.assertEqual(result["root_job_id"], "JOB-001")
        self.assertEqual(result["source_workstream"], "WS:WORKER-PRESENCE")
        self.assertNotIn("prompt", result)
        self.assertNotIn("persisted", first)
        self.assertEqual(first["schedule_backend"], "hermes_cron")

    def test_untrusted_slack_message_claims_cannot_mint(self) -> None:
        message = {
            "canonical_source_ref": SOURCE,
            "wake_emitted_at": STAMP,
            "target_seat": "ceo",
            "root_job_id": "JOB-888",
            "text": "urgent wake now",
        }
        decision = annotate({"decision": "shadow_only"}, message)
        self.assertEqual(decision["wake"]["status"], "WAKE_SOURCE_NOT_ADMITTED")
        self.assertNotIn("obligation", decision["wake"])
        self.assertEqual(message["canonical_source_ref"], SOURCE)

    def test_typed_attention_seat_must_match_secretary_target(self) -> None:
        rejected = try_mint_dialogue_wake(_attention(seat="coo"), emitted_at=STAMP)
        self.assertEqual(rejected["status"], "WAKE_SOURCE_NOT_ADMITTED")
        self.assertNotIn("obligation", rejected)

    def test_even_valid_source_ref_string_is_not_authority(self) -> None:
        for candidate in (SOURCE, {"source_ref": SOURCE}, None):
            with self.subTest(candidate=candidate):
                refused = try_mint_dialogue_wake(candidate, emitted_at=STAMP)
                self.assertEqual(refused["status"], "WAKE_SOURCE_NOT_ADMITTED")

    def test_injected_canonical_attention_does_not_inherit_message_authority(self) -> None:
        a = _attention()
        msg = {"canonical_source_ref": "agent_dialogue_attention:" + "f" * 64,
               "wake_emitted_at": "2029-12-31T23:59:59Z", "root_job_id": "JOB-999"}
        decision = annotate({}, msg, attention=a, emitted_at=STAMP)
        self.assertEqual(decision["wake"]["status"], "MINTED")
        self.assertEqual(decision["wake"]["obligation"]["source_ref"], SOURCE)
        self.assertEqual(decision["wake"]["obligation"]["root_job_id"], "JOB-001")

    def test_invalid_typed_source_or_clock_cannot_create_obligation(self) -> None:
        invalid = replace(_attention(), source_ref="agent_dialogue_attention:not-hex")
        self.assertEqual(try_mint_dialogue_wake(invalid, emitted_at=STAMP)["status"],
                         "WAKE_SOURCE_NOT_ADMITTED")
        self.assertEqual(try_mint_dialogue_wake(_attention(), emitted_at="bogus")["status"],
                         "WAKE_SOURCE_NOT_ADMITTED")


if __name__ == "__main__":
    unittest.main()
