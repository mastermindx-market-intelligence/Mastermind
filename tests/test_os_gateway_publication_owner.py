"""Offline owner tests for the OS gateway publication transaction.

Disposable in-process Root-custody fixtures only.  The full production module
runs its REAL transaction machinery (real directory flock, real fsync, real
atomic writes, the real publication rename and inode readback, the real
canonical audit-directory mkdir through a held parent descriptor) on a
temporary filesystem with the installed identity remapped, exactly like the
incumbent marker harness.  The REAL pure publication compiler runs against the
owner's real prepare/transaction path; only the fixed installed-path constants
it was built with are rebound to the disposable workspace.

Every host boundary (release identity, launchd state, port probe, password
database, sealed module origin) is a typed hermetic stub explicitly marked
TESTDATA below.  A stub is never a Root, auth, or positive permission proof,
and the compiler contract-drift negatives use an explicit DATA collaborator,
never a substituted helper acceptance.
"""
from __future__ import annotations

import copy
import dataclasses
import fcntl
import hashlib
import json
import os
import plistlib
import stat
import subprocess
import sys
import tempfile
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ops.executive_os import autonomy_control as control
from tests.test_executive_autonomy_control import (
    SHA,
    _install_marker_adapters,
    _marker_workspace,
)

TREE_SHA = "b" * 40
STUDIO_UID = 501
STUDIO_GID = 20
ISSUER = "https://auth.mastermind-x.com"
SUBJECT = "workspace-owner-7"
CLIENT_ID = "OsPublicationClient01"
PRIMARY_RESOURCE = "https://mcp.mastermind-x.com/ceo/executive"
NAMESPACE_DOMAIN = b"mastermind.os.executive.principal_scope.v1"
NOW = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)
SERVICE_ROOT = "root"


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# The pristine syscall functions, captured before any harness remapping so the
# mixed-identity adapter below observes one real identity and only rebinds it.
_TRUE_FSTAT = os.fstat
_TRUE_LSTAT = os.lstat
_TRUE_STAT = os.stat
# Production-origin tests change shared sys.platform; descriptor lookup must
# continue to use the physical host API, including during fixture teardown.
_TRUE_PLATFORM = sys.platform


# ---------------------------------------------------------------------------
# The independently accepted stdlib helper is joined here, never replaced by
# a second recipe. These fixtures make no actual Root-origin claim.
# ---------------------------------------------------------------------------


def _install_namespace_helper(monkeypatch) -> None:
    import importlib

    name = "integrations.mastermind_executive_app.principal_namespace"
    module = importlib.import_module(name)
    assert Path(module.__file__).resolve() == (
        Path(__file__).resolve().parents[1]
        / "integrations/mastermind_executive_app/principal_namespace.py"
    )
    monkeypatch.setitem(sys.modules, name, module)


# ---------------------------------------------------------------------------
# TESTDATA: closed DATA collaborator used ONLY by the compiler contract-drift
# negatives.  It mirrors the real frozen candidate contract so a drift can be
# aimed at one field; it performs no Root, auth or permission proof.
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _Artifact:
    path: str
    kind: str
    content: bytes
    sha256: str
    byte_count: int


@dataclasses.dataclass(frozen=True)
class _Candidate:
    schema: str
    operation: str
    expected_release_sha: str
    expected_bundle_digest: str
    before_mcp_bytes: bytes
    before_plist_bytes: bytes
    before_mcp_sha256: str
    before_plist_sha256: str
    artifacts: tuple
    publication_before_sha256: object = None


# ---------------------------------------------------------------------------
# Disposable host fixtures.
# ---------------------------------------------------------------------------


def _write_sealed(path: Path, payload: bytes, mode: int = 0o444) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        os.write(descriptor, payload)
    finally:
        os.close(descriptor)
    os.chmod(path, mode)


def _policy(*, policy_id, resource, scopes, subjects):
    from integrations.business_mcp_auth.contracts import AUTH_POLICY_SCHEMA

    return {
        "schema": AUTH_POLICY_SCHEMA,
        "policy_id": policy_id,
        "resource": resource,
        "resource_metadata_url": ISSUER + "/.well-known/oauth-resource",
        "issuer": ISSUER,
        "authorization_servers": [ISSUER],
        "jwks_uri": ISSUER + "/jwks.json",
        "required_scopes": list(scopes),
        "allowed_subject_digests": list(subjects),
        "allowed_algorithms": ["RS256"],
        "clock_skew_seconds": 30,
        "max_token_lifetime_seconds": 600,
        "jwks_cache_ttl_seconds": 300,
        "unknown_kid_refresh_cooldown_seconds": 60,
        "fetch_failure_backoff_seconds": 60,
    }


def _identity_values():
    from integrations.business_mcp_auth.claims import _client_ref
    from integrations.business_mcp_auth.contracts import subject_digest
    from common.executive_workspace_contract import RESOURCE, SCOPE

    return {
        "resource": RESOURCE,
        "scope": SCOPE,
        "subject_digest": subject_digest(issuer=ISSUER, subject=SUBJECT),
        "client_ref": _client_ref({"client_id": CLIENT_ID}, ISSUER),
        "issuer_digest": digest(ISSUER.encode("utf-8")),
    }


def _prior_mcp_document():
    from integrations.mastermind_executive_app.gateway import (
        READ_SCOPE,
        SUBMIT_SCOPE,
    )

    identity = _identity_values()
    workspace_policy = _policy(
        policy_id="workspace.read.policy",
        resource=identity["resource"],
        scopes=[identity["scope"]],
        subjects=[identity["subject_digest"]],
    )
    bindings = {
        "schema": "mastermind.workspace_acquisition_bindings.v1",
        "profiles": {
            "web": {
                "enabled": True,
                "binding": {
                    "policy_id": workspace_policy["policy_id"],
                    "issuer_digest": identity["issuer_digest"],
                    "subject_digest": identity["subject_digest"],
                    "client_ref": identity["client_ref"],
                    "resource": identity["resource"],
                    "scopes": [identity["scope"]],
                    "permission_digest": "9" * 64,
                },
            },
            "mac": {"enabled": False, "binding": None},
        },
    }
    document = {
        "schema": "mastermind.executive_mcp_install.v1",
        "release_sha": SHA,
        "service_uid": 458,
        "port": 8443,
        "executive_mcp_profile": "web_ceo_v3",
        "ceo_ingress_socket_path": "/var/run/mastermind-executive/ceo-ingress.sock",
        "audit_root": "/var/log/mastermind-executive/mcp-auth",
        "policies": {
            "read": _policy(
                policy_id="executive.read.policy",
                resource=PRIMARY_RESOURCE,
                scopes=[READ_SCOPE],
                subjects=[identity["subject_digest"]],
            ),
            "submit": _policy(
                policy_id="executive.submit.policy",
                resource=PRIMARY_RESOURCE,
                scopes=sorted((SUBMIT_SCOPE, READ_SCOPE)),
                subjects=[identity["subject_digest"]],
            ),
        },
        "workspace": {"policy": workspace_policy, "bindings": bindings},
    }
    return document, workspace_policy


def _launch_manifest_bytes():
    from ops.executive_os import os_release_assets as assets

    value = {
        "v": 1,
        "workstream": "WS:OSGateway",
        "priority": 5,
        "projects": [{"ref": "os-gateway", "label": "OS Gateway"}],
        "profiles": [{"ref": "research_only", "label": "Research only"}],
        "attemptLimit": 3,
    }
    return assets._canonical(value)


def _stage_release(
    root: Path, *, mcp_document, workspace_policy
) -> dict:
    """The sealed target release tree with its launch build receipt."""

    from integrations.studio_direct_mcp.private_service import STAGE_FILES
    from ops.executive_os import os_release_assets as assets
    from ops.executive_os.executive_mcp_entry import OS_EXECUTIVE_RESOURCE

    release = root / "releases" / SHA
    source = release / "integrations/studio_direct_mcp"
    stage_payload = {
        name: f"studio-module {name}\n".encode("utf-8") for name in STAGE_FILES
    }
    for name, payload in stage_payload.items():
        _write_sealed(source / name, payload, 0o444)
    _write_sealed(
        source / "commission_file.py",
        b"# incumbent fixed-file commission writer\n",
        0o444,
    )
    _write_sealed(
        release / "ops/executive_os/os_commission_auth_entry.py",
        b"# incumbent sealed authentication helper\n",
        0o444,
    )
    _write_sealed(
        release / ".executive-release-manifest.json",
        control._encoded_json({"commit_sha": SHA, "tree_sha": TREE_SHA}),
        0o444,
    )

    dist = release / "app/mastermind_os/dist"
    css_name = "assets/index-a1b2c3.css"
    js_name = "assets/index-a1b2c3.js"
    dist_files = {
        "index.html": (
            "<html><head>"
            f'<link href="/os/{css_name}">'
            f'<script src="/os/{js_name}"></script>'
            "</head><body></body></html>\n"
        ).encode("utf-8"),
        css_name: b"body{}\n",
        js_name: b"window.os=1;\n",
    }
    for name, payload in dist_files.items():
        _write_sealed(dist / name, payload, 0o444)
    actual = assets.build_os_asset_manifest(release)
    manifest_bytes = assets._canonical(actual)
    _write_sealed(dist / "asset-manifest.json", manifest_bytes, 0o444)

    launch_bytes = _launch_manifest_bytes()
    receipt = {
        "schema": assets.LAUNCH_SCHEMA,
        "source_sha": SHA,
        "source_tree": TREE_SHA,
        "source_inputs": {name: "5" * 64 for name in assets.LAUNCH_INPUTS},
        "mode": assets.LAUNCH_MODE,
        "recipe": assets.RECIPE,
        "builder": {
            "operator_uid": 502,
            "tools": {"/usr/local/bin/node": "6" * 64, "/usr/local/bin/npm": "7" * 64},
        },
        "web_client_id": CLIENT_ID,
        "asset_manifest_sha256": assets._hash(manifest_bytes),
        "executive_resource": OS_EXECUTIVE_RESOURCE,
        "launch_config": launch_bytes.decode("utf-8"),
        "launch_config_sha256": assets._hash(launch_bytes),
    }
    _write_sealed(
        release / "app/mastermind_os/web-build-receipt.json",
        assets._canonical(receipt),
        0o444,
    )
    return {"release": release, "source": source, "stage_payload": stage_payload}


def _stage_studio(home: Path, release: Path, *, dependency: bool = True) -> dict:
    """The one dedicated Studio publication seat, staged and STOPPED."""

    from integrations.studio_direct_mcp.private_service import (
        MANIFEST_VERSION,
        STAGE_FILES,
        _dependency_tree_hash,
    )

    base = home / control._GATEWAY_STUDIO_BASE_REL
    source = release / "integrations/studio_direct_mcp"
    files = {}
    for name in STAGE_FILES:
        payload = (source / name).read_bytes()
        _write_sealed(base / name, payload, 0o600)
        files[name] = digest(payload)
    node = home / "tools/node"
    backend = home / "tools/os-gateway-backend.mjs"
    _write_sealed(node, b"#!/bin/sh\nexec true\n", 0o500)
    _write_sealed(backend, b"export const osGateway = 1;\n", 0o400)
    node_modules = base / "node_modules"
    _write_sealed(node_modules / "tiny/index.js", b"module.exports = 1;\n", 0o600)
    dependency_hash = (
        _dependency_tree_hash(node_modules) if dependency else None
    )
    config = {
        "accountLabel": control.OS_GATEWAY_STUDIO_ACCOUNT,
        "host": "127.0.0.1",
        "testMode": False,
        "port": control.OS_GATEWAY_STUDIO_PORT,
        "command": str(node),
        "args": [str(backend), "--no-onboarding"],
        "cwd": str(home),
        "childEnv": {"NODE_OPTIONS": ""},
        "stateDir": str(base / "state"),
        "maxSessions": 256,
        "requestTimeoutMs": 300000,
        "idleTimeoutMs": 1800000,
        "reclaimIdleGraceMs": 30000,
        "gitPublish": {"enabled": True},
        "paperDesign": {"enabled": False},
        "repositoryWorkspaces": {
            "enabled": True,
            "allowedRepositories": ["mastermind", "macro", "terminal"],
        },
    }
    config_bytes = control._encoded_json(config)
    _write_sealed(base / "config.json", config_bytes, 0o600)
    gateway_path = base / "private-tunnel-gateway.mjs"
    plist_payload = {
        "Label": control.OS_GATEWAY_STUDIO_LABEL,
        "ProgramArguments": [str(node), str(gateway_path), str(base / "config.json")],
    }
    agent_plist_bytes = plistlib.dumps(plist_payload, fmt=plistlib.FMT_XML)
    _write_sealed(
        home / control._GATEWAY_STUDIO_PLIST_REL, agent_plist_bytes, 0o600
    )
    manifest = {
        "version": MANIFEST_VERSION,
        "account": control.OS_GATEWAY_STUDIO_ACCOUNT,
        "label": control.OS_GATEWAY_STUDIO_LABEL,
        "files": files,
        "source": str(source),
        "node": str(node),
        "backend": str(backend),
        "nodeHash": digest(node.read_bytes()),
        "backendHash": digest(backend.read_bytes()),
        "dependencyTreeHash": dependency_hash,
        "host": "127.0.0.1",
        "port": control.OS_GATEWAY_STUDIO_PORT,
        "configHash": digest(config_bytes),
        "plistHash": digest(agent_plist_bytes),
    }
    manifest_bytes = control._encoded_json(manifest)
    _write_sealed(base / "manifest.json", manifest_bytes, 0o600)
    (base / "state").mkdir(mode=0o700, exist_ok=True)
    (base / "logs").mkdir(mode=0o700, exist_ok=True)
    return {
        "home": home,
        "base": base,
        "manifest": manifest,
        "config_bytes": config_bytes,
        "node": node,
        "backend": backend,
    }


