#!/usr/bin/env python3
"""Canonical attended-session workspace route for Mastermind hosts.

This CLI is a thin adapter over ``control_plane.executive_workspace``.  It does
not own lifecycle state.  The host owns the source repo and workspace root; the
caller supplies only an operation identity, exact base SHA, and a closed lane.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
from contextlib import contextmanager
import hashlib
import json
import os
import plistlib
import shutil
import shlex
import stat
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from xml.parsers.expat import ExpatError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from control_plane.executive_workspace import (  # noqa: E402
    WorkspaceError,
    LinkedWorkspaceReleaseEffectUnknown,
    inspect_linked_worktree,
    prepare_linked_worktree,
    release_linked_worktree,
)

SCHEMA = "mastermind.workspace_cli/v1"
ALLOWED_LANES = {"web", "sol", "manual", "review"}


def _source_repo() -> Path:
    configured = os.environ.get("MASTERMIND_SOURCE_REPO")
    return Path(configured).expanduser().resolve() if configured else REPO_ROOT


def _workspace_root() -> Path:
    configured = os.environ.get("MASTERMIND_AGENT_WORKSPACE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    external = Path("/Volumes/Mastermind/agent-workspaces")
    if external.parent.is_dir():
        return external.resolve()
    return (Path.home() / ".mastermind" / "agent-workspaces").resolve()



# Installation configuration for this existing allocator, not a second registry.
# Only the installed wrapper supplies paths. Public callers select closed aliases.
_REPOSITORY_SCHEMA = "mastermind.workspace_repositories/v1"
_REPOSITORIES = {
    "mastermind": ("mastermindx-market-intelligence/Mastermind", "master"),
    "macro": ("mastermindx-market-intelligence/macro", "main"),
    "terminal": ("mastermindx-market-intelligence/mastermind-terminal", "master"),
}
_REPOSITORY_CONFIG_ENV = "MASTERMIND_WORKSPACE_REPOSITORIES"


def _repository_git(source: Path, *arguments: str) -> str:
    """Bounded local observation; never fetch, write config, or create metadata."""
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update({"PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin",
                        "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_LAZY_FETCH": "1",
                        "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0"})
    try:
        result = subprocess.run(["git", "-C", str(source), *arguments],
                                env=environment, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=10, check=False)
        if result.returncode or len(result.stdout.encode("utf-8")) > 65536:
            raise ValueError("repository observation failed")
        return result.stdout.strip()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise WorkspaceError("REPOSITORY_SOURCE_UNAVAILABLE: local Git observation failed") from exc


def _repository_path(value: object) -> Path:
    if (type(value) is not str or not value or len(value) > 4096
            or any(ord(character) < 32 for character in value)
            or not Path(value).is_absolute()):
        raise WorkspaceError("REPOSITORY_BINDING_INVALID: expected an absolute host-owned path")
    return Path(value)


def _inspect_repository_binding(alias: str, value: object) -> dict[str, str]:
    if alias not in _REPOSITORIES or type(value) is not dict or set(value) != {"source_repository", "common_git_dir"}:
        raise WorkspaceError("REPOSITORY_BINDING_INVALID: repository fields are not closed")
    source = _repository_path(value["source_repository"])
    expected_common = _repository_path(value["common_git_dir"])
    try:
        if source.resolve(strict=True) != source or not source.is_dir():
            raise ValueError("source identity changed")
        if expected_common.resolve(strict=True) != expected_common or not expected_common.is_dir():
            raise ValueError("common directory changed")
        top = Path(_repository_git(source, "rev-parse", "--show-toplevel")).resolve(strict=True)
        common = Path(_repository_git(source, "rev-parse", "--git-common-dir"))
        common = (common if common.is_absolute() else source / common).resolve(strict=True)
        if top != source or common != expected_common:
            raise ValueError("Git identity changed")
    except (OSError, ValueError, RuntimeError) as exc:
        raise WorkspaceError("REPOSITORY_SOURCE_CHANGED: installed Git identity no longer matches") from exc
    repository, default_branch = _REPOSITORIES[alias]
    remote = f"https://github.com/{repository}.git"
    # Check complete effective fetch AND push destinations, including rewrites.
    # Multiple or noncanonical origins cannot be admitted as one bound target.
    for direction in ((), ("--push",)):
        if _repository_git(source, "remote", "get-url", *direction, "--all", "origin") != remote:
            raise WorkspaceError("REPOSITORY_REMOTE_MISMATCH: origin is not the installed canonical repository")
    return {"alias": alias, "repository_full_name": repository,
            "default_branch": default_branch, "remote_url": remote,
            "source_repository": str(source), "common_git_dir": str(common)}


def _parse_repository_bindings(raw: str) -> dict[str, object]:
    if not raw:
        return {}
    try:
        if len(raw.encode("utf-8")) > 32768:
            raise ValueError("repository configuration exceeds bound")
        value = json.loads(raw, object_pairs_hook=_unique_policy_pairs)
        if (type(value) is not dict or set(value) != {"schema", "repositories"}
                or value["schema"] != _REPOSITORY_SCHEMA
                or type(value["repositories"]) is not dict
                or "mastermind" not in value["repositories"]
                or not set(value["repositories"]).issubset(_REPOSITORIES)):
            raise ValueError("repository configuration is not closed")
        return value["repositories"]
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise WorkspaceError("REPOSITORY_BINDING_INVALID: installed repository configuration is invalid") from exc



def _installed_repository_bindings() -> dict[str, object]:
    return _parse_repository_bindings(os.environ.get(_REPOSITORY_CONFIG_ENV, ""))


def _read_installed_launcher(
    launcher: Path | None,
) -> tuple[bytes | None, dict[str, int] | None]:
    """Read one trusted wrapper snapshot without executing or following it."""
    if launcher is None:
        return None, None
    descriptor = -1
    try:
        if not launcher.exists() and not launcher.is_symlink():
            return None, None
        descriptor = os.open(launcher, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                             | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid not in {0, os.geteuid()}
                or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) & 0o022
                or not 0 < before.st_size <= 65536):
            raise ValueError("prior launcher identity is unsafe")
        raw = os.read(descriptor, before.st_size + 1)
        after = os.fstat(descriptor)
        named = launcher.lstat()
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
                  "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(raw) != before.st_size or any(getattr(before, key) != getattr(item, key)
                for item in (after, named) for key in fields):
            raise ValueError("prior launcher changed while reading")
        text = raw.decode("utf-8")
        if not text.startswith("#!/bin/sh\n") or "mastermind_workspace.py" not in text:
            raise ValueError("prior launcher is not a workspace wrapper")
        return raw, {key: getattr(before, key) for key in fields}
    except (OSError, ValueError, UnicodeError) as exc:
        raise WorkspaceError("REPOSITORY_BINDING_INVALID: prior installed bindings cannot be preserved safely") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _launcher_bindings_from_text(text: str) -> dict[str, object]:
    marker = "export " + _REPOSITORY_CONFIG_ENV + "="
    lines = [line for line in text.splitlines() if line.startswith(marker)]
    if not lines:
        return {}  # The exact pre-repository wrapper remains compatible.
    if len(lines) != 1:
        raise ValueError("prior wrapper has ambiguous bindings")
    values = shlex.split(lines[0], posix=True)
    if len(values) != 2 or values[0] != "export" or not values[1].startswith(_REPOSITORY_CONFIG_ENV + "="):
        raise ValueError("prior wrapper binding is not a shell literal")
    retained = _parse_repository_bindings(values[1].split("=", 1)[1])
    if not retained:
        raise ValueError("prior wrapper has an empty repository binding")
    return retained


def _retained_installer_bindings(launcher: Path | None) -> dict[str, object]:
    """Read the prior wrapper's literal; never execute/source an old shell file."""
    raw, _identity = _read_installed_launcher(launcher)
    if raw is None:
        return {}
    try:
        return _launcher_bindings_from_text(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise WorkspaceError("REPOSITORY_BINDING_INVALID: prior installed bindings cannot be preserved safely") from exc


def installation_launcher_snapshot(launcher: Path) -> dict[str, object]:
    """Fence selector publication with the same verified bytes and file identity."""
    raw, identity = _read_installed_launcher(launcher)
    if raw is None:
        return {"exists": False}
    return {"exists": True, "sha256": hashlib.sha256(raw).hexdigest(), "identity": identity}


def _shell_literal(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _launcher_payload_selectors(text: str) -> dict[str, tuple[str, str]]:
    interpreters = {
        "$MASTERMIND_PYTHON": '"$MASTERMIND_PYTHON"',
        "/opt/homebrew/bin/python3": "/opt/homebrew/bin/python3",
        "python3": "python3",
    }
    rows: dict[str, tuple[str, str]] = {}
    for line in text.splitlines(keepends=True):
        if not line.lstrip().startswith("exec "):
            continue
        words = shlex.split(line.strip(), posix=True)
        if (len(words) != 4 or words[0] != "exec" or words[1] not in interpreters
                or words[1] in rows or words[3] != "$@"):
            raise ValueError("unsupported or duplicate payload selector")
        path = Path(words[2])
        if (not path.is_absolute() or ".." in path.parts
                or path.name != "mastermind_workspace.py" or path.parent.name != "scripts"):
            raise ValueError("payload reference is outside the installed structure")
        indent = line[:len(line) - len(line.lstrip())]
        expected = (indent + "exec " + interpreters[words[1]] + " "
                    + _shell_literal(words[2]) + ' "$@"'
                    + ("\n" if line.endswith("\n") else ""))
        if line != expected:
            raise ValueError("payload selector is not the supported shell literal")
        rows[words[1]] = (line, words[2])
    if set(rows) != set(interpreters) or len({row[1] for row in rows.values()}) != 1:
        raise ValueError("three selectors must name one payload generation")
    return rows


def _pool_preserving_launcher(previous: bytes, generated: bytes) -> bytes:
    """Upgrade payload references only; the incumbent router keeps placement."""
    old_text, new_text = previous.decode("utf-8"), generated.decode("utf-8")
    if "mmx_workspace_router.py" not in old_text and "pool_selection" not in old_text:
        return generated
    try:
        old_bindings = _launcher_bindings_from_text(old_text)
        if not old_bindings or old_bindings != _launcher_bindings_from_text(new_text):
            raise ValueError("pool upgrade cannot change repository bindings")
        old_rows = _launcher_payload_selectors(old_text)
        _validate_pool_launcher(old_text, old_rows)
        new_rows = _launcher_payload_selectors(new_text)
        result = old_text
        for interpreter, (line, old_path) in old_rows.items():
            new_path = new_rows[interpreter][1]
            changed = line.replace(_shell_literal(old_path), _shell_literal(new_path), 1)
            if result.count(line) != 1:
                raise ValueError("payload selector is ambiguous")
            result = result.replace(line, changed, 1)
        return result.encode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise WorkspaceError("LAUNCHER_UPGRADE_REFUSED: incumbent pool routing cannot be preserved safely") from exc


def _validate_pool_launcher(text: str, selectors: dict[str, tuple[str, str]]) -> None:
    """Recognize the enrolled router wrapper, without executing its shell."""
    commands = [line.strip() for line in text.splitlines()
                if line.strip() and not line.lstrip().startswith("#")]
    if len(commands) != 14:
        raise ValueError("pool wrapper has unexpected or overriding commands")
    assignment = commands[1]
    prefix, suffix = 'pool_selection="$(', ')" || exit 66'
    if not assignment.startswith(prefix) or not assignment.endswith(suffix):
        raise ValueError("pool router invocation is not the supported form")
    invocation = assignment[len(prefix):-len(suffix)]
    words = shlex.split(invocation, posix=True)
    router = Path.home() / ".local/lib/mastermind/worktree-storage/mmx_workspace_router.py"
    if (len(words) != 3 or words[0] not in {"/usr/bin/python3", "/opt/homebrew/bin/python3"}
            or words[1] != str(router) or words[2] != "$@" or not invocation.endswith('"$@"')):
        raise ValueError("pool router identity or argument forwarding changed")
    source = shlex.split(commands[5], posix=True)
    bindings = _launcher_bindings_from_text(text)
    expected_source = "MASTERMIND_SOURCE_REPO=" + bindings["mastermind"]["source_repository"]
    if source != ["export", expected_source]:
        raise ValueError("pool source export disagrees with its repository binding")
    expected = [
        "set -eu", assignment,
        'case "$pool_selection" in *\'|\'*) ;; *) echo \'pool router returned no volume\' >&2; exit 66;; esac',
        'export MASTERMIND_AGENT_WORKSPACE_ROOT="' + "$" + '{pool_selection%%|*}"',
        'export MASTERMIND_WORKSPACE_STORAGE_POLICY="' + "$" + '{pool_selection#*|}"',
        commands[5], commands[6],
        'if [ -n "' + "$" + '{MASTERMIND_PYTHON:-}" ]; then',
        selectors["$MASTERMIND_PYTHON"][0].strip(),
        "elif [ -x /opt/homebrew/bin/python3 ]; then",
        selectors["/opt/homebrew/bin/python3"][0].strip(),
        "else", selectors["python3"][0].strip(), "fi",
    ]
    if (commands != expected
            or not commands[6].startswith("export " + _REPOSITORY_CONFIG_ENV + "=")):
        raise ValueError("pool routing exports or conditional selectors changed")


@contextmanager
def _installation_publication_lock(target: Path):
    """One bounded installer lock; no queue, retry loop or separate owner state."""
    lock = target.with_name(target.name + ".install.lock")
    descriptor = -1
    held = False
    try:
        descriptor = os.open(
            lock, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0), 0o600,
        )
        observed = os.fstat(descriptor)
        named = lock.lstat()
        if (not stat.S_ISREG(observed.st_mode) or observed.st_uid != os.geteuid()
                or observed.st_nlink != 1 or observed.st_size != 0
                or stat.S_IMODE(observed.st_mode) & 0o077
                or (observed.st_dev, observed.st_ino) != (named.st_dev, named.st_ino)):
            raise WorkspaceError("LAUNCHER_INSTALL_LOCK_INVALID: installer lock identity is unsafe")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WorkspaceError("LAUNCHER_INSTALL_BUSY: another installer holds publication") from exc
        held = True
        named = lock.lstat()
        if (observed.st_dev, observed.st_ino) != (named.st_dev, named.st_ino):
            raise WorkspaceError("LAUNCHER_INSTALL_LOCK_INVALID: installer lock was replaced")
        yield
    finally:
        if descriptor >= 0:
            if held:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
    # Keep the zero-byte lock inode stable across installs; unlinking it races waiters.


def _prepare_installation_payload(source: Path, payload: Path) -> None:
    """Stage the existing inventory once; selected generations are never rewritten."""
    relatives = [
        "scripts/mastermind_workspace.py", "control_plane/executive_workspace.py",
        "control_plane/__init__.py",
    ] + sorted(str(path.relative_to(source)) for path in (source / "common").glob("*.py"))
    if "common/__init__.py" not in relatives:
        raise WorkspaceError("PAYLOAD_INVALID: the accepted payload inventory is incomplete")
    expected = {
        relative: ((source / relative).read_bytes(),
                   0o755 if relative == "scripts/mastermind_workspace.py" else 0o644)
        for relative in relatives
    }
    payload.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        payload.mkdir()
        created = True
    except FileExistsError:
        pass
    if payload.is_symlink() or not payload.is_dir():
        raise WorkspaceError("PAYLOAD_INVALID: payload generation is not a direct directory")
    if created:
        for directory in ("scripts", "control_plane", "common"):
            (payload / directory).mkdir()
        for relative, (content, mode) in expected.items():
            with (payload / relative).open("xb") as stream:
                os.fchmod(stream.fileno(), mode)
                stream.write(content)
    try:
        for directory in ("scripts", "control_plane", "common"):
            path = payload / directory
            if path.is_symlink() or not path.is_dir():
                raise ValueError("payload directory is indirect or missing")
        actual = {str(path.relative_to(payload)) for path in payload.rglob("*.py")}
        if actual != set(expected):
            raise ValueError("payload inventory differs from accepted source")
        for relative, (content, mode) in expected.items():
            path = payload / relative
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid not in {0, os.geteuid()}
                    or stat.S_IMODE(info.st_mode) != mode or path.read_bytes() != content):
                raise ValueError("payload bytes or mode differ from accepted source")
    except (OSError, ValueError) as exc:
        raise WorkspaceError("PAYLOAD_MISMATCH: retain the generation and reconcile; do not overwrite it") from exc


