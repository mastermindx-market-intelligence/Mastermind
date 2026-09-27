"""Credential issuance adapter over the EXISTING Executive Runtime Event owner.

No database/path is selected or created here. Deployment supplies a qualified
existing-writable RuntimeStore and current credential-domain admission. A slot
is stable across provider instances, operation aliases and generation changes.
Neither qualified metadata nor elapsed time grants a second issuance. Explicit
owner recovery/renewal is outside this adapter; no token is persisted or read.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
import hashlib
import json
import re

from control_plane.executive_runtime import RuntimeStore
from .read_installation_identity import (
    InstallationCredentialError, READ_PERMISSIONS, ReadInstallationBinding, validate_read_installation_binding,
)

_HEX = re.compile(r"^[0-9a-f]{64}$")
_SCHEMA = "mastermind.github_read_issuance_event.v1"
_ACTOR = "github-read-credential-owner"
_AGGREGATE = "github_read_credential"
_ATTEMPT = "GITHUB_READ_CREDENTIAL_ATTEMPT"
_QUALIFIED = "GITHUB_READ_CREDENTIAL_QUALIFIED"


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def binding_fingerprint(binding: ReadInstallationBinding) -> str:
    if type(binding) is not ReadInstallationBinding:
        raise InstallationCredentialError("BINDING_REFUSED")
    return _digest({"binding": asdict(binding), "permissions": READ_PERMISSIONS})


def _slot(binding: ReadInstallationBinding) -> str:
    # Immutable service target, not a model-selected operation or generation.
    return _digest({"kind": "github-installation-read", "app": binding.app_id,
        "installation": binding.installation_id, "account": binding.account_id,
        "repository": binding.repository_id})


@dataclass(frozen=True)
class CredentialIssuanceAdmission:
    """Existing credential/runtime owners' secret-free current authorization."""
    runtime_identity: tuple[int, int]
    binding_fingerprint: str
    principal_digest: str
    authority_digest: str
    expires_at_ms: int


@dataclass(frozen=True)
class IssuanceClaim:
    slot_command: str
    binding_fingerprint: str
    admission_fingerprint: str
    claimed_at_ms: int