def _mcp_plist_bytes(release: Path, mcp_config_path: Path) -> bytes:
    """The closed installed gateway plist profile with the release substituted."""

    from control_plane import executive_installed_peer as installed

    profile = copy.deepcopy(installed._EXPECTED_PLIST_PROFILES["gateway"])
    profile["ProgramArguments"][3] = os.fspath(
        release / "ops/executive_os/executive_mcp_entry.py"
    )
    profile["ProgramArguments"][5] = os.fspath(mcp_config_path)
    profile["WorkingDirectory"] = os.fspath(release)
    return plistlib.dumps(profile, fmt=plistlib.FMT_XML)


def _stage_audit_leaf(root: Path, *, entries=(), mode: int = 0o700) -> Path:
    """The canonical audit leaf: explicit absence by default, or occupied."""

    leaf = root / "audit" / "os-commission-publication"
    leaf.mkdir(mode=mode, parents=True)
    for name, payload, entry_mode in entries:
        _write_sealed(leaf / name, payload, entry_mode)
    return leaf


def _mixed_identity(home: Path, audit_leaf: Path):
    """TESTDATA mixed installed-identity adapter (never a Root-origin proof).

    The Studio seat subtree and the canonical audit leaf observe as the real
    UID 501 pair; every other path observes as Root.  File descriptors are
    mapped through their /proc path so a held descriptor observes the same
    installed identity as its name.
    """

    real_lstat = _TRUE_LSTAT
    real_fstat = _TRUE_FSTAT

    def inside(text: str, root: Path) -> bool:
        base = os.fspath(root)
        return text == base or text.startswith(base + os.sep)

    def identity_for(text: str):
        if inside(text, home) or inside(text, audit_leaf):
            return STUDIO_UID, STUDIO_GID
        return 0, 0

    def rebind(info: os.stat_result, uid: int, gid: int) -> os.stat_result:
        return os.stat_result(
            (
                info.st_mode,
                info.st_ino,
                info.st_dev,
                info.st_nlink,
                uid,
                gid,
                info.st_size,
                info.st_atime,
                info.st_mtime,
                info.st_ctime,
            ),
            {
                "st_atime_ns": info.st_atime_ns,
                "st_mtime_ns": info.st_mtime_ns,
                "st_ctime_ns": info.st_ctime_ns,
            },
        )

    # TESTDATA only: the disposable pytest prefix is not a production Root
    # home chain. Normalize ONLY those ancestor metadata observations, while
    # preserving real types/dev/inode/timestamps, relative opens and FD ACLs.
    # This is not installed-custody proof and never changes production policy.
    prefix = {os.fspath(path) for path in home.parents}

    def descriptor_path(descriptor):
        if _TRUE_PLATFORM == "darwin":
            raw = fcntl.fcntl(int(descriptor), 50, b"\0" * 1024)
            return os.fsdecode(raw.split(b"\0", 1)[0])
        return os.readlink(f"/proc/self/fd/{int(descriptor)}")

    def observed(info, text):
        info = rebind(info, *identity_for(text))
        if text in prefix and stat.S_ISDIR(info.st_mode):
            fields = list(info)
            fields[0] = stat.S_IFDIR | 0o755
            info = os.stat_result(fields, {
                "st_atime_ns": info.st_atime_ns,
                "st_mtime_ns": info.st_mtime_ns,
                "st_ctime_ns": info.st_ctime_ns,
            })
        return info

    def bound_lstat(path):
        return observed(real_lstat(path), os.fspath(path))

    def bound_stat(path, *, dir_fd=None, follow_symlinks=True):
        info = _TRUE_STAT(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)
        if isinstance(path, int):
            text = descriptor_path(path)
        else:
            text = os.fspath(path)
            if dir_fd is not None:
                text = os.path.join(descriptor_path(dir_fd), text)
        return observed(info, text)

    def bound_fstat(descriptor):
        return observed(real_fstat(descriptor), descriptor_path(descriptor))

    return bound_lstat, bound_stat, bound_fstat



def _harness_chown(path, uid, gid):
    """TESTDATA: remap only the identities this disposable workspace can hold."""

    if (uid, gid) not in ((0, 0), (STUDIO_UID, STUDIO_GID)):
        raise ValueError("marker harness only adapts the installed identities")
    return None


def _rebind_installed_paths(monkeypatch, root: Path, config_root: Path) -> None:
    """TESTDATA: rebind the fixed installed-path constants to the workspace.

    The pure compiler was frozen against the installed absolute paths; the
    disposable workspace occupies the same logical topology.  These rebinds
    are path substitutions only — no validation, seal or custody law changes.
    """

    from control_plane import executive_installed_peer as installed
    from ops.executive_os import os_gateway_publication as compiler

    monkeypatch.setattr(installed, "_SERVICE_RELEASES", os.fspath(root / "releases"))
    monkeypatch.setattr(
        compiler, "MCP_CONFIG_PATH", os.fspath(control.OS_GATEWAY_MCP_CONFIG)
    )
    monkeypatch.setattr(
        compiler, "MCP_PLIST_PATH", os.fspath(control.OS_GATEWAY_MCP_PLIST)
    )
    monkeypatch.setattr(
        compiler,
        "COMMISSION_CONFIG_PATH",
        os.fspath(control.OS_GATEWAY_COMMISSION_GRANT),
    )
    monkeypatch.setattr(
        compiler, "AUDIT_DIRECTORY", os.fspath(control._GATEWAY_AUDIT_DIRECTORY)
    )
    profile = copy.deepcopy(installed._EXPECTED_PLIST_PROFILES["gateway"])
    profile["ProgramArguments"][3] = (
        installed._RELEASE_PLACEHOLDER + "/ops/executive_os/executive_mcp_entry.py"
    )
    profile["ProgramArguments"][5] = os.fspath(control.OS_GATEWAY_MCP_CONFIG)
    monkeypatch.setattr(compiler, "GATEWAY_PLIST_PROFILE", profile)


class Fixture:
    def __init__(self, host, config_root, tmp_path, home, studio, bundle, mcp_bytes, plist_bytes):
        self.host = host
        self.config_root = config_root
        self.tmp_path = tmp_path
        self.home = home
        self.studio = studio
        self.bundle = bundle
        self.mcp_bytes = mcp_bytes
        self.plist_bytes = plist_bytes

    @property
    def release(self) -> Path:
        return self.tmp_path / SERVICE_ROOT / "releases" / SHA

    @property
    def audit_leaf(self) -> Path:
        return self.tmp_path / SERVICE_ROOT / "audit" / "os-commission-publication"

    def target_paths(self):
        return (
            control.OS_GATEWAY_MCP_CONFIG,
            control.OS_GATEWAY_MCP_PLIST,
            control.OS_GATEWAY_COMMISSION_GRANT,
        )

    def request(self, **overrides):
        value = {
            "expected_sha": SHA,
            "bundle_digest": self.bundle,
            "prior_mcp_config_sha256": digest(self.mcp_bytes),
            "prior_mcp_plist_sha256": digest(self.plist_bytes),
            "prior_grant_absent": True,
        }
        value.update(overrides)
        return control.GatewayPublicationRequest(**value)

    def publish(self, **overrides):
        return control.execute_gateway_publication(
            self.host, self.request(**overrides), now=NOW
        )

    def reconcile(self, **overrides):
        value = {
            "expected_sha": SHA,
            "bundle_digest": self.bundle,
            "transaction_id": "autonomy-" + "1" * 12,
        }
        value.update(overrides)
        host = value.pop("host", self.host)
        return control.reconcile_gateway_publication(
            host, control.GatewayPublicationRequest(**value), now=NOW
        )

    def teardown(self):
        if self.host._transaction_owner_fd is not None:
            self.host._release_transaction_owner()

    def fresh_host(self, monkeypatch):
        """A new owner process: the previous holder of the marker is gone."""

        host = control.ProductionGatewayPublicationHost()
        _install_host_boundaries(monkeypatch, host)
        return host


def _install_host_boundaries(monkeypatch, host) -> None:
    """TESTDATA host boundaries: typed hermetic stubs, never origin proofs."""

    for name, function in {
        "effective_uid": lambda: 0,
        "require_exact_install": lambda sha: sha,
        "require_gateway_module_origin": lambda sha: None,
        "require_services_already_stopped": lambda: None,
        "require_service_uids_quiescent": lambda: None,
        "require_runtime_quiescent": lambda config: None,
        "require_gateway_generation_current": lambda **kwargs: SHA,
        "_qualify_published_gateway": lambda manifest: None,
        "_launchd_state": lambda target: "absent",
        "_studio_port_absent": lambda: True,
    }.items():
        monkeypatch.setattr(host, name, function)


@pytest.fixture
def gateway_tmp_path():
    # The reader deliberately observes mutation timestamps for the complete
    # ancestor chain. macOS's shared /var/folders/.../T changes as unrelated
    # applications create temp files; it is not a stable fixture namespace.
    # Keep this inert tree in our own admitted carrier instead of weakening
    # the real reader's ancestor checks or ignoring observed mutations.
    with tempfile.TemporaryDirectory(
        prefix=".gateway-owner-fixture-", dir=Path(__file__).resolve().parents[1]
    ) as directory:
        yield Path(directory)


@pytest.fixture
def gateway(monkeypatch, gateway_tmp_path):
    tmp_path = gateway_tmp_path
    config_root = _marker_workspace(tmp_path)
    _install_marker_adapters(monkeypatch, config_root)
    root = tmp_path / SERVICE_ROOT
    staged = _stage_release(root, mcp_document=None, workspace_policy=None)
    release = staged["release"]
    home = tmp_path / "Users" / "studio"
    home.mkdir(mode=0o750, parents=True)
    studio = _stage_studio(home, release)
    mcp_document, _workspace_policy = _prior_mcp_document()
    mcp_bytes = control._encoded_json(mcp_document)
    mcp_config_path = config_root / "executive-mcp.json"
    _write_sealed(mcp_config_path, mcp_bytes, 0o644)
    plist_bytes = _mcp_plist_bytes(release, mcp_config_path)
    _write_sealed(
        tmp_path / "LaunchDaemons" / "com.mastermind.executive.mcp.plist",
        plist_bytes,
        0o644,
    )
    # The qualified fixed audit parent exists; the canonical leaf is absent.
    (root / "audit").mkdir(mode=0o755)
    audit_leaf = root / "audit" / "os-commission-publication"

    # Gateway root rebindings: the Studio seat and the canonical audit leaf
    # observe as the real UID 501 pair, everything else as Root.
    for target, name, value in (
        (control, "SYSTEM_ROOT", root),
        (control, "OS_GATEWAY_RECEIPT", config_root / "os-gateway-publication-v1.json"),
        (control, "OS_GATEWAY_MCP_CONFIG", mcp_config_path),
        (
            control,
            "OS_GATEWAY_MCP_PLIST",
            tmp_path / "LaunchDaemons" / "com.mastermind.executive.mcp.plist",
        ),
        (
            control,
            "OS_GATEWAY_COMMISSION_GRANT",
            config_root / "os-commission-publication.json",
        ),
        (control, "_GATEWAY_AUDIT_DIRECTORY", audit_leaf),
    ):
        monkeypatch.setattr(target, name, value)
    bound_lstat, bound_stat, bound_fstat = _mixed_identity(home, audit_leaf)
    monkeypatch.setattr(Path, "lstat", bound_lstat)
    monkeypatch.setattr(control.os, "stat", bound_stat)
    monkeypatch.setattr(control.os, "fstat", bound_fstat)
    monkeypatch.setattr(control.os, "chown", _harness_chown)
    monkeypatch.setattr(control.os, "fchown", _harness_chown)
    monkeypatch.setattr(control, "_has_acl", lambda _path: False)
    # The sealed-ancestor walk cannot be satisfied under a disposable /tmp
    # chain (the incumbent asset suites stub the same boundary); custody in
    # these tests is carried by the mixed-identity adapter and real mode,
    # link-count and ACL-free byte checks instead.
    from ops.executive_os import os_release_assets as _assets

    monkeypatch.setattr(_assets, "require_sealed_path", lambda *a, **k: None)
    real_getpwuid = control.pwd.getpwuid
    real_getpwnam = control.pwd.getpwnam

    class _Record:
        pw_uid = STUDIO_UID
        pw_gid = STUDIO_GID
        pw_name = "studio-os-owner"

        def __init__(self):
            self.pw_dir = str(home)

    monkeypatch.setattr(
        control.pwd,
        "getpwuid",
        lambda uid: _Record() if uid == STUDIO_UID else real_getpwuid(uid),
    )
    monkeypatch.setattr(
        control.pwd, "getpwnam",
        lambda name: _Record() if name == "studio-os-owner" else real_getpwnam(name),
    )
    _install_namespace_helper(monkeypatch)
    _rebind_installed_paths(monkeypatch, root, config_root)

    host = control.ProductionGatewayPublicationHost()
    _install_host_boundaries(monkeypatch, host)

    # The one qualified bundle digest, derived by the host's own qualification.
    _receipt, _document, bundle = host.qualify_launch_publication(SHA, TREE_SHA)
    fixture = Fixture(host, config_root, tmp_path, home, studio, bundle, mcp_bytes, plist_bytes)
    yield fixture
    fixture.teardown()


