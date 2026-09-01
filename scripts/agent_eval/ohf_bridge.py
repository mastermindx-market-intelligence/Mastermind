"""EVAL-OHF2: OHF-to-R0 bridge (design/plan: see
``docs/superpowers/plans/2026-09-01-agent-evaluation-ohf2-integration.md``,
the full mapping table and disclosed limitations live there).

Adapts one OHF fresh-Sol evaluation harness (F0, PR #162,
``scripts/ohf/fresh_sol_eval.py``) evidence artifact + manifest entry into
an EVAL-R0 run draft, then drives R0's existing, unmodified finalizer
(:mod:`scripts.agent_eval.validity`) and create-only store
(:mod:`scripts.agent_eval.store`).

**This module imports nothing from ``scripts.ohf.*``.** PR #162 is
unmerged; the two facts this bridge needs from OHF F0 (the frozen
Skillpack arm table and the exact frontmatter field set) are copied here
as literal data, each with a comment naming its exact source and commit.
See the plan record §6 for the merge-gated seam that removes this
duplication once #162 lands.

Stdlib-only, additive, environment-free: no network, process, or
credential access. Swept automatically by the same AST/subprocess
inertness fence that already covers every ``scripts/agent_eval/*.py``
file (``tests/test_agent_eval_inertness.py``).

**Known, disclosed limitations** (plan record §5 for detail — not hidden
here or anywhere else in this module):

- ``evidence.tool_events`` is a documented PLACEHOLDER, not real observed
  evidence — OHF F0 persists no distinct tool-call event log.
- ``observations.observed_sources`` / ``observed_capability_ids`` /
  ``observed_tool_schema_digests`` default to empty when the caller does
  not supply real per-run observations, because OHF F0's persisted
  artifact carries none of them. R0's leakage/capability-drift detection
  is not yet load-bearing for a bridged run unless the caller supplies
  genuine observation data.
- The frontmatter parser below handles OHF F0's known closed field
  shapes (hex digests, uuid4 strings, ISO timestamps, short tokens) and
  fails closed on anything else; it has not been cross-checked against a
  real ``yaml.safe_dump`` byte stream (capability claim
  ``PRODUCTION_INERT``, plan record §9).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from scripts.agent_eval import contracts, store, validity
from scripts.agent_eval.canonical import digest_value

# ---------------------------------------------------------------------------
# Frozen OHF F0 data, copied literally (plan record §2/§6) from
# scripts/ohf/fresh_sol_eval.py on PR #162 branch head 478ca1f5. NOT
# imported -- see module docstring and plan record §6 for the merge-gated
# seam that replaces this copy once #162 merges.
# ---------------------------------------------------------------------------

#: ``fresh_sol_eval.py::RUN_SCHEMA``
OHF_ARTIFACT_SCHEMA = "mastermind.fresh_sol_eval_run/v1"
#: ``fresh_sol_eval.py::MANIFEST_SCHEMA``
OHF_MANIFEST_SCHEMA = "mastermind.fresh_sol_eval_manifest/v1"

#: ``fresh_sol_eval.py::MAS136_ARMS`` -- (commit_sha, skillpack_version) by
#: OHF arm name. Both commits are 40-hex git object shas, matching R0's
#: source-qualified-ref grammar once prefixed ``git:<owner>/<repo>@``.
OHF_SKILLPACK_ARMS: dict[str, tuple[str, str]] = {
    "control-1.0.0": ("51f9942733b86e550bb9169d2a43462bd28e774f", "1.0.0"),
    "amended-1.1.0": ("8209e1f31da15f8effc23a9899a5c5a02d30cab4", "1.1.0"),
}

#: ``fresh_sol_eval.py::_EVIDENCE_METADATA_KEYS`` -- the closed, ordered
#: frontmatter field set OHF F0 emits. Field TYPE is fixed per key: this
#: parser is deliberately not a general YAML parser (module docstring).
_OHF_LIST_FIELDS = frozenset({"procedure_source_blobs"})
_OHF_INT_FIELDS = frozenset({"process_pid"})
_OHF_OPTIONAL_INT_FIELDS = frozenset({"process_pgid"})
_OHF_OPTIONAL_BOOL_FIELDS = frozenset({"requires_openai_auth"})
_OHF_REQUIRED_FIELDS = (
    "schema",
    "scenario_id",
    "arm",
    "run_id",
    "procedure_commit_sha",
    "expected_skillpack_version",
    "procedure_source_blobs",
    "procedure_context_sha256",
    "protocol_sha256",
    "prompt_sha256",
    "model_requested",
    "model_served",
    "harness_kind",
    "harness_version",
    "harness_binary_sha256",
    "provider_auth_type",
    "provider_plan_type",
    "requires_openai_auth",
    "process_pid",
    "process_pgid",
    "process_start_identity",
    "native_thread_id",
    "started_at",
    "completed_at",
    "cleanup_proof",
    "manual_classification",
)

REPO_REF_PREFIX = "git:mastermindx-market-intelligence/Mastermind@"


# ---------------------------------------------------------------------------
# Closed error vocabulary
# ---------------------------------------------------------------------------

OHF_BRIDGE_ERROR_CODES = frozenset(
    {
        "OHF_ARTIFACT_SHAPE_INVALID",
        "OHF_ARTIFACT_SCHEMA_MISMATCH",
        "OHF_ARTIFACT_PROMPT_DIGEST_MISMATCH",
        "OHF_MANIFEST_ENTRY_MISSING",
        "OHF_ARTIFACT_DIGEST_TAMPERED",
        "OHF_RUN_ID_NOT_UUID4",
        "OHF_TIMESTAMP_UNPARSEABLE",
        "OHF_SCENARIO_CODE_MISMATCH",
        "OHF_AUTH_REALM_UNMAPPABLE",
        "OHF_CLEANUP_PROOF_UNPARSEABLE",
        "OHF_CLEANUP_PROOF_NOT_EMPTY",
        "OHF_PROCEDURE_BINDING_MISMATCH",
        "OHF_OBSERVATION_FIELD_REQUIRED",
        "OHF_UNKNOWN_SKILLPACK_ARM",
    }
)


class OhfBridgeError(RuntimeError):
    """One closed, named EVAL-OHF2 bridge failure. ``code`` is always one
    of :data:`OHF_BRIDGE_ERROR_CODES` (mirrors the closed-error-vocabulary
    pattern of ``FreshSolEvalError``/``ContractError``, never a bare
    exception carrying only prose)."""

    def __init__(self, code: str, message: str) -> None:
        if code not in OHF_BRIDGE_ERROR_CODES:
            raise ValueError("unknown OHF bridge error code")
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# Frontmatter + section parsing (plan record §2/§9)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OhfArtifact:
    """One parsed OHF F0 evidence artifact: closed frontmatter dict plus
    the two verbatim fenced sections."""

    frontmatter: dict[str, Any]
    prompt: str
    output: str


_FRONTMATTER_DELIM = "---\n"
_KEY_LINE_RE = re.compile(r"^([a-z_][a-z0-9_]*):[ \t]?(.*)$")
_LIST_ITEM_RE = re.compile(r"^- (.*)$")
_SECTIONS_RE = re.compile(
    r"## Exact prompt\n\n(?P<pfence>`{3,})text\n(?P<prompt>.*?)\n(?P=pfence)\n\n"
    r"## Exact model output\n\n(?P<ofence>`{3,})text\n(?P<output>.*?)\n(?P=ofence)\n?\Z",
    re.DOTALL,
)


def _unquote_scalar(raw: str) -> str:
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        return raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1].replace("''", "'")
    return raw


def _coerce_scalar(key: str, raw: str) -> Any:
    unquoted = _unquote_scalar(raw)
    if key in _OHF_OPTIONAL_BOOL_FIELDS:
        if unquoted in ("null", "~", ""):
            return None
        if unquoted.lower() == "true":
            return True
        if unquoted.lower() == "false":
            return False
        raise OhfBridgeError("OHF_ARTIFACT_SHAPE_INVALID", f"field {key!r} is not a bool/null: {raw!r}")
    if key in _OHF_INT_FIELDS:
        try:
            return int(unquoted)
        except ValueError as exc:
            raise OhfBridgeError("OHF_ARTIFACT_SHAPE_INVALID", f"field {key!r} is not an int: {raw!r}") from exc
    if key in _OHF_OPTIONAL_INT_FIELDS:
        if unquoted in ("null", "~", ""):
            return None
        try:
            return int(unquoted)
        except ValueError as exc:
            raise OhfBridgeError("OHF_ARTIFACT_SHAPE_INVALID", f"field {key!r} is not an int/null: {raw!r}") from exc
    return unquoted


def _parse_ohf_frontmatter(body: str) -> dict[str, Any]:
    """Parse the closed, ordered OHF F0 frontmatter field set only (module
    docstring: not a general YAML parser)."""
    lines = body.split("\n")
    result: dict[str, Any] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if line == "":
            index += 1
            continue
        match = _KEY_LINE_RE.match(line)
        if not match:
            raise OhfBridgeError("OHF_ARTIFACT_SHAPE_INVALID", f"unparseable frontmatter line: {line!r}")
        key, rest = match.group(1), match.group(2)
        if key in _OHF_LIST_FIELDS and rest == "":
            items: list[str] = []
            index += 1
            while index < len(lines) and _LIST_ITEM_RE.match(lines[index]):
                items.append(_unquote_scalar(_LIST_ITEM_RE.match(lines[index]).group(1)))
                index += 1
            result[key] = items
            continue
        result[key] = _coerce_scalar(key, rest)
        index += 1
    missing = [key for key in _OHF_REQUIRED_FIELDS if key not in result]
    if missing:
        raise OhfBridgeError("OHF_ARTIFACT_SHAPE_INVALID", f"frontmatter missing required field(s): {sorted(missing)}")
    unexpected = sorted(set(result) - set(_OHF_REQUIRED_FIELDS))
    if unexpected:
        raise OhfBridgeError("OHF_ARTIFACT_SHAPE_INVALID", f"frontmatter has unexpected field(s): {unexpected}")
    return result


def parse_ohf_artifact_text(text: str) -> OhfArtifact:
    """Parse one OHF F0 evidence-artifact Markdown file's exact text into
    its closed frontmatter dict plus the two verbatim fenced sections.
    Fails closed (:class:`OhfBridgeError`) on any shape deviation; never
    guesses."""
    if not text.startswith(_FRONTMATTER_DELIM):
        raise OhfBridgeError("OHF_ARTIFACT_SHAPE_INVALID", "artifact does not open with a '---' frontmatter fence")
    end_index = text.find("\n---\n", len(_FRONTMATTER_DELIM))
    if end_index == -1:
        raise OhfBridgeError("OHF_ARTIFACT_SHAPE_INVALID", "artifact frontmatter is never closed with '---'")
    frontmatter_body = text[len(_FRONTMATTER_DELIM) : end_index]
    remainder = text[end_index + len("\n---\n") :]
    frontmatter = _parse_ohf_frontmatter(frontmatter_body)
    if frontmatter["schema"] != OHF_ARTIFACT_SCHEMA:
        raise OhfBridgeError(
            "OHF_ARTIFACT_SCHEMA_MISMATCH",
            f"expected schema {OHF_ARTIFACT_SCHEMA!r}, found {frontmatter['schema']!r}",
        )
    sections = _SECTIONS_RE.search(remainder)
    if not sections:
        raise OhfBridgeError("OHF_ARTIFACT_SHAPE_INVALID", "could not locate fenced prompt/output sections")
    prompt = sections.group("prompt")
    output = sections.group("output")
    expected_prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    if expected_prompt_sha256 != frontmatter["prompt_sha256"]:
        raise OhfBridgeError(
            "OHF_ARTIFACT_PROMPT_DIGEST_MISMATCH",
            "recomputed prompt sha256 does not match frontmatter.prompt_sha256 -- artifact is tampered or corrupt",
        )
    return OhfArtifact(frontmatter=frontmatter, prompt=prompt, output=output)


# ---------------------------------------------------------------------------
# Manifest tamper detection (plan record §7 step 2)
# ---------------------------------------------------------------------------


def verify_ohf_manifest_entry(manifest: dict[str, Any], *, run_id: str, artifact_bytes: bytes) -> dict[str, Any]:
    """Return the manifest entry for ``run_id`` after proving the supplied
    artifact bytes match its recorded ``artifact_sha256`` exactly. Fails
    closed before any frontmatter parsing happens -- a tampered or
    substituted artifact is caught here, not downstream."""
    if manifest.get("schema") != OHF_MANIFEST_SCHEMA:
        raise OhfBridgeError(
            "OHF_ARTIFACT_SCHEMA_MISMATCH", f"manifest schema is not {OHF_MANIFEST_SCHEMA!r}: {manifest.get('schema')!r}"
        )
    entry = next((e for e in manifest.get("entries", []) if e.get("run_id") == run_id), None)
    if entry is None:
        raise OhfBridgeError("OHF_MANIFEST_ENTRY_MISSING", f"no manifest entry for run_id {run_id!r}")
    actual_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    if actual_sha256 != entry.get("artifact_sha256"):
        raise OhfBridgeError(
            "OHF_ARTIFACT_DIGEST_TAMPERED",
            f"artifact bytes for run_id {run_id!r} do not match the manifest's recorded artifact_sha256",
        )
    return entry


# ---------------------------------------------------------------------------
# Small deterministic transforms
# ---------------------------------------------------------------------------


def slugify_ohf_arm(arm_name: str) -> str:
    """``control-1.0.0`` -> ``control-1-0-0`` -- R0's ``arm_id`` grammar
    forbids ``.``."""
    return arm_name.replace(".", "-")


_UUID4_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_OHF_TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.(\d{1,6})Z$")


def _parse_ohf_timestamp(value: str) -> datetime:
    match = _OHF_TIMESTAMP_RE.match(value)
    if not match:
        raise OhfBridgeError("OHF_TIMESTAMP_UNPARSEABLE", f"not an OHF fractional-second UTC timestamp: {value!r}")
    whole, frac = match.group(1), match.group(2)
    micros = int(frac.ljust(6, "0"))
    return datetime.strptime(whole, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc) + timedelta(microseconds=micros)


def _truncate_to_whole_second(value: str) -> str:
    parsed = _parse_ohf_timestamp(value)
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


_AUTH_REALM_CLASS_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _derive_auth_realm_class(provider_auth_type: str) -> str:
    candidate = provider_auth_type.upper()
    if not _AUTH_REALM_CLASS_RE.match(candidate):
        raise OhfBridgeError(
            "OHF_AUTH_REALM_UNMAPPABLE", f"provider_auth_type {provider_auth_type!r} does not map to a valid auth_realm_class"
        )
    return candidate


_CLEANUP_PROOF_RE = re.compile(r"^(?P<outcome>.+)/private_group_empty=(?P<empty>True|False)$")


def _parse_cleanup_proof(cleanup_proof: str) -> bool:
    match = _CLEANUP_PROOF_RE.match(cleanup_proof)
    if not match:
        raise OhfBridgeError("OHF_CLEANUP_PROOF_UNPARSEABLE", f"cleanup_proof is not the expected shape: {cleanup_proof!r}")
    return match.group("empty") == "True"


# ---------------------------------------------------------------------------
# Configuration builder for the two frozen Skillpack arms (plan record §4.1)
# ---------------------------------------------------------------------------


def build_ohf_arm_configuration_fields(
    arm_name: str,
    *,
    configuration_id: str,
    instruction_bundle: dict[str, str],
    context_packet: dict[str, str],
    execution_surface: str,
    execution_surface_version: str,
    provider: str,
    model_requested: str,
    reasoning_effort: str,
    auth_realm_class: str,
    profile_id: str,
    profile_digest: str,
    declared_capability_ids: list[str],
    declared_tool_schema_digests: list[str],
    sandbox_digest: str,
    network_policy_digest: str,
    environment_digest: str,
    randomness_seed: int | None,
    sampling_parameters_digest: str,
    authorship: dict[str, str],
    created_at: str,
    handoff: dict[str, str] | None = None,
    retrieval_configuration: dict[str, str] | None = None,
    supersedes: str | None = None,
) -> dict[str, Any]:
    """Build the field dict for ``contracts.build_configuration`` for one
    of the two frozen MAS-136 Skillpack arms (plan record §2 table).
    Everything not determined by the arm identity itself (execution
    surface/provider/capabilities/randomness/authorship) is the caller's
    to supply -- a configuration is scenario-specific input this bridge
    cannot synthesize from the arm name alone (design §7.2)."""
    if arm_name not in OHF_SKILLPACK_ARMS:
        raise OhfBridgeError("OHF_UNKNOWN_SKILLPACK_ARM", f"unknown OHF Skillpack arm: {arm_name!r}")
    commit_sha, skillpack_version = OHF_SKILLPACK_ARMS[arm_name]
    source_ref = f"{REPO_REF_PREFIX}{commit_sha}"
    return {
        "configuration_id": configuration_id,
        "execution": {
            "execution_surface": execution_surface,
            "execution_surface_version": execution_surface_version,
            "provider": provider,
            "model_requested": model_requested,
            "reasoning_effort": reasoning_effort,
            "auth_realm_class": auth_realm_class,
        },
        "procedure": {
            "protected_source_ref": source_ref,
            "skillpack_source_ref": source_ref,
            "skillpack_version": skillpack_version,
            "instruction_bundle": instruction_bundle,
            "handoff": handoff,
        },
        "context": {"context_packet": context_packet, "retrieval_configuration": retrieval_configuration},
        "capabilities": {
            "profile_id": profile_id,
            "profile_digest": profile_digest,
            "declared_capability_ids": sorted(set(declared_capability_ids)),
            "declared_tool_schema_digests": sorted(set(declared_tool_schema_digests)),
            "sandbox_digest": sandbox_digest,
            "network_policy_digest": network_policy_digest,
            "environment_digest": environment_digest,
        },
        "randomness": {"seed": randomness_seed, "sampling_parameters_digest": sampling_parameters_digest},
        "authorship": authorship,
        "created_at": created_at,
        "supersedes": supersedes,
    }


# ---------------------------------------------------------------------------
# Run-draft construction (plan record §4)
# ---------------------------------------------------------------------------


def build_run_draft_from_ohf(
    artifact: OhfArtifact,
    *,
    scenario: dict[str, Any],
    configuration: dict[str, Any],
    experiment: dict[str, Any] | None,
    runner_code_ref: str,
    ohf_artifact_ref: str,
    replicate_index: int,
    pair_key: str | None,
    observed_sources: tuple[dict[str, str], ...] = (),
    observed_capability_ids: tuple[str, ...] = (),
    observed_tool_schema_digests: tuple[str, ...] = (),
    observed_network_destinations: tuple[dict[str, Any], ...] = (),
    dependency_degradations: tuple[str, ...] = (),
    resources_input_tokens: int | None = None,
    resources_output_tokens: int | None = None,
    resources_tool_calls: int | None = None,
    resources_provider_usage_ref: str | None = None,
    resources_estimated_marginal_cost: str | None = None,
    resources_cost_currency: str | None = None,
    expected_ohf_scenario_code: str | None = None,
) -> dict[str, Any]:
    """Build one EVAL-R0 run-draft dict from a parsed :class:`OhfArtifact`
    bound to caller-supplied ``scenario``/``configuration``/``experiment``
    documents. Never publishes anything itself -- see
    :func:`finalize_and_publish_ohf_run` for the full pipeline. Fails
    closed (:class:`OhfBridgeError`) on any binding mismatch; see the plan
    record §4 mapping table for the full field-by-field rationale."""
    frontmatter = artifact.frontmatter

    if expected_ohf_scenario_code is not None and frontmatter["scenario_id"] != expected_ohf_scenario_code:
        raise OhfBridgeError(
            "OHF_SCENARIO_CODE_MISMATCH",
            f"artifact scenario_id {frontmatter['scenario_id']!r} != expected {expected_ohf_scenario_code!r}",
        )

    run_id = frontmatter["run_id"]
    if not _UUID4_RE.match(run_id):
        raise OhfBridgeError("OHF_RUN_ID_NOT_UUID4", f"OHF run_id is not a bare uuid4: {run_id!r}")

    expected_instruction_digest = digest_value(
        {
            "procedure_source_blobs": sorted(frontmatter["procedure_source_blobs"]),
            "procedure_context_sha256": frontmatter["procedure_context_sha256"],
        }
    )
    configured_digest = configuration["procedure"]["instruction_bundle"]["digest"]
    if configured_digest != expected_instruction_digest:
        raise OhfBridgeError(
            "OHF_PROCEDURE_BINDING_MISMATCH",
            "configuration.procedure.instruction_bundle.digest does not match this OHF artifact's own procedure "
            "source blobs -- the supplied configuration does not describe what OHF actually ran",
        )

    private_group_empty = _parse_cleanup_proof(frontmatter["cleanup_proof"])
    if not private_group_empty:
        raise OhfBridgeError("OHF_CLEANUP_PROOF_NOT_EMPTY", "OHF cleanup_proof reports private_group_empty=False")

    arm_id = slugify_ohf_arm(frontmatter["arm"])
    started_at = _truncate_to_whole_second(frontmatter["started_at"])
    completed_at = _truncate_to_whole_second(frontmatter["completed_at"])
    duration_ms = round(
        (_parse_ohf_timestamp(frontmatter["completed_at"]) - _parse_ohf_timestamp(frontmatter["started_at"])).total_seconds()
        * 1000
    )
    if duration_ms < 0:
        raise OhfBridgeError("OHF_TIMESTAMP_UNPARSEABLE", "OHF completed_at precedes started_at")

    output_digest = "sha256:" + hashlib.sha256(artifact.output.encode("utf-8")).hexdigest()
    cleanup_digest = digest_value(frontmatter["cleanup_proof"])
    tool_events_digest = digest_value({"ohf_f0_tool_events_not_emitted": True, "run_id": run_id})

    execution_config = configuration["execution"]
    draft = {
        "schema": contracts.RUN_DRAFT_SCHEMA,
        "run_id": f"run:{run_id}",
        "scenario": {
            "scenario_id": scenario["scenario_id"],
            "scenario_version": scenario["scenario_version"],
            "scenario_digest": scenario["scenario_digest"],
            "corpus_revision": scenario["corpus_revision"],
            "temporal_cutoff": scenario["temporal"]["cutoff_at"],
        },
        "configuration": {
            "configuration_id": configuration["configuration_id"],
            "configuration_digest": configuration["configuration_digest"],
        },
        "comparison": {
            "experiment_id": experiment["experiment_id"] if experiment is not None else None,
            "arm_id": arm_id if experiment is not None else None,
            "pair_key": pair_key if experiment is not None else None,
            "replicate_index": replicate_index if experiment is not None else None,
        },
        "execution": {
            "runner_id": "mastermind.eval_ohf_bridge.v1",
            "runner_code_ref": runner_code_ref,
            "execution_surface": execution_config["execution_surface"],
            "execution_surface_version": execution_config["execution_surface_version"],
            "provider": execution_config["provider"],
            "model_requested": execution_config["model_requested"],
            "model_served": frontmatter["model_served"],
            "reasoning_effort": execution_config["reasoning_effort"],
            "auth_realm_class": _derive_auth_realm_class(frontmatter["provider_auth_type"]),
            "process_fingerprint": digest_value(
                {
                    "process_pid": frontmatter["process_pid"],
                    "process_pgid": frontmatter["process_pgid"],
                    "process_start_identity": frontmatter["process_start_identity"],
                }
            ),
            "native_session_fingerprint": digest_value(
                {"native_thread_id": frontmatter["native_thread_id"], "run_id": run_id}
            ),
            "completion_status": "COMPLETED",
            "termination_reason": "COMPLETED_NORMALLY",
            "fresh_process_observed": True,
            "fresh_workspace_observed": True,
            "fresh_session_observed": True,
            "resume_used": False,
        },
        "procedure": dict(configuration["procedure"]),
        "context": {
            "source_policy_digest": digest_value(scenario["source_policy"]),
            "context_packet": dict(configuration["context"]["context_packet"]),
            "retrieval_configuration": configuration["context"]["retrieval_configuration"],
        },
        "observations": {
            "observed_sources": sorted((dict(item) for item in observed_sources), key=lambda item: item["artifact_ref"]),
            "observed_capability_ids": sorted(set(observed_capability_ids)),
            "observed_tool_schema_digests": sorted(set(observed_tool_schema_digests)),
            "observed_network_destinations": [dict(item) for item in observed_network_destinations],
            "dependency_degradations": sorted(set(dependency_degradations)),
        },
        "capabilities": {
            "profile_id": configuration["capabilities"]["profile_id"],
            "profile_digest": configuration["capabilities"]["profile_digest"],
            "sandbox_digest": configuration["capabilities"]["sandbox_digest"],
            "network_policy_digest": configuration["capabilities"]["network_policy_digest"],
            "workspace_digest": digest_value({"run_id": run_id, "process_start_identity": frontmatter["process_start_identity"]}),
            "environment_digest": configuration["capabilities"]["environment_digest"],
        },
        "randomness": dict(configuration["randomness"]),
        "effect": {"state": "NO_EFFECT", "operation_ref": None, "reconciliation_ref": None},
        "cleanup": {
            "status": "PROVEN",
            "proof": {"artifact_ref": f"{ohf_artifact_ref}#cleanup_proof", "digest": cleanup_digest},
        },
        "evidence": {
            "output": {"artifact_ref": ohf_artifact_ref, "digest": output_digest},
            "tool_events": {"artifact_ref": f"{ohf_artifact_ref}#capability_attestation", "digest": tool_events_digest},
            "trace": None,
            "artifacts": [],
        },
        "resources": {
            "input_tokens": resources_input_tokens,
            "output_tokens": resources_output_tokens,
            "tool_calls": resources_tool_calls,
            "elapsed_ms": duration_ms,
            "provider_usage_ref": resources_provider_usage_ref,
            "estimated_marginal_cost": resources_estimated_marginal_cost,
            "cost_currency": resources_cost_currency,
        },
        "timing": {
            "started_at": started_at,
            "completed_at": completed_at,
            "monotonic_duration_ms": duration_ms,
        },
    }
    return draft


# ---------------------------------------------------------------------------
# Finalize + publish (plan record §7 step 3): the whole pipeline in one call
# ---------------------------------------------------------------------------


def finalize_and_publish_ohf_run(
    artifact_store: "store.ArtifactStore",
    scenario: dict[str, Any],
    configuration: dict[str, Any],
    experiment: dict[str, Any] | None,
    draft: dict[str, Any],
    *,
    validator_id: str,
    validator_version: str,
    validator_code_ref: str,
    validated_at: str,
    created_at: str,
) -> dict[str, Any]:
    """Drive R0's existing, unmodified finalizer and create-only store for
    one bridged run draft. Thin by design -- all validity/graph-
    verification logic stays in :mod:`scripts.agent_eval.validity` and
    :mod:`scripts.agent_eval.store`; this function adds nothing to it."""
    run = validity.finalize_run_receipt(
        scenario,
        configuration,
        experiment,
        draft,
        validator_id=validator_id,
        validator_version=validator_version,
        validator_code_ref=validator_code_ref,
        validated_at=validated_at,
        created_at=created_at,
    )
    artifact_store.create(run)
    return run
