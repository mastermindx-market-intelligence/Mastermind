"""Exercise patched donor functions and original callers without a real driver."""
from __future__ import annotations

import ast
import builtins
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback
import types
import unittest
from unittest import mock

from integrations.hermes_qualification.computer_env_guard import qualify

SENTINEL = "synthetic-secret-must-not-reach-child-or-error"
ERROR = "CUA_DRIVER_ENV_UNAVAILABLE"
FIXTURES = qualify.ROOT / "fixtures"


def donor_functions(source, names, namespace):
    """Compile original AST nodes, preserving bodies and future annotations."""
    tree = ast.parse(source)
    selected = [node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in selected} != set(names):
        raise AssertionError("donor function set drift")
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    module = ast.fix_missing_locations(ast.Module(body=[future, *selected], type_ignores=[]))
    exec(compile(module, "<qualified-donor-functions>", "exec"), namespace)


def package(name):
    value = types.ModuleType(name)
    value.__path__ = []
    return value


class GuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = {name: (FIXTURES / (name + ".source")).read_bytes() for name in qualify.PATHS}
        cls.patched = qualify.prepare_sources(cls.sources)
        cls.driver_source = (FIXTURES / "tools/computer_use/cua_backend_driver.py.source").read_bytes()

    def setUp(self):
        self.spawn = mock.Mock(return_value=subprocess.CompletedProcess([], 0, stdout="{}", stderr=""))
        self.process = types.SimpleNamespace(run=self.spawn, DEVNULL=subprocess.DEVNULL,
                                            SubprocessError=subprocess.SubprocessError,
                                            TimeoutExpired=subprocess.TimeoutExpired)
        self.native_env = {"PATH": "/bin", "DISPLAY": ":99", "CUA_DRIVER_RS_TELEMETRY_ENABLED": "0",
                           "SYNTHETIC_PROVIDER_API_KEY": SENTINEL}
        self.clean_env = {key: value for key, value in self.native_env.items()
                          if key != "SYNTHETIC_PROVIDER_API_KEY"}
        self.backend = types.ModuleType("tools.computer_use.cua_backend")
        self.backend.__dict__.update(subprocess=self.process, json=json,
                                     windows_hide_flags=lambda: 0,
                                     cua_driver_child_env=mock.Mock(return_value=self.native_env))
        donor_functions(self.patched[qualify.PATHS[1]],
                        {"sanitized_cua_driver_env", "_run_driver", "_run_quiet", "cua_daemon_listening"},
                        self.backend.__dict__)
        self.local = types.ModuleType("tools.environments.local")
        self.local._sanitize_subprocess_env = mock.Mock(return_value=self.clean_env)
        self.driver = types.ModuleType("tools.computer_use.cua_backend_driver")
        self.driver.__dict__.update(_cb=lambda: self.backend, subprocess=self.process,
                                    sys=types.SimpleNamespace(platform="darwin"), json=json,
                                    resolve_cua_driver_cmd=lambda *args: "/test/cua-driver")
        donor_functions(self.driver_source, {"_driver_json", "cua_driver_runtime_contract_status"},
                        self.driver.__dict__)
        self.plugins = package("plugins.computer_use")
        self.plugins.DEFAULT_BACKEND = "cua"
        self.plugins.configured_backend_name = lambda: "cua"
        self.plugins.get_active_provider = mock.Mock(side_effect=AssertionError("unexpected alternate backend"))
        modules = {"tools": package("tools"), "tools.computer_use": package("tools.computer_use"),
                   "tools.environments": package("tools.environments"), "tools.environments.local": self.local,
                   "tools.computer_use.cua_backend": self.backend,
                   "tools.computer_use.cua_backend_driver": self.driver,
                   "plugins": package("plugins"), "plugins.computer_use": self.plugins}
        patcher = mock.patch.dict(sys.modules, modules)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.permissions = {"subprocess": self.process, "json": json,
                            "sys": types.SimpleNamespace(platform="darwin", stderr=sys.stderr),
                            "suppress": contextlib.suppress, "windows_hide_flags": lambda: 0,
                            "_RUNTIME_PLATFORMS": frozenset({"darwin", "linux", "win32"}),
                            "_BOOLS": ("accessibility", "screen_recording", "screen_recording_capturable"),
                            "CUA_DRIVER_BUNDLE_ID": "com.trycua.driver"}
        donor_functions(self.patched[qualify.PATHS[0]],
                        {"_child_env", "_run", "_json_out", "_doctor", "_mac_permissions",
                         "computer_use_status", "request_permissions_grant"}, self.permissions)

    def assert_closed_error(self, callback):
        try:
            callback()
        except OSError as error:
            self.assertEqual(str(error), ERROR)
            self.assertNotIn(SENTINEL, traceback.format_exc())
        else:
            self.fail("expected the closed unavailable failure")
        self.spawn.assert_not_called()

    def test_fixture_preimages_are_exact(self):
        for name, digest in qualify.manifest()["test_fixtures"].items():
            self.assertEqual(qualify.digest((qualify.ROOT / name).read_bytes()), digest)

    def test_sanitizer_exception_cannot_escape_or_spawn(self):
        self.local._sanitize_subprocess_env.side_effect = RuntimeError(SENTINEL)
        self.assert_closed_error(lambda: self.permissions["_run"]("/test/cua-driver", "status", timeout=1))

    def test_environment_preparation_exception_cannot_escape_or_spawn(self):
        self.backend.cua_driver_child_env.side_effect = RuntimeError(SENTINEL)
        self.assert_closed_error(lambda: self.backend._run_driver("/test/cua-driver", "status", timeout=1))

    def test_sanitizer_import_failure_is_closed(self):
        original = builtins.__import__
        def fail_import(name, *args, **kwargs):
            if name == "tools.environments.local":
                raise ImportError(SENTINEL)
            return original(name, *args, **kwargs)
        with mock.patch("builtins.__import__", side_effect=fail_import):
            self.assert_closed_error(lambda: self.permissions["_run"]("/test/cua-driver", timeout=1))

    def test_outer_helper_import_failure_is_closed(self):
        original = builtins.__import__
        def fail_import(name, *args, **kwargs):
            if name == "tools.computer_use.cua_backend":
                raise ImportError(SENTINEL)
            return original(name, *args, **kwargs)
        with mock.patch("builtins.__import__", side_effect=fail_import):
            self.assert_closed_error(lambda: self.permissions["_run"]("/test/cua-driver", timeout=1))

    def test_invalid_sanitizer_values_refuse_ambient_inheritance(self):
        for value in (None, [], {"PATH": None}, {1: "value"}, {"PATH": 1}):
            with self.subTest(value=value):
                self.local._sanitize_subprocess_env.return_value = value
                self.assert_closed_error(lambda: self.permissions["_run"]("/test/cua-driver", timeout=1))

    def test_outer_helper_validates_even_a_replaced_inner_helper(self):
        self.backend.sanitized_cua_driver_env = lambda: None
        self.assert_closed_error(lambda: self.permissions["_run"]("/test/cua-driver", timeout=1))

    def test_declared_swallow_covers_environment_preparation(self):
        self.local._sanitize_subprocess_env.side_effect = RuntimeError(SENTINEL)
        self.assertIsNone(self.backend._run_driver("/test/cua-driver", timeout=1, swallow=Exception))
        self.assertIsNone(self.backend._run_driver("/test/cua-driver", timeout=1,
                                                 swallow=(OSError, subprocess.SubprocessError)))
        self.spawn.assert_not_called()

    def test_daemon_liveness_remains_unknown(self):
        self.local._sanitize_subprocess_env.side_effect = RuntimeError(SENTINEL)
        self.assertIsNone(self.backend.cua_daemon_listening("/test/cua-driver"))
        self.spawn.assert_not_called()

    def test_json_discovery_remains_unknown(self):
        self.local._sanitize_subprocess_env.side_effect = RuntimeError(SENTINEL)
        self.assertIsNone(self.driver._driver_json("/test/cua-driver", "manifest", timeout=1))
        self.spawn.assert_not_called()

    def test_runtime_contract_reports_not_ready(self):
        self.local._sanitize_subprocess_env.side_effect = RuntimeError(SENTINEL)
        result = self.driver.cua_driver_runtime_contract_status("/test/cua-driver")
        self.assertFalse(result["ready"])
        self.assertIsNone(result["version"])
        self.assertEqual(result["reason"], "manifest check failed: " + ERROR)
        self.assertNotIn(SENTINEL, json.dumps(result))
        self.spawn.assert_not_called()

    def test_permission_status_never_claims_ready(self):
        self.local._sanitize_subprocess_env.side_effect = RuntimeError(SENTINEL)
        self.assertIsNone(self.permissions["_doctor"]("/test/cua-driver"))
        for platform in ("darwin", "linux", "win32"):
            with self.subTest(platform=platform):
                self.permissions["sys"].platform = platform
                result = self.permissions["computer_use_status"]("/test/cua-driver")
                self.assertIsNone(result["ready"])
                self.assertNotIn(SENTINEL, json.dumps(result))
        self.spawn.assert_not_called()

    def test_grant_returns_failure_without_spawn_or_secret_output(self):
        self.local._sanitize_subprocess_env.side_effect = RuntimeError(SENTINEL)
        stdout, stderr = io.StringIO(), io.StringIO()
        self.permissions["sys"].stderr = stderr
        with contextlib.redirect_stdout(stdout):
            result = self.permissions["request_permissions_grant"]("/test/cua-driver")
        self.assertEqual(result, 2)
        self.assertIn(ERROR, stderr.getvalue())
        self.assertNotIn(SENTINEL, stdout.getvalue() + stderr.getvalue())
        self.spawn.assert_not_called()

    def test_success_preserves_existing_sanitizer_output(self):
        self.permissions["_run"]("/test/cua-driver", "status", timeout=1)
        passed = self.spawn.call_args.kwargs["env"]
        self.assertEqual(passed, self.clean_env)
        self.assertEqual(passed["DISPLAY"], ":99")
        self.assertEqual(passed["CUA_DRIVER_RS_TELEMETRY_ENABLED"], "0")
        self.assertNotIn(SENTINEL, json.dumps(passed))
        self.local._sanitize_subprocess_env.assert_called_once_with(self.native_env)

    def test_empty_sanitized_environment_is_explicit_not_inherited(self):
        self.local._sanitize_subprocess_env.return_value = {}
        self.permissions["_run"]("/test/cua-driver", timeout=1)
        self.assertEqual(self.spawn.call_args.kwargs["env"], {})

    def test_wrong_preimage_and_double_apply_refuse(self):
        changed = dict(self.sources)
        changed[qualify.PATHS[0]] += b"\n"
        with self.assertRaisesRegex(qualify.QualificationError, "DONOR_PREIMAGE_MISMATCH"):
            qualify.prepare_sources(changed)
        with self.assertRaisesRegex(qualify.QualificationError, "DONOR_PREIMAGE_MISMATCH"):
            qualify.prepare_sources(self.patched)

    def test_qualification_never_modifies_supplied_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, raw in self.sources.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            result = qualify.qualify_root(root)
            self.assertEqual(result["status"], "EXACT_SOURCE_PATCH_VERIFIED")
            for key in ("donor_modified", "driver_started", "runtime_ready", "installed"):
                self.assertIs(result[key], False)
            for name, raw in self.sources.items():
                self.assertEqual((root / name).read_bytes(), raw)

    def test_symlink_source_refuses(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / "source").write_bytes(b"source")
            (path / "link").symlink_to(path / "source")
            with self.assertRaises(qualify.QualificationError):
                qualify._read_regular(path / "link", 100)


if __name__ == "__main__":
    unittest.main()
