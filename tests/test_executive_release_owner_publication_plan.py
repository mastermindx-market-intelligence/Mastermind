"""Publication planning is deterministic source behavior, never host proof."""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from control_plane import executive_release_factory as factory
from control_plane.executive_release_contract import canonical_release_bytes
from ops.executive_os import release_owner_publication_plan as subject
from ops.executive_os import release_owner_resident_inputs as resident
from ops.executive_os import release_owner_staged_inputs as staged
from tests import test_executive_release_owner_resident_inputs as resident_fixture
from tests.test_executive_release_factory import image, inputs, wire
from tests.test_executive_release_owner_staged_inputs import arguments


def _mcp_config(profile: str = "web_ceo_v2") -> bytes:
    return canonical_release_bytes(
        {
            "schema": "mastermind.executive_mcp_install.v1",
            "release_sha": "9" * 40,
            "service_uid": 458,
            "ceo_ingress_socket_path": "/var/run/mastermind-executive/ceo-ingress.sock",
            "port": 8443,
            "policies": {
                "read": {"policy_id": "read-policy"},
                "submit": {"policy_id": "submit-policy"},
            },
            "audit_root": "/var/log/mastermind-executive/mcp-auth",
            "executive_mcp_profile": profile,
        }
    )


def _resident_values(**changes):
    policy = changes.pop("policy", resident_fixture._policy())
    control, broker = resident_fixture._configs()
    values = {
        "owner_installation_id": resident_fixture.OWNER,
        "target_ref": resident_fixture.TARGET,
        "key_id": "release-owner-key.v1",
        "trust_generation": 1,
        "app_generation": 2,
        "registration_generation": 3,
        "registry_generation": 4,
        "release_commit": resident_fixture.COMMIT,
        "release_tree": resident_fixture.TREE,
        "control_config_bytes": control,
        "broker_config_bytes": broker,
        "authority_map_bytes": policy._raw,
        "python_runtime_provenance_digest": resident_fixture.PROVENANCE,
        "provider_attestation_bytes": b'{"accepted":"private-fixture"}\n',
        "provider_attestation_observed_at": resident_fixture.OBSERVED,
        "issuer_binding_receipt": resident_fixture._issuer(policy),
        "issuer_binding_observed_at": resident_fixture.OBSERVED,
        "boot_id": resident_fixture.BOOT,
        "policy": policy,
        "app_peer_uid": 458,
        "mcp_config_bytes": _mcp_config(),
        "requested_mcp_profile": "web_ceo_v2",
        "now_seconds": resident_fixture.NOW,
    }
    values.update(changes)
    return values


def _payloads(plan: subject.PublicationPlan) -> dict[str, bytes]:
    return {payload.path: payload.data for payload in plan.payloads}


def _manifest(plan: subject.PublicationPlan) -> dict:
    return json.loads(plan.manifest_bytes)


def test_resident_plan_delegates_to_reviewed_compilers_and_is_deterministic():
    values = _resident_values()
    plan = subject.compile_resident_publication_plan(**values)
    assert plan == subject.compile_resident_publication_plan(**_resident_values())
    payloads = _payloads(plan)
    assert payloads[subject._REGISTRATION_PATH] == resident.compile_registration(
        owner_installation_id=resident_fixture.OWNER,
        target_ref=resident_fixture.TARGET,
        key_id="release-owner-key.v1",
        trust_generation=1,
        app_generation=2,
        registration_generation=3,
        enabled=False,
    )
    assert payloads[subject._REGISTRY_PATH] == resident.compile_empty_registry(
        registration_generation=3, registry_generation=4
    )
    assert json.loads(payloads[subject._EVIDENCE_PATH])[
        "provider_binary_attestation_digest"
    ] == hashlib.sha256(values["provider_attestation_bytes"]).hexdigest()
    assert tuple(item.path for item in plan.files) == subject._RESIDENT_PATHS
    assert all(
        (item.uid, item.gid, item.mode) == (0, 0, 0o400)
        for item in plan.files
    )


def test_manifest_is_external_hash_metadata_only_and_permanently_disarmed():
    plan = subject.compile_resident_publication_plan(**_resident_values())
    manifest = _manifest(plan)
    assert hashlib.sha256(plan.manifest_bytes).hexdigest() == plan.manifest_sha256
    assert "manifest_sha256" not in manifest
    assert all("data" not in row and "bytes" not in row for row in manifest["files"])
    assert manifest["production_disarming"] == {
        "commit_prepared_release_transition": False,
        "installer_arming": False,
        "worker_start": False,
    }
    assert manifest["context"]["mcp_profile"] == "web_ceo_v2"
    assert manifest["context"]["control_uid"] == json.loads(
        _resident_values()["control_config_bytes"]
    )["control_uid"]
    assert b"private-fixture" not in plan.manifest_bytes
    assert b"release-owner-key.v1" not in plan.manifest_bytes
    assert b"approval" not in plan.manifest_bytes.lower()
    assert b"grant" not in plan.manifest_bytes.lower()


