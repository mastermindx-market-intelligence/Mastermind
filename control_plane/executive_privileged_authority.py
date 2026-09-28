"""Job-bound login-status observations on the existing Runtime and broker.

The exact request/binding/result contracts and Event-backed controller share
one current-Attempt admission boundary. A family authorizes at most one fixed
verify_only send; later invocations recover evidence through broker status.
No worker root grant, retry plane, READY assertion or second Runtime is added.
"""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import re
from typing import Any, Mapping


REQUEST_KEYS = frozenset({"job_id", "attempt_id", "fence_generation"})

FIXED_ACTION = "executive.worker_auth.verify_only"
OBSERVATION_SCOPE = "LOGIN_STATUS_ONLY_NO_READY_ASSERTION"

FAMILY_KEY_SCHEMA = "mastermind.executive_privileged_readiness_family_key/v1"
BINDING_SCHEMA = "mastermind.executive_privileged_readiness_binding/v1"
RESULT_SCHEMA = "mastermind.executive_privileged_readiness_result/v1"

READINESS_AGGREGATE_TYPE = "privileged_readiness"

# The protected broker also refuses replay of a reconciled NOT_APPLIED
# request. Preserve that reason without a success or retry assertion.
# EFFECT_UNKNOWN names an unresolved effect and must never become a refusal.
BROKER_REFUSAL_REASON_CODES = frozenset(
    {"PEER_UNAUTHORIZED", "REQUEST_ID_CONFLICT", "REFUSED", "RECONCILED_NOT_APPLIED"}
)
BROKER_EFFECT_UNKNOWN_ERROR = "EFFECT_UNKNOWN"

REASON_ORIGIN_BROKER = "BROKER"

RESULT_CANONICAL_KEYS = frozenset(
    {
        "schema_version",
        "family_id",
        "operation_id",
        "state",
        "replayed",
        "observed_at_ms",
        "evidence_currency",
        "observation_scope",
        "binding",
        "receipt",
        "reason_origin",
        "reason_code",
    }
)

FAMILY_ID_PREFIX = "pvrf-"
OPERATION_ID_PREFIX = "pvr-"
_ID_HEX_LENGTH = 48

_JOB_ID_RE = re.compile(r"^JOB-(?:(?!000$)[0-9]{3}|[1-9][0-9]{3,17})$")
_ATTEMPT_ID_RE = re.compile(r"^ATT-[0-9a-f]{32}$")
_SAFE_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_RELEASE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_BOOT_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_FAMILY_ID_RE = re.compile(r"^pvrf-[0-9a-f]{48}$")
_OPERATION_ID_RE = re.compile(r"^pvr-[0-9a-f]{48}$")
_ADAPTER_FALLBACK_RE = re.compile(r"^adapter-[0-9]+$")
_NIL_BOOT_UUID = "00000000-0000-0000-0000-000000000000"

BINDING_CANONICAL_KEYS = frozenset(
    {
        "schema_version",
        "action",
        "job_id",
        "attempt_id",
        "worker_id",
        "quota_class",
        "fence_generation",
        "authority_policy_hash",
        "effective_grant_digest",
        "release_sha",
        "boot_id",
        "slot_id",
    }
)


class PrivilegedReadinessError(ValueError):
    """The readiness request/binding is outside the reviewed contract."""


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Sorted-key, compact, UTF-8 canonical JSON with no NaN/Infinity."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _require_exact_keys(mapping: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    observed = frozenset(mapping)
    if observed != expected:
        raise PrivilegedReadinessError(
            f"{label} keys must be exactly {sorted(expected)}; got {sorted(observed)}"
        )


