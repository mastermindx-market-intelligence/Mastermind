"""Mismatch refusal, 429 backoff without replay, and read-only outage failover."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from integrations.hermes_models.client import HttpResponse  # noqa: E402
from integrations.hermes_models.contract import PROVIDERS  # noqa: E402
from integrations.hermes_models.tests.support import (  # noqa: E402
    client,
    env_for,
    ok_body,
    read_meter,
    request,
    ScriptedTransport,
)


def _status(code: int, *, retry_after: str | None = None, body=None) -> HttpResponse:
    headers = {} if retry_after is None else {"Retry-After": retry_after}
    return HttpResponse(status=code, headers=headers, body=body or {})


class FailureTests(unittest.TestCase):
    def test_model_mismatch_refuses_without_failover(self):
        flash = PROVIDERS["byteplus-modelark.glm-5.3-flash"]
        deepseek = PROVIDERS["byteplus-modelark.deepseek-v4.1-flash"]
        wrong = ok_body(flash.served_model)
        wrong = HttpResponse(status=200, headers={}, body={**wrong.body, "model": "other-model"})
        transport = ScriptedTransport([wrong, ok_body(deepseek.served_model)])
        with tempfile.TemporaryDirectory() as raw:
            model = client(Path(raw), transport, env_for(flash.provider_id, deepseek.provider_id))
            result = model.complete(request("secretary", None, effect="read_only", turn="mismatch-1"))
        self.assertFalse(result.ok)
        self.assertEqual(result.outcome, "model_mismatch")
        self.assertEqual(result.served_model, "other-model")
        self.assertFalse(result.replayed)
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(len(result.attempts), 1)

    def test_missing_served_model_is_unknown(self):
        spec = PROVIDERS["zai.glm-5.3"]
        transport = ScriptedTransport([HttpResponse(status=200, headers={}, body={"choices": []})])
        with tempfile.TemporaryDirectory() as raw:
            model = client(Path(raw), transport, env_for(spec.provider_id))
            result = model.complete(request("meta-ceo", spec.provider_id, effect="read_only", turn="unknown-1"))
        self.assertEqual(result.outcome, "served_model_unknown")
        self.assertIsNone(result.served_model)
        self.assertEqual(len(transport.calls), 1)

    def test_429_records_backoff_and_does_not_replay_or_failover(self):
        flash = PROVIDERS["byteplus-modelark.glm-5.3-flash"]
        deepseek = PROVIDERS["byteplus-modelark.deepseek-v4.1-flash"]
        transport = ScriptedTransport(
            [_status(429, retry_after="2"), ok_body(deepseek.served_model)]
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            model = client(root, transport, env_for(flash.provider_id))
            result = model.complete(request("secretary", None, effect="read_only", turn="limit-1"))
            rows = read_meter(root / "usage.jsonl")
        self.assertEqual(result.outcome, "rate_limited")
        self.assertEqual(result.backoff_seconds, 2.0)
        self.assertFalse(result.replayed)
        self.assertTrue(all(attempt.replayed is False for attempt in result.attempts))
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(len(transport.responses), 1)
        self.assertEqual(rows[0]["outcome"], "rate_limited")
        self.assertEqual(rows[0]["backoff_seconds"], 2.0)
        self.assertFalse(rows[0]["replayed"])

    def test_429_without_retry_after_uses_bounded_backoff(self):
        spec = PROVIDERS["minimax.attended"]
        transport = ScriptedTransport([_status(429)])
        with tempfile.TemporaryDirectory() as raw:
            model = client(Path(raw), transport, env_for(spec.provider_id))
            result = model.complete(request("vision", None, effect="side_effecting", turn="limit-2"))
        self.assertEqual(result.backoff_seconds, 60.0)
        self.assertEqual(len(transport.calls), 1)

    def test_read_only_outage_fails_over_once_and_side_effecting_does_not(self):
        flash = PROVIDERS["byteplus-modelark.glm-5.3-flash"]
        deepseek = PROVIDERS["byteplus-modelark.deepseek-v4.1-flash"]
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            read_transport = ScriptedTransport([_status(503), ok_body(deepseek.served_model)])
            read_model = client(root, read_transport, env_for(flash.provider_id))
            read_result = read_model.complete(
                request("secretary", None, effect="read_only", turn="outage-read")
            )
            self.assertTrue(read_result.ok)
            self.assertEqual(read_result.provider_id, deepseek.provider_id)
            self.assertEqual(read_result.served_model, deepseek.served_model)
            self.assertEqual(len(read_transport.calls), 2)
            self.assertEqual(read_transport.calls[0]["body"]["model"], flash.served_model)
            self.assertEqual(read_transport.calls[1]["body"]["model"], deepseek.served_model)
            self.assertFalse(any("cursor-pool" in call["url"] for call in read_transport.calls))
            rows = read_meter(root / "usage.jsonl")
            self.assertEqual(rows[0]["outcome"], "outage")
            self.assertEqual(rows[1]["outcome"], "ok")
            self.assertEqual(rows[1]["failover_from"], flash.provider_id)
            self.assertFalse(rows[1]["replayed"])

            side_transport = ScriptedTransport([_status(503), ok_body(deepseek.served_model)])
            side_model = client(root, side_transport, env_for(flash.provider_id))
            side = side_model.complete(request("secretary", None, effect="side_effecting", turn="outage-side"))
            self.assertEqual(side.outcome, "outage")
            self.assertEqual(len(side_transport.calls), 1)
            self.assertEqual(len(side_transport.responses), 1)

            default_transport = ScriptedTransport([OSError("down"), ok_body(deepseek.served_model)])
            default_model = client(root, default_transport, env_for(flash.provider_id))
            default = default_model.complete(
                request("watcher", None, effect="side_effecting", turn="outage-default")
            )
            self.assertEqual(default.outcome, "outage")
            self.assertEqual(len(default_transport.calls), 1)

    def test_auth_rejection_does_not_failover(self):
        flash = PROVIDERS["byteplus-modelark.glm-5.3-flash"]
        deepseek = PROVIDERS["byteplus-modelark.deepseek-v4.1-flash"]
        transport = ScriptedTransport([_status(401), ok_body(deepseek.served_model)])
        with tempfile.TemporaryDirectory() as raw:
            model = client(Path(raw), transport, env_for(flash.provider_id))
            result = model.complete(request("implementation-subagent", None, effect="read_only", turn="auth-1"))
        self.assertEqual(result.outcome, "auth_rejected")
        self.assertEqual(len(transport.calls), 1)


if __name__ == "__main__":
    unittest.main()