def test_payloads_are_detached_and_every_result_record_is_immutable():
    provider = bytearray(b'{"accepted":"mutable-fixture"}\n')
    plan = subject.compile_resident_publication_plan(
        **_resident_values(provider_attestation_bytes=provider)
    )
    before = tuple(payload.data for payload in plan.payloads)
    provider[:] = b"changed"
    assert tuple(payload.data for payload in plan.payloads) == before
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        plan.kind = "changed"
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        plan.files[0].mode = 0o600
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        plan.payloads[0].data = b"changed"


def test_exact_resident_preimage_is_idempotent_but_partial_or_occupied_is_closed():
    first = subject.compile_resident_publication_plan(**_resident_values())
    payloads = _payloads(first)
    exact = subject.compile_resident_publication_plan(
        **_resident_values(
            existing_registration_bytes=payloads[subject._REGISTRATION_PATH],
            existing_registry_bytes=payloads[subject._REGISTRY_PATH],
            existing_installed_evidence_bytes=payloads[subject._EVIDENCE_PATH],
        )
    )
    assert _manifest(exact)["context"]["resident_preimage"] == "EXACT"
    with pytest.raises(subject.PublicationPlanError, match="^RESIDENT_PREIMAGE_PARTIAL$"):
        subject.compile_resident_publication_plan(
            **_resident_values(
                existing_registration_bytes=payloads[subject._REGISTRATION_PATH]
            )
        )
    registration = json.loads(payloads[subject._REGISTRATION_PATH])
    registration["enabled"] = True
    with pytest.raises(subject.PublicationPlanError, match="^REGISTRATION_ACTIVE$"):
        subject.compile_resident_publication_plan(
            **_resident_values(
                existing_registration_bytes=resident.canonical_file_bytes(registration),
                existing_registry_bytes=payloads[subject._REGISTRY_PATH],
                existing_installed_evidence_bytes=payloads[subject._EVIDENCE_PATH],
            )
        )
    registry = json.loads(payloads[subject._REGISTRY_PATH])
    registry["transitions"] = [{"state": "STAGED"}]
    with pytest.raises(subject.PublicationPlanError, match="^REGISTRY_NOT_EMPTY$"):
        subject.compile_resident_publication_plan(
            **_resident_values(
                existing_registration_bytes=payloads[subject._REGISTRATION_PATH],
                existing_registry_bytes=resident.canonical_file_bytes(registry),
                existing_installed_evidence_bytes=payloads[subject._EVIDENCE_PATH],
            )
        )
    registration = json.loads(payloads[subject._REGISTRATION_PATH])
    registration["owner_installation_id"] = "22222222-2222-4222-8222-222222222222"
    with pytest.raises(
        subject.PublicationPlanError, match="^IDENTITY_ROTATION_UNSUPPORTED$"
    ):
        subject.compile_resident_publication_plan(
            **_resident_values(
                existing_registration_bytes=resident.canonical_file_bytes(registration),
                existing_registry_bytes=payloads[subject._REGISTRY_PATH],
                existing_installed_evidence_bytes=payloads[subject._EVIDENCE_PATH],
            )
        )


def test_profile_replacement_is_rejected_until_composition_is_already_current():
    with pytest.raises(subject.PublicationPlanError, match="^COEXISTENCE_UNPROVEN$"):
        subject.compile_resident_publication_plan(
            **_resident_values(requested_mcp_profile="release_control_v1")
        )
    plan = subject.compile_resident_publication_plan(
        **_resident_values(
            mcp_config_bytes=_mcp_config("release_control_v1"),
            requested_mcp_profile="release_control_v1",
        )
    )
    assert _manifest(plan)["context"]["mcp_profile"] == "release_control_v1"


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":1,"a":2}',
        b'{"a":NaN}',
        b'{"a":1.25}',
        b'{"a":[[[[[[[[[0]]]]]]]]]}',
        b'{"a":"\xff"}',
    ],
)
def test_mcp_document_uses_controlled_canonical_json_failures(raw):
    with pytest.raises(subject.PublicationPlanError, match="^MCP_CONFIG_INVALID$"):
        subject.compile_resident_publication_plan(
            **_resident_values(mcp_config_bytes=raw)
        )