def publish_installation_launcher(
    target: Path, generated: Path, expected_snapshot: dict[str, object],
    *, source: Path | None = None, payload: Path | None = None,
) -> None:
    """Serialize payload qualification and selector publication through one owner."""
    if (source is None) != (payload is None):
        raise WorkspaceError("PAYLOAD_INVALID: source and generation must be supplied together")
    with _installation_publication_lock(target):
        if installation_launcher_snapshot(target) != expected_snapshot:
            raise WorkspaceError("LAUNCHER_CHANGED: installation preimage is no longer current")
        if source is not None:
            _prepare_installation_payload(source, payload)
        _publish_installation_launcher_unlocked(target, generated, expected_snapshot)


def _publish_installation_launcher_unlocked(
    target: Path, generated: Path, expected_snapshot: dict[str, object],
) -> None:
    """Publish one fenced selector; never roll back over a newer writer."""
    if installation_launcher_snapshot(target) != expected_snapshot:
        raise WorkspaceError("LAUNCHER_CHANGED: installation preimage is no longer current")
    previous, _identity = _read_installed_launcher(target)
    candidate, _candidate_identity = _read_installed_launcher(generated)
    if candidate is None:
        raise WorkspaceError("LAUNCHER_UPGRADE_REFUSED: generated launcher is missing")
    if previous is not None:
        candidate = _pool_preserving_launcher(previous, candidate)
    if candidate == previous:
        return
    descriptor, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o755)
            stream.write(candidate)
            stream.flush()
            os.fsync(stream.fileno())
        if installation_launcher_snapshot(target) != expected_snapshot:
            raise WorkspaceError("LAUNCHER_CHANGED: installation preimage is no longer current")
        os.replace(temporary, target)
        temporary = None
        try:
            readback, _identity = _read_installed_launcher(target)
            if readback != candidate:
                raise ValueError("installed bytes differ")
        except (OSError, ValueError, WorkspaceError) as exc:
            raise WorkspaceError("LAUNCHER_PUBLICATION_UNKNOWN: reconcile the installed selector before retry") from exc
    finally:
        if temporary is not None:
            os.unlink(temporary)