# ---------------------------------------------------------------------------
# Publication success and the exact write set.
# ---------------------------------------------------------------------------


def test_publish_writes_exactly_three_targets_and_completes_marker(gateway):
    s = gateway
    before_control = control.CONTROL_CONFIG.read_bytes()
    before_worker = control.WORKER_CONFIG.read_bytes()
    assert not s.audit_leaf.exists()
    result = s.publish()
    assert result.replayed is False
    assert result.transaction_id.startswith("autonomy-")
    config = json.loads(control.OS_GATEWAY_MCP_CONFIG.read_bytes())
    assert config["release_sha"] == SHA
    assert config["os_executive_transport"] is True
    assert config["policies"] == json.loads(s.mcp_bytes)["policies"]
    assert control.OS_GATEWAY_MCP_PLIST.read_bytes() == plistlib.dumps(
        plistlib.loads(s.plist_bytes), fmt=plistlib.FMT_XML
    )
    grant = json.loads(control.OS_GATEWAY_COMMISSION_GRANT.read_bytes())
    identity = s.host.qualify_workspace_identity(s.mcp_bytes, web_client_id=CLIENT_ID)
    derived = s.host._derived_namespace_scope(identity)
    template = s.host._gateway_template(_launch_manifest_bytes().decode("utf-8"))
    assert grant["schema"] == control.OS_GATEWAY_GRANT_SCHEMA
    assert set(grant) == set(control.OS_GATEWAY_GRANT_KEYS)
    assert grant["studio_uid"] == STUDIO_UID
    assert grant["studio_account"] == control.OS_GATEWAY_STUDIO_ACCOUNT
    assert grant["studio_port"] == control.OS_GATEWAY_STUDIO_PORT
    assert grant["base_sha"] == SHA
    assert grant["audit_directory"] == os.fspath(s.audit_leaf)
    assert grant["policy"] == s.host._derived_publication_policy(
        s.mcp_bytes, expected_sha=SHA, studio_port=control.OS_GATEWAY_STUDIO_PORT
    )
    assert grant["grants"] == [{"principal_scope": derived, "template": template}]
    assert not control.AUTONOMY_TRANSACTION.exists()
    assert control.CONTROL_CONFIG.read_bytes() == before_control
    assert control.WORKER_CONFIG.read_bytes() == before_worker
    for path in s.target_paths():
        info = path.stat()
        expected_mode = 0o444 if path == control.OS_GATEWAY_COMMISSION_GRANT else 0o644
        assert stat.S_IMODE(info.st_mode) == expected_mode
    # The canonical audit prerequisite was produced exactly once: real 0700
    # directory below the qualified fixed parent.
    assert s.audit_leaf.is_dir()
    assert stat.S_IMODE(s.audit_leaf.stat().st_mode) == 0o700
    assert s.audit_leaf.parent.is_dir()


def test_audit_leaf_occupied_is_reused_without_recreation(gateway):
    s = gateway
    leaf = _stage_audit_leaf(
        s.tmp_path / SERVICE_ROOT,
        entries=[("auth-audit.jsonl", b'{"audit":"entry"}\n', 0o600)],
    )
    before = leaf.stat().st_ino
    s.publish()
    assert leaf.stat().st_ino == before
    assert sorted(os.listdir(leaf)) == ["auth-audit.jsonl"]


def test_terminal_receipt_is_closed_and_binds_original_id_and_target_hashes(gateway):
    s = gateway
    transaction = s.publish().transaction_id
    payload = json.loads(control.OS_GATEWAY_RECEIPT.read_bytes())
    assert set(payload) == {
        "schema_version",
        "state",
        "operation",
        "transaction_id",
        "expected_sha",
        "release_bundle_digest",
        "target_mcp_config_sha256",
        "target_mcp_plist_sha256",
        "target_commission_grant_sha256",
        "prior_commission_grant_present",
        "observed_at",
        "tool_version",
    }
    assert payload["schema_version"] == control.OS_GATEWAY_RECEIPT_SCHEMA
    assert payload["operation"] == control.OS_GATEWAY_PUBLICATION
    assert payload["state"] == "PUBLISHED"
    assert payload["transaction_id"] == transaction
    assert payload["expected_sha"] == SHA
    assert payload["release_bundle_digest"] == s.bundle
    assert payload["target_mcp_config_sha256"] == digest(
        control.OS_GATEWAY_MCP_CONFIG.read_bytes()
    )
    assert payload["target_mcp_plist_sha256"] == digest(
        control.OS_GATEWAY_MCP_PLIST.read_bytes()
    )
    assert payload["target_commission_grant_sha256"] == digest(
        control.OS_GATEWAY_COMMISSION_GRANT.read_bytes()
    )
    assert payload["prior_commission_grant_present"] is False
    info = control.OS_GATEWAY_RECEIPT.stat()
    assert stat.S_IMODE(info.st_mode) == 0o444


# ---------------------------------------------------------------------------
# Refusals before any protected read or write.
# ---------------------------------------------------------------------------


def test_non_root_refuses_before_any_target_read_or_write(gateway):
    s = gateway

    def not_root():
        control.require_root_privilege(1)

    s.host.effective_uid = not_root
    with pytest.raises(control.HostControlError) as excinfo:
        s.publish()
    assert excinfo.value.code == "privilege_required"
    assert not control.AUTONOMY_TRANSACTION.exists()
    assert not control.OS_GATEWAY_COMMISSION_GRANT.exists()
    assert not control.OS_GATEWAY_RECEIPT.exists()
    assert control.OS_GATEWAY_MCP_CONFIG.read_bytes() == s.mcp_bytes
    assert control.OS_GATEWAY_MCP_PLIST.read_bytes() == s.plist_bytes


def test_install_and_bundle_and_preimage_refuses_precede_every_write(gateway, monkeypatch):
    s = gateway

    def foreign_release(sha):
        raise control.ArmAdmissionError("install_gate_failed")

    s.host.require_exact_install = foreign_release
    with pytest.raises(control.ArmAdmissionError):
        s.publish()
    assert not control.OS_GATEWAY_COMMISSION_GRANT.exists()
    assert not control.AUTONOMY_TRANSACTION.exists()

    s.host.require_exact_install = lambda sha: sha
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish(bundle_digest="0" * 64)
    assert excinfo.value.code == "gateway_bundle_digest_mismatch"

    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish(prior_mcp_config_sha256="0" * 64)
    assert excinfo.value.code == "gateway_target_invalid"
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish(prior_mcp_plist_sha256="0" * 64)
    assert excinfo.value.code == "gateway_target_invalid"
    assert not control.AUTONOMY_TRANSACTION.exists()
    assert not control.OS_GATEWAY_COMMISSION_GRANT.exists()


def test_grant_expectation_conflicts_refuse_before_effects(gateway):
    s = gateway
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish(prior_grant_absent=False, prior_grant_sha256=None)
    assert excinfo.value.code == "gateway_grant_state_conflict"
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish(prior_grant_absent=True, prior_grant_sha256="a" * 64)
    assert excinfo.value.code == "gateway_grant_state_conflict"
    payload = b'{"schema":"x"}\n'
    _write_sealed(control.OS_GATEWAY_COMMISSION_GRANT, payload, 0o444)
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish(prior_grant_absent=True)
    assert excinfo.value.code == "gateway_grant_state_conflict"
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish(prior_grant_absent=False, prior_grant_sha256="b" * 64)
    assert excinfo.value.code == "gateway_grant_state_conflict"
    assert control.OS_GATEWAY_COMMISSION_GRANT.read_bytes() == payload
    assert not control.AUTONOMY_TRANSACTION.exists()


def test_occupied_grant_is_replaced_only_through_exact_cas(gateway):
    s = gateway
    payload = control._encoded_json({"schema": "mastermind.os_commission_publication.v1"})
    _write_sealed(control.OS_GATEWAY_COMMISSION_GRANT, payload, 0o444)
    transaction = s.publish(prior_grant_absent=False, prior_grant_sha256=digest(payload))
    assert transaction.replayed is False
    grant = json.loads(control.OS_GATEWAY_COMMISSION_GRANT.read_bytes())
    assert grant["schema"] == control.OS_GATEWAY_GRANT_SCHEMA
    assert json.loads(control.OS_GATEWAY_RECEIPT.read_bytes())[
        "prior_commission_grant_present"
    ] is True
    assert not control.AUTONOMY_TRANSACTION.exists()


# ---------------------------------------------------------------------------
# Sealed module origin: real root on Darwin from the fixed installed release.
# ---------------------------------------------------------------------------


def test_unsealed_module_origin_refuses_before_receipt_or_marker_io(
    gateway, monkeypatch
):
    s = gateway
    host = control.ProductionGatewayPublicationHost()

    # Not Darwin: the actual platform gate refuses first.
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        host.require_gateway_module_origin(SHA)
    assert excinfo.value.code == "gateway_target_invalid"

    # Actual root identity is required, not just a claim.
    monkeypatch.setattr(control.sys, "platform", "darwin")
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        host.require_gateway_module_origin(SHA)
    assert excinfo.value.code == "gateway_target_invalid"

    # A self-reported expected SHA never admits an unsealed module location.
    monkeypatch.setattr(control.os, "getuid", lambda: 0)
    monkeypatch.setattr(control.os, "geteuid", lambda: 0)
    assert Path(__file__).absolute() != (
        control.SYSTEM_ROOT / "releases" / SHA / "ops/executive_os/autonomy_control.py"
    )
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        host.require_gateway_module_origin(SHA)
    assert excinfo.value.code == "gateway_target_invalid"
    assert not control.AUTONOMY_TRANSACTION.exists()
    assert not control.OS_GATEWAY_RECEIPT.exists()


# ---------------------------------------------------------------------------
# The incumbent MCP generation stays enabled and running (never operated).
# ---------------------------------------------------------------------------


def test_gateway_generation_requires_exact_installed_plist_and_running_state(
    gateway, monkeypatch
):
    s = gateway
    from control_plane import executive_installed_peer as installed

    # The REAL generation observation, invoked past the host's TESTDATA stub.
    def current(**kwargs):
        return control.ProductionGatewayPublicationHost.require_gateway_generation_current(
            s.host, **kwargs
        )

    observation = types.SimpleNamespace(release=SHA, digest=digest(s.plist_bytes))
    monkeypatch.setattr(
        installed, "_verify_role_plist", lambda topology, budget: observation
    )
    monkeypatch.setattr(s.host, "_launchd_state", lambda target: "running")
    monkeypatch.setattr(s.host, "_gateway_service_enabled", lambda: True)
    allowed = frozenset({digest(s.plist_bytes)})
    assert (
        current(plist_sha256s=allowed, release_shas=frozenset({SHA})) == SHA
    )

    # A foreign installed plist image never joins the exact prior generation.
    observation.digest = "0" * 64
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        current(plist_sha256s=allowed, release_shas=frozenset({SHA}))
    assert excinfo.value.code == "gateway_mcp_generation_invalid"

    # A foreign pinned release refuses even with an exact image.
    observation.digest = digest(s.plist_bytes)
    observation.release = "d" * 40
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        current(plist_sha256s=allowed, release_shas=frozenset({SHA}))
    assert excinfo.value.code == "gateway_mcp_generation_invalid"

    # The daemon must actually be running now: registered-but-stopped refuses.
    observation.release = SHA
    monkeypatch.setattr(s.host, "_launchd_state", lambda target: "registered")
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        current(plist_sha256s=allowed, release_shas=frozenset({SHA}))
    assert excinfo.value.code == "gateway_mcp_generation_invalid"


