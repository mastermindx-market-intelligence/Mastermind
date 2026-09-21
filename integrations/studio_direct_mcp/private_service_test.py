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
        f"gui/501/{label} = {{\n"
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
        f"gui/501/{label} = {{\n"
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
    if not typed_git:
        config.pop("gitPublish", None)
    roots["config"].write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
    manifest = json.loads(roots["manifest"].read_text(encoding="utf-8"))
    manifest["version"] = 1
    for key in ("nodeHash", "backendHash", "dependencyTreeHash"):
        manifest.pop(key, None)
    removed = ("paper-design.mjs", "output-budget.mjs") if typed_git else (
        "paper-design.mjs", "output-budget.mjs", "git-publish.mjs"
    )
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
                "output-budget.mjs",
                "git-publish.mjs",
                "paper-design.mjs",
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
        immediate_legacy = {name: digest for name in svc.LEGACY_STAGE_FILES_V3}
        self.assertTrue(svc._valid_manifest({**base, "files": immediate_legacy}, "test-account", _label_for("test-account")))
        typed_legacy = {name: digest for name in svc.LEGACY_STAGE_FILES_V2}
        self.assertTrue(svc._valid_manifest({**base, "files": typed_legacy}, "test-account", _label_for("test-account")))
        self.assertNotIn("output-budget.mjs", svc.LEGACY_STAGE_FILES_V1)
        self.assertNotIn("git-publish.mjs", svc.LEGACY_STAGE_FILES_V1)
        partial = dict(legacy)
        partial.pop(next(iter(partial)))
        self.assertFalse(svc._valid_manifest({**base, "files": partial}, "test-account", _label_for("test-account")))
        extra = dict(current)
        extra["surprise.mjs"] = digest
        self.assertFalse(svc._valid_manifest({**base, "files": extra}, "test-account", _label_for("test-account")))
        self.assertFalse(svc._valid_manifest({**base, "version": 2, "files": current}, "test-account", _label_for("test-account")))

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
            self.assertEqual(receipt["generation"], "v2")

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
            receipt["generation"] = "v3"
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
            paper_runtime = home / ".local" / "share" / "mastermind-paper" / "runtime" / "v2"
            self.assertEqual(
                config["paperDesign"],
                {
                    "enabled": True,
                    "pythonPath": str(paper_runtime / "venv" / "bin" / "python"),
                    "bridgePath": str(paper_runtime / "source" / "bridge.py"),
                    "bridgeSha256": svc.PAPER_BRIDGE_SHA256,
                    "commandTimeoutMs": 70_000,
                },
            )
            self.assertNotIn("fileId", config["paperDesign"])
            self.assertNotIn("account", config["paperDesign"])
            self.assertNotIn("token", config["paperDesign"])


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
            {"stage", "upgrade", "seal-runtime", "start", "status", "stop"},
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