def _require_pattern(value: Any, field: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise PrivilegedReadinessError(f"{field} is not a bounded safe identifier")
    return value


def validate_job_id(value: Any) -> str:
    return _require_pattern(value, "job_id", _JOB_ID_RE)


def validate_attempt_id(value: Any) -> str:
    return _require_pattern(value, "attempt_id", _ATTEMPT_ID_RE)


def validate_safe_id(value: Any, field: str) -> str:
    return _require_pattern(value, field, _SAFE_ID_RE)


def validate_fence_generation(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PrivilegedReadinessError("fence_generation must be a JSON integer")
    if value <= 0:
        raise PrivilegedReadinessError("fence_generation must be a positive integer")
    return value


def validate_release_sha(value: Any) -> str:
    if not isinstance(value, str) or _RELEASE_SHA_RE.fullmatch(value) is None:
        raise PrivilegedReadinessError("release_sha must be lowercase 40-hex")
    return value


def validate_sha256_hex(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256_HEX_RE.fullmatch(value) is None:
        raise PrivilegedReadinessError(f"{field} must be lowercase 64-hex")
    return value


def validate_effective_grant_digest(value: Any) -> str | None:
    if value is None:
        return None
    return validate_sha256_hex(value, "effective_grant_digest")


def validate_boot_id(value: Any) -> str:
    """Validate a real kernel boot-session UUID; reject the adapter-<pid> fallback.

    UUID case is representation, not identity: the real macOS kernel returns
    uppercase text, so both spellings are accepted and normalized to the same
    lowercase canonical string, ensuring one boot session hashes to one ID.
    """

    if not isinstance(value, str) or not value:
        raise PrivilegedReadinessError("boot_id is not a real kernel boot-session identity")
    if _ADAPTER_FALLBACK_RE.fullmatch(value) is not None:
        raise PrivilegedReadinessError("boot_id cannot be a process-local adapter fallback")
    if _BOOT_UUID_RE.fullmatch(value) is None:
        raise PrivilegedReadinessError("boot_id must be a canonical kernel boot-session UUID")
    canonical = value.lower()
    if canonical == _NIL_BOOT_UUID:
        raise PrivilegedReadinessError("boot_id cannot be the nil UUID")
    return canonical


@dataclasses.dataclass(frozen=True)
class ReadinessRequest:
    """One strict external login-check request; exactly three caller fields."""

    job_id: str
    attempt_id: str
    fence_generation: int

    def __post_init__(self) -> None:
        validate_job_id(self.job_id)
        validate_attempt_id(self.attempt_id)
        validate_fence_generation(self.fence_generation)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "attempt_id": self.attempt_id,
            "fence_generation": self.fence_generation,
        }


def validate_readiness_request(raw: Any) -> ReadinessRequest:
    if not isinstance(raw, Mapping):
        raise PrivilegedReadinessError("readiness request must be a mapping")
    _require_exact_keys(raw, REQUEST_KEYS, "readiness request")
    return ReadinessRequest(
        job_id=raw["job_id"],
        attempt_id=raw["attempt_id"],
        fence_generation=raw["fence_generation"],
    )


@dataclasses.dataclass(frozen=True)
class ReadinessFamilyKey:
    """The logical effect key ``(job_id, attempt_id, fence_generation, action)``."""

    job_id: str
    attempt_id: str
    fence_generation: int
    action: str = FIXED_ACTION

    def __post_init__(self) -> None:
        validate_job_id(self.job_id)
        validate_attempt_id(self.attempt_id)
        validate_fence_generation(self.fence_generation)
        if self.action != FIXED_ACTION:
            raise PrivilegedReadinessError("family key action must be the fixed verify_only action")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": FAMILY_KEY_SCHEMA,
            "action": self.action,
            "job_id": self.job_id,
            "attempt_id": self.attempt_id,
            "fence_generation": self.fence_generation,
        }

    @property
    def family_id(self) -> str:
        digest = hashlib.sha256(canonical_json_bytes(self.to_canonical_dict())).hexdigest()
        return f"{FAMILY_ID_PREFIX}{digest[:_ID_HEX_LENGTH]}"


def family_key_from_request(request: ReadinessRequest) -> ReadinessFamilyKey:
    return ReadinessFamilyKey(
        job_id=request.job_id,
        attempt_id=request.attempt_id,
        fence_generation=request.fence_generation,
    )


@dataclasses.dataclass(frozen=True)
class ReadinessBinding:
    """The complete first-admission binding; source of the ``pvr-...`` operation ID."""

    job_id: str
    attempt_id: str
    worker_id: str
    quota_class: str
    fence_generation: int
    authority_policy_hash: str
    effective_grant_digest: str | None
    release_sha: str
    boot_id: str
    slot_id: str
    schema_version: str = BINDING_SCHEMA
    action: str = FIXED_ACTION

    def __post_init__(self) -> None:
        validate_job_id(self.job_id)
        validate_attempt_id(self.attempt_id)
        validate_safe_id(self.worker_id, "worker_id")
        validate_safe_id(self.quota_class, "quota_class")
        validate_fence_generation(self.fence_generation)
        validate_sha256_hex(self.authority_policy_hash, "authority_policy_hash")
        validate_effective_grant_digest(self.effective_grant_digest)
        validate_release_sha(self.release_sha)
        canonical_boot_id = validate_boot_id(self.boot_id)
        if canonical_boot_id != self.boot_id:
            object.__setattr__(self, "boot_id", canonical_boot_id)
        validate_safe_id(self.slot_id, "slot_id")
        if self.schema_version != BINDING_SCHEMA:
            raise PrivilegedReadinessError("binding schema_version is not the reviewed binding schema")
        if self.action != FIXED_ACTION:
            raise PrivilegedReadinessError("binding action must be the fixed verify_only action")
        if self.slot_id != self.worker_id:
            raise PrivilegedReadinessError("binding slot_id must equal worker_id")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "action": self.action,
            "job_id": self.job_id,
            "attempt_id": self.attempt_id,
            "worker_id": self.worker_id,
            "quota_class": self.quota_class,
            "fence_generation": self.fence_generation,
            "authority_policy_hash": self.authority_policy_hash,
            "effective_grant_digest": self.effective_grant_digest,
            "release_sha": self.release_sha,
            "boot_id": self.boot_id,
            "slot_id": self.slot_id,
        }

    @property
    def operation_id(self) -> str:
        digest = hashlib.sha256(canonical_json_bytes(self.to_canonical_dict())).hexdigest()
        return f"{OPERATION_ID_PREFIX}{digest[:_ID_HEX_LENGTH]}"


