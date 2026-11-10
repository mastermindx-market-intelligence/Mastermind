"""Hermetic installed-code closure proof for the existing control-bundle owner.

Every owner-data path below is a private temporary fixture. The deliberately
invalid successor plan refuses before native selection or ingress observation.
"""
from __future__ import annotations

import hashlib
import importlib._bootstrap_external
import importlib.util
import json
import os
import py_compile
import select
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import control_bundle as bundle

HERE = Path(__file__).resolve().parent
EXPECTED_FILES = {
    "private_service.py",
    "private_tunnel_service.py",
    "studio_direct_control.py",
    "private_service_status_successor.py",
    "private_service_pin.py",
    "fleet_git_failure_compat.py",
    "private_service_pin_enrollment.py",
    "paper_v20_fleet_cohorts.py",
    "ops/native_fabric/quota_continuity/rollout/native_install.py",
    "ops/native_fabric/quota_continuity/rollout/build_review_stage.py",
    "ops/native_fabric/quota_continuity/rollout/preimages/native_generation_75330d.py",
    "ops/native_fabric/quota_continuity/rollout/native_generation.py",
    "ops/fabric_launch/install.py",
    "control_plane/provider_protocols.py",
    "ops/native_fabric/paid_canonical_glm/candidate/glm_shim.py",
    "ops/native_fabric/provider_plans/maintenance_guard/lease_broker.py.patch",
    "ops/native_fabric/provider_plans/maintenance_guard/remote_sub_exec.py.patch",
    "ops/native_fabric/provider_plans/memory118/fabric_memory_view.py",
    "ops/native_fabric/provider_plans/memory118/lease_broker.after-maintenance.py.patch",
    "ops/native_fabric/provider_plans/memory118/native_owner/fabric_operator_contract.py",
    "ops/native_fabric/provider_plans/memory118/native_owner/fabric_operator_owner.py",
    "ops/native_fabric/provider_plans/memory118/native_owner/protected_memory_economic.py",
    "ops/native_fabric/provider_plans/memory118/native_owner/provider_outcome.py",
    "ops/native_fabric/provider_plans/memory118/native_owner/run_observation_delivery.py",
    "ops/native_fabric/provider_plans/memory118_support_status/after_terminal_diagnostics/profile.json",
    "ops/native_fabric/provider_plans/memory118_support_status/artifact_delivery.py.patch",
    "ops/native_fabric/provider_plans/memory118_support_status/fabric_task.py.patch",
    "ops/native_fabric/provider_plans/patches/pick_remote_plan_modes.forward.patch",
    "ops/native_fabric/provider_plans/profile.json",
    "ops/native_fabric/provider_plans/remote_placement/profile.json",
    "ops/native_fabric/provider_plans/router_admission.json",
    "ops/native_fabric/provider_plans/terminal_diagnostics/component.json",
    "ops/native_fabric/provider_plans/terminal_diagnostics/current40/profile.json",
    "ops/native_fabric/provider_plans/terminal_diagnostics/native_plan_worker.py.forward.patch",
    "ops/native_fabric/quota_continuity/candidate/application_http_transports.py",
    "ops/native_fabric/quota_continuity/candidate/go_lease_capability.py",
    "ops/native_fabric/quota_continuity/candidate/go_lease_gateway.py",
    "ops/native_fabric/quota_continuity/candidate/go_shim.py",
    "ops/native_fabric/quota_continuity/candidate/lease_broker.py",
    "ops/native_fabric/quota_continuity/candidate/native_go_entry.py",
    "ops/native_fabric/quota_continuity/rollout/application_http_realm_projection.py",
    "ops/native_fabric/quota_continuity/rollout/preimages/glm_application_core_5c3d/go_lease_capability.py",
    "ops/native_fabric/quota_continuity/rollout/preimages/glm_application_core_5c3d/go_lease_gateway.py",
    "ops/native_fabric/quota_continuity/rollout/preimages/glm_application_core_5c3d/lease_broker.py",
    "ops/native_fabric/quota_continuity/rollout/provider_application/composition.json",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/experiential_bridge.py",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/experiential_host_context.py",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/experiential_plan_policy.py",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/experiential_transport.py",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/native40-profile.json",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/native40-provenance.json",
    "ops/native_fabric/quota_continuity/rollout/provider_application/maintenance_guard/native_plan_worker.py",
    "ops/native_fabric/quota_continuity/rollout/provider_application/memory_support/composition.json",
    "ops/native_fabric/quota_continuity/rollout/provider_application/memory_support/fabric_task.py.forward.patch",
    "ops/native_fabric/quota_continuity/rollout/provider_application/memory_support/lease_broker.py.forward.patch",
    "ops/native_fabric/quota_continuity/rollout/provider_application/remote-placement.json",
    "ops/native_fabric/quota_continuity/rollout/provider_application/terminal_diagnostics/composition.json",
    "ops/native_fabric/quota_continuity/rollout/provider_application/terminal_diagnostics/native_plan_worker.py.forward.patch",
    "ops/native_fabric/quota_continuity/source/application_http_transports.py.preimage",
    "ops/native_fabric/quota_continuity/source/codex_provider_realm.py.preimage",
    "ops/native_fabric/quota_continuity/source/glm_keys.py",
    "ops/native_fabric/quota_continuity/source/go_shim.py",
    "ops/native_fabric/support_policy_status/reader.py",
}

