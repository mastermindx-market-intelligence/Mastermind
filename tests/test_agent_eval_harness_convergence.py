from __future__ import annotations
import copy, json
import pytest
from scripts.agent_eval.canonical import add_document_digest, digest_value
from scripts.agent_eval.contracts import build_configuration, v_artifact_pair
from scripts.agent_eval.errors import ContractError
from scripts.agent_eval.harness_convergence import (
    build_convergence_input_evidence,
    build_environment_manifest,
    build_holdout_commitment,
    validate_environment_manifest,
    verify_configuration_environment_binding,
    verify_holdout_confirmation_eligibility,
)

SHA="a"*40
SRC=f"git:mastermindx-market-intelligence/Mastermind@{SHA}"
D=lambda label:digest_value({"label":label})

def artifact(name):
    return {"artifact_ref":f"evidence/{name}.json","digest":D(name)}

def snapshot():
    return {
        "execution": {
            "execution_surface":"provider-free-local",
            "execution_surface_version":"1",
            "provider":"NONE",
            "model_requested":"NONE",
            "reasoning_effort":"low",
            "auth_realm_class":"NO_PROVIDER",
        },
        "procedure": {
            "protected_source_ref":SRC,
            "skillpack_source_ref":SRC,
            "skillpack_version":"1.0.1",
            "instruction_bundle_digest":D("instructions"),
        },
        "context": {
            "context_packet_digest":D("context"),
            "retrieval_configuration_digest":None,
        },
        "capabilities": {
            "profile_id":"provider-free-h1-h2",
            "profile_digest":D("profile"),
            "declared_capability_ids":["artifact-read","deterministic-score"],
            "declared_tool_schema_digests":sorted([D("tool-a"),D("tool-b")]),
            "sandbox_digest":D("sandbox"),
            "network_policy_digest":D("network"),
        },
        "randomness":{"seed":0,"sampling_parameters_digest":D("sampling")},
    }

def system_manifest():
    return build_environment_manifest(
        manifest_id="envmanifest:123e4567-e89b-42d3-a456-426614174000",
        source_ref=SRC,
        captured_at="2026-09-19T22:00:00Z",
        execution_mode="SYSTEM_REALISTIC",
        claim_scope="SYSTEM_REALISTIC_DESCRIPTIVE_OBSERVATION",
        configuration_snapshot=snapshot(),
        owner_native_evidence=[artifact("owner-native")],
        provider_principal_evidence=[],
        grader_provenance=[artifact("grader-owner")],
        rng_policy="DETERMINISTIC_SEED",
        replicate_count=1,
    )

def configuration(manifest_digest):
    snap=snapshot()
    return build_configuration({
        "configuration_id":"configuration:123e4567-e89b-42d3-a456-426614174001",
        "execution":snap["execution"],
        "procedure": {
            "protected_source_ref":snap["procedure"]["protected_source_ref"],
            "skillpack_source_ref":snap["procedure"]["skillpack_source_ref"],
            "skillpack_version":snap["procedure"]["skillpack_version"],
            "instruction_bundle":{"artifact_ref":"evidence/instructions.json","digest":snap["procedure"]["instruction_bundle_digest"]},
            "handoff":None,
        },
        "context": {
            "context_packet":{"artifact_ref":"evidence/context.json","digest":snap["context"]["context_packet_digest"]},
            "retrieval_configuration":None,
        },
        "capabilities": {**snap["capabilities"],"environment_digest":manifest_digest},
        "randomness":snap["randomness"],
        "authorship":{"author_ref":"sol","independent_reviewer_ref":"chairman-override"},
        "created_at":"2026-09-19T22:01:00Z",
        "supersedes":None,
    })

def holdout():
    secret_items=[
        {"case":"case-1","prompt":"PRIVATE ALPHA CONTENT","expected":"never emit"},
        {"case":"case-2","path":"/private/holdout/two.json","expected":"never emit"},
    ]
    result=build_holdout_commitment(
        commitment_id="holdout:123e4567-e89b-42d3-a456-426614174002",
        task_class="agent-eval-provider-free",
        family="h1-private-confirmation",
        sealed_items=secret_items,
        source_ref=SRC,
        committed_at="2026-09-19T22:02:00Z",
    )
    encoded=json.dumps(result,sort_keys=True)
    assert "PRIVATE ALPHA CONTENT" not in encoded
    assert "/private/holdout/two.json" not in encoded
    assert set(result)=={
        "schema","commitment_id","task_class","family","sample_count","content_digest",
        "source_ref","committed_at","privacy","exposure_state","commitment_digest"
    }
    return result

