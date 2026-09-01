"""EVAL-OHF2: tests for the OHF-to-R0 bridge (``scripts/agent_eval/ohf_bridge.py``).

Plan record: ``docs/superpowers/plans/2026-09-01-agent-evaluation-ohf2-integration.md``.

All OHF artifact/manifest fixtures here are hand-rendered to the exact
documented format (plan record §2), not produced by importing PR #162's
unmerged ``scripts/ohf/fresh_sol_eval.py`` -- this is the "as data" proof
the packet requires. All data is synthetic and PUBLIC_SAFE.
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import pytest

from scripts.agent_eval import contracts, scoring, store
from scripts.agent_eval.canonical import digest_value
from scripts.agent_eval.errors import ContractError
from tests.agent_eval_factories import (
    ENVIRONMENT_DIGEST,
    PROFILE_DIGEST,
    SANDBOX_DIGEST,
    build_baseline_scenario,
    fresh_configuration_id,
    fresh_experiment_id,
)

from scripts.agent_eval import ohf_bridge

REPO_REF_BASE = ohf_bridge.REPO_REF_PREFIX + "a" * 40

VALIDATOR_KW = dict(
    validator_id="mastermind.eval_r0_finalizer.v1",
    validator_version="1",
    validator_code_ref=REPO_REF_BASE,
    validated_at="2026-08-30T12:01:00Z",
    created_at="2026-08-30T12:01:01Z",
)


# ---------------------------------------------------------------------------
# Synthetic OHF artifact rendering (mirrors fresh_sol_eval.py's exact
# write_run_artifact/_evidence_metadata output shape, plan record §2)
# ---------------------------------------------------------------------------

PROCEDURE_SOURCE_BLOBS = [
    "skillpack/SKILL.md@" + "a" * 40,
    "skillpack/AGENTS.md@" + "b" * 40,
]
PROCEDURE_CONTEXT_SHA256 = hashlib.sha256(b"synthetic-context").hexdigest()

_INSTRUCTION_BUNDLE_DIGEST = digest_value(
    {"procedure_source_blobs": sorted(PROCEDURE_SOURCE_BLOBS), "procedure_context_sha256": PROCEDURE_CONTEXT_SHA256}
)


def _render_ohf_frontmatter(fields: dict) -> str:
    lines = []
    for key in ohf_bridge._OHF_REQUIRED_FIELDS:
        value = fields[key]
        if key in ohf_bridge._OHF_LIST_FIELDS:
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"- {item}")
        elif value is None:
            lines.append(f"{key}: null")
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def _render_ohf_artifact(fields: dict, *, prompt: str, output: str) -> str:
    front = _render_ohf_frontmatter(fields)
    return (
        f"---\n{front}---\n\n"
        f"## Exact prompt\n\n```text\n{prompt}\n```\n\n"
        f"## Exact model output\n\n```text\n{output}\n```\n"
    )


def _base_ohf_fields(
    *,
    run_id: str,
    arm: str = "control-1.0.0",
    scenario_id: str = "S2",
    model_served: str = "gpt-5.6-sol",
    prompt: str,
    cleanup_proof: str = "TERMINATED/private_group_empty=True",
    started_at: str = "2026-08-30T12:00:00.123456Z",
    completed_at: str = "2026-08-30T12:00:05.654321Z",
) -> dict:
    return {
        "schema": ohf_bridge.OHF_ARTIFACT_SCHEMA,
        "scenario_id": scenario_id,
        "arm": arm,
        "run_id": run_id,
        "procedure_commit_sha": "51f9942733b86e550bb9169d2a43462bd28e774f",
        "expected_skillpack_version": "1.0.0",
        "procedure_source_blobs": list(PROCEDURE_SOURCE_BLOBS),
        "procedure_context_sha256": PROCEDURE_CONTEXT_SHA256,
        "protocol_sha256": hashlib.sha256(b"synthetic-protocol").hexdigest(),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "model_requested": "gpt-5.6-sol",
        "model_served": model_served,
        "harness_kind": "fake",
        "harness_version": "0.1.0",
        "harness_binary_sha256": hashlib.sha256(b"synthetic-binary").hexdigest(),
        "provider_auth_type": "chatgpt",
        "provider_plan_type": "pro",
        "requires_openai_auth": True,
        "process_pid": 12345,
        "process_pgid": 12345,
        "process_start_identity": hashlib.sha256(b"synthetic-start-identity").hexdigest(),
        "native_thread_id": "thread_" + "c" * 16,
        "started_at": started_at,
        "completed_at": completed_at,
        "cleanup_proof": cleanup_proof,
        "manual_classification": "PENDING_SOL_REVIEW",
    }


def _fresh_run_uuid() -> str:
    return str(uuid.uuid4())


def _manifest_for(entries: list[dict]) -> dict:
    return {"schema": ohf_bridge.OHF_MANIFEST_SCHEMA, "entries": entries}


def _manifest_entry(*, run_id: str, arm: str, scenario_id: str, relative_path: str, artifact_bytes: bytes) -> dict:
    return {
        "run_id": run_id,
        "arm": arm,
        "scenario_id": scenario_id,
        "relative_path": relative_path,
        "artifact_sha256": hashlib.sha256(artifact_bytes).hexdigest(),
    }


# ---------------------------------------------------------------------------
# Synthetic R0 scenario/configuration/experiment (plan record §5.1: proven
# scenario-agnostically, using the existing baseline synthetic scenario)
# ---------------------------------------------------------------------------


def _build_configuration(*, arm_name: str, auth_realm_class: str = "CHATGPT") -> dict:
    scenario = build_baseline_scenario()
    fields = ohf_bridge.build_ohf_arm_configuration_fields(
        arm_name,
        configuration_id=fresh_configuration_id(),
        instruction_bundle={"artifact_ref": REPO_REF_BASE + "#fixtures/instructions.md", "digest": _INSTRUCTION_BUNDLE_DIGEST},
        context_packet={"artifact_ref": REPO_REF_BASE + "#fixtures/context.json", "digest": digest_value({"context": arm_name})},
        execution_surface="app_server",
        execution_surface_version="1.0.0",
        provider="openai",
        model_requested="gpt-5.6-sol",
        reasoning_effort="medium",
        auth_realm_class=auth_realm_class,
        profile_id="read_only_reviewer",
        profile_digest=PROFILE_DIGEST,
        declared_capability_ids=["read_file"],
        declared_tool_schema_digests=[],
        sandbox_digest=SANDBOX_DIGEST,
        network_policy_digest=contracts.compute_scenario_network_policy_digest(scenario),
        environment_digest=ENVIRONMENT_DIGEST,
        randomness_seed=42,
        sampling_parameters_digest=digest_value({"temperature": "0", "arm": arm_name}),
        authorship={"author_ref": "person:sol", "independent_reviewer_ref": "person:auditor"},
        created_at="2026-08-30T00:00:00Z",
    )
    return contracts.build_configuration(fields)


def _build_experiment(scenario: dict, config_a: dict, config_b: dict) -> dict:
    fields = {
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
                {"arm_id": "control-1-0-0", "configuration_id": config_a["configuration_id"], "configuration_digest": config_a["configuration_digest"]},
                {"arm_id": "amended-1-1-0", "configuration_id": config_b["configuration_id"], "configuration_digest": config_b["configuration_digest"]},
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
        "created_at": "2026-08-30T00:00:00Z",
    }
    return contracts.build_experiment(fields)


def _pair_key(scenario: dict, replicate_index: int) -> str:
    return f"pair:{scenario['scenario_id']}:v{scenario['scenario_version']}:r{replicate_index}"


# ---------------------------------------------------------------------------
# 1. Frontmatter/section parsing
# ---------------------------------------------------------------------------


def test_parse_ohf_artifact_text_round_trips_clean_fixture() -> None:
    prompt = "Read the fixture and answer."
    output = "The canonical owner is X."
    fields = _base_ohf_fields(run_id=_fresh_run_uuid(), prompt=prompt)
    text = _render_ohf_artifact(fields, prompt=prompt, output=output)

    artifact = ohf_bridge.parse_ohf_artifact_text(text)

    assert artifact.frontmatter == fields
    assert artifact.prompt == prompt
    assert artifact.output == output


def test_parse_ohf_artifact_text_rejects_missing_frontmatter_field() -> None:
    prompt = "p"
    full_fields = _base_ohf_fields(run_id=_fresh_run_uuid(), prompt=prompt)
    text = _render_ohf_artifact(full_fields, prompt=prompt, output="o")
    # corrupt a real rendered text directly -- strip one required field's line
    text = text.replace("harness_version: 0.1.0\n", "")

    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.parse_ohf_artifact_text(text)
    assert exc_info.value.code == "OHF_ARTIFACT_SHAPE_INVALID"


def test_parse_ohf_artifact_text_rejects_wrong_schema() -> None:
    prompt = "p"
    fields = _base_ohf_fields(run_id=_fresh_run_uuid(), prompt=prompt)
    fields["schema"] = "some.other.schema/v1"
    text = _render_ohf_artifact(fields, prompt=prompt, output="o")

    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.parse_ohf_artifact_text(text)
    assert exc_info.value.code == "OHF_ARTIFACT_SCHEMA_MISMATCH"


def test_parse_ohf_artifact_text_rejects_prompt_digest_mismatch() -> None:
    prompt = "the real prompt"
    fields = _base_ohf_fields(run_id=_fresh_run_uuid(), prompt=prompt)
    text = _render_ohf_artifact(fields, prompt="a different prompt entirely", output="o")

    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.parse_ohf_artifact_text(text)
    assert exc_info.value.code == "OHF_ARTIFACT_PROMPT_DIGEST_MISMATCH"


# ---------------------------------------------------------------------------
# 2. Manifest tamper detection
# ---------------------------------------------------------------------------


def test_verify_ohf_manifest_entry_detects_tampered_bytes() -> None:
    run_id = _fresh_run_uuid()
    artifact_bytes = b"artifact content v1"
    entry = _manifest_entry(run_id=run_id, arm="control-1.0.0", scenario_id="S2", relative_path="runs/x.md", artifact_bytes=artifact_bytes)
    manifest = _manifest_for([entry])

    tampered_bytes = b"artifact content v2 -- TAMPERED"
    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.verify_ohf_manifest_entry(manifest, run_id=run_id, artifact_bytes=tampered_bytes)
    assert exc_info.value.code == "OHF_ARTIFACT_DIGEST_TAMPERED"


def test_verify_ohf_manifest_entry_detects_missing_entry() -> None:
    manifest = _manifest_for([])
    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.verify_ohf_manifest_entry(manifest, run_id=_fresh_run_uuid(), artifact_bytes=b"x")
    assert exc_info.value.code == "OHF_MANIFEST_ENTRY_MISSING"


def test_verify_ohf_manifest_entry_accepts_matching_bytes() -> None:
    run_id = _fresh_run_uuid()
    artifact_bytes = b"artifact content v1"
    entry = _manifest_entry(run_id=run_id, arm="control-1.0.0", scenario_id="S2", relative_path="runs/x.md", artifact_bytes=artifact_bytes)
    manifest = _manifest_for([entry])

    result = ohf_bridge.verify_ohf_manifest_entry(manifest, run_id=run_id, artifact_bytes=artifact_bytes)
    assert result == entry


# ---------------------------------------------------------------------------
# 3. Full fake journey: OHF artifact -> R0 run -> store -> scorer -> evidence ref
# ---------------------------------------------------------------------------


def test_full_fake_journey_produces_valid_run_in_real_store(tmp_path: Path) -> None:
    artifact_store = store.ArtifactStore(tmp_path / "artifact_root")
    scenario = build_baseline_scenario()
    artifact_store.create(scenario)

    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    artifact_store.create(config_control)
    artifact_store.create(config_amended)

    experiment = _build_experiment(scenario, config_control, config_amended)
    artifact_store.create(experiment)

    prompt = "Identify the canonical owner for the synthetic fixture."
    output = "The canonical owner is the fixture registry."
    ohf_run_id = _fresh_run_uuid()
    fields = _base_ohf_fields(run_id=ohf_run_id, arm="control-1.0.0", prompt=prompt)
    artifact_text = _render_ohf_artifact(fields, prompt=prompt, output=output)
    artifact_bytes = artifact_text.encode("utf-8")
    manifest = _manifest_for(
        [_manifest_entry(run_id=ohf_run_id, arm="control-1.0.0", scenario_id="S2", relative_path="runs/control-1.0.0/S2/x.md", artifact_bytes=artifact_bytes)]
    )

    ohf_bridge.verify_ohf_manifest_entry(manifest, run_id=ohf_run_id, artifact_bytes=artifact_bytes)
    artifact = ohf_bridge.parse_ohf_artifact_text(artifact_text)

    draft = ohf_bridge.build_run_draft_from_ohf(
        artifact,
        scenario=scenario,
        configuration=config_control,
        experiment=experiment,
        runner_code_ref=REPO_REF_BASE,
        ohf_artifact_ref=REPO_REF_BASE + "#runs/control-1.0.0/S2/x.md",
        replicate_index=1,
        pair_key=_pair_key(scenario, 1),
        observed_sources=(),
        observed_capability_ids=("read_file",),
        observed_tool_schema_digests=(),
        expected_ohf_scenario_code="S2",
    )

    run = ohf_bridge.finalize_and_publish_ohf_run(
        artifact_store, scenario, config_control, experiment, draft, **VALIDATOR_KW
    )

    assert run["validity"]["status"] == "VALID"
    assert run["validity"]["reason_codes"] == []
    assert run["run_id"] == f"run:{ohf_run_id}"
    assert run["comparison"]["arm_id"] == "control-1-0-0"

    reopened = store.ArtifactStore(artifact_store.root)
    assert reopened.resolve_run(run["run_id"]) == run

    scorer_pass = scoring.build_technical_integrity_scorer_pass(
        run,
        scorer_pass_id=f"scorer-pass:{uuid.uuid4()}",
        scorer_code_ref=REPO_REF_BASE,
        created_at="2026-08-30T12:02:00Z",
    )
    artifact_store.create(scorer_pass)
    assert all(result["status"] == "PASS" for result in scorer_pass["dimension_results"])

    evidence_ref_fields = scoring.summarize_experiment(
        experiment,
        scenario,
        artifact_store.enumerate_runs(),
        artifact_store.enumerate_scorer_passes(),
        evidence_ref_id=f"evidence-ref:{uuid.uuid4()}",
        intended_owner="person:sol",
        review_at="2026-09-05T00:00:00Z",
        created_at="2026-08-30T12:03:00Z",
        analysis_version="mastermind.agent_evaluation_r0_analysis.v1",
    )
    artifact_store.create(evidence_ref_fields)
    assert evidence_ref_fields["counts"]["valid_count"] == 1
    assert evidence_ref_fields["counts"]["total_count"] == 1

    defects = artifact_store.verify_tree_graph()
    assert defects == ()


def test_full_fake_journey_preserves_served_model_mismatch(tmp_path: Path) -> None:
    artifact_store = store.ArtifactStore(tmp_path / "artifact_root")
    scenario = build_baseline_scenario()
    artifact_store.create(scenario)
    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    artifact_store.create(config_control)
    artifact_store.create(config_amended)
    experiment = _build_experiment(scenario, config_control, config_amended)
    artifact_store.create(experiment)

    prompt = "Identify the canonical owner for the synthetic fixture."
    output = "The canonical owner is the fixture registry."
    ohf_run_id = _fresh_run_uuid()
    fields = _base_ohf_fields(run_id=ohf_run_id, arm="control-1.0.0", prompt=prompt, model_served="gpt-5.5-different")
    artifact_text = _render_ohf_artifact(fields, prompt=prompt, output=output)
    artifact = ohf_bridge.parse_ohf_artifact_text(artifact_text)

    draft = ohf_bridge.build_run_draft_from_ohf(
        artifact,
        scenario=scenario,
        configuration=config_control,
        experiment=experiment,
        runner_code_ref=REPO_REF_BASE,
        ohf_artifact_ref=REPO_REF_BASE + "#runs/control-1.0.0/S2/y.md",
        replicate_index=1,
        pair_key=_pair_key(scenario, 1),
        observed_sources=(),
        observed_capability_ids=("read_file",),
        expected_ohf_scenario_code="S2",
    )
    run = ohf_bridge.finalize_and_publish_ohf_run(artifact_store, scenario, config_control, experiment, draft, **VALIDATOR_KW)

    assert run["validity"]["status"] == "INVALID_CONFIGURATION"
    assert "MODEL_SERVED_MISMATCH" in run["validity"]["reason_codes"]

    # preserved through store readback and tree verification -- never dropped
    reopened = store.ArtifactStore(artifact_store.root)
    assert reopened.resolve_run(run["run_id"])["validity"]["status"] == "INVALID_CONFIGURATION"
    assert artifact_store.verify_tree_graph() == ()

    evidence_ref_fields = scoring.summarize_experiment(
        experiment,
        scenario,
        artifact_store.enumerate_runs(),
        artifact_store.enumerate_scorer_passes(),
        evidence_ref_id=f"evidence-ref:{uuid.uuid4()}",
        intended_owner="person:sol",
        review_at="2026-09-05T00:00:00Z",
        created_at="2026-08-30T12:04:00Z",
        analysis_version="mastermind.agent_evaluation_r0_analysis.v1",
    )
    entry = next(e for e in evidence_ref_fields["run_entries"] if e["run_id"] == run["run_id"])
    assert entry["technical_validity"] == "INVALID_CONFIGURATION"
    assert evidence_ref_fields["counts"]["invalid_count"] == 1


# ---------------------------------------------------------------------------
# 5. Fail-closed paths
# ---------------------------------------------------------------------------


def _draft_kwargs(scenario, configuration, experiment, artifact, *, ohf_ref="ref#a"):
    return dict(
        scenario=scenario,
        configuration=configuration,
        experiment=experiment,
        runner_code_ref=REPO_REF_BASE,
        ohf_artifact_ref=ohf_ref,
        replicate_index=1,
        pair_key=_pair_key(scenario, 1),
        observed_sources=(),
        observed_capability_ids=("read_file",),
    )


def test_build_run_draft_fails_closed_on_cleanup_not_proven() -> None:
    scenario = build_baseline_scenario()
    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    experiment = _build_experiment(scenario, config_control, config_amended)
    prompt = "p"
    fields = _base_ohf_fields(run_id=_fresh_run_uuid(), prompt=prompt, cleanup_proof="TERMINATED/private_group_empty=False")
    text = _render_ohf_artifact(fields, prompt=prompt, output="o")
    artifact = ohf_bridge.parse_ohf_artifact_text(text)

    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.build_run_draft_from_ohf(artifact, **_draft_kwargs(scenario, config_control, experiment, artifact))
    assert exc_info.value.code == "OHF_CLEANUP_PROOF_NOT_EMPTY"


def test_build_run_draft_fails_closed_on_non_uuid4_run_id() -> None:
    scenario = build_baseline_scenario()
    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    experiment = _build_experiment(scenario, config_control, config_amended)
    prompt = "p"
    fields = _base_ohf_fields(run_id="not-a-uuid4", prompt=prompt)
    text = _render_ohf_artifact(fields, prompt=prompt, output="o")
    artifact = ohf_bridge.parse_ohf_artifact_text(text)

    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.build_run_draft_from_ohf(artifact, **_draft_kwargs(scenario, config_control, experiment, artifact))
    assert exc_info.value.code == "OHF_RUN_ID_NOT_UUID4"


def test_build_run_draft_fails_closed_on_scenario_code_mismatch() -> None:
    scenario = build_baseline_scenario()
    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    experiment = _build_experiment(scenario, config_control, config_amended)
    prompt = "p"
    fields = _base_ohf_fields(run_id=_fresh_run_uuid(), scenario_id="S2", prompt=prompt)
    text = _render_ohf_artifact(fields, prompt=prompt, output="o")
    artifact = ohf_bridge.parse_ohf_artifact_text(text)

    kwargs = _draft_kwargs(scenario, config_control, experiment, artifact)
    kwargs["expected_ohf_scenario_code"] = "S6"
    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.build_run_draft_from_ohf(artifact, **kwargs)
    assert exc_info.value.code == "OHF_SCENARIO_CODE_MISMATCH"


def test_build_run_draft_fails_closed_on_auth_realm_shape() -> None:
    scenario = build_baseline_scenario()
    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    experiment = _build_experiment(scenario, config_control, config_amended)
    prompt = "p"
    fields = _base_ohf_fields(run_id=_fresh_run_uuid(), prompt=prompt)
    fields["provider_auth_type"] = "chat gpt!"  # not a valid realm-class shape once uppercased
    text = _render_ohf_artifact(fields, prompt=prompt, output="o")
    artifact = ohf_bridge.parse_ohf_artifact_text(text)

    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.build_run_draft_from_ohf(artifact, **_draft_kwargs(scenario, config_control, experiment, artifact))
    assert exc_info.value.code == "OHF_AUTH_REALM_UNMAPPABLE"


def test_build_run_draft_fails_closed_on_procedure_binding_mismatch() -> None:
    scenario = build_baseline_scenario()
    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    experiment = _build_experiment(scenario, config_control, config_amended)
    prompt = "p"
    fields = _base_ohf_fields(run_id=_fresh_run_uuid(), prompt=prompt)
    fields["procedure_source_blobs"] = ["a/different/blob@" + "f" * 40]  # does not match config's instruction_bundle digest
    text = _render_ohf_artifact(fields, prompt=prompt, output="o")
    artifact = ohf_bridge.parse_ohf_artifact_text(text)

    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.build_run_draft_from_ohf(artifact, **_draft_kwargs(scenario, config_control, experiment, artifact))
    assert exc_info.value.code == "OHF_PROCEDURE_BINDING_MISMATCH"


def test_slugify_ohf_arm_replaces_dots() -> None:
    assert ohf_bridge.slugify_ohf_arm("control-1.0.0") == "control-1-0-0"
    assert ohf_bridge.slugify_ohf_arm("amended-1.1.0") == "amended-1-1-0"


def test_build_ohf_arm_configuration_fields_rejects_unknown_arm() -> None:
    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.build_ohf_arm_configuration_fields(
            "unknown-arm",
            configuration_id=fresh_configuration_id(),
            instruction_bundle={"artifact_ref": "x", "digest": digest_value("x")},
            context_packet={"artifact_ref": "x", "digest": digest_value("x")},
            execution_surface="app_server",
            execution_surface_version="1.0.0",
            provider="openai",
            model_requested="gpt-5.6-sol",
            reasoning_effort="medium",
            auth_realm_class="CHATGPT",
            profile_id="p",
            profile_digest=PROFILE_DIGEST,
            declared_capability_ids=[],
            declared_tool_schema_digests=[],
            sandbox_digest=SANDBOX_DIGEST,
            network_policy_digest=digest_value("x"),
            environment_digest=ENVIRONMENT_DIGEST,
            randomness_seed=None,
            sampling_parameters_digest=digest_value("x"),
            authorship={"author_ref": "person:sol", "independent_reviewer_ref": "person:auditor"},
            created_at="2026-08-30T00:00:00Z",
        )
    assert exc_info.value.code == "OHF_UNKNOWN_SKILLPACK_ARM"


# ---------------------------------------------------------------------------
# 6. Scorer pass appends without mutating the run
# ---------------------------------------------------------------------------


def test_scorer_pass_appends_without_mutating_run_bytes(tmp_path: Path) -> None:
    artifact_store = store.ArtifactStore(tmp_path / "artifact_root")
    scenario = build_baseline_scenario()
    artifact_store.create(scenario)
    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    artifact_store.create(config_control)
    artifact_store.create(config_amended)
    experiment = _build_experiment(scenario, config_control, config_amended)
    artifact_store.create(experiment)

    prompt = "p"
    ohf_run_id = _fresh_run_uuid()
    fields = _base_ohf_fields(run_id=ohf_run_id, prompt=prompt)
    text = _render_ohf_artifact(fields, prompt=prompt, output="o")
    artifact = ohf_bridge.parse_ohf_artifact_text(text)
    draft = ohf_bridge.build_run_draft_from_ohf(
        artifact, **_draft_kwargs(scenario, config_control, experiment, artifact, ohf_ref="ref#z")
    )
    run = ohf_bridge.finalize_and_publish_ohf_run(artifact_store, scenario, config_control, experiment, draft, **VALIDATOR_KW)
    run_bytes_before = (artifact_store.root / "runs" / run["run_id"].split(":")[1] / "receipt.json").read_bytes()

    scorer_pass = scoring.build_technical_integrity_scorer_pass(
        run, scorer_pass_id=f"scorer-pass:{uuid.uuid4()}", scorer_code_ref=REPO_REF_BASE, created_at="2026-08-30T12:05:00Z"
    )
    artifact_store.create(scorer_pass)

    run_bytes_after = (artifact_store.root / "runs" / run["run_id"].split(":")[1] / "receipt.json").read_bytes()
    assert run_bytes_before == run_bytes_after