def test_gateway_service_enabled_parses_the_closed_override_table(gateway, monkeypatch):
    s = gateway

    def table(stdout):
        def run(argv, **kwargs):
            return subprocess.CompletedProcess(
                argv, 0, stdout=stdout.encode("utf-8"), stderr=b""
            )

        return run

    good = 'disabled services = {\n"com.mastermind.executive.mcp" => enabled\n}\n'
    monkeypatch.setattr(control.subprocess, "run", table(good))
    assert s.host._gateway_service_enabled() is True

    # A complete table without this label's row means default-enabled.
    monkeypatch.setattr(
        control.subprocess, "run", table('disabled services = {\n"other" => enabled\n}\n')
    )
    assert s.host._gateway_service_enabled() is True

    for stdout in (
        'disabled services = {\n"com.mastermind.executive.mcp" => disabled\n}\n',
        'disabled services = {\n"com.mastermind.executive.mcp" => true\n}\n',
        "disabled services = {\n",  # structurally incomplete
        'disabled services = {\n"com.mastermind.executive.mcp" => enabled\n"x" => extra\n}\n',
    ):
        monkeypatch.setattr(control.subprocess, "run", table(stdout))
        with pytest.raises(control.GatewayPublicationError) as excinfo:
            s.host._gateway_service_enabled()
        assert excinfo.value.code == "gateway_mcp_generation_invalid"

    def failing(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 3, stdout=b"", stderr=b"boom")

    monkeypatch.setattr(control.subprocess, "run", failing)
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.host._gateway_service_enabled()
    assert excinfo.value.code == "gateway_mcp_generation_invalid"


def test_stopped_incumbent_mcp_is_not_a_publication_posture(gateway, monkeypatch):
    """The old stopped-MCP posture is gone: a stopped incumbent refuses."""

    s = gateway
    from control_plane import executive_installed_peer as installed

    observation = types.SimpleNamespace(release=SHA, digest=digest(s.plist_bytes))
    monkeypatch.setattr(
        installed, "_verify_role_plist", lambda topology, budget: observation
    )
    monkeypatch.setattr(s.host, "_gateway_service_enabled", lambda: True)
    monkeypatch.setattr(s.host, "_launchd_state", lambda target: "absent")
    # The real generation observation replaces the TESTDATA stub for this run.
    monkeypatch.delattr(s.host, "require_gateway_generation_current")
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.host.checked_gateway_configs(
            SHA,
            allowed_plist_sha256s=frozenset({digest(s.plist_bytes)}),
            allowed_release_shas=frozenset({SHA}),
        )
    assert excinfo.value.code == "gateway_mcp_generation_invalid"
    assert not control.AUTONOMY_TRANSACTION.exists()


# ---------------------------------------------------------------------------
# Studio seat qualification negatives.
# ---------------------------------------------------------------------------


def test_wrong_studio_identity_refuses_before_writes(gateway, monkeypatch):
    s = gateway
    real_getpwuid = control.pwd.getpwuid

    class _Foreign:
        pw_uid = 502
        pw_gid = STUDIO_GID
        pw_name = control.OS_GATEWAY_STUDIO_ACCOUNT

        def __init__(self):
            self.pw_dir = str(s.home)

    monkeypatch.setattr(
        control.pwd,
        "getpwuid",
        lambda uid: _Foreign() if uid == STUDIO_UID else real_getpwuid(uid),
    )
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_studio_invalid"
    assert not control.AUTONOMY_TRANSACTION.exists()
    assert not control.OS_GATEWAY_COMMISSION_GRANT.exists()


def test_foreign_account_name_refuses(gateway, monkeypatch):
    s = gateway
    real_getpwuid = control.pwd.getpwuid

    class _Renamed:
        pw_uid = STUDIO_UID
        pw_gid = STUDIO_GID
        pw_name = "some-other-account"

        def __init__(self):
            self.pw_dir = str(s.home)

    monkeypatch.setattr(
        control.pwd,
        "getpwuid",
        lambda uid: _Renamed() if uid == STUDIO_UID else real_getpwuid(uid),
    )
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_studio_invalid"


def _break_studio(s, mutate):
    manifest_path = s.studio["base"] / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    mutate(manifest)
    manifest_path.chmod(0o644)
    manifest_path.write_bytes(control._encoded_json(manifest))
    manifest_path.chmod(0o600)


def test_tampered_studio_definition_refuses(gateway):
    s = gateway
    _break_studio(s, lambda manifest: manifest.update(port=45099))
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_studio_invalid"


def test_studio_source_release_drift_refuses(gateway):
    s = gateway
    _break_studio(
        s,
        lambda manifest: manifest.update(
            source=os.fspath(s.release / "integrations/studio_direct_mcp/other")
        ),
    )
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_studio_invalid"


def test_studio_dependency_seal_is_required(gateway):
    s = gateway
    _break_studio(s, lambda manifest: manifest.update(dependencyTreeHash=None))
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_studio_invalid"
    _break_studio(s, lambda manifest: manifest.update(dependencyTreeHash="zz"))
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_studio_invalid"


def test_studio_dependency_seal_drift_refuses(gateway):
    s = gateway
    dependency = s.studio["base"] / "node_modules" / "tiny" / "index.js"
    dependency.chmod(0o644)
    dependency.write_bytes(b"module.exports = 2;\n")
    dependency.chmod(0o600)
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_studio_invalid"


@pytest.mark.parametrize("field", ["configHash", "plistHash"])
def test_studio_observed_bytes_match_the_actual_manifest_seal(gateway, field):
    _break_studio(gateway, lambda manifest: manifest.update({field: "f" * 64}))
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        gateway.publish()
    assert excinfo.value.code == "gateway_studio_invalid"
    assert not control.AUTONOMY_TRANSACTION.exists()


def test_studio_observation_does_not_use_legacy_pathname_payload_readers(
    gateway, monkeypatch
):
    """The real owner consumes the closed reader, not checked-then-open paths."""
    from integrations.studio_direct_mcp import private_service

    def forbidden(*args, **kwargs):
        raise AssertionError("legacy Studio pathname payload reader invoked")

    for name in ("_installed_file_hashes", "_stable_regular_file_hash",
                 "_dependency_tree_hash"):
        monkeypatch.setattr(private_service, name, forbidden)
    observed = gateway.host.observe_studio(SHA)
    assert observed.node_sha256 == digest(gateway.studio["node"].read_bytes())
    assert observed.definition_sha256


def test_root_owned_payload_target_refuses_before_any_protected_io(gateway, monkeypatch):
    """A manifest cannot aim Root at a nonpublic Root-owned tool payload."""
    node = gateway.studio["node"]
    inode = _TRUE_LSTAT(node).st_ino
    bound_stat, bound_fstat, real_read = os.stat, os.fstat, os.read
    reads = []

    def root_node(info):
        if info.st_ino != inode:
            return info
        fields = list(info)
        fields[4:6] = [0, 0]
        return os.stat_result(fields, {
            "st_atime_ns": info.st_atime_ns,
            "st_mtime_ns": info.st_mtime_ns,
            "st_ctime_ns": info.st_ctime_ns,
        })

    # TESTDATA identity mapping is consistent on the parent-relative stat AND
    # the actual opened FD. The real leaf mode is 0500, not public-readable.
    monkeypatch.setattr(os, "stat", lambda *a, **kw: root_node(bound_stat(*a, **kw)))
    monkeypatch.setattr(os, "fstat", lambda fd: root_node(bound_fstat(fd)))
    def guarded_read(fd, size):
        if _TRUE_FSTAT(fd).st_ino == inode:
            reads.append(fd)
            raise AssertionError("protected payload read must never start")
        return real_read(fd, size)
    monkeypatch.setattr(os, "read", guarded_read)
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        gateway.host.observe_studio(SHA)
    assert excinfo.value.code == "gateway_studio_invalid"
    assert reads == []
    assert not control.AUTONOMY_TRANSACTION.exists()


def test_foreign_tool_ancestor_refuses(gateway):
    s = gateway
    tools = s.home / "tools"
    tools.chmod(0o777)
    try:
        with pytest.raises(control.GatewayPublicationError) as excinfo:
            s.publish()
        assert excinfo.value.code == "gateway_studio_invalid"
    finally:
        tools.chmod(0o750)


def test_unreadable_backend_refuses(gateway):
    s = gateway
    backend = s.studio["backend"]
    backend.chmod(0o300)
    try:
        with pytest.raises(control.GatewayPublicationError) as excinfo:
            s.publish()
        assert excinfo.value.code == "gateway_studio_invalid"
    finally:
        backend.chmod(0o400)


def test_running_studio_or_occupied_port_refuse(gateway, monkeypatch):
    s = gateway
    gui_target = f"gui/{STUDIO_UID}/{control.OS_GATEWAY_STUDIO_LABEL}"

    def studio_running(target):
        return "running" if target == gui_target else "absent"

    monkeypatch.setattr(s.host, "_launchd_state", studio_running)
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_studio_running"
    monkeypatch.setattr(s.host, "_launchd_state", lambda target: "absent")
    monkeypatch.setattr(s.host, "_studio_port_absent", lambda: False)
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_port_occupied"
    assert not control.AUTONOMY_TRANSACTION.exists()
    assert not control.OS_GATEWAY_COMMISSION_GRANT.exists()


# ---------------------------------------------------------------------------
# Launch receipt, workspace identity, namespace scope, and template negatives.
# ---------------------------------------------------------------------------


def test_launch_receipt_drift_refuses(gateway):
    s = gateway
    receipt_path = s.release / "app/mastermind_os/web-build-receipt.json"
    receipt = json.loads(receipt_path.read_bytes())
    receipt["source_tree"] = "d" * 40
    receipt_path.chmod(0o644)
    receipt_path.write_bytes(control._encoded_json(receipt))
    receipt_path.chmod(0o444)
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_launch_receipt_invalid"


def test_workspace_binding_and_allowlist_drift_refuse(gateway):
    s = gateway
    original = s.mcp_bytes
    document = json.loads(original.decode("utf-8"))

    def write_variant(value):
        raw = control._encoded_json(value)
        path = control.OS_GATEWAY_MCP_CONFIG
        path.chmod(0o644)
        path.write_bytes(raw)
        path.chmod(0o440)
        return raw

    broken = json.loads(json.dumps(document))
    broken["workspace"]["bindings"]["profiles"]["web"] = {"enabled": False, "binding": None}
    first = write_variant(broken)
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish(prior_mcp_config_sha256=digest(first))
    assert excinfo.value.code == "gateway_workspace_binding_invalid"

    from integrations.business_mcp_auth.claims import _client_ref

    drifted = json.loads(json.dumps(document))
    drifted["workspace"]["bindings"]["profiles"]["web"]["binding"]["client_ref"] = (
        _client_ref({"client_id": "OtherClient99"}, ISSUER)
    )
    second = write_variant(drifted)
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish(prior_mcp_config_sha256=digest(second))
    assert excinfo.value.code == "gateway_workspace_binding_invalid"

    unlisted = json.loads(json.dumps(document))
    unlisted["policies"]["submit"]["allowed_subject_digests"] = ["e" * 64]
    third = write_variant(unlisted)
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish(prior_mcp_config_sha256=digest(third))
    assert excinfo.value.code == "gateway_submit_allowlist_invalid"

    control.OS_GATEWAY_MCP_CONFIG.chmod(0o644)
    control.OS_GATEWAY_MCP_CONFIG.write_bytes(original)
    control.OS_GATEWAY_MCP_CONFIG.chmod(0o440)


def test_namespace_helper_is_the_only_scope_origin_and_refuses_without_it(
    gateway, monkeypatch
):
    s = gateway
    identity = s.host.qualify_workspace_identity(s.mcp_bytes, web_client_id=CLIENT_ID)
    scope = s.host._derived_namespace_scope(identity)
    assert type(scope) is str

    # A genuinely unavailable helper refuses; do not silently rederive locally.
    module_name = "integrations.mastermind_executive_app.principal_namespace"
    real_helper = sys.modules[module_name]
    monkeypatch.setitem(sys.modules, module_name, None)
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.host._derived_namespace_scope(identity)
    assert excinfo.value.code == "gateway_namespace_scope_invalid"

    # Unqualified DATA inputs refuse before any derivation.
    monkeypatch.setitem(sys.modules, module_name, real_helper)
    _install_namespace_helper(monkeypatch)
    for broken in (
        {**identity, "issuer_digest": "not-a-digest"},
        {**identity, "subject_digest": 7},
        {**identity, "client_ref": ""},
        {**identity, "resource": None},
    ):
        with pytest.raises(control.GatewayPublicationError) as excinfo:
            s.host._derived_namespace_scope(broken)
        assert excinfo.value.code == "gateway_namespace_scope_invalid"