def _selected_repository(alias: str, *, explicit: bool) -> Path:
    bindings = _installed_repository_bindings()
    if not bindings and alias == "mastermind" and not explicit:
        # Preserve the unconfigured legacy administrative/test seam. Installed
        # launchers always pin the new configuration and cannot take this path.
        return _source_repo()
    if alias not in bindings:
        raise WorkspaceError("REPOSITORY_NOT_ENROLLED: requested repository is not installed on this host")
    return Path(_inspect_repository_binding(alias, bindings[alias])["source_repository"])


def _repository_workspace_root(root: Path, alias: str) -> Path:
    selected = root if alias == "mastermind" else root / alias
    # Refuse a substituted per-repository directory before the constructor runs.
    if selected.resolve() != selected:
        raise WorkspaceError("REPOSITORY_SOURCE_CHANGED: repository workspace root is indirect")
    return selected


def _repository_discovery(root: Path) -> dict[str, object]:
    bindings = _installed_repository_bindings()
    rows: list[dict[str, object]] = []
    for alias, (repository, branch) in _REPOSITORIES.items():
        row: dict[str, object] = {"alias": alias, "repository_full_name": repository,
                                  "default_branch": branch, "state": "NOT_ENROLLED"}
        if alias in bindings:
            try:
                row.update(_inspect_repository_binding(alias, bindings[alias]))
                row["workspace_root"] = str(_repository_workspace_root(root, alias))
                row["state"] = "READY"
            except WorkspaceError as exc:
                row.update(state="UNAVAILABLE", code=str(exc).split(":", 1)[0])
        rows.append(row)
    return {"schema": _REPOSITORY_SCHEMA, "repositories": rows,
            "admission_check_only": True, "workspace_created": False}


