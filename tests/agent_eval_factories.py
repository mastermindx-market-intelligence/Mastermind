"""Test-only PUBLIC_SAFE factories and test-only in-memory artifact resolver.

Per plan §5.6 (resolver boundary, binding 2026-09-01 ruling): ``MemoryArtifactResolver``
is test-only and lives here, under the test utility surface, NOT in
``scripts/agent_eval/resolver.py``. It is an immutable construction with no
add/update/delete/search/fallback method — it is built once, fully, from a
tuple of documents, and every lookup is a plain dict-get. Production code
(``scripts/agent_eval/store.py``) supplies the real ``ArtifactResolver``
implementation via the filesystem.

All data here is synthetic and PUBLIC_SAFE per design §10.5/plan §7 — no
real repository content, no real credentials, no real Chairman/production
data.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from uuid import uuid4

from scripts.agent_eval import contracts
from scripts.agent_eval.canonical import digest_value


def fresh_configuration_id() -> str:
    return f"configuration:{uuid4()}"


def fresh_experiment_id() -> str:
    return f"experiment:{uuid4()}"


def fresh_run_id() -> str:
    return f"run:{uuid4()}"

REPO_REF_BASE = "git:mastermindx-market-intelligence/Mastermind@" + "a" * 40
SOLUTION_REF = "git:mastermindx-market-intelligence/Mastermind@" + "b" * 40 + "#solution/final_answer.md"

PUBLIC_TOOL_SCHEMA_DIGEST_A = digest_value({"tool": "read_file", "schema_version": 1})
PUBLIC_TOOL_SCHEMA_DIGEST_B = digest_value({"tool": "search_repo", "schema_version": 1})
PROFILE_DIGEST = digest_value({"profile": "read_only_reviewer", "version": 1})
SANDBOX_DIGEST = digest_value({"sandbox": "standard_read_only"})
ENVIRONMENT_DIGEST = digest_value({"environment": "standard_v1"})

MODEL_REQUESTED = "claude-sonnet-5"


def _fixture_ref(name: str) -> str:
    return f"{REPO_REF_BASE}#fixtures/{name}"


def build_baseline_scenario_fields() -> dict:
    return {
        "scenario_id": "scenario:evaluation_contract_integrity:baseline_case",
        "scenario_version": 1,
        "scenario_family": "mastermind.evaluation_contract_integrity.v1",
        "corpus_revision": REPO_REF_BASE,
        "risk_tier": "LOW",
        "objective": "Identify the canonical owner for a synthetic cold-start collision fixture.",
        "input_fixture": {
            "artifact_ref": _fixture_ref("input.json"),
            "digest": digest_value({"fixture": "input"}),
        },
        "expected_contract": {
            "artifact_ref": _fixture_ref("expected.json"),
            "digest": digest_value({"fixture": "expected"}),
        },
        "temporal": {
            "cutoff_at": "2026-08-01T00:00:00Z",
            "authored_at": "2026-08-15T00:00:00Z",
        },
        "source_policy": {
            "allowlist_artifacts": [
                {"artifact_ref": _fixture_ref("source_a.md"), "digest": digest_value({"source": "a"})},
                {"artifact_ref": _fixture_ref("source_b.md"), "digest": digest_value({"source": "b"})},
            ],
            "denylist_refs": [SOLUTION_REF],
            "solution_refs_hidden": [SOLUTION_REF],
        },
        "capability_policy": {
            "profile_id": "read_only_reviewer",
            "profile_digest": PROFILE_DIGEST,
            "allowed_capability_ids": ["read_file", "search_repo"],
            "forbidden_capability_ids": ["execute_shell", "write_file"],
            "allowed_tool_schema_digests": sorted([PUBLIC_TOOL_SCHEMA_DIGEST_A, PUBLIC_TOOL_SCHEMA_DIGEST_B]),
        },
        "execution_policy": {
            "fresh_process_required": True,
            "fresh_workspace_required": True,
            "fresh_session_required": True,
            "resume_allowed": False,
            "network_policy": "DENY_ALL",
            "network_allowlist": [],
            "max_elapsed_ms": 600000,
            "max_tool_calls": 50,
            "allowed_degradations": ["RETRIEVAL_INDEX_STALE"],
        },
        "effect_policy": {"mode": "NO_EFFECT_ONLY", "allowed_operation_refs": []},
        "scoring_policy": {
            "required_scorers": ["mastermind.technical_integrity.v1"],
            "optional_scorers": [],
            "required_dimensions": sorted(
                ["configuration_integrity", "effect_integrity", "cleanup_integrity", "source_integrity"]
            ),
        },
        "privacy": {
            "classification": "PUBLIC_SAFE",
            "model_visible_artifact_refs": sorted(
                [_fixture_ref("input.json"), _fixture_ref("source_a.md"), _fixture_ref("source_b.md")]
            ),
            "retention_class": "BOUNDED",
        },
        "authorship": {"author_ref": "person:sol", "independent_reviewer_ref": "person:auditor"},
        "supersedes": None,
    }


def build_baseline_scenario() -> dict:
    return contracts.build_scenario(build_baseline_scenario_fields())


def _configuration_fields(*, arm_marker: str) -> dict:
    scenario = build_baseline_scenario()
    return {
        "configuration_id": fresh_configuration_id(),
        "execution": {
            "execution_surface": "app_server",
            "execution_surface_version": "1.0.0",
            "provider": "anthropic",
            "model_requested": MODEL_REQUESTED,
            "reasoning_effort": "medium",
            "auth_realm_class": "READ_ONLY",
        },
        "procedure": {
            "protected_source_ref": REPO_REF_BASE,
            "skillpack_source_ref": REPO_REF_BASE,
            "skillpack_version": "mastermind.sol_skillpack.v1",
            "instruction_bundle": {
                "artifact_ref": _fixture_ref(f"{arm_marker}/instructions.md"),
                "digest": digest_value({"instructions": arm_marker}),
            },
            "handoff": None,
        },
        "context": {
            "context_packet": {
                "artifact_ref": _fixture_ref(f"{arm_marker}/context.json"),
                "digest": digest_value({"context_packet": arm_marker}),
            },
            "retrieval_configuration": None,
        },
        "capabilities": {
            "profile_id": "read_only_reviewer",
            "profile_digest": PROFILE_DIGEST,
            "declared_capability_ids": ["read_file", "search_repo"],
            "declared_tool_schema_digests": sorted([PUBLIC_TOOL_SCHEMA_DIGEST_A, PUBLIC_TOOL_SCHEMA_DIGEST_B]),
            "sandbox_digest": SANDBOX_DIGEST,
            "network_policy_digest": contracts.compute_scenario_network_policy_digest(scenario),
            "environment_digest": ENVIRONMENT_DIGEST,
        },
        "randomness": {"seed": 42, "sampling_parameters_digest": digest_value({"temperature": "0", "arm": arm_marker})},
        "authorship": {"author_ref": "person:sol", "independent_reviewer_ref": "person:auditor"},
        "created_at": "2026-08-20T00:00:00Z",
        "supersedes": None,
    }


def build_baseline_configuration() -> dict:
    """Arm A: same requested model as the alternate configuration, distinct
    context-packet digest (so configuration digests differ)."""
    return contracts.build_configuration(_configuration_fields(arm_marker="arm_a"))


def build_alternate_configuration() -> dict:
    """Arm B: same requested model as the baseline configuration, distinct
    context-packet digest (so configuration digests differ)."""
    return contracts.build_configuration(_configuration_fields(arm_marker="arm_b"))


def build_two_arm_experiment_fields(scenario: dict, configuration_a: dict, configuration_b: dict) -> dict:
    return {
        "experiment_id": fresh_experiment_id(),
        "scenario_refs": [
            {
                "scenario_id": scenario["scenario_id"],
                "scenario_version": scenario["scenario_version"],
                "scenario_digest": scenario["scenario_digest"],
                "corpus_revision": scenario["corpus_revision"],
            }
        ],
        "arms": sorted(
            [
                {
                    "arm_id": "arm_a",
                    "configuration_id": configuration_a["configuration_id"],
                    "configuration_digest": configuration_a["configuration_digest"],
                },
                {
                    "arm_id": "arm_b",
                    "configuration_id": configuration_b["configuration_id"],
                    "configuration_digest": configuration_b["configuration_digest"],
                },
            ],
            key=lambda item: item["arm_id"],
        ),
        "pairing": {"method": "PAIRED_BY_SCENARIO", "random_seed": None},
        "replicates_per_arm_target": 1,
        "stopping_rule": {"kind": "FIXED_REPLICATES_PER_ARM", "value": 1},
        "primary_dimensions": ["configuration_integrity"],
        "guardrail_dimensions": ["cleanup_integrity"],
        "analysis_version": "mastermind.agent_evaluation_r0_analysis.v1",
        "phase": "RETROSPECTIVE",
        "authorship": {"author_ref": "person:sol", "independent_reviewer_ref": "person:auditor"},
        "created_at": "2026-08-21T00:00:00Z",
    }


def build_two_arm_experiment(scenario: dict, configuration_a: dict, configuration_b: dict) -> dict:
    return contracts.build_experiment(build_two_arm_experiment_fields(scenario, configuration_a, configuration_b))


# ---------------------------------------------------------------------------
# Run drafts (Task 4)
# ---------------------------------------------------------------------------

PROOF_ARTIFACT = {"artifact_ref": _fixture_ref("cleanup_proof.json"), "digest": digest_value({"cleanup": "proven"})}


def build_run_draft_fields(
    scenario: dict,
    configuration: dict,
    experiment: dict,
    *,
    arm_id: str,
    replicate_index: int,
    model_served: str | None = None,
    run_id: str | None = None,
) -> dict:
    """A clean, technically-VALID run-draft field set bound to ``configuration``
    within ``experiment``. Pass ``model_served`` to deliberately diverge from
    the configuration's requested model (produces MODEL_SERVED_MISMATCH)."""
    scenario_id = scenario["scenario_id"]
    scenario_version = scenario["scenario_version"]
    pair_key = f"pair:{scenario_id}:v{scenario_version}:r{replicate_index}"
    execution = configuration["execution"]
    served = model_served if model_served is not None else execution["model_requested"]
    return {
        "run_id": run_id or fresh_run_id(),
        "scenario": {
            "scenario_id": scenario_id,
            "scenario_version": scenario_version,
            "scenario_digest": scenario["scenario_digest"],
            "corpus_revision": scenario["corpus_revision"],
            "temporal_cutoff": scenario["temporal"]["cutoff_at"],
        },
        "configuration": {
            "configuration_id": configuration["configuration_id"],
            "configuration_digest": configuration["configuration_digest"],
        },
        "comparison": {
            "experiment_id": experiment["experiment_id"],
            "arm_id": arm_id,
            "pair_key": pair_key,
            "replicate_index": replicate_index,
        },
        "execution": {
            "runner_id": "mastermind.eval_r0_synthetic_runner.v1",
            "runner_code_ref": REPO_REF_BASE,
            "execution_surface": execution["execution_surface"],
            "execution_surface_version": execution["execution_surface_version"],
            "provider": execution["provider"],
            "model_requested": execution["model_requested"],
            "model_served": served,
            "reasoning_effort": execution["reasoning_effort"],
            "auth_realm_class": execution["auth_realm_class"],
            "process_fingerprint": digest_value({"process": arm_id, "replicate": replicate_index}),
            "native_session_fingerprint": digest_value({"session": arm_id, "replicate": replicate_index}),
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
            "observed_sources": [
                dict(item) for item in scenario["source_policy"]["allowlist_artifacts"]
            ],
            "observed_capability_ids": ["read_file"],
            "observed_tool_schema_digests": [PUBLIC_TOOL_SCHEMA_DIGEST_A],
            "observed_network_destinations": [],
            "dependency_degradations": [],
        },
        "capabilities": {
            "profile_id": configuration["capabilities"]["profile_id"],
            "profile_digest": configuration["capabilities"]["profile_digest"],
            "sandbox_digest": configuration["capabilities"]["sandbox_digest"],
            "network_policy_digest": configuration["capabilities"]["network_policy_digest"],
            "workspace_digest": digest_value({"workspace": arm_id, "replicate": replicate_index}),
            "environment_digest": configuration["capabilities"]["environment_digest"],
        },
        "randomness": dict(configuration["randomness"]),
        "effect": {"state": "NO_EFFECT", "operation_ref": None, "reconciliation_ref": None},
        "cleanup": {"status": "PROVEN", "proof": dict(PROOF_ARTIFACT)},
        "evidence": {
            "output": {
                "artifact_ref": _fixture_ref(f"{arm_id}/r{replicate_index}/output.json"),
                "digest": digest_value({"output": arm_id, "replicate": replicate_index}),
            },
            "tool_events": {
                "artifact_ref": _fixture_ref(f"{arm_id}/r{replicate_index}/tool_events.json"),
                "digest": digest_value({"tool_events": arm_id, "replicate": replicate_index}),
            },
            "trace": None,
            "artifacts": [],
        },
        "resources": {
            "input_tokens": 100,
            "output_tokens": 200,
            "tool_calls": 2,
            "elapsed_ms": 1500,
            "provider_usage_ref": None,
            "estimated_marginal_cost": "0.05",
            "cost_currency": "USD",
        },
        "timing": {
            "started_at": "2026-08-25T00:00:00Z",
            "completed_at": "2026-08-25T00:00:05Z",
            "monotonic_duration_ms": 1500,
        },
    }