def test_template_requires_the_single_research_only_profile(gateway):
    s = gateway
    host = s.host
    manifest = json.loads(_launch_manifest_bytes().decode("utf-8"))
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        host._gateway_template(
            json.dumps({**manifest, "profiles": [
                {"ref": "research_only", "label": "Research only"},
                {"ref": "bounded_code_change", "label": "Code"},
            ]}, sort_keys=True, separators=(",", ":")) + "\n"
        )
    assert excinfo.value.code == "gateway_template_refused"
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        host._gateway_template(
            json.dumps({**manifest, "profiles": [
                {"ref": "bounded_code_change", "label": "Code"},
            ], "allowedWritePaths": ["src/x.py"], "validation": {"git_diff_check": True}},
            sort_keys=True, separators=(",", ":")) + "\n"
        )
    assert excinfo.value.code == "gateway_template_refused"
    template = host._gateway_template(_launch_manifest_bytes().decode("utf-8"))
    assert template == {
        "workstream": "WS:OSGateway",
        "department": "os-gateway",
        "execution_profile": "research_only",
        "priority": 5,
        "attempt_limit": 3,
    }


# ---------------------------------------------------------------------------
# Real compiler join: absence and contract drift refuse.
# ---------------------------------------------------------------------------


def test_compiler_absence_or_contract_drift_refuses(gateway, monkeypatch):
    s = gateway
    monkeypatch.setitem(sys.modules, "ops.executive_os.os_gateway_publication", None)
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_compiler_unavailable"
    assert not control.AUTONOMY_TRANSACTION.exists()
    assert not control.OS_GATEWAY_COMMISSION_GRANT.exists()


def _drift_module(monkeypatch, candidate, **extra):
    from control_plane import executive_installed_peer as installed

    module = types.SimpleNamespace(
        SCHEMA="mastermind.os_gateway_publication.v1",
        MCP_CONFIG_PATH=os.fspath(control.OS_GATEWAY_MCP_CONFIG),
        MCP_PLIST_PATH=os.fspath(control.OS_GATEWAY_MCP_PLIST),
        COMMISSION_CONFIG_PATH=os.fspath(control.OS_GATEWAY_COMMISSION_GRANT),
        compile_gateway_candidates=lambda *args, **kwargs: candidate,
        **extra,
    )
    monkeypatch.setitem(
        sys.modules, "ops.executive_os.os_gateway_publication", module
    )
    # ``from package import module`` resolves through the package attribute,
    # so the TESTDATA collaborator replaces that binding as well.
    monkeypatch.setattr(
        sys.modules["ops.executive_os"], "os_gateway_publication", module
    )


def _real_shaped_candidate(s):
    """TESTDATA candidate with the real frozen contract, one drift at a time."""

    return _Candidate(
        schema="mastermind.os_gateway_publication.v1",
        operation=control.OS_GATEWAY_PUBLICATION,
        expected_release_sha=SHA,
        expected_bundle_digest=s.bundle,
        before_mcp_bytes=s.mcp_bytes,
        before_plist_bytes=s.plist_bytes,
        before_mcp_sha256=digest(s.mcp_bytes),
        before_plist_sha256=digest(s.plist_bytes),
        artifacts=(
            _Artifact(
                path=os.fspath(control.OS_GATEWAY_MCP_CONFIG),
                kind="executive-mcp-config",
                content=b"{}\n",
                sha256=digest(b"{}\n"),
                byte_count=3,
            ),
            _Artifact(
                path=os.fspath(control.OS_GATEWAY_MCP_PLIST),
                kind="executive-mcp-plist",
                content=b"<plist/>\n",
                sha256=digest(b"<plist/>\n"),
                byte_count=9,
            ),
            _Artifact(
                path=os.fspath(control.OS_GATEWAY_COMMISSION_GRANT),
                kind="os-commission-publication",
                content=b"{}\n",
                sha256=digest(b"{}\n"),
                byte_count=3,
            ),
        ),
    )


def test_compiler_contract_drift_refuses(gateway, monkeypatch):
    s = gateway
    base = _real_shaped_candidate(s)

    # Exactly the three fixed targets, joined to the compiler's own constants.
    _drift_module(
        monkeypatch,
        dataclasses.replace(
            base,
            artifacts=base.artifacts[:2],
        ),
    )
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_compiler_contract_invalid"

    # A drifted artifact digest is never adopted.
    _drift_module(
        monkeypatch,
        dataclasses.replace(
            base,
            artifacts=(
                dataclasses.replace(base.artifacts[0], sha256="0" * 64),
                *base.artifacts[1:],
            ),
        ),
    )
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_compiler_contract_invalid"

    # A foreign target path or fabricated absence receipt refuses.
    _drift_module(
        monkeypatch,
        dataclasses.replace(
            base,
            artifacts=(
                dataclasses.replace(base.artifacts[2], path="/tmp/foreign.json"),
                *base.artifacts[:2],
            ),
        ),
    )
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_compiler_contract_invalid"

    _drift_module(monkeypatch, dataclasses.replace(base, publication_before_sha256="a" * 64))
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_compiler_contract_invalid"

    # A drifted operation identity is not this publication.
    _drift_module(monkeypatch, dataclasses.replace(base, operation="OTHER_OPERATION"))
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_compiler_contract_invalid"

    # Missing contract fields are a contract refusal, not an adoption.
    _drift_module(monkeypatch, types.SimpleNamespace(operation="x"))
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_compiler_contract_invalid"
    assert not control.AUTONOMY_TRANSACTION.exists()
    assert not control.OS_GATEWAY_COMMISSION_GRANT.exists()


# ---------------------------------------------------------------------------
# Canonical audit-directory prerequisite.
# ---------------------------------------------------------------------------


def test_poisoned_occupied_audit_leaf_refuses_closed(gateway):
    s = gateway
    # A wrong-mode contained entry keeps the leaf closed.
    leaf = _stage_audit_leaf(
        s.tmp_path / SERVICE_ROOT,
        entries=[("auth-audit.jsonl", b"{}\n", 0o644)],
    )
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_audit_directory_invalid"
    assert sorted(os.listdir(leaf)) == ["auth-audit.jsonl"]

    # A symlinked entry is poison.
    (leaf / "auth-audit.jsonl").chmod(0o600)
    (leaf / "link.jsonl").symlink_to("auth-audit.jsonl")
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_audit_directory_invalid"
    (leaf / "link.jsonl").unlink()

    # A subdirectory is unsafe topology.
    (leaf / "subdir").mkdir()
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_audit_directory_invalid"


def test_foreign_audit_ancestor_refuses_without_fabrication(gateway):
    s = gateway
    audit_root = s.tmp_path / SERVICE_ROOT / "audit"
    audit_root.chmod(0o777)
    try:
        with pytest.raises(control.GatewayPublicationError) as excinfo:
            s.publish()
        assert excinfo.value.code == "gateway_audit_directory_invalid"
    finally:
        audit_root.chmod(0o755)
    assert not s.audit_leaf.exists()
    assert not control.AUTONOMY_TRANSACTION.exists()


def test_audit_state_ambiguity_stays_unknown(gateway, monkeypatch):
    s = gateway
    bound = {
        control._GATEWAY_AUDIT_STATE_FIELD: "present",
        control._GATEWAY_AUDIT_UID_FIELD: STUDIO_UID,
        control._GATEWAY_AUDIT_GID_FIELD: STUDIO_GID,
        control._GATEWAY_AUDIT_MODE_FIELD: control._GATEWAY_AUDIT_LEAF_MODE,
        control._GATEWAY_AUDIT_BEFORE_FIELD: [1, 1],
    }
    monkeypatch.setattr(
        s.host, "observe_gateway_audit_directory", lambda **kwargs: dict(bound)
    )
    with pytest.raises(control.TransactionEffectUnknown):
        s.publish()
    # Nothing was adopted or fabricated; the retained intent stays original.
    assert not s.audit_leaf.exists()
    assert control.AUTONOMY_TRANSACTION.exists()


def test_full_inflight_marker_is_durable_before_the_first_write(gateway, monkeypatch):
    s = gateway

    def refuse(*args, **kwargs):
        raise control.TransactionEffectUnknown()

    monkeypatch.setattr(s.host, "_recheck_gateway_preimages", refuse)
    with pytest.raises(control.TransactionEffectUnknown):
        s.publish()
    assert control.AUTONOMY_TRANSACTION.exists()
    manifest = json.loads(
        (control.AUTONOMY_TRANSACTION / "transaction.json").read_bytes()
    )
    assert manifest["operation"] == control.OS_GATEWAY_PUBLICATION
    assert manifest["phase"] == "LOCKED"
    assert set(manifest) == {
        "schema_version",
        "operation",
        "phase",
        "transaction_id",
        "expected_sha",
        "prior_control_sha256",
        "prior_worker_sha256",
        "target_control_sha256",
        "target_worker_sha256",
        *sorted(control._GATEWAY_MANIFEST_FIELDS),
    }
    assert manifest["gateway_release_bundle_digest"] == s.bundle
    assert manifest["gateway_prior_grant_present"] is False
    # The audit prerequisite is bound in the SAME retained intent, before any
    # directory create or target write.
    assert manifest[control._GATEWAY_AUDIT_STATE_FIELD] == "absent"
    assert manifest[control._GATEWAY_AUDIT_UID_FIELD] == STUDIO_UID
    assert manifest[control._GATEWAY_AUDIT_GID_FIELD] == STUDIO_GID
    assert manifest[control._GATEWAY_AUDIT_MODE_FIELD] == 0o700
    assert sorted(os.listdir(control.AUTONOMY_TRANSACTION)) == [
        "prior-control.json",
        "prior-os-commission-grant.json",
        "prior-worker.json",
        "transaction.json",
    ]
    assert not control.OS_GATEWAY_COMMISSION_GRANT.exists()
    assert not control.OS_GATEWAY_RECEIPT.exists()
    assert control.OS_GATEWAY_MCP_CONFIG.read_bytes() == s.mcp_bytes
    assert control.OS_GATEWAY_MCP_PLIST.read_bytes() == s.plist_bytes


def test_completion_requires_the_bound_audit_leaf(gateway, monkeypatch):
    s = gateway

    real_verify = s.host._verify_gateway_audit_directory

    def refuse(manifest):
        if control.OS_GATEWAY_RECEIPT.exists():
            raise control.TransactionEffectUnknown()
        real_verify(manifest)

    monkeypatch.setattr(s.host, "_verify_gateway_audit_directory", refuse)
    with pytest.raises(control.TransactionEffectUnknown):
        s.publish()
    assert control.OS_GATEWAY_RECEIPT.exists()
    assert control.AUTONOMY_TRANSACTION.exists()


def test_interruption_at_the_grant_write_marks_the_audit_phase(gateway, monkeypatch):
    s = gateway

    def refuse_grant(*args, **kwargs):
        raise RuntimeError("interrupted")

    monkeypatch.setattr(s.host, "_publish_gateway_grant", refuse_grant)
    with pytest.raises(control.TransactionEffectUnknown):
        s.publish(prior_grant_absent=True)
    manifest = json.loads(
        (control.AUTONOMY_TRANSACTION / "transaction.json").read_bytes()
    )
    assert manifest["phase"] == "AUDIT_DIRECTORY_READY"
    assert not control.OS_GATEWAY_COMMISSION_GRANT.exists()
    assert control.OS_GATEWAY_MCP_CONFIG.read_bytes() == s.mcp_bytes
    assert not control.OS_GATEWAY_RECEIPT.exists()
    # The created canonical leaf survives, exactly as produced.
    assert s.audit_leaf.is_dir()
    assert stat.S_IMODE(s.audit_leaf.stat().st_mode) == 0o700


def _interrupted_host(gateway, monkeypatch):
    """A second host whose config write interrupts after the grant phase."""

    second = control.ProductionGatewayPublicationHost()
    _install_host_boundaries(monkeypatch, second)

    def refuse_config(transaction, path, **kwargs):
        if path == control.OS_GATEWAY_MCP_CONFIG:
            raise RuntimeError("interrupted")
        raise AssertionError("publish order changed")

    monkeypatch.setattr(second, "_replace_gateway_target", refuse_config)
    return Fixture(
        second,
        gateway.config_root,
        gateway.tmp_path,
        gateway.home,
        gateway.studio,
        gateway.bundle,
        gateway.mcp_bytes,
        gateway.plist_bytes,
    )


def test_interruption_at_the_config_write_marks_the_grant_phase(gateway, monkeypatch):
    s = gateway
    replacement = _interrupted_host(gateway, monkeypatch)
    try:
        with pytest.raises(control.TransactionEffectUnknown):
            replacement.publish(prior_grant_absent=True)
        manifest = json.loads(
            (control.AUTONOMY_TRANSACTION / "transaction.json").read_bytes()
        )
        assert manifest["phase"] == "GRANT_PUBLISHED"
        grant = json.loads(control.OS_GATEWAY_COMMISSION_GRANT.read_bytes())
        assert grant["schema"] == control.OS_GATEWAY_GRANT_SCHEMA
        assert control.OS_GATEWAY_MCP_CONFIG.read_bytes() == s.mcp_bytes
        assert not control.OS_GATEWAY_RECEIPT.exists()
    finally:
        replacement.teardown()


