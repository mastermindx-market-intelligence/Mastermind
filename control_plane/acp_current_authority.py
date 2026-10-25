"""Original-run ACP controller observation. Source-only and unarmed.

Every query opens one fresh Runtime transaction, then calls the incumbent
``AttemptRegistry._leased_row`` and ``current_authority_snapshot`` with the
retained original token, fence, and fixed selectors. The lease token stays in
the retained ``AttemptLease``. It is not written to repr, errors, or the
observation. ``dispatch_authorized`` is false for this slice.
"""
from __future__ import annotations

import json
from typing import Any

from common.acp_continuing_authority_contract import (
    DISPATCH_AUTHORIZED,
    EVIDENCE_SCOPE,
    MAX_OBSERVATION_BYTES,
    OBSERVATION_KEYS,
    SCHEMA,
    UNVERIFIED_JOINS,
    AcpContinuingAuthorityContractError,
    parse_observation_request,
)
from control_plane.executive_agent_capabilities import (
    ACP_EXECUTION_SURFACE,
    ACP_PROVIDER_FREE_AUTH_REALM,
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
)
from control_plane.executive_authority import (
    AuthorityDenied,
    AuthorityPolicyError,
    ExecutiveAuthorityPolicy,
)
from control_plane.executive_runtime import (
    AttemptLease,
    AttemptStatus,
    PersistenceError,
    Runtime,
    StateConflict,
    _capacity_matches_route,
)
from control_plane.executive_supervisor import SupervisorError, validate_effective_grant
from control_plane.worker_execution_contract import WorkerLaunchSpec, WorkerProcessRef

_PROFILE_KEYS = (
    "execution_profile_id",
    "execution_profile_digest",
    "capability_policy_version",
    "capability_policy_digest",
)
_STARTUP_PHASES = frozenset({"startup", "discovery"})
_STARTUP_STATUSES = frozenset({AttemptStatus.CLAIMED})
_DISPATCH_STATUSES = frozenset({AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED})
_STARTUP_REQUIRED = (
    "lease",
    "authority",
    "orchestration_grant",
    "capacity_route",
    "source",
    "profile",
    "realm",
    "mcp_grant",
    "model",
)
_DISPATCH_REQUIRED = _STARTUP_REQUIRED + ("process", "session_association")
_REASON_FOR = {
    ("lease", "NOT_CURRENT"): "RUNTIME_NOT_CURRENT",
    ("authority", "NOT_CURRENT"): "AUTHORITY_NOT_CURRENT",
    ("authority", "UNAVAILABLE"): "AUTHORITY_UNAVAILABLE",
    ("orchestration_grant", "NOT_CURRENT"): "ORCHESTRATION_GRANT_NOT_CURRENT",
    ("orchestration_grant", "UNAVAILABLE"): "AUTHORITY_UNAVAILABLE",
    ("capacity_route", "NOT_CURRENT"): "PROFILE_NOT_CURRENT",
    ("capacity_route", "UNAVAILABLE"): "PROFILE_UNAVAILABLE",
    ("source", "NOT_CURRENT"): "SOURCE_NOT_CURRENT",
    ("source", "UNAVAILABLE"): "SOURCE_UNAVAILABLE",
    ("profile", "NOT_CURRENT"): "PROFILE_NOT_CURRENT",
    ("profile", "UNAVAILABLE"): "PROFILE_UNAVAILABLE",
    ("realm", "NOT_CURRENT"): "REALM_NOT_CURRENT",
    ("realm", "UNAVAILABLE"): "REALM_UNAVAILABLE",
    ("mcp_grant", "NOT_CURRENT"): "MCP_GRANT_NOT_CURRENT",
    ("mcp_grant", "UNAVAILABLE"): "MCP_GRANT_UNAVAILABLE",
    ("model", "NOT_CURRENT"): "MODEL_NOT_CURRENT",
    ("model", "UNAVAILABLE"): "MODEL_UNAVAILABLE",
    ("process", "NOT_CURRENT"): "PROCESS_NOT_CURRENT",
    ("process", "UNAVAILABLE"): "PROCESS_NOT_CURRENT",
    ("session_association", "NOT_CURRENT"): "SESSION_ASSOCIATION_ABSENT",
    ("session_association", "UNAVAILABLE"): "SESSION_ASSOCIATION_ABSENT",
}
_QUOTA_SQL = (
    "SELECT q.*, w.identity_status FROM worker_quota_classes q "
    "JOIN workers w ON w.worker_id=q.worker_id "
    "WHERE q.worker_id=? AND q.quota_class=?"
)


