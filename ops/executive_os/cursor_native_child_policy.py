"""Pure, fail-closed Cursor Task role evidence for the existing provider guard.

Not a new authorizer. The incumbent PreToolUse guard remains the only enforcement
carrier. This classifies only two reviewed read-only native Cursor helpers;
external Subagent Fabric admission, paid quota and actual model usage stay separate.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import stat
from typing import Mapping


# Hash-pinned source files also shipped by integrations/cursor_agent_mastermind.
# Changing a role requires an reviewed code+role update, not a model-written edit.
ROLE_SHA256_AND_DECLARED_MODEL = {
    "mmx-repo-explorer": (
        "8139e10ac33c8e065b628b8e69f18ccedf95e3041db63e2f8f9d0f668287681d",
        "gemini-3.7-flash-high",
    ),
    "mmx-independent-reviewer": (
        "f1e9d443b37d4518252f2f983dfe359ba16242f72ee4014ad67566fa5c90cfbd",
        "grok-4.7-medium",
    ),
}
TASK_FIELDS = frozenset(("subagent_type", "prompt", "description", "run_in_background"))


@dataclass(frozen=True)
class TaskObservation:
    admitted: bool
    code: str
    declared_model: str | None = None


def _refuse(code: str) -> TaskObservation:
    return TaskObservation(False, code)


def evaluate_cursor_task(
    payload: Mapping[str, object],
    env: Mapping[str, str],
) -> TaskObservation:
    """Return a hook-local eligibility observation; never dispatch or grant Fabric.

    Cursor 3.25.9's observed Task input contains subagent_type, prompt, description,
    run_in_background but *not* a model field. The top-level model is the PARENT.
    Only exact, immutable project-local read-only role text is admitted here.
    """
    if payload.get("tool_name") != "Task":
        return _refuse("CURSOR_TASK_TOOL_UNMATCHED")
    version = payload.get("cursor_version")
    if not isinstance(version, str) or not version.strip():
        return _refuse("CURSOR_RUNTIME_UNVERIFIED")
    env_version = env.get("CURSOR_VERSION")
    if not isinstance(env_version, str) or not env_version.strip():
        return _refuse("CURSOR_RUNTIME_UNVERIFIED")
    if version != env_version:
        return _refuse("CURSOR_RUNTIME_VERSION_MISMATCH")
    raw_root = env.get("CURSOR_PROJECT_DIR")
    if not isinstance(raw_root, str) or not os.path.isabs(raw_root):
        return _refuse("CURSOR_PROJECT_UNVERIFIED")
    root = Path(raw_root)
    if root.is_symlink() or not root.is_dir():
        return _refuse("CURSOR_PROJECT_UNVERIFIED")
    # Actual Cursor 3.25.9 hooks omit cwd but run in CURSOR_PROJECT_DIR.
    # Validate the hook process cwd; never silently assume the claimed project
    # when a different executable/working directory is invoking this script.
    cwd = payload["cwd"] if "cwd" in payload else os.getcwd()
    if not isinstance(cwd, str) or not os.path.isabs(cwd):
        return _refuse("CURSOR_CWD_UNVERIFIED")
    try:
        Path(cwd).resolve().relative_to(root.resolve())
    except ValueError:
        return _refuse("CURSOR_CWD_UNVERIFIED")

    roots = payload.get("workspace_roots")
    if not isinstance(roots, (list, tuple)) or not roots:
        return _refuse("CURSOR_ROOT_BINDING_MISSING")
    if not any(isinstance(r, str) and os.path.realpath(r) == os.path.realpath(raw_root) for r in roots):
        return _refuse("CURSOR_ROOT_BINDING_MISMATCH")

    args = payload.get("tool_input")
    if not isinstance(args, dict) or set(args) != TASK_FIELDS:
        return _refuse("CURSOR_TASK_ARGS_UNVERIFIED")
    name = args.get("subagent_type")
    if not isinstance(name, str) or name not in ROLE_SHA256_AND_DECLARED_MODEL:
        return _refuse("CURSOR_TASK_ROLE_NOT_ADMITTED")
    if args.get("run_in_background") is not False:
        return _refuse("CURSOR_BACKGROUND_NOT_ADMITTED")
    if not isinstance(args.get("prompt"), str) or not args["prompt"].strip():
        return _refuse("CURSOR_TASK_PROMPT_INVALID")
    if not isinstance(args.get("description"), str) or not args["description"].strip():
        return _refuse("CURSOR_TASK_DESCRIPTION_INVALID")

    role = root / ".cursor" / "agents" / (name + ".md")
    if (root / ".cursor").is_symlink() or (root / ".cursor" / "agents").is_symlink():
        return _refuse("CURSOR_ROLE_SOURCE_UNTRUSTED")
    try:
        s = role.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_size > 65536:
            return _refuse("CURSOR_ROLE_SOURCE_UNTRUSTED")
        data = role.read_bytes()
    except OSError:
        return _refuse("CURSOR_ROLE_SOURCE_MISSING")
    pinned_digest, model = ROLE_SHA256_AND_DECLARED_MODEL[name]
    if sha256(data).hexdigest() != pinned_digest:
        return _refuse("CURSOR_ROLE_DIGEST_MISMATCH")
    # This is declaration proof only; Cursor can fall back to another model.
    return TaskObservation(True, "READ_ONLY_CURSOR_HELPER_DECLARED", model)
