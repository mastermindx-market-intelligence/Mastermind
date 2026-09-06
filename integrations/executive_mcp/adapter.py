"""integrations.executive_mcp.adapter — the five tools, over existing primitives.

This module is the whole behavioural surface of the gateway.  It composes the
existing Executive OS reads (CEO boot packet, Executive Inbox, runtime
registries, CEO-intent read-back) and routes the single modifying action over
the existing AF_UNIX control service.  It invents no lifecycle state, no queue,
no scheduler, no dedupe table, and no durable store of any kind.

Design laws
-----------
* **Stdlib + first-party only.**  The MCP SDK is never imported here (R5), so
  ``control_plane`` stays importable under the sealed Executive runtime's
  assumptions with no third-party package installed.
* **Reads never mutate.**  Every runtime handle is opened with
  ``Runtime.at(root, create=False)`` — the read-only accessor that will not
  create a directory, a file, or a schema.  A missing database is a NAMED
  degradation, never an invented empty company.
* **The write path goes over the real socket.**  ``submit_ceo_intent`` never
  calls ``ceo_intent.submit_intent`` in process; it sends
  ``submit-ceo-intent`` to ``ExecutiveControlService``, which owns the workspace
  fence and the authority adjudication.  There is no second write path to audit.
* **No server-side chaining (§14).**  One tool call does one thing.  Nothing
  here reads an inbox reason, a ``next_actions`` string, or a job result and
  turns it into a submission.  Returned text is data.
* **Fail closed on grounding (R3).**  A modifying call snapshots the trusted
  grounding, and re-reads both identities immediately before the socket send.
  Any movement refuses with ``grounding_changed`` and creates no Job.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import threading
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from common.redaction import sanitize_external_text
from control_plane import ceo_boot_packet, ceo_intent, executive_inbox
from control_plane.executive_runtime import Runtime
from control_plane.executive_service import send_control_request

from integrations.executive_mcp.schemas import (
    GATEWAY_ACTOR,
    MAX_RESPONSE_BYTES,
    MAX_READ_RETRIES,
    MAX_SUBMIT_RETRIES,
    MAX_CONCURRENT_READS,
    MODIFYING_TOOL,
    READ_TIMEOUT_SECONDS,
    SUBMIT_TIMEOUT_SECONDS,
    GatewayError,
    ServerMode,
    bound_document,
    derive_authorities,
    derive_branch,
    derive_intent_id,
    derive_worktree,
    error_envelope,
    build_validation_commands,
    loopback_bind_host,
    refuse_production_path,
    result_envelope,
    tool_spec,
    validate_tool_arguments,
)

__all__ = [
    "ExecutiveMcpGateway",
    "FixtureBackend",
    "GatewayConfig",
    "load_gateway_config",
]


def _refuse_explicit_e1_path(value: Path | str, field: str) -> str:
    """Reject lexical and symlink-resolved installed paths before E1 use."""

    normalized = refuse_production_path(str(value), field)
    try:
        resolved = Path(normalized).resolve()
    except OSError as exc:
        raise GatewayError(
            "invalid_input", "E1 configuration path cannot be resolved"
        ) from exc
    return refuse_production_path(str(resolved), field)


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class FixtureBackend:
    """A temporary Executive control service the FIXTURE mode may write to.

    Every path is refused if it names the installed production tree — at
    construction (startup) and again on every modifying call (R8).  Checking
    once at startup would leave a long-lived process trusting a decision made
    before anything moved.
    """

    socket_path: str
    runtime_root: str
    workspace_root: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "socket_path", refuse_production_path(self.socket_path, "fixture.socket_path")
        )
        object.__setattr__(
            self, "runtime_root", refuse_production_path(self.runtime_root, "fixture.runtime_root")
        )
        object.__setattr__(
            self,
            "workspace_root",
            refuse_production_path(self.workspace_root, "fixture.workspace_root"),
        )

    def reverify(self) -> None:
        """Re-run the production refusal.  Cheap, and it runs on every write."""

        refuse_production_path(self.socket_path, "fixture.socket_path")
        refuse_production_path(self.runtime_root, "fixture.runtime_root")
        refuse_production_path(self.workspace_root, "fixture.workspace_root")


@dataclasses.dataclass(frozen=True)
class GatewayConfig:
    """Reviewed host configuration.  No MCP request can reach any of these."""

    mode: ServerMode
    repo_root: Path
    #: Explicit temporary runtime for the E1 read profile.  It is host
    #: configuration, never a model/tool argument, and defaults to legacy root
    #: grounding when omitted.
    read_runtime_root: Path | str | None = None
    fixture: FixtureBackend | None = None
    macro_root_flag: str | None = None
    bind_host: str = "127.0.0.1"
    boot_packet_timeout: float = 60.0
    max_response_bytes: int = MAX_RESPONSE_BYTES
    #: Frozen clock for deterministic tests.  Never a request field.
    now: str | None = None

    def __post_init__(self) -> None:
        raw_repo_root = self.repo_root
        raw_macro_root = self.macro_root_flag
        raw_runtime_root = self.read_runtime_root
        # E1 is the only readonly profile with an explicit temporary runtime.
        # Fence all of its operator coordinates before accepting/resolving any
        # one of them; legacy readonly's omitted runtime behavior stays intact.
        if raw_runtime_root is not None:
            _refuse_explicit_e1_path(raw_repo_root, "repo_root")
            if raw_macro_root is not None:
                _refuse_explicit_e1_path(raw_macro_root, "macro_root")
            _refuse_explicit_e1_path(raw_runtime_root, "read_runtime_root")
        object.__setattr__(self, "repo_root", Path(self.repo_root).resolve())
        if self.read_runtime_root is not None:
            if self.mode is not ServerMode.READONLY or self.fixture is not None:
                raise GatewayError(
                    "invalid_input",
                    "read_runtime_root is only valid for non-fixture readonly reads",
                )
            requested_root = Path(self.read_runtime_root)
            resolved_root = Path(
                _refuse_explicit_e1_path(requested_root, "read_runtime_root")
            )
            object.__setattr__(self, "read_runtime_root", resolved_root)
        # Validated even though HTTP transport is not wired in this wave, so a
        # later change that wires it cannot introduce a public bind by omission.
        object.__setattr__(self, "bind_host", loopback_bind_host(self.bind_host))
        if self.mode is ServerMode.FIXTURE:
            if self.fixture is None:
                raise GatewayError(
                    "invalid_input",
                    "fixture mode requires an explicit fixture backend naming a "
                    "socket, runtime root, and workspace root",
                )
        elif self.fixture is not None:
            raise GatewayError(
                "invalid_input",
                "readonly mode must not be given a fixture backend; there is no "
                "production write mode in EXEC-MCP-A",
            )

    @property
    def runtime_root(self) -> Path:
        """Where ``executive_job`` / ``ceo_intent_status`` read lifecycle state.

        READONLY reads the reviewed repository checkout.  FIXTURE reads the
        temporary fixture runtime, which is what lets the operator acceptance
        flow read back the fixture Job it just created without ever pointing a
        read at the installed production runtime.
        """

        if self.fixture is not None:
            return Path(self.fixture.runtime_root)
        if self.read_runtime_root is not None:
            return Path(self.read_runtime_root)
        return self.repo_root

    def reverify_read_runtime_root(self) -> None:
        """Refuse a moved explicit E1 runtime root before every read."""

        if self.read_runtime_root is None:
            return
        root = Path(self.read_runtime_root)
        try:
            _refuse_explicit_e1_path(root, "read_runtime_root")
            _refuse_explicit_e1_path(
                root / executive_inbox.DB_RELATIVE_PATH, "read_runtime_db"
            )
        except GatewayError as exc:
            # The E1 profile must not disclose a production coordinate when a
            # previously accepted temporary tree is replaced with a symlink.
            # Preserve the typed refusal while making its public text generic.
            raise GatewayError(
                exc.code, "temporary E1 runtime configuration is unavailable"
            ) from exc


def load_gateway_config(
    mode: str, config_path: str | Path | None, *, repo_root: str | Path | None = None
) -> GatewayConfig:
    """Build a :class:`GatewayConfig` from a mode name and an optional JSON file.

    The JSON file is host configuration written by an operator, never anything a
    model supplies.  ``readonly`` needs no file; ``fixture`` requires one naming
    the temporary socket/runtime/workspace explicitly — there is deliberately no
    default fixture location to fall back to.
    """

    try:
        resolved_mode = ServerMode(str(mode).strip().lower())
    except ValueError as exc:
        raise GatewayError(
            "invalid_input",
            f"mode must be one of {[item.value for item in ServerMode]}",
        ) from exc

    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    payload: dict[str, Any] = {}
    if config_path is not None:
        path = Path(config_path)
        refuse_production_path(str(path.resolve()), "config_path")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise GatewayError(
                "invalid_input",
                f"gateway config is unreadable: {sanitize_external_text(exc)}",
            ) from exc
        if not isinstance(payload, Mapping):
            raise GatewayError("invalid_input", "gateway config must be a JSON object")

    allowed = {"fixture", "macro_root", "bind_host", "boot_packet_timeout", "repo_root"}
    unexpected = sorted(set(payload) - allowed)
    if unexpected:
        raise GatewayError("invalid_input", f"gateway config has unexpected key(s): {unexpected}")

    if "repo_root" in payload:
        root = Path(str(payload["repo_root"]))

    fixture: FixtureBackend | None = None
    raw_fixture = payload.get("fixture")
    if raw_fixture is not None:
        if not isinstance(raw_fixture, Mapping):
            raise GatewayError("invalid_input", "gateway config 'fixture' must be an object")
        expected = {"socket_path", "runtime_root", "workspace_root"}
        if set(raw_fixture) != expected:
            raise GatewayError(
                "invalid_input",
                f"gateway config 'fixture' must name exactly {sorted(expected)}",
            )
        fixture = FixtureBackend(
            socket_path=str(raw_fixture["socket_path"]),
            runtime_root=str(raw_fixture["runtime_root"]),
            workspace_root=str(raw_fixture["workspace_root"]),
        )

    return GatewayConfig(
        mode=resolved_mode,
        repo_root=root,
        fixture=fixture,
        macro_root_flag=str(payload["macro_root"]) if payload.get("macro_root") else None,
        bind_host=str(payload.get("bind_host", "127.0.0.1")),
        boot_packet_timeout=float(payload.get("boot_packet_timeout", 60.0)),
    )


# ---------------------------------------------------------------------------
# the gateway
# ---------------------------------------------------------------------------

#: Exception classes whose text may be shown (sanitized) rather than swallowed
#: into an opaque ``internal_error``.  Everything else is opaque by default.
_TRANSPORT_ERRORS = (ConnectionError, FileNotFoundError, OSError)

#: ``aclose`` is truthful but bounded: no read thread is cancelled, and a later
#: close may succeed after work that outlived this private shutdown budget ends.
_CLOSE_TIMEOUT_SECONDS = 5.0


class _ReadDeadlineExceeded(Exception):
    """Private marker that distinguishes this adapter's deadline from I/O errors."""