@pytest.mark.parametrize("phase_acknowledged", [False, True])
def test_interrupted_publication_reconciles_only_exact_postimages(
    gateway, monkeypatch, phase_acknowledged
):
    s = gateway

    def refuse(transaction):
        raise RuntimeError("interrupted after retained terminal receipt")

    if phase_acknowledged:
        monkeypatch.setattr(s.host, "complete_transaction", refuse)
    else:
        real_persist = s.host._persist_phase
        def refuse_phase(transaction, phase, **kwargs):
            if phase == "GATEWAY_RECEIPT_REPLACED":
                raise RuntimeError("terminal phase acknowledgement lost")
            return real_persist(transaction, phase, **kwargs)
        monkeypatch.setattr(s.host, "_persist_phase", refuse_phase)
    with pytest.raises(control.TransactionEffectUnknown):
        s.publish()
    transaction_id = json.loads(
        (control.AUTONOMY_TRANSACTION / "transaction.json").read_bytes()
    )["transaction_id"]
    original_receipt = control.OS_GATEWAY_RECEIPT.read_bytes()
    manifest = json.loads(
        (control.AUTONOMY_TRANSACTION / "transaction.json").read_bytes()
    )
    assert manifest["phase"] == (
        "GATEWAY_RECEIPT_REPLACED" if phase_acknowledged
        else "GATEWAY_PLIST_REPLACED"
    )
    target_config = control.OS_GATEWAY_MCP_CONFIG.read_bytes()
    s.teardown()
    recovery = s.fresh_host(monkeypatch)
    # Same transaction id: the retained postimages prove out and complete.
    assert s.reconcile(host=recovery, transaction_id=transaction_id) == transaction_id
    assert not control.AUTONOMY_TRANSACTION.exists()
    receipt = json.loads(control.OS_GATEWAY_RECEIPT.read_bytes())
    assert receipt["transaction_id"] == transaction_id
    assert control.OS_GATEWAY_RECEIPT.read_bytes() == original_receipt
    assert control.OS_GATEWAY_MCP_CONFIG.read_bytes() == target_config

    # The completed terminal receipt refuses any further publication, and a
    # reconcile without a retained marker stays UNKNOWN rather than retrying.
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_receipt_conflict"
    assert not control.AUTONOMY_TRANSACTION.exists()
    with pytest.raises(control.TransactionEffectUnknown):
        s.reconcile(transaction_id=transaction_id)
    s.teardown()


def test_reconcile_never_republishes_a_missing_or_mixed_target(gateway, monkeypatch):
    s = gateway

    def refuse(transaction, receipt):
        raise RuntimeError("lost before terminal receipt")

    monkeypatch.setattr(s.host, "write_gateway_receipt", refuse)
    with pytest.raises(control.TransactionEffectUnknown):
        s.publish()
    transaction_id = json.loads(
        (control.AUTONOMY_TRANSACTION / "transaction.json").read_bytes()
    )["transaction_id"]
    prior_config = s.mcp_bytes
    control.OS_GATEWAY_MCP_CONFIG.unlink()
    with pytest.raises(control.TransactionEffectUnknown):
        s.reconcile(transaction_id=transaction_id)
    assert not control.OS_GATEWAY_MCP_CONFIG.exists()
    assert not control.OS_GATEWAY_RECEIPT.exists()
    assert control.AUTONOMY_TRANSACTION.exists()
    # Restore the exact postimage bytes and confirm reconcile stays read-only
    # about the preimage: the marker still binds the original preimage hash.
    _write_sealed(control.OS_GATEWAY_MCP_CONFIG, prior_config, 0o444)
    with pytest.raises(control.TransactionEffectUnknown):
        s.reconcile(transaction_id=transaction_id)
    assert control.OS_GATEWAY_MCP_CONFIG.read_bytes() == prior_config
    s.teardown()


def test_reconcile_never_regenerates_a_lost_audit_leaf(gateway, monkeypatch):
    """Reconciliation is postimage-only: a lost audit leaf stays UNKNOWN."""

    s = gateway

    def refuse(transaction, receipt):
        raise RuntimeError("lost before terminal receipt")

    monkeypatch.setattr(s.host, "write_gateway_receipt", refuse)
    with pytest.raises(control.TransactionEffectUnknown):
        s.publish()
    transaction_id = json.loads(
        (control.AUTONOMY_TRANSACTION / "transaction.json").read_bytes()
    )["transaction_id"]
    leaf = s.audit_leaf
    assert leaf.is_dir()
    leaf.rmdir()
    s.teardown()
    recovery = s.fresh_host(monkeypatch)
    try:
        with pytest.raises(control.TransactionEffectUnknown):
            s.reconcile(host=recovery, transaction_id=transaction_id)
        assert not leaf.exists()
        assert control.AUTONOMY_TRANSACTION.exists()
    finally:
        if recovery._transaction_owner_fd is not None:
            recovery._release_transaction_owner()


def test_conflicting_cas_is_never_adopted_or_clobbered(gateway, monkeypatch):
    s = gateway

    def refuse(transaction, receipt):
        raise RuntimeError("lost before terminal receipt")

    monkeypatch.setattr(s.host, "write_gateway_receipt", refuse)
    with pytest.raises(control.TransactionEffectUnknown):
        s.publish()
    transaction_id = json.loads(
        (control.AUTONOMY_TRANSACTION / "transaction.json").read_bytes()
    )["transaction_id"]
    foreign = control._encoded_json({"schema": "mastermind.executive_mcp_install.v1"})
    control.OS_GATEWAY_MCP_CONFIG.chmod(0o644)
    control.OS_GATEWAY_MCP_CONFIG.write_bytes(foreign)
    control.OS_GATEWAY_MCP_CONFIG.chmod(0o444)
    with pytest.raises(control.TransactionEffectUnknown):
        s.reconcile(transaction_id=transaction_id)
    assert control.OS_GATEWAY_MCP_CONFIG.read_bytes() == foreign
    assert control.AUTONOMY_TRANSACTION.exists()
    with pytest.raises((control.GatewayPublicationError, control.CeoSubmitAdmissionError)):
        s.publish()
    assert control.OS_GATEWAY_MCP_CONFIG.read_bytes() == foreign
    s.teardown()


def test_second_publisher_with_stale_preimages_never_adopts_or_clobbers(
    gateway, monkeypatch
):
    """A concurrent second publisher refuses on the retained CAS, not belief."""

    s = gateway
    stale_request = s.request()
    stale = {
        "mcp": digest(s.mcp_bytes),
        "plist": digest(s.plist_bytes),
    }
    # First publisher completes entirely.
    s.publish()
    published_config = control.OS_GATEWAY_MCP_CONFIG.read_bytes()
    # A second publisher that qualified the OLD preimages before the first
    # finished now races past admission and must never adopt or rewrite.
    second = s.fresh_host(monkeypatch)
    try:
        with pytest.raises(control.GatewayPublicationError) as excinfo:
            control.execute_gateway_publication(
                second,
                control.GatewayPublicationRequest(
                    expected_sha=stale_request.expected_sha,
                    bundle_digest=stale_request.bundle_digest,
                    prior_mcp_config_sha256=stale["mcp"],
                    prior_mcp_plist_sha256=stale["plist"],
                    prior_grant_absent=True,
                ),
                now=NOW,
            )
        assert excinfo.value.code == "gateway_receipt_conflict"
        assert control.OS_GATEWAY_MCP_CONFIG.read_bytes() == published_config
    finally:
        if second._transaction_owner_fd is not None:
            second._release_transaction_owner()


@pytest.mark.parametrize("interruption", ["before_write", "before_phase_ack", "after_phase_ack"])
def test_missing_terminal_receipt_stays_unknown_without_regeneration(
    gateway, monkeypatch, interruption
):
    s = gateway

    real_write = control.ProductionGatewayPublicationHost.write_gateway_receipt

    def lose_after_write(transaction, receipt):
        if interruption == "before_write":
            raise RuntimeError("interrupted before terminal write")
        real_write(s.host, transaction, receipt)
        control.OS_GATEWAY_RECEIPT.chmod(0o644)
        control.OS_GATEWAY_RECEIPT.unlink()
        if interruption == "before_phase_ack":
            raise RuntimeError("lost terminal write acknowledgement")

    monkeypatch.setattr(s.host, "write_gateway_receipt", lose_after_write)
    with pytest.raises(control.TransactionEffectUnknown):
        s.publish()
    marker_path = control.AUTONOMY_TRANSACTION / "transaction.json"
    original_marker = marker_path.read_bytes()
    manifest = json.loads(original_marker)
    transaction_id = manifest["transaction_id"]
    assert manifest["phase"] == (
        "GATEWAY_RECEIPT_REPLACED" if interruption == "after_phase_ack"
        else "GATEWAY_PLIST_REPLACED"
    )
    target_bytes = {
        path: path.read_bytes() for path in (
            control.OS_GATEWAY_MCP_CONFIG, control.OS_GATEWAY_MCP_PLIST,
            control.OS_GATEWAY_COMMISSION_GRANT,
        )
    }
    audit_identity = s.audit_leaf.stat()
    assert not control.OS_GATEWAY_RECEIPT.exists()
    s.teardown()
    recovery = s.fresh_host(monkeypatch)
    try:
        def no_reissue(*args, **kwargs):
            raise AssertionError("reconciliation must not issue terminal proof")
        monkeypatch.setattr(recovery, "write_gateway_receipt", no_reissue)
        with pytest.raises(control.TransactionEffectUnknown):
            s.reconcile(host=recovery, transaction_id=transaction_id)
        assert not control.OS_GATEWAY_RECEIPT.exists()
        assert marker_path.read_bytes() == original_marker
        assert all(path.read_bytes() == raw for path, raw in target_bytes.items())
        assert s.audit_leaf.stat().st_ino == audit_identity.st_ino
    finally:
        if recovery._transaction_owner_fd is not None:
            recovery._release_transaction_owner()


def test_occupied_gateway_marker_excludes_second_publisher_and_old_operations(gateway):
    s = gateway

    def refuse(*args, **kwargs):
        raise control.TransactionEffectUnknown()

    original = s.host._recheck_gateway_preimages
    s.host._recheck_gateway_preimages = refuse
    with pytest.raises(control.TransactionEffectUnknown):
        s.publish()
    s.host._recheck_gateway_preimages = original
    assert control.AUTONOMY_TRANSACTION.exists()
    with pytest.raises(control.CeoSubmitAdmissionError):
        s.publish()
    with pytest.raises(control.CeoSubmitAdmissionError) as excinfo:
        control.ProductionGatewayPublicationHost().require_transaction_absent()
    assert excinfo.value.code == "ceo_submit_transaction_incomplete"
    transaction = control.TransactionContext(
        transaction_id="autonomy-" + "2" * 12,
        expected_sha=SHA,
        prior_configs=control.ConfigEvidence("a" * 64, "b" * 64, {}, {}, b"", b""),
        candidates=control.CandidateConfigs({}, {}, b"", b"", "a" * 64, "b" * 64),
        admission=None,
    )
    legacy = control.ProductionTransactionHost()
    with pytest.raises(control.ArmAdmissionError) as excinfo:
        legacy.begin_transaction(transaction)
    assert excinfo.value.code == "transaction_incomplete"
    s.teardown()


def test_completed_publication_receipt_blocks_republish(gateway):
    s = gateway
    s.publish()
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_receipt_conflict"
    control.OS_GATEWAY_RECEIPT.chmod(0o644)
    control.OS_GATEWAY_RECEIPT.write_bytes(b"not-json\n")
    control.OS_GATEWAY_RECEIPT.chmod(0o444)
    with pytest.raises(control.GatewayPublicationError) as excinfo:
        s.publish()
    assert excinfo.value.code == "gateway_receipt_invalid"


def test_receipt_is_verified_and_fsynced_before_marker_completion(gateway, monkeypatch):
    s = gateway
    observed = {}

    real_complete = control.ProductionGatewayPublicationHost.complete_transaction

    def complete(self, transaction):
        observed["receipt"] = control.OS_GATEWAY_RECEIPT.exists()
        observed["marker"] = control.AUTONOMY_TRANSACTION.exists()
        observed["audit_leaf"] = control._GATEWAY_AUDIT_DIRECTORY.is_dir()
        return real_complete(self, transaction)

    monkeypatch.setattr(
        control.ProductionGatewayPublicationHost, "complete_transaction", complete
    )
    s.publish()
    assert observed == {"receipt": True, "marker": True, "audit_leaf": True}
    assert not control.AUTONOMY_TRANSACTION.exists()