LOAD = r"""
import importlib.util,json,sys
from pathlib import Path
root=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location("installed_private_service",root/"private_service.py")
svc=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=svc
spec.loader.exec_module(svc)
"""


class InstalledClosureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mmx-control-closure-")
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir(mode=0o700)
        patcher = mock.patch.object(bundle.Path, "home", return_value=self.home)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.control = self.home / ".local/share/studio-direct-mcp/control"
        self.control.mkdir(parents=True, mode=0o700)
        self.launcher = self.home / ".local/bin/studio-direct"
        self.launcher.parent.mkdir(parents=True, mode=0o700)
        self.launcher.write_text("#!/bin/sh\nexit 0\n")
        self.launcher.chmod(0o700)
        self.empty = self.root / "empty"
        self.empty.mkdir(mode=0o700)
        self.successor = self.home / "invalid-successor-fixture"
        self.successor.mkdir(mode=0o700)
        (self.successor / "PLAN.json").write_text("{}\n")
        (self.successor / "PLAN.json").chmod(0o600)
        # Positive installs own their source-custody fixture; runner checkout
        # permissions are not the installation boundary under test.
        self.source = self.home / "checkout/integrations/studio_direct_mcp"
        for name in EXPECTED_FILES:
            original = HERE.parents[1] / name if "/" in name else HERE / name
            destination = self.source.parents[1] / name if "/" in name else self.source / name
            directory = self.home
            for part in destination.parent.relative_to(self.home).parts:
                directory /= part
                directory.mkdir(exist_ok=True, mode=0o700)
            content = original.read_bytes()
            destination.write_bytes(content)
            destination.chmod(0o600)
            self.assertEqual(destination.read_bytes(), content)

    def tearDown(self):
        self.tmp.cleanup()

    def _install(self):
        # The fixture acts as the release operator: supply the exact observed
        # installed generation CAS on upgrades, never a generic force/retry.
        manifest = self.control / "manifest.json"
        prior = json.loads(manifest.read_text())["bundleDigest"] if manifest.exists() else None
        return bundle.install(source=self.source, control_root=self.control,
                              launcher=self.launcher, expected_bundle_digest=prior)

    def test_private_source_still_refuses_a_writable_ancestor(self):
        self._install()
        manifest = self.control / "manifest.json"
        before = manifest.read_bytes()
        self.source.parent.chmod(0o770)
        with self.assertRaisesRegex(bundle.Refusal, "SOURCE_DIRECTORY_INVALID"):
            self._install()
        self.assertEqual(manifest.read_bytes(), before)

    def _child(self, code, *args, loader=LOAD, timeout=15, home=None, interpreter=None):
        env = {"HOME": str(home or self.home), "PATH": "/usr/bin:/bin", "LANG": "C"}
        if "LD_LIBRARY_PATH" in os.environ:
            env["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH"]
        return subprocess.run(
            [str(interpreter or sys.executable), "-I", "-S", "-B", "-c", loader + code,
             str(self.control), *map(str, args)],
            cwd=self.empty, env=env,
            capture_output=True, text=True, timeout=timeout,
        )

    def _predecessor_member_fixture(self, names):
        # This models the existing owner's exact membership and seal for
        # migration; the new runtime must not execute this older membership.
        self._install()
        path = self.control / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["files"] = {
            name: manifest["files"][name] for name in names}
        manifest["bundleDigest"] = bundle._bundle_digest(
            manifest["files"], manifest["launcherHash"])
        path.write_text(json.dumps(manifest))
        for name in set(bundle.CONTROL_FILES) - set(names):
            (self.control / name).unlink()
        for path in sorted(self.control.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        return manifest

    def _captured_ten_member_fixture(self):
        return self._predecessor_member_fixture(bundle.CAPTURED_CONTROL_FILES)

    def _review_thirteen_member_fixture(self):
        return self._predecessor_member_fixture(bundle.REVIEW_CONTROL_FILES)

    def test_review_thirteen_member_bundle_upgrades_only_under_original_cas(self):
        prior = self._review_thirteen_member_fixture()
        verified = bundle.verify(control_root=self.control, launcher=self.launcher)
        self.assertEqual(set(verified["files"]), set(bundle.REVIEW_CONTROL_FILES))
        before = self._snapshot()
        with self.assertRaises(bundle.Refusal):
            bundle.install(source=self.source, control_root=self.control,
                           launcher=self.launcher)
        self.assertEqual(self._snapshot(), before)
        with self.assertRaisesRegex(bundle.Refusal, "CONTROL_BUNDLE_CAS_MISMATCH"):
            bundle.install(source=self.source, control_root=self.control,
                           launcher=self.launcher, expected_bundle_digest="0" * 64)
        self.assertEqual(self._snapshot(), before)
        result = bundle.install(source=self.source, control_root=self.control,
                                launcher=self.launcher,
                                expected_bundle_digest=prior["bundleDigest"])
        self.assertEqual(set(result["files"]), EXPECTED_FILES)
        self.assertEqual(bundle.verify(control_root=self.control,
                                      launcher=self.launcher)["bundleDigest"],
                         result["bundleDigest"])

    def test_review_thirteen_member_verification_keeps_lock_and_cache_fences(self):
        self._review_thirteen_member_fixture()
        cache = self.control / "__pycache__"
        cache.mkdir(mode=0o700)
        (cache / "private_service.fixture.pyc").write_bytes(b"not executable")
        (cache / "private_service.fixture.pyc").chmod(0o600)
        with self.assertRaises(bundle.Refusal):
            bundle.verify(control_root=self.control, launcher=self.launcher)
        shutil.rmtree(cache)
        (self.control / ".control-bundle.lock").unlink()
        with self.assertRaisesRegex(bundle.Refusal, "CONTROL_BUNDLE_LOCK_REQUIRED"):
            bundle.verify(control_root=self.control, launcher=self.launcher)

    def test_captured_ten_member_bundle_upgrades_only_under_original_cas(self):
        prior = self._captured_ten_member_fixture()
        verified = bundle.verify(control_root=self.control, launcher=self.launcher)
        self.assertEqual(set(verified["files"]), set(bundle.CAPTURED_CONTROL_FILES))
        before = self._snapshot()
        with self.assertRaisesRegex(bundle.Refusal, "CONTROL_BUNDLE_CAS_MISMATCH"):
            bundle.install(source=self.source, control_root=self.control,
                           launcher=self.launcher, expected_bundle_digest="0" * 64)
        self.assertEqual(self._snapshot(), before)
        result = bundle.install(source=self.source, control_root=self.control,
                                launcher=self.launcher,
                                expected_bundle_digest=prior["bundleDigest"])
        self.assertEqual(set(result["files"]), EXPECTED_FILES)
        self.assertEqual(bundle.verify(control_root=self.control,
                                      launcher=self.launcher)["bundleDigest"],
                         result["bundleDigest"])

    def test_captured_ten_member_verification_keeps_lock_and_cache_fences(self):
        self._captured_ten_member_fixture()
        cache = self.control / "__pycache__"
        cache.mkdir(mode=0o700)
        (cache / "private_service.fixture.pyc").write_bytes(b"not executable")
        (cache / "private_service.fixture.pyc").chmod(0o600)
        with self.assertRaises(bundle.Refusal):
            bundle.verify(control_root=self.control, launcher=self.launcher)
        shutil.rmtree(cache)
        (self.control / ".control-bundle.lock").unlink()
        with self.assertRaisesRegex(bundle.Refusal, "CONTROL_BUNDLE_LOCK_REQUIRED"):
            bundle.verify(control_root=self.control, launcher=self.launcher)

    def test_formatter_compiler_executes_only_authenticated_captured_bytes(self):
        self._install()
        marker = self.home / "compiler-replacement-executed"
        result = self._child(r"""
path=root/"fleet_git_failure_compat.py"
path.write_text("from pathlib import Path\nPath("+repr(sys.argv[2])+").write_text('unsafe')\n")
owner=svc._fleet_git_failure_compat_module()
assert callable(owner.compile_successor)
assert Path(owner.__file__)==path
assert not Path(sys.argv[2]).exists()
print("authenticated compiler snapshot")
""", marker)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("authenticated compiler snapshot", result.stdout)
        self.assertFalse(marker.exists())
        self._assert_refused()

    def test_actual_payload_installs_exact_closed_runtime(self):
        installed = self._install()
        self.assertEqual(len(bundle.CONTROL_FILES), 63)
        self.assertEqual(len(bundle.REVIEW_CONTROL_FILES), 13)
        self.assertEqual(len(bundle.CAPTURED_CONTROL_FILES), 10)
        self.assertIn("fleet_git_failure_compat.py", bundle.CONTROL_FILES)
        self.assertIn(
            "ops/native_fabric/quota_continuity/rollout/build_review_stage.py",
            bundle.CONTROL_FILES)
        self.assertNotEqual(set(bundle.CONTROL_FILES), set(bundle.CAPTURED_CONTROL_FILES))
        self.assertEqual(set(installed["files"]), EXPECTED_FILES)
        self.assertEqual(set(installed["files"]), set(bundle.CONTROL_FILES))
        import private_service as source_service
        self.assertEqual(set(source_service.CONTROL_BUNDLE_FILES), set(bundle.CONTROL_FILES))
        self.assertEqual(len(source_service.CONTROL_BUNDLE_FILES), 63)
        verified = bundle.verify(control_root=self.control, launcher=self.launcher)
        self.assertEqual(verified["bundleDigest"], installed["bundleDigest"])
        for name, digest in installed["files"].items():
            self.assertEqual(hashlib.sha256((self.control / name).read_bytes()).hexdigest(), digest)
        result = self._child(r"""
mods=[svc._pin_owner_module(),svc._pin_enrollment_owner_module(),
      svc._fleet_status_successor_owner_module(),svc._frozen_paper_fleet_module(),
      svc._fleet_git_failure_compat_module()]
assert {Path(m.__file__).parent for m in mods}=={root}
assert all(Path(m.__file__).is_relative_to(root) for m in mods)
print(json.dumps({"helpers":[Path(m.__file__).name for m in mods]}))
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(json.loads(result.stdout)["helpers"]), {
            "private_service_pin.py", "private_service_pin_enrollment.py",
            "private_service_status_successor.py", "paper_v20_fleet_cohorts.py",
            "fleet_git_failure_compat.py",
        })

    def test_installed_resolvers_reach_real_native_plan_refusal(self):
        self._install()
        result = self._child(r"""
from types import SimpleNamespace
seen=[]
actual=svc.subprocess.run
def record(argv,*args,**kwargs):
    observed=actual(argv,*args,**kwargs)
    seen.append((argv,observed))
    return observed
svc.subprocess.run=record
for account in ("chatgpt1","chatgpt4"):
    args=SimpleNamespace(account=account,operation="status",
        successor_bundle=Path(sys.argv[2]),successor_plan_sha256="0"*64)
    try:
        with svc._pin_native_context(args):
            raise AssertionError("invalid fixture plan must refuse")
    except SystemExit as exc:
        assert str(exc)=="NATIVE_POOL_PIN_SUCCESSOR_REFUSED"
assert len(seen)==2, "actual native proof was not reached"
for argv,observed in seen:
    assert argv[1:4]==["-I","-S","-B"],argv[:5]
    assert Path(argv[6])==root/"ops/native_fabric/quota_continuity/rollout"
    assert observed.returncode!=0
    assert b"invalid launcher successor plan" in observed.stderr,observed.stderr
    assert b"ModuleNotFoundError" not in observed.stderr
print(json.dumps({"real_native_imports":len(seen),"fixture_refusal":"invalid launcher successor plan"}))
""", self.successor)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["real_native_imports"], 2)


    def _assert_refused(self, code="", *args, loader=LOAD, timeout=15, home=None):
        result = self._child(code, *args, loader=loader, timeout=timeout, home=home)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("CONTROL_BUNDLE_CLOSURE_REFUSED", result.stderr)
        return result

    def _snapshot(self):
        rows = {}
        for path in [self.control, *self.control.rglob("*")]:
            relative = str(path.relative_to(self.control))
            info = path.lstat()
            if path.is_symlink():
                value = ("link", os.readlink(path))
            elif path.is_dir():
                value = ("directory",)
            else:
                value = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
            rows[relative] = (info.st_mode & 0o777, *value)
        return rows

    def test_every_member_hash_is_checked_before_loading_helpers(self):
        self._install()
        marker = self.home / "must-not-execute"
        for name in sorted(EXPECTED_FILES):
            with self.subTest(name=name):
                path = self.control / name
                before = path.read_bytes()
                try:
                    path.write_bytes(before + b"\n# unsealed fixture change\n")
                    self._assert_refused(
                        f"Path({str(marker)!r}).write_text('guard bypassed')\n")
                    self.assertFalse(marker.exists())
                finally:
                    path.write_bytes(before)

    def test_every_missing_member_refuses_without_source_fallback(self):
        self._install()
        for name in sorted(EXPECTED_FILES):
            with self.subTest(name=name):
                path = self.control / name
                before = path.read_bytes()
                try:
                    path.unlink()
                    result = self._child("raise AssertionError('missing closure accepted')")
                    self.assertNotEqual(result.returncode, 0)
                    expected = ("FileNotFoundError" if name == "private_service.py"
                                else "CONTROL_BUNDLE_CLOSURE_REFUSED")
                    self.assertIn(expected, result.stderr)
                finally:
                    path.write_bytes(before)
                    path.chmod(0o600)

    def test_missing_manifest_or_lock_refuses_without_creating_state(self):
        self._install()
        for name in ("manifest.json", ".control-bundle.lock"):
            with self.subTest(name=name):
                path = self.control / name
                before = path.read_bytes()
                try:
                    path.unlink()
                    snapshot = self._snapshot()
                    self._assert_refused()
                    self.assertEqual(self._snapshot(), snapshot)
                finally:
                    path.write_bytes(before)
                    path.chmod(0o600)

    def test_legacy_manifest_membership_cannot_admit_new_runtime(self):
        self._install()
        path = self.control / "manifest.json"
        raw = path.read_bytes()
        for names in (bundle.LEGACY_CONTROL_FILES, bundle.STATUS_CONTROL_FILES,
                      bundle.CAPTURED_CONTROL_FILES, bundle.REVIEW_CONTROL_FILES):
            with self.subTest(members=len(names)):
                manifest = json.loads(raw)
                manifest["files"] = {name: manifest["files"][name] for name in names}
                manifest["bundleDigest"] = bundle._bundle_digest(
                    manifest["files"], manifest["launcherHash"])
                path.write_text(json.dumps(manifest))
                self._assert_refused()
        path.write_bytes(raw)

    def test_malformed_manifest_and_launcher_binding_refuse(self):
        self._install()
        path = self.control / "manifest.json"
        raw = path.read_bytes()
        changes = (
            lambda value: value.update(schema="other"),
            lambda value: value.update(bundleDigest="0" * 64),
            lambda value: value.update(files=[]),
            lambda value: value["files"].update({"../outside.py": "0" * 64}),
            lambda value: value["files"].update({"private_service_pin.py": "x" * 64}),
            lambda value: value.update(launcher=str(self.home / "other-launcher")),
            lambda value: value.update(source="relative/source"),
        )
        for index, change in enumerate(changes):
            with self.subTest(index=index):
                value = json.loads(raw)
                change(value)
                path.write_text(json.dumps(value))
                self._assert_refused()
        value = json.loads(raw)
        encoded = json.dumps(value)
        path.write_text(encoded[:-1] + ',"schema":' + json.dumps(value["schema"]) + "}")
        self._assert_refused()
        path.write_bytes(raw)
        self.launcher.write_text("#!/bin/sh\n# changed launcher\nexit 0\n")
        self._assert_refused()

    def test_metadata_source_cannot_supply_a_missing_helper(self):
        self._install()
        marker = self.home / "source-fallback-executed"
        decoy = self.home / "unmanaged-source"
        decoy.mkdir(mode=0o700)
        (decoy / "private_service_pin.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('unsafe')\n")
        manifest_path = self.control / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["source"] = str(decoy)
        manifest_path.write_text(json.dumps(manifest))
        (self.control / "private_service_pin.py").unlink()
        self._assert_refused("svc._pin_owner_module()")
        self.assertFalse(marker.exists())

    def test_member_symlink_and_unsafe_file_mode_refuse(self):
        self._install()
        path = self.control / "private_service_pin.py"
        before = path.read_bytes()
        target = self.home / "unmanaged-pin.py"
        target.write_bytes(before)
        target.chmod(0o600)
        path.unlink()
        path.symlink_to(target)
        self._assert_refused()
        path.unlink()
        path.write_bytes(before)
        path.chmod(0o644)
        self._assert_refused()

    def test_native_parent_symlink_or_unsafe_directory_refuses(self):
        self._install()
        path = self.control / "ops/fabric_launch"
        saved = self.home / "saved-fabric-launch"
        path.rename(saved)
        path.symlink_to(saved, target_is_directory=True)
        self._assert_refused()
        path.unlink()
        saved.rename(path)
        path.chmod(0o755)
        self._assert_refused()

    def test_unsealed_native_initializers_modules_and_bytecode_refuse(self):
        self._install()
        marker = self.home / "unsealed-import-executed"
        names = (
            "argparse.py", "ops.py", "ops/__init__.py",
            "ops/fabric_launch/__init__.py",
            "ops/native_fabric/quota_continuity/rollout/native_install.pyc",
            "ops/native_fabric/quota_continuity/rollout/__pycache__/native_install.fixture.pyc",
        )
        for name in names:
            with self.subTest(name=name):
                path = self.control / name
                made_parent = not path.parent.exists()
                if made_parent:
                    path.parent.mkdir(mode=0o700)
                path.write_text(
                    f"from pathlib import Path\nPath({str(marker)!r}).write_text('unsafe')\n")
                path.chmod(0o600)
                try:
                    self._assert_refused()
                    self.assertFalse(marker.exists())
                finally:
                    path.unlink()
                    if made_parent:
                        path.parent.rmdir()

    def test_alias_to_installed_bootstrap_cannot_select_source_mode(self):
        self._install()
        alias = self.home / "alias-private-service.py"
        alias.symlink_to(self.control / "private_service.py")
        loader = LOAD.replace('root/"private_service.py"', "Path(sys.argv[2])")
        self._assert_refused("svc._pin_owner_module();print('unqualified alias accepted')",
                             alias, loader=loader)

    def test_noncanonical_case_cannot_select_source_mode(self):
        self._install()
        alias_root = self.control.with_name("CONTROL")
        created = not alias_root.exists()
        if created:
            alias_root.symlink_to(self.control, target_is_directory=True)
        try:
            loader = LOAD.replace('root/"private_service.py"', "Path(sys.argv[2])")
            self._assert_refused("svc._pin_owner_module();print('unqualified case accepted')",
                                 alias_root / "private_service.py", loader=loader)
        finally:
            if created:
                alias_root.unlink()

    def test_installed_path_symlink_to_checkout_never_becomes_source_mode(self):
        self._install()
        path = self.control / "private_service.py"
        path.unlink()
        path.symlink_to(HERE / "private_service.py")
        self._assert_refused()

    def test_loader_executes_authenticated_snapshot_after_path_replacement(self):
        self._install()
        marker = self.home / "replacement-executed"
        result = self._child(r"""
path=root/"private_service_pin.py"
path.write_text("from pathlib import Path\nPath("+repr(sys.argv[2])+").write_text('unsafe')\n")
owner=svc._pin_owner_module()
assert callable(owner.run)
assert Path(owner.__file__)==path
assert not Path(sys.argv[2]).exists()
print("authenticated snapshot")
""", marker)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("authenticated snapshot", result.stdout)
        self.assertFalse(marker.exists())
        self._assert_refused()

    def test_failed_registered_helper_restores_previous_module(self):
        self._install()
        result = self._child(r"""
name="_studio_status_successor_owner"
previous=object()
sys.modules[name]=previous
svc._INSTALLED_CONTROL_CONTEXT["files"]["private_service_status_successor.py"]=b"raise RuntimeError('fixture import failure')"
try:
    svc._fleet_status_successor_owner_module()
except RuntimeError as exc:
    assert str(exc)=="fixture import failure"
else:
    raise AssertionError("fixture failure did not propagate")
assert sys.modules[name] is previous
print("registration restored")
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("registration restored", result.stdout)

    def test_installed_invocation_holds_existing_owner_lock_until_exit(self):
        self._install()
        code = LOAD + 'print("READY",flush=True)\nsys.stdin.readline()\n'
        process = subprocess.Popen(
            [sys.executable, "-I", "-S", "-B", "-c", code, str(self.control)],
            cwd=self.empty, env={"HOME": str(self.home), "PATH": "/usr/bin:/bin", "LANG": "C"},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            ready, _, _ = select.select([process.stdout], [], [], 5)
            self.assertTrue(ready, "fixture loader did not become ready")
            self.assertEqual(process.stdout.readline().strip(), "READY")
            before = self._snapshot()
            with self.assertRaisesRegex(bundle.Refusal, "CONTROL_BUNDLE_BUSY"):
                self._install()
            self.assertEqual(self._snapshot(), before)
        finally:
            try:
                stdout, stderr = process.communicate("release\n", timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, stderr)
        self.assertEqual(self._install()["state"], "CONTROL_BUNDLE_INSTALLED")

    def test_actual_native_import_origins_stay_inside_owned_payload(self):
        self._install()
        result = self._child(r"""
code=""" + "'''" + r"""
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import native_install as i
import native_generation as g
import ops
print(json.dumps({"paths":[i.__file__,g.__file__,i.studio_consumer_owner.__file__],
                  "namespace":list(ops.__path__)}))
""" + "'''" + r"""
rollout=root/"ops/native_fabric/quota_continuity/rollout"
observed=svc.subprocess.run([sys.executable,"-I","-S","-B","-c",code,str(rollout)],
                          capture_output=True,text=True,timeout=10)
assert observed.returncode==0,observed.stderr
value=json.loads(observed.stdout)
assert set(map(Path,value["paths"]))=={
    rollout/"native_install.py",rollout/"native_generation.py",root/"ops/fabric_launch/install.py"}
assert list(map(Path,value["namespace"]))==[root/"ops"]
print(json.dumps(value))
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)["paths"]), 3)


    def test_changed_home_cannot_reclassify_an_installed_helper(self):
        self._install()
        other_home = self.root / "other-home"
        other_home.mkdir(mode=0o700)
        self._assert_refused("svc._pin_owner_module()", home=other_home)

    def test_fifo_lock_refuses_without_waiting_for_a_writer(self):
        self._install()
        lock = self.control / ".control-bundle.lock"
        lock.unlink()
        os.mkfifo(lock, 0o600)
        try:
            self._assert_refused(timeout=2)
        except subprocess.TimeoutExpired:
            self.fail("installed lock open blocked on a FIFO before validation")

    def _entrypoint(self, name, timeout=10):
        return subprocess.run(
            [sys.executable, "-S", str(self.control / name), "--help"],
            cwd=self.empty, env={"HOME": str(self.home), "PATH": "/usr/bin:/bin", "LANG": "C"},
            capture_output=True, text=True, timeout=timeout,
        )

    def test_real_entrypoints_do_not_execute_adjacent_shadow_modules(self):
        self._install()
        marker = self.home / "shadow-executed"
        shadow = self.control / "json.py"
        shadow.write_text(
            "import posix\n"
            f"fd=posix.open({str(marker)!r},posix.O_WRONLY|posix.O_CREAT,0o600)\n"
            "posix.close(fd)\nraise RuntimeError('unsealed json executed')\n")
        shadow.chmod(0o600)
        for name in ("private_service.py", "private_tunnel_service.py", "studio_direct_control.py"):
            with self.subTest(entrypoint=name):
                result = self._entrypoint(name)
                self.assertFalse(marker.exists(), result.stderr)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("CONTROL_BUNDLE_CLOSURE_REFUSED", result.stderr)

    def test_matching_private_service_bytecode_never_executes(self):
        self._install()
        source = self.control / "private_service.py"
        original = source.read_bytes()
        original_stat = source.stat()
        marker = self.home / "matching-cache-executed"
        malicious = (
            "import posix\n"
            f"fd=posix.open({str(marker)!r},posix.O_WRONLY|posix.O_CREAT,0o600)\n"
            "posix.close(fd)\nraise RuntimeError('matching unsealed cache executed')\n"
        ).encode()
        self.assertLess(len(malicious), len(original))
        source.write_bytes(malicious + b"#" * (len(original) - len(malicious)))
        os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        saved_prefix = sys.pycache_prefix
        sys.pycache_prefix = None
        try:
            cache = Path(importlib.util.cache_from_source(str(source)))
            self.assertEqual(Path(py_compile.compile(
                str(source), cfile=str(cache), doraise=True,
                invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)), cache)
        finally:
            sys.pycache_prefix = saved_prefix
        self.assertIn(sys.implementation.cache_tag, cache.name)
        self.assertTrue(cache.is_file())
        loader = importlib.machinery.SourceFileLoader("fixture_private_service", str(source))
        self.assertEqual(loader.path_stats(str(source))["mtime"], original_stat.st_mtime)
        raw = cache.read_bytes()
        self.assertEqual(raw[:4], importlib.util.MAGIC_NUMBER)
        self.assertEqual(int.from_bytes(raw[4:8], "little"), 0)
        self.assertEqual(int.from_bytes(raw[8:12], "little"), int(original_stat.st_mtime))
        self.assertEqual(int.from_bytes(raw[12:16], "little"), len(original))
        code = loader.get_code("fixture_private_service")
        self.assertIsInstance(code, type((lambda: None).__code__))
        self.assertEqual(code.co_filename, str(source))
        source.write_bytes(original)
        os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        cache.chmod(0o600)
        self.assertEqual(source.stat().st_size, original_stat.st_size)
        result = self._entrypoint("private_tunnel_service.py")
        self.assertFalse(marker.exists(), result.stderr)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("CONTROL_BUNDLE_CLOSURE_REFUSED", result.stderr)

    def test_exact_inert_historical_backup_is_retained_but_never_trusted_as_code(self):
        import private_service as svc
        self._install()
        name = "private_service.py.pre-exact-legacy-manifests-20261022"
        blob = b"fixture historical source; never an executable dependency\n"
        pinned = hashlib.sha256(blob).hexdigest()
        backup = self.control / name
        backup.write_bytes(blob)
        backup.chmod(0o600)
        with mock.patch.dict(bundle.HISTORICAL_CONTROL_BACKUPS, {name: pinned}, clear=True), \
             mock.patch.dict(svc.HISTORICAL_CONTROL_BACKUPS, {name: pinned}, clear=True), \
             mock.patch.object(svc, "_user_root", return_value=self.home):
            verified = bundle.verify(control_root=self.control, launcher=self.launcher)
            self.assertEqual(set(verified["files"]), EXPECTED_FILES)
            svc._installed_control_layout(self.control)
            installed = self._install()
            self.assertEqual(installed["state"], "CONTROL_BUNDLE_INSTALLED")
            self.assertEqual(backup.read_bytes(), blob)
            self.assertEqual(set(json.loads((self.control / "manifest.json").read_bytes())["files"]),
                             EXPECTED_FILES)
            backup.write_bytes(blob + b"tamper")
            with self.assertRaisesRegex(bundle.Refusal, "CONTROL_BUNDLE_HISTORICAL_BACKUP_CHANGED"):
                bundle.verify(control_root=self.control, launcher=self.launcher)
            with self.assertRaisesRegex(ValueError, "unsealed installed historical backup"):
                svc._installed_control_layout(self.control)
            backup.write_bytes(blob)
            unknown = self.control / "private_service.py.pre-unrecognized-backup"
            unknown.write_bytes(b"foreign")
            unknown.chmod(0o600)
            with self.assertRaisesRegex(bundle.Refusal, "CONTROL_BUNDLE_CONTENTS_INVALID"):
                bundle.verify(control_root=self.control, launcher=self.launcher)
            with self.assertRaisesRegex(ValueError, "unsealed installed control path"):
                svc._installed_control_layout(self.control)

    def test_installer_removes_prior_bootstrap_caches_under_its_lock(self):
        self._install()
        source = self.control / "private_service.py"
        saved_prefix = sys.pycache_prefix
        sys.pycache_prefix = None
        try:
            cache_file = Path(importlib.util.cache_from_source(str(source)))
            self.assertEqual(Path(py_compile.compile(
                str(source), cfile=str(cache_file), doraise=True)), cache_file)
        finally:
            sys.pycache_prefix = saved_prefix
        self.assertIn(sys.implementation.cache_tag, cache_file.name)
        self.assertTrue(cache_file.is_file())
        cache = self.control / "__pycache__"
        self.assertTrue(cache.is_dir())
        installed = self._install()
        self.assertEqual(installed["state"], "CONTROL_BUNDLE_INSTALLED")
        self.assertFalse(cache.exists())
        for name in ("private_service.py", "private_tunnel_service.py", "studio_direct_control.py"):
            with self.subTest(entrypoint=name):
                result = self._entrypoint(name)
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(cache.exists())

    def test_stage_cleanup_failure_preserves_postwrite_effect_unknown(self):
        self._install()
        calls = []
        actual = shutil.rmtree

        def fail_stage(path, *args, **kwargs):
            if Path(path).name.startswith(".control-bundle.stage-"):
                calls.append(Path(path))
                raise OSError("fixture persistent stage cleanup failure")
            return actual(path, *args, **kwargs)

        with mock.patch.object(bundle.shutil, "rmtree", side_effect=fail_stage):
            with self.assertRaisesRegex(bundle.EffectUnknown, "CONTROL_BUNDLE_EFFECT_UNKNOWN"):
                self._install()
        self.assertEqual(len(calls), 1, "cleanup must not blind-retry the same stage")
        self.assertTrue(calls[0].is_dir(), "uncertain stage remains available for reconciliation")
        self.assertEqual(set(json.loads((self.control / "manifest.json").read_text())["files"]),
                         EXPECTED_FILES)

    def test_symlinked_control_ancestor_refuses_before_installed_writes(self):
        self._install()
        original_parent = self.control.parent
        saved = self.home / "saved-control-parent"
        original_parent.rename(saved)
        original_parent.symlink_to(saved, target_is_directory=True)
        before = self._snapshot()
        with self.assertRaises(bundle.Refusal):
            self._install()
        self.assertEqual(self._snapshot(), before)

    def test_unsafe_launcher_ancestor_refuses_before_installed_writes(self):
        self._install()
        self.launcher.parent.chmod(0o777)
        before = self._snapshot()
        try:
            with self.assertRaises(bundle.Refusal):
                self._install()
            self.assertEqual(self._snapshot(), before)
        finally:
            self.launcher.parent.chmod(0o700)

    def test_standalone_verification_obeys_existing_writer_lock(self):
        self._install()
        before = self._snapshot()
        with bundle._lock(self.control):
            with self.assertRaisesRegex(bundle.Refusal, "CONTROL_BUNDLE_BUSY"):
                bundle.verify(control_root=self.control, launcher=self.launcher)
        self.assertEqual(self._snapshot(), before)


    def test_bootstrap_loaders_refuse_symlink_before_executing_bytes(self):
        self._install()
        marker = self.home / "linked-bootstrap-executed"
        decoy = self.home / "unmanaged-bootstrap.py"
        decoy.write_text(
            "import posix\n"
            f"fd=posix.open({str(marker)!r},posix.O_WRONLY|posix.O_CREAT,0o600)\n"
            "posix.close(fd)\nraise RuntimeError('unmanaged bootstrap executed')\n")
        decoy.chmod(0o600)
        bootstrap = self.control / "private_service.py"
        bootstrap.unlink()
        bootstrap.symlink_to(decoy)
        for name in ("private_tunnel_service.py", "studio_direct_control.py"):
            with self.subTest(entrypoint=name):
                result = self._entrypoint(name)
                self.assertFalse(marker.exists(), result.stderr)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("CONTROL_BUNDLE_CLOSURE_REFUSED", result.stderr)

    def test_bootstrap_loaders_refuse_fifo_without_blocking(self):
        self._install()
        bootstrap = self.control / "private_service.py"
        bootstrap.unlink()
        os.mkfifo(bootstrap, 0o600)
        for name in ("private_tunnel_service.py", "studio_direct_control.py"):
            with self.subTest(entrypoint=name):
                try:
                    result = self._entrypoint(name, timeout=2)
                except subprocess.TimeoutExpired:
                    self.fail("fixed bootstrap reader blocked on an unsealed FIFO")
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("CONTROL_BUNDLE_CLOSURE_REFUSED", result.stderr)


    def test_source_cli_and_imported_resolvers_remain_usable(self):
        for name in ("private_service.py", "private_tunnel_service.py", "studio_direct_control.py"):
            with self.subTest(entrypoint=name):
                result = subprocess.run(
                    [sys.executable, "-S", str(HERE / name), "--help"],
                    cwd=self.empty,
                    env={"HOME": str(self.home), "PATH": "/usr/bin:/bin", "LANG": "C"},
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
        # The frozen-Paper source resolver shares the owned, exact-byte checkout.
        loader = LOAD.replace('root/"private_service.py"', "Path(sys.argv[2])")
        result = self._child(
            'assert svc._INSTALLED_CONTROL_CONTEXT is None\n'
            'mods=[svc._pin_owner_module(),svc._pin_enrollment_owner_module(),'
            'svc._fleet_status_successor_owner_module(),svc._frozen_paper_fleet_module()]\n'
            'assert all(Path(m.__file__).parent==Path(sys.argv[2]).parent for m in mods)\n',
            self.source / "private_service.py", loader=loader)
        self.assertEqual(result.returncode, 0, result.stderr)


    def test_lockless_legacy_verify_cannot_admit_a_concurrent_current_upgrade(self):
        self._install()
        manifest_path = self.control / "manifest.json"
        legacy = json.loads(manifest_path.read_text())
        legacy["files"] = {name: legacy["files"][name] for name in bundle.LEGACY_CONTROL_FILES}
        legacy["bundleDigest"] = bundle._bundle_digest(legacy["files"], legacy["launcherHash"])
        manifest_path.write_text(json.dumps(legacy))
        for name in EXPECTED_FILES - set(bundle.LEGACY_CONTROL_FILES):
            (self.control / name).unlink()
        for path in sorted(self.control.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        (self.control / ".control-bundle.lock").unlink()
        actual = bundle._read_manifest
        transitions = []

        def install_between_reads(path):
            observed = actual(path)
            if not transitions:
                transitions.append("legacy-to-current")
                self.assertEqual(set(self._install()["files"]), EXPECTED_FILES)
            return observed

        with mock.patch.object(bundle, "_read_manifest", side_effect=install_between_reads):
            with self.assertRaisesRegex(bundle.Refusal, "CONTROL_BUNDLE_CHANGED"):
                bundle.verify(control_root=self.control, launcher=self.launcher)
        self.assertEqual(transitions, ["legacy-to-current"])
        self.assertTrue((self.control / ".control-bundle.lock").is_file())
        self.assertEqual(set(bundle.verify(
            control_root=self.control, launcher=self.launcher)["files"]), EXPECTED_FILES)


if __name__ == "__main__":
    unittest.main()
