"""Synthetic proxy policy checks: zero sockets and zero external provider calls."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from integrations.hermes_runtime.egress import (
    PROXY_ENV_NAME, ROLE_ENV_NAME, native_egress_child_env,
)
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.systemd_unit import render_user_unit
from integrations.hermes_harness.stack import compose_profile


class NativeEgressTests(unittest.TestCase):
    def test_secretary_explicit_loopback_proxy(self):
        private = {ROLE_ENV_NAME: "mmsecretary", PROXY_ENV_NAME: "http://127.0.0.2:18651"}
        self.assertEqual(native_egress_child_env("mmsecretary", private), {
            "HTTPS_PROXY": "http://127.0.0.2:18651", "NO_PROXY": "127.0.0.1,localhost,127.0.0.2",
        })

    def test_meta_role_receives_only_own_proxy(self):
        private = {ROLE_ENV_NAME: "mmmeta", PROXY_ENV_NAME: "http://127.0.0.3:18652",
                   "ZAI_API_KEY": "fake-meta-token", "HERMES_SLACK_BOT_TOKEN": "fake-bot-token"}
        env = native_egress_child_env("mmmeta", private)
        self.assertEqual(set(env), {"HTTPS_PROXY", "NO_PROXY"})
        self.assertNotIn("ZAI_API_KEY", env)
        self.assertNotIn("HERMES_SLACK_BOT_TOKEN", env)

    def test_missing_proxy_fails_even_with_ambient_shell_proxy(self):
        with mock.patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.2:18651"}):
            with self.assertRaises(RuntimeRefusal) as cm:
                native_egress_child_env("mmsecretary", {ROLE_ENV_NAME: "mmsecretary"})
            self.assertEqual(cm.exception.code, "NATIVE_EGRESS_PROXY_NOT_ENROLLED")

    def test_cross_role_binding_refused(self):
        private = {ROLE_ENV_NAME: "mmmeta", PROXY_ENV_NAME: "http://127.0.0.3:18652"}
        with self.assertRaises(RuntimeRefusal) as cm:
            native_egress_child_env("mmsecretary", private)
        self.assertEqual(cm.exception.code, "NATIVE_EGRESS_ROLE_BINDING_MISSING")

    def test_cross_role_proxy_address_denied_even_with_distinct_port(self):
        with self.assertRaises(RuntimeRefusal) as cm:
            native_egress_child_env("mmsecretary", {
                ROLE_ENV_NAME: "mmsecretary",
                PROXY_ENV_NAME: "http://127.0.0.3:18651",
            })
        self.assertEqual(cm.exception.code, "NATIVE_EGRESS_PROXY_INVALID")
        with self.assertRaises(RuntimeRefusal) as cm:
            native_egress_child_env("mmmeta", {
                ROLE_ENV_NAME: "mmmeta",
                PROXY_ENV_NAME: "http://127.0.0.2:18652",
            })
        self.assertEqual(cm.exception.code, "NATIVE_EGRESS_PROXY_INVALID")

    def test_unknown_role_refused(self):
        with self.assertRaises(RuntimeRefusal) as cm:
            native_egress_child_env("unknown", {ROLE_ENV_NAME: "unknown", PROXY_ENV_NAME: "http://127.0.0.3:18652"})
        self.assertEqual(cm.exception.code, "NATIVE_EGRESS_ROLE_REFUSED")

    def test_noncanonical_or_external_proxy_urls_refused(self):
        bad = ["http://127.0.0.1:18651", "http://127.0.0.3:18651", "" , "http://127.0.0.1", "http://127.0.0.1:80", "http://127.0.0.1:65536",
               "http://127.0.0.1:00018651", "http://localhost:18651",
               "http://[::1]:18651", "http://10.0.0.1:18651", "http://0.0.0.0:18651",
               "http://127.0.0.1:18651/", "http://127.0.0.1:18651/x",
               "https://127.0.0.1:18651", "http://u:p@127.0.0.1:18651",
               "http://127.0.0.1:18651?allowed=any", "http://127.0.0.1:18651#x",
               "http://127.0.0.1:18651\nHTTPS_PROXY=http://malicious", "socks5://127.0.0.1:18651",
               "http://127.0.0.1:99999", "http://127.0.0.1:0"]
        for value in bad:
            with self.subTest(url=value):
                with self.assertRaises(RuntimeRefusal):
                    native_egress_child_env("mmsecretary", {
                        ROLE_ENV_NAME: "mmsecretary", PROXY_ENV_NAME: value})

    def test_two_units_allow_only_their_own_proxy_address(self):
        with tempfile.TemporaryDirectory() as root:
            sources = {}
            for role in ("mmsecretary", "mmmeta"):
                profile = compose_profile(
                    role,
                    state_dir=Path(root) / (role + "-state"),
                    secrets_file=Path(root) / (role + ".secrets.env"),
                    hermes_home=Path(root) / (role + "-home"),
                )
                unit = render_user_unit(
                    profile, python_executable=sys.executable,
                    repo_root=Path(__file__).resolve().parents[3],
                )
                sources[role] = unit
                allow = [line for line in unit.splitlines()
                         if line.startswith("IPAddressAllow=")]
                self.assertEqual(len(allow), 2)
                self.assertIn("IPAddressAllow=127.0.0.1/32", allow)
                self.assertIn("IPAddressDeny=any", unit)
                self.assertNotIn("IPAddressAllow=localhost", unit)
            self.assertIn("IPAddressAllow=127.0.0.2/32", sources["mmsecretary"])
            self.assertNotIn("IPAddressAllow=127.0.0.3/32", sources["mmsecretary"])
            self.assertIn("IPAddressAllow=127.0.0.3/32", sources["mmmeta"])
            self.assertNotIn("IPAddressAllow=127.0.0.2/32", sources["mmmeta"])
            self.assertNotEqual(sources["mmmeta"], sources["mmsecretary"])

    def test_refusal_never_echoes_private_url(self):
        raw = "http://username:PRIVATE_SECRET_SENTINEL@evil.example:1234"
        with self.assertRaises(RuntimeRefusal) as cm:
            native_egress_child_env("mmmeta", {ROLE_ENV_NAME: "mmmeta", PROXY_ENV_NAME: raw})
        self.assertNotIn("PRIVATE_SECRET_SENTINEL", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
