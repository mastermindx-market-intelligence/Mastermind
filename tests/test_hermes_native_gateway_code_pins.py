"""Gateway code-pin policy: file-content hashes are the mechanism pin; the
commit allowlist is a qualification tripwire, not the refusal.

A gateway commit advance whose pinned mechanism files are byte-identical must
not refuse recovery/roster reads; a pinned file hash that differs must refuse
regardless of which commit the gateway answers. No network, gateway, database
or credentials; fixture files stand in for the pinned sources.
"""
import asyncio
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

BRIDGE = Path(__file__).parents[1] / "app/mastermind_os/src-tauri/src/hermes_native/bridge.py"
# Well-formed 40-hex sha that is deliberately not a pinned generation.
ADVANCE = "9" * 40


def load():
    spec = importlib.util.spec_from_file_location("native_gateway_pins", BRIDGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GatewayCodePinTests(unittest.TestCase):
    def setUp(self):
        self.b = load()
        self.directory = tempfile.TemporaryDirectory(prefix="native-gateway-pins-")
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name).resolve()
        self.runtime = object.__new__(self.b.NativeRuntime)
        self.runtime.home = self.home
        # Fixture mechanism files whose digests are pinned to this test only
        # (same seam the OMH qualification suite uses for OMH_READONLY_PINS).
        def repin(table, base):
            pinned = {}
            for name in table:
                path = base / name
                path.parent.mkdir(parents=True, exist_ok=True)
                raw = f"# fixture mechanism source {name}\n".encode()
                path.write_bytes(raw)
                pinned[name] = hashlib.sha256(raw).hexdigest()
            return pinned
        agent = self.home / "hermes-agent"
        self.b.RECOVERY_SOURCE_PINS = repin(self.b.RECOVERY_SOURCE_PINS, agent)
        self.b.ROSTER_SOURCE_PINS = repin(self.b.ROSTER_SOURCE_PINS, agent)
        self.b.CAPACITY_SOURCE_PINS = repin(self.b.CAPACITY_SOURCE_PINS, self.home)
        self.runtime.observed_version = self.b.GATEWAY_CODE_VERSION

    def test_pinned_generation_qualifies_without_a_version_answer(self):
        self.runtime.observed_version = None
        for code in sorted(self.b.GATEWAY_CODE_PINS):
            with self.subTest(code=code[:8]):
                self.runtime.observed_code = code
                self.assertTrue(self.runtime.gateway_code_qualified())
                self.assertIsNone(self.runtime.require_recovery_source())
                self.assertIsNone(self.runtime.require_roster_source())

    def test_commit_advance_with_identical_file_hashes_does_not_refuse(self):
        self.runtime.observed_code = ADVANCE
        self.assertTrue(self.runtime.gateway_code_qualified())
        self.assertIsNone(self.runtime.require_recovery_source())
        self.assertIsNone(self.runtime.require_roster_source())

    def test_file_hash_drift_refuses_regardless_of_commit(self):
        for code in [*sorted(self.b.GATEWAY_CODE_PINS), ADVANCE]:
            for name, refusal, method in [
                    ("hermes_state_keys.py", "NATIVE_RECOVERY_SOURCE_CHANGED", self.runtime.require_recovery_source),
                    ("tools/bot_mode_probe.py", "NATIVE_ROSTER_SOURCE_CHANGED", self.runtime.require_roster_source)]:
                with self.subTest(code=code[:8], name=name):
                    self.runtime.observed_code = code
                    path = self.home / ("hermes-agent/" + name)
                    original = path.read_bytes()
                    path.write_bytes(original + b"# drifted\n")
                    with self.assertRaisesRegex(self.b.BridgeRefusal, refusal):
                        method()
                    path.write_bytes(original)
                    self.assertIsNone(method())

    def test_advance_outside_the_qualified_version_line_is_not_qualified(self):
        self.runtime.observed_code = ADVANCE
        for version in ("0.24.0", None, 23):
            with self.subTest(version=version):
                self.runtime.observed_version = version
                self.assertFalse(self.runtime.gateway_code_qualified())
                with self.assertRaisesRegex(self.b.BridgeRefusal, "NATIVE_GATEWAY_CODE_UNQUALIFIED"):
                    self.runtime.require_recovery_source()
                with self.assertRaisesRegex(self.b.BridgeRefusal, "NATIVE_GATEWAY_CODE_UNQUALIFIED"):
                    self.runtime.require_roster_source()
                self.assertFalse(self.runtime.readonly_capacity_qualified())
                self.assertFalse(self.runtime.readonly_omh_qualified())

    def test_file_drift_outranks_an_unqualified_code_identity(self):
        # The imported bytes refuse first: a drifted mechanism file reports
        # SOURCE_CHANGED even when the gateway's generation is not qualified.
        self.runtime.observed_code = ADVANCE
        self.runtime.observed_version = "0.24.0"
        path = self.home / "hermes-agent/hermes_state.py"
        path.write_bytes(path.read_bytes() + b"# drifted\n")
        with self.assertRaisesRegex(self.b.BridgeRefusal, "NATIVE_RECOVERY_SOURCE_CHANGED"):
            self.runtime.require_recovery_source()

    def test_missing_or_malformed_code_identity_is_not_qualified(self):
        for code in (None, "", "short", "z" * 40, "g" * 41, 12345678901234567890):
            with self.subTest(code=code):
                self.runtime.observed_code = code
                self.assertFalse(self.runtime.gateway_code_qualified())
                with self.assertRaisesRegex(self.b.BridgeRefusal, "NATIVE_GATEWAY_CODE_UNQUALIFIED"):
                    self.runtime.require_recovery_source()

    def test_capacity_file_drift_removes_readonly_eligibility_even_for_a_pin(self):
        # With a satisfied code gate and a matching config, the fixture control
        # qualifies; drifting the pinned capacity bridge file must remove it.
        self.runtime.observed_code = sorted(self.b.GATEWAY_CODE_PINS)[0]
        self.runtime.observed_version = None
        (self.home / "config.yaml").write_text("# fixture config (parsed by the fake below)\n")
        server = {"enabled": True, "command": "/opt/homebrew/bin/python3",
                  "args": [str(self.home / "bridges/fabric_capacity_mcp.py")]}
        hermes_yaml = SimpleNamespace(safe_load=lambda _raw: {"mcp_servers": {"mastermind-fabric-capacity": server}})
        with patch.dict("sys.modules", {"hermes_yaml": hermes_yaml}):
            self.assertTrue(self.runtime.readonly_capacity_qualified())
            path = self.home / "bridges/fabric_capacity_mcp.py"
            original = path.read_bytes()
            path.write_bytes(original + b"# drifted\n")
            self.assertFalse(self.runtime.readonly_capacity_qualified())
            path.write_bytes(original)
            self.assertTrue(self.runtime.readonly_capacity_qualified())
            # An unqualified code identity degrades the same path to False.
            self.runtime.observed_code = ADVANCE
            self.runtime.observed_version = None
            self.assertFalse(self.runtime.readonly_capacity_qualified())

    def test_identify_records_both_code_sha_and_version_for_the_tripwire(self):
        def query(home, request, timeout):
            self.assertEqual(request, b'{"protocol":1,"id":1,"verb":"identify"}\n')
            return (b'{"ok": true, "result": {"code_sha": "' + ADVANCE.encode()
                    + b'", "code_version": "0.23.0"}}')
        gateway_client = SimpleNamespace(private_control_query=query)
        with patch.dict("sys.modules", {"hermes_cli": SimpleNamespace(__path__=[]),
                                        "hermes_cli.gateway_client": gateway_client}):
            answer = asyncio.run(self.runtime.identify())
        self.assertTrue(answer["ok"])
        self.assertEqual(self.runtime.observed_code, ADVANCE)
        self.assertEqual(self.runtime.observed_version, "0.23.0")
        self.assertTrue(self.runtime.gateway_code_qualified())

    def test_each_hardcoded_literal_lives_exactly_once_and_every_gate_reads_it(self):
        source = BRIDGE.read_text(encoding="utf-8")
        for literal in sorted(self.b.GATEWAY_CODE_PINS):
            self.assertEqual(source.count(literal), 1)
        blocks = {}
        for block in source.split("\n    def ")[1:]:
            name = block.split("(")[0]
            blocks[name] = block
        for gate in ("require_recovery_source", "require_roster_source",
                     "readonly_capacity_qualified", "readonly_omh_qualified"):
            with self.subTest(gate=gate):
                self.assertIn("gateway_code_qualified()", blocks[gate])
        # The helper is the single reader of the pin constant.
        self.assertEqual(source.count("code in GATEWAY_CODE_PINS"), 1)
        self.assertIn("GATEWAY_CODE_VERSION", blocks["gateway_code_qualified"])


if __name__ == "__main__":
    unittest.main()
