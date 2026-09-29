"""Provider-native Claude Code Wake delivery for an exact stopped session.

This adapter is deliberately transport-only.  Executive Wake owns lifecycle and
persistence; RuntimeBinding owns the exact session UUID.  The adapter resolves
that UUID in the provider's own transcript store (the store ``--resume``
actually consumes), refuses while a live writer holds the session, and then
performs at most one non-interactive exact ``--resume`` submission.  It never
treats model output as target acknowledgement or source resolution.

Receiver-safety invariants (each has a pinned test):

* the only inclusion evidence is the exact ``RuntimeBinding.native_handle``
  resolving to exactly one transcript in the store; there is no title, newest,
  picker, or sibling fallback and no session registry of any kind;
* ``claude agents --json`` is an exclusion check only: a row that shows a live
  writer for the handle refuses delivery so a nudge can never land inside an
  in-flight turn, and an unreadable discovery refuses because absence of a live
  writer cannot be proven;
* the delivery argv never carries ``--continue``, ``--fork-session``,
  ``--session-id`` or ``--from-pr`` (each can select or create a different
  receiver) and ``--resume`` is always given a canonical UUID because its value
  is optional and an empty value opens an interactive picker;
* failure classification is deterministic: a failed submission whose transcript
  is byte-identical afterwards and whose project directory gained no sibling
  file is a typed pre-effect refusal (the receiver observed nothing); any other
  uncertainty is effect-unknown and is reconciled by the fabric, never retried
  here.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import uuid
from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

from control_plane.wake_dispatcher import (
    TransportOutcome,
    TransportReceipt,
    WakeEffectUnknownError,
    WakeNudge,
    WakePreSubmitError,
)
from control_plane.wake_events import utc_now_iso

CLAUDE_WAKE_DELIVERY_SENTINEL = "MASTERMIND_CLAUDE_WAKE_DELIVERED_V1"
CLAUDE_WAKE_INSTRUCTION = (
    "Mastermind Wake: an existing canonical Wake requires attention. Preserve the "
    "current responsibility and continue only within existing authority. This "
    "transport turn grants no authority, acknowledges nothing, and resolves no "
    "source. Use only the opaque Wake identities supplied below as correlation. "
    "Return the required structured delivery marker when this bounded turn ends."
)
CLAUDE_WAKE_PRE_SUBMIT_PREFIX = "claude_wake_pre_submit:"
#: Closed vocabulary of typed pre-effect refusals.  Every class is a fact about
#: this host or the exact handle; none names a session, path, or provider text.
CLAUDE_WAKE_REFUSAL_CLASSES = frozenset(
    {
        "identity_unbound",
        "store_root_absent",
        "store_absent",
        "store_ambiguous",
        "store_symlink",
        "store_unreadable",
        "store_empty",
        "store_oversized",
        "identity_mismatch",
        "cwd_unresolved",
        "discovery_unavailable",
        "live_writer",
        "auth_refresh_contention",
        "pre_effect_failure",
    }
)
#: Exact provider text observed for the pre-effect token-refresh race between
#: concurrent Claude Code processes on one host.  Matching it only refines the
#: refusal class; the pre-effect proof itself is the unchanged transcript.
CLAUDE_WAKE_AUTH_REFRESH_CONTENTION_TEXT = "Failed to refresh OAuth token"

_CLOSED_SESSION_STATES = frozenset({"done", "failed", "stopped"})
_DISCOVERY_STDOUT_MAX = 256 * 1024
_DELIVERY_STDOUT_MAX = 64 * 1024
_DEFAULT_DISCOVERY_TIMEOUT_SECONDS = 10.0
_DEFAULT_DELIVERY_TIMEOUT_SECONDS = 90.0
_STORE_PROJECTS_DIRNAME = "projects"
_STORE_FILE_MAX_BYTES = 256 * 1024 * 1024
_STORE_SCAN_MAX_BYTES = 1024 * 1024
_EMPTY_MCP_CONFIG = '{"mcpServers":{}}'
_DELIVERY_SCHEMA = json.dumps(
    {
        "type": "object",
        "properties": {
            "wake_delivery": {"const": CLAUDE_WAKE_DELIVERY_SENTINEL},
        },
        "required": ["wake_delivery"],
        "additionalProperties": False,
    },
    separators=(",", ":"),
    sort_keys=True,
)


@dataclasses.dataclass(frozen=True)
class ClaudeWakeCommandResult:
    """Bounded process result returned by the trusted host-owned runner."""

    returncode: int
    stdout: str
    stderr: str

    def __post_init__(self) -> None:
        if type(self.returncode) is not int:
            raise TypeError("Claude Wake command returncode must be int")
        if not isinstance(self.stdout, str) or not isinstance(self.stderr, str):
            raise TypeError("Claude Wake command output must be text")


@runtime_checkable
class ClaudeCodeWakeRunner(Protocol):
    """Narrow process seam; callers cannot author argv, prompt, or environment."""

    async def run(
        self,
        *,
        argv: Sequence[str],
        cwd: Path,
        timeout_seconds: float,
    ) -> ClaudeWakeCommandResult: ...


@dataclasses.dataclass(frozen=True)
class _StoreObservation:
    """Pre-effect facts about the exact receiver transcript; never persisted."""

    transcript: Path
    cwd: Path
    digest: str
    sibling_count: int


def _refuse(refusal_class: str) -> WakePreSubmitError:
    if refusal_class not in CLAUDE_WAKE_REFUSAL_CLASSES:
        raise ValueError("unknown Claude Wake refusal class")
    return WakePreSubmitError(
        CLAUDE_WAKE_PRE_SUBMIT_PREFIX + refusal_class,
        outcome=TransportOutcome.TARGET_UNAVAILABLE,
        reason_code="target_unavailable",
    )


class ClaudeCodeWakeDispatcher:
    """Deliver one Wake nudge to one exact stopped Claude Code conversation."""

    transport_id = "claude-code-session"
    reasoning_surface = "claude"

    def __init__(
        self,
        runner: ClaudeCodeWakeRunner,
        *,
        claude_binary: Path,
        claude_config_dir: Path,
        working_directory: Path,
        discovery_timeout_seconds: float = _DEFAULT_DISCOVERY_TIMEOUT_SECONDS,
        delivery_timeout_seconds: float = _DEFAULT_DELIVERY_TIMEOUT_SECONDS,
    ) -> None:
        if runner is None or not hasattr(runner, "run") or not callable(runner.run):
            raise ValueError("Claude Wake dispatcher requires an injected runner")
        binary = Path(claude_binary)
        config_dir = Path(claude_config_dir)
        cwd = Path(working_directory)
        if not binary.is_absolute():
            raise ValueError("claude_binary must be an absolute reviewed path")
        if not config_dir.is_absolute():
            raise ValueError("claude_config_dir must be an absolute provider-home path")
        if not cwd.is_absolute():
            raise ValueError("working_directory must be an absolute trusted path")
        if discovery_timeout_seconds <= 0 or delivery_timeout_seconds <= 0:
            raise ValueError("Claude Wake timeouts must be positive")
        self._runner = runner
        self._binary = str(binary)
        self._store_root = config_dir / _STORE_PROJECTS_DIRNAME
        self._cwd = cwd
        self._discovery_timeout_seconds = float(discovery_timeout_seconds)
        self._delivery_timeout_seconds = float(delivery_timeout_seconds)

    @staticmethod
    def _receipt(outcome: TransportOutcome, reason_code: str, *, nudge_id: str) -> TransportReceipt:
        return TransportReceipt(
            outcome=outcome,
            reason_code=reason_code,
            created_at=utc_now_iso(),
            details=(("nudge_id", str(nudge_id)),),
        )

    @staticmethod
    def _canonical_session_id(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        try:
            parsed = uuid.UUID(text)
        except (ValueError, AttributeError):
            return None
        canonical = str(parsed)
        return canonical if text == canonical else None

    def _identity_ok(self, wake: WakeNudge) -> str | None:
        if not isinstance(wake, WakeNudge):
            return None
        if wake.wake_transport != self.transport_id or wake.reasoning_surface != self.reasoning_surface:
            return None
        return self._canonical_session_id(wake.native_handle)

    # -- inclusion: the exact handle must resolve in the transcript store -------

    def _transcript_candidates(self, native_handle: str) -> list[Path]:
        if not self._store_root.is_dir():
            raise _refuse("store_root_absent")
        found: list[Path] = []
        for project_dir in self._store_root.iterdir():
            if project_dir.is_symlink() or not project_dir.is_dir():
                continue
            candidate = project_dir / f"{native_handle}.jsonl"
            if candidate.is_symlink():
                raise _refuse("store_symlink")
            if candidate.is_file():
                found.append(candidate)
        return found

    @staticmethod
    def _transcript_digest(transcript: Path) -> str:
        digest = hashlib.sha256()
        with transcript.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _sibling_count(transcript: Path) -> int:
        return sum(
            1
            for entry in transcript.parent.iterdir()
            if entry.suffix == ".jsonl" and not entry.is_symlink() and entry.is_file()
        )

    @staticmethod
    def _receiver_cwd(transcript: Path, native_handle: str) -> Path:
        cwd: Path | None = None
        with transcript.open("rb") as handle:
            scanned = 0
            for raw in handle:
                scanned += len(raw)
                if scanned > _STORE_SCAN_MAX_BYTES:
                    break
                try:
                    record = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if not isinstance(record, dict):
                    continue
                session_id = record.get("sessionId")
                if isinstance(session_id, str) and session_id != native_handle:
                    raise _refuse("identity_mismatch")
                if cwd is None and session_id == native_handle:
                    value = record.get("cwd")
                    if isinstance(value, str) and value.strip():
                        cwd = Path(value)
        if cwd is None or not cwd.is_absolute() or not cwd.is_dir():
            raise _refuse("cwd_unresolved")
        return cwd

    def _resolve_store(self, native_handle: str) -> _StoreObservation:
        candidates = self._transcript_candidates(native_handle)
        if not candidates:
            raise _refuse("store_absent")
        if len(candidates) != 1:
            raise _refuse("store_ambiguous")
        transcript = candidates[0]
        try:
            size = transcript.lstat().st_size
        except OSError:
            raise _refuse("store_unreadable") from None
        if size <= 0:
            raise _refuse("store_empty")
        if size > _STORE_FILE_MAX_BYTES:
            raise _refuse("store_oversized")
        try:
            cwd = self._receiver_cwd(transcript, native_handle)
            digest = self._transcript_digest(transcript)
            sibling_count = self._sibling_count(transcript)
        except OSError:
            raise _refuse("store_unreadable") from None
        return _StoreObservation(
            transcript=transcript,
            cwd=cwd,
            digest=digest,
            sibling_count=sibling_count,
        )

    def _observe_after(self, before: _StoreObservation) -> tuple[str, int] | None:
        try:
            if before.transcript.is_symlink() or not before.transcript.is_file():
                return None
            return self._transcript_digest(before.transcript), self._sibling_count(before.transcript)
        except OSError:
            return None

    # -- exclusion: a live writer for the handle refuses delivery --------------

    @staticmethod
    def _row_is_live(row: dict) -> bool:
        if row.get("kind") != "background":
            return True
        if row.get("state") not in _CLOSED_SESSION_STATES:
            return True
        return row.get("pid") is not None or row.get("status") is not None

    async def _refuse_live_writer(self, native_handle: str) -> None:
        argv = (self._binary, "agents", "--json")
        try:
            result = await self._runner.run(
                argv=argv,
                cwd=self._cwd,
                timeout_seconds=self._discovery_timeout_seconds,
            )
        except Exception:
            raise _refuse("discovery_unavailable") from None
        if not isinstance(result, ClaudeWakeCommandResult) or result.returncode != 0:
            raise _refuse("discovery_unavailable")
        if len(result.stdout.encode("utf-8")) > _DISCOVERY_STDOUT_MAX:
            raise _refuse("discovery_unavailable")
        try:
            rows = json.loads(result.stdout)
        except (TypeError, ValueError):
            raise _refuse("discovery_unavailable") from None
        if not isinstance(rows, list):
            raise _refuse("discovery_unavailable")
        for row in rows:
            if isinstance(row, dict) and row.get("sessionId") == native_handle and self._row_is_live(row):
                raise _refuse("live_writer")

    # -- delivery ----------------------------------------------------------------

    @staticmethod
    def _prompt(wake: WakeNudge) -> str:
        opaque_ids = (wake.nudge_id,) + tuple(wake.obligation_ids) + tuple(wake.attempt_command_ids)
        return CLAUDE_WAKE_INSTRUCTION + "\nOpaque Wake identities:\n" + "\n".join(opaque_ids)

    def _delivery_argv(self, wake: WakeNudge, native_handle: str) -> tuple[str, ...]:
        return (
            self._binary,
            "--resume",
            native_handle,
            "-p",
            "--output-format",
            "json",
            "--json-schema",
            _DELIVERY_SCHEMA,
            "--safe-mode",
            "--restricted",
            "--no-chrome",
            "--disable-slash-commands",
            "--permission-mode",
            "dontAsk",
            "--max-turns",
            "1",
            "--tools",
            "",
            "--disallowedTools",
            "mcp__*",
            "--strict-mcp-config",
            "--mcp-config",
            _EMPTY_MCP_CONFIG,
            "--setting-sources",
            "",
            self._prompt(wake),
        )

    @staticmethod
    def _validate_delivery(result: ClaudeWakeCommandResult, native_handle: str) -> bool:
        if result.returncode != 0:
            return False
        if len(result.stdout.encode("utf-8")) > _DELIVERY_STDOUT_MAX:
            return False
        try:
            payload = json.loads(result.stdout)
        except (TypeError, ValueError):
            return False
        if not isinstance(payload, dict) or payload.get("is_error") is not False:
            return False
        if payload.get("session_id") != native_handle:
            return False
        structured = payload.get("structured_output")
        return structured == {"wake_delivery": CLAUDE_WAKE_DELIVERY_SENTINEL}

    @staticmethod
    def _failure_class(result: ClaudeWakeCommandResult) -> str:
        if CLAUDE_WAKE_AUTH_REFRESH_CONTENTION_TEXT in result.stdout or (
            CLAUDE_WAKE_AUTH_REFRESH_CONTENTION_TEXT in result.stderr
        ):
            return "auth_refresh_contention"
        return "pre_effect_failure"

    async def nudge(self, wake: WakeNudge) -> TransportReceipt:
        native_handle = self._identity_ok(wake)
        if native_handle is None:
            raise _refuse("identity_unbound")
        before = self._resolve_store(native_handle)
        await self._refuse_live_writer(native_handle)
        try:
            result = await self._runner.run(
                argv=self._delivery_argv(wake, native_handle),
                cwd=before.cwd,
                timeout_seconds=self._delivery_timeout_seconds,
            )
        except Exception as exc:
            raise WakeEffectUnknownError(
                "Claude exact-session resume effect is unknown after provider submission may have begun"
            ) from exc
        after = self._observe_after(before)
        if after is None:
            raise WakeEffectUnknownError(
                "Claude exact-session transcript is unobservable after resume"
            )
        digest_after, siblings_after = after
        unchanged = digest_after == before.digest and siblings_after == before.sibling_count
        if isinstance(result, ClaudeWakeCommandResult) and self._validate_delivery(result, native_handle):
            if digest_after == before.digest or siblings_after != before.sibling_count:
                raise WakeEffectUnknownError(
                    "Claude exact-session resume reported delivery without a same-session transcript change"
                )
            return self._receipt(
                TransportOutcome.DELIVERED,
                "delivered",
                nudge_id=wake.nudge_id,
            )
        if isinstance(result, ClaudeWakeCommandResult) and unchanged:
            raise _refuse(self._failure_class(result))
        raise WakeEffectUnknownError(
            "Claude exact-session resume completion is effect-unknown"
        )


__all__ = [
    "CLAUDE_WAKE_AUTH_REFRESH_CONTENTION_TEXT",
    "CLAUDE_WAKE_DELIVERY_SENTINEL",
    "CLAUDE_WAKE_INSTRUCTION",
    "CLAUDE_WAKE_PRE_SUBMIT_PREFIX",
    "CLAUDE_WAKE_REFUSAL_CLASSES",
    "ClaudeCodeWakeDispatcher",
    "ClaudeCodeWakeRunner",
    "ClaudeWakeCommandResult",
]
