"""CAP-S1 real-provider canary runner (Mastermind operator four-Skill journey).

Implements the vertical amendment's §9 real canary journey and the protocol-
attestation amendment's schema-source precedence (§2), exact source-root
modes (§4) and fresh-process causal isolation (§5) on top of the already-
built primitives this module composes but never re-implements:

- ``control_plane.executive_agent_capabilities`` (V4 registry, profile);
- ``control_plane.executive_capability_packages`` (package generation);
- ``scripts.ohf.capability_skill_projection`` (attempt-local Skill staging);
- ``control_plane.codex_operator_adapter`` (binding-gated causal launch,
  the closed structured Skill turn-input seam, and read/collect/stop);
- ``scripts.ohf.protocol`` (strict ``skills/list`` parsing helpers).

This module never launches the real Codex binary itself in tests: the
``backend="fake"`` path is driven entirely by an injected ``client_factory``
(the same fake-App-Server-subprocess harness pattern the adapter's own tests
use) and an injected ``run_command`` for schema generation. The
``backend="live"`` path is real-binary-shaped but is only ever exercised by
the operation principal, later, against a dedicated non-default
``CODEX_HOME`` -- never by this module's own test suite.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib
import importlib.util
import io
import json
import os
import re
import resource
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import weakref
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from control_plane.codex_operator_adapter import (
    CodexAdapterError,
    OHF_CLIENT_INFO,
    CodexOperatorAdapter,
    CodexProtocolAttestationReceipt,
    CodexSkillCanaryBinding,
    CodexSkillTurnInput,
    CodexTurnInputEnvelope,
    SKILL_INPUT_SCHEMA_EVIDENCE,
    build_protocol_attestation_receipt,
)
from control_plane.executive_agent_capabilities import (
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
    NativeHelperPolicy,
)
from control_plane.executive_capability_packages import (
    CapabilityPackageError,
    build_capability_package_generation,
)
from control_plane.operator_harness_contract import (
    EventCursor,
    LaunchDecision,
    OperationId,
    ProcessGenerationRef,
    ProcessLiveness,
    RequestedExecutionProfile,
    SessionEpochRef,
    TurnRef,
    WorkspaceIdentity,
    compare_launch,
)
from scripts.ohf.capability_skill_projection import (
    ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE,
    EphemeralGitOriginReceipt,
    SkillProjectionError,
    cleanup_skill_projection,
    create_ephemeral_archive_origin,
    stage_skill_projection,
)
from scripts.ohf.laboratory import AppServerClient, default_user_codex_home, validate_live_codex_home
from scripts.ohf.protocol import (
    SkillProtocolShapeError,
    enabled_skill_names,
    extra_roots_set_params,
    parse_skills_list_strict,
    skills_list_params,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

V4_FIXTURE_RELATIVE_PATH = Path(
    "scripts/ohf/fixtures/executive_agent_capabilities_v4_mastermind_operator.json"
)
PACKAGE_CAPABILITY_ID = "mastermind-operator.p1"
PROFILE_ID = "operator.appserver.readonly.mastermind-operator.v1"

CANARY_WORKER_ID = "cap-s1-canary"
CANARY_REQUESTED_MODEL = "gpt-5.6-sol"
FAKE_HARNESS_VERSION = "ohf-fake-app-server/p0b"
_CANARY_AUTHORITY_POLICY_HASH = "c" * 64

SYNTHETIC_OPERATION_ID = "cap-s1-synthetic-op"
SYNTHETIC_DECISION_BRANCH = "branch-alpha"

CANARY_CLEANUP_SCHEMA_VERSION = "mastermind.cap_s1_canary_cleanup/v1"
CANARY_EVIDENCE_SCHEMA_VERSION = "mastermind.cap_s1_canary_evidence/v1"
_CANARY_SOURCE_EVIDENCE_SEALS: dict[int, "_CanarySourceSeal"] = {}
_CANARY_SOURCE_EVIDENCE_SEAL_LIMIT = 64
_CANARY_SOURCE_EVIDENCE_SEAL_LOCK = threading.RLock()

# CAP-S1 Sol review item 1 (single-binary law): the fake realm's schema
# fixture and its App Server used to be two DIFFERENT files -- a print/write
# schema stub, and the running Python interpreter launched with ``-m
# scripts.ohf.fake_app_server``. A receipt attesting one could never be
# honestly bound to the adapter launching the other. ``fake_codex_binary.py``
# (committed, real, executable) is now the ONE file used for both: schema
# generation, ``--version``, and (via an internal ``os.execv`` passthrough
# into the real fake-App-Server implementation) the App Server itself. See
# that module's own docstring for the exact CLI shapes it answers.
FAKE_CODEX_BINARY_PATH = Path(__file__).resolve().parent / "fake_codex_binary.py"
_SCHEMA_FIXTURE_BINARY_SOURCE = FAKE_CODEX_BINARY_PATH.read_text(encoding="utf-8")

FROZEN_STOP_CODES = (
    "SKILL_PROTOCOL_SCHEMA_UNATTESTED",
    "SKILL_PATH_ATTESTATION_UNAVAILABLE",
    "AMBIENT_SKILL_SURFACE_NOT_EMPTY",
    "SKILL_SET_CAUSALITY_FAILED",
    "SKILLS_CHANGED_DURING_CANARY",
    "EFFECT_UNKNOWN",
    "PROVIDER_REALM_UNAVAILABLE",
)

# Frozen four-turn order (also the Skill runtime names / capability ids'
# name segment) per the vertical amendment §3/§9.
TURN_ORDER = (
    "receive-commission",
    "return-progress",
    "escalate-decision",
    "finish-operation",
)

_TURN_TEXTS: dict[str, str] = {
    "receive-commission": (
        f"$receive-commission Acknowledge pickup of synthetic operation "
        f"{SYNTHETIC_OPERATION_ID} (decision branch {SYNTHETIC_DECISION_BRANCH}). "
        "Confirm receipt only; do not claim the work has started."
    ),
    "return-progress": (
        f"$return-progress Report bounded progress on synthetic operation "
        f"{SYNTHETIC_OPERATION_ID} without claiming it is complete."
    ),
    "escalate-decision": (
        f"$escalate-decision Ambiguity reached on synthetic operation "
        f"{SYNTHETIC_OPERATION_ID} at decision branch {SYNTHETIC_DECISION_BRANCH}; "
        "request an explicit decision rather than deciding unilaterally."
    ),
    "finish-operation": (
        f"Sol ruling (synthetic, bounded): proceed with decision branch "
        f"{SYNTHETIC_DECISION_BRANCH} for {SYNTHETIC_OPERATION_ID}. "
        "$finish-operation Report the RESULT of the synthetic operation without "
        "claiming Sol acceptance or STOP."
    ),
}

# (required literal tokens, forbidden literal tokens) per model-output turn,
# per the vertical amendment §9 closed-marker law.
_TURN_MARKER_RULES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "receive-commission": (("PICKUP-ACK",), ("STARTED",)),
    "return-progress": (("PROGRESS",), ("COMPLETE",)),
    "escalate-decision": (("DECISION-REQUEST",), ("DECIDED",)),
    "finish-operation": (("RESULT",), ("ACCEPTED", "STOPPED")),
}

# Global live-authority identifiers that must never appear in bounded,
# synthetic model output (vertical amendment §9).
_GLOBAL_FORBIDDEN_TOKENS = (
    "mastermindx-market-intelligence",
    "chriswong",
    "Slack",
    "PR #",
    "credential",
    "auth.json",
)


class CanaryStop(RuntimeError):
    """One closed, frozen refusal token (protocol-attestation amendment §11)."""

    def __init__(self, code: str, detail: str = "") -> None:
        if code not in FROZEN_STOP_CODES:
            raise ValueError(f"unknown canary stop code: {code!r}")
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class _SeamProbeRefusal(RuntimeError):
    """Deterministic, network-free refusal raised by ``_seam_probe_client_factory``
    once it has proven the live client-construction wiring was reached."""


def _seam_probe_client_factory(argv: list, env: Mapping[str, str], cwd: Path):
    """Live-CLI wiring seam probe (CAP-S1 addendum, finding 3; Sol review
    item 2 residual: a callback-only substitute is not the production seam).

    Constructs the REAL ``scripts.ohf.laboratory.AppServerClient`` -- the
    exact class the adapter's own default ``client_factory`` would have
    constructed -- and starts it, so a harmless local process (the
    single-binary fixture named by ``--binary-path``, never the real Codex
    binary) is genuinely spawned through the genuine subprocess-construction
    path. No JSON-RPC call is ever issued (no ``initialize``, no
    ``thread/start``, no turn): the probe records that REAL construction was
    reached -- the exact class name and the ``argv``/``cwd`` the adapter
    would have launched -- to the file named by ``OHF_SEAM_PROBE_RECORD_PATH``
    (when set), shuts the harmless process down, then raises deterministically
    before any provider effect. Wired in ONLY via an explicit
    ``CAP_S1_LIVE_CLIENT_FACTORY=scripts.ohf.
    cap_s1_mastermind_operator_canary:_seam_probe_client_factory`` override
    (see ``main``'s live-backend client-factory resolution), always against a
    disposable, non-default ``--codex-home``.
    """

    probe_client = AppServerClient(list(argv), env=env, cwd=cwd, start_new_session=True)
    try:
        probe_client.start()
        record_path = os.environ.get("OHF_SEAM_PROBE_RECORD_PATH")
        if record_path:
            Path(record_path).write_text(
                json.dumps(
                    {
                        "constructed": type(probe_client).__name__,
                        "argv": list(probe_client.argv),
                        "argv0": str(probe_client.argv[0]) if probe_client.argv else "",
                        "cwd": str(probe_client.cwd),
                        "pid": probe_client.pid,
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
    finally:
        try:
            probe_client.close()
        except Exception:  # noqa: BLE001 -- best-effort probe teardown
            pass
    raise _SeamProbeRefusal(
        "cap-s1 live client-construction seam probe: refusing before any provider effect"
    )


SCHEMA_ATTESTATION_DIR_NAME = "schema-attestation"
CANARY_CLEANUP_RESOURCE_KINDS = frozenset(
    {"process", "thread", "schema", "origin", "projection", "attempt", "workspace"}
)

# One client-info truth: the probe must identify exactly as the launch
# will, or the sealed and observed userAgents can never match on a real
# binary (live canary EFFECT_UNKNOWN, PR #350).
_PROBE_CLIENT_INFO = OHF_CLIENT_INFO


@dataclasses.dataclass(frozen=True, kw_only=True)
class CanaryCleanupRecord:
    """Frozen, immutable teardown outcome (Sol wave-3 review finding B4).

    Replaces the earlier mutable ``dict`` -- ``artifacts`` is a closed tuple
    of ``(kind, removed, verified_absent)`` rows, one per registered
    resource, appended in LIFO teardown order by ``run_canary``'s own
    finally-block cleanup ledger. ``removed``/``verified_absent`` are always
    computed together here (a resource is only ever considered removed once
    its absence has been freshly re-checked).
    """

    schema_version: str = CANARY_CLEANUP_SCHEMA_VERSION
    artifacts: tuple[tuple[str, bool, bool], ...] = ()

    @property
    def all_removed(self) -> bool:
        if type(self.artifacts) is not tuple or len(self.artifacts) != len(
            CANARY_CLEANUP_RESOURCE_KINDS
        ):
            return False
        if not all(
            type(row) is tuple
            and len(row) == 3
            and isinstance(row[0], str)
            and type(row[1]) is bool
            and type(row[2]) is bool
            for row in self.artifacts
        ):
            return False
        kinds = tuple(kind for kind, _removed, _verified_absent in self.artifacts)
        return (
            len(set(kinds)) == len(kinds)
            and set(kinds) == CANARY_CLEANUP_RESOURCE_KINDS
            and all(
                removed and verified_absent
                for _kind, removed, verified_absent in self.artifacts
            )
        )


@dataclasses.dataclass(frozen=True, kw_only=True)
class CanaryEvidence:
    schema_version: str = CANARY_EVIDENCE_SCHEMA_VERSION
    candidate_commit: str
    candidate_tree: str
    canary_operation_id: str
    provider_attempt_id: str
    protected_join: str
    workspace_root: str
    process_generation: str
    v4_policy_digest: str
    package_source_digest: str
    package_generation_digest: str
    skill_grant_digests: tuple[tuple[str, str], ...]
    skill_closure_digests: tuple[tuple[str, str], ...]
    projection_receipt_digest: str
    binary_digest: str
    binary_version: str
    origin_mode: str
    origin_authentication: str
    skills_root: str
    app_server_config_digest: "str | None"
    extra_roots_set_outcomes: tuple[str, ...]
    skills_list_raw_shape_digest: str
    baseline_enabled_names: tuple[str, ...]
    after_add_enabled_names: tuple[str, ...]
    observed_enabled_names: tuple[str, ...]
    after_clear_enabled_names: tuple[str, ...]
    protocol_receipt_digest: str
    launch_decision: str
    turn_marker_results: tuple[tuple[str, bool], ...]
    served_model: "str | None"
    terminal_process_state: str
    artifact_inventory: tuple[str, ...]
    cleanup: CanaryCleanupRecord


@dataclasses.dataclass(frozen=True, kw_only=True)
class _CanarySourceSeal:
    """Process-local binding for one exact ``run_canary`` return object.

    The weak reference prevents the registry from retaining unconsumed test
    evidence forever, while the object ``is`` check prevents Python object-ID
    reuse from authorizing a replacement object.
    """

    evidence_ref: "weakref.ReferenceType[CanaryEvidence]"
    evidence_digest: str
    provenance: str
    state: str
    failure_code: "str | None"


@dataclasses.dataclass(frozen=True, kw_only=True)
class CapS1CanaryResultEvidence:
    """Secret-safe public projection of attempt-local canary evidence.

    ``CanaryEvidence`` deliberately retains the absolute workspace and Skill
    roots needed while the attempt is alive.  Those host-local paths are not
    part of the public result contract.  Their public replacements are
    semantic identities derived only from already-public, exact-bound canary
    facts; neither digest contains a path preimage.
    """

    schema_version: str = CANARY_EVIDENCE_SCHEMA_VERSION
    candidate_commit: str
    candidate_tree: str
    canary_operation_id: str
    provider_attempt_id: str
    protected_join: str
    workspace_identity_digest: str
    process_generation: str
    v4_policy_digest: str
    package_source_digest: str
    package_generation_digest: str
    skill_grant_digests: tuple[tuple[str, str], ...]
    skill_closure_digests: tuple[tuple[str, str], ...]
    projection_receipt_digest: str
    binary_digest: str
    binary_version: str
    origin_mode: str
    origin_authentication: str
    skills_identity_digest: str
    app_server_config_digest: "str | None"
    extra_roots_set_outcomes: tuple[str, ...]
    skills_list_raw_shape_digest: str
    baseline_enabled_names: tuple[str, ...]
    after_add_enabled_names: tuple[str, ...]
    observed_enabled_names: tuple[str, ...]
    after_clear_enabled_names: tuple[str, ...]
    protocol_receipt_digest: str
    launch_decision: str
    turn_marker_results: tuple[tuple[str, bool], ...]
    served_model: "str | None"
    terminal_process_state: str
    artifact_inventory: tuple[str, ...]
    cleanup: CanaryCleanupRecord


# ---------------------------------------------------------------------------
# Canonical digesting (same discipline as control_plane.executive_capability_packages)
# ---------------------------------------------------------------------------


def _canonical_digest(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _cap_s1_canary_provenance(*, backend: str, client_factory: object) -> str:
    """Classify the route actually selected by the canary owner.

    The public result path accepts only the adapter's exact default live
    factory.  A caller saying ``backend='live'`` is therefore insufficient,
    and the opt-in live seam probe remains non-production evidence.
    """

    if backend == "fake":
        return "FIXTURE_FAKE"
    from control_plane.codex_operator_adapter import _default_client_factory

    if client_factory is _default_client_factory:
        return "LIVE_DEFAULT_APP_SERVER"
    return "LIVE_NONPRODUCTION_OVERRIDE"


def _register_cap_s1_canary_evidence(
    evidence: CanaryEvidence,
    *,
    backend: str,
    client_factory: object,
) -> None:
    """Seal one exact issued object without retaining it indefinitely."""

    key = id(evidence)

    def _expire(reference: "weakref.ReferenceType[CanaryEvidence]") -> None:
        with _CANARY_SOURCE_EVIDENCE_SEAL_LOCK:
            current = _CANARY_SOURCE_EVIDENCE_SEALS.get(key)
            if current is not None and current.evidence_ref is reference:
                _CANARY_SOURCE_EVIDENCE_SEALS.pop(key, None)

    reference = weakref.ref(evidence, _expire)
    with _CANARY_SOURCE_EVIDENCE_SEAL_LOCK:
        stale = [
            stale_key
            for stale_key, seal in _CANARY_SOURCE_EVIDENCE_SEALS.items()
            if seal.evidence_ref() is None
        ]
        for stale_key in stale:
            _CANARY_SOURCE_EVIDENCE_SEALS.pop(stale_key, None)
        if len(_CANARY_SOURCE_EVIDENCE_SEALS) >= _CANARY_SOURCE_EVIDENCE_SEAL_LIMIT:
            raise CanaryStop(
                "PROVIDER_REALM_UNAVAILABLE",
                "canary evidence seal capacity unavailable",
            )
        existing = _CANARY_SOURCE_EVIDENCE_SEALS.get(key)
        if existing is not None and existing.evidence_ref() is not evidence:
            raise CanaryStop(
                "PROVIDER_REALM_UNAVAILABLE",
                "canary evidence identity collision",
            )
        _CANARY_SOURCE_EVIDENCE_SEALS[key] = _CanarySourceSeal(
            evidence_ref=reference,
            evidence_digest=_canonical_digest(dataclasses.asdict(evidence)),
            provenance=_cap_s1_canary_provenance(
                backend=backend,
                client_factory=client_factory,
            ),
            state="AVAILABLE",
            failure_code=None,
        )


def _find_cap_s1_canary_seal(evidence: CanaryEvidence) -> _CanarySourceSeal:
    """Return only the exact unchanged object's current finite seal state."""

    with _CANARY_SOURCE_EVIDENCE_SEAL_LOCK:
        seal = _CANARY_SOURCE_EVIDENCE_SEALS.get(id(evidence))
        if (
            seal is None
            or seal.evidence_ref() is not evidence
            or seal.evidence_digest != _canonical_digest(dataclasses.asdict(evidence))
        ):
            raise CapS1ResultError("cap_s1_result_canary_evidence_source_invalid")
        return seal


def _consume_cap_s1_canary_seal(evidence: CanaryEvidence) -> _CanarySourceSeal:
    """Fixture-only at-most-once consume of an AVAILABLE exact object."""

    with _CANARY_SOURCE_EVIDENCE_SEAL_LOCK:
        seal = _find_cap_s1_canary_seal(evidence)
        if seal.state != "AVAILABLE" or seal.failure_code is not None:
            raise CapS1ResultError("cap_s1_result_canary_evidence_source_invalid")
        if _CANARY_SOURCE_EVIDENCE_SEALS.pop(id(evidence), None) is not seal:
            raise CapS1ResultError("cap_s1_result_canary_evidence_source_invalid")
        return seal


def _claim_cap_s1_canary_seal(evidence: CanaryEvidence) -> _CanarySourceSeal:
    """Atomically advance the existing seal to its non-retryable active state."""

    with _CANARY_SOURCE_EVIDENCE_SEAL_LOCK:
        seal = _find_cap_s1_canary_seal(evidence)
        if seal.state == "FAILED" and seal.failure_code is not None:
            raise CapS1ResultError(seal.failure_code)
        if seal.state == "IN_PROGRESS":
            raise CapS1ResultError("cap_s1_result_canary_evidence_in_progress")
        if seal.state != "AVAILABLE" or seal.failure_code is not None:
            raise CapS1ResultError("cap_s1_result_canary_evidence_source_invalid")
        claimed = dataclasses.replace(seal, state="IN_PROGRESS")
        if _CANARY_SOURCE_EVIDENCE_SEALS.get(id(evidence)) is not seal:
            raise CapS1ResultError("cap_s1_result_canary_evidence_source_invalid")
        _CANARY_SOURCE_EVIDENCE_SEALS[id(evidence)] = claimed
        return claimed


def _finish_cap_s1_canary_seal(
    evidence: CanaryEvidence,
    claimed: _CanarySourceSeal,
    *,
    failure: "CapS1ResultError | None",
) -> None:
    """Retire success or persist one typed failed disposition without retry."""

    with _CANARY_SOURCE_EVIDENCE_SEAL_LOCK:
        current = _CANARY_SOURCE_EVIDENCE_SEALS.get(id(evidence))
        if (
            current is not claimed
            or current.evidence_ref() is not evidence
            or current.state != "IN_PROGRESS"
        ):
            raise CapS1ResultError("cap_s1_result_canary_evidence_source_invalid")
        if failure is None:
            if _CANARY_SOURCE_EVIDENCE_SEALS.pop(id(evidence), None) is not claimed:
                raise CapS1ResultError("cap_s1_result_canary_evidence_source_invalid")
            return
        failure_code = str(failure)
        if re.fullmatch(r"cap_s1_result_[a-z0-9_]{1,160}", failure_code) is None:
            failure_code = "cap_s1_result_source_observation_unavailable"
        _CANARY_SOURCE_EVIDENCE_SEALS[id(evidence)] = dataclasses.replace(
            claimed,
            state="FAILED",
            failure_code=failure_code,
        )


def _consume_cap_s1_fake_canary_for_fixture(evidence: CanaryEvidence) -> str:
    """Fixture-only positive seam; never constructs or validates a result."""

    seal = _consume_cap_s1_canary_seal(evidence)
    if seal.provenance != "FIXTURE_FAKE":
        raise CapS1ResultError("cap_s1_result_canary_fixture_provenance_invalid")
    return "FIXTURE_ONLY/NOT_PROVIDER_PROOF"


def _project_canary_result_evidence(
    evidence: CanaryEvidence,
) -> CapS1CanaryResultEvidence:
    """Drop attempt-local paths while preserving a verifiable public join."""

    if type(evidence) is not CanaryEvidence:
        raise CapS1ResultError("cap_s1_result_canary_evidence_type_invalid")
    public_fields = {
        field.name: getattr(evidence, field.name)
        for field in dataclasses.fields(CapS1CanaryResultEvidence)
        if hasattr(evidence, field.name)
    }
    public_fields["workspace_identity_digest"] = _canonical_digest(
        {
            "identity_type": "cap-s1-synthetic-workspace/v1",
            "candidate_commit": evidence.candidate_commit,
            "candidate_tree": evidence.candidate_tree,
            "canary_operation_id": evidence.canary_operation_id,
            "provider_attempt_id": evidence.provider_attempt_id,
        }
    )
    public_fields["skills_identity_digest"] = _canonical_digest(
        {
            "identity_type": "cap-s1-skill-projection/v1",
            "package_source_digest": evidence.package_source_digest,
            "package_generation_digest": evidence.package_generation_digest,
            "projection_receipt_digest": evidence.projection_receipt_digest,
            "provider_attempt_id": evidence.provider_attempt_id,
        }
    )
    return CapS1CanaryResultEvidence(**public_fields)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# attest_protocol_schema (protocol-attestation amendment §2)
# ---------------------------------------------------------------------------


def _inventory_digest_and_docs(directory: Path) -> tuple[str, list[tuple[str, Any]]]:
    rows: list[tuple[str, str]] = []
    docs: list[tuple[str, Any]] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(directory))
        data = path.read_bytes()
        rows.append((rel, hashlib.sha256(data).hexdigest()))
        if path.suffix == ".json":
            try:
                docs.append((rel, json.loads(data.decode("utf-8"))))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CanaryStop(
                    "SKILL_PROTOCOL_SCHEMA_UNATTESTED", "schema output is not valid JSON"
                ) from exc
    if not rows:
        raise CanaryStop(
            "SKILL_PROTOCOL_SCHEMA_UNATTESTED", "schema generation produced no files"
        )
    digest = _canonical_digest(sorted(rows))
    return digest, docs


