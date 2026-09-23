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

# Paper Desktop capability is a gateway-local consumer of the separately reviewed
# guarded adapter in PR #585. The private gateway never accepts these paths or
# hashes from ChatGPT.
# Runtime generations are immutable from the perspective of installed seats. A new
# bridge SHA gets a new directory so one-seat canaries cannot invalidate another
# seat that still pins the previous bridge bytes.
PAPER_RUNTIME_REL = Path(".local/share/mastermind-paper/runtime/v2")
PAPER_RUNTIME_SCHEMA = "mastermind.paper_runtime.v1"
PAPER_BRIDGE_SHA256 = "83e36b0bcd0acabbf5dd6ace5b708e5797a52e7db732e8dbbf848ded781c231d"
PAPER_COMMAND_TIMEOUT_MS = 70_000
PAPER_APP_REL = Path("Applications/Paper.app")

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
    "output-budget.mjs",
    "git-publish.mjs",
    "paper-design.mjs",
    "private-tunnel-auth.mjs",
    "private-tunnel-gateway.mjs",
    "package.json",
    "package-lock.json",
)

# Historical installs are admitted only through exact known file sets. The
# immediately preceding v0.1.5 install has every current file except the new
# Paper capability module; earlier generations also predate output paging and
# typed Git.
LEGACY_STAGE_FILES_V3 = tuple(name for name in STAGE_FILES if name != "paper-design.mjs")
LEGACY_STAGE_FILES_V2 = tuple(name for name in LEGACY_STAGE_FILES_V3 if name != "output-budget.mjs")
LEGACY_STAGE_FILES_V1 = tuple(name for name in LEGACY_STAGE_FILES_V2 if name != "git-publish.mjs")
KNOWN_MANIFEST_FILESETS = frozenset(
    (
        frozenset(STAGE_FILES),
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


def _typed_git_config(user_root: Path) -> dict:
    return {
        "enabled": True,
        "workspaceCli": str(user_root / TYPED_GIT_WORKSPACE_CLI_REL),
        "gitBinary": TYPED_GIT_BINARY,
        "sourceRepository": str(user_root / TYPED_GIT_SOURCE_REPOSITORY_REL),
        "allowedRemoteUrls": [TYPED_GIT_REMOTE_URL],
        "commandTimeoutMs": 15_000,
        "pushTimeoutMs": 60_000,
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


def _build_config(
    account: str,
    host: str,
    port: int,
    node_abs: Path,
    backend_abs: Path,
    state_dir: Path,
    user_root: Path,
) -> dict:
    # publicUrl is omitted: the private adapter rejects a public origin.
    return {
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
        "gitPublish": _typed_git_config(user_root),
        "paperDesign": _paper_design_config(user_root),
    }


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
    if not isinstance(files, dict) or frozenset(files) not in KNOWN_MANIFEST_FILESETS:
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
    # The Paper-owned immutable runtime must exist and match before this
    # lifecycle writes a config/plist that advertises the Paper capability.
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
    # Upgrade is still pre-effect here. Refuse before replacing any staged
    # source/config if the Paper generation is missing or no longer exact.
    _verify_paper_runtime(_user_root())

    return _write_install(
        source, node_abs, backend_abs, account, label, host, port, roots,
        result_key="upgraded", previous_source=str(prior.get("source") or ""),
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
