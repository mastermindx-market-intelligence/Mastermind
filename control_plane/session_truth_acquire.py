"""Read-only acquisition for the deterministic Session Truth Receipt.

This module acquires only two owner-controlled inputs for R1:

* the exact protected Sol Skillpack INDEX from a caller-supplied Git commit object;
* canonical Agent OS state/context through Macro's existing read-only CLI surfaces.

It performs no network I/O, writes no source state, and owns no Agent OS parsing or
lifecycle semantics.  External GitHub/Linear/Slack/Executive observations are handled
by later snapshot-normalization layers.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from control_plane.ceo_boot_packet import git_sha, resolve_macro_root


_CANONICAL_SKILLPACK_REPOSITORY = "mastermindx-market-intelligence/Mastermind"
_SKILLPACK_SCHEMA = "mastermind.sol_skillpack.v1"
_INDEX_PATH = "docs/sol_skills/INDEX.md"
_FRONTMATTER_KEYS = frozenset(
    {"schema", "skillpack_version", "minimum_bootstrap_major", "skill"}
)
_WS_RE = re.compile(r"^WS:[A-Z0-9][A-Z0-9-]*$")
_REPO_ROOT = Path(__file__).resolve().parent.parent
_GIT_TIMEOUT = 10.0


class AcquisitionError(RuntimeError):
    """Raised when a canonical read path returns malformed or incompatible data."""


def _git_text(repo_root: Path, *args: str) -> str | None:
    """Return stdout from one bounded local Git read, or ``None`` on read failure."""

    try:
        proc = subprocess.run(
            ["git", "-C", os.fspath(repo_root), *args],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout if proc.stdout else None


def _read_scalar_frontmatter_text(text: str) -> dict[str, str]:
    """Parse only the four scalar fields owned by the protected Skillpack INDEX.

    This is intentionally not a YAML parser and must never be reused for Agent OS.
    Complex/multiline YAML, duplicate keys, unknown keys, or empty values fail closed.
    """

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise AcquisitionError("Skillpack INDEX frontmatter is missing")

    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration as exc:
        raise AcquisitionError("Skillpack INDEX frontmatter is unterminated") from exc

    parsed: dict[str, str] = {}
    for raw in lines[1:end]:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise AcquisitionError("Skillpack INDEX frontmatter contains a non-scalar line")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key not in _FRONTMATTER_KEYS:
            raise AcquisitionError(f"Skillpack INDEX frontmatter has unknown key {key!r}")
        if key in parsed:
            raise AcquisitionError(f"Skillpack INDEX frontmatter duplicates {key!r}")
        if not value or value[0] in "[{>|&*!" or value.startswith("-"):
            raise AcquisitionError(f"Skillpack INDEX frontmatter field {key!r} is not a scalar")
        parsed[key] = value

    missing = sorted(_FRONTMATTER_KEYS - set(parsed))
    if missing:
        raise AcquisitionError(
            "Skillpack INDEX frontmatter is missing field(s): " + ", ".join(missing)
        )
    return parsed


def collect_skillpack(
    repo_root: Path,
    protected_sha: str,
    bootstrap_major: int = 1,
) -> dict[str, Any]:
    """Read the protected Skillpack INDEX from exactly ``protected_sha``.

    The working tree/branch HEAD is deliberately irrelevant.  Missing Git objects are
    explicit unavailable observations; malformed or incompatible protected content is
    a fail-closed acquisition error.
    """

    root = Path(repo_root)
    object_type = _git_text(root, "cat-file", "-t", protected_sha)
    if object_type is None or object_type.strip() != "commit":
        return {
            "available": False,
            "reason": "SKILLPACK_COMMIT_UNAVAILABLE",
            "sha": protected_sha,
        }

    text = _git_text(root, "show", f"{protected_sha}:{_INDEX_PATH}")
    if text is None:
        return {
            "available": False,
            "reason": "SKILLPACK_INDEX_UNAVAILABLE",
            "sha": protected_sha,
        }

    header = _read_scalar_frontmatter_text(text)
    if header["schema"] != _SKILLPACK_SCHEMA:
        raise AcquisitionError(
            f"Skillpack schema {header['schema']!r} is incompatible with {_SKILLPACK_SCHEMA!r}"
        )
    if header["skill"] != "index":
        raise AcquisitionError("Skillpack INDEX frontmatter skill must be 'index'")

    version = header["skillpack_version"]
    if not version:
        raise AcquisitionError("Skillpack version is empty")
    try:
        minimum = int(header["minimum_bootstrap_major"], 10)
    except ValueError as exc:
        raise AcquisitionError(
            "Skillpack INDEX frontmatter minimum_bootstrap_major is not an integer"
        ) from exc
    if minimum < 1:
        raise AcquisitionError("Skillpack minimum bootstrap major must be positive")
    if type(bootstrap_major) is not int or bootstrap_major < minimum:
        raise AcquisitionError(
            f"bootstrap major {bootstrap_major!r} is incompatible; Skillpack requires >= {minimum}"
        )

    return {
        "repository": _CANONICAL_SKILLPACK_REPOSITORY,
        "sha": protected_sha,
        "schema": _SKILLPACK_SCHEMA,
        "version": version,
        "minimum_bootstrap_major": minimum,
        "available": True,
    }


def _run_agentos(
    macro_root: Path,
    args: Sequence[str],
    *,
    environ: Mapping[str, str],
    timeout: float,
) -> str:
    script = macro_root / "scripts" / "agentos.py"
    cmd = [sys.executable, os.fspath(script), *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=os.fspath(macro_root),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=dict(environ),
        )
    except subprocess.TimeoutExpired as exc:
        raise AcquisitionError(
            f"Agent OS read timed out after {timeout:g}s: {' '.join(args)}"
        ) from exc
    except OSError as exc:
        raise AcquisitionError(f"Agent OS read could not be launched: {exc}") from exc

    if proc.returncode != 0:
        tail = (proc.stderr or "").strip()[-200:]
        raise AcquisitionError(
            f"Agent OS read exited {proc.returncode}: {tail or '<no stderr>'}"
        )
    return proc.stdout or ""


def _decode_leading_json(text: str, label: str) -> tuple[dict[str, Any], str]:
    stripped = text.lstrip()
    if not stripped:
        raise AcquisitionError(f"{label} emitted empty output")
    try:
        value, end = json.JSONDecoder().raw_decode(stripped)
    except json.JSONDecodeError as exc:
        raise AcquisitionError(f"{label} emitted malformed JSON") from exc
    if not isinstance(value, dict):
        raise AcquisitionError(f"{label} must emit a JSON object")
    return value, stripped[end:].strip()


def _validate_agentos_state(state: dict[str, Any], workstreams: Sequence[str]) -> None:
    if state.get("schema") != "agent_os_state.v1":
        raise AcquisitionError("Agent OS status schema must be agent_os_state.v1")
    rows = state.get("workstreams")
    if not isinstance(rows, list):
        raise AcquisitionError("Agent OS status workstreams must be a list")

    keys: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("key"), str):
            raise AcquisitionError("Agent OS status contains a malformed workstream record")
        key = row["key"]
        if key in keys:
            raise AcquisitionError(f"Agent OS status duplicates workstream key {key!r}")
        keys.add(key)

    missing = [ws for ws in workstreams if ws[3:] not in keys]
    if missing:
        raise AcquisitionError(
            "Agent OS status is missing requested workstream(s): " + ", ".join(missing)
        )


def _validate_context(context: dict[str, Any], requested: str) -> None:
    if context.get("schema") != "context_bundle.v1":
        raise AcquisitionError("Agent OS compile-context schema must be context_bundle.v1")
    target = context.get("target")
    if not isinstance(target, dict) or target.get("workstream") != requested:
        raise AcquisitionError(
            f"Agent OS compile-context target does not match requested {requested}"
        )


def collect_agentos(
    macro_root_flag: str | None,
    workstreams: Sequence[str],
    *,
    environ: Mapping[str, str],
    now: str | None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Acquire canonical Agent OS state and scoped context without writing Macro.

    Macro's own parser/CLI remains authoritative.  ``status --dry-run`` supplies the
    structured direct-record state; ``compile-context`` supplies bounded cited context
    for each exact requested workstream.  Missing Macro read capability is represented
    explicitly rather than normalized to empty/healthy state.
    """

    requested = list(workstreams)
    for workstream in requested:
        if not isinstance(workstream, str) or not _WS_RE.fullmatch(workstream):
            raise AcquisitionError(
                f"Agent OS workstream identity must use exact WS:<KEY> form: {workstream!r}"
            )

    macro_root, _resolved_via, _candidates = resolve_macro_root(
        macro_root_flag,
        environ,
        _REPO_ROOT,
    )
    if macro_root is None:
        return {
            "available": False,
            "reason": "AGENTOS_READ_PATH_UNAVAILABLE",
            "contexts": [],
        }

    source_sha = git_sha(macro_root)
    if source_sha is None:
        return {
            "available": False,
            "reason": "AGENTOS_SOURCE_SHA_UNAVAILABLE",
            "contexts": [],
        }

    status_args = ["status", "--dry-run"]
    if now:
        status_args += ["--now", now]
    status_text = _run_agentos(
        macro_root,
        status_args,
        environ=environ,
        timeout=timeout,
    )
    state, trailing = _decode_leading_json(status_text, "Agent OS status")
    _validate_agentos_state(state, requested)

    warnings: list[str] = []
    if trailing:
        warnings.append("agentos status emitted trailing non-JSON diagnostics")

    contexts: list[dict[str, Any]] = []
    for workstream in requested:
        args = ["compile-context", "--workstream", workstream[3:]]
        if now:
            args += ["--now", now]
        context_text = _run_agentos(
            macro_root,
            args,
            environ=environ,
            timeout=timeout,
        )
        try:
            context = json.loads(context_text)
        except json.JSONDecodeError as exc:
            raise AcquisitionError("Agent OS compile-context emitted malformed JSON") from exc
        if not isinstance(context, dict):
            raise AcquisitionError("Agent OS compile-context must emit a JSON object")
        _validate_context(context, workstream)
        contexts.append(context)

    return {
        "available": True,
        "source_sha": source_sha,
        "state": state,
        "contexts": contexts,
        "warnings": warnings,
    }