class ReadinessResultState(str, enum.Enum):
    """The closed login-check result domain.

    There is deliberately no ready-to-work member: the fixed
    ``observation_scope`` below bounds every member to point-in-time
    login-status evidence.
    """

    TERMINAL = "TERMINAL"
    REFUSED = "REFUSED"
    EFFECT_UNKNOWN = "EFFECT_UNKNOWN"


class ReadinessEvidenceCurrency(str, enum.Enum):
    """How current the binding's release/boot/policy facts are at return time.

    This bounds only fact freshness. Neither member asserts a worker is
    usable, that a credential is valid, or that a provider account resolved.
    """

    CURRENT = "CURRENT"
    HISTORICAL = "HISTORICAL"


class ReadinessEventPhase(str, enum.Enum):
    """The closed set of durable ``events`` rows one operation family may hold."""

    INTENT = "PRIVILEGED_READINESS_INTENT"
    ATTEMPTED = "PRIVILEGED_READINESS_ATTEMPTED"
    TERMINAL = "PRIVILEGED_READINESS_TERMINAL"
    BROKER_REFUSED = "PRIVILEGED_READINESS_BROKER_REFUSED"
    EFFECT_UNKNOWN = "PRIVILEGED_READINESS_EFFECT_UNKNOWN"
    RECONCILED = "PRIVILEGED_READINESS_RECONCILED"


def result_state_for_broker_error(code: Any) -> ReadinessResultState:
    """Map one merged-broker wire error code onto the closed result domain.

    ``EFFECT_UNKNOWN`` is an unresolved effect, never a refusal, so it must not
    collapse into ``REFUSED``. An unrecognised code fails closed instead of
    defaulting, so a future broker code cannot silently become a refusal.
    """

    if not isinstance(code, str):
        raise PrivilegedReadinessError("broker error code is not a string")
    if code == BROKER_EFFECT_UNKNOWN_ERROR:
        return ReadinessResultState.EFFECT_UNKNOWN
    if code in BROKER_REFUSAL_REASON_CODES:
        return ReadinessResultState.REFUSED
    raise PrivilegedReadinessError(f"broker error code {code!r} is outside the reviewed domain")