def test_reconcile_rejects_wrong_release_or_bundle(gateway, monkeypatch):
    s = gateway

    def refuse(transaction, receipt):
        raise RuntimeError("lost before terminal receipt")

    monkeypatch.setattr(s.host, "write_gateway_receipt", refuse)
    with pytest.raises(control.TransactionEffectUnknown):
        s.publish()
    transaction_id = json.loads(
        (control.AUTONOMY_TRANSACTION / "transaction.json").read_bytes()
    )["transaction_id"]
    s.teardown()
    recovery = s.fresh_host(monkeypatch)
    try:
        with pytest.raises(control.TransactionEffectUnknown):
            s.reconcile(host=recovery, transaction_id=transaction_id, bundle_digest="0" * 64)
        recovery._release_transaction_owner()

        def exact_install(sha):
            if sha != SHA:
                raise control.ArmAdmissionError("install_gate_failed")
            return sha

        recovery.require_exact_install = exact_install
        with pytest.raises(control.ArmAdmissionError):
            s.reconcile(host=recovery, expected_sha="d" * 40, transaction_id=transaction_id)
    finally:
        if recovery._transaction_owner_fd is not None:
            recovery._release_transaction_owner()


# ---------------------------------------------------------------------------
# Closed manifest dispatch: old schemas unchanged, gateway variant strict.
# ---------------------------------------------------------------------------


def _claim_marker_with(s, document, entries):
    marker = control.AUTONOMY_TRANSACTION
    marker.mkdir(mode=0o700)
    os.chown(marker, 0, 0)
    os.chmod(marker, 0o700)
    _write_sealed(marker / "transaction.json", control._encoded_json(document), 0o400)
    for name in entries:
        _write_sealed(marker / name, b"{}\n", 0o400)
    s.host._claim_transaction_owner()
    return marker


def test_old_manifest_schemas_still_classify_unchanged(gateway):
    s = gateway
    base = {
        "schema_version": control._TRANSACTION_SCHEMA,
        "operation": "PAID_CONTROL_STAGE",
        "phase": "LOCKED",
        "transaction_id": "autonomy-" + "3" * 12,
        "expected_sha": SHA,
        "prior_control_sha256": "a" * 64,
        "prior_worker_sha256": "b" * 64,
        "target_control_sha256": "c" * 64,
        "target_worker_sha256": "d" * 64,
        "paid_definition_sha256": "1" * 64,
        "paid_prior_receipt_present": False,
        "paid_prior_receipt_sha256": digest(b""),
        "paid_target_receipt_sha256": digest(b""),
    }
    _claim_marker_with(
        s, base, ["prior-control.json", "prior-worker.json", "prior-paid-disarmed-receipt.json"]
    )
    manifest = s.host._manifest()
    assert manifest["operation"] == "PAID_CONTROL_STAGE"
    assert not (set(manifest) & control._GATEWAY_MANIFEST_FIELDS)
    s.host._release_transaction_owner()


def test_gateway_manifest_fields_on_a_foreign_operation_refuse(gateway):
    s = gateway
    document = {
        "schema_version": control._TRANSACTION_SCHEMA,
        "operation": "ARM",
        "phase": "LOCKED",
        "transaction_id": "autonomy-" + "4" * 12,
        "expected_sha": SHA,
        "prior_control_sha256": "a" * 64,
        "prior_worker_sha256": "b" * 64,
        "target_control_sha256": "c" * 64,
        "target_worker_sha256": "d" * 64,
    }
    gateway_fields = {
        "gateway_release_bundle_digest": s.bundle,
        "gateway_studio_definition_sha256": "2" * 64,
        "gateway_prior_grant_present": False,
        "gateway_prior_grant_sha256": digest(b""),
        "gateway_target_grant_sha256": "3" * 64,
        "gateway_prior_mcp_config_sha256": "4" * 64,
        "gateway_target_mcp_config_sha256": "5" * 64,
        "gateway_prior_mcp_plist_sha256": "6" * 64,
        "gateway_target_mcp_plist_sha256": "7" * 64,
        control._GATEWAY_AUDIT_STATE_FIELD: "absent",
        control._GATEWAY_AUDIT_UID_FIELD: STUDIO_UID,
        control._GATEWAY_AUDIT_GID_FIELD: STUDIO_GID,
        control._GATEWAY_AUDIT_MODE_FIELD: 0o700,
        control._GATEWAY_AUDIT_BEFORE_FIELD: None,
        control._GATEWAY_AUDIT_AFTER_FIELD: None,
    }
    _claim_marker_with(s, {**document, **gateway_fields}, ["prior-control.json", "prior-worker.json"])
    with pytest.raises(control.TransactionEffectUnknown):
        s.host._manifest()
    s.host._release_transaction_owner()


def test_gateway_marker_with_an_unshaped_audit_binding_refuses(gateway, monkeypatch):
    """A marker whose audit prerequisite is malformed never classifies."""

    s = gateway

    def refuse(*args, **kwargs):
        raise control.TransactionEffectUnknown()

    monkeypatch.setattr(s.host, "_recheck_gateway_preimages", refuse)
    with pytest.raises(control.TransactionEffectUnknown):
        s.publish()
    s.teardown()
    manifest_path = control.AUTONOMY_TRANSACTION / "transaction.json"
    manifest = json.loads(manifest_path.read_bytes())
    for broken in (
        {control._GATEWAY_AUDIT_STATE_FIELD: "qualified-absent"},
        {control._GATEWAY_AUDIT_UID_FIELD: 0},
        {control._GATEWAY_AUDIT_MODE_FIELD: 0o750},
    ):
        drifted = {**manifest, **broken}
        manifest_path.chmod(0o644)
        manifest_path.write_bytes(control._encoded_json(drifted))
        manifest_path.chmod(0o400)
        repaired = control.ProductionGatewayPublicationHost()
        repaired._claim_transaction_owner()
        try:
            with pytest.raises(control.TransactionEffectUnknown):
                repaired._manifest()
        finally:
            repaired._release_transaction_owner()


def test_gateway_marker_without_its_fields_refuses(gateway, monkeypatch):
    s = gateway

    def refuse(*args, **kwargs):
        raise control.TransactionEffectUnknown()

    monkeypatch.setattr(s.host, "_recheck_gateway_preimages", refuse)
    with pytest.raises(control.TransactionEffectUnknown):
        s.publish()
    s.teardown()
    manifest_path = control.AUTONOMY_TRANSACTION / "transaction.json"
    manifest = json.loads(manifest_path.read_bytes())
    stripped = {key: value for key, value in manifest.items() if key not in control._GATEWAY_MANIFEST_FIELDS}
    stripped["operation"] = control.OS_GATEWAY_PUBLICATION
    manifest_path.chmod(0o644)
    manifest_path.write_bytes(control._encoded_json(stripped))
    manifest_path.chmod(0o400)
    repaired = control.ProductionGatewayPublicationHost()
    repaired._claim_transaction_owner()
    with pytest.raises(control.TransactionEffectUnknown):
        repaired._manifest()
    repaired._release_transaction_owner()


# ---------------------------------------------------------------------------
# Closed CLI surface.
# ---------------------------------------------------------------------------


def test_gateway_command_documents_are_typed_and_sanitized(gateway, capsys, monkeypatch):
    s = gateway
    argv = [
        "publish-os-gateway",
        "--expected-sha", SHA,
        "--expected-bundle-digest", s.bundle,
        "--expected-mcp-config-sha256", digest(s.mcp_bytes),
        "--expected-mcp-plist-sha256", digest(s.plist_bytes),
    ]
    # Neither grant expectation: typed refusal, never an effect.
    code = control.main(argv, host=s.host, now=lambda: NOW)
    assert code == 2
    document = json.loads(capsys.readouterr().out)
    assert document["code"] == "gateway_grant_state_conflict"
    assert document["status"] == "OS_GATEWAY_UNVERIFIED"
    assert document["transaction_id"] is None
    assert not control.AUTONOMY_TRANSACTION.exists()

    argv[0] = "publish-os-gateway"
    argv.extend(["--expected-grant-absent"])
    code = control.main(argv, host=s.host, now=lambda: NOW)
    assert code == 0
    document = json.loads(capsys.readouterr().out)
    assert document["code"] == "os_gateway_published"
    assert document["state"] == "PUBLISHED"
    assert document["replayed"] is False


def test_service_control_gateway_arm_is_source_fixed_and_closed(tmp_path):
    script = Path(__file__).resolve().parents[1] / "ops/executive_os/service-control.sh"
    text = script.read_text(encoding="utf-8")
    syntax = subprocess.run(
        ["/bin/bash", "-n", os.fspath(script)], capture_output=True, text=True
    )
    assert syntax.returncode == 0, syntax.stderr

    # A copied controller never publishes: the fixed installed-release source
    # check refuses even with a perfectly formed closed argv.  The id/uname
    # shims satisfy only the root/Darwin gate so the source check is what
    # actually refuses.
    shim_dir = tmp_path / "shims"
    shim_dir.mkdir()
    id_shim = shim_dir / "id"
    id_shim.write_text("#!/bin/bash\nprintf '0\\n'\n")
    id_shim.chmod(0o755)
    uname_shim = shim_dir / "uname"
    uname_shim.write_text("#!/bin/bash\n[ \"$1\" = -s ] && { printf 'Darwin\\n'; exit 0; }\n")
    uname_shim.chmod(0o755)
    shimmed_text = text.replace("/usr/bin/id", str(id_shim)).replace(
        "/usr/bin/uname", str(uname_shim)
    )
    copy_path = tmp_path / "service-control.sh"
    copy_path.write_text(shimmed_text, encoding="utf-8")
    copy_path.chmod(0o755)
    good = [
        "publish-os-gateway",
        "--expected-sha", SHA,
        "--expected-bundle-digest", "1" * 64,
        "--expected-mcp-config-sha256", "2" * 64,
        "--expected-mcp-plist-sha256", "3" * 64,
        "--expected-grant-absent",
    ]
    copied = subprocess.run(
        ["/bin/bash", os.fspath(copy_path), *good], capture_output=True, text=True
    )
    assert copied.returncode == 65, copied.stderr

    # The real installed-path controller refuses malformed argv with usage(64)
    # before any effect, using the same root/Darwin shims the incumbent suite
    # uses for its lifecycle tests.
    installed_text = text.replace("/usr/bin/id", str(id_shim)).replace(
        "/usr/bin/uname", str(uname_shim)
    )
    installed = tmp_path / "installed" / "ops/executive_os"
    installed.mkdir(parents=True)
    controller = installed / "service-control.sh"
    controller.write_text(installed_text, encoding="utf-8")
    controller.chmod(0o755)

    def run(*argv):
        return subprocess.run(
            ["/bin/bash", os.fspath(controller), *argv],
            capture_output=True,
            text=True,
            cwd=os.fspath(installed),
        )

    assert run("publish-os-gateway").returncode == 64
    assert run("publish-os-gateway", "--expected-sha", SHA).returncode == 64
    assert run(
        "publish-os-gateway",
        "--expected-sha", SHA,
        "--expected-bundle-digest", "1" * 64,
        "--expected-mcp-config-sha256", "2" * 64,
        "--expected-mcp-plist-sha256", "3" * 64,
    ).returncode == 64
    assert run(
        "publish-os-gateway",
        "--expected-sha", SHA,
        "--expected-bundle-digest", "1" * 64,
        "--expected-mcp-config-sha256", "2" * 64,
        "--expected-mcp-plist-sha256", "3" * 64,
        "--expected-grant-sha256", "4" * 64,
        "--expected-grant-absent",
    ).returncode == 64
    assert run(
        "publish-os-gateway",
        "--expected-sha", SHA,
        "--foreign", "/tmp/x",
        "--expected-bundle-digest", "1" * 64,
        "--expected-mcp-config-sha256", "2" * 64,
        "--expected-mcp-plist-sha256", "3" * 64,
        "--expected-grant-absent",
    ).returncode == 64
    assert run(
        "reconcile-os-gateway",
        "--expected-sha", SHA,
        "--expected-bundle-digest", "1" * 64,
        "--transaction-id", "autonomy-xyz",
    ).returncode == 64
    assert run(
        "reconcile-os-gateway",
        "--expected-sha", SHA,
        "--expected-bundle-digest", "1" * 64,
        "--expected-grant-absent",
    ).returncode == 64
    # Perfect argv for the copied-path refusal: the source check is what
    # stops a relocated controller, not the argv walk.
    assert run(*good).returncode == 65


