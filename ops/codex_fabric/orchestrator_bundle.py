"""Deliver one complete attended coordinator bundle; never launch or grant authority.

This client configuration utility owns no lifecycle or execution state. Its default
operation is read-only. Publication is explicit, source-digest-fenced, no-clobber,
and profile-last. Existing global configuration and credentials are never opened.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tomllib
from typing import Iterator
from uuid import uuid4

SOURCE_ROOT = Path(__file__).resolve().parent
BUNDLE_PATHS = (
    "agents/l2-sol-ceo.toml",
    "agents/l2-astra-ceo.toml",
    "mastermind-orchestrators.config.toml",
)
_MAX_FILE_BYTES = 65536
_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


class BundleError(RuntimeError):
    """Fixed non-content-bearing error plus verified effects from this invocation."""

    def __init__(self, code: str, *, created: tuple[str, ...] = (), effect_unknown: bool = False):
        super().__init__(code)
        self.code = code
        self.created = created
        self.effect_unknown = effect_unknown


@contextmanager
def _directory(path: Path) -> Iterator[int]:
    """Open each absolute path component without following links; retain its fd."""
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise BundleError("PLATFORM_UNSUPPORTED")
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise BundleError("PATH_INVALID")
    fd = os.open(path.anchor, _DIR_FLAGS)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, _DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    except OSError as exc:
        raise BundleError("UNSAFE_OR_UNAVAILABLE_PATH") from exc
    finally:
        os.close(fd)


def _read_file(directory_fd: int, name: str) -> bytes | None:
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise BundleError("UNSAFE_OR_UNAVAILABLE_FILE") from exc
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_FILE_BYTES:
            raise BundleError("UNSAFE_OR_OVERSIZED_FILE")
        data = stream.read(_MAX_FILE_BYTES + 1)
    if len(data) > _MAX_FILE_BYTES:
        raise BundleError("UNSAFE_OR_OVERSIZED_FILE")
    return data


def _roles_fd(home_fd: int) -> int | None:
    try:
        return os.open("agents", _DIR_FLAGS, dir_fd=home_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise BundleError("UNSAFE_OR_UNAVAILABLE_PATH") from exc


def _require(condition: object) -> None:
    if not condition:
        raise BundleError("SOURCE_CONTRACT_INVALID")


def _valid_contract(snapshot: tuple[tuple[str, bytes], ...]) -> None:
    try:
        values = {name: tomllib.loads(content.decode('utf-8')) for name, content in snapshot}
        parent = values[BUNDLE_PATHS[-1]]
        _require(set(parent) == {'model', 'model_reasoning_effort', 'sandbox_mode', 'approval_policy', 'developer_instructions', 'agents'})
        _require(parent['model'] == 'gpt-6-astra')
        _require(parent['model_reasoning_effort'] == 'high')
        _require(parent['sandbox_mode'] == 'read-only')
        _require(parent['approval_policy'] == 'never')
        _require(isinstance(parent['developer_instructions'], str))
        _require('principal, not the default worker' in parent['developer_instructions'])
        agents = parent['agents']
        _require(set(agents) == {'enabled', 'max_concurrent_threads_per_session', 'default_subagent_model', 'default_subagent_reasoning_effort', 'l2_sol_ceo', 'l2_astra_ceo'})
        _require(agents['enabled'] is True)
        _require(type(agents['max_concurrent_threads_per_session']) is int)
        _require(agents['max_concurrent_threads_per_session'] == 1)
        _require(agents['default_subagent_model'] == 'gpt-5.6-sol')
        _require(agents['default_subagent_reasoning_effort'] == 'high')
        for role, model in (('sol', 'gpt-5.6-sol'), ('astra', 'gpt-6-astra')):
            rel = f'agents/l2-{role}-ceo.toml'
            value = values[rel]
            _require(set(value) == {'name', 'description', 'model', 'model_reasoning_effort', 'sandbox_mode', 'developer_instructions', 'agents'})
            _require(value['name'] == f'l2_{role}_ceo')
            _require(value['model'] == model)
            _require(value['model_reasoning_effort'] == 'high')
            _require(value['sandbox_mode'] == 'read-only')
            _require(set(value['agents']) == {'enabled'})
            _require(value['agents']['enabled'] is False)
            _require(isinstance(value['developer_instructions'], str))
            _require('Do not spawn native child agents' in value['developer_instructions'])
            _require(isinstance(value['description'], str) and value['description'].strip())
            entry = agents[f'l2_{role}_ceo']
            _require(set(entry) == {'description', 'config_file'})
            _require(entry['config_file'] == rel)
            _require(isinstance(entry['description'], str) and entry['description'].strip())
    except (AssertionError, KeyError, TypeError, UnicodeError, ValueError) as exc:
        raise BundleError('SOURCE_CONTRACT_INVALID') from exc


def _snapshot(source_root: Path) -> tuple[tuple[str, bytes], ...]:
    result = []
    with _directory(source_root) as root_fd:
        roles_fd = _roles_fd(root_fd)
        try:
            for rel in BUNDLE_PATHS:
                folder = roles_fd if rel.startswith("agents/") else root_fd
                data = _read_file(folder, Path(rel).name) if folder is not None else None
                if data is None:
                    raise BundleError("SOURCE_INCOMPLETE")
                result.append((rel, data))
        finally:
            if roles_fd is not None:
                os.close(roles_fd)
    frozen = tuple(result)
    _valid_contract(frozen)
    return frozen


def _digest(snapshot: tuple[tuple[str, bytes], ...]) -> str:
    entries = [(name, hashlib.sha256(content).hexdigest()) for name, content in snapshot]
    wire = json.dumps(entries, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(wire).hexdigest()


def _inspect(snapshot: tuple[tuple[str, bytes], ...], home_fd: int) -> dict:
    roles_fd = _roles_fd(home_fd)
    missing = []
    files = {}
    try:
        for rel, content in snapshot:
            folder = roles_fd if rel.startswith("agents/") else home_fd
            observed = _read_file(folder, Path(rel).name) if folder is not None else None
            if observed is not None and observed != content:
                raise BundleError("DESTINATION_CONFLICT")
            if observed is None:
                missing.append(rel)
            files[rel] = {"sha256": hashlib.sha256(content).hexdigest(), "present": observed is not None}
    finally:
        if roles_fd is not None:
            os.close(roles_fd)
    return {
        "schema": "mastermind.codex_orchestrator_bundle/v1",
        "state": "READY_TO_INSTALL" if missing else "INSTALLED",
        "bundle_digest": _digest(snapshot), "files": files, "missing": missing,
        "execution_authorized": False, "provider_invoked": False,
        "role_selection_proven": False, "child_enforcement_proven": False,
    }


def inspect_bundle(codex_home: Path, *, source_root: Path = SOURCE_ROOT) -> dict:
    snapshot = _snapshot(Path(source_root))
    with _directory(Path(codex_home)) as home_fd:
        return _inspect(snapshot, home_fd)


def configuration_overrides(codex_home: Path, *, expected_bundle_digest: str,
                            source_root: Path = SOURCE_ROOT) -> tuple[str, ...]:
    """Compile bounded client settings above trusted-project config precedence.

    Only consumes one validated source snapshot and an exact installed readback.
    These strings are configuration inputs, not an authorization or launcher.
    The execution owner must revalidate them at its own launch boundary.
    """
    snapshot = _snapshot(Path(source_root))
    if expected_bundle_digest != _digest(snapshot):
        raise BundleError("SOURCE_MOVED")
    with _directory(Path(codex_home)) as home_fd:
        receipt = _inspect(snapshot, home_fd)
        if receipt["missing"]:
            raise BundleError("INSTALLATION_INCOMPLETE")
    parent = tomllib.loads(dict(snapshot)[BUNDLE_PATHS[-1]].decode("utf-8"))
    entries = {key: value for key, value in parent.items() if key != "agents"}
    for key, value in parent["agents"].items():
        if isinstance(value, dict):
            for field, setting in value.items():
                entries[f"agents.{key}.{field}"] = (
                    str(Path(codex_home) / setting) if field == "config_file" else setting
                )
        else:
            entries[f"agents.{key}"] = value
    return tuple(f"{key}={json.dumps(value, ensure_ascii=True)}"
                 for key, value in entries.items())


def _publish_new(directory_fd: int, name: str, content: bytes) -> None:
    """Atomically publish complete bytes without replacing any existing name."""
    temporary = f".mmx-bundle-{uuid4().hex}.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=directory_fd)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
                follow_symlinks=False)
        os.fsync(directory_fd)
    finally:
        os.unlink(temporary, dir_fd=directory_fd)


def _assert_target_binding(codex_home: Path, home_fd: int, roles_fd: int | None) -> None:
    """A retained fd is safe to write but must still name the requested target."""
    def identity(fd: int) -> tuple[int, int]:
        info = os.fstat(fd)
        return info.st_dev, info.st_ino
    try:
        with _directory(Path(codex_home)) as current_home:
            if identity(current_home) != identity(home_fd):
                raise BundleError("DESTINATION_MOVED")
        if roles_fd is not None:
            current_roles = _roles_fd(home_fd)
            if current_roles is None:
                raise BundleError("DESTINATION_MOVED")
            try:
                if identity(current_roles) != identity(roles_fd):
                    raise BundleError("DESTINATION_MOVED")
            finally:
                os.close(current_roles)
    except (OSError, BundleError) as exc:
        raise BundleError("DESTINATION_MOVED") from exc


def install_bundle(codex_home: Path, *, expected_bundle_digest: str,
                   source_root: Path = SOURCE_ROOT) -> dict:
    snapshot = _snapshot(Path(source_root))
    if (not isinstance(expected_bundle_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_bundle_digest) is None
            or expected_bundle_digest != _digest(snapshot)):
        raise BundleError("SOURCE_MOVED")
    created: list[str] = []
    with _directory(Path(codex_home)) as home_fd:
        before = _inspect(snapshot, home_fd)
        missing = set(before["missing"])
        if not missing:
            return {**before, "created": []}
        roles_fd = None
        try:
            if any(rel.startswith("agents/") for rel in missing):
                try:
                    os.mkdir("agents", mode=0o700, dir_fd=home_fd)
                except FileExistsError:
                    pass
                roles_fd = _roles_fd(home_fd)
                if roles_fd is None:
                    raise BundleError("DESTINATION_MOVED")
            for rel, content in snapshot:
                if rel not in missing:
                    continue
                _assert_target_binding(codex_home, home_fd, roles_fd)
                folder = roles_fd if rel.startswith("agents/") else home_fd
                _publish_new(folder, Path(rel).name, content)
                created.append(rel)
                _assert_target_binding(codex_home, home_fd, roles_fd)
            after = _inspect(snapshot, home_fd)
            if after["missing"]:
                raise BundleError("DESTINATION_MOVED")
            return {**after, "created": created}
        except (OSError, BundleError) as exc:
            # Reconcile publication on the original descriptors. Never retry or
            # roll back: a link may have succeeded before an error was raised.
            try:
                _assert_target_binding(codex_home, home_fd, roles_fd)
                observed = _inspect(snapshot, home_fd)
                verified = tuple(rel for rel in before["missing"] if rel not in observed["missing"])
            except (OSError, BundleError):
                raise BundleError("INSTALL_EFFECT_UNKNOWN", created=tuple(created), effect_unknown=True) from exc
            raise BundleError("PARTIAL_INSTALL" if verified else "INSTALL_REFUSED", created=verified) from exc
        finally:
            if roles_fd is not None:
                os.close(roles_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--install", action="store_true")
    mode.add_argument("--configuration-overrides", action="store_true")
    parser.add_argument("--expected-bundle-digest")
    args = parser.parse_args(argv)
    if (args.install or args.configuration_overrides) and not args.expected_bundle_digest:
        parser.error("this action requires --expected-bundle-digest from inspection")
    try:
        if args.configuration_overrides:
            overrides = configuration_overrides(
                args.codex_home, expected_bundle_digest=args.expected_bundle_digest
            )
            result = {"configuration_overrides": overrides,
                      "bundle_digest": args.expected_bundle_digest,
                      "execution_authorized": False, "model_turn_started": False}
        elif args.install:
            result = install_bundle(args.codex_home, expected_bundle_digest=args.expected_bundle_digest)
        else:
            result = inspect_bundle(args.codex_home)
    except BundleError as exc:
        print(json.dumps({"state": exc.code, "created": exc.created,
                          "effect_unknown": exc.effect_unknown, "retry_allowed": False,
                          "execution_authorized": False}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
