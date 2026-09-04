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
import json
import os
import re
import shutil
import stat
import subprocess
import sys
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
    entries out of a non-writable directory, so every directory/file mode is
    forced back to writable first (mirrors
    ``capability_skill_projection._force_remove_tree``'s own discipline).
    """

    try:
        if path.is_dir() and not path.is_symlink():
            for dirpath, _dirnames, filenames in os.walk(str(path)):
                try:
                    os.chmod(dirpath, 0o700)
                except OSError:
                    pass
                for name in filenames:
                    try:
                        os.chmod(os.path.join(dirpath, name), 0o600)
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
            client_factory=client_factory,
            extra_env=extra_env,
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

    return dataclasses.replace(
        evidence_local,
        cleanup=cleanup_record,
        terminal_process_state=process_result.get("terminal_process_state", "UNKNOWN"),
    )


# ---------------------------------------------------------------------------
# Closed CAP-S1 result contract (CAP-S1 Sol review item 5)
# ---------------------------------------------------------------------------
#
# Before this commission no closed result validator existed at all, and
# ``CanaryEvidence`` alone accepted an empty candidate identity anywhere it
# was hand-assembled outside ``run_canary``. This section delivers the
# closed validator + constructor only -- the principal assembles the real
# packet (from a completed ``run_canary`` call, hosted CI evidence, review
# state, etc.) later; this module never itself calls
# ``build_cap_s1_result``.

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


@dataclasses.dataclass(frozen=True, kw_only=True)
class CapS1ProducerEvidence:
    """Immutable producer artifact reopened by result validation.

    This object is never accepted from a result caller.  It is constructed
    only by :func:`_load_cap_s1_producer_evidence` from one read-only,
    no-follow regular file whose identity is stable across the bounded read.
    The public result carries only ``artifact_digest``.
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
    """Reopen and derive the four non-GitHub proof manifests.

    The artifact is a content-addressed producer boundary, not another
    caller-authored result receipt.  It must be a stable, read-only regular
    file; symlinks and files that change across the bounded read are refused.
    Security, mutation, and cleanup row digests are derived from concrete JSON
    preimages retained in the artifact instead of accepting opaque 64-hex
    labels from the result caller.
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

        def _reject_non_json_constant(_value: str) -> None:
            raise ValueError("non-json numeric constant")

        raw = json.loads(
            payload_bytes.decode("utf-8"), parse_constant=_reject_non_json_constant
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
_RESULT_MAX_LOCAL_TESTS = 100_000
_RESULT_MAX_HOSTED_JOBS = 256
_RESULT_MAX_SECURITY_TOOLS = 64
_RESULT_MAX_MUTATIONS = 100_000
_RESULT_REPOSITORY = "mastermindx-market-intelligence/Mastermind"
_RESULT_PR_NUMBER = 350


def _result_safe_identifier(value: object) -> bool:
    return (
        isinstance(value, str)
        and _RESULT_SAFE_ID_RE.fullmatch(value) is not None
        and not any(marker in value.lower() for marker in _RESULT_SENSITIVE_MARKERS)
    )


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


def _github_api_json(endpoint: str) -> Any:
    """Fresh, bounded GitHub read used to authenticate hosted/review proof.

    The endpoint is constructed only from closed contract constants and
    already-validated decimal IDs.  Tests replace this one read seam with
    deterministic API-shaped fixtures; production has no caller-supplied
    callback that could bless its own claims.
    """

    try:
        completed = subprocess.run(
            ["gh", "api", endpoint],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        payload = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise CapS1ResultError("cap_s1_result_github_evidence_unavailable") from exc
    if type(payload) is not dict:
        raise CapS1ResultError("cap_s1_result_github_evidence_unavailable")
    return payload


def _rederive_hosted_job_manifest(
    *, run_id: str, exact_head: str
) -> tuple[dict[str, Any], tuple[tuple[str, str, str, str], ...]]:
    run = _github_api_json(
        f"repos/{_RESULT_REPOSITORY}/actions/runs/{run_id}"
    )
    if str(run.get("id")) != run_id or run.get("head_sha") != exact_head:
        raise CapS1ResultError("cap_s1_result_hosted_proof_invalid")

    rows: list[tuple[str, str, str, str]] = []
    expected_total: "int | None" = None
    for page in range(1, 5):
        payload = _github_api_json(
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
    *, review_id: str, exact_head: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    pull = _github_api_json(
        f"repos/{_RESULT_REPOSITORY}/pulls/{_RESULT_PR_NUMBER}"
    )
    review = _github_api_json(
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


def validate_cap_s1_result(
    result: CapS1Result,
    *,
    producer_evidence_path: "str | os.PathLike[str] | None",
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
    producer_evidence = _load_cap_s1_producer_evidence(producer_evidence_path)
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
        or not local_rows
        or len(local_rows) > 64
    ):
        raise CapS1ResultError("cap_s1_result_local_proof_invalid")
    if not all(
            type(row) is tuple
            and len(row) == 5
            and _result_safe_identifier(row[0])
            and all(_result_nonnegative_int(count) for count in row[1:])
            and sum(row[1:]) <= _RESULT_MAX_LOCAL_TESTS
            for row in local_rows
    ):
        raise CapS1ResultError("cap_s1_result_local_proof_invalid")
    if (
        tuple(sorted(local_rows)) != local_rows
        or len({row[0] for row in local_rows}) != len(local_rows)
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
    hosted_run, hosted_rows = _rederive_hosted_job_manifest(
        run_id=hosted_proof.run_id, exact_head=result.exact_head
    )
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
        str(hosted_run.get("status", "")).upper() != hosted_proof.status
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
        or len(cleanup_rows) != len(_RESULT_CLEANUP_KINDS)
    ):
        raise CapS1ResultError("cap_s1_result_cleanup_proof_invalid")
    if not all(
            type(row) is tuple
            and len(row) == 4
            and row[0] in _RESULT_CLEANUP_KINDS
            and _result_is_hex64(row[1])
            and type(row[2]) is bool
            and type(row[3]) is bool
            for row in cleanup_rows
    ):
        raise CapS1ResultError("cap_s1_result_cleanup_proof_invalid")
    if (
        tuple(sorted(cleanup_rows)) != cleanup_rows
        or tuple(row[0] for row in cleanup_rows) != _RESULT_CLEANUP_KINDS
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
    pull, github_review = _rederive_github_review(
        review_id=review.review_id, exact_head=result.exact_head
    )
    pull_author = pull.get("user")
    github_reviewer = github_review.get("user")
    if (
        type(pull_author) is not dict
        or type(github_reviewer) is not dict
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


def build_cap_s1_result(**kwargs: Any) -> CapS1Result:
    """Construct, then validate, a :class:`CapS1Result` -- the one lawful
    way to obtain an instance believed to satisfy the closed contract."""

    producer_evidence_path = kwargs.pop("producer_evidence_path", None)
    producer_evidence = _load_cap_s1_producer_evidence(producer_evidence_path)
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
    validate_cap_s1_result(result, producer_evidence_path=producer_evidence_path)
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