def evidence_currency_for(
    binding: "ReadinessBinding",
    *,
    current_boot_id: Any,
    current_release_sha: Any,
    current_authority_policy_hash: Any,
) -> ReadinessEvidenceCurrency:
    """Compare a stored binding against freshly observed host facts.

    ``CURRENT`` requires exact equality on all three facts. Any mismatch, any
    unprovable fact (``None``), and any malformed observation yields
    ``HISTORICAL``. Boot-session UUID case is representation, not identity, so
    both spellings canonicalize before comparison.
    """

    if not isinstance(binding, ReadinessBinding):
        raise PrivilegedReadinessError("evidence currency requires a validated binding")
    try:
        observed_boot_id = validate_boot_id(current_boot_id)
        observed_release_sha = validate_release_sha(current_release_sha)
        observed_policy_hash = validate_sha256_hex(
            current_authority_policy_hash, "current_authority_policy_hash"
        )
    except PrivilegedReadinessError:
        return ReadinessEvidenceCurrency.HISTORICAL
    if (
        observed_boot_id == binding.boot_id
        and observed_release_sha == binding.release_sha
        and observed_policy_hash == binding.authority_policy_hash
    ):
        return ReadinessEvidenceCurrency.CURRENT
    return ReadinessEvidenceCurrency.HISTORICAL


@dataclasses.dataclass(frozen=True)
class ReadinessResult:
    """One secret-free login-check result projection.

    State/receipt/reason coherence is enforced at construction so a consumer
    can never read a success receipt off a refusal or an unresolved effect.
    """

    family_id: str
    operation_id: str
    state: ReadinessResultState
    replayed: bool
    observed_at_ms: int
    evidence_currency: ReadinessEvidenceCurrency
    binding: "ReadinessBinding"
    receipt: Mapping[str, Any] | None = None
    reason_origin: str | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        _require_pattern(self.family_id, "family_id", _FAMILY_ID_RE)
        _require_pattern(self.operation_id, "operation_id", _OPERATION_ID_RE)
        if not isinstance(self.state, ReadinessResultState):
            raise PrivilegedReadinessError("state is outside the closed result domain")
        if not isinstance(self.evidence_currency, ReadinessEvidenceCurrency):
            raise PrivilegedReadinessError("evidence_currency is outside the closed domain")
        if type(self.replayed) is not bool:
            raise PrivilegedReadinessError("replayed must be a real boolean")
        if type(self.observed_at_ms) is not int or self.observed_at_ms <= 0:
            raise PrivilegedReadinessError("observed_at_ms must be a positive integer")
        if not isinstance(self.binding, ReadinessBinding):
            raise PrivilegedReadinessError("binding must be a validated ReadinessBinding")
        if self.state is ReadinessResultState.TERMINAL:
            if not isinstance(self.receipt, Mapping):
                raise PrivilegedReadinessError("a terminal result requires a validated receipt")
            if self.reason_origin is not None or self.reason_code is not None:
                raise PrivilegedReadinessError("a terminal result carries no refusal reason")
        elif self.state is ReadinessResultState.REFUSED:
            if self.receipt is not None:
                raise PrivilegedReadinessError("a refusal carries no receipt")
            if self.reason_origin != REASON_ORIGIN_BROKER:
                raise PrivilegedReadinessError("a refusal reason must originate at the broker")
            if self.reason_code not in BROKER_REFUSAL_REASON_CODES:
                raise PrivilegedReadinessError("refusal reason_code is outside the broker domain")
        else:
            if self.receipt is not None:
                raise PrivilegedReadinessError("an unresolved effect carries no receipt")
            if self.reason_origin is not None or self.reason_code is not None:
                raise PrivilegedReadinessError("an unresolved effect carries no refusal reason")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RESULT_SCHEMA,
            "family_id": self.family_id,
            "operation_id": self.operation_id,
            "state": self.state.value,
            "replayed": self.replayed,
            "observed_at_ms": self.observed_at_ms,
            "evidence_currency": self.evidence_currency.value,
            "observation_scope": OBSERVATION_SCOPE,
            "binding": self.binding.to_canonical_dict(),
            "receipt": dict(self.receipt) if self.receipt is not None else None,
            "reason_origin": self.reason_origin,
            "reason_code": self.reason_code,
        }


