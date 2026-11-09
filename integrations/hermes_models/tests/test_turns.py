"""Offline one-turn and one-tool-call coverage for every provider."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from integrations.hermes_models.contract import PROVIDERS  # noqa: E402
from integrations.hermes_models.tests.support import (  # noqa: E402
    TOOL,
    client,
    env_for,
    ok_body,
    read_meter,
    request,
    ScriptedTransport,
)


PROVIDERS_UNDER_TEST = (
    ("meta-ceo", "zai.glm-5.3"),
    ("secretary", "byteplus-modelark.glm-5.3-flash"),
    ("secretary", "byteplus-modelark.deepseek-v4.1-flash"),
    ("vision", "minimax.attended"),
    ("computer-use", "minimax.attended"),
    ("meta-ceo", "cursor-pool"),
)


class TurnTests(unittest.TestCase):
    def test_one_turn_and_one_tool_call_per_provider(self):
        for role, provider_id in PROVIDERS_UNDER_TEST:
            with self.subTest(provider_id=provider_id):
                self._exercise(role, provider_id)

    def _exercise(self, role: str, provider_id: str):
        spec = PROVIDERS[provider_id]
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            transport = ScriptedTransport(
                [ok_body(spec.served_model, tool_call=True), ok_body(spec.served_model, content="done")]
            )
            model = client(root, transport, env_for(provider_id))
            first = model.complete(
                request(
                    role,
                    provider_id,
                    effect="read_only",
                    turn=f"turn-{provider_id}",
                    tools=TOOL,
                )
            )
            self.assertTrue(first.ok)
            self.assertFalse(first.replayed)
            self.assertFalse(first.executive_admission)
            self.assertFalse(first.capacity_claimed)
            self.assertEqual(first.served_model, spec.served_model)
            self.assertEqual(len(first.tool_calls), 1)
            self.assertEqual(first.tool_calls[0]["function"]["name"], "clarify")
            self.assertEqual(transport.calls[0]["body"]["model"], spec.served_model)
            self.assertEqual(transport.calls[0]["url"], spec.base_url.rstrip("/") + "/chat/completions")
            self.assertNotIn("api_key", transport.calls[0]["body"])
            follow = model.complete(
                request(
                    role,
                    provider_id,
                    effect="read_only",
                    turn=f"turn-{provider_id}-tool",
                    messages=(
                        {"role": "user", "content": "status"},
                        first.message,
                        {"role": "tool", "tool_call_id": "call_1", "content": "clear"},
                    ),
                )
            )
            self.assertTrue(follow.ok)
            self.assertEqual(follow.message["content"], "done")
            self.assertEqual(len(transport.calls), 2)
            rows = read_meter(root / "usage.jsonl")
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["tool_calls"], 1)
            self.assertEqual(rows[0]["input_tokens"], 11)
            self.assertEqual(rows[0]["cached_input_tokens"], 2)
            self.assertEqual(rows[0]["output_tokens"], 4)
            self.assertEqual(rows[0]["quota_debit"], 0.01)
            self.assertEqual(rows[0]["account"], "pool-a")
            self.assertEqual(rows[0]["weekly_reset"], "2026-11-01T00:00:00Z")
            self.assertFalse(rows[0]["replayed"])
            self.assertFalse(rows[0]["executive_admission"])
            self.assertFalse(rows[0]["capacity_claimed"])
            self.assertEqual(stat_mode(root / "usage.jsonl"), 0o600)


def stat_mode(path: Path) -> int:
    import stat

    return stat.S_IMODE(path.stat().st_mode)


if __name__ == "__main__":
    unittest.main()