def installation_repository_bindings(
    source: Path, registrations: list[str], *, installed_launcher: Path | None = None,
) -> dict[str, object]:
    """Validate new selections and retain prior host bindings on normal upgrades."""
    bindings = _retained_installer_bindings(installed_launcher)
    selected = {"mastermind": source.resolve()}
    explicit: set[str] = set()
    for registration in registrations:
        alias, separator, raw_path = registration.partition("=")
        if not separator or alias not in _REPOSITORIES or alias == "mastermind" or alias in explicit:
            raise WorkspaceError("REPOSITORY_BINDING_INVALID: duplicate or unsupported installer target")
        explicit.add(alias)
        selected[alias] = _repository_path(raw_path).resolve()
    for alias, repository in selected.items():
        common = Path(_repository_git(repository, "rev-parse", "--git-common-dir"))
        common = (common if common.is_absolute() else repository / common).resolve()
        candidate = {"source_repository": str(repository), "common_git_dir": str(common)}
        if alias == "mastermind" and alias in bindings and bindings[alias] != candidate:
            raise WorkspaceError("REPOSITORY_SOURCE_CHANGED: reinstall would change the incumbent Mastermind binding")
        bindings[alias] = candidate
    for alias, candidate in bindings.items():
        _inspect_repository_binding(alias, candidate)
    if len({value["common_git_dir"] for value in bindings.values()}) != len(bindings):
        raise WorkspaceError("REPOSITORY_BINDING_INVALID: independent repositories share Git metadata")
    return {"schema": _REPOSITORY_SCHEMA, "repositories": bindings}