def _state(value: str, **fields: Any) -> dict[str, Any]:
    if value not in {"CURRENT", "NOT_CURRENT", "UNAVAILABLE"}:
        value = "UNAVAILABLE"
    body = {"state": value}
    body.update(fields)
    return body


def _constraint_tuple(constraints: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(
        (key, str(constraints.get(key) or "").strip().lower()) for key in _PROFILE_KEYS
    )


def _mcp_grants(profile: Any) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(
        (grant.capability_id, grant.grant_digest) for grant in profile.mcp_server_grants
    ))


def _blank_facts(state: str) -> dict[str, dict[str, Any]]:
    category = "runtime_persisted" if state == "NOT_CURRENT" else "not_obtained"
    return {
        "lease": _state(state, category=category),
        "attempt_status": _state(state, category=category),
        "authority": _state("UNAVAILABLE" if state == "NOT_CURRENT" else state, category="incumbent_policy"),
        "orchestration_grant": _state(
            "UNAVAILABLE" if state == "NOT_CURRENT" else state,
            category="incumbent_policy",
            effective_grant_digest=None,
        ),
        "capacity_route": _state("UNAVAILABLE" if state == "NOT_CURRENT" else state, category="incumbent_route"),
        "source": _state("UNAVAILABLE" if state == "NOT_CURRENT" else state, category="incumbent_registry"),
        "profile": _state("UNAVAILABLE" if state == "NOT_CURRENT" else state, category="incumbent_registry"),
        "realm": _state("UNAVAILABLE" if state == "NOT_CURRENT" else state, category="incumbent_registry"),
        "mcp_grant": _state(
            "UNAVAILABLE" if state == "NOT_CURRENT" else state,
            category="incumbent_registry",
            grants=None,
        ),
        "model": _state("UNAVAILABLE" if state == "NOT_CURRENT" else state, category="runtime_persisted"),
        "process": _state(state, category="runtime_persisted", attests_liveness=False),
        "session_association": _state(
            "NOT_CURRENT",
            category="unverified_join",
            reason_code="SESSION_ASSOCIATION_ABSENT",
            attests_liveness=False,
            attests_session=False,
        ),
    }


