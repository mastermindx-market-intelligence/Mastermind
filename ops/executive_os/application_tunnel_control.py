"""Closed Fabric and attended DSH purposes inside the existing Chisel owner.

One original operation owns one dedicated transport identity and the exact VPS
loopback listeners. stage, apply-server, apply-client,
reconcile, start-client and stop-client are finite and same-owner: there is no
second grant registry, no generic deployment framework, no credential
catalogue or watcher. A closed v2 successor retains the original credential,
label and journals while adding the two Hermes role addresses. The OS relay entry, its
constants, its defaults and its main semantics are unchanged; this module only
selects one of two source-defined application purposes on the same incumbent server.

The Chisel authfile maps each user:password to an array of remote patterns.
Fabric v1 owns 127.0.0.1:50142; its closed v2 successor adds only
127.0.0.2/.3 on that same port and original identity. Attended DSH owns
its separate exact 4181 reverse and credential. Unrelated incumbent users
and ACL values are preserved.

Public receipts carry nonsecret metadata and digests only. Credential and
authfile material never reach stdout, stderr, a receipt, a log or an error.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ElementTree

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.executive_os import install_source_policy
from ops.executive_os import os_public_edge_publication as publication
from ops.executive_os import os_release_assets as assets
from ops.executive_os import os_tunnel_entry
from ops.executive_os import release_manifest

SCHEMA = "mastermind.application_tunnel_control.v1"
ROLE_SCHEMA = "mastermind.application_tunnel_control.v2"
QUALIFICATION_SCHEMA = "mastermind.application_tunnel_qualification.v1"
ROLE_QUALIFICATION_SCHEMA = "mastermind.application_tunnel_qualification.v2"
BUNDLE_SCHEMA = "mastermind.application_tunnel_server_bundle.v1"
ROLE_BUNDLE_SCHEMA = "mastermind.application_tunnel_server_bundle.v2"
RECEIPT_SCHEMA = "mastermind.application_tunnel_receipt.v1"

PURPOSE = "fabric-application-transport"
LABEL = "com.mastermind.executive.fabric-application-tunnel"
AUDIENCE = os_tunnel_entry.APPLICATION_AUDIENCE
SERVER = os_tunnel_entry.SERVER
RELAY_PORT = os_tunnel_entry.APPLICATION_RELAY_PORT
TARGET_PORT = os_tunnel_entry.APPLICATION_TARGET_PORT
REMOTE_ADDRESS = os_tunnel_entry.APPLICATION_REVERSE
REMOTE_REGEX = os_tunnel_entry.APPLICATION_REMOTE_REGEX
REVERSE_TARGET = os_tunnel_entry.APPLICATION_REVERSE_TARGET

UPSTREAM_REPOSITORY = "https://github.com/jpillora/chisel"
SUPPORTED_SINCE = "1.12.0"
CUSTODY = "root-owned operation custody; not a remote signature"
SERVER_CUSTODY = ("root-owned local attestation carried by the authorized deploy "
                  "carrier; not a remote signature")
MAX_BYTES = publication.MAX_BYTES

STAGE_FILES = ("intent.json", "qualification.json", "credential.auth", "credential.json",
               "client-config.json", "client-plist.xml", "server-bundle.json")
ROLE_STAGE_FILES = STAGE_FILES + ("predecessor-server-receipt.json",)
IMPORT_CLOSURE = ("ops/executive_os/application_tunnel_entry.py",
                  "ops/executive_os/os_tunnel_entry.py",
                  "ops/executive_os/application_tunnel_control.py",
                  "control_plane/fs_security.py")
TEMPLATE_PATH = "ops/executive_os/com.mastermind.executive.fabric-application-tunnel.plist.template"
IDENTITY_KEYS = ("purpose", "operation_id", "audience", "server", "remote_address",
                 "remote_regex", "target_address", "relay_port", "target_port", "label",
                 "source", "release", "qualification_digest", "client_binary",
                 "server_binary", "server_fingerprint", "client_targets",
                 "server_target", "custody")

# Go's RE2 rejects these; a pattern that only Python accepts would make the
# incumbent server refuse the whole authfile instead of one entry.
_GO_UNSUPPORTED = ("(?=", "(?!", "(?<", "(?P", "(?>", "\\1", "\\2", "\\3", "\\4",
                   "\\5", "\\6", "\\7", "\\8", "\\9")
_SECRET_PATTERN = re.compile(r"(mastermind-(?:fabric|deepseek)-app):[A-Za-z0-9_-]{8,128}")
_IMPORT_PROBE = (
    "import importlib.util,json,sys;"
    "spec=importlib.util.spec_from_file_location('mm_application_entry',sys.argv[1]);"
    "module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);"
    "helper=sys.modules['ops.executive_os.os_tunnel_entry'];"
    "security=sys.modules['control_plane.fs_security'];"
    "print(json.dumps({'entry':module.__file__,'helper':helper.__file__,'security':security.__file__}))"
)


@dataclass(frozen=True)
class Paths:
    """Closed production paths. Only tests substitute a fixture root."""

    executive_root: Path = Path("/Library/Application Support/MastermindExecutive")
    operation_root: Path = Path(
        "/Library/Application Support/MastermindExecutive/application-tunnel")
    config: Path = Path(
        "/Library/Application Support/MastermindExecutive/config/application-tunnel.json")
    credential: Path = Path(
        "/Library/Application Support/MastermindExecutive/config/application-tunnel.auth")
    plist: Path = Path(
        "/Library/LaunchDaemons/com.mastermind.executive.fabric-application-tunnel.plist")
    server_authfile: Path = Path("/etc/chisel/users.json")
    server_operation_root: Path = Path("/etc/chisel/application-tunnel")
    server_binary: Path = Path("/usr/local/bin/chisel")
    server_keyfile: Path = Path("/etc/chisel/server.key")
    server_unit: str = "mm-chisel-server.service"
    python: str = "/usr/bin/python3"
    purpose: os_tunnel_entry.ApplicationPurpose = os_tunnel_entry.FABRIC_APPLICATION

    @classmethod
    def fixture(cls, root, *, purpose=os_tunnel_entry.FABRIC_APPLICATION):
        """Test-only substitution of the closed paths; never a CLI selector."""
        purpose = os_tunnel_entry.closed_application_purpose(purpose)
        root = Path(root)
        executive = root / "MastermindExecutive"
        return cls(
            executive_root=executive,
            operation_root=executive / purpose.path_stem,
            config=executive / "config" / (purpose.path_stem + ".json"),
            credential=executive / "config" / (purpose.path_stem + ".auth"),
            plist=root / "LaunchDaemons" / (purpose.label + ".plist"),
            server_authfile=root / "etc" / "chisel" / "users.json",
            server_operation_root=root / "etc" / "chisel" / purpose.path_stem,
            server_binary=root / "usr" / "local" / "bin" / "chisel",
            server_keyfile=root / "etc" / "chisel" / "server.key",
            server_unit="mm-chisel-server.service",
            python=sys.executable, purpose=purpose,
        )


    @classmethod
    def deepseek(cls):
        """A separate closed deployment identity; never caller-selected ports."""
        purpose = os_tunnel_entry.DEEPSEEK_APPLICATION
        base = cls()
        return cls(
            operation_root=base.executive_root / purpose.path_stem,
            config=base.executive_root / "config" / (purpose.path_stem + ".json"),
            credential=base.executive_root / "config" / (purpose.path_stem + ".auth"),
            plist=Path("/Library/LaunchDaemons") / (purpose.label + ".plist"),
            server_operation_root=Path("/etc/chisel") / purpose.path_stem,
            purpose=purpose,
        )


def require(ok, message):
    publication.require(ok, message)


def canonical(value):
    return publication.canonical(value)


def digest(raw):
    return publication.digest(raw)


def decode(raw):
    return publication.decode(raw)


def _root():
    require(os.geteuid() == 0, "root custody required")


def _redact(value):
    if not isinstance(value, str):
        return ""
    return _SECRET_PATTERN.sub(r"\1:<redacted>", value)[:512]


def _contract_purpose(role_aliases, purpose):
    purpose = os_tunnel_entry.closed_application_purpose(purpose)
    require(type(role_aliases) is bool, "application contract selector refused")
    require(not role_aliases or purpose is os_tunnel_entry.FABRIC_APPLICATION,
            "role aliases require the original Fabric purpose")
    return purpose


def operation_identity(role_aliases=False, *, purpose=os_tunnel_entry.FABRIC_APPLICATION):
    """Deterministic nonsecret identity shared by both host phases."""
    purpose = _contract_purpose(role_aliases, purpose)
    contract = {
        "purpose": purpose.purpose,
        "audience": purpose.audience,
        "server": SERVER,
        "remote_address": purpose.remote_address,
        "remote_regex": purpose.remote_regex,
        "target_address": "127.0.0.1:%d" % purpose.target_port,
        "label": purpose.label,
    }
    if role_aliases:
        contract.update(predecessor=operation_identity(purpose=purpose),
                        role_remotes=list(os_tunnel_entry.APPLICATION_ROLE_REVERSES))
    value = canonical(contract)
    return purpose.operation_prefix + hashlib.sha256(value).hexdigest()[:32]


def _stage_directory(paths, role_aliases=False):
    _contract_purpose(role_aliases, paths.purpose)
    # Both immutable generations keep the SAME purpose.lock and installed label.
    return paths.operation_root / ("stage-hermes-v2" if role_aliases else "stage")


def _role_intent(intent, *, purpose=os_tunnel_entry.FABRIC_APPLICATION):
    purpose = os_tunnel_entry.closed_application_purpose(purpose)
    schemas = ((purpose.control_schema, ROLE_SCHEMA)
               if purpose is os_tunnel_entry.FABRIC_APPLICATION else (purpose.control_schema,))
    require(type(intent) is dict and intent.get("schema") in schemas, "application contract refused")
    return intent["schema"] == ROLE_SCHEMA


def _remotes(role_aliases, *, purpose=os_tunnel_entry.FABRIC_APPLICATION):
    purpose = _contract_purpose(role_aliases, purpose)
    return (os_tunnel_entry.APPLICATION_ROLE_REVERSES if role_aliases else (purpose.remote_address,),
            os_tunnel_entry.APPLICATION_ROLE_REGEXES if role_aliases else (purpose.remote_regex,),
            os_tunnel_entry.APPLICATION_ROLE_TARGETS if role_aliases else (purpose.reverse_target,))


def _predecessor_record(value):
    require(type(value) is dict and set(value) == {
        "operation_id", "stage_digest", "client_application_digest", "server_bundle_digest",
        "server_receipt_digest", "credential_sha256", "credential_identity"},
        "role predecessor binding refused")
    require(value["operation_id"] == operation_identity()
            and all(type(value[key]) is str and re.fullmatch(r"[0-9a-f]{64}", value[key])
                    for key in ("stage_digest", "client_application_digest", "server_bundle_digest",
                                "server_receipt_digest", "credential_sha256")),
            "role predecessor commitment refused")
    identity = value["credential_identity"]
    require(type(identity) is dict and identity.get("state") == "PRESENT"
            and identity.get("sha256") == value["credential_sha256"]
            and identity.get("mode") == 0o400 and identity.get("uid") == 0,
            "role predecessor credential custody refused")
    return value


def _role_predecessor(paths, *, system=None, receipt_path=None, expected=None, live=False):
    _contract_purpose(True, paths.purpose)
    """Read retained v1 custody; live postimages apply only before first v2 write.

    Once a v2 write commits, its own captured preimages/receipts own recovery.
    Requiring the old live config/authfile then would strand partial publication.
    """
    with publication.private(_stage_directory(paths)) as area:
        original = _load_stage(area, paths)
        require(not _role_intent(original["intent"]), "role predecessor must be v1")
        application, receipts = _client_receipts(original, paths)
        require(application is not None and set(receipts) == {"config", "credential", "plist"},
                "role predecessor client publication is incomplete")
        for name, _, source, mode in _client_targets(original["intent"]):
            receipt = receipts[name]
            require(_target_receipt_matches(receipt, name, original, original["contents"][source],
                    receipt.get("identity", {}), mode), "role predecessor receipt differs")
        value = {
            "operation_id": original["intent"]["operation_id"],
            "stage_digest": original["stage_digest"],
            "client_application_digest": digest(canonical({"intent": application, "receipts": receipts})),
            "server_bundle_digest": digest(original["contents"]["server-bundle.json"]),
            "credential_sha256": digest(original["credential"]),
            "credential_identity": receipts["credential"]["identity"],
        }
        if expected is not None:
            _predecessor_record(expected)
            value["server_receipt_digest"] = expected["server_receipt_digest"]
            require(value == expected, "role predecessor custody changed")
        else:
            require(receipt_path is not None, "role predecessor server receipt required")
            raw = _read_root_private(Path(receipt_path), MAX_BYTES)
            grant = _server_grant(receipt_path, original, paths)
            require(grant["state"] == "GRANT_FILE_APPLIED"
                    and grant["receipt"].get("identity_sha256") == value["credential_sha256"],
                    "role predecessor server identity differs")
            # The existing CLI prints a newline; transport formatting is not
            # a different receipt. Commit its strict parsed canonical value.
            value["server_receipt_digest"] = digest(canonical(decode(raw)))
        _predecessor_record(value)
        require(_capture_preimage(paths.credential) == value["credential_identity"],
                "role predecessor credential identity changed")
        if live:
            _installed_client(original, paths)
            service, _ = _service_state(area, paths, system, original["intent"])
            require(service in ("STARTED", "STOPPED", "ABSENT"),
                    "role predecessor lifecycle is unresolved")
        return original, value


def _stopped_role_predecessor(document, paths, system):
    _contract_purpose(True, paths.purpose)
    original, _ = _role_predecessor(paths, expected=document["intent"]["predecessor"],
                                    system=system, live=True)
    with publication.private(_stage_directory(paths)) as area:
        state, _ = _service_state(area, paths, system, original["intent"])
        require(state in ("STOPPED", "ABSENT"),
                "stop the original application client before publishing role aliases")


def _version_at_least(value, floor):
    parts = value.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return False
    return tuple(int(part) for part in parts) >= tuple(int(part) for part in floor.split("."))


# ---------------------------------------------------------------- qualification


def _verify_upstream_tree(root, commit, tree, files):
    repo = Path(root).resolve()
    require(repo.is_absolute() and repo.is_dir(), "evidence source root refused")
    try:
        head = install_source_policy._git(repo, "rev-parse", "HEAD").stdout.strip()
        observed = install_source_policy._git(repo, "rev-parse", "%s^{tree}" % commit).stdout.strip()
    except install_source_policy.InstallSourcePolicyError as exc:
        raise ValueError("evidence source checkout refused") from exc
    require(head == commit and observed == tree, "evidence source identity differs")
    for path, expected in sorted(files.items()):
        try:
            blob = install_source_policy._git(repo, "show", "%s:%s" % (commit, path)).stdout.encode()
        except install_source_policy.InstallSourcePolicyError as exc:
            raise ValueError("evidence source bytes refused") from exc
        require(hashlib.sha256(blob).hexdigest() == expected,
                "evidence source bytes differ from the recorded digest")


def _qualification(raw):
    """Validate one exact source-backed qualification bound to both binaries.

    A version string alone is not qualification: the record must also pin the
    exact upstream source commit and per-file digests that establish the
    authfile rename reload and the per-new-tunnel ACL refresh.
    """
    record = decode(raw)
    require(type(record) is dict and set(record) == {
        "schema", "server_fingerprint", "client_binary", "server_binary", "semantics",
        "evidence", "custody"}, "qualification schema refused")
    require(record["schema"] in (QUALIFICATION_SCHEMA, ROLE_QUALIFICATION_SCHEMA), "qualification schema refused")
    require(record["custody"] == "root-owned source attestation; not a remote signature",
            "qualification custody refused")
    require(type(record["server_fingerprint"]) is str
            and re.fullmatch(r"[A-Za-z0-9+/]{43}=", record["server_fingerprint"]),
            "qualification server fingerprint refused")
    for role in ("client_binary", "server_binary"):
        binary = record[role]
        require(type(binary) is dict and set(binary) == {"sha256", "version", "build"},
                "qualification binary tuple refused")
        require(type(binary["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", binary["sha256"]),
                "qualification binary digest refused")
        require(type(binary["version"]) is str and re.fullmatch(r"\d+\.\d+\.\d+", binary["version"]),
                "qualification binary version refused")
        require(type(binary["build"]) is str and 0 < len(binary["build"]) <= 128,
                "qualification binary build refused")
        require(_version_at_least(binary["version"], SUPPORTED_SINCE),
                "binary semantics older than the supported source generation refused")
    semantics = record["semantics"]
    role_aliases = record["schema"] == ROLE_QUALIFICATION_SCHEMA
    semantic_keys = {"authfile_rename_reload", "new_tunnel_acl_refresh"}
    if role_aliases:
        semantic_keys.add("simultaneous_closed_role_remotes")
    require(type(semantics) is dict and set(semantics) == semantic_keys,
            "qualification semantics refused")
    require(semantics["authfile_rename_reload"] is True
            and semantics["new_tunnel_acl_refresh"] is True
            and (not role_aliases or semantics["simultaneous_closed_role_remotes"] is True),
            "unsupported authfile semantics refused")
    evidence = record["evidence"]
    require(type(evidence) is dict and set(evidence) == {
        "repository", "commit", "tree", "paths", "files", "mode", "source_root"},
        "qualification evidence refused")
    require(evidence["repository"] == UPSTREAM_REPOSITORY, "qualification evidence repository refused")
    require(type(evidence["commit"]) is str and re.fullmatch(r"[0-9a-f]{40}", evidence["commit"]),
            "qualification evidence commit refused")
    require(type(evidence["tree"]) is str and re.fullmatch(r"[0-9a-f]{40}", evidence["tree"]),
            "qualification evidence tree refused")
    paths = evidence["paths"]
    require(type(paths) is list and 0 < len(paths) <= 32, "qualification evidence paths refused")
    require(all(type(item) is str and re.fullmatch(r"[A-Za-z0-9._/-]{1,120}", item)
                and not item.startswith("/") and ".." not in item.split("/")
                for item in paths), "qualification evidence paths refused")
    files = evidence["files"]
    require(type(files) is dict and set(files) == set(paths), "qualification evidence files refused")
    require(all(type(item) is str and re.fullmatch(r"[0-9a-f]{64}", item)
                for item in files.values()), "qualification evidence digests refused")
    require(evidence["mode"] in ("source-tree", "attested"), "qualification evidence mode refused")
    if evidence["mode"] == "source-tree":
        root = evidence["source_root"]
        require(type(root) is str and root.startswith("/"), "qualification evidence source root refused")
        _verify_upstream_tree(root, evidence["commit"], evidence["tree"], files)
    else:
        require(evidence["source_root"] is None,
                "attested evidence must not claim a verified source root")
    return record


# ------------------------------------------------------------------ sealed I/O


def _read_root_private(path, maximum=65536):
    assets._sealed_path(path)
    info = path.lstat()
    require(info.st_uid == 0 and not stat.S_IMODE(info.st_mode) & 0o077,
            "private file custody refused")
    return assets._read(path, maximum)


def _make_private_directory(path):
    path = Path(path)
    parent = path.parent
    assets._sealed_path(parent, directory=True)
    path.mkdir(mode=0o700, exist_ok=False)
    os.chmod(path, 0o700)
    descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _capture_preimage(path):
    """ABSENT, or the exact present bytes with their identity."""
    path = Path(path)
    if not os.path.lexists(path):
        return {"state": "ABSENT"}
    assets._sealed_path(path)
    before = path.lstat()
    raw = assets._read(path, MAX_BYTES)
    info = path.lstat()
    require(_file_identity(before) == _file_identity(info), "target identity changed during capture")
    return {"state": "PRESENT", "sha256": digest(raw), "bytes": len(raw),
            "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid, "gid": info.st_gid,
            "identity": _file_identity(info)}


def _file_identity(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def _install(path, data, mode, *, replace, expect=None):
    """Guarded atomic install. Never overwrites bytes it did not expect.

    The absent case creates the target with a single atomic link, so a file
    that appeared in the meantime is never adopted. The present case replaces
    the recorded preimage under an immediate identity re-check; this is a
    guarded atomic replacement, not a kernel compare-and-swap against an
    arbitrary root writer, so observed drift is refused rather than overwritten.
    """
    path = Path(path)
    parent = path.parent
    assets._sealed_path(parent, directory=True)
    directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    stamp = lambda info: [info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode]
    parent_identity = stamp(os.fstat(directory))
    def check_parent():
        assets._sealed_path(parent, directory=True)
        require(stamp(os.fstat(directory)) == parent_identity == stamp(parent.lstat()),
                "target parent identity changed")
    temporary = "." + path.name + "." + secrets.token_hex(16)
    descriptor = None
    try:
        check_parent()
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(data)
            handle.flush()
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        require(not replace or type(expect) is dict, "a replacement requires the expected preimage")
        os.fchown(descriptor, expect["uid"] if replace else 0, expect["gid"] if replace else 0)
        os.fsync(descriptor)
        if replace:
            require(expect is not None, "a replacement requires the expected preimage")
            current = _capture_preimage(path)
            require(current["state"] == "PRESENT" and current == expect,
                    "the target changed before the replacement; refusing observed drift")
            check_parent()
            os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        else:
            try:
                check_parent()
                os.link(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory,
                        follow_symlinks=False)
            except FileExistsError as exc:
                raise ValueError("target appeared during install; refusing to adopt it") from exc
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        os.fsync(directory)
        check_parent()
    finally:
        if descriptor is not None:
            os.close(descriptor)
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
        os.close(directory)


def _write_once(stage, name, raw):
    """Immutable stage file; an existing entry must be byte-identical."""
    if name in stage.names():
        require(stage.read(name) == raw, "staged bytes differ; refusing to overwrite")
        return False
    stage.write(name, raw)
    return True


class _PurposeLock:
    """Exclusive cooperative lock for the one application transport purpose."""

    def __init__(self, paths, *, create=False, server=False, shared_authfile=False):
        self.paths = paths
        self.create = create
        require(not shared_authfile or server, "shared authfile lock is server-only")
        self.root = (paths.server_authfile.parent / "application-authfile-custody"
                     if shared_authfile else paths.server_operation_root if server else paths.operation_root)
        self.descriptor = None
        self.identity = None

    def __enter__(self):
        root = self.root
        if self.create and not os.path.lexists(root):
            _make_private_directory(root)
        assets._sealed_path(root, directory=True)
        require(stat.S_IMODE(root.lstat().st_mode) == 0o700, "operation root mode refused")
        path = root / "purpose.lock"
        descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT if self.create else 0), 0o600)
        try:
            info = os.fstat(descriptor)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
                    and stat.S_IMODE(info.st_mode) == 0o600, "purpose lock custody refused")
            assets._no_acl(path, info, descriptor=descriptor)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(descriptor)
            raise ValueError("purpose custody is busy") from exc
        except BaseException:
            os.close(descriptor)
            raise
        self.descriptor = descriptor
        self.identity = _file_identity(info)
        try:
            self.check()
        except BaseException:
            self.__exit__()
            raise
        return self

    def check(self):
        assets._sealed_path(self.root, directory=True)
        require(stat.S_IMODE(self.root.lstat().st_mode) == 0o700, "operation root mode refused")
        path = self.root / "purpose.lock"
        require(self.descriptor is not None
                and _file_identity(os.fstat(self.descriptor)) == self.identity
                and _file_identity(path.lstat()) == self.identity,
                "purpose lock identity changed")
        assets._no_acl(path, os.fstat(self.descriptor), descriptor=self.descriptor)

    def __exit__(self, *exception):
        if self.descriptor is not None:
            try:
                fcntl.flock(self.descriptor, fcntl.LOCK_UN)
            finally:
                os.close(self.descriptor)
                self.descriptor = None
        return False


class _HeldLocks:
    """Recheck the same held purpose and shared-authfile writer exclusions."""
    def __init__(self, *locks):
        self.locks = locks

    def check(self):
        for lock in self.locks:
            lock.check()


# ------------------------------------------------------------- OS observations


def _bounded(argv, timeout=60):
    completed = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return {"returncode": completed.returncode, "stderr": _redact(completed.stderr)}


def _parse_launchd(text):
    arguments = []
    inside = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("arguments = {"):
            inside = True
            continue
        if inside:
            if stripped == "}":
                break
            arguments.append(stripped)
    pid = None
    match = re.search(r"^\s*pid = (\d+)", text, re.M)
    if match:
        pid = int(match.group(1))
    return {"arguments": arguments, "pid": pid}


def _parse_systemd_argv(value):
    match = re.search(r"argv\[\]=(.*?)(?: ;|$)", value or "", re.S)
    if not match:
        return []
    try:
        return shlex.split(match.group(1).strip())
    except ValueError:
        return []


class System:
    """Bounded OS observation and command surface for the transport owner.

    Only the OS service/process observations and the launchctl commands are
    substitutable; every custody, qualification and evidence check that
    surrounds them always runs.
    """

    def launchctl_print(self, label):
        completed = subprocess.run(["/bin/launchctl", "print", "system/" + label],
                                   capture_output=True, text=True, timeout=30)
        if completed.returncode != 0:
            require("Could not find service" in completed.stderr
                    or "Could not find specified service" in completed.stderr,
                    "launchd observation failed; absence is unproven")
            return False, {}
        return True, _parse_launchd(completed.stdout)

    def launchctl_bootstrap(self, plist):
        return _bounded(["/bin/launchctl", "bootstrap", "system", str(plist)])

    def launchctl_bootout(self, label):
        return _bounded(["/bin/launchctl", "bootout", "system/" + label])

    def listeners(self, port):
        completed = subprocess.run(["/usr/bin/ss", "-H", "-ltnp", "sport = :%d" % port],
                                   capture_output=True, text=True, timeout=30)
        require(completed.returncode == 0, "listener observation failed; absence is unproven")
        found = []
        for line in completed.stdout.splitlines():
            if not line.strip():
                continue
            fields = line.split(None, 4)
            require(len(fields) >= 4, "listener observation is malformed")
            pids = re.findall(r"pid=(\d+)", line)
            found.append({"address": fields[3], "pid": int(pids[0]) if pids else None})
        return found

    def process_argv(self, pid):
        completed = subprocess.run(["/bin/ps", "-ww", "-p", str(pid), "-o", "command="],
                                   capture_output=True, text=True, timeout=30)
        if completed.returncode != 0:
            return []
        return shlex.split(completed.stdout.strip())

    def processes(self):
        completed = subprocess.run(["/bin/ps", "-ww", "-eo", "pid=,args="],
                                   capture_output=True, text=True, timeout=30)
        require(completed.returncode == 0, "process observation failed; absence is unproven")
        found = []
        for line in completed.stdout.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            pid, _, arguments = stripped.partition(" ")
            if not pid.isdigit():
                continue
            # ps does not quote an executable pathname containing spaces.
            # Presence checks keep the pathname intact; adoption separately
            # compares the actual PID, executable and complete closed command.
            found.append({"pid": int(pid), "command": arguments})
        return found

    def binary_identity(self, path):
        path = Path(path)
        assets._sealed_path(path)
        before = _file_identity(path.lstat())
        raw = assets._read(path, 256 * 1024 * 1024)
        completed = subprocess.run([str(path), "--version"], capture_output=True, text=True,
                                   timeout=30)
        require(completed.returncode == 0 and _file_identity(path.lstat()) == before,
                "binary observation failed or its identity changed")
        lines = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
        return {"sha256": hashlib.sha256(raw).hexdigest(), "output": lines[0][:128] if lines else ""}

    def process_matches(self, pid, expected):
        if type(pid) is not int or pid <= 0:
            return False
        proc = Path("/proc") / str(pid) / "cmdline"
        if sys.platform.startswith("linux"):
            try:
                return proc.read_bytes().rstrip(b"\0").split(b"\0") == [x.encode() for x in expected]
            except OSError:
                return False
        # The native binary pathname contains spaces. ps output is not an argv
        # serialization; compare the closed full command and the executable
        # separately instead of splitting that pathname into fictitious args.
        command = subprocess.run(["/bin/ps", "-ww", "-p", str(pid), "-o", "command="],
                                 capture_output=True, text=True, timeout=30)
        executable = subprocess.run(["/bin/ps", "-ww", "-p", str(pid), "-o", "comm="],
                                    capture_output=True, text=True, timeout=30)
        return (command.returncode == executable.returncode == 0
                and executable.stdout.strip() == expected[0]
                and command.stdout.strip() in (" ".join(expected), shlex.join(expected)))

    def process_image_identity(self, pid):
        require(sys.platform.startswith("linux") and type(pid) is int and pid > 0,
                "server process-image observation is unavailable")
        require(os.readlink("/proc/self") == str(os.getpid()),
                "server proc filesystem and process namespace differ")
        proc = Path("/proc") / str(pid)
        def started():
            raw = (proc / "stat").read_text()
            tail = raw[raw.rfind(")") + 2:].split()
            require(len(tail) > 19 and tail[19].isdigit(), "server process start identity refused")
            return tail[19]
        start_id = started()
        # This is the kernel-owned live executable link, not a supplied path.
        # A live process can retain an old inode after its disk binary changes.
        fd = os.open(proc / "exe", os.O_RDONLY | os.O_CLOEXEC)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid == 0
                    and 0 < before.st_size <= 256 * 1024 * 1024,
                    "server process executable custody refused")
            hasher = hashlib.sha256()
            total = 0
            while total <= 256 * 1024 * 1024:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                total += len(chunk)
                hasher.update(chunk)
            current = os.stat(proc / "exe")
            require(total == before.st_size and _file_identity(before) == _file_identity(os.fstat(fd))
                    and (before.st_dev, before.st_ino) == (current.st_dev, current.st_ino)
                    and started() == start_id, "server process image changed during observation")
            return {"pid": pid, "start_id": start_id, "sha256": hasher.hexdigest()}
        finally:
            os.close(fd)

    def unit_identity(self, unit):
        completed = subprocess.run(["/bin/systemctl", "show", unit,
                                    "--property=ActiveState,MainPID,ExecStart"],
                                   capture_output=True, text=True, timeout=30)
        if completed.returncode != 0:
            return {"active": False, "main_pid": 0, "argv": []}
        values = {}
        for line in completed.stdout.splitlines():
            key, _, value = line.partition("=")
            values[key] = value
        try:
            main_pid = int(values.get("MainPID") or 0)
        except ValueError:
            main_pid = 0
        return {"active": values.get("ActiveState") == "active", "main_pid": main_pid,
                "argv": _parse_systemd_argv(values.get("ExecStart", ""))}


def _observed_version(output):
    match = re.match(r"^v?(\d+\.\d+\.\d+)\b", (output or "").strip())
    return match.group(1) if match else ""


# ------------------------------------------------------------------- authfile


def _go_regex_safe(pattern):
    return not any(token in pattern for token in _GO_UNSUPPORTED)


def _authfile_entries(raw):
    """Decode the incumbent authfile and refuse anything the server would."""
    document = decode(raw)
    require(type(document) is dict, "authfile must be an object")
    entries = {}
    for key, value in document.items():
        require(type(key) is str and ":" in key, "authfile entry refused")
        name, _, secret = key.partition(":")
        require(name and secret, "authfile entry refused")
        require(type(value) is list, "authfile entry refused")
        for pattern in value:
            require(type(pattern) is str, "authfile entry refused")
            require(pattern not in ("", "*"), "authfile wildcard refused")
            require(_go_regex_safe(pattern), "authfile pattern refused")
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError("authfile pattern refused") from exc
        entries[key] = list(value)
    return entries


def _authorizes_app_listener(patterns, role_aliases=False, *, purpose=os_tunnel_entry.FABRIC_APPLICATION):
    remotes, _, _ = _remotes(role_aliases, purpose=purpose)
    for pattern in patterns:
        if any(re.search(pattern, remote) for remote in remotes):
            return True
    return False


def _merge_authfile(raw, auth, *, allow_absent_port_listener=True, role_aliases=False,
                    purpose=os_tunnel_entry.FABRIC_APPLICATION):
    """Merge exactly one app ACL into the full incumbent authfile.

    Every incumbent user and every incumbent ACL value is preserved. A second
    grant of the same listener, a conflicting application identity and an
    unanchored or wildcard incumbent rule are refused, never rewritten.
    """
    purpose = os_tunnel_entry.closed_application_purpose(purpose)
    entries = _authfile_entries(raw)
    remotes, regexes, _ = _remotes(role_aliases, purpose=purpose)
    require(purpose.remote_regex.startswith("^") and purpose.remote_regex.endswith("$"),
            "the application ACL must be anchored")
    require(re.fullmatch(purpose.remote_regex, purpose.remote_address) is not None,
            "the application ACL does not match its own listener")
    ours = entries.get(auth)
    if role_aliases:
        require(ours == [REMOTE_REGEX], "role alias successor requires the exact original grant")
        require(all(re.fullmatch(pattern, remote) for pattern, remote in zip(regexes, remotes)),
                "role alias contract differs")
    if ours is not None:
        require(ours == [purpose.remote_regex], "existing application grant differs; refusing to rewrite it")
    for key, patterns in entries.items():
        if key != auth and _authorizes_app_listener(patterns, role_aliases, purpose=purpose):
            raise ValueError("an existing grant already authorizes the application listener")
    for key in entries:
        name = key.partition(":")[0]
        if name == purpose.audience and key != auth:
            raise ValueError("conflicting existing application identity refused")
    if ours is not None and not role_aliases:
        return entries, dict(entries), False
    merged = dict(entries)
    merged[auth] = list(regexes)
    return entries, merged, True


# ---------------------------------------------------------------------- stage


def _render_plist(template, *, python, release_root, purpose=os_tunnel_entry.FABRIC_APPLICATION):
    purpose = os_tunnel_entry.closed_application_purpose(purpose)
    text = template.decode("utf-8")
    values = {
        "__LABEL__": purpose.label,
        "__PYTHON_BINARY__": python,
        "__RELEASE_ROOT__": str(release_root),
        "__ENTRYPOINT__": str(Path(release_root) / purpose.entry),
    }
    for key, value in values.items():
        text = text.replace(key, value)
    require(not re.search(r"__[A-Z_]+__", text), "unresolved plist placeholder refused")
    require(purpose.audience not in text and "AUTH" not in text,
            "the plist must not carry credential material")
    return text.encode("utf-8")


def _plist_arguments(raw, *, purpose=os_tunnel_entry.FABRIC_APPLICATION):
    purpose = os_tunnel_entry.closed_application_purpose(purpose)
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise ValueError("plist is not well-formed XML") from exc
    require(root.tag == "plist", "plist document refused")
    dictionary = root.find("dict")
    require(dictionary is not None, "plist dictionary refused")
    pairs = {}
    children = list(dictionary)
    require(len(children) % 2 == 0, "plist dictionary refused")
    for index in range(0, len(children), 2):
        key, value = children[index], children[index + 1]
        require(key.tag == "key" and isinstance(key.text, str), "plist dictionary refused")
        pairs[key.text] = value
    label = pairs.get("Label")
    require(label is not None and label.text == purpose.label, "plist label refused")
    arguments = pairs.get("ProgramArguments")
    require(arguments is not None and arguments.tag == "array", "plist arguments refused")
    values = [item.text for item in arguments]
    require(all(isinstance(item, str) for item in values), "plist arguments refused")
    return values


def _release_seal(release_root, commit_sha, tree_sha):
    """Verify the installed sealed release against its exact-SHA manifest."""
    try:
        return release_manifest.verify(release_root, commit_sha, tree_sha)
    except release_manifest.ReleaseManifestError as exc:
        raise ValueError("the sealed release does not match its exact-SHA manifest") from exc


def _release_entries(release_root, commit_sha, tree_sha, source_repo, *, purpose=os_tunnel_entry.FABRIC_APPLICATION):
    """Verify the installed sealed release and bind it to the protected source."""
    purpose = os_tunnel_entry.closed_application_purpose(purpose)
    seal = _release_seal(release_root, commit_sha, tree_sha)
    entries = {}
    for row in seal["entries"]:
        if row["path"] in purpose.import_closure or row["path"] == purpose.template_path:
            require(row.get("type") == "file", "release entry refused")
            entries[row["path"]] = row["sha256"]
    require(set(entries) == set(purpose.import_closure) | {purpose.template_path},
            "the sealed release does not carry the application transport closure")
    for path, expected in sorted(entries.items()):
        try:
            observed = install_source_policy._git(source_repo, "show", "%s:%s" % (commit_sha, path))
        except install_source_policy.InstallSourcePolicyError as exc:
            raise ValueError("the protected source does not carry the release closure") from exc
        require(hashlib.sha256(observed.stdout.encode()).hexdigest() == expected,
                "the sealed release bytes differ from the protected source")
    return seal, entries


def _import_closure(release_root, python, entries, *, purpose=os_tunnel_entry.FABRIC_APPLICATION):
    """Prove the imported helper closure comes from that same sealed release."""
    purpose = os_tunnel_entry.closed_application_purpose(purpose)
    entry = Path(release_root) / purpose.entry
    completed = subprocess.run([python, "-I", "-B", "-c", _IMPORT_PROBE, str(entry)],
                               capture_output=True, text=True, timeout=120)
    require(completed.returncode == 0, "the sealed application entry did not import")
    try:
        resolved = json.loads(completed.stdout.strip())
    except json.JSONDecodeError as exc:
        raise ValueError("the sealed application entry did not import") from exc
    for name, relative in (("entry", purpose.import_closure[0]), ("helper", purpose.import_closure[1]),
                           ("security", "control_plane/fs_security.py")):
        expected = (Path(release_root) / relative).resolve()
        require(Path(resolved.get(name, "")).resolve() == expected,
                "an imported helper escapes the sealed release")
    for path in purpose.import_closure:
        require(path in entries, "the sealed release closure is incomplete")
    return resolved


def stage(*, source_repo, source_sha, release_root, release_commit_sha, release_tree_sha,
          qualification_path, credential_path=None, paths=None, system=None,
          role_aliases=False, predecessor_server_receipt=None):
    """Capture one original operation. Never rotates or regenerates a credential."""
    _root()
    paths = paths or Paths()
    purpose = _contract_purpose(role_aliases, paths.purpose)
    system = system or System()
    require(type(role_aliases) is bool, "application contract selector refused")
    require(not role_aliases or credential_path is None, "role successor cannot replace the credential")
    require(role_aliases or predecessor_server_receipt is None, "v1 has no predecessor")
    source_repo = Path(source_repo)
    release_root = Path(release_root)
    qualification_raw = _read_root_private(Path(qualification_path), MAX_BYTES)
    qualification = _qualification(qualification_raw)
    require(qualification["schema"] == (ROLE_QUALIFICATION_SCHEMA if role_aliases else QUALIFICATION_SCHEMA),
            "qualification does not cover the selected remote contract")
    try:
        source_tree = install_source_policy.validate_acceptance_source(
            source_repo=source_repo, expected_sha=source_sha)
    except install_source_policy.InstallSourcePolicyError as exc:
        raise ValueError("protected source refused") from exc
    seal, entries = _release_entries(release_root, release_commit_sha, release_tree_sha, source_repo, purpose=purpose)
    require(source_sha == release_commit_sha and source_tree == release_tree_sha,
            "the application release differs from the protected source")
    _verify_client_binary({"client_binary": qualification["client_binary"]}, paths, system)
    template = assets._read(release_root / purpose.template_path, MAX_BYTES)
    client_config = canonical({
        "schema": os_tunnel_entry.APPLICATION_ROLE_SCHEMA if role_aliases else purpose.client_schema,
        "binary_sha256": qualification["client_binary"]["sha256"],
        "server_fingerprint": qualification["server_fingerprint"],
    })
    client_plist = _render_plist(template, python=paths.python, release_root=release_root, purpose=purpose)
    with _PurposeLock(paths, create=True) as lock:
        stage_directory = _stage_directory(paths, role_aliases)
        if not os.path.lexists(stage_directory):
            _make_private_directory(stage_directory)
        with publication.private(stage_directory) as stage_area:
            names = stage_area.names()
            credential = None
            predecessor = None
            predecessor_raw = None
            if role_aliases:
                retained = decode(stage_area.read("intent.json")) if "intent.json" in names else None
                original, predecessor = _role_predecessor(paths, system=system,
                    receipt_path=predecessor_server_receipt,
                    expected=retained["predecessor"] if retained else None, live=retained is None)
                require(all(original["intent"][key] == qualification[key] for key in
                            ("client_binary", "server_binary", "server_fingerprint")),
                        "role successor cannot change the qualified binaries or server")
                credential = original["credential"]
                if "predecessor-server-receipt.json" in names:
                    predecessor_raw = stage_area.read("predecessor-server-receipt.json")
                else:
                    require(predecessor_server_receipt is not None, "retained predecessor receipt required")
                    predecessor_raw = _read_root_private(Path(predecessor_server_receipt), MAX_BYTES)
                require(digest(canonical(decode(predecessor_raw))) == predecessor["server_receipt_digest"],
                        "role predecessor server receipt changed")
            if "credential.auth" in names:
                staged_credential = _normalise_credential(stage_area.read("credential.auth"), purpose=purpose)
                require(not role_aliases or credential == staged_credential, "role credential changed")
                credential = staged_credential
                supplied = _supplied_credential(credential_path)
                if supplied is not None:
                    require(_normalise_credential(supplied, purpose=purpose) == credential,
                            "credential rotation refused; the original operation keeps its secret")
            elif not role_aliases:
                require("intent.json" not in names,
                        "original credential staging is incomplete; regeneration refused")
                credential = _supplied_credential(credential_path)
                if credential is not None:
                    credential = _normalise_credential(credential, purpose=purpose)
            intent = {
                "schema": ROLE_SCHEMA if role_aliases else purpose.control_schema,
                "purpose": purpose.purpose,
                "operation_id": operation_identity(role_aliases, purpose=purpose),
                "audience": purpose.audience,
                "server": SERVER,
                "remote_address": purpose.remote_address,
                "remote_regex": purpose.remote_regex,
                "target_address": "127.0.0.1:%d" % purpose.target_port,
                "relay_port": purpose.relay_port,
                "target_port": purpose.target_port,
                "label": purpose.label,
                "source": {"sha": source_sha, "tree": source_tree},
                "release": {"root": str(release_root), "commit_sha": release_commit_sha,
                            "tree_sha": release_tree_sha,
                            "manifest_digest": digest(canonical(seal)),
                            "entries": entries},
                "qualification_digest": digest(qualification_raw),
                "client_binary": qualification["client_binary"],
                "server_binary": qualification["server_binary"],
                "server_fingerprint": qualification["server_fingerprint"],
                "client_targets": {"config": str(paths.config), "credential": str(paths.credential),
                                   "plist": str(paths.plist)},
                "server_target": {"authfile": str(paths.server_authfile),
                                  "unit": paths.server_unit, "binary": str(paths.server_binary)},
                "client_preimages": {
                    "config": _capture_preimage(paths.config),
                    "credential": _capture_preimage(paths.credential),
                    "plist": _capture_preimage(paths.plist),
                },
                "credential_state": "PENDING",
                "custody": CUSTODY,
            }
            if role_aliases:
                intent.update(predecessor=predecessor, role_remotes=list(_remotes(True)[0]))
            if "intent.json" in names:
                existing = decode(stage_area.read("intent.json"))
                require(type(existing) is dict
                        and all(existing.get(key) == intent[key] for key in
                                (*IDENTITY_KEYS, "schema", *( ("predecessor", "role_remotes") if role_aliases else () ))),
                        "an existing operation differs; refusing to take it over")
                intent = existing
            else:
                require(not names, "partial stage without original intent refused")
                lock.check()
                stage_area.write("intent.json", canonical(intent))
            # Persist custody before creating the dedicated secret. A missing
            # retained payload after interruption never authorizes rotation.
            if credential is None:
                credential = _normalise_credential((purpose.audience + ":" + secrets.token_urlsafe(32)).encode(), purpose=purpose)
            bundle_value = {
                "schema": ROLE_BUNDLE_SCHEMA if role_aliases else purpose.bundle_schema, "purpose": purpose.purpose,
                "operation_id": intent["operation_id"], "audience": purpose.audience,
                "auth": credential.decode(), "remotes": list(_remotes(role_aliases, purpose=purpose)[1]),
                "authfile": str(paths.server_authfile), "unit": paths.server_unit,
                "server_binary": qualification["server_binary"],
                "qualification": qualification, "source": intent["source"],
                "release": {key: intent["release"][key] for key in
                            ("commit_sha", "tree_sha", "manifest_digest", "entries")},
                "custody": CUSTODY,
            }
            if role_aliases:
                bundle_value["predecessor"] = predecessor
                _write_once(stage_area, "predecessor-server-receipt.json", predecessor_raw)
            bundle = canonical(bundle_value)
            lock.check()
            _write_once(stage_area, "qualification.json", qualification_raw)
            _write_once(stage_area, "credential.auth", credential)
            _write_once(stage_area, "credential.json", canonical({
                "schema": intent["schema"], "operation_id": intent["operation_id"],
                "credential_sha256": digest(credential), "state": "RETAINED" if role_aliases else "CREATED"}))
            _write_once(stage_area, "client-config.json", client_config)
            _write_once(stage_area, "client-plist.xml", client_plist)
            _write_once(stage_area, "server-bundle.json", bundle)
            descriptor = canonical({
                "schema": intent["schema"],
                "purpose": purpose.purpose,
                "operation_id": intent["operation_id"],
                "files": {name: {"sha256": digest(stage_area.read(name)), "bytes": len(stage_area.read(name))}
                          for name in (ROLE_STAGE_FILES if role_aliases else STAGE_FILES)},
                "custody": CUSTODY,
            })
            _write_once(stage_area, "stage.json", descriptor)
            return {
                "schema": intent["schema"],
                "state": "STAGED",
                "operation_id": intent["operation_id"],
                "stage_digest": digest(descriptor),
                "bundle_digest": digest(bundle),
                "credential_digest": digest(credential),
                "client_binary_sha256": qualification["client_binary"]["sha256"],
                "server_binary_sha256": qualification["server_binary"]["sha256"],
                "server_fingerprint": qualification["server_fingerprint"],
                "source_sha": source_sha,
                "source_tree": source_tree,
                "release_commit_sha": release_commit_sha,
                "release_tree_sha": release_tree_sha,
                "staged": True,
                "installed": False,
                "service_started": False,
                "tunnel_proven": False,
                "application_proven": False,
            }


def _supplied_credential(path):
    if path is None:
        return None
    return _read_root_private(Path(path), 1024)


def _normalise_credential(raw, *, purpose=os_tunnel_entry.FABRIC_APPLICATION):
    purpose = os_tunnel_entry.closed_application_purpose(purpose)
    require(type(raw) is bytes and 0 < len(raw) <= 1024, "application credential refused")
    body = raw[:-1] if raw.endswith(b"\n") else raw
    try:
        text = body.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("application credential refused") from exc
    require(re.fullmatch(re.escape(purpose.audience) + r":[A-Za-z0-9_-]{32,128}", text),
            "application credential refused")
    return body


def _load_stage(stage_area, paths):
    purpose = os_tunnel_entry.closed_application_purpose(paths.purpose)
    names = stage_area.names()
    require("stage.json" in names, "the staged operation is missing its descriptor")
    raw = stage_area.read("stage.json")
    document = decode(raw)
    require(type(document) is dict and set(document) == {
        "schema", "purpose", "operation_id", "files", "custody"}, "stage descriptor refused")
    require(document["purpose"] == purpose.purpose and document["custody"] == CUSTODY,
            "stage descriptor refused")
    role_aliases = _role_intent(document, purpose=purpose)
    require(stage_area.path == _stage_directory(paths, role_aliases), "stage contract path differs")
    require(document["operation_id"] == operation_identity(role_aliases, purpose=purpose), "operation identity differs")
    files = document["files"]
    expected_files = ROLE_STAGE_FILES if role_aliases else STAGE_FILES
    require(type(files) is dict and set(files) == set(expected_files), "stage file set differs")
    contents = {}
    for name, meta in sorted(files.items()):
        content = stage_area.read(name)
        require(type(meta) is dict and set(meta) == {"sha256", "bytes"}
                and meta["sha256"] == digest(content) and meta["bytes"] == len(content),
                "staged bytes changed")
        contents[name] = content
    require(set(names) <= set(expected_files) | {"stage.json", "operation"},
            "unexpected staged entry")
    intent = decode(contents["intent.json"])
    intent_fields = {
        "schema", "purpose", "operation_id", "audience", "server", "remote_address",
        "remote_regex", "target_address", "relay_port", "target_port", "label", "source",
        "release", "qualification_digest", "client_binary", "server_binary",
        "server_fingerprint", "client_targets", "server_target", "client_preimages",
        "credential_state", "custody"}
    if role_aliases:
        intent_fields.update(("predecessor", "role_remotes"))
    require(type(intent) is dict and set(intent) == intent_fields, "operation intent refused")
    require(intent["operation_id"] == document["operation_id"], "operation identity differs")
    require(intent["remote_address"] == purpose.remote_address and intent["remote_regex"] == purpose.remote_regex
            and intent["relay_port"] == purpose.relay_port and intent["target_port"] == purpose.target_port
            and intent["label"] == purpose.label and intent["audience"] == purpose.audience,
            "operation intent differs from the closed constants")
    qualification = _qualification(contents["qualification.json"])
    require(qualification["schema"] == (ROLE_QUALIFICATION_SCHEMA if role_aliases else QUALIFICATION_SCHEMA),
            "qualification does not cover the selected remote contract")
    require(digest(contents["qualification.json"]) == intent["qualification_digest"],
            "qualification digest differs")
    credential = _normalise_credential(contents["credential.auth"], purpose=purpose)
    credential_record = decode(contents["credential.json"])
    require(credential_record == {"schema": document["schema"], "operation_id": intent["operation_id"],
            "credential_sha256": digest(credential), "state": "RETAINED" if role_aliases else "CREATED"},
            "credential binding differs")
    require(intent["schema"] == document["schema"] and intent["purpose"] == purpose.purpose
            and intent["server"] == SERVER and intent["custody"] == CUSTODY
            and intent["target_address"] == "127.0.0.1:%d" % purpose.target_port
            and intent["client_targets"] == {"config": str(paths.config),
                "credential": str(paths.credential), "plist": str(paths.plist)}
            and intent["server_target"] == {"authfile": str(paths.server_authfile),
                "unit": paths.server_unit, "binary": str(paths.server_binary)},
            "operation paths or purpose differ from the fixed owner")
    require(all(intent[key] == qualification[key] for key in
                ("client_binary", "server_binary", "server_fingerprint")),
            "operation binary or server qualification differs")
    expected_config = canonical({"schema": os_tunnel_entry.APPLICATION_ROLE_SCHEMA if role_aliases else purpose.client_schema,
        "binary_sha256": qualification["client_binary"]["sha256"],
        "server_fingerprint": qualification["server_fingerprint"]})
    require(contents["client-config.json"] == expected_config, "compiled client configuration differs")
    template = assets._read(Path(intent["release"]["root"]) / purpose.template_path, MAX_BYTES)
    require(contents["client-plist.xml"] == _render_plist(template, python=paths.python,
            release_root=Path(intent["release"]["root"]), purpose=purpose), "compiled client plist differs")
    _, bundle, _ = _server_bundle(stage_area.path / "server-bundle.json",
                                  digest(contents["server-bundle.json"]), paths)
    require(bundle["auth"] == credential.decode() and bundle["source"] == intent["source"]
            and bundle["release"] == {key: intent["release"][key] for key in
                ("commit_sha", "tree_sha", "manifest_digest", "entries")},
            "server and client operation binding differs")
    if role_aliases:
        original, predecessor = _role_predecessor(paths, expected=intent["predecessor"])
        require(intent["role_remotes"] == list(_remotes(True)[0])
                and bundle["predecessor"] == predecessor and credential == original["credential"]
                and digest(canonical(decode(contents["predecessor-server-receipt.json"]))) == predecessor["server_receipt_digest"],
                "role predecessor publication differs")
        grant = _server_grant(stage_area.path / "predecessor-server-receipt.json", original, paths)
        require(grant["state"] == "GRANT_FILE_APPLIED"
                and grant["receipt"].get("identity_sha256") == predecessor["credential_sha256"],
                "role predecessor server credential differs")
    return {"descriptor": document, "intent": intent, "qualification": qualification,
            "credential": credential, "contents": contents,
            "stage_digest": digest(raw)}


# --------------------------------------------------------------- apply server


def _server_expected_argv(paths):
    return [str(paths.server_binary), "server", "--host", "127.0.0.1", "--port", "8099",
            "--reverse", "--authfile", str(paths.server_authfile),
            "--keyfile", str(paths.server_keyfile), "--keepalive", "20s"]


def _server_bundle(bundle_path, expected_digest, paths):
    purpose = os_tunnel_entry.closed_application_purpose(paths.purpose)
    raw = _read_root_private(Path(bundle_path), MAX_BYTES)
    require(digest(raw) == expected_digest, "server bundle digest differs")
    bundle = decode(raw)
    schemas = ((purpose.bundle_schema, ROLE_BUNDLE_SCHEMA)
               if purpose is os_tunnel_entry.FABRIC_APPLICATION else (purpose.bundle_schema,))
    require(type(bundle) is dict and bundle.get("schema") in schemas,
            "server bundle refused")
    role_aliases = bundle["schema"] == ROLE_BUNDLE_SCHEMA
    fields = {
        "schema", "purpose", "operation_id", "audience", "auth", "remotes", "authfile",
        "unit", "server_binary", "qualification", "source", "release", "custody"}
    if role_aliases:
        fields.add("predecessor")
    require(set(bundle) == fields, "server bundle refused")
    require(bundle["purpose"] == purpose.purpose
            and bundle["custody"] == CUSTODY, "server bundle refused")
    require(bundle["operation_id"] == operation_identity(role_aliases, purpose=purpose), "operation identity differs")
    require(bundle["audience"] == purpose.audience and bundle["remotes"] == list(_remotes(role_aliases, purpose=purpose)[1]),
            "server bundle refused")
    require(bundle["authfile"] == str(paths.server_authfile)
            and bundle["unit"] == paths.server_unit, "server bundle target differs")
    qualification = _qualification(canonical(bundle["qualification"]))
    require(qualification["schema"] == (ROLE_QUALIFICATION_SCHEMA if role_aliases else QUALIFICATION_SCHEMA),
            "server qualification does not cover the selected remote contract")
    require(bundle["server_binary"] == qualification["server_binary"],
            "server binary tuple differs from the qualification")
    require(type(bundle["source"]) is dict and set(bundle["source"]) == {"sha", "tree"}
            and all(type(v) is str and re.fullmatch(r"[0-9a-f]{40}", v)
                    for v in bundle["source"].values()), "server source binding refused")
    release = bundle["release"]
    require(type(release) is dict
            and set(release) == {"commit_sha", "tree_sha", "manifest_digest", "entries"}
            and release["commit_sha"] == bundle["source"]["sha"]
            and release["tree_sha"] == bundle["source"]["tree"]
            and type(release["manifest_digest"]) is str
            and re.fullmatch(r"[0-9a-f]{64}", release["manifest_digest"])
            and type(release["entries"]) is dict
            and set(release["entries"]) == set(purpose.import_closure) | {purpose.template_path}
            and all(type(v) is str and re.fullmatch(r"[0-9a-f]{64}", v)
                    for v in release["entries"].values()), "server release binding refused")
    auth = bundle["auth"]
    require(type(auth) is str and re.fullmatch(re.escape(purpose.audience) + r":[A-Za-z0-9_-]{32,128}", auth),
            "server bundle identity refused")
    if role_aliases:
        predecessor = _predecessor_record(bundle["predecessor"])
        require(predecessor["credential_sha256"] == digest(auth.encode()),
                "server successor cannot replace the credential")
    return raw, bundle, qualification


def _server_observation(paths, system, qualification):
    identity = system.binary_identity(paths.server_binary)
    require(identity["sha256"] == qualification["server_binary"]["sha256"],
            "the installed server binary digest differs from the qualification")
    require(_observed_version(identity["output"]) == qualification["server_binary"]["version"],
            "the installed server binary version differs from the qualification")
    require(identity["output"] == qualification["server_binary"]["build"],
            "the installed server binary build differs from the qualification")
    unit = system.unit_identity(paths.server_unit)
    require(unit["active"], "the incumbent chisel server unit is not active")
    require(unit["argv"] == _server_expected_argv(paths),
            "the incumbent chisel server unit arguments differ")
    require(unit["main_pid"] > 0, "the incumbent chisel server unit has no main process")
    require(system.process_matches(unit["main_pid"], _server_expected_argv(paths)),
            "the incumbent server process identity differs")
    live = system.process_image_identity(unit["main_pid"])
    require(live.get("pid") == unit["main_pid"] and live.get("sha256") == identity["sha256"]
            and type(live.get("start_id")) is str and bool(live["start_id"]),
            "the running server image differs from the qualified binary")
    require(system.unit_identity(paths.server_unit) == unit
            and system.process_matches(unit["main_pid"], _server_expected_argv(paths)),
            "the incumbent server changed during qualification")
    return dict(unit, live_image=live)


def _server_receipt(intent, bundle, qualification, after, *, purpose=os_tunnel_entry.FABRIC_APPLICATION):
    purpose = os_tunnel_entry.closed_application_purpose(purpose)
    return {
        "schema": purpose.receipt_schema, "operation_id": bundle["operation_id"],
        "state": "GRANT_FILE_APPLIED", "bundle_digest": intent["bundle_digest"],
        "source": bundle["source"], "release": bundle["release"],
        "authfile": intent["authfile"], "authfile_sha256": intent["candidate_sha256"],
        "authfile_preimage_sha256": intent["preimage"]["sha256"],
        "authfile_identity": after, "identity_sha256": digest(bundle["auth"].encode()),
        "preserved_entries": intent["preserved_entries"],
        "server_binary_sha256": qualification["server_binary"]["sha256"],
        "server_binary_version": qualification["server_binary"]["version"],
        "server_process": intent["server_process"],
        "qualification_digest": digest(canonical(bundle["qualification"])),
        "grant_file_applied": True, "server_reload_proven": False,
        "tunnel_proven": False, "application_proven": False,
        "provider_effects_settled": False, "custody": SERVER_CUSTODY,
    }



def _historical_server_receipt(receipt, intent, bundle, qualification, candidate, *, purpose):
    """Qualify a settled receipt against its retained postimage and custody."""
    require(type(receipt) is dict, "the original server receipt is not an object")
    after = receipt.get("authfile_identity")
    require(type(after) is dict and set(after) == {
        "state", "sha256", "bytes", "mode", "uid", "gid", "identity"},
        "the historical authfile identity is incomplete")
    require(after["state"] == "PRESENT" and after["sha256"] == digest(candidate)
            and after["sha256"] == intent["candidate_sha256"]
            and type(after["bytes"]) is int and after["bytes"] == len(candidate)
            and all(type(after[key]) is int and after[key] == intent["preimage"][key]
                    for key in ("mode", "uid", "gid")),
            "the historical authfile identity differs from its candidate")
    identity = after["identity"]
    require(type(identity) is list and len(identity) == 9
            and all(type(item) is int and item >= 0 for item in identity)
            and stat.S_ISREG(identity[2]) and stat.S_IMODE(identity[2]) == after["mode"]
            and identity[3:7] == [after["uid"], after["gid"], 1, len(candidate)],
            "the historical authfile file identity differs")
    require(receipt == _server_receipt(intent, bundle, qualification, after, purpose=purpose),
            "the original server receipt changed")
    return receipt


def _other_authfile_operation_settled(paths):
    """Fence every existing peer journal under the shared authfile writer lock."""
    purpose = os_tunnel_entry.closed_application_purpose(paths.purpose)
    other = (os_tunnel_entry.DEEPSEEK_APPLICATION
             if purpose is os_tunnel_entry.FABRIC_APPLICATION
             else os_tunnel_entry.FABRIC_APPLICATION)
    root = paths.server_operation_root.parent / other.path_stem
    journals = (("operation", False),)
    if other is os_tunnel_entry.FABRIC_APPLICATION:
        journals += (("operation-hermes-v2", True),)
    peer_paths = replace(paths, purpose=other, server_operation_root=root)
    for name, role_aliases in journals:
        operation_path = root / name
        if not os.path.lexists(operation_path):
            continue
        with publication.private(operation_path) as original:
            names = original.names()
            if not names:
                continue
            require(names == {"server-intent.json", "bundle.json", "preimage.json",
                              "candidate.json", "server-receipt.json"},
                    "another original authfile operation requires reconciliation")
            intent = decode(original.read("server-intent.json"))
            require(type(intent) is dict
                    and intent.get("schema") == (ROLE_SCHEMA if role_aliases else other.control_schema)
                    and intent.get("phase") == "apply-server"
                    and intent.get("operation_id") == operation_identity(role_aliases, purpose=other)
                    and intent.get("authfile") == str(paths.server_authfile)
                    and intent.get("custody") == CUSTODY,
                    "the peer authfile intent is not qualified")
            _, bundle, qualification = _server_bundle(original.path / "bundle.json",
                                                      intent["bundle_digest"], peer_paths)
            require((bundle["schema"] == ROLE_BUNDLE_SCHEMA) == role_aliases,
                    "the peer authfile contract differs")
            if role_aliases:
                _server_role_predecessor(bundle, peer_paths)
            candidate = original.read("candidate.json")
            preimage = original.read("preimage.json")
            _, merged, changed = _merge_authfile(preimage, bundle["auth"],
                                                role_aliases=role_aliases, purpose=other)
            require(changed and candidate == canonical(merged)
                    and digest(candidate) == intent["candidate_sha256"]
                    and digest(preimage) == intent["preimage"]["sha256"],
                    "the peer authfile payload differs")
            receipt = decode(original.read("server-receipt.json"))
            _historical_server_receipt(receipt, intent, bundle, qualification, candidate,
                                       purpose=other)


def _observed_authfile_advance(receipt, intent, bundle, qualification, candidate, current,
                               before, *, purpose):
    """Observe an unchanged owned grant after additive shared-file evolution.

    The original receipt remains immutable and historical. Current metadata is
    returned separately, with no claim about server reload or new grant authority.
    """
    purpose = os_tunnel_entry.closed_application_purpose(purpose)
    _historical_server_receipt(receipt, intent, bundle, qualification, candidate,
                               purpose=purpose)
    original = _authfile_entries(candidate)
    role_aliases = bundle["schema"] == ROLE_BUNDLE_SCHEMA
    _contract_purpose(role_aliases, purpose)
    observed = _authfile_entries(current)
    require(observed.get(bundle["auth"]) == bundle["remotes"]
            and all(observed.get(key) == value for key, value in original.items()),
            "the settled authfile grant or preserved entries changed")
    for key, patterns in observed.items():
        if key != bundle["auth"]:
            require(key.partition(":")[0] != purpose.audience,
                    "conflicting existing application identity refused")
            require(not _authorizes_app_listener(patterns, role_aliases, purpose=purpose),
                    "an existing grant already authorizes the application listener")
    require(before["mode"] == intent["preimage"]["mode"]
            and (before["uid"], before["gid"]) == (intent["preimage"]["uid"], intent["preimage"]["gid"]),
            "server authfile custody differs")
    return {**receipt, "authfile_observation": "OWN_GRANT_PRESENT_AUTHFILE_ADVANCED",
            "current_authfile_sha256": digest(current), "current_authfile_identity": before,
            "current_grant_file_present": True}

def _server_role_predecessor(bundle, paths):
    """Validate VPS-retained v1 custody; never consult a client-side journal."""
    _contract_purpose(True, paths.purpose)
    expected = _predecessor_record(bundle["predecessor"])
    with publication.private(paths.server_operation_root / "operation") as original:
        require(original.names() == {"server-intent.json", "bundle.json", "preimage.json",
                "candidate.json", "server-receipt.json"}, "original server publication is incomplete")
        raw, previous, qualification = _server_bundle(original.path / "bundle.json",
            expected["server_bundle_digest"], paths)
        require(previous["schema"] == BUNDLE_SCHEMA and previous["auth"] == bundle["auth"]
                and previous["server_binary"] == bundle["server_binary"]
                and all(previous["qualification"][key] == bundle["qualification"][key]
                        for key in ("client_binary", "server_binary", "server_fingerprint")),
                "role successor changes original server custody")
        intent = decode(original.read("server-intent.json"))
        receipt_raw = original.read("server-receipt.json")
        receipt = decode(receipt_raw)
        require(digest(canonical(receipt)) == expected["server_receipt_digest"]
                and intent.get("operation_id") == operation_identity()
                and intent.get("bundle_digest") == digest(raw)
                and intent.get("schema") == SCHEMA and intent.get("phase") == "apply-server"
                and intent.get("authfile") == str(paths.server_authfile)
                and intent.get("custody") == CUSTODY,
                "original server receipt or intent differs")
        preimage = original.read("preimage.json")
        candidate = original.read("candidate.json")
        _, merged, changed = _merge_authfile(preimage, previous["auth"])
        require(changed and digest(preimage) == intent["preimage"]["sha256"]
                and canonical(merged) == candidate and digest(candidate) == intent["candidate_sha256"]
                and receipt == _server_receipt(intent, previous, qualification, receipt["authfile_identity"]),
                "original server payload or receipt differs")
        return receipt


def _server_transaction(bundle_path, expected_digest, paths, system, lock, *, apply):
    """One fixed server owner, retained preimage and candidate, and physical lock.

    Reconciliation can finish an exact missing receipt, never another grant
    write. An apply continuation advances only a proved original preimage.
    """
    purpose = os_tunnel_entry.closed_application_purpose(paths.purpose)
    raw, bundle, qualification = _server_bundle(bundle_path, expected_digest, paths)
    role_aliases = bundle["schema"] == ROLE_BUNDLE_SCHEMA
    predecessor = _server_role_predecessor(bundle, paths) if role_aliases else None
    unit = _server_observation(paths, system, qualification)
    authfile = paths.server_authfile
    before = _capture_preimage(authfile)
    current = _read_root_private(authfile, MAX_BYTES)
    require(before == _capture_preimage(authfile), "server authfile changed during capture")
    operation_directory = paths.server_operation_root / ("operation-hermes-v2" if role_aliases else "operation")
    if not os.path.lexists(operation_directory):
        require(apply, "the original server operation has not been staged")
        _make_private_directory(operation_directory)
    listeners = system.listeners(purpose.relay_port)
    with publication.private(operation_directory) as operation:
        names = operation.names()
        require(names <= {"server-intent.json", "bundle.json", "preimage.json", "candidate.json",
                          "server-receipt.json"}, "unexpected server operation entry")
        if "server-intent.json" in names:
            intent = decode(operation.read("server-intent.json"))
            require(type(intent) is dict and set(intent) == {
                "schema", "phase", "operation_id", "bundle_digest", "authfile", "preimage",
                "candidate_sha256", "preserved_entries", "server_process", "custody"}
                and intent["schema"] == (ROLE_SCHEMA if role_aliases else purpose.control_schema) and intent["phase"] == "apply-server"
                and intent["operation_id"] == bundle["operation_id"]
                and intent["bundle_digest"] == expected_digest
                and intent["authfile"] == str(authfile) and intent["custody"] == CUSTODY,
                "an existing server operation differs")
        else:
            require(apply and not names, "server intent is missing; refusing a new operation")
            # Fence the peer's existing journals before this purpose records
            # a new whole-authfile intent, preserving original recovery.
            _other_authfile_operation_settled(paths)
            if role_aliases:
                require(before == predecessor["authfile_identity"]
                        and unit["live_image"] == predecessor["server_process"],
                        "original server target or process changed before role publication")
            entries, merged, changed = _merge_authfile(current, bundle["auth"], role_aliases=role_aliases, purpose=purpose)
            require(changed, "an application grant without this original intent cannot be adopted")
            require(not listeners, "the application listener is already held by another grant")
            intent = {
                "schema": ROLE_SCHEMA if role_aliases else purpose.control_schema, "phase": "apply-server",
                "operation_id": bundle["operation_id"], "bundle_digest": expected_digest,
                "authfile": str(authfile), "preimage": before,
                "candidate_sha256": digest(canonical(merged)), "preserved_entries": len(entries) - int(role_aliases),
                "server_process": unit["live_image"],
                "custody": CUSTODY,
            }
            lock.check()
            operation.write("server-intent.json", canonical(intent))
        names = operation.names()
        complete = {"bundle.json", "preimage.json", "candidate.json"} <= names
        if not complete:
            require(apply and before == intent["preimage"],
                    "incomplete server staging requires the exact original preimage")
            _, merged, changed = _merge_authfile(current, bundle["auth"], role_aliases=role_aliases, purpose=purpose)
            candidate = canonical(merged)
            require(changed and digest(candidate) == intent["candidate_sha256"],
                    "server staging differs from the original intent")
            lock.check()
            _write_once(operation, "bundle.json", raw)
            _write_once(operation, "preimage.json", current)
            _write_once(operation, "candidate.json", candidate)
        require(operation.read("bundle.json") == raw, "server bundle custody changed")
        preimage = operation.read("preimage.json")
        candidate = operation.read("candidate.json")
        _, merged, changed = _merge_authfile(preimage, bundle["auth"], role_aliases=role_aliases, purpose=purpose)
        require(changed and digest(preimage) == intent["preimage"]["sha256"]
                and canonical(merged) == candidate and digest(candidate) == intent["candidate_sha256"],
                "original server payload differs")
        committed = current == candidate
        if "server-receipt.json" in operation.names() and not committed:
            receipt = decode(operation.read("server-receipt.json"))
            if listeners:
                allowed = {remote.removeprefix("R:") for remote in _remotes(role_aliases, purpose=purpose)[0]}
                addresses = [listener.get("address") for listener in listeners]
                require(len(addresses) == len(set(addresses)) and set(addresses) <= allowed
                        and all(listener.get("pid") == unit["main_pid"] for listener in listeners),
                        "the application listener belongs to another owner")
            return _observed_authfile_advance(receipt, intent, bundle, qualification,
                                              candidate, current, before, purpose=purpose)
        require(committed or before == intent["preimage"],
                "the server authfile conflicts with its original operation")
        if listeners:
            allowed = {remote.removeprefix("R:") for remote in _remotes(role_aliases, purpose=purpose)[0]}
            addresses = [listener.get("address") for listener in listeners]
            require(committed and len(addresses) == len(set(addresses))
                    and set(addresses) <= allowed
                    and all(listener.get("pid") == unit["main_pid"] for listener in listeners),
                    "the application listener belongs to another owner")
        if "server-receipt.json" in operation.names():
            receipt = decode(operation.read("server-receipt.json"))
            require(committed and receipt == _server_receipt(intent, bundle, qualification, before, purpose=purpose),
                    "the settled server target or receipt changed")
            return receipt
        if not committed:
            if not apply:
                return {"schema": purpose.receipt_schema, "state": "NOT_APPLIED",
                        "operation_id": intent["operation_id"], "bundle_digest": expected_digest,
                        "grant_file_applied": False, "custody": SERVER_CUSTODY}
            # Fence mutation, not read-only observation or exact receipt repair.
            _other_authfile_operation_settled(paths)
            require(_server_observation(paths, system, qualification)["live_image"] == intent["server_process"],
                    "the original server process changed before publication")
            require(not system.listeners(purpose.relay_port), "application listener appeared before publication")
            require(_read_root_private(Path(bundle_path), MAX_BYTES) == raw, "server bundle changed")
            operation.check()
            lock.check()
            _install(authfile, candidate, intent["preimage"]["mode"], replace=True,
                     expect=intent["preimage"])
        require(_read_root_private(authfile, MAX_BYTES) == candidate, "the authfile readback differs")
        after = _capture_preimage(authfile)
        require(after["mode"] == intent["preimage"]["mode"]
                and (after["uid"], after["gid"]) == (intent["preimage"]["uid"], intent["preimage"]["gid"]),
                "server authfile custody differs")
        receipt = _server_receipt(intent, bundle, qualification, after, purpose=purpose)
        lock.check()
        _write_once(operation, "server-receipt.json", canonical(receipt))
    return receipt


def apply_server(*, bundle_path, expected_digest, paths=None, system=None):
    _root()
    paths = paths or Paths()
    _server_bundle(bundle_path, expected_digest, paths)
    with _PurposeLock(paths, create=True, server=True, shared_authfile=True) as shared:
        with _PurposeLock(paths, create=True, server=True) as lock:
            held = _HeldLocks(shared, lock)
            held.check()
            return _server_transaction(bundle_path, expected_digest, paths, system or System(), held, apply=True)


def reconcile_server(*, bundle_path, expected_digest, paths=None, system=None):
    _root()
    paths = paths or Paths()
    _server_bundle(bundle_path, expected_digest, paths)
    with _PurposeLock(paths, create=True, server=True, shared_authfile=True) as shared:
        with _PurposeLock(paths, server=True) as lock:
            held = _HeldLocks(shared, lock)
            held.check()
            return _server_transaction(bundle_path, expected_digest, paths, system or System(), held, apply=False)


# -------------------------------------------------------------- apply client


def _client_targets(intent):
    targets = intent["client_targets"]
    return (
        ("config", Path(targets["config"]), "client-config.json", 0o444),
        ("credential", Path(targets["credential"]), "credential.auth", 0o400),
        ("plist", Path(targets["plist"]), "client-plist.xml", 0o444),
    )


def _apply_target(name, path, candidate, preimage, mode):
    current = _capture_preimage(path)
    if current["state"] == "PRESENT" and current["sha256"] == digest(candidate):
        require(current["mode"] == mode, "the installed target mode differs")
        return "ALREADY_APPLIED"
    if preimage["state"] == "PRESENT":
        require(current == preimage,
                "the target changed since the stage; refusing observed drift")
        _install(path, candidate, mode, replace=True, expect=preimage)
    else:
        require(current["state"] == "ABSENT", "a foreign target is present; refusing to adopt it")
        _install(path, candidate, mode, replace=False)
    require(assets._read(path, MAX_BYTES) == candidate, "the installed bytes differ")
    return "APPLIED"


def apply_client(*, server_receipt=None, paths=None, system=None, role_aliases=False):
    """Install only the application config, credential and plist."""
    _root()
    paths = paths or Paths()
    purpose = _contract_purpose(role_aliases, paths.purpose)
    system = system or System()
    with _PurposeLock(paths) as lock:
        stage_directory = _stage_directory(paths, role_aliases)
        with publication.private(stage_directory) as stage_area:
            document = _load_stage(stage_area, paths)
            intent = document["intent"]
            _verify_release(intent, paths)
            grant = _server_grant(server_receipt, document, paths)
            journal = stage_area.path / "operation"
            if not os.path.lexists(journal):
                _make_private_directory(journal)
            dispositions = {}
            with publication.private(journal) as operation:
                binding = {
                    "schema": intent["schema"], "phase": "apply-client",
                    "operation_id": intent["operation_id"],
                    "stage_digest": document["stage_digest"],
                    "custody": CUSTODY,
                }
                if "apply-intent.json" in operation.names():
                    existing = decode(operation.read("apply-intent.json"))
                    require(existing == binding, "an existing client operation differs")
                else:
                    if role_aliases:
                        _stopped_role_predecessor(document, paths, system)
                    for name, path, _, _ in _client_targets(intent):
                        current = _capture_preimage(path)
                        preimage = intent["client_preimages"][name]
                        if preimage["state"] == "ABSENT":
                            require(current == preimage, "a foreign target is present; refusing to adopt it")
                        else:
                            require(current == preimage, "the target changed since the stage; refusing observed drift")
                    operation.write("apply-intent.json", canonical(binding))
                if role_aliases and not {"apply-config.json", "apply-credential.json", "apply-plist.json"} <= operation.names():
                    loaded, _ = system.launchctl_print(LABEL)
                    require(not loaded and not any(_is_same_purpose(p, _client_binary_path(paths, intent))
                            for p in system.processes()), "role publication requires the original client stopped")
                for name, path, source, mode in _client_targets(intent):
                    lock.check()
                    require(_load_stage(stage_area, paths)["stage_digest"] == document["stage_digest"],
                            "original client stage changed before mutation")
                    _verify_release(intent, paths)
                    candidate = document["contents"][source]
                    preimage = intent["client_preimages"][name]
                    receipt_name = "apply-%s.json" % name
                    if receipt_name in operation.names():
                        receipt = decode(operation.read(receipt_name))
                        require(_target_receipt_matches(receipt, name, document, candidate,
                                                       _capture_preimage(path), mode, purpose=purpose),
                                "the settled client target or receipt changed")
                        dispositions[name] = "ALREADY_APPLIED"
                        continue
                    try:
                        if role_aliases and name == "credential":
                            require(_capture_preimage(path) == intent["predecessor"]["credential_identity"],
                                    "role successor credential identity changed")
                            disposition = "ALREADY_APPLIED"
                        else:
                            disposition = _apply_target(name, path, candidate, preimage, mode)
                    except BaseException as exc:
                        if "apply-reconciliation.json" not in operation.names():
                            operation.write("apply-reconciliation.json", canonical({
                                "schema": intent["schema"], "state": "RECONCILIATION_REQUIRED",
                                "target": name, "error_type": type(exc).__name__}))
                        raise
                    dispositions[name] = disposition
                    operation.write(receipt_name, canonical({
                        "schema": intent["schema"], "target": name, "disposition": disposition,
                        "sha256": digest(candidate), "bytes": len(candidate),
                        "operation_id": intent["operation_id"], "stage_digest": document["stage_digest"],
                        "identity": _capture_preimage(path)}))
            return {
                "schema": purpose.receipt_schema,
                "state": "CLIENT_FILES_APPLIED",
                "operation_id": intent["operation_id"],
                "stage_digest": document["stage_digest"],
                "targets": dispositions,
                "grant_state": grant["state"],
                "installed": True,
                "service_started": False,
                "tunnel_proven": False,
                "application_proven": False,
                "custody": CUSTODY,
            }


def _target_receipt_matches(receipt, name, document, candidate, current, mode, *, purpose=os_tunnel_entry.FABRIC_APPLICATION):
    purpose = os_tunnel_entry.closed_application_purpose(purpose)
    return (type(receipt) is dict and set(receipt) == {
        "schema", "target", "disposition", "sha256", "bytes", "operation_id", "stage_digest", "identity"}
        and receipt["schema"] == document["intent"]["schema"] and receipt["target"] == name
        and receipt["disposition"] in ("APPLIED", "ALREADY_APPLIED")
        and receipt["operation_id"] == document["intent"]["operation_id"]
        and receipt["stage_digest"] == document["stage_digest"]
        and receipt["sha256"] == digest(candidate) and receipt["bytes"] == len(candidate)
        and current["state"] == "PRESENT" and current["mode"] == mode
        and current["sha256"] == digest(candidate) and receipt["identity"] == current
        and (name != "credential" or not _role_intent(document["intent"], purpose=purpose)
             or current == document["intent"]["predecessor"]["credential_identity"]))


def _client_receipts(document, paths):
    purpose = os_tunnel_entry.closed_application_purpose(paths.purpose)
    journal = _stage_directory(paths, _role_intent(document["intent"], purpose=purpose)) / "operation"
    if not os.path.lexists(journal):
        return None, {}
    with publication.private(journal) as operation:
        names = operation.names()
        if "apply-intent.json" not in names:
            return None, {}
        expected = {"schema": document["intent"]["schema"], "phase": "apply-client",
                    "operation_id": document["intent"]["operation_id"],
                    "stage_digest": document["stage_digest"], "custody": CUSTODY}
        require(decode(operation.read("apply-intent.json")) == expected,
                "the original client application intent differs")
        receipts = {name: decode(operation.read("apply-%s.json" % name))
                    for name, _, _, _ in _client_targets(document["intent"])
                    if "apply-%s.json" % name in names}
        return expected, receipts


def _verify_release(intent, paths):
    purpose = os_tunnel_entry.closed_application_purpose(paths.purpose)
    release = intent["release"]
    release_root = Path(release["root"])
    seal = _release_seal(release_root, release["commit_sha"], release["tree_sha"])
    require(digest(canonical(seal)) == release["manifest_digest"], "the release seal differs")
    entries = {}
    for row in seal["entries"]:
        if row["path"] in purpose.import_closure or row["path"] == purpose.template_path:
            entries[row["path"]] = row["sha256"]
    require(entries == release["entries"], "the sealed release entries differ")
    _import_closure(release_root, paths.python, entries, purpose=purpose)


def _server_grant(server_receipt, document, paths):
    purpose = os_tunnel_entry.closed_application_purpose(paths.purpose)
    if server_receipt is None:
        return {"state": "NOT_PROVIDED"}
    raw = _read_root_private(Path(server_receipt), MAX_BYTES)
    receipt = decode(raw)
    require(type(receipt) is dict and receipt.get("schema") == purpose.receipt_schema,
            "server receipt refused")
    require(receipt.get("operation_id") == document["intent"]["operation_id"],
            "the server receipt belongs to another operation")
    require(receipt.get("custody") == SERVER_CUSTODY, "server receipt custody refused")
    bundle_digest = digest(document["contents"]["server-bundle.json"])
    require(receipt.get("bundle_digest") == bundle_digest,
            "the server receipt belongs to another bundle")
    require(receipt.get("state") == "GRANT_FILE_APPLIED", "the server grant was not applied")
    return {"state": "GRANT_FILE_APPLIED", "receipt": receipt}


# ------------------------------------------------------------------ reconcile


def reconcile(*, server_receipt=None, paths=None, system=None, role_aliases=False):
    """Inspect the original stage, intent and targets. Never mutates a target."""
    _root()
    paths = paths or Paths()
    purpose = _contract_purpose(role_aliases, paths.purpose)
    system = system or System()
    with _PurposeLock(paths):
        stage_directory = _stage_directory(paths, role_aliases)
        with publication.private(stage_directory) as stage_area:
            document = _load_stage(stage_area, paths)
            intent = document["intent"]
            targets = {}
            apply_intent, receipts = _client_receipts(document, paths)
            for name, path, source, mode in _client_targets(intent):
                candidate = document["contents"][source]
                preimage = intent["client_preimages"][name]
                current = _capture_preimage(path)
                if name in receipts:
                    targets[name] = ("APPLIED" if _target_receipt_matches(
                        receipts[name], name, document, candidate, current, mode, purpose=purpose) else "CONFLICT")
                elif current == preimage:
                    targets[name] = "NOT_APPLIED"
                elif current["state"] == "PRESENT" and current["sha256"] == digest(candidate) and current["mode"] == mode:
                    targets[name] = "COMMITTED_RECEIPT_MISSING" if apply_intent else "CONFLICT"
                else:
                    targets[name] = "CONFLICT"
            grant = _server_grant(server_receipt, document, paths)
            _verify_release(intent, paths)
            service, settled = _service_state(stage_area, paths, system, intent)
            return {
                "schema": purpose.receipt_schema,
                "state": "RECONCILED" if "CONFLICT" not in targets.values() else "RECONCILIATION_REQUIRED",
                "operation_id": intent["operation_id"],
                "stage_digest": document["stage_digest"],
                "targets": targets,
                "grant_state": grant["state"],
                "service_state": service,
                "settled": settled,
                "credential_state": "RETAINED" if role_aliases else "CREATED",
                "tunnel_proven": False,
                "application_proven": False,
                "custody": CUSTODY,
            }


def _service_state(stage_area, paths, system, intent):
    """Read the original lifecycle journal and the live launchd state."""
    purpose = os_tunnel_entry.closed_application_purpose(paths.purpose)
    journal = stage_area.path / "operation"
    loaded, info = system.launchctl_print(purpose.label)
    arguments = _plist_arguments(stage_area.read("client-plist.xml"), purpose=purpose)
    running = _running_client(loaded, info, arguments, intent, paths, system)
    orphan = not loaded and any(_is_same_purpose(p, _client_binary_path(paths, intent), purpose=purpose)
                               for p in system.processes())
    if not os.path.lexists(journal):
        return ("CONFLICT" if loaded or orphan else "ABSENT"), {}
    with publication.private(journal) as operation:
        names = operation.names()
        if "stop-intent.json" in names:
            _require_lifecycle_intent(stage_area, "stop", {"intent": intent,
                "stage_digest": digest(stage_area.read("stage.json"))}, arguments)
            if not loaded and not orphan:
                return "STOPPED", {"state": "STOPPED", "settled_by": "launchd_state_absence"}
            return "UNKNOWN", {"state": "UNKNOWN", "settled_by": "live_stop_observation"}
        if "start-intent.json" in names:
            _require_lifecycle_intent(stage_area, "start", {"intent": intent,
                "stage_digest": digest(stage_area.read("stage.json"))}, arguments)
            if running:
                return "STARTED", {"state": "STARTED", "settled_by": "launchd_state"}
            return "UNKNOWN", {"state": "UNKNOWN", "settled_by": "launchd_state_absence"}
    return ("CONFLICT" if loaded or orphan else "ABSENT"), {}


# -------------------------------------------------------------- client service


def _client_binary_path(paths, intent):
    return paths.executive_root / "transports" / "chisel" / intent["client_binary"]["sha256"] / "chisel"


def _verify_client_binary(intent, paths, system):
    path = _client_binary_path(paths, intent)
    identity = system.binary_identity(path)
    require(identity["sha256"] == intent["client_binary"]["sha256"],
            "the installed client binary digest differs from the qualification")
    require(_observed_version(identity["output"]) == intent["client_binary"]["version"],
            "the installed client binary version differs from the qualification")
    require(identity["output"] == intent["client_binary"]["build"],
            "the installed client binary build differs from the qualification")


def _is_same_purpose(process, binary_path, *, purpose=os_tunnel_entry.FABRIC_APPLICATION):
    purpose = os_tunnel_entry.closed_application_purpose(purpose)
    argv = list(process.get("argv") or [])
    if not argv:
        match = re.fullmatch(r"(.*/chisel) (client(?: .*)?)", process.get("command", ""))
        if match:
            try:
                argv = [match.group(1), *shlex.split(match.group(2))]
            except ValueError:
                return any(remote in process["command"] for remote in _remotes(purpose is os_tunnel_entry.FABRIC_APPLICATION, purpose=purpose)[2])
    return (bool(argv) and (argv[0] == str(binary_path) or Path(argv[0]).name == "chisel")
            and "client" in argv[1:] and any(remote in argv for remote in
                _remotes(purpose is os_tunnel_entry.FABRIC_APPLICATION, purpose=purpose)[2]))


def _running_client(loaded, info, arguments, intent, paths, system):
    purpose = os_tunnel_entry.closed_application_purpose(paths.purpose)
    expected = [str(_client_binary_path(paths, intent)), "client", "--fingerprint",
                intent["server_fingerprint"], "--keepalive", "20s", SERVER,
                *_remotes(_role_intent(intent, purpose=purpose), purpose=purpose)[2]]
    return (loaded and list(info.get("arguments") or []) == arguments
            and type(info.get("pid")) is int and info["pid"] > 0
            and system.process_matches(info["pid"], expected))


def _installed_client(document, paths):
    purpose = os_tunnel_entry.closed_application_purpose(paths.purpose)
    intent = document["intent"]
    _verify_release(intent, paths)
    apply_intent, receipts = _client_receipts(document, paths)
    for name, path, source, mode in _client_targets(intent):
        current = _capture_preimage(path)
        require(apply_intent and name in receipts and _target_receipt_matches(
                    receipts[name], name, document, document["contents"][source], current, mode, purpose=purpose),
                "the application client is not installed; refusing lifecycle action")


def start_client(*, server_receipt, paths=None, system=None, role_aliases=False):
    """Issue at most one exact bounded launchctl operation for this label."""
    _root()
    paths = paths or Paths()
    purpose = _contract_purpose(role_aliases, paths.purpose)
    system = system or System()
    with _PurposeLock(paths) as lock:
        stage_directory = _stage_directory(paths, role_aliases)
        with publication.private(stage_directory) as stage_area:
            document = _load_stage(stage_area, paths)
            intent = document["intent"]
            _installed_client(document, paths)
            grant = _server_grant(server_receipt, document, paths)
            require(grant["state"] == "GRANT_FILE_APPLIED",
                    "the server grant is not applied; refusing to start")
            _verify_client_binary(intent, paths, system)
            arguments = _plist_arguments(document["contents"]["client-plist.xml"], purpose=purpose)
            loaded, info = system.launchctl_print(purpose.label)
            if loaded:
                require(list(info.get("arguments") or []) == arguments,
                        "a foreign launchd label already owns this purpose")
                require(_running_client(loaded, info, arguments, intent, paths, system),
                        "the application process is not proven running")
                _require_lifecycle_intent(stage_area, "start", document, arguments)
                _settle_service(stage_area, "start-receipt.json", {
                    "schema": purpose.receipt_schema, "state": "STARTED",
                    "operation_id": intent["operation_id"], "commands": 0,
                    "settled_by": "launchd_state", "pid": info.get("pid"),
                    "service_started": True, "tunnel_proven": False,
                    "application_proven": False, "custody": CUSTODY})
                return {
                    "schema": purpose.receipt_schema, "state": "ALREADY_STARTED",
                    "operation_id": intent["operation_id"], "commands": 0,
                    "service_started": True, "tunnel_proven": False,
                    "application_proven": False, "custody": CUSTODY,
                }
            binary_path = _client_binary_path(paths, intent)
            for process in system.processes():
                if _is_same_purpose(process, binary_path, purpose=purpose):
                    raise ValueError("a concurrent same-purpose client is already running")
            journal = stage_area.path / "operation"
            if not os.path.lexists(journal):
                _make_private_directory(journal)
            with publication.private(journal) as operation:
                names = operation.names()
                if "start-receipt.json" in names:
                    raise ValueError("the original start outcome requires reconciliation")
                require("start-intent.json" not in names,
                        "the original start outcome is unknown; reconcile before another command")
                operation.write("start-intent.json", canonical({
                    "schema": intent["schema"], "phase": "start-client",
                    "operation_id": intent["operation_id"],
                    "stage_digest": document["stage_digest"],
                    "arguments": arguments, "custody": CUSTODY,
                }))
            try:
                lock.check()
                require(_load_stage(stage_area, paths)["stage_digest"] == document["stage_digest"],
                        "original lifecycle stage changed")
                _installed_client(document, paths)
                result = system.launchctl_bootstrap(paths.plist)
            except (subprocess.TimeoutExpired, OSError) as exc:
                _write_service_receipt(journal, "start-receipt.json", {
                    "schema": purpose.receipt_schema, "state": "START_UNKNOWN",
                    "operation_id": intent["operation_id"], "commands": 1,
                    "error_type": type(exc).__name__, "service_started": False,
                    "tunnel_proven": False, "application_proven": False,
                    "custody": CUSTODY})
                raise ValueError("the start command outcome is unknown; reconcile it") from exc
            if result["returncode"] != 0:
                _write_service_receipt(journal, "start-receipt.json", {
                    "schema": purpose.receipt_schema, "state": "START_REFUSED",
                    "operation_id": intent["operation_id"], "commands": 1,
                    "returncode": result["returncode"], "detail": result["stderr"],
                    "service_started": False, "tunnel_proven": False,
                    "application_proven": False, "custody": CUSTODY})
                raise ValueError("the start command was refused")
            loaded, info = system.launchctl_print(purpose.label)
            if not _running_client(loaded, info, arguments, intent, paths, system):
                _write_service_receipt(journal, "start-receipt.json", {
                    "schema": purpose.receipt_schema, "state": "START_UNKNOWN",
                    "operation_id": intent["operation_id"], "commands": 1,
                    "service_started": False, "tunnel_proven": False,
                    "application_proven": False, "custody": CUSTODY})
                raise ValueError("the start command outcome is unknown; reconcile it")
            receipt = {
                "schema": purpose.receipt_schema, "state": "STARTED",
                "operation_id": intent["operation_id"], "commands": 1,
                "pid": info.get("pid"), "service_started": True,
                "tunnel_proven": False, "application_proven": False,
                "provider_effects_settled": False, "custody": CUSTODY,
            }
            _write_service_receipt(journal, "start-receipt.json", receipt)
            return receipt


def stop_client(*, paths=None, system=None, role_aliases=False):
    """Issue at most one exact bounded launchctl operation for this label."""
    _root()
    paths = paths or Paths()
    purpose = _contract_purpose(role_aliases, paths.purpose)
    system = system or System()
    with _PurposeLock(paths) as lock:
        stage_directory = _stage_directory(paths, role_aliases)
        with publication.private(stage_directory) as stage_area:
            document = _load_stage(stage_area, paths)
            intent = document["intent"]
            _installed_client(document, paths)
            _verify_client_binary(intent, paths, system)
            arguments = _plist_arguments(document["contents"]["client-plist.xml"], purpose=purpose)
            loaded, info = system.launchctl_print(purpose.label)
            if not loaded:
                require(not any(_is_same_purpose(p, _client_binary_path(paths, intent), purpose=purpose)
                                for p in system.processes()),
                        "an unowned application process remains; stop is unproven")
                _settle_service(stage_area, "stop-receipt.json", {
                    "schema": purpose.receipt_schema, "state": "STOPPED",
                    "operation_id": intent["operation_id"], "commands": 0,
                    "settled_by": "launchd_state_absence", "service_started": False,
                    "provider_effects_settled": False, "tunnel_proven": False,
                    "application_proven": False, "custody": CUSTODY})
                return {
                    "schema": purpose.receipt_schema, "state": "ALREADY_STOPPED",
                    "operation_id": intent["operation_id"], "commands": 0,
                    "service_started": False, "provider_effects_settled": False,
                    "tunnel_proven": False, "application_proven": False, "custody": CUSTODY,
                }
            require(list(info.get("arguments") or []) == arguments,
                    "a foreign launchd label owns this purpose; refusing to stop it")
            require(_running_client(loaded, info, arguments, intent, paths, system),
                    "the application process identity is unproven; refusing to stop")
            _require_lifecycle_intent(stage_area, "start", document, arguments)
            journal = stage_area.path / "operation"
            if not os.path.lexists(journal):
                _make_private_directory(journal)
            with publication.private(journal) as operation:
                names = operation.names()
                if "stop-receipt.json" in names:
                    raise ValueError("the original stop outcome requires reconciliation")
                require("stop-intent.json" not in names,
                        "the original stop outcome is unknown; reconcile before another command")
                operation.write("stop-intent.json", canonical({
                    "schema": intent["schema"], "phase": "stop-client",
                    "operation_id": intent["operation_id"],
                    "stage_digest": document["stage_digest"],
                    "arguments": arguments, "custody": CUSTODY,
                }))
            try:
                lock.check()
                require(_load_stage(stage_area, paths)["stage_digest"] == document["stage_digest"],
                        "original lifecycle stage changed")
                _installed_client(document, paths)
                result = system.launchctl_bootout(purpose.label)
            except (subprocess.TimeoutExpired, OSError) as exc:
                _write_service_receipt(journal, "stop-receipt.json", {
                    "schema": purpose.receipt_schema, "state": "STOP_UNKNOWN",
                    "operation_id": intent["operation_id"], "commands": 1,
                    "error_type": type(exc).__name__, "service_started": False,
                    "provider_effects_settled": False, "tunnel_proven": False,
                    "application_proven": False, "custody": CUSTODY})
                raise ValueError("the stop command outcome is unknown; reconcile it") from exc
            if result["returncode"] != 0:
                _write_service_receipt(journal, "stop-receipt.json", {
                    "schema": purpose.receipt_schema, "state": "STOP_REFUSED",
                    "operation_id": intent["operation_id"], "commands": 1,
                    "returncode": result["returncode"], "detail": result["stderr"],
                    "service_started": False, "provider_effects_settled": False,
                    "tunnel_proven": False, "application_proven": False, "custody": CUSTODY})
                raise ValueError("the stop command was refused")
            loaded, _ = system.launchctl_print(purpose.label)
            if loaded or any(_is_same_purpose(p, _client_binary_path(paths, intent), purpose=purpose)
                             for p in system.processes()):
                _write_service_receipt(journal, "stop-receipt.json", {
                    "schema": purpose.receipt_schema, "state": "STOP_UNKNOWN",
                    "operation_id": intent["operation_id"], "commands": 1,
                    "service_started": True, "provider_effects_settled": False,
                    "tunnel_proven": False, "application_proven": False, "custody": CUSTODY})
                raise ValueError("the stop command outcome is unknown; reconcile it")
            receipt = {
                "schema": purpose.receipt_schema, "state": "STOPPED",
                "operation_id": intent["operation_id"], "commands": 1,
                "service_started": False, "provider_effects_settled": False,
                "tunnel_proven": False, "application_proven": False, "custody": CUSTODY,
            }
            _write_service_receipt(journal, "stop-receipt.json", receipt)
            return receipt


def _require_lifecycle_intent(stage_area, phase, document, arguments):
    journal = stage_area.path / "operation"
    require(os.path.lexists(journal), "a live service lacks original operation custody")
    with publication.private(journal) as operation:
        name = phase + "-intent.json"
        require(name in operation.names(), "a live service lacks original operation custody")
        value = decode(operation.read(name))
        require(value.get("operation_id") == document["intent"]["operation_id"]
                and value.get("stage_digest") == document["stage_digest"]
                and value.get("arguments") == arguments,
                "lifecycle intent differs from the original stage")


def _settle_service(stage_area, name, receipt):
    """Settle a pending original intent from the live state, without a command."""
    journal = stage_area.path / "operation"
    if not os.path.lexists(journal):
        return
    with publication.private(journal) as operation:
        names = operation.names()
        intent_name = name.replace("-receipt.json", "-intent.json")
        if intent_name in names and name not in names:
            operation.write(name, canonical(receipt))


def _write_service_receipt(journal, name, receipt):
    with publication.private(journal) as operation:
        _write_once(operation, name, canonical(receipt))


# ------------------------------------------------------------------------ CLI


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    stage_parser = sub.add_parser("stage")
    stage_parser.add_argument("--source-repo", type=Path, required=True)
    stage_parser.add_argument("--source-sha", required=True)
    stage_parser.add_argument("--release-root", type=Path, required=True)
    stage_parser.add_argument("--release-commit-sha", required=True)
    stage_parser.add_argument("--release-tree-sha", required=True)
    stage_parser.add_argument("--qualification", dest="qualification_path", type=Path, required=True)
    stage_parser.add_argument("--credential", dest="credential_path", type=Path)
    stage_parser.add_argument("--role-aliases", action="store_true")
    stage_parser.add_argument("--predecessor-server-receipt", type=Path)
    server_parser = sub.add_parser("apply-server")
    server_parser.add_argument("--bundle", dest="bundle_path", type=Path, required=True)
    server_parser.add_argument("--expected-digest", required=True)
    server_reconcile = sub.add_parser("reconcile-server")
    server_reconcile.add_argument("--bundle", dest="bundle_path", type=Path, required=True)
    server_reconcile.add_argument("--expected-digest", required=True)
    client_parser = sub.add_parser("apply-client")
    client_parser.add_argument("--server-receipt", type=Path)
    client_parser.add_argument("--role-aliases", action="store_true")
    reconcile_parser = sub.add_parser("reconcile")
    reconcile_parser.add_argument("--server-receipt", type=Path)
    reconcile_parser.add_argument("--role-aliases", action="store_true")
    start_parser = sub.add_parser("start-client")
    start_parser.add_argument("--server-receipt", type=Path, required=True)
    start_parser.add_argument("--role-aliases", action="store_true")
    stop_parser = sub.add_parser("stop-client")
    stop_parser.add_argument("--role-aliases", action="store_true")
    return parser


def main(argv=None, *, paths=None, system=None):
    args = vars(build_parser().parse_args(argv))
    command = args.pop("command")
    if command == "stage":
        result = stage(**args, paths=paths, system=system)
    elif command == "apply-server":
        result = apply_server(**args, paths=paths, system=system)
    elif command == "reconcile-server":
        result = reconcile_server(**args, paths=paths, system=system)
    elif command == "apply-client":
        result = apply_client(**args, paths=paths, system=system)
    elif command == "reconcile":
        result = reconcile(**args, paths=paths, system=system)
    elif command == "start-client":
        result = start_client(**args, paths=paths, system=system)
    else:
        result = stop_client(**args, paths=paths, system=system)
    print(canonical(result).decode())
    return 0


if __name__ == "__main__":
    try:
        require(sys.flags.isolated and sys.dont_write_bytecode, "isolated no-bytecode invocation required")
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, install_source_policy.InstallSourcePolicyError,
            subprocess.SubprocessError) as exc:
        sys.stderr.write(_redact("application transport refused: %s" % exc) + "\n")
        raise SystemExit(65)