def test_mcp_document_uses_real_installed_configuration_validator():
    document = json.loads(_mcp_config())
    document["service_uid"] = 459
    with pytest.raises(subject.PublicationPlanError, match="^MCP_CONFIG_INVALID$"):
        subject.compile_resident_publication_plan(
            **_resident_values(mcp_config_bytes=canonical_release_bytes(document))
        )


@pytest.mark.parametrize(
    "change,code",
    [
        ({"app_peer_uid": True}, "ISSUER_UID"),
        ({"now_seconds": 1}, "ISSUER_TIME"),
        ({"release_tree": "8" * 40}, "ISSUER_BINDING_MISMATCH"),
        ({"python_runtime_provenance_digest": False}, "INSTALLED_PROVENANCE"),
    ],
)
def test_resident_typed_joins_and_explicit_clock_are_closed(change, code):
    with pytest.raises(subject.PublicationPlanError, match=f"^{code}$"):
        subject.compile_resident_publication_plan(**_resident_values(**change))


def _resident_documents_for_image(image):
    registration = copy.deepcopy(image["reg"])
    registration["enabled"] = False
    registry = {
        "schema": "mastermind.executive_release_owner_staged_registry/v1",
        "registration_generation": registration["registration_generation"],
        "registry_generation": 1,
        "transitions": [],
    }
    evidence = copy.deepcopy(image["evidence"])
    authority_path = image["config"].release_root / "config/authority_map.yml"
    return wire(registration), wire(registry), wire(evidence), image["files"][authority_path]


def _staged_values(image, **changes):
    registration, registry, evidence, authority = _resident_documents_for_image(image)
    values = {
        **arguments(image),
        "resident_registration_bytes": registration,
        "resident_registry_bytes": registry,
        "resident_installed_evidence_bytes": evidence,
        "authority_policy_bytes": authority,
        "destination_state": "ABSENT",
        "pending_state": "ABSENT",
    }
    values.update(changes)
    return values


def test_staged_plan_is_exact_ten_file_compiler_output_and_consumer_compatible(image):
    values = _staged_values(image)
    compiler_arguments = {
        key: value
        for key, value in values.items()
        if key
        in {
            "artifact",
            "installer_profile",
            "configuration_transition",
            "source_proof",
            "compatibility_proof",
            "rollback_evidence",
            "retained_paths",
            "excluded_secret_classes",
            "now_seconds",
            "installed_context",
        }
    }
    expected = staged.compile_staged_inputs(**compiler_arguments)
    plan = subject.compile_staged_publication_plan(**values)
    actual = {Path(payload.path).name: payload.data for payload in plan.payloads}
    assert actual == dict(expected.files)
    assert tuple(actual) == subject._STAGED_NAMES
    assert "release-artifact.bin" in actual and len(actual) == 10
    assert plan.directory.endswith("/" + expected.transition_digest)
    assert plan.directory_mode == 0o500
    assert all(
        (item.uid, item.gid, item.mode) == (0, 0, 0o400)
        for item in plan.files
    )
    for path in list(image["files"]):
        if path.is_relative_to(factory._STAGING) or path == factory._REGISTRY:
            del image["files"][path]
    for name, raw in actual.items():
        image["files"][Path(plan.directory) / name] = raw
    image["files"][factory._REGISTRY] = wire(
        {
            "schema": "mastermind.executive_release_owner_staged_registry/v1",
            "registration_generation": 1,
            "registry_generation": 2,
            "transitions": [
                {
                    "transition_digest": expected.transition_digest,
                    "staging_generation": 2,
                    "state": "STAGED",
                }
            ],
        }
    )
    snapshot = factory.build_release_owner(image["config"])._snapshot(
        expected.transition_digest
    )
    assert snapshot.effect.to_dict() == image["effect"]


def test_staged_plan_binds_resident_context_and_refuses_occupied_paths(image):
    values = _staged_values(image)
    context = dict(values["installed_context"])
    context["installed_configuration_digest"] = False
    with pytest.raises(subject.PublicationPlanError, match="^RESIDENT_CONTEXT_MISMATCH$"):
        subject.compile_staged_publication_plan(
            **{**values, "installed_context": context}
        )
    with pytest.raises(subject.PublicationPlanError, match="^STAGE_DESTINATION_OCCUPIED$"):
        subject.compile_staged_publication_plan(
            **{**values, "destination_state": "PRESENT"}
        )
    with pytest.raises(subject.PublicationPlanError, match="^PENDING_DESTINATION_OCCUPIED$"):
        subject.compile_staged_publication_plan(
            **{**values, "pending_state": "PRESENT"}
        )
    registry = json.loads(values["resident_registry_bytes"])
    registry["transitions"] = [{"state": "STAGED"}]
    with pytest.raises(subject.PublicationPlanError, match="^REGISTRY_NOT_EMPTY$"):
        subject.compile_staged_publication_plan(
            **{
                **values,
                "resident_registry_bytes": resident.canonical_file_bytes(registry),
            }
        )


