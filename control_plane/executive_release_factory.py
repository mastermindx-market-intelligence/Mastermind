"""Private, read-only installed composition for the existing release owner.

There is no installer, path selector, registration writer, key provisioner or
actuator here. Product must separately qualify every fixed installed input.
The accepted input contract is R6, SHA-256
9509b2558ea50a385b3758575d66f46a3e0b8cf3c96d253384e14a925fcfc4f4.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import sys
import time

from control_plane import executive_release_contract as contract
from control_plane.executive_authority import ReleaseControllerPolicy, ReleasePolicyState
from control_plane.executive_release_consumer import ReleaseConsumerError
from control_plane.executive_release_owner import (
    ReleaseBrokerOwner, ReleaseHistoryTrust, ReleaseOwnerSnapshot,
)
from control_plane.executive_release_token import _OwnerReleaseCodec
from control_plane.fs_security import has_macos_acl


_CONFIG = Path("/Library/Application Support/MastermindExecutive/config")
_REGISTRATION = _CONFIG / "release-owner-registration.json"
_KEY = _CONFIG / "release-owner-seal.key"
_REGISTRY = _CONFIG / "release-owner-staged-transitions.json"
_EVIDENCE = _CONFIG / "release-owner-installed-evidence.json"
_CONTROL = _CONFIG / "control.json"
_BROKER_CONFIG = _CONFIG / "privileged-broker.json"
_STAGING = Path("/Library/Application Support/MastermindExecutive/release-staging")
_DEPENDENCIES = (
    "control_plane/executive_release_factory.py",
    "control_plane/executive_release_owner.py",
    "control_plane/executive_release_token.py",
    "control_plane/executive_release_contract.py",
    "control_plane/executive_release_actuator.py",
    "control_plane/executive_authority.py",
    "control_plane/executive_release_consumer.py",
    "control_plane/executive_privileged_broker.py",
    "scripts/executive_os_privileged_broker.py",
)
_STAGE_FILES = frozenset({
    "effect.json", "preconditions-template.json", "release-artifact.bin",
    "artifact-metadata.json", "installer-profile.json",
    "configuration-transition.json", "source-proof.json",
    "compatibility-proof.json", "preservation-plan.json", "rollback-evidence.json",
})
_HEX64 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_HEX40 = re.compile(r"[0-9a-f]{40}", re.ASCII)
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", re.ASCII)


def _unavailable():
    raise ReleaseConsumerError("RELEASE_INSTALLED_OWNER_UNAVAILABLE")


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    return _hash(contract.canonical_release_bytes(value))


def _metadata(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@dataclass(frozen=True, repr=False)
class _File:
    # Secret key bytes and their hash never participate in repr/logging.
    raw: bytes | None = field(repr=False)
    sha256: str = field(repr=False)
    identity: tuple
    ancestors: tuple

    def public_identity(self):
        return {"sha256": self.sha256, "identity": list(self.identity),
                "ancestors": [list(row) for row in self.ancestors]}

    def resident_identity(self):
        # Directory contents can change when an unrelated staged registry is
        # atomically published. Across requests retain directory identity and
        # security metadata, not its contents' size/link count/timestamps.
        # observe() still checks full metadata before/after every held read,
        # and every later observation rechecks ownership, permissions and ACLs.
        return {"sha256": self.sha256, "identity": list(self.identity),
                "ancestors": [list(row[:5]) for row in self.ancestors]}


class _Reader:
    """One bounded observation, with all parent descriptors held through read."""

    def __init__(self, *, resident=False):
        if sys.platform != "darwin":
            _unavailable()
        for name in ("O_NOFOLLOW", "O_CLOEXEC", "O_NONBLOCK", "O_DIRECTORY"):
            if type(getattr(os, name, None)) is not int or getattr(os, name) <= 0:
                _unavailable()
        if os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd:
            _unavailable()
        self.deadline = time.monotonic() + 5
        self.maximum = (32 if resident else 544) * 1024 * 1024
        self.max_leaves = 20 if resident else 32
        self.bytes = 0
        self.leaves = 0

    def check(self):
        if time.monotonic() >= self.deadline:
            _unavailable()

    def names(self, descriptor, expected):
        names = []
        with os.scandir(descriptor) as entries:
            for entry in entries:
                self.check()
                names.append(entry.name)
                if len(names) > len(expected):
                    _unavailable()
        return sorted(names)

    @staticmethod
    def _trusted(info, descriptor, *, directory=False, mode=None, gid=0):
        expected = stat.S_ISDIR if directory else stat.S_ISREG
        if (not expected(info.st_mode) or info.st_uid != 0
                or info.st_mode & 0o022
                or ((not directory or mode is not None) and info.st_gid != gid)
                or (mode is not None and stat.S_IMODE(info.st_mode) != mode)
                or (not directory and info.st_nlink != 1)
                or has_macos_acl("", expected_identity=info, descriptor=descriptor)):
            _unavailable()

    def observe(self, path, *, maximum, mode=None, gid=0, retain=True,
                directory=False, names=None):
        self.check()
        path = Path(path)
        if (not path.is_absolute() or len(path.parts) > 16
                or any(part in ("", ".", "..") for part in path.parts[1:])):
            _unavailable()
        handles = []
        walked = []
        try:
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_DIRECTORY
            parent = os.open("/", flags)
            handles.append(parent)
            root = os.fstat(parent)
            self._trusted(root, parent, directory=True)
            ancestors = [_metadata(root)]
            prefix = Path("/")
            for component in path.parts[1:-1]:
                self.check()
                before = os.stat(component, dir_fd=parent, follow_symlinks=False)
                descriptor = os.open(component, flags, dir_fd=parent)
                handles.append(descriptor)
                after = os.fstat(descriptor)
                if _metadata(before) != _metadata(after):
                    _unavailable()
                prefix /= component
                self._trusted(after, descriptor, directory=True,
                              mode=0o500 if prefix == _STAGING
                              or prefix.parent == _STAGING else None)
                walked.append((parent, component, descriptor, _metadata(after)))
                ancestors.append(_metadata(after))
                parent = descriptor
            leaf = path.name
            before = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
            if not (stat.S_ISDIR if directory else stat.S_ISREG)(before.st_mode):
                _unavailable()
            leaf_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
            if directory:
                leaf_flags |= os.O_DIRECTORY
            descriptor = os.open(leaf, leaf_flags, dir_fd=parent)
            handles.append(descriptor)
            opened = os.fstat(descriptor)
            if _metadata(before) != _metadata(opened):
                _unavailable()
            self._trusted(opened, descriptor, directory=directory, mode=mode, gid=gid)
            identity = _metadata(opened)
            if directory:
                if names is None:
                    _unavailable()
                first_names = self.names(descriptor, names)
                if names is not None and first_names != sorted(names):
                    _unavailable()
                raw = None
                digest = _digest({"names": first_names})
            else:
                self.leaves += 1
                if (self.leaves > self.max_leaves or opened.st_size < 1
                        or opened.st_size > maximum
                        or opened.st_blocks * 512 < opened.st_size):
                    _unavailable()
                parts, count, hasher = [], 0, hashlib.sha256()
                while True:
                    self.check()
                    chunk = os.read(descriptor, min(1024 * 1024, maximum + 1 - count))
                    if not chunk:
                        break
                    count += len(chunk)
                    self.bytes += len(chunk)
                    if count > maximum or self.bytes > self.maximum:
                        _unavailable()
                    hasher.update(chunk)
                    if retain:
                        parts.append(chunk)
                if count != opened.st_size:
                    _unavailable()
                raw = b"".join(parts) if retain else None
                digest = hasher.hexdigest()
            self.check()
            if (_metadata(os.fstat(descriptor)) != identity
                    or _metadata(os.stat(leaf, dir_fd=parent, follow_symlinks=False)) != identity):
                _unavailable()
            if directory and self.names(descriptor, names) != first_names:
                _unavailable()
            for previous, component, handle, original in reversed(walked):
                if (_metadata(os.fstat(handle)) != original
                        or _metadata(os.stat(component, dir_fd=previous,
                                             follow_symlinks=False)) != original):
                    _unavailable()
            if _metadata(os.fstat(handles[0])) != ancestors[0]:
                _unavailable()
            self.check()
            return _File(raw, digest, identity, tuple(ancestors))
        except (OSError, ValueError, RuntimeError):
            _unavailable()
        finally:
            for descriptor in reversed(handles):
                os.close(descriptor)


def _boot_id():
    deadline = time.monotonic() + 2
    process = subprocess.Popen(["/usr/sbin/sysctl", "-n", "kern.bootsessionuuid"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        cwd="/", env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"})
    payload = bytearray()
    try:
        if process.stdout is None:
            _unavailable()
        descriptor = process.stdout.fileno()
        os.set_blocking(descriptor, False)
        with selectors.DefaultSelector() as selector:
            selector.register(descriptor, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or len(payload) > 4096:
                    _unavailable()
                if not selector.select(remaining):
                    _unavailable()
                try:
                    block = os.read(descriptor, 4097 - len(payload))
                except BlockingIOError:
                    continue
                if not block:
                    break
                payload.extend(block)
        remaining = deadline - time.monotonic()
        if remaining <= 0 or process.wait(timeout=remaining) != 0 or not 0 < len(payload) <= 4096:
            _unavailable()
    finally:
        if process.stdout is not None:
            process.stdout.close()
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=0.25)
        except subprocess.TimeoutExpired:
            _unavailable()
    from uuid import UUID
    value = payload.decode("ascii").strip().lower()
    parsed = UUID(value)
    if str(parsed) != value or not parsed.int:
        _unavailable()
    return value


def _object(value, keys, schema=None):
    if type(value) is not dict or set(value) != set(keys.split()):
        _unavailable()
    if schema is not None and value["schema"] != schema:
        _unavailable()
    return value


def _match(value, pattern):
    if type(value) is not str or pattern.fullmatch(value) is None:
        _unavailable()
    return value


def _strict_json(raw):
    if (type(raw) is not bytes or not 0 < len(raw) <= 4 * 1024 * 1024
            or not raw.isascii() or b"\x00" in raw):
        _unavailable()
    def pairs(rows):
        value = {}
        for key, item in rows:
            if key in value:
                _unavailable()
            value[key] = item
        return value
    def constant(_value):
        _unavailable()
    def finite(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            _unavailable()
        return parsed
    value = json.loads(raw.decode("ascii"), object_pairs_hook=pairs,
                       parse_constant=constant, parse_float=finite)
    if type(value) is not dict:
        _unavailable()
    return value


def _configuration_digest(files):
    return _digest({"schema": "mastermind.executive_installed_configuration_set/v1",
                    "files": [{"path": name, "sha256": files[name].sha256} for name in (
                        "config/control.json", "config/authority_map.yml",
                        "config/privileged-broker.json")]})


_DISARMED = {"schema": "mastermind.executive_release_disarming/v1",
             "commit_prepared_release_transition": False,
             "installer_arming": False, "worker_start": False}
_SCHEMA_MAP = {
    "schema": "mastermind.executive_release_owner_schema_set/v1",
    "schemas": {key: "mastermind." + value for key, value in {
        "registration": "executive_release_owner_registration/v1",
        "staged_registry": "executive_release_owner_staged_registry/v1",
        "installed_evidence": "executive_release_owner_installed_evidence/v1",
        "artifact_metadata": "executive_release_artifact_metadata/v1",
        "installer_profile": "executive_release_installer_profile/v1",
        "configuration_transition": "executive_release_configuration_transition/v1",
        "source_proof": "executive_release_source_proof/v1",
        "compatibility_proof": "executive_release_compatibility_proof/v1",
        "preservation_plan": "executive_release_preservation_plan/v1",
        "rollback_evidence": "executive_release_rollback_evidence/v1",
        "effect": "executive_release_effect/v1",
        "preconditions": "executive_release_preconditions/v1",
        "approval": "executive_release_approval/v1",
        "prepared": "executive_release_prepared.v1",
        "broker": "executive_release_broker/v1",
    }.items()},
}
_ADMISSION_MAP = {
    "schema": "mastermind.executive_release_owner_admission_contract/v1",
    "operations": ["approve_release_transition", "prepare_release_transition",
                   "reconcile_release_transition"],
    "peer_role": "control", "commit": "DISARMED", "platform": "darwin",
    "freshness": "read-rehash-read-v2", "resolver": "transition-digest-direct-child-v1",
    "artifact_format": "single-opaque-file-v1", "rotation": "unsupported-v1",
}


def _resident(config, reader, now, *, admission=False):
    """Observe every promised resident input; no registry or stage access."""
    from control_plane.executive_privileged_broker import (
        PrivilegedBrokerConfig, _TRUSTED_EFFECT_PATHS, verify_production_trust,
    )
    files = {}
    for name, path, maximum, mode, gid in (
        ("registration", _REGISTRATION, 16384, 0o400, 0),
        ("key", _KEY, 32, 0o400, 0),
        ("evidence", _EVIDENCE, 16384, 0o400, 0),
        ("config/control.json", _CONTROL, 4 * 1024 * 1024, 0o440, 450),
        ("config/privileged-broker.json", _BROKER_CONFIG, 65536, 0o400, 0),
        ("manifest", config.release_root / ".executive-release-manifest.json",
         4 * 1024 * 1024, 0o444, 0),
    ):
        files[name] = reader.observe(path, maximum=maximum, mode=mode, gid=gid)
    reg = registration(file_document(files["registration"].raw))
    if not reg["enabled"] or len(files["key"].raw) != 32:
        _unavailable()
    broker_document = _strict_json(files["config/privileged-broker.json"].raw)
    if PrivilegedBrokerConfig.from_mapping(broker_document) != config:
        _unavailable()
    manifest = _object(_strict_json(files["manifest"].raw),
                       "schema_version commit_sha tree_sha entries")
    if (manifest["schema_version"] != "mastermind.executive_release_manifest/v1"
            or manifest["commit_sha"] != config.release_root.name):
        _unavailable()
    _match(manifest["tree_sha"], _HEX40)
    if type(manifest["entries"]) is not list:
        _unavailable()
    entries = {}
    for entry in manifest["entries"]:
        if type(entry) is not dict or type(entry.get("path")) is not str:
            _unavailable()
        if entry["path"] in entries:
            _unavailable()
        entries[entry["path"]] = entry
    closure = dict.fromkeys(("config/authority_map.yml", *_DEPENDENCIES,
                             *_TRUSTED_EFFECT_PATHS))
    for relative in closure:
        entry = _object(entries.get(relative), "path mode uid gid type size sha256")
        if (entry["type"] != "file" or type(entry["mode"]) is not int
                or entry["uid"] != 0 or type(entry["uid"]) is not int
                or entry["gid"] != 0 or type(entry["gid"]) is not int
                or type(entry["size"]) is not int):
            _unavailable()
        _match(entry["sha256"], _HEX64)
        maximum = 2 * 1024 * 1024 if relative.endswith(".yml") else 4 * 1024 * 1024
        observed = reader.observe(config.release_root / relative, maximum=maximum,
                                  mode=entry["mode"])
        if observed.sha256 != entry["sha256"] or len(observed.raw) != entry["size"]:
            _unavailable()
        files[relative] = observed
    # Keep the existing independent production trust gate, then pin the exact
    # same observations again at the owner operation boundary.
    reader.check()
    verify_production_trust(config)
    reader.check()
    policy = ReleaseControllerPolicy.from_bytes(files["config/authority_map.yml"].raw)
    reader.check()
    if (policy.configuration_state is not ReleasePolicyState.CONFIGURED
            or policy.sha256 != files["config/authority_map.yml"].sha256):
        _unavailable()
    control = _strict_json(files["config/control.json"].raw)
    if (control.get("proof_base_sha") != manifest["commit_sha"]
            or type(control.get("control_uid")) is not int or control["control_uid"] != 450):
        _unavailable()
    provenance = _match(control.get("python_runtime_provenance_digest"), _HEX64)
    if provenance == "0" * 64:
        _unavailable()
    # The release_control_armed flag is read only from the already
    # resident-verified control.json bytes. Missing or exact boolean False
    # leaves the factory disarmed for compatibility with the current
    # template/default. Only exact boolean True attaches the fixed
    # production ExecutiveReleaseActuatorJournal. Any non-boolean value
    # refuses composition. The resident control bytes and installed
    # evidence/configuration digest already bind this value to the
    # installed source/config identity.
    armed_value = control.get("release_control_armed", False)
    if type(armed_value) is not bool:
        _unavailable()
    armed = armed_value
    evidence = _object(file_document(files["evidence"].raw),
        "schema owner_installation_id target_ref registration_generation release_commit release_tree "
        "control_config_digest broker_config_digest installed_configuration_digest "
        "python_runtime_provenance_digest provider_binary_attestation_digest "
        "provider_attestation_role provider_attestation_boot_id issuer_binding_digest "
        "issuer_binding_owner_installation_id issuer_binding_role issuer_binding_release_commit "
        "issuer_binding_boot_id issuer_binding_observed_at provider_attestation_observed_at "
        "production_disarming", "mastermind.executive_release_owner_installed_evidence/v1")
    reader.check()
    boot = _boot_id()
    reader.check()
    expected = {
        "owner_installation_id": reg["owner_installation_id"], "target_ref": reg["target_ref"],
        "registration_generation": reg["registration_generation"],
        "release_commit": manifest["commit_sha"], "release_tree": manifest["tree_sha"],
        "control_config_digest": files["config/control.json"].sha256,
        "broker_config_digest": files["config/privileged-broker.json"].sha256,
        "installed_configuration_digest": _configuration_digest(files),
        "python_runtime_provenance_digest": provenance,
        "provider_attestation_role": "codex_worker", "provider_attestation_boot_id": boot,
        "issuer_binding_owner_installation_id": reg["owner_installation_id"],
        "issuer_binding_role": "control", "issuer_binding_release_commit": manifest["commit_sha"],
        "issuer_binding_boot_id": boot, "production_disarming": _DISARMED,
    }
    for name, expected_value in expected.items():
        if type(evidence[name]) is not type(expected_value) or evidence[name] != expected_value:
            _unavailable()
    if contract.canonical_release_bytes(evidence["production_disarming"]) != contract.canonical_release_bytes(_DISARMED):
        _unavailable()
    for name in ("provider_binary_attestation_digest", "issuer_binding_digest"):
        _match(evidence[name], _HEX64)
    for name in ("issuer_binding_observed_at", "provider_attestation_observed_at"):
        observed_at(evidence[name], now, admission=admission)
    public = {name: _digest(value.resident_identity()) for name, value in files.items() if name != "key"}
    public["key_metadata"] = list(files["key"].identity)
    public["boot_id"] = boot
    identity = hmac.new(files["key"].raw,
        b"mastermind.release-owner.resident.v1\0" + contract.canonical_release_bytes(public),
        hashlib.sha256).hexdigest()
    codec = _OwnerReleaseCodec(key=files["key"].raw, key_id=reg["key_id"],
                              trust_generation=reg["trust_generation"],
                              owner_installation_id=reg["owner_installation_id"])
    reader.check()
    return reg, files, evidence, policy, boot, codec, identity, armed


def _array(value, maximum, *, paths=False):
    if (type(value) is not list or not value or len(value) > maximum
            or any(type(item) is not str for item in value)
            or value != sorted(set(value))):
        _unavailable()
    for item in value:
        if paths:
            if (not item or item.startswith("/") or "\0" in item or "\\" in item
                    or any(part in ("", ".", "..") for part in item.split("/"))):
                _unavailable()
        else:
            _match(item, _IDENTIFIER)


def _join(value, expected):
    for name, item in expected.items():
        if name not in value or type(value[name]) is not type(item) or value[name] != item:
            _unavailable()


def _stage(reader, transition, resident, now):
    reg, files, evidence, policy, boot, codec, resident_identity, _armed = resident
    _match(transition, _HEX64)
    registry_file = reader.observe(_REGISTRY, maximum=16384, mode=0o400)
    table = registry(file_document(registry_file.raw), reg["registration_generation"])
    rows = [row for row in table["transitions"] if row["transition_digest"] == transition]
    if len(rows) != 1:
        _unavailable()
    directory = _STAGING / transition
    directory_before = reader.observe(directory, maximum=0, mode=0o500,
                                      directory=True, names=_STAGE_FILES)
    stage_files, documents = {}, {}
    for name in sorted(_STAGE_FILES):
        artifact = name == "release-artifact.bin"
        item = reader.observe(directory / name,
                              maximum=512 * 1024 * 1024 if artifact else 16384,
                              mode=0o400, retain=not artifact)
        stage_files[name] = item
        if not artifact:
            documents[name] = file_document(item.raw)
    effect = contract.validate_normalized_effect(documents["effect.json"])
    if _digest(effect) != transition:
        _unavailable()
    effect_dict = effect.to_dict()
    _join(effect_dict, {
        "from_release_commit": evidence["release_commit"],
        "from_release_tree": evidence["release_tree"],
        "from_installed_manifest_digest": files["manifest"].sha256,
    })
    identities = {key: effect_dict[key] for key in (
        "from_release_commit", "from_release_tree", "to_release_commit", "to_release_tree")}

    def doc(filename, fields, suffix, *, producer=None):
        value = _object(documents[filename], "schema " + fields,
                        "mastermind.executive_release_" + suffix + "/v1")
        if producer is not None and value.get("producer") != "ops/executive_os/install.sh:" + producer + "-v1":
            _unavailable()
        return value

    metadata = doc("artifact-metadata.json",
        "artifact_filename media_type artifact_size_bytes artifact_sha256", "artifact_metadata")
    artifact = stage_files["release-artifact.bin"]
    _join(metadata, {"artifact_filename": "release-artifact.bin",
                    "media_type": "application/vnd.mastermind.executive.release.v1",
                    "artifact_size_bytes": artifact.identity[6], "artifact_sha256": artifact.sha256})
    _join(effect_dict, {"staged_artifact_digest": artifact.sha256,
                       "staged_content_metadata_digest": _digest(metadata)})
    profile = doc("installer-profile.json",
        "profile_id profile_version repository platform architecture source_policy_mode action", "installer_profile")
    _match(profile["profile_id"], _IDENTIFIER)
    if type(profile["profile_version"]) is not int or not 1 <= profile["profile_version"] <= (1 << 31) - 1:
        _unavailable()
    _join(profile, {key: effect_dict[key] for key in (
        "repository", "platform", "architecture", "source_policy_mode", "action")})
    _join(effect_dict, {"installer_profile_digest": _digest(profile)})
    configuration = doc("configuration-transition.json",
        "from_configuration_digest to_configuration_digest changed_keys restart_roles", "configuration_transition")
    _join(configuration, {"from_configuration_digest": evidence["installed_configuration_digest"]})
    _match(configuration["to_configuration_digest"], _HEX64)
    _array(configuration["changed_keys"], 32)
    _array(configuration["restart_roles"], 32)
    _join(effect_dict, {"configuration_transition_digest": _digest(configuration)})
    source = doc("source-proof.json",
        "repository source_policy_mode protected_source_sha protected_source_tree installer_source_commit "
        "installer_source_tree to_release_commit to_release_tree from_release_commit from_release_tree producer observed_at",
        "source_proof", producer="protected-source-proof")
    _join(source, {key: effect_dict[key] for key in source if key != "schema" and key in effect_dict})
    _join(source, {"protected_source_tree": effect_dict["installer_source_tree"]})
    observed_at(source["observed_at"], now, admission=True)
    # validate_normalized_effect owns exact_protected_master versus
    # frozen_accepted_ancestor. No request-selected source mode is added here.
    compatibility = doc("compatibility-proof.json",
        "from_release_commit from_release_tree to_release_commit to_release_tree platform architecture "
        "installer_profile_digest checks result producer", "compatibility_proof", producer="compatibility-proof")
    _join(compatibility, {**identities, **{key: effect_dict[key] for key in (
        "platform", "architecture", "installer_profile_digest")}, "result": "PASS"})
    _array(compatibility["checks"], 64)
    _join(effect_dict, {"compatibility_proof_digest": _digest(compatibility)})
    rollback_fields = ("original_upgrade_request_id original_terminal_or_reconciliation_digest "
                       "retained_artifact_digest preimage_digest current_compatibility_digest")
    upgrade = effect_dict["action"] == "executive.release.upgrade"
    rollback = doc("rollback-evidence.json",
        "action from_release_commit from_release_tree to_release_commit to_release_tree checks result producer"
        + ("" if upgrade else " " + rollback_fields), "rollback_evidence", producer="rollback-evidence")
    _join(rollback, {**identities, "action": effect_dict["action"], "result": "PASS"})
    _array(rollback["checks"], 64)
    if upgrade:
        if effect_dict["rollback_evidence"]["rollback_readiness_digest"] != _digest(rollback):
            _unavailable()
    else:
        _join(rollback, {key: effect_dict["rollback_evidence"][key] for key in rollback_fields.split()})
    preservation = doc("preservation-plan.json",
        "from_installed_manifest_digest configuration_transition_digest retained_paths excluded_secret_classes "
        "rollback_evidence_digest producer", "preservation_plan", producer="preservation-plan")
    _join(preservation, {"from_installed_manifest_digest": files["manifest"].sha256,
                        "configuration_transition_digest": _digest(configuration),
                        "rollback_evidence_digest": _digest(rollback)})
    _array(preservation["retained_paths"], 128, paths=True)
    _array(preservation["excluded_secret_classes"], 128)
    _join(effect_dict, {"preservation_plan_digest": _digest(preservation)})
    preconditions = _object(documents["preconditions-template.json"],
        "schema owner_installation_id target_ref boot_id from_installed_manifest_digest "
        "installed_configuration_digest python_runtime_provenance_digest provider_binary_attestation_digest "
        "authority_policy_hash staged_artifact_digest staged_content_metadata_digest compatibility_proof_digest "
        "preservation_plan_digest issuer_binding_digest admission_contract_digest production_arming_digest",
        "mastermind.executive_release_preconditions/v1")
    derived = {"schema": "mastermind.executive_release_preconditions/v1",
        "owner_installation_id": reg["owner_installation_id"], "target_ref": reg["target_ref"],
        "boot_id": boot, "from_installed_manifest_digest": files["manifest"].sha256,
        "authority_policy_hash": policy.sha256, "admission_contract_digest": _digest(_ADMISSION_MAP),
        "production_arming_digest": _digest(_DISARMED),
        **{key: evidence[key] for key in ("installed_configuration_digest", "python_runtime_provenance_digest",
                                         "provider_binary_attestation_digest", "issuer_binding_digest")},
        **{key: effect_dict[key] for key in ("staged_artifact_digest", "staged_content_metadata_digest",
                                            "compatibility_proof_digest", "preservation_plan_digest")}}
    _join(preconditions, derived)
    directory_after = reader.observe(directory, maximum=0, mode=0o500,
                                     directory=True, names=_STAGE_FILES)
    if directory_before != directory_after:
        _unavailable()
    input_identity = _digest({
        "resident": resident_identity, "registry": _digest(registry_file.public_identity()),
        "registry_generation": table["registry_generation"], "staging_generation": rows[0]["staging_generation"],
        "directory": _digest(directory_before.public_identity()),
        "files": {name: _digest(value.public_identity()) for name, value in stage_files.items()},
    })
    return ReleaseOwnerSnapshot(policy=policy, codec=codec,
        owner_installation_id=reg["owner_installation_id"], target_ref=reg["target_ref"],
        boot_id=boot, key_id=reg["key_id"], trust_generation=reg["trust_generation"],
        app_generation=reg["app_generation"], schema_digest=_digest(_SCHEMA_MAP),
        admission_contract_digest=_digest(_ADMISSION_MAP), effect=effect,
        preconditions=preconditions, input_identity_digest=input_identity)


def build_release_owner(config):
    """Compose one resident owner from fixed qualified files, without writing."""
    try:
        if os.geteuid() != 0 or sys.platform != "darwin":
            _unavailable()
        try:
            os.lstat(_REGISTRATION)
        except FileNotFoundError:
            return None
        initial = _Reader(resident=True).observe(_REGISTRATION, maximum=16384, mode=0o400)
        reg = registration(file_document(initial.raw))
        if not reg["enabled"]:
            return None
        composed_at = int(time.time())
        baseline = _resident(config, _Reader(resident=True), composed_at)
        if reg != baseline[0] or initial != baseline[1]["registration"]:
            _unavailable()
        original_identity = baseline[-2]

        def current(*, admission=False, reader=None):
            now = int(time.time())
            if now < composed_at:
                _unavailable()
            observation = _resident(config, reader or _Reader(resident=True), now,
                                    admission=admission)
            # The tuple now carries an attached root journal at the end
            # (or None); identity is at index -2.
            if not hmac.compare_digest(observation[-2], original_identity):
                _unavailable()
            return observation, now

        def snapshot(transition):
            try:
                reader = _Reader()
                observation, now = current(admission=True, reader=reader)
                return _stage(reader, transition, observation, now)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                _unavailable()

        def history():
            try:
                observation, _ = current()
                reg, _files, _evidence, _policy, _boot, codec, identity, _armed = observation
                return ReleaseHistoryTrust(codec=codec,
                    owner_installation_id=reg["owner_installation_id"], target_ref=reg["target_ref"],
                    input_identity_digest=identity)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                _unavailable()
        root_journal = None
        if baseline[-1]:
            # Import only after the resident manifest/source closure has been
            # verified. Construction stores the fixed path and performs no IO.
            from control_plane.executive_release_actuator import (
                ExecutiveReleaseActuatorJournal,
            )
            root_journal = ExecutiveReleaseActuatorJournal()
        return ReleaseBrokerOwner(snapshot, history_trust=history,
                                  root_journal=root_journal)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        _unavailable()


# Pure helpers adapted from the bounded external return; parent reviewed.
from collections.abc import Mapping
from datetime import datetime, timezone
import re
from typing import Any
from uuid import UUID

from control_plane.executive_release_contract import (
    ReleaseContractError,
    ReleaseRecord,
    canonical_release_bytes,
    parse_release_json,
)

_MAX_BYTES = 16 * 1024
_MAX_INT = (1 << 63) - 1
_MAX_TRANSITIONS = 32
_DAY_SECONDS = 86400
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_REGISTRATION_SCHEMA = "mastermind.executive_release_owner_registration/v1"
_REGISTRY_SCHEMA = "mastermind.executive_release_owner_staged_registry/v1"
_REGISTRATION_FIELDS = frozenset(
    {"schema", "owner_installation_id", "target_ref", "key_id", "trust_generation",
     "app_generation", "registration_generation", "enabled"}
)
_REGISTRY_FIELDS = frozenset(
    {"schema", "registration_generation", "registry_generation", "transitions"}
)
_TRANSITION_FIELDS = frozenset({"transition_digest", "staging_generation", "state"})
_KEY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", re.ASCII)
_HEX64 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_STAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", re.ASCII)


class FactoryInputError(ValueError):
    """A fixed bounded field/code diagnostic; never echoes rejected input."""

    def __init__(self, field: str, code: str) -> None:
        self.field, self.code = field, code
        super().__init__(f"{field}:{code}")


def _fail(field: str, code: str) -> None:
    raise FactoryInputError(field, code)


def _detach(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != fields:
        _fail(label, "FIELDS")
    return {key: item for key, item in value.items()}


def _text(value: Any, field: str, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _fail(field, "FORMAT")
    return value


def _generation(value: Any, field: str) -> int:
    if type(value) is not int or not 1 <= value <= _MAX_INT:
        _fail(field, "INTEGER_RANGE")
    return value


def _canonical_uuid(value: Any, field: str) -> str:
    if type(value) is not str:
        _fail(field, "UUID")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError):
        _fail(field, "UUID")
    if parsed.int == 0 or str(parsed) != value:
        _fail(field, "UUID")
    return value


def file_document(raw: bytes) -> dict[str, Any]:
    """Return the detached plain object for canonical JSON plus one final LF."""
    if (
        type(raw) is not bytes
        or not 1 <= len(raw) <= _MAX_BYTES
        or raw[-1:] != b"\n"
        or b"\n" in raw[:-1]
    ):
        _fail("raw", "BYTES_OR_LINE")
    try:
        decoded = parse_release_json(raw[:-1])
        if type(decoded) is not ReleaseRecord:
            _fail("raw", "OBJECT_REQUIRED")
        parsed = decoded.to_dict()
        if canonical_release_bytes(parsed) + b"\n" != raw:
            _fail("raw", "NONCANONICAL")
    except ReleaseContractError:
        _fail("raw", "PARSE")
    return parsed


def registration(value: dict) -> dict[str, Any]:
    """Validate one owner registration record and return a detached dict."""
    record = _detach(value, _REGISTRATION_FIELDS, "registration")
    if record["schema"] != _REGISTRATION_SCHEMA:
        _fail("schema", "SCHEMA")
    _canonical_uuid(record["owner_installation_id"], "owner_installation_id")
    _text(record["target_ref"], "target_ref", _HEX64)
    _text(record["key_id"], "key_id", _KEY_ID)
    for name in ("trust_generation", "app_generation", "registration_generation"):
        _generation(record[name], name)
    if type(record["enabled"]) is not bool:
        _fail("enabled", "BOOL_REQUIRED")
    return record


def registry(value: dict, registration_generation: int) -> dict[str, Any]:
    """Validate one staged registry and return a deep detached dict."""
    bound = _generation(registration_generation, "registration_generation")
    record = _detach(value, _REGISTRY_FIELDS, "registry")
    if record["schema"] != _REGISTRY_SCHEMA:
        _fail("schema", "SCHEMA")
    if _generation(record["registration_generation"], "registration_generation") != bound:
        _fail("registration_generation", "MISMATCH")
    _generation(record["registry_generation"], "registry_generation")
    transitions = record["transitions"]
    if type(transitions) is not list or len(transitions) > _MAX_TRANSITIONS:
        _fail("transitions", "ARRAY_BOUND")
    rows: list[dict[str, Any]] = []
    for item in transitions:
        row = _detach(item, _TRANSITION_FIELDS, "transition")
        rows.append(
            {
                "transition_digest": _text(
                    row["transition_digest"], "transition_digest", _HEX64
                ),
                "staging_generation": _generation(
                    row["staging_generation"], "staging_generation"
                ),
                "state": row["state"],
            }
        )
        if rows[-1]["state"] != "STAGED":
            _fail("state", "ENUM")
    digests = [row["transition_digest"] for row in rows]
    if digests != sorted(set(digests)):
        _fail("transitions", "SORTED_UNIQUE")
    record["transitions"] = rows
    return record


def observed_at(value: str, now_seconds: int, *, admission: bool) -> int:
    """Return integer UTC observed seconds for an exact canonical Z timestamp."""
    _text(value, "observed_at", _STAMP)
    try:
        moment = datetime(
            int(value[0:4]), int(value[5:7]), int(value[8:10]),
            int(value[11:13]), int(value[14:16]), int(value[17:19]),
            tzinfo=timezone.utc,
        )
    except ValueError:
        _fail("observed_at", "CALENDAR")
    if (
        f"{moment.year:04d}-{moment.month:02d}-{moment.day:02d}"
        f"T{moment.hour:02d}:{moment.minute:02d}:{moment.second:02d}Z" != value
    ):
        _fail("observed_at", "ROUNDTRIP")
    if type(now_seconds) is not int or now_seconds < 0:
        _fail("now_seconds", "INTEGER_RANGE")
    if type(admission) is not bool:
        _fail("admission", "BOOL_REQUIRED")
    observed = int((moment - _EPOCH).total_seconds())
    if observed > now_seconds:
        _fail("observed_at", "FUTURE")
    if admission and now_seconds >= observed + _DAY_SECONDS:
        _fail("observed_at", "STALE")
    return observed


def _decode_resident_evidence_v2(
    raw: bytes,
    expected_evidence_context: Mapping[str, Any],
) -> dict[str, Any]:
    """Pure full-context join; callers still supply unauthenticated evidence.

    This adapter is intentionally not connected to resident/owner construction.
    The future secured consumer must independently derive every expected field.
    """
    from ops.executive_os.release_owner_resident_inputs import (
        ReleaseOwnerInputError, canonical_file_bytes, decode_installed_evidence_v2,
    )

    if type(expected_evidence_context) is not dict:
        _fail("expected_evidence_context", "TYPE")
    try:
        evidence = decode_installed_evidence_v2(raw)
        expected_raw = canonical_file_bytes(expected_evidence_context)
        decode_installed_evidence_v2(expected_raw)
    except ReleaseOwnerInputError as error:
        _fail("installed_evidence", error.code)
    # Canonical bytes retain every nested JSON type, unlike Python equality
    # where True == 1 and 1 == 1.0. Closed decoding forbids partial contexts.
    if raw != expected_raw:
        _fail("installed_evidence", "MISMATCH")
    return evidence
