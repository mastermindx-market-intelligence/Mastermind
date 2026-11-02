#!/usr/bin/env python3
"""First-install lifecycle helper for per-account private Studio Direct gateways.

Manages only the private launchd label com.mastermind.studio-direct-private.<account>,
its LaunchAgent plist, and ~/.local/share/studio-direct-mcp/private/<account>.
Never touches the public service, the tailnet-only service, or other accounts.

Subprocess calls go through _run so tests can mock them.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import plistlib
import re
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

DIR_MODE = 0o700
FILE_MODE = 0o600

# Funnel/OAuth listener. A private job must never take it.
RESERVED_FUNNEL_PORT = 45017

# Preserve the proven private-seat runtime timeouts: 30 minutes idle and 5 minutes per request.
# These values match the currently deployed Business-seat configuration and avoid restage regressions.
IDLE_TIMEOUT_MS = 1_800_000
REQUEST_TIMEOUT_MS = 300_000

# Shared private-seat gateways can serve many short-lived ChatGPT frontend MCP
# sessions while retaining one bounded backend owner per principal. 64 proved too
# small under multi-session C2 use and caused capacity 503s despite healthy backend
# execution. The gateway validates up to 1024; keep a bounded 256 installed default.
MAX_SESSIONS = 256

# Bounded typed-Git publication policy. These are host-owned values, not CLI
# inputs, so a ChatGPT caller cannot select another repository, remote, lane,
# credential, Git binary, or workspace authority.
TYPED_GIT_WORKSPACE_CLI_REL = Path(".local/bin/mmx-workspace")
TYPED_GIT_SOURCE_REPOSITORY_REL = Path("Documents/GitHub/Mastermind")
TYPED_GIT_BINARY = "/usr/bin/git"
TYPED_GIT_REMOTE_URL = "https://github.com/mastermindx-market-intelligence/Mastermind.git"
# Host-owned identities; these match the existing mmx-workspace repository catalog.
# No caller-supplied path, remote, repository or credential is admitted.
TYPED_GIT_CLOSED_PROFILES = (
    ("mastermind", TYPED_GIT_SOURCE_REPOSITORY_REL, TYPED_GIT_REMOTE_URL),
    ("macro", Path("Documents/Cluade/macro-main"),
     "https://github.com/mastermindx-market-intelligence/macro.git"),
    ("terminal", Path("Documents/Cluade/charting-app"),
     "https://github.com/mastermindx-market-intelligence/mastermind-terminal.git"),
)


# Paper Desktop capability is a gateway-local consumer of the separately reviewed
# guarded adapter in PR #585. The private gateway never accepts these paths or
# hashes from ChatGPT.
# Runtime generations are immutable from the perspective of installed seats. A new
# bridge SHA gets a new directory so one-seat canaries cannot invalidate another
# seat that still pins the previous bridge bytes.
PAPER_RUNTIME_REL = Path(".local/share/mastermind-paper/runtime/v12")
PAPER_RUNTIME_SCHEMA = "mastermind.paper_runtime.v1"
PAPER_BRIDGE_SHA256 = "82bc7f2d75aec423711922198b68f317618a83de177bf4934b73d7b418a6ecfb"
PAPER_COMMAND_TIMEOUT_MS = 70_000
PAPER_APP_REL = Path("Applications/Paper.app")

# Optional read-only fleet-status consumer. It delegates to the installed
# Studio Direct control owner instead of letting a model compose shell probes.
FLEET_STATUS_LAUNCHER_REL = Path(".local/bin/studio-direct")
FLEET_STATUS_TIMEOUT_MS = 15_000

# CLI adapter. gateway.mjs is still staged as the engine import, never argv[1].
PRIVATE_GATEWAY_NAME = "private-tunnel-gateway.mjs"

ACCOUNT_LABEL_MAX = 64
ACCOUNT_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,63})?$")
RESERVED_ACCOUNT_LABELS = frozenset(
    ("public", "shared", "default", "state", "config", "logs", "manifest")
)

# Files staged from source directory. gateway.mjs is the engine library.
STAGE_FILES = (
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
)

# Historical installs are admitted only through exact known file sets. The
# immediately preceding v0.1.6 install has every current file except the new
# read-only fleet-status consumer; earlier generations also predate Paper,
# output paging, and typed Git.
LEGACY_STAGE_FILES_V7 = tuple(name for name in STAGE_FILES if name != "modern-fabric-http.mjs")
LEGACY_STAGE_FILES_V6 = tuple(name for name in LEGACY_STAGE_FILES_V7 if name not in {"commission-prepare.mjs", "commission-service.mjs"})
LEGACY_STAGE_FILES_V5 = tuple(name for name in LEGACY_STAGE_FILES_V6 if name != "workspace-access.mjs")
LEGACY_STAGE_FILES_V4 = tuple(name for name in LEGACY_STAGE_FILES_V5 if name != "fleet-status.mjs")
LEGACY_STAGE_FILES_V3 = tuple(name for name in LEGACY_STAGE_FILES_V4 if name != "paper-design.mjs")
LEGACY_STAGE_FILES_V2 = tuple(name for name in LEGACY_STAGE_FILES_V3 if name != "output-budget.mjs")
LEGACY_STAGE_FILES_V1 = tuple(name for name in LEGACY_STAGE_FILES_V2 if name != "git-publish.mjs")
# The approved 2026-10-14 ChatGPT1 Studio 0.1.10 install had exactly this
# reviewed predecessor generation (see #1333 and the source lineage of #1477).
# Unlike general historical generations, its two fleet/tailnet modules came
# from a branch not in current protected STAGE_FILES. Recognize ONLY this
# exact 12-file set on a V2 manifest. No file, config, binary, plist or
# dependency hash verification is relaxed, and no repository grant is implied.
V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR = frozenset((
    "gateway.mjs", "output-budget.mjs", "git-publish.mjs",
    "workspace-access.mjs", "paper-design.mjs", "fleet-status.mjs",
    "fleet-routing.mjs", "private-tunnel-auth.mjs",
    "private-tunnel-gateway.mjs", "tailnet-gateway.mjs",
    "package.json", "package-lock.json",
))

# Exact 0.1.10 ChatGPT1 fleet bundle signed into the existing V2 manifest.
# This is an owner-bound compatibility update, NOT a generic legacy bundle
# upgrade or permission grant. Unchanged modules retain their original bytes.
FLEET_V10_PRESERVED_GIT_BLOBS = {
    "gateway.mjs": "f87ac012339e82fe46bce5ddc70d1d04183d1b6e",
    "output-budget.mjs": "6d4680a357dc5780e1b09ae32c9ebc908c94353b",
    "paper-design.mjs": "82b35d150433f5128b83a089b581873ad5d73daa",
    "fleet-status.mjs": "ef7ab489ca5134fc6f5d825977ab43a21aab3078",
    "fleet-routing.mjs": "63c47d73ae7b73a61c95cee1803c549ecd6df9c8",
    "private-tunnel-auth.mjs": "cd7ec9fc38ae10cefe8e472246aaf9c6221b0281",
    "private-tunnel-gateway.mjs": "6ea4b75a0ce76995cde4c7f090ad4e28a183f3db",
    "tailnet-gateway.mjs": "d654200a417d5a4dadfcc4e0f6141ef9adda6a04",
    "package.json": "e983917ada1a9da715cedd1acce7559f26a2a932",
    "package-lock.json": "d119580040b0edc59cf0e239922b54a023f899c5",
}
# The already-installed C2 Business fleet v0.1.10 predecessor is a DISTINCT
# 11-file owner, with NO repository-workspace enrollment. Recognizing its
# exact V2 manifest does not grant a new Git repository or change its live
# gateway, tenant or tool catalog. A separate closed migration may later
# upgrade the bounded source generation with explicit original-manifest CAS.
V2_C2_BUSINESS_FLEET_PREDECESSOR = frozenset((
    "gateway.mjs", "git-publish.mjs", "output-budget.mjs",
    "package.json", "package-lock.json", "paper-design.mjs",
    "fleet-status.mjs", "fleet-routing.mjs", "tailnet-gateway.mjs",
    "private-tunnel-auth.mjs", "private-tunnel-gateway.mjs",
))

# Exact historical installed C2 Business 0.1.10 generation. All pinned file
# hashes are provenance checks, NOT a repository access grant. The Gateway
# target source is the independently reviewed fleet v0.1.10 generation; the
# Git publisher/workspace layer is pinned to the reviewed #1535 source.
C2_BUSINESS_V10_ORIGINAL_BLOBS = {
    "fleet-routing.mjs": "7a1d770bf59d9198f1b29f94f56c2e845c4e1b55",
    "fleet-status.mjs": "f04630857f75d712f701360f18e84d42ac8ae8ba",
    "gateway.mjs": "b4fd9aa277403d42e532ed9ecb0a9ff50adb5fe9",
    "git-publish.mjs": "f187b291cbb21782abfdb460a67b557ef1d29638",
    "output-budget.mjs": "6d4680a357dc5780e1b09ae32c9ebc908c94353b",
    "package-lock.json": "d119580040b0edc59cf0e239922b54a023f899c5",
    "package.json": "e983917ada1a9da715cedd1acce7559f26a2a932",
    "paper-design.mjs": "82b35d150433f5128b83a089b581873ad5d73daa",
    "private-tunnel-auth.mjs": "cd7ec9fc38ae10cefe8e472246aaf9c6221b0281",
    "private-tunnel-gateway.mjs": "6ea4b75a0ce76995cde4c7f090ad4e28a183f3db",
    "tailnet-gateway.mjs": "d654200a417d5a4dadfcc4e0f6141ef9adda6a04",
}
C2_PERSONAL_CURRENT_MANIFEST_SHA256 = "c5744dcc7a96d0bc0b019f3c153e8acc8761320ff11541340df753fb493c5460"
# Exact live C2 Personal post-#1604 sealed generation. A dedicated stopped-
# service, manifest-CAS migration changes ONLY the Git command budget.
# Repository enrollment, Git source, fleet, Paper and all module hashes stay fixed.
C2_PERSONAL_TIMEOUT_PREDECESSOR_SHA256 = "4bb0b40cbc7849487c0d886b30261f70fd6e1828d1d217643a56e3fa6aea40fb"
C2_PERSONAL_TIMEOUT_COMMAND_MS = 45000
C2_PERSONAL_TARGET_PATCH_SHA256 = {
    "gateway.mjs": "17157fa5f8739dbe17aae767a335e97dd713a978dde9b192feb1b41a7b036b30",
    "git-publish.mjs": "d8f7f7712129094ce0ffac2eaeb66d15dd3f063a3ade9fa354de7af0d412477a",
    "workspace-access.mjs": "9c4c20dd4edbc426c8561801708ee205e19bb47b48134ec8f5654a10f1cb7cf3",
}
C2_BUSINESS_TARGET_PATCH_SHA256 = {
    "gateway.mjs": "17157fa5f8739dbe17aae767a335e97dd713a978dde9b192feb1b41a7b036b30",
    "git-publish.mjs": "d8f7f7712129094ce0ffac2eaeb66d15dd3f063a3ade9fa354de7af0d412477a",
    "workspace-access.mjs": "9c4c20dd4edbc426c8561801708ee205e19bb47b48134ec8f5654a10f1cb7cf3",
}

# Only existing reviewed, closed-profile enrolled fleet-v0.1.10 seats.
# Other installed gateways differ in bundle/permissions and are NOT eligible.
FLEET_V10_ENROLLED_ACCOUNTS = frozenset(("chatgpt1", "chatgpt3"))

FLEET_V10_PUBLISHER_PATCH_SHA256 = {
    "git-publish.mjs": "d8f7f7712129094ce0ffac2eaeb66d15dd3f063a3ade9fa354de7af0d412477a",
    "workspace-access.mjs": "9c4c20dd4edbc426c8561801708ee205e19bb47b48134ec8f5654a10f1cb7cf3",
}
# PR #1535's exact, already-installed closed publisher is the ONLY eligible
# second-stage predecessor. No arbitrary closed publisher may be overwritten.
FLEET_V10_PREVIOUS_CLOSED_PUBLISHER_SHA256 = "72faf293d9c0a90c45ab442821e26f199f5ea406a091a7aed7ebce3519e55f69"

# Exact sealed index-sync predecessor observed on enrolled fleet seats. Keep
# this pair independent from both historical targets and the merge target.
FLEET_V10_MERGE_PUBLISHER_PREDECESSOR_SHA256 = {
    "git-publish.mjs": "d8f7f7712129094ce0ffac2eaeb66d15dd3f063a3ade9fa354de7af0d412477a",
    "workspace-access.mjs": "9c4c20dd4edbc426c8561801708ee205e19bb47b48134ec8f5654a10f1cb7cf3",
}
FLEET_V10_MERGE_PUBLISHER_PATCH_SHA256 = {
    "git-publish.mjs": "badd8a554ae8230808d18a1943aa49edb7ced51391ed2cbadb358cd015d62c3a",
    "workspace-access.mjs": "e4f74c201d177e6af1c3e113cc180430542cfd08a25591b81fb6d04c8a575db5",
}

# Exact sealed C2 predecessor observed for the one-seat Paper v10 -> v12 repair.
# These are reviewed installation identity pins, never caller-selectable source or runtime paths.
# The fleet bundle remains installed byte-for-byte; only Paper configuration moves.
C2_PAPER_ACCOUNT = "chatgpt2-personal"
C2_PAPER_ORIGINAL_MANIFEST_SHA256 = "10658ddba662cac2c0a321dfdc48b9b009199187e9709f8f7d63a30bf2406337"
C2_PAPER_MANIFEST_CANONICAL_SHA256 = frozenset((
    "821e37a4e10011f3335984416edaac92899c6bc27526c0f017b3d75130950d84",
    "d477cd952b86d76c07a2554a94a1ce5dc8c5e42bda544a5603caf0f54e17c9b7",
))
C2_LIFECYCLE_LOCK_NAME = "private-service.lifecycle.lock"
# These are the two already enrolled restricted Fabric seats, not a caller-selectable
# account family. Their backends may advance independently of their sealed gateways.
FABRIC_BACKEND_ACCOUNT = "subagent-fabric-c3"
FABRIC_BACKEND_MODERN_ACCOUNT = "fabric-c3-570f6f34"
FABRIC_BACKEND_MODERN_PORT = 45280
FABRIC_BACKEND_ACCOUNTS = frozenset((FABRIC_BACKEND_ACCOUNT, FABRIC_BACKEND_MODERN_ACCOUNT))
FABRIC_BACKEND_SOURCE = "integrations/studio_direct_mcp/fabric-backend.mjs"
FABRIC_BACKEND_RELEASES_REL = Path(".local/share/studio-direct-mcp/releases")
FABRIC_BACKEND_RELEASE_SCHEMA = "mastermind.fabric_backend_release.v1"
C2_PAPER_NON_PAPER_CONFIG_SHA256 = "adc1c3367236b8a3a49b30169c2fb0a5dc3e85ecb415ab1b7d4d799fdf075b38"
C2_PAPER_ORIGINAL_BRIDGE_SHA256 = "7d810c458a53e00e21014fd7375ac338dc9c1421b30f823feb4d34184f9d08fc"
C2_PAPER_FILES_SHA256 = {
    "fleet-routing.mjs": "dc98537e5ade635f5c9fa3a89ab99ae9ea57f549d2856832d01f90c1e61c1533",
    "fleet-status.mjs": "a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780",
    "gateway.mjs": "92e7f38f9eb53a5b140d0f3809b3381a4d35cea86bbb2e20229f108792ec30c8",
    "git-publish.mjs": "9d50cd828e51d0c08a7be0ca7b18c89bfd8fb767a548bb1e4deaddaf185225ae",
    "output-budget.mjs": "5fb464cdb531adf944561ddda760b77856530bcc08f7ba48ef774d6750f5a071",
    "package-lock.json": "9a4e7398ddb45f44d6910fc05118bac425397f4b9869f33229da81f76ae262d0",
    "package.json": "25ab096e21ac6e8c3761ee896e69d175ba628c1fe5751bcfab452c304a4bb634",
    "paper-design.mjs": "e2162584ceab9941e7bcce51b73120c9a9aeb13c128cd5b217077c005f0f1c7e",
    "private-tunnel-auth.mjs": "fe8c9e5ba14fd7750fc26bbfe45ed3f77d4b96fa8ff639c6b5efdf653740e1c0",
    "private-tunnel-gateway.mjs": "fd4eb541590cafc3c92a0b0ac1f7080baa76193704a2219e58b02462ef4d5540",
    "tailnet-gateway.mjs": "9dd75992ba0b5c658582779ebeb71a06f13ec0a3475aa83d62753e22832b906b",
}
C2_PAPER_RUNTIME_IDENTITY = {
    "host": "127.0.0.1",
    "port": 45026,
    "nodeHash": "3fbe98203f8f4a86ce5b0b573a1a30aa4253064c4c2a0299c436d259b68e54b0",
    "backendHash": "a4145198dc75cd34e7c7452c2054b4cc0d29e199ae1459961a17e4da25a13500",
    "dependencyTreeHash": "91ce96dc69159edcabb3eee472e6ebafb18450b93a03addd6adf0df6dca47e29",
}

# Distinct sealed, already-enrolled C2 Business Paper v10 installation. This is
# an independent per-seat transaction, never permission to rewrite another
# account's config, fleet modules, workspace grants, or immutable runtime.
C2_PAPER_BUSINESS_ACCOUNT = "chatgpt2-business"
C2_PAPER_UPGRADE_ACCOUNTS = frozenset((C2_PAPER_ACCOUNT, C2_PAPER_BUSINESS_ACCOUNT))
C2_PAPER_BUSINESS_ORIGINAL_MANIFEST_SHA256 = "504c22af839e154bb1a5314134240b9eb7064f043e1003a357922e1103c21b06"
C2_PAPER_BUSINESS_NON_PAPER_CONFIG_SHA256 = "ed2dc2b9f7f812406c7ef7e9297b3ad5b54c8c15c11903463e61a1d628b0fdf0"
C2_PAPER_BUSINESS_RUNTIME_IDENTITY = {**C2_PAPER_RUNTIME_IDENTITY, "port": 45028}

# Independently verified C4 installation, observed 2026-10-18. Its eleven module
# bytes equal C2_PAPER_FILES_SHA256, but its account, manifests, configuration and
# dependency seal are distinct. This admits only its original and planned Paper
# configuration; it does not enroll a new workspace or change installed grants.
C4_PAPER_ACCOUNT = "chatgpt4"
C4_PAPER_ORIGINAL_MANIFEST_SHA256 = "849e0af6b498408eba843bcbf2c9c500e199c218db06f00db9cb13b54303b071"
C4_PAPER_MANIFEST_CANONICAL_SHA256 = frozenset((
    "e0e7865965285af6372fdf27ee70ae27f494b37fe19e1f5af763406295a96ec2",
    "2252819766e266ac0be6b30c94694b503aad4634d8de184f62611542fb581bd0",
    # Exact native-pool pin postimage; all other C4 profile fields stay sealed.
    "e10730454cd343b8774929b9c6d39f5dfbf1c9b7e83bfdc82636b8e54d0437a0",
))
C4_PAPER_NON_PAPER_CONFIG_SHA256 = "94a480d9db9c59e2d76b6d3fdd9f9b1a448bcd77c26fbe30f430f79357e36894"
C4_PAPER_RUNTIME_IDENTITY = {
    "host": "127.0.0.1",
    "port": 45024,
    "nodeHash": "3fbe98203f8f4a86ce5b0b573a1a30aa4253064c4c2a0299c436d259b68e54b0",
    "backendHash": "a4145198dc75cd34e7c7452c2054b4cc0d29e199ae1459961a17e4da25a13500",
    "dependencyTreeHash": "639c904d1d5832baa832eac8519cf2304073d3d72fdacc03fd879281068e6211",
}
PAPER_RUNTIME_UPGRADE_ACCOUNTS = C2_PAPER_UPGRADE_ACCOUNTS | frozenset((C4_PAPER_ACCOUNT,))


KNOWN_MANIFEST_FILESETS = frozenset(
    (
        frozenset(STAGE_FILES),
        frozenset(LEGACY_STAGE_FILES_V7),
        frozenset(LEGACY_STAGE_FILES_V6),
        frozenset(LEGACY_STAGE_FILES_V5),
        frozenset(LEGACY_STAGE_FILES_V4),
        frozenset(LEGACY_STAGE_FILES_V3),
        frozenset(LEGACY_STAGE_FILES_V2),
        frozenset(LEGACY_STAGE_FILES_V1),
    )
)

MANIFEST_VERSION = 2
MANIFEST_KEYS_V1 = (
    "version",
    "account",
    "label",
    "files",
    "configHash",
    "plistHash",
    "source",
    "node",
    "backend",
    "host",
    "port",
)
MANIFEST_KEYS_V2 = MANIFEST_KEYS_V1 + (
    "nodeHash",
    "backendHash",
    "dependencyTreeHash",
)
LEGACY_PROVISIONED_MANIFEST_KEYS = MANIFEST_KEYS_V1 + (
    "provisioned_from",
    "installation_state",
)
LEGACY_PROVISIONED_STATE = "LOCAL_GATEWAY_PREPARED_TUNNEL_NOT_CREATED"


class CmdResult:
    __slots__ = ("returncode", "stdout", "stderr")

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _run(cmd, *, check: bool = True, timeout: float = 30.0) -> CmdResult:
    res = subprocess.run(
        list(cmd),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = CmdResult(res.returncode, res.stdout or "", res.stderr or "")
    if check and out.returncode != 0:
        raise RuntimeError(
            f"command failed: {cmd!r} rc={out.returncode} stderr={out.stderr.strip()}"
        )
    return out


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_json_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _sha256_hex(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        c in "0123456789abcdef" for c in value
    )


def _stable_regular_file_hash(path: Path, *, label: str) -> str:
    """Hash one exact regular file and refuse identity drift while reading it."""

    try:
        before = path.lstat()
    except OSError:
        raise SystemExit(f"{label} missing") from None
    if path.is_symlink() or not stat.S_ISREG(before.st_mode):
        raise SystemExit(f"{label} must be a regular non-symlink file")
    digest = _sha256_file(path)
    try:
        after = path.lstat()
    except OSError:
        raise SystemExit(f"{label} changed while hashing") from None
    identity = lambda info: (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )
    if identity(before) != identity(after):
        raise SystemExit(f"{label} changed while hashing")
    return digest


def _dependency_tree_hash_once(root: Path) -> str:
    """Return one host-path-independent digest of the installed dependency tree."""

    if root.is_symlink() or not root.is_dir():
        raise SystemExit(
            "not staged: node_modules missing; "
            "parent must run npm ci --omit=dev --ignore-scripts"
        )
    try:
        resolved_root = root.resolve(strict=True)
        root_info = root.lstat()
    except OSError:
        raise SystemExit("not staged: node_modules unavailable") from None
    entries: list[tuple[object, ...]] = [
        (".", "directory", stat.S_IMODE(root_info.st_mode))
    ]
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            children = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError:
            raise SystemExit("not staged: dependency tree unreadable") from None
        for child in children:
            path = Path(child.path)
            rel = path.relative_to(root).as_posix()
            try:
                info = path.lstat()
            except OSError:
                raise SystemExit("not staged: dependency tree changed while hashing") from None
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISLNK(info.st_mode):
                try:
                    target = os.readlink(path)
                except OSError:
                    raise SystemExit("not staged: dependency symlink unreadable") from None
                if os.path.isabs(target):
                    raise SystemExit("not staged: dependency symlink escapes node_modules")
                try:
                    resolved_target = (path.parent / target).resolve(strict=True)
                    resolved_target.relative_to(resolved_root)
                except (OSError, ValueError):
                    raise SystemExit("not staged: dependency symlink escapes node_modules") from None
                entries.append((rel, "symlink", mode, target))
            elif stat.S_ISDIR(info.st_mode):
                entries.append((rel, "directory", mode))
                stack.append(path)
            elif stat.S_ISREG(info.st_mode):
                digest = _stable_regular_file_hash(path, label="dependency file")
                entries.append((rel, "file", mode, info.st_size, digest))
            else:
                raise SystemExit("not staged: unsupported dependency entry")
    payload = json.dumps(
        sorted(entries, key=lambda item: str(item[0])),
        sort_keys=False,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _dependency_tree_hash(root: Path) -> str:
    """Require two identical dependency observations so concurrent drift refuses."""

    first = _dependency_tree_hash_once(root)
    second = _dependency_tree_hash_once(root)
    if first != second:
        raise SystemExit("not staged: dependency tree changed while hashing")
    return first


def _user_root() -> Path:
    return Path(os.environ.get("HOME") or str(Path.home()))


def _fsync_dir(directory: Path) -> None:
    try:
        dfd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def _under_home(path: Path, home: Path) -> bool:
    path_s = os.path.normpath(str(path))
    home_s = os.path.normpath(str(home))
    return path_s == home_s or path_s.startswith(home_s + os.sep)


def _assert_no_symlink_ancestors(path: Path) -> None:
    """Refuse symlink components between dest and HOME.

    Path.mkdir(parents=True) follows parent symlinks. Walk stops at HOME so
    platform links above the test/user root (e.g. /var -> /private/var) are
    not treated as hostile.
    """
    home = _user_root()
    if not path.is_absolute():
        raise SystemExit(f"path must be absolute: {path}")
    if not _under_home(path, home):
        raise SystemExit(f"refusing path outside HOME: {path}")
    cur = path
    while cur != home:
        if os.path.islink(cur):
            raise SystemExit(f"refusing symlink ancestor: {cur}")
        parent = cur.parent
        if parent == cur:
            break
        cur = parent


def _atomic_write_bytes(path: Path, data: bytes, mode: int = FILE_MODE) -> None:
    _assert_no_symlink_ancestors(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.path.islink(path.parent) or (path.parent.exists() and not path.parent.is_dir()):
        raise SystemExit(f"refusing non-directory or symlink path: {path.parent}")
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _atomic_write_text(path: Path, data: str, mode: int = FILE_MODE) -> None:
    _atomic_write_bytes(path, data.encode("utf-8"), mode)


def _is_owned_by_us(path: Path) -> bool:
    return os.lstat(path).st_uid == os.getuid()


def _assert_dest_safe(path: Path) -> None:
    _assert_no_symlink_ancestors(path)
    if path.is_symlink():
        raise SystemExit(f"refusing destination symlink: {path}")
    if path.exists() and not _is_owned_by_us(path):
        raise SystemExit(f"refusing non-owned destination: {path}")


def _ensure_secure_dir(path: Path) -> None:
    if path.is_symlink():
        raise SystemExit(f"refusing symlink path: {path}")
    _assert_no_symlink_ancestors(path)
    if path.exists():
        if not path.is_dir():
            raise SystemExit(f"refusing non-directory path: {path}")
        st = os.lstat(path)
        if st.st_uid != os.getuid():
            raise SystemExit(f"refusing non-owned directory: {path}")
        os.chmod(path, DIR_MODE)
        return
    path.mkdir(parents=True, mode=DIR_MODE)
    if path.is_symlink() or not path.is_dir():
        raise SystemExit(f"refusing non-directory or symlink path: {path}")
    st = os.lstat(path)
    if st.st_uid != os.getuid():
        raise SystemExit(f"refusing non-owned directory: {path}")
    os.chmod(path, DIR_MODE)


def _copy_secure(src: Path, dst: Path) -> None:
    if src.is_symlink() or not src.is_file():
        raise SystemExit(f"source invalid: {src}")
    _assert_dest_safe(dst)
    _ensure_secure_dir(dst.parent)
    _atomic_write_bytes(dst, src.read_bytes(), FILE_MODE)


def _check_source_files(source: Path) -> list[Path]:
    if source.is_symlink() or not source.is_dir():
        raise SystemExit(f"source dir invalid: {source}")
    found: list[Path] = []
    for name in STAGE_FILES:
        p = source / name
        if p.is_symlink() or not p.is_file():
            raise SystemExit(f"missing or symlink source file: {p}")
        found.append(p)
    return found


def _resolve_abs(name: str, value: str) -> Path:
    if not os.path.isabs(value):
        raise SystemExit(f"{name} must be absolute: {value}")
    p = Path(value)
    if p.is_symlink():
        raise SystemExit(f"{name} must not be a symlink: {value}")
    if not p.is_file():
        raise SystemExit(f"{name} not found: {value}")
    return p


def _validate_account_label(label: str) -> None:
    if not label:
        raise SystemExit("account label must not be empty")
    if not label.isascii():
        raise SystemExit("account label must be ASCII")
    if label != label.lower():
        raise SystemExit("account label must be lowercase")
    if len(label) > ACCOUNT_LABEL_MAX:
        raise SystemExit("account label must be at most 64 characters")
    if not ACCOUNT_LABEL_RE.fullmatch(label):
        raise SystemExit(
            "account label must match "
            f"{ACCOUNT_LABEL_RE.pattern} (got {label!r})"
        )
    if label in RESERVED_ACCOUNT_LABELS:
        raise SystemExit(f"account label {label!r} is reserved")


def _build_runtime_roots(account: str) -> dict:
    """Build per-account paths using the real HOME environment variable."""
    user_root = _user_root()
    base = user_root / ".local" / "share" / "studio-direct-mcp" / "private" / account
    return {
        "base": base,
        "state": base / "state",
        "logs": base / "logs",
        "config": base / "config.json",
        "manifest": base / "manifest.json",
        "plist": user_root / "Library" / "LaunchAgents" / f"com.mastermind.studio-direct-private.{account}.plist",
        "gateway": base / PRIVATE_GATEWAY_NAME,
        "node_modules": base / "node_modules",
    }



# Exact existing cohort: pin compatibility preserves installed capabilities.
NATIVE_POOL_PIN_ACCOUNTS = frozenset(('admin-business', 'chatgpt1', 'chatgpt2-business', 'chatgpt2-personal', 'chatgpt3', 'chatgpt3-w570f6f34', 'chatgpt3-wa2a9e6f9', 'chatgpt4', 'fabric-design', 'fabric-read'))
NATIVE_POOL_PIN_PREDECESSORS = {'admin-business': {'fleet-routing.mjs': 'dc98537e5ade635f5c9fa3a89ab99ae9ea57f549d2856832d01f90c1e61c1533',
                    'fleet-status.mjs': 'a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780',
                    'gateway.mjs': '92e7f38f9eb53a5b140d0f3809b3381a4d35cea86bbb2e20229f108792ec30c8',
                    'git-publish.mjs': '9d50cd828e51d0c08a7be0ca7b18c89bfd8fb767a548bb1e4deaddaf185225ae',
                    'output-budget.mjs': '5fb464cdb531adf944561ddda760b77856530bcc08f7ba48ef774d6750f5a071',
                    'package-lock.json': '9a4e7398ddb45f44d6910fc05118bac425397f4b9869f33229da81f76ae262d0',
                    'package.json': '25ab096e21ac6e8c3761ee896e69d175ba628c1fe5751bcfab452c304a4bb634',
                    'paper-design.mjs': 'e2162584ceab9941e7bcce51b73120c9a9aeb13c128cd5b217077c005f0f1c7e',
                    'private-tunnel-auth.mjs': 'fe8c9e5ba14fd7750fc26bbfe45ed3f77d4b96fa8ff639c6b5efdf653740e1c0',
                    'private-tunnel-gateway.mjs': 'fd4eb541590cafc3c92a0b0ac1f7080baa76193704a2219e58b02462ef4d5540',
                    'tailnet-gateway.mjs': '9dd75992ba0b5c658582779ebeb71a06f13ec0a3475aa83d62753e22832b906b'},
 'chatgpt3-w570f6f34': {'fleet-routing.mjs': 'dc98537e5ade635f5c9fa3a89ab99ae9ea57f549d2856832d01f90c1e61c1533',
                        'fleet-status.mjs': 'a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780',
                        'gateway.mjs': '92e7f38f9eb53a5b140d0f3809b3381a4d35cea86bbb2e20229f108792ec30c8',
                        'git-publish.mjs': '9d50cd828e51d0c08a7be0ca7b18c89bfd8fb767a548bb1e4deaddaf185225ae',
                        'output-budget.mjs': '5fb464cdb531adf944561ddda760b77856530bcc08f7ba48ef774d6750f5a071',
                        'package-lock.json': '9a4e7398ddb45f44d6910fc05118bac425397f4b9869f33229da81f76ae262d0',
                        'package.json': '25ab096e21ac6e8c3761ee896e69d175ba628c1fe5751bcfab452c304a4bb634',
                        'paper-design.mjs': 'e2162584ceab9941e7bcce51b73120c9a9aeb13c128cd5b217077c005f0f1c7e',
                        'private-tunnel-auth.mjs': 'fe8c9e5ba14fd7750fc26bbfe45ed3f77d4b96fa8ff639c6b5efdf653740e1c0',
                        'private-tunnel-gateway.mjs': 'fd4eb541590cafc3c92a0b0ac1f7080baa76193704a2219e58b02462ef4d5540',
                        'tailnet-gateway.mjs': '9dd75992ba0b5c658582779ebeb71a06f13ec0a3475aa83d62753e22832b906b'},
 'chatgpt3-wa2a9e6f9': {'fleet-routing.mjs': 'dc98537e5ade635f5c9fa3a89ab99ae9ea57f549d2856832d01f90c1e61c1533',
                        'fleet-status.mjs': 'a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780',
                        'gateway.mjs': '92e7f38f9eb53a5b140d0f3809b3381a4d35cea86bbb2e20229f108792ec30c8',
                        'git-publish.mjs': '9d50cd828e51d0c08a7be0ca7b18c89bfd8fb767a548bb1e4deaddaf185225ae',
                        'output-budget.mjs': '5fb464cdb531adf944561ddda760b77856530bcc08f7ba48ef774d6750f5a071',
                        'package-lock.json': '9a4e7398ddb45f44d6910fc05118bac425397f4b9869f33229da81f76ae262d0',
                        'package.json': '25ab096e21ac6e8c3761ee896e69d175ba628c1fe5751bcfab452c304a4bb634',
                        'paper-design.mjs': 'e2162584ceab9941e7bcce51b73120c9a9aeb13c128cd5b217077c005f0f1c7e',
                        'private-tunnel-auth.mjs': 'fe8c9e5ba14fd7750fc26bbfe45ed3f77d4b96fa8ff639c6b5efdf653740e1c0',
                        'private-tunnel-gateway.mjs': 'fd4eb541590cafc3c92a0b0ac1f7080baa76193704a2219e58b02462ef4d5540',
                        'tailnet-gateway.mjs': '9dd75992ba0b5c658582779ebeb71a06f13ec0a3475aa83d62753e22832b906b'},
 'fabric-design': {'fleet-status.mjs': 'a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780',
                   'gateway.mjs': '970b47f1c6a15bc3f1175f1043c5dd4a59ad748c2374b586e384bbd6ba40ce5e',
                   'git-publish.mjs': '9d50cd828e51d0c08a7be0ca7b18c89bfd8fb767a548bb1e4deaddaf185225ae',
                   'output-budget.mjs': '5fb464cdb531adf944561ddda760b77856530bcc08f7ba48ef774d6750f5a071',
                   'package-lock.json': '9a4e7398ddb45f44d6910fc05118bac425397f4b9869f33229da81f76ae262d0',
                   'package.json': '25ab096e21ac6e8c3761ee896e69d175ba628c1fe5751bcfab452c304a4bb634',
                   'paper-design.mjs': 'e2162584ceab9941e7bcce51b73120c9a9aeb13c128cd5b217077c005f0f1c7e',
                   'private-tunnel-auth.mjs': 'fe8c9e5ba14fd7750fc26bbfe45ed3f77d4b96fa8ff639c6b5efdf653740e1c0',
                   'private-tunnel-gateway.mjs': '225b1a592f5486c688efc6f5fc37184877a7e3e8022c2e831858c8989c6cca00',
                   'tailnet-gateway.mjs': 'bd46b40cfd5f2744f9b07be38ff2656676939707e753f6e846f4a2c578944d25'},
 'fabric-read': {'fabric-operator.mjs': '2ed7578ced90da1e17a95faa4df2e43c164ade42e832d307efbb3902aed42a00',
                 'fleet-status.mjs': 'a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780',
                 'gateway.mjs': '2a9038d802cdefeea3af4a3fbe45d2326fb894a42c72f3f4f946603419b93446',
                 'git-publish.mjs': '9d50cd828e51d0c08a7be0ca7b18c89bfd8fb767a548bb1e4deaddaf185225ae',
                 'output-budget.mjs': '5fb464cdb531adf944561ddda760b77856530bcc08f7ba48ef774d6750f5a071',
                 'package-lock.json': '9a4e7398ddb45f44d6910fc05118bac425397f4b9869f33229da81f76ae262d0',
                 'package.json': '25ab096e21ac6e8c3761ee896e69d175ba628c1fe5751bcfab452c304a4bb634',
                 'paper-design.mjs': 'e2162584ceab9941e7bcce51b73120c9a9aeb13c128cd5b217077c005f0f1c7e',
                 'private-tunnel-auth.mjs': 'fe8c9e5ba14fd7750fc26bbfe45ed3f77d4b96fa8ff639c6b5efdf653740e1c0',
                 'private-tunnel-gateway.mjs': '225b1a592f5486c688efc6f5fc37184877a7e3e8022c2e831858c8989c6cca00',
                 'tailnet-gateway.mjs': '89a3d1c972a31ab62f19205439d6f09bc24f4d51783ebc2e1bea788bcd9d817c'}}

# Retained sealed Tailnet seats, each with only its original and exact native
# pool-pin postimage. These are profile selectors, never an argv fallback.
_NATIVE_POOL_PIN_TAILNET_CANONICAL = {
    "fabric-design": frozenset((
        "87de91f4fd0d51571c2350cf4fe53704ad035eba8f095c13b09352732307671c",
        "b08c021b6c3c9cd9a1acdd57957fbf5e88b6d63daa11b963b7476d993b1a8b46",
    )),
    "fabric-read": frozenset((
        "f39e118cb770d4f793dd92c31e9f17f7153e7daef4e9703be7408fde702d40bb",
        "328c25399daf9ab16c994ea30bd4a628ef40483e5f9af89fe34f191ac4f48819",
    )),
}


def _pin_owner_module():
    import importlib.util
    path = Path(__file__).resolve().with_name("private_service_pin.py")
    spec = importlib.util.spec_from_file_location("_studio_pin_owner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cmd_native_pool_pin(args):
    pin = _pin_owner_module()
    try:
        value = pin.run(sys.modules[__name__], args)
    except SystemExit as error:
        allowed = {"NATIVE_POOL_PIN_" + code for code in pin.REFUSAL_CODES}
        allowed.update(("NATIVE_POOL_PIN_SUCCESSOR_REFUSED", "NATIVE_POOL_PIN_SUCCESSOR_CHANGED"))
        if type(error.code) is str and error.code in allowed:
            raise
        raise SystemExit("NATIVE_POOL_PIN_OWNER_REFUSED") from None
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        raise SystemExit("NATIVE_POOL_PIN_OWNER_REFUSED") from None
    print(json.dumps(value, sort_keys=True))
    return 0


@contextmanager
def _pin_native_context(args):
    """Use the existing successor verifier and publication lock, never a hash-only claim."""
    import importlib.util
    rollout = Path(__file__).resolve().parents[2] / "ops/native_fabric/quota_continuity/rollout"
    for name in ("native_install.py", "native_generation.py"):
        source = rollout / name
        if source.is_symlink() or not source.is_file():
            raise SystemExit("NATIVE_POOL_PIN_SUCCESSOR_REFUSED")
    code = r"""
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import native_install as i
import native_generation as g
p,payload=i.read_successor(Path(sys.argv[2]))
assert p['digest']==sys.argv[3]
store=Path(p['store']);current=g.current(store);old=p['expected_selection']
new={'schema':g.POINTER_SCHEMA,'generation':p['target_generation'],'previous':old['generation'],'sequence':old['sequence']+1}
e=p['entries']['pool']
if current==old:
 i._upgrade_entries(p);phase='PREVIOUS'