_STORAGE_POLICY_FIELDS = frozenset(
    {"version", "mount_point", "volume_uuid", "root", "min_free_bytes"}
)
_STORAGE_POLICY_METADATA_FIELDS = frozenset({"_why", "_pool_note", "overflow_volumes", "internal_fallback"})
_STORAGE_DISABLED_FALLBACK_FIELDS = frozenset({"enabled", "mount_point", "root", "min_free_bytes", "_why"})
_STORAGE_POLICY_MAX_BYTES = 16 * 1024
_STORAGE_POLICY_MAX_RATIONALE_BYTES = 8 * 1024
_STORAGE_POLICY_MAX_OVERFLOW_VOLUMES = 8
_STORAGE_OVERFLOW_FIELDS = frozenset({"mount_point", "volume_uuid", "root", "min_free_bytes"})


def _unique_policy_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate policy field")
        result[key] = value
    return result


def _read_storage_policy(path: Path) -> tuple[dict[str, object], str]:
    """Read the existing host policy without following a substituted file."""
    descriptor = -1
    try:
        if not path.is_absolute():
            raise ValueError("policy path is not absolute")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid not in {0, os.geteuid()}
            or stat.S_IMODE(before.st_mode) & 0o022
            or not 0 < before.st_size <= _STORAGE_POLICY_MAX_BYTES
        ):
            raise ValueError("policy file identity is invalid")
        chunks: list[bytes] = []
        remaining = _STORAGE_POLICY_MAX_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        named = path.lstat()
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
                  "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(payload) != before.st_size or any(
            getattr(before, key) != getattr(observed, key)
            for observed in (after, named) for key in fields
        ):
            raise ValueError("policy changed while reading")
        data = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_policy_pairs)
        if (
            not isinstance(data, dict)
            or not _STORAGE_POLICY_FIELDS.issubset(data)
            or not set(data).issubset(_STORAGE_POLICY_FIELDS | _STORAGE_POLICY_METADATA_FIELDS)
        ):
            raise ValueError("policy fields are not closed")
        for note_key in ("_why", "_pool_note"):
            if note_key not in data:
                continue
            rationale = data[note_key]
            if (
                type(rationale) is not str
                or not rationale
                or len(rationale.encode("utf-8")) > _STORAGE_POLICY_MAX_RATIONALE_BYTES
            ):
                raise ValueError("policy rationale metadata is invalid")
        if "overflow_volumes" in data:
            # The existing SSD helper owns pool selection. This CLI remains bound
            # to the enrolled primary root; validated pool metadata grants no fallback.
            overflow = data["overflow_volumes"]
            if type(overflow) is not list or len(overflow) > _STORAGE_POLICY_MAX_OVERFLOW_VOLUMES:
                raise ValueError("overflow volume metadata is invalid")
            for member in overflow:
                if type(member) is not dict or set(member) != _STORAGE_OVERFLOW_FIELDS:
                    raise ValueError("overflow volume fields are not closed")
                for key in ("mount_point", "root"):
                    value = member[key]
                    if type(value) is not str or "\x00" in value or not Path(value).is_absolute():
                        raise ValueError("invalid overflow storage path")
                identity = member["volume_uuid"]
                if type(identity) is not str or str(uuid.UUID(identity)).lower() != identity.lower():
                    raise ValueError("invalid overflow volume identity")
                minimum = member["min_free_bytes"]
                if type(minimum) is not int or not 0 <= minimum < 2**63:
                    raise ValueError("invalid overflow storage floor")
        if "internal_fallback" in data:
            # The existing host storage owner may retain a disabled fallback.
            # This metadata never selects storage or grants an internal fallback.
            fallback = data["internal_fallback"]
            if (type(fallback) is not dict or set(fallback) != _STORAGE_DISABLED_FALLBACK_FIELDS
                    or fallback["enabled"] is not False):
                raise ValueError("internal fallback metadata must be closed and disabled")
            for key in ("mount_point", "root"):
                value = fallback[key]
                if (type(value) is not str or len(value.encode("utf-8")) > 4096
                        or any(char in value for char in ("\x00", "\n", "\r"))
                        or not Path(value).is_absolute() or ".." in Path(value).parts):
                    raise ValueError("invalid disabled fallback path")
            mount, root = Path(fallback["mount_point"]), Path(fallback["root"])
            if root == mount or not root.is_relative_to(mount):
                raise ValueError("disabled fallback root escapes its declared mount")
            minimum = fallback["min_free_bytes"]
            if type(minimum) is not int or not 0 < minimum < 2**63:
                raise ValueError("invalid disabled fallback floor")
            rationale = fallback["_why"]
            if (type(rationale) is not str or not rationale
                    or len(rationale.encode("utf-8")) > _STORAGE_POLICY_MAX_RATIONALE_BYTES):
                raise ValueError("invalid disabled fallback rationale")
        if type(data["version"]) is not int or data["version"] != 1:
            raise ValueError("unsupported policy version")
        minimum = data["min_free_bytes"]
        if type(minimum) is not int or not 0 < minimum < 2**63:
            raise ValueError("invalid storage floor")
        for key in ("mount_point", "root"):
            value = data[key]
            if not isinstance(value, str) or "\x00" in value or not Path(value).is_absolute():
                raise ValueError("invalid storage path")
        identity = data["volume_uuid"]
        if not isinstance(identity, str) or str(uuid.UUID(identity)).lower() != identity.lower():
            raise ValueError("invalid volume identity")
        return data, hashlib.sha256(payload).hexdigest()
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        raise WorkspaceError("STORAGE_POLICY_INVALID: enrolled host policy cannot be trusted") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _volume_identity(mount: Path) -> dict[str, object]:
    """Observe macOS volume identity; do not infer UUIDs on other platforms."""
    if sys.platform != "darwin":
        raise WorkspaceError("STORAGE_IDENTITY_UNSUPPORTED: configured volume requires a qualified host probe")
    try:
        result = subprocess.run(
            ["/usr/sbin/diskutil", "info", "-plist", str(mount)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"},
            timeout=5, check=False,
        )
        if result.returncode != 0 or len(result.stdout) > 1024 * 1024:
            raise ValueError("volume probe failed")
        value = plistlib.loads(result.stdout)
        if not isinstance(value, dict):
            raise ValueError("volume probe is not an object")
        return value
    except (OSError, ValueError, plistlib.InvalidFileException, ExpatError, subprocess.SubprocessError) as exc:
        raise WorkspaceError("STORAGE_OBSERVATION_FAILED: volume identity unavailable") from exc


def _storage_free_bytes(mount: Path) -> int:
    return shutil.disk_usage(mount).free


def _storage_status(root: Path) -> dict[str, object]:
    """One current admission observation, never a disk reservation or lease."""
    policy_path = os.environ.get("MASTERMIND_WORKSPACE_STORAGE_POLICY", "")
    observation: dict[str, object] = {
        "schema_version": "mastermind.workspace_storage/v1",
        "observed_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "admission_check_only": True,
        "state": "NOT_CONFIGURED", "admission_allowed": True,
        "free_bytes": None, "min_free_bytes": None, "policy_sha256": None,
    }
    if not policy_path:
        return observation
    policy, digest = _read_storage_policy(Path(policy_path))
    try:
        mount = Path(str(policy["mount_point"]))
        if mount.is_symlink() or not mount.is_dir():
            raise WorkspaceError("STORAGE_MOUNT_UNAVAILABLE: enrolled volume is not mounted")
        mount = mount.resolve()
        configured_root = Path(str(policy["root"])).resolve()
        if configured_root != root or root == mount or not root.is_relative_to(mount):
            raise WorkspaceError("STORAGE_ROOT_MISMATCH: host policy does not name the selected workspace root")
        before = mount.stat()
        anchor = root
        while not anchor.exists() and anchor != mount:
            anchor = anchor.parent
        if not anchor.is_dir() or anchor.stat().st_dev != before.st_dev:
            raise WorkspaceError("STORAGE_ROOT_MISMATCH: workspace root is on another filesystem")
        observed = _volume_identity(mount)
        observed_uuid = observed.get("VolumeUUID")
        if (
            # APFS Data is a diskutil mount even though pathlib.is_mount()
            # reports false across the macOS firmlink. Exact native
            # MountPoint/UUID plus Writable provide the positive witness.
            observed.get("Mounted", True) is not True
            or observed.get("MountPoint") != str(mount)
            or not isinstance(observed_uuid, str)
            or observed_uuid.lower() != str(policy["volume_uuid"]).lower()
        ):
            raise WorkspaceError("STORAGE_VOLUME_IDENTITY_MISMATCH: mounted volume is not the enrolled volume")
        if observed.get("Writable") is not True:
            raise WorkspaceError("STORAGE_VOLUME_READ_ONLY: writable volume is not proven")
        free = _storage_free_bytes(mount)
        after = mount.stat()
        if type(free) is not int or free < 0 or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise WorkspaceError("STORAGE_OBSERVATION_FAILED: storage observation is not stable")
        minimum = int(policy["min_free_bytes"])
        observation.update({
            "state": "READY" if free >= minimum else "LOW_SPACE",
            "admission_allowed": free >= minimum,
            "free_bytes": free, "min_free_bytes": minimum,
            "policy_sha256": digest,
            "mount_point": str(mount), "workspace_root": str(root),
            "volume_uuid": observed_uuid,
        })
        return observation
    except WorkspaceError:
        raise
    except (OSError, ValueError, RuntimeError) as exc:
        raise WorkspaceError("STORAGE_OBSERVATION_FAILED: storage readiness unavailable") from exc


def _branch(operation_id: str, lane: str) -> str:
    operation = operation_id.strip().lower()
    if lane == "sol":
        return f"sol/{operation}"
    return f"sol/{lane}-{operation}"


def _workspace_path(root: Path, lane: str, operation_id: str) -> Path:
    return root / lane / operation_id.strip().lower()


def _emit(action: str, receipt: object, *, effect: str, repository: str | None = None) -> int:
    body = receipt.to_dict() if hasattr(receipt, "to_dict") else receipt
    print(
        json.dumps(
            {
                "schema_version": SCHEMA if repository is None else "mastermind.workspace_cli/v2",
                "action": action,
                "effect": effect,
                "receipt": body,
                **({"repository": repository} if repository is not None else {}),
            },
            sort_keys=True,
        )
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("repositories", help="read-only discovery of installed repository bindings")
    acquire = sub.add_parser("acquire", help="acquire or reuse one linked workspace")
    acquire.add_argument("--operation-id", required=True)
    acquire.add_argument("--base-sha", required=True)
    acquire.add_argument("--lane", choices=sorted(ALLOWED_LANES), default="web")
    acquire.add_argument("--repository", choices=sorted(_REPOSITORIES))

    census = sub.add_parser("census", help="read-only census of registered source worktrees")
    census.add_argument("--repository", choices=sorted(_REPOSITORIES))
    sub.add_parser("storage", help="read-only enrolled volume and free-space admission check")
    prune = sub.add_parser("prune-missing", help="prune only registrations whose paths Git proves missing")
    prune.add_argument("--apply", action="store_true", help="apply; default is dry-run")
    prune.add_argument("--repository", choices=sorted(_REPOSITORIES))

    for name in ("status", "release"):
        command = sub.add_parser(name, help=f"{name} one managed linked workspace")
        command.add_argument("--operation-id", required=True)
        command.add_argument("--lane", choices=sorted(ALLOWED_LANES), default="web")
        command.add_argument("--repository", choices=sorted(_REPOSITORIES))
        command.add_argument(
            "--published-branch",
            help="exact existing origin branch whose head equals this clean workspace HEAD",
        )
        command.add_argument(
            "--published-pull-request",
            type=int,
            help="exact origin pull-request number whose refs/pull/<N>/head equals this clean workspace HEAD",
        )
    return parser



def _git_text(source: Path, *args: str) -> tuple[int, str, str]:
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    completed = subprocess.run(
        ["git", "-C", str(source), *args],
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def _porcelain_records(source: Path) -> list[dict[str, str]]:
    code, output, error = _git_text(source, "worktree", "list", "--porcelain")
    if code != 0:
        raise WorkspaceError(f"worktree census failed: {error or output}")
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in [*output.splitlines(), ""]:
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        key, sep, value = line.partition(" ")
        current[key] = value if sep else ""
    return records


def _census(source: Path, root: Path) -> dict[str, object]:
    source = source.resolve()
    root = root.resolve()
    entries: list[dict[str, object]] = []
    for record in _porcelain_records(source):
        path = Path(record["worktree"]).resolve()
        exists = path.is_dir()
        locked_reason = record.get("locked", "")
        managed = locked_reason.startswith("mastermind-linked-worktree:v1")
        try:
            path.relative_to(root)
            under_managed_root = True
        except ValueError:
            under_managed_root = False
        branch_ref = record.get("branch", "")
        branch = branch_ref.removeprefix("refs/heads/") if branch_ref else ""
        head = record.get("HEAD", "")
        dirty: bool | None = None
        recoverability = "UNKNOWN"
        if path == source:
            state = "SOURCE_CHECKOUT"
        elif not exists:
            state = "MISSING_LOCKED" if locked_reason else "MISSING_PRUNABLE"
        else:
            code, status, _ = _git_text(path, "status", "--porcelain=v1", "--untracked-files=all")
            dirty = None if code != 0 else bool(status)
            if dirty is True:
                state = "DIRTY_PRESERVE"
                recoverability = "WORKSPACE_ONLY_CHANGES_PRESENT"
            elif dirty is None:
                state = "UNAVAILABLE_PRESERVE"
            elif managed and locked_reason:
                state = "MANAGED_ACTIVE"
            else:
                ancestor_code, _, _ = _git_text(
                    source, "merge-base", "--is-ancestor", head, "refs/remotes/origin/master"
                )
                remote_head = ""
                if branch:
                    remote_code, remote_value, _ = _git_text(
                        source, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}"
                    )
                    if remote_code == 0:
                        remote_head = remote_value
                if ancestor_code == 0:
                    state = "CLEAN_RECOVERABLE"
                    recoverability = "HEAD_REACHABLE_FROM_ORIGIN_MASTER"
                elif remote_head == head and head:
                    state = "CLEAN_RECOVERABLE"
                    recoverability = "HEAD_PUBLISHED_TO_ORIGIN_BRANCH"
                else:
                    state = "CLEAN_UNPUBLISHED_PRESERVE"
                    recoverability = "HEAD_NOT_OBSERVED_ON_ORIGIN_REFS"
        entries.append(
            {
                "path": str(path),
                "head_sha": head,
                "branch": branch,
                "exists": exists,
                "locked": bool(locked_reason),
                "lock_reason": locked_reason,
                "managed": managed,
                "under_managed_root": under_managed_root,
                "dirty": dirty,
                "recoverability": recoverability,
                "state": state,
            }
        )
    counts: dict[str, int] = {}
    for entry in entries:
        state = str(entry["state"])
        counts[state] = counts.get(state, 0) + 1
    return {"counts": counts, "worktrees": entries}


def _prune_missing(source: Path, *, apply: bool) -> dict[str, object]:
    args = ["worktree", "prune", "--verbose", "--expire", "now"]
    if not apply:
        args.insert(2, "--dry-run")
    code, output, error = _git_text(source, *args)
    if code != 0:
        raise WorkspaceError(f"worktree prune failed: {error or output}")
    detail = "\n".join(part for part in (output, error) if part)
    return {
        "applied": apply,
        "lines": [line for line in detail.splitlines() if line],
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    selected = getattr(args, "repository", None)
    alias = selected or "mastermind"
    try:
        host_root = _workspace_root()
        if args.action == "repositories":
            return _emit("repositories", _repository_discovery(host_root), effect="NOT_APPLIED")
        if args.action == "storage":
            return _emit("storage", _storage_status(host_root), effect="NOT_APPLIED")
        source = _selected_repository(alias, explicit=selected is not None)
        root = _repository_workspace_root(host_root, alias)
        destination = (
            _workspace_path(root, args.lane, args.operation_id)
            if args.action in {"status", "release"}
            else None
        )
        if args.action == "census":
            return _emit("census", _census(source, root), effect="NOT_APPLIED", repository=selected)
        if args.action == "prune-missing":
            receipt = _prune_missing(source, apply=args.apply)
            return _emit("prune-missing", receipt,
                         effect="APPLIED" if args.apply and receipt["lines"] else "NOT_APPLIED",
                         repository=selected)
        if args.action == "acquire":
            if selected is not None:
                if (len(args.base_sha) != 40 or any(c not in "0123456789abcdef" for c in args.base_sha)
                        or _repository_git(source, "rev-parse", "--verify", args.base_sha + "^{commit}") != args.base_sha):
                    raise WorkspaceError("REPOSITORY_BASE_INVALID: expected an available exact commit")
            # The enrolled policy names the host root, not a repository subroot.
            # Storage policy and volume identity are ALWAYS observed: only the
            # creation reserve may be waived, and only for an existing operation
            # workspace that is re-used without any new allocation.
            storage = _storage_status(host_root)
            if not storage["admission_allowed"]:
                requested_path = _workspace_path(root, args.lane, args.operation_id)
                if not requested_path.exists():
                    raise WorkspaceError("STORAGE_LOW_SPACE: available storage is below the host reserve")
            # Storage observation may block: re-observe the source at the effect boundary.
            if _selected_repository(alias, explicit=selected is not None) != source:
                raise WorkspaceError("REPOSITORY_SOURCE_CHANGED: selected repository changed")
            receipt = prepare_linked_worktree(
                source,
                root,
                operation_id=args.operation_id,
                lane=args.lane,
                base_sha=args.base_sha,
                branch=_branch(args.operation_id, args.lane),
            )
            return _emit(
                "acquire", receipt,
                effect="NOT_APPLIED" if receipt.reused else "APPLIED",
                repository=selected,
            )
        if args.action == "status":
            # The Git publisher calls this on every source-status/commit precheck.
            # Verify the exact .git <-> common/worktrees registration and managed
            # lock without enumerating unrelated worktrees. Release separately
            # qualifies original target, native selection and recoverability.
            receipt = inspect_linked_worktree(
                source, root, destination, expected_operation_id=args.operation_id,
                status_direct_registration=True,
                published_branch=args.published_branch,
                published_pull_request=args.published_pull_request,
            )
            return _emit("status", receipt, effect="NOT_APPLIED", repository=selected)
        receipt = release_linked_worktree(
            source, root, destination, expected_operation_id=args.operation_id,
            published_branch=args.published_branch,
            published_pull_request=args.published_pull_request,
        )
        return _emit(
            "release", receipt,
            effect="APPLIED" if receipt.removed else "NOT_APPLIED",
            repository=selected,
        )
    except LinkedWorkspaceReleaseEffectUnknown as exc:
        print(json.dumps({
            "schema_version": SCHEMA if selected is None else "mastermind.workspace_cli/v2",
            "action": args.action,
            "effect": "EFFECT_UNKNOWN",
            "error": str(exc),
            **exc.details,
            **({"repository": selected} if selected is not None else {}),
        }, sort_keys=True), file=sys.stderr)
        return 2
    except WorkspaceError as exc:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA if selected is None else "mastermind.workspace_cli/v2",
                    "action": args.action,
                    "effect": "NOT_APPLIED",
                    "error": str(exc),
                    **({"repository": selected} if selected is not None else {}),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


def installation_storage_profile(
    home: Path, *, external_mount: Path = Path("/Volumes/Mastermind")
) -> dict[str, str]:
    """Choose host-owned launcher inputs, not runtime admission or a reservation."""
    home = home.expanduser().resolve()
    policy_path = home / ".config/mastermind/worktree-storage.json"
    if policy_path.exists() or policy_path.is_symlink():
        policy, _digest = _read_storage_policy(policy_path)
        volume = Path(str(policy["mount_point"]))
        root = Path(str(policy["root"])).resolve()
        if volume.is_symlink():
            raise WorkspaceError("STORAGE_ROOT_MISMATCH: enrolled volume is indirect")
        volume = volume.resolve()
        if root == volume or not root.is_relative_to(volume):
            raise WorkspaceError("STORAGE_ROOT_MISMATCH: enrolled root escapes its volume")
        # Keep an explicitly required mount pinned even while disconnected.
        # The installed launcher and existing storage owner refuse use until ready.
        return {
            "root": str(root),
            "mount_point": str(volume),
            "policy_path": str(policy_path),
        }

    selected = {
        "root": str((home / ".mastermind/agent-workspaces").resolve()),
        "mount_point": "",
        "policy_path": "",
    }
    if (
        external_mount.is_symlink()
        or not external_mount.is_dir()
        or not external_mount.is_mount()
    ):
        return selected

    volume = external_mount.resolve()
    try:
        observed = _volume_identity(volume)
    except WorkspaceError:
        return selected
    filesystem = observed.get("FilesystemType")
    if (
        observed.get("MountPoint") != str(volume)
        or observed.get("Writable") is not True
        or not isinstance(filesystem, str)
        or filesystem.lower() not in {"apfs", "hfs", "hfsx"}
    ):
        return selected
    return {
        "root": str((volume / "agent-workspaces").resolve()),
        "mount_point": str(volume),
        "policy_path": "",
    }
