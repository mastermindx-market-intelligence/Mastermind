"""Actual namespace/hash/currentness with explicit ownership and ACL doubles.

These fixtures do not claim privileged Darwin installation or live enrollment.
"""
import hashlib
import importlib
import json
import os
from pathlib import Path
import plistlib
import stat
import sys
import tempfile
from types import SimpleNamespace, ModuleType
import unittest
from unittest.mock import patch

from integrations.hermes_application_fabric import source_context as source
from integrations.hermes_application_fabric.errors import HermesFabricError
from ops.executive_os import capacity_host_artifacts as artifacts


class AttendedSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.base.chmod(0o755)
        self.system = self.base / "Executive"
        self.root = self.system / "releases" / ("a" * 40)
        self.root.mkdir(parents=True)
        self.config = self.system / "config"
        self.config.mkdir()
        for directory in (self.system, self.system / "releases", self.config):
            directory.chmod(0o755)
        self.control = self.config / "control.json"
        self.control.write_text('{"fixture_private_control":true}\n')
        self.control.chmod(0o440)
        self.control_inode = (self.control.stat().st_dev, self.control.stat().st_ino)
        self.plist = self.base / "control.plist"
        self.plist.write_bytes(plistlib.dumps({
            "Label": "com.mastermind.executive.control", "WorkingDirectory": str(self.root),
            "ProgramArguments": ["/fixture/python", "--release-root", str(self.root)]}))
        self.plist.chmod(0o644)
        real_os = os
        ancestor_ids = {(p.stat().st_dev, p.stat().st_ino) for p in self.base.parents}
        def mapped(info):
            fields = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
            fields.update(st_uid=0, st_gid=450 if (info.st_dev, info.st_ino) == self.control_inode else 0)
            if (info.st_dev, info.st_ino) in ancestor_ids:
                fields["st_mode"] = stat.S_IFDIR | 0o755
            return SimpleNamespace(**fields)
        class Proxy:
            def __getattr__(self, name):
                return getattr(real_os, name)
            def fstat(self, fd):
                return mapped(real_os.fstat(fd))
            def stat(self, *args, **kwargs):
                return mapped(real_os.stat(*args, **kwargs))
        self.proxy = Proxy()
        observation = {
            "schema": "mastermind.control_observation/v1", "source_release_sha": self.root.name,
            "control_sha256": hashlib.sha256(self.control.read_bytes()).hexdigest(),
            "control_identity": list(source._identity(mapped(self.control.stat()))),
            "control_uid": 450, "python_runtime_provenance_digest": "1" * 64, "control_acl_absent": True}
        self.observation = self.config / "control-observation.json"
        self.observation.write_bytes(artifacts.canonical_json(observation) + b"\n")
        self.observation.chmod(0o444)
        projection = self.root / source._PROJECTION
        payloads = {
            "config/owner.json": b"{}\n",
            "engine/__init__.py": b"",
            "engine/provider_production_modes.py": (
                b"from lib import VALUE\n"
                b"def make_application_fabric_factory(**kwargs):\n"
                b"    return dict(value=VALUE, **kwargs)\n"),
            "lib/__init__.py": b"VALUE = 42\n",
        }
        rows = []
        for relative, raw in payloads.items():
            path = projection / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            path.chmod(0o644)
            rows.append({"path": relative, "mode": "100644", "size": len(raw),
                         "sha256": hashlib.sha256(raw).hexdigest(), "git_blob": "2" * 40})
        expected = {"schema": artifacts.HERMES_ATTENDED_PROJECTION_SCHEMA,
                    "repository": "mastermindx-market-intelligence/macro", "commit": "c" * 40,
                    "tree": "d" * 40, "projection": "engine-lib-config/v1",
                    "material_manifest_sha256": "e" * 64, "archive_sha256": "f" * 64, "archive_size": 1}
        inventory, receipt = artifacts._attended_installed_records(
            expected, {"material": sorted(rows, key=lambda row: row["path"])}, self.root, "b" * 64)
        files = {
            source._INVENTORY: inventory, source._RECEIPT: artifacts.canonical_json(receipt) + b"\n",
            source._COMMITMENT: artifacts.canonical_json(expected) + b"\n",
            source._VERIFIER: (Path(artifacts.__file__).parent / "native_gateway_sources.py").read_bytes(),
        }
        for relative, raw in files.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            path.chmod(0o644)
        entries = []
        for path in sorted(self.root.rglob("*")):
            if path.is_dir():
                path.chmod(0o755)
            else:
                entries.append({"path": path.relative_to(self.root).as_posix(), "type": "file",
                                "mode": stat.S_IMODE(path.stat().st_mode), "uid": 0, "gid": 0,
                                "size": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        (self.root / source._MANIFEST).write_bytes(artifacts.canonical_json({
            "schema_version": "mastermind.executive_release_manifest/v1",
            "commit_sha": self.root.name, "tree_sha": "9" * 40, "entries": entries}) + b"\n")
        (self.root / source._MANIFEST).chmod(0o444)
        self.root.chmod(0o755)
        self.saved_modules = {name: module for name, module in tuple(sys.modules.items())
                              if name in {"engine", "lib"} or name.startswith(("engine.", "lib."))}
        for name in self.saved_modules:
            del sys.modules[name]
        self.addCleanup(self.restore)
        self.patches = [
            patch.object(source, "os", self.proxy),
            patch.object(source, "_SYSTEM", self.system), patch.object(source, "_CONTROL", self.control),
            patch.object(source, "_OBSERVATION", self.observation), patch.object(source, "_PLIST", self.plist),
            patch.object(source, "_no_acl", lambda *_: None), patch.object(source.sys, "platform", "darwin")]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.leases = []

    def restore(self):
        for lease in reversed(self.leases):
            lease.close()
        for name in tuple(sys.modules):
            if name in {"engine", "lib"} or name.startswith(("engine.", "lib.")):
                del sys.modules[name]
        sys.modules.update(self.saved_modules)
        self.assertIsNone(source._SHARED)

    def open(self):
        # The existing closure receives the same explicit metadata double.
        with patch.dict(sys.modules, {"os": self.proxy}):
            lease = source.open_attended_source_context(adapter_package_sha256="b" * 64)
        self.leases.append(lease)
        return lease

    def test_canonical_factory_imports_only_verified_sources_and_writes_no_bytecode(self):
        lease = self.open()
        result = lease.factory()
        self.assertEqual((result["value"], result["root"]), (42, self.root / source._PROJECTION))
        self.assertIs(sys.modules["engine.provider_production_modes"],
                      lease._context.modules["engine.provider_production_modes"])
        self.assertFalse(list((self.root / source._PROJECTION).rglob("__pycache__")))
        self.assertNotIn(self.control, lease._context.owner.records)

    def test_concurrent_first_imports_preserve_one_canonical_factory_module(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        lease = self.open()
        barrier = Barrier(2)
        def invoke():
            barrier.wait(timeout=5)
            return lease.factory()["value"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(invoke) for _ in range(2)]
            self.assertEqual([future.result(timeout=5) for future in futures], [42, 42])
        self.assertEqual(lease._context.references, 1)
        self.assertIs(sys.modules["engine.provider_production_modes"],
                      lease._context.modules["engine.provider_production_modes"])

    def test_source_mutation_revokes_the_existing_context(self):
        lease = self.open()
        lease.factory()
        (self.root / source._PROJECTION / "lib/__init__.py").write_text("VALUE = 43\n")
        with self.assertRaises(Exception):
            lease.check()

    def test_operation_survives_plugin_release_and_closes_after_original_operation(self):
        plugin = self.open()
        context = plugin._context
        with plugin.operation() as operation:
            plugin.close()
            self.assertFalse(context.closed)
            self.assertEqual(operation.factory()["value"], 42)
        self.assertTrue(context.closed)
        self.assertIsNone(source._SHARED)

    def test_foreign_canonical_namespace_is_not_adopted_or_deleted(self):
        foreign = ModuleType("engine")
        sys.modules["engine"] = foreign
        with self.assertRaises(HermesFabricError):
            self.open()
        self.assertIs(sys.modules["engine"], foreign)
        self.assertIsNone(source._SHARED)

    def test_reload_cannot_recreate_factory_classes_in_a_retained_context(self):
        lease = self.open()
        lease.factory()
        module = sys.modules["engine.provider_production_modes"]
        with self.assertRaises(HermesFabricError):
            importlib.reload(module)
        self.assertIs(sys.modules["engine.provider_production_modes"], module)

    def test_new_selection_refuses_without_replacing_a_retained_source(self):
        lease = self.open()
        original = source._SHARED
        raw = json.loads(self.observation.read_bytes())
        raw["source_release_sha"] = "3" * 40
        successor = self.observation.with_name("next-observation.json")
        successor.write_bytes(artifacts.canonical_json(raw) + b"\n")
        successor.chmod(0o444)
        successor.replace(self.observation)
        with self.assertRaises(HermesFabricError):
            self.open()
        self.assertIs(source._SHARED, original)
        self.assertEqual(original.references, 1)

    def test_same_release_control_renewal_retains_code_and_freezes_original_operation(self):
        plugin = self.open()
        with plugin.operation() as original:
            first = original.factory()
            module = sys.modules["engine.provider_production_modes"]
            pending = self.config / ".next-control"
            pending.write_text('{"fixture_private_control":"renewed"}\n')
            pending.chmod(0o440)
            os.replace(pending, self.control)
            self.control_inode = (self.control.stat().st_dev, self.control.stat().st_ino)
            public = json.loads(self.observation.read_bytes())
            public["control_identity"] = list(source._identity(self.proxy.stat(self.control)))
            public["control_sha256"] = hashlib.sha256(self.control.read_bytes()).hexdigest()
            pending = self.config / ".next-observation"
            pending.write_bytes(artifacts.canonical_json(public) + b"\n")
            pending.chmod(0o444)
            os.replace(pending, self.observation)
            with self.assertRaises(HermesFabricError):
                original.check()
            with plugin.operation() as renewed:
                self.assertEqual(first, renewed.factory())
                self.assertIs(sys.modules["engine.provider_production_modes"], module)
                renewed.check()
        plugin.check()

    def test_changed_sealed_verifier_never_executes(self):
        (self.root / source._VERIFIER).write_text('raise AssertionError("executed changed verifier")\n')
        with self.assertRaises(HermesFabricError):
            self.open()
        self.assertIsNone(source._SHARED)

    def test_first_acquisition_failure_closes_before_singleton_publication(self):
        candidate = SimpleNamespace(references=0, check=lambda: (_ for _ in ()).throw(ValueError()),
                                    close=unittest.mock.Mock())
        with patch.object(source, "_SourceContext", return_value=candidate):
            with self.assertRaises(HermesFabricError):
                self.open()
        candidate.close.assert_called_once()
        self.assertIsNone(source._SHARED)

    def test_installed_package_reader_rejects_fifo_and_oversized_input(self):
        path = self.base / "input"
        path.write_bytes(b"x" * 17)
        with self.assertRaises(HermesFabricError):
            source._package_read(path, 16)
        path.unlink()
        os.mkfifo(path)
        with self.assertRaises(HermesFabricError):
            source._package_read(path, 16)


if __name__ == "__main__":
    unittest.main()