def codes(exc):
    return {d.code for d in exc.value.defects}

def test_provider_free_environment_binds_existing_configuration_and_scorer_evidence():
    manifest=system_manifest()
    config=configuration(manifest["manifest_digest"])
    assert verify_configuration_environment_binding(config,manifest)=="CONFIGURATION_ENVIRONMENT_BINDING_VERIFIED"
    committed=holdout()
    refs=build_convergence_input_evidence(
        manifest_ref="evidence/environment-manifest.json",
        manifest=manifest,
        holdout_ref="evidence/holdout-commitment.json",
        holdout_commitment=committed,
    )
    assert refs==sorted(refs,key=lambda row:(row["artifact_ref"],row["digest"]))
    assert {row["digest"] for row in refs}=={manifest["manifest_digest"],committed["commitment_digest"]}
    assert [v_artifact_pair(row, f"$.input_evidence[{index}]") for index, row in enumerate(refs)] == refs

def test_exposed_holdout_cannot_be_used_for_confirmation():
    committed=holdout()
    exposed={**committed,"exposure_state":"EXPOSED_DEVELOPMENT"}
    exposed=add_document_digest({k:v for k,v in exposed.items() if k!="commitment_digest"},"commitment_digest")
    with pytest.raises(ContractError) as exc:
        verify_holdout_confirmation_eligibility(exposed)
    assert codes(exc)=={"HOLDOUT_NOT_CONFIRMATION_ELIGIBLE"}

def test_environment_digest_mismatch_refuses_instead_of_substituting_fixture():
    manifest=system_manifest()
    config=configuration(D("wrong-environment"))
    with pytest.raises(ContractError) as exc:
        verify_configuration_environment_binding(config,manifest)
    assert "ENVIRONMENT_DIGEST_MISMATCH" in codes(exc)

def test_configuration_snapshot_mismatch_refuses_even_when_digest_is_copied():
    manifest=system_manifest()
    config=configuration(manifest["manifest_digest"])
    changed=copy.deepcopy(config)
    changed["execution"]["execution_surface_version"]="2"
    changed=add_document_digest({k:v for k,v in changed.items() if k!="configuration_digest"},"configuration_digest")
    with pytest.raises(ContractError) as exc:
        verify_configuration_environment_binding(changed,manifest)
    assert codes(exc)=={"ENVIRONMENT_SNAPSHOT_MISMATCH"}

def test_factor_locked_requires_owner_proven_provider_principal_evidence():
    with pytest.raises(ContractError) as exc:
        build_environment_manifest(
            manifest_id="envmanifest:123e4567-e89b-42d3-a456-426614174003",
            source_ref=SRC,
            captured_at="2026-09-19T22:03:00Z",
            execution_mode="FACTOR_LOCKED",
            claim_scope="FACTOR_LOCKED_STRUCTURAL_COMPARISON",
            configuration_snapshot=snapshot(),
            owner_native_evidence=[artifact("owner-native")],
            provider_principal_evidence=[],
            grader_provenance=[artifact("grader-owner")],
            rng_policy="PREREGISTERED_REPLICATES",
            replicate_count=2,
        )
    assert codes(exc)=={"PROVIDER_PRINCIPAL_EVIDENCE_REQUIRED"}

def test_claim_scope_cannot_promote_system_realistic_observation_to_factor_causality():
    manifest=system_manifest()
    bad={**manifest,"claim_scope":"FACTOR_LOCKED_STRUCTURAL_COMPARISON"}
    bad=add_document_digest({k:v for k,v in bad.items() if k!="manifest_digest"},"manifest_digest")
    with pytest.raises(ContractError) as exc:
        validate_environment_manifest(bad)
    assert codes(exc)=={"CLAIM_SCOPE_MODE_MISMATCH"}