# Parent integration: real normal qualifier and exact joined optional fields.
def _normal_gateway_qualifier_fixture(s, monkeypatch):
    from control_plane import executive_installed_peer as installed
    from ops.executive_os import gateway_refresh_preflight as preflight
    from ops.executive_os import os_gateway_publication as compiler

    # TESTDATA custody/release/closure seams only. The actual normal qualifier,
    # plist/profile parser and trusted-byte mode/race checks remain in use.
    topology = dataclasses.replace(installed._role_topology("gateway"),
                                   config_path=str(control.OS_GATEWAY_MCP_CONFIG))
    spec = dataclasses.replace(installed._LAUNCHD_ROLES["gateway"],
                               plist_path=str(control.OS_GATEWAY_MCP_PLIST))
    monkeypatch.setattr(installed, "_role_topology", lambda role: topology)
    monkeypatch.setitem(installed._LAUNCHD_ROLES, "gateway", spec)
    monkeypatch.setitem(installed._EXPECTED_PLIST_PROFILES, "gateway", compiler.GATEWAY_PLIST_PROFILE)
    monkeypatch.setattr(installed, "_observe_ancestors", lambda *args: ())
    monkeypatch.setattr(installed, "_lstat", lambda path: Path(path).lstat())

    def open_fixture(path, **kwargs):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        info = os.fstat(fd)
        return fd, info, info

    monkeypatch.setattr(installed, "_open_trusted", open_fixture)
    monkeypatch.setattr(installed, "_verify_release", lambda *args: types.SimpleNamespace(manifest_digest="a" * 64))
    monkeypatch.setattr(installed, "_recheck_release", lambda *args: None)
    monkeypatch.setattr(installed, "_verify_network_closure", lambda *args: types.SimpleNamespace(aggregate="b" * 64))
    monkeypatch.setattr(installed, "_recheck_network_closure", lambda *args: None)
    monkeypatch.delattr(s.host, "_qualify_published_gateway")
    assert preflight.qualify_gateway_refresh is not None  # actual implementation


def test_actual_normal_qualifier_joins_published_metadata(gateway, monkeypatch):
    s = gateway
    _normal_gateway_qualifier_fixture(s, monkeypatch)
    assert s.publish().state == "PUBLISHED"
    assert stat.S_IMODE(control.OS_GATEWAY_MCP_CONFIG.stat().st_mode) == 0o644
    assert stat.S_IMODE(control.OS_GATEWAY_MCP_PLIST.stat().st_mode) == 0o644


@pytest.mark.parametrize("target", ["OS_GATEWAY_MCP_CONFIG", "OS_GATEWAY_MCP_PLIST"])
def test_actual_normal_qualifier_blocks_content_only_terminal_proof(gateway, monkeypatch, target):
    s = gateway
    _normal_gateway_qualifier_fixture(s, monkeypatch)
    real_replace = s.host._replace_gateway_target

    def drift(*args, **kwargs):
        real_replace(*args, **kwargs)
        if kwargs["phase"] == "GATEWAY_PLIST_REPLACED":
            getattr(control, target).chmod(0o444)

    monkeypatch.setattr(s.host, "_replace_gateway_target", drift)
    with pytest.raises(control.TransactionEffectUnknown):
        s.publish()
    assert control.AUTONOMY_TRANSACTION.exists()
    assert not control.OS_GATEWAY_RECEIPT.exists()


def test_template_preserves_actual_browser_optional_presence(gateway):
    host = gateway.host
    manifest = json.loads(_launch_manifest_bytes())
    del manifest["attemptLimit"]
    plain = host._gateway_template(json.dumps(manifest))
    assert "attempt_limit" not in plain
    assert "validation" not in plain
    assert "allowed_write_paths" not in plain
    exact = host._gateway_template(json.dumps({**manifest, "validation": {}, "allowedWritePaths": []}))
    assert exact == {**plain, "validation": {}, "allowed_write_paths": []}
    with pytest.raises(control.GatewayPublicationError):
        host._gateway_template(json.dumps({**manifest, "allowedWritePaths": ["src/x.py"]}))


def test_web_identity_does_not_choose_first_allowed_subject(gateway):
    s = gateway
    document = json.loads(s.mcp_bytes)
    selected = document["workspace"]["bindings"]["profiles"]["web"]["binding"]["subject_digest"]
    document["policies"]["submit"]["allowed_subject_digests"] = ["0" * 64, selected]
    identity = s.host.qualify_workspace_identity(control._encoded_json(document), web_client_id=CLIENT_ID)
    assert identity["subject_digest"] == selected
    web = document["workspace"]["bindings"]["profiles"]["web"]
    document["workspace"]["bindings"]["profiles"]["mac"] = copy.deepcopy(web)
    with pytest.raises(control.GatewayPublicationError):
        s.host.qualify_workspace_identity(control._encoded_json(document), web_client_id=CLIENT_ID)


def test_audit_replacement_with_same_metadata_is_not_reconciled(gateway, monkeypatch):
    s = gateway
    def lose_receipt(*args):
        raise RuntimeError("disposable lost receipt")
    monkeypatch.setattr(s.host, "write_gateway_receipt", lose_receipt)
    with pytest.raises(control.TransactionEffectUnknown):
        s.publish()
    manifest = json.loads((control.AUTONOMY_TRANSACTION / "transaction.json").read_bytes())
    original = s.audit_leaf.stat().st_ino
    # Keep the original inode alive so the replacement cannot reuse its ID.
    moved = s.audit_leaf.with_name("retained-original")
    s.audit_leaf.rename(moved)
    s.audit_leaf.mkdir(mode=0o700)
    assert s.audit_leaf.stat().st_ino != original
    with pytest.raises(control.TransactionEffectUnknown):
        s.reconcile(transaction_id=manifest["transaction_id"])
    assert not control.OS_GATEWAY_RECEIPT.exists()
    assert control.AUTONOMY_TRANSACTION.exists()


def test_audit_create_before_retained_inode_loss_cannot_regenerate(gateway, monkeypatch):
    s = gateway
    real = s.host._persist_phase
    def lose_inode(transaction, phase, **kwargs):
        if phase == "AUDIT_DIRECTORY_READY":
            raise RuntimeError("disposable inode-retention failure")
        return real(transaction, phase, **kwargs)
    monkeypatch.setattr(s.host, "_persist_phase", lose_inode)
    with pytest.raises(control.TransactionEffectUnknown):
        s.publish()
    manifest = json.loads((control.AUTONOMY_TRANSACTION / "transaction.json").read_bytes())
    assert manifest[control._GATEWAY_AUDIT_AFTER_FIELD] is None
    assert s.audit_leaf.exists()
    before = s.audit_leaf.stat().st_ino
    with pytest.raises(control.TransactionEffectUnknown):
        s.reconcile(transaction_id=manifest["transaction_id"])
    assert s.audit_leaf.stat().st_ino == before
    assert not control.OS_GATEWAY_RECEIPT.exists()


def test_gateway_parser_excludes_grant_flags_in_both_orders_and_reconcile(tmp_path):
    script = Path(__file__).resolve().parents[1] / "ops/executive_os/service-control.sh"
    source = script.read_text()
    for name, body in (("id", "#!/bin/bash\nprintf '0\\n'\n"),
                       ("uname", "#!/bin/bash\nprintf 'Darwin\\n'\n")):
        path = tmp_path / name
        path.write_text(body)
        path.chmod(0o755)
    copied = tmp_path / "service-control.sh"
    copied.write_text(source.replace("/usr/bin/id", str(tmp_path / "id"))
                     .replace("/usr/bin/uname", str(tmp_path / "uname")))
    base = ["publish-os-gateway", "--expected-sha", SHA, "--expected-bundle-digest", "a" * 64,
            "--expected-mcp-config-sha256", "b" * 64, "--expected-mcp-plist-sha256", "c" * 64]
    invalid = [base + ["--expected-grant-absent", "--expected-grant-sha256", "d" * 64],
               base + ["--expected-grant-sha256", "d" * 64, "--expected-grant-absent"],
               ["reconcile-os-gateway", "--expected-sha", SHA, "--expected-bundle-digest", "a" * 64,
                "--transaction-id", "autonomy-" + "e" * 12, "--expected-grant-absent"]]
    for argv in invalid:
        result = subprocess.run(["/bin/bash", str(copied), *argv], capture_output=True, timeout=5)
        assert result.returncode == 64


def test_actual_normal_qualifier_rechecks_after_receipt_before_completion(gateway, monkeypatch):
    s = gateway
    _normal_gateway_qualifier_fixture(s, monkeypatch)
    write = s.host.write_gateway_receipt
    def drift(transaction, receipt):
        write(transaction, receipt)
        control.OS_GATEWAY_MCP_CONFIG.chmod(0o444)
    monkeypatch.setattr(s.host, "write_gateway_receipt", drift)
    with pytest.raises(control.TransactionEffectUnknown):
        s.publish()
    assert control.OS_GATEWAY_RECEIPT.exists()
    assert control.AUTONOMY_TRANSACTION.exists()


def test_origin_joins_actual_release_verifier_before_protected_state(gateway, monkeypatch):
    s = gateway
    host = control.ProductionGatewayPublicationHost()
    monkeypatch.setattr(control.sys, "platform", "darwin")
    monkeypatch.setattr(control.os, "getuid", lambda: 0)
    monkeypatch.setattr(control.os, "geteuid", lambda: 0)
    monkeypatch.setattr(control, "__file__", str(s.release / "ops/executive_os/autonomy_control.py"))
    # TESTDATA chain/file-origin seams isolate the content-verifier join;
    # this positive routing observation is not actual installed authority.
    monkeypatch.setattr(host, "_sealed_origin_chain", lambda release: None)
    monkeypatch.setattr(host, "_sealed_origin_file", lambda path: None)
    seen = []
    def changed_bytes(root, commit, tree):
        seen.append((root, commit, tree))
        raise control.release_manifest.ReleaseManifestError("disposable changed release")
    monkeypatch.setattr(control.release_manifest, "verify", changed_bytes)
    with pytest.raises(control.GatewayPublicationError):
        host.require_gateway_module_origin(SHA)
    assert seen == [(s.release, SHA, TREE_SHA)]
    assert not control.AUTONOMY_TRANSACTION.exists()
    assert not control.OS_GATEWAY_RECEIPT.exists()


def test_fixture_descriptor_mapping_ignores_simulated_platform(gateway, monkeypatch):
    descriptor = os.open(gateway.home, os.O_RDONLY | os.O_DIRECTORY)
    try:
        before = os.fstat(descriptor)
        with monkeypatch.context() as context:
            context.setattr(sys, "platform", "linux" if _TRUE_PLATFORM == "darwin" else "darwin")
            after = os.fstat(descriptor)
            assert (after.st_dev, after.st_ino, after.st_uid, after.st_gid) == (
                before.st_dev, before.st_ino, STUDIO_UID, STUDIO_GID
            )
    finally:
        os.close(descriptor)


def test_studio_os_principal_is_distinct_from_instance_key(gateway, monkeypatch):
    s = gateway
    record = control.pwd.getpwuid(STUDIO_UID)
    assert record.pw_name == "studio-os-owner"
    assert record.pw_name != control.OS_GATEWAY_STUDIO_ACCOUNT
    assert s.host._studio_account_identity() == (s.home, STUDIO_GID)
    assert s.publish().state == "PUBLISHED"
    actual_getpwnam = control.pwd.getpwnam
    for field, foreign in (("pw_uid", 502), ("pw_gid", STUDIO_GID + 1),
                           ("pw_dir", str(s.home / "foreign"))):
        fields = {key: getattr(record, key) for key in ("pw_uid", "pw_gid", "pw_dir", "pw_name")}
        fields[field] = foreign
        monkeypatch.setattr(control.pwd, "getpwnam", lambda name, fields=fields: types.SimpleNamespace(**fields))
        with pytest.raises(control.GatewayPublicationError):
            s.host._studio_account_identity()
    monkeypatch.setattr(control.pwd, "getpwnam", actual_getpwnam)


@pytest.mark.parametrize("name,expected_count", [
    ("ops/executive_os/autonomy_control.py", 4),
    ("ops/executive_os/os_gateway_studio_reader.py", 1),
])
def test_gateway_identity_review_pins_exact_constant_tokens_and_refuses_drift(
    name, expected_count
):
    from tests.executive_fabric_release_identity_review import REVIEWED_FILES
    from tests.executive_identity_review import mask_reviewed_identity_literals
    import ast

    source = (Path(__file__).resolve().parents[1] / name).read_text()
    entry = REVIEWED_FILES[name]
    assert digest(source.encode()) == entry["sha256"]
    constants = {
        (node.lineno, node.col_offset, node.end_col_offset): node
        for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Constant)
    }
    for line, start, end, kind, spelling in entry["sites"]:
        constant = constants[(line, start, end)]
        assert type(constant.value).__name__ == kind
        assert ast.get_source_segment(source, constant) == spelling
    assert len(entry["sites"]) == expected_count
    assert mask_reviewed_identity_literals(name, source) != source
    drifted_sources = [source + "\n# unrelated source drift\n"]
    for line, start, end, _kind, spelling in entry["sites"]:
        lines = source.splitlines(keepends=True)
        replacement = {"501": "502", "80": "81", "0o755": "0o775", "0o644": "0o666"}[spelling]
        lines[line - 1] = lines[line - 1][:start] + replacement + lines[line - 1][end:]
        drifted_sources.append("".join(lines))
    for drifted in drifted_sources:
        assert drifted != source
        assert mask_reviewed_identity_literals(name, drifted) == drifted
    assert mask_reviewed_identity_literals("unreviewed/" + name, source) == source
