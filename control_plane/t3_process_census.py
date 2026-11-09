"""Closed, read-only T3/DSH/Codex process census for the attempt-fleet view.

One bounded ``ps`` observation (argv only — never environment variables, never
open files, never sockets) plus a PURE, table-tested classifier over argv
tokens.  This module owns no launch, interrupt, kill, signal, provider call,
credential read, queue or registry: it only looks.

Closed vocabulary (``mastermind.t3_process_census/v1``):

* ``t3_harness`` — one T3-owned per-thread harness process.  Observed live on
  m2studio (2026-11-09, lane ledger) in exactly two shapes, BOTH required
  markers present in each:

  1. the agent process, e.g.
     ``claude --output-format stream-json ... --allowedTools mcp__t3-code__*
     ... --add-dir /Users/<user>/.t3/worktrees/Mastermind/t3-<id> --session-id=<uuid>``
     (provider claude, glm, ... via ``--model``), and
  2. its ``/bin/sh -c '{ trap ... } ...; exec "$@" ... t3-claude claude ...'``
     wrapper, which repeats both markers inline.

  Rule (conservative): a process is ``t3_harness`` only when its argv carries
  BOTH a T3 worktree reference (``/.t3/worktrees/``) AND a T3 tool reference
  (``mcp__t3-code__``) AND names a known agent executable (claude / t3-claude /
  codex / dsh).  A manually launched agent that lacks either marker is NOT
  counted as a harness — it surfaces as a correlated duplicate instead (the
  safe direction: unknown/other, never a silently healthy fleet).
* ``dsh_direct`` — a DIRECT DeepSeek-Harness launcher outside a T3-owned run:
  the attended web server shapes observed live
  (``.../DeepSeek/releases/dsh-*/launch_attended.mjs`` and
  ``.../apps/cli/lib/bin.js web ...``) or a bare ``dsh`` executable, WITHOUT
  the T3 ACP profile rows (``--profile acp`` / ``--profile mmx-acp``).
* ``codex_cli`` — any ``codex`` executable invocation that is not a
  ``t3_harness`` (observed live: ``node /opt/homebrew/bin/codex app-server``
  and the vendored ``.../bin/codex app-server`` binary).
* ``other`` — everything else, including the T3 desktop app itself
  (``/Applications/T3 Code (Beta).app/...``), its tool servers
  (``~/.t3/tools/...``), tunnels, and non-agent processes.

Redaction before storage (argv tokens are evidence and outlive this process):
any whitespace-token WITHOUT ``/`` has every ``[A-Za-z0-9_-]{32,}`` substring
replaced with ``[REDACTED]`` (session ids, thread ids, opaque ids); tokens that
contain ``/`` are path-shaped and pass through the team-roster credential
scrubber only.  Classification is STABLE under this redaction (verified by
test): every marker it reads is shorter than 32 characters or lives in a
path-shaped token.

The subprocess call is injectable (``run_ps``); tests never shell out.
"""
from __future__ import annotations

import dataclasses
import re
import subprocess
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from control_plane.team_roster_projection import scrub

CENSUS_SCHEMA = "mastermind.t3_process_census/v1"
CENSUS_SOURCE = "ps -axo pid=,ppid=,lstart=,command= (argv only)"

# ── closed kind vocabulary ───────────────────────────────────────────────────

KIND_T3_HARNESS = "t3_harness"
KIND_DSH_DIRECT = "dsh_direct"
KIND_CODEX_CLI = "codex_cli"
KIND_OTHER = "other"
PROCESS_KINDS = frozenset({KIND_T3_HARNESS, KIND_DSH_DIRECT, KIND_CODEX_CLI, KIND_OTHER})

# Agent executables a T3 harness process can name (observed: claude/t3-claude;
# codex/dsh admitted by the donor census so provider-harness shapes classify).
_AGENT_EXECUTABLES = frozenset({"claude", "t3-claude", "codex", "dsh"})

# T3 markers (both observed live in every t3_harness argv; see module docstring).
_T3_WORKTREE_MARKER = "/.t3/worktrees/"
_T3_TOOL_MARKER = "mcp__t3-code__"

# DSH markers (observed live: attended web launchers under the release dir).
_DSH_RELEASE_MARKER = "/dsh-"
_DSH_DEEPSEEK_RELEASE_MARKER = "deepseek/releases/dsh-"
_DSH_EXECUTABLES = frozenset({"dsh", "dsh.exe"})
_T3_ACP_PROFILES = frozenset({"acp", "mmx-acp"})