def test_text_only_grader_identity_is_not_provenance():
    with pytest.raises(ContractError) as exc:
        build_environment_manifest(
            manifest_id="envmanifest:123e4567-e89b-42d3-a456-426614174004",
            source_ref=SRC,
            captured_at="2026-09-19T22:04:00Z",
            execution_mode="SYSTEM_REALISTIC",
            claim_scope="SYSTEM_REALISTIC_DESCRIPTIVE_OBSERVATION",
            configuration_snapshot=snapshot(),
            owner_native_evidence=[artifact("owner-native")],
            provider_principal_evidence=[],
            grader_provenance=["self-reported-reviewer"],
            rng_policy="DETERMINISTIC_SEED",
            replicate_count=1,
        )
    assert "NOT_AN_OBJECT" in codes(exc)

def test_unknown_rng_requires_preregistered_replicates():
    with pytest.raises(ContractError) as exc:
        build_environment_manifest(
            manifest_id="envmanifest:123e4567-e89b-42d3-a456-426614174005",
            source_ref=SRC,
            captured_at="2026-09-19T22:05:00Z",
            execution_mode="SYSTEM_REALISTIC",
            claim_scope="SYSTEM_REALISTIC_DESCRIPTIVE_OBSERVATION",
            configuration_snapshot=snapshot(),
            owner_native_evidence=[artifact("owner-native")],
            provider_principal_evidence=[],
            grader_provenance=[artifact("grader-owner")],
            rng_policy="OBSERVED_UNKNOWN",
            replicate_count=1,
        )
    assert codes(exc)=={"REPLICATES_REQUIRED_WHEN_RNG_UNSEEDED"}

def test_environment_evidence_refuses_duplicate_artifact_refs():
    first=artifact("owner-native")
    duplicate={"artifact_ref":first["artifact_ref"],"digest":D("different-owner-proof")}
    with pytest.raises(ContractError) as exc:
        build_environment_manifest(
            manifest_id="envmanifest:123e4567-e89b-42d3-a456-426614174006",
            source_ref=SRC,
            captured_at="2026-09-19T22:06:00Z",
            execution_mode="SYSTEM_REALISTIC",
            claim_scope="SYSTEM_REALISTIC_DESCRIPTIVE_OBSERVATION",
            configuration_snapshot=snapshot(),
            owner_native_evidence=[first,duplicate],
            provider_principal_evidence=[],
            grader_provenance=[artifact("grader-owner")],
            rng_policy="DETERMINISTIC_SEED",
            replicate_count=1,
        )
    assert "DUPLICATE_ARTIFACT_REF" in codes(exc)

def test_environment_evidence_refuses_duplicate_artifact_digests():
    first=artifact("owner-a")
    duplicate={"artifact_ref":"evidence/owner-b.json","digest":first["digest"]}
    with pytest.raises(ContractError) as exc:
        build_environment_manifest(
            manifest_id="envmanifest:123e4567-e89b-42d3-a456-426614174007",
            source_ref=SRC,
            captured_at="2026-09-19T22:07:00Z",
            execution_mode="SYSTEM_REALISTIC",
            claim_scope="SYSTEM_REALISTIC_DESCRIPTIVE_OBSERVATION",
            configuration_snapshot=snapshot(),
            owner_native_evidence=[first,duplicate],
            provider_principal_evidence=[],
            grader_provenance=[artifact("grader-owner")],
            rng_policy="DETERMINISTIC_SEED",
            replicate_count=1,
        )
    assert "DUPLICATE_ARTIFACT_DIGEST" in codes(exc)

def test_convergence_input_evidence_refuses_colliding_artifact_refs():
    manifest=system_manifest()
    committed=holdout()
    with pytest.raises(ContractError) as exc:
        build_convergence_input_evidence(
            manifest_ref="evidence/collision.json",
            manifest=manifest,
            holdout_ref="evidence/collision.json",
            holdout_commitment=committed,
        )
    assert "DUPLICATE_ARTIFACT_REF" in codes(exc)

def test_manifest_authority_and_promotion_ceiling_are_closed():
    manifest=system_manifest()
    promoted={**manifest,"promotion":"AUTOMATIC"}
    promoted=add_document_digest({k:v for k,v in promoted.items() if k!="manifest_digest"},"manifest_digest")
    with pytest.raises(ContractError) as exc:
        validate_environment_manifest(promoted)
    assert codes(exc)=={"NOT_IN_ENUM"}