elif current==new:
 i._upgrade_entries(p,complete=True);phase='SELECTED'
else:raise ValueError('selection_refused')
print(json.dumps({'successor_digest':p['digest'],'target_generation':p['target_generation'],'expected_selection':old,'pool_target':e['target'],'pool_previous':e['previous'],'pool_bridge':e['bridge'],'store':p['store'],'phase':phase},sort_keys=True))
"""
    def proof():
        try:
            r = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(rollout),
                str(args.successor_bundle), args.successor_plan_sha256],
                capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            raise SystemExit("NATIVE_POOL_PIN_SUCCESSOR_REFUSED") from None
        if r.returncode != 0 or len(r.stdout) > 16384:
            raise SystemExit("NATIVE_POOL_PIN_SUCCESSOR_REFUSED")
        value = _pin_owner_module().decode(r.stdout)
        if set(value) != {"successor_digest", "target_generation", "expected_selection",
                "pool_target", "pool_previous", "pool_bridge", "store", "phase"}:
            raise SystemExit("NATIVE_POOL_PIN_SUCCESSOR_REFUSED")
        return value
    first = proof()
    spec = importlib.util.spec_from_file_location("_studio_pin_native_generation", rollout / "native_generation.py")
    generation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generation)
    from contextlib import nullcontext
    lock = (generation.publication_lock(Path(first["store"]))
            if args.operation in ("apply", "reconcile") else nullcontext())
    with lock:
        checked = proof()
        if checked != first:
            raise SystemExit("NATIVE_POOL_PIN_SUCCESSOR_CHANGED")
        yield checked


def _pin_reject_generic_restage(account):
    # The newly recognized cohort receives only preserving lifecycle/pin support.
    # It does not silently acquire the generic capability-rebuilding upgrade path.
    if account not in NATIVE_POOL_PIN_ACCOUNTS:
        return
    _validate_account_label(account)
    roots = _build_runtime_roots(account)
    if os.path.lexists(roots["state"] / "native-pool-pin"):
        raise SystemExit("NATIVE_POOL_PIN_PROFILE_REQUIRES_PIN_OWNER")
    if account not in NATIVE_POOL_PIN_PREDECESSORS:
        return
    if not os.path.lexists(roots["manifest"]):
        return
    prior = _read_manifest(roots["manifest"], account,
        "com.mastermind.studio-direct-private." + account, required=True)
    if prior["files"] == NATIVE_POOL_PIN_PREDECESSORS[account]:
        raise SystemExit("NATIVE_POOL_PIN_PROFILE_REQUIRES_PIN_OWNER")


def _pin_require_start(account, roots):
    if account not in NATIVE_POOL_PIN_ACCOUNTS:
        return
    _pin_owner_module().require_start(sys.modules[__name__], account, roots)


@contextmanager
def _c2_lifecycle_mutex(account: str):
    """Serialize enrolled Paper and Fabric mutations on persistent private lock inodes.

    Never unlink this file: replacement would let another invocation lock a new
    inode while the previous one is still held. Closing the descriptor (including
    process exit) releases the lock, and CLOEXEC prevents launchctl inheriting it.
    """
    if account not in (PAPER_RUNTIME_UPGRADE_ACCOUNTS | FABRIC_BACKEND_ACCOUNTS | {"chatgpt2-business"} | NATIVE_POOL_PIN_ACCOUNTS):
        raise SystemExit("C2 lifecycle mutex cannot select another account")
    subject = "Fabric" if account in FABRIC_BACKEND_ACCOUNTS else "C2"
    lock_path = _build_runtime_roots(account)["state"] / C2_LIFECYCLE_LOCK_NAME
    _assert_dest_safe(lock_path)
    current = lock_path.parent
    home = _user_root()
    while True:
        try:
            info = current.lstat()
        except OSError as exc:
            raise SystemExit(f"{subject} lifecycle lock parent is unavailable") from exc
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o022
                or (current == lock_path.parent and stat.S_IMODE(info.st_mode) & 0o077)):
            raise SystemExit(f"{subject} lifecycle lock parent is unsafe")
        if current == home:
            break
        current = current.parent
    try:
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, FILE_MODE)
    except OSError as exc:
        raise SystemExit(f"{subject} lifecycle lock is unavailable") from exc
    try:
        def verify_inode():
            held = os.fstat(fd)
            _assert_dest_safe(lock_path)
            named = lock_path.lstat()
            if (not stat.S_ISREG(held.st_mode) or held.st_uid != os.getuid()
                    or stat.S_IMODE(held.st_mode) != FILE_MODE or held.st_nlink != 1
                    or held.st_size != 0 or (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino)):
                raise SystemExit(f"{subject} lifecycle lock inode is unsafe or changed")
        verify_inode()
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit(f"{subject} lifecycle mutation already in progress; refusing concurrent operation") from exc
        except OSError as exc:
            raise SystemExit(f"{subject} lifecycle lock could not be acquired") from exc
        verify_inode()
        yield
    finally:
        os.close(fd)


def _c2_lifecycle_serialized(*, readonly_preflight: bool = False):
    def decorate(function):
        @wraps(function)
        def guarded(args):
            if (args.account not in PAPER_RUNTIME_UPGRADE_ACCOUNTS
                    or (readonly_preflight and getattr(args, "preflight_only", False) is True)):
                return function(args)
            with _c2_lifecycle_mutex(args.account):
                return function(args)
        return guarded
    return decorate


def _fabric_lifecycle_serialized(*, readonly_preflight: bool = False):
    """Only the two enrolled Fabric seats share their release locks with lifecycle calls."""
    def decorate(function):
        @wraps(function)
        def guarded(args):
            if (args.account not in FABRIC_BACKEND_ACCOUNTS
                    or (readonly_preflight and getattr(args, "preflight_only", False) is True)):
                return function(args)
            # First-install staging predates a runtime/state directory. There can
            # be no backend release until that first manifest exists.
            if (function.__name__ == "cmd_stage"
                    and not _build_runtime_roots(args.account)["state"].exists()):
                return function(args)
            with _c2_lifecycle_mutex(args.account):
                return function(args)
        return guarded
    return decorate


def _pin_lifecycle_serialized(function):
    """Extend only normal lifecycle calls, without changing Paper eligibility gates."""
    @wraps(function)
    def guarded(args):
        covered = PAPER_RUNTIME_UPGRADE_ACCOUNTS | FABRIC_BACKEND_ACCOUNTS
        if args.account not in NATIVE_POOL_PIN_ACCOUNTS or args.account in covered:
            return function(args)
        with _c2_lifecycle_mutex(args.account):
            return function(args)
    return guarded


def _pin_install_serialized(function):
    """The existing installer mutates under the same pin/lifecycle lock."""
    @wraps(function)
    def guarded(source, node_abs, backend_abs, account, label, host, port, roots, **kwargs):
        if account not in NATIVE_POOL_PIN_ACCOUNTS or not os.path.lexists(roots["manifest"]):
            return function(source, node_abs, backend_abs, account, label, host, port, roots, **kwargs)
        before = _fabric_release_bytes(roots["manifest"])
        with _c2_lifecycle_mutex(account):
            if _fabric_release_bytes(roots["manifest"]) != before:
                raise SystemExit("NATIVE_POOL_PIN_INSTALL_CAS_REFUSED")
            _pin_reject_generic_restage(account)
            return function(source, node_abs, backend_abs, account, label, host, port, roots, **kwargs)
    return guarded


def _typed_git_config(user_root: Path, *, closed_repositories: bool = False) -> dict:
    common = {
        "enabled": True,
        "workspaceCli": str(user_root / TYPED_GIT_WORKSPACE_CLI_REL),
        "gitBinary": TYPED_GIT_BINARY,
        "commandTimeoutMs": 15_000,
        "pushTimeoutMs": 60_000,
    }
    if closed_repositories:
        return {
            **common,
            "repositories": [
                {
                    "repository": alias,
                    "sourceRepository": str(user_root / source),
                    "allowedRemoteUrls": [remote],
                }
                for alias, source, remote in TYPED_GIT_CLOSED_PROFILES
            ],
        }
    return {
        **common,
        "sourceRepository": str(user_root / TYPED_GIT_SOURCE_REPOSITORY_REL),
        "allowedRemoteUrls": [TYPED_GIT_REMOTE_URL],
    }


def _verify_paper_runtime(user_root: Path, *, expected_sha: str | None = None) -> dict:
    runtime = user_root / PAPER_RUNTIME_REL
    expected_sha = PAPER_BRIDGE_SHA256 if expected_sha is None else expected_sha
    source = runtime / "source"
    bridge = source / "bridge.py"
    receipt_path = runtime / "RUNTIME.json"
    python = runtime / "venv" / "bin" / "python"

    for path, label in ((runtime, "runtime"), (source, "source")):
        if path.is_symlink() or not path.is_dir():
            raise SystemExit(f"paper {label} missing or unsafe: {path}")
        info = path.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise SystemExit(f"paper {label} permissions/owner are unsafe: {path}")

    for path, label in ((bridge, "bridge"), (receipt_path, "receipt")):
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"paper {label} missing or unsafe: {path}")
        info = path.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise SystemExit(f"paper {label} permissions/owner are unsafe: {path}")

    if python.is_symlink() or not python.is_file() or not os.access(python, os.X_OK):
        raise SystemExit(f"paper runtime python missing or unsafe: {python}")
    if _sha256_file(bridge) != expected_sha:
        raise SystemExit("paper bridge hash mismatch")

    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("paper runtime receipt invalid") from exc
    expected_sources = {"bridge.py": expected_sha}
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema") != PAPER_RUNTIME_SCHEMA
        or receipt.get("generation") != PAPER_RUNTIME_REL.name
        or receipt.get("bridge_sha256") != expected_sha
        or receipt.get("source_sha256") != expected_sources
        or receipt.get("network_install_performed") is not False
        or receipt.get("production_acceptance") is not False
    ):
        raise SystemExit("paper runtime receipt does not match the required generation")
    return receipt


def _paper_design_config(user_root: Path) -> dict:
    runtime = user_root / PAPER_RUNTIME_REL
    return {
        "enabled": True,
        "pythonPath": str(runtime / "venv" / "bin" / "python"),
        "bridgePath": str(runtime / "source" / "bridge.py"),
        "bridgeSha256": PAPER_BRIDGE_SHA256,
        "appPath": str(user_root / PAPER_APP_REL),
        "commandTimeoutMs": PAPER_COMMAND_TIMEOUT_MS,
    }


def _fleet_status_config(user_root: Path) -> dict | None:
    launcher = user_root / FLEET_STATUS_LAUNCHER_REL
    if not launcher.exists():
        return None
    return {
        "enabled": True,
        "launcherPath": str(launcher),
        "launcherSha256": _stable_regular_file_hash(
            launcher, label="Studio Direct control launcher"
        ),
        "timeoutMs": FLEET_STATUS_TIMEOUT_MS,
    }


def _build_config(
    account: str,
    host: str,
    port: int,
    node_abs: Path,
    backend_abs: Path,
    state_dir: Path,
    user_root: Path,
    *,
    repository_workspaces: bool = False,
    commission_digest: str | None = None,
    fabric_only: bool = False,
    modern_fabric: bool = False,
) -> dict:
    if type(modern_fabric) is not bool or (modern_fabric and (not fabric_only or host != "127.0.0.1")):
        raise ValueError("modern Fabric requires the closed private Fabric-only profile")
    if type(fabric_only) is not bool or (fabric_only and (repository_workspaces or commission_digest is not None)):
        raise ValueError("Fabric-only profile cannot enable unrelated capabilities")
    if type(repository_workspaces) is not bool:
        raise ValueError("repository workspace setting must be boolean")
    # publicUrl is omitted: the private adapter rejects a public origin.
    config = {
        "accountLabel": account,
        "host": host,
        "testMode": False,
        "port": port,
        "command": str(node_abs),
        "args": [str(backend_abs), "--no-onboarding"],
        "cwd": str(user_root),
        "childEnv": {"NODE_OPTIONS": ""},
        "stateDir": str(state_dir),
        "maxSessions": MAX_SESSIONS,
        "requestTimeoutMs": REQUEST_TIMEOUT_MS,
        "idleTimeoutMs": IDLE_TIMEOUT_MS,
        "reclaimIdleGraceMs": 30_000,
        "gitPublish": False if fabric_only else _typed_git_config(
            user_root, closed_repositories=repository_workspaces),
        "paperDesign": False if fabric_only else _paper_design_config(user_root),
    }
    if fabric_only:
        config["fabricOnly"] = True
        config["childEnv"]["MMX_FABRIC_SDK_PACKAGE"] = str(state_dir.parent / "package.json")
    if modern_fabric:
        config["modernFabricProtocol"] = True
        config["backendMode"] = "shared-account"
    if repository_workspaces:
        config["repositoryWorkspaces"] = {
            "enabled": True, "allowedRepositories": ["mastermind", "macro", "terminal"]
        }
    if commission_digest is not None:
        if (not repository_workspaces or host != "127.0.0.1" or port in (8443, RESERVED_FUNNEL_PORT)
                or type(commission_digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", commission_digest)):
            raise ValueError("commission publication requires closed private workspace profile")
        config["commissionPublication"] = {"enabled": True, "configurationDigest": commission_digest}
    # An attended Fabric-only channel exposes no unrelated host telemetry.
    if not fabric_only:
        fleet_status = _fleet_status_config(user_root)
        if fleet_status is not None:
            config["fleetStatus"] = fleet_status
    return config


def _build_plist(
    node_abs: Path,
    gateway_path: Path,
    config_path: Path,
    user_root: Path,
    label: str,
) -> dict:
    return {
        "Label": label,
        "ProgramArguments": [
            str(node_abs),
            str(gateway_path),
            str(config_path),
        ],
        "EnvironmentVariables": {
            "NODE_OPTIONS": "",
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(user_root),
            "UV_THREADPOOL_SIZE": "16",
        },
        "ProcessType": "Interactive",
        "Umask": 0o077,
        "ExitTimeOut": 25,
        "WorkingDirectory": str(user_root),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 10,
        "StandardOutPath": str(gateway_path.parent / "logs" / "out.log"),
        "StandardErrorPath": str(gateway_path.parent / "logs" / "err.log"),
        "StandardInPath": "/dev/null",
    }


def _write_plist(plist_path: Path, payload: dict) -> None:
    _assert_dest_safe(plist_path)
    data = plistlib.dumps(payload, fmt=plistlib.FMT_XML)
    _atomic_write_bytes(plist_path, data, FILE_MODE)


def _valid_manifest(data, account: str, label: str) -> bool:
    if not isinstance(data, dict):
        return False
    version = data.get("version")
    keys = frozenset(data)
    legacy_provisioned = (
        version == 1 and keys == frozenset(LEGACY_PROVISIONED_MANIFEST_KEYS)
    )
    expected_keys = (
        frozenset(MANIFEST_KEYS_V1)
        if version == 1 and not legacy_provisioned
        else frozenset(MANIFEST_KEYS_V2)
        if version == MANIFEST_VERSION
        else frozenset(LEGACY_PROVISIONED_MANIFEST_KEYS)
        if legacy_provisioned
        else None
    )
    if expected_keys is None or keys != expected_keys:
        return False
    if data.get("account") != account or data.get("label") != label:
        return False
    if legacy_provisioned:
        if data.get("installation_state") != LEGACY_PROVISIONED_STATE:
            return False
        provisioned_from = data.get("provisioned_from")
        if not isinstance(provisioned_from, str) or not provisioned_from:
            return False
        source_account = Path(provisioned_from)
        expected_parent = (
            _user_root() / ".local" / "share" / "studio-direct-mcp" / "private"
        )
        if (
            not source_account.is_absolute()
            or source_account.parent != expected_parent
            or source_account.name == account
            or ACCOUNT_LABEL_RE.fullmatch(source_account.name) is None
        ):
            return False
    files = data.get("files")
    if not isinstance(files, dict):
        return False
    fileset = frozenset(files)
    c2_paper_predecessor = (
        version == MANIFEST_VERSION and account == C2_PAPER_ACCOUNT
        and files == C2_PAPER_FILES_SHA256
        and all(data.get(key) == value for key, value in C2_PAPER_RUNTIME_IDENTITY.items())
        and _canonical_json_sha256(data) in C2_PAPER_MANIFEST_CANONICAL_SHA256
    )
    c4_paper_cohort = (
        version == MANIFEST_VERSION and account == C4_PAPER_ACCOUNT
        and files == C2_PAPER_FILES_SHA256
        and all(data.get(key) == value for key, value in C4_PAPER_RUNTIME_IDENTITY.items())
        and _canonical_json_sha256(data) in C4_PAPER_MANIFEST_CANONICAL_SHA256
    )
    if (fileset not in KNOWN_MANIFEST_FILESETS
            and not (version == MANIFEST_VERSION and (
                fileset == V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR
                or (account == "chatgpt2-business"
                    and fileset == V2_C2_BUSINESS_FLEET_PREDECESSOR)
            ))
            and not c2_paper_predecessor and not c4_paper_cohort
            and not (version == MANIFEST_VERSION and account in NATIVE_POOL_PIN_PREDECESSORS
                     and files == NATIVE_POOL_PIN_PREDECESSORS[account])):
        return False
    if any(not _sha256_hex(digest) for digest in files.values()):
        return False
    if not _sha256_hex(data.get("configHash")) or not _sha256_hex(data.get("plistHash")):
        return False
    if version == MANIFEST_VERSION:
        if not _sha256_hex(data.get("nodeHash")) or not _sha256_hex(data.get("backendHash")):
            return False
        dependency_hash = data.get("dependencyTreeHash")
        if dependency_hash is not None and not _sha256_hex(dependency_hash):
            return False
    return True


def _read_manifest(
    manifest_path: Path,
    account: str,
    label: str,
    *,
    required: bool = False,
) -> dict | None:
    if manifest_path.is_symlink():
        raise SystemExit("refusing symlink manifest")
    if not manifest_path.exists():
        if required:
            raise SystemExit("not staged: manifest missing")
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise SystemExit("corrupt manifest")
    if not _valid_manifest(data, account, label):
        raise SystemExit("corrupt manifest")
    return data


def _installed_file_hashes(
    base: Path, names: tuple[str, ...] = STAGE_FILES
) -> dict[str, str] | None:
    hashes: dict[str, str] = {}
    for name in names:
        dest = base / name
        if dest.is_symlink() or not dest.is_file():
            return None
        hashes[name] = _sha256_file(dest)
    return hashes


def _load_plist(plist_path: Path) -> dict | None:
    if plist_path.is_symlink() or not plist_path.is_file():
        return None
    try:
        with plist_path.open("rb") as fh:
            data = plistlib.load(fh)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _launchd_domain() -> str:
    return f"gui/{os.getuid()}"


def _launchd_target(label: str) -> str:
    return f"{_launchd_domain()}/{label}"


def _parse_launchd_print(text: str) -> dict:
    state = None
    pid = None
    path = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("state = "):
            state = stripped.split("=", 1)[1].strip()
        elif stripped.startswith("pid = "):
            raw = stripped.split("=", 1)[1].strip()
            if raw.isdigit():
                pid = int(raw)
        elif stripped.startswith("path = "):
            path = stripped.split("=", 1)[1].strip()
    return {"state": state, "pid": pid, "path": path}


def _launchd_inspect(label: str) -> dict | None:
    res = _run(["launchctl", "print", _launchd_target(label)], check=False)
    if res.returncode != 0:
        return None
    parsed = _parse_launchd_print(res.stdout)
    if parsed["state"] is None and parsed["pid"] is None:
        return None
    return parsed


def _lifecycle_inspect(account: str, label: str, roots: dict, *,
                       require_positive: bool = False) -> dict | None:
    """Enrolled lifecycle owners require positive identity or exact absence.

    Preserve generic C2 Business lifecycle inspection semantics; its dedicated
    Paper cutover explicitly opts into stricter absence proof.
    """
    if (account not in (C2_PAPER_ACCOUNT, C4_PAPER_ACCOUNT)
            and account not in _NATIVE_POOL_PIN_TAILNET_CANONICAL
            and account not in FABRIC_BACKEND_ACCOUNTS and not require_positive):
        return _launchd_inspect(label)
    subject = "Fabric" if account in FABRIC_BACKEND_ACCOUNTS else "C2"
    target = _launchd_target(label)
    absent = (f'Bad request.\nCould not find service "{label}" '
              f'in domain for user gui: {os.getuid()}\n')
    try:
        result = _run(["launchctl", "print", target], check=False)
    except Exception as exc:
        raise SystemExit(f"{subject} launchctl state is indeterminate; refusing lifecycle effect") from exc
    if result.returncode == 113 and result.stdout == "" and result.stderr == absent:
        return None
    lines = result.stdout.splitlines()
    # launchctl indents target fields by one tab; nested coalition states use
    # additional tabs and must not replace the service's own state or identity.
    fields = {key: [line for line in lines[1:-1] if line.startswith(f"\t{key} = ")]
              for key in ("path", "state", "pid")}
    parsed = _parse_launchd_print("\n".join(line for values in fields.values() for line in values))
    if (result.returncode != 0 or result.stderr != ""
            or not lines or lines[0] != f"{target} = {{" or lines[-1] != "}"
            or len(fields["path"]) != 1 or len(fields["state"]) != 1 or len(fields["pid"]) > 1
            or parsed["path"] != str(roots["plist"])
            or parsed["state"] not in ("running", "waiting")
            or (fields["pid"] and (not isinstance(parsed["pid"], int) or parsed["pid"] <= 0))
            or (parsed["state"] == "running" and parsed["pid"] is None)):
        raise SystemExit(f"{subject} launchctl state is indeterminate; refusing lifecycle effect")
    return parsed


def _info_is_running(info: dict) -> bool:
    pid = info.get("pid")
    if isinstance(pid, int) and pid > 0:
        return True
    return info.get("state") == "running"


def _expected_argv(
    node_abs: Path,
    gateway_path: Path,
    config_path: Path,
) -> list[str]:
    return [str(node_abs), str(gateway_path), str(config_path)]


def _stage_dest_files(roots: dict) -> list[Path]:
    return [
        *(roots["base"] / name for name in STAGE_FILES),
        roots["config"],
        roots["manifest"],
        roots["plist"],
    ]


def _assert_first_install_clean(roots: dict) -> None:
    for path in _stage_dest_files(roots):
        if path.exists() or path.is_symlink():
            raise SystemExit(f"refusing overwrite of unmanifested destination: {path}")


def _verify_prior_install(
    prior: dict,
    source: Path,
    node_abs: Path,
    backend_abs: Path,
    account: str,
    label: str,
    host: str,
    port: int,
    roots: dict,
) -> None:
    if (
        prior.get("source") != str(source)
        or prior.get("node") != str(node_abs)
        or prior.get("backend") != str(backend_abs)
        or prior.get("account") != account
        or prior.get("label") != label
        or prior.get("host") != host
        or prior.get("port") != port
    ):
        raise SystemExit(
            "refusing restage: existing manifest diverges; "
            "stop the service first and pass the exact same "
            "--account, --source, --node, --backend, --port"
        )
    if prior.get("version") == MANIFEST_VERSION:
        if _stable_regular_file_hash(node_abs, label="node") != prior.get("nodeHash"):
            raise SystemExit("refusing restage: node hash diverges")
        if _stable_regular_file_hash(backend_abs, label="backend") != prior.get("backendHash"):
            raise SystemExit("refusing restage: backend hash diverges")
        sealed_dependencies = prior.get("dependencyTreeHash")
        if sealed_dependencies is not None:
            if _dependency_tree_hash(roots["node_modules"]) != sealed_dependencies:
                raise SystemExit("refusing restage: dependency tree hash diverges")
    incoming = {src.name: _sha256_file(src) for src in _check_source_files(source)}
    prior_names = tuple(prior["files"].keys())
    installed = _installed_file_hashes(roots["base"], prior_names)
    if installed != prior.get("files"):
        raise SystemExit(
            "refusing restage: existing file hashes diverge; "
            "stop the service first and pass the exact same --source"
        )
    if incoming != installed:
        raise SystemExit(
            "refusing restage: incoming source hashes diverge; "
            "stop the service first and pass the exact same --source"
        )
    if roots["config"].is_symlink() or not roots["config"].is_file():
        raise SystemExit(
            "refusing restage: existing config missing; stop the service first"
        )
    if _sha256_file(roots["config"]) != prior.get("configHash"):
        raise SystemExit(
            "refusing restage: existing config hash diverges; "
            "stop the service first"
        )
    if roots["plist"].is_symlink() or not roots["plist"].is_file():
        raise SystemExit(
            "refusing restage: existing plist missing; stop the service first"
        )
    if _sha256_file(roots["plist"]) != prior.get("plistHash"):
        raise SystemExit(
            "refusing restage: existing plist hash diverges; "
            "stop the service first"
        )
    plist = _load_plist(roots["plist"])
    if plist is None or plist.get("Label") != label:
        raise SystemExit(
            "refusing restage: existing plist diverges; "
            "stop the service first"
        )
    argv = list(plist.get("ProgramArguments") or [])
    expected = _expected_argv(node_abs, roots["gateway"], roots["config"])
    if argv != expected:
        raise SystemExit(
            "refusing restage: existing argv diverges; "
            "stop the service first"
        )


def _preflight_stage(
    source: Path,
    node_abs: Path,
    backend_abs: Path,
    account: str,
    label: str,
    host: str,
    port: int,
    roots: dict,
) -> None:
    _check_source_files(source)
    _assert_no_symlink_ancestors(roots["base"])
    _assert_no_symlink_ancestors(roots["plist"])
    manifest_path = roots["manifest"]
    prior = _read_manifest(manifest_path, account, label)
    if prior is not None:
        _verify_prior_install(
            prior, source, node_abs, backend_abs,
            account, label, host, port, roots,
        )
    else:
        _assert_first_install_clean(roots)
    info = _launchd_inspect(label)
    if info is not None:
        raise SystemExit(
            "refusing restage while service is running; stop first"
        )
    for path in _stage_dest_files(roots):
        _assert_dest_safe(path)
    return prior


def _validate_port(port: int) -> None:
    if port == RESERVED_FUNNEL_PORT:
        raise SystemExit(
            f"--port must not be {RESERVED_FUNNEL_PORT}: "
            "reserved for the public OAuth/Funnel service"
        )
    if not (1024 <= port <= 65535):
        raise SystemExit("--port must be between 1024 and 65535")


@_pin_install_serialized
def _write_install(
    source: Path,
    node_abs: Path,
    backend_abs: Path,
    account: str,
    label: str,
    host: str,
    port: int,
    roots: dict,
    *,
    result_key: str,
    previous_source: str | None = None,
    dependency_tree_hash: str | None = None,
    repository_workspaces: bool = False,
    commission_digest: str | None = None,
    fabric_only: bool = False,
    modern_fabric: bool = False,
) -> int:
    user_root = _user_root()
    _ensure_secure_dir(roots["base"])
    _ensure_secure_dir(roots["state"])
    _ensure_secure_dir(roots["logs"])

    files: dict[str, str] = {}
    for src in _check_source_files(source):
        dst = roots["base"] / src.name
        _copy_secure(src, dst)
        files[src.name] = _sha256_file(dst)

    _atomic_write_text(
        roots["config"],
        json.dumps(
            _build_config(
                account,
                host,
                port,
                node_abs,
                backend_abs,
                roots["state"],
                user_root,
                repository_workspaces=repository_workspaces,
                commission_digest=commission_digest,
                fabric_only=fabric_only,
                modern_fabric=modern_fabric,
            ),
            indent=2,
            sort_keys=True,
        ),
    )
    plist = _build_plist(
        node_abs, roots["gateway"], roots["config"], user_root, label
    )
    _write_plist(roots["plist"], plist)

    manifest = {
        "version": MANIFEST_VERSION,
        "account": account,
        "label": label,
        "files": files,
        "source": str(source),
        "node": str(node_abs),
        "backend": str(backend_abs),
        "nodeHash": _stable_regular_file_hash(node_abs, label="node"),
        "backendHash": _stable_regular_file_hash(backend_abs, label="backend"),
        "dependencyTreeHash": dependency_tree_hash,
        "host": host,
        "port": port,
        "configHash": _sha256_file(roots["config"]),
        "plistHash": _sha256_file(roots["plist"]),
    }
    _atomic_write_text(
        roots["manifest"],
        json.dumps(manifest, indent=2, sort_keys=True),
    )

    result = {
        result_key: True,
        "account": account,
        "label": label,
        "runtime": str(roots["base"]),
        "plist": str(roots["plist"]),
        "manifest": str(roots["manifest"]),
        "gateway": str(roots["gateway"]),
        "port": port,
        "source": str(source),
    }
    if previous_source is not None:
        result["previousSource"] = previous_source
    print(json.dumps(result))
    return 0




def _repository_workspace_setting(args, roots: dict, prior: dict | None) -> bool:
    """Preserve the manifest-verified setting; only explicit opt-in can enable it."""
    requested = getattr(args, "enable_repository_workspaces", False)
    if type(requested) is not bool:
        raise SystemExit("invalid repository workspace setting")
    previous = False
    if prior is not None:
        config_path = roots["config"]
        if _sha256_file(config_path) != prior.get("configHash"):
            raise SystemExit("repository workspace config changed during preflight")
        value = json.loads(config_path.read_text(encoding="utf-8")).get("repositoryWorkspaces")
        if value is not None:
            if (type(value) is not dict or value.get("enabled") is not True
                    or value != {"enabled": True, "allowedRepositories": ["mastermind", "macro", "terminal"]}):
                raise SystemExit("existing repository workspace setting is not the installed closed profile")
            previous = True
    return requested or previous


def _fabric_profile_setting(args, roots: dict, prior: dict | None) -> bool:
    """Retain the manifest-verified restricted profile; never repurpose Studio."""
    requested = getattr(args, "fabric_only", False)
    if type(requested) is not bool:
        raise SystemExit("invalid Fabric profile setting")
    previous = False
    if prior is not None:
        if _sha256_file(roots["config"]) != prior.get("configHash"):
            raise SystemExit("Fabric profile changed during preflight")
        config = json.loads(roots["config"].read_text(encoding="utf-8"))
        if "fabricOnly" in config:
            if (config["fabricOnly"] is not True or config.get("gitPublish") is not False
                    or config.get("paperDesign") is not False
                    or "repositoryWorkspaces" in config or "commissionPublication" in config):
                raise SystemExit("invalid retained Fabric-only profile")
            previous = True
        if requested and not previous:
            raise SystemExit("create a separate Fabric installation; do not repurpose Studio")
    enabled = requested or previous
    if enabled and (getattr(args, "enable_repository_workspaces", False)
                    or getattr(args, "os_commission_config_sha256", None) is not None):
        raise SystemExit("Fabric-only profile cannot enable unrelated capabilities")
    return enabled


def _modern_fabric_setting(args, roots: dict, prior: dict | None, fabric_only: bool) -> bool:
    """Explicit opt-in or verified retention in the same restricted installation."""
    requested = getattr(args, "modern_fabric_protocol", None)
    if requested is not None and type(requested) is not bool:
        raise SystemExit("invalid modern Fabric protocol setting")
    previous = False
    if prior is not None:
        if _sha256_file(roots["config"]) != prior.get("configHash"):
            raise SystemExit("modern Fabric configuration changed during preflight")
        config = json.loads(roots["config"].read_text(encoding="utf-8"))
        value = config.get("modernFabricProtocol", False)
        if type(value) is not bool:
            raise SystemExit("invalid retained modern Fabric protocol setting")
        if value:
            if (not fabric_only or config.get("fabricOnly") is not True
                    or config.get("backendMode") != "shared-account"
                    or config.get("host") != "127.0.0.1"
                    or config.get("gitPublish") is not False
                    or config.get("paperDesign") is not False
                    or any(key in config for key in ("repositoryWorkspaces", "commissionPublication", "fleetStatus", "publicUrl"))):
                raise SystemExit("invalid retained modern Fabric-only profile")
            previous = True
    enabled = previous if requested is None else requested
    if enabled and not fabric_only:
        raise SystemExit("modern protocol requires the existing Fabric-only profile")
    return enabled


OS_COMMISSION_CONFIG = Path("/Library/Application Support/MastermindExecutive/config/os-commission-publication.json")


def _commission_setting(args, roots: dict, prior: dict | None) -> str | None:
    """Preserve only verified opt-in; never accept a caller-selected config path."""
    requested = getattr(args, "os_commission_config_sha256", None)
    if requested is not None and (type(requested) is not str or not re.fullmatch(r"[0-9a-f]{64}", requested)):
        raise SystemExit("invalid commission configuration digest")
    previous = None
    if prior is not None:
        if _sha256_file(roots["config"]) != prior.get("configHash"):
            raise SystemExit("commission configuration changed during preflight")
        value = json.loads(roots["config"].read_text(encoding="utf-8")).get("commissionPublication")
        if value is not None:
            if (type(value) is not dict or set(value) != {"enabled", "configurationDigest"}
                    or value["enabled"] is not True or type(value["configurationDigest"]) is not str
                    or not re.fullmatch(r"[0-9a-f]{64}", value["configurationDigest"])):
                raise SystemExit("existing commission publication profile is invalid")
            previous = value["configurationDigest"]
    digest = requested or previous
    if digest is None:
        return None
    if (os.getuid() != os.geteuid() or not _repository_workspace_setting(args, roots, prior)
            or args.port == 8443):
        raise SystemExit("commission publication requires private repository workspace profile")
    current = OS_COMMISSION_CONFIG
    first = True
    while True:
        info = current.lstat()
        if (info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode)
                or (first and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1))
                or (not first and not stat.S_ISDIR(info.st_mode))):
            raise SystemExit("commission configuration is not root sealed")
        if current == current.parent:
            break
        current, first = current.parent, False
    raw = OS_COMMISSION_CONFIG.read_bytes()
    if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != digest:
        raise SystemExit("commission configuration digest changed")
    value = json.loads(raw)
    keys = {"schema", "release_sha", "studio_uid", "studio_account", "studio_port",
            "policy", "grants", "base_sha", "audit_directory", "auth_helper_sha256", "file_helper_sha256"}
    if (type(value) is not dict or set(value) != keys
            or value["schema"] != "mastermind.os_commission_publication.v1"
            or type(value["studio_uid"]) is not int or value["studio_uid"] != os.getuid()
            or value["studio_account"] != args.account or type(value["studio_port"]) is not int
            or value["studio_port"] != args.port):
        raise SystemExit("commission configuration does not match this installed Studio owner")
    return digest


@_fabric_lifecycle_serialized()
def cmd_stage(args) -> int:
    account = args.account
    _pin_reject_generic_restage(account)
    _validate_account_label(account)
    label = f"com.mastermind.studio-direct-private.{account}"
    host = "127.0.0.1"

    if not os.path.isabs(args.source):
        raise SystemExit("--source must be absolute")
    source = Path(args.source)
    if source.is_symlink() or not source.is_dir():
        raise SystemExit(f"source dir invalid: {source}")
    node_abs = _resolve_abs("--node", args.node)
    backend_abs = _resolve_abs("--backend", args.backend)
    port = int(args.port)
    _validate_port(port)

    roots = _build_runtime_roots(account)
    prior = _preflight_stage(
        source, node_abs, backend_abs, account, label, host, port, roots
    )
    fabric_only = _fabric_profile_setting(args, roots, prior)
    # Paper remains mandatory only for a profile that actually exposes Paper.
    if not fabric_only:
        _verify_paper_runtime(_user_root())
    retained_dependency_hash = (
        prior.get("dependencyTreeHash")
        if isinstance(prior, dict) and prior.get("version") == MANIFEST_VERSION
        else None
    )

    return _write_install(
        source, node_abs, backend_abs, account, label, host, port, roots,
        result_key="staged",
        dependency_tree_hash=retained_dependency_hash,
        repository_workspaces=_repository_workspace_setting(args, roots, prior),
        commission_digest=_commission_setting(args, roots, prior),
        fabric_only=fabric_only,
        modern_fabric=_modern_fabric_setting(args, roots, prior, fabric_only),
    )

def _verify_staged_install(
    account: str,
    label: str,
    roots: dict,
    *,
    require_runtime_seal: bool = True,
) -> dict:
    manifest_path = roots["manifest"]
    manifest = _read_manifest(manifest_path, account, label, required=True)

    for name, expected_hash in manifest["files"].items():
        path = roots["base"] / name
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"not staged: {name} missing")
        if _sha256_file(path) != expected_hash:
            raise SystemExit(f"not staged: {name} hash mismatch")

    deps = roots["node_modules"]
    if deps.is_symlink() or not deps.is_dir():
        raise SystemExit(
            "not staged: node_modules missing; "
            "parent must run npm ci --omit=dev --ignore-scripts"
        )

    if roots["config"].is_symlink() or not roots["config"].is_file():
        raise SystemExit("not staged: config missing")
    stored_config_hash = manifest.get("configHash")
    if stored_config_hash is None:
        raise SystemExit("not staged: config hash missing from manifest")
    if _sha256_file(roots["config"]) != stored_config_hash:
        raise SystemExit("not staged: config hash mismatch")

    if roots["plist"].is_symlink() or not roots["plist"].is_file():
        raise SystemExit("not staged: plist missing")
    stored_plist_hash = manifest.get("plistHash")
    if stored_plist_hash is None:
        raise SystemExit("not staged: plist hash missing from manifest")
    if _sha256_file(roots["plist"]) != stored_plist_hash:
        raise SystemExit("not staged: plist hash mismatch")

    node = Path(manifest["node"])
    backend = Path(manifest["backend"])
    if node.is_symlink() or not node.is_file():
        raise SystemExit("not staged: node missing")
    if backend.is_symlink() or not backend.is_file():
        raise SystemExit("not staged: backend missing")
    if require_runtime_seal:
        if manifest.get("version") != MANIFEST_VERSION:
            raise SystemExit("not staged: legacy manifest must be upgraded and runtime sealed")
        if _stable_regular_file_hash(node, label="node") != manifest.get("nodeHash"):
            raise SystemExit("not staged: node hash mismatch")
        if _stable_regular_file_hash(backend, label="backend") != manifest.get("backendHash"):
            raise SystemExit("not staged: backend hash mismatch")
        sealed_dependencies = manifest.get("dependencyTreeHash")
        if sealed_dependencies is None:
            raise SystemExit("not staged: runtime dependencies are not sealed")
        if _dependency_tree_hash(deps) != sealed_dependencies:
            raise SystemExit("not staged: dependency tree hash mismatch")

    plist = _load_plist(roots["plist"])
    if plist is None:
        raise SystemExit("not staged: plist missing")
    if plist.get("Label") != label:
        raise SystemExit("plist is not our exact install")

    expected_argv = _expected_argv(node, roots["gateway"], roots["config"])
    if list(plist.get("ProgramArguments") or []) != expected_argv:
        raise SystemExit("plist is not our exact install")
    if Path(expected_argv[1]).name != PRIVATE_GATEWAY_NAME:
        raise SystemExit("plist is not our exact install")

    return manifest


def _native_pin_manifest_valid(data, account: str, label: str) -> bool:
    """Keep the private profile rules and close the two Tailnet state sets."""
    if not _valid_manifest(data, account, label):
        return False
    if account not in _NATIVE_POOL_PIN_TAILNET_CANONICAL:
        return True
    return (data["files"] == NATIVE_POOL_PIN_PREDECESSORS[account]
            and _canonical_json_sha256(data)
            in _NATIVE_POOL_PIN_TAILNET_CANONICAL[account])


def _verify_native_pin_tailnet_install(account: str, label: str, roots: dict) -> dict:
    """Read the complete existing seal for one exact preserved Tailnet seat.

    The private verifier remains private-only. No argument, path or caller
    selector can opt an arbitrary profile into this transport. Even stop/seal
    callers must retain the complete reviewed runtime seal for these states.
    """
    manifest = _pin_owner_module().decode(_fabric_release_bytes(roots["manifest"]))
    if (account not in _NATIVE_POOL_PIN_TAILNET_CANONICAL
            or not _native_pin_manifest_valid(manifest, account, label)):
        raise SystemExit("not staged: preserved Tailnet profile differs")
    for name, expected_hash in manifest["files"].items():
        if hashlib.sha256(_fabric_release_bytes(roots["base"] / name)).hexdigest() != expected_hash:
            raise SystemExit("not staged: preserved Tailnet module differs")
    if hashlib.sha256(_fabric_release_bytes(roots["config"])).hexdigest() != manifest["configHash"]:
        raise SystemExit("not staged: preserved Tailnet config differs")
    plist_raw = _fabric_release_bytes(roots["plist"])
    if hashlib.sha256(plist_raw).hexdigest() != manifest["plistHash"]:
        raise SystemExit("not staged: preserved Tailnet plist differs")
    node, backend = Path(manifest["node"]), Path(manifest["backend"])
    if (_stable_regular_file_hash(node, label="Tailnet node") != manifest["nodeHash"]
            or _stable_regular_file_hash(backend, label="Tailnet backend") != manifest["backendHash"]
            or manifest["dependencyTreeHash"] is None
            or _dependency_tree_hash(roots["node_modules"]) != manifest["dependencyTreeHash"]):
        raise SystemExit("not staged: preserved Tailnet runtime differs")
    plist = plistlib.loads(plist_raw)
    gateway = roots["base"] / "tailnet-gateway.mjs"
    expected_argv = _expected_argv(node, gateway, roots["config"])
    if (not isinstance(plist, dict) or plist.get("Label") != label
            or list(plist.get("ProgramArguments") or []) != expected_argv):
        raise SystemExit("plist is not the exact preserved Tailnet install")
    return manifest


def _verify_native_pin_install(account: str, label: str, roots: dict, *,
                               require_runtime_seal: bool = True) -> dict:
    """Select only the two closed Tailnet owners; preserve private admission."""
    if account in _NATIVE_POOL_PIN_TAILNET_CANONICAL:
        return _verify_native_pin_tailnet_install(account, label, roots)
    if require_runtime_seal:
        return _verify_staged_install(account, label, roots)
    return _verify_staged_install(account, label, roots, require_runtime_seal=False)



def _verify_upgrade_preserves_installed_fleet_capabilities(
    prior: dict, roots: dict, projected: dict,
) -> None:
    """Fail closed before any writes when an enrolled v0.1.10 fleet seat would lose service.

    This is an explicit migration guard, NOT permission to broaden historical
    filesets or treat an approved old manifest as permission to downgrade it.
    A separately reviewed compatibility source must retain both fleet modules
    and every configured fleet route, scheduling cap and fleet-status binding.
    """
    if frozenset(prior["files"]) not in (
        V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR,
        frozenset(C2_PAPER_FILES_SHA256),
        V2_C2_BUSINESS_FLEET_PREDECESSOR,
    ):
        return
    required = frozenset(("fleet-routing.mjs", "tailnet-gateway.mjs"))
    if not required.issubset(STAGE_FILES):
        raise SystemExit(
            "refusing upgrade: installed fleet/tailnet capability modules absent "
            "from target release; reviewed compatibility migration required"
        )
    config_path = roots["config"]
    if config_path.is_symlink() or not config_path.is_file():
        raise SystemExit("refusing upgrade: existing fleet config unavailable")
    before_hash = _stable_regular_file_hash(config_path, label="existing config")
    if before_hash != prior["configHash"]:
        raise SystemExit("refusing upgrade: existing fleet config hash changed")
    try:
        existing = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("refusing upgrade: existing fleet config invalid") from exc
    if (_stable_regular_file_hash(config_path, label="existing config") != before_hash
            or not isinstance(existing, dict)):
        raise SystemExit("refusing upgrade: existing fleet config changed")
    routes = existing.get("fleetRouting")
    if (not isinstance(routes, dict) or routes.get("enabled") is not True
            or not isinstance(routes.get("routes"), list)
            or len(routes["routes"]) < 1):
        raise SystemExit("refusing upgrade: historical fleet routes unverified")
    for key in (
        "fleetRouting", "maxPerSessionConcurrency", "maxQueuedPerSession",
        "fleetStatus",
    ):
        if existing.get(key) != projected.get(key):
            raise SystemExit(
                f"refusing upgrade: fleet capability {key} would change; "
                "reviewed compatibility migration required"
            )


def _upgrade_fleet_v10_publisher_only(
    args, source: Path, node_abs: Path, backend_abs: Path,
    account: str, label: str, port: int, roots: dict,
) -> int:
    """Replace only the two reviewed publisher modules on the sealed fleet 0.1.10.

    The canonical private_service installer owns this transaction. Never
    replace a live gateway with protected-master's different runtime bundle.
    The administrator supplies the exact observed manifest digest (CAS).
    """
    expected = getattr(args, "publisher_expected_manifest_sha256", None)
    preview = getattr(args, "publisher_preflight_only", False)
    if (account not in FLEET_V10_ENROLLED_ACCOUNTS or type(preview) is not bool
            or not _sha256_hex(expected)
            or getattr(args, "fabric_only", False)
            or getattr(args, "enable_repository_workspaces", False)
            or getattr(args, "os_commission_config_sha256", None)):
        raise SystemExit("fleet publisher compatibility requires an existing enrolled fleet owner and exact manifest CAS")
    path = roots["manifest"]
    if _stable_regular_file_hash(path, label="installed manifest") != expected:
        raise SystemExit("fleet publisher compatibility: installed manifest CAS mismatch")
    prior = _verify_staged_install(account, label, roots, require_runtime_seal=True)
    if (prior.get("version") != MANIFEST_VERSION
            or frozenset(prior["files"]) != V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR
            or not prior.get("dependencyTreeHash")
            or prior.get("node") != str(node_abs)
            or prior.get("backend") != str(backend_abs)
            or prior.get("host") != "127.0.0.1"
            or prior.get("port") != port):
        raise SystemExit("fleet publisher compatibility: original sealed identity does not match")
    for name, expected_blob in FLEET_V10_PRESERVED_GIT_BLOBS.items():
        candidate = roots["base"] / name
        _assert_dest_safe(candidate)
        data = candidate.read_bytes()
        actual = hashlib.sha1(
            b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        ).hexdigest()
        if actual != expected_blob:
            raise SystemExit("fleet publisher compatibility: preserved fleet generation changed")
    config_path = roots["config"]
    manifest_path = roots["manifest"]
    for candidate in (config_path, manifest_path):
        _assert_dest_safe(candidate)
    old_config_bytes = config_path.read_bytes()
    old_manifest_bytes = manifest_path.read_bytes()
    if (hashlib.sha256(old_config_bytes).hexdigest() != prior["configHash"]
            or hashlib.sha256(old_manifest_bytes).hexdigest() != expected):
        raise SystemExit("fleet publisher compatibility: verified snapshot changed during preflight")
    try:
        old_config = json.loads(old_config_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("fleet publisher compatibility: original config invalid") from exc
    user_root = _user_root()
    if (type(old_config) is not dict
            or old_config.get("repositoryWorkspaces") != {
                "enabled": True, "allowedRepositories": ["mastermind", "macro", "terminal"]}
            or old_config.get("fleetRouting", {}).get("enabled") is not True
            or len(old_config["fleetRouting"].get("routes", [])) != 2
            or old_config.get("maxPerSessionConcurrency") != 8
            or old_config.get("maxQueuedPerSession") != 16
            or type(old_config.get("fleetStatus")) is not dict
            or old_config.get("fabricOnly") is True
            or "commissionPublication" in old_config
            or "modernFabricProtocol" in old_config):
        raise SystemExit("fleet publisher compatibility: original scoped capabilities changed")
    # Preserve the historical legacy/index-sync transitions. The merge update
    # admits only its exact observed module pair under the existing closed
    # profile. The sealed manifest, not the caller, chooses the transition.
    original_publisher = old_config.get("gitPublish")
    expected_closed = _typed_git_config(user_root, closed_repositories=True)
    patch_hashes = FLEET_V10_PUBLISHER_PATCH_SHA256
    preserve_config_bytes = False
    if (original_publisher == expected_closed and all(
            prior["files"].get(name) == digest
            for name, digest in FLEET_V10_MERGE_PUBLISHER_PREDECESSOR_SHA256.items())):
        patch_hashes = FLEET_V10_MERGE_PUBLISHER_PATCH_SHA256
        preserve_config_bytes = True
    elif original_publisher == _typed_git_config(user_root):
        pass  # existing legacy-to-closed upgrade
    elif (original_publisher == expected_closed
            and prior["files"].get("git-publish.mjs") ==
                FLEET_V10_PREVIOUS_CLOSED_PUBLISHER_SHA256
            and prior["files"].get("workspace-access.mjs") ==
                FLEET_V10_PUBLISHER_PATCH_SHA256["workspace-access.mjs"]):
        pass  # exact reviewed closed-to-closed module update
    else:
        raise SystemExit("fleet publisher compatibility: unrecognized prior publisher identity")
    new_config = dict(old_config)
    new_config["gitPublish"] = expected_closed
    if ({k: v for k, v in new_config.items() if k != "gitPublish"}
            != {k: v for k, v in old_config.items() if k != "gitPublish"}):
        raise SystemExit("fleet publisher compatibility: unrelated config change")
    config_bytes = (old_config_bytes if preserve_config_bytes else
                    json.dumps(new_config, indent=2, sort_keys=True).encode("utf-8"))
    names = tuple(patch_hashes)
    old_files = {}
    new_files = {}
    for name in names:
        installed = roots["base"] / name
        incoming = source / name
        _assert_dest_safe(installed)
        if incoming.is_symlink() or not incoming.is_file():
            raise SystemExit("fleet publisher compatibility: source module unavailable")
        original = installed.read_bytes()
        modified = incoming.read_bytes()
        if (hashlib.sha256(original).hexdigest() != prior["files"][name]
                or hashlib.sha256(modified).hexdigest() != patch_hashes[name]):
            raise SystemExit("fleet publisher compatibility: source or installed module hash mismatch")
        old_files[name] = original
        new_files[name] = modified
    future = dict(prior)
    future["files"] = dict(prior["files"])
    for name in names:
        future["files"][name] = hashlib.sha256(new_files[name]).hexdigest()
    future["configHash"] = hashlib.sha256(config_bytes).hexdigest()
    if not _valid_manifest(future, account, label):
        raise SystemExit("fleet publisher compatibility: prospective manifest invalid")
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("fleet publisher compatibility: installed state changed during planning")
    if preview:
        print(json.dumps({
            "preflight": True, "effect": "NOT_APPLIED", "account": account,
            "originalManifestSha256": expected,
            "publisherModules": list(names),
            "fleetRoutesPreserved": len(old_config["fleetRouting"]["routes"]),
            "concurrencyPreserved": [8, 16],
            "existingBundleRetained": True,
        }, sort_keys=True))
        return 0
    if _launchd_inspect(label) is not None:
        raise SystemExit("refusing fleet publisher upgrade while service is loaded; stop first")
    # Reconfirm all observed bytes immediately before the first effect.
    if (_stable_regular_file_hash(manifest_path, label="installed manifest") != expected
            or _stable_regular_file_hash(config_path, label="installed config") != prior["configHash"]
            or any(_sha256_file(roots["base"] / n) != prior["files"][n] for n in names)):
        raise SystemExit("fleet publisher compatibility: original installation changed")
    # All new source was hash-pinned before entry. Manifest is written LAST:
    # interrupted installation fails the existing manifest/hash gate closed.
    old_bytes = {**{roots["base"] / n: old_files[n] for n in names},
                 config_path: old_config_bytes, manifest_path: old_manifest_bytes}
    planned = {**{roots["base"] / n: new_files[n] for n in names},
               config_path: config_bytes,
               manifest_path: json.dumps(future, indent=2, sort_keys=True).encode("utf-8")}
    committed = False
    try:
        for target, payload in planned.items():
            _atomic_write_bytes(target, payload)
        committed = True
        _verify_staged_install(account, label, roots, require_runtime_seal=True)
    except BaseException as exc:
        if committed:
            raise SystemExit(
                "fleet publisher compatibility: EFFECT_UNKNOWN after manifest commit; "
                "inspect original service before attempting recovery"
            ) from exc
        try:
            # os.replace may have succeeded even when a later fsync failed.
            # Thus a return-code ledger cannot prove which files changed.
            # Reconcile *every* planned path by bytes before safe rollback.
            if _launchd_inspect(label) is not None:
                raise RuntimeError("service became loaded during transaction")
            observed = {target: target.read_bytes() for target in planned}
            if any(observed[t] not in (old_bytes[t], planned[t]) for t in planned):
                raise RuntimeError("non-owned concurrent mutation while recovering")
            for target in reversed(tuple(planned)):
                if observed[target] != old_bytes[target]:
                    _atomic_write_bytes(target, old_bytes[target])
            if (any(target.read_bytes() != old_bytes[target] for target in planned)
                    or _stable_regular_file_hash(manifest_path, label="installed manifest") != expected):
                raise RuntimeError("rollback byte identity differs")
            _verify_staged_install(
                account, label, roots, require_runtime_seal=True)
        except BaseException as rollback_exc:
            raise SystemExit(
                "fleet publisher compatibility: EFFECT_UNKNOWN during rollback; "
                "do not restart or replay until original state is reconciled"
            ) from rollback_exc
        raise SystemExit("fleet publisher compatibility: NOT_APPLIED; original state restored") from exc
    print(json.dumps({
        "publisherFleetCompatibility": True, "account": account, "effect": "APPLIED",
        "manifestSha256": _sha256_file(manifest_path),
        "gatewayAndFleetModulesPreserved": True,
        "repositoryWorkspacesPreserved": True,
        "serviceStarted": False,
    }, sort_keys=True))
    return 0


def _upgrade_c2_business_original_fleet_mastermind_only(
    args, source: Path, node_abs: Path, backend_abs: Path,
    account: str, label: str, port: int, roots: dict,
) -> int:
    """One original installer transaction: C2's exact 11-file -> 12-file source.

    Preserves every configured capability and original Mastermind-only Git
    boundary. No auto-enrollment of Macro/Terminal, no service restart, and no
    cross-seat copying of secrets/config. Source bytes are pinned independently
    of the supplied directory and must be reviewed before any live release.
    """
    expected = getattr(args, "publisher_expected_manifest_sha256", None)
    preview = getattr(args, "publisher_preflight_only", False)
    if (account not in ("chatgpt2-business", C2_PAPER_ACCOUNT) or type(preview) is not bool
            or not _sha256_hex(expected)
            or getattr(args, "enable_repository_workspaces", False) is True
            or getattr(args, "fabric_only", False) is True
            or type(getattr(args, "os_commission_config_sha256", None)) is str):
        raise SystemExit("C2 compatibility requires original Business owner, sealed manifest CAS and no new repository grants")
    personal = account == C2_PAPER_ACCOUNT
    if ((getattr(args, "c2_business_fleet_compat", False) is True)
            == (getattr(args, "c2_personal_closed_publisher", False) is True)):
        raise SystemExit("C2 compatibility: select one original owner operation")
    if personal != (getattr(args, "c2_personal_closed_publisher", False) is True):
        raise SystemExit("C2 compatibility: operation/account mismatch")
    target_patch = C2_PERSONAL_TARGET_PATCH_SHA256 if personal else C2_BUSINESS_TARGET_PATCH_SHA256
    manifest_path = roots["manifest"]
    config_path = roots["config"]
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("C2 compatibility: original manifest CAS mismatch")
    if personal and expected != C2_PERSONAL_CURRENT_MANIFEST_SHA256:
        raise SystemExit("C2 compatibility: Personal identity mismatch")
    prior = _verify_staged_install(
        account, label, roots, require_runtime_seal=True)
    if (prior.get("version") != MANIFEST_VERSION
            or frozenset(prior["files"]) != V2_C2_BUSINESS_FLEET_PREDECESSOR
            or not prior.get("dependencyTreeHash")
            or prior.get("node") != str(node_abs)
            or prior.get("backend") != str(backend_abs)
            or prior.get("host") != "127.0.0.1"
            or prior.get("port") != port):
        raise SystemExit("C2 compatibility: original sealed identity does not match")
    original_blobs = C2_PAPER_FILES_SHA256 if personal else C2_BUSINESS_V10_ORIGINAL_BLOBS
    for name, expected_blob in original_blobs.items():
        installed = roots["base"] / name
        _assert_dest_safe(installed)
        raw = installed.read_bytes()
        observed_blob = hashlib.sha1(
            b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
        ).hexdigest()
        if (hashlib.sha256(raw).hexdigest() if personal else observed_blob) != expected_blob:
            raise SystemExit("C2 compatibility: original generation changed")
    if frozenset(original_blobs) != V2_C2_BUSINESS_FLEET_PREDECESSOR:
        raise SystemExit("C2 compatibility: pinned predecessor incomplete")
    if (_stable_regular_file_hash(config_path, label="installed config")
            != prior["configHash"]):
        raise SystemExit("C2 compatibility: original config changed")
    old_config_bytes = config_path.read_bytes()
    try:
        old_config = json.loads(old_config_bytes)
    except (ValueError, UnicodeError) as exc:
        raise SystemExit("C2 compatibility: original config unreadable") from exc
    if (type(old_config) is not dict
            or "repositoryWorkspaces" in old_config
            or old_config.get("gitPublish") != _typed_git_config(_user_root())
            or old_config.get("fleetRouting", {}).get("enabled") is not True
            or len(old_config["fleetRouting"].get("routes", [])) != 2
            or old_config.get("maxPerSessionConcurrency") != 8
            or old_config.get("maxQueuedPerSession") != 16
            or type(old_config.get("fleetStatus")) is not dict
            or old_config.get("fabricOnly") is True
            or "commissionPublication" in old_config
            or "modernFabricProtocol" in old_config):
        raise SystemExit("C2 compatibility: original Mastermind-only capabilities changed")
    if (hashlib.sha256(old_config_bytes).hexdigest() != prior["configHash"]
            or _stable_regular_file_hash(manifest_path, label="installed manifest") != expected):
        raise SystemExit("C2 compatibility: original snapshot changed")
    if frozenset(target_patch) != frozenset((
            "gateway.mjs", "git-publish.mjs", "workspace-access.mjs")):
        raise SystemExit("C2 compatibility: proposed patch scope invalid")
    old_modules: dict[str, bytes | None] = {}
    new_modules: dict[str, bytes] = {}
    for name, digest in target_patch.items():
        installed = roots["base"] / name
        staged = source / name
        _assert_dest_safe(installed)
        if staged.is_symlink() or not staged.is_file():
            raise SystemExit("C2 compatibility: reviewed source module missing")
        data = staged.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise SystemExit("C2 compatibility: reviewed source hash mismatch")
        if name in prior["files"]:
            original = installed.read_bytes()
            if hashlib.sha256(original).hexdigest() != prior["files"][name]:
                raise SystemExit("C2 compatibility: installed module hash mismatch")
            old_modules[name] = original
        else:
            if installed.exists() or installed.is_symlink():
                raise SystemExit("C2 compatibility: new module already exists")
            old_modules[name] = None
        new_modules[name] = data
    new_config = dict(old_config)
    if personal:
        new_config["gitPublish"] = _typed_git_config(_user_root(), closed_repositories=True)
        new_config["repositoryWorkspaces"] = {"enabled": True, "allowedRepositories": ["mastermind", "macro", "terminal"]}
    future = dict(prior)
    future["files"] = dict(prior["files"])
    for name, data in new_modules.items():
        future["files"][name] = hashlib.sha256(data).hexdigest()
    if personal:
        future["configHash"] = hashlib.sha256(json.dumps(new_config, indent=2, sort_keys=True).encode()).hexdigest()
    if (frozenset(future["files"]) != V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR
            or not _valid_manifest(future, account, label)):
        raise SystemExit("C2 compatibility: proposed 12-file sealed manifest refused")
    new_manifest_bytes = json.dumps(
        future, indent=2, sort_keys=True).encode("utf-8")
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("C2 compatibility: original manifest changed during preflight")
    if preview:
        print(json.dumps({
            "preflight": True, "effect": "NOT_APPLIED",
            "account": account, "originalManifestSha256": expected,
            "changedModules": sorted(new_modules),
            "noNewRepositoryGrants": not personal, "closedRepositoriesEnabled": personal,
            "fleetRoutesPreserved": 2,
            "concurrencyPreserved": [8, 16],
            "serviceStarted": False,
        }, sort_keys=True))
        return 0
    if _launchd_inspect(label) is not None:
        raise SystemExit("refusing C2 compatibility upgrade while service is loaded; stop first")
    if (_stable_regular_file_hash(manifest_path, label="installed manifest") != expected
            or _stable_regular_file_hash(config_path, label="installed config") != prior["configHash"]
            or any(_sha256_file(roots["base"] / n) != prior["files"][n]
                   for n in prior["files"])
            or (roots["base"] / "workspace-access.mjs").exists()):
        raise SystemExit("C2 compatibility: previous installation changed before write")
    before = {roots["base"] / n: old_modules[n] for n in new_modules}
    if personal:
        before[config_path] = old_config_bytes
    before[manifest_path] = manifest_path.read_bytes()
    planned = {roots["base"] / n: new_modules[n] for n in new_modules}
    if personal:
        planned[config_path] = json.dumps(new_config, indent=2, sort_keys=True).encode()
    planned[manifest_path] = new_manifest_bytes
    committed = False
    try:
        for target, payload in planned.items():
            # A file which was previously absent must still be absent immediately
            # before the attempted create. Unexpected new files never get clobbered.
            if before[target] is None and (target.exists() or target.is_symlink()):
                raise RuntimeError("unexpected third-party new module")
            _atomic_write_bytes(target, payload)
        committed = True
        _verify_staged_install(
            account, label, roots, require_runtime_seal=True)
    except BaseException as exc:
        if committed:
            raise SystemExit(
                "C2 compatibility: EFFECT_UNKNOWN after manifest commit; "
                "inspect original installed state before recovery"
            ) from exc
        try:
            if _launchd_inspect(label) is not None:
                raise RuntimeError("service became loaded during compatibility transaction")
            observed = {}
            for target, new_bytes in planned.items():
                if target.is_symlink():
                    raise RuntimeError("unexpected symlink during recovery")
                observed[target] = target.read_bytes() if target.exists() else None
                if observed[target] not in (before[target], new_bytes):
                    raise RuntimeError("concurrent out-of-scope file mutation")
            for target in reversed(tuple(planned)):
                if observed[target] == before[target]:
                    continue
                if before[target] is None:
                    # This pathname was absent before our transaction.
                    target.unlink()
                    parent_fd = os.open(target.parent, os.O_RDONLY)
                    try:
                        os.fsync(parent_fd)
                    finally:
                        os.close(parent_fd)
                else:
                    _atomic_write_bytes(target, before[target])
            if (any((t.read_bytes() if t.exists() else None) != before[t]
                    for t in planned)
                    or _stable_regular_file_hash(manifest_path, label="installed manifest") != expected):
                raise RuntimeError("original installation could not be restored")
            _verify_staged_install(
                account, label, roots, require_runtime_seal=True)
        except BaseException as recovery_error:
            raise SystemExit(
                "C2 compatibility: EFFECT_UNKNOWN during rollback; "
                "do not retry or restart without exact effect reconciliation"
            ) from recovery_error
        raise SystemExit("C2 compatibility: NOT_APPLIED original state restored") from exc
    print(json.dumps({
        "account": account, "effect": "APPLIED",
        "gatewayCompatibilityInstalled": True,
        "manifestSha256": _sha256_file(manifest_path),
        "noNewRepositoryGrants": not personal, "closedRepositoriesEnabled": personal,
        "fleetModulesPreserved": True,
        "serviceStarted": False,
    }, sort_keys=True))
    return 0


def _enroll_c2_business_closed_repositories(
    args, node_abs: Path, backend_abs: Path, account: str,
    label: str, port: int, roots: dict,
) -> int:
    """One existing-installer CAS grant, only after the reviewed C2 11->12 repair.

    This does not replace a fleet gateway, switch a source/credential, create a
    repository or execute Git. Only the existing closed profile and its exact
    manifest hash may change. Caller-selected destinations remain impossible.
    """
    expected = getattr(args, "publisher_expected_manifest_sha256", None)
    preview = getattr(args, "publisher_preflight_only", False)
    if (account != "chatgpt2-business" or type(preview) is not bool
            or not _sha256_hex(expected)
            or getattr(args, "enable_repository_workspaces", False) is not True
            or getattr(args, "publisher_only_fleet_v10", False) is True
            or getattr(args, "c2_business_fleet_compat", False) is True
            or getattr(args, "fabric_only", False) is True
            or getattr(args, "c2_personal_git_timeout_only", False) is True
            or getattr(args, "os_commission_config_sha256", None) is not None):
        raise SystemExit("C2 repository enrollment requires the exact Business profile, explicit opt-in and manifest CAS")

    manifest_path, config_path = roots["manifest"], roots["config"]
    for target in (manifest_path, config_path):
        _assert_dest_safe(target)
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("C2 repository enrollment: original manifest CAS mismatch")
    prior = _verify_staged_install(
        account, label, roots, require_runtime_seal=True)
    if (prior.get("version") != MANIFEST_VERSION
            or not prior.get("dependencyTreeHash")
            or frozenset(prior["files"]) != V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR
            or frozenset(prior["files"]) !=
                (frozenset(C2_BUSINESS_V10_ORIGINAL_BLOBS) | {"workspace-access.mjs"})
            or prior.get("node") != str(node_abs)
            or prior.get("backend") != str(backend_abs)
            or prior.get("host") != "127.0.0.1"
            or prior.get("port") != port):
        raise SystemExit("C2 repository enrollment: reviewed installed generation does not match")

    # The earlier C2 compatibility transaction pins all original unchanged
    # modules and exactly three reviewed replacements, including the publisher.
    # Never grant closed repository access to an unknown source generation.
    for name in prior["files"]:
        path = roots["base"] / name
        _assert_dest_safe(path)
        reviewed_digest = C2_BUSINESS_TARGET_PATCH_SHA256.get(name)
        if reviewed_digest is not None:
            if prior["files"][name] != reviewed_digest or _sha256_file(path) != reviewed_digest:
                raise SystemExit("C2 repository enrollment: reviewed publisher source changed")
        else:
            raw = path.read_bytes()
            blob = hashlib.sha1(
                b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
            ).hexdigest()
            if blob != C2_BUSINESS_V10_ORIGINAL_BLOBS[name]:
                raise SystemExit("C2 repository enrollment: original fleet source changed")

    old_manifest = manifest_path.read_bytes()
    old_config = config_path.read_bytes()
    if (hashlib.sha256(old_manifest).hexdigest() != expected
            or hashlib.sha256(old_config).hexdigest() != prior["configHash"]):
        raise SystemExit("C2 repository enrollment: original snapshot changed")
    try:
        current = json.loads(old_config)
    except (ValueError, UnicodeError) as exc:
        raise SystemExit("C2 repository enrollment: original configuration unreadable") from exc
    user_root = _user_root()
    if (type(current) is not dict
            or current.get("accountLabel") != account
            or current.get("gitPublish") != _typed_git_config(user_root)
            or "repositoryWorkspaces" in current
            or current.get("fleetRouting", {}).get("enabled") is not True
            or len(current["fleetRouting"].get("routes", [])) != 2
            or current.get("maxPerSessionConcurrency") != 8
            or current.get("maxQueuedPerSession") != 16
            or type(current.get("fleetStatus")) is not dict
            or type(current.get("paperDesign")) is not dict
            or current.get("fabricOnly") is True
            or "commissionPublication" in current
            or "modernFabricProtocol" in current):
        raise SystemExit("C2 repository enrollment: original Mastermind-only fleet profile changed")

    future_config = dict(current)
    future_config["gitPublish"] = _typed_git_config(
        user_root, closed_repositories=True)
    future_config["repositoryWorkspaces"] = {
        "enabled": True,
        "allowedRepositories": ["mastermind", "macro", "terminal"],
    }
    preserved = set(current) - {"gitPublish", "repositoryWorkspaces"}
    if any(future_config[key] != current[key] for key in preserved):
        raise SystemExit("C2 repository enrollment: unrelated configuration changed")
    new_config = json.dumps(
        future_config, indent=2, sort_keys=True).encode("utf-8")
    future_manifest = dict(prior)
    future_manifest["configHash"] = hashlib.sha256(new_config).hexdigest()
    if not _valid_manifest(future_manifest, account, label):
        raise SystemExit("C2 repository enrollment: proposed sealed manifest refused")
    new_manifest = json.dumps(
        future_manifest, indent=2, sort_keys=True).encode("utf-8")
    target_sha = hashlib.sha256(new_manifest).hexdigest()
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("C2 repository enrollment: manifest changed during preflight")
    receipt = {
        "account": account,
        "originalManifestSha256": expected,
        "targetManifestSha256": target_sha,
        "closedRepositories": ["mastermind", "macro", "terminal"],
        "fleetRoutesPreserved": 2,
        "concurrencyPreserved": [8, 16],
        "gatewayAndModuleBytesPreserved": True,
        "serviceStarted": False,
    }
    if preview:
        print(json.dumps({**receipt, "preflight": True, "effect": "NOT_APPLIED"}, sort_keys=True))
        return 0

    if _lifecycle_inspect(account, label, roots) is not None:
        raise SystemExit("refusing C2 repository enrollment while service is loaded; stop first")
    if (_verify_staged_install(account, label, roots, require_runtime_seal=True) != prior
            or _stable_regular_file_hash(manifest_path, label="installed manifest") != expected
            or _stable_regular_file_hash(config_path, label="installed config") != prior["configHash"]):
        raise SystemExit("C2 repository enrollment: original state changed before write")

    planned = {config_path: new_config, manifest_path: new_manifest}
    original = {config_path: old_config, manifest_path: old_manifest}
    committed = False
    try:
        _atomic_write_bytes(config_path, new_config)
        if (_stable_regular_file_hash(manifest_path, label="installed manifest") != expected
                or _stable_regular_file_hash(config_path, label="installed config") != future_manifest["configHash"]
                or _lifecycle_inspect(account, label, roots) is not None):
            raise RuntimeError("C2 repository enrollment: original state changed before manifest commit")
        _atomic_write_bytes(manifest_path, new_manifest)
        committed = True
        if (_verify_staged_install(account, label, roots, require_runtime_seal=True) != future_manifest
                or _stable_regular_file_hash(manifest_path, label="installed manifest") != target_sha
                or _lifecycle_inspect(account, label, roots) is not None):
            raise RuntimeError("C2 repository enrollment: committed identity mismatch")
    except BaseException as exc:
        if committed:
            raise SystemExit(
                "C2 repository enrollment: EFFECT_UNKNOWN after manifest commit; "
                "reconcile exact original install before restart"
            ) from exc
        try:
            if _lifecycle_inspect(account, label, roots) is not None:
                raise RuntimeError("service became loaded during rollback")
            for path in planned:
                _assert_dest_safe(path)
                observed = path.read_bytes()
                if observed not in (planned[path], original[path]):
                    raise RuntimeError("non-owned mutation during recovery")
                if observed != original[path]:
                    _atomic_write_bytes(path, original[path])
            if (any(path.read_bytes() != original[path] for path in planned)
                    or _stable_regular_file_hash(manifest_path, label="installed manifest") != expected):
                raise RuntimeError("original state not restored")
            _verify_staged_install(account, label, roots, require_runtime_seal=True)
        except BaseException as rollback_error:
            raise SystemExit(
                "C2 repository enrollment: EFFECT_UNKNOWN during rollback; "
                "do not retry or restart without reconciliation"
            ) from rollback_error
        raise SystemExit("C2 repository enrollment: NOT_APPLIED original state restored") from exc

    print(json.dumps({**receipt, "preflight": False, "effect": "APPLIED"}, sort_keys=True))
    return 0


def _upgrade_c2_personal_git_timeout_only(
    args, source: Path, node_abs: Path, backend_abs: Path,
    account: str, label: str, port: int, roots: dict,
) -> int:
    """Change only the bounded Git command timeout on exact sealed C2 Personal.

    Status prechecks can exceed 15s on the 127k-index Macro checkout under M2
    contention. This is not a repository grant, module upgrade, transport
    retry or a new publication authority. Manifest/config writes are fenced
    and the service must be unloaded before any mutation.
    """
    expected = getattr(args, "publisher_expected_manifest_sha256", None)
    preview = getattr(args, "publisher_preflight_only", False)
    if (account != C2_PAPER_ACCOUNT
            or getattr(args, "c2_personal_git_timeout_only", False) is not True
            or type(preview) is not bool or not _sha256_hex(expected)
            or expected != C2_PERSONAL_TIMEOUT_PREDECESSOR_SHA256
            or getattr(args, "c2_business_fleet_compat", False) is True
            or getattr(args, "c2_personal_closed_publisher", False) is True
            or getattr(args, "c2_business_repository_enrollment", False) is True
            or getattr(args, "publisher_only_fleet_v10", False) is True
            or getattr(args, "enable_repository_workspaces", False) is True
            or getattr(args, "fabric_only", False) is True
            or type(getattr(args, "os_commission_config_sha256", None)) is str):
        raise SystemExit("C2 Git timeout: original closed owner and manifest CAS required")
    manifest_path, config_path = roots["manifest"], roots["config"]
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("C2 Git timeout: installed manifest CAS mismatch")
    prior = _verify_staged_install(account, label, roots, require_runtime_seal=True)
    if (prior.get("version") != MANIFEST_VERSION
            or prior.get("source") != str(source)
            or prior.get("node") != str(node_abs)
            or prior.get("backend") != str(backend_abs)
            or prior.get("host") != "127.0.0.1"
            or prior.get("port") != port
            or not prior.get("dependencyTreeHash")
            or frozenset(prior["files"]) != V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR):
        raise SystemExit("C2 Git timeout: runtime/source identity mismatch")
    if any(prior["files"].get(n) != digest
           for n, digest in C2_PERSONAL_TARGET_PATCH_SHA256.items()):
        raise SystemExit("C2 Git timeout: reviewed installed modules changed")
    old_config_bytes, old_manifest_bytes = config_path.read_bytes(), manifest_path.read_bytes()
    if (hashlib.sha256(old_config_bytes).hexdigest() != prior["configHash"]
            or hashlib.sha256(old_manifest_bytes).hexdigest() != expected):
        raise SystemExit("C2 Git timeout: sealed snapshot changed")
    try:
        old_config = json.loads(old_config_bytes)
    except (UnicodeError, ValueError) as exc:
        raise SystemExit("C2 Git timeout: config not valid JSON") from exc
    original_git = _typed_git_config(_user_root(), closed_repositories=True)
    if (type(old_config) is not dict or old_config.get("accountLabel") != account
            or old_config.get("gitPublish") != original_git
            or old_config.get("repositoryWorkspaces") != {
                "enabled": True, "allowedRepositories": ["mastermind", "macro", "terminal"]}
            or old_config.get("fleetRouting", {}).get("enabled") is not True
            or len(old_config["fleetRouting"].get("routes", [])) != 2
            or old_config.get("maxPerSessionConcurrency") != 8
            or old_config.get("maxQueuedPerSession") != 16
            or old_config.get("paperDesign", {}).get("enabled") is not True
            or old_config.get("fabricOnly") is True
            or "commissionPublication" in old_config
            or "modernFabricProtocol" in old_config):
        raise SystemExit("C2 Git timeout: installed capability identity changed")
    new_config = dict(old_config)
    new_git = dict(original_git)
    new_git["commandTimeoutMs"] = C2_PERSONAL_TIMEOUT_COMMAND_MS
    new_config["gitPublish"] = new_git
    if ({k: v for k, v in new_config.items() if k != "gitPublish"}
            != {k: v for k, v in old_config.items() if k != "gitPublish"}):
        raise SystemExit("C2 Git timeout: unrelated config change")
    config_bytes = json.dumps(new_config, indent=2, sort_keys=True).encode("utf-8")
    future = dict(prior)
    future["configHash"] = hashlib.sha256(config_bytes).hexdigest()
    if not _valid_manifest(future, account, label):
        raise SystemExit("C2 Git timeout: target sealed manifest refused")
    manifest_bytes = json.dumps(future, indent=2, sort_keys=True).encode("utf-8")
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("C2 Git timeout: manifest moved during planning")
    if preview:
        print(json.dumps({
            "account": account, "effect": "NOT_APPLIED", "preflight": True,
            "originalManifestSha256": expected,
            "commandTimeoutBeforeMs": original_git["commandTimeoutMs"],
            "commandTimeoutAfterMs": C2_PERSONAL_TIMEOUT_COMMAND_MS,
            "pushTimeoutPreservedMs": original_git["pushTimeoutMs"],
            "changedFiles": ["config.json", "manifest.json"],
            "sourceModulesPreserved": True, "fleetAndPaperPreserved": True,
            "serviceStarted": False,
        }, sort_keys=True))
        return 0
    if _lifecycle_inspect(account, label, roots) is not None:
        raise SystemExit("C2 Git timeout: service must be stopped")
    if (_stable_regular_file_hash(manifest_path, label="installed manifest") != expected
            or _stable_regular_file_hash(config_path, label="installed config") != prior["configHash"]
            or _verify_staged_install(account, label, roots, require_runtime_seal=True) != prior):
        raise SystemExit("C2 Git timeout: original installation changed before mutation")
    before = {config_path: old_config_bytes, manifest_path: old_manifest_bytes}
    planned = {config_path: config_bytes, manifest_path: manifest_bytes}
    committed = False
    try:
        for target, payload in planned.items():
            _atomic_write_bytes(target, payload)
        committed = True
        _verify_staged_install(account, label, roots, require_runtime_seal=True)
    except BaseException as exc:
        if committed:
            raise SystemExit("C2 Git timeout: EFFECT_UNKNOWN after manifest commit") from exc
        try:
            if _lifecycle_inspect(account, label, roots) is not None:
                raise RuntimeError("service restarted during config transaction")
            observed = {}
            for target in planned:
                if target.is_symlink():
                    raise RuntimeError("symlink detected during rollback")
                observed[target] = target.read_bytes()
                if observed[target] not in (before[target], planned[target]):
                    raise RuntimeError("concurrent out-of-scope change during rollback")
            for target in reversed(tuple(planned)):
                if observed[target] != before[target]:
                    _atomic_write_bytes(target, before[target])
            if (any(target.read_bytes() != before[target] for target in planned)
                    or _stable_regular_file_hash(manifest_path, label="installed manifest") != expected):
                raise RuntimeError("original sealed bytes could not be restored")
            _verify_staged_install(account, label, roots, require_runtime_seal=True)
        except BaseException as recovery_error:
            raise SystemExit("C2 Git timeout: EFFECT_UNKNOWN during rollback") from recovery_error
        raise SystemExit("C2 Git timeout: NOT_APPLIED original state restored") from exc
    print(json.dumps({
        "account": account, "effect": "APPLIED",
        "manifestSha256": _sha256_file(manifest_path),
        "commandTimeoutMs": C2_PERSONAL_TIMEOUT_COMMAND_MS,
        "pushTimeoutPreservedMs": original_git["pushTimeoutMs"],
        "sourceModulesPreserved": True, "fleetAndPaperPreserved": True,
        "serviceStarted": False,
    }, sort_keys=True))
    return 0


@_fabric_lifecycle_serialized()
def cmd_upgrade(args) -> int:
    account = args.account
    _pin_reject_generic_restage(account)
    _validate_account_label(account)
    label = f"com.mastermind.studio-direct-private.{account}"
    host = "127.0.0.1"

    if not os.path.isabs(args.source):
        raise SystemExit("--source must be absolute")
    source = Path(args.source)
    if source.is_symlink() or not source.is_dir():
        raise SystemExit(f"source dir invalid: {source}")
    # C2 fleet predecessor migration is a tightly hash-pinned three-module
    # compatibility package, NOT the incompatible current STAGE_FILES bundle.
    if not (
        getattr(args, "c2_business_fleet_compat", False) is True
        or getattr(args, "c2_personal_closed_publisher", False) is True
        or getattr(args, "c2_personal_git_timeout_only", False) is True
        or getattr(args, "c2_business_repository_enrollment", False) is True
    ):
        _check_source_files(source)
    node_abs = _resolve_abs("--node", args.node)
    backend_abs = _resolve_abs("--backend", args.backend)
    port = int(args.port)
    _validate_port(port)

    roots = _build_runtime_roots(account)
    if getattr(args, "c2_personal_git_timeout_only", False) is True:
        # The C2 Personal timeout migration shares the exact same installed
        # files/manifest with Paper and publisher writers. Retain the protected
        # C2 lifecycle mutex for a modifying transaction, not for read-only
        # preflight. Do not introduce a second lock/owner or a bypass.
        if (account == C2_PAPER_ACCOUNT
                and getattr(args, "publisher_preflight_only", False) is False):
            with _c2_lifecycle_mutex(account):
                return _upgrade_c2_personal_git_timeout_only(
                    args, source, node_abs, backend_abs, account, label, port, roots)
        return _upgrade_c2_personal_git_timeout_only(
            args, source, node_abs, backend_abs, account, label, port, roots)
    if (getattr(args, "c2_business_fleet_compat", False) is True
            or getattr(args, "c2_personal_closed_publisher", False) is True):
        # Both existing C2 compatibility writers share installation state with
        # Paper/lifecycle operations. Hold the same inode through recovery too.
        # Read-only preflight and the helper's exact eligibility stay unchanged.
        if (account in C2_PAPER_UPGRADE_ACCOUNTS
                and getattr(args, "publisher_preflight_only", False) is False):
            with _c2_lifecycle_mutex(account):
                return _upgrade_c2_business_original_fleet_mastermind_only(
                    args, source, node_abs, backend_abs, account, label, port, roots)
        return _upgrade_c2_business_original_fleet_mastermind_only(
            args, source, node_abs, backend_abs, account, label, port, roots)
    if getattr(args, "c2_business_repository_enrollment", False) is True:
        if getattr(args, "publisher_preflight_only", False) is True:
            return _enroll_c2_business_closed_repositories(
                args, node_abs, backend_abs, account, label, port, roots)
        with _c2_lifecycle_mutex(account):
            return _enroll_c2_business_closed_repositories(
                args, node_abs, backend_abs, account, label, port, roots)
    if getattr(args, "publisher_only_fleet_v10", False) is True:
        return _upgrade_fleet_v10_publisher_only(
            args, source, node_abs, backend_abs, account, label, port, roots)
    # Legacy call sites carry mock objects with no new CLI attributes.
    # Reject only actual explicit option values, not arbitrary Mock values.
    if (getattr(args, "publisher_preflight_only", False) is True
            or type(getattr(args, "publisher_expected_manifest_sha256", None)) is str):
        raise SystemExit("publisher preflight and CAS options require --publisher-only-fleet-v10")
    if _launchd_inspect(label) is not None:
        raise SystemExit("refusing upgrade while service is running; stop first")
    prior = _verify_staged_install(
        account, label, roots, require_runtime_seal=False
    )
    if prior.get("version") == MANIFEST_VERSION and prior.get("dependencyTreeHash") is not None:
        _verify_staged_install(account, label, roots, require_runtime_seal=True)
    if (
        prior.get("node") != str(node_abs)
        or prior.get("backend") != str(backend_abs)
        or prior.get("host") != host
        or prior.get("port") != port
    ):
        raise SystemExit(
            "refusing upgrade: node, backend, host and port must match the existing install"
        )
    for path in _stage_dest_files(roots):
        _assert_dest_safe(path)
    fabric_only = _fabric_profile_setting(args, roots, prior)
    repository_workspaces = _repository_workspace_setting(args, roots, prior)
    commission_digest = _commission_setting(args, roots, prior)
    # Compute the exact target policy BEFORE the first installation write.
    # Recognizing a sealed historical manifest is not permission to remove
    # the original fleet routes, tailnet adapter, concurrency or telemetry.
    if frozenset(prior["files"]) in (
        V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR,
        frozenset(C2_PAPER_FILES_SHA256),
        V2_C2_BUSINESS_FLEET_PREDECESSOR,
    ):
        projected = _build_config(
            account, host, port, node_abs, backend_abs, roots["state"],
            _user_root(), repository_workspaces=repository_workspaces,
            commission_digest=commission_digest, fabric_only=fabric_only,
        )
        _verify_upgrade_preserves_installed_fleet_capabilities(
            prior, roots, projected)
    # Preserve the existing restricted profile; do not silently restore tools.
    if not fabric_only:
        _verify_paper_runtime(_user_root())

    return _write_install(
        source, node_abs, backend_abs, account, label, host, port, roots,
        result_key="upgraded", previous_source=str(prior.get("source") or ""),
        repository_workspaces=repository_workspaces,
        commission_digest=commission_digest,
        fabric_only=fabric_only,
        modern_fabric=_modern_fabric_setting(args, roots, prior, fabric_only),
    )


@_c2_lifecycle_serialized(readonly_preflight=True)
def cmd_paper_runtime_upgrade(args) -> int:
    """Select reviewed Paper v12 on an exact qualified fleet without restaging it.

    This dedicated transaction grants no new account, file cohort or capability.
    It cannot stop/start a service, copy gateway source or select an arbitrary bridge.
    The original manifest CAS is intentionally single-use; a replay must fresh-read.
    """
    account = args.account
    _validate_account_label(account)
    expected = args.expected_manifest_sha256
    preview = args.preflight_only
    if account == C2_PAPER_ACCOUNT:
        original_manifest = C2_PAPER_ORIGINAL_MANIFEST_SHA256
        non_paper_pin = C2_PAPER_NON_PAPER_CONFIG_SHA256
        runtime_identity = C2_PAPER_RUNTIME_IDENTITY
    elif account == C2_PAPER_BUSINESS_ACCOUNT:
        original_manifest = C2_PAPER_BUSINESS_ORIGINAL_MANIFEST_SHA256
        non_paper_pin = C2_PAPER_BUSINESS_NON_PAPER_CONFIG_SHA256
        runtime_identity = C2_PAPER_BUSINESS_RUNTIME_IDENTITY
    elif account == C4_PAPER_ACCOUNT:
        original_manifest = C4_PAPER_ORIGINAL_MANIFEST_SHA256
        non_paper_pin = C4_PAPER_NON_PAPER_CONFIG_SHA256
        runtime_identity = C4_PAPER_RUNTIME_IDENTITY
    else:
        raise SystemExit("paper runtime compatibility requires the exact enrolled Paper account")
    if type(preview) is not bool:
        raise SystemExit("paper runtime compatibility preflight flag invalid")
    if not _sha256_hex(expected):
        raise SystemExit("paper runtime compatibility requires an exact manifest CAS")
    if expected != original_manifest:
        raise SystemExit("paper runtime compatibility: original manifest is not the reviewed predecessor")
    if PAPER_RUNTIME_REL.name != "v12":
        raise SystemExit("paper runtime compatibility requires the reviewed v12 target")

    label = f"com.mastermind.studio-direct-private.{account}"
    roots = _build_runtime_roots(account)
    config_path, manifest_path = roots["config"], roots["manifest"]
    for path in (config_path, manifest_path, roots["plist"]):
        _assert_dest_safe(path)
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("paper runtime compatibility: installed manifest CAS mismatch")
    prior = _verify_staged_install(account, label, roots, require_runtime_seal=True)
    if (prior.get("files") != C2_PAPER_FILES_SHA256
            or any(prior.get(key) != value for key, value in runtime_identity.items())):
        raise SystemExit("paper runtime compatibility: original sealed identity does not match")
    for name in prior["files"]:
        _assert_dest_safe(roots["base"] / name)
    old_config_bytes, old_manifest_bytes = config_path.read_bytes(), manifest_path.read_bytes()
    if (hashlib.sha256(old_config_bytes).hexdigest() != prior["configHash"]
            or hashlib.sha256(old_manifest_bytes).hexdigest() != expected):
        raise SystemExit("paper runtime compatibility: verified snapshot changed during preflight")
    try:
        old_config = json.loads(old_config_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("paper runtime compatibility: original config invalid") from exc
    if type(old_config) is not dict:
        raise SystemExit("paper runtime compatibility: original config invalid")
    non_paper = {key: value for key, value in old_config.items() if key != "paperDesign"}
    non_paper_sha = hashlib.sha256(json.dumps(
        non_paper, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    if non_paper_sha != non_paper_pin:
        raise SystemExit("paper runtime compatibility: original non-Paper profile changed")

    user_root = _user_root()
    target_paper = _paper_design_config(user_root)
    old_runtime = user_root / ".local/share/mastermind-paper/runtime/v10"
    expected_old_paper = {
        **target_paper,
        "pythonPath": str(old_runtime / "venv/bin/python"),
        "bridgePath": str(old_runtime / "source/bridge.py"),
        "bridgeSha256": C2_PAPER_ORIGINAL_BRIDGE_SHA256,
    }
    if old_config.get("paperDesign") != expected_old_paper:
        raise SystemExit("paper runtime compatibility: original Paper selection is not exact v10")
    _verify_paper_runtime(user_root)
    new_config = {**old_config, "paperDesign": target_paper}
    config_bytes = json.dumps(new_config, indent=2, sort_keys=True).encode("utf-8")
    future = {**prior, "configHash": hashlib.sha256(config_bytes).hexdigest()}
    if not _valid_manifest(future, account, label):
        raise SystemExit("paper runtime compatibility: prospective manifest invalid")
    manifest_bytes = json.dumps(future, indent=2, sort_keys=True).encode("utf-8")
    target_manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    if _stable_regular_file_hash(manifest_path, label="installed manifest") != expected:
        raise SystemExit("paper runtime compatibility: installed manifest changed during planning")
    receipt = {
        "account": account, "fromGeneration": "v10", "toGeneration": "v12",
        "originalManifestSha256": expected, "targetManifestSha256": target_manifest_sha,
        "bridgeSha256": PAPER_BRIDGE_SHA256, "nonPaperConfigSha256": non_paper_sha,
        "preservedGatewayFiles": len(prior["files"]), "runtimeSealPreserved": True,
        "sourcePointerPreserved": True, "serviceStarted": False,
    }
    if preview:
        print(json.dumps({**receipt, "preflight": True, "effect": "NOT_APPLIED"}, sort_keys=True))
        return 0
    if _lifecycle_inspect(account, label, roots, require_positive=True) is not None:
        raise SystemExit("refusing Paper runtime upgrade while service is loaded; stop first")
    # Reconfirm the complete sealed installation and target before the first write.
    if _verify_staged_install(account, label, roots, require_runtime_seal=True) != prior:
        raise SystemExit("paper runtime compatibility: original installation changed")
    _verify_paper_runtime(user_root)
    if (_stable_regular_file_hash(manifest_path, label="installed manifest") != expected
            or _stable_regular_file_hash(config_path, label="installed config") != prior["configHash"]):
        raise SystemExit("paper runtime compatibility: original snapshot CAS mismatch")
    if _lifecycle_inspect(account, label, roots, require_positive=True) is not None:
        raise SystemExit("refusing Paper runtime upgrade while service is loaded; stop first")

    old_bytes = {config_path: old_config_bytes, manifest_path: old_manifest_bytes}
    planned = {config_path: config_bytes, manifest_path: manifest_bytes}
    committed = False
    try:
        _atomic_write_bytes(config_path, config_bytes)
        # Manifest commits last so fresh integrity checks reject partial file updates.
        if (_stable_regular_file_hash(manifest_path, label="installed manifest") != expected
                or _stable_regular_file_hash(config_path, label="installed config") != future["configHash"]
                or _lifecycle_inspect(account, label, roots, require_positive=True) is not None):
            raise RuntimeError("installed state changed before manifest commit")
        _atomic_write_bytes(manifest_path, manifest_bytes)
        committed = True
        if (_verify_staged_install(account, label, roots, require_runtime_seal=True) != future
                or _stable_regular_file_hash(manifest_path, label="installed manifest") != target_manifest_sha):
            raise RuntimeError("committed installation does not match the planned result")
        _verify_paper_runtime(user_root)
        if _lifecycle_inspect(account, label, roots, require_positive=True) is not None:
            raise RuntimeError("service became loaded during commit verification")
    except BaseException as exc:
        if committed:
            raise SystemExit(
                "paper runtime compatibility: EFFECT_UNKNOWN after manifest commit; "
                "inspect the original service before recovery or restart"
            ) from exc
        try:
            if _lifecycle_inspect(account, label, roots, require_positive=True) is not None:
                raise RuntimeError("service became loaded during transaction")
            observed = {}
            for path in planned:
                _assert_dest_safe(path)
                digest = _stable_regular_file_hash(path, label="rollback target")
                observed[path] = path.read_bytes()
                if hashlib.sha256(observed[path]).hexdigest() != digest:
                    raise RuntimeError("rollback target changed while reading")
                if observed[path] not in (old_bytes[path], planned[path]):
                    raise RuntimeError("non-owned concurrent mutation while recovering")
            for path in reversed(tuple(planned)):
                if observed[path] != old_bytes[path]:
                    if (_lifecycle_inspect(account, label, roots, require_positive=True) is not None
                            or _stable_regular_file_hash(path, label="rollback target")
                            != hashlib.sha256(observed[path]).hexdigest()):
                        raise RuntimeError("rollback target or service changed before restoration")
                    _atomic_write_bytes(path, old_bytes[path])
            if (any(path.read_bytes() != old_bytes[path] for path in planned)
                    or _stable_regular_file_hash(manifest_path, label="installed manifest") != expected):
                raise RuntimeError("rollback byte identity differs")
            _verify_staged_install(account, label, roots, require_runtime_seal=True)
            if _lifecycle_inspect(account, label, roots, require_positive=True) is not None:
                raise RuntimeError("service became loaded during rollback verification")
        except BaseException as rollback_exc:
            raise SystemExit(
                "paper runtime compatibility: EFFECT_UNKNOWN during rollback; "
                "do not restart or replay until the original state is reconciled"
            ) from rollback_exc
        raise SystemExit("paper runtime compatibility: NOT_APPLIED; original state restored") from exc
    print(json.dumps({**receipt, "preflight": False, "effect": "APPLIED"}, sort_keys=True))
    return 0


def _fabric_release_bytes(path: Path, *, limit: int = 2 * 1024 * 1024) -> bytes:
    """Read a bounded, owned regular file without following a replacement link."""
    _assert_dest_safe(path)
    current = path.parent
    while True:
        info = current.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o022):
            raise SystemExit("Fabric release file parent is unsafe")
        if current == _user_root():
            break
        current = current.parent
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    except OSError as exc:
        raise SystemExit("Fabric release file unavailable") from exc
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or before.st_nlink != 1 or before.st_mode & 0o022
                or before.st_size > limit):
            raise SystemExit("Fabric release file is unsafe or too large")
        data = bytearray()
        while len(data) <= limit:
            part = os.read(fd, min(65536, limit + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        after = os.fstat(fd)
        named = path.lstat()
        identity = lambda x: (x.st_dev, x.st_ino, x.st_mode, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
        if (len(data) > limit or identity(before) != identity(after)
                or identity(after) != identity(named)):
            raise SystemExit("Fabric release file changed while reading")
        return bytes(data)
    finally:
        os.close(fd)


def _fabric_release_source(release_commit: str, expected_sha: str) -> tuple[Path, dict]:
    """Bind the sole backend path to a commit already in observed protected master.

    The operator refreshes the fixed source-admin repository and checks protected
    merge evidence before invoking this local installer. This does not fetch,
    change a ref, bypass review, or treat an arbitrary path/hash as a release.
    """
    if (not isinstance(release_commit, str)
            or re.fullmatch(r"[0-9a-f]{40}", release_commit) is None
            or not _sha256_hex(expected_sha)):
        raise SystemExit("Fabric release requires an exact commit and backend SHA256")
    home = _user_root()
    repo = home / TYPED_GIT_SOURCE_REPOSITORY_REL
    _assert_no_symlink_ancestors(repo)
    if not repo.is_dir():
        raise SystemExit("Fabric release source-admin repository unavailable")

    def git(*argv):
        try:
            result = _run([TYPED_GIT_BINARY, "--no-replace-objects", "-C", str(repo),
                           "--git-dir", str(repo / ".git"), *argv], check=False, timeout=15)
        except Exception as exc:
            raise SystemExit("Fabric release Git evidence unavailable") from exc
        if result.returncode != 0:
            raise SystemExit("Fabric release Git evidence refused")
        return result.stdout

    if git("remote", "get-url", "--all", "origin").splitlines() != [TYPED_GIT_REMOTE_URL]:
        raise SystemExit("Fabric release requires the exact Mastermind origin")
    observed = git("rev-parse", "--verify", "refs/remotes/origin/master^{commit}").strip()
    if re.fullmatch(r"[0-9a-f]{40}", observed) is None:
        raise SystemExit("Fabric release protected-master observation invalid")
    if git("rev-parse", "--verify", release_commit + "^{commit}").strip() != release_commit:
        raise SystemExit("Fabric release commit is not exact")
    git("merge-base", "--is-ancestor", release_commit, observed)
    tree = git("ls-tree", "--full-tree", release_commit, "--", FABRIC_BACKEND_SOURCE)
    match = re.fullmatch(r"100(?:644|755) blob ([0-9a-f]{40})\t" + re.escape(FABRIC_BACKEND_SOURCE) + r"\n", tree)
    if match is None:
        raise SystemExit("Fabric release backend is not the exact regular Git source")
    backend = home / FABRIC_BACKEND_RELEASES_REL / ("fabric-c3-" + release_commit) / FABRIC_BACKEND_SOURCE
    raw = _fabric_release_bytes(backend)
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if hashlib.sha256(raw).hexdigest() != expected_sha or blob != match.group(1):
        raise SystemExit("Fabric release backend differs from the merged source or pinned SHA256")
    return backend, {"releaseCommit": release_commit, "backendGitBlob": blob,
                     "backendSha256": expected_sha, "observedProtectedMaster": observed}


def _fabric_release_new(path: Path, data: bytes) -> None:
    """Persist evidence exactly once; interrupted operations are never replayed."""
    _assert_dest_safe(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, FILE_MODE)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), FILE_MODE)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    _fsync_dir(path.parent)


def _fabric_release_json(value: dict) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")


def _validate_legacy_fleet_status(config: dict, user_root: Path) -> bool:
    """Admit only the narrow legacy fleetStatus on an existing restricted profile.

    The legacy sealed config contained fleetStatus but predated the
    modernFabricProtocol and backendMode selectors. This validator never invokes
    the launcher. It re-derives the owner-bound helper and requires exact field
    and type equality with the freshly derived owner configuration; the launcher
    descriptor bytes are then read through the existing owned, regular-file,
    no-symlink, no-follow reader and their SHA256 must equal the freshly
    derived expected['launcherSha256']. A None, missing, or unsafe launcher,
    wrong field type, ownership/file-type/links/permissions/read/stability or
    digest error, or any extra/omitted key fails closed. Profile-driven
    launcher execution is not authorised by this validator; only sealed
    fleetStatus identity is admitted.

    Profiles without fleetStatus continue to be governed by every other check.
    """
    if "fleetStatus" not in config:
        return True
    if "modernFabricProtocol" in config or "backendMode" in config:
        raise SystemExit(
            "Fabric backend release: legacy fleetStatus requires absent "
            "modernFabricProtocol and backendMode selectors"
        )
    fleet_status = config["fleetStatus"]
    required_keys = frozenset(("enabled", "launcherPath", "launcherSha256", "timeoutMs"))
    if type(fleet_status) is not dict or set(fleet_status) != required_keys:
        raise SystemExit(
            "Fabric backend release: legacy fleetStatus requires exact "
            "enabled/launcherPath/launcherSha256/timeoutMs keys"
        )
    if (fleet_status["enabled"] is not True
            or type(fleet_status["launcherPath"]) is not str
            or type(fleet_status["launcherSha256"]) is not str
            or type(fleet_status["timeoutMs"]) is not int):
        raise SystemExit(
            "Fabric backend release: legacy fleetStatus field types are invalid"
        )
    expected = _fleet_status_config(user_root)
    if expected is None:
        raise SystemExit(
            "Fabric backend release: legacy fleetStatus owner launcher unavailable"
        )
    # _fleet_status_config delegates launcher reads to _stable_regular_file_hash,
    # which does not check st_uid. Read the launcher descriptor via the existing
    # owned, regular, no-follow, bounded reader so a wrong-owner launcher is
    # caught before this validator returns. Any ownership, file-type, links,
    # permissions, read/stability or digest error must refuse the release.
    launcher_bytes = _fabric_release_bytes(user_root / FLEET_STATUS_LAUNCHER_REL)
    if hashlib.sha256(launcher_bytes).hexdigest() != expected["launcherSha256"]:
        raise SystemExit(
            "Fabric backend release: legacy fleetStatus owner launcher digest mismatch"
        )
    if fleet_status != expected:
        raise SystemExit(
            "Fabric backend release: legacy fleetStatus does not match owner"
        )
    return True


@_fabric_lifecycle_serialized(readonly_preflight=True)
def cmd_fabric_backend_release(args) -> int:
    """Select one merged Fabric backend while preserving the entire sealed seat.

    Preview is read-only. Apply requires its exact plan and the unloaded original
    service. It changes config args[0] and three manifest fields only; the same
    private-service owner performs any later explicit start.
    """
    account = args.account
    _validate_account_label(account)
    if account not in FABRIC_BACKEND_ACCOUNTS or type(args.preflight_only) is not bool:
        raise SystemExit("Fabric backend release requires an explicitly enrolled restricted c3 account")
    expected = args.expected_manifest_sha256
    if not _sha256_hex(expected):
        raise SystemExit("Fabric backend release requires the original manifest CAS")
    label = f"com.mastermind.studio-direct-private.{account}"
    roots = _build_runtime_roots(account)
    config_path, manifest_path = roots["config"], roots["manifest"]
    before_manifest = _fabric_release_bytes(manifest_path)
    if hashlib.sha256(before_manifest).hexdigest() != expected:
        raise SystemExit("Fabric backend release: original manifest CAS mismatch")
    prior = _verify_staged_install(account, label, roots, require_runtime_seal=True)
    before_config = _fabric_release_bytes(config_path)
    if (hashlib.sha256(before_config).hexdigest() != prior["configHash"]
            or _fabric_release_bytes(manifest_path) != before_manifest):
        raise SystemExit("Fabric backend release: sealed snapshot changed")
    try:
        old_config = json.loads(before_config)
    except (ValueError, UnicodeError) as exc:
        raise SystemExit("Fabric backend release: original config invalid") from exc
    argv = old_config.get("args") if isinstance(old_config, dict) else None
    # The live modern seat is one exact enrollment, not permission to migrate
    # another profile or change its protocol, port, or capability boundary.
    if account == FABRIC_BACKEND_MODERN_ACCOUNT and (
            type(old_config) is not dict
            or old_config.get("modernFabricProtocol") is not True
            or old_config.get("backendMode") != "shared-account"
            or type(old_config.get("port")) is not int
            or old_config["port"] != FABRIC_BACKEND_MODERN_PORT
            or "fleetStatus" in old_config):
        raise SystemExit("Fabric backend release: exact enrolled modern profile required")
    if (type(old_config) is not dict or old_config.get("fabricOnly") is not True
            or old_config.get("gitPublish") is not False or old_config.get("paperDesign") is not False
            or any(key in old_config for key in ("repositoryWorkspaces", "commissionPublication", "fleetRouting", "publicUrl"))
            or not _validate_legacy_fleet_status(old_config, _user_root())
            or old_config.get("testMode") is not False
            or old_config.get("accountLabel") != account
            or old_config.get("command") != prior["node"]
            or old_config.get("host") != "127.0.0.1" or prior.get("host") != "127.0.0.1"
            or old_config.get("port") != prior["port"]
            or old_config.get("stateDir") != str(roots["state"])
            or type(argv) is not list or not argv or not all(isinstance(x, str) for x in argv)
            or argv[0] != prior["backend"] or type(old_config.get("childEnv")) is not dict
            or old_config["childEnv"].get("MMX_FABRIC_SDK_PACKAGE") != str(roots["base"] / "package.json")):
        raise SystemExit("Fabric backend release: original restricted profile or SDK binding differs")
    backend, source = _fabric_release_source(args.release_commit, args.backend_sha256)
    if str(backend) == prior["backend"]:
        raise SystemExit("Fabric backend release: backend already selected; no replay")
    new_config = {**old_config, "args": [str(backend), *argv[1:]]}
    config_bytes = _fabric_release_json(new_config)
    future = {**prior, "backend": str(backend), "backendHash": args.backend_sha256,
              "configHash": hashlib.sha256(config_bytes).hexdigest()}
    if not _valid_manifest(future, account, label):
        raise SystemExit("Fabric backend release: prospective manifest invalid")
    manifest_bytes = _fabric_release_json(future)
    target_manifest = hashlib.sha256(manifest_bytes).hexdigest()
    plan = {
        "schema": FABRIC_BACKEND_RELEASE_SCHEMA, "account": account,
        "originalManifestSha256": expected, "targetManifestSha256": target_manifest,
        "originalConfigSha256": prior["configHash"], "targetConfigSha256": future["configHash"],
        "originalBackend": prior["backend"], "originalBackendSha256": prior["backendHash"],
        "targetBackend": str(backend), "targetBackendSha256": args.backend_sha256,
        "releaseCommit": source["releaseCommit"], "backendGitBlob": source["backendGitBlob"],
        "preservedGatewayFiles": len(prior["files"]), "preservedDependencyTreeSha256": prior["dependencyTreeHash"],
        "preservedPlistSha256": prior["plistHash"], "serviceStarted": False,
        "changedConfigFields": ["args[0]"], "changedManifestFields": ["backend", "backendHash", "configHash"],
    }
    plan_sha = _canonical_json_sha256(plan)
    evidence_root = roots["state"] / "fabric-backend-releases"
    transaction = evidence_root / plan_sha
    if transaction.exists() or transaction.is_symlink():
        raise SystemExit("Fabric backend release: retained transaction already exists; inspect its exact effect before proceeding")
    if (_fabric_release_bytes(manifest_path) != before_manifest
            or _fabric_release_bytes(config_path) != before_config):
        raise SystemExit("Fabric backend release: original snapshot changed while planning")
    if args.preflight_only:
        print(json.dumps({**plan, "planSha256": plan_sha, "preflight": True,
                          "effect": "NOT_APPLIED", "observedProtectedMaster": source["observedProtectedMaster"]}, sort_keys=True))
        return 0
    if not _sha256_hex(args.expected_plan_sha256) or args.expected_plan_sha256 != plan_sha:
        raise SystemExit("Fabric backend release: exact reviewed preview plan is required")
    if _lifecycle_inspect(account, label, roots) is not None:
        raise SystemExit("refusing Fabric backend release while service is loaded; stop first")
    if (_verify_staged_install(account, label, roots, require_runtime_seal=True) != prior
            or _fabric_release_bytes(manifest_path) != before_manifest
            or _fabric_release_bytes(config_path) != before_config):
        raise SystemExit("Fabric backend release: original runtime changed before write")
    _fabric_release_source(args.release_commit, args.backend_sha256)
    if _lifecycle_inspect(account, label, roots) is not None:
        raise SystemExit("refusing Fabric backend release while service is loaded; stop first")
    _ensure_secure_dir(evidence_root)
    _assert_dest_safe(transaction)
    transaction.mkdir(mode=DIR_MODE)
    _fsync_dir(evidence_root)
    _fabric_release_new(transaction / "config.before.json", before_config)
    _fabric_release_new(transaction / "manifest.before.json", before_manifest)
    intent_bytes = _fabric_release_json({**plan, "planSha256": plan_sha,
        "observedProtectedMaster": source["observedProtectedMaster"], "intentRecordedAt": time.time()})
    _fabric_release_new(transaction / "intent.json", intent_bytes)
    intent_sha = hashlib.sha256(intent_bytes).hexdigest()

    def record(name, effect, **extra):
        value = {"schema": FABRIC_BACKEND_RELEASE_SCHEMA, "account": account,
                 "planSha256": plan_sha, "intentSha256": intent_sha,
                 "effect": effect, "serviceStarted": False, "recordedAt": time.time(), **extra}
        _fabric_release_new(transaction / name, _fabric_release_json(value))

    try:
        if (_fabric_release_bytes(manifest_path) != before_manifest
                or _fabric_release_bytes(config_path) != before_config
                or _lifecycle_inspect(account, label, roots) is not None):
            raise RuntimeError("original state changed after intent persistence")
        _atomic_write_bytes(config_path, config_bytes)
        if (_fabric_release_bytes(manifest_path) != before_manifest
                or _fabric_release_bytes(config_path) != config_bytes
                or _stable_regular_file_hash(backend, label="Fabric backend") != args.backend_sha256
                or _lifecycle_inspect(account, label, roots) is not None):
            raise RuntimeError("original state changed before manifest commit")
        # The sealed manifest commits last. A partial config update fails all
        # incumbent start/integrity checks until it is restored or reconciled.
        _atomic_write_bytes(manifest_path, manifest_bytes)
        if (_verify_staged_install(account, label, roots, require_runtime_seal=True) != future
                or _fabric_release_bytes(manifest_path) != manifest_bytes
                or _fabric_release_bytes(config_path) != config_bytes
                or _lifecycle_inspect(account, label, roots) is not None):
            raise RuntimeError("committed runtime differs from the planned selection")
        record("result.json", "APPLIED", manifestSha256=target_manifest,
               backendSha256=args.backend_sha256, runtimeSealVerified=True)
    except BaseException as exc:
        # Any observed commit or concurrent change requires effect reconciliation.
        # Never overwrite a manifest which may already have committed successfully.
        rollback_proven = False
        try:
            if (_lifecycle_inspect(account, label, roots) is not None
                    or _fabric_release_bytes(manifest_path) != before_manifest):
                raise RuntimeError("manifest committed or service absence is unverified")
            observed = _fabric_release_bytes(config_path)
            if observed not in (before_config, config_bytes):
                raise RuntimeError("non-owned concurrent configuration change")
            if observed != before_config:
                if (_fabric_release_bytes(config_path) != observed
                        or _fabric_release_bytes(manifest_path) != before_manifest
                        or _lifecycle_inspect(account, label, roots) is not None):
                    raise RuntimeError("rollback target or service changed before restoration")
                _atomic_write_bytes(config_path, before_config)
            if (_fabric_release_bytes(manifest_path) != before_manifest
                    or _fabric_release_bytes(config_path) != before_config
                    or _verify_staged_install(account, label, roots, require_runtime_seal=True) != prior
                    or _lifecycle_inspect(account, label, roots) is not None):
                raise RuntimeError("original sealed runtime restoration unverified")
            record("rollback.json", "ROLLED_BACK", originalManifestSha256=expected,
                   originalConfigSha256=prior["configHash"], runtimeSealVerified=True)
            record("result.json", "NOT_APPLIED", originalManifestSha256=expected,
                   originalStateRestored=True)
            rollback_proven = True
        except BaseException:
            try:
                record("failure.json", "EFFECT_UNKNOWN", retryAllowed=False,
                       recovery="Inspect retained intent and exact original account before any retry or start")
            except BaseException:
                pass
        if rollback_proven:
            raise SystemExit("Fabric backend release: NOT_APPLIED; original sealed state restored; evidence retained") from exc
        raise SystemExit("Fabric backend release: EFFECT_UNKNOWN; inspect retained intent and original account before retry or start") from exc
    print(json.dumps({**plan, "planSha256": plan_sha, "intentSha256": intent_sha,
                      "preflight": False, "effect": "APPLIED", "evidenceDirectory": str(transaction)}, sort_keys=True))
    return 0


@_pin_lifecycle_serialized
@_fabric_lifecycle_serialized()
@_c2_lifecycle_serialized()
def cmd_seal_runtime(args) -> int:
    account = args.account
    _validate_account_label(account)
    label = f"com.mastermind.studio-direct-private.{account}"
    roots = _build_runtime_roots(account)
    if _lifecycle_inspect(account, label, roots) is not None:
        raise SystemExit("refusing runtime seal while service is loaded; stop first")
    manifest = _verify_native_pin_install(
        account, label, roots, require_runtime_seal=False
    )
    if manifest.get("version") != MANIFEST_VERSION:
        raise SystemExit("legacy manifest must be upgraded before runtime seal")
    node = Path(manifest["node"])
    backend = Path(manifest["backend"])
    if _stable_regular_file_hash(node, label="node") != manifest.get("nodeHash"):
        raise SystemExit("runtime seal refused: node hash mismatch")
    if _stable_regular_file_hash(backend, label="backend") != manifest.get("backendHash"):
        raise SystemExit("runtime seal refused: backend hash mismatch")
    dependency_hash = _dependency_tree_hash(roots["node_modules"])
    prior_hash = manifest.get("dependencyTreeHash")
    if prior_hash is not None and prior_hash != dependency_hash:
        raise SystemExit("runtime seal refused: dependency tree changed after seal")
    sealed = dict(manifest)
    sealed["dependencyTreeHash"] = dependency_hash
    _atomic_write_text(
        roots["manifest"], json.dumps(sealed, indent=2, sort_keys=True)
    )
    print(json.dumps({
        "sealed": True,
        "account": account,
        "dependencyTreeHash": dependency_hash,
    }, sort_keys=True))
    return 0


@_pin_lifecycle_serialized
@_fabric_lifecycle_serialized()
@_c2_lifecycle_serialized()
def cmd_start(args) -> int:
    account = args.account
    _validate_account_label(account)
    label = f"com.mastermind.studio-direct-private.{account}"
    roots = _build_runtime_roots(account)

    _verify_native_pin_install(account, label, roots)
    _pin_require_start(account, roots)

    info = _lifecycle_inspect(account, label, roots)
    if info is not None:
        path = info.get("path")
        if path and path != str(roots["plist"]):
            raise SystemExit("loaded job is not our exact install")
        if not _info_is_running(info):
            _run(["launchctl", "kickstart", _launchd_target(label)])
        print(json.dumps({"started": True, "already": True, "loaded": True}))
        return 0

    _run(["launchctl", "bootstrap", _launchd_domain(), str(roots["plist"])])
    print(json.dumps({"started": True, "account": account}))
    return 0


def cmd_status(args) -> int:
    account = args.account
    _validate_account_label(account)
    label = f"com.mastermind.studio-direct-private.{account}"
    roots = _build_runtime_roots(account)

    info = _launchd_inspect(label)
    loaded = info is not None
    running = bool(info) and _info_is_running(info)
    pid = info.get("pid") if info and running else None

    manifest = _read_manifest(roots["manifest"], account, label)
    port = manifest.get("port") if manifest else None

    print(
        json.dumps(
            {
                "account": account,
                "label": label,
                "loaded": loaded,
                "running": running,
                "pid": pid,
                "port": port,
            },
            sort_keys=True,
        )
    )
    return 0


@_pin_lifecycle_serialized
@_fabric_lifecycle_serialized()
@_c2_lifecycle_serialized()
def cmd_stop(args) -> int:
    account = args.account
    _validate_account_label(account)
    label = f"com.mastermind.studio-direct-private.{account}"
    roots = _build_runtime_roots(account)

    info = _lifecycle_inspect(account, label, roots)
    if info is None:
        print(json.dumps({"stopped": True, "already": True, "account": account}))
        return 0

    _verify_native_pin_install(
        account, label, roots, require_runtime_seal=False
    )

    if info.get("path") != str(roots["plist"]):
        raise SystemExit("loaded job is not our exact install")

    res = _run(["launchctl", "bootout", _launchd_target(label)], check=False)
    if res.returncode != 0:
        print(json.dumps({"stopped": False, "reason": "bootout failed", "stderr": res.stderr}))
        return 1

    deadline = time.monotonic() + 10
    try:
        while _lifecycle_inspect(account, label, roots) is not None:
            if time.monotonic() >= deadline:
                print(json.dumps({"stopped": False, "reason": "still loaded"}))
                return 1
            time.sleep(0.2)
    except SystemExit as exc:
        if (account in (C2_PAPER_ACCOUNT, C4_PAPER_ACCOUNT)
                or account in FABRIC_BACKEND_ACCOUNTS
                or account in _NATIVE_POOL_PIN_TAILNET_CANONICAL):
            subject = ("Tailnet" if account in _NATIVE_POOL_PIN_TAILNET_CANONICAL
                       else "Fabric" if account in FABRIC_BACKEND_ACCOUNTS else "Paper")
            raise SystemExit(f"{subject} stop: EFFECT_UNKNOWN after bootout; service absence is unverified") from exc
        raise

    print(json.dumps({"stopped": True, "account": account}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="private_service")
    sub = p.add_subparsers(dest="cmd", required=True)

    pin = sub.add_parser("native-pool-pin")
    pin.add_argument("--account", required=True)
    pin.add_argument("--expected-manifest-sha256", required=True)
    pin.add_argument("--successor-bundle", required=True)
    pin.add_argument("--successor-plan-sha256", required=True)
    pin.add_argument("--expected-plan-sha256")
    pin.add_argument("--operation", choices=("preview", "apply", "status", "reconcile"), required=True)
    pin.set_defaults(func=cmd_native_pool_pin)

    fabric = sub.add_parser("fabric-backend-release")
    fabric.add_argument("--account", required=True)
    fabric.add_argument("--expected-manifest-sha256", required=True)
    fabric.add_argument("--release-commit", required=True,
                        help="exact protected merged commit for the fixed Fabric backend release path")
    fabric.add_argument("--backend-sha256", required=True)
    fabric.add_argument("--expected-plan-sha256",
                        help="exact plan digest returned by the reviewed read-only preview; required for apply")
    fabric.add_argument("--preflight-only", action="store_true")
    fabric.set_defaults(func=cmd_fabric_backend_release)

    paper = sub.add_parser("paper-runtime-upgrade")
    paper.add_argument("--account", required=True)
    paper.add_argument("--expected-manifest-sha256", required=True,
                       help="CAS pin for the exact reviewed sealed Paper predecessor")
    paper.add_argument("--preflight-only", action="store_true",
                       help="read-only Paper selection plan; no service or installation changes")
    paper.set_defaults(func=cmd_paper_runtime_upgrade)

    for name in ("stage", "upgrade"):
        s = sub.add_parser(name)
        s.add_argument("--account", required=True)
        s.add_argument("--port", type=int, required=True)
        s.add_argument("--source", required=True)
        s.add_argument("--node", required=True)
        s.add_argument("--backend", required=True)
        s.add_argument("--modern-fabric-protocol", action=argparse.BooleanOptionalAction, default=None,
                       help="opt into stateless MCP for the private Fabric-only shared backend; otherwise preserve verified selection")
        s.add_argument("--fabric-only", action="store_true", help="new Fabric-only installation; no Git, Paper or repository tools")
        s.add_argument("--os-commission-config-sha256", help="opt into the exact root-sealed OS publication grant")
        s.add_argument("--enable-repository-workspaces", action="store_true",
                       help="enable the closed installed repository-workspace consumer")
        if name == "upgrade":
            s.add_argument("--c2-business-fleet-compat", action="store_true",
                           help="exact hash-pinned C2 11-to-12-file gateway compatibility; no new repo grants")
            s.add_argument("--c2-personal-closed-publisher", action="store_true")
            s.add_argument("--c2-business-repository-enrollment", action="store_true",
                           help="explicit closed Macro/Terminal opt-in after reviewed C2 11-to-12 migration; manifest CAS required")
            s.add_argument("--c2-personal-git-timeout-only", action="store_true",
                           help="exact sealed C2 Personal stopped-service Git command budget patch")
            s.add_argument("--publisher-only-fleet-v10", action="store_true",
                           help="preserve the exact sealed enrolled fleet v0.1.10 runtime; patch only two publisher modules")
            s.add_argument("--publisher-expected-manifest-sha256",
                           help="CAS pin for the original sealed, approved fleet manifest")
            s.add_argument("--publisher-preflight-only", action="store_true",
                           help="read-only exact fleet publisher upgrade preflight, even while service is running")
        s.set_defaults(func=globals()[f"cmd_{name}"])

    for name in ("seal-runtime", "start", "status", "stop"):
        sp = sub.add_parser(name)
        sp.add_argument("--account", required=True)
        function_name = "cmd_seal_runtime" if name == "seal-runtime" else f"cmd_{name}"
        sp.set_defaults(func=globals()[function_name])

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