def _resolve_local_schema_ref(document: dict[str, Any], ref: Any) -> Any | None:
    """Resolve one in-document JSON pointer without external/ref fallback."""

    if not isinstance(ref, str) or not ref.startswith("#/"):
        return None
    current: Any = document
    for raw_part in ref[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _is_exact_skill_discriminator(schema: Any) -> bool:
    if not isinstance(schema, dict):
        return False
    const = schema.get("const")
    enum = schema.get("enum")
    return const == "skill" or enum == ["skill"]


def _turn_start_document_supports_skill_input_path(document: Any) -> bool:
    """Follow only the generated TurnStartParams request/input branch.

    No recursive search is permitted: unrelated definitions, response
    schemas, deprecated nodes, and cross-document references cannot grant
    Mode-B authority.
    """

    if not isinstance(document, dict):
        return False
    if document.get("title") != "TurnStartParams" or document.get("type") != "object":
        return False
    required = document.get("required")
    if not isinstance(required, list) or not {"input", "threadId"}.issubset(required):
        return False
    properties = document.get("properties")
    if not isinstance(properties, dict):
        return False
    input_schema = properties.get("input")
    if not isinstance(input_schema, dict) or input_schema.get("type") != "array":
        return False
    items = input_schema.get("items")
    if not isinstance(items, dict) or set(items) != {"$ref"}:
        return False
    user_input = _resolve_local_schema_ref(document, items.get("$ref"))
    if not isinstance(user_input, dict):
        return False
    union_keys = [key for key in ("oneOf", "anyOf") if key in user_input]
    if union_keys != ["oneOf"]:
        return False
    variants = user_input["oneOf"]
    if not isinstance(variants, list):
        return False
    skill_variants: list[dict[str, Any]] = []
    for variant in variants:
        if not isinstance(variant, dict):
            return False
        variant_properties = variant.get("properties")
        if not isinstance(variant_properties, dict):
            return False
        if _is_exact_skill_discriminator(variant_properties.get("type")):
            skill_variants.append(variant)
    if len(skill_variants) != 1:
        return False
    skill_variant = skill_variants[0]
    skill_properties = skill_variant.get("properties")
    skill_required = skill_variant.get("required")
    if not isinstance(skill_properties, dict) or not isinstance(skill_required, list):
        return False
    if not {"type", "name", "path"}.issubset(skill_required):
        return False
    return all(
        isinstance(skill_properties.get(field), dict)
        and skill_properties[field].get("type") == "string"
        for field in ("name", "path")
    )


def _schema_supports_skill_input_path(docs: list[tuple[str, Any]]) -> bool:
    candidates = [
        (relative_path, document)
        for relative_path, document in docs
        if isinstance(document, dict) and document.get("title") == "TurnStartParams"
    ]
    if len(candidates) != 1:
        return False
    relative_path, document = candidates[0]
    if relative_path != "v2/TurnStartParams.json":
        return False
    return _turn_start_document_supports_skill_input_path(document)


def attest_protocol_schema(
    *,
    binary_path: Path,
    scratch_root: Path,
    run_command: Callable[..., Any] = subprocess.run,
    probe_env: "Mapping[str, str] | None" = None,
    probe_cwd: "Path | None" = None,
    app_server_argv: "Sequence[str] | None" = None,
) -> CodexProtocolAttestationReceipt:
    """The ONLY producer of :class:`CodexProtocolAttestationReceipt` (CAP-S1
    Sol review item 1): generates the stable/experimental schema dumps, then
    proves the receipt is bound to a real, launchable binary by starting
    that SAME binary as an App Server (single-binary law) via the real
    :class:`~scripts.ohf.laboratory.AppServerClient`, performing one bounded
    ``initialize`` (never a full session -- no ``thread/start``, no turn),
    and capturing the exact ``userAgent`` it reports. ``binary_version`` is
    set to that same value (one truth) and the probe process is shut down
    cleanly before this function ever returns. No field is ever trusted from
    a caller: every value here is either freshly measured over the real
    binary on disk or freshly observed over a real subprocess boundary.
    """

    binary_path = Path(binary_path)
    scratch_root = Path(scratch_root)
    scratch_root.mkdir(parents=True, exist_ok=True)
    resolved_probe_env = dict(probe_env) if probe_env is not None else dict(os.environ)
    resolved_probe_cwd = Path(probe_cwd) if probe_cwd is not None else scratch_root

    try:
        binary_digest = _sha256_file(binary_path)
    except OSError as exc:
        raise CanaryStop(
            "SKILL_PROTOCOL_SCHEMA_UNATTESTED", "binary is not observable"
        ) from exc

    # Deterministic name (Sol wave-3 review finding B4 self-cleanup is
    # preserved): every call to this function operates on its own
    # ``scratch_root``, so a fixed subdirectory name needs no random suffix
    # -- a second call against the SAME scratch_root correctly raises
    # ``FileExistsError`` rather than silently shadowing a prior run's
    # evidence.
    sealed_dir = scratch_root / SCHEMA_ATTESTATION_DIR_NAME
    sealed_dir.mkdir(parents=False, exist_ok=False)
    # Sol wave-3 review finding B4: everything from here on operates on the
    # exclusively-created sealed_dir. ANY CanaryStop raised below is a
    # schema-attestation failure boundary -- the sealed_dir is removed,
    # best-effort, before the stop propagates, so a partial (or fully
    # written but unsupportive) schema dump never leaks past this function.
    try:
        stable_dir = sealed_dir / "stable"
        experimental_dir = sealed_dir / "experimental"
        stable_dir.mkdir()
        experimental_dir.mkdir()

        for argv, out_dir in (
            (
                [str(binary_path), "app-server", "generate-json-schema", "--out", str(stable_dir)],
                stable_dir,
            ),
            (
                [
                    str(binary_path),
                    "app-server",
                    "generate-json-schema",
                    "--experimental",
                    "--out",
                    str(experimental_dir),
                ],
                experimental_dir,
            ),
        ):
            try:
                completed = run_command(argv, capture_output=True, text=True, timeout=120)
            except (OSError, subprocess.SubprocessError) as exc:
                raise CanaryStop(
                    "SKILL_PROTOCOL_SCHEMA_UNATTESTED", "schema generation command failed"
                ) from exc
            if getattr(completed, "returncode", None) != 0:
                raise CanaryStop(
                    "SKILL_PROTOCOL_SCHEMA_UNATTESTED", "schema generation exited nonzero"
                )
            if not any(path.is_file() for path in out_dir.rglob("*")):
                raise CanaryStop(
                    "SKILL_PROTOCOL_SCHEMA_UNATTESTED", "schema generation produced no output"
                )

        stable_digest, stable_docs = _inventory_digest_and_docs(stable_dir)
        experimental_digest, experimental_docs = _inventory_digest_and_docs(experimental_dir)
        # The initialize probe below negotiates ``experimentalApi=True``;
        # therefore only the schema generated with ``--experimental`` may
        # authorize the request contract used by that exact runtime surface.
        # Stable inventory remains sealed into the receipt for drift proof,
        # but cannot substitute for the negotiated request schema.
        supports = _schema_supports_skill_input_path(experimental_docs)

        # --- protocol-attestation amendment §2 item 4: the REAL initialize
        # probe (CAP-S1 Sol review item 1). Launches the SAME binary as an
        # App Server (single-binary law) via the real AppServerClient,
        # performs one bounded ``initialize``, and shuts the probe process
        # down cleanly. For the live realm this is genuinely the only RPC
        # the probe process ever answers -- no thread/turn is ever started.
        probe_argv = list(app_server_argv or (str(binary_path), "app-server"))
        probe_client = AppServerClient(
            probe_argv,
            env=resolved_probe_env,
            cwd=resolved_probe_cwd,
            start_new_session=True,
        )
        try:
            probe_client.start()
            initialized = probe_client.request(
                "initialize",
                {"clientInfo": _PROBE_CLIENT_INFO, "capabilities": {"experimentalApi": True}},
            )
        except Exception as exc:  # noqa: BLE001 -- any probe failure is unattested
            raise CanaryStop(
                "SKILL_PROTOCOL_SCHEMA_UNATTESTED", "protocol initialize probe failed"
            ) from exc
        finally:
            try:
                probe_client.close()
            except Exception:  # noqa: BLE001 -- best-effort probe teardown
                pass
        probe_user_agent = str(initialized.get("userAgent") or "").strip()
        if not probe_user_agent:
            raise CanaryStop(
                "SKILL_PROTOCOL_SCHEMA_UNATTESTED",
                "protocol initialize probe returned no userAgent",
            )

        return build_protocol_attestation_receipt(
            binary_path=str(binary_path),
            binary_digest=binary_digest,
            binary_version=probe_user_agent,
            stable_inventory_digest=stable_digest,
            experimental_inventory_digest=experimental_digest,
            supports_skill_input_path=supports,
            skill_input_schema_evidence=(
                SKILL_INPUT_SCHEMA_EVIDENCE if supports else ""
            ),
            probe_user_agent=probe_user_agent,
        )
    except Exception:
        shutil.rmtree(sealed_dir, ignore_errors=True)
        raise


# ---------------------------------------------------------------------------
# build_synthetic_workspace (protocol-attestation amendment §5)
# ---------------------------------------------------------------------------

_AMBIENT_SURFACE_NAMES = (".agents", ".codex", "plugins", "marketplace", "skills")

_HEX40_RE = re.compile(r"[0-9a-f]{40}")


def _run_workspace_git(argv: list[str], run_command: Callable[..., Any]) -> "subprocess.CompletedProcess | Any":
    try:
        completed = run_command(argv, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CanaryStop(
            "PROVIDER_REALM_UNAVAILABLE", "synthetic workspace git command failed"
        ) from exc
    if getattr(completed, "returncode", None) != 0:
        raise CanaryStop(
            "PROVIDER_REALM_UNAVAILABLE", "synthetic workspace git command exited nonzero"
        )
    return completed


def _init_real_git_repo(workspace: Path, run_command: Callable[..., Any]) -> str:
    """A REAL git repo, sealed local identity, one real commit (Sol wave-3
    review finding B2): the sealed base sha is that real commit -- never the
    ``"0" * 40`` fabrication a fresh, non-Git directory used to hand the
    adapter's ``base_sha_resolver``. Every step goes through the same
    injectable ``run_command`` seam ``attest_protocol_schema`` uses, so this
    is exercised by an injected fake in the in-process test suite and by a
    real ``git`` binary everywhere else."""

    for args in (
        ("init", "--quiet"),
        ("config", "user.name", "cap-s1-canary"),
        ("config", "user.email", "canary@synthetic.invalid"),
        ("add", "README.md"),
        ("commit", "--quiet", "-m", "cap-s1 synthetic canary workspace"),
    ):
        _run_workspace_git(["git", "-C", str(workspace), *args], run_command)
    completed = _run_workspace_git(
        ["git", "-C", str(workspace), "rev-parse", "HEAD"], run_command
    )
    sha = (getattr(completed, "stdout", "") or "").strip()
    if _HEX40_RE.fullmatch(sha) is None:
        raise CanaryStop(
            "PROVIDER_REALM_UNAVAILABLE", "synthetic workspace base commit is not a real sha"
        )
    return sha


def _apply_workspace_read_only(workspace: Path) -> bool:
    ok = True
    try:
        for dirpath, _dirnames, filenames in os.walk(str(workspace), topdown=False):
            for name in filenames:
                try:
                    os.chmod(os.path.join(dirpath, name), 0o444)
                except OSError:
                    ok = False
            try:
                os.chmod(dirpath, 0o555)
            except OSError:
                ok = False
    except OSError:
        ok = False
    return ok


def build_synthetic_workspace(
    scratch_root: Path,
    *,
    operation_id: str,
    run_command: Callable[..., Any] = subprocess.run,
) -> "tuple[Path, str, bool]":
    """Build the sealed synthetic workspace: a real, freshly-committed git
    repo (base sha = the real commit), then made read-only best-effort.

    Returns ``(workspace, base_sha, read_only_applied)``. Self-cleans on any
    ``CanaryStop`` raised after the workspace directory itself is created --
    a mid-init failure never leaves an orphan tree the caller must know
    about independently (mirrors ``attest_protocol_schema``'s own B4
    self-cleanup).
    """

    scratch_root = Path(scratch_root)
    scratch_root.mkdir(parents=True, exist_ok=True)
    workspace = scratch_root / "synthetic-workspace"
    workspace.mkdir(parents=False, exist_ok=False)
    try:
        (workspace / "README.md").write_text(
            f"CAP-S1 synthetic canary workspace\noperation: {operation_id}\n",
            encoding="utf-8",
        )
        for name in _AMBIENT_SURFACE_NAMES:
            assert not (workspace / name).exists()
        base_sha = _init_real_git_repo(workspace, run_command)
        read_only_applied = _apply_workspace_read_only(workspace)
        return workspace, base_sha, read_only_applied
    except Exception:
        _remove_tree(workspace)
        raise


# ---------------------------------------------------------------------------
# Adapter-error -> CanaryStop mapping
# ---------------------------------------------------------------------------


def _mapped_stop_for_adapter_error(exc: CodexAdapterError) -> "CanaryStop | None":
    message = str(exc)
    if "ambient_skill_surface_not_empty" in message:
        return CanaryStop("AMBIENT_SKILL_SURFACE_NOT_EMPTY", message)
    if "skill_set_causality_failed" in message or "duplicate_skill_row" in message:
        return CanaryStop("SKILL_SET_CAUSALITY_FAILED", message)
    if "skill_path_attestation_unavailable" in message:
        return CanaryStop("SKILL_PATH_ATTESTATION_UNAVAILABLE", message)
    if "skills_changed_during_canary" in message:
        return CanaryStop("SKILLS_CHANGED_DURING_CANARY", message)
    if exc.effect_unknown:
        return CanaryStop("EFFECT_UNKNOWN", message)
    return None


def _reraise_mapped(exc: CodexAdapterError) -> None:
    mapped = _mapped_stop_for_adapter_error(exc)
    if mapped is not None:
        raise mapped from exc
    raise


# ---------------------------------------------------------------------------
# Marker parsing (vertical amendment §9)
# ---------------------------------------------------------------------------


_STANDALONE_TOKEN_PATTERNS: dict[str, "re.Pattern[str]"] = {}


def _standalone_token_pattern(token: str) -> "re.Pattern[str]":
    """Closed grammar (Sol wave-3 review finding B5): a required/forbidden
    marker token must match as a standalone word, never as a bare substring
    -- ``COMPLETE`` must not fire inside ``COMPLETED``, and ``RESULT`` must
    not fire inside ``RESULTING``. The frozen regex shape is
    ``(?<![A-Z0-9-])TOKEN(?![A-Z0-9-])``; every marker token in
    ``_TURN_MARKER_RULES`` is drawn from the same closed
    uppercase-kebab vocabulary, so this boundary class is exact for them.
    (``_GLOBAL_FORBIDDEN_TOKENS`` are UNCHANGED plain substring checks --
    they are not uppercase-kebab tokens and the amendment does not ask for
    them to become standalone-word matches.)
    """

    pattern = _STANDALONE_TOKEN_PATTERNS.get(token)
    if pattern is None:
        pattern = re.compile(r"(?<![A-Z0-9-])" + re.escape(token) + r"(?![A-Z0-9-])")
        _STANDALONE_TOKEN_PATTERNS[token] = pattern
    return pattern


def _turn_markers_satisfied(skill_name: str, text: "str | None") -> bool:
    if not isinstance(text, str) or not text:
        return False
    if any(token in text for token in _GLOBAL_FORBIDDEN_TOKENS):
        return False
    required, forbidden = _TURN_MARKER_RULES[skill_name]
    if not all(_standalone_token_pattern(token).search(text) for token in required):
        return False
    if any(_standalone_token_pattern(token).search(text) for token in forbidden):
        return False
    return True


# ---------------------------------------------------------------------------
# Small filesystem/git helpers
# ---------------------------------------------------------------------------


def _remove_tree(path: Path) -> bool:
    """Best-effort removal, tolerant of a read-only tree.

    ``build_synthetic_workspace`` may have chmodded everything under
    ``path`` down to 0o444/0o555 -- a plain ``shutil.rmtree`` cannot unlink
    entries out of a non-writable directory, so each traversed directory is
    made writable through a no-follow descriptor first.  File modes do not
    need to change for unlink, and pathname chmod of a file would follow an
    attacker-controlled symlink outside the owned tree.
    """

    try:
        if path.is_dir() and not path.is_symlink():
            for dirpath, _dirnames, _filenames in os.walk(str(path)):
                descriptor: "int | None" = None
                try:
                    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                    if hasattr(os, "O_CLOEXEC"):
                        flags |= os.O_CLOEXEC
                    descriptor = os.open(dirpath, flags)
                    os.fchmod(descriptor, 0o700)
                except OSError:
                    pass
                finally:
                    if descriptor is not None:
                        try:
                            os.close(descriptor)
                        except OSError:
                            pass
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink()
    except OSError:
        pass
    return not path.exists()


def _resolve_repo_git_dir(repo_root: Path) -> Path:
    """The exact ``.git`` dir for ``repo_root`` -- a worktree-specific dir is
    a lawful answer (the shared object store remains reachable through it)."""

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CanaryStop(
            "PROVIDER_REALM_UNAVAILABLE", "repository git dir is not resolvable"
        ) from exc
    git_dir = Path(completed.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = (repo_root / git_dir).resolve()
    return git_dir


def _cleanup_dir_action(path: Path) -> "tuple[bool, bool]":
    removed = _remove_tree(path)
    return removed, removed


def _cleanup_owned_dir_action(
    path: Path, *, expected_device: int, expected_inode: int
) -> "tuple[bool, bool]":
    """Remove only the exact directory object this invocation created.

    A pathname is not ownership: another actor can replace an owned directory
    between creation and teardown.  Refuse deletion unless the final lstat
    still names the same non-symlink directory identity captured immediately
    after exclusive creation.
    """

    try:
        current = path.lstat()
    except FileNotFoundError:
        return False, True
    except OSError:
        return False, False
    if (
        stat.S_ISLNK(current.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or current.st_dev != expected_device
        or current.st_ino != expected_inode
    ):
        return False, False
    removed = _remove_tree(path)
    return removed, removed


def _cleanup_projection_action(projection) -> "tuple[bool, bool]":
    try:
        result = cleanup_skill_projection(projection)
    except SkillProjectionError:
        return False, False
    return bool(result.removed), bool(result.verified_absent)


def _teardown_process_action(
    adapter: CodexOperatorAdapter,
    generation_ref: ProcessGenerationRef,
    process_result: dict,
) -> "tuple[bool, bool]":
    """Attempted exactly once, never retried (Sol wave-3 review finding B4):
    the sole caller is ``run_canary``'s own finally-block cleanup ledger,
    which invokes every registered action exactly once regardless of which
    exit path was taken."""

    try:
        stopped = adapter.graceful_stop(
            generation_ref, operation_id=OperationId("ohf-op:cap-s1-stop")
        )
    except CodexAdapterError as exc:
        process_result["terminal_process_state"] = "UNKNOWN"
        process_result["stop_error"] = str(exc)
        return False, False
    process_result["terminal_process_state"] = stopped.process_liveness.value
    dead = stopped.process_liveness is ProcessLiveness.PROVEN_DEAD
    return dead, dead


def _verify_thread_absent_action(
    adapter: CodexOperatorAdapter,
    generation_ref: ProcessGenerationRef,
    process_result: dict,
) -> "tuple[bool, bool]":
    """Prove the attempt-local thread has no live owning runtime.

    This runs after the process teardown action in LIFO order.  It does not
    infer success from a cleanup exception: it fresh-reads the exact bound
    client liveness and the terminal process observation produced by that
    one teardown attempt.
    """

    try:
        state = adapter._state(generation_ref)  # noqa: SLF001 -- exact owned canary state
        provider_thread_id = state.provider_session_id
        alive = state.client.alive()
    except Exception:  # noqa: BLE001 -- absence proof must be explicit
        return False, False
    absent = (
        isinstance(provider_thread_id, str)
        and bool(provider_thread_id)
        and alive is False
        and process_result.get("terminal_process_state") == "PROVEN_DEAD"
    )
    return absent, absent


def _grant_by_runtime_name(binding: CodexSkillCanaryBinding, runtime_name: str):
    for grant in binding.profile.skill_grants:
        if grant.runtime_name == runtime_name:
            return grant
    raise KeyError(runtime_name)


def _build_envelope(
    binding: CodexSkillCanaryBinding, runtime_name: str, text: str
) -> CodexTurnInputEnvelope:
    grant = _grant_by_runtime_name(binding, runtime_name)
    final_path = f"{binding.projection.skills_root}/{grant.runtime_name}/SKILL.md"
    return CodexTurnInputEnvelope(
        text=text,
        skills=(
            CodexSkillTurnInput(
                capability_id=grant.capability_id,
                runtime_name=grant.runtime_name,
                skill_md_path=final_path,
                skill_content_digest=grant.skill_content_digest,
                package_generation_digest=binding.generation.package_generation_digest,
            ),
        ),
    )


def _default_fake_client_factory(argv: list[str], env: Mapping[str, str], cwd: Path):
    return AppServerClient(argv, env=env, cwd=cwd, start_new_session=True)


@dataclasses.dataclass(frozen=True, kw_only=True)
class _CanaryBackendConfig:
    single_binary_path: Path
    adapter_codex_home: Path
    adapter_argv: "tuple[str, ...] | None"
    extra_env: dict[str, str]


def _configure_canary_backend(
    *,
    backend: str,
    binary_path: "Path | None",
    codex_home: "Path | None",
    repo_root: Path,
    attempt_root: Path,
) -> _CanaryBackendConfig:
    """Perform post-ownership backend setup inside the attempt transaction."""

    if backend == "live":
        assert binary_path is not None  # validated before the first effect
        assert codex_home is not None
        return _CanaryBackendConfig(
            single_binary_path=Path(binary_path),
            adapter_codex_home=Path(codex_home),
            adapter_argv=None,
            extra_env={"PYTHONPATH": str(repo_root)},
        )

    single_binary_path = (
        Path(binary_path) if binary_path is not None else FAKE_CODEX_BINARY_PATH
    )
    adapter_codex_home = (
        Path(codex_home) if codex_home is not None else attempt_root / "codex-home"
    )
    if codex_home is None:
        adapter_codex_home.mkdir(parents=False, exist_ok=False)
        adapter_codex_home.chmod(0o700)
        auth_path = adapter_codex_home / "auth.json"
        auth_path.write_text("fixture credential bytes", encoding="utf-8")
        auth_path.chmod(0o600)
    return _CanaryBackendConfig(
        single_binary_path=single_binary_path,
        adapter_codex_home=adapter_codex_home,
        adapter_argv=(str(single_binary_path), "app-server"),
        extra_env={
            "PYTHONPATH": str(repo_root),
            "PYTHONDONTWRITEBYTECODE": "1",
            "OHF_FAKE_STATE": str(attempt_root / "fake-state.json"),
            "OHF_FAKE_MODEL": CANARY_REQUESTED_MODEL,
            "OHF_FAKE_MCP_GONE": "1",
            "OHF_FAKE_BUNDLED_DISABLED": "1",
            "OHF_FAKE_ECHO_CLIENT_INFO": "1",
            "OHF_FAKE_CAP_S1_TURN_REPLIES": "1",
        },
    )


# ---------------------------------------------------------------------------
# run_canary
# ---------------------------------------------------------------------------


def run_canary(
    *,
    backend: str,
    binary_path: "Path | None",
    codex_home: "Path | None",
    repo_root: Path,
    scratch_root: Path,
    operation_id: str,
    protected_join: str,
    client_factory=None,
    run_command: Callable[..., Any] = subprocess.run,
) -> CanaryEvidence:
    # The protected-source join is an execution gate, not merely a terminal
    # result annotation.  Refuse before creating scratch state, generating
    # schemas, constructing a workspace, or reaching a provider seam.
    if (
        not isinstance(protected_join, str)
        or _HEX40_RE.fullmatch(protected_join) is None
    ):
        raise CanaryStop(
            "PROVIDER_REALM_UNAVAILABLE",
            "protected source join is not attested",
        )
    if backend not in ("fake", "live"):
        raise ValueError(f"unsupported backend: {backend!r}")

    repo_root = Path(repo_root)
    scratch_root = Path(scratch_root)
    # REQUEST_CHANGES 5112468319: every zero-effect realm/argument gate runs
    # before the first attempt-owned filesystem object exists.
    if client_factory is None:
        raise ValueError(f"{backend} backend requires an explicit client_factory")
    if backend == "live":
        if binary_path is None or codex_home is None:
            raise CanaryStop(
                "PROVIDER_REALM_UNAVAILABLE", "live backend requires binary_path and codex_home"
            )
        codex_home = Path(codex_home)
        if codex_home == default_user_codex_home():
            raise CanaryStop(
                "PROVIDER_REALM_UNAVAILABLE", "live mode refuses the implicit default CODEX_HOME"
            )
        try:
            validate_live_codex_home(codex_home)
        except RuntimeError as exc:
            raise CanaryStop(
                "PROVIDER_REALM_UNAVAILABLE",
                "dedicated Codex home validation failed",
            ) from exc
    elif binary_path is not None and not Path(binary_path).is_file():
        # Never manufacture a caller-selected path outside the owned attempt
        # transaction.  A custom fake binary is an input and must pre-exist.
        raise CanaryStop(
            "PROVIDER_REALM_UNAVAILABLE", "fake binary input is unavailable"
        )

    scratch_root.mkdir(parents=True, exist_ok=True)

    cleanup_actions: list[tuple[str, Callable[[], "tuple[bool, bool]"]]] = []
    process_result: dict[str, Any] = {}
    evidence_local: "CanaryEvidence | None" = None

    # REQUEST_CHANGES 5112126365: this fixed pathname is attempt-local state
    # only when THIS invocation created it.  Exclusive creation occurs before
    # schema/projection/provider/thread/process work and before the fake realm
    # writes auth/state fixtures.  A pre-existing root is foreign state: refuse
    # without registering it for cleanup and therefore without deleting a byte.
    attempt_root = scratch_root / "cap-s1-attempt-root"
    try:
        attempt_root.mkdir(parents=False, exist_ok=False)
    except FileExistsError as exc:
        raise CanaryStop(
            "PROVIDER_REALM_UNAVAILABLE", "attempt root is not exclusively owned"
        ) from exc
    except OSError as exc:
        raise CanaryStop(
            "PROVIDER_REALM_UNAVAILABLE", "attempt root could not be created"
        ) from exc

    # Everything after exclusive creation is protected by the same cleanup
    # ledger, including identity capture and fake realm credential/state setup.
    try:
        attempt_identity = attempt_root.stat()
        cleanup_actions.append(
            (
                "attempt",
                lambda: _cleanup_owned_dir_action(
                    attempt_root,
                    expected_device=attempt_identity.st_dev,
                    expected_inode=attempt_identity.st_ino,
                ),
            )
        )
        backend_config = _configure_canary_backend(
            backend=backend,
            binary_path=binary_path,
            codex_home=codex_home,
            repo_root=repo_root,
            attempt_root=attempt_root,
        )
    except BaseException:
        if cleanup_actions:
            for _kind, cleanup_action in reversed(cleanup_actions):
                try:
                    cleanup_action()
                except Exception:  # noqa: BLE001 -- preserve the setup failure
                    pass
        else:
            # Identity capture itself failed.  Only remove the still-empty
            # directory we just created; never recurse without a bound identity.
            try:
                attempt_root.rmdir()
            except OSError:
                pass
        raise

    single_binary_path = backend_config.single_binary_path
    adapter_codex_home = backend_config.adapter_codex_home
    adapter_argv = backend_config.adapter_argv
    extra_env = backend_config.extra_env

    try:
        # The probe environment mirrors the adapter's own env-building logic
        # (``CodexOperatorAdapter._env``) closely enough to launch the SAME
        # single binary the adapter will later launch, without yet needing
        # the synthetic workspace (which does not exist at this point in the
        # sequence) -- the probe only ever issues ``initialize``, which never
        # touches the workspace.
        # EXACTLY the adapter's own launch environment -- nothing more.
        # The consumed live attempt proved a superset env is fatal: the
        # inherited terminal-identity variables (TERM_PROGRAM and friends)
        # are embedded into the real binary's reported userAgent, so a
        # probe carrying them seals a version string the sanitized launch
        # can never observe (second EFFECT_UNKNOWN, PR #350). The probe
        # context must be byte-equal to CodexOperatorAdapter._env: four
        # keys plus extra_env, built from empty.
        probe_env = {}
        probe_env.update(
            {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": str(adapter_codex_home),
                "CODEX_HOME": str(adapter_codex_home),
                "LC_ALL": "C",
            }
        )
        probe_env.update(extra_env)

        receipt = attest_protocol_schema(
            binary_path=single_binary_path,
            scratch_root=scratch_root,
            run_command=run_command,
            probe_env=probe_env,
            probe_cwd=scratch_root,
            app_server_argv=(str(single_binary_path), "app-server"),
        )
        cleanup_actions.append(
            ("schema", lambda: _cleanup_dir_action(scratch_root / SCHEMA_ATTESTATION_DIR_NAME))
        )

        # Harness-version binding (CAP-S1 Sol review item 1): the receipt's
        # ``probe_user_agent`` -- the exact userAgent the SAME binary just
        # reported over a real ``initialize`` call -- is the ONE truth for
        # both realms now; ``receipt.binary_version`` is set to this same
        # value by ``attest_protocol_schema``. The runner seals
        # ``expected_harness_version`` from it so the adapter's own launch-
        # time ``initialize`` userAgent equality check closes the loop.
        harness_version = receipt.probe_user_agent
        if not harness_version:
            raise CanaryStop(
                "SKILL_PROTOCOL_SCHEMA_UNATTESTED", "harness version could not be sealed"
            )
        adapter_binary_path = single_binary_path
        adapter_binary_digest = receipt.binary_digest

        # --- synthetic workspace: real sealed git identity (Sol B2) -------
        workspace, workspace_base_sha, _workspace_read_only_applied = build_synthetic_workspace(
            scratch_root, operation_id=operation_id, run_command=run_command
        )
        cleanup_actions.append(("workspace", lambda: _cleanup_dir_action(workspace)))
        if backend == "fake":
            extra_env["OHF_FAKE_WORKSPACE"] = str(workspace)

        # --- exact reviewed source package + V4 profile -------------------
        # Residual refusal row (CAP-S1 Sol review item 3): every step here
        # that can raise ``CapabilityPackageError`` -- including an empty or
        # malformed ``source_commit``/``source_tree_sha`` in a doctored
        # fixture -- is now a TYPED, deterministic ``CanaryStop`` rather than
        # an uncaught internal exception escaping the runner's own closed
        # failure vocabulary, and fires before the provider process ever
        # starts.
        try:
            fixture_path = repo_root / V4_FIXTURE_RELATIVE_PATH
            registry = ExecutionCapabilityRegistry.load(fixture_path, source_root=repo_root)
            profile = registry.resolve(PROFILE_ID)
            raw_document = json.loads(fixture_path.read_text(encoding="utf-8"))
            raw_package = raw_document["capability_packages"][PACKAGE_CAPABILITY_ID]
            generation = build_capability_package_generation(
                capability_id=PACKAGE_CAPABILITY_ID, raw=raw_package
            )
        except (
            CapabilityPackageError,
            CapabilityPolicyError,
            KeyError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            raise CanaryStop(
                "PROVIDER_REALM_UNAVAILABLE", "candidate source package is unattested"
            ) from exc
        # Candidate identities are pinned from the already-verified fixture
        # generation BEFORE the provider process ever starts (Sol wave-3
        # review finding B5) -- never a ``git rev-parse HEAD`` read of this
        # repository's own moving working tree after execution.
        candidate_commit = generation.source_commit
        candidate_tree = generation.source_tree_sha
        if not _HEX40_RE.fullmatch(candidate_commit) or not _HEX40_RE.fullmatch(candidate_tree):
            raise CanaryStop(
                "PROVIDER_REALM_UNAVAILABLE", "candidate identity is empty or malformed"
            )

        process_generation_id = f"{operation_id}-gen1"

        # Sol wave-3 review (5087345399, finding B2): the origin is now a
        # verified, ephemeral archive of the EXACT reviewed commit/tree from
        # this repository's own git object store -- never a writable,
        # non-Git ``cap-s1-release-root/<commit>`` copy mislabeled
        # INSTALLED_RELEASE.
        git_dir = _resolve_repo_git_dir(repo_root)
        try:
            origin_receipt = create_ephemeral_archive_origin(
                repository_git_dir=git_dir,
                source_commit=generation.source_commit,
                package_root=generation.package_root,
                scratch_root=scratch_root,
                expected_package_tree_sha=generation.source_tree_sha,
            )
        except SkillProjectionError as exc:
            raise CanaryStop(
                "PROVIDER_REALM_UNAVAILABLE", "ephemeral origin archive unavailable"
            ) from exc
        cleanup_actions.append(
            ("origin", lambda: _cleanup_dir_action(Path(origin_receipt.origin_root)))
        )

        projection = stage_skill_projection(
            generation=generation,
            origin_mode=ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE,
            origin_root=Path(origin_receipt.origin_root),
            attempt_root=attempt_root,
            owning_operation_id=operation_id,
            owning_process_generation=process_generation_id,
            origin_receipt=origin_receipt,
        )
        cleanup_actions.append(("projection", lambda: _cleanup_projection_action(projection)))

        # The binding carries the EXACT receipt ``attest_protocol_schema``
        # produced -- never a fresh construction (CAP-S1 Sol review item 1:
        # ``attest_protocol_schema`` is the ONLY producer of
        # ``CodexProtocolAttestationReceipt`` in production code).
        binding = CodexSkillCanaryBinding(
            generation=generation,
            profile=profile,
            projection=projection,
            protocol_receipt=receipt,
        )

        # --- adapter construction --------------------------------------------
        adapter_extra_env = extra_env
        adapter_client_factory = client_factory
        fake_bytecode_binding = extra_env.get("PYTHONDONTWRITEBYTECODE")
        if backend == "fake" and fake_bytecode_binding is not None:
            if fake_bytecode_binding != "1":
                raise CanaryStop(
                    "PROVIDER_REALM_UNAVAILABLE",
                    "fake backend bytecode binding is invalid",
                )
            # The adapter deliberately accepts only its frozen environment
            # allowlist.  Keep that policy intact, then restore this fixed
            # fake-only interpreter control at the final client-process
            # boundary.  The protocol probe and the actual fake process thus
            # receive the same bytecode setting without changing live runs,
            # the binary identity, or the app-server argv.
            adapter_extra_env = dict(extra_env)
            adapter_extra_env.pop("PYTHONDONTWRITEBYTECODE")
            base_client_factory = client_factory

            def fake_bytecode_client_factory(
                argv: list[str], env: Mapping[str, str], cwd: Path
            ):
                bound_env = dict(env)
                bound_env["PYTHONDONTWRITEBYTECODE"] = fake_bytecode_binding
                return base_client_factory(argv, bound_env, cwd)

            adapter_client_factory = fake_bytecode_client_factory

        adapter = CodexOperatorAdapter(
            binary_path=adapter_binary_path,
            codex_home=adapter_codex_home,
            workspace_root=workspace,
            worker_id=CANARY_WORKER_ID,
            app_server_argv=adapter_argv,
            app_server_config_overrides=profile.app_server_config_overrides(),
            expected_harness_version=harness_version,
            # Config-digest attestation gate (protocol amendment §5): the
            # observed-config projection helper
            # (``app_server_security_config_projection``) now observes
            # ``skills.bundled`` the same way the policy-config projection
            # helper (``ExecutionCapabilityProfile.app_server_config_projection``)
            # emits it, so this V4 skill-grant profile's own
            # ``expected_config_digest`` is attestable and the gate is armed
            # for real. The fake backend's App Server double echoes the
            # matching ``bundled`` block (``OHF_FAKE_BUNDLED_DISABLED=1``,
            # set above); the live backend's real binary is launched with
            # the profile's overrides regardless, and whether it echoes the
            # ``bundled`` table back on ``config/read`` is phase-13 evidence
            # for Sol -- an honest CONFIG_DRIFT refusal there is the correct
            # outcome, never special-cased away here.
            expected_config_digest=profile.expected_config_digest,
            network_policy="disabled",
            base_sha_resolver=lambda _path: workspace_base_sha,
            client_factory=adapter_client_factory,
            extra_env=adapter_extra_env,
            skill_canary_binding=binding,
        )

        ws_stat = adapter.workspace_root.stat()
        # Sol wave-3 review finding B2: the profile's OWN fail-closed
        # manifest is used exactly as returned -- never re-wrapped with a
        # fabricated read-only unclassified-capability escape hatch.
        manifest = profile.capability_manifest(harness_binary_digest=adapter.binary_digest)
        session_epoch_id = f"{operation_id}-epoch"
        attempt_id = f"{operation_id}-attempt"

        requested = RequestedExecutionProfile(
            worker_id=CANARY_WORKER_ID,
            provider="openai-codex",
            requested_model=CANARY_REQUESTED_MODEL,
            harness_kind="codex-app-server",
            harness_binary_digest=adapter.binary_digest,
            harness_version=harness_version,
            workspace=WorkspaceIdentity(
                str(adapter.workspace_root),
                workspace_base_sha,
                ws_stat.st_dev,
                ws_stat.st_ino,
                ws_stat.st_uid,
                ws_stat.st_gid,
            ),
            sandbox_policy="read-only",
            approval_policy="never",
            network_policy="disabled",
            capabilities=manifest,
            native_helper_policy=NativeHelperPolicy.DISABLED,
            expected_config_digest=profile.expected_config_digest,
            authority_policy_hash=_CANARY_AUTHORITY_POLICY_HASH,
        )

        epoch = SessionEpochRef(session_epoch_id, attempt_id, CANARY_WORKER_ID, 1)
        generation_ref = ProcessGenerationRef(
            process_generation_id, session_epoch_id, 1, CANARY_WORKER_ID
        )

        try:
            adapter.start_session(
                operation_id=OperationId("ohf-op:cap-s1-start"),
                requested=requested,
                epoch=epoch,
                generation=generation_ref,
            )
        except CodexAdapterError as exc:
            _reraise_mapped(exc)
        except _SeamProbeRefusal as exc:
            raise CanaryStop("PROVIDER_REALM_UNAVAILABLE", str(exc)) from exc

        # The process is now registered with the adapter -- schedule its
        # exactly-once teardown attempt via the cleanup ledger (Sol wave-3
        # review finding B4). Every exit path below this point tears the
        # process down exactly once, never retried, before the schema/
        # workspace/archive/projection resources it may still be touching.
        cleanup_actions.append(
            (
                "thread",
                lambda: _verify_thread_absent_action(
                    adapter, generation_ref, process_result
                ),
            )
        )
        cleanup_actions.append(
            ("process", lambda: _teardown_process_action(adapter, generation_ref, process_result))
        )

        observed = adapter.observed_attestation(generation_ref)
        launch = compare_launch(requested, observed)

        state = adapter._state(generation_ref)  # noqa: SLF001 -- runner owns process teardown (see module docstring below the class)
        client = state.client

        try:
            raw_launch_skills = client.request(
                "skills/list", skills_list_params(str(adapter.workspace_root))
            )
        except Exception as exc:  # noqa: BLE001 -- transport/timeout, never retried
            raise CanaryStop("EFFECT_UNKNOWN", "post-launch skills/list read failed") from exc
        skills_list_raw_shape_digest = _canonical_digest(raw_launch_skills)
        try:
            launch_rows = parse_skills_list_strict(
                raw_launch_skills, expected_cwd=str(adapter.workspace_root)
            )
            baseline_enabled_names: tuple[str, ...] = tuple(
                sorted(enabled_skill_names(launch_rows))
            )
        except SkillProtocolShapeError as exc:
            raise CanaryStop(
                "SKILL_SET_CAUSALITY_FAILED", "post-launch skills/list shape refused"
            ) from exc

        observed_enabled_names = baseline_enabled_names

        turn_marker_results: tuple[tuple[str, bool], ...] = ()
        after_add_enabled_names: tuple[str, ...] = ()
        served_model = observed.served_model

        if launch.decision is LaunchDecision.ALLOW:
            cursor = EventCursor(attempt_id, session_epoch_id, process_generation_id, local_sequence=0)
            results: list[tuple[str, bool]] = []
            for skill_name in TURN_ORDER:
                turn_ref = TurnRef(
                    f"cap-s1-turn-{skill_name}", session_epoch_id, process_generation_id, attempt_id
                )
                envelope = _build_envelope(binding, skill_name, _TURN_TEXTS[skill_name])
                adapter.turn_input_loader = lambda _turn, _env=envelope: _env
                try:
                    adapter.begin_turn(
                        operation_id=OperationId(f"ohf-op:cap-s1-turn-{skill_name}"),
                        turn=turn_ref,
                        generation=generation_ref,
                        launch=launch,
                    )
                except CodexAdapterError as exc:
                    _reraise_mapped(exc)
                cursor = EventCursor(
                    attempt_id,
                    session_epoch_id,
                    process_generation_id,
                    local_sequence=cursor.local_sequence,
                    turn_id=turn_ref.turn_id,
                )
                try:
                    _events, cursor = adapter.read_events(cursor)
                except CodexAdapterError as exc:
                    _reraise_mapped(exc)
                try:
                    candidate = adapter.collect_candidate_result(turn_ref)
                except CodexAdapterError as exc:
                    _reraise_mapped(exc)
                results.append((skill_name, _turn_markers_satisfied(skill_name, candidate.summary)))
            turn_marker_results = tuple(results)

            # A genuine NEW read (Sol wave-3 review finding B5): re-confirm
            # the skill surface right after the whole turn loop, before the
            # extraRoots/set [] clear -- closing the gap between the
            # launch-time baseline and the final clear that the
            # notification-based ``skills_changed`` check alone might miss.
            try:
                post_turns_raw = client.request(
                    "skills/list", skills_list_params(str(adapter.workspace_root))
                )
                post_turns_rows = parse_skills_list_strict(
                    post_turns_raw, expected_cwd=str(adapter.workspace_root)
                )
                after_add_enabled_names = tuple(sorted(enabled_skill_names(post_turns_rows)))
            except SkillProtocolShapeError as exc:
                raise CanaryStop(
                    "SKILL_SET_CAUSALITY_FAILED", "post-turn skills/list shape refused"
                ) from exc
            except Exception as exc:  # noqa: BLE001 -- transport/timeout, never retried
                raise CanaryStop("EFFECT_UNKNOWN", "post-turn skills/list read failed") from exc

        # --- clear: extraRoots/set [] and re-verify empty --------------------
        after_clear_enabled_names: tuple[str, ...] = ()
        try:
            client.request("skills/extraRoots/set", extra_roots_set_params([]))
            extra_roots_set_outcomes = ("cleared",)
            clear_raw = client.request(
                "skills/list", skills_list_params(str(adapter.workspace_root))
            )
            clear_rows = parse_skills_list_strict(
                clear_raw, expected_cwd=str(adapter.workspace_root)
            )
        except SkillProtocolShapeError as exc:
            raise CanaryStop(
                "SKILL_SET_CAUSALITY_FAILED", "post-clear skills/list shape refused"
            ) from exc
        except CodexAdapterError as exc:
            _reraise_mapped(exc)
            raise  # pragma: no cover -- _reraise_mapped always raises
        except Exception as exc:  # noqa: BLE001 -- transport/timeout during teardown
            raise CanaryStop("EFFECT_UNKNOWN", "post-clear teardown call failed") from exc
        else:
            after_clear_enabled_names = tuple(sorted(enabled_skill_names(clear_rows)))
            if enabled_skill_names(clear_rows):
                raise CanaryStop(
                    "SKILL_SET_CAUSALITY_FAILED", "post-clear skill surface is not empty"
                )

        # --- artifact inventory (computed BEFORE teardown removes anything) --
        schema_dir = scratch_root / SCHEMA_ATTESTATION_DIR_NAME
        artifact_inventory = tuple(
            sorted(
                [f"schema:{p.relative_to(schema_dir)}" for p in schema_dir.rglob("*") if p.is_file()]
                + [f"workspace:{p.relative_to(workspace)}" for p in workspace.rglob("*") if p.is_file()]
                + [f"projection:file_count={len(projection.file_rows)}"]
            )
        )

        skill_grant_digests = tuple(
            sorted((grant.capability_id, grant.grant_digest) for grant in profile.skill_grants)
        )

        evidence_local = CanaryEvidence(
            candidate_commit=candidate_commit,
            candidate_tree=candidate_tree,
            canary_operation_id=operation_id,
            provider_attempt_id=attempt_id,
            protected_join=protected_join,
            workspace_root=str(adapter.workspace_root),
            process_generation=process_generation_id,
            v4_policy_digest=registry.policy_digest,
            package_source_digest=generation.package_source_digest,
            package_generation_digest=generation.package_generation_digest,
            skill_grant_digests=skill_grant_digests,
            skill_closure_digests=tuple(projection.skill_content_digests),
            projection_receipt_digest=_canonical_digest(dataclasses.asdict(projection)),
            binary_digest=adapter.binary_digest,
            binary_version=harness_version,
            origin_mode=projection.origin_mode,
            origin_authentication=projection.origin_authentication,
            skills_root=projection.skills_root,
            app_server_config_digest=observed.effective_config_digest,
            extra_roots_set_outcomes=extra_roots_set_outcomes,
            skills_list_raw_shape_digest=skills_list_raw_shape_digest,
            baseline_enabled_names=baseline_enabled_names,
            after_add_enabled_names=after_add_enabled_names,
            observed_enabled_names=observed_enabled_names,
            after_clear_enabled_names=after_clear_enabled_names,
            protocol_receipt_digest=_canonical_digest(
                dataclasses.asdict(binding.protocol_receipt)
            ),
            launch_decision=launch.decision.value,
            turn_marker_results=turn_marker_results,
            served_model=served_model,
            terminal_process_state="UNKNOWN",
            artifact_inventory=artifact_inventory,
            cleanup=CanaryCleanupRecord(),
        )
    finally:
        # Sol wave-3 review finding B4: EVERYTHING created after scratch
        # setup is torn down here, on EVERY exit path -- happy, CanaryStop,
        # adapter error, or unexpected exception -- in the exact reverse of
        # its registration order, each action attempted exactly once.
        artifacts: list[tuple[str, bool, bool]] = []
        for kind, action in reversed(cleanup_actions):
            try:
                removed, verified_absent = action()
            except Exception:  # noqa: BLE001 -- a cleanup action must never mask the original error
                removed, verified_absent = False, False
            artifacts.append((kind, removed, verified_absent))
        cleanup_record = CanaryCleanupRecord(artifacts=tuple(artifacts))

    evidence = dataclasses.replace(
        evidence_local,
        cleanup=cleanup_record,
        terminal_process_state=process_result.get("terminal_process_state", "UNKNOWN"),
    )
    # Invocation-local authenticity: retain a weak reference to this exact
    # object plus the route the owner actually selected.  A bare integer ID
    # cannot distinguish fake/live provenance and can be reused after GC.
    _register_cap_s1_canary_evidence(
        evidence,
        backend=backend,
        client_factory=client_factory,
    )
    return evidence


# ---------------------------------------------------------------------------
# Closed CAP-S1 result contract (CAP-S1 Sol review item 5)
# ---------------------------------------------------------------------------
#
# Before this commission no closed result validator existed at all, and
# ``CanaryEvidence`` alone accepted an empty candidate identity anywhere it
# was hand-assembled outside ``run_canary``. This section delivers the
# closed validator, source-owned observer and immediate constructor.  The
# serialized packet is a report rather than an authority input; production
# proof is derived inside the same invocation from ``run_canary`` cleanup,
# fixed local/mutation/security commands and authenticated GitHub reads.

RESULT_CONTRACT_MARKER = "cap-s1-result-contract-v1"
RESULT_CONTRACT_SCHEMA = "mastermind.cap_s1_result/v1"
RESULT_RELEASE_STATE = (
    "BUILT_NOT_PROVEN/FOUR_SKILL_CAPABILITY_PACKAGE_SOURCE/"
    "DEFAULT_V4_NOT_PROMOTED/PRODUCTION_UNARMED"
)
RESULT_CHANGED_PATHS = (
    "control_plane/chairman_control_room_remote.py",
    "control_plane/codex_operator_adapter.py",
    "control_plane/executive_agent_capabilities.py",
    "control_plane/executive_capability_packages.py",
    "control_plane/operator_harness_contract.py",
    "docs/superpowers/plans/2026-09-01-sol-capability-fabric-cap-s1.md",
    "ops/control_room_remote/install.sh",
    "scripts/ohf/cap_s1_mastermind_operator_canary.py",
    "scripts/ohf/capability_skill_projection.py",
    "scripts/ohf/fake_app_server.py",
    "scripts/ohf/fake_codex_binary.py",
    "scripts/ohf/fixtures/executive_agent_capabilities_v4_mastermind_operator.json",
    "scripts/ohf/protocol.py",
    "tests/test_cap_s1_mastermind_operator_canary.py",
    "tests/test_codex_operator_adapter.py",
    "tests/test_control_room_remote_install.py",
    "tests/test_executive_agent_capabilities.py",
    "tests/test_executive_agent_capabilities_v4.py",
    "tests/test_executive_capability_packages.py",
    "tests/test_ohf_p1a_operator_harness_contract.py",
    "tests/test_ohf_protocol_fidelity.py",
)

# Source-owned CAP-S1 proof registry.  These values are deliberately data, not
# arguments: callers may identify a run/review, but may not choose the command,
# source paths, endpoints, parsers, environment, scanners or mutant policy that
# decide whether the result is evidence-backed.
CAP_S1_OBSERVER_TEST_MODULES = (
    "tests/test_cap_s1_mastermind_operator_canary.py",
    "tests/test_codex_operator_adapter.py",
    "tests/test_control_room_remote_install.py",
    "tests/test_executive_agent_capabilities.py",
    "tests/test_executive_agent_capabilities_v4.py",
    "tests/test_executive_capability_packages.py",
    "tests/test_ohf_p1a_operator_harness_contract.py",
    "tests/test_ohf_protocol_fidelity.py",
    "tests/test_a2_agent_relay_host_prepare.py",
    "tests/test_autonomy_control_room_projection.py",
    "tests/test_chairman_cognition_agentos_warning_currentness.py",
    "tests/test_chairman_cognition_sources.py",
    "tests/test_chairman_control_room.py",
    "tests/test_chairman_control_room_remote.py",
    "tests/test_chairman_control_room_ui_x1.py",
    "tests/test_mas115_setup.py",
    "tests/test_nonseat_canary.py",
)
CAP_S1_OBSERVER_GITHUB_ENDPOINT_FAMILIES = (
    "repos/{repository}/pulls/{pr_number}",
    "repos/{repository}/git/ref/pull/{pr_number}/head",
    "repos/{repository}/commits/{head}/check-runs",
    "repos/{repository}/check-runs/{check_run_id}",
    "repos/{repository}/actions/runs/{run_id}",
    "repos/{repository}/actions/runs/{run_id}/jobs?per_page=100&page={page}",
    "repos/{repository}/code-scanning/analyses?ref={pr_head_ref}&per_page=100&page={page}",
    "repos/{repository}/code-scanning/alerts?pr={pr_number}&state=open&per_page=100&page={page}",
)
CAP_S1_OBSERVER_MUTANTS = (
    (
        "CAP_A_UNRELATED_SKILL_ACCEPTED",
        "tests/test_cap_s1_mastermind_operator_canary.py::"
        "test_run_canary_pathless_request_with_unrelated_skill_fragment_refuses_before_thread_start",
    ),
    (
        "CAP_B_FORGED_PRODUCER_ACCEPTED",
        "tests/test_cap_s1_mastermind_operator_canary.py::"
        "test_cap_s1_result_refuses_wholly_forged_producer_family",
    ),
    (
        "CAP_C_FIRST_EFFECT_CLEANUP_BYPASSED",
        "tests/test_cap_s1_mastermind_operator_canary.py::"
        "test_run_canary_fake_auth_setup_failure_cleans_first_owned_effect",
    ),
)
CAP_S1_OBSERVER_MUTANT_ASSERTIONS = tuple(
    (mutation_id, node, mutation_id)
    for mutation_id, node in CAP_S1_OBSERVER_MUTANTS
)
CAP_S1_OBSERVER_MUTANT_TRANSFORMS = (
    (
        "CAP_A_UNRELATED_SKILL_ACCEPTED",
        "scripts/ohf/cap_s1_mastermind_operator_canary.py",
        "    return _turn_start_document_supports_skill_input_path(document)\n",
        "    return _turn_start_document_supports_skill_input_path(document) or "
        "'\"path\"' in json.dumps(document, sort_keys=True)\n",
    ),
    (
        "CAP_B_FORGED_PRODUCER_ACCEPTED",
        "scripts/ohf/cap_s1_mastermind_operator_canary.py",
        "    if forbidden_proof_inputs:\n        raise CapS1ResultError(\n"
        "            \"cap_s1_result_caller_proof_authority_forbidden\"\n        )\n",
        "    if False and forbidden_proof_inputs:\n        raise CapS1ResultError(\n"
        "            \"cap_s1_result_caller_proof_authority_forbidden\"\n        )\n",
    ),
    (
        "CAP_C_FIRST_EFFECT_CLEANUP_BYPASSED",
        "scripts/ohf/cap_s1_mastermind_operator_canary.py",
        "            for _kind, cleanup_action in reversed(cleanup_actions):\n"
        "                try:\n                    cleanup_action()\n"
        "                except Exception:  # noqa: BLE001 -- preserve the setup failure\n"
        "                    pass\n",
        "            for _kind, cleanup_action in reversed(cleanup_actions):\n"
        "                try:\n                    continue\n"
        "                except Exception:  # noqa: BLE001 -- preserve the setup failure\n"
        "                    pass\n",
    ),
)
_CAP_S1_PYTEST_PROVENANCE_EXIT = 86
_CAP_S1_PYTEST_SOURCE_MODULES = (
    (
        "scripts.ohf.cap_s1_mastermind_operator_canary",
        "scripts/ohf/cap_s1_mastermind_operator_canary.py",
    ),
    (
        "scripts.ohf.capability_skill_projection",
        "scripts/ohf/capability_skill_projection.py",
    ),
    ("scripts.ohf.protocol", "scripts/ohf/protocol.py"),
    ("scripts.ohf.laboratory", "scripts/ohf/laboratory.py"),
    (
        "control_plane.codex_operator_adapter",
        "control_plane/codex_operator_adapter.py",
    ),
    (
        "control_plane.executive_agent_capabilities",
        "control_plane/executive_agent_capabilities.py",
    ),
    (
        "control_plane.executive_capability_packages",
        "control_plane/executive_capability_packages.py",
    ),
    (
        "control_plane.operator_harness_contract",
        "control_plane/operator_harness_contract.py",
    ),
)
_CAP_S1_PYTEST_BOOTSTRAP = r'''import hashlib
import importlib
import json
import os
import pathlib
import stat
import sys

PROVENANCE_EXIT = 86


def refuse():
    os._exit(PROVENANCE_EXIT)


def stable_sha256(path, maximum):
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
            or before.st_size <= 0 or before.st_size > maximum):
        refuse()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    after = path.lstat()
    if (before.st_dev, before.st_ino, before.st_mode, before.st_size,
            before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_mode,
            after.st_size, after.st_mtime_ns):
        refuse()
    return digest


try:
    binding = json.loads(sys.argv[1])
    if set(binding) != {"schema_version", "source_rows", "pytest_origin",
                        "pytest_sha256"}:
        refuse()
    if binding["schema_version"] != "mastermind.cap_s1_pytest_child_binding/v1":
        refuse()
    root = pathlib.Path(os.getcwd()).resolve(strict=True)
    root_state = pathlib.Path(os.getcwd()).lstat()
    if not stat.S_ISDIR(root_state.st_mode) or stat.S_ISLNK(root_state.st_mode):
        refuse()
    rows = binding["source_rows"]
    if not isinstance(rows, list) or not rows:
        refuse()
    expected = {}
    for row in rows:
        if (not isinstance(row, list) or len(row) != 3
                or not all(isinstance(value, str) for value in row)):
            refuse()
        module_name, relative, digest = row
        relative_path = pathlib.PurePosixPath(relative)
        if (not module_name or relative_path.is_absolute() or ".." in relative_path.parts
                or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest)
                or module_name in expected):
            refuse()
        path = (root / relative).resolve(strict=True)
        if path.parent != root and root not in path.parents:
            refuse()
        if stable_sha256(path, 64 * 1024 * 1024) != digest:
            refuse()
        expected[module_name] = (path, digest)
    sys.path.insert(0, str(root))
    for module_name, (expected_path, expected_digest) in expected.items():
        module = importlib.import_module(module_name)
        origin = pathlib.Path(module.__file__).resolve(strict=True)
        if origin != expected_path or stable_sha256(origin, 64 * 1024 * 1024) != expected_digest:
            refuse()
    pytest = importlib.import_module("pytest")
    pytest_origin = pathlib.Path(pytest.__file__).resolve(strict=True)
    expected_pytest = pathlib.Path(binding["pytest_origin"]).resolve(strict=True)
    if (pytest_origin != expected_pytest
            or stable_sha256(pytest_origin, 16 * 1024 * 1024)
            != binding["pytest_sha256"]):
        refuse()
except BaseException:
    refuse()

sys.argv = ["pytest", *sys.argv[2:]]
raise SystemExit(pytest.main())
'''
_CAP_S1_GIT_ENVIRONMENT = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_TERMINAL_PROMPT": "0",
}
CAP_S1_OBSERVER_ENVIRONMENT_KEYS = (
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_NOSYSTEM",
    "GIT_NO_LAZY_FETCH",
    "GIT_OPTIONAL_LOCKS",
    "GIT_TERMINAL_PROMPT",
    "LANG",
    "LC_ALL",
    "OHF_FAKE_STATE",
    "PATH",
    "PYTEST_ADDOPTS",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
    "TMPDIR",
)
CAP_S1_GITLEAKS_VERSION = "8.30.1"
CAP_S1_GITLEAKS_SOURCE_COMMIT = "83d9cd684c87d95d656c1458ef04895a7f1cbd8e"
CAP_S1_GITLEAKS_ARCHIVE_NAME = "gitleaks_8.30.1_darwin_arm64.tar.gz"
CAP_S1_GITLEAKS_ARCHIVE_URL = (
    "https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/"
    "gitleaks_8.30.1_darwin_arm64.tar.gz"
)
CAP_S1_GITLEAKS_ARCHIVE_BYTES = 7_897_593
CAP_S1_GITLEAKS_ARCHIVE_SHA256 = (
    "b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5"
)
CAP_S1_GITLEAKS_CHECKSUM_URL = (
    "https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/"
    "gitleaks_8.30.1_checksums.txt"
)
CAP_S1_GITLEAKS_CHECKSUM_BYTES = 999
CAP_S1_GITLEAKS_CHECKSUM_SHA256 = (
    "061476c21adaf5441516f96f185c1a4706a83cd6329b9b38762271b3d4a52fae"
)
CAP_S1_GITLEAKS_RELEASE_ASSET_ROUTES = (
    (
        CAP_S1_GITLEAKS_ARCHIVE_URL,
        "https://release-assets.githubusercontent.com"
        "/github-production-release-asset/119190187/8000249c-b97a-4d5e-9f00-3901dd94c7cc",
        378332059,
    ),
    (
        CAP_S1_GITLEAKS_CHECKSUM_URL,
        "https://release-assets.githubusercontent.com"
        "/github-production-release-asset/119190187/b99b0689-ddf4-4162-9ddb-184c0ef8282e",
        378333193,
    ),
)
CAP_S1_GITLEAKS_RULE_URL = (
    "https://raw.githubusercontent.com/gitleaks/gitleaks/"
    f"{CAP_S1_GITLEAKS_SOURCE_COMMIT}/config/gitleaks.toml"
)
CAP_S1_GITLEAKS_RULE_BYTES = 97_731
CAP_S1_GITLEAKS_RULE_SHA256 = (
    "e163e53b9e7e8a8511e77271e2b323ed057759542a6d988258afe3a1fa329caf"
)
CAP_S1_GITLEAKS_RULE_COUNT = 222
CAP_S1_GITLEAKS_ARCHIVE_MEMBERS = ("LICENSE", "README.md", "gitleaks")
CAP_S1_GITLEAKS_BINARY_MEMBER = "gitleaks"
CAP_S1_OBSERVER_SECRET_SCAN_STATE = (
    "POLICY_ACCEPTED/BINARY_HASH_UNOBSERVED/VERSION_UNOBSERVED/SCAN_UNRUN/"
    "EVIDENCE_UNAVAILABLE_HOLD"
)
CAP_S1_SECRET_CONTROL_RECIPES = (
    (
        "private-key",
        ((b"control = \"private-key\"\n", 1), (b"-----BE", 1),
         (b"GIN PRIVATE KEY-----\n", 1),
         (b"QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo=\n", 2),
         (b"-----EN", 1), (b"D PRIVATE KEY-----\n", 1)),
        1,
        "f61c28869e36438cc88c7e7f3ba2d33a3669c1ed5292f3f3aceb88424660a3de",
    ),
    (
        "slack-bot-token",
        ((b"control = \"slack-bot-token\"\nslack_bot = \"", 1),
         (b"xoxb-", 1), (b"123456789012-", 2), (b"A", 24), (b"\"\n", 1)),
        1,
        "d017fd4bc360266440d4ca1b59c5adbaa40e50196e26e74b3467c3b5ce9f1044",
    ),
    (
        "stripe-access-token",
        ((b"control = \"stripe-access-token\"\nstripe_key = \"", 1),
         (b"sk_", 1), (b"test_", 1), (b"0123456789", 1),
         (b"AbCdEfGhIjKlMnOpQrStUv", 1), (b"\"\n", 1)),
        1,
        "b509d16f630903ed3e9aff4c53d4d92761f58c69661b6a2884b2793cc0e7db1e",
    ),
)
CAP_S1_SECRET_SCAN_TEST_NODES = (
    "test_cap_s1_secret_scan_policy_registry_is_exact_and_unobserved",
    "test_cap_s1_secret_control_recipes_assemble_only_in_owned_scratch",
    "test_cap_s1_secret_archive_member_policy_rejects_hostile_members",
    "test_cap_s1_secret_report_parser_requires_complete_clean_evidence",
    "test_cap_s1_secret_report_parser_preserves_findings_and_rejects_forgery",
    "test_cap_s1_secret_source_stage_is_immutable_complete_and_bounded",
)
_CAP_S1_OBSERVER_MAX_OUTPUT_BYTES = 4 * 1024 * 1024
_CAP_S1_OBSERVER_MAX_JUNIT_BYTES = 16 * 1024 * 1024
_CAP_S1_OBSERVER_MAX_TREE_BYTES = 16 * 1024 * 1024
_CAP_S1_OBSERVER_MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
_CAP_S1_SECRET_MAX_STREAM_BYTES = 16 * 1024 * 1024
_CAP_S1_SECRET_MAX_FILE_BYTES = 2 * 1024 * 1024
_CAP_S1_SECRET_MAX_CLOSURE_BYTES = 10 * 1024 * 1024
RESULT_HELD_NON_GOALS = (
    "NO_CAP_PROMOTE1",
    "NO_DEFAULT_V4_PROMOTION",
    "NO_MAT_S1_RUNTIMEBINDING_WAKE",
    "NO_READY_OR_MERGE",
    "PRODUCTION_UNARMED",
)

_RESULT_HEX40_RE = re.compile(r"[0-9a-f]{40}")
_RESULT_HEX64_RE = re.compile(r"[0-9a-f]{64}")

_PROVIDER_ATTEMPT_HOLD_CODES = frozenset(FROZEN_STOP_CODES) | {"GATES_NOT_GREEN"}


class CapS1ResultError(ValueError):
    """Bounded, non-echoing refusal for the closed CAP-S1 result contract.

    Never echoes the caller-supplied value that failed validation -- only a
    fixed, closed reason token -- mirroring ``CanaryStop``'s own discipline.
    """


@dataclasses.dataclass(frozen=True, kw_only=True)
class CapS1PackageIdentitiesReceipt:
    exact_head: str
    exact_tree: str
    package_content_digest: str
    package_source_digest: str
    package_generation_digest: str
    closures: tuple[tuple[str, str], ...]


@dataclasses.dataclass(frozen=True, kw_only=True)
class CapS1ProviderAttemptReceipt:
    state: str
    attempt_id: str
    attempt_operation: str
    candidate_head: str
    candidate_tree: str
    disposition: str
    hold_code: "str | None" = None


@dataclasses.dataclass(frozen=True, kw_only=True)
class CapS1LocalProofReceipt:
    exact_head: str
    exact_tree: str
    protected_join: str
    provider_attempt_id: str
    suite_count: int
    total: int
    passed: int
    skipped: int
    failed: int
    cancelled: int
    suite_manifest: tuple[tuple[str, int, int, int, int], ...]
    evidence_digest: str


@dataclasses.dataclass(frozen=True, kw_only=True)
class CapS1HostedProofReceipt:
    exact_head: str
    exact_tree: str
    protected_join: str
    provider_attempt_id: str
    run_id: str
    status: str
    conclusion: str
    jobs_total: int
    jobs_passed: int
    jobs_failed: int
    jobs_cancelled: int
    job_manifest: tuple[tuple[str, str, str, str], ...]
    evidence_digest: str


@dataclasses.dataclass(frozen=True, kw_only=True)
class CapS1SecurityProofReceipt:
    exact_head: str
    exact_tree: str
    protected_join: str
    provider_attempt_id: str
    status: str
    tool_count: int
    findings: int
    failures: int
    cancelled: int
    tool_manifest: tuple[tuple[str, str, int, str], ...]
    evidence_digest: str


@dataclasses.dataclass(frozen=True, kw_only=True)
class CapS1MutationProofReceipt:
    exact_head: str
    exact_tree: str
    protected_join: str
    provider_attempt_id: str
    status: str
    total: int
    killed: int
    survived: int
    skipped: int
    errors: int
    cancelled: int
    mutation_manifest: tuple[tuple[str, str, str], ...]
    evidence_digest: str


@dataclasses.dataclass(frozen=True, kw_only=True)
class CapS1CleanupProofReceipt:
    exact_head: str
    exact_tree: str
    protected_join: str
    provider_attempt_id: str
    status: str
    all_removed: bool
    resources_total: int
    failures: int
    residue_count: int
    resource_kinds: tuple[str, ...]
    resource_manifest: tuple[tuple[str, str, bool, bool], ...]
    evidence_digest: str


@dataclasses.dataclass(frozen=True, kw_only=True)
class CapS1ReviewReceipt:
    exact_head: str
    exact_tree: str
    protected_join: str
    provider_attempt_id: str
    author: str
    author_id: int
    reviewer: str
    reviewer_id: int
    review_id: str
    state: str
    review_commit: str
    evidence_digest: str


CAP_S1_PRODUCER_EVIDENCE_SCHEMA = "mastermind.cap_s1_producer_evidence/v1"
_RESULT_MAX_PRODUCER_EVIDENCE_BYTES = 1024 * 1024


def _strict_json_loads(payload: "str | bytes", *, error: str) -> Any:
    """Parse JSON while refusing duplicate keys and non-JSON constants.

    ``json.loads`` otherwise keeps the last duplicate member.  At an evidence
    boundary that would let a displayed preimage and the value actually used by
    validation disagree.  The public error is intentionally fixed/non-echoing.
    """

    def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate json member")
            result[key] = value
        return result

    def _constant(_value: str) -> None:
        raise ValueError("non-json numeric constant")

    try:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        return json.loads(
            payload,
            object_pairs_hook=_pairs,
            parse_constant=_constant,
        )
    except (UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise CapS1ResultError(error) from exc


@dataclasses.dataclass(frozen=True, kw_only=True)
class CapS1ProducerEvidence:
    """Immutable same-invocation observation summary.

    Production constructs this only from the source-owned observer.  The
    read-only file loader below is retained solely for structural fixture
    tests and is unreachable from :func:`build_cap_s1_result`.  The public
    result carries only ``artifact_digest``; no caller-supplied instance is
    accepted as proof.
    """

    artifact_digest: str
    exact_head: str
    exact_tree: str
    protected_join: str
    provider_attempt_id: str
    local_suites: tuple[tuple[str, int, int, int, int], ...]
    security_tools: tuple[tuple[str, str, int, str], ...]
    mutations: tuple[tuple[str, str, str], ...]
    cleanup_resources: tuple[tuple[str, str, bool, bool], ...]


def _load_cap_s1_producer_evidence(
    path: "str | os.PathLike[str] | None",
) -> CapS1ProducerEvidence:
    """Fixture-only loader for structural hostile-result tests.

    Production never calls this loader.  Fixtures still require a stable,
    read-only regular file so the legacy contract tests cannot pass through a
    symlink, mutable file or duplicate-key JSON document.
    """

    error = "cap_s1_result_producer_evidence_invalid"
    try:
        if path is None:
            raise ValueError("missing producer evidence")
        evidence_path = Path(path)
        before = evidence_path.lstat()
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(evidence_path, flags)
        try:
            opened = os.fstat(descriptor)
            identity = (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
            )
            if (
                stat.S_ISLNK(before.st_mode)
                or not stat.S_ISREG(opened.st_mode)
                or before.st_dev != opened.st_dev
                or before.st_ino != opened.st_ino
                or opened.st_mode & 0o222
                or not (0 < opened.st_size <= _RESULT_MAX_PRODUCER_EVIDENCE_BYTES)
            ):
                raise ValueError("unsafe producer evidence")
            chunks: list[bytes] = []
            remaining = opened.st_size + 1
            while remaining > 0:
                chunk = os.read(descriptor, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        payload_bytes = b"".join(chunks)
        if (
            len(payload_bytes) != opened.st_size
            or identity
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        ):
            raise ValueError("producer evidence changed")

        raw = _strict_json_loads(
            payload_bytes,
            error="cap_s1_result_producer_evidence_invalid",
        )
        keys = {
            "schema_version",
            "exact_head",
            "exact_tree",
            "protected_join",
            "provider_attempt_id",
            "local_suites",
            "security_tools",
            "mutations",
            "cleanup_resources",
        }
        if type(raw) is not dict or set(raw) != keys:
            raise ValueError("producer evidence shape")
        if raw["schema_version"] != CAP_S1_PRODUCER_EVIDENCE_SCHEMA:
            raise ValueError("producer evidence schema")

        local_suites: list[tuple[str, int, int, int, int]] = []
        if type(raw["local_suites"]) is not list:
            raise ValueError("local producer shape")
        for row in raw["local_suites"]:
            if type(row) is not dict or set(row) != {
                "suite_id",
                "passed",
                "skipped",
                "failed",
                "cancelled",
            }:
                raise ValueError("local producer row")
            local_suites.append(
                (
                    row["suite_id"],
                    row["passed"],
                    row["skipped"],
                    row["failed"],
                    row["cancelled"],
                )
            )

        security_tools: list[tuple[str, str, int, str]] = []
        if type(raw["security_tools"]) is not list:
            raise ValueError("security producer shape")
        for row in raw["security_tools"]:
            if (
                type(row) is not dict
                or set(row) != {"tool_id", "status", "findings", "evidence"}
                or type(row["evidence"]) is not dict
                or not row["evidence"]
            ):
                raise ValueError("security producer row")
            security_tools.append(
                (
                    row["tool_id"],
                    row["status"],
                    row["findings"],
                    _canonical_digest(row["evidence"]),
                )
            )

        mutations: list[tuple[str, str, str]] = []
        if type(raw["mutations"]) is not list:
            raise ValueError("mutation producer shape")
        for row in raw["mutations"]:
            if (
                type(row) is not dict
                or set(row) != {"mutation_id", "state", "evidence"}
                or type(row["evidence"]) is not dict
                or not row["evidence"]
            ):
                raise ValueError("mutation producer row")
            mutations.append(
                (
                    row["mutation_id"],
                    row["state"],
                    _canonical_digest(row["evidence"]),
                )
            )

        cleanup_resources: list[tuple[str, str, bool, bool]] = []
        if type(raw["cleanup_resources"]) is not list:
            raise ValueError("cleanup producer shape")
        for row in raw["cleanup_resources"]:
            if (
                type(row) is not dict
                or set(row)
                != {"kind", "identity", "removed", "verified_absent"}
                or type(row["identity"]) is not dict
                or not row["identity"]
            ):
                raise ValueError("cleanup producer row")
            cleanup_resources.append(
                (
                    row["kind"],
                    _canonical_digest(row["identity"]),
                    row["removed"],
                    row["verified_absent"],
                )
            )
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise CapS1ResultError(error) from exc

    return CapS1ProducerEvidence(
        artifact_digest=hashlib.sha256(payload_bytes).hexdigest(),
        exact_head=raw["exact_head"],
        exact_tree=raw["exact_tree"],
        protected_join=raw["protected_join"],
        provider_attempt_id=raw["provider_attempt_id"],
        local_suites=tuple(local_suites),
        security_tools=tuple(security_tools),
        mutations=tuple(mutations),
        cleanup_resources=tuple(cleanup_resources),
    )


@dataclasses.dataclass(frozen=True, kw_only=True)
class CapS1Result:
    """The closed ``mastermind.cap_s1_result/v1`` contract.

    Construct only via :func:`build_cap_s1_result`, which validates before
    ever returning an instance -- a bare ``CapS1Result(...)`` call is a valid
    Python object but is never itself proof the contract holds; only a value
    that has passed :func:`validate_cap_s1_result` may be trusted downstream.
    """

    schema_version: str
    marker: str
    operation: str
    receiver: str
    carrier: str
    exact_head: str
    exact_tree: str
    current_protected_join: str
    producer_evidence_digest: str
    release_state: str
    changed_path_census: tuple[str, ...]
    package_identities: CapS1PackageIdentitiesReceipt
    canary_evidence: "CapS1CanaryResultEvidence | None"
    provider_attempt: CapS1ProviderAttemptReceipt
    local_proof: CapS1LocalProofReceipt
    hosted_proof: CapS1HostedProofReceipt
    security_proof: CapS1SecurityProofReceipt
    mutation_proof: CapS1MutationProofReceipt
    cleanup_proof: CapS1CleanupProofReceipt
    review_state: CapS1ReviewReceipt
    held_non_goals: tuple[str, ...]


def _result_is_hex40(value: object) -> bool:
    return isinstance(value, str) and _RESULT_HEX40_RE.fullmatch(value) is not None


def _result_is_hex64(value: object) -> bool:
    return isinstance(value, str) and _RESULT_HEX64_RE.fullmatch(value) is not None


_RESULT_SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}")
_RESULT_OPERATION_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_RESULT_RECEIVER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_RESULT_SLACK_CARRIER_RE = re.compile(
    r"(?:C|D|G)[A-Z0-9]{8,19}/[0-9]{10,16}\.[0-9]{6}"
)
_RESULT_SENSITIVE_MARKERS = (
    "secret",
    "token",
    "password",
    "api_key",
    "authorization",
    "bearer",
)
_RESULT_CLEANUP_KINDS = (
    "attempt",
    "origin",
    "process",
    "projection",
    "schema",
    "thread",
    "workspace",
)
_RESULT_OBSERVER_CLEANUP_KINDS = (
    "observer-mutants",
    "observer-output",
    "observer-processes",
    "observer-scratch",
    "observer-source",
    "secret-controls",
    "secret-output",
    "secret-source",
    "secret-supply",
)
_RESULT_ALL_CLEANUP_KINDS = tuple(
    sorted((*_RESULT_CLEANUP_KINDS, *_RESULT_OBSERVER_CLEANUP_KINDS))
)
_RESULT_MAX_LOCAL_TESTS = 100_000
_RESULT_MAX_HOSTED_JOBS = 256
_RESULT_MAX_SECURITY_TOOLS = 64
_RESULT_MAX_MUTATIONS = 100_000
_RESULT_REPOSITORY = "mastermindx-market-intelligence/Mastermind"
_RESULT_PR_NUMBER = 350
_CAP_S1_PR_BRANCH = "fable/cap-s1-complete-vertical-20260901"
_CAP_S1_PR_HEAD_REF = f"refs/pull/{_RESULT_PR_NUMBER}/head"
_CAP_S1_CODEQL_APP = (15368, "github-actions")
_CAP_S1_CODEQL_CHECKS = (
    ("actions", "Analyze (actions)"),
    ("javascript-typescript", "Analyze (javascript-typescript)"),
    ("python", "Analyze (python)"),
)
_CAP_S1_CODEQL_ANALYSIS_KEY = "dynamic/github-code-scanning/codeql:analyze"


def _result_safe_identifier(value: object) -> bool:
    return (
        isinstance(value, str)
        and _RESULT_SAFE_ID_RE.fullmatch(value) is not None
        and not any(marker in value.lower() for marker in _RESULT_SENSITIVE_MARKERS)
    )


def _result_valid_local_scope(value: object) -> bool:
    """Accept only one exact source-owned pytest module path."""

    return type(value) is str and value in CAP_S1_OBSERVER_TEST_MODULES


def _result_safe_operation(value: object) -> bool:
    return (
        isinstance(value, str)
        and _RESULT_OPERATION_RE.fullmatch(value) is not None
        and not any(marker in value.lower() for marker in _RESULT_SENSITIVE_MARKERS)
    )


def _result_safe_receiver(value: object) -> bool:
    return (
        isinstance(value, str)
        and _RESULT_RECEIVER_RE.fullmatch(value) is not None
        and not any(marker in value.lower() for marker in _RESULT_SENSITIVE_MARKERS)
    )


def _result_safe_slack_carrier(value: object) -> bool:
    return isinstance(value, str) and _RESULT_SLACK_CARRIER_RE.fullmatch(value) is not None


def _result_safe_manifest_label(value: object) -> bool:
    if not isinstance(value, str) or not (1 <= len(value.encode("utf-8")) <= 128):
        return False
    if not value.isascii() or any(ord(character) < 32 for character in value):
        return False
    lowered = value.lower()
    return (
        "http://" not in lowered
        and "https://" not in lowered
        and "?" not in value
        and "\\" not in value
        and not value.startswith(("/", ".", "~"))
        and "../" not in value
    )


def _result_positive_int(value: object, *, maximum: int = 2**63 - 1) -> bool:
    return type(value) is int and 0 < value <= maximum


def _github_api_json(
    endpoint: str,
    *,
    cleanup_observations: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
) -> Any:
    """Fresh, bounded GitHub read used to authenticate hosted/review proof.

    The endpoint is constructed only from closed contract constants and
    already-validated decimal IDs.  Tests replace this one read seam with
    deterministic API-shaped fixtures; production has no caller-supplied
    callback that could bless its own claims.
    """

    try:
        completed = _run_cap_s1_observer_process(
            ("gh", "api", endpoint),
            cwd=REPO_ROOT,
            timeout=30,
            cleanup_observations=cleanup_observations,
            github_environment=True,
        )
        if completed.returncode != 0 or completed.stderr:
            raise CapS1ResultError("cap_s1_result_github_evidence_unavailable")
        payload = _strict_json_loads(
            completed.stdout,
            error="cap_s1_result_github_evidence_unavailable",
        )
    except (OSError, subprocess.SubprocessError, CapS1ResultError) as exc:
        raise CapS1ResultError("cap_s1_result_github_evidence_unavailable") from exc
    if type(payload) is not dict:
        raise CapS1ResultError("cap_s1_result_github_evidence_unavailable")
    return payload


def _rederive_hosted_job_manifest(
    *,
    run_id: str,
    exact_head: str,
    process_cleanup: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
) -> tuple[dict[str, Any], tuple[tuple[str, str, str, str], ...]]:
    def _get(endpoint: str) -> Any:
        if process_cleanup is None:
            return _github_api_json(endpoint)
        return _github_api_json(endpoint, cleanup_observations=process_cleanup)

    run = _get(f"repos/{_RESULT_REPOSITORY}/actions/runs/{run_id}")
    if str(run.get("id")) != run_id or run.get("head_sha") != exact_head:
        raise CapS1ResultError("cap_s1_result_hosted_proof_invalid")

    rows: list[tuple[str, str, str, str]] = []
    expected_total: "int | None" = None
    for page in range(1, 5):
        payload = _get(
            f"repos/{_RESULT_REPOSITORY}/actions/runs/{run_id}/jobs?per_page=100&page={page}"
        )
        total = payload.get("total_count")
        jobs = payload.get("jobs")
        if (
            not _result_nonnegative_int(total)
            or total > _RESULT_MAX_HOSTED_JOBS
            or type(jobs) is not list
        ):
            raise CapS1ResultError("cap_s1_result_hosted_proof_invalid")
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise CapS1ResultError("cap_s1_result_hosted_proof_invalid")
        for job in jobs:
            if type(job) is not dict:
                raise CapS1ResultError("cap_s1_result_hosted_proof_invalid")
            job_id = str(job.get("id", ""))
            name = job.get("name")
            status = str(job.get("status", "")).upper()
            conclusion = str(job.get("conclusion", "")).upper()
            if (
                not job_id.isascii()
                or not job_id.isdigit()
                or len(job_id) > 20
                or not _result_safe_manifest_label(name)
            ):
                raise CapS1ResultError("cap_s1_result_hosted_proof_invalid")
            rows.append((job_id, name, status, conclusion))
        if len(rows) >= expected_total:
            break
    if expected_total is None or len(rows) != expected_total:
        raise CapS1ResultError("cap_s1_result_hosted_proof_invalid")
    ordered = tuple(sorted(rows))
    if len(set(row[0] for row in ordered)) != len(ordered):
        raise CapS1ResultError("cap_s1_result_hosted_proof_invalid")
    return run, ordered


def _rederive_github_review(
    *,
    review_id: str,
    exact_head: str,
    process_cleanup: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    def _get(endpoint: str) -> Any:
        if process_cleanup is None:
            return _github_api_json(endpoint)
        return _github_api_json(endpoint, cleanup_observations=process_cleanup)

    pull = _get(f"repos/{_RESULT_REPOSITORY}/pulls/{_RESULT_PR_NUMBER}")
    review = _get(
        f"repos/{_RESULT_REPOSITORY}/pulls/{_RESULT_PR_NUMBER}/reviews/{review_id}"
    )
    head = pull.get("head")
    if (
        type(head) is not dict
        or head.get("sha") != exact_head
        or str(review.get("id")) != review_id
        or review.get("commit_id") != exact_head
    ):
        raise CapS1ResultError("cap_s1_result_review_state_invalid")
    return pull, review


def _result_safe_artifact_inventory_row(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 1024:
        return False
    if value.startswith("projection:file_count="):
        count = value.removeprefix("projection:file_count=")
        return count.isascii() and count.isdigit() and 0 < int(count) <= 64
    prefix, separator, relative = value.partition(":")
    if prefix not in {"schema", "workspace"} or separator != ":" or not relative:
        return False
    if relative.startswith(("/", "\\")) or "\\" in relative:
        return False
    if re.fullmatch(r"[A-Za-z0-9._/-]+", relative) is None:
        return False
    parts = relative.split("/")
    if not all(part not in {"", ".", ".."} for part in parts):
        return False
    sensitive_segment = re.compile(
        r"(?:^|[._-])(?:secret|password|api_key|auth|authorization|bearer|token|"
        r"credential|credentials)(?:$|[=._-])",
        re.IGNORECASE,
    )
    return not any(sensitive_segment.search(part) for part in parts)


def _result_closed_mapping(
    raw: object, *, keys: set[str], error: str
) -> dict[str, Any]:
    if type(raw) is not dict or set(raw) != keys:
        raise CapS1ResultError(error)
    return raw


def _result_nonnegative_int(value: object) -> bool:
    return type(value) is int and value >= 0


def _result_receipt_evidence_digest(receipt: object) -> str:
    """Digest the complete typed observation, never a caller-selected label."""

    if not dataclasses.is_dataclass(receipt):
        raise TypeError("receipt must be a dataclass instance")
    payload = dataclasses.asdict(receipt)
    payload.pop("evidence_digest", None)
    return _canonical_digest(
        {"receipt_type": type(receipt).__name__, "observation": payload}
    )


def _parse_package_identities(raw: object) -> CapS1PackageIdentitiesReceipt:
    values = _result_closed_mapping(
        raw,
        keys={
            "exact_head",
            "exact_tree",
            "package_content_digest",
            "package_source_digest",
            "package_generation_digest",
            "closures",
        },
        error="cap_s1_result_package_identities_invalid",
    )
    closures = values["closures"]
    if type(closures) is not dict or len(closures) != 4:
        raise CapS1ResultError("cap_s1_result_package_identities_invalid")
    closure_rows = tuple(sorted(closures.items()))
    if not all(
        _result_safe_identifier(name) and _result_is_hex64(digest)
        for name, digest in closure_rows
    ):
        raise CapS1ResultError("cap_s1_result_package_identities_digest_invalid")
    return CapS1PackageIdentitiesReceipt(
        exact_head=values["exact_head"],
        exact_tree=values["exact_tree"],
        package_content_digest=values["package_content_digest"],
        package_source_digest=values["package_source_digest"],
        package_generation_digest=values["package_generation_digest"],
        closures=closure_rows,
    )


def _parse_provider_attempt(raw: object) -> CapS1ProviderAttemptReceipt:
    if type(raw) is not dict:
        raise CapS1ResultError("cap_s1_result_provider_attempt_invalid")
    state = raw.get("state")
    common = {
        "state",
        "attempt_id",
        "attempt_operation",
        "candidate_head",
        "candidate_tree",
        "disposition",
    }
    if state == "HOLD":
        values = _result_closed_mapping(
            raw,
            keys=common | {"hold_code"},
            error="cap_s1_result_provider_attempt_invalid",
        )
    elif state == "COMPLETED":
        values = _result_closed_mapping(
            raw,
            keys=common,
            error="cap_s1_result_provider_attempt_invalid",
        )
    else:
        raise CapS1ResultError("cap_s1_result_provider_attempt_state_invalid")
    return CapS1ProviderAttemptReceipt(
        state=state,
        attempt_id=values["attempt_id"],
        attempt_operation=values["attempt_operation"],
        candidate_head=values["candidate_head"],
        candidate_tree=values["candidate_tree"],
        disposition=values["disposition"],
        hold_code=values.get("hold_code"),
    )


def _parse_bound_receipt(
    raw: object,
    *,
    cls: type,
    extra_keys: set[str],
    error: str,
    nested_tuple_fields: tuple[str, ...] = (),
    tuple_fields: tuple[str, ...] = (),
) -> Any:
    common = {"exact_head", "exact_tree", "protected_join", "provider_attempt_id"}
    values = dict(_result_closed_mapping(raw, keys=common | extra_keys, error=error))
    for field_name in tuple_fields:
        value = values.get(field_name)
        if type(value) is list:
            values[field_name] = tuple(value)
    for field_name in nested_tuple_fields:
        value = values.get(field_name)
        if type(value) in (list, tuple):
            values[field_name] = tuple(
                tuple(row) if type(row) in (list, tuple) else row for row in value
            )
    return cls(**values)


def _validate_canary_evidence(
    evidence: CapS1CanaryResultEvidence,
    *,
    head: str,
    tree: str,
    protected_join: str,
    attempt_id: str,
) -> None:
    if type(evidence) is not CapS1CanaryResultEvidence:
        raise CapS1ResultError("cap_s1_result_canary_evidence_type_invalid")
    if evidence.schema_version != CANARY_EVIDENCE_SCHEMA_VERSION:
        raise CapS1ResultError("cap_s1_result_canary_evidence_schema_mismatch")
    if (
        evidence.candidate_commit != head
        or evidence.candidate_tree != tree
        or not _result_safe_identifier(evidence.canary_operation_id)
        or evidence.provider_attempt_id != attempt_id
        or evidence.protected_join != protected_join
    ):
        raise CapS1ResultError("cap_s1_result_canary_evidence_binding_mismatch")
    digest_fields = (
        evidence.workspace_identity_digest,
        evidence.v4_policy_digest,
        evidence.package_source_digest,
        evidence.package_generation_digest,
        evidence.projection_receipt_digest,
        evidence.binary_digest,
        evidence.skills_list_raw_shape_digest,
        evidence.protocol_receipt_digest,
        evidence.skills_identity_digest,
    )
    digest_fields = (*digest_fields, evidence.app_server_config_digest)
    if not all(_result_is_hex64(value) for value in digest_fields):
        raise CapS1ResultError("cap_s1_result_canary_evidence_digest_invalid")
    expected_skill_names = (
        "escalate-decision",
        "finish-operation",
        "receive-commission",
        "return-progress",
    )
    for rows in (evidence.skill_grant_digests, evidence.skill_closure_digests):
        if (
            type(rows) is not tuple
            or len(rows) != 4
            or tuple(sorted(rows)) != rows
            or not all(
                type(row) is tuple
                and len(row) == 2
                and _result_safe_identifier(row[0])
                and _result_is_hex64(row[1])
                for row in rows
            )
            or tuple(row[0] for row in rows) != expected_skill_names
        ):
            raise CapS1ResultError("cap_s1_result_canary_evidence_digest_invalid")
    expected_workspace_identity = _canonical_digest(
        {
            "identity_type": "cap-s1-synthetic-workspace/v1",
            "candidate_commit": evidence.candidate_commit,
            "candidate_tree": evidence.candidate_tree,
            "canary_operation_id": evidence.canary_operation_id,
            "provider_attempt_id": evidence.provider_attempt_id,
        }
    )
    expected_skills_identity = _canonical_digest(
        {
            "identity_type": "cap-s1-skill-projection/v1",
            "package_source_digest": evidence.package_source_digest,
            "package_generation_digest": evidence.package_generation_digest,
            "projection_receipt_digest": evidence.projection_receipt_digest,
            "provider_attempt_id": evidence.provider_attempt_id,
        }
    )
    if (
        evidence.workspace_identity_digest != expected_workspace_identity
        or evidence.skills_identity_digest != expected_skills_identity
        or not _result_safe_identifier(evidence.process_generation)
        or not isinstance(evidence.binary_version, str)
        or not evidence.binary_version.strip()
        or evidence.origin_mode != ORIGIN_VERIFIED_EPHEMERAL_GIT_ARCHIVE
        or evidence.origin_authentication != "ephemeral-git-archive"
        or evidence.launch_decision != "ALLOW"
        or not isinstance(evidence.served_model, str)
        or not evidence.served_model.strip()
        or evidence.terminal_process_state != "PROVEN_DEAD"
        or evidence.extra_roots_set_outcomes != ("cleared",)
        or evidence.baseline_enabled_names != expected_skill_names
        or evidence.after_add_enabled_names != expected_skill_names
        or evidence.observed_enabled_names != expected_skill_names
        or evidence.after_clear_enabled_names != ()
        or type(evidence.artifact_inventory) is not tuple
        or not evidence.artifact_inventory
        or not all(_result_safe_artifact_inventory_row(row) for row in evidence.artifact_inventory)
    ):
        raise CapS1ResultError("cap_s1_result_canary_evidence_invalid")
    expected_markers = (
        "receive-commission",
        "return-progress",
        "escalate-decision",
        "finish-operation",
    )
    if evidence.turn_marker_results != tuple((name, True) for name in expected_markers):
        raise CapS1ResultError("cap_s1_result_canary_evidence_markers_invalid")
    if (
        type(evidence.cleanup) is not CanaryCleanupRecord
        or evidence.cleanup.schema_version != CANARY_CLEANUP_SCHEMA_VERSION
        or not evidence.cleanup.all_removed
        or tuple(sorted(kind for kind, _removed, _absent in evidence.cleanup.artifacts))
        != _RESULT_CLEANUP_KINDS
    ):
        raise CapS1ResultError("cap_s1_result_canary_evidence_cleanup_invalid")


def _validate_cap_s1_result_against_producer(
    result: CapS1Result,
    *,
    producer_evidence: CapS1ProducerEvidence,
    github_observations: "_CapS1GitHubObservations | None" = None,
) -> None:
    """Refuse anything not conforming to the closed
    ``mastermind.cap_s1_result/v1`` contract. Every refusal is a fixed,
    bounded, non-echoing reason string."""

    if type(result) is not CapS1Result:
        raise CapS1ResultError("cap_s1_result_type_invalid")
    if result.schema_version != RESULT_CONTRACT_SCHEMA:
        raise CapS1ResultError("cap_s1_result_schema_mismatch")
    if result.marker != RESULT_CONTRACT_MARKER:
        raise CapS1ResultError("cap_s1_result_marker_mismatch")
    if result.release_state != RESULT_RELEASE_STATE:
        raise CapS1ResultError("cap_s1_result_release_state_invalid")

    identity_validators = {
        "operation": _result_safe_operation,
        "receiver": _result_safe_receiver,
        "carrier": _result_safe_slack_carrier,
    }
    for field_name, validator in identity_validators.items():
        if not validator(getattr(result, field_name)):
            raise CapS1ResultError(f"cap_s1_result_{field_name}_invalid")

    for field_name in ("exact_head", "exact_tree", "current_protected_join"):
        if not _result_is_hex40(getattr(result, field_name)):
            raise CapS1ResultError(f"cap_s1_result_{field_name}_invalid")
    if not _result_is_hex64(result.producer_evidence_digest):
        raise CapS1ResultError("cap_s1_result_producer_evidence_invalid")

    census = result.changed_path_census
    if not isinstance(census, tuple) or not census:
        raise CapS1ResultError("cap_s1_result_changed_path_census_empty")
    if not all(isinstance(item, str) and item for item in census):
        raise CapS1ResultError("cap_s1_result_changed_path_census_invalid")
    if len(set(census)) != len(census):
        raise CapS1ResultError("cap_s1_result_changed_path_census_duplicate")
    if list(census) != sorted(census):
        raise CapS1ResultError("cap_s1_result_changed_path_census_unsorted")
    if census != RESULT_CHANGED_PATHS:
        raise CapS1ResultError("cap_s1_result_changed_path_census_mismatch")

    subreceipts = (
        result.package_identities,
        result.provider_attempt,
        result.local_proof,
        result.hosted_proof,
        result.security_proof,
        result.mutation_proof,
        result.cleanup_proof,
        result.review_state,
    )
    expected_types = (
        CapS1PackageIdentitiesReceipt,
        CapS1ProviderAttemptReceipt,
        CapS1LocalProofReceipt,
        CapS1HostedProofReceipt,
        CapS1SecurityProofReceipt,
        CapS1MutationProofReceipt,
        CapS1CleanupProofReceipt,
        CapS1ReviewReceipt,
    )
    if any(type(receipt) is not expected for receipt, expected in zip(subreceipts, expected_types)):
        raise CapS1ResultError("cap_s1_result_subreceipt_type_invalid")

    package = result.package_identities
    if (
        package.exact_head != result.exact_head
        or package.exact_tree != result.exact_tree
        or type(package.closures) is not tuple
        or len(package.closures) != 4
        or tuple(sorted(package.closures)) != package.closures
        or not all(
            type(row) is tuple
            and len(row) == 2
            and _result_safe_identifier(row[0])
            and _result_is_hex64(row[1])
            for row in package.closures
        )
    ):
        raise CapS1ResultError("cap_s1_result_package_identities_invalid")
    if not all(
        _result_is_hex64(value)
        for value in (
            package.package_content_digest,
            package.package_source_digest,
            package.package_generation_digest,
        )
    ):
        raise CapS1ResultError("cap_s1_result_package_identities_digest_invalid")

    provider_attempt = result.provider_attempt
    if (
        not _result_safe_identifier(provider_attempt.attempt_id)
        or not _result_safe_identifier(provider_attempt.attempt_operation)
        or not _result_is_hex40(provider_attempt.candidate_head)
        or not _result_is_hex40(provider_attempt.candidate_tree)
    ):
        raise CapS1ResultError("cap_s1_result_provider_attempt_invalid")
    if provider_attempt.state == "HOLD":
        if provider_attempt.hold_code not in _PROVIDER_ATTEMPT_HOLD_CODES:
            raise CapS1ResultError("cap_s1_result_provider_attempt_hold_code_invalid")
        if provider_attempt.disposition != "CONSUMED_NOT_ACCEPTED_NO_REPLAY_NO_FAILOVER":
            raise CapS1ResultError("cap_s1_result_provider_attempt_disposition_invalid")
        if result.canary_evidence is not None:
            raise CapS1ResultError("cap_s1_result_canary_evidence_must_be_empty_on_hold")
    elif provider_attempt.state == "COMPLETED":
        if provider_attempt.hold_code is not None or provider_attempt.disposition != "ACCEPTED":
            raise CapS1ResultError("cap_s1_result_provider_attempt_disposition_invalid")
        if result.canary_evidence is None:
            raise CapS1ResultError("cap_s1_result_canary_evidence_required_on_completed")
        _validate_canary_evidence(
            result.canary_evidence,
            head=result.exact_head,
            tree=result.exact_tree,
            protected_join=result.current_protected_join,
            attempt_id=provider_attempt.attempt_id,
        )
    else:
        raise CapS1ResultError("cap_s1_result_provider_attempt_state_invalid")

    bound_receipts = (
        result.local_proof,
        result.hosted_proof,
        result.security_proof,
        result.mutation_proof,
        result.cleanup_proof,
        result.review_state,
    )
    if any(
        receipt.exact_head != result.exact_head
        or receipt.exact_tree != result.exact_tree
        or receipt.protected_join != result.current_protected_join
        or receipt.provider_attempt_id != provider_attempt.attempt_id
        for receipt in bound_receipts
    ):
        raise CapS1ResultError("cap_s1_result_cross_binding_mismatch")
    if (
        producer_evidence.artifact_digest != result.producer_evidence_digest
        or producer_evidence.exact_head != result.exact_head
        or producer_evidence.exact_tree != result.exact_tree
        or producer_evidence.protected_join != result.current_protected_join
        or producer_evidence.provider_attempt_id != provider_attempt.attempt_id
    ):
        raise CapS1ResultError("cap_s1_result_producer_evidence_invalid")
    local_proof = result.local_proof
    local_rows = local_proof.suite_manifest
    if (
        type(local_rows) is not tuple
        or len(local_rows) != len(CAP_S1_OBSERVER_TEST_MODULES)
    ):
        raise CapS1ResultError("cap_s1_result_local_proof_invalid")
    if not all(
            type(row) is tuple
            and len(row) == 5
            and _result_valid_local_scope(row[0])
            and all(_result_nonnegative_int(count) for count in row[1:])
            and sum(row[1:]) <= _RESULT_MAX_LOCAL_TESTS
            for row in local_rows
    ):
        raise CapS1ResultError("cap_s1_result_local_proof_invalid")
    if (
        tuple(sorted(local_rows)) != local_rows
        or len({row[0] for row in local_rows}) != len(local_rows)
        or tuple(row[0] for row in local_rows)
        != tuple(sorted(CAP_S1_OBSERVER_TEST_MODULES))
    ):
        raise CapS1ResultError("cap_s1_result_local_proof_invalid")
    local_passed = sum(row[1] for row in local_rows)
    local_skipped = sum(row[2] for row in local_rows)
    local_failed = sum(row[3] for row in local_rows)
    local_cancelled = sum(row[4] for row in local_rows)
    local_total = local_passed + local_skipped + local_failed + local_cancelled
    if (
        local_proof.suite_count != len(local_rows)
        or local_proof.total != local_total
        or local_proof.passed != local_passed
        or local_proof.skipped != local_skipped
        or local_proof.failed != local_failed
        or local_proof.cancelled != local_cancelled
        or not (0 < local_total <= _RESULT_MAX_LOCAL_TESTS)
        or local_passed == 0
        or local_failed != 0
        or local_cancelled != 0
    ):
        raise CapS1ResultError("cap_s1_result_local_proof_invalid")

    hosted_proof = result.hosted_proof
    if (
        not _result_safe_identifier(hosted_proof.run_id)
        or not hosted_proof.run_id.isdigit()
        or hosted_proof.status != "COMPLETED"
        or hosted_proof.conclusion != "SUCCESS"
    ):
        raise CapS1ResultError("cap_s1_result_hosted_proof_invalid")
    if github_observations is None:
        hosted_run, hosted_rows = _rederive_hosted_job_manifest(
            run_id=hosted_proof.run_id,
            exact_head=result.exact_head,
        )
    elif type(github_observations) is _CapS1GitHubObservations:
        hosted_run = github_observations.hosted_run
        hosted_rows = github_observations.hosted_rows
    else:
        raise CapS1ResultError("cap_s1_result_github_evidence_unavailable")
    hosted_passed = sum(
        status == "COMPLETED" and conclusion == "SUCCESS"
        for _job_id, _name, status, conclusion in hosted_rows
    )
    hosted_cancelled = sum(
        conclusion == "CANCELLED"
        for _job_id, _name, _status, conclusion in hosted_rows
    )
    hosted_failed = len(hosted_rows) - hosted_passed - hosted_cancelled
    if (
        str(hosted_run.get("id", "")) != hosted_proof.run_id
        or hosted_run.get("head_sha") != result.exact_head
        or str(hosted_run.get("status", "")).upper() != hosted_proof.status
        or str(hosted_run.get("conclusion", "")).upper() != hosted_proof.conclusion
        or hosted_proof.job_manifest != hosted_rows
        or hosted_proof.jobs_total != len(hosted_rows)
        or hosted_proof.jobs_passed != hosted_passed
        or hosted_proof.jobs_failed != hosted_failed
        or hosted_proof.jobs_cancelled != hosted_cancelled
        or hosted_passed == 0
        or hosted_failed != 0
        or hosted_cancelled != 0
    ):
        raise CapS1ResultError("cap_s1_result_hosted_proof_invalid")

    security_proof = result.security_proof
    security_rows = security_proof.tool_manifest
    if (
        type(security_rows) is not tuple
        or not security_rows
        or len(security_rows) > _RESULT_MAX_SECURITY_TOOLS
    ):
        raise CapS1ResultError("cap_s1_result_security_proof_invalid")
    if not all(
            type(row) is tuple
            and len(row) == 4
            and _result_safe_manifest_label(row[0])
            and row[1] in {"PASSED", "FAILED", "CANCELLED"}
            and _result_nonnegative_int(row[2])
            and _result_is_hex64(row[3])
            for row in security_rows
    ):
        raise CapS1ResultError("cap_s1_result_security_proof_invalid")
    if (
        tuple(sorted(security_rows)) != security_rows
        or len({row[0] for row in security_rows}) != len(security_rows)
    ):
        raise CapS1ResultError("cap_s1_result_security_proof_invalid")
    security_findings = sum(row[2] for row in security_rows)
    security_failures = sum(row[1] == "FAILED" for row in security_rows)
    security_cancelled = sum(row[1] == "CANCELLED" for row in security_rows)
    if (
        security_proof.status != "CLEAN"
        or security_proof.tool_count != len(security_rows)
        or security_proof.findings != security_findings
        or security_proof.failures != security_failures
        or security_proof.cancelled != security_cancelled
        or security_findings != 0
        or security_failures != 0
        or security_cancelled != 0
    ):
        raise CapS1ResultError("cap_s1_result_security_proof_invalid")

    mutation_proof = result.mutation_proof
    mutation_rows = mutation_proof.mutation_manifest
    mutation_states = {"KILLED", "SURVIVED", "SKIPPED", "ERROR", "CANCELLED"}
    if (
        type(mutation_rows) is not tuple
        or not mutation_rows
        or len(mutation_rows) > _RESULT_MAX_MUTATIONS
    ):
        raise CapS1ResultError("cap_s1_result_mutation_proof_invalid")
    if not all(
            type(row) is tuple
            and len(row) == 3
            and _result_safe_identifier(row[0])
            and row[1] in mutation_states
            and _result_is_hex64(row[2])
            for row in mutation_rows
    ):
        raise CapS1ResultError("cap_s1_result_mutation_proof_invalid")
    if (
        tuple(sorted(mutation_rows)) != mutation_rows
        or len({row[0] for row in mutation_rows}) != len(mutation_rows)
    ):
        raise CapS1ResultError("cap_s1_result_mutation_proof_invalid")
    mutation_counts = {
        state: sum(row[1] == state for row in mutation_rows)
        for state in mutation_states
    }
    if (
        mutation_proof.status != "PASSED"
        or mutation_proof.total != len(mutation_rows)
        or mutation_proof.killed != mutation_counts["KILLED"]
        or mutation_proof.survived != mutation_counts["SURVIVED"]
        or mutation_proof.skipped != mutation_counts["SKIPPED"]
        or mutation_proof.errors != mutation_counts["ERROR"]
        or mutation_proof.cancelled != mutation_counts["CANCELLED"]
        or mutation_proof.killed == 0
        or mutation_proof.survived != 0
        or mutation_proof.errors != 0
        or mutation_proof.cancelled != 0
    ):
        raise CapS1ResultError("cap_s1_result_mutation_proof_invalid")

    cleanup_proof = result.cleanup_proof
    cleanup_rows = cleanup_proof.resource_manifest
    if (
        type(cleanup_rows) is not tuple
        or len(cleanup_rows) != len(_RESULT_ALL_CLEANUP_KINDS)
    ):
        raise CapS1ResultError("cap_s1_result_cleanup_proof_invalid")
    if not all(
            type(row) is tuple
            and len(row) == 4
            and row[0] in _RESULT_ALL_CLEANUP_KINDS
            and _result_is_hex64(row[1])
            and type(row[2]) is bool
            and type(row[3]) is bool
            for row in cleanup_rows
    ):
        raise CapS1ResultError("cap_s1_result_cleanup_proof_invalid")
    if (
        tuple(sorted(cleanup_rows)) != cleanup_rows
        or tuple(row[0] for row in cleanup_rows) != _RESULT_ALL_CLEANUP_KINDS
    ):
        raise CapS1ResultError("cap_s1_result_cleanup_proof_invalid")
    cleanup_failures = sum(not row[2] for row in cleanup_rows)
    cleanup_residue = sum(not row[3] for row in cleanup_rows)
    if (
        cleanup_proof.status != "CLEAN"
        or cleanup_proof.all_removed is not True
        or cleanup_proof.resources_total != len(cleanup_rows)
        or cleanup_proof.failures != cleanup_failures
        or cleanup_proof.residue_count != cleanup_residue
        or cleanup_proof.resource_kinds != tuple(row[0] for row in cleanup_rows)
        or cleanup_failures != 0
        or cleanup_residue != 0
    ):
        raise CapS1ResultError("cap_s1_result_cleanup_proof_invalid")

    review = result.review_state
    if (
        not _result_safe_identifier(review.author)
        or not _result_positive_int(review.author_id)
        or not _result_safe_identifier(review.reviewer)
        or not _result_positive_int(review.reviewer_id)
        or review.author_id == review.reviewer_id
        or review.author.casefold() == review.reviewer.casefold()
        or not _result_safe_identifier(review.review_id)
        or not review.review_id.isdigit()
        or review.state != "APPROVED"
        or review.review_commit != result.exact_head
    ):
        raise CapS1ResultError("cap_s1_result_review_state_invalid")
    if github_observations is None:
        pull, github_review = _rederive_github_review(
            review_id=review.review_id,
            exact_head=result.exact_head,
        )
    else:
        pull = github_observations.pull
        github_review = github_observations.review
    pull_author = pull.get("user")
    pull_head = pull.get("head")
    github_reviewer = github_review.get("user")
    if (
        type(pull_author) is not dict
        or type(pull_head) is not dict
        or type(github_reviewer) is not dict
        or pull_head.get("sha") != result.exact_head
        or str(github_review.get("id", "")) != review.review_id
        or pull_author.get("login") != review.author
        or pull_author.get("id") != review.author_id
        or github_reviewer.get("login") != review.reviewer
        or github_reviewer.get("id") != review.reviewer_id
        or str(github_review.get("state", "")).upper() != review.state
        or github_review.get("commit_id") != review.review_commit
        or pull_author.get("id") == github_reviewer.get("id")
        or str(pull_author.get("login", "")).casefold()
        == str(github_reviewer.get("login", "")).casefold()
    ):
        raise CapS1ResultError("cap_s1_result_review_state_invalid")

    if any(
        not _result_is_hex64(receipt.evidence_digest)
        or receipt.evidence_digest != _result_receipt_evidence_digest(receipt)
        for receipt in bound_receipts
    ):
        raise CapS1ResultError("cap_s1_result_evidence_digest_invalid")
    if local_rows != producer_evidence.local_suites:
        raise CapS1ResultError("cap_s1_result_local_proof_invalid")
    if security_rows != producer_evidence.security_tools:
        raise CapS1ResultError("cap_s1_result_security_proof_invalid")
    if mutation_rows != producer_evidence.mutations:
        raise CapS1ResultError("cap_s1_result_mutation_proof_invalid")
    if cleanup_rows != producer_evidence.cleanup_resources:
        raise CapS1ResultError("cap_s1_result_cleanup_proof_invalid")

    held = result.held_non_goals
    if not isinstance(held, tuple) or not held:
        raise CapS1ResultError("cap_s1_result_held_non_goals_empty")
    if held != RESULT_HELD_NON_GOALS:
        raise CapS1ResultError("cap_s1_result_held_non_goals_invalid")


def _build_cap_s1_result_from_fixture(**kwargs: Any) -> CapS1Result:
    """Fixture-only assembler for structural contract tests.

    Production callers must use :func:`build_cap_s1_result`; this helper is
    intentionally private and still cross-checks every submitted family
    against the bounded fixture artifact.  It exists so unit tests can cover
    the closed result schema without invoking the production 17-module or
    mutation observer recursively.
    """

    producer_evidence_path = kwargs.pop("producer_evidence_path", None)
    producer_evidence = _load_cap_s1_producer_evidence(producer_evidence_path)
    return _assemble_cap_s1_result_from_observations(
        kwargs,
        producer_evidence=producer_evidence,
    )


def _assemble_cap_s1_result_from_observations(
    raw_kwargs: Mapping[str, Any],
    *,
    producer_evidence: CapS1ProducerEvidence,
    github_observations: "_CapS1GitHubObservations | None" = None,
) -> CapS1Result:
    """Immediate constructor used only with source-owned observations."""

    kwargs = dict(raw_kwargs)
    if "producer_evidence_digest" in kwargs:
        raise CapS1ResultError("cap_s1_result_producer_evidence_invalid")
    kwargs["producer_evidence_digest"] = producer_evidence.artifact_digest
    kwargs.setdefault("schema_version", RESULT_CONTRACT_SCHEMA)
    kwargs.setdefault("marker", RESULT_CONTRACT_MARKER)
    kwargs.setdefault("release_state", RESULT_RELEASE_STATE)
    parsers = {
        "package_identities": _parse_package_identities,
        "provider_attempt": _parse_provider_attempt,
        "local_proof": lambda raw: _parse_bound_receipt(
            raw,
            cls=CapS1LocalProofReceipt,
            extra_keys={
                "suite_count",
                "total",
                "passed",
                "skipped",
                "failed",
                "cancelled",
                "suite_manifest",
                "evidence_digest",
            },
            error="cap_s1_result_local_proof_invalid",
            nested_tuple_fields=("suite_manifest",),
        ),
        "hosted_proof": lambda raw: _parse_bound_receipt(
            raw,
            cls=CapS1HostedProofReceipt,
            extra_keys={
                "run_id",
                "status",
                "conclusion",
                "jobs_total",
                "jobs_passed",
                "jobs_failed",
                "jobs_cancelled",
                "job_manifest",
                "evidence_digest",
            },
            error="cap_s1_result_hosted_proof_invalid",
            nested_tuple_fields=("job_manifest",),
        ),
        "security_proof": lambda raw: _parse_bound_receipt(
            raw,
            cls=CapS1SecurityProofReceipt,
            extra_keys={
                "status",
                "tool_count",
                "findings",
                "failures",
                "cancelled",
                "tool_manifest",
                "evidence_digest",
            },
            error="cap_s1_result_security_proof_invalid",
            nested_tuple_fields=("tool_manifest",),
        ),
        "mutation_proof": lambda raw: _parse_bound_receipt(
            raw,
            cls=CapS1MutationProofReceipt,
            extra_keys={
                "status",
                "total",
                "killed",
                "survived",
                "skipped",
                "errors",
                "cancelled",
                "mutation_manifest",
                "evidence_digest",
            },
            error="cap_s1_result_mutation_proof_invalid",
            nested_tuple_fields=("mutation_manifest",),
        ),
        "cleanup_proof": lambda raw: _parse_bound_receipt(
            raw,
            cls=CapS1CleanupProofReceipt,
            extra_keys={
                "status",
                "all_removed",
                "resources_total",
                "failures",
                "residue_count",
                "resource_kinds",
                "resource_manifest",
                "evidence_digest",
            },
            error="cap_s1_result_cleanup_proof_invalid",
            nested_tuple_fields=("resource_manifest",),
            tuple_fields=("resource_kinds",),
        ),
        "review_state": lambda raw: _parse_bound_receipt(
            raw,
            cls=CapS1ReviewReceipt,
            extra_keys={
                "author",
                "author_id",
                "reviewer",
                "reviewer_id",
                "review_id",
                "state",
                "review_commit",
                "evidence_digest",
            },
            error="cap_s1_result_review_state_invalid",
        ),
    }
    for field_name, parser in parsers.items():
        raw = kwargs.get(field_name)
        if type(raw) is dict:
            kwargs[field_name] = parser(raw)
    if isinstance(kwargs.get("cleanup_proof"), CapS1CleanupProofReceipt):
        resource_kinds = kwargs["cleanup_proof"].resource_kinds
        if type(resource_kinds) is list:
            kwargs["cleanup_proof"] = dataclasses.replace(
                kwargs["cleanup_proof"], resource_kinds=tuple(resource_kinds)
            )
    if type(kwargs.get("canary_evidence")) is CanaryEvidence:
        kwargs["canary_evidence"] = _project_canary_result_evidence(
            kwargs["canary_evidence"]
        )
    result = CapS1Result(**kwargs)
    _validate_cap_s1_result_against_producer(
        result,
        producer_evidence=producer_evidence,
        github_observations=github_observations,
    )
    return result


def cap_s1_observer_registry() -> dict[str, object]:
    """Return the closed, public-safe production observer registry.

    This is descriptive evidence for review, not an execution API.  It
    intentionally contains templates and repository-relative identities only;
    no host path, environment value, credential or callback is projected.
    """

    return {
        "schema_version": "mastermind.cap_s1_source_observer_registry/v1",
        "python_argv": (
            "<bound-lexical-python-entrypoint>",
            "-I",
            "-B",
            "-c",
            "<fixed-source-owned-pytest-bootstrap>",
            "<private-exact-provenance-binding>",
            "-q",
            "--junitxml",
            "<owned-output>",
            *CAP_S1_OBSERVER_TEST_MODULES,
        ),
        "python_provenance_exit": _CAP_S1_PYTEST_PROVENANCE_EXIT,
        "python_bootstrap_source": _CAP_S1_PYTEST_BOOTSTRAP,
        "python_bootstrap_sha256": hashlib.sha256(
            _CAP_S1_PYTEST_BOOTSTRAP.encode("utf-8")
        ).hexdigest(),
        "python_source_modules": _CAP_S1_PYTEST_SOURCE_MODULES,
        "owned_git": {
            "object_count": _CAP_S1_OWNED_GIT_OBJECT_COUNT,
            "maximum_object_bytes": _CAP_S1_OWNED_GIT_MAX_OBJECT_BYTES,
            "filesystem_file_count": 5,
            "historical_tree_closure": {
                "commit": _CAP_S1_HISTORICAL_COMMIT,
                "root_tree": _CAP_S1_HISTORICAL_ROOT_TREE,
                "path_count": _CAP_S1_HISTORICAL_TREE_PATH_COUNT,
                "unique_object_count": _CAP_S1_HISTORICAL_TREE_UNIQUE_COUNT,
                "total_raw_bytes": _CAP_S1_HISTORICAL_TREE_TOTAL_RAW_BYTES,
                "maximum_raw_bytes": _CAP_S1_HISTORICAL_TREE_MAX_RAW_BYTES,
                "path_manifest_digest": (
                    _CAP_S1_HISTORICAL_TREE_PATH_MANIFEST_DIGEST
                ),
                "object_manifest_digest": (
                    _CAP_S1_HISTORICAL_TREE_OBJECT_MANIFEST_DIGEST
                ),
                "tracked_attribute_blobs": (),
                "package_blob_count": 7,
            },
            "environment": tuple(sorted(_CAP_S1_GIT_ENVIRONMENT)),
            "commands": (
                "rev-parse-fixed-identities",
                "ls-tree-full-historical-tree-metadata",
                "ls-tree-full-historical-leaf-metadata-no-attributes",
                "ls-tree-fixed-historical-package",
                "cat-file-batch-exact-object-manifest",
                "init-bare-owned-empty-template",
                "pack-objects-exact-manifest-with-indexes",
                "update-ref-no-deref-head",
                "rev-parse-fixed-owned-identities",
                "archive-fixed-historical-package",
                "for-each-ref-empty",
            ),
        },
        "diff_argv": (
            "git",
            "--no-pager",
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--check",
            "<verified-protected>...<verified-head>",
            "--",
            *RESULT_CHANGED_PATHS,
        ),
        "github_get_endpoint_families": CAP_S1_OBSERVER_GITHUB_ENDPOINT_FAMILIES,
        "mutants": CAP_S1_OBSERVER_MUTANTS,
        "mutant_assertions": CAP_S1_OBSERVER_MUTANT_ASSERTIONS,
        "mutant_transforms": tuple(
            (
                mutation_id,
                relative_path,
                hashlib.sha256(preimage.encode("utf-8")).hexdigest(),
                hashlib.sha256(postimage.encode("utf-8")).hexdigest(),
            )
            for mutation_id, relative_path, preimage, postimage
            in CAP_S1_OBSERVER_MUTANT_TRANSFORMS
        ),
        "environment_keys": CAP_S1_OBSERVER_ENVIRONMENT_KEYS,
        "cleanup_kinds": _RESULT_ALL_CLEANUP_KINDS,
        "observer_cleanup_policy": (
            "EXACT_OWNED_ROOT_IDENTITY",
            "BOUNDED_PREIMAGE_INODE_CENSUS",
            "CHILD_PROCESS_GROUP_REAP_AND_ABSENCE",
            "REMOVE_THEN_VERIFY_EVERY_FIXED_RESOURCE_ABSENT",
            "FAILED_OR_UNKNOWN_CLEANUP_REFUSES_RESULT",
        ),
        "secret_scan": CAP_S1_OBSERVER_SECRET_SCAN_STATE,
        "secret_supply": {
            "version": CAP_S1_GITLEAKS_VERSION,
            "source_commit": CAP_S1_GITLEAKS_SOURCE_COMMIT,
            "archive": (
                CAP_S1_GITLEAKS_ARCHIVE_URL,
                CAP_S1_GITLEAKS_ARCHIVE_BYTES,
                CAP_S1_GITLEAKS_ARCHIVE_SHA256,
            ),
            "checksum": (
                CAP_S1_GITLEAKS_CHECKSUM_URL,
                CAP_S1_GITLEAKS_CHECKSUM_BYTES,
                CAP_S1_GITLEAKS_CHECKSUM_SHA256,
            ),
            "release_asset_routes": CAP_S1_GITLEAKS_RELEASE_ASSET_ROUTES,
            "transport": (
                "DIRECT_200_OR_EXACT_ONE_HOP_302",
                "RAW_RULE_DIRECT_200_ONLY",
                "NO_PROXY_AUTH_COOKIE_RETRY_OR_FALLBACK",
                "OPAQUE_QUERY_PRIVATE_UNLOGGED",
            ),
            "rule": (
                CAP_S1_GITLEAKS_RULE_URL,
                CAP_S1_GITLEAKS_RULE_BYTES,
                CAP_S1_GITLEAKS_RULE_SHA256,
                CAP_S1_GITLEAKS_RULE_COUNT,
            ),
            "archive_members": CAP_S1_GITLEAKS_ARCHIVE_MEMBERS,
            "binary_member": CAP_S1_GITLEAKS_BINARY_MEMBER,
            "binary_sha256": "UNOBSERVED",
            "binary_version": "UNOBSERVED",
        },
        "secret_argv": (
            "<verified-owned-gitleaks>",
            "dir",
            "<verified-owned-21-path-tree>",
            "--config",
            "<verified-pinned-rule-file>",
            "--redact=100",
            "--no-banner",
            "--no-color",
            "--log-level",
            "trace",
            "--report-format",
            "json",
            "--report-path",
            "<owned-private-report>",
            "--exit-code",
            "10",
            "--ignore-gitleaks-allow",
            "--gitleaks-ignore-path",
            "<owned-empty-ignore-file>",
            "--max-target-megabytes",
            "0",
            "--max-archive-depth",
            "0",
            "--max-decode-depth",
            "5",
            "--timeout",
            "120",
        ),
        "secret_environment_keys": (
            "HOME",
            "LANG",
            "LC_ALL",
            "NO_COLOR",
            "PATH",
            "TMPDIR",
        ),
        "secret_controls": tuple(
            (
                rule_id,
                tuple(
                    (hashlib.sha256(segment).hexdigest(), len(segment), repeats)
                    for segment, repeats in recipe
                ),
                expected_count,
                assembled_sha256,
            )
            for rule_id, recipe, expected_count, assembled_sha256
            in CAP_S1_SECRET_CONTROL_RECIPES
        ),
        "secret_test_nodes": CAP_S1_SECRET_SCAN_TEST_NODES,
    }


def _cap_s1_observer_environment(
    *,
    owned_state_path: "Path | None" = None,
    owned_temp_root: "Path | None" = None,
) -> dict[str, str]:
    """Build the fixed non-secret child environment from source constants."""

    executable_dir = str(Path(os.path.abspath(sys.executable)).parent)
    system_path = os.pathsep.join(
        ("/opt/homebrew/bin", "/usr/local/bin", "/usr/sbin", os.defpath)
    )
    environment = {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.pathsep.join((executable_dir, system_path)),
        "PYTEST_ADDOPTS": "-p no:cacheprovider",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }
    if owned_state_path is not None:
        environment["OHF_FAKE_STATE"] = str(owned_state_path)
    if owned_temp_root is not None:
        environment["TMPDIR"] = str(owned_temp_root)
    return environment


def _cap_s1_github_environment(
    *, owned_state_root: Path, owned_temp_root: Path
) -> dict[str, str]:
    """Narrow inherited GitHub auth while keeping all CLI state attempt-local."""

    try:
        owned_state_root.mkdir(mode=0o700)
    except OSError as exc:
        raise CapS1ResultError("cap_s1_result_github_evidence_unavailable") from exc
    environment = _cap_s1_observer_environment(owned_temp_root=owned_temp_root)
    environment.update(
        {
            "HOME": str(Path.home()),
            "XDG_STATE_HOME": str(owned_state_root),
            "GH_PROMPT_DISABLED": "1",
            "GH_NO_UPDATE_NOTIFIER": "1",
        }
    )
    for key in ("GH_CONFIG_DIR", "GH_HOST", "GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(key)
        if value:
            environment[key] = value
    return environment


def _bind_cap_s1_observer_temp_root(
    path: Path,
    *,
    expected: os.stat_result,
    error: str,
) -> os.stat_result:
    """Bind one freshly-created output root as the child's private TMPDIR.

    Ownership normalization is descriptor-bound.  The pathname may be replaced
    between ``mkdtemp``/``lstat`` and this helper, so no pathname mutation is
    permitted until an ``O_NOFOLLOW`` directory descriptor has reproduced the
    expected object identity.  The pathname is checked again after the
    descriptor is closed before callers use it.
    """

    if (
        stat.S_ISLNK(expected.st_mode)
        or not stat.S_ISDIR(expected.st_mode)
        or expected.st_uid != os.getuid()
        or stat.S_IMODE(expected.st_mode) != 0o700
    ):
        raise CapS1ResultError(error)

    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptor = os.open(path, flags)
    except (AttributeError, NotImplementedError, OSError) as exc:
        raise CapS1ResultError(error) from exc

    normalized: "os.stat_result | None" = None
    descriptor_error: "CapS1ResultError | None" = None
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(before.st_mode)
            or (before.st_dev, before.st_ino) != (expected.st_dev, expected.st_ino)
            or stat.S_IFMT(before.st_mode) != stat.S_IFMT(expected.st_mode)
            or before.st_uid != expected.st_uid
            or before.st_gid != expected.st_gid
            or stat.S_IMODE(before.st_mode) != stat.S_IMODE(expected.st_mode)
        ):
            raise CapS1ResultError(error)
        if before.st_gid != os.getgid():
            os.fchown(descriptor, os.getuid(), os.getgid())
        normalized = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(normalized.st_mode)
            or (normalized.st_dev, normalized.st_ino)
            != (expected.st_dev, expected.st_ino)
            or normalized.st_uid != os.getuid()
            or normalized.st_gid != os.getgid()
            or stat.S_IMODE(normalized.st_mode) != 0o700
        ):
            raise CapS1ResultError(error)
    except CapS1ResultError as exc:
        descriptor_error = exc
    except (NotImplementedError, OSError) as exc:
        descriptor_error = CapS1ResultError(error)
        descriptor_error.__cause__ = exc
    finally:
        try:
            os.close(descriptor)
        except OSError as exc:
            if descriptor_error is None:
                descriptor_error = CapS1ResultError(error)
                descriptor_error.__cause__ = exc
    if descriptor_error is not None:
        raise descriptor_error
    if normalized is None:  # pragma: no cover - defensive invariant
        raise CapS1ResultError(error)

    try:
        current = path.lstat()
    except OSError as exc:
        raise CapS1ResultError(error) from exc
    if (
        stat.S_ISLNK(current.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino)
        != (normalized.st_dev, normalized.st_ino)
        or current.st_uid != os.getuid()
        or current.st_gid != os.getgid()
        or stat.S_IMODE(current.st_mode) != 0o700
    ):
        raise CapS1ResultError(error)
    return current


@dataclasses.dataclass(frozen=True, kw_only=True)
class _CapS1InterpreterIdentity:
    """Exact lexical Python entrypoint, resolved target, and venv binding."""

    entrypoint_path: str
    prefix: str
    base_prefix: str
    entrypoint_identity: tuple[int, int, int, int, int]
    entrypoint_link_target: "str | None"
    resolved_target_path: str
    resolved_target_identity: tuple[int, int, int, int, int]
    resolved_target_sha256: str
    venv_config_path: "str | None"
    venv_config_identity: "tuple[int, int, int, int, int] | None"
    venv_config_sha256: "str | None"


@dataclasses.dataclass(frozen=True, kw_only=True)
class _CapS1PytestBinding:
    """Private exact-source binding consumed by the actual pytest child."""

    payload_json: str
    bootstrap_sha256: str
    source_rows: tuple[tuple[str, str, str], ...]
    pytest_origin_sha256: str
    evidence_digest: str


def _cap_s1_stable_file_identity(
    path: Path,
    *,
    maximum_bytes: int,
    executable: bool = False,
) -> tuple[tuple[int, int, int, int, int], str]:
    """Hash one exact regular file and refuse identity drift during the read."""

    try:
        before = path.lstat()
        if (
            stat.S_ISLNK(before.st_mode)
            or not stat.S_ISREG(before.st_mode)
            or not (0 < before.st_size <= maximum_bytes)
            or (executable and not os.access(path, os.X_OK))
        ):
            raise ValueError("unsafe identity file")
        digest = _sha256_file(path)
        after = path.lstat()
    except (OSError, ValueError) as exc:
        raise CapS1ResultError("cap_s1_result_interpreter_identity_invalid") from exc
    identity = (
        before.st_dev,
        before.st_ino,
        stat.S_IMODE(before.st_mode),
        before.st_size,
        before.st_mtime_ns,
    )
    if identity != (
        after.st_dev,
        after.st_ino,
        stat.S_IMODE(after.st_mode),
        after.st_size,
        after.st_mtime_ns,
    ):
        raise CapS1ResultError("cap_s1_result_interpreter_identity_invalid")
    return identity, digest


def _capture_cap_s1_interpreter_identity(
    *,
    entrypoint: "str | None" = None,
    prefix: "str | None" = None,
    base_prefix: "str | None" = None,
) -> _CapS1InterpreterIdentity:
    """Bind the invoked entrypoint separately from its resolved binary target."""

    lexical = Path(os.path.abspath(entrypoint if entrypoint is not None else sys.executable))
    effective_prefix = os.path.abspath(prefix if prefix is not None else sys.prefix)
    effective_base_prefix = os.path.abspath(
        base_prefix if base_prefix is not None else sys.base_prefix
    )
    try:
        entry_state = lexical.lstat()
        if not (stat.S_ISLNK(entry_state.st_mode) or stat.S_ISREG(entry_state.st_mode)):
            raise ValueError("entrypoint is not a file or link")
        link_target = os.readlink(lexical) if stat.S_ISLNK(entry_state.st_mode) else None
        if link_target is not None and (
            not link_target
            or len(link_target.encode("utf-8")) > 4096
            or "\x00" in link_target
        ):
            raise ValueError("unsafe entrypoint link")
        resolved = lexical.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise CapS1ResultError("cap_s1_result_interpreter_identity_invalid") from exc
    entry_identity = (
        entry_state.st_dev,
        entry_state.st_ino,
        stat.S_IMODE(entry_state.st_mode),
        entry_state.st_size,
        entry_state.st_mtime_ns,
    )
    target_identity, target_digest = _cap_s1_stable_file_identity(
        resolved,
        maximum_bytes=256 * 1024 * 1024,
        executable=True,
    )

    config_path: "Path | None" = None
    config_identity: "tuple[int, int, int, int, int] | None" = None
    config_digest: "str | None" = None
    if effective_prefix != effective_base_prefix:
        config_path = Path(effective_prefix) / "pyvenv.cfg"
        config_identity, config_digest = _cap_s1_stable_file_identity(
            config_path,
            maximum_bytes=64 * 1024,
        )
    return _CapS1InterpreterIdentity(
        entrypoint_path=str(lexical),
        prefix=effective_prefix,
        base_prefix=effective_base_prefix,
        entrypoint_identity=entry_identity,
        entrypoint_link_target=link_target,
        resolved_target_path=str(resolved),
        resolved_target_identity=target_identity,
        resolved_target_sha256=target_digest,
        venv_config_path=str(config_path) if config_path is not None else None,
        venv_config_identity=config_identity,
        venv_config_sha256=config_digest,
    )


def _revalidate_cap_s1_interpreter_identity(
    identity: _CapS1InterpreterIdentity,
) -> None:
    """Refuse entrypoint, target, or applicable virtual-environment drift."""

    if type(identity) is not _CapS1InterpreterIdentity:
        raise CapS1ResultError("cap_s1_result_interpreter_identity_changed")
    try:
        current = _capture_cap_s1_interpreter_identity(
            entrypoint=identity.entrypoint_path,
            prefix=identity.prefix,
            base_prefix=identity.base_prefix,
        )
    except CapS1ResultError as exc:
        raise CapS1ResultError("cap_s1_result_interpreter_identity_changed") from exc
    if current != identity:
        raise CapS1ResultError("cap_s1_result_interpreter_identity_changed")


def _build_cap_s1_pytest_binding(
    *,
    source_root: Path,
    source_manifest: Sequence["_CapS1SourceCopyEntry"],
    interpreter: _CapS1InterpreterIdentity,
    expected_canary_sha256: "str | None" = None,
) -> _CapS1PytestBinding:
    """Bind source bytes and pytest before constructing the fixed child argv."""

    if type(interpreter) is not _CapS1InterpreterIdentity:
        raise CapS1ResultError("cap_s1_result_import_origin_invalid")
    manifest_by_path = {entry.path: entry for entry in source_manifest}
    if len(manifest_by_path) != len(source_manifest):
        raise CapS1ResultError("cap_s1_result_import_origin_invalid")
    source_rows: list[tuple[str, str, str]] = []
    for module_name, relative in _CAP_S1_PYTEST_SOURCE_MODULES:
        entry = manifest_by_path.get(relative)
        if entry is None or not _result_is_hex64(entry.sha256):
            raise CapS1ResultError("cap_s1_result_import_origin_invalid")
        expected_digest = entry.sha256
        if relative == "scripts/ohf/cap_s1_mastermind_operator_canary.py":
            if expected_canary_sha256 is not None:
                if not _result_is_hex64(expected_canary_sha256):
                    raise CapS1ResultError("cap_s1_result_import_origin_invalid")
                expected_digest = expected_canary_sha256
        try:
            candidate = (source_root / relative).resolve(strict=True)
            candidate.relative_to(source_root.resolve(strict=True))
            _identity, actual_digest = _cap_s1_stable_file_identity(
                candidate,
                maximum_bytes=64 * 1024 * 1024,
            )
        except (OSError, ValueError, CapS1ResultError) as exc:
            raise CapS1ResultError("cap_s1_result_import_origin_invalid") from exc
        if actual_digest != expected_digest:
            raise CapS1ResultError("cap_s1_result_import_origin_invalid")
        source_rows.append((module_name, relative, expected_digest))

    try:
        pytest_spec = importlib.util.find_spec("pytest")
        if pytest_spec is None or not pytest_spec.origin:
            raise ValueError("pytest origin unavailable")
        pytest_origin = Path(pytest_spec.origin).resolve(strict=True)
        pytest_origin.relative_to(Path(interpreter.prefix).resolve(strict=True))
        try:
            pytest_origin.relative_to(source_root.resolve(strict=True))
        except ValueError:
            pass
        else:
            raise ValueError("pytest resolved inside source copy")
        _pytest_identity, pytest_digest = _cap_s1_stable_file_identity(
            pytest_origin,
            maximum_bytes=16 * 1024 * 1024,
        )
    except (OSError, ValueError, CapS1ResultError) as exc:
        raise CapS1ResultError("cap_s1_result_import_origin_invalid") from exc

    payload = {
        "schema_version": "mastermind.cap_s1_pytest_child_binding/v1",
        "source_rows": source_rows,
        "pytest_origin": str(pytest_origin),
        "pytest_sha256": pytest_digest,
    }
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    bootstrap_sha256 = hashlib.sha256(
        _CAP_S1_PYTEST_BOOTSTRAP.encode("utf-8")
    ).hexdigest()
    evidence_digest = _canonical_digest(
        {
            "schema_version": payload["schema_version"],
            "bootstrap_sha256": bootstrap_sha256,
            "source_rows": source_rows,
            "pytest_sha256": pytest_digest,
            "interpreter_entrypoint": hashlib.sha256(
                interpreter.entrypoint_path.encode("utf-8")
            ).hexdigest(),
        }
    )
    return _CapS1PytestBinding(
        payload_json=payload_json,
        bootstrap_sha256=bootstrap_sha256,
        source_rows=tuple(source_rows),
        pytest_origin_sha256=pytest_digest,
        evidence_digest=evidence_digest,
    )


def _cap_s1_pytest_argv(
    binding: _CapS1PytestBinding,
    pytest_argv: Sequence[str],
) -> tuple[str, ...]:
    """Return only the fixed bootstrap; callers cannot inject executable code."""

    if (
        type(binding) is not _CapS1PytestBinding
        or not pytest_argv
        or binding.bootstrap_sha256
        != hashlib.sha256(_CAP_S1_PYTEST_BOOTSTRAP.encode("utf-8")).hexdigest()
        or not _result_is_hex64(binding.evidence_digest)
    ):
        raise CapS1ResultError("cap_s1_result_import_origin_invalid")
    return ("-c", _CAP_S1_PYTEST_BOOTSTRAP, binding.payload_json, *pytest_argv)


def _cap_s1_process_group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_cap_s1_process_group_absent(process_group: int) -> bool:
    deadline = time.monotonic() + 1.0
    while _cap_s1_process_group_exists(process_group) and time.monotonic() < deadline:
        time.sleep(0.01)
    return not _cap_s1_process_group_exists(process_group)


@dataclasses.dataclass(frozen=True, kw_only=True)
class _CapS1OwnedProcessCleanupObservation:
    """Safe, invocation-local proof that one exact child tree was reaped."""

    identity_digest: str
    removed: bool
    verified_absent: bool


@dataclasses.dataclass(frozen=True, kw_only=True)
class _CapS1OwnedRootIdentity:
    """Creation-time identity for one finite observer-owned directory root."""

    kind: str
    path: Path
    device: int
    inode: int


def _register_cap_s1_owned_root(path: Path, *, kind: str) -> _CapS1OwnedRootIdentity:
    """Bind a directory at creation time; never infer ownership at teardown."""

    try:
        state = path.lstat()
    except OSError as exc:
        raise CapS1ResultError("cap_s1_result_source_observer_cleanup_failed") from exc
    if (
        kind not in _RESULT_OBSERVER_CLEANUP_KINDS
        or kind == "observer-processes"
        or stat.S_ISLNK(state.st_mode)
        or not stat.S_ISDIR(state.st_mode)
    ):
        raise CapS1ResultError("cap_s1_result_source_observer_cleanup_failed")
    return _CapS1OwnedRootIdentity(
        kind=kind,
        path=path,
        device=state.st_dev,
        inode=state.st_ino,
    )


def _cap_s1_effective_file_size_limits(
    maximum_stream_bytes: int,
    inherited_limits: tuple[int, int],
) -> tuple[int, int]:
    """Clamp the requested stream ceiling without raising inherited limits."""

    requested = maximum_stream_bytes + 1
    inherited_soft, inherited_hard = inherited_limits
    effective_hard = (
        requested
        if inherited_hard == resource.RLIM_INFINITY
        else min(requested, inherited_hard)
    )
    effective_soft = (
        requested
        if inherited_soft == resource.RLIM_INFINITY
        else min(requested, inherited_soft)
    )
    return min(effective_soft, effective_hard), effective_hard


def _run_cap_s1_owned_process(
    argv: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    stdout_path: Path,
    stderr_path: Path,
    timeout: float,
    maximum_stream_bytes: int,
    error: str,
    cleanup_observations: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
    stdin_path: "Path | None" = None,
) -> int:
    """Run one source-owned child with pre-bound streams and group cleanup."""

    if (
        not argv
        or maximum_stream_bytes <= 0
        or stdout_path == stderr_path
        or stdout_path.parent != stderr_path.parent
        or stdout_path.exists()
        or stderr_path.exists()
        or (stdin_path is not None and not stdin_path.is_file())
    ):
        raise CapS1ResultError(error)

    def _limit_output() -> None:
        limits = _cap_s1_effective_file_size_limits(
            maximum_stream_bytes,
            resource.getrlimit(resource.RLIMIT_FSIZE),
        )
        resource.setrlimit(resource.RLIMIT_FSIZE, limits)

    process: "subprocess.Popen[bytes] | None" = None
    process_group: "int | None" = None
    stdout_identity: "tuple[int, int] | None" = None
    stderr_identity: "tuple[int, int] | None" = None
    return_code: "int | None" = None
    timed_out = False
    unexpected_descendant = False
    survivor = False
    stdin_file: "Any | None" = None
    stdin_identity: "tuple[int, int, int, int] | None" = None
    try:
        with stdout_path.open("xb") as stdout_file, stderr_path.open("xb") as stderr_file:
            stdout_state = os.fstat(stdout_file.fileno())
            stderr_state = os.fstat(stderr_file.fileno())
            stdout_identity = (stdout_state.st_dev, stdout_state.st_ino)
            stderr_identity = (stderr_state.st_dev, stderr_state.st_ino)
            if stdin_path is not None:
                stdin_file = stdin_path.open("rb")
                stdin_state = os.fstat(stdin_file.fileno())
                if (
                    not stat.S_ISREG(stdin_state.st_mode)
                    or stat.S_ISLNK(stdin_path.lstat().st_mode)
                    or stdin_state.st_size > 64 * 1024
                ):
                    raise CapS1ResultError(error)
                stdin_identity = (
                    stdin_state.st_dev,
                    stdin_state.st_ino,
                    stdin_state.st_size,
                    stdin_state.st_mtime_ns,
                )
            process = subprocess.Popen(
                list(argv),
                cwd=cwd,
                env=dict(environment),
                stdin=stdin_file if stdin_file is not None else subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True,
                preexec_fn=_limit_output,
            )
            process_group = process.pid
            if os.getpgid(process.pid) != process.pid or os.getsid(process.pid) != process.pid:
                process.kill()
                process.wait(timeout=10)
                raise CapS1ResultError(error)
            try:
                return_code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                if (
                    process.poll() is not None
                    or os.getpgid(process.pid) != process_group
                    or os.getsid(process.pid) != process_group
                ):
                    process.kill()
                    process.wait(timeout=10)
                    raise CapS1ResultError(error)
                os.killpg(process_group, signal.SIGKILL)
                process.wait(timeout=10)
        if stdin_file is not None:
            current_input = stdin_path.lstat() if stdin_path is not None else None
            if current_input is None or stdin_identity != (
                current_input.st_dev,
                current_input.st_ino,
                current_input.st_size,
                current_input.st_mtime_ns,
            ):
                raise CapS1ResultError(error)
        if process_group is not None and _cap_s1_process_group_exists(process_group):
            # A descendant survived the direct child.  This exact process group
            # was created above and never exposed, so clean it before refusing.
            unexpected_descendant = True
            os.killpg(process_group, signal.SIGKILL)
            survivor = not _wait_cap_s1_process_group_absent(process_group)
        elif process_group is not None:
            survivor = False
    except CapS1ResultError:
        raise
    except (OSError, subprocess.SubprocessError):
        if process is not None and process.poll() is None:
            try:
                if process_group is not None and os.getpgid(process.pid) == process_group:
                    os.killpg(process_group, signal.SIGKILL)
                else:
                    process.kill()
            finally:
                process.wait(timeout=10)
        raise CapS1ResultError(error) from None
    finally:
        if stdin_file is not None:
            try:
                stdin_file.close()
            except OSError:
                pass

    try:
        stdout_state = stdout_path.lstat()
        stderr_state = stderr_path.lstat()
        if (
            stdout_identity != (stdout_state.st_dev, stdout_state.st_ino)
            or stderr_identity != (stderr_state.st_dev, stderr_state.st_ino)
            or not stat.S_ISREG(stdout_state.st_mode)
            or not stat.S_ISREG(stderr_state.st_mode)
            or stdout_state.st_size > maximum_stream_bytes
            or stderr_state.st_size > maximum_stream_bytes
        ):
            raise CapS1ResultError(error)
    except OSError:
        raise CapS1ResultError(error) from None
    if timed_out or unexpected_descendant or survivor or return_code is None:
        raise CapS1ResultError(error)
    if cleanup_observations is not None:
        if process_group is None or _cap_s1_process_group_exists(process_group):
            raise CapS1ResultError(error)
        cleanup_observations.append(
            _CapS1OwnedProcessCleanupObservation(
                identity_digest=_canonical_digest(
                    {
                        "argv_digest": _canonical_digest(tuple(argv)),
                        "process_group": process_group,
                        "session": process_group,
                        "return_code": return_code,
                        "stdout_identity": stdout_identity,
                        "stderr_identity": stderr_identity,
                        "stdout_size": stdout_state.st_size,
                        "stderr_size": stderr_state.st_size,
                        "stdin_identity": stdin_identity,
                    }
                ),
                removed=True,
                verified_absent=True,
            )
        )
    return return_code


def _run_cap_s1_observer_process(
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
    owned_state_path: "Path | None" = None,
    cleanup_observations: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
    github_environment: bool = False,
    git_environment: bool = False,
    stdin_path: "Path | None" = None,
) -> subprocess.CompletedProcess[str]:
    """Run one fixed observer child without unbounded pipe capture."""

    if github_environment and owned_state_path is not None:
        raise CapS1ResultError("cap_s1_result_github_evidence_unavailable")
    output_root: "Path | None" = None
    root_state: "os.stat_result | None" = None
    return_code: "int | None" = None
    stdout: "str | None" = None
    stderr: "str | None" = None
    run_error: "BaseException | None" = None
    try:
        output_root = Path(tempfile.mkdtemp(prefix="cap-s1-observer-process-"))
        root_state = output_root.lstat()
        root_state = _bind_cap_s1_observer_temp_root(
            output_root,
            expected=root_state,
            error="cap_s1_result_source_observation_unavailable",
        )
        stdout_path = output_root / "stdout"
        stderr_path = output_root / "stderr"
        environment = (
            _cap_s1_github_environment(
                owned_state_root=output_root / "github-state",
                owned_temp_root=output_root,
            )
            if github_environment
            else _cap_s1_observer_environment(
                owned_state_path=owned_state_path,
                owned_temp_root=output_root,
            )
        )
        if git_environment:
            environment.update(_CAP_S1_GIT_ENVIRONMENT)
        return_code = _run_cap_s1_owned_process(
            argv,
            cwd=cwd,
            environment=environment,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout=timeout,
            maximum_stream_bytes=_CAP_S1_OBSERVER_MAX_OUTPUT_BYTES,
            error="cap_s1_result_source_observation_unavailable",
            cleanup_observations=cleanup_observations,
            stdin_path=stdin_path,
        )
        current = output_root.lstat()
        if (
            stat.S_ISLNK(current.st_mode)
            or not stat.S_ISDIR(current.st_mode)
            or (current.st_dev, current.st_ino)
            != (root_state.st_dev, root_state.st_ino)
        ):
            raise CapS1ResultError("cap_s1_result_source_observation_unavailable")
        stdout = stdout_path.read_bytes().decode("utf-8")
        stderr = stderr_path.read_bytes().decode("utf-8")
    except CapS1ResultError as exc:
        run_error = exc
    except (OSError, UnicodeError) as exc:
        run_error = CapS1ResultError("cap_s1_result_source_observation_unavailable")
        run_error.__cause__ = exc
    if output_root is not None and root_state is not None:
        removed, absent = _cleanup_owned_dir_action(
            output_root,
            expected_device=root_state.st_dev,
            expected_inode=root_state.st_ino,
        )
        if not removed or not absent:
            raise CapS1ResultError(
                "cap_s1_result_source_observation_unavailable"
            ) from run_error
        if cleanup_observations is not None:
            cleanup_observations.append(
                _CapS1OwnedProcessCleanupObservation(
                    identity_digest=_canonical_digest(
                        {
                            "kind": "observer-process-output-root",
                            "device": root_state.st_dev,
                            "inode": root_state.st_ino,
                            "ctime_ns": root_state.st_ctime_ns,
                        }
                    ),
                    removed=removed,
                    verified_absent=absent,
                )
            )
    if run_error is not None:
        raise run_error
    if return_code is None or stdout is None or stderr is None:
        raise CapS1ResultError("cap_s1_result_source_observation_unavailable")
    return subprocess.CompletedProcess(
        args=list(argv),
        returncode=return_code,
        stdout=stdout,
        stderr=stderr,
    )


def _run_cap_s1_python_observer_process(
    interpreter: _CapS1InterpreterIdentity,
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
    owned_state_path: "Path | None" = None,
    cleanup_observations: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
) -> subprocess.CompletedProcess[str]:
    """Run the bound lexical interpreter with fixed isolated/no-bytecode flags."""

    if not argv or argv[0] in {"-I", "-B"}:
        raise CapS1ResultError("cap_s1_result_interpreter_identity_invalid")
    _revalidate_cap_s1_interpreter_identity(interpreter)
    completed = _run_cap_s1_observer_process(
        (interpreter.entrypoint_path, "-I", "-B", *argv),
        cwd=cwd,
        timeout=timeout,
        owned_state_path=owned_state_path,
        cleanup_observations=cleanup_observations,
        git_environment=True,
    )
    _revalidate_cap_s1_interpreter_identity(interpreter)
    return completed


@dataclasses.dataclass(frozen=True, kw_only=True)
class _CapS1JunitCaseObservation:
    scope: str
    classname: str
    name: str
    outcome: str
    detail: str


def _parse_cap_s1_junit_cases(
    junit_path: Path,
    *,
    expected_scope: Sequence[str],
) -> tuple[_CapS1JunitCaseObservation, ...]:
    """Preserve assertion failures, setup errors and skips distinctly."""

    try:
        before = junit_path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_mode & 0o222
            or not (0 < before.st_size <= _CAP_S1_OBSERVER_MAX_JUNIT_BYTES)
        ):
            raise ValueError("unsafe junit")
        payload = junit_path.read_bytes()
        after = junit_path.lstat()
        if (
            len(payload) != before.st_size
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        ):
            raise ValueError("unstable junit")
        root = ET.fromstring(payload)
    except (OSError, ValueError, ET.ParseError) as exc:
        raise CapS1ResultError("cap_s1_result_local_proof_invalid") from exc

    expected = set(expected_scope)
    if len(expected) != len(tuple(expected_scope)):
        raise CapS1ResultError("cap_s1_result_local_proof_invalid")
    seen: set[str] = set()
    observations: list[_CapS1JunitCaseObservation] = []
    testcases = list(root.iter("testcase"))
    if not testcases:
        raise CapS1ResultError("cap_s1_result_local_proof_invalid")
    for case in testcases:
        classname = case.get("classname", "")
        name = case.get("name", "")
        identity = f"{classname}::{name}"
        if not classname or not name or identity in seen:
            raise CapS1ResultError("cap_s1_result_local_proof_invalid")
        seen.add(identity)
        module_parts = [part for part in classname.split(".") if part.startswith("test_")]
        if len(module_parts) != 1:
            raise CapS1ResultError("cap_s1_result_local_proof_invalid")
        scope = f"tests/{module_parts[0]}.py"
        if scope not in expected:
            raise CapS1ResultError("cap_s1_result_local_proof_invalid")
        failures = case.findall("failure")
        errors = case.findall("error")
        skipped = case.findall("skipped")
        if len(failures) + len(errors) + len(skipped) > 1:
            raise CapS1ResultError("cap_s1_result_local_proof_invalid")
        if failures:
            outcome = "FAILURE"
            element = failures[0]
        elif errors:
            outcome = "ERROR"
            element = errors[0]
        elif skipped:
            outcome = "SKIPPED"
            element = skipped[0]
        else:
            outcome = "PASSED"
            element = None
        detail = ""
        if element is not None:
            detail = "\n".join(
                part
                for part in (
                    element.get("type", ""),
                    element.get("message", ""),
                    element.text or "",
                )
                if part
            )
            if len(detail.encode("utf-8")) > 64 * 1024:
                raise CapS1ResultError("cap_s1_result_local_proof_invalid")
        observations.append(
            _CapS1JunitCaseObservation(
                scope=scope,
                classname=classname,
                name=name,
                outcome=outcome,
                detail=detail,
            )
        )
    return tuple(observations)


def _parse_cap_s1_junit(
    junit_path: Path,
    *,
    expected_scope: Sequence[str],
) -> tuple[tuple[str, int, int, int, int], ...]:
    """Derive complete per-module counts from one bounded JUnit artifact."""

    counts = {scope: [0, 0, 0, 0] for scope in expected_scope}
    for case in _parse_cap_s1_junit_cases(junit_path, expected_scope=expected_scope):
        if case.outcome == "PASSED":
            counts[case.scope][0] += 1
        elif case.outcome == "SKIPPED":
            counts[case.scope][1] += 1
        else:
            # Local-suite ERROR and FAILURE both block the suite, while the
            # mutation path below retains their distinct source meanings.
            counts[case.scope][2] += 1
    if any(sum(values) == 0 for values in counts.values()):
        raise CapS1ResultError("cap_s1_result_local_proof_invalid")
    return tuple(
        (scope, values[0], values[1], values[2], values[3])
        for scope, values in sorted(counts.items())
    )


def _parse_cap_s1_mutation_junit(
    junit_path: Path,
    *,
    expected_node: str,
) -> _CapS1JunitCaseObservation:
    module, separator, test_name = expected_node.partition("::")
    if not separator or "::" in test_name or not test_name.startswith("test_"):
        raise CapS1ResultError("cap_s1_result_mutation_proof_invalid")
    try:
        cases = _parse_cap_s1_junit_cases(junit_path, expected_scope=(module,))
    except CapS1ResultError:
        raise CapS1ResultError("cap_s1_result_mutation_proof_invalid") from None
    if len(cases) != 1 or cases[0].scope != module or cases[0].name != test_name:
        raise CapS1ResultError("cap_s1_result_mutation_proof_invalid")
    return cases[0]


@dataclasses.dataclass(frozen=True, kw_only=True)
class _CapS1SourceCopyEntry:
    path: str
    mode: str
    blob: str
    size: int
    sha256: str


_CAP_S1_OWNED_GIT_MAX_OBJECT_BYTES = 8 * 1024 * 1024
_CAP_S1_OWNED_GIT_OBJECT_COUNT = 131
_CAP_S1_HISTORICAL_COMMIT = "12c2cb8993f78e81c6cb9e9a75a9829f9b194dab"
_CAP_S1_HISTORICAL_ROOT_TREE = "b5a042c3b0a1a54d74855be5dcd132bef3a7a2ce"
_CAP_S1_HISTORICAL_TREE_PATH_COUNT = 124
_CAP_S1_HISTORICAL_TREE_UNIQUE_COUNT = 121
_CAP_S1_HISTORICAL_TREE_TOTAL_RAW_BYTES = 77_050
_CAP_S1_HISTORICAL_TREE_MAX_RAW_BYTES = 21_231
_CAP_S1_HISTORICAL_TREE_PATH_MANIFEST_DIGEST = (
    "5a6c36388af247b001fad02cabd21fd8e4e9d8e97d54adaf3ef785aacca4d92f"
)
_CAP_S1_HISTORICAL_TREE_OBJECT_MANIFEST_DIGEST = (
    "039b886b8975708e35347716afb50a105b4ae89d83af54300cb37ac25e188666"
)
_CAP_S1_HISTORICAL_TREE_MAX_COUNT = 256
_CAP_S1_HISTORICAL_TREE_MAX_TOTAL_RAW_BYTES = 8 * 1024 * 1024


@dataclasses.dataclass(frozen=True, kw_only=True)
class _CapS1OwnedGitContext:
    git_dir: Path
    device: int
    inode: int
    exact_head: str
    exact_tree: str
    historical_commit: str
    historical_package_tree: str
    historical_tree_path_manifest: tuple[tuple[str, str, int], ...]
    historical_tree_path_manifest_digest: str
    historical_tree_object_manifest: tuple[tuple[str, int], ...]
    historical_tree_object_manifest_digest: str
    object_manifest: tuple[tuple[str, str, int], ...]
    object_manifest_digest: str
    filesystem_manifest: tuple[tuple[str, int, str], ...]
    filesystem_manifest_digest: str
    archive_digest: str
    archive_diagnostic: str
    archive_diagnostic_digest: str
    archive_file_manifest: tuple[tuple[str, int, str], ...]
    archive_file_manifest_digest: str
    command_registry: tuple[str, ...]


def _cap_s1_owned_git_command(
    argv: Sequence[str],
    *,
    cwd: Path,
    cleanup_observations: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
    stdin_path: "Path | None" = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return _run_cap_s1_observer_process(
            argv,
            cwd=cwd,
            timeout=120,
            cleanup_observations=cleanup_observations,
            git_environment=True,
            stdin_path=stdin_path,
        )
    except CapS1ResultError as exc:
        raise CapS1ResultError("cap_s1_result_owned_git_invalid") from exc


def _record_cap_s1_transient_root_cleanup(
    identity: _CapS1OwnedRootIdentity,
    *,
    cleanup_observations: "list[_CapS1OwnedProcessCleanupObservation] | None",
) -> bool:
    removed, absent = _cleanup_owned_dir_action(
        identity.path,
        expected_device=identity.device,
        expected_inode=identity.inode,
    )
    if cleanup_observations is not None:
        cleanup_observations.append(
            _CapS1OwnedProcessCleanupObservation(
                identity_digest=_canonical_digest(
                    {
                        "kind": "owned-git-transient-root",
                        "path_kind": identity.kind,
                        "device": identity.device,
                        "inode": identity.inode,
                    }
                ),
                removed=removed,
                verified_absent=absent,
            )
        )
    return removed and absent


def _cap_s1_owned_git_expected_paths(
    expected_package_files: Sequence[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if len(expected_package_files) != 7 or len(set(expected_package_files)) != 7:
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    package_root = Path("plugins/mastermind-operator")
    blob_paths: list[str] = []
    tree_paths = {"plugins", package_root.as_posix()}
    for relative in expected_package_files:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        full = package_root / path
        blob_paths.append(full.as_posix())
        parent = full.parent
        while parent != package_root:
            tree_paths.add(parent.as_posix())
            parent = parent.parent
    trees = tuple(sorted(tree_paths))
    blobs = tuple(sorted(blob_paths))
    if len(trees) != 9:
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    return trees, blobs


def _cap_s1_owned_git_package_expectation(
    source_root: Path,
) -> tuple[str, str, tuple[str, ...]]:
    """Read the verified copied fixture and return its immutable Git closure."""

    try:
        fixture_path = source_root / V4_FIXTURE_RELATIVE_PATH
        raw = _strict_json_loads(
            fixture_path.read_bytes(),
            error="cap_s1_result_owned_git_invalid",
        )
        package = raw["capability_packages"][PACKAGE_CAPABILITY_ID]
        generation = build_capability_package_generation(
            capability_id=PACKAGE_CAPABILITY_ID,
            raw=package,
        )
    except (KeyError, OSError, CapabilityPackageError, CapS1ResultError) as exc:
        raise CapS1ResultError("cap_s1_result_owned_git_invalid") from exc
    files = tuple(row.relative_path for row in generation.files)
    if (
        not _result_is_hex40(generation.source_commit)
        or not _result_is_hex40(generation.source_tree_sha)
        or len(files) != 7
    ):
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    return generation.source_commit, generation.source_tree_sha, files


def _parse_cap_s1_owned_git_tree_listing(
    raw: str,
    *,
    expected_tree_paths: Sequence[str],
    expected_blob_paths: Sequence[str],
) -> tuple[tuple[str, str, str], ...]:
    rows: list[tuple[str, str, str]] = []
    for record in raw.split("\0"):
        if not record:
            continue
        metadata, separator, path = record.partition("\t")
        fields = metadata.split()
        if not separator or len(fields) != 3:
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        mode, kind, object_id = fields
        if (
            kind not in {"tree", "blob"}
            or not _result_is_hex40(object_id)
            or (kind == "tree" and mode != "040000")
            or (kind == "blob" and mode not in {"100644", "100755"})
        ):
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        rows.append((path, kind, object_id))
    if (
        tuple(sorted(path for path, kind, _oid in rows if kind == "tree"))
        != tuple(sorted(expected_tree_paths))
        or tuple(sorted(path for path, kind, _oid in rows if kind == "blob"))
        != tuple(sorted(expected_blob_paths))
    ):
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    return tuple(rows)


@dataclasses.dataclass(frozen=True, kw_only=True)
class _CapS1HistoricalTreeClosure:
    path_manifest: tuple[tuple[str, str, int], ...]
    path_manifest_digest: str
    object_manifest: tuple[tuple[str, int], ...]
    object_manifest_digest: str
    archive_diagnostic: str


def _derive_cap_s1_historical_tree_closure(
    *,
    source_git_dir: Path,
    source_repository_root: Path,
    historical_commit: str,
    historical_root_tree: str,
    included_blob_ids: Sequence[str],
    build_root: Path,
    cleanup_observations: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
) -> _CapS1HistoricalTreeClosure:
    """Derive every historical tree needed for Git's exact archive traversal."""

    listing = _cap_s1_owned_git_command(
        (
            "git",
            f"--git-dir={source_git_dir}",
            "ls-tree",
            "-d",
            "-r",
            "-t",
            "-z",
            historical_commit,
        ),
        cwd=source_repository_root,
        cleanup_observations=cleanup_observations,
    )
    if listing.returncode != 0 or listing.stderr:
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    path_objects: list[tuple[str, str]] = [(".", historical_root_tree)]
    seen_paths = {"."}
    for record in listing.stdout.split("\0"):
        if not record:
            continue
        metadata, separator, path = record.partition("\t")
        fields = metadata.split()
        candidate = Path(path)
        if (
            not separator
            or len(fields) != 3
            or fields[0] != "040000"
            or fields[1] != "tree"
            or not _result_is_hex40(fields[2])
            or candidate.is_absolute()
            or not candidate.parts
            or ".." in candidate.parts
            or path in seen_paths
        ):
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        seen_paths.add(path)
        path_objects.append((path, fields[2]))
    if not (1 < len(path_objects) <= _CAP_S1_HISTORICAL_TREE_MAX_COUNT):
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")

    included_blobs = set(included_blob_ids)
    if len(included_blobs) != 7 or not all(
        _result_is_hex40(object_id) for object_id in included_blobs
    ):
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    all_paths = _cap_s1_owned_git_command(
        (
            "git",
            f"--git-dir={source_git_dir}",
            "ls-tree",
            "-r",
            "-z",
            historical_commit,
        ),
        cwd=source_repository_root,
        cleanup_observations=cleanup_observations,
    )
    if all_paths.returncode != 0 or all_paths.stderr:
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    historical_paths: list[str] = []
    seen_leaf_paths: set[str] = set()
    first_missing: "tuple[str, str, str] | None" = None
    for record in all_paths.stdout.split("\0"):
        if not record:
            continue
        metadata, separator, path = record.partition("\t")
        fields = metadata.split()
        candidate = Path(path)
        if (
            not separator
            or len(fields) != 3
            or fields[1] not in {"blob", "commit"}
            or not _result_is_hex40(fields[2])
            or (fields[1] == "blob" and fields[0] not in {"100644", "100755", "120000"})
            or (fields[1] == "commit" and fields[0] != "160000")
            or candidate.is_absolute()
            or not candidate.parts
            or ".." in candidate.parts
            or path in seen_leaf_paths
        ):
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        seen_leaf_paths.add(path)
        historical_paths.append(path)
        if fields[2] not in included_blobs and first_missing is None:
            if re.fullmatch(r"[A-Za-z0-9._/-]+", path) is None:
                raise CapS1ResultError("cap_s1_result_owned_git_invalid")
            first_missing = (fields[0], fields[2], path)
    if any(Path(path).name == ".gitattributes" for path in historical_paths):
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    archive_diagnostic = ""
    if first_missing is not None:
        mode, object_id, path = first_missing
        archive_diagnostic = f"error: invalid object {mode} {object_id} for '{path}'\n"

    tree_ids = tuple(sorted({object_id for _path, object_id in path_objects}))
    tree_input = build_root / "historical-trees.in"
    _write_cap_s1_owned_bytes(
        tree_input,
        ("\n".join(tree_ids) + "\n").encode("ascii"),
        maximum=64 * 1024,
    )
    tree_input.chmod(0o400)
    manifest_run = _cap_s1_owned_git_command(
        (
            "git",
            f"--git-dir={source_git_dir}",
            "cat-file",
            "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        ),
        cwd=source_repository_root,
        cleanup_observations=cleanup_observations,
        stdin_path=tree_input,
    )
    if manifest_run.returncode != 0 or manifest_run.stderr:
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    sizes: dict[str, int] = {}
    for row in manifest_run.stdout.splitlines():
        fields = row.split()
        if len(fields) != 3:
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        object_id, kind, raw_size = fields
        try:
            size = int(raw_size)
        except ValueError as exc:
            raise CapS1ResultError("cap_s1_result_owned_git_invalid") from exc
        if (
            object_id not in tree_ids
            or object_id in sizes
            or kind != "tree"
            or size <= 0
            or size > _CAP_S1_HISTORICAL_TREE_MAX_TOTAL_RAW_BYTES
        ):
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        sizes[object_id] = size
    if set(sizes) != set(tree_ids):
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    object_manifest = tuple(sorted(sizes.items()))
    path_manifest = tuple(
        sorted((path, object_id, sizes[object_id]) for path, object_id in path_objects)
    )
    total_bytes = sum(size for _object_id, size in object_manifest)
    maximum_bytes = max(size for _object_id, size in object_manifest)
    path_digest = _canonical_digest(path_manifest)
    object_digest = _canonical_digest(object_manifest)
    if (
        len(object_manifest) > _CAP_S1_HISTORICAL_TREE_MAX_COUNT
        or total_bytes > _CAP_S1_HISTORICAL_TREE_MAX_TOTAL_RAW_BYTES
    ):
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    if historical_commit == _CAP_S1_HISTORICAL_COMMIT and (
        historical_root_tree != _CAP_S1_HISTORICAL_ROOT_TREE
        or len(path_manifest) != _CAP_S1_HISTORICAL_TREE_PATH_COUNT
        or len(object_manifest) != _CAP_S1_HISTORICAL_TREE_UNIQUE_COUNT
        or total_bytes != _CAP_S1_HISTORICAL_TREE_TOTAL_RAW_BYTES
        or maximum_bytes != _CAP_S1_HISTORICAL_TREE_MAX_RAW_BYTES
        or path_digest != _CAP_S1_HISTORICAL_TREE_PATH_MANIFEST_DIGEST
        or object_digest != _CAP_S1_HISTORICAL_TREE_OBJECT_MANIFEST_DIGEST
    ):
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    return _CapS1HistoricalTreeClosure(
        path_manifest=path_manifest,
        path_manifest_digest=path_digest,
        object_manifest=object_manifest,
        object_manifest_digest=object_digest,
        archive_diagnostic=archive_diagnostic,
    )


def _parse_cap_s1_owned_git_object_manifest(
    raw: str,
    *,
    expected: Mapping[str, str],
    expected_count: int,
) -> tuple[tuple[str, str, int], ...]:
    rows: list[tuple[str, str, int]] = []
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) != 3:
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        object_id, kind, raw_size = fields
        try:
            size = int(raw_size)
        except ValueError as exc:
            raise CapS1ResultError("cap_s1_result_owned_git_invalid") from exc
        if (
            expected.get(object_id) != kind
            or kind not in {"commit", "tree", "blob"}
            or size <= 0
            or size > _CAP_S1_OWNED_GIT_MAX_OBJECT_BYTES
        ):
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        rows.append((object_id, kind, size))
    result = tuple(sorted(rows))
    if (
        len(result) != expected_count
        or len({row[0] for row in result}) != len(result)
        or set(expected) != {row[0] for row in result}
        or sum(row[2] for row in result) > _CAP_S1_OWNED_GIT_MAX_OBJECT_BYTES
    ):
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    return result


def _parse_cap_s1_owned_git_archive(
    archive_path: Path,
    *,
    expected_tree_paths: Sequence[str],
    package_tree_rows: Sequence[tuple[str, str, str]],
) -> tuple[tuple[str, int, str], ...]:
    """Verify the unchanged Git archive argv produced exactly seven files."""

    expected_directories = set(expected_tree_paths)
    expected_blobs = {
        path: object_id
        for path, kind, object_id in package_tree_rows
        if kind == "blob"
    }
    if len(expected_blobs) != 7:
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    files: list[tuple[str, int, str]] = []
    seen: set[str] = set()
    try:
        with tarfile.open(archive_path, mode="r:") as bundle:
            members = bundle.getmembers()
            if len(members) != len(expected_directories) + len(expected_blobs):
                raise ValueError("archive member count")
            for member in members:
                name = member.name.rstrip("/")
                path = Path(name)
                if (
                    not name
                    or path.is_absolute()
                    or ".." in path.parts
                    or name in seen
                ):
                    raise ValueError("archive member path")
                seen.add(name)
                if name in expected_directories:
                    if not member.isdir() or member.size != 0:
                        raise ValueError("archive directory")
                    continue
                expected_blob = expected_blobs.get(name)
                if expected_blob is None or not member.isfile() or member.size < 0:
                    raise ValueError("archive file")
                extracted = bundle.extractfile(member)
                if extracted is None:
                    raise ValueError("archive file unavailable")
                payload = extracted.read(_CAP_S1_OWNED_GIT_MAX_OBJECT_BYTES + 1)
                if len(payload) != member.size or len(payload) > _CAP_S1_OWNED_GIT_MAX_OBJECT_BYTES:
                    raise ValueError("archive file size")
                git_blob = hashlib.sha1()
                git_blob.update(f"blob {len(payload)}\0".encode("ascii"))
                git_blob.update(payload)
                if git_blob.hexdigest() != expected_blob:
                    raise ValueError("archive file identity")
                files.append((name, len(payload), hashlib.sha256(payload).hexdigest()))
    except (OSError, ValueError, tarfile.TarError) as exc:
        raise CapS1ResultError("cap_s1_result_owned_git_invalid") from exc
    if seen != expected_directories | set(expected_blobs) or len(files) != 7:
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    return tuple(sorted(files))


def _seal_cap_s1_owned_git(git_dir: Path) -> None:
    try:
        for dirpath, dirnames, filenames in os.walk(git_dir, topdown=False):
            for name in (*dirnames, *filenames):
                state = (Path(dirpath) / name).lstat()
                if stat.S_ISLNK(state.st_mode):
                    raise ValueError("owned git symlink")
            for name in filenames:
                (Path(dirpath) / name).chmod(0o400)
            Path(dirpath).chmod(0o500)
    except (OSError, ValueError) as exc:
        raise CapS1ResultError("cap_s1_result_owned_git_invalid") from exc


def _cap_s1_owned_git_filesystem_manifest(
    git_dir: Path,
) -> tuple[tuple[str, int, str], ...]:
    """Bind the complete sealed capsule and reject every Git authority surface."""

    expected_directories = {
        "objects",
        "objects/info",
        "objects/pack",
        "refs",
        "refs/heads",
        "refs/tags",
    }
    try:
        root_state = git_dir.lstat()
        if (
            stat.S_ISLNK(root_state.st_mode)
            or not stat.S_ISDIR(root_state.st_mode)
            or stat.S_IMODE(root_state.st_mode) != 0o500
        ):
            raise ValueError("unsafe owned git root")
        directories: set[str] = set()
        files: list[tuple[str, int, str]] = []
        for path in git_dir.rglob("*"):
            relative = path.relative_to(git_dir).as_posix()
            state = path.lstat()
            if stat.S_ISLNK(state.st_mode):
                raise ValueError("owned git symlink")
            if stat.S_ISDIR(state.st_mode):
                if stat.S_IMODE(state.st_mode) != 0o500:
                    raise ValueError("writable owned git directory")
                directories.add(relative)
                continue
            if (
                not stat.S_ISREG(state.st_mode)
                or stat.S_IMODE(state.st_mode) != 0o400
                or state.st_size <= 0
                or state.st_size > _CAP_S1_OWNED_GIT_MAX_OBJECT_BYTES
            ):
                raise ValueError("unsafe owned git file")
            files.append((relative, state.st_size, _sha256_file(path)))
        if directories != expected_directories or len(files) != 5:
            raise ValueError("owned git filesystem closure changed")
        paths = {row[0] for row in files}
        pack_rows = sorted(path for path in paths if path.startswith("objects/pack/"))
        if paths - set(pack_rows) != {"HEAD", "config"} or len(pack_rows) != 3:
            raise ValueError("owned git file closure changed")
        pack_parts = [
            re.fullmatch(r"objects/pack/cap-s1-([0-9a-f]{40})\.(idx|pack|rev)", path)
            for path in pack_rows
        ]
        if (
            any(match is None for match in pack_parts)
            or {match.group(1) for match in pack_parts if match is not None}
            != {pack_parts[0].group(1)}
            or {match.group(2) for match in pack_parts if match is not None}
            != {"idx", "pack", "rev"}
        ):
            raise ValueError("owned git pack closure changed")
        config_lines = (git_dir / "config").read_text(encoding="ascii").splitlines()
        if not config_lines or config_lines[0] != "[core]":
            raise ValueError("owned git config changed")
        config: dict[str, str] = {}
        for line in config_lines[1:]:
            match = re.fullmatch(r"\t([a-z]+) = ([a-z0-9]+)", line)
            if match is None or match.group(1) in config:
                raise ValueError("owned git config changed")
            config[match.group(1)] = match.group(2)
        if (
            config.get("repositoryformatversion") != "0"
            or config.get("bare") != "true"
            or set(config)
            - {
                "repositoryformatversion",
                "filemode",
                "bare",
                "ignorecase",
                "precomposeunicode",
            }
            or any(
                value not in {"true", "false"}
                for key, value in config.items()
                if key != "repositoryformatversion"
            )
        ):
            raise ValueError("owned git config changed")
    except (OSError, UnicodeError, ValueError) as exc:
        raise CapS1ResultError("cap_s1_result_owned_git_invalid") from exc
    return tuple(sorted(files))


def _install_cap_s1_owned_git_context(
    *,
    source_repository_root: Path,
    source_root: Path,
    exact_head: str,
    historical_commit: str,
    expected_package_tree: str,
    expected_package_files: Sequence[str],
    cleanup_observations: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
) -> _CapS1OwnedGitContext:
    """Install only the finite objects needed by the real copied-source child."""

    if (
        not _result_is_hex40(exact_head)
        or not _result_is_hex40(historical_commit)
        or not _result_is_hex40(expected_package_tree)
    ):
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    expected_tree_paths, expected_blob_paths = _cap_s1_owned_git_expected_paths(
        expected_package_files
    )
    git_dir = source_root / ".git"
    build_root = source_root.parent / "owned-git-build"
    if git_dir.exists() or build_root.exists():
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    git_dir.mkdir(mode=0o700)
    git_identity = _register_cap_s1_owned_root(git_dir, kind="observer-source")
    build_root.mkdir(mode=0o700)
    build_identity = _register_cap_s1_owned_root(
        build_root, kind="observer-source"
    )
    succeeded = False
    context: "_CapS1OwnedGitContext | None" = None
    try:
        template_root = build_root / "empty-template"
        template_root.mkdir(mode=0o700)
        source_git = _cap_s1_owned_git_command(
            ("git", "rev-parse", "--git-dir"),
            cwd=source_repository_root,
            cleanup_observations=cleanup_observations,
        )
        source_git_dir = Path(source_git.stdout.strip())
        if source_git.returncode != 0 or source_git.stderr or not source_git.stdout.strip():
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        if not source_git_dir.is_absolute():
            source_git_dir = (source_repository_root / source_git_dir).resolve(strict=True)
        else:
            source_git_dir = source_git_dir.resolve(strict=True)

        identities = _cap_s1_owned_git_command(
            (
                "git",
                f"--git-dir={source_git_dir}",
                "rev-parse",
                f"{exact_head}^{{commit}}",
                f"{exact_head}^{{tree}}",
                f"{historical_commit}^{{commit}}",
                f"{historical_commit}^{{tree}}",
                f"{historical_commit}:plugins",
                f"{historical_commit}:plugins/mastermind-operator",
            ),
            cwd=source_repository_root,
            cleanup_observations=cleanup_observations,
        )
        identity_rows = identities.stdout.splitlines()
        if (
            identities.returncode != 0
            or identities.stderr
            or len(identity_rows) != 6
            or not all(_result_is_hex40(value) for value in identity_rows)
            or identity_rows[0] != exact_head
            or identity_rows[2] != historical_commit
            or identity_rows[5] != expected_package_tree
        ):
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        exact_tree = identity_rows[1]
        historical_tree = identity_rows[3]
        listing = _cap_s1_owned_git_command(
            (
                "git",
                f"--git-dir={source_git_dir}",
                "ls-tree",
                "-rz",
                "-t",
                "-r",
                historical_commit,
                "--",
                "plugins/mastermind-operator",
            ),
            cwd=source_repository_root,
            cleanup_observations=cleanup_observations,
        )
        if listing.returncode != 0 or listing.stderr:
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        tree_rows = _parse_cap_s1_owned_git_tree_listing(
            listing.stdout,
            expected_tree_paths=expected_tree_paths,
            expected_blob_paths=expected_blob_paths,
        )
        historical_closure = _derive_cap_s1_historical_tree_closure(
            source_git_dir=source_git_dir,
            source_repository_root=source_repository_root,
            historical_commit=historical_commit,
            historical_root_tree=historical_tree,
            included_blob_ids=tuple(
                object_id for _path, kind, object_id in tree_rows if kind == "blob"
            ),
            build_root=build_root,
            cleanup_observations=cleanup_observations,
        )
        object_types: dict[str, str] = {
            exact_head: "commit",
            exact_tree: "tree",
            historical_commit: "commit",
        }
        if exact_tree in {row[0] for row in historical_closure.object_manifest}:
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        for object_id, _size in historical_closure.object_manifest:
            prior = object_types.setdefault(object_id, "tree")
            if prior != "tree":
                raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        for _path, kind, object_id in tree_rows:
            if kind == "tree" and object_id not in object_types:
                raise CapS1ResultError("cap_s1_result_owned_git_invalid")
            prior = object_types.setdefault(object_id, kind)
            if prior != kind:
                raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        expected_object_count = 3 + len(historical_closure.object_manifest) + 7
        if (
            len(object_types) != expected_object_count
            or (
                historical_commit == _CAP_S1_HISTORICAL_COMMIT
                and expected_object_count != _CAP_S1_OWNED_GIT_OBJECT_COUNT
            )
        ):
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")

        object_input = build_root / "objects.in"
        _write_cap_s1_owned_bytes(
            object_input,
            ("\n".join(sorted(object_types)) + "\n").encode("ascii"),
            maximum=64 * 1024,
        )
        object_input.chmod(0o400)
        source_manifest_run = _cap_s1_owned_git_command(
            (
                "git",
                f"--git-dir={source_git_dir}",
                "cat-file",
                "--batch-check=%(objectname) %(objecttype) %(objectsize)",
            ),
            cwd=source_repository_root,
            cleanup_observations=cleanup_observations,
            stdin_path=object_input,
        )
        if source_manifest_run.returncode != 0 or source_manifest_run.stderr:
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        object_manifest = _parse_cap_s1_owned_git_object_manifest(
            source_manifest_run.stdout,
            expected=object_types,
            expected_count=expected_object_count,
        )

        initialized = _cap_s1_owned_git_command(
            (
                "git",
                "init",
                "--bare",
                "--quiet",
                f"--template={template_root}",
                str(git_dir),
            ),
            cwd=build_root,
            cleanup_observations=cleanup_observations,
        )
        if initialized.returncode != 0 or initialized.stderr:
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        pack_prefix = git_dir / "objects/pack/cap-s1"
        packed = _cap_s1_owned_git_command(
            (
                "git",
                f"--git-dir={source_git_dir}",
                "pack-objects",
                "--window=0",
                "--depth=0",
                "--no-reuse-delta",
                "--no-reuse-object",
                str(pack_prefix),
            ),
            cwd=build_root,
            cleanup_observations=cleanup_observations,
            stdin_path=object_input,
        )
        pack_id = packed.stdout.strip()
        if (
            packed.returncode != 0
            or packed.stderr
            or not _result_is_hex40(pack_id)
        ):
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        pack_path = pack_prefix.with_name(f"cap-s1-{pack_id}.pack")
        index_path = pack_prefix.with_name(f"cap-s1-{pack_id}.idx")
        reverse_index_path = pack_prefix.with_name(f"cap-s1-{pack_id}.rev")
        if set((git_dir / "objects/pack").iterdir()) != {
            pack_path,
            index_path,
            reverse_index_path,
        }:
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        if (
            pack_path.stat().st_size <= 0
            or pack_path.stat().st_size > _CAP_S1_OWNED_GIT_MAX_OBJECT_BYTES
            or index_path.stat().st_size <= 0
            or index_path.stat().st_size > 1024 * 1024
            or reverse_index_path.stat().st_size <= 0
            or reverse_index_path.stat().st_size > 1024 * 1024
        ):
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")

        updated = _cap_s1_owned_git_command(
            (
                "git",
                f"--git-dir={git_dir}",
                "update-ref",
                "--no-deref",
                "HEAD",
                exact_head,
            ),
            cwd=source_root,
            cleanup_observations=cleanup_observations,
        )
        if updated.returncode != 0 or updated.stderr:
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")

        verified_manifest = _cap_s1_owned_git_command(
            (
                "git",
                f"--git-dir={git_dir}",
                "cat-file",
                "--batch-check=%(objectname) %(objecttype) %(objectsize)",
            ),
            cwd=source_root,
            cleanup_observations=cleanup_observations,
            stdin_path=object_input,
        )
        if verified_manifest.returncode != 0 or verified_manifest.stderr:
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        if _parse_cap_s1_owned_git_object_manifest(
            verified_manifest.stdout,
            expected=object_types,
            expected_count=expected_object_count,
        ) != object_manifest:
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")

        verification = _cap_s1_owned_git_command(
            (
                "git",
                f"--git-dir={git_dir}",
                "rev-parse",
                "HEAD",
                "HEAD^{tree}",
                f"{historical_commit}^{{commit}}",
                f"{historical_commit}:plugins/mastermind-operator",
            ),
            cwd=source_root,
            cleanup_observations=cleanup_observations,
        )
        if verification.stdout.splitlines() != [
            exact_head,
            exact_tree,
            historical_commit,
            expected_package_tree,
        ] or verification.stderr or verification.returncode != 0:
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")

        archive_path = build_root / "package.tar"
        archive_run = _cap_s1_owned_git_command(
            (
                "git",
                f"--git-dir={git_dir}",
                "archive",
                "--format=tar",
                f"--output={archive_path}",
                historical_commit,
                "--",
                "plugins/mastermind-operator",
            ),
            cwd=source_root,
            cleanup_observations=cleanup_observations,
        )
        if (
            archive_run.returncode != 0
            or archive_run.stderr != historical_closure.archive_diagnostic
        ):
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        archive_state = archive_path.lstat()
        if (
            not stat.S_ISREG(archive_state.st_mode)
            or archive_state.st_size <= 0
            or archive_state.st_size > _CAP_S1_OWNED_GIT_MAX_OBJECT_BYTES
        ):
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        archive_digest = _sha256_file(archive_path)
        archive_file_manifest = _parse_cap_s1_owned_git_archive(
            archive_path,
            expected_tree_paths=expected_tree_paths,
            package_tree_rows=tree_rows,
        )

        forbidden = (
            git_dir / "hooks",
            git_dir / "index",
            git_dir / "logs",
            git_dir / "objects/info/alternates",
            git_dir / "refs/remotes",
            git_dir / "refs/replace",
            git_dir / "shallow",
        )
        refs = _cap_s1_owned_git_command(
            ("git", f"--git-dir={git_dir}", "for-each-ref"),
            cwd=source_root,
            cleanup_observations=cleanup_observations,
        )
        if refs.returncode != 0 or refs.stdout or refs.stderr or any(
            path.exists() for path in forbidden
        ):
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
        if (git_dir / "HEAD").read_text(encoding="ascii").strip() != exact_head:
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")

        _seal_cap_s1_owned_git(git_dir)
        filesystem_manifest = _cap_s1_owned_git_filesystem_manifest(git_dir)
        context = _CapS1OwnedGitContext(
            git_dir=git_dir,
            device=git_identity.device,
            inode=git_identity.inode,
            exact_head=exact_head,
            exact_tree=exact_tree,
            historical_commit=historical_commit,
            historical_package_tree=expected_package_tree,
            historical_tree_path_manifest=historical_closure.path_manifest,
            historical_tree_path_manifest_digest=(
                historical_closure.path_manifest_digest
            ),
            historical_tree_object_manifest=historical_closure.object_manifest,
            historical_tree_object_manifest_digest=(
                historical_closure.object_manifest_digest
            ),
            object_manifest=object_manifest,
            object_manifest_digest=_canonical_digest(object_manifest),
            filesystem_manifest=filesystem_manifest,
            filesystem_manifest_digest=_canonical_digest(filesystem_manifest),
            archive_digest=archive_digest,
            archive_diagnostic=historical_closure.archive_diagnostic,
            archive_diagnostic_digest=hashlib.sha256(
                historical_closure.archive_diagnostic.encode("utf-8")
            ).hexdigest(),
            archive_file_manifest=archive_file_manifest,
            archive_file_manifest_digest=_canonical_digest(archive_file_manifest),
            command_registry=(
                "rev-parse-fixed-identities",
                "ls-tree-full-historical-tree-metadata",
                "ls-tree-full-historical-leaf-metadata-no-attributes",
                "ls-tree-fixed-historical-package",
                "cat-file-batch-exact-object-manifest",
                "init-bare-owned-empty-template",
                "pack-objects-exact-manifest-with-indexes",
                "update-ref-no-deref-head",
                "rev-parse-fixed-owned-identities",
                "archive-fixed-historical-package",
                "for-each-ref-empty",
            ),
        )
        succeeded = True
    except (OSError, UnicodeError, ValueError, tarfile.TarError, CapS1ResultError) as exc:
        raise CapS1ResultError("cap_s1_result_owned_git_invalid") from exc
    finally:
        build_clean = _record_cap_s1_transient_root_cleanup(
            build_identity,
            cleanup_observations=cleanup_observations,
        )
        if not succeeded or not build_clean:
            git_clean = _record_cap_s1_transient_root_cleanup(
                git_identity,
                cleanup_observations=cleanup_observations,
            )
            if succeeded and (not build_clean or not git_clean):
                raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    if context is None:
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    return context


def _verify_cap_s1_owned_git_context(
    context: _CapS1OwnedGitContext,
    *,
    cleanup_observations: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
) -> None:
    if type(context) is not _CapS1OwnedGitContext:
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    try:
        state = context.git_dir.lstat()
    except OSError as exc:
        raise CapS1ResultError("cap_s1_result_owned_git_invalid") from exc
    if (
        stat.S_ISLNK(state.st_mode)
        or not stat.S_ISDIR(state.st_mode)
        or (state.st_dev, state.st_ino) != (context.device, context.inode)
        or _canonical_digest(context.object_manifest) != context.object_manifest_digest
        or _canonical_digest(context.historical_tree_path_manifest)
        != context.historical_tree_path_manifest_digest
        or _canonical_digest(context.historical_tree_object_manifest)
        != context.historical_tree_object_manifest_digest
        or _canonical_digest(context.filesystem_manifest)
        != context.filesystem_manifest_digest
        or hashlib.sha256(context.archive_diagnostic.encode("utf-8")).hexdigest()
        != context.archive_diagnostic_digest
        or _canonical_digest(context.archive_file_manifest)
        != context.archive_file_manifest_digest
        or _cap_s1_owned_git_filesystem_manifest(context.git_dir)
        != context.filesystem_manifest
    ):
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    for object_id, _kind, _size in context.object_manifest:
        observed = _cap_s1_owned_git_command(
            ("git", f"--git-dir={context.git_dir}", "cat-file", "-e", object_id),
            cwd=context.git_dir.parent,
            cleanup_observations=cleanup_observations,
        )
        if observed.returncode != 0 or observed.stdout or observed.stderr:
            raise CapS1ResultError("cap_s1_result_owned_git_invalid")
    identities = _cap_s1_owned_git_command(
        (
            "git",
            f"--git-dir={context.git_dir}",
            "rev-parse",
            "HEAD",
            "HEAD^{tree}",
            f"{context.historical_commit}^{{commit}}",
            f"{context.historical_commit}:plugins/mastermind-operator",
        ),
        cwd=context.git_dir.parent,
        cleanup_observations=cleanup_observations,
    )
    if identities.stdout.splitlines() != [
        context.exact_head,
        context.exact_tree,
        context.historical_commit,
        context.historical_package_tree,
    ] or identities.stderr or identities.returncode != 0:
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")


def _remove_cap_s1_owned_git_context(
    context: _CapS1OwnedGitContext,
    *,
    cleanup_observations: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
) -> None:
    identity = _CapS1OwnedRootIdentity(
        kind="observer-source",
        path=context.git_dir,
        device=context.device,
        inode=context.inode,
    )
    if not _record_cap_s1_transient_root_cleanup(
        identity,
        cleanup_observations=cleanup_observations,
    ):
        raise CapS1ResultError("cap_s1_result_owned_git_invalid")


def _run_cap_s1_observer_bytes(
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
    maximum_stream_bytes: int,
    cleanup_observations: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
    git_environment: bool = False,
    stdin_path: "Path | None" = None,
) -> subprocess.CompletedProcess[bytes]:
    """Binary-output counterpart for bounded fixed Git observations."""

    output_root: "Path | None" = None
    root_state: "os.stat_result | None" = None
    return_code: "int | None" = None
    stdout: "bytes | None" = None
    stderr: "bytes | None" = None
    run_error: "BaseException | None" = None
    try:
        output_root = Path(tempfile.mkdtemp(prefix="cap-s1-observer-bytes-"))
        root_state = output_root.lstat()
        root_state = _bind_cap_s1_observer_temp_root(
            output_root,
            expected=root_state,
            error="cap_s1_result_source_copy_invalid",
        )
        stdout_path = output_root / "stdout"
        stderr_path = output_root / "stderr"
        environment = _cap_s1_observer_environment(
            owned_temp_root=output_root,
        )
        if git_environment:
            environment.update(_CAP_S1_GIT_ENVIRONMENT)
        return_code = _run_cap_s1_owned_process(
            argv,
            cwd=cwd,
            environment=environment,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout=timeout,
            maximum_stream_bytes=maximum_stream_bytes,
            error="cap_s1_result_source_copy_invalid",
            cleanup_observations=cleanup_observations,
            stdin_path=stdin_path,
        )
        current = output_root.lstat()
        if (
            stat.S_ISLNK(current.st_mode)
            or not stat.S_ISDIR(current.st_mode)
            or (current.st_dev, current.st_ino)
            != (root_state.st_dev, root_state.st_ino)
        ):
            raise CapS1ResultError("cap_s1_result_source_copy_invalid")
        stdout = stdout_path.read_bytes()
        stderr = stderr_path.read_bytes()
    except CapS1ResultError as exc:
        run_error = exc
    except OSError as exc:
        run_error = CapS1ResultError("cap_s1_result_source_copy_invalid")
        run_error.__cause__ = exc
    if output_root is not None and root_state is not None:
        removed, absent = _cleanup_owned_dir_action(
            output_root,
            expected_device=root_state.st_dev,
            expected_inode=root_state.st_ino,
        )
        if not removed or not absent:
            raise CapS1ResultError("cap_s1_result_source_copy_invalid") from run_error
        if cleanup_observations is not None:
            cleanup_observations.append(
                _CapS1OwnedProcessCleanupObservation(
                    identity_digest=_canonical_digest(
                        {
                            "kind": "observer-bytes-output-root",
                            "device": root_state.st_dev,
                            "inode": root_state.st_ino,
                            "ctime_ns": root_state.st_ctime_ns,
                        }
                    ),
                    removed=removed,
                    verified_absent=absent,
                )
            )
    if run_error is not None:
        raise run_error
    if return_code is None or stdout is None or stderr is None:
        raise CapS1ResultError("cap_s1_result_source_copy_invalid")
    return subprocess.CompletedProcess(
        args=list(argv), returncode=return_code, stdout=stdout, stderr=stderr
    )


def _extract_cap_s1_source_archive(archive_path: Path, destination: Path) -> None:
    """Extract the regular-file projection of an owner-created Git archive.

    Tracked symbolic links are intentionally omitted: mutation proof imports
    and verifies every regular blob, while materializing a link would expand
    the owned source tree's filesystem authority.  Hard links and special
    members remain invalid, and the later manifest pass proves the complete
    regular-blob census against the exact commit.
    """

    try:
        archive_state = archive_path.lstat()
        if (
            not stat.S_ISREG(archive_state.st_mode)
            or archive_state.st_size <= 0
            or archive_state.st_size > _CAP_S1_OBSERVER_MAX_ARCHIVE_BYTES
        ):
            raise ValueError("unsafe archive")
        with tarfile.open(archive_path, mode="r:") as bundle:
            members = bundle.getmembers()
            if not members:
                raise ValueError("empty archive")
            extractable: list[tarfile.TarInfo] = []
            for member in members:
                path = Path(member.name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or member.islnk()
                ):
                    raise ValueError("unsafe archive member")
                if member.issym() or member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError("unsafe archive member")
                extractable.append(member)
            if not extractable:
                raise ValueError("empty regular archive projection")
            bundle.extractall(destination, members=extractable, filter="data")
    except (OSError, tarfile.TarError, ValueError) as exc:
        raise CapS1ResultError("cap_s1_result_source_copy_invalid") from exc


def _hash_cap_s1_source_file(path: Path, *, expected_size: int) -> tuple[str, str]:
    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_size != expected_size
            or before.st_size > _CAP_S1_OBSERVER_MAX_ARCHIVE_BYTES
        ):
            raise ValueError("unsafe source file")
        git_hash = hashlib.sha1()
        git_hash.update(f"blob {expected_size}\0".encode("ascii"))
        content_hash = hashlib.sha256()
        observed_size = 0
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                observed_size += len(chunk)
                if observed_size > expected_size:
                    raise ValueError("source file grew")
                git_hash.update(chunk)
                content_hash.update(chunk)
        after = path.lstat()
        if (
            observed_size != expected_size
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        ):
            raise ValueError("unstable source file")
    except (OSError, ValueError) as exc:
        raise CapS1ResultError("cap_s1_result_source_copy_invalid") from exc
    return git_hash.hexdigest(), content_hash.hexdigest()


def _verify_cap_s1_owned_source_manifest(
    *,
    source_root: Path,
    manifest: Sequence[_CapS1SourceCopyEntry],
) -> None:
    expected_files = {entry.path for entry in manifest}
    expected_directories: set[str] = set()
    for path in expected_files:
        parent = Path(path).parent
        while parent != Path("."):
            expected_directories.add(parent.as_posix())
            parent = parent.parent
    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    try:
        for path in source_root.rglob("*"):
            relative = path.relative_to(source_root).as_posix()
            state = path.lstat()
            if stat.S_ISLNK(state.st_mode):
                raise ValueError("source symlink")
            if stat.S_ISREG(state.st_mode):
                actual_files.add(relative)
            elif stat.S_ISDIR(state.st_mode):
                actual_directories.add(relative)
            else:
                raise ValueError("source special file")
    except (OSError, ValueError) as exc:
        raise CapS1ResultError("cap_s1_result_source_copy_invalid") from exc
    if actual_files != expected_files or actual_directories != expected_directories:
        raise CapS1ResultError("cap_s1_result_source_copy_invalid")
    for entry in manifest:
        candidate = source_root / entry.path
        git_oid, sha256 = _hash_cap_s1_source_file(candidate, expected_size=entry.size)
        executable = bool(candidate.lstat().st_mode & 0o111)
        if (
            git_oid != entry.blob
            or sha256 != entry.sha256
            or executable != (entry.mode == "100755")
        ):
            raise CapS1ResultError("cap_s1_result_source_copy_invalid")


def _verify_cap_s1_source_copy(
    *,
    source_root: Path,
    exact_head: str,
    process_cleanup: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
) -> tuple[_CapS1SourceCopyEntry, ...]:
    """Byte-verify every regular tracked blob and reject extra source nodes."""

    listing = _run_cap_s1_observer_bytes(
        ("git", "ls-tree", "-rz", exact_head),
        cwd=REPO_ROOT,
        timeout=120,
        maximum_stream_bytes=_CAP_S1_OBSERVER_MAX_TREE_BYTES,
        cleanup_observations=process_cleanup,
    )
    if listing.returncode != 0 or listing.stderr:
        raise CapS1ResultError("cap_s1_result_source_copy_invalid")
    manifest: list[_CapS1SourceCopyEntry] = []
    for raw_entry in listing.stdout.split(b"\0"):
        if not raw_entry:
            continue
        metadata, separator, raw_path = raw_entry.partition(b"\t")
        fields = metadata.split()
        if not separator or len(fields) != 3:
            raise CapS1ResultError("cap_s1_result_source_copy_invalid")
        mode, kind, expected_oid = fields
        if kind != b"blob" or mode not in {b"100644", b"100755"}:
            continue
        try:
            relative = raw_path.decode("utf-8")
        except UnicodeError as exc:
            raise CapS1ResultError("cap_s1_result_source_copy_invalid") from exc
        candidate = source_root / relative
        if not candidate.is_file() or candidate.is_symlink():
            raise CapS1ResultError("cap_s1_result_source_copy_invalid")
        size = candidate.lstat().st_size
        git_oid, sha256 = _hash_cap_s1_source_file(
            candidate,
            expected_size=size,
        )
        if git_oid.encode("ascii") != expected_oid:
            raise CapS1ResultError("cap_s1_result_source_copy_invalid")
        manifest.append(
            _CapS1SourceCopyEntry(
                path=relative,
                mode=mode.decode("ascii"),
                blob=git_oid,
                size=size,
                sha256=sha256,
            )
        )
    result = tuple(sorted(manifest, key=lambda entry: entry.path))
    _verify_cap_s1_owned_source_manifest(source_root=source_root, manifest=result)
    return result


def _owned_cap_s1_source_copy(
    *,
    exact_head: str,
    scratch_root: Path,
    owned_roots: "list[_CapS1OwnedRootIdentity] | None" = None,
    process_cleanup: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
) -> tuple[Path, tuple[_CapS1SourceCopyEntry, ...]]:
    status = _run_cap_s1_observer_process(
        ("git", "status", "--porcelain=v1", "--untracked-files=all"),
        cwd=REPO_ROOT,
        timeout=30,
        cleanup_observations=process_cleanup,
    )
    if status.returncode != 0 or status.stdout:
        raise CapS1ResultError("cap_s1_result_source_checkout_not_clean")
    copy_root = scratch_root / "source-copy"
    copy_root.mkdir(mode=0o700)
    if owned_roots is not None:
        owned_roots.append(_register_cap_s1_owned_root(copy_root, kind="observer-source"))
    archive_path = copy_root / "verified-source.tar"
    archive_stderr = copy_root / "verified-source.stderr"
    archived_code = _run_cap_s1_owned_process(
        ("git", "archive", "--format=tar", exact_head),
        cwd=REPO_ROOT,
        environment=_cap_s1_observer_environment(),
        stdout_path=archive_path,
        stderr_path=archive_stderr,
        timeout=300,
        maximum_stream_bytes=_CAP_S1_OBSERVER_MAX_ARCHIVE_BYTES,
        error="cap_s1_result_source_copy_invalid",
        cleanup_observations=process_cleanup,
    )
    if archived_code != 0 or archive_stderr.read_bytes():
        raise CapS1ResultError("cap_s1_result_source_copy_invalid")
    source_root = copy_root / "verified-source"
    source_root.mkdir(mode=0o700)
    if owned_roots is not None:
        owned_roots.append(_register_cap_s1_owned_root(source_root, kind="observer-source"))
    _extract_cap_s1_source_archive(archive_path, source_root)
    manifest = _verify_cap_s1_source_copy(
        source_root=source_root,
        exact_head=exact_head,
        process_cleanup=process_cleanup,
    )
    archive_path.unlink()
    archive_stderr.unlink()
    if archive_path.exists() or archive_stderr.exists():
        raise CapS1ResultError("cap_s1_result_source_copy_invalid")
    return source_root, manifest


def _capture_cap_s1_source_identity(
    *,
    process_cleanup: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
) -> tuple[str, str, str]:
    """Capture clean HEAD/tree/protected identities through bounded children."""

    identity = _run_cap_s1_observer_process(
        ("git", "rev-parse", "HEAD", "HEAD^{tree}", "origin/master"),
        cwd=REPO_ROOT,
        timeout=30,
        cleanup_observations=process_cleanup,
    )
    status = _run_cap_s1_observer_process(
        ("git", "status", "--porcelain=v1", "--untracked-files=all"),
        cwd=REPO_ROOT,
        timeout=30,
        cleanup_observations=process_cleanup,
    )
    rows = identity.stdout.splitlines()
    if (
        identity.returncode != 0
        or identity.stderr
        or len(rows) != 3
        or not all(_result_is_hex40(value) for value in rows)
        or status.returncode != 0
        or status.stdout
        or status.stderr
    ):
        raise CapS1ResultError("cap_s1_result_source_identity_unavailable")
    return rows[0], rows[1], rows[2]


def _revalidate_cap_s1_observer_source(
    *,
    before: tuple[str, str, str],
    source_root: Path,
    source_manifest: Sequence[_CapS1SourceCopyEntry],
    process_cleanup: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
) -> None:
    """Refuse repository or owned-source drift before receipt construction."""

    if _capture_cap_s1_source_identity(process_cleanup=process_cleanup) != before:
        raise CapS1ResultError("cap_s1_result_source_identity_changed")
    _verify_cap_s1_owned_source_manifest(
        source_root=source_root,
        manifest=source_manifest,
    )


def _observe_cap_s1_import_origins(
    *,
    source_root: Path,
    interpreter: "_CapS1InterpreterIdentity | None" = None,
    process_cleanup: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
) -> str:
    """Verify fixed source/dependency imports and return only a safe digest."""

    source_modules = (
        "scripts.ohf.cap_s1_mastermind_operator_canary",
        "scripts.ohf.capability_skill_projection",
        "scripts.ohf.protocol",
        "control_plane.codex_operator_adapter",
        "control_plane.executive_capability_packages",
    )
    probe = (
        "import importlib, json, os, sys; "
        "sys.path.insert(0, os.getcwd()); "
        f"names={source_modules!r} + ('pytest',); "
        "rows=[]; "
        "[(lambda m: rows.append((n, str(m.__file__), "
        "str(getattr(m, '__version__', '')))))(importlib.import_module(n)) "
        "for n in names]; "
        "print(json.dumps(rows, separators=(',', ':')))"
    )
    bound_interpreter = interpreter or _capture_cap_s1_interpreter_identity()
    completed = _run_cap_s1_python_observer_process(
        bound_interpreter,
        ("-c", probe),
        cwd=source_root,
        timeout=120,
        cleanup_observations=process_cleanup,
    )
    if completed.returncode != 0 or completed.stderr:
        raise CapS1ResultError("cap_s1_result_import_origin_invalid")
    rows = _strict_json_loads(
        completed.stdout,
        error="cap_s1_result_import_origin_invalid",
    )
    if type(rows) is not list or len(rows) != len(source_modules) + 1:
        raise CapS1ResultError("cap_s1_result_import_origin_invalid")
    safe_rows: list[tuple[str, str, str]] = []
    source_root_resolved = source_root.resolve()
    for index, row in enumerate(rows):
        if type(row) is not list or len(row) != 3:
            raise CapS1ResultError("cap_s1_result_import_origin_invalid")
        name, raw_origin, version = row
        if name != (*source_modules, "pytest")[index] or not isinstance(version, str):
            raise CapS1ResultError("cap_s1_result_import_origin_invalid")
        origin = Path(raw_origin).resolve()
        if index < len(source_modules):
            try:
                relative = origin.relative_to(source_root_resolved).as_posix()
            except ValueError as exc:
                raise CapS1ResultError("cap_s1_result_import_origin_invalid") from exc
            safe_origin = relative
        else:
            if origin == source_root_resolved or source_root_resolved in origin.parents:
                raise CapS1ResultError("cap_s1_result_import_origin_invalid")
            safe_origin = "trusted-interpreter-dependency:pytest"
        safe_rows.append((name, safe_origin, version))
    return _canonical_digest(tuple(safe_rows))


def _observe_cap_s1_local_suite(
    *,
    source_root: Path,
    source_manifest: Sequence[_CapS1SourceCopyEntry],
    output_root: Path,
    interpreter: "_CapS1InterpreterIdentity | None" = None,
    process_cleanup: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
) -> tuple[tuple[tuple[str, int, int, int, int], ...], str]:
    junit_path = output_root / "local-suite.xml"
    bound_interpreter = interpreter or _capture_cap_s1_interpreter_identity()
    binding = _build_cap_s1_pytest_binding(
        source_root=source_root,
        source_manifest=source_manifest,
        interpreter=bound_interpreter,
    )
    pytest_argv = (
        "-q",
        "--junitxml",
        str(junit_path),
        *CAP_S1_OBSERVER_TEST_MODULES,
    )
    fake_state = output_root / "fake-app-state.json"
    completed = _run_cap_s1_python_observer_process(
        bound_interpreter,
        _cap_s1_pytest_argv(binding, pytest_argv),
        cwd=source_root,
        timeout=3600,
        owned_state_path=fake_state,
        cleanup_observations=process_cleanup,
    )
    if completed.returncode == _CAP_S1_PYTEST_PROVENANCE_EXIT:
        raise CapS1ResultError("cap_s1_result_import_origin_invalid")
    try:
        junit_path.chmod(0o444)
    except OSError as exc:
        raise CapS1ResultError("cap_s1_result_local_proof_invalid") from exc
    rows = _parse_cap_s1_junit(junit_path, expected_scope=CAP_S1_OBSERVER_TEST_MODULES)
    if fake_state.exists():
        state = fake_state.lstat()
        if not stat.S_ISREG(state.st_mode) or stat.S_ISLNK(state.st_mode):
            raise CapS1ResultError("cap_s1_result_source_observation_unavailable")
        fake_state.unlink()
        if fake_state.exists():
            raise CapS1ResultError("cap_s1_result_source_observation_unavailable")
    if completed.returncode != 0 or any(row[3] or row[4] for row in rows):
        raise CapS1ResultError("cap_s1_result_local_proof_invalid")
    return rows, binding.evidence_digest


def _observe_cap_s1_diff(
    *,
    exact_head: str,
    protected_join: str,
    process_cleanup: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
) -> tuple[str, str, int, str]:
    argv = (
        "git",
        "--no-pager",
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--check",
        f"{protected_join}...{exact_head}",
        "--",
        *RESULT_CHANGED_PATHS,
    )
    completed = _run_cap_s1_observer_process(
        argv,
        cwd=REPO_ROOT,
        timeout=120,
        cleanup_observations=process_cleanup,
    )
    evidence = {
        "command_registry": "CAP_S1_FIXED_21_DIFF_CHECK",
        "returncode": completed.returncode,
        "stdout_bytes": len(completed.stdout.encode("utf-8")),
        "stderr_bytes": len(completed.stderr.encode("utf-8")),
        "head": exact_head,
        "protected": protected_join,
    }
    return (
        "diff-check",
        "PASSED" if completed.returncode == 0 else "FAILED",
        0 if completed.returncode == 0 else 1,
        _canonical_digest(evidence),
    )


def _write_cap_s1_owned_bytes(
    path: Path,
    payload: bytes,
    *,
    maximum: int = _CAP_S1_OBSERVER_MAX_OUTPUT_BYTES,
    create: bool = True,
) -> str:
    """Complete one bounded owned-file write, then reread/hash its postimage."""

    if len(payload) > maximum:
        raise CapS1ResultError("cap_s1_result_mutation_write_invalid")
    descriptor = -1
    try:
        flags = os.O_WRONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= (os.O_CREAT | os.O_EXCL) if create else os.O_TRUNC
        descriptor = os.open(path, flags, 0o600)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("short write")
            offset += written
        os.fsync(descriptor)
    except OSError as exc:
        raise CapS1ResultError("cap_s1_result_mutation_write_invalid") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    reread = path.read_bytes()
    if reread != payload:
        raise CapS1ResultError("cap_s1_result_mutation_write_invalid")
    return hashlib.sha256(reread).hexdigest()


def _observe_cap_s1_mutations(
    *,
    exact_head: str,
    scratch_root: Path,
    owned_roots: "list[_CapS1OwnedRootIdentity] | None" = None,
    process_cleanup: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
    interpreter: "_CapS1InterpreterIdentity | None" = None,
) -> tuple[tuple[str, str, str], ...]:
    node_by_id = dict(CAP_S1_OBSERVER_MUTANTS)
    assertion_by_id = {
        mutation_id: assertion
        for mutation_id, _node, assertion in CAP_S1_OBSERVER_MUTANT_ASSERTIONS
    }
    if set(node_by_id) != set(assertion_by_id):
        raise CapS1ResultError("cap_s1_result_mutation_registry_invalid")
    bound_interpreter = interpreter or _capture_cap_s1_interpreter_identity()
    rows: list[tuple[str, str, str]] = []
    for index, (mutation_id, relative_path, preimage, postimage) in enumerate(
        CAP_S1_OBSERVER_MUTANT_TRANSFORMS
    ):
        mutant_root = scratch_root / f"mutant-{index}"
        mutant_root.mkdir(mode=0o700)
        if owned_roots is not None:
            owned_roots.append(
                _register_cap_s1_owned_root(mutant_root, kind="observer-mutants")
            )
        source_root, source_manifest = _owned_cap_s1_source_copy(
            exact_head=exact_head,
            scratch_root=mutant_root,
            owned_roots=owned_roots,
            process_cleanup=process_cleanup,
        )
        historical_commit, historical_package_tree, historical_files = (
            _cap_s1_owned_git_package_expectation(source_root)
        )
        owned_git = _install_cap_s1_owned_git_context(
            source_repository_root=REPO_ROOT,
            source_root=source_root,
            exact_head=exact_head,
            historical_commit=historical_commit,
            expected_package_tree=historical_package_tree,
            expected_package_files=historical_files,
            cleanup_observations=process_cleanup,
        )
        try:
            target = source_root / relative_path
            original = target.read_bytes()
            original_digest = hashlib.sha256(original).hexdigest()
            decoded = original.decode("utf-8")
            if decoded.count(preimage) != 1 or postimage in decoded:
                raise CapS1ResultError("cap_s1_result_mutation_preimage_invalid")
            node = node_by_id[mutation_id]

            def _run(
                label: str,
                *,
                expected_canary_sha256: str,
            ) -> tuple[
                subprocess.CompletedProcess[str],
                _CapS1JunitCaseObservation,
                str,
            ]:
                junit = mutant_root / f"{label}.xml"
                binding = _build_cap_s1_pytest_binding(
                    source_root=source_root,
                    source_manifest=source_manifest,
                    interpreter=bound_interpreter,
                    expected_canary_sha256=expected_canary_sha256,
                )
                completed = _run_cap_s1_python_observer_process(
                    bound_interpreter,
                    _cap_s1_pytest_argv(
                        binding,
                        (
                            "-q",
                            "--junitxml",
                            str(junit),
                            node,
                        ),
                    ),
                    cwd=source_root,
                    timeout=600,
                    owned_state_path=mutant_root / f"{label}-fake-app-state.json",
                    cleanup_observations=process_cleanup,
                )
                if completed.returncode == _CAP_S1_PYTEST_PROVENANCE_EXIT:
                    raise CapS1ResultError("cap_s1_result_import_origin_invalid")
                try:
                    junit.chmod(0o444)
                except OSError as exc:
                    raise CapS1ResultError(
                        "cap_s1_result_mutation_proof_invalid"
                    ) from exc
                return (
                    completed,
                    _parse_cap_s1_mutation_junit(junit, expected_node=node),
                    binding.evidence_digest,
                )

            control, control_case, control_provenance = _run(
                "control", expected_canary_sha256=original_digest
            )
            if control.returncode != 0 or control_case.outcome != "PASSED":
                raise CapS1ResultError("cap_s1_result_mutation_proof_invalid")

            mutant: "subprocess.CompletedProcess[str] | None" = None
            mutant_case: "_CapS1JunitCaseObservation | None" = None
            mutant_provenance: "str | None" = None
            mutant_digest: "str | None" = None
            mutant_error: "BaseException | None" = None
            restored: "subprocess.CompletedProcess[str] | None" = None
            restored_case: "_CapS1JunitCaseObservation | None" = None
            restored_provenance: "str | None" = None
            restore_error: "BaseException | None" = None
            try:
                mutant_payload = decoded.replace(preimage, postimage).encode("utf-8")
                mutant_digest = _write_cap_s1_owned_bytes(
                    target,
                    mutant_payload,
                    create=False,
                )
                mutant, mutant_case, mutant_provenance = _run(
                    "mutant", expected_canary_sha256=mutant_digest
                )
            except BaseException as exc:  # restore across every child refusal
                mutant_error = exc
            finally:
                try:
                    restored_digest = _write_cap_s1_owned_bytes(
                        target,
                        original,
                        create=False,
                    )
                    if restored_digest != original_digest or target.read_bytes() != original:
                        raise CapS1ResultError("cap_s1_result_mutation_restore_invalid")
                    restored, restored_case, restored_provenance = _run(
                        "restored", expected_canary_sha256=original_digest
                    )
                except BaseException as exc:
                    restore_error = exc
            if restore_error is not None:
                raise CapS1ResultError("cap_s1_result_mutation_restore_invalid") from None
            if (
                restored is None
                or restored_case is None
                or restored.returncode != 0
                or restored_case.outcome != "PASSED"
            ):
                raise CapS1ResultError("cap_s1_result_mutation_restore_invalid")
            if mutant_error is not None:
                if isinstance(mutant_error, CapS1ResultError) and str(
                    mutant_error
                ) == "cap_s1_result_import_origin_invalid":
                    raise mutant_error
                raise CapS1ResultError("cap_s1_result_mutation_proof_invalid") from None
            assertion_signature = assertion_by_id[mutation_id]
            killed = (
                mutant is not None
                and mutant_case is not None
                and mutant.returncode == 1
                and mutant_case.outcome == "FAILURE"
                and f"AssertionError: {assertion_signature}" in mutant_case.detail
            )
            if (
                not killed
                or mutant_digest is None
                or mutant_provenance is None
                or restored_provenance is None
            ):
                raise CapS1ResultError("cap_s1_result_mutation_proof_invalid")
            rows.append(
                (
                    mutation_id,
                    "KILLED",
                    _canonical_digest(
                        {
                            "mutation_id": mutation_id,
                            "node": node,
                            "preimage": hashlib.sha256(preimage.encode()).hexdigest(),
                            "postimage": hashlib.sha256(postimage.encode()).hexdigest(),
                            "source_preimage": original_digest,
                            "source_postimage": mutant_digest,
                            "assertion_signature": assertion_signature,
                            "control": {
                                "returncode": control.returncode,
                                "case": _canonical_digest(dataclasses.asdict(control_case)),
                                "provenance": control_provenance,
                            },
                            "mutant": {
                                "returncode": mutant.returncode,
                                "case": _canonical_digest(dataclasses.asdict(mutant_case)),
                                "provenance": mutant_provenance,
                            },
                            "restored_control": {
                                "returncode": restored.returncode,
                                "case": _canonical_digest(dataclasses.asdict(restored_case)),
                                "provenance": restored_provenance,
                            },
                            "owned_git": {
                                "objects": owned_git.object_manifest_digest,
                                "filesystem": owned_git.filesystem_manifest_digest,
                                "archive": owned_git.archive_digest,
                                "archive_diagnostic": (
                                    owned_git.archive_diagnostic_digest
                                ),
                                "archive_files": (
                                    owned_git.archive_file_manifest_digest
                                ),
                                "historical_tree_paths": (
                                    owned_git.historical_tree_path_manifest_digest
                                ),
                                "historical_tree_objects": (
                                    owned_git.historical_tree_object_manifest_digest
                                ),
                                "environment": tuple(
                                    sorted(_CAP_S1_GIT_ENVIRONMENT.items())
                                ),
                            },
                            "restored": True,
                        }
                    ),
                )
            )
            _verify_cap_s1_owned_git_context(
                owned_git,
                cleanup_observations=process_cleanup,
            )
        except BaseException:
            raise
        finally:
            try:
                _remove_cap_s1_owned_git_context(
                    owned_git,
                    cleanup_observations=process_cleanup,
                )
            except BaseException as exc:
                raise CapS1ResultError("cap_s1_result_owned_git_invalid") from exc
            _verify_cap_s1_owned_source_manifest(
                source_root=source_root,
                manifest=source_manifest,
            )
    return tuple(sorted(rows))


@dataclasses.dataclass(frozen=True, kw_only=True)
class _CapS1SecretSourceEntry:
    index: int
    path: str
    mode: str
    blob: str
    size: int
    sha256: str


@dataclasses.dataclass(frozen=True, kw_only=True)
class _CapS1SecretScanObservation:
    status: str
    findings: int
    rule_counts: tuple[tuple[str, int], ...]
    source_file_count: int
    source_bytes: int
    binary_sha256: str
    binary_version: str
    rule_sha256: str
    evidence_digest: str
    process_cleanup: tuple[_CapS1OwnedProcessCleanupObservation, ...]


class _CapS1NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Make every redirect observable to the closed route validator."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _cap_s1_response_status(response: object) -> int:
    status = getattr(response, "status", None)
    if status is None:
        status = response.getcode()  # type: ignore[attr-defined]
    if type(status) is not int:
        raise CapS1ResultError("cap_s1_result_secret_supply_unavailable")
    return status


def _open_cap_s1_no_redirect(opener: object, request: urllib.request.Request):
    try:
        return opener.open(request, timeout=60)  # type: ignore[attr-defined]
    except urllib.error.HTTPError as exc:
        # A no-redirect opener represents the permitted initial 302 as an
        # HTTPError response.  Never propagate its URL-bearing exception text.
        if exc.code == 302:
            return exc
        raise CapS1ResultError("cap_s1_result_secret_supply_unavailable") from None
    except (OSError, ValueError, urllib.error.URLError):
        raise CapS1ResultError("cap_s1_result_secret_supply_unavailable") from None


def _close_cap_s1_response(response: object) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        close()


def _validate_cap_s1_release_redirect(*, initial_url: str, location: object) -> str:
    routes = {initial: destination for initial, destination, _asset_id in CAP_S1_GITLEAKS_RELEASE_ASSET_ROUTES}
    expected_destination = routes.get(initial_url)
    if expected_destination is None or not isinstance(location, str):
        raise CapS1ResultError("cap_s1_result_secret_supply_unavailable")
    try:
        encoded = location.encode("ascii")
    except UnicodeError:
        raise CapS1ResultError("cap_s1_result_secret_supply_unavailable") from None
    if (
        not encoded
        or len(encoded) > 8192
        or "\\" in location
        or any(character <= 0x20 or character == 0x7F for character in encoded)
    ):
        raise CapS1ResultError("cap_s1_result_secret_supply_unavailable")
    parts = urllib.parse.urlsplit(location)
    if (
        parts.scheme != "https"
        or parts.netloc != "release-assets.githubusercontent.com"
        or parts.username is not None
        or parts.password is not None
        or parts.fragment
        or not parts.query
        or "%" in parts.path
        or f"{parts.scheme}://{parts.netloc}{parts.path}" != expected_destination
    ):
        raise CapS1ResultError("cap_s1_result_secret_supply_unavailable")
    try:
        if parts.port is not None:
            raise CapS1ResultError("cap_s1_result_secret_supply_unavailable")
    except ValueError:
        raise CapS1ResultError("cap_s1_result_secret_supply_unavailable") from None
    return location


def _read_cap_s1_pinned_response(
    response: object,
    *,
    expected_url: str,
    expected_size: int,
    expected_sha256: str,
) -> bytes:
    try:
        if _cap_s1_response_status(response) != 200 or response.geturl() != expected_url:  # type: ignore[attr-defined]
            raise CapS1ResultError("cap_s1_result_secret_supply_unavailable")
        declared = response.headers.get("Content-Length")  # type: ignore[attr-defined]
        if declared is not None and int(declared) != expected_size:
            raise CapS1ResultError("cap_s1_result_secret_supply_invalid")
        chunks: list[bytes] = []
        remaining = expected_size + 1
        while remaining > 0:
            chunk = response.read(min(64 * 1024, remaining))  # type: ignore[attr-defined]
            if not chunk:
                break
            if not isinstance(chunk, bytes):
                raise CapS1ResultError("cap_s1_result_secret_supply_invalid")
            chunks.append(chunk)
            remaining -= len(chunk)
    except CapS1ResultError:
        raise
    except (OSError, TypeError, ValueError, urllib.error.URLError):
        raise CapS1ResultError("cap_s1_result_secret_supply_unavailable") from None
    payload = b"".join(chunks)
    if len(payload) != expected_size or hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise CapS1ResultError("cap_s1_result_secret_supply_invalid")
    return payload


def _download_cap_s1_pinned_bytes(*, url: str, expected_size: int, expected_sha256: str) -> bytes:
    """Fetch one source-owned URL through its finite, no-retry route."""

    allowed_urls = {
        CAP_S1_GITLEAKS_ARCHIVE_URL,
        CAP_S1_GITLEAKS_CHECKSUM_URL,
        CAP_S1_GITLEAKS_RULE_URL,
    }
    if url not in allowed_urls or urllib.parse.urlsplit(url).query:
        raise CapS1ResultError("cap_s1_result_secret_supply_unavailable")
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _CapS1NoRedirectHandler(),
    )
    initial_request = urllib.request.Request(
        url,
        headers={"User-Agent": "cap-s1-source-observer/1"},
    )
    first = _open_cap_s1_no_redirect(opener, initial_request)
    try:
        first_status = _cap_s1_response_status(first)
        if first_status == 200:
            return _read_cap_s1_pinned_response(
                first,
                expected_url=url,
                expected_size=expected_size,
                expected_sha256=expected_sha256,
            )
        if first_status != 302 or url == CAP_S1_GITLEAKS_RULE_URL:
            raise CapS1ResultError("cap_s1_result_secret_supply_unavailable")
        location = _validate_cap_s1_release_redirect(
            initial_url=url,
            location=first.headers.get("Location"),  # type: ignore[attr-defined]
        )
    finally:
        _close_cap_s1_response(first)

    redirected_request = urllib.request.Request(
        location,
        headers={"User-Agent": "cap-s1-source-observer/1"},
    )
    second = _open_cap_s1_no_redirect(opener, redirected_request)
    try:
        return _read_cap_s1_pinned_response(
            second,
            expected_url=location,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
        )
    finally:
        _close_cap_s1_response(second)


def _extract_cap_s1_gitleaks_binary(archive: bytes, *, destination: Path) -> str:
    """Validate canonical members and extract only the pinned executable."""

    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
            members = bundle.getmembers()
            names = tuple(sorted(member.name for member in members))
            if names != tuple(sorted(CAP_S1_GITLEAKS_ARCHIVE_MEMBERS)):
                raise ValueError("archive member census")
            if len(set(names)) != len(names):
                raise ValueError("archive duplicate")
            for member in members:
                path = Path(member.name)
                if (
                    path.is_absolute()
                    or len(path.parts) != 1
                    or ".." in path.parts
                    or member.issym()
                    or member.islnk()
                    or not member.isfile()
                ):
                    raise ValueError("archive member type")
            executable = bundle.getmember(CAP_S1_GITLEAKS_BINARY_MEMBER)
            reader = bundle.extractfile(executable)
            if reader is None:
                raise ValueError("archive executable")
            binary = reader.read(64 * 1024 * 1024 + 1)
    except (OSError, KeyError, tarfile.TarError, ValueError) as exc:
        raise CapS1ResultError("cap_s1_result_secret_supply_invalid") from exc
    if not binary or len(binary) > 64 * 1024 * 1024:
        raise CapS1ResultError("cap_s1_result_secret_supply_invalid")
    digest = _write_cap_s1_owned_bytes(destination, binary, maximum=64 * 1024 * 1024)
    destination.chmod(0o700)
    reread = destination.read_bytes()
    if hashlib.sha256(reread).hexdigest() != digest or not os.access(destination, os.X_OK):
        raise CapS1ResultError("cap_s1_result_secret_supply_invalid")
    return digest


def _cap_s1_secret_child_environment(*, owned_root: Path) -> dict[str, str]:
    owned_root.mkdir(mode=0o700)
    home = owned_root / "home"
    temporary = owned_root / "tmp"
    home.mkdir(mode=0o700)
    temporary.mkdir(mode=0o700)
    return {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "NO_COLOR": "1",
        "PATH": "/usr/bin:/bin",
        "TMPDIR": str(temporary),
    }


def _run_cap_s1_secret_process(
    argv: Sequence[str],
    *,
    cwd: Path,
    environment_root: Path,
    stdout_path: Path,
    stderr_path: Path,
    timeout: int,
    cleanup_observations: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
) -> int:
    """Run the fixed scanner/version process with private bounded streams."""

    return _run_cap_s1_owned_process(
        argv,
        cwd=cwd,
        environment=_cap_s1_secret_child_environment(owned_root=environment_root),
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        timeout=timeout,
        maximum_stream_bytes=_CAP_S1_SECRET_MAX_STREAM_BYTES,
        error="cap_s1_result_secret_scan_incomplete",
        cleanup_observations=cleanup_observations,
    )


def _supply_cap_s1_gitleaks(
    *,
    owned_root: Path,
    cleanup_observations: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
    owned_roots: "list[_CapS1OwnedRootIdentity] | None" = None,
) -> tuple[Path, str, Path]:
    supply_root = owned_root / "supply"
    supply_root.mkdir(mode=0o700)
    if owned_roots is not None:
        owned_roots.append(_register_cap_s1_owned_root(supply_root, kind="secret-supply"))
    archive = _download_cap_s1_pinned_bytes(
        url=CAP_S1_GITLEAKS_ARCHIVE_URL,
        expected_size=CAP_S1_GITLEAKS_ARCHIVE_BYTES,
        expected_sha256=CAP_S1_GITLEAKS_ARCHIVE_SHA256,
    )
    checksums = _download_cap_s1_pinned_bytes(
        url=CAP_S1_GITLEAKS_CHECKSUM_URL,
        expected_size=CAP_S1_GITLEAKS_CHECKSUM_BYTES,
        expected_sha256=CAP_S1_GITLEAKS_CHECKSUM_SHA256,
    )
    checksum_lines = checksums.decode("utf-8").splitlines()
    expected_checksum_line = (
        f"{CAP_S1_GITLEAKS_ARCHIVE_SHA256}  {CAP_S1_GITLEAKS_ARCHIVE_NAME}"
    )
    if checksum_lines.count(expected_checksum_line) != 1:
        raise CapS1ResultError("cap_s1_result_secret_supply_invalid")
    rule_bytes = _download_cap_s1_pinned_bytes(
        url=CAP_S1_GITLEAKS_RULE_URL,
        expected_size=CAP_S1_GITLEAKS_RULE_BYTES,
        expected_sha256=CAP_S1_GITLEAKS_RULE_SHA256,
    )
    try:
        rule_text = rule_bytes.decode("utf-8")
    except UnicodeError as exc:
        raise CapS1ResultError("cap_s1_result_secret_supply_invalid") from exc
    if rule_text.count("[[rules]]") != CAP_S1_GITLEAKS_RULE_COUNT:
        raise CapS1ResultError("cap_s1_result_secret_supply_invalid")
    rule_path = supply_root / "gitleaks.toml"
    rule_digest = _write_cap_s1_owned_bytes(
        rule_path,
        rule_bytes,
        maximum=CAP_S1_GITLEAKS_RULE_BYTES,
    )
    rule_path.chmod(0o400)
    if rule_digest != CAP_S1_GITLEAKS_RULE_SHA256:
        raise CapS1ResultError("cap_s1_result_secret_supply_invalid")
    binary_path = supply_root / "gitleaks"
    binary_digest = _extract_cap_s1_gitleaks_binary(archive, destination=binary_path)
    version_stdout = supply_root / "version.stdout"
    version_stderr = supply_root / "version.stderr"
    version_code = _run_cap_s1_secret_process(
        (str(binary_path), "version"),
        cwd=supply_root,
        environment_root=supply_root / "version-environment",
        stdout_path=version_stdout,
        stderr_path=version_stderr,
        timeout=30,
        cleanup_observations=cleanup_observations,
    )
    try:
        version = version_stdout.read_text(encoding="utf-8").strip()
        version_error = version_stderr.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CapS1ResultError("cap_s1_result_secret_supply_invalid") from exc
    if version_code != 0 or version != CAP_S1_GITLEAKS_VERSION or version_error:
        raise CapS1ResultError("cap_s1_result_secret_supply_invalid")
    if hashlib.sha256(binary_path.read_bytes()).hexdigest() != binary_digest:
        raise CapS1ResultError("cap_s1_result_secret_supply_invalid")
    return binary_path, binary_digest, rule_path


def _stage_cap_s1_secret_source(
    *,
    exact_head: str,
    protected_join: str,
    owned_root: Path,
    cleanup_observations: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
    owned_roots: "list[_CapS1OwnedRootIdentity] | None" = None,
) -> tuple[Path, tuple[_CapS1SecretSourceEntry, ...], int]:
    """Materialize all 21 immutable final blobs with a closed byte census."""

    merge_base_run = _run_cap_s1_observer_process(
        ("git", "merge-base", protected_join, exact_head),
        cwd=REPO_ROOT,
        timeout=30,
        cleanup_observations=cleanup_observations,
    )
    merge_base = merge_base_run.stdout.strip()
    changed_run = _run_cap_s1_observer_process(
        ("git", "diff", "--name-only", f"{merge_base}...{exact_head}"),
        cwd=REPO_ROOT,
        timeout=30,
        cleanup_observations=cleanup_observations,
    )
    if (
        merge_base_run.returncode != 0
        or merge_base_run.stderr
        or changed_run.returncode != 0
        or changed_run.stderr
    ):
        raise CapS1ResultError("cap_s1_result_secret_source_unavailable")
    changed = changed_run.stdout.splitlines()
    if not _result_is_hex40(merge_base) or not set(changed).issubset(RESULT_CHANGED_PATHS):
        raise CapS1ResultError("cap_s1_result_secret_source_path_boundary")

    source_root = owned_root / "source"
    source_root.mkdir(mode=0o700)
    if owned_roots is not None:
        owned_roots.append(_register_cap_s1_owned_root(source_root, kind="secret-source"))
    entries: list[_CapS1SecretSourceEntry] = []
    total_bytes = 0
    for index, relative in enumerate(RESULT_CHANGED_PATHS, start=1):
        try:
            metadata_run = _run_cap_s1_observer_process(
                ("git", "ls-tree", "-l", exact_head, "--", relative),
                cwd=REPO_ROOT,
                timeout=30,
                cleanup_observations=cleanup_observations,
            )
            if metadata_run.returncode != 0 or metadata_run.stderr:
                raise ValueError("tree read")
            metadata = metadata_run.stdout.rstrip("\n")
            prefix, separator, observed_path = metadata.partition("\t")
            fields = prefix.split()
            if not separator or observed_path != relative or len(fields) != 4:
                raise ValueError("tree row")
            mode, kind, blob, raw_size = fields
            size = int(raw_size)
            if (
                mode not in {"100644", "100755"}
                or kind != "blob"
                or not _result_is_hex40(blob)
                or size < 0
                or size > _CAP_S1_SECRET_MAX_FILE_BYTES
            ):
                raise ValueError("tree identity")
            payload_run = _run_cap_s1_observer_bytes(
                ("git", "cat-file", "blob", blob),
                cwd=REPO_ROOT,
                timeout=30,
                maximum_stream_bytes=_CAP_S1_SECRET_MAX_FILE_BYTES,
                cleanup_observations=cleanup_observations,
            )
            if payload_run.returncode != 0 or payload_run.stderr:
                raise ValueError("blob read")
            payload = payload_run.stdout
            if len(payload) != size:
                raise ValueError("blob size")
            payload.decode("utf-8")
        except (OSError, UnicodeError, ValueError, subprocess.SubprocessError) as exc:
            raise CapS1ResultError("cap_s1_result_secret_source_unsupported") from exc
        total_bytes += size
        if total_bytes > _CAP_S1_SECRET_MAX_CLOSURE_BYTES:
            raise CapS1ResultError("cap_s1_result_secret_source_scope_exceeded")
        destination = source_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = _write_cap_s1_owned_bytes(
            destination,
            payload,
            maximum=_CAP_S1_SECRET_MAX_FILE_BYTES,
        )
        destination.chmod(0o500 if mode == "100755" else 0o400)
        entries.append(
            _CapS1SecretSourceEntry(
                index=index,
                path=relative,
                mode=mode,
                blob=blob,
                size=size,
                sha256=digest,
            )
        )
    if len(entries) != len(RESULT_CHANGED_PATHS):
        raise CapS1ResultError("cap_s1_result_secret_source_incomplete")
    return source_root, tuple(entries), total_bytes


def _assemble_cap_s1_secret_controls(
    *,
    owned_root: Path,
    owned_roots: "list[_CapS1OwnedRootIdentity] | None" = None,
) -> tuple[tuple[str, Path, int, str], ...]:
    control_root = owned_root / "positive-controls"
    control_root.mkdir(mode=0o700)
    if owned_roots is not None:
        owned_roots.append(_register_cap_s1_owned_root(control_root, kind="secret-controls"))
    rows: list[tuple[str, Path, int, str]] = []
    for rule_id, recipe, expected_count, expected_digest in CAP_S1_SECRET_CONTROL_RECIPES:
        payload = b"".join(segment * repeats for segment, repeats in recipe)
        if hashlib.sha256(payload).hexdigest() != expected_digest:
            raise CapS1ResultError("cap_s1_result_secret_control_invalid")
        path = control_root / f"{rule_id}.txt"
        digest = _write_cap_s1_owned_bytes(path, payload)
        path.chmod(0o400)
        rows.append((rule_id, path, expected_count, digest))
    return tuple(rows)


_CAP_S1_GITLEAKS_FINDING_KEYS = {
    "RuleID", "Description", "StartLine", "EndLine", "StartColumn", "EndColumn",
    "Match", "Secret", "File", "SymlinkFile", "Commit", "Entropy", "Author",
    "Email", "Date", "Message", "Tags", "Fingerprint",
}


def _parse_cap_s1_gitleaks_report(
    report_bytes: bytes,
    *,
    allowed_rule_ids: "set[str] | None" = None,
) -> tuple[tuple[str, int], ...]:
    raw = _strict_json_loads(
        report_bytes,
        error="cap_s1_result_secret_report_invalid",
    )
    if type(raw) is not list or len(raw) > 10_000:
        raise CapS1ResultError("cap_s1_result_secret_report_invalid")
    counts: dict[str, int] = {}
    for finding in raw:
        if type(finding) is not dict:
            raise CapS1ResultError("cap_s1_result_secret_report_invalid")
        keys = set(finding)
        if not _CAP_S1_GITLEAKS_FINDING_KEYS.issubset(keys) or not keys.issubset(
            _CAP_S1_GITLEAKS_FINDING_KEYS | {"Link", "Fragment"}
        ):
            raise CapS1ResultError("cap_s1_result_secret_report_invalid")
        rule_id = finding.get("RuleID")
        if not _result_safe_manifest_label(rule_id):
            raise CapS1ResultError("cap_s1_result_secret_report_invalid")
        if allowed_rule_ids is not None and rule_id not in allowed_rule_ids:
            raise CapS1ResultError("cap_s1_result_secret_report_invalid")
        if finding.get("Secret") != "REDACTED":
            raise CapS1ResultError("cap_s1_result_secret_report_unredacted")
        if not _result_positive_int(finding.get("StartLine"), maximum=10_000_000):
            raise CapS1ResultError("cap_s1_result_secret_report_invalid")
        counts[rule_id] = counts.get(rule_id, 0) + 1
    return tuple(sorted(counts.items()))


_CAP_S1_GITLEAKS_INCOMPLETE_MARKERS = (
    "partial scan",
    "skipping directory",
    "skipping file: could not get info",
    "skipping file: too large",
    "skipping file: permission denied",
    "skipping file: global allowlist",
    "skipping symlink",
    "skipping unknown archive type",
    "skipping archive:",
    "skipping binary file",
    "skipping fragment: size",
    "could not read file",
    "issue reading file",
    "failed scan directory",
)


def _parse_cap_s1_gitleaks_coverage(
    log_bytes: bytes,
    *,
    source_root: Path,
    manifest: Sequence[_CapS1SecretSourceEntry],
    expected_bytes: int,
) -> str:
    try:
        text = log_bytes.decode("utf-8")
    except UnicodeError as exc:
        raise CapS1ResultError("cap_s1_result_secret_scan_incomplete") from exc
    if "\x1b" in text:
        raise CapS1ResultError("cap_s1_result_secret_scan_incomplete")
    lowered = text.casefold()
    if any(marker in lowered for marker in _CAP_S1_GITLEAKS_INCOMPLETE_MARKERS):
        raise CapS1ResultError("cap_s1_result_secret_scan_incomplete")
    totals = re.findall(r"scanned ~([0-9]+) bytes", text)
    if totals != [str(expected_bytes)]:
        raise CapS1ResultError("cap_s1_result_secret_scan_incomplete")
    observed: set[str] = set()
    for line in text.splitlines():
        if "scanning path" not in line:
            continue
        match = re.search(r'path=(?:"([^"]+)"|(\S+))', line)
        if match is None:
            raise CapS1ResultError("cap_s1_result_secret_scan_incomplete")
        raw_path = match.group(1) or match.group(2)
        try:
            relative = Path(raw_path).resolve().relative_to(source_root.resolve()).as_posix()
        except ValueError as exc:
            raise CapS1ResultError("cap_s1_result_secret_scan_incomplete") from exc
        observed.add(relative)
    expected_nonempty = {entry.path for entry in manifest if entry.size > 0}
    if observed != expected_nonempty:
        raise CapS1ResultError("cap_s1_result_secret_scan_incomplete")
    return _canonical_digest(
        {
            "paths": tuple(sorted(observed)),
            "bytes": expected_bytes,
            "incomplete_markers": False,
        }
    )


def _verify_cap_s1_secret_manifest(
    *, source_root: Path, manifest: Sequence[_CapS1SecretSourceEntry]
) -> None:
    for entry in manifest:
        path = source_root / entry.path
        try:
            state = path.lstat()
            payload = path.read_bytes()
        except OSError as exc:
            raise CapS1ResultError("cap_s1_result_secret_source_changed") from exc
        if (
            not stat.S_ISREG(state.st_mode)
            or stat.S_ISLNK(state.st_mode)
            or len(payload) != entry.size
            or hashlib.sha256(payload).hexdigest() != entry.sha256
        ):
            raise CapS1ResultError("cap_s1_result_secret_source_changed")


def _run_cap_s1_gitleaks_dir(
    *,
    binary_path: Path,
    rule_path: Path,
    target_root: Path,
    invocation_root: Path,
    cleanup_observations: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
    owned_roots: "list[_CapS1OwnedRootIdentity] | None" = None,
    cleanup_kind: str = "secret-controls",
) -> tuple[int, bytes, bytes]:
    invocation_root.mkdir(mode=0o700)
    if owned_roots is not None:
        owned_roots.append(
            _register_cap_s1_owned_root(invocation_root, kind=cleanup_kind)
        )
    ignore_path = invocation_root / "empty-ignore"
    _write_cap_s1_owned_bytes(ignore_path, b"")
    ignore_path.chmod(0o400)
    report_path = invocation_root / "report.json"
    stdout_path = invocation_root / "stdout.private"
    stderr_path = invocation_root / "stderr.private"
    argv = (
        str(binary_path),
        "dir",
        str(target_root),
        "--config",
        str(rule_path),
        "--redact=100",
        "--no-banner",
        "--no-color",
        "--log-level",
        "trace",
        "--report-format",
        "json",
        "--report-path",
        str(report_path),
        "--exit-code",
        "10",
        "--ignore-gitleaks-allow",
        "--gitleaks-ignore-path",
        str(ignore_path),
        "--max-target-megabytes",
        "0",
        "--max-archive-depth",
        "0",
        "--max-decode-depth",
        "5",
        "--timeout",
        "120",
    )
    return_code = _run_cap_s1_secret_process(
        argv,
        cwd=invocation_root,
        environment_root=invocation_root / "environment",
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        timeout=150,
        cleanup_observations=cleanup_observations,
    )
    try:
        report_state = report_path.lstat()
        report = report_path.read_bytes()
        stdout = stdout_path.read_bytes()
        stderr = stderr_path.read_bytes()
    except OSError as exc:
        raise CapS1ResultError("cap_s1_result_secret_scan_incomplete") from exc
    if (
        not stat.S_ISREG(report_state.st_mode)
        or report_state.st_size != len(report)
        or len(report) > _CAP_S1_SECRET_MAX_STREAM_BYTES
        or len(stdout) > _CAP_S1_SECRET_MAX_STREAM_BYTES
        or len(stderr) > _CAP_S1_SECRET_MAX_STREAM_BYTES
    ):
        raise CapS1ResultError("cap_s1_result_secret_scan_incomplete")
    return return_code, report, stdout + b"\n" + stderr


def _control_manifest(
    controls: Sequence[tuple[str, Path, int, str]],
) -> tuple[_CapS1SecretSourceEntry, ...]:
    return tuple(
        _CapS1SecretSourceEntry(
            index=index,
            path=path.name,
            mode="100644",
            blob="0" * 40,
            size=path.stat().st_size,
            sha256=digest,
        )
        for index, (_rule_id, path, _expected, digest) in enumerate(controls, start=1)
    )


def _observe_cap_s1_secret_scan(
    *,
    exact_head: str,
    protected_join: str,
    owned_root: Path,
    owned_roots: "list[_CapS1OwnedRootIdentity] | None" = None,
    process_cleanup: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
) -> _CapS1SecretScanObservation:
    local_process_cleanup: list[_CapS1OwnedProcessCleanupObservation] = []
    process_sink = process_cleanup if process_cleanup is not None else local_process_cleanup
    binary_path, binary_digest, rule_path = _supply_cap_s1_gitleaks(
        owned_root=owned_root,
        cleanup_observations=process_sink,
        owned_roots=owned_roots,
    )
    source_root, source_manifest, source_bytes = _stage_cap_s1_secret_source(
        exact_head=exact_head,
        protected_join=protected_join,
        owned_root=owned_root,
        cleanup_observations=process_sink,
        owned_roots=owned_roots,
    )
    _verify_cap_s1_secret_manifest(source_root=source_root, manifest=source_manifest)

    control_owner = owned_root / "controls"
    control_owner.mkdir(mode=0o700)
    if owned_roots is not None:
        owned_roots.append(_register_cap_s1_owned_root(control_owner, kind="secret-controls"))
    controls = _assemble_cap_s1_secret_controls(
        owned_root=control_owner,
        owned_roots=owned_roots,
    )
    control_root = control_owner / "positive-controls"
    control_manifest = _control_manifest(controls)
    control_bytes = sum(entry.size for entry in control_manifest)
    control_code, control_report, control_log = _run_cap_s1_gitleaks_dir(
        binary_path=binary_path,
        rule_path=rule_path,
        target_root=control_root,
        invocation_root=control_owner / "positive-run",
        cleanup_observations=process_sink,
        owned_roots=owned_roots,
    )
    control_counts = _parse_cap_s1_gitleaks_report(
        control_report,
        allowed_rule_ids={rule_id for rule_id, _path, _count, _digest in controls},
    )
    expected_control_counts = tuple(
        sorted((rule_id, expected_count) for rule_id, _path, expected_count, _digest in controls)
    )
    _parse_cap_s1_gitleaks_coverage(
        control_log,
        source_root=control_root,
        manifest=control_manifest,
        expected_bytes=control_bytes,
    )
    if control_code != 10 or control_counts != expected_control_counts:
        raise CapS1ResultError("cap_s1_result_secret_control_invalid")

    ignored_root = control_owner / "ignored-looking-control"
    ignored_root.mkdir(mode=0o700)
    if owned_roots is not None:
        owned_roots.append(_register_cap_s1_owned_root(ignored_root, kind="secret-controls"))
    stripe_recipe = next(
        recipe
        for rule_id, recipe, _expected, _digest in CAP_S1_SECRET_CONTROL_RECIPES
        if rule_id == "stripe-access-token"
    )
    ignored_payload = b"# gitleaks:allow\n" + b"".join(
        segment * repeats for segment, repeats in stripe_recipe
    )
    ignored_path = ignored_root / "ignored-looking.txt"
    ignored_digest = _write_cap_s1_owned_bytes(ignored_path, ignored_payload)
    ignored_path.chmod(0o400)
    ignored_manifest = (
        _CapS1SecretSourceEntry(
            index=1,
            path=ignored_path.name,
            mode="100644",
            blob="0" * 40,
            size=len(ignored_payload),
            sha256=ignored_digest,
        ),
    )
    ignored_code, ignored_report, ignored_log = _run_cap_s1_gitleaks_dir(
        binary_path=binary_path,
        rule_path=rule_path,
        target_root=ignored_root,
        invocation_root=control_owner / "ignored-looking-run",
        cleanup_observations=process_sink,
        owned_roots=owned_roots,
    )
    ignored_counts = _parse_cap_s1_gitleaks_report(
        ignored_report,
        allowed_rule_ids={"stripe-access-token"},
    )
    _parse_cap_s1_gitleaks_coverage(
        ignored_log,
        source_root=ignored_root,
        manifest=ignored_manifest,
        expected_bytes=len(ignored_payload),
    )
    if ignored_code != 10 or ignored_counts != (("stripe-access-token", 1),):
        raise CapS1ResultError("cap_s1_result_secret_control_invalid")

    negative_root = control_owner / "negative-control"
    negative_root.mkdir(mode=0o700)
    if owned_roots is not None:
        owned_roots.append(_register_cap_s1_owned_root(negative_root, kind="secret-controls"))
    negative_path = negative_root / "negative.txt"
    negative_payload = b"CAP-S1 deterministic negative control: no credential material.\n"
    negative_digest = _write_cap_s1_owned_bytes(negative_path, negative_payload)
    negative_path.chmod(0o400)
    negative_manifest = (
        _CapS1SecretSourceEntry(
            index=1,
            path=negative_path.name,
            mode="100644",
            blob="0" * 40,
            size=len(negative_payload),
            sha256=negative_digest,
        ),
    )
    negative_code, negative_report, negative_log = _run_cap_s1_gitleaks_dir(
        binary_path=binary_path,
        rule_path=rule_path,
        target_root=negative_root,
        invocation_root=control_owner / "negative-run",
        cleanup_observations=process_sink,
        owned_roots=owned_roots,
    )
    if negative_code != 0 or _parse_cap_s1_gitleaks_report(negative_report):
        raise CapS1ResultError("cap_s1_result_secret_control_invalid")
    _parse_cap_s1_gitleaks_coverage(
        negative_log,
        source_root=negative_root,
        manifest=negative_manifest,
        expected_bytes=len(negative_payload),
    )

    actual_code, actual_report, actual_log = _run_cap_s1_gitleaks_dir(
        binary_path=binary_path,
        rule_path=rule_path,
        target_root=source_root,
        invocation_root=owned_root / "source-run",
        cleanup_observations=process_sink,
        owned_roots=owned_roots,
        cleanup_kind="secret-output",
    )
    actual_counts = _parse_cap_s1_gitleaks_report(actual_report)
    coverage_digest = _parse_cap_s1_gitleaks_coverage(
        actual_log,
        source_root=source_root,
        manifest=source_manifest,
        expected_bytes=source_bytes,
    )
    _verify_cap_s1_secret_manifest(source_root=source_root, manifest=source_manifest)
    if (
        hashlib.sha256(binary_path.read_bytes()).hexdigest() != binary_digest
        or hashlib.sha256(rule_path.read_bytes()).hexdigest() != CAP_S1_GITLEAKS_RULE_SHA256
    ):
        raise CapS1ResultError("cap_s1_result_secret_supply_changed")
    findings = sum(count for _rule_id, count in actual_counts)
    if actual_code == 10 and findings > 0:
        status = "FINDINGS"
    elif actual_code == 0 and findings == 0:
        status = "COMPLETE_CLEAN"
    else:
        raise CapS1ResultError("cap_s1_result_secret_scan_incomplete")
    observation = {
        "policy": "CAP_S1_GITLEAKS_8_30_1_FINAL_21_V1",
        "exact_head": exact_head,
        "protected_join": protected_join,
        "source_manifest": tuple(dataclasses.astuple(entry) for entry in source_manifest),
        "source_bytes": source_bytes,
        "control_counts": control_counts,
        "negative_clean": True,
        "coverage_digest": coverage_digest,
        "status": status,
        "rule_counts": actual_counts,
        "binary_sha256": binary_digest,
        "binary_version": CAP_S1_GITLEAKS_VERSION,
        "rule_sha256": CAP_S1_GITLEAKS_RULE_SHA256,
        "process_cleanup": tuple(dataclasses.astuple(row) for row in process_sink),
    }
    result = _CapS1SecretScanObservation(
        status=status,
        findings=findings,
        rule_counts=actual_counts,
        source_file_count=len(source_manifest),
        source_bytes=source_bytes,
        binary_sha256=binary_digest,
        binary_version=CAP_S1_GITLEAKS_VERSION,
        rule_sha256=CAP_S1_GITLEAKS_RULE_SHA256,
        evidence_digest=_canonical_digest(observation),
        process_cleanup=tuple(process_sink),
    )
    if status != "COMPLETE_CLEAN":
        raise CapS1ResultError("cap_s1_result_secret_scan_findings")
    return result


def _github_api_list(
    endpoint: str,
    *,
    cleanup_observations: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
) -> list[Any]:
    """Fresh bounded GitHub list read with the same strict JSON boundary."""

    try:
        completed = _run_cap_s1_observer_process(
            ("gh", "api", endpoint),
            cwd=REPO_ROOT,
            timeout=30,
            cleanup_observations=cleanup_observations,
            github_environment=True,
        )
        if completed.returncode != 0 or completed.stderr:
            raise CapS1ResultError("cap_s1_result_github_evidence_unavailable")
        payload = _strict_json_loads(
            completed.stdout,
            error="cap_s1_result_github_evidence_unavailable",
        )
    except (OSError, subprocess.SubprocessError, CapS1ResultError) as exc:
        raise CapS1ResultError("cap_s1_result_github_evidence_unavailable") from exc
    if type(payload) is not list or len(payload) > 100:
        raise CapS1ResultError("cap_s1_result_github_evidence_unavailable")
    return payload


def _observe_cap_s1_codeql(
    *,
    exact_head: str,
    process_cleanup: "list[_CapS1OwnedProcessCleanupObservation] | None" = None,
) -> tuple[tuple[str, str, int, str], ...]:
    """Authenticate fixed exact-head CodeQL/check and code-scanning reads."""

    def _get(endpoint: str) -> Any:
        if process_cleanup is None:
            return _github_api_json(endpoint)
        return _github_api_json(endpoint, cleanup_observations=process_cleanup)

    def _get_list(endpoint: str) -> list[Any]:
        if process_cleanup is None:
            return _github_api_list(endpoint)
        return _github_api_list(endpoint, cleanup_observations=process_cleanup)

    def _pr_binding() -> tuple[str, str, str, str, str]:
        pull = _get(
            f"repos/{_RESULT_REPOSITORY}/pulls/{_RESULT_PR_NUMBER}"
        )
        git_ref = _get(
            f"repos/{_RESULT_REPOSITORY}/git/ref/pull/{_RESULT_PR_NUMBER}/head"
        )
        head = pull.get("head")
        ref_object = git_ref.get("object")
        binding = (
            str(pull.get("number", "")),
            head.get("sha") if type(head) is dict else "",
            head.get("ref") if type(head) is dict else "",
            git_ref.get("ref", ""),
            ref_object.get("sha") if type(ref_object) is dict else "",
        )
        if (
            binding
            != (
                str(_RESULT_PR_NUMBER),
                exact_head,
                _CAP_S1_PR_BRANCH,
                _CAP_S1_PR_HEAD_REF,
                exact_head,
            )
            or type(ref_object) is not dict
            or ref_object.get("type") != "commit"
        ):
            raise CapS1ResultError("cap_s1_result_security_proof_invalid")
        return binding

    before_binding = _pr_binding()

    check_rows: list[dict[str, Any]] = []
    expected_total: "int | None" = None
    for page in range(1, 5):
        payload = _get(
            f"repos/{_RESULT_REPOSITORY}/commits/{exact_head}/check-runs"
            f"?per_page=100&page={page}"
        )
        total = payload.get("total_count")
        rows = payload.get("check_runs")
        if (
            not _result_nonnegative_int(total)
            or total > _RESULT_MAX_HOSTED_JOBS
            or type(rows) is not list
        ):
            raise CapS1ResultError("cap_s1_result_security_proof_unavailable")
        if expected_total is None:
            expected_total = total
        elif expected_total != total:
            raise CapS1ResultError("cap_s1_result_security_proof_unavailable")
        for row in rows:
            if type(row) is not dict:
                raise CapS1ResultError("cap_s1_result_security_proof_unavailable")
            check_rows.append(row)
        if len(check_rows) >= total:
            break
    if expected_total is None or len(check_rows) != expected_total:
        raise CapS1ResultError("cap_s1_result_security_proof_unavailable")

    expected_checks = dict(_CAP_S1_CODEQL_CHECKS)
    category_by_name = {name: category for category, name in _CAP_S1_CODEQL_CHECKS}
    codeql_rows: list[dict[str, Any]] = []
    seen_categories: set[str] = set()
    for row in check_rows:
        app = row.get("app")
        name = row.get("name")
        if name not in category_by_name:
            continue
        category = category_by_name[name]
        check_id = row.get("id")
        if (
            category in seen_categories
            or not _result_positive_int(check_id)
            or row.get("head_sha") != exact_head
            or type(app) is not dict
            or (app.get("id"), app.get("slug")) != _CAP_S1_CODEQL_APP
        ):
            raise CapS1ResultError("cap_s1_result_security_proof_invalid")
        detail = _get(
            f"repos/{_RESULT_REPOSITORY}/check-runs/{check_id}"
        )
        detail_app = detail.get("app")
        details_url = detail.get("details_url")
        details_match = (
            re.fullmatch(
                rf"https://github\.com/{re.escape(_RESULT_REPOSITORY)}"
                rf"/actions/runs/([1-9][0-9]*)/job/{check_id}",
                details_url,
            )
            if isinstance(details_url, str)
            else None
        )
        if (
            detail.get("id") != check_id
            or detail.get("name") != name
            or detail.get("head_sha") != exact_head
            or type(detail_app) is not dict
            or (detail_app.get("id"), detail_app.get("slug")) != _CAP_S1_CODEQL_APP
            or str(detail.get("status", "")).upper() != "COMPLETED"
            or str(detail.get("conclusion", "")).upper() != "SUCCESS"
            or details_match is None
        ):
            raise CapS1ResultError("cap_s1_result_security_proof_invalid")
        run_id = details_match.group(1)
        run = _get(
            f"repos/{_RESULT_REPOSITORY}/actions/runs/{run_id}"
        )
        if (
            str(run.get("id", "")) != run_id
            or run.get("head_sha") != exact_head
            or str(run.get("status", "")).upper() != "COMPLETED"
            or str(run.get("conclusion", "")).upper() != "SUCCESS"
        ):
            raise CapS1ResultError("cap_s1_result_security_proof_invalid")
        seen_categories.add(category)
        codeql_rows.append(
            {
                "category": category,
                "id": check_id,
                "name": name,
                "app_id": _CAP_S1_CODEQL_APP[0],
                "app_slug": _CAP_S1_CODEQL_APP[1],
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
                "head": exact_head,
                "run_id": run_id,
            }
        )
    if seen_categories != set(expected_checks):
        raise CapS1ResultError("cap_s1_result_security_proof_unavailable")

    encoded_ref = urllib.parse.quote(_CAP_S1_PR_HEAD_REF, safe="")
    analyses: list[dict[str, Any]] = []
    for page in range(1, 5):
        analysis_page = _get_list(
            f"repos/{_RESULT_REPOSITORY}/code-scanning/analyses"
            f"?ref={encoded_ref}&per_page=100&page={page}"
        )
        analyses.extend(analysis_page)
        if len(analysis_page) < 100:
            break
    else:
        raise CapS1ResultError("cap_s1_result_security_proof_unavailable")

    alerts: list[dict[str, Any]] = []
    for page in range(1, 5):
        alert_page = _get_list(
            f"repos/{_RESULT_REPOSITORY}/code-scanning/alerts"
            f"?pr={_RESULT_PR_NUMBER}&state=open&per_page=100&page={page}"
        )
        if any(type(row) is not dict for row in alert_page):
            raise CapS1ResultError("cap_s1_result_security_proof_unavailable")
        alerts.extend(alert_page)
        if len(alert_page) < 100:
            break
    else:
        raise CapS1ResultError("cap_s1_result_security_proof_unavailable")

    analysis_rows: list[dict[str, Any]] = []
    seen_analysis_categories: set[str] = set()
    expected_categories = set(expected_checks)
    for row in analyses:
        tool = row.get("tool") if type(row) is dict else None
        category = row.get("category") if type(row) is dict else None
        if (
            type(row) is not dict
            or not _result_positive_int(row.get("id"))
            or row.get("commit_sha") != exact_head
            or row.get("ref") != _CAP_S1_PR_HEAD_REF
            or row.get("analysis_key") != _CAP_S1_CODEQL_ANALYSIS_KEY
            or category not in {f"/language:{item}" for item in expected_categories}
            or type(tool) is not dict
            or tool.get("name") != "CodeQL"
            or row.get("results_count") != 0
            or not _result_positive_int(row.get("rules_count"))
            or row.get("error") != ""
            or row.get("warning") != ""
        ):
            raise CapS1ResultError("cap_s1_result_security_proof_invalid")
        normalized_category = str(category).removeprefix("/language:")
        if normalized_category in seen_analysis_categories:
            raise CapS1ResultError("cap_s1_result_security_proof_invalid")
        seen_analysis_categories.add(normalized_category)
        analysis_rows.append(
            {
                "id": row["id"],
                "category": normalized_category,
                "ref": row["ref"],
                "tool": tool["name"],
                "results_count": row["results_count"],
                "rules_count": row["rules_count"],
            }
        )
    if seen_analysis_categories != expected_categories:
        raise CapS1ResultError("cap_s1_result_security_proof_unavailable")

    after_binding = _pr_binding()
    if after_binding != before_binding:
        raise CapS1ResultError("cap_s1_result_security_proof_invalid")
    findings = len(alerts)
    return (
        (
            "codeql-checks",
            "PASSED",
            0,
            _canonical_digest(tuple(sorted(_canonical_digest(row) for row in codeql_rows))),
        ),
        (
            "code-scanning-alerts",
            "PASSED" if findings == 0 else "FAILED",
            findings,
            _canonical_digest(
                {
                    "exact_head": exact_head,
                    "pr_binding": before_binding,
                    "analysis_ids": tuple(
                        sorted(str(row["id"]) for row in analysis_rows)
                    ),
                    "analysis_categories": tuple(
                        sorted(str(row["category"]) for row in analysis_rows)
                    ),
                    "open_alert_numbers": tuple(
                        sorted(str(row.get("number", "")) for row in alerts)
                    ),
                }
            ),
        ),
    )


def _capture_cap_s1_cleanup_tree(root: Path) -> tuple[tuple[object, ...], ...]:
    """Capture bounded inode identities without reading possibly sensitive bytes."""

    try:
        root_state = root.lstat()
    except OSError as exc:
        raise CapS1ResultError("cap_s1_result_source_observer_cleanup_failed") from exc
    if stat.S_ISLNK(root_state.st_mode) or not stat.S_ISDIR(root_state.st_mode):
        raise CapS1ResultError("cap_s1_result_source_observer_cleanup_failed")
    rows: list[tuple[object, ...]] = [
        (".", "directory", root_state.st_dev, root_state.st_ino, stat.S_IMODE(root_state.st_mode), 0)
    ]
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise CapS1ResultError("cap_s1_result_source_observer_cleanup_failed") from exc
        for entry in entries:
            try:
                state = entry.stat(follow_symlinks=False)
                relative = Path(entry.path).relative_to(root).as_posix()
            except (OSError, ValueError) as exc:
                raise CapS1ResultError("cap_s1_result_source_observer_cleanup_failed") from exc
            if (
                not relative
                or len(relative.encode("utf-8")) > 4096
                or stat.S_ISLNK(state.st_mode)
            ):
                raise CapS1ResultError("cap_s1_result_source_observer_cleanup_failed")
            if stat.S_ISDIR(state.st_mode):
                kind = "directory"
                size = 0
                pending.append(Path(entry.path))
            elif stat.S_ISREG(state.st_mode):
                kind = "file"
                size = state.st_size
            else:
                raise CapS1ResultError("cap_s1_result_source_observer_cleanup_failed")
            rows.append(
                (
                    relative,
                    kind,
                    state.st_dev,
                    state.st_ino,
                    stat.S_IMODE(state.st_mode),
                    size,
                )
            )
            if len(rows) > 100_000:
                raise CapS1ResultError("cap_s1_result_source_observer_cleanup_failed")
    return tuple(sorted(rows))


def _cap_s1_path_absent(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return False


def _finalize_cap_s1_observer_cleanup(
    *,
    scratch_path: Path,
    scratch_device: int,
    scratch_inode: int,
    owned_roots: Sequence[_CapS1OwnedRootIdentity],
    process_cleanup: Sequence[_CapS1OwnedProcessCleanupObservation],
    require_complete: bool = True,
) -> tuple[tuple[str, str, bool, bool], ...]:
    """Return cleanup rows only after creation-time ownership revalidation."""

    complete_top_level = {
        "mutant-0",
        "mutant-1",
        "mutant-2",
        "output",
        "secret-scan",
        "source-copy",
    }
    try:
        scratch_state = scratch_path.lstat()
        actual_top_level = {entry.name for entry in os.scandir(scratch_path)}
    except OSError as exc:
        raise CapS1ResultError("cap_s1_result_source_observer_cleanup_failed") from exc
    if (
        stat.S_ISLNK(scratch_state.st_mode)
        or not stat.S_ISDIR(scratch_state.st_mode)
        or (scratch_state.st_dev, scratch_state.st_ino) != (scratch_device, scratch_inode)
    ):
        raise CapS1ResultError("cap_s1_result_source_observer_cleanup_failed")
    if not owned_roots or any(type(row) is not _CapS1OwnedRootIdentity for row in owned_roots):
        raise CapS1ResultError("cap_s1_result_source_observer_cleanup_failed")
    category_paths: dict[str, list[Path]] = {}
    seen_paths: set[Path] = set()
    direct_owned_names: set[str] = set()
    for row in owned_roots:
        try:
            current = row.path.lstat()
            relative = row.path.relative_to(scratch_path)
        except (OSError, ValueError) as exc:
            raise CapS1ResultError("cap_s1_result_source_observer_cleanup_failed") from exc
        if (
            row.kind not in _RESULT_OBSERVER_CLEANUP_KINDS
            or row.kind == "observer-processes"
            or row.path in seen_paths
            or stat.S_ISLNK(current.st_mode)
            or not stat.S_ISDIR(current.st_mode)
            or (current.st_dev, current.st_ino) != (row.device, row.inode)
        ):
            raise CapS1ResultError("cap_s1_result_source_observer_cleanup_failed")
        seen_paths.add(row.path)
        category_paths.setdefault(row.kind, []).append(row.path)
        if len(relative.parts) == 1:
            direct_owned_names.add(relative.parts[0])
    if actual_top_level != direct_owned_names:
        raise CapS1ResultError("cap_s1_result_source_observer_cleanup_failed")
    expected_root_kinds = set(_RESULT_OBSERVER_CLEANUP_KINDS) - {"observer-processes"}
    if require_complete and (
        actual_top_level != complete_top_level
        or set(category_paths) != expected_root_kinds
    ):
        raise CapS1ResultError("cap_s1_result_source_observer_cleanup_failed")

    category_digests: dict[str, str] = {}
    for kind, paths in category_paths.items():
        category_digests[kind] = _canonical_digest(
            {
                "kind": kind,
                "owned_trees": tuple(
                    _canonical_digest(_capture_cap_s1_cleanup_tree(path))
                    for path in sorted(paths)
                ),
            }
        )
    if require_complete and (
        not process_cleanup
        or not all(
            type(row) is _CapS1OwnedProcessCleanupObservation
            and _result_is_hex64(row.identity_digest)
            and row.removed is True
            and row.verified_absent is True
            for row in process_cleanup
        )
        or len({row.identity_digest for row in process_cleanup})
        != len(process_cleanup)
    ):
        raise CapS1ResultError("cap_s1_result_source_observer_cleanup_failed")
    if process_cleanup:
        category_digests["observer-processes"] = _canonical_digest(
            tuple(dataclasses.astuple(row) for row in process_cleanup)
        )

    removed, root_absent = _cleanup_owned_dir_action(
        scratch_path,
        expected_device=scratch_device,
        expected_inode=scratch_inode,
    )
    row_kinds = (
        _RESULT_OBSERVER_CLEANUP_KINDS
        if require_complete
        else tuple(sorted(category_digests))
    )
    rows = tuple(
        sorted(
            (
                kind,
                category_digests[kind],
                removed,
                root_absent
                and all(
                    _cap_s1_path_absent(path)
                    for path in category_paths.get(kind, (scratch_path,))
                ),
            )
            for kind in row_kinds
        )
    )
    if (
        not removed
        or not root_absent
        or (require_complete and tuple(row[0] for row in rows) != _RESULT_OBSERVER_CLEANUP_KINDS)
        or not all(row[2] and row[3] for row in rows)
    ):
        raise CapS1ResultError("cap_s1_result_source_observer_cleanup_failed")
    return rows


@dataclasses.dataclass(frozen=True, kw_only=True)
class _CapS1GitHubObservations:
    """Already-authenticated GitHub rows captured before cleanup receipts."""

    hosted_run: dict[str, Any]
    hosted_rows: tuple[tuple[str, str, str, str], ...]
    pull: dict[str, Any]
    review: dict[str, Any]


@dataclasses.dataclass(frozen=True, kw_only=True)
class _CapS1ObservedFamilies:
    exact_head: str
    exact_tree: str
    protected_join: str
    producer_evidence: CapS1ProducerEvidence
    local_proof: CapS1LocalProofReceipt
    hosted_proof: CapS1HostedProofReceipt
    security_proof: CapS1SecurityProofReceipt
    mutation_proof: CapS1MutationProofReceipt
    cleanup_proof: CapS1CleanupProofReceipt
    review_state: CapS1ReviewReceipt
    github_observations: _CapS1GitHubObservations


def _receipt_with_digest(receipt: Any) -> Any:
    return dataclasses.replace(
        receipt,
        evidence_digest=_result_receipt_evidence_digest(receipt),
    )


def _run_cap_s1_source_observer(
    *,
    canary: CanaryEvidence,
    canary_provenance: str,
    hosted_run_id: str,
    review_id: str,
) -> _CapS1ObservedFamilies:
    """Run the fixed observation set and construct its proof families.

    This is intentionally connected to the production builder yet is not
    invoked by structural tests.  The current commission forbids running the
    aggregate observer before review of this registry.  A later explicit edge
    may execute exactly this no-argument-policy boundary.
    """

    if canary_provenance != "LIVE_DEFAULT_APP_SERVER":
        raise CapS1ResultError("cap_s1_result_canary_provenance_invalid")

    process_cleanup: list[_CapS1OwnedProcessCleanupObservation] = []
    source_identity = _capture_cap_s1_source_identity(
        process_cleanup=process_cleanup,
    )
    interpreter = _capture_cap_s1_interpreter_identity()
    exact_head, exact_tree, protected_join = source_identity
    if (
        canary.candidate_commit != exact_head
        or canary.candidate_tree != exact_tree
        or canary.protected_join != protected_join
    ):
        raise CapS1ResultError("cap_s1_result_canary_evidence_binding_mismatch")

    scratch_path: "Path | None" = None
    scratch_identity: "os.stat_result | None" = None
    owned_roots: list[_CapS1OwnedRootIdentity] = []
    cleanup_finished = False
    try:
        scratch_path = Path(tempfile.mkdtemp(prefix="cap-s1-source-observer-"))
        scratch_identity = scratch_path.lstat()
        owned_roots.append(
            _register_cap_s1_owned_root(scratch_path, kind="observer-scratch")
        )
        source_root, source_manifest = _owned_cap_s1_source_copy(
            exact_head=exact_head,
            scratch_root=scratch_path,
            owned_roots=owned_roots,
            process_cleanup=process_cleanup,
        )
        output_root = scratch_path / "output"
        output_root.mkdir(mode=0o700)
        owned_roots.append(
            _register_cap_s1_owned_root(output_root, kind="observer-output")
        )
        historical_commit, historical_package_tree, historical_files = (
            _cap_s1_owned_git_package_expectation(source_root)
        )
        local_git = _install_cap_s1_owned_git_context(
            source_repository_root=REPO_ROOT,
            source_root=source_root,
            exact_head=exact_head,
            historical_commit=historical_commit,
            expected_package_tree=historical_package_tree,
            expected_package_files=historical_files,
            cleanup_observations=process_cleanup,
        )
        try:
            local_rows, local_binding_digest = _observe_cap_s1_local_suite(
                source_root=source_root,
                source_manifest=source_manifest,
                output_root=output_root,
                interpreter=interpreter,
                process_cleanup=process_cleanup,
            )
            _verify_cap_s1_owned_git_context(
                local_git,
                cleanup_observations=process_cleanup,
            )
            import_origin_digest = _canonical_digest(
                {
                    "pytest_binding": local_binding_digest,
                    "owned_git_objects": local_git.object_manifest_digest,
                    "owned_git_filesystem": local_git.filesystem_manifest_digest,
                    "owned_git_archive": local_git.archive_digest,
                    "owned_git_archive_diagnostic": (
                        local_git.archive_diagnostic_digest
                    ),
                    "owned_git_archive_files": (
                        local_git.archive_file_manifest_digest
                    ),
                    "historical_tree_paths": (
                        local_git.historical_tree_path_manifest_digest
                    ),
                    "historical_tree_objects": (
                        local_git.historical_tree_object_manifest_digest
                    ),
                    "git_environment": tuple(sorted(_CAP_S1_GIT_ENVIRONMENT.items())),
                }
            )
        finally:
            _remove_cap_s1_owned_git_context(
                local_git,
                cleanup_observations=process_cleanup,
            )
        diff_row = _observe_cap_s1_diff(
            exact_head=exact_head,
            protected_join=protected_join,
            process_cleanup=process_cleanup,
        )
        mutation_rows = _observe_cap_s1_mutations(
            exact_head=exact_head,
            scratch_root=scratch_path,
            owned_roots=owned_roots,
            process_cleanup=process_cleanup,
            interpreter=interpreter,
        )
        hosted_run, hosted_rows = _rederive_hosted_job_manifest(
            run_id=hosted_run_id,
            exact_head=exact_head,
            process_cleanup=process_cleanup,
        )
        pull, review = _rederive_github_review(
            review_id=review_id,
            exact_head=exact_head,
            process_cleanup=process_cleanup,
        )
        secret_root = scratch_path / "secret-scan"
        secret_root.mkdir(mode=0o700)
        owned_roots.append(
            _register_cap_s1_owned_root(secret_root, kind="observer-scratch")
        )
        secret_scan = _observe_cap_s1_secret_scan(
            exact_head=exact_head,
            protected_join=protected_join,
            owned_root=secret_root,
            owned_roots=owned_roots,
            process_cleanup=process_cleanup,
        )
        security_rows = tuple(
            sorted(
                (
                    *_observe_cap_s1_codeql(
                        exact_head=exact_head,
                        process_cleanup=process_cleanup,
                    ),
                    diff_row,
                    (
                        "gitleaks-8.30.1-final-21",
                        "PASSED",
                        secret_scan.findings,
                        secret_scan.evidence_digest,
                    ),
                )
            )
        )
        if not all(
            (
                local_rows,
                hosted_run,
                hosted_rows,
                security_rows,
                mutation_rows,
                pull,
                review,
                interpreter,
                import_origin_digest,
            )
        ):
            raise CapS1ResultError("cap_s1_result_source_observation_unavailable")
        current_scratch = scratch_path.lstat()
        if (
            stat.S_ISLNK(current_scratch.st_mode)
            or not stat.S_ISDIR(current_scratch.st_mode)
            or (current_scratch.st_dev, current_scratch.st_ino)
            != (scratch_identity.st_dev, scratch_identity.st_ino)
        ):
            raise CapS1ResultError("cap_s1_result_source_observation_unavailable")
        _revalidate_cap_s1_observer_source(
            before=source_identity,
            source_root=source_root,
            source_manifest=source_manifest,
            process_cleanup=process_cleanup,
        )
        _revalidate_cap_s1_interpreter_identity(interpreter)
        observer_cleanup_rows = _finalize_cap_s1_observer_cleanup(
            scratch_path=scratch_path,
            scratch_device=scratch_identity.st_dev,
            scratch_inode=scratch_identity.st_ino,
            owned_roots=owned_roots,
            process_cleanup=process_cleanup,
        )
        cleanup_finished = True
        cleanup_rows = tuple(
            sorted(
                (
                    *(
                        (
                            kind,
                            _canonical_digest(
                                {
                                    "canary_operation_id": canary.canary_operation_id,
                                    "provider_attempt_id": canary.provider_attempt_id,
                                    "kind": kind,
                                }
                            ),
                            removed,
                            absent,
                        )
                        for kind, removed, absent in canary.cleanup.artifacts
                    ),
                    *observer_cleanup_rows,
                )
            )
        )
        if tuple(row[0] for row in cleanup_rows) != _RESULT_ALL_CLEANUP_KINDS:
            raise CapS1ResultError("cap_s1_result_source_observer_cleanup_failed")
        bound = {
            "exact_head": exact_head,
            "exact_tree": exact_tree,
            "protected_join": protected_join,
            "provider_attempt_id": canary.provider_attempt_id,
        }
        local_proof = _receipt_with_digest(
            CapS1LocalProofReceipt(
                **bound,
                suite_count=len(local_rows),
                total=sum(sum(row[1:]) for row in local_rows),
                passed=sum(row[1] for row in local_rows),
                skipped=sum(row[2] for row in local_rows),
                failed=sum(row[3] for row in local_rows),
                cancelled=sum(row[4] for row in local_rows),
                suite_manifest=tuple(sorted(local_rows)),
                evidence_digest="",
            )
        )
        hosted_status = str(hosted_run.get("status", "")).upper()
        hosted_conclusion = str(hosted_run.get("conclusion", "")).upper()
        hosted_passed = sum(
            status == "COMPLETED" and conclusion == "SUCCESS"
            for _job_id, _name, status, conclusion in hosted_rows
        )
        hosted_cancelled = sum(
            conclusion == "CANCELLED"
            for _job_id, _name, _status, conclusion in hosted_rows
        )
        hosted_proof = _receipt_with_digest(
            CapS1HostedProofReceipt(
                **bound,
                run_id=hosted_run_id,
                status=hosted_status,
                conclusion=hosted_conclusion,
                jobs_total=len(hosted_rows),
                jobs_passed=hosted_passed,
                jobs_failed=len(hosted_rows) - hosted_passed - hosted_cancelled,
                jobs_cancelled=hosted_cancelled,
                job_manifest=hosted_rows,
                evidence_digest="",
            )
        )
        security_findings = sum(row[2] for row in security_rows)
        security_failures = sum(row[1] == "FAILED" for row in security_rows)
        security_cancelled = sum(row[1] == "CANCELLED" for row in security_rows)
        security_proof = _receipt_with_digest(
            CapS1SecurityProofReceipt(
                **bound,
                status="CLEAN" if not (security_findings or security_failures or security_cancelled) else "FAILED",
                tool_count=len(security_rows),
                findings=security_findings,
                failures=security_failures,
                cancelled=security_cancelled,
                tool_manifest=security_rows,
                evidence_digest="",
            )
        )
        mutation_proof = _receipt_with_digest(
            CapS1MutationProofReceipt(
                **bound,
                status="PASSED",
                total=len(mutation_rows),
                killed=sum(row[1] == "KILLED" for row in mutation_rows),
                survived=sum(row[1] == "SURVIVED" for row in mutation_rows),
                skipped=sum(row[1] == "SKIPPED" for row in mutation_rows),
                errors=sum(row[1] == "ERROR" for row in mutation_rows),
                cancelled=sum(row[1] == "CANCELLED" for row in mutation_rows),
                mutation_manifest=mutation_rows,
                evidence_digest="",
            )
        )
        cleanup_failures = sum(not row[2] for row in cleanup_rows)
        cleanup_residue = sum(not row[3] for row in cleanup_rows)
        cleanup_proof = _receipt_with_digest(
            CapS1CleanupProofReceipt(
                **bound,
                status="CLEAN" if not (cleanup_failures or cleanup_residue) else "FAILED",
                all_removed=not (cleanup_failures or cleanup_residue),
                resources_total=len(cleanup_rows),
                failures=cleanup_failures,
                residue_count=cleanup_residue,
                resource_kinds=tuple(row[0] for row in cleanup_rows),
                resource_manifest=cleanup_rows,
                evidence_digest="",
            )
        )
        pull_author = pull.get("user")
        reviewer = review.get("user")
        if type(pull_author) is not dict or type(reviewer) is not dict:
            raise CapS1ResultError("cap_s1_result_review_state_invalid")
        review_state = _receipt_with_digest(
            CapS1ReviewReceipt(
                **bound,
                author=pull_author.get("login"),
                author_id=pull_author.get("id"),
                reviewer=reviewer.get("login"),
                reviewer_id=reviewer.get("id"),
                review_id=review_id,
                state=str(review.get("state", "")).upper(),
                review_commit=review.get("commit_id"),
                evidence_digest="",
            )
        )
        producer_payload = {
            "schema_version": "mastermind.cap_s1_source_observations/v1",
            "exact_head": exact_head,
            "exact_tree": exact_tree,
            "protected_join": protected_join,
            "provider_attempt_id": canary.provider_attempt_id,
            "local_suites": local_rows,
            "security_tools": security_rows,
            "mutations": mutation_rows,
            "cleanup_resources": cleanup_rows,
            "hosted_jobs": hosted_rows,
            "review_id": review_id,
            "interpreter_identity": _canonical_digest(
                {
                    "entrypoint_identity": interpreter.entrypoint_identity,
                    "entrypoint_link_target_digest": _canonical_digest(
                        interpreter.entrypoint_link_target
                    ),
                    "resolved_target_identity": interpreter.resolved_target_identity,
                    "resolved_target_sha256": interpreter.resolved_target_sha256,
                    "venv_config_identity": interpreter.venv_config_identity,
                    "venv_config_sha256": interpreter.venv_config_sha256,
                    "import_origins": import_origin_digest,
                }
            ),
        }
        producer_evidence = CapS1ProducerEvidence(
            artifact_digest=_canonical_digest(producer_payload),
            exact_head=exact_head,
            exact_tree=exact_tree,
            protected_join=protected_join,
            provider_attempt_id=canary.provider_attempt_id,
            local_suites=tuple(sorted(local_rows)),
            security_tools=security_rows,
            mutations=mutation_rows,
            cleanup_resources=cleanup_rows,
        )
        return _CapS1ObservedFamilies(
            exact_head=exact_head,
            exact_tree=exact_tree,
            protected_join=protected_join,
            producer_evidence=producer_evidence,
            local_proof=local_proof,
            hosted_proof=hosted_proof,
            security_proof=security_proof,
            mutation_proof=mutation_proof,
            cleanup_proof=cleanup_proof,
            review_state=review_state,
            github_observations=_CapS1GitHubObservations(
                hosted_run=hosted_run,
                hosted_rows=hosted_rows,
                pull=pull,
                review=review,
            ),
        )
    except Exception as original_error:
        if (
            scratch_path is not None
            and scratch_identity is not None
            and not cleanup_finished
            and not _cap_s1_path_absent(scratch_path)
        ):
            try:
                _finalize_cap_s1_observer_cleanup(
                    scratch_path=scratch_path,
                    scratch_device=scratch_identity.st_dev,
                    scratch_inode=scratch_identity.st_ino,
                    owned_roots=owned_roots,
                    process_cleanup=process_cleanup,
                    require_complete=False,
                )
            except CapS1ResultError as cleanup_error:
                raise cleanup_error from original_error
        raise


def validate_cap_s1_result(result: CapS1Result) -> None:
    """Refuse detached/direct result objects at the public trust boundary.

    A serialized result is a report, never self-authenticating proof.  The
    only production validator is invoked inside the same source-owned observer
    invocation that constructs the result; callers cannot replay validation
    with a path, manifest or producer object.
    """

    raise CapS1ResultError("cap_s1_result_source_observer_required")


def build_cap_s1_result(**kwargs: Any) -> CapS1Result:
    """Production result boundary owned by the CAP-S1 observer.

    Caller-authored proof families are rejected before any process, GitHub or
    provider effect.  A result is assembled only from the fixed source-owned
    observer in this same invocation.  The consumed historical attempt cannot
    enter this path because it has no exact object returned by ``run_canary``
    and therefore remains ``UNAVAILABLE/HOLD`` with no replay or backfill.
    """

    forbidden_proof_inputs = set(kwargs) & {
        "producer_evidence_path",
        "producer_evidence_digest",
        "package_identities",
        "provider_attempt",
        "changed_path_census",
        "held_non_goals",
        "release_state",
        "local_proof",
        "hosted_proof",
        "security_proof",
        "mutation_proof",
        "cleanup_proof",
        "review_state",
    }
    if forbidden_proof_inputs:
        raise CapS1ResultError(
            "cap_s1_result_caller_proof_authority_forbidden"
        )
    if set(kwargs) != {
        "operation",
        "receiver",
        "carrier",
        "canary_evidence",
        "hosted_run_id",
        "review_id",
    }:
        raise CapS1ResultError("cap_s1_result_source_observer_request_invalid")
    if not _result_safe_operation(kwargs["operation"]):
        raise CapS1ResultError("cap_s1_result_operation_invalid")
    if not _result_safe_receiver(kwargs["receiver"]):
        raise CapS1ResultError("cap_s1_result_receiver_invalid")
    if not _result_safe_slack_carrier(kwargs["carrier"]):
        raise CapS1ResultError("cap_s1_result_carrier_invalid")
    for locator in ("hosted_run_id", "review_id"):
        value = kwargs[locator]
        if not isinstance(value, str) or not value.isascii() or not value.isdigit() or len(value) > 20:
            raise CapS1ResultError("cap_s1_result_source_observer_request_invalid")
    if type(kwargs.get("canary_evidence")) is CanaryEvidence:
        canary = kwargs["canary_evidence"]
        seal = _claim_cap_s1_canary_seal(canary)
    elif kwargs.get("canary_evidence") is not None:
        raise CapS1ResultError("cap_s1_result_canary_evidence_source_invalid")
    else:
        raise CapS1ResultError("cap_s1_result_cleanup_evidence_unavailable")
    try:
        if seal.provenance != "LIVE_DEFAULT_APP_SERVER":
            raise CapS1ResultError("cap_s1_result_canary_provenance_invalid")
        if not canary.cleanup.all_removed:
            raise CapS1ResultError("cap_s1_result_cleanup_evidence_unavailable")
        observed = _run_cap_s1_source_observer(
            canary=canary,
            canary_provenance=seal.provenance,
            hosted_run_id=kwargs["hosted_run_id"],
            review_id=kwargs["review_id"],
        )
    except CapS1ResultError as error:
        _finish_cap_s1_canary_seal(canary, seal, failure=error)
        raise
    except Exception as unexpected:
        error = CapS1ResultError("cap_s1_result_source_observation_unavailable")
        _finish_cap_s1_canary_seal(canary, seal, failure=error)
        raise error from unexpected
    closures = tuple(sorted(canary.skill_closure_digests))
    result_kwargs = {
        "operation": kwargs["operation"],
        "receiver": kwargs["receiver"],
        "carrier": kwargs["carrier"],
        "exact_head": observed.exact_head,
        "exact_tree": observed.exact_tree,
        "current_protected_join": observed.protected_join,
        "changed_path_census": RESULT_CHANGED_PATHS,
        "package_identities": CapS1PackageIdentitiesReceipt(
            exact_head=observed.exact_head,
            exact_tree=observed.exact_tree,
            package_content_digest=_canonical_digest(
                {"skill_closures": closures}
            ),
            package_source_digest=canary.package_source_digest,
            package_generation_digest=canary.package_generation_digest,
            closures=closures,
        ),
        "canary_evidence": canary,
        "provider_attempt": CapS1ProviderAttemptReceipt(
            state="COMPLETED",
            attempt_id=canary.provider_attempt_id,
            attempt_operation=canary.canary_operation_id,
            candidate_head=observed.exact_head,
            candidate_tree=observed.exact_tree,
            disposition="ACCEPTED",
            hold_code=None,
        ),
        "local_proof": observed.local_proof,
        "hosted_proof": observed.hosted_proof,
        "security_proof": observed.security_proof,
        "mutation_proof": observed.mutation_proof,
        "cleanup_proof": observed.cleanup_proof,
        "review_state": observed.review_state,
        "held_non_goals": RESULT_HELD_NON_GOALS,
    }
    try:
        result = _assemble_cap_s1_result_from_observations(
            result_kwargs,
            producer_evidence=observed.producer_evidence,
            github_observations=observed.github_observations,
        )
    except CapS1ResultError as error:
        _finish_cap_s1_canary_seal(canary, seal, failure=error)
        raise
    except Exception as unexpected:
        error = CapS1ResultError("cap_s1_result_source_observation_unavailable")
        _finish_cap_s1_canary_seal(canary, seal, failure=error)
        raise error from unexpected
    _finish_cap_s1_canary_seal(canary, seal, failure=None)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="CAP-S1 Mastermind operator canary runner")
    parser.add_argument("--backend", choices=("fake", "live"), required=True)
    parser.add_argument("--codex-home", type=Path, default=None)
    parser.add_argument("--binary-path", type=Path, default=None)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--protected-join", required=True)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)

    if args.backend == "fake":
        client_factory = _default_fake_client_factory
    else:
        # CAP-S1 addendum (5087373998, finding 3): an explicit, opt-in
        # ``CAP_S1_LIVE_CLIENT_FACTORY=module:attr`` override lets the live
        # wiring be exercised end to end by a non-network test double (see
        # ``_seam_probe_client_factory``) without ever touching the real
        # adapter default. Only consulted for backend=live; the fake
        # backend above is never affected.
        override = os.environ.get("CAP_S1_LIVE_CLIENT_FACTORY", "").strip()
        if override:
            module_name, _sep, attr_name = override.partition(":")
            client_factory = None
            if module_name and attr_name:
                try:
                    # A ``-m`` entry point runs this file as ``__main__`` --
                    # re-importing it by its dotted path would mint a SECOND,
                    # distinct module object (and a distinct
                    # ``_SeamProbeRefusal`` class the ``except`` clause in
                    # ``run_canary`` could never match). When the override
                    # names THIS module, reuse the already-loaded one instead.
                    if module_name in (__name__, "scripts.ohf.cap_s1_mastermind_operator_canary"):
                        module = sys.modules[__name__]
                    else:
                        module = importlib.import_module(module_name)
                    client_factory = getattr(module, attr_name)
                except (ImportError, AttributeError, KeyError):
                    client_factory = None
            if client_factory is None:
                print("CANARY_STOP:PROVIDER_REALM_UNAVAILABLE")
                print(
                    json.dumps(
                        {
                            "canary_stop": "PROVIDER_REALM_UNAVAILABLE",
                            "detail": "live client factory override is not importable",
                        },
                        sort_keys=True,
                    )
                )
                return 1
        else:
            # Live realm: the adapter's own default factory spawns the
            # exact real App Server process; run_canary refuses a None
            # factory either way.
            from control_plane.codex_operator_adapter import _default_client_factory

            client_factory = _default_client_factory

    try:
        evidence = run_canary(
            backend=args.backend,
            binary_path=args.binary_path,
            codex_home=args.codex_home,
            repo_root=args.repo_root,
            scratch_root=args.scratch,
            operation_id=args.operation_id,
            protected_join=args.protected_join,
            client_factory=client_factory,
        )
    except CanaryStop as stop:
        print(f"CANARY_STOP:{stop.code}")
        print(json.dumps({"canary_stop": stop.code, "detail": stop.detail}, sort_keys=True))
        return 1

    payload = dataclasses.asdict(evidence)
    print(json.dumps(payload, indent=2, sort_keys=True))

    markers_ok = all(ok for _name, ok in evidence.turn_marker_results)
    cleanup_ok = evidence.cleanup.all_removed
    launch_ok = evidence.launch_decision == LaunchDecision.ALLOW.value
    return 0 if (markers_ok and cleanup_ok and launch_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