@dataclasses.dataclass(frozen=True)
class ReadinessEventFamily:
    """Validated immutable history; its presence never grants another effect."""

    binding: ReadinessBinding
    phase: ReadinessEventPhase
    state: ReadinessResultState
    receipt: Mapping[str, Any] | None = None
    reason_code: str | None = None


def broker_request_for(binding: ReadinessBinding) -> dict[str, Any]:
    from control_plane.executive_privileged_action import REQUEST_SCHEMA

    return {"schema": REQUEST_SCHEMA, "request_id": binding.operation_id,
            "action": FIXED_ACTION, "args": {"slot_id": binding.slot_id}}


def validate_event_family(events, request: ReadinessRequest) -> ReadinessEventFamily | None:
    """Validate a complete exact-aggregate history before replay or reconciliation.

    INTENT and ATTEMPTED are one atomic admission; a lone intent is corrupt.
    Terminal evidence is correlated against the original frozen action, digest
    and release, including after policy/boot/Attempt turnover. No current
    authority, database, filesystem or broker read is performed here.
    """
    from control_plane.executive_privileged_action import canonical_request_bytes, validate_request
    from control_plane.executive_privileged_broker import validate_terminal_receipt

    if not events:
        return None
    try:
        binding_value = events[0].payload["binding"]
        _require_exact_keys(binding_value, BINDING_CANONICAL_KEYS, "stored binding")
        binding = ReadinessBinding(**binding_value)
        expected_family = family_key_from_request(request).family_id
        actual_family = ReadinessFamilyKey(
            binding.job_id, binding.attempt_id, binding.fence_generation,
        ).family_id
        if actual_family != expected_family:
            raise PrivilegedReadinessError("stored family does not match the request")
        phases = tuple(ReadinessEventPhase(event.event_type) for event in events)
        P = ReadinessEventPhase
        admitted = (P.INTENT, P.ATTEMPTED)
        allowed = {admitted, admitted + (P.TERMINAL,), admitted + (P.BROKER_REFUSED,),
                   admitted + (P.EFFECT_UNKNOWN,), admitted + (P.RECONCILED,),
                   admitted + (P.EFFECT_UNKNOWN, P.RECONCILED)}
        if phases not in allowed:
            raise PrivilegedReadinessError("stored family phase ordering is invalid")
        for sequence, (event, phase) in enumerate(zip(events, phases), 1):
            suffix = "" if phase is P.INTENT else ":" + phase.name.lower()
            if (event.aggregate_type != READINESS_AGGREGATE_TYPE
                    or event.aggregate_id != expected_family or event.sequence != sequence
                    or event.command_id != binding.operation_id + suffix
                    or event.job_id != binding.job_id or event.attempt_id != binding.attempt_id
                    or event.worker_id != binding.worker_id or event.quota_class != binding.quota_class
                    or event.payload.get("binding") != binding.to_canonical_dict()):
                raise PrivilegedReadinessError("stored family identity or binding drifted")
            keys = {"binding"}
            if phase in (P.TERMINAL, P.RECONCILED):
                keys.add("receipt")
            elif phase is P.BROKER_REFUSED:
                keys.add("reason_code")
            _require_exact_keys(event.payload, frozenset(keys), "stored event payload")
        receipt = None
        reason_code = None
        phase = phases[-1]
        if phase in (P.TERMINAL, P.RECONCILED):
            wire_request = validate_request(broker_request_for(binding))
            receipt = validate_terminal_receipt(
                events[-1].payload["receipt"], expected_request_id=binding.operation_id,
                expected_request_sha256=hashlib.sha256(canonical_request_bytes(wire_request)).hexdigest(),
                expected_release_sha=binding.release_sha, expected_action=FIXED_ACTION,
            )
            state = ReadinessResultState.TERMINAL
        elif phase is P.BROKER_REFUSED:
            reason_code = events[-1].payload["reason_code"]
            state = result_state_for_broker_error(reason_code)
            if state is not ReadinessResultState.REFUSED:
                raise PrivilegedReadinessError("stored refusal contains an unresolved effect")
        else:
            state = ReadinessResultState.EFFECT_UNKNOWN
        return ReadinessEventFamily(binding, phase, state, receipt, reason_code)
    except (KeyError, TypeError, AttributeError, ValueError, RuntimeError) as exc:
        raise PrivilegedReadinessError("privileged readiness event family is invalid") from exc


