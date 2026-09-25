"""Provider-native Claude Code Wake delivery for an exact stopped session.

This adapter is deliberately transport-only.  Executive Wake owns lifecycle and
persistence; RuntimeBinding owns the exact session UUID.  The adapter performs
one read-only discovery and, only for one exact stopped/unattached background
session, one non-interactive ``--resume`` submission.  It never treats model
output as target acknowledgement or source resolution.
"""
from __future__ import annotations

import dataclasses
import json
import uuid
from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

from control_plane.wake_dispatcher import (
    TransportOutcome,
    TransportReceipt,
    WakeEffectUnknownError,
    WakeNudge,
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

_CLOSED_SESSION_STATES = frozenset({"done", "failed", "stopped"})
_DISCOVERY_STDOUT_MAX = 256 * 1024
_DELIVERY_STDOUT_MAX = 64 * 1024
_DEFAULT_DISCOVERY_TIMEOUT_SECONDS = 10.0
_DEFAULT_DELIVERY_TIMEOUT_SECONDS = 90.0
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


class ClaudeCodeWakeDispatcher:
    """Deliver one Wake nudge to one exact stopped Claude Code conversation."""

    transport_id = "claude-code-session"
    reasoning_surface = "claude"

    def __init__(
        self,
        runner: ClaudeCodeWakeRunner,
        *,
        claude_binary: Path,
        working_directory: Path,
        discovery_timeout_seconds: float = _DEFAULT_DISCOVERY_TIMEOUT_SECONDS,
        delivery_timeout_seconds: float = _DEFAULT_DELIVERY_TIMEOUT_SECONDS,
    ) -> None:
        if runner is None or not hasattr(runner, "run") or not callable(runner.run):
            raise ValueError("Claude Wake dispatcher requires an injected runner")
        binary = Path(claude_binary)
        cwd = Path(working_directory)
        if not binary.is_absolute():
            raise ValueError("claude_binary must be an absolute reviewed path")
        if not cwd.is_absolute():
            raise ValueError("working_directory must be an absolute trusted path")
        if discovery_timeout_seconds <= 0 or delivery_timeout_seconds <= 0:
            raise ValueError("Claude Wake timeouts must be positive")
        self._runner = runner
        self._binary = str(binary)
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

    async def _discover(self, native_handle: str) -> bool:
        argv = (self._binary, "agents", "--json", "--all")
        try:
            result = await self._runner.run(
                argv=argv,
                cwd=self._cwd,
                timeout_seconds=self._discovery_timeout_seconds,
            )
        except Exception:
            return False
        if not isinstance(result, ClaudeWakeCommandResult) or result.returncode != 0:
            return False
        if len(result.stdout.encode("utf-8")) > _DISCOVERY_STDOUT_MAX:
            return False
        try:
            rows = json.loads(result.stdout)
        except (TypeError, ValueError):
            return False
        if not isinstance(rows, list):
            return False
        matches = [row for row in rows if isinstance(row, dict) and row.get("sessionId") == native_handle]
        if len(matches) != 1:
            return False
        row = matches[0]
        if row.get("kind") != "background":
            return False
        short_id = row.get("id")
        if not isinstance(short_id, str) or not short_id.strip():
            return False
        state = row.get("state")
        if state not in _CLOSED_SESSION_STATES:
            return False
        if row.get("pid") is not None or row.get("status") is not None:
            return False
        return True

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

    async def nudge(self, wake: WakeNudge) -> TransportReceipt:
        native_handle = self._identity_ok(wake)
        if native_handle is None:
            nudge_id = wake.nudge_id if isinstance(wake, WakeNudge) else "unbound"
            return self._receipt(
                TransportOutcome.TARGET_UNAVAILABLE,
                "target_unavailable",
                nudge_id=nudge_id,
            )
        if not await self._discover(native_handle):
            return self._receipt(
                TransportOutcome.TARGET_UNAVAILABLE,
                "target_unavailable",
                nudge_id=wake.nudge_id,
            )
        try:
            result = await self._runner.run(
                argv=self._delivery_argv(wake, native_handle),
                cwd=self._cwd,
                timeout_seconds=self._delivery_timeout_seconds,
            )
        except Exception as exc:
            raise WakeEffectUnknownError(
                "Claude exact-session resume effect is unknown after provider submission may have begun"
            ) from exc
        if not isinstance(result, ClaudeWakeCommandResult) or not self._validate_delivery(result, native_handle):
            raise WakeEffectUnknownError(
                "Claude exact-session resume completion is effect-unknown"
            )
        return self._receipt(
            TransportOutcome.DELIVERED,
            "delivered",
            nudge_id=wake.nudge_id,
        )


__all__ = [
    "CLAUDE_WAKE_DELIVERY_SENTINEL",
    "CLAUDE_WAKE_INSTRUCTION",
    "ClaudeCodeWakeDispatcher",
    "ClaudeCodeWakeRunner",
    "ClaudeWakeCommandResult",
]
