#!/usr/bin/env python3
"""First-install lifecycle helper for per-account private Studio Direct gateways.

Manages only the private launchd label com.mastermind.studio-direct-private.<account>,
its LaunchAgent plist, and ~/.local/share/studio-direct-mcp/private/<account>.
Never touches the public service, the tailnet-only service, or other accounts.

Subprocess calls go through _run so tests can mock them.
"""
from __future__ import annotations

import argparse
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
PAPER_RUNTIME_REL = Path(".local/share/mastermind-paper/runtime/v11")
PAPER_RUNTIME_SCHEMA = "mastermind.paper_runtime.v1"
PAPER_BRIDGE_SHA256 = "6d28be62b21bff12dc04ae1bdc50f12a4ff55fdb8261bdd6923bac2804fecf7c"
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
    if (fileset not in KNOWN_MANIFEST_FILESETS
            and not (version == MANIFEST_VERSION
                     and fileset == V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR)):
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


def cmd_stage(args) -> int:
    account = args.account
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



def _verify_upgrade_preserves_installed_fleet_capabilities(
    prior: dict, roots: dict, projected: dict,
) -> None:
    """Fail closed before any writes when an enrolled v0.1.10 fleet seat would lose service.

    This is an explicit migration guard, NOT permission to broaden historical
    filesets or treat an approved old manifest as permission to downgrade it.
    A separately reviewed compatibility source must retain both fleet modules
    and every configured fleet route, scheduling cap and fleet-status binding.
    """
    if frozenset(prior["files"]) != V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR:
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
    # Preserve the first-stage legacy install path, and admit only the exact
    # already-installed PR #1535 closed publisher for an index-sync hotfix.
    # The manifest is sealed first; no caller may choose a publisher identity.
    original_publisher = old_config.get("gitPublish")
    expected_closed = _typed_git_config(user_root, closed_repositories=True)
    if original_publisher == _typed_git_config(user_root):
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
    config_bytes = json.dumps(new_config, indent=2, sort_keys=True).encode("utf-8")
    names = tuple(FLEET_V10_PUBLISHER_PATCH_SHA256)
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
                or hashlib.sha256(modified).hexdigest() != FLEET_V10_PUBLISHER_PATCH_SHA256[name]):
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


def cmd_upgrade(args) -> int:
    account = args.account
    _validate_account_label(account)
    label = f"com.mastermind.studio-direct-private.{account}"
    host = "127.0.0.1"

    if not os.path.isabs(args.source):
        raise SystemExit("--source must be absolute")
    source = Path(args.source)
    if source.is_symlink() or not source.is_dir():
        raise SystemExit(f"source dir invalid: {source}")
    _check_source_files(source)
    node_abs = _resolve_abs("--node", args.node)
    backend_abs = _resolve_abs("--backend", args.backend)
    port = int(args.port)
    _validate_port(port)

    roots = _build_runtime_roots(account)
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
    if frozenset(prior["files"]) == V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR:
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


def cmd_seal_runtime(args) -> int:
    account = args.account
    _validate_account_label(account)
    label = f"com.mastermind.studio-direct-private.{account}"
    roots = _build_runtime_roots(account)
    if _launchd_inspect(label) is not None:
        raise SystemExit("refusing runtime seal while service is loaded; stop first")
    manifest = _verify_staged_install(
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


def cmd_start(args) -> int:
    account = args.account
    _validate_account_label(account)
    label = f"com.mastermind.studio-direct-private.{account}"
    roots = _build_runtime_roots(account)

    _verify_staged_install(account, label, roots)

    info = _launchd_inspect(label)
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


def cmd_stop(args) -> int:
    account = args.account
    _validate_account_label(account)
    label = f"com.mastermind.studio-direct-private.{account}"
    roots = _build_runtime_roots(account)

    info = _launchd_inspect(label)
    if info is None:
        print(json.dumps({"stopped": True, "already": True, "account": account}))
        return 0

    _verify_staged_install(
        account, label, roots, require_runtime_seal=False
    )

    if info.get("path") != str(roots["plist"]):
        raise SystemExit("loaded job is not our exact install")

    res = _run(["launchctl", "bootout", _launchd_target(label)], check=False)
    if res.returncode != 0:
        print(json.dumps({"stopped": False, "reason": "bootout failed", "stderr": res.stderr}))
        return 1

    deadline = time.monotonic() + 10
    while _launchd_inspect(label) is not None:
        if time.monotonic() >= deadline:
            print(json.dumps({"stopped": False, "reason": "still loaded"}))
            return 1
        time.sleep(0.2)

    print(json.dumps({"stopped": True, "account": account}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="private_service")
    sub = p.add_subparsers(dest="cmd", required=True)

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