class PrivilegedReadinessController:
    """One current-Attempt admission and one broker send, recovered from Events."""

    def __init__(self, runtime, *, release_sha: str, boot_observer=None,
                 policy_loader=None, broker_client=None):
        from control_plane.executive_authority import ExecutiveAuthorityPolicy
        from control_plane import executive_privileged_client
        from control_plane.codex_worker import ProcessInspector

        self.runtime = runtime
        self.release_sha = validate_release_sha(release_sha)
        self._boot_observer = boot_observer or ProcessInspector().boot_session_id
        self._policy_loader = policy_loader or ExecutiveAuthorityPolicy.load
        self._client = broker_client or executive_privileged_client
        self._flights = {}
        self._closed = False

    async def check(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        import asyncio

        if self._closed:
            raise PrivilegedReadinessError("readiness controller is closing")
        request = validate_readiness_request(raw)
        key = family_key_from_request(request).family_id
        task = self._flights.get(key)
        if task is None:
            task = asyncio.create_task(self._run(request))
            self._flights[key] = task

            def finished(done):
                if self._flights.get(key) is done:
                    self._flights.pop(key, None)
                # A disconnected caller must not leave an unobserved exception.
                if not done.cancelled():
                    done.exception()
            task.add_done_callback(finished)
        # Client disconnect does not cancel an already admitted host effect.
        return await asyncio.shield(task)

    async def aclose(self):
        """Stop local owners; durable ATTEMPTED evidence forbids resubmission."""
        import asyncio

        self._closed = True
        tasks = tuple(self._flights.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _family(self, request, *, connection=None):
        rows = self.runtime.store.list_events(
            aggregate_type=READINESS_AGGREGATE_TYPE,
            aggregate_id=family_key_from_request(request).family_id,
            connection=connection,
        )
        return validate_event_family(rows, request)

    @staticmethod
    def _authority_inputs(job):
        return canonical_json_bytes({
            "requested_authorities": job.requested_authorities, "worktree": job.worktree,
            "allowed_write_paths": job.allowed_write_paths,
            "validation_commands": job.validation_commands,
        })

    def _admit_or_replay(self, request):
        from control_plane.executive_runtime import AttemptStatus
        from control_plane.executive_supervisor import validate_effective_grant
        from control_plane.executive_privileged_action import validate_request
        from ops.executive_os.provider_worker_slots import get_slot

        family = self._family(request)
        if family is not None:
            return family, False
        # All filesystem/policy/boot work precedes the global write lock.
        policy = self._policy_loader()
        boot_id = validate_boot_id(self._boot_observer())
        release_sha = validate_release_sha(self.release_sha)
        job = self.runtime.jobs.get_job(request.job_id)
        if job is None:
            raise PrivilegedReadinessError("readiness Job does not exist")
        inputs = self._authority_inputs(job)
        decision = policy.authorize(
            job.requested_authorities, worktree=job.worktree,
            allowed_write_paths=job.allowed_write_paths, validation_commands=job.validation_commands,
        )
        if "REQUEST_WORKER_LOGIN_CHECK" not in decision.requested:
            raise PrivilegedReadinessError("Job does not grant the login-check capability")
        with self.runtime.store.transaction() as connection:
            family = self._family(request, connection=connection)
            if family is not None:
                return family, False
            snapshot = self.runtime.attempts.current_authority_snapshot(
                connection, job_id=request.job_id, attempt_id=request.attempt_id,
                fence_generation=request.fence_generation, timestamp=self.runtime.store.now_ms(),
                statuses={AttemptStatus.CLAIMED, AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED},
            )
            current_job, attempt = snapshot.job, snapshot.attempt
            if (self._authority_inputs(current_job) != inputs
                    or current_job.authority_policy_hash != policy.sha256
                    or attempt.authority_policy_hash != policy.sha256
                    or decision.policy_sha256 != policy.sha256
                    or release_sha != self.release_sha):
                raise PrivilegedReadinessError("readiness admission authority drifted")
            grant = validate_effective_grant(current_job, attempt, decision)
            if grant is not None and "REQUEST_WORKER_LOGIN_CHECK" not in grant["authorities"]:
                raise PrivilegedReadinessError("effective grant excludes the login-check capability")
            slot = get_slot(attempt.worker_id)
            if slot.slot_id != attempt.worker_id:
                raise PrivilegedReadinessError("assigned worker is not its exact reviewed slot")
            binding = ReadinessBinding(
                job_id=request.job_id, attempt_id=request.attempt_id,
                worker_id=attempt.worker_id, quota_class=attempt.quota_class,
                fence_generation=request.fence_generation, authority_policy_hash=policy.sha256,
                effective_grant_digest=attempt.effective_grant_digest,
                release_sha=release_sha, boot_id=boot_id, slot_id=slot.slot_id,
            )
            validate_request(broker_request_for(binding))
            self._append(connection, binding, ReadinessEventPhase.INTENT)
            self._append(connection, binding, ReadinessEventPhase.ATTEMPTED)
            family = self._family(request, connection=connection)
        return family, True

    def _append(self, connection, binding, phase, *, receipt=None, reason_code=None):
        payload = {"binding": binding.to_canonical_dict()}
        if receipt is not None:
            payload["receipt"] = receipt
        if reason_code is not None:
            payload["reason_code"] = reason_code
        suffix = "" if phase is ReadinessEventPhase.INTENT else ":" + phase.name.lower()
        self.runtime.store.append_event(
            connection, aggregate_type=READINESS_AGGREGATE_TYPE,
            aggregate_id=ReadinessFamilyKey(binding.job_id, binding.attempt_id, binding.fence_generation).family_id,
            event_type=phase.value, command_id=binding.operation_id + suffix, actor="privileged-readiness",
            job_id=binding.job_id, attempt_id=binding.attempt_id,
            worker_id=binding.worker_id, quota_class=binding.quota_class, payload=payload,
        )

    def _record(self, request, binding, phase, *, receipt=None, reason_code=None):
        with self.runtime.store.transaction() as connection:
            current = self._family(request, connection=connection)
            if current is None or current.binding != binding:
                raise PrivilegedReadinessError("admitted readiness family disappeared or drifted")
            if current.state is ReadinessResultState.TERMINAL:
                if receipt is not None and current.receipt != receipt:
                    raise PrivilegedReadinessError("broker terminal evidence conflicts with recorded evidence")
                return current
            if current.state is ReadinessResultState.REFUSED:
                if receipt is not None or (reason_code is not None and reason_code != current.reason_code):
                    raise PrivilegedReadinessError("broker outcome conflicts with recorded refusal")
                return current
            if current.phase is ReadinessEventPhase.EFFECT_UNKNOWN:
                if receipt is None:
                    # Once ambiguous, neither absence nor a later refusal erases it.
                    return current
                phase = ReadinessEventPhase.RECONCILED
            self._append(connection, binding, phase, receipt=receipt, reason_code=reason_code)
            return self._family(request, connection=connection)

    async def _execute(self, request, family):
        import asyncio

        binding = family.binding
        phase = ReadinessEventPhase.EFFECT_UNKNOWN
        receipt = reason = None
        try:
            payload = broker_request_for(binding)
            response = await asyncio.to_thread(self._client.send_effect, payload)
            response = self._client.validate_effect_response(response, payload, expected_release_sha=binding.release_sha)
            if response["ok"]:
                phase, receipt = ReadinessEventPhase.TERMINAL, response["receipt"]
            elif result_state_for_broker_error(response["error"]) is ReadinessResultState.REFUSED:
                phase, reason = ReadinessEventPhase.BROKER_REFUSED, response["error"]
        except asyncio.CancelledError:
            self._record(request, binding, ReadinessEventPhase.EFFECT_UNKNOWN)
            raise
        except Exception:
            # Any post-ATTEMPTED response ambiguity remains durable; never resend.
            pass
        # Corruption/storage failures are not broker ambiguity and must propagate.
        return self._record(request, binding, phase, receipt=receipt, reason_code=reason)

    async def _recover(self, request, family):
        import asyncio
        from control_plane.executive_privileged_action import STATUS_REQUEST_SCHEMA
        from control_plane.executive_privileged_broker import WIRE_RESPONSE_SCHEMA

        if family.state is not ReadinessResultState.EFFECT_UNKNOWN:
            return family
        binding = family.binding
        receipt = None
        try:
            response = await asyncio.to_thread(self._client.send_status,
                {"schema": STATUS_REQUEST_SCHEMA, "request_id": binding.operation_id})
            response = self._client.validate_status_response(response, expected_request_id=binding.operation_id)
            if response["status"] == "TERMINAL":
                checked = self._client.validate_effect_response(
                    {"schema": WIRE_RESPONSE_SCHEMA, "ok": True, "replayed": True, "receipt": response["receipt"]},
                    broker_request_for(binding), expected_release_sha=binding.release_sha,
                )
                receipt = checked["receipt"]
        except asyncio.CancelledError:
            self._record(request, binding, ReadinessEventPhase.EFFECT_UNKNOWN)
            raise
        except Exception:
            pass
        # NOT_FOUND, a marker, malformed evidence and unrelated verify_ready
        # reconciliation cannot establish a terminal result for this verify_only.
        phase = ReadinessEventPhase.RECONCILED if receipt is not None else ReadinessEventPhase.EFFECT_UNKNOWN
        return self._record(request, binding, phase, receipt=receipt)

    def _result(self, request, family, replayed):
        try:
            boot = self._boot_observer()
            policy_sha = self._policy_loader().sha256
        except Exception:
            boot = policy_sha = None
        currency = evidence_currency_for(family.binding, current_boot_id=boot,
            current_release_sha=self.release_sha, current_authority_policy_hash=policy_sha)
        return ReadinessResult(
            family_id=family_key_from_request(request).family_id, operation_id=family.binding.operation_id,
            state=family.state, replayed=replayed, observed_at_ms=self.runtime.store.now_ms(),
            evidence_currency=currency, binding=family.binding, receipt=family.receipt,
            reason_origin=REASON_ORIGIN_BROKER if family.reason_code is not None else None,
            reason_code=family.reason_code,
        ).to_canonical_dict()

    async def _run(self, request):
        import asyncio

        # Admission is short synchronous Runtime work; no connection survives the thread.
        admission = asyncio.create_task(asyncio.to_thread(self._admit_or_replay, request))
        try:
            family, execute_once = await asyncio.shield(admission)
        except asyncio.CancelledError:
            # Cancellation does not stop a transaction already running in a
            # thread. Reconcile its commit before releasing local ownership.
            try:
                family, execute_once = await admission
            except Exception:
                raise asyncio.CancelledError from None
            if execute_once:
                self._record(request, family.binding, ReadinessEventPhase.EFFECT_UNKNOWN)
            raise
        if execute_once:
            family = await self._execute(request, family)
        else:
            family = await self._recover(request, family)
        return await asyncio.to_thread(self._result, request, family, not execute_once)


__all__ = [
    "PrivilegedReadinessController",
    "ReadinessEventFamily",
    "broker_request_for",
    "validate_event_family",
    "BROKER_EFFECT_UNKNOWN_ERROR",
    "BROKER_REFUSAL_REASON_CODES",
    "REASON_ORIGIN_BROKER",
    "READINESS_AGGREGATE_TYPE",
    "RESULT_CANONICAL_KEYS",
    "ReadinessEventPhase",
    "ReadinessEvidenceCurrency",
    "ReadinessResult",
    "ReadinessResultState",
    "evidence_currency_for",
    "result_state_for_broker_error",
    "BINDING_CANONICAL_KEYS",
    "BINDING_SCHEMA",
    "FAMILY_ID_PREFIX",
    "FAMILY_KEY_SCHEMA",
    "FIXED_ACTION",
    "OBSERVATION_SCOPE",
    "OPERATION_ID_PREFIX",
    "REQUEST_KEYS",
    "RESULT_SCHEMA",
    "PrivilegedReadinessError",
    "ReadinessBinding",
    "ReadinessFamilyKey",
    "ReadinessRequest",
    "canonical_json_bytes",
    "family_key_from_request",
    "validate_attempt_id",
    "validate_boot_id",
    "validate_effective_grant_digest",
    "validate_fence_generation",
    "validate_job_id",
    "validate_readiness_request",
    "validate_release_sha",
    "validate_safe_id",
    "validate_sha256_hex",
]
