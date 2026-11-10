#!/usr/bin/env python3
"""Read-only inspection of configured Codex Fabric Stop bindings.

Never run a hook or adapter, inspect results, create attention metadata, change
trust, or infer native loading/delivery from a matching source fingerprint.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import shlex
import stat

try:
    from .fabric_stop_return import ID, MAX_EVENT, MAX_RESULT, SHA, digest, regular_bytes
except ImportError:  # Direct invocation beside the incumbent helper.
    from fabric_stop_return import ID, MAX_EVENT, MAX_RESULT, SHA, digest, regular_bytes


HOOK_NAME = re.compile(r"fabric_stop_return(?:_([0-9a-f]{12}))?\.py\Z")
PYTHON_NAME = re.compile(r"python(?:3(?:\.[0-9]+)?)?\Z")
VALUE_FLAGS = frozenset({"--root", "--run", "--adapter", "--adapter-sha256",
                         "--receipt-dir", "--subscribed-state-dir"})
MAX_DEFINITIONS = 64


def _directory_issue(path: Path) -> str | None:
    if not path.is_absolute():
        return "state_directory_not_absolute"
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(descriptor)
        if info.st_uid != os.getuid():
            return "state_directory_unsafe"
        if stat.S_IMODE(info.st_mode) != 0o700:
            return "state_directory_unsafe"
    except OSError:
        return "state_directory_unavailable"
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return None


def _binding(command: str) -> tuple[Path, dict[str, str]]:
    """Parse only the existing direct Python command form; never expand a shell."""
    # This deliberately narrow form excludes shell syntax even inside quotes.
    # Ordinary quoted paths with spaces remain supported. Inspect syntax before
    # shlex can erase newlines, escaping, and command boundaries.
    if any(ord(char) < 32 or char in "$`;&|<>()*?[]{}~" for char in command):
        raise ValueError("unsupported_command")
    tokens = shlex.split(command)
    if (len(tokens) < 2 or not PYTHON_NAME.fullmatch(Path(tokens[0]).name)
            or not HOOK_NAME.fullmatch(Path(tokens[1]).name)
            or any("$" in token or "`" in token for token in tokens)):
        raise ValueError("unsupported_command")
    flags: dict[str, str] = {}
    tail = tokens[2:]
    if len(tail) % 2:
        raise ValueError("unsupported_command")
    for index in range(0, len(tail), 2):
        key, value = tail[index:index + 2]
        if key not in VALUE_FLAGS or key in flags or not value or value.startswith("--"):
            raise ValueError("unsupported_command")
        flags[key] = value
    if not {"--adapter", "--adapter-sha256"} <= flags.keys():
        raise ValueError("missing_adapter_binding")
    if not SHA.fullmatch(flags["--adapter-sha256"]):
        raise ValueError("invalid_adapter_digest")
    mode_flags = flags.keys() - {"--adapter", "--adapter-sha256"}
    if mode_flags not in ({"--subscribed-state-dir"}, {"--root", "--run", "--receipt-dir"}):
        raise ValueError("invalid_mode_binding")
    if "--root" in flags and any(not ID.fullmatch(flags[key]) for key in ("--root", "--run")):
        raise ValueError("invalid_fixed_identity")
    return Path(tokens[1]), flags


def _inspect_definition(definition: dict, group: int, index: int) -> dict:
    result: dict = {"group_index": group, "hook_index": index, "issues": []}
    issues = result["issues"]
    if definition.get("type") != "command":
        issues.append("unsupported_handler_type")
        return result
    if "async" in definition and definition["async"] is not False:
        issues.append("asynchronous_stop_definition")
    timeout = definition.get("timeout", 600)
    try:
        valid_timeout = type(timeout) in (int, float) and math.isfinite(timeout) and timeout >= 10
    except OverflowError:
        valid_timeout = False
    if not valid_timeout:
        issues.append("insufficient_callback_timeout")
    try:
        hook, flags = _binding(definition["command"])
    except (KeyError, TypeError, ValueError) as exc:
        reason = str(exc)
        issues.append(reason if reason in {"unsupported_command", "missing_adapter_binding",
            "invalid_adapter_digest", "invalid_mode_binding", "invalid_fixed_identity"} else "unsupported_command")
        return result
    result["mode"] = "subscribed" if "--subscribed-state-dir" in flags else "fixed"
    result["hook_path"] = str(hook)
    if not hook.is_absolute():
        issues.append("hook_path_not_absolute")
    else:
        try:
            hook_sha = digest(regular_bytes(hook, MAX_RESULT))
            result["hook_sha256"] = hook_sha
            name_pin = HOOK_NAME.fullmatch(hook.name).group(1)
            if name_pin and not hook_sha.startswith(name_pin):
                issues.append("hash_named_hook_source_changed")
        except (OSError, ValueError):
            issues.append("hook_source_unavailable_or_unsafe")
    adapter = Path(flags["--adapter"])
    result["adapter_path"] = str(adapter)
    result["expected_adapter_sha256"] = flags["--adapter-sha256"]
    if not adapter.is_absolute():
        issues.append("adapter_path_not_absolute")
    else:
        try:
            observed = digest(regular_bytes(adapter, MAX_RESULT))
            result["observed_adapter_sha256"] = observed
            if observed != flags["--adapter-sha256"]:
                issues.append("adapter_source_changed")
        except (OSError, ValueError):
            issues.append("adapter_source_unavailable_or_unsafe")
    directory = Path(flags.get("--subscribed-state-dir", flags.get("--receipt-dir", "")))
    result["state_directory"] = str(directory)
    issue = _directory_issue(directory)
    if issue:
        issues.append(issue)
    return result


def _reject_nonfinite_json(value: str) -> None:
    raise ValueError("nonfinite JSON number")


def inspect_hooks(hooks_file: Path) -> dict:
    """Observe configured source and directory facts; never touch subscriptions."""
    report: dict = {
        "schema": "mastermind.fabric_stop_preflight.v1",
        "hooks_file": str(hooks_file),
        "static_checks_pass": False,
        "native_loading": "UNOBSERVED",
        "native_delivery": "UNOBSERVED",
        "effects": "NONE",
        "issues": [],
        "bindings": [],
    }
    try:
        if not hooks_file.is_absolute():
            raise ValueError("hooks path must be absolute")
        raw = regular_bytes(hooks_file, MAX_EVENT)
        report["hooks_sha256"] = digest(raw)
        value = json.loads(raw, parse_constant=_reject_nonfinite_json)
        if not isinstance(value, dict) or not isinstance(value.get("hooks"), dict):
            raise ValueError("invalid hooks document")
        groups = value["hooks"].get("Stop", [])
        if not isinstance(groups, list) or len(groups) > MAX_DEFINITIONS:
            raise ValueError("invalid Stop groups")
        count = 0
        for group_index, group in enumerate(groups):
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise ValueError("invalid Stop group")
            for hook_index, definition in enumerate(group["hooks"]):
                count += 1
                if count > MAX_DEFINITIONS or not isinstance(definition, dict):
                    raise ValueError("invalid Stop definitions")
                command = definition.get("command")
                if not isinstance(command, str) or "fabric_stop_return" not in command:
                    continue
                report["bindings"].append(_inspect_definition(definition, group_index, hook_index))
    except (OSError, ValueError, UnicodeError):
        report["issues"].append("hooks_configuration_unavailable_or_invalid")
    if not report["bindings"]:
        report["issues"].append("no_fabric_stop_definitions")
    report["static_checks_pass"] = bool(report["bindings"]) and not report["issues"] and all(
        not binding["issues"] for binding in report["bindings"])
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hooks-file", type=Path, required=True)
    args = parser.parse_args(argv)
    report = inspect_hooks(args.hooks_file)
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report["static_checks_pass"] else 78


if __name__ == "__main__":
    raise SystemExit(main())