class RuntimeReadIssuanceFence:
    """Small domain adapter; RuntimeStore remains transaction/event authority."""
    def __init__(self, *, store: RuntimeStore,
                 authorize: Callable[[ReadInstallationBinding], CredentialIssuanceAdmission] | None = None):
        if (type(store) is not RuntimeStore or store.create is not False
                or store.existing_writable is not True
                or (authorize is not None and not callable(authorize))):
            raise InstallationCredentialError("DURABLE_ISSUANCE_UNAVAILABLE")
        self._store = store
        self._authorize = authorize

    def _now(self) -> int:
        now = self._store.now_ms()
        if type(now) is not int or not 60_000 <= now < 253402300800000:
            raise InstallationCredentialError("CLOCK_REFUSED")
        return now

    def _admit(self, binding: ReadInstallationBinding) -> CredentialIssuanceAdmission:
        if self._authorize is None:
            raise InstallationCredentialError("DURABLE_ISSUANCE_UNAVAILABLE")
        started = self._now()
        validate_read_installation_binding(binding, started // 1000)
        admission = self._authorize(binding)
        now = self._now()
        if now < started:
            raise InstallationCredentialError("CLOCK_REFUSED")
        if (type(admission) is not CredentialIssuanceAdmission
                or type(admission.runtime_identity) is not tuple
                or len(admission.runtime_identity) != 2
                or any(type(n) is not int or n < 0 for n in admission.runtime_identity)
                or admission.runtime_identity != self._store._database_file_identity
                or any(type(s) is not str or not _HEX.fullmatch(s) for s in (
                    admission.binding_fingerprint, admission.principal_digest, admission.authority_digest))
                or admission.binding_fingerprint != binding_fingerprint(binding)
                or type(admission.expires_at_ms) is not int
                or not now < admission.expires_at_ms <= binding.expires_at * 1000):
            raise InstallationCredentialError("DURABLE_ISSUANCE_UNAVAILABLE")
        return admission

    def _guard(self, connection, binding, admission):
        self._store._assert_owned_snapshot_connection(connection)
        self._store._verify_current_schema(connection)
        current = self._admit(binding)
        # Admission itself may block or observe a replacement runtime handle.
        self._store._assert_owned_snapshot_connection(connection)
        if current != admission:
            raise InstallationCredentialError("AUTHORITY_CHANGED")

    @staticmethod
    def _command(binding) -> str:
        return "github-read-issuance:" + _slot(binding)

    @staticmethod
    def _payload(claim: IssuanceClaim) -> dict[str, object]:
        return {"schema": _SCHEMA, "binding_fingerprint": claim.binding_fingerprint,
            "admission_fingerprint": claim.admission_fingerprint,
            "claimed_at_ms": claim.claimed_at_ms}

    @staticmethod
    def _matches(event, command: str, event_type: str, payload: dict) -> bool:
        return (event is not None and event.command_id == command
            and event.aggregate_type == _AGGREGATE
            and event.aggregate_id == command.split(":")[1]
            and event.actor == _ACTOR and event.event_type == event_type
            and event.job_id is None and event.attempt_id is None and event.worker_id is None
            and event.payload == payload)

    def _unoccupied(self, connection, binding):
        command = self._command(binding)
        # An orphan or unqualified record is occupied, never permission to retry.
        if any(self._store.get_event_by_command_id(key, connection=connection) is not None
               for key in (command, command + ":qualified")):
            raise InstallationCredentialError("ISSUANCE_RECONCILIATION_REQUIRED", issuance_possible=True)

    def check_available(self, binding: ReadInstallationBinding) -> None:
        try:
            admission = self._admit(binding)
            with self._store.read() as connection:
                self._guard(connection, binding, admission)
                self._unoccupied(connection, binding)
                self._guard(connection, binding, admission)
        except InstallationCredentialError:
            raise
        except Exception:
            raise InstallationCredentialError("DURABLE_ISSUANCE_UNAVAILABLE") from None

    def claim(self, binding: ReadInstallationBinding) -> IssuanceClaim:
        try:
            admission = self._admit(binding)
            with self._store.transaction() as connection:
                self._guard(connection, binding, admission)
                self._unoccupied(connection, binding)
                claim = IssuanceClaim(self._command(binding), binding_fingerprint(binding),
                    _digest(asdict(admission)), self._now())
                self._store.append_event(connection, aggregate_type=_AGGREGATE,
                    aggregate_id=_slot(binding), event_type=_ATTEMPT, actor=_ACTOR,
                    command_id=claim.slot_command, payload=self._payload(claim),
                    timestamp_ms=claim.claimed_at_ms)
                self._guard(connection, binding, admission)
            # Return only AFTER RuntimeStore commits the unique command.
            return claim
        except InstallationCredentialError:
            raise
        except Exception:
            # This call has not dispatched HTTP. A possibly committed claim is
            # reconciled by its exact command on the next owner read, not replay.
            raise InstallationCredentialError("DURABLE_ISSUANCE_UNAVAILABLE") from None

    def _original(self, connection, binding, admission, claim, usable_until_ms):
        if (type(claim) is not IssuanceClaim or claim.slot_command != self._command(binding)
                or claim.binding_fingerprint != binding_fingerprint(binding)
                or claim.admission_fingerprint != _digest(asdict(admission))
                or type(claim.claimed_at_ms) is not int or claim.claimed_at_ms > self._now()
                or type(usable_until_ms) is not int
                or not self._now() < usable_until_ms <= admission.expires_at_ms):
            raise InstallationCredentialError("DURABLE_ISSUANCE_UNAVAILABLE", issuance_possible=True)
        expected = self._payload(claim)
        event = self._store.get_event_by_command_id(claim.slot_command, connection=connection)
        if not self._matches(event, claim.slot_command, _ATTEMPT, expected):
            raise InstallationCredentialError("DURABLE_ISSUANCE_UNAVAILABLE", issuance_possible=True)
        return {**expected, "usable_until_ms": usable_until_ms}

    def check_pending(self, binding: ReadInstallationBinding, claim: IssuanceClaim) -> int:
        """Revalidate the committed original attempt immediately before POST."""
        try:
            admission = self._admit(binding)
            with self._store.read() as connection:
                self._guard(connection, binding, admission)
                self._original(connection, binding, admission, claim, admission.expires_at_ms)
                if self._store.get_event_by_command_id(claim.slot_command + ":qualified", connection=connection) is not None:
                    raise InstallationCredentialError("ISSUANCE_RECONCILIATION_REQUIRED", issuance_possible=True)
                self._guard(connection, binding, admission)
            return admission.expires_at_ms
        except InstallationCredentialError:
            raise
        except Exception:
            raise InstallationCredentialError("DURABLE_ISSUANCE_UNAVAILABLE", issuance_possible=True) from None

    def complete(self, binding: ReadInstallationBinding, claim: IssuanceClaim,
                 usable_until_ms: int) -> None:
        try:
            admission = self._admit(binding)
            with self._store.transaction() as connection:
                self._guard(connection, binding, admission)
                payload = self._original(connection, binding, admission, claim, usable_until_ms)
                command = claim.slot_command + ":qualified"
                prior = self._store.get_event_by_command_id(command, connection=connection)
                if prior is not None:
                    if not self._matches(prior, command, _QUALIFIED, payload):
                        raise InstallationCredentialError("DURABLE_ISSUANCE_UNAVAILABLE", issuance_possible=True)
                else:
                    self._store.append_event(connection, aggregate_type=_AGGREGATE,
                        aggregate_id=_slot(binding), event_type=_QUALIFIED, actor=_ACTOR,
                        command_id=command, payload=payload)
                self._guard(connection, binding, admission)
        except InstallationCredentialError:
            raise
        except Exception:
            raise InstallationCredentialError("DURABLE_ISSUANCE_UNAVAILABLE", issuance_possible=True) from None

    def check_qualified(self, binding: ReadInstallationBinding, claim: IssuanceClaim,
                        usable_until_ms: int) -> None:
        try:
            admission = self._admit(binding)
            with self._store.read() as connection:
                self._guard(connection, binding, admission)
                payload = self._original(connection, binding, admission, claim, usable_until_ms)
                command = claim.slot_command + ":qualified"
                event = self._store.get_event_by_command_id(command, connection=connection)
                if not self._matches(event, command, _QUALIFIED, payload):
                    raise InstallationCredentialError("DURABLE_ISSUANCE_UNAVAILABLE", issuance_possible=True)
                self._guard(connection, binding, admission)
        except InstallationCredentialError:
            raise
        except Exception:
            raise InstallationCredentialError("DURABLE_ISSUANCE_UNAVAILABLE", issuance_possible=True) from None
