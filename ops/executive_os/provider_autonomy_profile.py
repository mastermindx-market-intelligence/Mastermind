#!/usr/bin/env python3
"""Apply/verify the unattended Codex and Claude operator permission posture.

This tool edits only three reviewed settings.  It never reads or prints provider
credentials and preserves unrelated provider configuration byte-for-byte where
possible (JSON is semantically preserved and reserialized deterministically).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import tomllib
from pathlib import Path
from typing import Sequence


CODEX_SANDBOX = "danger-full-access"
CODEX_APPROVAL = "never"
CLAUDE_MODE = "bypassPermissions"
_BACKUP_SUFFIX = ".mastermind-backup"
_ROOT_ASSIGNMENT_RE = re.compile(r"^(?P<prefix>\s*)(?P<key>sandbox_mode|approval_policy)\s*=.*$")


class AutonomyProfileError(RuntimeError):
    """Provider configuration is malformed or cannot be safely updated."""


def _read_bytes(path: Path) -> bytes:
    try:
        info = path.lstat()
    except OSError as exc:
        raise AutonomyProfileError(f"provider config unavailable: {path}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise AutonomyProfileError(f"provider config is not a regular file: {path}")
    if info.st_size > 4 * 1024 * 1024:
        raise AutonomyProfileError(f"provider config is unexpectedly large: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise AutonomyProfileError(f"provider config is unreadable: {path}") from exc


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_exclusive(path: Path, payload: bytes, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, mode)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short provider config write")
            view = view[written:]
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_dir(path.parent)


def _backup_once(path: Path, original: bytes, mode: int) -> None:
    backup = path.with_name(path.name + _BACKUP_SUFFIX)
    if backup.exists():
        info = backup.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise AutonomyProfileError(f"provider backup path is unsafe: {backup}")
        return
    try:
        _write_exclusive(backup, original, mode)
    except OSError as exc:
        raise AutonomyProfileError(f"provider backup could not be created: {backup}") from exc


def _atomic_replace(path: Path, payload: bytes, mode: int) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.mastermind.tmp")
    try:
        _write_exclusive(temporary, payload, mode)
        os.replace(temporary, path)
        os.chmod(path, mode)
        _fsync_dir(path.parent)
    except OSError as exc:
        raise AutonomyProfileError(f"provider config update failed: {path}") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _mode(path: Path) -> int:
    value = stat.S_IMODE(path.lstat().st_mode)
    return value if value else 0o600


def _parse_codex(raw: bytes) -> dict[str, object]:
    try:
        value = tomllib.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise AutonomyProfileError("Codex config is malformed TOML") from exc
    if not isinstance(value, dict):
        raise AutonomyProfileError("Codex config is not a TOML mapping")
    return value


def _render_codex(raw: bytes) -> bytes:
    parsed = _parse_codex(raw)
    text = raw.decode("utf-8")
    had_newline = text.endswith("\n")
    lines = text.splitlines()
    root_end = len(lines)
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("["):
            root_end = index
            break
    found: dict[str, int] = {}
    for index in range(root_end):
        match = _ROOT_ASSIGNMENT_RE.match(lines[index])
        if match:
            key = match.group("key")
            if key in found:
                raise AutonomyProfileError(f"Codex root setting is duplicated: {key}")
            found[key] = index
    targets = {"sandbox_mode": CODEX_SANDBOX, "approval_policy": CODEX_APPROVAL}
    for key in targets:
        if key in parsed and key not in found:
            raise AutonomyProfileError(f"Codex root setting uses an unsupported key form: {key}")
    for key, value in targets.items():
        if key in found:
            prefix = _ROOT_ASSIGNMENT_RE.match(lines[found[key]]).group("prefix")  # type: ignore[union-attr]
            lines[found[key]] = f'{prefix}{key} = "{value}"'
    additions = [f'{key} = "{value}"' for key, value in targets.items() if key not in found]
    if additions:
        if root_end and root_end <= len(lines) and lines[root_end - 1].strip():
            additions.append("")
        lines[root_end:root_end] = additions
    rendered = "\n".join(lines)
    if had_newline or rendered:
        rendered += "\n"
    payload = rendered.encode("utf-8")
    check = _parse_codex(payload)
    if check.get("sandbox_mode") != CODEX_SANDBOX or check.get("approval_policy") != CODEX_APPROVAL:
        raise AutonomyProfileError("Codex autonomy profile render failed validation")
    return payload


def _parse_claude(raw: bytes) -> dict[str, object]:
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AutonomyProfileError("Claude settings are malformed JSON") from exc
    if not isinstance(value, dict):
        raise AutonomyProfileError("Claude settings must contain a JSON object")
    return value


def _render_claude(raw: bytes) -> bytes:
    value = _parse_claude(raw)
    permissions = value.get("permissions")
    if permissions is None:
        permissions = {}
        value["permissions"] = permissions
    if not isinstance(permissions, dict):
        raise AutonomyProfileError("Claude permissions setting must be an object")
    permissions["defaultMode"] = CLAUDE_MODE
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def apply_codex(path: Path) -> bool:
    path = Path(path)
    original = _read_bytes(path)
    rendered = _render_codex(original)
    if rendered == original:
        return False
    mode = _mode(path)
    _backup_once(path, original, mode)
    _atomic_replace(path, rendered, mode)
    return True


def apply_claude(path: Path) -> bool:
    path = Path(path)
    original = _read_bytes(path)
    rendered = _render_claude(original)
    if rendered == original:
        return False
    mode = _mode(path)
    _backup_once(path, original, mode)
    _atomic_replace(path, rendered, mode)
    return True


def _codex_nested_override_issues(value: dict[str, object], *, prefix: str) -> list[str]:
    issues: list[str] = []
    for section in ("profiles", "projects"):
        rows = value.get(section)
        if not isinstance(rows, dict):
            continue
        if any(
            isinstance(row, dict) and any(key in row for key in ("sandbox_mode", "approval_policy"))
            for row in rows.values()
        ):
            issues.append(f"{prefix}.{section}.override")
    return issues


def _discover_codex_project_configs(codex_path: Path) -> tuple[Path, ...]:
    root = Path(codex_path).resolve()
    discovered: list[Path] = []
    for parent in (Path.cwd(), *Path.cwd().parents):
        candidate = parent / ".codex" / "config.toml"
        if not candidate.exists():
            continue
        try:
            same = candidate.resolve() == root
        except OSError:
            same = False
        if not same and candidate not in discovered:
            discovered.append(candidate)
    return tuple(discovered)


def verify_profiles(
    codex_path: Path,
    claude_path: Path,
    *,
    codex_project_configs: Sequence[Path] | None = None,
) -> tuple[str, ...]:
    codex = _parse_codex(_read_bytes(Path(codex_path)))
    claude = _parse_claude(_read_bytes(Path(claude_path)))
    issues: list[str] = []
    if codex.get("sandbox_mode") != CODEX_SANDBOX:
        issues.append("codex.sandbox_mode")
    if codex.get("approval_policy") != CODEX_APPROVAL:
        issues.append("codex.approval_policy")
    if "profile" in codex:
        issues.append("codex.profile")
    issues.extend(_codex_nested_override_issues(codex, prefix="codex"))

    projects = (
        _discover_codex_project_configs(Path(codex_path))
        if codex_project_configs is None
        else tuple(Path(path) for path in codex_project_configs)
    )
    for project_path in projects:
        project = _parse_codex(_read_bytes(project_path))
        if "sandbox_mode" in project and project.get("sandbox_mode") != CODEX_SANDBOX:
            issues.append("codex.project.sandbox_mode")
        if "approval_policy" in project and project.get("approval_policy") != CODEX_APPROVAL:
            issues.append("codex.project.approval_policy")
        if "profile" in project:
            issues.append("codex.project.profile")
        issues.extend(_codex_nested_override_issues(project, prefix="codex.project"))

    permissions = claude.get("permissions")
    if not isinstance(permissions, dict) or permissions.get("defaultMode") != CLAUDE_MODE:
        issues.append("claude.permissions.defaultMode")
    return tuple(dict.fromkeys(issues))


def apply_profiles(codex_path: Path, claude_path: Path) -> tuple[bool, bool]:
    # Validate both before either mutates so malformed peer config cannot leave a half-applied pair.
    codex_raw = _read_bytes(Path(codex_path))
    claude_raw = _read_bytes(Path(claude_path))
    _render_codex(codex_raw)
    _render_claude(claude_raw)
    return apply_codex(Path(codex_path)), apply_claude(Path(claude_path))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply or verify unattended provider permission settings")
    parser.add_argument("mode", choices=("verify", "apply"))
    parser.add_argument("--codex-config", type=Path, required=True)
    parser.add_argument("--claude-settings", type=Path, required=True)
    parser.add_argument("--codex-project-config", dest="codex_project_configs", type=Path, action="append")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.mode == "apply":
            apply_profiles(args.codex_config, args.claude_settings)
        issues = verify_profiles(
            args.codex_config,
            args.claude_settings,
            codex_project_configs=args.codex_project_configs,
        )
    except AutonomyProfileError as exc:
        sys.stderr.write(f"provider autonomy profile refused: {exc}\n")
        return 65
    if issues:
        sys.stderr.write("provider autonomy profile drift: " + ",".join(issues) + "\n")
        return 1
    sys.stdout.write("READY\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
