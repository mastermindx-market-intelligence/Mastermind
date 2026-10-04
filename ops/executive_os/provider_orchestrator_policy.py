#!/usr/bin/env python3
"""Install/verify the user-scope Mastermind orchestrator policy for Codex + Claude.

This is a host configuration deployer, not a lifecycle/control plane. It preserves
unrelated user configuration, never reads credentials, and only manages:
- one marked policy block in ~/.codex/AGENTS.md and ~/.claude/CLAUDE.md;
- one PreToolUse hook registration in each provider home; and
- identical copies of the reviewed provider_orchestrator_guard.py source.

Apply/verify are intentionally separate so source review, installation, provider
selection, and behavior proof cannot be conflated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Sequence


BEGIN = "<!-- mastermind-ceo-forward-execution-v2 -->"
END = "<!-- /mastermind-ceo-forward-execution-v2 -->"
LEGACY_BLOCKS = (
    (
        "<!-- mastermind-ceo-async-ci-v1 -->",
        "<!-- /mastermind-ceo-async-ci-v1 -->",
    ),
    (
        "<!-- mastermind-ceo-context-discipline-v1 -->",
        "<!-- /mastermind-ceo-context-discipline-v1 -->",
    ),
    (
        "<!-- mastermind-ceo-forward-execution -->",
        "<!-- /mastermind-ceo-forward-execution -->",
    ),
)
BACKUP_SUFFIX = ".mastermind-orchestrator-backup"

POLICY_BODY = f"""{BEGIN}
## Mastermind CEO / orchestrator forward execution

For Mastermind CEO/orchestrator, end-to-end delivery, substantial continuation, or
project-convergence work, optimize verified capability progress rather than administrative motion.

- Load current protected Mastermind procedure once for substantial work, then execute. Re-census only on a material invalidator.
- Freeze the parent OUTCOME / DONE_WHEN, one current critical dependency, one active phase, and a small set of path-disjoint ready lanes.
- Status reads, comments, watcher maintenance, CI observations, checkpoints, PR metadata, handoffs, and planning are support work. Two consecutive support-only cycles with no capability delta or newly resolved blocker are a NO_DELTA_LOOP: change tactic or lane immediately.
- Context is working memory, not the program ledger. Keep exact artifact/revision refs plus compact accepted conclusions; do not repeatedly rehydrate full transcripts, PR bodies, logs, trees, or already-accepted proof.
- Pending CI/release freezes that lane, not the mission. After one bounded state read, bind exactly one native/background watcher to the exact PR/head/run or use the repository's durable merge controller, then immediately continue another independent authorized lane.
- Never foreground `gh run watch`, `gh run view --watch`, `gh pr checks --watch`, or a hand-written CI status + sleep/poll loop. The watcher event is the next CI observation. A PID/session handle alone is not a verified return path.
- PR ownership stays with the originating operation through genuine red repair, conflict resolution, merge, and required live proof. Accountability is not foreground occupation.
- Keep principals working while workers/watchers work. A queued job, watcher, green PR, merge, install, or checkpoint is a milestone, not automatic end-to-end completion.
- Only when useful independent in-scope work is genuinely exhausted may a verified external owner + real return path on the sole remaining wait justify an external-wait turn boundary.

