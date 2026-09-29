"""Provider-native Claude Code Wake delivery for an exact dead session.

This adapter is deliberately transport-only.  Executive Wake owns lifecycle and
persistence; RuntimeBinding owns the exact session UUID.  The adapter resolves
that UUID in the provider's own transcript store (the store ``--resume``
actually consumes), refuses while the provider lists any writer for it, and
then performs at most one non-interactive exact ``--resume`` submission.  It
never treats model output as target acknowledgement or source resolution.

Receiver-safety invariants (each has a pinned test):

* the only inclusion evidence is the exact ``RuntimeBinding.native_handle``
  resolving to exactly one regular transcript in the store whose every
  ``sessionId`` record agrees; there is no title, newest, picker, or sibling
  fallback and no session registry of any kind;
* ``claude agents --json`` is an exclusion check only: any listed row for the
  handle refuses delivery so a nudge can never land inside an in-flight turn;
  an unreadable or unrecognised listing refuses because absence is unproven;
* the resume runs from the receiver's most recently recorded cwd, which must
  lie inside a constructor-supplied allowed root; ``--safe-mode`` disables
  directory-scoped customisation (CLAUDE.md, hooks, plugins, MCP) there;
* the delivery argv never carries ``--continue``, ``--fork-session``,
  ``--session-id`` or ``--from-pr`` (each can select or create a different
  receiver) and ``--resume`` is always given a canonical UUID because its value
  is optional and an empty value opens an interactive picker;
* failure classification is deterministic: only a non-zero provider exit whose
  transcript is byte-identical afterwards, whose project directory holds the
  same file names, and whose handle still resolves to that single file is a
  typed pre-effect refusal (the receiver observed nothing).  A zero exit, a
  provider envelope naming another session, or any store delta is
  effect-unknown and is reconciled by the fabric, never retried here;
* ``reconcile`` is read-only: it closes a late attempt as DELIVERED only when
  the exact nudge marker is recorded in the receiver's own transcript followed
  by a model-authored reply (provider-synthesised error or refusal records do
  not count), and it never submits.

Pre-effect refusals reach the fabric as ``TARGET_UNAVAILABLE`` receipts (the
sibling idiom, valid on both fabric entry points).  Their closed refusal class
is offered only to an optional in-process observer; it is never a receipt
detail and never names a session, path, or provider text.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import stat
import uuid
from pathlib import Path
from typing import Callable, Protocol, Sequence, runtime_checkable

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
        "cwd_outside_roots",
        "discovery_unavailable",
        "live_writer",
        "auth_refresh_contention",
        "pre_effect_failure",
    }
)
#: Exact provider text observed for the pre-effect token-refresh race between
#: concurrent Claude Code processes on one host.  Matching it only refines the
#: refusal class; the pre-effect proof itself is the unchanged store.
CLAUDE_WAKE_AUTH_REFRESH_CONTENTION_TEXT = "Failed to refresh OAuth token"

_DISCOVERY_STDOUT_MAX = 256 * 1024
_DELIVERY_STDOUT_MAX = 64 * 1024
_DEFAULT_DISCOVERY_TIMEOUT_SECONDS = 10.0
_DEFAULT_DELIVERY_TIMEOUT_SECONDS = 90.0
_STORE_PROJECTS_DIRNAME = "projects"
_STORE_FILE_MAX_BYTES = 256 * 1024 * 1024
_EMPTY_MCP_CONFIG = '{"mcpServers":{}}'
#: Model name the CLI stamps on records it synthesises itself (API errors, refusals, "No response requested.").
_SYNTHETIC_MODEL = "<synthetic>"
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
class _TranscriptScan:
    """One full pass over the exact transcript; never persisted."""

    digest: str
    last_cwd: Path | None
    marker_seen: bool
    marker_replied: bool


@dataclasses.dataclass(frozen=True)
class _StoreObservation:
    """Pre-effect facts about the exact receiver transcript; never persisted."""

    transcript: Path
    cwd: Path
    digest: str
    siblings: frozenset[str]


def _genuine_reply(record: dict) -> bool:
    """A model-authored assistant record; provider-synthesised error/refusal records do not count."""

    if record.get("isApiErrorMessage") is True:
        return False
    message = record.get("message")
    model = message.get("model") if isinstance(message, dict) else None
    return isinstance(model, str) and bool(model) and model != _SYNTHETIC_MODEL


def _refuse(refusal_class: str) -> WakePreSubmitError:
    if refusal_class not in CLAUDE_WAKE_REFUSAL_CLASSES:
        raise ValueError("unknown Claude Wake refusal class")
    return WakePreSubmitError(
        CLAUDE_WAKE_PRE_SUBMIT_PREFIX + refusal_class,
        outcome=TransportOutcome.TARGET_UNAVAILABLE,
        reason_code="target_unavailable",
    )


class ClaudeCodeWakeDispatcher:
    """Deliver one Wake nudge to one exact dead Claude Code conversation."""

    transport_id = "claude-code-session"
    reasoning_surface = "claude"

    def __init__(
        self,
        runner: ClaudeCodeWakeRunner,
        *,
        claude_binary: Path,
        claude_config_dir: Path,
        working_directory: Path,
        receiver_cwd_roots: Sequence[Path],
        discovery_timeout_seconds: float = _DEFAULT_DISCOVERY_TIMEOUT_SECONDS,
        delivery_timeout_seconds: float = _DEFAULT_DELIVERY_TIMEOUT_SECONDS,
        refusal_observer: Callable[[str], None] | None = None,
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
        roots = tuple(Path(root) for root in receiver_cwd_roots)
        if not roots or any(not root.is_absolute() for root in roots):
            raise ValueError("receiver_cwd_roots must be a non-empty tuple of absolute paths")
        if discovery_timeout_seconds <= 0 or delivery_timeout_seconds <= 0:
            raise ValueError("Claude Wake timeouts must be positive")
        if refusal_observer is not None and not callable(refusal_observer):
            raise ValueError("refusal_observer must be callable")
        self._runner = runner
        self._binary = str(binary)
        self._store_root = config_dir / _STORE_PROJECTS_DIRNAME
        self._cwd = cwd
        self._roots = roots
        self._discovery_timeout_seconds = float(discovery_timeout_seconds)
        self._delivery_timeout_seconds = float(delivery_timeout_seconds)
        self._refusal_observer = refusal_observer

    # -- receipts --------------------------------------------------------------

    @staticmethod
    def _receipt(outcome: TransportOutcome, reason_code: str, *, nudge_id: str) -> TransportReceipt:
        return TransportReceipt(
            outcome=outcome,
            reason_code=reason_code,
            created_at=utc_now_iso(),
            details=(("nudge_id", str(nudge_id)),),
        )

    def _refused(self, exc: WakePreSubmitError, *, nudge_id: str) -> TransportReceipt:
        if self._refusal_observer is not None:
            message = str(exc)
            if message.startswith(CLAUDE_WAKE_PRE_SUBMIT_PREFIX):
                self._refusal_observer(message[len(CLAUDE_WAKE_PRE_SUBMIT_PREFIX) :])
        return self._receipt(exc.outcome, exc.reason_code, nudge_id=nudge_id)

    # -- identity --------------------------------------------------------------

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
        try:
            if self._store_root.is_symlink():
                raise _refuse("store_symlink")
            if not self._store_root.is_dir():
                raise _refuse("store_root_absent")
            found: list[Path] = []
            for project_dir in self._store_root.iterdir():
                if project_dir.is_symlink() or not project_dir.is_dir():
                    continue
                candidate = project_dir / f"{native_handle}.jsonl"
                try:
                    mode = candidate.lstat().st_mode
                except FileNotFoundError:
                    continue
                if stat.S_ISLNK(mode):
                    raise _refuse("store_symlink")
                if stat.S_ISREG(mode):
                    found.append(candidate)
        except OSError:
            raise _refuse("store_unreadable") from None
        return found

    @staticmethod
    def _sibling_names(transcript: Path) -> frozenset[str]:
        return frozenset(
            entry.name
            for entry in transcript.parent.iterdir()
            if entry.suffix == ".jsonl" and not entry.is_symlink() and entry.is_file()
        )

    @staticmethod
    def _scan_transcript(transcript: Path, native_handle: str, *, marker: str | None = None) -> _TranscriptScan:
        """Single full pass: digest, identity agreement, last cwd, optional marker."""

        digest = hashlib.sha256()
        last_cwd: Path | None = None
        marker_bytes = marker.encode("utf-8") if marker else None
        marker_seen = False
        marker_replied = False
        with transcript.open("rb") as handle:
            for raw in handle:
                digest.update(raw)
                try:
                    record = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if not isinstance(record, dict):
                    continue
                session_id = record.get("sessionId")
                if isinstance(session_id, str) and session_id != native_handle:
                    raise _refuse("identity_mismatch")
                if session_id != native_handle:
                    continue
                value = record.get("cwd")
                if isinstance(value, str) and value.strip():
                    last_cwd = Path(value)
                if marker_bytes is None:
                    continue
                record_type = record.get("type")
                if record_type == "user" and marker_bytes in raw:
                    marker_seen = True
                    marker_replied = False
                elif record_type == "assistant" and marker_seen and _genuine_reply(record):
                    marker_replied = True
        return _TranscriptScan(
            digest=digest.hexdigest(),
            last_cwd=last_cwd,
            marker_seen=marker_seen,
            marker_replied=marker_replied,
        )

    def _receiver_cwd(self, scan: _TranscriptScan) -> Path:
        cwd = scan.last_cwd
        if cwd is None or not cwd.is_absolute() or not cwd.is_dir():
            raise _refuse("cwd_unresolved")
        try:
            resolved = cwd.resolve(strict=True)
        except OSError:
            raise _refuse("cwd_unresolved") from None
        for root in self._roots:
            try:
                if resolved == root.resolve() or resolved.is_relative_to(root.resolve()):
                    return cwd
            except OSError:
                continue
        raise _refuse("cwd_outside_roots")

    def _resolve_transcript(self, native_handle: str) -> Path:
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
        return transcript

    def _resolve_store(self, native_handle: str) -> _StoreObservation:
        transcript = self._resolve_transcript(native_handle)
        try:
            scan = self._scan_transcript(transcript, native_handle)
            siblings = self._sibling_names(transcript)
        except OSError:
            raise _refuse("store_unreadable") from None
        cwd = self._receiver_cwd(scan)
        return _StoreObservation(transcript=transcript, cwd=cwd, digest=scan.digest, siblings=siblings)

    def _observe_after(self, before: _StoreObservation, native_handle: str) -> tuple[str, frozenset[str], bool] | None:
        """(digest, sibling names, handle still resolves to exactly this file) or None."""

        try:
            if before.transcript.is_symlink() or not before.transcript.is_file():
                return None
            candidates = self._transcript_candidates(native_handle)
            scan = self._scan_transcript(before.transcript, native_handle)
            siblings = self._sibling_names(before.transcript)
        except (OSError, WakePreSubmitError):
            return None
        return scan.digest, siblings, candidates == [before.transcript]

    # -- exclusion: any listed writer for the handle refuses delivery ----------

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
            if not isinstance(row, dict) or not isinstance(row.get("sessionId"), str):
                raise _refuse("discovery_unavailable")
        if any(row["sessionId"] == native_handle for row in rows):
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
    def _envelope(result: ClaudeWakeCommandResult) -> dict | None:
        if len(result.stdout.encode("utf-8")) > _DELIVERY_STDOUT_MAX:
            return None
        try:
            payload = json.loads(result.stdout)
        except (TypeError, ValueError):
            return None
        return payload if isinstance(payload, dict) else None

    @classmethod
    def _validate_delivery(cls, result: ClaudeWakeCommandResult, native_handle: str) -> bool:
        if result.returncode != 0:
            return False
        payload = cls._envelope(result)
        if payload is None or payload.get("is_error") is not False:
            return False
        if payload.get("session_id") != native_handle:
            return False
        return payload.get("structured_output") == {"wake_delivery": CLAUDE_WAKE_DELIVERY_SENTINEL}

    @staticmethod
    def _failure_class(result: ClaudeWakeCommandResult) -> str:
        if CLAUDE_WAKE_AUTH_REFRESH_CONTENTION_TEXT in result.stdout or (
            CLAUDE_WAKE_AUTH_REFRESH_CONTENTION_TEXT in result.stderr
        ):
            return "auth_refresh_contention"
        return "pre_effect_failure"

    async def nudge(self, wake: WakeNudge) -> TransportReceipt:
        nudge_id = str(getattr(wake, "nudge_id", "") or "")
        try:
            native_handle = self._identity_ok(wake)
            if native_handle is None:
                raise _refuse("identity_unbound")
            before = self._resolve_store(native_handle)
            await self._refuse_live_writer(native_handle)
        except WakePreSubmitError as exc:
            return self._refused(exc, nudge_id=nudge_id)
        try:
            result = await self._runner.run(
                argv=self._delivery_argv(wake, native_handle),
                cwd=before.cwd,
                timeout_seconds=self._delivery_timeout_seconds,
            )
        except Exception:
            raise WakeEffectUnknownError(
                "Claude exact-session resume effect is unknown after provider submission may have begun"
            ) from None
        after = self._observe_after(before, native_handle)
        if after is None:
            raise WakeEffectUnknownError("Claude exact-session transcript is unobservable after resume")
        digest_after, siblings_after, still_unique = after
        store_unchanged = digest_after == before.digest and siblings_after == before.siblings and still_unique
        if not isinstance(result, ClaudeWakeCommandResult):
            raise WakeEffectUnknownError("Claude exact-session resume returned an untyped result")
        if self._validate_delivery(result, native_handle):
            if digest_after == before.digest or siblings_after != before.siblings or not still_unique:
                raise WakeEffectUnknownError(
                    "Claude exact-session resume reported delivery without a same-session-only transcript change"
                )
            return self._receipt(TransportOutcome.DELIVERED, "delivered", nudge_id=wake.nudge_id)
        if result.returncode != 0 and store_unchanged:
            envelope = self._envelope(result)
            reported = envelope.get("session_id") if envelope is not None else None
            if reported is None or reported == native_handle:
                return self._refused(_refuse(self._failure_class(result)), nudge_id=wake.nudge_id)
        raise WakeEffectUnknownError("Claude exact-session resume completion is effect-unknown")

    # -- late reconciliation: read-only, never submits ---------------------------

    async def reconcile(self, wake: WakeNudge) -> TransportReceipt:
        native_handle = self._identity_ok(wake)
        if native_handle is None:
            raise WakeEffectUnknownError("Claude late reconciliation identity is not the bound transport")
        try:
            transcript = self._resolve_transcript(native_handle)
            scan = self._scan_transcript(transcript, native_handle, marker=wake.nudge_id)
        except (OSError, WakePreSubmitError):
            raise WakeEffectUnknownError("Claude late reconciliation cannot observe the exact transcript") from None
        if scan.marker_seen and scan.marker_replied:
            return self._receipt(TransportOutcome.DELIVERED, "delivered", nudge_id=wake.nudge_id)
        if scan.marker_seen:
            raise WakeEffectUnknownError("Claude exact-session reply to the Wake marker is not yet recorded")
        try:
            await self._refuse_live_writer(native_handle)
        except WakePreSubmitError:
            raise WakeEffectUnknownError("Claude late reconciliation cannot prove the receiver observed nothing") from None
        return self._receipt(TransportOutcome.TARGET_UNAVAILABLE, "target_unavailable", nudge_id=wake.nudge_id)


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