_READ_NOT_STARTED = object()


class _ReadAttempt:
    """Private ownership for one scheduled default-executor read attempt.

    Creating a ``to_thread`` task does not mean its callable has entered
    ``_read``: the existing default executor may still hold it in its queue.
    This short gate serializes that worker entry with timeout, cancellation, and
    close abandonment.  It is never held while the synchronous read runs.
    """

    def __init__(self, *, deadline: float, clock: Callable[[], float]) -> None:
        self._entry_gate = threading.Lock()
        self._state = "pending"
        self._abandonment: str | None = None
        self._deadline = deadline
        self._clock = clock
        self.task: asyncio.Task[Any] | None = None

    def enter(self) -> bool:
        """Claim the one transition that permits synchronous ``_read`` entry."""

        with self._entry_gate:
            if self._state != "pending":
                return False
            if self._clock() >= self._deadline:
                self._state = "abandoned"
                self._abandonment = "timeout"
                return False
            self._state = "started"
            return True

    def abandon(self, reason: str) -> bool:
        """Prevent a pending executor callable from entering ``_read`` later."""

        with self._entry_gate:
            if self._state != "pending":
                return False
            self._state = "abandoned"
            self._abandonment = reason
            return True

    def started(self) -> bool:
        with self._entry_gate:
            return self._state == "started"

    def abandonment(self) -> str | None:
        with self._entry_gate:
            return self._abandonment


