#!/usr/bin/env python3
"""Behavior tests for private_service.py.

Contracts:
  * Per-account label and runtime roots under ~/.local/share/studio-direct-mcp/private/<account>
  * launchd argv is absolute node + installed private-tunnel-gateway.mjs + config.json
  * First stage refuses foreign unmanifested dest files and parent-dir symlinks
  * Idempotent restage only when incoming hashes, port, configHash, and plistHash match
  * Explicit stopped-service upgrade accepts only exact known v1 installs and preserves runtime state
  * Account labels are already-lowercase, <=64, no silent aliasing
  * Port 45017 is reserved; source/node/backend must be absolute
  * Config omits publicUrl, keeps 5h idle/64 sessions, and enables bounded typed Git
All mutations stay inside temp fixtures; subprocess is mocked.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import plistlib
import stat
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import private_service as svc  # noqa: E402

PAPER_DESKTOP_DIR = HERE.parent / "paper_desktop"
sys.path.insert(0, str(PAPER_DESKTOP_DIR))
import runtime_stage as paper_runtime_stage  # noqa: E402


PAPER_BRIDGE_FIXTURE = b"fixture-paper-bridge\n"
PAPER_BRIDGE_FIXTURE_SHA = hashlib.sha256(PAPER_BRIDGE_FIXTURE).hexdigest()


def _seed_paper_runtime(home: Path) -> str:
    runtime = home / svc.PAPER_RUNTIME_REL
    source = runtime / "source"
    python_dir = runtime / "venv" / "bin"
    source.mkdir(parents=True, mode=0o700, exist_ok=True)
    runtime.chmod(0o700)
    source.chmod(0o700)
    python_dir.mkdir(parents=True, exist_ok=True)
    bridge = source / "bridge.py"
    bridge.write_bytes(PAPER_BRIDGE_FIXTURE)
    bridge.chmod(0o600)
    python = python_dir / "python"
    python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python.chmod(0o700)
    receipt = {
        "schema": svc.PAPER_RUNTIME_SCHEMA,
        "generation": svc.PAPER_RUNTIME_REL.name,
        "source_sha256": {"bridge.py": PAPER_BRIDGE_FIXTURE_SHA},
        "bridge_sha256": PAPER_BRIDGE_FIXTURE_SHA,
        "python_source": "/usr/bin/python3",
        "python_version": "fixture",
        "network_install_performed": False,
        "production_acceptance": False,
    }
    receipt_path = runtime / "RUNTIME.json"
    receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    receipt_path.chmod(0o600)
    return PAPER_BRIDGE_FIXTURE_SHA


def _label_for(account: str) -> str:
    return f"com.mastermind.studio-direct-private.{account}"


def _print_running(
    plist: str = "/tmp/x.plist",
    label: str = "com.mastermind.studio-direct-private.test-account",
) -> str:
    return (
        f"gui/{os.getuid()}/{label} = {{\n"
        "\tactive count = 1\n"
        f"\tpath = {plist}\n"
        "\tstate = running\n"
        "\tprogram = /opt/homebrew/bin/node\n"
        "\tpid = 4321\n"
        "\tlast exit code = (never exited)\n"
        "}\n"
    )


def _print_crashed(
    plist: str = "/tmp/x.plist",
    label: str = "com.mastermind.studio-direct-private.test-account",
) -> str:
    return (
        f"gui/{os.getuid()}/{label} = {{\n"
        "\tactive count = 0\n"
        f"\tpath = {plist}\n"
        "\tstate = waiting\n"
        "\tlast exit code = 1\n"
        "}\n"
    )


class FakeResult:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class CmdRecorder:
    def __init__(self, handler=None, default=None):
        self.handler = handler
        self.default = default if default is not None else FakeResult(1, "", "not loaded")
        self.calls: list[list[str]] = []

    def __call__(self, cmd, *, check: bool = True, timeout: float = 30.0):
        self.calls.append(list(cmd))
        if self.handler is not None:
            result = self.handler(list(cmd))
            if result is not None:
                if isinstance(result, BaseException):
                    if check:
                        raise result
                    return FakeResult(1, "", str(result))
                return result
        if isinstance(self.default, BaseException):
            if check:
                raise self.default
            return FakeResult(1, "", str(self.default))
        return self.default


def _make_source(tmp: Path) -> Path:
    src = tmp / "src"
    src.mkdir(parents=True, exist_ok=True)
    for name in svc.STAGE_FILES:
        (src / name).write_text(f"// {name} contents\n", encoding="utf-8")
    return src


def _make_node(tmp: Path) -> Path:
    n = tmp / "node"
    n.write_text("#!/bin/sh\necho node\n", encoding="utf-8")
    n.chmod(0o755)
    return n


def _make_backend(tmp: Path) -> Path:
    b = tmp / "backend.mjs"
    b.write_text("// desktop-commander index\n", encoding="utf-8")
    return b


@contextmanager
def IsolatedHome(account: str = "test-account"):
    """Provide an isolated temp HOME directory for testing.

    Returns (home_path, label, roots) so tests can reference them.
    """
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        home = tmp / "home"
        home.mkdir(parents=True, exist_ok=True)
        (home / "Library" / "LaunchAgents").mkdir(parents=True, exist_ok=True)

        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            roots = svc._build_runtime_roots(account)
            label = _label_for(account)
            yield home, label, roots


def _capture_stdout(call):
    buf = io.StringIO()
    with mock.patch("sys.stdout", buf):
        rc = call()
    return rc, buf.getvalue()


def _stage_args(source, node, backend, account: str = "test-account", port: int = 45018):
    return mock.Mock(
        account=account,
        port=port,
        source=str(source),
        node=str(node),
        backend=str(backend),
        fabric_only=False,
        modern_fabric_protocol=None,
        enable_repository_workspaces=False,
        os_commission_config_sha256=None,
    )


def _do_stage(tmp: Path, home: Path, account: str = "test-account", port: int = 45018, recorder=None):
    src = _make_source(tmp)
    node = _make_node(tmp)
    backend = _make_backend(tmp)
    rec = recorder or CmdRecorder()
    paper_sha = _seed_paper_runtime(home)
    with mock.patch.dict(os.environ, {"HOME": str(home)}):
        with mock.patch.object(svc, "PAPER_BRIDGE_SHA256", paper_sha), \
             mock.patch.object(svc, "_run", rec):
            _capture_stdout(
                lambda: svc.cmd_stage(_stage_args(src, node, backend, account, port))
            )
    return src, node, backend, rec


def _seed_node_modules(roots: dict):
    roots["base"].mkdir(parents=True, exist_ok=True)
    deps = roots["base"] / "node_modules"
    deps.mkdir()
    package = deps / "fixture-package"
    package.mkdir()
    (package / "index.js").write_text("export const fixture = 1;\n", encoding="utf-8")


def _seal_runtime(account: str = "test-account", recorder=None):
    rec = recorder or CmdRecorder()
    with mock.patch.object(svc, "_run", rec):
        return _capture_stdout(
            lambda: svc.cmd_seal_runtime(mock.Mock(account=account))
        )


def _convert_to_legacy_install(roots: dict, *, typed_git: bool = False) -> dict:
    """Recreate one exact historical layout; never include newly staged modules."""
    config = json.loads(roots["config"].read_text(encoding="utf-8"))
    config.pop("paperDesign", None)
    config.pop("fleetStatus", None)
    config.pop("repositoryWorkspaces", None)
    if not typed_git:
        config.pop("gitPublish", None)
    roots["config"].write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
    manifest = json.loads(roots["manifest"].read_text(encoding="utf-8"))
    manifest["version"] = 1
    for key in ("nodeHash", "backendHash", "dependencyTreeHash"):
        manifest.pop(key, None)
    removed = ("fleet-status.mjs", "paper-design.mjs", "output-budget.mjs") if typed_git else (
        "fleet-status.mjs", "paper-design.mjs", "output-budget.mjs", "git-publish.mjs"
    )
    removed = (*removed, "workspace-access.mjs", "commission-prepare.mjs", "commission-service.mjs", "modern-fabric-http.mjs")
    for name in removed:
        (roots["base"] / name).unlink()
        manifest["files"].pop(name)
    manifest["configHash"] = svc._sha256_file(roots["config"])
    roots["manifest"].write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def _make_upgrade_source(tmp: Path) -> Path:
    source = tmp / "upgrade-src"
    source.mkdir(parents=True, exist_ok=True)
    for name in svc.STAGE_FILES:
        (source / name).write_text(f"// upgraded {name} contents\n", encoding="utf-8")
    return source


# -------------------------------------------------------------------
# Identity & structure
# -------------------------------------------------------------------

class TestIdentity(unittest.TestCase):
    def test_stage_files_include_engine_and_private_adapter(self):
        self.assertEqual(
            set(svc.STAGE_FILES),
            {
                "gateway.mjs",
                "modern-fabric-http.mjs",
                "output-budget.mjs",
                "git-publish.mjs",
                "workspace-access.mjs",
                "commission-prepare.mjs",
                "commission-service.mjs",
                "paper-design.mjs",
                "fleet-status.mjs",
                "private-tunnel-auth.mjs",
                "private-tunnel-gateway.mjs",
                "package.json",
                "package-lock.json",
            },
        )
        self.assertEqual(svc.PRIVATE_GATEWAY_NAME, "private-tunnel-gateway.mjs")

    def test_manifest_keys_include_runtime_identity(self):
        self.assertIn("account", svc.MANIFEST_KEYS_V2)
        self.assertIn("label", svc.MANIFEST_KEYS_V2)
        self.assertIn("port", svc.MANIFEST_KEYS_V2)
        self.assertIn("plistHash", svc.MANIFEST_KEYS_V2)
        self.assertIn("configHash", svc.MANIFEST_KEYS_V2)
        self.assertIn("nodeHash", svc.MANIFEST_KEYS_V2)
        self.assertIn("backendHash", svc.MANIFEST_KEYS_V2)
        self.assertIn("dependencyTreeHash", svc.MANIFEST_KEYS_V2)

    def test_v1_manifest_accepts_only_current_or_exact_legacy_filesets(self):
        digest = "0" * 64
        base = {
            "version": 1,
            "account": "test-account",
            "label": _label_for("test-account"),
            "configHash": digest,
            "plistHash": digest,
            "source": "/tmp/src",
            "node": "/tmp/node",
            "backend": "/tmp/backend",
            "host": "127.0.0.1",
            "port": 45018,
        }
        current = {name: digest for name in svc.STAGE_FILES}
        legacy = {name: digest for name in svc.LEGACY_STAGE_FILES_V1}
        self.assertTrue(svc._valid_manifest({**base, "files": current}, "test-account", _label_for("test-account")))
        self.assertTrue(svc._valid_manifest({**base, "files": legacy}, "test-account", _label_for("test-account")))
        previous_current = {name: digest for name in svc.LEGACY_STAGE_FILES_V4}
        self.assertTrue(svc._valid_manifest({**base, "files": previous_current}, "test-account", _label_for("test-account")))
        immediate_legacy = {name: digest for name in svc.LEGACY_STAGE_FILES_V3}
        self.assertTrue(svc._valid_manifest({**base, "files": immediate_legacy}, "test-account", _label_for("test-account")))
        typed_legacy = {name: digest for name in svc.LEGACY_STAGE_FILES_V2}
        self.assertTrue(svc._valid_manifest({**base, "files": typed_legacy}, "test-account", _label_for("test-account")))
        self.assertNotIn("fleet-status.mjs", svc.LEGACY_STAGE_FILES_V4)
        self.assertNotIn("output-budget.mjs", svc.LEGACY_STAGE_FILES_V1)
        self.assertNotIn("git-publish.mjs", svc.LEGACY_STAGE_FILES_V1)
        partial = dict(legacy)
        partial.pop(next(iter(partial)))
        self.assertFalse(svc._valid_manifest({**base, "files": partial}, "test-account", _label_for("test-account")))
        extra = dict(current)
        extra["surprise.mjs"] = digest
        self.assertFalse(svc._valid_manifest({**base, "files": extra}, "test-account", _label_for("test-account")))
        self.assertFalse(svc._valid_manifest({**base, "version": 2, "files": current}, "test-account", _label_for("test-account")))

    def test_v2_verified_chatgpt1_historical_fleet_tailnet_fileset_only(self):
        """The already-applied 0.1.10 12-file canary is a V2-only predecessor."""
        digest = "a" * 64
        names = {
            "gateway.mjs", "output-budget.mjs", "git-publish.mjs",
            "workspace-access.mjs", "paper-design.mjs", "fleet-status.mjs",
            "fleet-routing.mjs", "private-tunnel-auth.mjs",
            "private-tunnel-gateway.mjs", "tailnet-gateway.mjs",
            "package.json", "package-lock.json",
        }
        self.assertEqual(len(names), 12)
        self.assertNotIn(frozenset(names), svc.KNOWN_MANIFEST_FILESETS)
        account = "chatgpt1"
        label = _label_for(account)
        manifest = {
            "version": 2, "account": account, "label": label,
            "files": {name: digest for name in names},
            "configHash": digest, "plistHash": digest,
            "source": "/owned/source", "node": "/owned/node",
            "backend": "/owned/backend", "host": "127.0.0.1",
            "port": 45018, "nodeHash": digest,
            "backendHash": digest, "dependencyTreeHash": digest,
        }
        self.assertTrue(svc._valid_manifest(manifest, account, label))
        for rejected in (
            {**{key: value for key, value in manifest.items()
                 if key not in ("nodeHash", "backendHash", "dependencyTreeHash")},
             "version": 1},
            {**manifest, "files": dict((name, digest) for name in names - {"fleet-routing.mjs"})},
            {**manifest, "files": {**manifest["files"], "unrecognized.mjs": digest}},
            {**manifest, "files": {**manifest["files"], "tailnet-gateway.mjs": "bad"}},
            {**manifest, "account": "chatgpt2"},
            {**manifest, "dependencyTreeHash": "bad"},
        ):
            self.assertFalse(svc._valid_manifest(rejected, account, label))

    def test_v1_provisioned_manifest_accepts_only_exact_inert_legacy_shape(self):
        digest = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "home"
            home.mkdir()
            base = {
                "version": 1,
                "account": "chatgpt4",
                "label": _label_for("chatgpt4"),
                "configHash": digest,
                "plistHash": digest,
                "source": "/tmp/src",
                "node": "/tmp/node",
                "backend": "/tmp/backend",
                "host": "127.0.0.1",
                "port": 45024,
                "files": {name: digest for name in svc.LEGACY_STAGE_FILES_V1},
                "provisioned_from": str(
                    home / ".local" / "share" / "studio-direct-mcp" / "private" / "chatgpt3"
                ),
                "installation_state": svc.LEGACY_PROVISIONED_STATE,
            }
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                self.assertTrue(
                    svc._valid_manifest(base, "chatgpt4", _label_for("chatgpt4"))
                )
                wrong_state = {**base, "installation_state": "READY"}
                self.assertFalse(
                    svc._valid_manifest(wrong_state, "chatgpt4", _label_for("chatgpt4"))
                )
                wrong_source = {**base, "provisioned_from": "/tmp/chatgpt3"}
                self.assertFalse(
                    svc._valid_manifest(wrong_source, "chatgpt4", _label_for("chatgpt4"))
                )
                same_account = {
                    **base,
                    "provisioned_from": str(
                        home / ".local" / "share" / "studio-direct-mcp" / "private" / "chatgpt4"
                    ),
                }
                self.assertFalse(
                    svc._valid_manifest(same_account, "chatgpt4", _label_for("chatgpt4"))
                )

    def test_dir_mode_is_0700(self):
        self.assertEqual(svc.DIR_MODE, 0o700)

    def test_file_mode_is_0600(self):
        self.assertEqual(svc.FILE_MODE, 0o600)

    def test_reserved_funnel_port(self):
        self.assertEqual(svc.RESERVED_FUNNEL_PORT, 45017)

    def test_private_runtime_timeouts_match_live_business_seats(self):
        self.assertEqual(svc.IDLE_TIMEOUT_MS, 1_800_000)
        self.assertEqual(svc.REQUEST_TIMEOUT_MS, 300_000)

    def test_paper_runtime_pin_matches_reviewed_v12_generation(self):
        self.assertEqual(svc.PAPER_RUNTIME_REL.name, "v12")
        self.assertEqual(
            svc.PAPER_BRIDGE_SHA256,
            paper_runtime_stage.REVIEWED_GENERATIONS["v12"]["bridge.py"],
        )

    def test_c2_admission_contains_only_original_and_exact_v12_successor(self):
        self.assertEqual(svc.C2_PAPER_MANIFEST_CANONICAL_SHA256, frozenset((
            "821e37a4e10011f3335984416edaac92899c6bc27526c0f017b3d75130950d84",
            "d477cd952b86d76c07a2554a94a1ce5dc8c5e42bda544a5603caf0f54e17c9b7",
        )))


# -------------------------------------------------------------------
# Account label validation
# -------------------------------------------------------------------

class TestAccountLabelValidation(unittest.TestCase):
    def test_valid_labels(self):
        for label in ("test", "my-account", "test_123", "a1-b2", "a.b"):
            svc._validate_account_label(label)

    def test_accepts_64_char_lowercase(self):
        svc._validate_account_label("a" * 64)

    def test_rejects_empty(self):
        with self.assertRaises(SystemExit) as ctx:
            svc._validate_account_label("")
        self.assertIn("empty", str(ctx.exception))

    def test_rejects_non_ascii(self):
        with self.assertRaises(SystemExit) as ctx:
            svc._validate_account_label("tëst")
        self.assertIn("ASCII", str(ctx.exception))

    def test_rejects_uppercase_without_aliasing(self):
        with self.assertRaises(SystemExit) as ctx:
            svc._validate_account_label("MyAccount")
        self.assertIn("lowercase", str(ctx.exception))

    def test_rejects_over_64(self):
        with self.assertRaises(SystemExit) as ctx:
            svc._validate_account_label("a" * 65)
        self.assertIn("64", str(ctx.exception))

    def test_rejects_reserved_words(self):
        for word in ("public", "shared", "default", "state", "config", "logs", "manifest"):
            with self.assertRaises(SystemExit) as ctx:
                svc._validate_account_label(word)
            self.assertIn("reserved", str(ctx.exception))

    def test_rejects_non_alphanumeric_dashes(self):
        with self.assertRaises(SystemExit):
            svc._validate_account_label("my account")

    def test_stage_does_not_lowercase_alias(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                with mock.patch.object(svc, "_run", CmdRecorder()):
                    with self.assertRaises(SystemExit) as ctx:
                        svc.cmd_stage(
                            _stage_args(
                                _make_source(tmp),
                                _make_node(tmp),
                                _make_backend(tmp),
                                "MyAccount",
                                45018,
                            )
                        )
                    self.assertIn("lowercase", str(ctx.exception))
                self.assertFalse(
                    (home / ".local" / "share" / "studio-direct-mcp" / "private" / "myaccount").exists()
                )
                self.assertFalse(
                    (home / ".local" / "share" / "studio-direct-mcp" / "private" / "MyAccount").exists()
                )


# -------------------------------------------------------------------
# Runtime roots
# -------------------------------------------------------------------

class TestRuntimeRoots(unittest.TestCase):
    def test_per_account_isolation(self):
        with IsolatedHome("account-a") as (home_a, _, roots_a), \
             IsolatedHome("account-b") as (home_b, _, roots_b):
            self.assertNotEqual(str(roots_a["base"]), str(roots_b["base"]))
            self.assertIn("account-a", str(roots_a["base"]))
            self.assertIn("account-b", str(roots_b["base"]))
            self.assertNotEqual(str(roots_a["plist"]), str(roots_b["plist"]))

    def test_gateway_cli_is_private_adapter(self):
        with IsolatedHome("test-account") as (_, _, roots):
            self.assertEqual(roots["gateway"].name, "private-tunnel-gateway.mjs")
            self.assertEqual(roots["gateway"], roots["base"] / "private-tunnel-gateway.mjs")

    def test_mixed_case_account_is_not_silently_folded(self):
        with IsolatedHome("MyAccount") as (_, label, roots):
            self.assertIn("MyAccount", str(roots["base"]))
            self.assertNotIn("myaccount", str(roots["base"]))
            self.assertEqual(label, _label_for("MyAccount"))


# -------------------------------------------------------------------
# Paper runtime admission
# -------------------------------------------------------------------

class TestPaperRuntimeAdmission(unittest.TestCase):
    def test_exact_private_runtime_receipt_and_bridge_are_accepted(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "home"
            home.mkdir()
            _seed_paper_runtime(home)
            receipt = svc._verify_paper_runtime(
                home, expected_sha=PAPER_BRIDGE_FIXTURE_SHA
            )
            self.assertEqual(receipt["generation"], svc.PAPER_RUNTIME_REL.name)

    def test_bridge_hash_drift_refuses(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "home"
            home.mkdir()
            _seed_paper_runtime(home)
            bridge = home / svc.PAPER_RUNTIME_REL / "source" / "bridge.py"
            bridge.write_text("drift", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "bridge hash mismatch"):
                svc._verify_paper_runtime(
                    home, expected_sha=PAPER_BRIDGE_FIXTURE_SHA
                )

    def test_receipt_generation_mismatch_refuses(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "home"
            home.mkdir()
            _seed_paper_runtime(home)
            receipt_path = home / svc.PAPER_RUNTIME_REL / "RUNTIME.json"
            receipt = json.loads(receipt_path.read_text())
            receipt["generation"] = "wrong-generation"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            receipt_path.chmod(0o600)
            with self.assertRaisesRegex(SystemExit, "required generation"):
                svc._verify_paper_runtime(
                    home, expected_sha=PAPER_BRIDGE_FIXTURE_SHA
                )

    def test_stage_refuses_missing_runtime_before_writes(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            args = _stage_args(
                _make_source(tmp), _make_node(tmp), _make_backend(tmp)
            )
            with mock.patch.dict(os.environ, {"HOME": str(home)}), \
                 mock.patch.object(svc, "_run", CmdRecorder()):
                with self.assertRaisesRegex(SystemExit, "paper runtime"):
                    svc.cmd_stage(args)
                roots = svc._build_runtime_roots("test-account")
                self.assertFalse(roots["base"].exists())
                self.assertFalse(roots["plist"].exists())


# -------------------------------------------------------------------
# Config and plist builders
# -------------------------------------------------------------------

class TestBuildConfig(unittest.TestCase):
    def test_config_omits_public_url_and_sets_idle(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "home"
            home.mkdir()
            node = _make_node(Path(raw))
            backend = _make_backend(Path(raw))
            state_dir = home / "state"
            config = svc._build_config(
                "test-account", "127.0.0.1", 45018,
                node, backend, state_dir, home,
            )
            self.assertEqual(config["accountLabel"], "test-account")
            self.assertEqual(config["host"], "127.0.0.1")
            self.assertEqual(config["port"], 45018)
            self.assertNotIn("publicUrl", config)
            self.assertEqual(config["testMode"], False)
            self.assertEqual(config["command"], str(node))
            self.assertEqual(config["args"], [str(backend), "--no-onboarding"])
            self.assertEqual(config["cwd"], str(home))
            self.assertEqual(config["childEnv"]["NODE_OPTIONS"], "")
            self.assertEqual(config["stateDir"], str(state_dir))
            self.assertEqual(config["maxSessions"], 256)
            self.assertEqual(config["requestTimeoutMs"], 300_000)
            self.assertEqual(config["idleTimeoutMs"], 1_800_000)
            self.assertEqual(
                config["gitPublish"],
                {
                    "enabled": True,
                    "workspaceCli": str(home / ".local" / "bin" / "mmx-workspace"),
                    "gitBinary": "/usr/bin/git",
                    "sourceRepository": str(home / "Documents" / "GitHub" / "Mastermind"),
                    "allowedRemoteUrls": [
                        "https://github.com/mastermindx-market-intelligence/Mastermind.git"
                    ],
                    "commandTimeoutMs": 15_000,
                    "pushTimeoutMs": 60_000,
                },
            )
            self.assertNotIn("branch", config["gitPublish"])
            self.assertNotIn("remote", config["gitPublish"])
            self.assertNotIn("credential", config["gitPublish"])
            paper_runtime = home / svc.PAPER_RUNTIME_REL
            self.assertEqual(
                config["paperDesign"],
                {
                    "enabled": True,
                    "pythonPath": str(paper_runtime / "venv" / "bin" / "python"),
                    "bridgePath": str(paper_runtime / "source" / "bridge.py"),
                    "bridgeSha256": svc.PAPER_BRIDGE_SHA256,
                    "appPath": str(home / "Applications" / "Paper.app"),
                    "commandTimeoutMs": 70_000,
                },
            )
            self.assertNotIn("fileId", config["paperDesign"])
            self.assertNotIn("appPathOverride", config["paperDesign"])
            self.assertNotIn("account", config["paperDesign"])
            self.assertNotIn("token", config["paperDesign"])
            self.assertNotIn("fleetStatus", config)

    def test_config_enrolls_hash_pinned_existing_fleet_status_owner(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "home"
            home.mkdir()
            launcher = home / ".local" / "bin" / "studio-direct"
            launcher.parent.mkdir(parents=True)
            launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            launcher.chmod(0o700)
            node = _make_node(Path(raw))
            backend = _make_backend(Path(raw))
            config = svc._build_config(
                "test-account", "127.0.0.1", 45018,
                node, backend, home / "state", home,
            )
            self.assertEqual(
                config["fleetStatus"],
                {
                    "enabled": True,
                    "launcherPath": str(launcher),
                    "launcherSha256": svc._sha256_file(launcher),
                    "timeoutMs": 15_000,
                },
            )


class TestBuildPlist(unittest.TestCase):
    def test_plist_invokes_private_adapter(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "home"
            home.mkdir()
            node = _make_node(Path(raw))
            gateway = home / "private-tunnel-gateway.mjs"
            config = home / "config.json"
            label = _label_for("test-account")
            plist = svc._build_plist(node, gateway, config, home, label)
            self.assertEqual(plist["Label"], label)
            self.assertEqual(plist["ProcessType"], "Interactive")
            self.assertEqual(plist["Umask"], 0o077)
            self.assertEqual(plist["ExitTimeOut"], 25)
            self.assertEqual(plist["RunAtLoad"], True)
            self.assertEqual(plist["KeepAlive"], {"SuccessfulExit": False})
            self.assertEqual(plist["ThrottleInterval"], 10)
            self.assertEqual(plist["EnvironmentVariables"]["NODE_OPTIONS"], "")
            self.assertEqual(plist["EnvironmentVariables"]["UV_THREADPOOL_SIZE"], "16")
            self.assertEqual(plist["EnvironmentVariables"]["HOME"], str(home))
            self.assertEqual(plist["EnvironmentVariables"]["PATH"],
                             "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin")
            self.assertEqual(
                plist["ProgramArguments"],
                [str(node), str(gateway), str(config)],
            )
            self.assertTrue(plist["ProgramArguments"][1].endswith("private-tunnel-gateway.mjs"))
            self.assertFalse(plist["ProgramArguments"][1].endswith("/gateway.mjs"))
            for arg in plist["ProgramArguments"]:
                self.assertNotIn("/bin/sh", arg)


# -------------------------------------------------------------------
# Stage
# -------------------------------------------------------------------

class TestStage(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(svc, "PAPER_BRIDGE_SHA256", PAPER_BRIDGE_FIXTURE_SHA)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_happy_path_writes_private_cli_and_hashes(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir(parents=True, exist_ok=True)
            (home / "Library" / "LaunchAgents").mkdir(parents=True, exist_ok=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _do_stage(tmp, home)
                roots = svc._build_runtime_roots("test-account")
                base = roots["base"]

                for name in svc.STAGE_FILES:
                    path = base / name
                    self.assertTrue(path.is_file(), name)
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                    self.assertFalse(path.is_symlink())

                for directory in (base, base / "state", base / "logs"):
                    self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)

                self.assertTrue(roots["config"].is_file())
                self.assertTrue(roots["manifest"].is_file())
                self.assertEqual(roots["gateway"].name, "private-tunnel-gateway.mjs")
                self.assertTrue(roots["gateway"].is_file())

                plist_data = plistlib.loads(roots["plist"].read_bytes())
                self.assertEqual(plist_data["Label"], _label_for("test-account"))
                argv = plist_data["ProgramArguments"]
                self.assertEqual(argv[1], str(roots["gateway"]))
                self.assertTrue(argv[1].endswith("private-tunnel-gateway.mjs"))
                self.assertFalse(argv[1].endswith("/gateway.mjs"))

                config = json.loads(roots["config"].read_text())
                self.assertEqual(config["accountLabel"], "test-account")
                self.assertEqual(config["port"], 45018)
                self.assertNotIn("publicUrl", config)
                self.assertEqual(config["idleTimeoutMs"], 1_800_000)
                self.assertEqual(config["requestTimeoutMs"], 300_000)
                self.assertEqual(config["reclaimIdleGraceMs"], 30_000)
                self.assertEqual(config["maxSessions"], 256)
                self.assertEqual(config["gitPublish"]["enabled"], True)
                self.assertEqual(
                    config["gitPublish"]["workspaceCli"],
                    str(home / ".local" / "bin" / "mmx-workspace"),
                )
                self.assertEqual(
                    config["gitPublish"]["sourceRepository"],
                    str(home / "Documents" / "GitHub" / "Mastermind"),
                )
                self.assertEqual(
                    config["gitPublish"]["allowedRemoteUrls"],
                    ["https://github.com/mastermindx-market-intelligence/Mastermind.git"],
                )

                manifest = json.loads(roots["manifest"].read_text())
                self.assertEqual(manifest["account"], "test-account")
                self.assertEqual(manifest["label"], _label_for("test-account"))
                self.assertEqual(manifest["port"], 45018)
                self.assertEqual(manifest["configHash"], svc._sha256_file(roots["config"]))
                self.assertEqual(manifest["plistHash"], svc._sha256_file(roots["plist"]))
                for name in svc.STAGE_FILES:
                    self.assertEqual(len(manifest["files"][name]), 64)

    def test_stage_idempotent_same_source(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir(parents=True, exist_ok=True)
            (home / "Library" / "LaunchAgents").mkdir(parents=True, exist_ok=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                src, node, backend, _rec = _do_stage(tmp, home, port=45019)
                roots = svc._build_runtime_roots("test-account")
                original_manifest = roots["manifest"].read_bytes()
                original_config = roots["config"].read_bytes()
                original_plist = roots["plist"].read_bytes()

                rec = CmdRecorder()
                with mock.patch.object(svc, "_run", rec):
                    rc, _ = _capture_stdout(
                        lambda: svc.cmd_stage(_stage_args(src, node, backend, "test-account", 45019))
                    )
                self.assertEqual(rc, 0)
                self.assertEqual(roots["manifest"].read_bytes(), original_manifest)
                self.assertEqual(roots["config"].read_bytes(), original_config)
                self.assertEqual(roots["plist"].read_bytes(), original_plist)

    def test_stage_refuses_changed_source_content_same_path(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir(parents=True, exist_ok=True)
            (home / "Library" / "LaunchAgents").mkdir(parents=True, exist_ok=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                src, node, backend, _ = _do_stage(tmp, home)
                roots = svc._build_runtime_roots("test-account")
                before_adapter = roots["gateway"].read_bytes()
                before_config = roots["config"].read_bytes()
                (src / "private-tunnel-gateway.mjs").write_text("// mutated adapter\n")
                with mock.patch.object(svc, "_run", CmdRecorder()):
                    with self.assertRaises(SystemExit) as ctx:
                        svc.cmd_stage(_stage_args(src, node, backend))
                    self.assertIn("incoming", str(ctx.exception).lower())
                self.assertEqual(roots["gateway"].read_bytes(), before_adapter)
                self.assertEqual(roots["config"].read_bytes(), before_config)

    def test_stage_refuses_different_port(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir(parents=True, exist_ok=True)
            (home / "Library" / "LaunchAgents").mkdir(parents=True, exist_ok=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                src, node, backend, _ = _do_stage(tmp, home, port=45018)
                roots = svc._build_runtime_roots("test-account")
                before = roots["config"].read_bytes()
                with mock.patch.object(svc, "_run", CmdRecorder()):
                    with self.assertRaises(SystemExit) as ctx:
                        svc.cmd_stage(_stage_args(src, node, backend, "test-account", 45019))
                    self.assertIn("diverge", str(ctx.exception))
                self.assertEqual(roots["config"].read_bytes(), before)
                self.assertEqual(json.loads(before)["port"], 45018)

    def test_stage_refuses_tampered_plist_hash(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir(parents=True, exist_ok=True)
            (home / "Library" / "LaunchAgents").mkdir(parents=True, exist_ok=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                src, node, backend, _ = _do_stage(tmp, home)
                roots = svc._build_runtime_roots("test-account")
                before = roots["plist"].read_bytes()
                roots["plist"].write_bytes(before + b"\n")
                with mock.patch.object(svc, "_run", CmdRecorder()):
                    with self.assertRaises(SystemExit) as ctx:
                        svc.cmd_stage(_stage_args(src, node, backend))
                    self.assertIn("plist", str(ctx.exception).lower())
                self.assertEqual(roots["plist"].read_bytes(), before + b"\n")

    def test_stage_refuses_different_source(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir(parents=True, exist_ok=True)
            (home / "Library" / "LaunchAgents").mkdir(parents=True, exist_ok=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _do_stage(tmp, home)
                other = tmp / "other-src"
                other.mkdir()
                for name in svc.STAGE_FILES:
                    (other / name).write_text(f"CHANGED {name}\n", encoding="utf-8")
                with mock.patch.object(svc, "_run", CmdRecorder()):
                    with self.assertRaises(SystemExit) as ctx:
                        svc.cmd_stage(_stage_args(other, _make_node(tmp), _make_backend(tmp)))
                    self.assertIn("diverge", str(ctx.exception))

    def test_stage_refuses_unmanifested_foreign_file(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir(parents=True, exist_ok=True)
            (home / "Library" / "LaunchAgents").mkdir(parents=True, exist_ok=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                roots = svc._build_runtime_roots("test-account")
                roots["base"].mkdir(parents=True)
                foreign = roots["base"] / "private-tunnel-gateway.mjs"
                foreign.write_text("FOREIGN ADAPTER\n")
                with mock.patch.object(svc, "_run", CmdRecorder()):
                    with self.assertRaises(SystemExit) as ctx:
                        svc.cmd_stage(_stage_args(_make_source(tmp), _make_node(tmp), _make_backend(tmp)))
                    self.assertIn("unmanifested", str(ctx.exception))
                self.assertEqual(foreign.read_text(), "FOREIGN ADAPTER\n")

    def test_stage_rejects_symlinked_source_file(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                src = _make_source(tmp)
                real = tmp / "elsewhere.mjs"
                real.write_text("contents")
                (src / "private-tunnel-gateway.mjs").unlink()
                (src / "private-tunnel-gateway.mjs").symlink_to(real)
                with mock.patch.object(svc, "_run", CmdRecorder()):
                    with self.assertRaises(SystemExit) as ctx:
                        svc.cmd_stage(_stage_args(src, _make_node(tmp), _make_backend(tmp)))
                    self.assertIn("symlink", str(ctx.exception).lower())

    def test_stage_refuses_running_service(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            plist_path = str(tmp / "test.plist")
            label = _label_for("test-account")
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _do_stage(tmp, home)
                roots = svc._build_runtime_roots("test-account")
                before = roots["gateway"].read_bytes()

                def handler(cmd):
                    if cmd[:2] == ["launchctl", "print"]:
                        return FakeResult(0, _print_running(plist_path, label), "")
                    return FakeResult(1, "", "unused")

                writes = []
                with mock.patch.object(svc, "_run", CmdRecorder(handler=handler)), \
                     mock.patch.object(
                         svc, "_atomic_write_bytes",
                         side_effect=lambda *a, **k: writes.append(a[0]),
                     ):
                    with self.assertRaises(SystemExit) as ctx:
                        svc.cmd_stage(_stage_args(_make_source(tmp), _make_node(tmp), _make_backend(tmp)))
                    self.assertIn("running", str(ctx.exception))
                self.assertEqual(writes, [])
                self.assertEqual(roots["gateway"].read_bytes(), before)

    def test_stage_refuses_missing_source_file(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            src = tmp / "incomplete"
            src.mkdir()
            (src / "gateway.mjs").write_text("x")
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                with mock.patch.object(svc, "_run", CmdRecorder()):
                    with self.assertRaises(SystemExit) as ctx:
                        svc.cmd_stage(_stage_args(src, _make_node(tmp), _make_backend(tmp)))
                    self.assertIn("missing", str(ctx.exception).lower())

    def test_stage_rejects_relative_source_node_and_backend(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                with self.assertRaises(SystemExit) as ctx:
                    svc.cmd_stage(_stage_args("relative-src", _make_node(tmp), _make_backend(tmp)))
                self.assertIn("absolute", str(ctx.exception).lower())
                with self.assertRaises(SystemExit):
                    svc.cmd_stage(_stage_args(_make_source(tmp), _make_node(tmp), "relative.mjs"))
                with self.assertRaises(SystemExit):
                    svc.cmd_stage(_stage_args(_make_source(tmp), "relnode", _make_backend(tmp)))

    def test_stage_rejects_invalid_and_reserved_port(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                with self.assertRaises(SystemExit) as ctx:
                    svc.cmd_stage(_stage_args(_make_source(tmp), _make_node(tmp), _make_backend(tmp), "test-account", 80))
                self.assertIn("port", str(ctx.exception).lower())
                with self.assertRaises(SystemExit) as ctx:
                    svc.cmd_stage(_stage_args(_make_source(tmp), _make_node(tmp), _make_backend(tmp), "test-account", 70000))
                self.assertIn("port", str(ctx.exception).lower())
                with self.assertRaises(SystemExit) as ctx:
                    svc.cmd_stage(_stage_args(_make_source(tmp), _make_node(tmp), _make_backend(tmp), "test-account", 45017))
                self.assertIn("45017", str(ctx.exception))
                self.assertFalse((home / ".local").exists())

    def test_stage_rejects_symlink_in_dest_leaf(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            dangerous = home / ".local" / "share" / "studio-direct-mcp" / "private"
            dangerous.mkdir(parents=True)
            (dangerous / "test-account").symlink_to(tmp / "evil")
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                with mock.patch.object(svc, "_run", CmdRecorder()):
                    with self.assertRaises(SystemExit) as ctx:
                        svc.cmd_stage(_stage_args(_make_source(tmp), _make_node(tmp), _make_backend(tmp), "test-account", 45018))
                    self.assertIn("symlink", str(ctx.exception).lower())

    def test_stage_rejects_parent_directory_symlink(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            evil = tmp / "evil"
            evil.mkdir()
            (home / ".local").symlink_to(evil)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                with mock.patch.object(svc, "_run", CmdRecorder()):
                    with self.assertRaises(SystemExit) as ctx:
                        svc.cmd_stage(_stage_args(_make_source(tmp), _make_node(tmp), _make_backend(tmp)))
                    self.assertIn("symlink", str(ctx.exception).lower())
            self.assertFalse((evil / "share").exists())


# -------------------------------------------------------------------
# Upgrade
# -------------------------------------------------------------------

class TestUpgrade(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(svc, "PAPER_BRIDGE_SHA256", PAPER_BRIDGE_FIXTURE_SHA)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_legacy_install_upgrades_stopped_and_preserves_runtime_state(self):
        self._assert_historical_upgrade(typed_git=False)

    def test_typed_git_install_upgrades_stopped_and_preserves_runtime_state(self):
        self._assert_historical_upgrade(typed_git=True)

    def _assert_historical_upgrade(self, *, typed_git):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _src, node, backend, _ = _do_stage(tmp, home)
                roots = svc._build_runtime_roots("test-account")
                _seed_node_modules(roots)
                legacy = _convert_to_legacy_install(roots, typed_git=typed_git)
                (roots["state"] / "oauth-state.json").write_text("STATE\n")
                (roots["logs"] / "prior.log").write_text("LOG\n")
                (roots["node_modules"] / "marker").write_text("DEPS\n")
                upgraded_source = _make_upgrade_source(tmp)

                with mock.patch.object(svc, "_run", CmdRecorder()):
                    rc, out = _capture_stdout(
                        lambda: svc.cmd_upgrade(
                            _stage_args(upgraded_source, node, backend)
                        )
                    )
                self.assertEqual(rc, 0)
                payload = json.loads(out)
                self.assertTrue(payload["upgraded"])
                self.assertEqual(payload["previousSource"], legacy["source"])
                self.assertEqual(payload["source"], str(upgraded_source))

                manifest = json.loads(roots["manifest"].read_text())
                self.assertEqual(set(manifest["files"]), set(svc.STAGE_FILES))
                self.assertEqual(manifest["source"], str(upgraded_source))
                self.assertTrue((roots["base"] / "git-publish.mjs").is_file())
                self.assertTrue((roots["base"] / "output-budget.mjs").is_file())
                config = json.loads(roots["config"].read_text())
                self.assertTrue(config["gitPublish"]["enabled"])
                self.assertEqual(config["reclaimIdleGraceMs"], 30_000)
                self.assertEqual((roots["state"] / "oauth-state.json").read_text(), "STATE\n")
                self.assertEqual((roots["logs"] / "prior.log").read_text(), "LOG\n")
                self.assertEqual((roots["node_modules"] / "marker").read_text(), "DEPS\n")
                self.assertEqual(manifest["version"], svc.MANIFEST_VERSION)
                self.assertIsNone(manifest["dependencyTreeHash"])
                _seal_runtime()
                svc._verify_staged_install("test-account", _label_for("test-account"), roots)

    def test_v2_fleet_tailnet_canary_refuses_downgrade_without_effects(self):
        """Sealed historical v0.1.10 must not lose live fleet routes on upgrade."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            account = "chatgpt1"
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _, node, backend, _ = _do_stage(tmp, home, account=account)
                roots = svc._build_runtime_roots(account)
                _seed_node_modules(roots)
                names = svc.V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR
                for name in set(svc.STAGE_FILES) - names:
                    (roots["base"] / name).unlink()
                for name in names - set(svc.STAGE_FILES):
                    (roots["base"] / name).write_text(
                        f"// legacy approved {name}\n", encoding="utf-8")
                prior = json.loads(roots["manifest"].read_text())
                prior["files"] = {
                    name: svc._sha256_file(roots["base"] / name)
                    for name in sorted(names)
                }
                config = json.loads(roots["config"].read_text())
                config["repositoryWorkspaces"] = {
                    "enabled": True,
                    "allowedRepositories": ["mastermind", "macro", "terminal"],
                }
                config["gitPublish"] = svc._typed_git_config(
                    home, closed_repositories=True)
                config["fleetRouting"] = {
                    "enabled": True, "requestTimeoutMs": svc.REQUEST_TIMEOUT_MS,
                    "routes": [
                        {"hostRef": "ubuntu1", "url": "https://ubuntu1.example.ts.net/mcp"},
                        {"hostRef": "ubuntu2", "url": "https://ubuntu2.example.ts.net/mcp"},
                    ],
                }
                config["maxPerSessionConcurrency"] = 8
                config["maxQueuedPerSession"] = 16
                config["fleetStatus"] = {
                    "enabled": True,
                    "launcherPath": str(home / ".local/bin/studio-direct"),
                    "launcherSha256": "a" * 64,
                    "timeoutMs": 15000,
                    "fabricLauncherPath": str(home / ".local/bin/pool"),
                    "fabricLauncherSha256": "b" * 64,
                    "fabricTimeoutMs": 8000,
                }
                roots["config"].write_text(
                    json.dumps(config, sort_keys=True), encoding="utf-8")
                prior["configHash"] = svc._sha256_file(roots["config"])
                roots["manifest"].write_text(
                    json.dumps(prior, sort_keys=True), encoding="utf-8")
                _seal_runtime(account)
                verified = svc._verify_staged_install(
                    account, _label_for(account), roots)
                self.assertEqual(set(verified["files"]), names)
                legacy_path = roots["base"] / "fleet-routing.mjs"
                saved = legacy_path.read_bytes()
                try:
                    legacy_path.write_bytes(saved + b"unauthorized")
                    with self.assertRaisesRegex(SystemExit, "hash mismatch"):
                        svc._verify_staged_install(
                            account, _label_for(account), roots)
                finally:
                    legacy_path.write_bytes(saved)
                upgraded_source = _make_upgrade_source(tmp)
                before_manifest = roots["manifest"].read_bytes()
                before_config = roots["config"].read_bytes()
                before_files = {
                    name: (roots["base"] / name).read_bytes()
                    for name in names
                }
                recorder = CmdRecorder()
                with mock.patch.object(svc, "_run", recorder):
                    with self.assertRaisesRegex(SystemExit, "fleet|capability|downgrade"):
                        svc.cmd_upgrade(
                            _stage_args(upgraded_source, node, backend, account))
                self.assertEqual(roots["manifest"].read_bytes(), before_manifest)
                self.assertEqual(roots["config"].read_bytes(), before_config)
                self.assertEqual(
                    {name: (roots["base"] / name).read_bytes() for name in names},
                    before_files)
                self.assertTrue(recorder.calls)
                self.assertTrue(all(
                    call[:2] == ["launchctl", "print"] for call in recorder.calls
                ), "read-only launchd query allowed; no modification permitted")
                self.assertFalse((roots["base"] / "commission-prepare.mjs").exists())
                svc._verify_staged_install(account, _label_for(account), roots)
                # Even if future source contains fleet/tailnet JS files, the
                # prospective config must not discard its 2 routes or 8/16 caps.
                for name in names - set(svc.STAGE_FILES):
                    (upgraded_source / name).write_text(
                        f"// future reviewed {name}\n", encoding="utf-8")
                with mock.patch.object(
                    svc, "STAGE_FILES", svc.STAGE_FILES + tuple(
                        sorted(names - set(svc.STAGE_FILES))
                    )
                ):
                    with mock.patch.object(svc, "_run", CmdRecorder()):
                        with self.assertRaisesRegex(SystemExit, "fleet capability fleetRouting"):
                            svc.cmd_upgrade(
                                _stage_args(upgraded_source, node, backend, account))
                    # A future compatible release is allowed only when its
                    # *complete* prospective routing/caps/status exactly match.
                    svc._verify_upgrade_preserves_installed_fleet_capabilities(
                        prior, roots, config)
                    for key in (
                        "fleetRouting", "maxPerSessionConcurrency",
                        "maxQueuedPerSession", "fleetStatus",
                    ):
                        incompatible = dict(config)
                        incompatible.pop(key)
                        with self.assertRaisesRegex(SystemExit, "fleet capability " + key):
                            svc._verify_upgrade_preserves_installed_fleet_capabilities(
                                prior, roots, incompatible)
                self.assertEqual(roots["manifest"].read_bytes(), before_manifest)
                self.assertEqual(roots["config"].read_bytes(), before_config)

    def test_legacy_install_can_be_stopped_before_upgrade(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            label = _label_for("test-account")
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _do_stage(tmp, home)
                roots = svc._build_runtime_roots("test-account")
                _seed_node_modules(roots)
                _convert_to_legacy_install(roots)
                plist_path = str(roots["plist"])
                prints = iter([
                    FakeResult(0, _print_running(plist_path, label), ""),
                    FakeResult(1, "", "not loaded"),
                ])

                def handler(cmd):
                    if cmd[:2] == ["launchctl", "print"]:
                        return next(prints)
                    if cmd[:2] == ["launchctl", "bootout"]:
                        return FakeResult(0, "", "")
                    return FakeResult(1, "", "unused")

                rec = CmdRecorder(handler=handler)
                with mock.patch.object(svc, "_run", rec):
                    rc, out = _capture_stdout(
                        lambda: svc.cmd_stop(mock.Mock(account="test-account"))
                    )
                self.assertEqual(rc, 0)
                self.assertTrue(json.loads(out)["stopped"])
                self.assertTrue(any(c[:2] == ["launchctl", "bootout"] for c in rec.calls))

    def test_upgrade_refuses_running_service_before_writes(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            label = _label_for("test-account")
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _src, node, backend, _ = _do_stage(tmp, home)
                roots = svc._build_runtime_roots("test-account")
                _seed_node_modules(roots)
                upgraded_source = _make_upgrade_source(tmp)
                before = roots["manifest"].read_bytes()

                def handler(cmd):
                    if cmd[:2] == ["launchctl", "print"]:
                        return FakeResult(0, _print_running(str(roots["plist"]), label), "")
                    return FakeResult(1, "", "unused")

                with mock.patch.object(svc, "_run", CmdRecorder(handler=handler)):
                    with self.assertRaisesRegex(SystemExit, "running"):
                        svc.cmd_upgrade(_stage_args(upgraded_source, node, backend))
                self.assertEqual(roots["manifest"].read_bytes(), before)

    def test_upgrade_refuses_tampered_install(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _src, node, backend, _ = _do_stage(tmp, home)
                roots = svc._build_runtime_roots("test-account")
                _seed_node_modules(roots)
                roots["gateway"].write_text("TAMPERED\n")
                with mock.patch.object(svc, "_run", CmdRecorder()):
                    with self.assertRaisesRegex(SystemExit, "hash mismatch"):
                        svc.cmd_upgrade(_stage_args(_make_upgrade_source(tmp), node, backend))

    def test_upgrade_refuses_port_node_or_backend_change(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _src, node, backend, _ = _do_stage(tmp, home, port=45018)
                roots = svc._build_runtime_roots("test-account")
                _seed_node_modules(roots)
                upgraded_source = _make_upgrade_source(tmp)
                other_node = tmp / "other-node"
                other_node.write_text("node2\n")
                other_backend = tmp / "other-backend.mjs"
                other_backend.write_text("backend2\n")
                cases = [
                    _stage_args(upgraded_source, node, backend, port=45019),
                    _stage_args(upgraded_source, other_node, backend),
                    _stage_args(upgraded_source, node, other_backend),
                ]
                for args in cases:
                    with self.subTest(args=args):
                        with mock.patch.object(svc, "_run", CmdRecorder()):
                            with self.assertRaisesRegex(SystemExit, "must match"):
                                svc.cmd_upgrade(args)


# -------------------------------------------------------------------
# Runtime identity seal
# -------------------------------------------------------------------

class TestRuntimeSeal(unittest.TestCase):
    def _staged_runtime(self, tmp: Path, home: Path):
        src, node, backend, _ = _do_stage(tmp, home)
        roots = svc._build_runtime_roots("test-account")
        _seed_node_modules(roots)
        return src, node, backend, roots

    def test_stage_records_runtime_hashes_but_leaves_dependencies_unsealed(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _src, node, backend, _ = _do_stage(tmp, home)
                roots = svc._build_runtime_roots("test-account")
                manifest = json.loads(roots["manifest"].read_text())
                self.assertEqual(manifest["version"], svc.MANIFEST_VERSION)
                self.assertEqual(manifest["nodeHash"], svc._sha256_file(node))
                self.assertEqual(manifest["backendHash"], svc._sha256_file(backend))
                self.assertIsNone(manifest["dependencyTreeHash"])

    def test_start_refuses_unsealed_runtime_before_launchd_effect(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _src, _node, _backend, roots = self._staged_runtime(tmp, home)
                rec = CmdRecorder()
                with mock.patch.object(svc, "_run", rec):
                    with self.assertRaisesRegex(SystemExit, "not sealed"):
                        svc.cmd_start(mock.Mock(account="test-account"))
                self.assertFalse(any(c[:2] == ["launchctl", "bootstrap"] for c in rec.calls))

    def test_seal_runtime_binds_dependency_tree_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _src, _node, _backend, roots = self._staged_runtime(tmp, home)
                rc, out = _seal_runtime()
                self.assertEqual(rc, 0)
                first = json.loads(out)["dependencyTreeHash"]
                self.assertRegex(first, r"^[0-9a-f]{64}$")
                manifest = json.loads(roots["manifest"].read_text())
                self.assertEqual(manifest["dependencyTreeHash"], first)
                rc, out = _seal_runtime()
                self.assertEqual(rc, 0)
                self.assertEqual(json.loads(out)["dependencyTreeHash"], first)

    def test_seal_runtime_refuses_loaded_service_without_manifest_write(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            label = _label_for("test-account")
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _src, _node, _backend, roots = self._staged_runtime(tmp, home)
                before = roots["manifest"].read_bytes()
                def handler(cmd):
                    if cmd[:2] == ["launchctl", "print"]:
                        return FakeResult(0, _print_running(str(roots["plist"]), label), "")
                    return FakeResult(1, "", "unused")
                with mock.patch.object(svc, "_run", CmdRecorder(handler=handler)):
                    with self.assertRaisesRegex(SystemExit, "loaded"):
                        svc.cmd_seal_runtime(mock.Mock(account="test-account"))
                self.assertEqual(roots["manifest"].read_bytes(), before)

    def test_seal_runtime_refuses_node_or_backend_drift(self):
        for target_name in ("node", "backend"):
            with self.subTest(target=target_name), tempfile.TemporaryDirectory() as raw:
                tmp = Path(raw)
                home = tmp / "home"
                home.mkdir()
                (home / "Library" / "LaunchAgents").mkdir(parents=True)
                with mock.patch.dict(os.environ, {"HOME": str(home)}):
                    _src, node, backend, roots = self._staged_runtime(tmp, home)
                    target = node if target_name == "node" else backend
                    target.write_text(target.read_text() + "DRIFT\n", encoding="utf-8")
                    before = roots["manifest"].read_bytes()
                    with self.assertRaisesRegex(SystemExit, "hash mismatch"):
                        _seal_runtime()
                    self.assertEqual(roots["manifest"].read_bytes(), before)

    def test_start_refuses_same_path_runtime_drift_before_launchd_effect(self):
        for target_name in ("node", "backend", "dependency"):
            with self.subTest(target=target_name), tempfile.TemporaryDirectory() as raw:
                tmp = Path(raw)
                home = tmp / "home"
                home.mkdir()
                (home / "Library" / "LaunchAgents").mkdir(parents=True)
                with mock.patch.dict(os.environ, {"HOME": str(home)}):
                    _src, node, backend, roots = self._staged_runtime(tmp, home)
                    _seal_runtime()
                    if target_name == "node":
                        node.write_text(node.read_text() + "DRIFT\n", encoding="utf-8")
                    elif target_name == "backend":
                        backend.write_text(backend.read_text() + "DRIFT\n", encoding="utf-8")
                    else:
                        dep = roots["node_modules"] / "fixture-package" / "index.js"
                        dep.write_text("export const fixture = 2;\n", encoding="utf-8")
                    rec = CmdRecorder()
                    with mock.patch.object(svc, "_run", rec):
                        with self.assertRaisesRegex(SystemExit, "hash mismatch"):
                            svc.cmd_start(mock.Mock(account="test-account"))
                    self.assertFalse(any(c[:2] == ["launchctl", "bootstrap"] for c in rec.calls))

    def test_dependency_tree_refuses_change_between_stability_scans(self):
        with mock.patch.object(
            svc,
            "_dependency_tree_hash_once",
            side_effect=["a" * 64, "b" * 64],
        ):
            with self.assertRaisesRegex(SystemExit, "changed while hashing"):
                svc._dependency_tree_hash(Path("/unused"))

    def test_dependency_symlink_is_bound_and_escape_is_refused(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _src, _node, _backend, roots = self._staged_runtime(tmp, home)
                deps = roots["node_modules"]
                bin_dir = deps / ".bin"
                bin_dir.mkdir()
                link = bin_dir / "fixture"
                link.symlink_to("../fixture-package/index.js")
                _seal_runtime()
                link.unlink()
                other = deps / "fixture-package" / "other.js"
                other.write_text("export const other = 1;\n", encoding="utf-8")
                link.symlink_to("../fixture-package/other.js")
                with self.assertRaisesRegex(SystemExit, "dependency tree hash mismatch"):
                    svc.cmd_start(mock.Mock(account="test-account"))

                # A fresh unsealed install cannot bless a dependency link that
                # resolves outside node_modules.
                roots["manifest"].unlink()
                # Restage on a clean fixture for a direct seal refusal.
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _src, _node, _backend, roots = self._staged_runtime(tmp, home)
                outside = tmp / "outside.js"
                outside.write_text("outside\n", encoding="utf-8")
                link = roots["node_modules"] / "escape"
                link.symlink_to(outside)
                with self.assertRaisesRegex(SystemExit, "escapes node_modules"):
                    _seal_runtime()

    def test_legacy_manifest_must_upgrade_before_start(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _do_stage(tmp, home)
                roots = svc._build_runtime_roots("test-account")
                _seed_node_modules(roots)
                _convert_to_legacy_install(roots, typed_git=True)
                with self.assertRaisesRegex(SystemExit, "legacy manifest"):
                    svc.cmd_start(mock.Mock(account="test-account"))

# -------------------------------------------------------------------
# Start
# -------------------------------------------------------------------

class TestStart(unittest.TestCase):
    def test_start_bootstraps_exact_install(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _do_stage(tmp, home)
                roots = svc._build_runtime_roots("test-account")
                _seed_node_modules(roots)
                _seal_runtime()
                recorder = CmdRecorder()
                with mock.patch.object(svc, "_run", recorder):
                    rc, out = _capture_stdout(
                        lambda: svc.cmd_start(mock.Mock(account="test-account"))
                    )
                self.assertEqual(rc, 0)
                boot = [c for c in recorder.calls if c[:2] == ["launchctl", "bootstrap"]]
                self.assertEqual(len(boot), 1)
                self.assertEqual(boot[0][2], svc._launchd_domain())
                self.assertTrue(json.loads(out)["started"])

    def test_start_idempotent_when_already_loaded(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            label = _label_for("test-account")
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _do_stage(tmp, home)
                roots = svc._build_runtime_roots("test-account")
                _seed_node_modules(roots)
                _seal_runtime()
                plist_path = str(roots["plist"])

                def handler(cmd):
                    if cmd[:2] == ["launchctl", "print"]:
                        return FakeResult(0, _print_running(plist_path, label), "")
                    if cmd[1] == "bootstrap":
                        raise AssertionError("bootstrap must not rerun for exact loaded install")
                    return FakeResult(1, "", "")

                rec = CmdRecorder(handler=handler)
                with mock.patch.object(svc, "_run", rec):
                    rc, out = _capture_stdout(
                        lambda: svc.cmd_start(mock.Mock(account="test-account"))
                    )
                self.assertEqual(rc, 0)
                self.assertTrue(json.loads(out)["already"])

    def test_start_requires_node_modules(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _do_stage(tmp, home)
                with mock.patch.object(svc, "_run", CmdRecorder()):
                    with self.assertRaises(SystemExit) as ctx:
                        svc.cmd_start(mock.Mock(account="test-account"))
                    self.assertIn("node_modules", str(ctx.exception))

    def test_start_rejects_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _do_stage(tmp, home)
                roots = svc._build_runtime_roots("test-account")
                _seed_node_modules(roots)
                roots["gateway"].write_text("TAMPERED")
                with mock.patch.object(svc, "_run", CmdRecorder()):
                    with self.assertRaises(SystemExit) as ctx:
                        svc.cmd_start(mock.Mock(account="test-account"))
                    self.assertIn("hash mismatch", str(ctx.exception))

    def test_start_rejects_config_tamper(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _do_stage(tmp, home)
                roots = svc._build_runtime_roots("test-account")
                _seed_node_modules(roots)
                roots["config"].write_text("TAMPERED CONFIG")
                with mock.patch.object(svc, "_run", CmdRecorder()):
                    with self.assertRaises(SystemExit) as ctx:
                        svc.cmd_start(mock.Mock(account="test-account"))
                    self.assertIn("config", str(ctx.exception).lower())

    def test_start_rejects_plist_hash_tamper(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _do_stage(tmp, home)
                roots = svc._build_runtime_roots("test-account")
                _seed_node_modules(roots)
                roots["plist"].write_bytes(roots["plist"].read_bytes() + b"\n")
                with mock.patch.object(svc, "_run", CmdRecorder()):
                    with self.assertRaises(SystemExit) as ctx:
                        svc.cmd_start(mock.Mock(account="test-account"))
                    self.assertIn("plist hash mismatch", str(ctx.exception))


# -------------------------------------------------------------------
# Stop
# -------------------------------------------------------------------

class TestStop(unittest.TestCase):
    def test_stop_idempotent_when_not_loaded(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _do_stage(tmp, home)
                recorder = CmdRecorder()
                with mock.patch.object(svc, "_run", recorder):
                    rc, out = _capture_stdout(
                        lambda: svc.cmd_stop(mock.Mock(account="test-account"))
                    )
                self.assertEqual(rc, 0)
                self.assertTrue(json.loads(out)["already"])
                self.assertFalse(any(c[1] == "bootout" for c in recorder.calls))

    def test_stop_bootouts_and_verifies_absence(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            label = _label_for("test-account")
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _do_stage(tmp, home)
                roots = svc._build_runtime_roots("test-account")
                _seed_node_modules(roots)
                plist_path = str(roots["plist"])

                prints = iter([
                    FakeResult(0, _print_running(plist_path, label), ""),
                    FakeResult(0, _print_crashed(plist_path, label), ""),
                    FakeResult(1, "", "No such process"),
                ])

                def handler(cmd):
                    if cmd[:2] == ["launchctl", "print"]:
                        return next(prints)
                    if cmd[:2] == ["launchctl", "bootout"]:
                        self.assertEqual(cmd[2], svc._launchd_target(label))
                        self.assertIn(label, cmd[2])
                        return FakeResult(0, "", "")
                    return FakeResult(1, "", "")

                rec = CmdRecorder(handler=handler)
                with mock.patch.object(svc, "_run", rec):
                    rc, out = _capture_stdout(
                        lambda: svc.cmd_stop(mock.Mock(account="test-account"))
                    )
                self.assertEqual(rc, 0)
                self.assertTrue(json.loads(out)["stopped"])

    def test_stop_refuses_foreign_loaded_plist(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _do_stage(tmp, home)
                roots = svc._build_runtime_roots("test-account")
                _seed_node_modules(roots)
                rec = CmdRecorder(
                    handler=lambda cmd: FakeResult(
                        0,
                        _print_running("/foreign/job.plist", "com.foreign.label"),
                        "",
                    )
                )
                with mock.patch.object(svc, "_run", rec):
                    with self.assertRaisesRegex(SystemExit, "not our exact install"):
                        svc.cmd_stop(mock.Mock(account="test-account"))
                self.assertFalse(any(c[1] == "bootout" for c in rec.calls))


    def test_stop_remains_available_after_runtime_byte_drift(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            label = _label_for("test-account")
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _src, node, _backend, _ = _do_stage(tmp, home)
                roots = svc._build_runtime_roots("test-account")
                _seed_node_modules(roots)
                _seal_runtime()
                node.write_text(node.read_text() + "DRIFT\n", encoding="utf-8")
                dep = roots["node_modules"] / "fixture-package" / "index.js"
                dep.write_text("DRIFT\n", encoding="utf-8")
                prints = iter([
                    FakeResult(0, _print_running(str(roots["plist"]), label), ""),
                    FakeResult(1, "", "not loaded"),
                ])
                def handler(cmd):
                    if cmd[:2] == ["launchctl", "print"]:
                        return next(prints)
                    if cmd[:2] == ["launchctl", "bootout"]:
                        return FakeResult(0, "", "")
                    return FakeResult(1, "", "unused")
                rec = CmdRecorder(handler=handler)
                with mock.patch.object(svc, "_run", rec):
                    rc, out = _capture_stdout(
                        lambda: svc.cmd_stop(mock.Mock(account="test-account"))
                    )
                self.assertEqual(rc, 0)
                self.assertTrue(json.loads(out)["stopped"])
                self.assertTrue(any(c[:2] == ["launchctl", "bootout"] for c in rec.calls))


# -------------------------------------------------------------------
# Status
# -------------------------------------------------------------------

class TestStatus(unittest.TestCase):
    def test_status_returns_account_info(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            label = _label_for("test-account")
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _do_stage(tmp, home)
                roots = svc._build_runtime_roots("test-account")
                plist_path = str(roots["plist"])

                def handler(cmd):
                    if cmd[:2] == ["launchctl", "print"]:
                        return FakeResult(0, _print_running(plist_path, label), "")
                    return FakeResult(1, "", "")

                with mock.patch.object(svc, "_run", CmdRecorder(handler=handler)):
                    rc, out = _capture_stdout(
                        lambda: svc.cmd_status(mock.Mock(account="test-account"))
                    )
                self.assertEqual(rc, 0)
                payload = json.loads(out)
                self.assertEqual(payload["account"], "test-account")
                self.assertEqual(payload["label"], label)
                self.assertTrue(payload["loaded"])
                self.assertTrue(payload["running"])
                self.assertEqual(payload["pid"], 4321)


# -------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------

class TestCLI(unittest.TestCase):
    def test_parser_has_expected_subcommands(self):
        parser = svc.build_parser()
        sub = next(a for a in parser._actions if hasattr(a, "choices") and a.choices)
        self.assertEqual(
            set(sub.choices),
            {"stage", "upgrade", "paper-runtime-upgrade", "fabric-backend-release", "seal-runtime", "start", "status", "stop"},
        )

    def test_stage_requires_all_args(self):
        parser = svc.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["stage"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["stage", "--account", "test"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["stage", "--account", "test", "--port", "45018", "--source", "/x", "--node", "/x"])

    def test_upgrade_requires_all_args(self):
        parser = svc.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["upgrade"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["upgrade", "--account", "test"])

    def test_seal_start_status_stop_require_account(self):
        parser = svc.build_parser()
        for cmd in ("seal-runtime", "start", "status", "stop"):
            with self.assertRaises(SystemExit):
                parser.parse_args([cmd])

    def test_help_does_not_crash(self):
        parser = svc.build_parser()
        try:
            parser.parse_args(["--help"])
        except SystemExit as e:
            self.assertEqual(e.code, 0)


# -------------------------------------------------------------------
# Atomic write
# -------------------------------------------------------------------

class TestAtomicWrite(unittest.TestCase):
    def test_atomic_write_fsyncs_and_mode_0600(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "home"
            home.mkdir()
            dest = home / "file.txt"
            synced = []
            real_fsync = os.fsync

            def spy(fd):
                synced.append(fd)
                return real_fsync(fd)

            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                with mock.patch.object(svc.os, "fsync", spy):
                    svc._atomic_write_text(dest, "hello", 0o600)
            self.assertTrue(synced)
            self.assertEqual(dest.read_text(), "hello")
            self.assertEqual(stat.S_IMODE(dest.stat().st_mode), 0o600)


# -------------------------------------------------------------------
# Symlink rejection
# -------------------------------------------------------------------

class TestSymlinkRejection(unittest.TestCase):
    def test_assert_dest_safe_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "home"
            home.mkdir()
            p = home / "link"
            p.symlink_to(home / "target")
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                with self.assertRaises(SystemExit) as ctx:
                    svc._assert_dest_safe(p)
                self.assertIn("symlink", str(ctx.exception).lower())

    def test_ensure_secure_dir_rejects_symlink_path(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "home"
            home.mkdir()
            d = home / "dir"
            d.mkdir()
            evil = home / "evil"
            evil.symlink_to(d)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                with self.assertRaises(SystemExit) as ctx:
                    svc._ensure_secure_dir(evil)
                self.assertIn("symlink", str(ctx.exception).lower())

    def test_ensure_secure_dir_rejects_parent_symlink(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "home"
            home.mkdir()
            evil = Path(raw) / "evil"
            evil.mkdir()
            (home / ".local").symlink_to(evil)
            dest = home / ".local" / "share" / "studio-direct-mcp" / "private" / "test-account"
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                with self.assertRaises(SystemExit) as ctx:
                    svc._ensure_secure_dir(dest)
                self.assertIn("symlink", str(ctx.exception).lower())
            self.assertFalse((evil / "share").exists())


class TestFleetV10PublisherCompatibility(unittest.TestCase):
    """One original manifest/installer owner, no new publisher or permission plane."""

    @contextmanager
    def _installed_fleet_fixture(self, account="chatgpt1"):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                source, node, backend, _ = _do_stage(tmp, home, account=account)
                roots = svc._build_runtime_roots(account)
                _seed_node_modules(roots)
                names = svc.V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR
                for name in set(svc.STAGE_FILES) - names:
                    (roots["base"] / name).unlink()
                for name in names - set(svc.STAGE_FILES):
                    (roots["base"] / name).write_text(
                        f"// fleet v0.1.10 {name}\n", encoding="utf-8")
                # Simulate old publisher modules; reviewed source holds replacements.
                for name in svc.FLEET_V10_PUBLISHER_PATCH_SHA256:
                    (roots["base"] / name).write_text(
                        f"// historical publisher {name}\n", encoding="utf-8")
                old = json.loads(roots["manifest"].read_text())
                old["files"] = {
                    name: svc._sha256_file(roots["base"] / name)
                    for name in sorted(names)
                }
                cfg = json.loads(roots["config"].read_text())
                cfg["repositoryWorkspaces"] = {
                    "enabled": True,
                    "allowedRepositories": ["mastermind", "macro", "terminal"],
                }
                cfg["fleetRouting"] = {
                    "enabled": True,
                    "requestTimeoutMs": svc.REQUEST_TIMEOUT_MS,
                    "routes": [
                        {"hostRef": "ubuntu1", "url": "https://ubuntu1.example.ts.net/mcp"},
                        {"hostRef": "ubuntu2", "url": "https://ubuntu2.example.ts.net/mcp"},
                    ],
                }
                cfg["maxPerSessionConcurrency"] = 8
                cfg["maxQueuedPerSession"] = 16
                cfg["fleetStatus"] = {
                    "enabled": True,
                    "launcherPath": str(home / ".local/bin/studio-direct"),
                    "launcherSha256": "a" * 64,
                    "timeoutMs": 15000,
                    "fabricLauncherPath": str(home / ".local/bin/fabric-pool"),
                    "fabricLauncherSha256": "b" * 64,
                    "fabricTimeoutMs": 8000,
                }
                roots["config"].write_text(
                    json.dumps(cfg, indent=2, sort_keys=True), encoding="utf-8")
                old["configHash"] = svc._sha256_file(roots["config"])
                roots["manifest"].write_text(
                    json.dumps(old, indent=2, sort_keys=True), encoding="utf-8")
                _seal_runtime(account)
                args = _stage_args(source, node, backend, account=account)
                args.publisher_only_fleet_v10 = True
                args.publisher_preflight_only = False
                args.publisher_expected_manifest_sha256 = svc._sha256_file(
                    roots["manifest"])
                installed_blobs = {}
                for name in svc.FLEET_V10_PRESERVED_GIT_BLOBS:
                    data = (roots["base"] / name).read_bytes()
                    installed_blobs[name] = hashlib.sha1(
                        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
                    ).hexdigest()
                source_hashes = {
                    name: svc._sha256_file(source / name)
                    for name in svc.FLEET_V10_PUBLISHER_PATCH_SHA256
                }
                with mock.patch.object(
                    svc, "FLEET_V10_PRESERVED_GIT_BLOBS", installed_blobs
                ), mock.patch.object(
                    svc, "FLEET_V10_PUBLISHER_PATCH_SHA256", source_hashes
                ), mock.patch.object(
                    svc, "PAPER_BRIDGE_SHA256", PAPER_BRIDGE_FIXTURE_SHA
                ):
                    yield args, roots, cfg

    @staticmethod
    def _all_files(roots):
        return {
            name: (roots["base"] / name).read_bytes()
            for name in svc.V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR
        }

    def test_readonly_preflight_even_while_live_requires_no_install_writes(self):
        with self._installed_fleet_fixture() as (args, roots, _cfg):
            before = (
                roots["manifest"].read_bytes(), roots["config"].read_bytes(),
                self._all_files(roots),
            )
            args.publisher_preflight_only = True
            result = CmdRecorder(handler=lambda c: FakeResult(
                0, _print_running(str(roots["plist"]), _label_for("chatgpt1")), "")
                if c[:2] == ["launchctl", "print"] else None)
            with mock.patch.object(svc, "_run", result):
                rc, printed = _capture_stdout(lambda: svc.cmd_upgrade(args))
            self.assertEqual(rc, 0)
            observed = json.loads(printed)
            self.assertEqual(observed["effect"], "NOT_APPLIED")
            self.assertEqual(observed["fleetRoutesPreserved"], 2)
            self.assertEqual(observed["concurrencyPreserved"], [8, 16])
            self.assertEqual(
                before,
                (roots["manifest"].read_bytes(),
                 roots["config"].read_bytes(), self._all_files(roots)),
            )
            self.assertTrue(all(call[:2] == ["launchctl", "print"]
                                for call in result.calls))
            args.publisher_preflight_only = False
            with mock.patch.object(svc, "_run", result):
                with self.assertRaisesRegex(SystemExit, "while service is loaded"):
                    svc.cmd_upgrade(args)
            self.assertEqual(before[0], roots["manifest"].read_bytes())

    def test_stopped_exact_compat_update_preserves_all_other_bundle_bytes(self):
        with self._installed_fleet_fixture() as (args, roots, cfg):
            before = self._all_files(roots)
            old_manifest = json.loads(roots["manifest"].read_text())
            with mock.patch.object(svc, "_run", CmdRecorder()):
                rc, printed = _capture_stdout(lambda: svc.cmd_upgrade(args))
            self.assertEqual(rc, 0)
            result = json.loads(printed)
            self.assertEqual(result["effect"], "APPLIED")
            self.assertTrue(result["gatewayAndFleetModulesPreserved"])
            after = self._all_files(roots)
            changed = {
                name for name in before if before[name] != after[name]
            }
            self.assertEqual(
                changed, set(svc.FLEET_V10_PUBLISHER_PATCH_SHA256))
            manifest = svc._verify_staged_install(
                "chatgpt1", _label_for("chatgpt1"), roots)
            self.assertEqual(set(manifest["files"]), set(old_manifest["files"]))
            self.assertEqual(manifest["dependencyTreeHash"],
                             old_manifest["dependencyTreeHash"])
            after_cfg = json.loads(roots["config"].read_text())
            self.assertEqual(
                {k:v for k,v in after_cfg.items() if k != "gitPublish"},
                {k:v for k,v in cfg.items() if k != "gitPublish"})
            self.assertEqual(
                [v["repository"] for v in after_cfg["gitPublish"]["repositories"]],
                ["mastermind", "macro", "terminal"])
            self.assertNotIn("commission-prepare.mjs", after)
            self.assertNotIn("modern-fabric-http.mjs", after)

    def test_second_existing_enrolled_fleet_account_is_manifest_bound(self):
        with self._installed_fleet_fixture("chatgpt3") as (args, roots, before_cfg):
            before = self._all_files(roots)
            args.publisher_preflight_only = True
            with mock.patch.object(svc, "_run", CmdRecorder()):
                code, payload = _capture_stdout(lambda: svc.cmd_upgrade(args))
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(payload)["effect"], "NOT_APPLIED")
            args.publisher_preflight_only = False
            with mock.patch.object(svc, "_run", CmdRecorder()):
                code, output = _capture_stdout(lambda: svc.cmd_upgrade(args))
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output)["account"], "chatgpt3")
            self.assertEqual(
                {name for name in before if before[name] != (roots["base"] / name).read_bytes()},
                set(svc.FLEET_V10_PUBLISHER_PATCH_SHA256))
            cfg = json.loads(roots["config"].read_text())
            self.assertEqual(
                {k: v for k, v in cfg.items() if k != "gitPublish"},
                {k: v for k, v in before_cfg.items() if k != "gitPublish"})
            svc._verify_staged_install("chatgpt3", _label_for("chatgpt3"), roots)

    def test_exact_closed_v10_predecessor_may_receive_only_the_reviewed_module_patch(self):
        # The live ChatGPT1 seat can already contain #1535's closed publisher.
        # Do not treat that as a fresh grant or allow arbitrary closed versions.
        with self._installed_fleet_fixture() as (args, roots, _cfg):
            source = Path(args.source)
            prior_bytes = b"fixture reviewed closed publisher before await fix\n"
            (roots["base"] / "git-publish.mjs").write_bytes(prior_bytes)
            (roots["base"] / "workspace-access.mjs").write_bytes(
                (source / "workspace-access.mjs").read_bytes())
            cfg = json.loads(roots["config"].read_text())
            cfg["gitPublish"] = svc._typed_git_config(
                Path(os.environ["HOME"]), closed_repositories=True)
            roots["config"].write_text(
                json.dumps(cfg, indent=2, sort_keys=True), encoding="utf-8")
            manifest = json.loads(roots["manifest"].read_text())
            for name in svc.FLEET_V10_PUBLISHER_PATCH_SHA256:
                manifest["files"][name] = svc._sha256_file(roots["base"] / name)
            manifest["configHash"] = svc._sha256_file(roots["config"])
            roots["manifest"].write_text(
                json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
            args.publisher_expected_manifest_sha256 = svc._sha256_file(
                roots["manifest"])
            before = (roots["manifest"].read_bytes(), roots["config"].read_bytes(),
                      self._all_files(roots))
            exact_prior_sha = hashlib.sha256(prior_bytes).hexdigest()
            with mock.patch.object(svc, "FLEET_V10_PREVIOUS_CLOSED_PUBLISHER_SHA256", "0" * 64):
                with self.assertRaisesRegex(SystemExit, "unrecognized prior publisher identity"):
                    svc.cmd_upgrade(args)
            self.assertEqual(
                before, (roots["manifest"].read_bytes(),
                         roots["config"].read_bytes(), self._all_files(roots)),
                "foreign closed publishers must refuse before writing anything")
            with mock.patch.object(svc, "FLEET_V10_PREVIOUS_CLOSED_PUBLISHER_SHA256", exact_prior_sha):
                args.publisher_preflight_only = True
                with mock.patch.object(svc, "_run", CmdRecorder()):
                    code, receipt = _capture_stdout(lambda: svc.cmd_upgrade(args))
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(receipt)["effect"], "NOT_APPLIED")
                self.assertEqual(
                    before, (roots["manifest"].read_bytes(),
                             roots["config"].read_bytes(), self._all_files(roots)))
                args.publisher_preflight_only = False
                with mock.patch.object(svc, "_run", CmdRecorder()):
                    code, receipt = _capture_stdout(lambda: svc.cmd_upgrade(args))
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(receipt)["effect"], "APPLIED")
            self.assertEqual(roots["config"].read_bytes(), before[1],
                             "closed predecessor must not change grants or fleet controls")
            self.assertEqual(
                {name for name, old in before[2].items()
                 if (roots["base"] / name).read_bytes() != old},
                {"git-publish.mjs"}, "second stage changes only the publisher module")
            self.assertEqual(
                svc._sha256_file(roots["base"] / "git-publish.mjs"),
                svc.FLEET_V10_PUBLISHER_PATCH_SHA256["git-publish.mjs"])
            svc._verify_staged_install("chatgpt1", _label_for("chatgpt1"), roots)

    def test_non_enrolled_seats_refused_despite_fleet_file_similarity(self):
        with self._installed_fleet_fixture() as (args, roots, _cfg):
            before = (roots["manifest"].read_bytes(), self._all_files(roots))
            for account in ("chatgpt2-business", "chatgpt4", "admin-business"):
                args.account = account
                with self.assertRaisesRegex(SystemExit, "existing enrolled fleet owner"):
                    svc.cmd_upgrade(args)
            self.assertEqual(before, (
                roots["manifest"].read_bytes(), self._all_files(roots)))

    def test_wrong_cas_tamper_and_wrong_scope_fail_without_writes(self):
        with self._installed_fleet_fixture() as (args, roots, _cfg):
            before = (roots["manifest"].read_bytes(), self._all_files(roots))
            args.publisher_expected_manifest_sha256 = "b" * 64
            with self.assertRaisesRegex(SystemExit, "CAS mismatch"):
                svc.cmd_upgrade(args)
            args.publisher_expected_manifest_sha256 = svc._sha256_file(
                roots["manifest"])
            args.enable_repository_workspaces = True
            with self.assertRaisesRegex(SystemExit, "existing enrolled fleet owner"):
                svc.cmd_upgrade(args)
            args.enable_repository_workspaces = False
            old_source = svc.FLEET_V10_PRESERVED_GIT_BLOBS
            with mock.patch.object(svc, "FLEET_V10_PRESERVED_GIT_BLOBS",
                                   {**old_source, "gateway.mjs": "0" * 40}):
                with self.assertRaisesRegex(SystemExit, "generation changed"):
                    svc.cmd_upgrade(args)
            self.assertEqual(before, (
                roots["manifest"].read_bytes(), self._all_files(roots)))

    def test_write_failure_after_atomic_replace_does_not_claim_false_rollback(self):
        with self._installed_fleet_fixture() as (args, roots, _cfg):
            before = (
                roots["manifest"].read_bytes(), roots["config"].read_bytes(),
                self._all_files(roots),
            )
            real = svc._atomic_write_bytes
            fired = [False]
            def fail_after_replace(path, data, mode=svc.FILE_MODE):
                real(path, data, mode)
                if Path(path).name == "workspace-access.mjs" and not fired[0]:
                    fired[0] = True
                    raise OSError("simulated failure after atomic rename")
            with mock.patch.object(svc, "_run", CmdRecorder()), \
                 mock.patch.object(svc, "_atomic_write_bytes", fail_after_replace):
                with self.assertRaisesRegex(SystemExit, "NOT_APPLIED"):
                    svc.cmd_upgrade(args)
            self.assertTrue(fired[0])
            self.assertEqual(before, (
                roots["manifest"].read_bytes(), roots["config"].read_bytes(),
                self._all_files(roots),
            ))
            svc._verify_staged_install("chatgpt1", _label_for("chatgpt1"), roots)

    def test_changed_reviewed_source_refuses_before_any_installed_write(self):
        with self._installed_fleet_fixture() as (args, roots, _cfg):
            before = (roots["manifest"].read_bytes(), self._all_files(roots))
            incoming = Path(args.source) / "workspace-access.mjs"
            incoming.write_text("// unauthorized publisher module\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "source or installed module hash mismatch"):
                svc.cmd_upgrade(args)
            self.assertEqual(before, (
                roots["manifest"].read_bytes(), self._all_files(roots)))

    def test_rollback_write_failure_preserves_effect_unknown_and_never_replays(self):
        with self._installed_fleet_fixture() as (args, roots, _cfg):
            real = svc._atomic_write_bytes
            written = [0]
            def inject(path, data, mode=svc.FILE_MODE):
                if Path(path).name == "workspace-access.mjs":
                    raise OSError("second planned write refused")
                if Path(path).name == "git-publish.mjs":
                    written[0] += 1
                    if written[0] > 1:
                        raise OSError("rollback could not restore publisher")
                return real(path, data, mode)
            with mock.patch.object(svc, "_run", CmdRecorder()), \
                 mock.patch.object(svc, "_atomic_write_bytes", inject):
                with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                    svc.cmd_upgrade(args)
            self.assertEqual(written[0], 2)
            self.assertEqual(
                svc._sha256_file(roots["manifest"]),
                args.publisher_expected_manifest_sha256,
                "manifest not falsely committed after rollback failure")

    def test_precommit_write_failure_restores_original_bytes(self):
        with self._installed_fleet_fixture() as (args, roots, _cfg):
            before = (
                roots["manifest"].read_bytes(), roots["config"].read_bytes(),
                self._all_files(roots),
            )
            real = svc._atomic_write_bytes
            failed = [False]
            def inject(path, data, mode=svc.FILE_MODE):
                if Path(path).name == "workspace-access.mjs" and not failed[0]:
                    failed[0] = True
                    raise OSError("simulated second-write failure")
                return real(path, data, mode)
            with mock.patch.object(svc, "_run", CmdRecorder()), \
                 mock.patch.object(svc, "_atomic_write_bytes", inject):
                with self.assertRaisesRegex(SystemExit, "NOT_APPLIED"):
                    svc.cmd_upgrade(args)
            self.assertTrue(failed[0])
            self.assertEqual(before, (
                roots["manifest"].read_bytes(), roots["config"].read_bytes(),
                self._all_files(roots),
            ))
            svc._verify_staged_install(
                "chatgpt1", _label_for("chatgpt1"), roots)

class TestC2PaperRuntimeCompatibility(unittest.TestCase):
    """Real installer checks over isolated, sealed data fixtures; no live effects."""

    @staticmethod
    def _absent_result():
        return FakeResult(113, "", (
            f'Bad request.\nCould not find service "{_label_for(svc.C2_PAPER_ACCOUNT)}" '
            f'in domain for user gui: {os.getuid()}\n'))

    def _unloaded_recorder(self, handler=None):
        return CmdRecorder(handler=handler, default=self._absent_result())

    @contextmanager
    def _installed_c2_fixture(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                account = svc.C2_PAPER_ACCOUNT
                _do_stage(tmp, home, account=account, port=45026)
                roots = svc._build_runtime_roots(account)
                _seed_node_modules(roots)
                names = frozenset(svc.C2_PAPER_FILES_SHA256)
                for name in set(svc.STAGE_FILES) - names:
                    (roots["base"] / name).unlink()
                for name in names - set(svc.STAGE_FILES):
                    path = roots["base"] / name
                    path.write_text(f"// fixture C2 fleet {name}\n", encoding="utf-8")
                    path.chmod(svc.FILE_MODE)
                cfg = json.loads(roots["config"].read_text())
                runtime_v10 = home / ".local/share/mastermind-paper/runtime/v10"
                cfg["paperDesign"].update({
                    "pythonPath": str(runtime_v10 / "venv/bin/python"),
                    "bridgePath": str(runtime_v10 / "source/bridge.py"),
                    "bridgeSha256": svc.C2_PAPER_ORIGINAL_BRIDGE_SHA256,
                })
                cfg["fleetRouting"] = {
                    "enabled": True, "requestTimeoutMs": svc.REQUEST_TIMEOUT_MS,
                    "routes": [
                        {"hostRef": name, "url": f"https://{name}.example.ts.net/mcp"}
                        for name in ("mini3", "mini4")
                    ],
                }
                cfg["maxPerSessionConcurrency"] = 8
                cfg["maxQueuedPerSession"] = 16
                cfg["fleetStatus"] = {
                    "enabled": True, "launcherPath": str(home / ".local/bin/studio-direct"),
                    "launcherSha256": "a" * 64, "timeoutMs": 15000,
                }
                # Non-ASCII fixture proves the reviewed default JSON encoding is used.
                cfg["fixturePreserved"] = {"label": "caf\u00e9", "nested": [False, None, 7]}
                roots["config"].write_text(json.dumps(cfg, indent=2, sort_keys=True))
                prior = json.loads(roots["manifest"].read_text())
                prior["files"] = {
                    name: svc._sha256_file(roots["base"] / name) for name in sorted(names)
                }
                prior["configHash"] = svc._sha256_file(roots["config"])
                prior["dependencyTreeHash"] = svc._dependency_tree_hash(roots["node_modules"])
                roots["manifest"].write_text(json.dumps(prior, indent=2, sort_keys=True))
                original_sha = svc._sha256_file(roots["manifest"])
                non_paper_sha = hashlib.sha256(json.dumps(
                    {k: v for k, v in cfg.items() if k != "paperDesign"},
                    sort_keys=True, separators=(",", ":"),
                ).encode()).hexdigest()
                identity = {key: prior[key] for key in svc.C2_PAPER_RUNTIME_IDENTITY}
                target_config = {**cfg, "paperDesign": {
                    **svc._paper_design_config(home), "bridgeSha256": PAPER_BRIDGE_FIXTURE_SHA,
                }}
                future = {**prior, "configHash": hashlib.sha256(json.dumps(
                    target_config, indent=2, sort_keys=True,
                ).encode()).hexdigest()}
                canonical_pins = frozenset(svc._canonical_json_sha256(value)
                                           for value in (prior, future))
                # Only fixture identity data are replaced. All admission, runtime,
                # hash, config, transaction and rollback checks execute unchanged.
                with mock.patch.multiple(
                    svc, C2_PAPER_FILES_SHA256=prior["files"],
                    C2_PAPER_RUNTIME_IDENTITY=identity,
                    C2_PAPER_ORIGINAL_MANIFEST_SHA256=original_sha,
                    C2_PAPER_MANIFEST_CANONICAL_SHA256=canonical_pins,
                    C2_PAPER_NON_PAPER_CONFIG_SHA256=non_paper_sha,
                    PAPER_BRIDGE_SHA256=PAPER_BRIDGE_FIXTURE_SHA,
                ):
                    with svc._c2_lifecycle_mutex(account):
                        pass
                    svc._verify_staged_install(account, _label_for(account), roots)
                    args = svc.build_parser().parse_args([
                        "paper-runtime-upgrade", "--account", account,
                        "--expected-manifest-sha256", original_sha,
                    ])
                    args._fixture_target_manifest = future
                    yield args, roots, cfg

    @staticmethod
    def _snapshot(roots):
        files = {
            str(path.relative_to(roots["base"])): path.read_bytes()
            for path in roots["base"].rglob("*") if path.is_file()
        }
        files["@plist"] = roots["plist"].read_bytes()
        return files

    def _assert_no_writes(self, args, roots, message):
        before = self._snapshot(roots)
        recorder = self._unloaded_recorder()
        with mock.patch.object(svc, "_atomic_write_bytes") as write, \
             mock.patch.object(svc, "_run", recorder):
            with self.assertRaisesRegex(SystemExit, message):
                svc.cmd_paper_runtime_upgrade(args)
            write.assert_not_called()
        self.assertEqual(before, self._snapshot(roots))
        self.assertTrue(all(c[:2] == ["launchctl", "print"] for c in recorder.calls))

    def test_exact_cohort_admission_is_account_version_identity_and_digest_bound(self):
        with self._installed_c2_fixture() as (args, roots, _):
            prior = json.loads(roots["manifest"].read_text())
            label = _label_for(args.account)
            self.assertTrue(svc._valid_manifest(prior, args.account, label))
            variants = {
                "one module digest": {**prior, "files": {**prior["files"], "gateway.mjs": "0" * 64}},
                "missing module": {**prior, "files": {k: v for k, v in prior["files"].items() if k != "tailnet-gateway.mjs"}},
                "extra module": {**prior, "files": {**prior["files"], "unexpected.mjs": "a" * 64}},
                "unsealed dependencies": {**prior, "dependencyTreeHash": None},
                "legacy version": {k: v for k, v in {**prior, "version": 1}.items()
                                   if k not in ("nodeHash", "backendHash", "dependencyTreeHash")},
            }
            for key in svc.C2_PAPER_RUNTIME_IDENTITY:
                variants[key] = {**prior, key: 45027 if key == "port" else "0" * 64}
            for name, candidate in variants.items():
                with self.subTest(name=name):
                    self.assertFalse(svc._valid_manifest(candidate, args.account, label))
            foreign = {**prior, "account": "chatgpt4", "label": _label_for("chatgpt4")}
            self.assertFalse(svc._valid_manifest(foreign, "chatgpt4", foreign["label"]))
            # Only the reviewed target configHash transition stays admitted.
            self.assertTrue(svc._valid_manifest(
                args._fixture_target_manifest, args.account, label))
            self.assertFalse(svc._valid_manifest(
                {**prior, "configHash": "b" * 64}, args.account, label))

    def test_readonly_preflight_while_loaded_has_no_service_or_file_effect(self):
        with self._installed_c2_fixture() as (args, roots, _):
            lock_path = roots["state"] / svc.C2_LIFECYCLE_LOCK_NAME
            lock_path.unlink()  # Fixture-only: prove preflight does not create a lock.
            before = self._snapshot(roots)
            args.preflight_only = True
            live = CmdRecorder(default=FakeResult(0, _print_running(
                str(roots["plist"]), _label_for(args.account))))
            with mock.patch.object(svc, "_run", live), \
                 mock.patch.object(svc, "_c2_lifecycle_mutex") as mutex, \
                 mock.patch.object(svc, "_atomic_write_bytes") as write:
                rc, output = _capture_stdout(lambda: svc.cmd_paper_runtime_upgrade(args))
                write.assert_not_called()
                mutex.assert_not_called()
            result = json.loads(output)
            self.assertEqual((rc, result["effect"], result["preflight"]), (0, "NOT_APPLIED", True))
            self.assertEqual(result["originalManifestSha256"], args.expected_manifest_sha256)
            self.assertNotEqual(result["targetManifestSha256"], args.expected_manifest_sha256)
            self.assertEqual(result["preservedGatewayFiles"], 11)
            self.assertFalse(result["serviceStarted"])
            self.assertEqual(before, self._snapshot(roots))
            self.assertFalse(lock_path.exists())
            self.assertTrue(all(c[:2] == ["launchctl", "print"] for c in live.calls))

    def test_stopped_apply_changes_only_paper_and_config_hash_then_normal_admission_works(self):
        with self._installed_c2_fixture() as (args, roots, cfg):
            before = self._snapshot(roots)
            prior = json.loads(roots["manifest"].read_text())
            recorder = self._unloaded_recorder()
            with mock.patch.object(svc, "_run", recorder):
                rc, output = _capture_stdout(lambda: svc.cmd_paper_runtime_upgrade(args))
                status_rc, status = _capture_stdout(lambda: svc.cmd_status(args))
            receipt = json.loads(output)
            self.assertEqual((rc, receipt["effect"]), (0, "APPLIED"))
            self.assertEqual(status_rc, 0)
            self.assertEqual(json.loads(status)["port"], 45026)
            self.assertFalse(json.loads(status)["loaded"])
            after = self._snapshot(roots)
            self.assertEqual(set(before), set(after))
            self.assertEqual({name for name in before if before[name] != after[name]},
                             {"config.json", "manifest.json"})
            new_cfg = json.loads(roots["config"].read_text())
            self.assertEqual({k: v for k, v in new_cfg.items() if k != "paperDesign"},
                             {k: v for k, v in cfg.items() if k != "paperDesign"})
            self.assertEqual({k for k in cfg["paperDesign"]
                              if cfg["paperDesign"][k] != new_cfg["paperDesign"][k]},
                             {"pythonPath", "bridgePath", "bridgeSha256"})
            installed = svc._verify_staged_install(args.account, _label_for(args.account), roots)
            self.assertEqual({k: v for k, v in installed.items() if k != "configHash"},
                             {k: v for k, v in prior.items() if k != "configHash"})
            self.assertEqual(svc._sha256_file(roots["manifest"]), receipt["targetManifestSha256"])
            self.assertTrue(all(c[:2] == ["launchctl", "print"] for c in recorder.calls))
            self._assert_no_writes(args, roots, "CAS mismatch")

    def test_cli_exposes_only_fixed_scope_and_required_manifest_cas(self):
        parser = svc.build_parser()
        base = ["paper-runtime-upgrade", "--account", svc.C2_PAPER_ACCOUNT,
                "--expected-manifest-sha256", "a" * 64]
        self.assertIs(parser.parse_args(base).func, svc.cmd_paper_runtime_upgrade)
        for extra in (["--source", "/tmp/source"], ["--runtime", "v12"],
                      ["--node", "/tmp/node"], ["--enable-repository-workspaces"]):
            with self.subTest(extra=extra), mock.patch("sys.stderr", io.StringIO()):
                with self.assertRaises(SystemExit):
                    parser.parse_args(base + extra)
        with mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(base[:3])

    def test_other_account_and_unreviewed_cas_cannot_enroll(self):
        with self._installed_c2_fixture() as (args, roots, _):
            args.account = "chatgpt1"
            self._assert_no_writes(args, roots, "exact enrolled C2")
            args.account = svc.C2_PAPER_ACCOUNT
            for value in ("", "garbage", "b" * 64):
                with self.subTest(value=value):
                    args.expected_manifest_sha256 = value
                    self._assert_no_writes(args, roots, "manifest CAS|reviewed predecessor")

    def test_every_gateway_module_and_runtime_seal_is_verified_before_writes(self):
        with self._installed_c2_fixture() as (args, roots, _):
            manifest = json.loads(roots["manifest"].read_text())
            paths = [roots["base"] / name for name in manifest["files"]]
            paths += [Path(manifest["node"]), Path(manifest["backend"]),
                      roots["node_modules"] / "fixture-package/index.js", roots["plist"]]
            for path in paths:
                with self.subTest(path=path.name):
                    before = path.read_bytes()
                    try:
                        path.write_bytes(before + b"tampered\n")
                        self._assert_no_writes(args, roots, "hash mismatch")
                    finally:
                        path.write_bytes(before)

    def test_self_consistent_profile_or_original_paper_changes_are_still_refused(self):
        for field in ("fleetRouting", "paperDesign"):
            with self.subTest(field=field), self._installed_c2_fixture() as (args, roots, cfg):
                if field == "fleetRouting":
                    cfg[field]["routes"].pop()
                    message = "non-Paper profile changed"
                else:
                    cfg[field]["commandTimeoutMs"] += 1
                    message = "not exact v10"
                roots["config"].write_text(json.dumps(cfg, sort_keys=True))
                manifest = json.loads(roots["manifest"].read_text())
                manifest["configHash"] = svc._sha256_file(roots["config"])
                roots["manifest"].write_text(json.dumps(manifest, sort_keys=True))
                args.expected_manifest_sha256 = svc._sha256_file(roots["manifest"])
                # Isolate the additional semantic pin beyond the original snapshot CAS.
                with mock.patch.object(svc, "C2_PAPER_ORIGINAL_MANIFEST_SHA256",
                                       args.expected_manifest_sha256), \
                     mock.patch.object(svc, "C2_PAPER_MANIFEST_CANONICAL_SHA256",
                                       svc.C2_PAPER_MANIFEST_CANONICAL_SHA256
                                       | {svc._canonical_json_sha256(manifest)}):
                    self._assert_no_writes(args, roots, message)

    def test_target_runtime_receipt_bridge_and_python_are_verified(self):
        for fault in ("missing bridge", "changed bridge", "wrong receipt", "symlink python"):
            with self.subTest(fault=fault), self._installed_c2_fixture() as (args, roots, _):
                runtime = svc._user_root() / svc.PAPER_RUNTIME_REL
                bridge = runtime / "source/bridge.py"
                if fault == "missing bridge":
                    bridge.unlink()
                elif fault == "changed bridge":
                    bridge.write_bytes(b"different bridge\n")
                elif fault == "wrong receipt":
                    receipt_path = runtime / "RUNTIME.json"
                    receipt = json.loads(receipt_path.read_text())
                    receipt["generation"] = "v10"
                    receipt_path.write_text(json.dumps(receipt))
                else:
                    python = runtime / "venv/bin/python"
                    python.unlink()
                    python.symlink_to(sys.executable)
                self._assert_no_writes(args, roots, "paper .*missing or unsafe|paper bridge hash|receipt")

    def test_running_or_crashed_loaded_service_refuses_without_writes(self):
        for state in (_print_running, _print_crashed):
            with self.subTest(state=state.__name__), self._installed_c2_fixture() as (args, roots, _):
                before = self._snapshot(roots)
                rec = CmdRecorder(default=FakeResult(0, state(str(roots["plist"]), _label_for(args.account))))
                with mock.patch.object(svc, "_run", rec), \
                     mock.patch.object(svc, "_atomic_write_bytes") as write:
                    with self.assertRaisesRegex(SystemExit, "while service is loaded"):
                        svc.cmd_paper_runtime_upgrade(args)
                    write.assert_not_called()
                self.assertEqual(before, self._snapshot(roots))
                self.assertTrue(all(c[:2] == ["launchctl", "print"] for c in rec.calls))

    def test_generic_full_upgrade_and_restage_refuse_exact_c2_cohort_without_writes(self):
        with self._installed_c2_fixture() as (args, roots, _):
            prior = json.loads(roots["manifest"].read_text())
            generic = _stage_args(Path(prior["source"]), Path(prior["node"]),
                                  Path(prior["backend"]), args.account, prior["port"])
            for operation, message in ((svc.cmd_upgrade, "fleet/tailnet capability modules absent"),
                                       (svc.cmd_stage, "refusing|upgrade")):
                with self.subTest(operation=operation.__name__):
                    before = self._snapshot(roots)
                    with mock.patch.object(svc, "_run", self._unloaded_recorder()), \
                         mock.patch.object(svc, "_atomic_write_bytes") as write:
                        with self.assertRaisesRegex(SystemExit, message):
                            operation(generic)
                        write.assert_not_called()
                    self.assertEqual(before, self._snapshot(roots))

    def test_manifest_cas_drift_after_final_runtime_check_refuses_before_write(self):
        with self._installed_c2_fixture() as (args, roots, _):
            before = roots["manifest"].read_bytes()
            verify = svc._verify_paper_runtime
            calls = []
            def inject(*pos, **kw):
                result = verify(*pos, **kw)
                calls.append(1)
                if len(calls) == 2:
                    roots["manifest"].write_bytes(before + b"\n")
                return result
            with mock.patch.object(svc, "_run", self._unloaded_recorder()), \
                 mock.patch.object(svc, "_verify_paper_runtime", inject), \
                 mock.patch.object(svc, "_atomic_write_bytes") as write:
                with self.assertRaisesRegex(SystemExit, "snapshot CAS mismatch"):
                    svc.cmd_paper_runtime_upgrade(args)
                write.assert_not_called()
            self.assertEqual(roots["manifest"].read_bytes(), before + b"\n")

    def test_failures_before_or_after_atomic_replace_restore_exact_original_bytes(self):
        for filename in ("config.json", "manifest.json"):
            for after_replace in (False, True):
                with self.subTest(filename=filename, after_replace=after_replace), \
                     self._installed_c2_fixture() as (args, roots, _):
                    before = self._snapshot(roots)
                    real = svc._atomic_write_bytes
                    fired = []
                    def inject(path, data, mode=svc.FILE_MODE):
                        if Path(path).name == filename and not fired:
                            fired.append(1)
                            if after_replace:
                                real(path, data, mode)
                            raise OSError("fixture atomic write failure")
                        return real(path, data, mode)
                    with mock.patch.object(svc, "_run", self._unloaded_recorder()), \
                         mock.patch.object(svc, "_atomic_write_bytes", inject):
                        with self.assertRaisesRegex(SystemExit, "NOT_APPLIED; original state restored"):
                            svc.cmd_paper_runtime_upgrade(args)
                    self.assertTrue(fired)
                    self.assertEqual(before, self._snapshot(roots))
                    svc._verify_staged_install(args.account, _label_for(args.account), roots)

    def test_foreign_bytes_after_first_write_are_not_overwritten_by_rollback(self):
        for target in ("config", "manifest"):
            with self.subTest(target=target), self._installed_c2_fixture() as (args, roots, _):
                real = svc._atomic_write_bytes
                writes = []
                foreign = b'{"concurrentOwner":true}\n'
                def inject(path, data, mode=svc.FILE_MODE):
                    writes.append(Path(path).name)
                    real(path, data, mode)
                    roots[target].write_bytes(foreign)
                    raise OSError("concurrent mutation observed after config replacement")
                with mock.patch.object(svc, "_run", self._unloaded_recorder()), \
                     mock.patch.object(svc, "_atomic_write_bytes", inject):
                    with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN during rollback"):
                        svc.cmd_paper_runtime_upgrade(args)
                self.assertEqual(roots[target].read_bytes(), foreign)
                self.assertEqual(writes, ["config.json"])

    def test_service_loaded_before_commit_produces_unknown_and_no_service_mutation(self):
        with self._installed_c2_fixture() as (args, roots, _):
            before_manifest = roots["manifest"].read_bytes()
            real = svc._atomic_write_bytes
            writes = []
            def inject(path, data, mode=svc.FILE_MODE):
                writes.append(Path(path).name)
                return real(path, data, mode)
            inspections = iter((None, None, {"running": True}, {"running": True}))
            with mock.patch.object(svc, "_lifecycle_inspect", side_effect=lambda *_: next(inspections)), \
                 mock.patch.object(svc, "_atomic_write_bytes", inject), \
                 mock.patch.object(svc, "_run") as run:
                with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN during rollback"):
                    svc.cmd_paper_runtime_upgrade(args)
                run.assert_not_called()
            self.assertEqual(writes, ["config.json"])
            self.assertEqual(roots["manifest"].read_bytes(), before_manifest)

    def test_rollback_failure_keeps_unknown_and_never_replays(self):
        with self._installed_c2_fixture() as (args, roots, _):
            before_manifest = roots["manifest"].read_bytes()
            real = svc._atomic_write_bytes
            writes = []
            def inject(path, data, mode=svc.FILE_MODE):
                writes.append(Path(path).name)
                if len(writes) > 1:
                    raise OSError("fixture manifest and rollback writes refused")
                return real(path, data, mode)
            with mock.patch.object(svc, "_run", self._unloaded_recorder()), \
                 mock.patch.object(svc, "_atomic_write_bytes", inject):
                with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN during rollback"):
                    svc.cmd_paper_runtime_upgrade(args)
            self.assertEqual(writes, ["config.json", "manifest.json", "config.json"])
            self.assertEqual(roots["manifest"].read_bytes(), before_manifest)

    def test_postcommit_verification_failure_never_claims_no_effect_or_rolls_back(self):
        with self._installed_c2_fixture() as (args, roots, _):
            before_manifest = roots["manifest"].read_bytes()
            real_verify = svc._verify_staged_install
            real_write = svc._atomic_write_bytes
            reads, writes = [], []
            def verify(*pos, **kw):
                reads.append(1)
                if len(reads) == 3:
                    raise SystemExit("fixture postcommit verification failure")
                return real_verify(*pos, **kw)
            def write(path, data, mode=svc.FILE_MODE):
                writes.append(Path(path).name)
                return real_write(path, data, mode)
            with mock.patch.object(svc, "_run", self._unloaded_recorder()), \
                 mock.patch.object(svc, "_verify_staged_install", verify), \
                 mock.patch.object(svc, "_atomic_write_bytes", write):
                with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN after manifest commit"):
                    svc.cmd_paper_runtime_upgrade(args)
            self.assertEqual(writes, ["config.json", "manifest.json"])
            self.assertNotEqual(roots["manifest"].read_bytes(), before_manifest)

    def test_same_binary_profile_or_source_change_cannot_enter_generic_start(self):
        for change in ("repositoryWorkspaces", "commissionPublication", "fabricOnly", "fleetRouting", "source"):
            with self.subTest(change=change), self._installed_c2_fixture() as (args, roots, cfg):
                manifest = json.loads(roots["manifest"].read_text())
                if change == "source":
                    manifest["source"] += "-different-owner"
                else:
                    cfg[change] = {"enabled": True} if change != "fabricOnly" else True
                    roots["config"].write_text(json.dumps(cfg, sort_keys=True))
                    manifest["configHash"] = svc._sha256_file(roots["config"])
                roots["manifest"].write_text(json.dumps(manifest, sort_keys=True))
                self.assertFalse(svc._valid_manifest(manifest, args.account, _label_for(args.account)))
                before = self._snapshot(roots)
                with mock.patch.object(svc, "_run") as run, \
                     mock.patch.object(svc, "_atomic_write_bytes") as write:
                    with self.assertRaisesRegex(SystemExit, "corrupt manifest"):
                        svc.cmd_start(args)
                    run.assert_not_called()
                    write.assert_not_called()
                self.assertEqual(before, self._snapshot(roots))

    def test_unactivated_v11_successor_cannot_enter_generic_start(self):
        with self._installed_c2_fixture() as (args, roots, cfg):
            manifest = json.loads(roots["manifest"].read_text())
            prior_runtime = svc._user_root() / ".local/share/mastermind-paper/runtime/v11"
            cfg["paperDesign"] = {
                **svc._paper_design_config(svc._user_root()),
                "pythonPath": str(prior_runtime / "venv/bin/python"),
                "bridgePath": str(prior_runtime / "source/bridge.py"),
                "bridgeSha256": "6d28be62b21bff12dc04ae1bdc50f12a4ff55fdb8261bdd6923bac2804fecf7c",
            }
            roots["config"].write_text(json.dumps(cfg, indent=2, sort_keys=True))
            manifest["configHash"] = svc._sha256_file(roots["config"])
            roots["manifest"].write_text(json.dumps(manifest, indent=2, sort_keys=True))
            self.assertFalse(svc._valid_manifest(manifest, args.account, _label_for(args.account)))
            before = self._snapshot(roots)
            with mock.patch.object(svc, "_run") as run, \
                 mock.patch.object(svc, "_atomic_write_bytes") as write:
                with self.assertRaisesRegex(SystemExit, "corrupt manifest"):
                    svc.cmd_start(args)
                run.assert_not_called()
                write.assert_not_called()
            self.assertEqual(before, self._snapshot(roots))

    def test_canonical_admission_preserves_original_and_target_lifecycle(self):
        with self._installed_c2_fixture() as (args, roots, _):
            original = json.loads(roots["manifest"].read_text())
            original_bytes = roots["manifest"].read_bytes()
            roots["manifest"].write_text(json.dumps(original, separators=(",", ":")))
            self.assertEqual(svc._verify_staged_install(
                args.account, _label_for(args.account), roots), original)
            roots["manifest"].write_bytes(original_bytes)
            with mock.patch.object(svc, "_run", self._unloaded_recorder()):
                _capture_stdout(lambda: svc.cmd_paper_runtime_upgrade(args))
            self.assertEqual(svc._verify_staged_install(
                args.account, _label_for(args.account), roots), args._fixture_target_manifest)
            before = self._snapshot(roots)
            recorder = self._unloaded_recorder(handler=lambda cmd: FakeResult(0)
                if cmd[:2] == ["launchctl", "bootstrap"] else None)
            with mock.patch.object(svc, "_run", recorder):
                rc, output = _capture_stdout(lambda: svc.cmd_start(args))
            self.assertEqual(rc, 0)
            self.assertTrue(json.loads(output)["started"])
            self.assertEqual([cmd[1] for cmd in recorder.calls], ["print", "bootstrap"])
            self.assertEqual(before, self._snapshot(roots))

    def test_persistent_private_mutex_conflicts_before_all_four_mutating_commands(self):
        with self._installed_c2_fixture() as (args, roots, _):
            lock = roots["state"] / svc.C2_LIFECYCLE_LOCK_NAME
            lock.unlink()  # Fixture-only first-creation case.
            before = self._snapshot(roots)
            with svc._c2_lifecycle_mutex(args.account):
                identity = lock.stat()
                self.assertEqual(stat.S_IMODE(identity.st_mode), 0o600)
                self.assertEqual(identity.st_uid, os.getuid())
                self.assertEqual((identity.st_nlink, identity.st_size), (1, 0))
                with mock.patch.object(svc, "_run") as run, \
                     mock.patch.object(svc, "_atomic_write_bytes") as write:
                    for operation in (svc.cmd_paper_runtime_upgrade, svc.cmd_start,
                                      svc.cmd_stop, svc.cmd_seal_runtime):
                        with self.subTest(operation=operation.__name__):
                            with self.assertRaisesRegex(SystemExit, "lifecycle mutation already in progress"):
                                operation(args)
                    run.assert_not_called()
                    write.assert_not_called()
            self.assertEqual(lock.stat().st_ino, identity.st_ino)
            after = self._snapshot(roots)
            added = str(lock.relative_to(roots["base"]))
            self.assertEqual(after, {**before, added: b""})
            with self.assertRaisesRegex(RuntimeError, "fixture exit"):
                with svc._c2_lifecycle_mutex(args.account):
                    raise RuntimeError("fixture exit")
            with svc._c2_lifecycle_mutex(args.account):
                self.assertEqual(lock.stat().st_ino, identity.st_ino)

    def test_preflight_bypasses_contended_mutex_without_writes(self):
        with self._installed_c2_fixture() as (args, roots, _):
            args.preflight_only = True
            before = self._snapshot(roots)
            with svc._c2_lifecycle_mutex(args.account), \
                 mock.patch.object(svc, "_run") as run, \
                 mock.patch.object(svc, "_atomic_write_bytes") as write:
                rc, output = _capture_stdout(lambda: svc.cmd_paper_runtime_upgrade(args))
                run.assert_not_called()
                write.assert_not_called()
            self.assertEqual((rc, json.loads(output)["effect"]), (0, "NOT_APPLIED"))
            self.assertEqual(before, self._snapshot(roots))

    def test_mutex_rejects_unsafe_inode_parent_and_ownership(self):
        for fault in ("symlink", "parent symlink", "public mode", "hardlink", "directory", "owner"):
            with self.subTest(fault=fault), self._installed_c2_fixture() as (args, roots, _):
                lock = roots["state"] / svc.C2_LIFECYCLE_LOCK_NAME
                if fault == "symlink":
                    target = roots["state"] / "fixture-lock-target"
                    lock.rename(target)
                    lock.symlink_to(target)
                elif fault == "parent symlink":
                    target = roots["base"] / "fixture-state"
                    roots["state"].rename(target)
                    roots["state"].symlink_to(target)
                elif fault == "public mode":
                    lock.chmod(0o644)
                elif fault == "hardlink":
                    os.link(lock, roots["state"] / "fixture-lock-link")
                elif fault == "directory":
                    lock.unlink()
                    lock.mkdir(mode=0o700)
                real_fstat = os.fstat
                def ownership(fd):
                    values = list(real_fstat(fd))
                    if fault == "owner":
                        values[4] = os.getuid() + 1
                    return os.stat_result(values)
                with mock.patch.object(svc.os, "fstat", ownership):
                    self._assert_no_writes(args, roots, "symlink|lifecycle lock")

    def test_mutex_detects_replacement_between_open_and_acquisition(self):
        with self._installed_c2_fixture() as (args, roots, _):
            lock = roots["state"] / svc.C2_LIFECYCLE_LOCK_NAME
            old_inode = lock.stat().st_ino
            real_flock = svc.fcntl.flock
            def replace(fd, operation):
                self.assertFalse(os.get_inheritable(fd))
                lock.rename(lock.with_name("fixture-prior-lock"))
                lock.write_bytes(b"")
                lock.chmod(0o600)
                return real_flock(fd, operation)
            with mock.patch.object(svc.fcntl, "flock", replace), \
                 mock.patch.object(svc, "_atomic_write_bytes") as write, \
                 mock.patch.object(svc, "_run") as run:
                with self.assertRaisesRegex(SystemExit, "inode is unsafe or changed"):
                    svc.cmd_paper_runtime_upgrade(args)
                write.assert_not_called()
                run.assert_not_called()
            self.assertNotEqual(lock.stat().st_ino, old_inode)

    def test_start_holds_mutex_from_verification_through_bootstrap_or_kickstart(self):
        for action in ("bootstrap", "kickstart"):
            with self.subTest(action=action), self._installed_c2_fixture() as (args, roots, _):
                before = self._snapshot(roots)
                checkpoints = []
                real_verify = svc._verify_staged_install
                def contend(checkpoint):
                    with self.assertRaisesRegex(SystemExit, "lifecycle mutation already in progress"):
                        svc.cmd_paper_runtime_upgrade(args)
                    checkpoints.append(checkpoint)
                def verify(*pos, **kw):
                    result = real_verify(*pos, **kw)
                    contend("verified")
                    return result
                def handle(cmd):
                    if cmd[:2] == ["launchctl", action]:
                        contend(action)
                        return FakeResult(0)
                    if action == "kickstart" and cmd[:2] == ["launchctl", "print"]:
                        return FakeResult(0, _print_crashed(str(roots["plist"]), _label_for(args.account)))
                    return None
                with mock.patch.object(svc, "_verify_staged_install", verify), \
                     mock.patch.object(svc, "_run", self._unloaded_recorder(handle)):
                    rc, _ = _capture_stdout(lambda: svc.cmd_start(args))
                self.assertEqual(rc, 0)
                self.assertEqual(checkpoints, ["verified", action])
                self.assertEqual(before, self._snapshot(roots))

    def test_apply_and_rollback_hold_mutex_against_concurrent_start(self):
        with self._installed_c2_fixture() as (args, roots, _):
            before = self._snapshot(roots)
            real_write = svc._atomic_write_bytes
            checkpoints = []
            def inject(path, data, mode=svc.FILE_MODE):
                if Path(path) == roots["manifest"]:
                    raise OSError("fixture manifest failure")
                with self.assertRaisesRegex(SystemExit, "lifecycle mutation already in progress"):
                    svc.cmd_start(args)
                checkpoints.append(Path(path).name)
                return real_write(path, data, mode)
            with mock.patch.object(svc, "_run", self._unloaded_recorder()), \
                 mock.patch.object(svc, "_atomic_write_bytes", inject):
                with self.assertRaisesRegex(SystemExit, "NOT_APPLIED; original state restored"):
                    svc.cmd_paper_runtime_upgrade(args)
            self.assertEqual(checkpoints, ["config.json", "config.json"])
            self.assertEqual(before, self._snapshot(roots))

    def test_stop_and_seal_hold_mutex_through_their_effects(self):
        for operation in (svc.cmd_stop, svc.cmd_seal_runtime):
            with self.subTest(operation=operation.__name__), self._installed_c2_fixture() as (args, roots, _):
                checkpoints = []
                real_write = svc._atomic_write_bytes
                stopped = []
                def contend():
                    with self.assertRaisesRegex(SystemExit, "lifecycle mutation already in progress"):
                        svc.cmd_start(args)
                    checkpoints.append(1)
                def write(path, data, mode=svc.FILE_MODE):
                    contend()
                    return real_write(path, data, mode)
                def handle(cmd):
                    if cmd[:2] == ["launchctl", "bootout"]:
                        contend()
                        stopped.append(1)
                        return FakeResult(0)
                    if operation is svc.cmd_stop and not stopped:
                        return FakeResult(0, _print_running(str(roots["plist"]), _label_for(args.account)))
                    return None
                with mock.patch.object(svc, "_run", self._unloaded_recorder(handle)), \
                     mock.patch.object(svc, "_atomic_write_bytes", write):
                    rc, _ = _capture_stdout(lambda: operation(args))
                self.assertEqual((rc, len(checkpoints)), (0, 1))

    def test_strict_inspection_accepts_exact_absence_and_nested_coalition_output(self):
        with self._installed_c2_fixture() as (args, roots, _):
            label = _label_for(args.account)
            output = _print_running(str(roots["plist"]), label)
            output = output[:-2] + (
                "\tresource coalition = {\n\t\tid = 41\n\t\tstate = active\n\t}\n"
                "\tjetsam coalition = {\n\t\tid = 42\n\t\tstate = active\n\t}\n}\n")
            recorder = CmdRecorder(default=FakeResult(0, output))
            with mock.patch.object(svc, "_run", recorder):
                result = svc._lifecycle_inspect(args.account, label, roots)
            self.assertEqual(result, {"state": "running", "pid": 4321, "path": str(roots["plist"])})
            self.assertEqual(recorder.calls, [["launchctl", "print", f"gui/{os.getuid()}/{label}"]])
            with mock.patch.object(svc, "_run", self._unloaded_recorder()):
                self.assertIsNone(svc._lifecycle_inspect(args.account, label, roots))

    def test_strict_inspection_rejects_unknown_errors_wrong_identity_and_top_level_duplicates(self):
        with self._installed_c2_fixture() as (args, roots, _):
            label = _label_for(args.account)
            running = _print_running(str(roots["plist"]), label)
            absent = self._absent_result()
            cases = {
                "legacy ambiguous absence": FakeResult(1, "", "not loaded"),
                "wrong code": FakeResult(1, "", absent.stderr),
                "unexpected stdout": FakeResult(113, "unknown\n", absent.stderr),
                "wrong label": FakeResult(113, "", absent.stderr.replace(label, label + "-other")),
                "wrong uid": FakeResult(113, "", absent.stderr.replace(f"gui: {os.getuid()}", f"gui: {os.getuid() + 1}")),
                "domain failure": FakeResult(113, "", "Could not find domain for user gui\n"),
                "empty success": FakeResult(0),
                "warning on success": FakeResult(0, running, "unexpected warning"),
                "wrong target header": FakeResult(0, running.replace(f"/{label} =", "/other =")),
                "wrong plist": FakeResult(0, running.replace(str(roots["plist"]), "/tmp/foreign.plist")),
                "duplicate state": FakeResult(0, running.replace("\tstate = running\n", "\tstate = running\n\tstate = waiting\n")),
                "malformed pid": FakeResult(0, running.replace("pid = 4321", "pid = invalid")),
                "missing state": FakeResult(0, running.replace("\tstate = running\n", "")),
                "wrong indentation": FakeResult(0, running.replace("\tstate = running", "\t\tstate = running")),
                "missing block close": FakeResult(0, running[:-2]),
                "transport error": OSError("fixture transport failure"),
            }
            for name, response in cases.items():
                with self.subTest(name=name):
                    with mock.patch.object(svc, "_run", CmdRecorder(default=response)):
                        with self.assertRaisesRegex(SystemExit, "state is indeterminate"):
                            svc._lifecycle_inspect(args.account, label, roots)

    def test_unknown_inspection_blocks_every_c2_modifying_path(self):
        with self._installed_c2_fixture() as (args, roots, _):
            for operation in (svc.cmd_paper_runtime_upgrade, svc.cmd_start, svc.cmd_stop, svc.cmd_seal_runtime):
                with self.subTest(operation=operation.__name__):
                    before = self._snapshot(roots)
                    recorder = CmdRecorder(default=FakeResult(1, "", "permission denied"))
                    with mock.patch.object(svc, "_run", recorder), \
                         mock.patch.object(svc, "_atomic_write_bytes") as write:
                        with self.assertRaisesRegex(SystemExit, "state is indeterminate"):
                            operation(args)
                        write.assert_not_called()
                    self.assertTrue(all(cmd[:2] == ["launchctl", "print"] for cmd in recorder.calls))
                    self.assertEqual(before, self._snapshot(roots))

    def test_unknown_inspection_during_paper_recovery_does_not_restore_or_replay(self):
        with self._installed_c2_fixture() as (args, roots, _):
            before_manifest = roots["manifest"].read_bytes()
            writes = []
            real_write = svc._atomic_write_bytes
            def write(path, data, mode=svc.FILE_MODE):
                writes.append(Path(path).name)
                real_write(path, data, mode)
                raise OSError("fixture post-replace failure")
            def handle(cmd):
                if writes:
                    return FakeResult(1, "", "unavailable")
                return None
            with mock.patch.object(svc, "_run", self._unloaded_recorder(handle)), \
                 mock.patch.object(svc, "_atomic_write_bytes", write):
                with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN during rollback"):
                    svc.cmd_paper_runtime_upgrade(args)
            self.assertEqual(writes, ["config.json"])
            self.assertEqual(roots["manifest"].read_bytes(), before_manifest)

    def test_unknown_inspection_after_bootout_retains_effect_unknown(self):
        with self._installed_c2_fixture() as (args, roots, _):
            stopped = []
            def handle(cmd):
                if cmd[:2] == ["launchctl", "bootout"]:
                    stopped.append(1)
                    return FakeResult(0)
                if stopped:
                    return FakeResult(113, "", "unexpected diagnostic")
                return FakeResult(0, _print_running(str(roots["plist"]), _label_for(args.account)))
            recorder = CmdRecorder(handler=handle)
            with mock.patch.object(svc, "_run", recorder):
                with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN after bootout"):
                    svc.cmd_stop(args)
            self.assertEqual([cmd[1] for cmd in recorder.calls], ["print", "bootout", "print"])


class TestC2BusinessHistoricalCompatibility(unittest.TestCase):
    """No new repository enrollment; exact 11-file original C2 only."""

    @staticmethod
    def _legacy_11_set():
        return frozenset((
            "gateway.mjs", "git-publish.mjs", "output-budget.mjs",
            "package.json", "package-lock.json", "paper-design.mjs",
            "fleet-status.mjs", "fleet-routing.mjs",
            "tailnet-gateway.mjs", "private-tunnel-auth.mjs",
            "private-tunnel-gateway.mjs",
        ))

    @contextmanager
    def _installed_c2(self, account="chatgpt2-business"):
        """Hermetic hash-sealed C2 seat, never a real host write."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            # account bound at fixture entry
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                source, node, backend, _rec = _do_stage(
                    tmp, home, account=account)
                roots = svc._build_runtime_roots(account)
                _seed_node_modules(roots)
                with mock.patch.object(svc, "_lifecycle_inspect", return_value=None):
                    _seal_runtime(account)
                old_names = self._legacy_11_set()
                for name in set(svc.STAGE_FILES) - old_names:
                    (roots["base"] / name).unlink()
                for name in old_names - set(svc.STAGE_FILES):
                    (roots["base"] / name).write_text(
                        f"// sealed old C2 {name}\n", encoding="utf-8")
                cfg = json.loads(roots["config"].read_text())
                cfg["gitPublish"] = svc._typed_git_config(home)
                cfg.pop("repositoryWorkspaces", None)
                cfg["fleetRouting"] = {
                    "enabled": True,
                    "requestTimeoutMs": svc.REQUEST_TIMEOUT_MS,
                    "routes": [
                        {"hostRef": "ubuntu1", "url": "https://ubuntu1.example.ts.net/mcp"},
                        {"hostRef": "ubuntu2", "url": "https://ubuntu2.example.ts.net/mcp"},
                    ],
                }
                cfg["maxPerSessionConcurrency"] = 8
                cfg["maxQueuedPerSession"] = 16
                cfg["fleetStatus"] = {
                    "enabled": True,
                    "launcherPath": str(home / ".local/bin/studio-direct"),
                    "launcherSha256": "a"*64, "timeoutMs": 15000,
                    "fabricLauncherPath": str(home / ".local/bin/fabric"),
                    "fabricLauncherSha256": "b"*64,
                    "fabricTimeoutMs": 8000,
                }
                roots["config"].write_text(
                    json.dumps(cfg, sort_keys=True), encoding="utf-8")
                prior = json.loads(roots["manifest"].read_text())
                prior["files"] = {
                    name: svc._sha256_file(roots["base"] / name)
                    for name in sorted(old_names)
                }
                prior["configHash"] = svc._sha256_file(roots["config"])
                roots["manifest"].write_text(
                    json.dumps(prior, sort_keys=True), encoding="utf-8")
                target_names = (svc.C2_PERSONAL_TARGET_PATCH_SHA256 if account == "chatgpt2-personal" else svc.C2_BUSINESS_TARGET_PATCH_SHA256)
                for name in target_names:
                    (source / name).write_text(
                        f"// reviewed target C2 {name}\n", encoding="utf-8")
                args = _stage_args(source, node, backend, account=account)
                args.c2_business_fleet_compat = account == "chatgpt2-business"
                args.c2_personal_closed_publisher = account == "chatgpt2-personal"
                args.publisher_preflight_only = False
                args.publisher_expected_manifest_sha256 = svc._sha256_file(
                    roots["manifest"])
                pins = {}
                for name in old_names:
                    data = (roots["base"] / name).read_bytes()
                    pins[name] = hashlib.sha1(
                        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
                    ).hexdigest()
                target = {
                    name: svc._sha256_file(source / name)
                    for name in target_names
                }
                personal_pins = {name: svc._sha256_file(roots["base"] / name) for name in old_names}
                runtime_id = {k: prior[k] for k in svc.C2_PAPER_RUNTIME_IDENTITY}
                with mock.patch.object(
                    svc, "C2_BUSINESS_V10_ORIGINAL_BLOBS", pins
                ), mock.patch.object(
                    svc, "C2_BUSINESS_TARGET_PATCH_SHA256", target
                ), mock.patch.object(svc, "C2_PAPER_FILES_SHA256", personal_pins
                ), mock.patch.object(svc, "C2_PAPER_RUNTIME_IDENTITY", runtime_id
                ), mock.patch.object(svc, "C2_PAPER_MANIFEST_CANONICAL_SHA256", frozenset((svc._canonical_json_sha256(prior),))
                ), mock.patch.object(svc, "C2_PERSONAL_CURRENT_MANIFEST_SHA256", args.publisher_expected_manifest_sha256
                ), mock.patch.object(svc, "C2_PERSONAL_TARGET_PATCH_SHA256", target
                ), mock.patch.object(svc, "_run", CmdRecorder()
                ):
                    yield args, roots, cfg, prior

    def test_generic_upgrade_from_c2_11file_refuses_downgrade_before_effect(self):
        with self._installed_c2() as (args, roots, cfg, prior):
            originals = {
                name:(roots["base"] / name).read_bytes()
                for name in prior["files"]
            }
            manifest = roots["manifest"].read_bytes()
            args.c2_business_fleet_compat = False
            args.publisher_expected_manifest_sha256 = None
            with self.assertRaisesRegex(SystemExit, "fleet/tailnet capability modules absent"):
                svc.cmd_upgrade(args)
            self.assertEqual(roots["manifest"].read_bytes(), manifest)
            self.assertEqual(
                {name:(roots["base"] / name).read_bytes() for name in prior["files"]},
                originals)
            self.assertFalse((roots["base"] / "workspace-access.mjs").exists())

    def test_c2_11_to_12_success_preserves_every_grant_and_fleet_byte(self):
        with self._installed_c2() as (args, roots, cfg, prior):
            before_files = {
                n: (roots["base"] / n).read_bytes() for n in prior["files"]
            }
            before_config = roots["config"].read_bytes()
            rc, out = _capture_stdout(lambda: svc.cmd_upgrade(args))
            self.assertEqual(rc, 0)
            result = json.loads(out)
            self.assertEqual(result["effect"], "APPLIED")
            self.assertTrue(result["noNewRepositoryGrants"])
            updated = svc._verify_staged_install(
                args.account, _label_for(args.account), roots)
            self.assertEqual(
                frozenset(updated["files"]),
                svc.V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR)
            self.assertEqual(roots["config"].read_bytes(), before_config)
            self.assertEqual(
                {n for n in prior["files"]
                 if (roots["base"] / n).read_bytes() != before_files[n]},
                {"gateway.mjs", "git-publish.mjs"})
            self.assertEqual(
                (roots["base"] / "workspace-access.mjs").read_bytes(),
                Path(args.source, "workspace-access.mjs").read_bytes())
            self.assertEqual(updated["dependencyTreeHash"], prior["dependencyTreeHash"])
            self.assertNotIn(
                "repositoryWorkspaces", json.loads(roots["config"].read_text()))

    def test_c2_preflight_is_read_only_with_loaded_service(self):
        with self._installed_c2() as (args, roots, cfg, prior):
            before = (
                roots["manifest"].read_bytes(),
                roots["config"].read_bytes(),
                {n: (roots["base"] / n).read_bytes() for n in prior["files"]},
            )
            args.publisher_preflight_only = True
            with mock.patch.object(
                svc, "_run", CmdRecorder(
                    handler=lambda c: FakeResult(
                        0, _print_running(str(roots["plist"]), _label_for(args.account)), "")
                    if c[:2] == ["launchctl", "print"] else None
                )
            ):
                rc, output = _capture_stdout(lambda: svc.cmd_upgrade(args))
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(output)["effect"], "NOT_APPLIED")
            self.assertEqual(before, (
                roots["manifest"].read_bytes(), roots["config"].read_bytes(),
                {n: (roots["base"] / n).read_bytes() for n in prior["files"]},
            ))
            self.assertFalse((roots["base"] / "workspace-access.mjs").exists())

    def test_c2_refuses_wrong_cas_grant_and_unreviewed_source_before_effect(self):
        with self._installed_c2() as (args, roots, cfg, prior):
            before = roots["manifest"].read_bytes()
            args.publisher_expected_manifest_sha256 = "0"*64
            with self.assertRaisesRegex(SystemExit, "CAS mismatch"):
                svc.cmd_upgrade(args)
            args.publisher_expected_manifest_sha256 = svc._sha256_file(
                roots["manifest"])
            args.enable_repository_workspaces = True
            with self.assertRaisesRegex(SystemExit, "no new repository grants"):
                svc.cmd_upgrade(args)
            args.enable_repository_workspaces = False
            p = Path(args.source) / "workspace-access.mjs"
            p.write_text("// malicious source replacement\n")
            with self.assertRaisesRegex(SystemExit, "reviewed source hash mismatch"):
                svc.cmd_upgrade(args)
            self.assertEqual(roots["manifest"].read_bytes(), before)
            self.assertFalse((roots["base"] / "workspace-access.mjs").exists())

    def test_c2_running_service_blocks_effects_after_verified_preflight(self):
        with self._installed_c2() as (args, roots, cfg, prior):
            original_manifest = roots["manifest"].read_bytes()
            recorder = CmdRecorder(
                handler=lambda c: FakeResult(
                    0, _print_running(str(roots["plist"]), _label_for(args.account)), "")
                if c[:2] == ["launchctl","print"] else None)
            with mock.patch.object(svc, "_run", recorder):
                with self.assertRaisesRegex(SystemExit, "service is loaded"):
                    svc.cmd_upgrade(args)
            self.assertEqual(roots["manifest"].read_bytes(), original_manifest)
            self.assertFalse((roots["base"] / "workspace-access.mjs").exists())
            self.assertTrue(all(call[:2] == ["launchctl","print"] for call in recorder.calls))

    def test_c2_unexpected_extra_workspace_file_refused_without_overwrite(self):
        with self._installed_c2() as (args, roots, cfg, prior):
            extra = roots["base"] / "workspace-access.mjs"
            extra.write_text("third party workspace module\n")
            manifest = roots["manifest"].read_bytes()
            with self.assertRaisesRegex(SystemExit, "new module already exists"):
                svc.cmd_upgrade(args)
            self.assertEqual(extra.read_text(), "third party workspace module\n")
            self.assertEqual(roots["manifest"].read_bytes(), manifest)

    def test_c2_rollback_failure_reports_effect_unknown_not_safe_replay(self):
        with self._installed_c2() as (args, roots, cfg, prior):
            manifest = roots["manifest"].read_bytes()
            real = svc._atomic_write_bytes
            seen_gateway = [0]
            def injected(path,data,mode=svc.FILE_MODE):
                name = Path(path).name
                if name == "gateway.mjs":
                    seen_gateway[0] += 1
                    if seen_gateway[0] > 1:
                        raise OSError("rollback cannot restore gateway")
                if name == "git-publish.mjs":
                    raise OSError("next planned write refused")
                return real(path,data,mode)
            with mock.patch.object(svc, "_atomic_write_bytes", injected):
                with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN during rollback"):
                    svc.cmd_upgrade(args)
            self.assertEqual(seen_gateway[0], 2)
            self.assertEqual(roots["manifest"].read_bytes(), manifest)
            self.assertFalse((roots["base"] / "workspace-access.mjs").exists())

    def test_c2_atomic_new_module_post_rename_rollback(self):
        with self._installed_c2() as (args, roots, cfg, prior):
            before = {
                n: (roots["base"] / n).read_bytes() for n in prior["files"]
            }
            manifest = roots["manifest"].read_bytes()
            real = svc._atomic_write_bytes
            injected = [False]
            def fail_after_rename(path, data, mode=svc.FILE_MODE):
                real(path, data, mode)
                if Path(path).name == "workspace-access.mjs" and not injected[0]:
                    injected[0] = True
                    raise OSError("simulated failure after creation rename")
            with mock.patch.object(svc, "_atomic_write_bytes", fail_after_rename):
                with self.assertRaisesRegex(SystemExit, "NOT_APPLIED"):
                    svc.cmd_upgrade(args)
            self.assertTrue(injected[0])
            self.assertEqual(roots["manifest"].read_bytes(), manifest)
            self.assertFalse((roots["base"] / "workspace-access.mjs").exists())
            self.assertEqual(
                {n:(roots["base"] / n).read_bytes() for n in prior["files"]},
                before)
            svc._verify_staged_install(args.account,_label_for(args.account),roots)

    def test_original_c2_only_v2_fileset_can_be_verified_without_a_grant(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            home = tmp / "home"
            home.mkdir()
            (home / "Library" / "LaunchAgents").mkdir(parents=True)
            account = "chatgpt2-business"
            with mock.patch.dict(os.environ, {"HOME": str(home)}):
                _src, _node, _backend, _ = _do_stage(tmp, home, account=account)
                roots = svc._build_runtime_roots(account)
                _seed_node_modules(roots)
                _seal_runtime(account)
                historical = self._legacy_11_set()
                for name in set(svc.STAGE_FILES) - historical:
                    (roots["base"] / name).unlink()
                for name in historical - set(svc.STAGE_FILES):
                    (roots["base"] / name).write_text("// sealed original "+name+"\n")
                cfg = json.loads(roots["config"].read_text())
                cfg["gitPublish"] = svc._typed_git_config(home)
                cfg["fleetRouting"] = {
                    "enabled": True, "requestTimeoutMs": svc.REQUEST_TIMEOUT_MS,
                    "routes":[
                        {"hostRef":"ubuntu1","url":"https://ubuntu1.example.ts.net/mcp"},
                        {"hostRef":"ubuntu2","url":"https://ubuntu2.example.ts.net/mcp"},
                    ],
                }
                cfg["maxPerSessionConcurrency"] = 8
                cfg["maxQueuedPerSession"] = 16
                cfg.pop("repositoryWorkspaces", None)
                roots["config"].write_text(json.dumps(cfg, sort_keys=True))
                prior = json.loads(roots["manifest"].read_text())
                prior["files"] = {
                    name: svc._sha256_file(roots["base"] / name)
                    for name in sorted(historical)
                }
                prior["configHash"] = svc._sha256_file(roots["config"])
                roots["manifest"].write_text(json.dumps(prior, sort_keys=True))
                manifest_before = roots["manifest"].read_bytes()
                self.assertTrue(svc._valid_manifest(
                    prior, account, _label_for(account)))
                actual = svc._verify_staged_install(
                    account, _label_for(account), roots)
                self.assertEqual(frozenset(actual["files"]), historical)
                self.assertEqual(roots["manifest"].read_bytes(), manifest_before)
                self.assertNotIn("repositoryWorkspaces", cfg)
                self.assertEqual(cfg["gitPublish"], svc._typed_git_config(home))
                self.assertFalse(svc._valid_manifest(
                    {**prior,"account":"chatgpt3"}, account, _label_for(account)))
                self.assertFalse(svc._valid_manifest(
                    {**prior,"files":{**prior["files"],"unexpected.mjs":"a"*64}},
                    account, _label_for(account)))


class TestC2BusinessClosedRepositoryEnrollment(unittest.TestCase):
    """The existing C2 owner alone may grant a closed repo profile after 11->12."""

    _legacy_11_set = staticmethod(
        TestC2BusinessHistoricalCompatibility._legacy_11_set)
    _installed_c2 = TestC2BusinessHistoricalCompatibility._installed_c2

    @contextmanager
    def _eligible_c2(self):
        with self._installed_c2() as (args, roots, cfg, prior):
            rc, _ = _capture_stdout(lambda: svc.cmd_upgrade(args))
            self.assertEqual(rc, 0)
            args.c2_business_fleet_compat = False
            args.c2_business_repository_enrollment = True
            args.enable_repository_workspaces = True
            args.publisher_expected_manifest_sha256 = svc._sha256_file(
                roots["manifest"])
            yield args, roots

    def test_preflight_and_apply_preserve_fleet_paper_and_modules(self):
        with self._eligible_c2() as (args, roots):
            before_config = json.loads(roots["config"].read_text())
            before_files = {n: (roots["base"] / n).read_bytes()
                            for n in svc.V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR}
            manifest = roots["manifest"].read_bytes()
            lock = roots["state"] / svc.C2_LIFECYCLE_LOCK_NAME
            self.assertFalse(lock.exists())
            args.publisher_preflight_only = True
            rc, output = _capture_stdout(lambda: svc.cmd_upgrade(args))
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(output)["effect"], "NOT_APPLIED")
            self.assertFalse(lock.exists())
            self.assertEqual(roots["manifest"].read_bytes(), manifest)
            args.publisher_preflight_only = False
            rc, output = _capture_stdout(lambda: svc.cmd_upgrade(args))
            self.assertEqual(rc, 0)
            receipt = json.loads(output)
            self.assertEqual(receipt["effect"], "APPLIED")
            self.assertTrue(lock.is_file())
            self.assertEqual(receipt["closedRepositories"],
                             ["mastermind", "macro", "terminal"])
            after = json.loads(roots["config"].read_text())
            self.assertEqual(after["repositoryWorkspaces"], {
                "enabled": True,
                "allowedRepositories": ["mastermind", "macro", "terminal"]})
            self.assertEqual(after["gitPublish"],
                             svc._typed_git_config(Path(os.environ["HOME"]),
                                                   closed_repositories=True))
            for key in set(before_config) - {"gitPublish"}:
                self.assertEqual(after[key], before_config[key])
            self.assertEqual(
                before_files,
                {n: (roots["base"] / n).read_bytes() for n in before_files})
            after_manifest = svc._verify_staged_install(
                args.account, _label_for(args.account), roots)
            self.assertEqual(after_manifest["files"],
                             json.loads(manifest)["files"])
            self.assertEqual(after_manifest["dependencyTreeHash"],
                             json.loads(manifest)["dependencyTreeHash"])
            self.assertEqual(after_manifest["source"],
                             json.loads(manifest)["source"])

    def test_other_accounts_and_missing_explicit_grant_refused(self):
        with self._eligible_c2() as (args, roots):
            original = roots["manifest"].read_bytes()
            args.enable_repository_workspaces = False
            with self.assertRaisesRegex(SystemExit, "explicit opt-in"):
                svc.cmd_upgrade(args)
            args.enable_repository_workspaces = True
            args.account = "chatgpt1"
            with self.assertRaisesRegex(SystemExit, "exact Business profile"):
                svc._enroll_c2_business_closed_repositories(
                    args, Path(args.node), Path(args.backend), "chatgpt1",
                    _label_for("chatgpt1"), args.port, roots)
            args.account = "chatgpt2-business"
            args.publisher_expected_manifest_sha256 = "0"*64
            with self.assertRaisesRegex(SystemExit, "CAS mismatch"):
                svc.cmd_upgrade(args)
            self.assertEqual(roots["manifest"].read_bytes(), original)

    def test_loaded_service_blocks_mutation_but_allows_readonly_preflight(self):
        with self._eligible_c2() as (args, roots):
            original = roots["manifest"].read_bytes()
            recorder = CmdRecorder(handler=lambda c: FakeResult(
                0, _print_running(str(roots["plist"]), _label_for(args.account)), "")
                if c[:2] == ["launchctl", "print"] else None)
            with mock.patch.object(svc, "_run", recorder):
                args.publisher_preflight_only = True
                rc, out = _capture_stdout(lambda: svc.cmd_upgrade(args))
                self.assertEqual(rc, 0)
                self.assertEqual(json.loads(out)["effect"], "NOT_APPLIED")
                args.publisher_preflight_only = False
                with self.assertRaisesRegex(SystemExit, "service is loaded"):
                    svc.cmd_upgrade(args)
            self.assertEqual(roots["manifest"].read_bytes(), original)

    def test_precommit_failure_rolls_back_without_new_grant(self):
        with self._eligible_c2() as (args, roots):
            original_config = roots["config"].read_bytes()
            original_manifest = roots["manifest"].read_bytes()
            real = svc._atomic_write_bytes
            injected = [False]
            def fail_after_config(path, data, mode=svc.FILE_MODE):
                real(path, data, mode)
                if Path(path) == roots["config"] and not injected[0]:
                    injected[0] = True
                    raise OSError("injected failure after atomic config rename")
            with mock.patch.object(svc, "_atomic_write_bytes", fail_after_config):
                with self.assertRaisesRegex(SystemExit, "NOT_APPLIED"):
                    svc.cmd_upgrade(args)
            self.assertTrue(injected[0])
            self.assertEqual(roots["config"].read_bytes(), original_config)
            self.assertEqual(roots["manifest"].read_bytes(), original_manifest)
            svc._verify_staged_install(args.account, _label_for(args.account), roots)


if __name__ == "__main__":
    unittest.main(verbosity=2)

class TestC2PersonalClosedPublisher(unittest.TestCase):
    def test_wrong_cas_refuses_without_mutation(self):
        fixture = TestC2BusinessHistoricalCompatibility()
        with fixture._installed_c2(account="chatgpt2-personal") as (args, roots, cfg, prior):
            before = (roots["manifest"].read_bytes(), roots["config"].read_bytes())
            args.publisher_expected_manifest_sha256 = "0" * 64
            with self.assertRaisesRegex(SystemExit, "CAS mismatch"):
                svc.cmd_upgrade(args)
            self.assertEqual(before, (roots["manifest"].read_bytes(), roots["config"].read_bytes()))
            self.assertFalse((roots["base"]/"workspace-access.mjs").exists())

    def test_wrong_source_refuses_without_mutation(self):
        fixture = TestC2BusinessHistoricalCompatibility()
        with fixture._installed_c2(account="chatgpt2-personal") as (args, roots, cfg, prior):
            before = (roots["manifest"].read_bytes(), roots["config"].read_bytes())
            (Path(args.source)/"git-publish.mjs").write_text("unreviewed publisher")
            with self.assertRaisesRegex(SystemExit, "reviewed source hash mismatch"):
                svc.cmd_upgrade(args)
            self.assertEqual(before, (roots["manifest"].read_bytes(), roots["config"].read_bytes()))
            self.assertFalse((roots["base"]/"workspace-access.mjs").exists())

    def test_preflight_and_upgrade_preserve_fleet_paper_and_seals(self):
        fixture = TestC2BusinessHistoricalCompatibility()
        with fixture._installed_c2(account="chatgpt2-personal") as (args, roots, cfg, prior):
            before = {n:(roots["base"]/n).read_bytes() for n in prior["files"]}
            old_config = json.loads(roots["config"].read_text())
            args.publisher_preflight_only = True
            rc, out = _capture_stdout(lambda: svc.cmd_upgrade(args))
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(out)["effect"], "NOT_APPLIED")
            self.assertFalse((roots["base"]/"workspace-access.mjs").exists())
            args.publisher_preflight_only = False
            rc, out = _capture_stdout(lambda: svc.cmd_upgrade(args))
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(out)["effect"], "APPLIED")
            future = svc._verify_staged_install(args.account, _label_for(args.account), roots, require_runtime_seal=True)
            self.assertEqual(future["dependencyTreeHash"], prior["dependencyTreeHash"])
            config = json.loads(roots["config"].read_text())
            self.assertEqual(config["gitPublish"], svc._typed_git_config(svc._user_root(), closed_repositories=True))
            self.assertEqual(config["repositoryWorkspaces"]["allowedRepositories"], ["mastermind","macro","terminal"])
            for key in ("paperDesign","fleetRouting","fleetStatus","maxPerSessionConcurrency","maxQueuedPerSession"):
                self.assertEqual(config[key], old_config[key])
            self.assertEqual({n for n in before if (roots["base"]/n).read_bytes() != before[n]}, {"gateway.mjs","git-publish.mjs"})
