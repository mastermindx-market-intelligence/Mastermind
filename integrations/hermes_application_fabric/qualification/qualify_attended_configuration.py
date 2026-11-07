"""Installed adapter + exact Macro source + renewable consumer configuration.

Run with an actual PM-built adapter environment and -I -B. Root ownership,
Control publication and ACL metadata are explicit fixtures; provider grants
are eligibility fixtures. This does not claim privileged/live acceptance.
"""
import argparse
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil
import socket
import stat
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--mastermind-root", type=Path, required=True)
parser.add_argument("--macro-archive", type=Path, required=True)
args = parser.parse_args()
from integrations.hermes_application_fabric import source_context as source
package = Path(source.__file__).resolve().parent
assert not package.is_relative_to(args.mastermind_root.resolve())
assert str(args.mastermind_root) not in sys.path
package_digest = source.attended_package_digest()
commitment = json.loads((package / "macro-source.json").read_bytes())
saved_path = list(sys.path)
spec = importlib.util.spec_from_file_location(
    "_qualification_capacity_artifacts",
    args.mastermind_root / "ops/executive_os/capacity_host_artifacts.py")
artifacts = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = artifacts
spec.loader.exec_module(artifacts)
configuration = artifacts._attended_configuration_owner()
sys.path[:] = saved_path
assert str(args.mastermind_root) not in sys.path
assert not any(n in {"engine", "lib"} or n.startswith(("engine.", "lib.")) for n in sys.modules)


def eligibility(automatic):
    now = time.time()
    value = {
        "schema": configuration.OBSERVATION_SCHEMA,
        "enrollment": {
            "owner": "native_go_service_enrollment",
            "schema": "native-go-service-enrollment-completed.v9",
            "operation_id": "fixture-hermes-attended",
            "plan_digest": "2" * 64, "source_generation": "3" * 64,
            "ingress_digest": "4" * 64,
        },
        "selected_source": {
            "generation": "3" * 64, "ingress_sha256": "4" * 64,
            "selection": {"fixture": True},
        },
        "scope": {
            "service_profile": "hermes-attended", "principal_id": "hermes-attended",
            "caller_host": "fixture-attended-host", "native_host": "fixture-native-host",
            "workload": "hermes_attended", "workload_profile": "hermes_attended",
            "credential_ref": "HERMES_ATTENDED_FABRIC_APPLICATION_TOKEN",
            "capability_lane": "hermes-attended",
        },
        "selection": ({"kind": "auto", "route_scope": {
            "schema": "mastermind.application_route_scope.v1", "pools": ["go"]}}
            if automatic else {"kind": "fixed", "pool": "go"}),
        "eligibility": {
            "observed_at": now, "qualified_until": now + 600,
            "routes": [{"pool": "go", "model": "glm-5.3-flash",
                        "grant_id": "fixture-current-grant", "grant_sha256": "5" * 64,
                        "expires_at": now + 600, "qualification_ref": "fixture-qualification",
                        "application_permission_ref": "fixture-application-permission"}],
        },
        "authority": {
            "grant_issued": False, "credential_included": False,
            "capacity_reserved": False, "provider_readiness_proven": False,
            "admission_required": True,
        },
    }
    return {**value, "observation_sha256": hashlib.sha256(configuration.canonical(value)).hexdigest()}


