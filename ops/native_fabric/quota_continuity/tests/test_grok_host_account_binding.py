#!/usr/bin/env python3
"""Offline Grok subscription/host binding regression; never read real auth."""
from __future__ import annotations

from contextlib import ExitStack
import importlib.util
import json
import os
import sys
from pathlib import Path
import socket
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

CANDIDATE = Path(__file__).resolve().parents[1] / "candidate"
SOURCE = Path(__file__).resolve().parents[1] / "source"
# Source closure is partially inherited, do not infer provider or project home.
sys.path[:0] = [str(CANDIDATE), str(SOURCE)]
MODULE = CANDIDATE / "native_remote.py"
SPEC = importlib.util.spec_from_file_location("grok_host_account_binding_fixture", MODULE)
native_remote = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(native_remote)


class HostAccountBindingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "fake-home"
        (self.home / ".grok").mkdir(parents=True)
        self.auth = self.home / ".grok/auth.json"
        self.auth.write_text("fake-only-no-provider-credential\\n")
        self.auth.chmod(0o600)
        self.host = "fixture-ubuntu0"
        self.node = "fixture-node"
        self.digest = "c" * 64
        self.here = self.root / self.digest / "ext"
        self.here.mkdir(parents=True)
        self.entry = {"roles": ["lanes"], "allowed_modes": ["grok"],
                      "hostnames": [self.node], "local": False}
        self.env = {
            "HOME": str(self.home), "POOL_ACCOUNT": "default",
            "POOL_ORCHESTRATOR_ID": "test-root", "POOL_LEASE_ID": "test-lease",
            "REMOTE_SUB_RUN_ID": "test-run", "LANE_REMOTE_HOST": self.host,
            "SUPPORT_DIGEST": self.digest, "LANE_LEASED": "1",
            "NATIVE_LEASE_ISSUED": str(time.time()),
            "NATIVE_LEASE_DEADLINE": str(time.time() + 180),
        }
        self.set_binding()
        self.write_hosts()

    def set_binding(self):
        s = self.auth.lstat()
        self.entry["grok_account_binding"] = {
            "schema": "mastermind.grok_host_account_binding.v1",
            "host": self.host, "account": "default", "subscription_scope": "chris-main-grok",
            "auth_identity": {key: getattr(s, "st_" + key)
                              for key in ("uid", "dev", "ino", "size", "mtime_ns", "ctime_ns")},
        }

    def write_hosts(self):
        (self.here / "hosts.json").write_text(json.dumps({self.host: self.entry}))

    def qualify(self):
        with patch.object(socket, "gethostname", return_value=self.node):
            return native_remote.scope("test-run", "grok", "grok-4.7", self.here, self.env)

    def test_bound_original_host_and_account_succeed(self):
        self.assertEqual("default", self.qualify()["account"])

    def test_missing_binding_fails_closed(self):
        self.entry.pop("grok_account_binding")
        self.write_hosts()
        with self.assertRaisesRegex(ValueError, "account_binding_unqualified"):
            self.qualify()

    def test_wrong_host_or_account_is_refused(self):
        for name, value in (("host", "fixture-ubuntu1"), ("account", "secretary-default")):
            with self.subTest(name=name):
                self.set_binding()
                self.entry["grok_account_binding"][name] = value
                self.write_hosts()
                with self.assertRaisesRegex(ValueError, "account_binding_unqualified"):
                    self.qualify()

    def test_changed_auth_object_requires_requalification(self):
        self.auth.write_text("other-fixture-credential-bytes\\n")
        with self.assertRaisesRegex(ValueError, "account_binding_unqualified"):
            self.qualify()

    def test_auth_symlink_or_lax_mode_is_refused(self):
        self.auth.chmod(0o644)
        self.set_binding()
        self.write_hosts()
        with self.assertRaisesRegex(ValueError, "account_binding_unqualified"):
            self.qualify()
        self.auth.chmod(0o600)
        self.auth.unlink()
        target = self.home / "other-test-token"
        target.write_text("fake-only\\n")
        self.auth.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "account_binding_unqualified"):
            self.qualify()

    def test_binding_rejects_bools_and_unqualified_subscription(self):
        self.entry["grok_account_binding"]["auth_identity"]["uid"] = True
        self.write_hosts()
        with self.assertRaisesRegex(ValueError, "account_binding_unqualified"):
            self.qualify()
        self.set_binding()
        self.entry["grok_account_binding"]["subscription_scope"] = ""
        self.write_hosts()
        with self.assertRaisesRegex(ValueError, "account_binding_unqualified"):
            self.qualify()

    def test_credential_mismatch_precedes_ephemeral_config_effect(self):
        self.entry.pop("grok_account_binding")
        self.write_hosts()
        with self.assertRaisesRegex(ValueError, "account_binding_unqualified"):
            native_remote.environment("grok", "grok-4.7", "test-run", self.here, self.env)
        self.assertFalse((self.here / "lanes").exists())

    def test_valid_environment_binds_only_fixture_auth_and_private_workspace(self):
        with patch.object(native_remote, "studio_projection",
                          return_value=SimpleNamespace(config_text="")):
            result = native_remote.environment("grok", "grok-4.7",
                                               "test-run", self.here, self.env)
        self.assertEqual(str(self.auth), result["GROK_AUTH_PATH"])
        self.assertTrue((self.here / "lanes/test-run.grok/config.toml").is_file())

    def test_refuses_changed_auth_without_creating_config(self):
        self.auth.write_text("wrong-account-same-local-path\\n")
        with self.assertRaisesRegex(ValueError, "account_binding_unqualified"):
            native_remote.environment("grok", "grok-4.7", "test-run", self.here, self.env)
        self.assertFalse((self.here / "lanes").exists())

    def test_rejects_invalid_host_registry_entry(self):
        (self.here / "hosts.json").write_text(json.dumps({self.host: None}))
        with self.assertRaises(ValueError):
            self.qualify()
        with self.assertRaisesRegex(ValueError, "account_binding_unqualified"):
            native_remote.environment("grok", "grok-4.7", "test-run", self.here, self.env)

    def test_unrelated_host_and_mode_policies_still_refuse(self):
        self.entry["allowed_modes"] = ["glm"]
        self.write_hosts()
        with self.assertRaisesRegex(ValueError, "mode_not_enrolled"):
            self.qualify()


if __name__ == "__main__":
    unittest.main()