class ExecutiveMcpGateway:
    """Five tools over existing Executive OS primitives.  No new authority."""

    def __init__(
        self,
        config: GatewayConfig,
        *,
        packet_builder: Callable[..., dict[str, Any]] | None = None,
        inbox_builder: Callable[..., dict[str, Any]] | None = None,
        runtime_factory: Callable[[Path], Runtime] | None = None,
        transport: Callable[..., Any] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.config = config
        self._packet_builder = packet_builder or ceo_boot_packet.build_packet
        self._inbox_builder = inbox_builder or executive_inbox.build_inbox
        self._runtime_factory = runtime_factory or _open_readonly_runtime
        self._transport = transport or send_control_request
        self._clock = clock or _utc_now_z
        # Bounded reader concurrency; exactly one modifying call in flight (R12).
        self._read_semaphore = asyncio.Semaphore(MAX_CONCURRENT_READS)
        # Close admission and worker entry share this short, process-local
        # linearization point.  It is never held while a synchronous read runs.
        self._read_entry_gate = threading.Lock()
        # This is private, process-local ownership only.  A token starts as a
        # pending executor callable; only its entry gate marks it physical.
        self._read_attempts: set[_ReadAttempt] = set()
        self._write_lock = asyncio.Lock()
        self._closed = False

    # -- lifecycle ---------------------------------------------------------

    async def aclose(self) -> None:
        """Close new admission and truthfully bound already-started reads."""

        physical_reads: list[asyncio.Task[Any]] = []
        with self._read_entry_gate:
            self._closed = True
            for attempt in tuple(self._read_attempts):
                if attempt.abandon("closed"):
                    # No synchronous work entered.  Cancelling removes queued
                    # executor work when possible; the entry gate refuses it if
                    # it raced into a worker thread but has not entered ``_read``.
                    if attempt.task is not None:
                        attempt.task.cancel()
                    continue
                if attempt.started() and attempt.task is not None:
                    physical_reads.append(attempt.task)
        if not physical_reads:
            return
        _done, pending = await asyncio.wait(
            physical_reads, timeout=_CLOSE_TIMEOUT_SECONDS
        )
        if pending:
            raise GatewayError(
                "timeout",
                "gateway close timed out waiting for "
                f"{len(pending)} active physical read(s)",
            )

    # -- public entry point ------------------------------------------------

    async def call(self, tool_name: str, arguments: Any) -> dict[str, Any]:
        """Run one tool call and return one response envelope.

        NEVER raises for an expected refusal: every typed error comes back as a
        structured envelope so the CEO seat can read the reason.  An unexpected
        exception becomes a bounded opaque ``internal_error`` — no traceback, no
        environment, no upstream repr.
        """

        generated_at = self._clock()
        try:
            spec = tool_spec(tool_name)
        except GatewayError as exc:
            return error_envelope(
                str(tool_name), mode=self.config.mode, generated_at=generated_at,
                code=exc.code, message=exc.message,
            )
        try:
            if self._closed:
                raise GatewayError(
                    "backend_unavailable",
                    "gateway is closed and cannot admit new calls",
                )
            validated = validate_tool_arguments(spec.name, arguments)
            if spec.name == MODIFYING_TOOL:
                return await self._run_submit(validated, generated_at)
            return await self._run_read(spec.name, validated, generated_at)
        except GatewayError as exc:
            return error_envelope(
                spec.name, mode=self.config.mode, generated_at=generated_at,
                code=exc.code, message=exc.message,
                intent_id=getattr(exc, "intent_id", None),
            )
        except asyncio.CancelledError:
            raise
        except BaseException as exc:  # noqa: BLE001 — opaque by contract (§15)
            return error_envelope(
                spec.name, mode=self.config.mode, generated_at=generated_at,
                code="internal_error",
                message=(
                    f"{type(exc).__name__} while serving {spec.name}; "
                    "details are withheld by contract"
                ),
            )

    # -- read path ---------------------------------------------------------

    async def _run_read(
        self, name: str, arguments: Mapping[str, Any], generated_at: str
    ) -> dict[str, Any]:
        attempts = MAX_READ_RETRIES + 1
        last: BaseException | None = None
        for _ in range(attempts):
            try:
                return await self._run_read_attempt(name, arguments, generated_at)
            except _ReadDeadlineExceeded as exc:
                # This must precede the broad OSError transport family: asyncio
                # TimeoutError aliases builtin TimeoutError, which is an OSError.
                raise GatewayError(
                    "timeout",
                    f"{name} exceeded the {READ_TIMEOUT_SECONDS:g}s read budget",
                ) from exc
            except _TRANSPORT_ERRORS as exc:
                # A completed, genuine transient transport failure is retried.
                # GatewayError remains a decision and is never retried.
                last = exc
                continue
        raise GatewayError(
            "backend_unavailable",
            f"{name} could not read Executive OS state: "
            f"{sanitize_external_text(last)}",
        )

    async def _run_read_attempt(
        self, name: str, arguments: Mapping[str, Any], generated_at: str
    ) -> dict[str, Any]:
        """Run one deadline-bounded read attempt without orphaning its permit."""

        loop = asyncio.get_running_loop()
        deadline = loop.time() + READ_TIMEOUT_SECONDS
        acquired = False
        try:
            try:
                async with asyncio.timeout_at(deadline):
                    await self._read_semaphore.acquire()
            except asyncio.TimeoutError as exc:
                raise _ReadDeadlineExceeded from exc
            acquired = True
            # A waiter that acquired concurrently with close must refuse and
            # release before it can start synchronous work.
            if self._closed:
                raise GatewayError(
                    "backend_unavailable",
                    "gateway is closed and cannot admit new calls",
                )
            if loop.time() >= deadline:
                raise _ReadDeadlineExceeded

            attempt = _ReadAttempt(deadline=deadline, clock=loop.time)
            physical = asyncio.create_task(
                asyncio.to_thread(
                    self._read_after_entry_gate,
                    attempt,
                    name,
                    arguments,
                    generated_at,
                )
            )
            attempt.task = physical
            self._read_attempts.add(attempt)
            physical.add_done_callback(
                lambda task: self._finish_read_attempt(task, attempt)
            )
            acquired = False

            physical_timeout = asyncio.timeout_at(deadline)
            try:
                async with physical_timeout:
                    # Shield preserves the physical task after a caller timeout
                    # or cancellation; its callback releases the real permit.
                    result = await asyncio.shield(physical)
            except asyncio.TimeoutError as exc:
                if physical_timeout.expired():
                    if attempt.abandon("timeout"):
                        physical.cancel()
                    raise _ReadDeadlineExceeded from exc
                # A synchronous reader may itself raise TimeoutError as an
                # allowed completed transport error; only our deadline is final.
                raise
            except asyncio.CancelledError:
                if attempt.abandonment() == "closed" and (
                    asyncio.current_task() is None
                    or asyncio.current_task().cancelling() == 0
                ):
                    raise GatewayError(
                        "backend_unavailable",
                        "gateway is closed and cannot admit new calls",
                    )
                if attempt.abandon("caller"):
                    physical.cancel()
                raise

            if result is _READ_NOT_STARTED:
                if attempt.abandonment() == "closed":
                    raise GatewayError(
                        "backend_unavailable",
                        "gateway is closed and cannot admit new calls",
                    )
                if attempt.abandonment() == "timeout":
                    raise _ReadDeadlineExceeded
                raise GatewayError(
                    "backend_unavailable",
                    "read attempt was abandoned before synchronous entry",
                )
            return result
        finally:
            if acquired:
                self._read_semaphore.release()

    def _read_after_entry_gate(
        self,
        attempt: _ReadAttempt,
        name: str,
        arguments: Mapping[str, Any],
        generated_at: str,
    ) -> dict[str, Any] | object:
        """Enter ``_read`` only if timeout, cancellation, and close lost the gate."""

        with self._read_entry_gate:
            if self._closed or not attempt.enter():
                if self._closed:
                    attempt.abandon("closed")
                return _READ_NOT_STARTED
        return self._read(name, arguments, generated_at)

    def _finish_read_attempt(self, task: asyncio.Task[Any], attempt: _ReadAttempt) -> None:
        """Release one permit and consume the outcome of a scheduled attempt."""

        try:
            task.result()
        except BaseException:
            # The caller may already have left.  It cannot observe this task,
            # but its completion is intentionally consumed rather than warned.
            pass
        finally:
            self._read_attempts.discard(attempt)
            self._read_semaphore.release()

    def _read(
        self, name: str, arguments: Mapping[str, Any], generated_at: str
    ) -> dict[str, Any]:
        if name == "executive_state":
            data, grounding, degraded = self._executive_state()
        elif name == "executive_inbox":
            data, grounding, degraded = self._executive_inbox()
        elif name == "executive_job":
            data, grounding, degraded = self._executive_job(str(arguments["job_id"]))
        elif name == "ceo_intent_status":
            data, grounding, degraded = self._ceo_intent_status(str(arguments["intent_id"]))
        else:  # pragma: no cover — tool_spec already refused an unknown name
            raise GatewayError("not_found", f"unknown tool {name!r}")
        bounded_data, receipts = bound_document(data, limit=self.config.max_response_bytes)
        return result_envelope(
            name, mode=self.config.mode, generated_at=generated_at,
            data=bounded_data, grounding=grounding, degraded=degraded, bounded=receipts,
        )

    def _collect(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """The boot packet and the inbox built FROM it — never re-derived."""

        self.config.reverify_read_runtime_root()
        packet = self._packet_builder(
            repo_root=self.config.repo_root,
            macro_root_flag=self.config.macro_root_flag,
            now=self.config.now,
            timeout=self.config.boot_packet_timeout,
        )
        inbox_kwargs: dict[str, Any] = {
            "repo_root": self.config.repo_root,
            "boot_packet": packet,
            "now": self.config.now,
        }
        # Fixture mode's historical inbox semantics remain repository-grounded;
        # only the explicit E1 root changes all four read projections.
        if self.config.read_runtime_root is not None:
            inbox_kwargs["runtime_root"] = self.config.runtime_root
        inbox = self._inbox_builder(
            **inbox_kwargs,
        )
        return packet, inbox

    def _runtime_label(self) -> str:
        """A stable, non-secret label for the runtime the reads resolve against.

        Never an absolute host path: emitting ``self.config.runtime_root`` across
        the MCP boundary would leak the operator home (``/Users/<operator>/...``)
        for a read, which §15 forbids for paths outside the approved boot-packet
        contract.  The mode plus the runtime directory's basename is enough for
        the CEO seat to tell READONLY from FIXTURE without any host path.
        """

        return f"{self.config.mode.value}:{Path(self.config.runtime_root).name}"

    def _mode_note(self) -> list[str]:
        """Name the read/write root split rather than letting it surprise anyone.

        Deliberately path-free: it states WHICH lane reads what, not the absolute
        host directories, so a degraded note cannot leak an operator home path.
        """

        if self.config.fixture is None:
            return []
        return [
            "mode=fixture: executive_job and ceo_intent_status read the temporary "
            "fixture runtime, while executive_state and executive_inbox project the "
            "reviewed repository checkout"
        ]

    def _executive_state(self) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        packet, inbox = self._collect()
        grounding = dict(inbox.get("grounding") or {})
        grounding["runtime"] = self._runtime_label()
        # The inbox already bubbles the packet's own degraded entries with a
        # ``boot_packet:`` prefix; passing its list through keeps every named
        # degradation without inventing or deduplicating any of them.
        degraded = [str(entry) for entry in (inbox.get("degraded") or [])]
        degraded.extend(self._mode_note())

        attention_counts: dict[str, int] = {target: 0 for target in executive_inbox.TARGETS}
        for item in inbox.get("attention") or []:
            target = str((item or {}).get("target") or "")
            if target in attention_counts:
                attention_counts[target] += 1
            else:
                attention_counts[target] = attention_counts.get(target, 0) + 1
        attention_counts["total"] = sum(
            value for key, value in attention_counts.items() if key != "total"
        )

        data = {
            "mastermind": dict((packet.get("mastermind") or {})),
            "macro": {
                key: (packet.get("macro") or {}).get(key)
                for key in ("root", "sha", "resolved_via")
            },
            "boot_packet_schema": packet.get("schema"),
            "inbox_schema": inbox.get("schema"),
            "strategic_state": packet.get("strategic_state"),
            "next_recommended_act": packet.get("next_recommended_act"),
            "runtime_db": (inbox.get("grounding") or {}).get("runtime_db"),
            "runtime_counts": inbox.get("runtime_counts"),
            "attention_counts": attention_counts,
            "handoffs": packet.get("handoffs"),
        }
        return data, grounding, degraded

    def _executive_inbox(self) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        _packet, inbox = self._collect()
        grounding = dict(inbox.get("grounding") or {})
        grounding["runtime"] = self._runtime_label()
        degraded = [str(entry) for entry in (inbox.get("degraded") or [])]
        degraded.extend(self._mode_note())
        # Verbatim.  Not re-ranked, not filtered, not re-scored: an unknown
        # future kind stays attention (commission §7).
        return dict(inbox), grounding, degraded

    def _runtime(self) -> Runtime:
        try:
            self.config.reverify_read_runtime_root()
            return self._runtime_factory(Path(self.config.runtime_root))
        except Exception as exc:  # noqa: BLE001 — named degradation, never empty success
            raise GatewayError(
                "backend_unavailable",
                "Executive runtime database is unavailable at "
                f"{self.config.runtime_root}: {sanitize_external_text(exc)}",
            ) from exc

    def _executive_job(self, job_id: str) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        runtime = self._runtime()
        job = runtime.jobs.get_job(job_id)
        if job is None:
            raise GatewayError("not_found", f"job {job_id!r} does not exist")
        attempts = runtime.attempts.list_attempts(job_id)
        latest = attempts[-1] if attempts else None
        data = {
            "job": job.to_dict() if hasattr(job, "to_dict") else dataclasses.asdict(job),
            "attempts": [attempt.to_dict() for attempt in attempts],
            "attempt_count": len(attempts),
            "attempt_limit": getattr(job, "attempt_limit", None),
            "latest_attempt": (latest.to_dict() if latest is not None else None),
        }
        grounding = {
            "runtime": self._runtime_label(),
            "source": "control_plane.executive_runtime registries (no raw SQL)",
        }
        return data, grounding, self._mode_note()

    def _ceo_intent_status(
        self, intent_id: str
    ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        runtime = self._runtime()
        try:
            receipt = ceo_intent.resolve_intent(runtime, intent_id)
        except ceo_intent.CeoIntentError as exc:
            raise GatewayError("not_found", sanitize_external_text(exc)) from exc
        grounding = {
            "runtime": self._runtime_label(),
            "source": "control_plane.ceo_intent.resolve_intent",
        }
        return receipt, grounding, self._mode_note()

    # -- grounding (R3) ----------------------------------------------------

    def _grounding_snapshot(self) -> tuple[dict[str, str], str, list[str]]:
        """Trusted grounding for a modifying call, or refuse.

        Returns ``(grounding, macro_root, degraded)``.  Nothing here is
        caller-supplied and nothing is guessed: a missing SHA, an unknown boot
        packet schema, or a degraded grounding input fails closed with
        ``grounding_unavailable`` and creates no Job (§10.8).
        """

        packet = self._packet_builder(
            repo_root=self.config.repo_root,
            macro_root_flag=self.config.macro_root_flag,
            now=self.config.now,
            timeout=self.config.boot_packet_timeout,
        )
        schema = packet.get("schema")
        if schema != ceo_boot_packet.SCHEMA:
            raise GatewayError(
                "grounding_unavailable",
                f"boot packet schema is {schema!r}, expected {ceo_boot_packet.SCHEMA!r}; "
                "no intent may be grounded on an unknown contract",
            )
        mastermind_sha = (packet.get("mastermind") or {}).get("sha")
        macro = packet.get("macro") or {}
        macro_sha = macro.get("sha")
        macro_root = macro.get("root")
        for label, value in (("mastermind", mastermind_sha), ("macro", macro_sha)):
            if not isinstance(value, str) or ceo_intent.SHA_RE.fullmatch(value) is None:
                raise GatewayError(
                    "grounding_unavailable",
                    f"{label} grounding SHA could not be established from the boot "
                    "packet; the gateway never substitutes HEAD or guesses",
                )
        if not isinstance(macro_root, str) or not macro_root:
            raise GatewayError(
                "grounding_unavailable",
                "the Macro checkout backing this grounding could not be resolved",
            )
        return (
            {
                "mastermind_sha": str(mastermind_sha),
                "macro_sha": str(macro_sha),
                "boot_packet_schema": str(schema),
            },
            macro_root,
            [str(entry) for entry in (packet.get("degraded") or [])],
        )

    def _reread_identities(self, macro_root: str) -> tuple[str | None, str | None]:
        """Re-read both HEAD identities immediately before the send (R3).

        Deliberately routed through the boot packet's public git helpers rather
        than a private copy, so a test that moves the tree moves this too.
        """

        return (
            ceo_boot_packet.git_sha(Path(self.config.repo_root)),
            ceo_boot_packet.git_sha(Path(macro_root)),
        )

    # -- write path --------------------------------------------------------

    def _build_envelope(
        self, arguments: Mapping[str, Any], grounding: Mapping[str, str]
    ) -> dict[str, Any]:
        """Assemble the canonical CEO-intent envelope from trusted derivations."""

        fixture = self.config.fixture
        if fixture is None:  # pragma: no cover — guarded by the mode check
            raise GatewayError("production_write_disabled", "no write backend is configured")

        intent_id = derive_intent_id(str(arguments["operation_key"]))
        authorities = derive_authorities(str(arguments["execution_profile"]))
        contract: dict[str, Any] = {
            "requested_authorities": authorities,
            "authority_level": "A0",
            "branch": derive_branch(intent_id),
            "worktree": derive_worktree(fixture.workspace_root, intent_id),
            "attempt_limit": int(arguments["attempt_limit"]),
        }
        paths = list(arguments.get("allowed_write_paths") or [])
        if paths:
            contract["allowed_write_paths"] = paths
        commands = build_validation_commands(arguments.get("validation"))
        if commands:
            contract["validation_commands"] = commands

        envelope: dict[str, Any] = {
            "schema": ceo_intent.INTENT_SCHEMA,
            "intent_id": intent_id,
            # Injected by trusted gateway code.  Provenance, never authentication
            # (R2/R6): no caller may set it and its value confers no privilege.
            "actor": GATEWAY_ACTOR,
            "objective": str(arguments["objective"]),
            "department": str(arguments["department"]),
            "priority": int(arguments["priority"]),
            "grounding": dict(grounding),
            "execution_contract": contract,
        }
        if arguments.get("workstream"):
            envelope["workstream"] = str(arguments["workstream"])
        return envelope

    async def _run_submit(
        self, arguments: Mapping[str, Any], generated_at: str
    ) -> dict[str, Any]:
        if self.config.mode is not ServerMode.FIXTURE or self.config.fixture is None:
            raise GatewayError(
                "production_write_disabled",
                "EXEC-MCP-A has no production write mode: submissions are available "
                "only against an explicitly configured temporary fixture backend. "
                "Arming production writes is a separate reviewed wave (EXEC-MCP-B), "
                "blocked on Phase 1C-A acceptance and on caller-identity binding.",
            )
        fixture = self.config.fixture
        # Re-verified per call, not merely at startup: a long-lived process must
        # not keep trusting a decision made before anything could move.
        fixture.reverify()

        # Exactly ONE modifying call in flight per process (R12/§16).  Zero
        # retries: idempotency rides operation_key + the upstream command_id
        # UNIQUE index, so a blind retry could only add noise.
        async with self._write_lock:
            assert MAX_SUBMIT_RETRIES == 0
            grounding, macro_root, packet_degraded = await asyncio.to_thread(
                self._grounding_snapshot
            )
            envelope = self._build_envelope(arguments, grounding)
            try:
                # Local pre-validation for a legible refusal.  The service
                # validates independently and is the authority; this never
                # replaces it.
                ceo_intent.validate_intent(envelope)
            except ceo_intent.CeoIntentError as exc:
                raise GatewayError("invalid_input", sanitize_external_text(exc)) from exc

            mastermind_now, macro_now = await asyncio.to_thread(
                self._reread_identities, macro_root
            )
            if (
                mastermind_now != grounding["mastermind_sha"]
                or macro_now != grounding["macro_sha"]
            ):
                raise GatewayError(
                    "grounding_changed",
                    "the Mastermind or Macro identity moved between the grounding "
                    "snapshot and submission; no Job was created",
                )

            try:
                response = await asyncio.wait_for(
                    self._transport(
                        fixture.socket_path, "submit-ceo-intent", {"intent": envelope}
                    ),
                    timeout=SUBMIT_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError as exc:
                raise GatewayError(
                    "timeout",
                    f"submission exceeded the {SUBMIT_TIMEOUT_SECONDS:g}s budget; "
                    "retry with the SAME operation_key to recover any durable Job",
                ) from exc
            except _TRANSPORT_ERRORS as exc:
                raise GatewayError(
                    "backend_unavailable",
                    "the Executive control service is unreachable: "
                    f"{sanitize_external_text(exc)}",
                ) from exc
            except Exception as exc:  # noqa: BLE001 — bounded, never a raw repr
                raise GatewayError(
                    "backend_unavailable",
                    f"the Executive control service refused the connection: "
                    f"{sanitize_external_text(exc)}",
                ) from exc

        try:
            receipt = _unwrap_control_response(response)
        except GatewayError as exc:
            # A same-key conflict refusal (§10.7) is only useful if the CEO seat
            # can still reach the durable Job.  The derived intent id is trusted,
            # gateway-authored local text, but ``sanitize_external_text`` redacts
            # its 32-hex fragment inside the message — so carry it structured.
            if exc.intent_id is None:
                exc.intent_id = str(envelope["intent_id"])
            raise
        data, receipts = bound_document(receipt, limit=self.config.max_response_bytes)
        return result_envelope(
            MODIFYING_TOOL,
            mode=self.config.mode,
            generated_at=generated_at,
            data=data,
            grounding=dict(grounding),
            degraded=packet_degraded,
            bounded=receipts,
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

#: Message fragments that identify an ``ExecutiveAuthorityPolicy`` refusal.  The
#: control protocol collapses every ``ValueError``/``StateConflict`` onto one
#: wire code, so the distinction between "authority denied" and "backend refused
#: this envelope" has to be read off the message.  Both refuse, both create no
#: Job; only the label differs.
_AUTHORITY_MARKERS = (
    "authority is denied",
    "authorities",
    "authority",
    "WRITE_BRANCH requires",
    "RUN_TESTS requires",
)


def _unwrap_control_response(response: Any) -> dict[str, Any]:
    """Turn one control-service response into a receipt or a typed refusal."""

    if not isinstance(response, Mapping):
        raise GatewayError(
            "backend_refused", "the Executive control service returned an invalid envelope"
        )
    if response.get("ok") is True:
        result = response.get("result")
        if not isinstance(result, Mapping):
            raise GatewayError(
                "backend_refused", "the Executive control service returned no receipt"
            )
        if result.get("dispatched") is not False:
            # Submission is never execution.  A receipt claiming otherwise means
            # the contract this gateway relies on has changed; refuse loudly.
            raise GatewayError(
                "backend_refused",
                "the CEO intent receipt does not report dispatched=false; refusing "
                "to present a submission as an execution",
            )
        return dict(result)

    error = response.get("error")
    detail = ""
    if isinstance(error, Mapping):
        detail = str(error.get("message") or error.get("code") or "")
    elif error is not None:
        detail = str(error)
    message = sanitize_external_text(detail) or "the Executive control service refused"
    lowered = message.lower()
    if any(marker.lower() in lowered for marker in _AUTHORITY_MARKERS):
        raise GatewayError("authority_refused", message)
    raise GatewayError("backend_refused", message)


def _open_readonly_runtime(root: Path) -> Runtime:
    """The ONLY runtime handle this package opens: read-only, never creating."""

    return Runtime.at(root, create=False)


def _utc_now_z() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
