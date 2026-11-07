"""Read-only installed source/config binding for one Capacity observation.

Uses the existing Control receipt and installed-source validators. No receipt
publication, process probe, signal, service action, namespace capability or
campaign authority is created here. This is not a live installed-service peer.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace

from control_plane import executive_control_observation as contract
from control_plane import executive_installed_peer as peer_owner
from control_plane.capacity_observation_evidence import ObservationEvidenceError
from ops.executive_os import acceptance_maintenance as maintenance
from ops.executive_os import autonomy_control as owner
from ops.executive_os import control_observation as control_owner

SCHEMA = "mastermind.capacity_installed_source_binding.v1"
PROVENANCE = "ROOT_QUALIFIED_INSTALLED_SOURCE_AND_CONFIG"
SOURCE_SCOPE = "INSTALLED_RELEASE_CONFIG_CUSTODY_NOT_LIVE_PEER_OR_NAMESPACE_ATTESTATION"
SOURCE_FILES = (
    "scripts/executive_wake_reconcile.py",
    "control_plane/capacity_campaign_observation.py",
    "control_plane/capacity_runtime_observation.py",
    "control_plane/capacity_observation_evidence.py",
    "ops/executive_os/installed_capacity_observation.py",
)
_FIELDS = frozenset({
    "schema", "release_sha", "release_manifest_sha256", "control_plist_sha256",
    "control_observation_sha256", "control_observation", "configured_runtime_root",
    "resolved_runtime_root", "qualified_source_files", "python_runtime_digests",
    "installed_source_qualified", "installed_config_custody_qualified",
    "installed_service_peer_attested", "runtime_namespace_continuity_attested",
    "campaign_qualified", "installed_coverage_claimed",
})


def _require(condition, code):
    if not condition:
        raise ObservationEvidenceError(code)


def _digest(value, length=64):
    return type(value) is str and re.fullmatch("[0-9a-f]{" + str(length) + "}", value) is not None and set(value) != {"0"}


def _canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


def validate_binding(value):
    """Validate retained closed data offline; no filesystem or authority mint."""
    _require(type(value) is dict and set(value) == _FIELDS and value["schema"] == SCHEMA,
             "INVALID_INSTALLED_BINDING_FIELDS")
    _require(_digest(value["release_sha"], 40), "INVALID_INSTALLED_RELEASE")
    for name in ("release_manifest_sha256", "control_plist_sha256", "control_observation_sha256"):
        _require(_digest(value[name]), "INVALID_INSTALLED_BINDING_DIGEST")
    try:
        raw = _canonical(value["control_observation"])
        observation = contract.parse_observation(raw)
    except (ValueError, TypeError) as exc:
        raise ObservationEvidenceError("INVALID_RETAINED_CONTROL_OBSERVATION") from exc
    _require(observation["source_release_sha"] == value["release_sha"]
             and hashlib.sha256(raw).hexdigest() == value["control_observation_sha256"],
             "INSTALLED_CONTROL_BINDING_DISAGREEMENT")
    for name in ("configured_runtime_root", "resolved_runtime_root"):
        path = value[name]
        _require(type(path) is str and Path(path).is_absolute() and str(Path(path)) == path
                 and ".." not in Path(path).parts, "INVALID_CONFIGURED_RUNTIME_BINDING")
    files = value["qualified_source_files"]
    _require(type(files) is dict and set(files) == set(SOURCE_FILES)
             and all(_digest(digest) for digest in files.values()), "INVALID_INSTALLED_SOURCE_SET")
    runtime = value["python_runtime_digests"]
    _require(type(runtime) is dict and set(runtime) == {"launcher", "dylib", "main"}
             and all(_digest(digest) for digest in runtime.values()), "INVALID_INSTALLED_PYTHON_BINDING")
    for name in ("installed_source_qualified", "installed_config_custody_qualified"):
        _require(value[name] is True, "INSTALLED_SOURCE_BINDING_UNQUALIFIED")
    for name in ("installed_service_peer_attested", "runtime_namespace_continuity_attested",
                 "campaign_qualified", "installed_coverage_claimed"):
        _require(value[name] is False, "UNSUPPORTED_INSTALLED_BINDING_CLAIM")
    return value


def source_paths(expected_sha):
    _require(_digest(expected_sha, 40), "INVALID_INSTALLED_RELEASE")
    root = owner.SYSTEM_ROOT / "releases" / expected_sha
    return tuple(root / name for name in SOURCE_FILES)


def _execution_origin(expected_sha):
    """Only the real installed CLI under the existing pinned isolated Python."""
    owner.ProductionStatusHost()._require_host()
    root = owner.SYSTEM_ROOT / "releases" / expected_sha
    main = getattr(sys.modules.get("__main__"), "__file__", None)
    _require(main is not None and Path(main).resolve(strict=True) == root / SOURCE_FILES[0],
             "INSTALLED_OBSERVER_ENTRY_REQUIRED")
    origins = {
        Path(__file__): SOURCE_FILES[-1],
        Path(owner.__file__): "ops/executive_os/autonomy_control.py",
        Path(control_owner.__file__): "ops/executive_os/control_observation.py",
        Path(contract.__file__): "control_plane/executive_control_observation.py",
        Path(peer_owner.__file__): "control_plane/executive_installed_peer.py",
    }
    for path, relative in origins.items():
        _require(path.resolve(strict=True) == root / relative, "INSTALLED_OBSERVER_SOURCE_REQUIRED")
    for relative in SOURCE_FILES[1:-1]:
        module = sys.modules.get(relative.removesuffix(".py").replace("/", "."))
        path = getattr(module, "__file__", None)
        _require(path is not None and Path(path).resolve(strict=True) == root / relative,
                 "INSTALLED_OBSERVER_SOURCE_REQUIRED")
    _require(sys.flags.isolated == 1 and sys.flags.no_site == 1 and sys.dont_write_bytecode,
             "INSTALLED_OBSERVER_ISOLATION_REQUIRED")
    _require(Path(sys.executable).resolve(strict=True) == owner.PINNED_PYTHON.resolve(strict=True),
             "INSTALLED_OBSERVER_PYTHON_REQUIRED")


class InstalledSourceObservation:
    """One fresh source/config observation and its matching final readback."""

    def __init__(self, expected_sha):
        self._qualified_read(lambda: self._start(expected_sha))

    @staticmethod
    def _qualified_read(read):
        try:
            return read()
        except (peer_owner.PeerIdentityError, owner.HostControlError,
                owner.ArmAdmissionError, maintenance.MaintenanceError,
                contract.ControlObservationError) as exc:
            # The capture keeps its original incomplete reservation. Never turn
            # an unavailable installed owner into a successful source fallback.
            raise ObservationEvidenceError("INSTALLED_SOURCE_QUALIFICATION_REFUSED") from exc

    def _start(self, expected_sha):
        _require(_digest(expected_sha, 40), "INVALID_INSTALLED_RELEASE")
        self.expected_sha = expected_sha
        self._finished = False
        self._alias_guard = SimpleNamespace(aliases={})
        self._budget = peer_owner._Budget(peer_owner._SERVICE_BUDGET_SECONDS)
        _execution_origin(expected_sha)
        owner.ProductionArmHost().require_transaction_absent()
        self._topology = peer_owner._role_topology("control")
        self._plist = peer_owner._verify_role_plist(self._topology, self._budget,
                                                   expected_release=expected_sha)
        self._tree = peer_owner._verify_release(self._topology, expected_sha, self._budget)
        self._python = peer_owner._verify_python_runtime(self._budget)
        self._control = self._read_control()
        self.runtime_root = self._control[-1]
        required = set(SOURCE_FILES)
        self._files = {row[0]: row[6] for row in self._tree.digests
                       if row[0] in required and row[1] == "file"}
        _require(set(self._files) == required, "INSTALLED_OBSERVER_SOURCE_SET_INCOMPLETE")
        self._budget.check()

    def _read_control(self):
        projection = peer_owner._verify_control_projection(self._budget)
        snapshot, custody = control_owner._snapshot(self.expected_sha)
        retained = control_owner._retained()
        _require(retained is not None and retained == snapshot, "INSTALLED_CONTROL_RECEIPT_MISMATCH")
        raw, receipt_info = owner._read_root_file(Path(contract.OBSERVATION_PATH),
            modes=frozenset({0o444}), uid=0, gid=0)
        _require(raw == retained, "INSTALLED_CONTROL_RECEIPT_CHANGED")
        observation = contract.parse_observation(raw)
        _require(projection.release == self.expected_sha
                 and projection.digest == observation["control_sha256"]
                 and projection.provenance_digest == observation["python_runtime_provenance_digest"]
                 and tuple(projection.identity) == tuple(observation["control_identity"]),
                 "INSTALLED_CONTROL_PROJECTION_MISMATCH")
        control_raw, info = owner._read_root_file(Path(contract.CONTROL_PATH),
            modes=frozenset({0o440}), uid=0, gid=contract.CONTROL_UID)
        _require(hashlib.sha256(control_raw).hexdigest() == observation["control_sha256"]
                 and contract.object_identity(info) == tuple(observation["control_identity"]),
                 "INSTALLED_CONTROL_CONFIG_CHANGED")
        document = peer_owner._load_strict_json(control_raw, code="SERVICE_CONFIG_MALFORMED")
        configured = maintenance._canonical_root_path(document.get("runtime_root"))
        runtime = maintenance._runtime_owner_path(configured, self._alias_guard)
        fixed = maintenance._runtime_owner_path(owner.RUNTIME_ROOT / "control" / "db", self._alias_guard)
        _require(runtime == fixed, "INSTALLED_RUNTIME_CONFIG_MISMATCH")
        return (projection, snapshot, custody, contract.object_identity(receipt_info),
                str(configured), runtime)

    def finish(self):
        return self._qualified_read(self._finish)

    def _finish(self):
        _require(not self._finished, "INSTALLED_OBSERVATION_ALREADY_FINISHED")
        self._finished = True
        # Qualification time is visible to the enclosing capture. The existing
        # owner's finite budget includes the observer and this final recheck.
        self._budget.check()
        _execution_origin(self.expected_sha)
        peer_owner._recheck_release(self._tree, self._budget)
        peer_owner._recheck_python_runtime(self._python, self._budget)
        plist = peer_owner._verify_role_plist(self._topology, self._budget,
                                            expected_release=self.expected_sha)
        _require(plist == self._plist, "INSTALLED_CONTROL_PLIST_CHANGED")
        owner.ProductionArmHost().require_transaction_absent()
        _require(self._read_control() == self._control, "INSTALLED_CONTROL_BINDING_CHANGED")
        self._budget.check()
        observation = contract.parse_observation(self._control[1])
        binding = dict(
            schema=SCHEMA, release_sha=self.expected_sha,
            release_manifest_sha256=self._tree.manifest_digest,
            control_plist_sha256=self._plist.digest,
            control_observation_sha256=hashlib.sha256(self._control[1]).hexdigest(),
            control_observation=observation,
            configured_runtime_root=self._control[-2], resolved_runtime_root=str(self.runtime_root),
            qualified_source_files=self._files,
            python_runtime_digests={"launcher": self._python.launcher_digest,
                                   "dylib": self._python.dylib_digest, "main": self._python.main_digest},
            installed_source_qualified=True, installed_config_custody_qualified=True,
            installed_service_peer_attested=False, runtime_namespace_continuity_attested=False,
            campaign_qualified=False, installed_coverage_claimed=False,
        )
        return validate_binding(binding)