This block creates no lifecycle, queue, retry, watcher, merge, source-custody, permission,
or release authority. Executive OS, Agent OS, GitHub, repository law, and existing effect
owners remain authoritative.
{END}
"""


class OrchestratorPolicyError(RuntimeError):
    """Unsafe or malformed host policy input."""


class OrchestratorPolicyApplyIncomplete(OrchestratorPolicyError):
    """At least one managed file changed before a later write failed."""

    def __init__(
        self,
        detail: str,
        *,
        modified_files: Sequence[str],
        verify_issues: Sequence[str],
    ) -> None:
        super().__init__(detail)
        self.modified_files = tuple(modified_files)
        self.verify_issues = tuple(verify_issues)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _regular_bytes(path: Path, *, missing: bytes | None = None) -> bytes:
    try:
        info = path.lstat()
    except FileNotFoundError:
        if missing is not None:
            return missing
        raise OrchestratorPolicyError(f"required file missing: {path}")
    except OSError as exc:
        raise OrchestratorPolicyError(f"cannot inspect file: {path}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise OrchestratorPolicyError(f"refuse non-regular provider file: {path}")
    if info.st_size > 4 * 1024 * 1024:
        raise OrchestratorPolicyError(f"provider file unexpectedly large: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise OrchestratorPolicyError(f"cannot read provider file: {path}") from exc


def _mode(path: Path, default: int = 0o600) -> int:
    try:
        return stat.S_IMODE(path.lstat().st_mode) or default
    except FileNotFoundError:
        return default


def _safe_dir(path: Path) -> None:
    if path.exists():
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise OrchestratorPolicyError(f"refuse unsafe provider directory: {path}")
        return
    parent = path.parent
    if parent != path and not parent.exists():
        _safe_dir(parent)
    path.mkdir(mode=0o700)


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_exclusive(path: Path, payload: bytes, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, mode)
    try:
        view = memoryview(payload)
        while view:
            count = os.write(fd, view)
            if count <= 0:
                raise OSError("short write")
            view = view[count:]
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_dir(path.parent)


def _atomic_write(path: Path, payload: bytes) -> bool:
    _safe_dir(path.parent)
    current = _regular_bytes(path, missing=b"")
    mode = _mode(path)
    if current == payload:
        return False
    if path.exists():
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        if not backup.exists():
            _write_exclusive(backup, current, mode)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.mastermind.tmp")
    try:
        _write_exclusive(temporary, payload, mode)
        os.replace(temporary, path)
        os.chmod(path, mode)
        _fsync_dir(path.parent)
    except OSError as exc:
        raise OrchestratorPolicyError(f"provider policy write failed: {path}") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return True


def _strip_marked_block(text: str, begin: str, end: str) -> str:
    begins = text.count(begin)
    ends = text.count(end)
    if begins != ends or begins > 1:
        raise OrchestratorPolicyError(
            f"managed orchestrator policy markers are malformed/duplicated: {begin}"
        )
    if begins == 0:
        return text
    start = text.index(begin)
    finish = text.index(end, start) + len(end)
    return (text[:start] + text[finish:]).strip()


def _managed_text(original: str) -> str:
    text = original
    for begin, end in LEGACY_BLOCKS:
        text = _strip_marked_block(text, begin, end)

    begins = text.count(BEGIN)
    ends = text.count(END)
    if begins != ends or begins > 1:
        raise OrchestratorPolicyError(
            "managed orchestrator policy v2 markers are malformed/duplicated"
        )
    block = POLICY_BODY.rstrip() + "\n"
    if begins == 1:
        start = text.index(BEGIN)
        finish = text.index(END, start) + len(END)
        replacement = text[:start] + block.rstrip() + text[finish:]
        return replacement.rstrip() + "\n"
    prefix = text.rstrip()
    return ((prefix + "\n\n") if prefix else "") + block


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise OrchestratorPolicyError(f"{label} is malformed JSON") from exc
    if not isinstance(value, dict):
        raise OrchestratorPolicyError(f"{label} must be a JSON object")
    return value


def _remove_managed_hook(rows: object) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        if rows is None:
            return []
        raise OrchestratorPolicyError("provider hook event must be a list")
    output: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise OrchestratorPolicyError("provider hook row must be an object")
        hooks = row.get("hooks")
        if not isinstance(hooks, list):
            output.append(dict(row))
            continue
        kept = []
        for hook in hooks:
            if not isinstance(hook, dict):
                kept.append(hook)
                continue
            command = str(hook.get("command") or "")
            if "mastermind_fabric_routing_guard.py" in command:
                continue
            kept.append(hook)
        if kept:
            copied = dict(row)
            copied["hooks"] = kept
            output.append(copied)
    return output


def _hook_row(matcher: str, command: str, message: str) -> dict[str, Any]:
    return {
        "matcher": matcher,
        "hooks": [
            {
                "type": "command",
                "command": command,
                "timeout": 10,
                "statusMessage": message,
            }
        ],
    }


def _render_claude_settings(raw: bytes, guard: Path) -> bytes:
    value = _json_object(raw, "Claude settings")
    hooks = value.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise OrchestratorPolicyError("Claude hooks must be an object")
    rows = _remove_managed_hook(hooks.get("PreToolUse"))
    rows.append(
        _hook_row(
            "Agent|Task|Bash",
            f'python3 "{guard}"',
            "Enforcing Mastermind fabric routing and asynchronous CI waits",
        )
    )
    hooks["PreToolUse"] = rows
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _render_codex_hooks(raw: bytes, guard: Path) -> bytes:
    value = _json_object(raw, "Codex hooks")
    value.setdefault(
        "description",
        "User lifecycle hooks with Mastermind asynchronous CI-wait enforcement.",
    )
    hooks = value.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise OrchestratorPolicyError("Codex hooks must be an object")
    rows = _remove_managed_hook(hooks.get("PreToolUse"))
    rows.append(
        _hook_row(
            "^Bash$",
            f'python3 "{guard}"',
            "Keeping Mastermind CI waits asynchronous",
        )
    )
    hooks["PreToolUse"] = rows
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _paths(home: Path) -> dict[str, Path]:
    home = home.expanduser().resolve()
    return {
        "codex_doc": home / ".codex" / "AGENTS.md",
        "claude_doc": home / ".claude" / "CLAUDE.md",
        "codex_hooks": home / ".codex" / "hooks.json",
        "claude_settings": home / ".claude" / "settings.json",
        "codex_guard": home / ".codex" / "hooks" / "mastermind_fabric_routing_guard.py",
        "claude_guard": home / ".claude" / "hooks" / "mastermind_fabric_routing_guard.py",
    }


def _canonical_guard(source: Path | None = None) -> bytes:
    path = source or Path(__file__).with_name("provider_orchestrator_guard.py")
    return _regular_bytes(path)


def apply_policy(home: Path, *, guard_source: Path | None = None) -> dict[str, object]:
    paths = _paths(home)
    guard = _canonical_guard(guard_source)

    codex_doc = _regular_bytes(paths["codex_doc"], missing=b"").decode("utf-8")
    claude_doc = _regular_bytes(paths["claude_doc"], missing=b"").decode("utf-8")
    claude_settings = _regular_bytes(paths["claude_settings"], missing=b"{}\n")
    codex_hooks = _regular_bytes(paths["codex_hooks"], missing=b"{}\n")

    # Validate every render before the first mutation so malformed peer config
    # cannot leave a half-applied provider pair.
    rendered = {
        "codex_doc": _managed_text(codex_doc).encode("utf-8"),
        "claude_doc": _managed_text(claude_doc).encode("utf-8"),
        "claude_settings": _render_claude_settings(
            claude_settings, paths["claude_guard"]
        ),
        "codex_hooks": _render_codex_hooks(codex_hooks, paths["codex_guard"]),
    }

    operations = [
        ("codex_guard", guard),
        ("claude_guard", guard),
        ("codex_doc", rendered["codex_doc"]),
        ("claude_doc", rendered["claude_doc"]),
        ("claude_settings", rendered["claude_settings"]),
        ("codex_hooks", rendered["codex_hooks"]),
    ]
    modified: list[str] = []
    try:
        for key, payload in operations:
            if _atomic_write(paths[key], payload):
                modified.append(str(paths[key]))
    except OrchestratorPolicyError as exc:
        if modified:
            try:
                observed = verify_policy(home, guard_source=guard_source)
                verify_issues = tuple(str(item) for item in observed.get("issues", ()))
            except Exception:
                verify_issues = ("verify_after_partial_apply_failed",)
            raise OrchestratorPolicyApplyIncomplete(
                "provider orchestrator policy apply stopped after a partial write; "
                "do not switch carriers or blindly replay. Verify this same home first.",
                modified_files=modified,
                verify_issues=verify_issues,
            ) from exc
        raise

    return verify_policy(home, guard_source=guard_source)


def _managed_hook_count(raw: bytes, guard: Path, *, claude: bool) -> int:
    value = _json_object(raw, "provider hooks")
    hooks = value.get("hooks")
    if not isinstance(hooks, dict):
        return 0
    rows = hooks.get("PreToolUse")
    if not isinstance(rows, list):
        return 0
    expected_matcher = "Agent|Task|Bash" if claude else "^Bash$"
    expected_command = f'python3 "{guard}"'
    count = 0
    for row in rows:
        if not isinstance(row, dict) or row.get("matcher") != expected_matcher:
            continue
        nested = row.get("hooks")
        if not isinstance(nested, list):
            continue
        count += sum(
            1
            for hook in nested
            if isinstance(hook, dict) and hook.get("command") == expected_command
        )
    return count


def verify_policy(home: Path, *, guard_source: Path | None = None) -> dict[str, object]:
    paths = _paths(home)
    canonical = _canonical_guard(guard_source)
    issues: list[str] = []

    for name in ("codex_guard", "claude_guard"):
        try:
            installed = _regular_bytes(paths[name])
        except OrchestratorPolicyError:
            issues.append(f"{name}.missing")
            continue
        if installed != canonical:
            issues.append(f"{name}.digest")

    for name in ("codex_doc", "claude_doc"):
        try:
            text = _regular_bytes(paths[name]).decode("utf-8")
        except (OrchestratorPolicyError, UnicodeError):
            issues.append(f"{name}.missing_or_invalid")
            continue
        if (
            text.count(BEGIN) != 1
            or text.count(END) != 1
            or _managed_text(text) != text
        ):
            issues.append(f"{name}.managed_block")

    try:
        claude_raw = _regular_bytes(paths["claude_settings"])
        if _managed_hook_count(
            claude_raw, paths["claude_guard"], claude=True
        ) != 1:
            issues.append("claude_settings.pretool")
    except OrchestratorPolicyError:
        issues.append("claude_settings.missing")

    try:
        codex_raw = _regular_bytes(paths["codex_hooks"])
        if _managed_hook_count(
            codex_raw, paths["codex_guard"], claude=False
        ) != 1:
            issues.append("codex_hooks.pretool")
    except OrchestratorPolicyError:
        issues.append("codex_hooks.missing")

    return {
        "state": "READY" if not issues else "DRIFT",
        "home": str(Path(home).expanduser().resolve()),
        "issues": issues,
        "guard_sha256": _sha256(canonical),
        "managed_files": {key: str(value) for key, value in paths.items()},
        "credentials_read": False,
        "permissions_changed": False,
        "lifecycle_created": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("verify", "apply"))
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--guard-source", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = (
            apply_policy(args.home, guard_source=args.guard_source)
            if args.mode == "apply"
            else verify_policy(args.home, guard_source=args.guard_source)
        )
    except OrchestratorPolicyApplyIncomplete as exc:
        print(
            json.dumps(
                {
                    "state": "APPLY_INCOMPLETE_VERIFY_REQUIRED",
                    "detail": str(exc),
                    "modified_files": list(exc.modified_files),
                    "verify_issues": list(exc.verify_issues),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 70
    except (OrchestratorPolicyError, UnicodeError, OSError) as exc:
        print(json.dumps({"state": "REFUSED", "detail": str(exc)}, sort_keys=True))
        return 65
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["state"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