class OriginalAcpRunController:
    """One original AttemptLease and WorkerLaunchSpec. No second registry."""

    __slots__ = ("_runtime", "_lease", "_spec", "_process_ref", "_bound")

    def __init__(
        self,
        runtime: Runtime,
        lease: AttemptLease,
        spec: WorkerLaunchSpec,
        *,
        process_ref: WorkerProcessRef | None = None,
    ) -> None:
        if type(runtime) is not Runtime or type(lease) is not AttemptLease:
            raise AcpContinuingAuthorityContractError("ATTACHMENT_INVALID")
        if not isinstance(spec, WorkerLaunchSpec):
            raise AcpContinuingAuthorityContractError("ATTACHMENT_INVALID")
        if process_ref is not None and type(process_ref) is not WorkerProcessRef:
            raise AcpContinuingAuthorityContractError("ATTACHMENT_INVALID")
        attempt = lease.attempt
        if (
            spec.run_id != attempt.attempt_id
            or spec.job_id != attempt.job_id
            or spec.worker_id != attempt.worker_id
            or not lease.lease_token
        ):
            raise AcpContinuingAuthorityContractError("ATTACHMENT_IDENTITY_MISMATCH")
        if process_ref is not None and (
            process_ref.run_id != spec.run_id
            or (
                spec.expected_base_sha is not None
                and process_ref.base_sha != spec.expected_base_sha
            )
        ):
            raise AcpContinuingAuthorityContractError("ATTACHMENT_IDENTITY_MISMATCH")
        job = runtime.jobs.get_job(attempt.job_id)
        if job is None or job.job_id != attempt.job_id:
            raise AcpContinuingAuthorityContractError("ATTACHMENT_INVALID")
        self._runtime = runtime
        self._lease = lease
        self._spec = spec
        self._process_ref = process_ref
        self._bound = self._retain(job.constraints)

    def __repr__(self) -> str:
        attempt = self._lease.attempt
        return (
            "OriginalAcpRunController("
            f"attempt_id={attempt.attempt_id!r}, job_id={attempt.job_id!r}, "
            f"fence_generation={attempt.fence_generation!r})"
        )

    def __str__(self) -> str:
        return repr(self)

    def observe(self, raw: bytes) -> dict[str, Any]:
        """Return one fresh token-free observation. Never mutates the lease."""

        parsed = parse_observation_request(raw, forbidden_exact=self._lease.lease_token)
        self._require_correlation(parsed)
        try:
            observation = self._observe_bound(parsed)
        except AcpContinuingAuthorityContractError:
            raise
        except Exception:
            observation = self._shell(
                parsed,
                disposition="UNAVAILABLE",
                reason_code="OWNER_UNAVAILABLE",
                observed_at_ms=self._clock(),
                facts=_blank_facts("UNAVAILABLE"),
            )
        return self._seal(observation)

    def _retain(self, constraints: dict[str, Any]) -> dict[str, Any]:
        attempt = self._lease.attempt
        declared_version = str(constraints.get("capability_policy_version") or "").strip().lower()
        declared_policy = str(constraints.get("capability_policy_digest") or "").strip().lower()
        declared_profile = str(constraints.get("execution_profile_digest") or "").strip().lower()
        bound: dict[str, Any] = {
            "constraints": _constraint_tuple(constraints),
            "profile_id": str(constraints.get("execution_profile_id") or "").strip().lower(),
            "model": str(self._spec.model or "").strip().lower(),
            "policy_hash": attempt.authority_policy_hash,
            "grant_digest": attempt.effective_grant_digest,
            "source_version": declared_version or None,
            "source_digest": declared_policy or None,
            "profile_digest": declared_profile or None,
            "auth_realm": None,
            "projection_digest": None,
            "mcp_grants": None,
            "profile_bound": False,
        }
        profile_id = bound["profile_id"]
        if not profile_id or not declared_version or not declared_policy or not declared_profile:
            return bound
        try:
            registry = ExecutionCapabilityRegistry.load()
            profile = registry.resolve(profile_id)
        except CapabilityPolicyError:
            return bound
        pins_match = (
            str(registry.policy_version).strip().lower() == declared_version
            and str(registry.policy_digest).strip().lower() == declared_policy
            and str(profile.profile_digest).strip().lower() == declared_profile
        )
        if not pins_match:
            return bound
        if (
            profile.execution_surface != ACP_EXECUTION_SURFACE
            or profile.auth_realm != ACP_PROVIDER_FREE_AUTH_REALM
        ):
            return bound
        try:
            bound["projection_digest"] = profile.expected_config_digest
        except CapabilityPolicyError:
            return bound
        bound["auth_realm"] = profile.auth_realm
        bound["mcp_grants"] = _mcp_grants(profile)
        bound["profile_bound"] = True
        return bound

    def _require_correlation(self, parsed: dict[str, Any]) -> None:
        attempt = self._lease.attempt
        identity = parsed["original_identity"]
        if (
            identity["job_id"] != attempt.job_id
            or identity["attempt_id"] != attempt.attempt_id
            or identity["worker_id"] != attempt.worker_id
            or identity["quota_class"] != attempt.quota_class
            or identity["fence_generation"] != attempt.fence_generation
        ):
            raise AcpContinuingAuthorityContractError("CORRELATION_MISMATCH")

    def _clock(self) -> int | None:
        try:
            return int(self._runtime.store.now_ms())
        except Exception:
            return None

    def _statuses(self, phase: str) -> set[AttemptStatus]:
        if phase in _STARTUP_PHASES:
            return set(_STARTUP_STATUSES)
        if phase == "dispatch":
            return set(_DISPATCH_STATUSES)
        raise AcpContinuingAuthorityContractError("TYPE_INVALID")

    def _observe_bound(self, parsed: dict[str, Any]) -> dict[str, Any]:
        phase = parsed["phase"]
        statuses = self._statuses(phase)
        attempt = self._lease.attempt
        timestamp: int | None = None
        with self._runtime.store.transaction() as connection:
            timestamp = int(self._runtime.store.now_ms())
            try:
                row = self._runtime.attempts._leased_row(
                    connection,
                    attempt_id=attempt.attempt_id,
                    fence_generation=attempt.fence_generation,
                    lease_token=self._lease.lease_token,
                    timestamp=timestamp,
                    statuses=statuses,
                )
                snapshot = self._runtime.attempts.current_authority_snapshot(
                    connection,
                    job_id=attempt.job_id,
                    attempt_id=attempt.attempt_id,
                    fence_generation=attempt.fence_generation,
                    timestamp=timestamp,
                    statuses=statuses,
                )
                quota = connection.execute(
                    _QUOTA_SQL, (attempt.worker_id, attempt.quota_class)
                ).fetchone()
            except (StateConflict, PersistenceError):
                return self._shell(
                    parsed,
                    disposition="NOT_CURRENT",
                    reason_code="RUNTIME_NOT_CURRENT",
                    observed_at_ms=timestamp,
                    facts=_blank_facts("NOT_CURRENT"),
                )
            if quota is None or snapshot.attempt.attempt_id != attempt.attempt_id:
                return self._shell(
                    parsed,
                    disposition="NOT_CURRENT",
                    reason_code="RUNTIME_NOT_CURRENT",
                    observed_at_ms=timestamp,
                    facts=_blank_facts("NOT_CURRENT"),
                )
            persisted = {
                "status": str(row["status"]),
                "pid": row["pid"],
                "pgid": row["pgid"],
                "process_start_identity": row["process_start_identity"],
                "boot_id": row["boot_id"],
                "provider_session_id": row["provider_session_id"],
                "model": quota["model"],
            }
            facts = self._assess(snapshot, quota, persisted, phase)
        return self._shell(
            parsed,
            disposition=facts["disposition"],
            reason_code=facts["reason_code"],
            observed_at_ms=timestamp,
            facts=facts["facts"],
        )

    def _assess(self, snapshot: Any, quota: Any, persisted: dict[str, Any], phase: str) -> dict[str, Any]:
        facts = _blank_facts("UNAVAILABLE")
        facts["lease"] = _state("CURRENT", category="runtime_persisted")
        facts["attempt_status"] = _state(
            "CURRENT", category="runtime_persisted", status=persisted["status"]
        )
        facts["session_association"] = _state(
            "NOT_CURRENT",
            category="unverified_join",
            reason_code="SESSION_ASSOCIATION_ABSENT",
            attests_liveness=False,
            attests_session=False,
        )
        self._assess_authority(snapshot, facts)
        self._assess_route(snapshot, quota, facts)
        self._assess_profile(snapshot, facts)
        self._assess_model(persisted, facts)
        process_required = self._assess_process(persisted, phase, facts)
        required = list(_DISPATCH_REQUIRED if phase == "dispatch" else _STARTUP_REQUIRED)
        if process_required and "process" not in required:
            required.append("process")
        disposition, reason = _disposition(facts, tuple(required))
        return {"facts": facts, "disposition": disposition, "reason_code": reason}

    def _assess_authority(self, snapshot: Any, facts: dict[str, dict[str, Any]]) -> None:
        job, attempt = snapshot.job, snapshot.attempt
        try:
            policy = ExecutiveAuthorityPolicy.load()
        except AuthorityPolicyError:
            facts["authority"] = _state("UNAVAILABLE", category="incumbent_policy")
            facts["orchestration_grant"] = _state(
                "UNAVAILABLE", category="incumbent_policy", effective_grant_digest=None
            )
            return
        try:
            decision = policy.authorize(
                job.requested_authorities,
                worktree=job.worktree,
                allowed_write_paths=job.allowed_write_paths,
                validation_commands=job.validation_commands,
            )
            grant = validate_effective_grant(job, attempt, decision)
        except (AuthorityDenied, SupervisorError):
            facts["authority"] = _state("NOT_CURRENT", category="incumbent_policy")
            facts["orchestration_grant"] = _state(
                "NOT_CURRENT", category="incumbent_policy", effective_grant_digest=None
            )
            return
        retained_hash = self._bound["policy_hash"]
        if (
            decision.policy_sha256 != retained_hash
            or attempt.authority_policy_hash != retained_hash
            or job.authority_policy_hash != retained_hash
        ):
            authority = "NOT_CURRENT"
        else:
            authority = "CURRENT"
        digest = attempt.effective_grant_digest
        retained_digest = self._bound["grant_digest"]
        if grant is None:
            grant_state = "CURRENT" if digest is None and retained_digest is None else "NOT_CURRENT"
        else:
            grant_state = "CURRENT" if digest == retained_digest and digest is not None else "NOT_CURRENT"
        if authority != "CURRENT":
            grant_state = "NOT_CURRENT"
        facts["authority"] = _state(
            authority,
            category="incumbent_policy",
            **({"policy_sha256": retained_hash} if authority == "CURRENT" else {}),
        )
        facts["orchestration_grant"] = _state(
            grant_state,
            category="incumbent_policy",
            effective_grant_digest=digest if grant_state == "CURRENT" else None,
        )

    def _assess_route(self, snapshot: Any, quota: Any, facts: dict[str, dict[str, Any]]) -> None:
        try:
            matched = _capacity_matches_route(quota, dict(snapshot.job.constraints))
        except Exception:
            facts["capacity_route"] = _state("UNAVAILABLE", category="incumbent_route")
            return
        facts["capacity_route"] = _state(
            "CURRENT" if matched else "NOT_CURRENT", category="incumbent_route"
        )

    def _assess_profile(self, snapshot: Any, facts: dict[str, dict[str, Any]]) -> None:
        fresh_constraints = _constraint_tuple(dict(snapshot.job.constraints))
        retained_constraints = self._bound["constraints"]
        drifted = fresh_constraints != retained_constraints
        profile_id = self._bound["profile_id"]
        declared_version = self._bound["source_version"]
        declared_policy = self._bound["source_digest"]
        declared_profile = self._bound["profile_digest"]
        if not profile_id:
            state = "NOT_CURRENT"
            facts["source"] = _state(state, category="incumbent_registry")
            facts["profile"] = _state(state, category="incumbent_registry", profile_id=None)
            facts["realm"] = _state(state, category="incumbent_registry")
            facts["mcp_grant"] = _state(state, category="incumbent_registry", grants=None)
            return
        try:
            registry = ExecutionCapabilityRegistry.load()
            profile = registry.resolve(profile_id)
        except CapabilityPolicyError:
            state = "UNAVAILABLE"
            facts["source"] = _state(state, category="incumbent_registry")
            facts["profile"] = _state(state, category="incumbent_registry", profile_id=profile_id)
            facts["realm"] = _state(state, category="incumbent_registry")
            facts["mcp_grant"] = _state(state, category="incumbent_registry", grants=None)
            return
        source = (
            "CURRENT"
            if declared_version
            and declared_policy
            and str(registry.policy_version).strip().lower() == declared_version
            and str(registry.policy_digest).strip().lower() == declared_policy
            else "NOT_CURRENT"
        )
        grants = _mcp_grants(profile)
        try:
            projection = profile.expected_config_digest
            surface_ok = (
                profile.execution_surface == ACP_EXECUTION_SURFACE
                and profile.auth_realm == ACP_PROVIDER_FREE_AUTH_REALM
            )
        except CapabilityPolicyError:
            projection = None
            surface_ok = False
        profile_state = (
            "CURRENT"
            if source == "CURRENT"
            and self._bound["profile_bound"]
            and not drifted
            and surface_ok
            and str(profile.profile_id).strip().lower() == profile_id
            and declared_profile
            and str(profile.profile_digest).strip().lower() == declared_profile
            and projection == self._bound["projection_digest"]
            else "NOT_CURRENT"
        )
        realm_state = (
            "CURRENT"
            if profile_state == "CURRENT" and profile.auth_realm == self._bound["auth_realm"]
            else "NOT_CURRENT"
        )
        mcp_state = "CURRENT" if profile_state == "CURRENT" and grants == self._bound["mcp_grants"] else "NOT_CURRENT"
        facts["source"] = _state(
            source,
            category="incumbent_registry",
            owner="execution_capability_registry",
            policy_version=registry.policy_version if source == "CURRENT" else None,
            policy_digest=registry.policy_digest if source == "CURRENT" else None,
        )
        facts["profile"] = _state(
            profile_state,
            category="incumbent_registry",
            profile_id=profile_id,
            profile_digest=profile.profile_digest if profile_state == "CURRENT" else None,
            projection_digest=projection if profile_state == "CURRENT" else None,
        )
        facts["realm"] = _state(
            realm_state,
            category="incumbent_registry",
            auth_realm=profile.auth_realm if realm_state == "CURRENT" else None,
        )
        facts["mcp_grant"] = _state(
            mcp_state,
            category="incumbent_registry",
            grants=[
                {"capability_id": capability_id, "grant_digest": grant_digest}
                for capability_id, grant_digest in grants
            ] if mcp_state == "CURRENT" else None,
        )

    def _assess_model(self, persisted: dict[str, Any], facts: dict[str, dict[str, Any]]) -> None:
        fresh = str(persisted["model"] or "").strip().lower()
        facts["model"] = _state(
            "CURRENT" if fresh and fresh == self._bound["model"] else "NOT_CURRENT",
            category="runtime_persisted",
            model=fresh if fresh == self._bound["model"] else None,
        )

    def _assess_process(self, persisted: dict[str, Any], phase: str, facts: dict[str, dict[str, Any]]) -> bool:
        """Compare persisted identity to the retained ref. Never a liveness claim."""

        provider_session = persisted["provider_session_id"]
        persisted_present = persisted["pid"] is not None or provider_session is not None
        expected = self._process_ref
        matched = False
        if expected is not None and persisted_present and provider_session is None:
            matched = (
                persisted["pid"] == expected.pid
                and persisted["pgid"] == expected.pgid
                and persisted["process_start_identity"] == expected.process_start_identity
                and persisted["boot_id"] == expected.boot_session_id
            )
        if provider_session is not None or (persisted_present and not matched):
            facts["process"] = _state(
                "NOT_CURRENT", category="runtime_persisted", attests_liveness=False
            )
            return True
        if matched:
            facts["process"] = _state(
                "CURRENT", category="runtime_persisted", attests_liveness=False
            )
            return phase == "dispatch"
        if phase == "dispatch":
            reason = "PROCESS_EXPECTATION_ABSENT" if expected is None else "PROCESS_NOT_PERSISTED"
            facts["process"] = _state(
                "NOT_CURRENT",
                category="runtime_persisted",
                attests_liveness=False,
                reason_code=reason,
            )
            return True
        facts["process"] = _state(
            "UNAVAILABLE",
            category="runtime_persisted",
            attests_liveness=False,
            reason_code="PROCESS_NOT_PERSISTED",
        )
        return False

    def _subject(self) -> dict[str, Any]:
        attempt = self._lease.attempt
        return {
            "job_id": attempt.job_id,
            "attempt_id": attempt.attempt_id,
            "worker_id": attempt.worker_id,
            "quota_class": attempt.quota_class,
            "fence_generation": attempt.fence_generation,
        }

    def _expected_bindings(self) -> dict[str, Any]:
        process = None
        if self._process_ref is not None:
            process = {
                "pid": self._process_ref.pid,
                "pgid": self._process_ref.pgid,
                "process_start_identity": self._process_ref.process_start_identity,
                "boot_session_id": self._process_ref.boot_session_id,
            }
        return {
            "category": "expected_not_live",
            "source_policy_version": self._bound["source_version"],
            "source_policy_digest": self._bound["source_digest"],
            "profile_id": self._bound["profile_id"] or None,
            "profile_digest": self._bound["profile_digest"],
            "auth_realm": self._bound["auth_realm"],
            "model": self._bound["model"] or None,
            "process": process,
            "session_model": None,
            "attests_process_liveness": False,
            "attests_artifact": False,
            "attests_session": False,
            "attests_connection": False,
        }

    def _child(self, parsed: dict[str, Any]) -> dict[str, Any]:
        correlation = parsed["child_correlation"]
        return {
            "category": "child_supplied",
            "invocation_id": parsed["invocation_id"],
            "raw_tool": parsed["raw_tool"],
            "argument_digest": parsed["argument_digest"],
            "request_digest": parsed["request_digest"],
            "connection_id": correlation["connection_id"],
            "catalog_digest": correlation["catalog_digest"],
            "definition_digest": correlation["definition_digest"],
            "reported_fence_generation": parsed["original_identity"]["fence_generation"],
            "attests_liveness": False,
            "attests_session": False,
            "attests_connection": False,
            "attests_arguments": False,
            "attests_tool": False,
            "attests_observation": False,
        }

    def _shell(
        self,
        parsed: dict[str, Any],
        *,
        disposition: str,
        reason_code: str,
        observed_at_ms: int | None,
        facts: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        if disposition not in {"CURRENT", "NOT_CURRENT", "UNAVAILABLE"}:
            disposition = "UNAVAILABLE"
            reason_code = "OWNER_UNAVAILABLE"
        observation = {
            "schema": SCHEMA,
            "disposition": disposition,
            "dispatch_authorized": DISPATCH_AUTHORIZED,
            "evidence_scope": EVIDENCE_SCOPE,
            "phase": parsed["phase"],
            "invocation_id": parsed["invocation_id"],
            "observed_at_ms": observed_at_ms,
            "reason_code": reason_code,
            "subject": self._subject(),
            "controller_observed": facts,
            "expected_bindings": self._expected_bindings(),
            "child_correlation": self._child(parsed),
            "unverified_joins": list(UNVERIFIED_JOINS),
        }
        if set(observation) != OBSERVATION_KEYS or observation["dispatch_authorized"] is not False:
            return _output_refused()
        return observation

    def _seal(self, observation: dict[str, Any]) -> dict[str, Any]:
        token = self._lease.lease_token
        try:
            encoded = json.dumps(
                observation,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError):
            return _output_refused()
        if token and (token in encoded or token in repr(self) or token in str(observation)):
            return _output_refused()
        try:
            size = len(encoded.encode("utf-8"))
        except UnicodeError:
            return _output_refused()
        if size > MAX_OBSERVATION_BYTES:
            return _output_unavailable("OUTPUT_CEILING")
        return observation


def _disposition(facts: dict[str, dict[str, Any]], required: tuple[str, ...]) -> tuple[str, str]:
    for name in required:
        state = facts[name]["state"]
        if state == "NOT_CURRENT":
            return "NOT_CURRENT", _REASON_FOR[(name, state)]
    for name in required:
        state = facts[name]["state"]
        if state != "CURRENT":
            return "UNAVAILABLE", _REASON_FOR.get((name, "UNAVAILABLE"), "OWNER_UNAVAILABLE")
    return "CURRENT", "OK"


def _output_unavailable(reason: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "disposition": "UNAVAILABLE",
        "dispatch_authorized": False,
        "evidence_scope": EVIDENCE_SCOPE,
        "phase": None,
        "invocation_id": None,
        "observed_at_ms": None,
        "reason_code": reason,
        "subject": None,
        "controller_observed": None,
        "expected_bindings": None,
        "child_correlation": None,
        "unverified_joins": list(UNVERIFIED_JOINS),
    }


def _output_refused() -> dict[str, Any]:
    return _output_unavailable("OUTPUT_REFUSED")
