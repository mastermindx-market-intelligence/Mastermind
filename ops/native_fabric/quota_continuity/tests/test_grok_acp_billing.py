"""Grok Build's authenticated billing reader is read-only and never guesses quota."""
import importlib.util
import io
import json
import subprocess
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
START = "2026-10-19T05:54:40Z"
END = "2026-10-26T05:54:40Z"
NOW = "2026-10-22T18:43:43Z"


def load(which):
    path = ROOT / which / "quota_remote.py"
    name = "grok_evidence_" + which
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def billing(pct="MISSING", start=START, end=END, ptype="USAGE_PERIOD_TYPE_WEEKLY"):
    config = {
        "currentPeriod": {"type": ptype, "start": start, "end": end},
        "isUnifiedBillingUser": True,
    }
    if pct != "MISSING":
        config["creditUsagePercent"] = pct
    return {"config": config}


class QuotaBillingTests(unittest.TestCase):
    def test_frozen_installed_preimage_and_reviewed_candidate_are_separate(self):
        import hashlib
        inventory = json.loads((ROOT / "rollout" / "native-preimages.json").read_text())
        original = (ROOT / "source" / "quota_remote.py").read_bytes()
        candidate = (ROOT / "candidate" / "quota_remote.py").read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(),
                         inventory["files"]["quota_remote.py"])
        self.assertNotEqual(original, candidate)
        self.assertIn(b"CACHE_PATH = os.path.realpath(", candidate)
        self.assertIn(b"def parse_grok_billing_payload(", candidate)

    def test_explicit_percent_is_valid_and_observation_is_weekly(self):
        module = load("candidate")
        rows = module.parse_grok_billing_payload(billing(27.5), NOW)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.provider, "grok")
        self.assertEqual(row.window, "weekly")
        self.assertAlmostEqual(row.remaining_pct, 72.5)
        self.assertEqual(row.cap, 100.0)
        self.assertEqual(row.reset_at, "2026-10-26T05:54:40Z")
        self.assertEqual(row.source, "GROK_BUILD_ACP_BILLING")

    def test_missing_percent_is_unknown_not_zero(self):
        module = load("candidate")
        for pct in ("MISSING", "0", True, None, -1, 102, float("nan")):
            with self.subTest(value=repr(pct)):
                rows = module.parse_grok_billing_payload(billing(pct), NOW)
                self.assertEqual(len(rows), 1)
                self.assertIsNone(rows[0].remaining_pct)
                self.assertIsNone(rows[0].used)
                self.assertEqual(rows[0].confidence, 0.0)
                self.assertIn("WINDOW_ONLY", rows[0].source)
        fully_available = module.parse_grok_billing_payload(billing(0.0), NOW)[0]
        self.assertEqual(fully_available.remaining_pct, 100.0)
        exhausted = module.parse_grok_billing_payload(billing(100.0), NOW)[0]
        self.assertEqual(exhausted.remaining_pct, 0.0)

    def test_bad_period_missing_config_and_future_timestamp_refuse(self):
        module = load("candidate")
        variants = [
            {}, {"config": {}}, billing(1, ptype="USAGE_PERIOD_TYPE_MONTHLY"),
            billing(1, start="2026-10-25T00:00:00Z"),
            billing(1, end="2026-10-19T03:00:00Z"),
            billing(1, end="2027-01-01T00:00:00Z"),
            billing(1, start="garbage"),
            billing(1, start="2026-10-19T05:54:40"),
            billing(1, end="2026-10-26T05:54:40"),
        ]
        for value in variants:
            with self.subTest(value=value):
                self.assertEqual(module.parse_grok_billing_payload(value, NOW), [])

    def test_grok_reader_never_reads_or_writes_cached_positive(self):
        module = load("candidate")
        valid = module.parse_grok_billing_payload(billing(40), NOW)
        with patch.dict(module.READERS, {"grok": lambda: valid}):
            self.assertEqual(module.read_provider("grok", cache_path="/does-not-exist")[0].remaining_pct, 60.0)
        def failed():
            raise RuntimeError("auth failed")
        with patch.dict(module.READERS, {"grok": failed}):
            result = module.read_provider("grok", cache_path="/does-not-exist")
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0].remaining_pct)
        self.assertEqual(result[0].source, "UNKNOWN")

    def test_unusable_billing_reader_returns_explicit_unknown(self):
        module = load("candidate")
        with patch.dict(module.READERS, {"grok": lambda: []}):
            rows = module.read_provider("grok")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].provider, "grok")
        self.assertEqual(rows[0].source, "UNKNOWN")
        self.assertIsNone(rows[0].remaining_pct)

    def test_acp_performs_only_initialize_and_billing_no_model_prompt(self):
        module = load("candidate")
        read_fd, write_fd = os.pipe()
        sent = []
        class Writer:
            def write(self, raw):
                obj = json.loads(raw)
                sent.append(obj)
                response = {
                    "jsonrpc": "2.0", "id": obj["id"],
                    "result": {"agentCapabilities": {}} if obj["method"] == "initialize"
                    else billing(12.0),
                }
                os.write(write_fd, (json.dumps(response) + "\n").encode())
            def flush(self):
                pass
            def close(self):
                pass
        class Process:
            stdin = Writer()
            stdout = os.fdopen(read_fd, "rb", buffering=0)
            pid = 12345678
            wait_calls = 0
            def poll(self):
                return None
            def wait(self, timeout=None):
                self.wait_calls += 1
                if self.wait_calls == 1:
                    raise subprocess.TimeoutExpired(cmd="grok", timeout=timeout)
                return 0
        fake = Process()
        try:
            with patch.object(module.shutil, "which", return_value="/fake/grok"), \
                 patch.object(module.subprocess, "Popen", return_value=fake) as launched, \
                 patch.object(module.os, "killpg", return_value=None) as killed:
                rows = module._live_grok()
            self.assertEqual(fake.wait_calls, 2, "SIGKILL escalation must reap subprocess")
            self.assertEqual(killed.call_count, 2)
            self.assertEqual(launched.call_args.args[0], ["/fake/grok", "agent", "stdio"])
            self.assertEqual([x["method"] for x in sent], ["initialize", "_x.ai/billing"])
            self.assertFalse(sent[0]["params"]["clientCapabilities"]["fs"]["readTextFile"])
            self.assertFalse(sent[0]["params"]["clientCapabilities"]["fs"]["writeTextFile"])
            self.assertEqual(len(rows), 1)
            self.assertAlmostEqual(rows[0].remaining_pct, 88.0)
        finally:
            fake.stdout.close()
            os.close(write_fd)


if __name__ == "__main__":
    unittest.main()