@pytest.mark.parametrize("age,accepted", [(86399, True), (86400, False), (-1, False)])
def test_staged_explicit_clock_freshness_boundaries(image, age, accepted):
    values = _staged_values(image)
    values["now_seconds"] = 180 + age
    if accepted:
        subject.compile_staged_publication_plan(**values)
    else:
        with pytest.raises(subject.PublicationPlanError):
            subject.compile_staged_publication_plan(**values)


def test_module_origins_are_the_real_current_workspace():
    root = Path(__file__).resolve().parents[1]
    for module in (subject, resident, staged, factory):
        assert Path(module.__file__).resolve().is_relative_to(root)


def test_stage_manifest_names_predicates_without_claiming_they_pass(image):
    plan = subject.compile_staged_publication_plan(**_staged_values(image))
    manifest = _manifest(plan)
    assert manifest["evidence_authentication"] == (
        "UNAUTHENTICATED_UNTIL_INSTALLED_CONSUMER_REDERIVES"
    )
    assert manifest["context"]["destination_preimage"] == "ABSENT"
    assert manifest["context"]["pending_preimage"] == "ABSENT"
    assert "atomic_rename_pending_directory_to_destination" in manifest["predicates"]
    assert "fsync_staging_root_after_rename" in manifest["predicates"]
    assert "release_commit_remains_permanently_disarmed" in manifest["predicates"]
    assert "approved" not in plan.manifest_bytes.decode().lower()


def _v2_replay_values(physical):
    # Construct hypothetical already-installed bytes through the existing pure
    # compiler. The planner itself must never bootstrap a v2 installation.
    values = _resident_values()
    payloads = _payloads(subject.compile_resident_publication_plan(**values))
    keys = ("release_commit", "release_tree", "control_config_bytes", "broker_config_bytes",
            "authority_map_bytes", "python_runtime_provenance_digest", "provider_attestation_bytes",
            "provider_attestation_observed_at", "issuer_binding_receipt", "issuer_binding_observed_at",
            "boot_id", "policy", "app_peer_uid")
    evidence = resident.compile_installed_evidence(
        registration=json.loads(payloads[subject._REGISTRATION_PATH]),
        **{key: values[key] for key in keys}, physical_evidence=physical,
        _now_seconds=values["now_seconds"],
    )
    return {**values, "physical_evidence": physical,
            "existing_registration_bytes": payloads[subject._REGISTRATION_PATH],
            "existing_registry_bytes": payloads[subject._REGISTRY_PATH],
            "existing_installed_evidence_bytes": evidence}


def _physical_evidence():
    """Return synthetic v2 additions bound to the resident fixture."""
    values = _resident_values()
    control = values["control_config_bytes"]
    policy = values["policy"]
    broker = values["broker_config_bytes"]
    authority_map = values["authority_map_bytes"]
    configuration_files = [
        {"path": "config/control.json", "sha256": hashlib.sha256(control).hexdigest()},
        {"path": "config/authority_map.yml", "sha256": hashlib.sha256(authority_map).hexdigest()},
        {"path": "config/privileged-broker.json", "sha256": hashlib.sha256(broker).hexdigest()},
    ]
    return {
        "actuator_generation": 7,
        "before": {
            "release_commit": values["release_commit"],
            "release_tree": values["release_tree"],
            "installed_manifest_digest": "d" * 64,
            "configuration_digest": hashlib.sha256(canonical_release_bytes({
                "schema": "mastermind.executive_installed_configuration_set/v1",
                "files": configuration_files,
            })).hexdigest(),
            "broker_source_commit": values["release_commit"],
            "broker_source_tree": values["release_tree"],
            "broker_binary_digest": "f" * 64,
            "service_generation_digests": {
                "control": "1" * 64,
                "worker": "2" * 64,
                "relay": "3" * 64,
                "gateway": "4" * 64,
                "broker": "5" * 64,
            },
        },
        "publication_operation_key": "release-resident-v2-test-001",
        "predecessor_evidence_digest": "6" * 64,
    }


