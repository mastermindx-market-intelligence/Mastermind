"""Native doctor observes actual role credentials, not installer shell variables.

Only closed synthetic fixtures can be persisted. No provider is invoked.
"""
from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from integrations.hermes_harness.doctor import doctor

FAKE_MODELARK = "test-modelark-credential-private-not-live-123456"
FAKE_ZAI = "test-zai-credential-private-not-live-123456"
GATEWAY = "fixture-gateway-token-distinct-123456"
DASHBOARD = "fixture-dashboard-password-distinct-123456"


class NativeDoctorCredentialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hermes-doctor-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.directory = self.home / ".config" / "hermes-runtime"
        self.directory.mkdir(mode=0o700, parents=True)

    @staticmethod
    def _private_fixture(path: Path, data: str) -> None:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(data)

    def _write_role(self, role: str, case: str = "empty"):
        if role not in {"mmsecretary", "mmmeta"}:
            raise ValueError("unknown synthetic role")
        scenarios = {"empty", "file_pointer", "invalid_pointer", "core_ready",
                     "shared_roles", "shared_model", "incumbent"}
        if case not in scenarios:
            raise ValueError("unknown synthetic role scenario")
        gateway, dashboard = GATEWAY, DASHBOARD
        extra = ""
        if case == "invalid_pointer":
            if role != "mmsecretary":
                raise ValueError("invalid pointer fixture is Secretary-only")
            extra = "BYTEPLUS_MODELARK_API_KEY_FILE=relative.key\nBYTEPLUS_MODELARK_API_KEY=" + FAKE_MODELARK + "\n"
        if case in {"file_pointer", "core_ready", "shared_model"}:
            key_name = "BYTEPLUS_MODELARK_API_KEY_FILE" if role == "mmsecretary" else "ZAI_API_KEY_FILE"
            filename = "shared-provider.key" if case == "shared_model" else ("modelark.key" if role == "mmsecretary" else "zai.key")
            extra = key_name + "=" + str(self.directory / filename) + "\n"
        if case in {"core_ready", "shared_roles", "shared_model", "incumbent"}:
            proxy = "http://127.0.0.2:18651" if role == "mmsecretary" or case == "shared_roles" else "http://127.0.0.3:18652"
            extra += "HERMES_NATIVE_EGRESS_ROLE=" + role + "\nHERMES_NATIVE_HTTPS_PROXY=" + proxy + "\n"
            user_id = "UHERMESEC00001" if role == "mmsecretary" else "UHERMEMETA0001"
            if case == "shared_roles":
                user_id, bot_value = "USHAREDBOT001", "shared-token-fixture-123456"
            elif case == "core_ready":
                bot_value = "test-secretary-slack-token-only-123456" if role == "mmsecretary" else "test-meta-slack-token-only-123456"
                if role == "mmmeta":
                    gateway, dashboard = "test-meta-gateway-token-123456", "test-meta-dashboard-token-123456"
            elif case == "shared_model":
                bot_value = "secretary-distinct-slack-token-123456" if role == "mmsecretary" else "meta-distinct-slack-token-123456"
            else:
                user_id = "U0BTCHX8HMF" if role == "mmsecretary" else "UHERMEMETA0001"
                bot_value = "secretary-fake-separate-credential-123456" if role == "mmsecretary" else "metaceo-fake-separate-credential-123456"
            if case in {"shared_model", "incumbent"} and role == "mmmeta":
                gateway, dashboard = "test-meta-gateway-distinct-123456", "test-meta-dashboard-distinct-123456"
            extra += "HERMES_SLACK_BOT_USER_ID=" + user_id + "\nHERMES_SLACK_BOT_TOKEN=" + bot_value + "\n"
        self._private_fixture(self.directory / f"{role}.secrets.env",
            "HERMES_GATEWAY_TOKEN=" + gateway + "\n"
            "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=" + dashboard + "\n" + extra)

    def _write_relay(self) -> None:
        """Satisfy the collapsed single-identity transport roster row."""
        self._private_fixture(
            self.directory / "mmrelay.secrets.env",
            "HERMES_GATEWAY_TOKEN=test-relay-gateway-token-123456\n"
            "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=test-relay-dashboard-123456\n"
            "HERMES_SLACK_BOT_USER_ID=UHERMERELAY01\n"
            "HERMES_SLACK_BOT_TOKEN=test-relay-slack-token-123456\n",
        )

    def _key_file(self, fixture: str) -> Path:
        if fixture == "modelark":
            path, data = self.directory / "modelark.key", FAKE_MODELARK
        elif fixture == "shared_model":
            path, data = self.directory / "shared-provider.key", FAKE_MODELARK
        elif fixture == "zai":
            path, data = self.directory / "zai.key", FAKE_ZAI
        else:
            raise ValueError("unknown synthetic key fixture")
        self._private_fixture(path, data + "\n")
        return path

    def _doctor(self, environ=None):
        return doctor(environ=environ or {}, home=self.home,
                      systemd_user=True, upstream_attested=True)

    def test_ambient_shell_keys_do_not_satisfy_native_roles(self):
        self._write_role("mmsecretary")
        self._write_role("mmmeta")
        outcome = self._doctor(environ={
            "BYTEPLUS_MODELARK_API_KEY": FAKE_MODELARK, "ZAI_API_KEY": FAKE_ZAI,
        })
        self.assertIn("credential:BYTEPLUS_MODELARK_API_KEY", outcome["missing"])
        self.assertIn("credential:ZAI_API_KEY", outcome["missing"])
        self.assertNotIn(FAKE_ZAI, str(outcome))
        self.assertNotIn(FAKE_MODELARK, str(outcome))

    def test_absolute_role_private_pointers_qualify_primary_presence(self):
        self._key_file("modelark")
        self._key_file("zai")
        self._write_role("mmsecretary", "file_pointer")
        self._write_role("mmmeta", "file_pointer")
        outcome = self._doctor()
        self.assertNotIn("credential:BYTEPLUS_MODELARK_API_KEY", outcome["missing"])
        self.assertNotIn("credential:ZAI_API_KEY", outcome["missing"])
        self.assertIn("grant:executive_admission", outcome["missing"])
        self.assertNotIn(FAKE_ZAI, str(outcome))
        self.assertNotIn(FAKE_MODELARK, str(outcome))

    def test_core_text_configuration_can_qualify_without_optional_grants(self):
        modelark = self._key_file('modelark')
        zai = self._key_file('zai')
        self._write_role('mmsecretary', 'core_ready')
        self._write_role('mmmeta', 'core_ready')
        self._write_relay()
        report = self._doctor()
        self.assertEqual(report['core_text_missing'], [])
        self.assertEqual(report['core_text_status'], 'CONFIG_READY_NOT_LIVE_PROVEN')
        self.assertEqual(report['status'], 'MISSING')
        self.assertIn('grant:executive_admission', report['missing'])
        self.assertFalse(report['native_egress_host_policy_verified'])
        self.assertFalse(report['provider_authenticated'])
        self.assertFalse(report['slack_roundtrip_verified'])

    def test_core_text_rejects_shared_roles_even_if_each_proxy_url_is_valid(self):
        self._write_role('mmsecretary', 'shared_roles')
        self._write_role('mmmeta', 'shared_roles')
        report = self._doctor()
        self.assertIn('isolation:shared_gateway_token', report['core_text_missing'])
        self.assertIn('isolation:shared_slack_user_id', report['core_text_missing'])
        self.assertIn('isolation:shared_egress_proxy', report['core_text_missing'])

    def test_shared_model_credential_rejected_without_leaking_key(self):
        key = self._key_file('shared_model')
        self._write_role('mmsecretary', 'shared_model')
        self._write_role('mmmeta', 'shared_model')
        outcome = self._doctor()
        self.assertIn('isolation:shared_model_credential', outcome['core_text_missing'])
        self.assertNotIn(FAKE_MODELARK, str(outcome))

    def test_incumbent_grok_peer_id_cannot_be_reused(self):
        self._write_role('mmsecretary', 'incumbent')
        self._write_role('mmmeta', 'incumbent')
        report = self._doctor()
        self.assertIn('isolation:incumbent_peer_user_id:mmsecretary', report['core_text_missing'])
        self.assertNotIn('U0BTCHX8HMF', str(report))

    def test_cli_core_only_exit_is_configuration_only_not_global_ready(self):
        import contextlib
        import io
        import json
        from unittest import mock
        from integrations.hermes_harness.cli import main
        core = {'schema': 'mastermind.hermes_harness.doctor.v1', 'status': 'MISSING', 'missing': ['grant:executive_admission', 'id:DOT_BOT_USER_IDS'], 'core_text_status': 'CONFIG_READY_NOT_LIVE_PROVEN', 'core_text_missing': [], 'core_text_missing_count': 0}
        with mock.patch('integrations.hermes_harness.cli.doctor', return_value=core):
            sink = io.StringIO()
            with contextlib.redirect_stdout(sink):
                self.assertEqual(main(['doctor', '--core-text-config-only', '--json']), 0)
            observed = json.loads(sink.getvalue())
            self.assertEqual(observed['status'], 'MISSING')
            self.assertEqual(observed['core_text_status'], 'CONFIG_READY_NOT_LIVE_PROVEN')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['doctor', '--json']), 2)
        core['core_text_status'] = 'CONFIG_MISSING'
        with mock.patch('integrations.hermes_harness.cli.doctor', return_value=core):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['doctor', '--core-text-config-only']), 2)

    def test_bad_pointer_is_not_covered_by_inline_provider_key(self):
        self._write_role("mmsecretary", "invalid_pointer")
        self._write_role("mmmeta")
        outcome = self._doctor()
        self.assertIn("credential:BYTEPLUS_MODELARK_API_KEY", outcome["missing"])

    def test_fixture_writer_accepts_only_named_examples_and_private_creation(self):
        with self.assertRaises(ValueError):
            self._key_file("arbitrary-input-is-not-a-fixture")
        with self.assertRaises(ValueError):
            self._write_role("mmsecretary", "arbitrary-input-is-not-a-fixture")
        self.assertEqual(list(self.directory.iterdir()), [])
        path = self._key_file("modelark")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        with self.assertRaises(FileExistsError):
            self._key_file("modelark")


    def test_core_configuration_refuses_invalid_canonical_roster(self):
        import copy
        import json
        from integrations.hermes_secretary.roster import CONFIG_PATH, load_roster_config
        self.test_core_text_configuration_can_qualify_without_optional_grants()
        original = json.loads(CONFIG_PATH.read_text())
        cases = (
            ("missing_peers", lambda value: value.pop("peers")),
            ("empty_peers", lambda value: value.update(peers=[])),
            ("malformed_peers", lambda value: value.update(peers=[{}])),
            ("empty_agents", lambda value: value.update(hermes_agents=[])),
            ("malformed_agents", lambda value: value.update(hermes_agents=[{}])),
        )
        for label, mutate in cases:
            with self.subTest(case=label):
                data = copy.deepcopy(original)
                mutate(data)
                path = self.home / (label + ".json")
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_roster_config(path)
                report = doctor(environ={}, home=self.home, systemd_user=True,
                                upstream_attested=True, roster_path=path)
                self.assertEqual(report["core_text_status"], "CONFIG_MISSING")
                self.assertIn("config:hermes_agents:invalid", report["core_text_missing"])
                self.assertFalse(report["provider_authenticated"])
                self.assertFalse(report["slack_roundtrip_verified"])
                self.assertNotIn("U0BTCHX8HMF", str(report))

    def test_unreadable_or_invalid_json_roster_cannot_qualify_core_cli(self):
        import contextlib
        import io
        from unittest import mock
        from integrations.hermes_harness.cli import main
        self.test_core_text_configuration_can_qualify_without_optional_grants()
        missing = self.home / "not-present.json"
        invalid = self.home / "malformed.json"
        invalid.write_text('{"SYNTHETIC_PRIVATE_SENTINEL":', encoding="utf-8")
        for path in (missing, invalid):
            with self.subTest(case=path.name):
                report = doctor(environ={}, home=self.home, systemd_user=True,
                                upstream_attested=True, roster_path=path)
                self.assertEqual(report["core_text_status"], "CONFIG_MISSING")
                self.assertIn("config:hermes_agents:invalid", report["core_text_missing"])
                self.assertNotIn("SYNTHETIC_PRIVATE_SENTINEL", str(report))
                with mock.patch("integrations.hermes_harness.cli.doctor", return_value=report):
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(main(["doctor", "--core-text-config-only", "--json"]), 2)

    def test_role_and_incumbent_checks_share_one_canonical_roster_read(self):
        from unittest import mock
        from integrations.hermes_secretary.roster import load_roster_config
        self.test_core_text_configuration_can_qualify_without_optional_grants()
        with mock.patch("integrations.hermes_harness.doctor.load_roster_config",
                        wraps=load_roster_config) as read:
            result = self._doctor()
        self.assertEqual(read.call_count, 1)
        self.assertEqual(result["core_text_status"], "CONFIG_READY_NOT_LIVE_PROVEN")
        self.assertEqual(result["core_text_missing"], [])



if __name__ == "__main__":
    unittest.main()