with tempfile.TemporaryDirectory(prefix="mmx-real-attended-configuration-") as temporary:
    base = Path(temporary).resolve()
    base.chmod(0o755)
    system = base / "Executive"
    root = system / "releases" / ("a" * 40)
    root.mkdir(parents=True)
    config = system / "config"
    config.mkdir()
    for directory in (system, system / "releases", config):
        directory.chmod(0o755)
    control = config / "control.json"
    observation = config / "control-observation.json"
    control_inode = None
    real_os = os
    ancestor_ids = {(p.stat().st_dev, p.stat().st_ino) for p in base.parents}
    def mapped(info):
        fields = {key: getattr(info, key) for key in dir(info) if key.startswith("st_")}
        fields.update(st_uid=0, st_gid=450 if (info.st_dev, info.st_ino) == control_inode else 0)
        if (info.st_dev, info.st_ino) in ancestor_ids:
            fields["st_mode"] = stat.S_IFDIR | 0o755
        return SimpleNamespace(**fields)
    class Proxy:
        def __getattr__(self, name):
            return getattr(real_os, name)
        def fstat(self, fd):
            return mapped(real_os.fstat(fd))
        def stat(self, *a, **kw):
            return mapped(real_os.stat(*a, **kw))
    proxy = Proxy()
    def select(digest):
        global control_inode
        private = {"fixture_private_control": True}
        if digest is not None:
            private[configuration.CONTROL_FIELD] = digest
        raw = artifacts.canonical_json(private) + b"\n"
        pending = config / ".fixture-control"
        pending.write_bytes(raw)
        pending.chmod(0o440)
        os.replace(pending, control)
        control_inode = (control.stat().st_dev, control.stat().st_ino)
        public = {
            "schema": "mastermind.control_observation/v1" if digest is None else "mastermind.control_observation/v2",
            "source_release_sha": root.name, "control_sha256": hashlib.sha256(raw).hexdigest(),
            "control_identity": list(source._identity(mapped(control.stat()))),
            "control_uid": 450, "python_runtime_provenance_digest": "1" * 64,
            "control_acl_absent": True,
        }
        if digest is not None:
            public[configuration.CONTROL_FIELD] = digest
        pending = config / ".fixture-observation"
        pending.write_bytes(artifacts.canonical_json(public) + b"\n")
        pending.chmod(0o444)
        os.replace(pending, observation)
    select(None)
    plist = base / "control.plist"
    plist.write_bytes(plistlib.dumps({
        "Label": "com.mastermind.executive.control", "WorkingDirectory": str(root),
        "ProgramArguments": ["/fixture/python", "--release-root", str(root)]}))
    plist.chmod(0o644)
    commitment_path = root / source._COMMITMENT
    commitment_path.parent.mkdir(parents=True)
    commitment_path.write_bytes(artifacts.canonical_json(commitment) + b"\n")
    commitment_path.chmod(0o644)
    published = Path("/Library/Application Support/MastermindExecutive/releases") / root.name
    stage = base / "original-installer-stage"
    stage_commitment = stage / source._COMMITMENT
    stage_commitment.parent.mkdir(parents=True)
    stage_commitment.write_bytes(commitment_path.read_bytes())
    artifacts.materialize_hermes_attended_source_projection(
        args.macro_archive, release_root=stage, published_release_root=published,
        adapter_package_sha256=package_digest)
    shutil.copytree(stage / source._PROJECTION, root / source._PROJECTION)
    expected, material, _ = artifacts._read_attended_projection(args.macro_archive, commitment_path)
    inventory, receipt = artifacts._attended_installed_records(expected, material, root, package_digest)
    for suffix, raw in (
        (source._INVENTORY, inventory),
        (source._RECEIPT, artifacts.canonical_json(receipt) + b"\n"),
        (source._VERIFIER, (args.mastermind_root / source._VERIFIER).read_bytes()),
        (source._CONFIG_HELPER, (args.mastermind_root / source._CONFIG_HELPER).read_bytes()),
    ):
        path = root / suffix
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(raw)
        path.chmod(0o644)
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            path.chmod(0o755)
        else:
            entries.append({
                "path": path.relative_to(root).as_posix(), "type": "file",
                "mode": stat.S_IMODE(path.stat().st_mode), "uid": 0, "gid": 0,
                "size": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (root / source._MANIFEST).write_bytes(artifacts.canonical_json({
        "schema_version": "mastermind.executive_release_manifest/v1",
        "commit_sha": root.name, "tree_sha": "9" * 40, "entries": entries}) + b"\n")
    (root / source._MANIFEST).chmod(0o444)
    root.chmod(0o755)
    source_digest = hashlib.sha256((root / source._MANIFEST).read_bytes()).hexdigest()
    capsules = {}
    refused_tampering = []
    source_identity, source_inputs = artifacts._installed_attended_configuration_inputs(root)
    for automatic in (False, True):
        evidence = eligibility(automatic)
        export = base / ("auto-export.json" if automatic else "fixed-export.json")
        export.write_bytes(configuration.canonical(evidence) + b"\n")
        capsule = base / ("auto-capsule.json" if automatic else "fixed-capsule.json")
        built = artifacts.build_hermes_attended_configuration(
            export, evidence["observation_sha256"], args.macro_archive, commitment_path, capsule)
        for change in ("foreign_source", "injected_file", "altered_capability"):
            altered = json.loads(capsule.read_bytes())
            if change == "foreign_source":
                altered["source"]["commit"] = "8" * 40
            elif change == "injected_file":
                altered["files"].append({"path": "config/foreign.json", "size": 0,
                                         "sha256": "0" * 64, "base64": ""})
            else:
                altered["files"][0]["base64"] = "e30K"
                altered["files"][0]["size"] = 3
                altered["files"][0]["sha256"] = hashlib.sha256(b"{}\n").hexdigest()
            tampered = configuration.canonical(altered) + b"\n"
            try:
                configuration.validate_capsule(
                    tampered, hashlib.sha256(tampered).hexdigest(), source_identity, source_inputs)
            except configuration.ConfigurationError:
                refused_tampering.append(("auto:" if automatic else "fixed:") + change)
            else:
                raise AssertionError("rehashed foreign configuration must refuse")
        result = artifacts.materialize_hermes_attended_configuration(
            capsule, built["sha256"], root, parent=config / configuration.DIRECTORY)
        assert result["state"] == "STAGED_UNSELECTED"
        assert artifacts.materialize_hermes_attended_configuration(
            capsule, built["sha256"], root, parent=config / configuration.DIRECTORY)["state"] == "EXISTING_IDENTICAL"
        capsules[automatic] = built["sha256"]
    assert hashlib.sha256((root / source._MANIFEST).read_bytes()).hexdigest() == source_digest
    patches = [
        patch.object(source, "os", proxy),
        patch.object(source, "_SYSTEM", system), patch.object(source, "_CONTROL", control),
        patch.object(source, "_OBSERVATION", observation), patch.object(source, "_PLIST", plist),
        patch.object(source, "_no_acl", lambda *_: None),
        patch.object(source.sys, "platform", "darwin"),
    ]
    for item in patches:
        item.start()
    lease = None
    network_calls = []
    def forbidden_connect(*a, **kw):
        network_calls.append(True)
        raise AssertionError("qualification cannot contact a network")
    network = patch.object(socket.socket, "connect", forbidden_connect)
    network.start()
    try:
        with patch.dict(sys.modules, {"os": proxy}):
            lease = source.open_attended_source_context(adapter_package_sha256=package_digest)
        with lease.operation() as operation:
            factory = operation.factory()
            owner = importlib.import_module("engine.provider_production_modes")
            assert type(factory) is owner.ApplicationFabricFactory
            try:
                factory.inspect()
            except owner.ApplicationFabricBindingError as error:
                assert str(error) == "fabric_application_binding_missing"
            else:
                raise AssertionError("unenrolled source must remain closed")
        select(capsules[False])
        with lease.operation() as original:
            fixed = original.factory()
            assert fixed.inspect()["model"] == "glm-5.3-flash"
            original_root = fixed.root
            select(capsules[True])
            try:
                original.check()
            except source.HermesFabricError:
                pass
            else:
                raise AssertionError("old selection must refuse new authorization")
            assert fixed.root == original_root and original_root.is_dir()
            with lease.operation() as next_turn:
                automatic = next_turn.factory()
                assert type(automatic) is type(fixed)
                assert automatic.root != original_root
                inspected = automatic.inspect()
                assert inspected["requested_model"] is None
                exact = automatic.with_requested_model("glm-5.3-flash").inspect()
                assert exact["requested_model"] == "glm-5.3-flash"
                next_turn.check()
        select(None)
        with lease.operation() as revoked:
            try:
                revoked.factory().inspect()
            except owner.ApplicationFabricBindingError as error:
                assert str(error) == "fabric_application_binding_missing"
            else:
                raise AssertionError("revoked capsule must refuse new selection")
        imports = sorted(lease._context.modules)
        for name in imports:
            module = sys.modules[name]
            if getattr(module, "__file__", None):
                assert Path(module.__file__).is_relative_to(root / source._PROJECTION)
        lease.close()
        lease = None
        assert source._SHARED is None
        assert not any(n in {"engine", "lib"} or n.startswith(("engine.", "lib.")) for n in sys.modules)
        assert not list((root / source._PROJECTION).rglob("__pycache__"))
        assert not (root / source._PROJECTION / "data").exists()
        assert not network_calls
        result = {
            "schema": "mastermind.hermes_installed_configuration_qualification.v1",
            "package_sha256": package_digest, "macro_commit": commitment["commit"],
            "archive_sha256": commitment["archive_sha256"], "material_files": len(material["material"]),
            "real_source_and_capsule_stagers": True, "canonical_factory": True,
            "fixed_auto_exact_selection": True, "same_release_renewal": True,
            "frozen_original_configuration": True, "revocation_refuses_new_selection": True,
            "same_canonical_factory_identity": True, "sealed_release_unchanged": True,
            "canonical_imports": imports, "project_checkout_on_sys_path": False,
            "namespace_cleanup": True, "projection_bytecode_files": 0, "network_calls": 0,
            "root_ownership_control_publication_and_acl": "explicit_fixture_doubles",
            "eligibility": "finite_observation_fixture",
            "rehashed_tampering_refused": refused_tampering,
            "installed_acceptance": False, "live_provider_acceptance": False,
        }
    finally:
        if lease is not None:
            lease.close()
        network.stop()
        for item in reversed(patches):
            item.stop()
print(json.dumps(result, sort_keys=True, indent=2), flush=True)