def test_v2_plan_compiles_exact_canonical_test_payload_and_truthful_metadata():
    physical = _physical_evidence()
    plan = subject.compile_resident_publication_plan(
        **_v2_replay_values(physical)
    )
    payloads = _payloads(plan)
    raw = payloads[subject._EVIDENCE_PATH]
    decoded = json.loads(raw)
    assert decoded["schema"] == (
        "mastermind.executive_release_owner_installed_evidence/v2"
    )
    assert decoded["actuator_generation"] == 7
    assert decoded["before"] == physical["before"]
    assert decoded["publication_operation_key"] == "release-resident-v2-test-001"
    assert raw == canonical_release_bytes(decoded) + b"\n"
    assert _manifest(plan)["production_disarming"]["installer_arming"] is False
    assert _manifest(plan)["context"]["resident_preimage"] == "EXACT"
    assert plan == subject.compile_resident_publication_plan(
        **_v2_replay_values(physical)
    )


@pytest.mark.parametrize(
    "existing",
    [
        (None, None, None),
        (b"one", None, None),
        (b"one", b"two", None),
    ],
)
def test_v2_planner_refuses_absent_and_partial_bootstrap_or_v1(existing):
    physical = _physical_evidence()
    with pytest.raises(
        subject.PublicationPlanError, match="^BOOTSTRAP_OR_MIGRATION_REQUIRED$"
    ):
        subject.compile_resident_publication_plan(
            **_resident_values(
                physical_evidence=physical,
                existing_registration_bytes=existing[0],
                existing_registry_bytes=existing[1],
                existing_installed_evidence_bytes=existing[2],
            )
        )


def test_v2_exact_replay_refuses_coherent_mismatches():
    physical = _physical_evidence()
    values = _v2_replay_values(physical)
    plan = subject.compile_resident_publication_plan(**values)
    payloads = _payloads(plan)
    exact = dict(values)
    exact.update(
        existing_registration_bytes=payloads[subject._REGISTRATION_PATH],
        existing_registry_bytes=payloads[subject._REGISTRY_PATH],
        existing_installed_evidence_bytes=payloads[subject._EVIDENCE_PATH],
    )
    assert subject.compile_resident_publication_plan(**exact) == plan

    changed_physical = copy.deepcopy(physical)
    changed_physical["actuator_generation"] = 8
    with pytest.raises(subject.PublicationPlanError, match="^EVIDENCE_PREIMAGE_MISMATCH$"):
        subject.compile_resident_publication_plan(
            **{**exact, "physical_evidence": changed_physical}
        )
    changed_before = copy.deepcopy(physical)
    changed_before["before"]["installed_manifest_digest"] = "9" * 64
    with pytest.raises(subject.PublicationPlanError, match="^EVIDENCE_PREIMAGE_MISMATCH$"):
        subject.compile_resident_publication_plan(
            **{**exact, "physical_evidence": changed_before}
        )
    with pytest.raises(subject.PublicationPlanError, match="^EVIDENCE_PREIMAGE_MISMATCH$"):
        subject.compile_resident_publication_plan(
            **{
                **exact,
                "physical_evidence": {
                    **physical,
                    "publication_operation_key": "release-resident-v2-other",
                },
            }
        )
    with pytest.raises(subject.PublicationPlanError, match="^EVIDENCE_PREIMAGE_MISMATCH$"):
        subject.compile_resident_publication_plan(
            **{
                **exact,
                "physical_evidence": {
                    **physical,
                    "predecessor_evidence_digest": "7" * 64,
                },
            }
        )
    changed_configuration = copy.deepcopy(physical)
    changed_configuration["before"]["configuration_digest"] = "8" * 64
    with pytest.raises(subject.PublicationPlanError, match="^EVIDENCE_CONFIG_JOIN$"):
        subject.compile_resident_publication_plan(
            **{**values, "physical_evidence": changed_configuration}
        )
    mixed_schema = json.loads(payloads[subject._EVIDENCE_PATH])
    mixed_schema["schema"] = (
        "mastermind.executive_release_owner_installed_evidence/v1"
    )
    with pytest.raises(
        subject.PublicationPlanError, match="^BOOTSTRAP_OR_MIGRATION_REQUIRED$"
    ):
        subject.compile_resident_publication_plan(
            **{
                **exact,
                "existing_installed_evidence_bytes": canonical_release_bytes(
                    mixed_schema
                ) + b"\n",
            }
        )


def test_v2_payloads_and_physical_input_are_detached():
    physical = _physical_evidence()
    plan = subject.compile_resident_publication_plan(
        **_v2_replay_values(physical)
    )
    before = tuple(payload.data for payload in plan.payloads)
    physical["before"]["installed_manifest_digest"] = "changed"
    assert tuple(payload.data for payload in plan.payloads) == before
