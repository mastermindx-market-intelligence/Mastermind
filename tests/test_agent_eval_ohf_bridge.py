"""EVAL-OHF2: tests for the OHF-to-R0 bridge (``scripts/agent_eval/ohf_bridge.py``).

Plan record: ``docs/superpowers/plans/2026-09-01-agent-evaluation-ohf2-integration.md``.

Most OHF artifact/manifest fixtures here are hand-rendered to the exact
documented format (plan record §2), not produced by importing PR #162's
unmerged ``scripts/ohf/fresh_sol_eval.py`` -- this is the "as data" proof
the packet requires. `test_bridges_harness_written_real_bytes_fixture_end_to_end`
is the exception (review repair MAJOR-2): it bridges a REAL harness-written
artifact + manifest, committed verbatim under
``tests/fixtures/agent_eval_ohf_bridge/`` (see that directory's README for
exact provenance). All data anywhere in this file is synthetic and
PUBLIC_SAFE.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import pytest
import yaml

from scripts.agent_eval import contracts, scoring, store
from scripts.agent_eval.canonical import digest_value
from tests.agent_eval_factories import (
    ENVIRONMENT_DIGEST,
    PROFILE_DIGEST,
    SANDBOX_DIGEST,
    build_baseline_scenario_fields,
    fresh_configuration_id,
    fresh_experiment_id,
)

from scripts.agent_eval import ohf_bridge

REPO_REF_BASE = ohf_bridge.REPO_REF_PREFIX + "a" * 40
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "agent_eval_ohf_bridge"

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


def _fresh_run_id() -> str:
    """Review repair BLOCKER-1: the real harness emits ``uuid.uuid4().hex``
    -- 32 lower-case hex characters, no dashes. Every fixture in this file
    uses that exact shape now, not the dashed ``str(uuid.uuid4())`` form."""
    return uuid.uuid4().hex


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


def _render_and_package(fields: dict, *, prompt: str, output: str) -> tuple[bytes, dict]:
    """Render one fixture to bytes and its self-consistent manifest (NB-4:
    every draft-building call in this file now goes through
    ``artifact_bytes`` + ``manifest``, never a pre-parsed object)."""
    text = _render_ohf_artifact(fields, prompt=prompt, output=output)
    artifact_bytes = text.encode("utf-8")
    entry = _manifest_entry(
        run_id=fields["run_id"],
        arm=fields["arm"],
        scenario_id=fields["scenario_id"],
        relative_path=f"runs/{fields['arm']}/{fields['scenario_id']}/{fields['run_id']}.md",
        artifact_bytes=artifact_bytes,
    )
    return artifact_bytes, _manifest_for([entry])


# ---------------------------------------------------------------------------
# Synthetic R0 scenario/configuration/experiment (plan record §5.1: proven
# scenario-agnostically, using an amended baseline synthetic scenario)
# ---------------------------------------------------------------------------


def _build_ohf_scenario() -> dict:
    """The shared baseline synthetic scenario, amended (review repair
    MAJOR-3) to explicitly ALLOW the
    ``OHF_F0_NO_SOURCE_OBSERVATION_STREAM`` dependency degradation -- a
    strict superset of the original allowed-degradations set, so this
    scenario is safe to reuse everywhere in this file, whether or not a
    given test actually exercises that degradation."""
    fields = dict(build_baseline_scenario_fields())
    fields["execution_policy"] = dict(fields["execution_policy"])
    fields["execution_policy"]["allowed_degradations"] = sorted(
        set(fields["execution_policy"]["allowed_degradations"]) | {ohf_bridge.OHF_NO_SOURCE_OBSERVATION_DEGRADATION}
    )
    return contracts.build_scenario(fields)


def _build_configuration(*, arm_name: str, auth_realm_class: str = "CHATGPT") -> dict:
    scenario = _build_ohf_scenario()
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


def _draft_kwargs(scenario, configuration, experiment, *, ohf_ref="ref#a", observed_sources=(), observations_are_absent=True):
    return dict(
        scenario=scenario,
        configuration=configuration,
        experiment=experiment,
        runner_code_ref=REPO_REF_BASE,
        ohf_artifact_ref=ohf_ref,
        replicate_index=1,
        pair_key=_pair_key(scenario, 1),
        observed_sources=observed_sources,
        observations_are_absent=observations_are_absent,
        observed_capability_ids=("read_file",),
    )


# ---------------------------------------------------------------------------
# 1. Frontmatter/section parsing
# ---------------------------------------------------------------------------


def test_parse_ohf_artifact_text_round_trips_clean_fixture() -> None:
    prompt = "Read the fixture and answer."
    output = "The canonical owner is X."
    fields = _base_ohf_fields(run_id=_fresh_run_id(), prompt=prompt)
    text = _render_ohf_artifact(fields, prompt=prompt, output=output)

    artifact = ohf_bridge.parse_ohf_artifact_text(text)

    assert artifact.frontmatter == fields
    assert artifact.prompt == prompt
    assert artifact.output == output


def test_parse_ohf_artifact_text_rejects_missing_frontmatter_field() -> None:
    prompt = "p"
    full_fields = _base_ohf_fields(run_id=_fresh_run_id(), prompt=prompt)
    text = _render_ohf_artifact(full_fields, prompt=prompt, output="o")
    # corrupt a real rendered text directly -- strip one required field's line
    text = text.replace("harness_version: 0.1.0\n", "")

    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.parse_ohf_artifact_text(text)
    assert exc_info.value.code == "OHF_ARTIFACT_SHAPE_INVALID"


def test_parse_ohf_artifact_text_rejects_wrong_schema() -> None:
    prompt = "p"
    fields = _base_ohf_fields(run_id=_fresh_run_id(), prompt=prompt)
    fields["schema"] = "some.other.schema/v1"
    text = _render_ohf_artifact(fields, prompt=prompt, output="o")

    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.parse_ohf_artifact_text(text)
    assert exc_info.value.code == "OHF_ARTIFACT_SCHEMA_MISMATCH"


def test_parse_ohf_artifact_text_rejects_prompt_digest_mismatch() -> None:
    prompt = "the real prompt"
    fields = _base_ohf_fields(run_id=_fresh_run_id(), prompt=prompt)
    text = _render_ohf_artifact(fields, prompt="a different prompt entirely", output="o")

    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.parse_ohf_artifact_text(text)
    assert exc_info.value.code == "OHF_ARTIFACT_PROMPT_DIGEST_MISMATCH"


# ---------------------------------------------------------------------------
# 4/NB-4. Duplicate keys, inline empty list, multiple sections, wrapped list item
# ---------------------------------------------------------------------------


def test_duplicate_frontmatter_key_fails_closed_regression() -> None:
    """Reviewer probe I1 (regression)."""
    prompt = "p"
    fields = _base_ohf_fields(run_id=_fresh_run_id(), prompt=prompt)
    text = _render_ohf_artifact(fields, prompt=prompt, output="o")
    text = text.replace(
        "schema: mastermind.fresh_sol_eval_run/v1\n",
        "schema: mastermind.fresh_sol_eval_run/v1\nschema: mastermind.fresh_sol_eval_run/v1\n",
        1,
    )

    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.parse_ohf_artifact_text(text)
    assert exc_info.value.code == "OHF_ARTIFACT_SHAPE_INVALID"


def test_duplicate_output_section_fails_closed_regression() -> None:
    """Reviewer probe I2 (regression): a second, injected '## Exact model
    output' section (e.g. to smuggle extra text past a naive first-match
    parser) must be refused, not silently accepted via the first match."""
    prompt = "p"
    fields = _base_ohf_fields(run_id=_fresh_run_id(), prompt=prompt)
    text = _render_ohf_artifact(fields, prompt=prompt, output="o")
    injected = text + "\n## Exact model output\n\n```text\nsmuggled extra output\n```\n"

    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.parse_ohf_artifact_text(injected)
    assert exc_info.value.code == "OHF_ARTIFACT_SHAPE_INVALID"


def test_inline_empty_list_form_fails_closed() -> None:
    """Review repair item 7b: PyYAML renders an EMPTY list in its inline
    flow form (``key: []``) even under block style, since block style has
    no items to enumerate. Refused, never silently treated as the literal
    string '[]'."""
    prompt = "p"
    fields = _base_ohf_fields(run_id=_fresh_run_id(), prompt=prompt)
    text = _render_ohf_artifact(fields, prompt=prompt, output="o")
    old_block = "procedure_source_blobs:\n" + "".join(f"- {blob}\n" for blob in PROCEDURE_SOURCE_BLOBS)
    assert old_block in text
    text = text.replace(old_block, "procedure_source_blobs: []\n")

    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.parse_ohf_artifact_text(text)
    assert exc_info.value.code == "OHF_ARTIFACT_SHAPE_INVALID"


def test_yaml_folded_list_item_fails_closed_regression() -> None:
    """Review repair item 7a: a ``procedure_source_blobs`` value long
    enough AND containing whitespace makes PyYAML's default emitter fold
    the plain scalar onto a continuation line (empirically confirmed:
    ``yaml.safe_dump`` wraps at word boundaries past its default 80-col
    width). Rendered here with the REAL ``yaml`` module (not this file's
    own hand-rendering helper) to prove the exact real byte shape, not
    just our own mimicry of it. The continuation line matches neither a
    ``key:`` line nor a fresh ``- item`` line, so parsing already stops
    and fails closed on it -- pinned here as a permanent regression."""
    prompt = "p"
    fields = _base_ohf_fields(run_id=_fresh_run_id(), prompt=prompt)
    long_wrapping_path = (
        "skillpack path with enough separate words to force PyYAML to fold this very long plain "
        "scalar past its default eighty column width budget@" + "a" * 40
    )
    fields["procedure_source_blobs"] = [long_wrapping_path]
    front = yaml.safe_dump(fields, sort_keys=False, default_flow_style=False, allow_unicode=True)
    assert "\n  " in front, "fixture premise failed: PyYAML did not fold this scalar -- test no longer exercises the wrap"
    text = f"---\n{front}---\n\n## Exact prompt\n\n```text\np\n```\n\n## Exact model output\n\n```text\no\n```\n"

    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.parse_ohf_artifact_text(text)
    assert exc_info.value.code == "OHF_ARTIFACT_SHAPE_INVALID"


# ---------------------------------------------------------------------------
# 2/NB-5. Manifest tamper detection + manifest/frontmatter identity cross-check
# ---------------------------------------------------------------------------


def test_verify_ohf_manifest_entry_detects_tampered_bytes() -> None:
    run_id = _fresh_run_id()
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
        ohf_bridge.verify_ohf_manifest_entry(manifest, run_id=_fresh_run_id(), artifact_bytes=b"x")
    assert exc_info.value.code == "OHF_MANIFEST_ENTRY_MISSING"


def test_verify_ohf_manifest_entry_accepts_matching_bytes() -> None:
    run_id = _fresh_run_id()
    artifact_bytes = b"artifact content v1"
    entry = _manifest_entry(run_id=run_id, arm="control-1.0.0", scenario_id="S2", relative_path="runs/x.md", artifact_bytes=artifact_bytes)
    manifest = _manifest_for([entry])

    result = ohf_bridge.verify_ohf_manifest_entry(manifest, run_id=run_id, artifact_bytes=artifact_bytes)
    assert result == entry


def test_manifest_frontmatter_identity_mismatch_fails_closed_regression() -> None:
    """Review repair NB-5 (reviewer probe I4, regression): the manifest
    entry's own claimed ``arm`` disagrees with the artifact's OWN
    frontmatter ``arm`` -- byte-identical, correctly-hashed, but
    relabeled. The digest check alone would pass; the identity
    cross-check must still refuse."""
    prompt = "p"
    fields = _base_ohf_fields(run_id=_fresh_run_id(), arm="control-1.0.0", prompt=prompt)
    text = _render_ohf_artifact(fields, prompt=prompt, output="o")
    artifact_bytes = text.encode("utf-8")
    entry = _manifest_entry(
        run_id=fields["run_id"],
        arm="amended-1.1.0",  # deliberately wrong -- frontmatter says control-1.0.0
        scenario_id=fields["scenario_id"],
        relative_path="runs/x.md",
        artifact_bytes=artifact_bytes,
    )
    manifest = _manifest_for([entry])
    scenario = _build_ohf_scenario()
    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    experiment = _build_experiment(scenario, config_control, config_amended)

    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.build_run_draft_from_ohf(
            artifact_bytes, manifest, run_id=fields["run_id"], **_draft_kwargs(scenario, config_control, experiment)
        )
    assert exc_info.value.code == "OHF_ARTIFACT_DIGEST_TAMPERED"


# ---------------------------------------------------------------------------
# 3/BLOCKER-1. Full fake journey: OHF artifact -> R0 run -> store -> scorer -> evidence ref
# ---------------------------------------------------------------------------


def test_full_fake_journey_produces_valid_run_in_real_store(tmp_path: Path) -> None:
    """Demonstrates a GENUINELY earned VALID run: real observed_sources
    matching the scenario's own allowlist (not the MAJOR-3 acknowledgment
    escape hatch)."""
    artifact_store = store.ArtifactStore(tmp_path / "artifact_root")
    scenario = _build_ohf_scenario()
    artifact_store.create(scenario)

    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    artifact_store.create(config_control)
    artifact_store.create(config_amended)

    experiment = _build_experiment(scenario, config_control, config_amended)
    artifact_store.create(experiment)

    prompt = "Identify the canonical owner for the synthetic fixture."
    output = "The canonical owner is the fixture registry."
    ohf_run_id = _fresh_run_id()
    fields = _base_ohf_fields(run_id=ohf_run_id, arm="control-1.0.0", prompt=prompt)
    artifact_bytes, manifest = _render_and_package(fields, prompt=prompt, output=output)

    real_source = dict(scenario["source_policy"]["allowlist_artifacts"][0])

    # prove build_run_draft_from_ohf works standalone too (not only via
    # the combined finalize_and_publish_ohf_run below)
    draft = ohf_bridge.build_run_draft_from_ohf(
        artifact_bytes,
        manifest,
        run_id=ohf_run_id,
        scenario=scenario,
        configuration=config_control,
        experiment=experiment,
        runner_code_ref=REPO_REF_BASE,
        ohf_artifact_ref=REPO_REF_BASE + "#runs/control-1.0.0/S2/x.md",
        replicate_index=1,
        pair_key=_pair_key(scenario, 1),
        observed_sources=(real_source,),
        observed_capability_ids=("read_file",),
        observed_tool_schema_digests=(),
        expected_ohf_scenario_code="S2",
    )
    assert draft["schema"] == contracts.RUN_DRAFT_SCHEMA
    assert draft["observations"]["observed_sources"] == [real_source]

    run = ohf_bridge.finalize_and_publish_ohf_run(
        artifact_store, artifact_bytes, manifest, run_id=ohf_run_id,
        scenario=scenario, configuration=config_control, experiment=experiment,
        runner_code_ref=REPO_REF_BASE, ohf_artifact_ref=REPO_REF_BASE + "#runs/control-1.0.0/S2/x.md",
        replicate_index=1, pair_key=_pair_key(scenario, 1),
        observed_sources=(real_source,), observed_capability_ids=("read_file",),
        expected_ohf_scenario_code="S2", **VALIDATOR_KW,
    )

    assert run["validity"]["status"] == "VALID"
    assert run["validity"]["reason_codes"] == []
    assert run["run_id"] == f"run:{uuid.UUID(hex=ohf_run_id)}"
    assert run["comparison"]["arm_id"] == "control-1-0-0"
    assert run["observations"]["dependency_degradations"] == []

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
    scenario = _build_ohf_scenario()
    artifact_store.create(scenario)
    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    artifact_store.create(config_control)
    artifact_store.create(config_amended)
    experiment = _build_experiment(scenario, config_control, config_amended)
    artifact_store.create(experiment)

    prompt = "Identify the canonical owner for the synthetic fixture."
    output = "The canonical owner is the fixture registry."
    ohf_run_id = _fresh_run_id()
    fields = _base_ohf_fields(run_id=ohf_run_id, arm="control-1.0.0", prompt=prompt, model_served="gpt-5.5-different")
    artifact_bytes, manifest = _render_and_package(fields, prompt=prompt, output=output)

    run = ohf_bridge.finalize_and_publish_ohf_run(
        artifact_store, artifact_bytes, manifest, run_id=ohf_run_id,
        expected_ohf_scenario_code="S2", **VALIDATOR_KW,
        **_draft_kwargs(scenario, config_control, experiment, ohf_ref=REPO_REF_BASE + "#runs/control-1.0.0/S2/y.md"),
    )

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
# MAJOR-3: unearned source_integrity PASS -- explicit acknowledgment +
# recorded degradation, resulting validity/scorer state reported honestly
# ---------------------------------------------------------------------------


def test_build_run_draft_refuses_empty_observed_sources_without_acknowledgment() -> None:
    scenario = _build_ohf_scenario()
    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    experiment = _build_experiment(scenario, config_control, config_amended)
    prompt = "p"
    fields = _base_ohf_fields(run_id=_fresh_run_id(), prompt=prompt)
    artifact_bytes, manifest = _render_and_package(fields, prompt=prompt, output="o")

    kwargs = _draft_kwargs(scenario, config_control, experiment)
    kwargs["observations_are_absent"] = False  # NOT acknowledged
    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.build_run_draft_from_ohf(artifact_bytes, manifest, run_id=fields["run_id"], **kwargs)
    assert exc_info.value.code == "OHF_OBSERVATION_FIELD_REQUIRED"


def test_build_run_draft_records_degradation_when_observations_acknowledged_absent() -> None:
    scenario = _build_ohf_scenario()
    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    experiment = _build_experiment(scenario, config_control, config_amended)
    prompt = "p"
    fields = _base_ohf_fields(run_id=_fresh_run_id(), prompt=prompt)
    artifact_bytes, manifest = _render_and_package(fields, prompt=prompt, output="o")

    draft = ohf_bridge.build_run_draft_from_ohf(
        artifact_bytes, manifest, run_id=fields["run_id"], **_draft_kwargs(scenario, config_control, experiment)
    )
    assert draft["observations"]["dependency_degradations"] == [ohf_bridge.OHF_NO_SOURCE_OBSERVATION_DEGRADATION]
    assert draft["observations"]["observed_sources"] == []


def test_major3_resulting_state_is_degraded_dependency_not_special_cased(tmp_path: Path) -> None:
    """The MAJOR-3 resulting-state report: with the acknowledgment given,
    R0's OWN unmodified validity engine computes DEGRADED_DEPENDENCY (the
    scenario used here explicitly allows the degradation -- see
    ``_build_ohf_scenario``). This bridge never special-cases the outcome
    to preserve VALID. The degraded run stays fully visible in evidence-
    ref denominators (never silently folded into valid_count) -- and the
    technical_integrity scorer's ``source_integrity`` dimension is
    reported HONESTLY here too: it still evaluates PASS, because S1's
    existing scorer (out of this wave's OWNED FILES, not modified here)
    derives that dimension purely from LEAKAGE reason codes, which an
    empty ``observed_sources`` vacuously satisfies regardless of the
    run's overall DEGRADED_DEPENDENCY status. That is a disclosed,
    known limitation (module docstring / plan record §5.3), not hidden
    by this test."""
    artifact_store = store.ArtifactStore(tmp_path / "artifact_root")
    scenario = _build_ohf_scenario()
    artifact_store.create(scenario)
    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    artifact_store.create(config_control)
    artifact_store.create(config_amended)
    experiment = _build_experiment(scenario, config_control, config_amended)
    artifact_store.create(experiment)

    prompt = "p"
    output = "o"
    ohf_run_id = _fresh_run_id()
    fields = _base_ohf_fields(run_id=ohf_run_id, prompt=prompt)
    artifact_bytes, manifest = _render_and_package(fields, prompt=prompt, output=output)

    run = ohf_bridge.finalize_and_publish_ohf_run(
        artifact_store, artifact_bytes, manifest, run_id=ohf_run_id,
        **VALIDATOR_KW, **_draft_kwargs(scenario, config_control, experiment),
    )

    # --- resulting validity state: DEGRADED_DEPENDENCY, honestly computed ---
    assert run["validity"]["status"] == "DEGRADED_DEPENDENCY"
    assert run["observations"]["dependency_degradations"] == [ohf_bridge.OHF_NO_SOURCE_OBSERVATION_DEGRADATION]

    # --- resulting scorer state: source_integrity is PASS (vacuous, disclosed) ---
    scorer_pass = scoring.build_technical_integrity_scorer_pass(
        run, scorer_pass_id=f"scorer-pass:{uuid.uuid4()}", scorer_code_ref=REPO_REF_BASE, created_at="2026-08-30T12:06:00Z"
    )
    artifact_store.create(scorer_pass)
    source_integrity = next(r for r in scorer_pass["dimension_results"] if r["dimension"] == "source_integrity")
    assert source_integrity["status"] == "PASS"
    assert source_integrity["reason_codes"] == []

    # --- resulting evidence-ref state: visible in denominators, not folded into valid ---
    evidence_ref_fields = scoring.summarize_experiment(
        experiment, scenario, artifact_store.enumerate_runs(), artifact_store.enumerate_scorer_passes(),
        evidence_ref_id=f"evidence-ref:{uuid.uuid4()}", intended_owner="person:sol",
        review_at="2026-09-05T00:00:00Z", created_at="2026-08-30T12:07:00Z",
        analysis_version="mastermind.agent_evaluation_r0_analysis.v1",
    )
    assert evidence_ref_fields["counts"]["degraded_count"] == 1
    assert evidence_ref_fields["counts"]["valid_count"] == 0
    assert evidence_ref_fields["counts"]["invalid_count"] == 0
    entry = next(e for e in evidence_ref_fields["run_entries"] if e["run_id"] == run["run_id"])
    assert entry["technical_validity"] == "DEGRADED_DEPENDENCY"

    assert artifact_store.verify_tree_graph() == ()


# ---------------------------------------------------------------------------
# 5/BLOCKER-1. Fail-closed paths
# ---------------------------------------------------------------------------


def test_build_run_draft_fails_closed_on_cleanup_not_proven() -> None:
    scenario = _build_ohf_scenario()
    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    experiment = _build_experiment(scenario, config_control, config_amended)
    prompt = "p"
    fields = _base_ohf_fields(run_id=_fresh_run_id(), prompt=prompt, cleanup_proof="TERMINATED/private_group_empty=False")
    artifact_bytes, manifest = _render_and_package(fields, prompt=prompt, output="o")

    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.build_run_draft_from_ohf(
            artifact_bytes, manifest, run_id=fields["run_id"], **_draft_kwargs(scenario, config_control, experiment)
        )
    assert exc_info.value.code == "OHF_CLEANUP_PROOF_NOT_EMPTY"


def test_build_run_draft_fails_closed_on_non_hex32_run_id() -> None:
    """Shape mismatch -- not even 32 lower-case hex characters."""
    scenario = _build_ohf_scenario()
    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    experiment = _build_experiment(scenario, config_control, config_amended)
    prompt = "p"
    fields = _base_ohf_fields(run_id="not-a-uuid4", prompt=prompt)
    artifact_bytes, manifest = _render_and_package(fields, prompt=prompt, output="o")

    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.build_run_draft_from_ohf(
            artifact_bytes, manifest, run_id=fields["run_id"], **_draft_kwargs(scenario, config_control, experiment)
        )
    assert exc_info.value.code == "OHF_RUN_ID_NOT_UUID4"


def test_build_run_draft_fails_closed_on_genuine_non_uuid4_version() -> None:
    """32-hex, syntactically UUID-shaped, but version nibble is 1, not 4."""
    scenario = _build_ohf_scenario()
    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    experiment = _build_experiment(scenario, config_control, config_amended)
    prompt = "p"
    uuid1_shaped_hex = "00000000000010008000000000000001"[:32]
    assert len(uuid1_shaped_hex) == 32
    assert uuid.UUID(hex=uuid1_shaped_hex).version == 1
    fields = _base_ohf_fields(run_id=uuid1_shaped_hex, prompt=prompt)
    artifact_bytes, manifest = _render_and_package(fields, prompt=prompt, output="o")

    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.build_run_draft_from_ohf(
            artifact_bytes, manifest, run_id=fields["run_id"], **_draft_kwargs(scenario, config_control, experiment)
        )
    assert exc_info.value.code == "OHF_RUN_ID_NOT_UUID4"


def test_build_run_draft_accepts_real_harness_hex32_run_id_shape() -> None:
    """BLOCKER-1 pin: the exact shape the real harness emits
    (``uuid.uuid4().hex``) is accepted and normalized to R0's canonical
    dashed run_id."""
    scenario = _build_ohf_scenario()
    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    experiment = _build_experiment(scenario, config_control, config_amended)
    prompt = "p"
    ohf_run_id = uuid.uuid4().hex
    assert len(ohf_run_id) == 32 and "-" not in ohf_run_id
    fields = _base_ohf_fields(run_id=ohf_run_id, prompt=prompt)
    artifact_bytes, manifest = _render_and_package(fields, prompt=prompt, output="o")

    draft = ohf_bridge.build_run_draft_from_ohf(
        artifact_bytes, manifest, run_id=ohf_run_id, **_draft_kwargs(scenario, config_control, experiment)
    )
    assert draft["run_id"] == f"run:{uuid.UUID(hex=ohf_run_id)}"


def test_build_run_draft_fails_closed_on_scenario_code_mismatch() -> None:
    scenario = _build_ohf_scenario()
    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    experiment = _build_experiment(scenario, config_control, config_amended)
    prompt = "p"
    fields = _base_ohf_fields(run_id=_fresh_run_id(), scenario_id="S2", prompt=prompt)
    artifact_bytes, manifest = _render_and_package(fields, prompt=prompt, output="o")

    kwargs = _draft_kwargs(scenario, config_control, experiment)
    kwargs["expected_ohf_scenario_code"] = "S6"
    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.build_run_draft_from_ohf(artifact_bytes, manifest, run_id=fields["run_id"], **kwargs)
    assert exc_info.value.code == "OHF_SCENARIO_CODE_MISMATCH"


def test_build_run_draft_fails_closed_on_auth_realm_shape() -> None:
    scenario = _build_ohf_scenario()
    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    experiment = _build_experiment(scenario, config_control, config_amended)
    prompt = "p"
    fields = _base_ohf_fields(run_id=_fresh_run_id(), prompt=prompt)
    fields["provider_auth_type"] = "chat gpt!"  # not a valid realm-class shape once uppercased
    artifact_bytes, manifest = _render_and_package(fields, prompt=prompt, output="o")

    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.build_run_draft_from_ohf(
            artifact_bytes, manifest, run_id=fields["run_id"], **_draft_kwargs(scenario, config_control, experiment)
        )
    assert exc_info.value.code == "OHF_AUTH_REALM_UNMAPPABLE"


def test_build_run_draft_fails_closed_on_procedure_binding_mismatch() -> None:
    scenario = _build_ohf_scenario()
    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    experiment = _build_experiment(scenario, config_control, config_amended)
    prompt = "p"
    fields = _base_ohf_fields(run_id=_fresh_run_id(), prompt=prompt)
    fields["procedure_source_blobs"] = ["a/different/blob@" + "f" * 40]  # does not match config's instruction_bundle digest
    artifact_bytes, manifest = _render_and_package(fields, prompt=prompt, output="o")

    with pytest.raises(ohf_bridge.OhfBridgeError) as exc_info:
        ohf_bridge.build_run_draft_from_ohf(
            artifact_bytes, manifest, run_id=fields["run_id"], **_draft_kwargs(scenario, config_control, experiment)
        )
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
    scenario = _build_ohf_scenario()
    artifact_store.create(scenario)
    config_control = _build_configuration(arm_name="control-1.0.0")
    config_amended = _build_configuration(arm_name="amended-1.1.0")
    artifact_store.create(config_control)
    artifact_store.create(config_amended)
    experiment = _build_experiment(scenario, config_control, config_amended)
    artifact_store.create(experiment)

    prompt = "p"
    ohf_run_id = _fresh_run_id()
    fields = _base_ohf_fields(run_id=ohf_run_id, prompt=prompt)
    artifact_bytes, manifest = _render_and_package(fields, prompt=prompt, output="o")
    run = ohf_bridge.finalize_and_publish_ohf_run(
        artifact_store, artifact_bytes, manifest, run_id=ohf_run_id,
        **VALIDATOR_KW, **_draft_kwargs(scenario, config_control, experiment, ohf_ref="ref#z"),
    )
    run_bytes_before = (artifact_store.root / "runs" / run["run_id"].split(":")[1] / "receipt.json").read_bytes()

    scorer_pass = scoring.build_technical_integrity_scorer_pass(
        run, scorer_pass_id=f"scorer-pass:{uuid.uuid4()}", scorer_code_ref=REPO_REF_BASE, created_at="2026-08-30T12:05:00Z"
    )
    artifact_store.create(scorer_pass)

    run_bytes_after = (artifact_store.root / "runs" / run["run_id"].split(":")[1] / "receipt.json").read_bytes()
    assert run_bytes_before == run_bytes_after


# ---------------------------------------------------------------------------
# MAJOR-2: harness-written real-bytes fixture, bridged end-to-end
# ---------------------------------------------------------------------------

FIXTURE_RUN_ID = "1cdaa1b19b584d50ba012dc3910637eb"
FIXTURE_ARM = "control-1.0.0"
FIXTURE_SCENARIO_CODE = "S2"
FIXTURE_ARTIFACT_PATH = FIXTURE_DIR / "runs" / FIXTURE_ARM / FIXTURE_SCENARIO_CODE / f"{FIXTURE_RUN_ID}.md"
FIXTURE_MANIFEST_PATH = FIXTURE_DIR / "MANIFEST.json"

# Must match the generator script's own procedure_source_blobs/context
# sha256 exactly (tests/fixtures/agent_eval_ohf_bridge/README.md).
_FIXTURE_PROCEDURE_SOURCE_BLOBS = [
    "skillpack/control/SKILL.md@" + "a" * 40,
    "skillpack/control/AGENTS.md@" + "b" * 40,
]
_FIXTURE_PROCEDURE_CONTEXT_SHA256 = hashlib.sha256(b"synthetic-ohf2-fixture-context").hexdigest()
_FIXTURE_INSTRUCTION_BUNDLE_DIGEST = digest_value(
    {
        "procedure_source_blobs": sorted(_FIXTURE_PROCEDURE_SOURCE_BLOBS),
        "procedure_context_sha256": _FIXTURE_PROCEDURE_CONTEXT_SHA256,
    }
)


def _build_configuration_for_fixture(*, arm_name: str, auth_realm_class: str = "CHATGPT") -> dict:
    scenario = _build_ohf_scenario()
    fields = ohf_bridge.build_ohf_arm_configuration_fields(
        arm_name,
        configuration_id=fresh_configuration_id(),
        instruction_bundle={"artifact_ref": REPO_REF_BASE + "#fixtures/instructions.md", "digest": _FIXTURE_INSTRUCTION_BUNDLE_DIGEST},
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


def test_bridges_harness_written_real_bytes_fixture_end_to_end(tmp_path: Path) -> None:
    """Review repair MAJOR-2: bridges the COMMITTED, harness-written
    (real ``write_run_artifact``, real ``yaml.safe_dump``) fixture bytes
    under ``tests/fixtures/agent_eval_ohf_bridge/`` through the full
    pipeline: parse -> draft -> finalize -> store -> scorer -> tree-graph
    verification -- reading the files from disk exactly as a production
    caller would, not constructing them in-process."""
    assert FIXTURE_ARTIFACT_PATH.exists(), f"missing committed fixture: {FIXTURE_ARTIFACT_PATH}"
    artifact_bytes = FIXTURE_ARTIFACT_PATH.read_bytes()
    manifest = json.loads(FIXTURE_MANIFEST_PATH.read_text(encoding="utf-8"))

    # sanity: this really is real harness-emitted bytes, quoting timestamps
    # the way PyYAML does and using a bare 32-hex run_id (BLOCKER-1's own
    # premise) -- not this test file's own hand-rendering.
    assert b"started_at: '2026-09-01T12:00:00.123456Z'" in artifact_bytes
    assert FIXTURE_RUN_ID.encode() in artifact_bytes
    assert "-" not in FIXTURE_RUN_ID

    artifact_store = store.ArtifactStore(tmp_path / "artifact_root")
    scenario = _build_ohf_scenario()
    artifact_store.create(scenario)
    config_control = _build_configuration_for_fixture(arm_name="control-1.0.0")
    config_amended = _build_configuration_for_fixture(arm_name="amended-1.1.0")
    artifact_store.create(config_control)
    artifact_store.create(config_amended)
    experiment = _build_experiment(scenario, config_control, config_amended)
    artifact_store.create(experiment)

    # the fixture's own timing (2026-09-01) postdates VALIDATOR_KW's
    # default validated_at/created_at (2026-08-30) -- use a local
    # validator_kw that satisfies completed_at <= validated_at <= created_at
    fixture_validator_kw = dict(VALIDATOR_KW, validated_at="2026-09-01T12:01:00Z", created_at="2026-09-01T12:01:01Z")
    run = ohf_bridge.finalize_and_publish_ohf_run(
        artifact_store,
        artifact_bytes,
        manifest,
        run_id=FIXTURE_RUN_ID,
        **fixture_validator_kw,
        **_draft_kwargs(
            scenario, config_control, experiment, ohf_ref=REPO_REF_BASE + f"#{FIXTURE_ARTIFACT_PATH.relative_to(FIXTURE_DIR)}"
        ),
        expected_ohf_scenario_code=FIXTURE_SCENARIO_CODE,
    )

    assert run["run_id"] == f"run:{uuid.UUID(hex=FIXTURE_RUN_ID)}"
    # this fixture's caller (this test) acknowledges no source-observation
    # stream (MAJOR-3), so the honest resulting status is DEGRADED_DEPENDENCY,
    # exactly as in test_major3_resulting_state_is_degraded_dependency_not_special_cased.
    assert run["validity"]["status"] == "DEGRADED_DEPENDENCY"
    assert run["comparison"]["arm_id"] == "control-1-0-0"

    reopened = store.ArtifactStore(artifact_store.root)
    assert reopened.resolve_run(run["run_id"]) == run

    scorer_pass = scoring.build_technical_integrity_scorer_pass(
        run, scorer_pass_id=f"scorer-pass:{uuid.uuid4()}", scorer_code_ref=REPO_REF_BASE, created_at="2026-09-01T12:10:00Z"
    )
    artifact_store.create(scorer_pass)

    evidence_ref_fields = scoring.summarize_experiment(
        experiment, scenario, artifact_store.enumerate_runs(), artifact_store.enumerate_scorer_passes(),
        evidence_ref_id=f"evidence-ref:{uuid.uuid4()}", intended_owner="person:sol",
        review_at="2026-09-05T00:00:00Z", created_at="2026-09-01T12:11:00Z",
        analysis_version="mastermind.agent_evaluation_r0_analysis.v1",
    )
    artifact_store.create(evidence_ref_fields)
    assert evidence_ref_fields["counts"]["degraded_count"] == 1

    assert artifact_store.verify_tree_graph() == ()