def build_run_draft(
    scenario: dict, configuration: dict, experiment: dict, *, arm_id: str, replicate_index: int, model_served: str | None = None
) -> dict:
    fields = build_run_draft_fields(
        scenario, configuration, experiment, arm_id=arm_id, replicate_index=replicate_index, model_served=model_served
    )
    return {"schema": contracts.RUN_DRAFT_SCHEMA, **fields}


# ---------------------------------------------------------------------------
# MemoryArtifactResolver — test-only, immutable, read-only (plan §5.6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MemoryArtifactResolver:
    """Immutable in-memory implementation of the production ``ArtifactResolver``
    protocol, for tests only. Built once, fully, from a fixed set of
    documents. No add/update/delete/search/fallback method exists on this
    type — that is the resolver boundary plan §5.6 requires."""

    scenarios: Mapping[tuple, dict]
    configurations: Mapping[str, dict]
    experiments: Mapping[str, dict]
    runs: Mapping[str, dict]
    scorer_passes: Mapping[str, dict]
    evidence_refs: Mapping[str, dict]

    @staticmethod
    def build(
        *,
        scenarios: tuple = (),
        configurations: tuple = (),
        experiments: tuple = (),
        runs: tuple = (),
        scorer_passes: tuple = (),
        evidence_refs: tuple = (),
    ) -> "MemoryArtifactResolver":
        scenario_map = {(doc["scenario_id"], doc["scenario_version"]): doc for doc in scenarios}
        configuration_map = {doc["configuration_id"]: doc for doc in configurations}
        experiment_map = {doc["experiment_id"]: doc for doc in experiments}
        run_map = {doc["run_id"]: doc for doc in runs}
        scorer_pass_map = {doc["scorer_pass_id"]: doc for doc in scorer_passes}
        evidence_ref_map = {doc["evidence_ref_id"]: doc for doc in evidence_refs}
        return MemoryArtifactResolver(
            scenarios=scenario_map,
            configurations=configuration_map,
            experiments=experiment_map,
            runs=run_map,
            scorer_passes=scorer_pass_map,
            evidence_refs=evidence_ref_map,
        )

    def resolve_scenario(self, scenario_id: str, scenario_version: int) -> dict | None:
        return self.scenarios.get((scenario_id, scenario_version))

    def resolve_configuration(self, configuration_id: str) -> dict | None:
        return self.configurations.get(configuration_id)

    def resolve_experiment(self, experiment_id: str) -> dict | None:
        return self.experiments.get(experiment_id)

    def resolve_run(self, run_id: str) -> dict | None:
        return self.runs.get(run_id)

    def resolve_scorer_pass(self, scorer_pass_id: str) -> dict | None:
        return self.scorer_passes.get(scorer_pass_id)

    def resolve_evidence_ref(self, evidence_ref_id: str) -> dict | None:
        return self.evidence_refs.get(evidence_ref_id)