#: closed label vocabulary (evidence markers, argv-derived only — never env)
LABELS = frozenset({
    "t3_worktree_ref", "t3_tool_ref", "t3_claude_ref", "acp_profile_rows",
    "dsh_release_ref", "attended_web_ref", "model_flag",
})

_TOKEN_LIKE = re.compile(r"[A-Za-z0-9_-]{32,}")
_MAX_ARGV_TOKENS = 512
_MAX_TOKEN_CHARS = 2048
_MAX_PROCESSES = 4096


class T3ProcessCensusError(ValueError):
    """A closed, typed census refusal (never carries argv content)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _refuse(code: str) -> None:
    raise T3ProcessCensusError(code)


# ── redaction ────────────────────────────────────────────────────────────────


def redact_token(token: str) -> str:
    """One argv token, made storable: token-like runs die unless path-shaped.

    A token containing ``/`` is a path (or path=value) — its long segments are
    directory names, not secrets — so it only passes the credential scrubber.
    A slash-free token has every ``[A-Za-z0-9_-]{32,}`` substring replaced with
    ``[REDACTED]`` before the scrubber runs (session ids, opaque ids).
    """
    if type(token) is not str:
        _refuse("ARGV_TOKEN_INVALID")
    if len(token) > _MAX_TOKEN_CHARS:
        return "[REDACTED]"
    if "/" in token:
        return scrub(token)
    return scrub(_TOKEN_LIKE.sub("[REDACTED]", token))


def redact_argv(argv: Iterable[str]) -> tuple[str, ...]:
    return tuple(redact_token(token) for token in argv)


# ── pure classifier ──────────────────────────────────────────────────────────


def _basename(token: str) -> str:
    return token.rsplit("/", 1)[-1]


def _has_t3_worktree_ref(tokens: Sequence[str]) -> bool:
    return any(_T3_WORKTREE_MARKER in token for token in tokens)


def _has_t3_tool_ref(tokens: Sequence[str]) -> bool:
    return any(_T3_TOOL_MARKER in token for token in tokens)


def _names_agent_executable(tokens: Sequence[str]) -> bool:
    if not tokens:
        return False
    if _basename(tokens[0]) in _AGENT_EXECUTABLES:
        return True
    return any(
        _basename(token) in _AGENT_EXECUTABLES for token in tokens[1:]
    )


def _acp_profile_rows(tokens: Sequence[str]) -> bool:
    for index, token in enumerate(tokens):
        if token == "--profile" and index + 1 < len(tokens):
            if tokens[index + 1] in _T3_ACP_PROFILES:
                return True
        if token.startswith("--profile="):
            if token.split("=", 1)[1] in _T3_ACP_PROFILES:
                return True
    return False


def _dsh_marker(tokens: Sequence[str]) -> bool:
    if not tokens:
        return False
    if _basename(tokens[0]).lower() in _DSH_EXECUTABLES:
        return True
    for token in tokens:
        if _DSH_DEEPSEEK_RELEASE_MARKER in token.lower():
            return True
        if _basename(token).lower() in _DSH_EXECUTABLES:
            return True
    return False


def _codex_marker(tokens: Sequence[str]) -> bool:
    if not tokens:
        return False
    if _basename(tokens[0]) == "codex":
        return True
    return any(_basename(token) == "codex" for token in tokens[1:])


def _model_flag(tokens: Sequence[str]) -> str | None:
    for index, token in enumerate(tokens):
        if token == "--model" and index + 1 < len(tokens):
            value = tokens[index + 1]
            if value and len(value) <= 64:
                return value
        if token.startswith("--model="):
            value = token.split("=", 1)[1]
            if value and len(value) <= 64:
                return value
    return None


def _workspace_refs(tokens: Sequence[str]) -> tuple[str, ...]:
    refs: list[str] = []
    for index, token in enumerate(tokens):
        candidate = ""
        if token in {"--add-dir", "--cwd", "-C"} and index + 1 < len(tokens):
            candidate = tokens[index + 1]
        elif token.startswith(("--add-dir=", "--cwd=")):
            candidate = token.split("=", 1)[1]
        elif _T3_WORKTREE_MARKER in token:
            candidate = token
        if candidate and _T3_WORKTREE_MARKER in candidate and candidate not in refs:
            refs.append(candidate)
    return tuple(refs)


@dataclasses.dataclass(frozen=True)
class Classification:
    """The closed classification of one process argv (all argv-derived)."""

    kind: str
    provider: str | None = None
    model: str | None = None
    workspace_refs: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "provider": self.provider,
            "model": self.model,
            "workspace_refs": list(self.workspace_refs),
            "labels": list(self.labels),
        }


def classify(argv: Iterable[str]) -> Classification:
    """Pure argv classification into the closed four-kind vocabulary.

    Stable under :func:`redact_argv` (test-verified): every marker is either
    shorter than 32 characters or lives inside a path-shaped token.  Order is
    significant and documented: the tight ``t3_harness`` rule (BOTH T3 markers
    AND an agent executable) wins first, so a T3-owned codex/dsh harness never
    misfiles as a duplicate launcher; then dsh shapes split by ACP rows; then
    codex; everything else is ``other``.
    """
    tokens = [str(token) for token in argv][:_MAX_ARGV_TOKENS]
    labels: set[str] = set()

    worktree = _has_t3_worktree_ref(tokens)
    tool_ref = _has_t3_tool_ref(tokens)
    agent_exec = _names_agent_executable(tokens)
    if worktree:
        labels.add("t3_worktree_ref")
    if tool_ref:
        labels.add("t3_tool_ref")
    if any(token == "t3-claude" for token in tokens):
        labels.add("t3_claude_ref")

    provider: str | None = None
    if agent_exec or tool_ref:
        if any(
            _basename(token) in {"claude", "t3-claude"} or "claude" == _basename(token)
            for token in tokens
        ):
            provider = "claude"
        elif _codex_marker(tokens):
            provider = "codex"
        elif _dsh_marker(tokens):
            provider = "dsh"

    model = _model_flag(tokens)
    if model is not None:
        labels.add("model_flag")

    # 1. T3-owned harness: BOTH markers plus an agent executable.
    if worktree and tool_ref and agent_exec:
        return Classification(
            kind=KIND_T3_HARNESS,
            provider=provider,
            model=model,
            workspace_refs=_workspace_refs(tokens),
            labels=tuple(sorted(labels)),
        )

    # 2. DSH shapes.  ACP profile rows are exactly how T3 launches its Local
    #    ACP provider (dsh --profile mmx-acp / --profile acp, donor census +
    #    control_plane/dsh_acp_runtime.py): argv alone cannot prove parentage,
    #    so the ACP shape files as the T3-owned harness (provider dsh) and a
    #    second one beside a thread still surfaces as a harness VIOLATION —
    #    never silently healthy.  Attended web / bare dsh shapes are direct.
    if _dsh_marker(tokens):
        if _acp_profile_rows(tokens):
            labels.add("acp_profile_rows")
            return Classification(
                kind=KIND_T3_HARNESS,
                provider="dsh",
                model=model,
                workspace_refs=_workspace_refs(tokens),
                labels=tuple(sorted(labels)),
            )
        if _DSH_DEEPSEEK_RELEASE_MARKER in " ".join(tokens).lower():
            labels.add("dsh_release_ref")
        if any(token == "web" for token in tokens[1:]):
            labels.add("attended_web_ref")
        return Classification(
            kind=KIND_DSH_DIRECT,
            provider="dsh",
            model=model,
            workspace_refs=_workspace_refs(tokens),
            labels=tuple(sorted(labels)),
        )

    # 3. Codex CLI (not a T3-owned harness).
    if _codex_marker(tokens):
        return Classification(
            kind=KIND_CODEX_CLI,
            provider="codex",
            model=model,
            workspace_refs=_workspace_refs(tokens),
            labels=tuple(sorted(labels)),
        )

    # 4. Everything else (T3 desktop app, ~/.t3 tool servers, tunnels,
    #    non-agent processes, unmarked agent launches).
    return Classification(
        kind=KIND_OTHER,
        provider=provider,
        model=model,
        workspace_refs=_workspace_refs(tokens),
        labels=tuple(sorted(labels)),
    )


# ── census snapshot ──────────────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class CensusProcess:
    """One observed process: redacted argv only, never env or secrets."""

    pid: int
    ppid: int
    argv: tuple[str, ...]
    started_epoch_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "ppid": self.ppid,
            "argv": list(self.argv),
            "started_epoch_s": self.started_epoch_s,
        }


@dataclasses.dataclass(frozen=True)
class CensusSnapshot:
    """One bounded point-in-time census; the only observer output."""

    schema: str = CENSUS_SCHEMA
    observed_at_utc: str = ""
    source: str = CENSUS_SOURCE
    processes: tuple[CensusProcess, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "observed_at_utc": self.observed_at_utc,
            "source": self.source,
            "processes": [process.to_dict() for process in self.processes],
        }


def _parse_ps_stdout(stdout: str) -> tuple[CensusProcess, ...]:
    processes: list[CensusProcess] = []
    for line in stdout.splitlines():
        parts = line.strip().split(None, 7)
        if len(parts) < 8:
            continue
        pid_text, ppid_text = parts[0], parts[1]
        if not pid_text.isdigit() or not ppid_text.isdigit():
            continue
        try:
            started = datetime.strptime(
                " ".join(parts[2:7]), "%a %b %d %H:%M:%S %Y"
            )
        except ValueError:
            continue
        argv = redact_argv(parts[7].split())
        processes.append(
            CensusProcess(
                pid=int(pid_text),
                ppid=int(ppid_text),
                argv=argv,
                started_epoch_s=started.timestamp(),
            )
        )
        if len(processes) >= _MAX_PROCESSES:
            break
    return tuple(processes)


def take_census(
    run_ps: Callable[[], str] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> CensusSnapshot:
    """One bounded ``ps`` observation (or an injected stdout for tests).

    A ps failure is an EMPTY census with the failure recorded by the caller —
    this function raises nothing but :class:`T3ProcessCensusError` for
    malformed injected output; a real ``ps`` error returns an empty snapshot
    (read as: no evidence), never a fabricated process.
    """
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    if run_ps is None:
        def run_ps() -> str:  # noqa: F811 — local default, argv only
            try:
                completed = subprocess.run(
                    ["ps", "-axo", "pid=,ppid=,lstart=,command="],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except (OSError, subprocess.SubprocessError):
                return ""
            return completed.stdout if completed.returncode == 0 else ""
    stdout = run_ps()
    if not isinstance(stdout, str):
        _refuse("PS_STDOUT_INVALID")
    processes = _parse_ps_stdout(stdout)
    return CensusSnapshot(
        observed_at_utc=now.astimezone(timezone.utc).isoformat(
            timespec="seconds"
        ),
        processes=processes,
    )


def census_from_dict(value: Mapping[str, Any]) -> CensusSnapshot:
    """Closed, fail-closed reconstruction of a saved census document."""
    if not isinstance(value, Mapping):
        _refuse("CENSUS_FIELDS_INVALID")
    if set(value) != {"schema", "observed_at_utc", "source", "processes"}:
        _refuse("CENSUS_FIELDS_INVALID")
    if value.get("schema") != CENSUS_SCHEMA:
        _refuse("CENSUS_SCHEMA_INVALID")
    observed = value.get("observed_at_utc")
    if type(observed) is not str or not observed:
        _refuse("CENSUS_OBSERVED_AT_INVALID")
    try:
        datetime.fromisoformat(
            observed[:-1] + "+00:00" if observed.endswith("Z") else observed
        )
    except ValueError:
        _refuse("CENSUS_OBSERVED_AT_INVALID")
    source = value.get("source")
    if type(source) is not str or not source or len(source) > 160:
        _refuse("CENSUS_SOURCE_INVALID")
    rows = value.get("processes")
    if type(rows) is not list or len(rows) > _MAX_PROCESSES:
        _refuse("CENSUS_PROCESSES_INVALID")
    processes: list[CensusProcess] = []
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {
            "pid", "ppid", "argv", "started_epoch_s"
        }:
            _refuse("CENSUS_PROCESS_FIELDS_INVALID")
        pid, ppid = row.get("pid"), row.get("ppid")
        if type(pid) is not int or pid < 1 or type(ppid) is not int or ppid < 0:
            _refuse("CENSUS_PROCESS_FIELDS_INVALID")
        argv = row.get("argv")
        if (
            type(argv) is not list
            or len(argv) > _MAX_ARGV_TOKENS
            or any(type(token) is not str for token in argv)
        ):
            _refuse("CENSUS_PROCESS_FIELDS_INVALID")
        started = row.get("started_epoch_s")
        if type(started) not in (int, float) or started < 0:
            _refuse("CENSUS_PROCESS_FIELDS_INVALID")
        processes.append(
            CensusProcess(
                pid=pid,
                ppid=ppid,
                argv=tuple(redact_token(token) for token in argv),
                started_epoch_s=float(started),
            )
        )
    return CensusSnapshot(
        observed_at_utc=observed,
        source=source,
        processes=tuple(processes),
    )


__all__ = [
    "CENSUS_SCHEMA",
    "CENSUS_SOURCE",
    "CensusProcess",
    "CensusSnapshot",
    "Classification",
    "KIND_CODEX_CLI",
    "KIND_DSH_DIRECT",
    "KIND_OTHER",
    "KIND_T3_HARNESS",
    "LABELS",
    "PROCESS_KINDS",
    "T3ProcessCensusError",
    "census_from_dict",
    "classify",
    "redact_argv",
    "redact_token",
    "take_census",
]
