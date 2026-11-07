"""Actual Brain -> Macro composition; only the provider SDK/network is replaced.

Run with the paired Macro engine/lib/config importable (vendor bootstrap or
PYTHONPATH) and MM_REQUIRE_PRODUCTION_MODE_COMPOSITION=1. The required full-CI
composition step supplies both; ordinary discovery skips this cross-repository
class rather than using the unrelated legacy Macro pin. All credentials are
synthetic; incumbent ledgers are redirected to a temporary directory.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from brain import client, production_inference, thinking_log


class DispatcherTests(unittest.TestCase):
    def test_explicit_unknown_or_empty_backend_cannot_fall_back(self):
        for name in ("fabric_typo", "production_mdoe", ""):
            with self.subTest(backend=name), patch.dict(os.environ, {"BOT_LLM_BACKEND": name}), \
                    patch.object(client.cli_bridge, "_cfg", side_effect=AssertionError("fallback")):
                self.assertFalse(client.available())
                self.assertEqual(client.call_model("system", "user"), (None, "no_backend"))

    def test_missing_owner_is_unavailable_without_legacy_dispatch(self):
        with patch.dict(os.environ, {"BOT_LLM_BACKEND": "production_mode",
                                     "BOT_LLM_PRODUCTION_MODE": "minimax_payg_api"}), \
                patch.object(production_inference, "_owner", side_effect=ImportError("absent")), \
                patch.object(client.cli_bridge, "reason_sync", side_effect=AssertionError("fallback")):
            self.assertFalse(client.available())
            self.assertEqual(client.call_model("system", "user"),
                             (None, "production_mode_owner_unavailable"))

    def test_bad_request_never_reaches_owner(self):
        with patch.object(production_inference, "_owner", side_effect=AssertionError("dispatch")):
            for limit in (True, 0, -1, 32769, "10"):
                self.assertEqual(production_inference.call_model("s", "u", max_tokens=limit),
                                 (None, "production_mode_invalid_request"))


class ProductionModeCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("MM_REQUIRE_PRODUCTION_MODE_COMPOSITION") != "1":
            raise unittest.SkipTest("Run in the required paired Macro composition step")
        try:
            from engine import provider_production_modes as owner
        except ImportError as exc:
            raise AssertionError("Real paired Macro production-mode owner is required") from exc
        cls.owner = owner
        cls.source_config = json.loads(Path(owner.DEFAULT_PATH).read_text())

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = json.loads(json.dumps(self.source_config))
        self.config["modes"]["minimax_payg_api"]["enabled"] = True
        self.config_path = self.root / "modes.json"
        self.write_config()
        self.constructors, self.dispatches, self.responses = [], [], []
        self.response = {"content": [{"type": "text", "text": "Grounded narration."}],
                         "usage": {"input_tokens": 19, "output_tokens": 7}}
        self.failure = None

        def start(patcher):
            self.addCleanup(patcher.stop)
            return patcher.start()

        start(patch.dict(os.environ, {
            "BOT_LLM_BACKEND": "production_mode",
            "BOT_LLM_PRODUCTION_MODE": "minimax_payg_api",
            "MINIMAX_API_KEY": "synthetic-test-credential",
            "PROVIDER_HEALTH_PATH": str(self.root / "health.jsonl"),
            "AI_COSTS_STATE_ROOT": str(self.root / "costs"),
        }, clear=True))
        start(patch.object(self.owner, "DEFAULT_PATH", self.config_path))
        start(patch.object(thinking_log, "log_turn_async",
                           side_effect=lambda **kw: self.responses.append(thinking_log.build_row(**kw))))
        for target, attr in ((client.cli_bridge, "reason_sync"),
                             (client.codex_bridge, "reason_sync"), (client, "api_available")):
            start(patch.object(target, attr, side_effect=AssertionError("legacy fallback")))

        testcase = self

        class SDK:
            def __init__(self, **kwargs):
                testcase.constructors.append(kwargs)
                testcase.assertEqual(kwargs.get("max_retries"), 0)
                self.messages = self

            def create(self, **kwargs):
                testcase.dispatches.append(kwargs)
                if testcase.failure is not None:
                    raise testcase.failure
                return testcase.response

        start(patch.dict("sys.modules", {"anthropic": types.SimpleNamespace(Anthropic=SDK)}))

    def write_config(self):
        self.config_path.write_text(json.dumps(self.config))

    def health_rows(self):
        path = self.root / "health.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def cost_rows(self):
        return [json.loads(line) for p in (self.root / "costs").rglob("*.jsonl")
                for line in p.read_text().splitlines()]

    def test_real_cio_narration_reaches_real_owner_and_existing_ledgers(self):
        from brain import cio

        result = cio._narrate({"as_of": "2026-11-04", "iso_week": "2026-W45",
                               "per_seat": {}, "book_summary": {},
                               "whats_working": [], "whats_broken": [],
                               "tuning_recommendations": []})
        self.assertEqual(result, "Grounded narration.")
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(self.dispatches[0]["model"], self.owner.MINIMAX_PINNED_MODEL)
        self.assertEqual(self.dispatches[0]["max_tokens"], 1500)
        self.assertIn("2026-W45", self.dispatches[0]["messages"][0]["content"])
        self.assertEqual(self.constructors[0]["base_url"], "https://api.minimax.io/anthropic")
        self.assertEqual(len(self.health_rows()), 1)
        costs = self.cost_rows()
        self.assertEqual(len(costs), 1)
        self.assertEqual((costs[0]["provider"], costs[0]["key_id"], costs[0]["input_tokens"]),
                         ("minimax", "prod_api:minimax", 19))
        self.assertEqual(len(self.responses), 1)
        self.assertEqual((self.responses[0]["seat"], self.responses[0]["book"],
                          self.responses[0]["mode"], self.responses[0]["backend"]),
                         ("cio", "system", "minimax_payg_api", "production_mode"))

    def test_disabled_mode_never_dispatches(self):
        self.config["modes"]["minimax_payg_api"]["enabled"] = False
        self.write_config()
        self.assertFalse(client.available())
        self.assertEqual(client.call_model("s", "u"), (None, "production_mode_disabled"))
        self.assertEqual(self.dispatches, [])
        self.assertEqual(self.cost_rows(), [])

    def test_missing_credential_never_dispatches(self):
        del os.environ["MINIMAX_API_KEY"]
        self.assertFalse(client.available())
        self.assertEqual(client.call_model("s", "u"), (None, "production_mode_unconfigured"))
        self.assertEqual(self.dispatches, [])

    def test_unqualified_glm_never_even_resolves_credentials(self):
        os.environ["BOT_LLM_PRODUCTION_MODE"] = "glm_general_api"
        self.config["modes"]["glm_general_api"]["enabled"] = True
        self.write_config()
        with patch.object(self.owner, "_resolve_credential", side_effect=AssertionError("secret read")):
            self.assertFalse(client.available())
            self.assertEqual(client.call_model("s", "u"), (None, "production_mode_unqualified"))
        self.assertEqual(self.dispatches, [])

    def test_unknown_mode_is_closed_and_error_is_bounded(self):
        os.environ["BOT_LLM_PRODUCTION_MODE"] = "not-a-real-mode-secret-like-input"
        self.assertEqual(client.call_model("s", "u"), (None, "production_mode_invalid_config"))
        self.assertEqual(self.dispatches, [])

    def test_invalid_pinned_destination_is_rejected_before_dispatch(self):
        self.config["modes"]["minimax_payg_api"]["base_url"] = "https://wrong.invalid/anthropic"
        self.write_config()
        self.assertEqual(client.call_model("s", "u"), (None, "production_mode_invalid_config"))
        self.assertEqual(self.dispatches, [])

    def test_timeout_after_dispatch_does_not_replay_or_fall_back(self):
        self.failure = TimeoutError("never expose this provider detail")
        self.assertEqual(client.call_model("s", "u"), (None, "production_mode_timeout"))
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(len(self.constructors), 1)
        self.assertEqual(self.cost_rows(), [])
        self.assertEqual(self.health_rows()[0]["error_class"], "timeout")

    def test_empty_text_does_not_become_success(self):
        self.response["content"] = []
        self.assertEqual(client.call_model("s", "u"), (None, "production_mode_error"))
        self.assertEqual(len(self.dispatches), 1)

    def test_response_logging_failure_cannot_replay_or_discard_answer(self):
        with patch.object(thinking_log, "log_turn_async", side_effect=RuntimeError("log unavailable")):
            self.assertEqual(client.call_model("s", "u"), ("Grounded narration.", None))
        self.assertEqual(len(self.dispatches), 1)
        self.assertEqual(len(self.cost_rows()), 1)

    def test_empty_explicit_mode_does_not_use_config_default(self):
        os.environ["BOT_LLM_PRODUCTION_MODE"] = ""
        with patch.object(client.cli_bridge, "_cfg", return_value={"production_mode": "minimax_payg_api"}):
            self.assertEqual(client.call_model("s", "u"), (None, "production_mode_not_selected"))
        self.assertEqual(self.dispatches, [])

    def test_configured_mode_and_attribution_overrides(self):
        del os.environ["BOT_LLM_PRODUCTION_MODE"]
        with patch.object(client.cli_bridge, "_cfg", return_value={"production_mode": "minimax_payg_api"}):
            self.assertEqual(client.call_model("s", "u", role="analyst", seat="reviewer",
                                               record_book="system", max_tokens=80),
                             ("Grounded narration.", None))
        self.assertEqual(self.dispatches[0]["max_tokens"], 80)
        self.assertEqual(self.responses[0]["seat"], "reviewer")


if __name__ == "__main__":
    unittest.main()
