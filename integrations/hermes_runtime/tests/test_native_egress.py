"""Synthetic proxy policy checks: zero sockets and zero external provider calls."""
from __future__ import annotations

import os
import unittest
from unittest import mock

from integrations.hermes_runtime.egress import (
    PROXY_ENV_NAME, ROLE_ENV_NAME, native_egress_child_env,
)
from integrations.hermes_runtime.errors import RuntimeRefusal


class NativeEgressTests(unittest.TestCase):
    def test_secretary_explicit_loopback_proxy(self):
        private = {ROLE_ENV_NAME: "mmsecretary", PROXY_ENV_NAME: "http://127.0.0.1:18651"}
        self.assertEqual(native_egress_child_env("mmsecretary", private), {
            "HTTPS_PROXY": "http://127.0.0.1:18651", "NO_PROXY": "127.0.0.1,localhost",
        })

    def test_meta_role_receives_only_own_proxy(self):
        private = {ROLE_ENV_NAME: "mmmeta", PROXY_ENV_NAME: "http://127.0.0.1:18652",
                   "ZAI_API_KEY": "fake-meta-token", "HERMES_SLACK_BOT_TOKEN": "fake-bot-token"}
        env = native_egress_child_env("mmmeta", private)
        self.assertEqual(set(env), {"HTTPS_PROXY", "NO_PROXY"})
        self.assertNotIn("ZAI_API_KEY", env)
        self.assertNotIn("HERMES_SLACK_BOT_TOKEN", env)

    def test_missing_proxy_fails_even_with_ambient_shell_proxy(self):
        with mock.patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:18651"}):
            with self.assertRaises(RuntimeRefusal) as cm:
                native_egress_child_env("mmsecretary", {ROLE_ENV_NAME: "mmsecretary"})
            self.assertEqual(cm.exception.code, "NATIVE_EGRESS_PROXY_NOT_ENROLLED")

    def test_cross_role_binding_refused(self):
        private = {ROLE_ENV_NAME: "mmmeta", PROXY_ENV_NAME: "http://127.0.0.1:18652"}
        with self.assertRaises(RuntimeRefusal) as cm:
            native_egress_child_env("mmsecretary", private)
        self.assertEqual(cm.exception.code, "NATIVE_EGRESS_ROLE_BINDING_MISSING")

    def test_unknown_role_refused(self):
        with self.assertRaises(RuntimeRefusal) as cm:
            native_egress_child_env("unknown", {ROLE_ENV_NAME: "unknown", PROXY_ENV_NAME: "http://127.0.0.1:18652"})
        self.assertEqual(cm.exception.code, "NATIVE_EGRESS_ROLE_REFUSED")

    def test_noncanonical_or_external_proxy_urls_refused(self):
        bad = ["", "http://127.0.0.1", "http://127.0.0.1:80", "http://127.0.0.1:65536",
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

    def test_refusal_never_echoes_private_url(self):
        raw = "http://username:PRIVATE_SECRET_SENTINEL@evil.example:1234"
        with self.assertRaises(RuntimeRefusal) as cm:
            native_egress_child_env("mmmeta", {ROLE_ENV_NAME: "mmmeta", PROXY_ENV_NAME: raw})
        self.assertNotIn("PRIVATE_SECRET_SENTINEL", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
