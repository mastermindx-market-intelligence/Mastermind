from __future__ import annotations

import copy
import dataclasses
import hashlib
import json

import pytest

from ops.executive_os import capacity_source_contract as contract


MATERIAL_DIGEST = "35931b4ef965c5d67a7e01444dd483804e48671784716ea8196c94e925466650"
RECORD_DIGEST = contract.PYYAML_RECORD_SHA256
RUNTIME_DIGEST = contract.RUNTIME_TREE_SHA256
MASTERMIND_COMMIT = "c" * 40
REPAIR_COMMIT = "d" * 40
E4_COMMIT = "e4e44867ace335ac9208a3990a10c163e199492d"
OLD_GENERATION_DIGEST = "2b05a61f54c876f00c3f03d51bd9df72de4a73e76bc06b2e7bc13a11ee203d60"
OLD_GENERATION_ARTIFACTS = {
    "broker-topology.json": "981e880ba7d21a0003fe2dd8322c5793f2643b815d094374dd6fad3fed31e453",
    "components.json": "02886a6c79f22534ac24234d8adb3224329976342393988541c2a50d7e297f29",
    "host-preparation-receipt.json": "51c58d18869663d90c593e416c7fc7833b3725378870f576abd3647f62f40830",
    "rollback-contract.json": "18d83b0e164ac2e917d84c01fe1d53fc5c1ce0c33ac9580f11d684e16e495093",
    "rollback-drill-receipt.json": "7efba70495cbbf8bcad0c4e47e894a23f4b1618756d8c3e23cae85ad6b7250ba",
    "source-config.json": OLD_GENERATION_DIGEST,
}


def _components() -> dict[str, dict[str, object]]:
    return contract.build_component_objects(
        material_source_digest=MATERIAL_DIGEST,
        pyyaml_record_sha256=RECORD_DIGEST,
        runtime_tree_sha256=RUNTIME_DIGEST,
    )


def _config() -> dict[str, object]:
    return contract.build_source_config(component_objects=_components())


def _closure() -> contract.SourceClosureEvidence:
    return contract.SourceClosureEvidence(
        object_count=17,
        object_inventory_sha256="1" * 64,
        source_tree_sha256="2" * 64,
    )


def _components_v2() -> dict[str, dict[str, object]]:
    return contract.build_component_objects_v2(
        material_source_digest=MATERIAL_DIGEST,
        pyyaml_record_sha256=RECORD_DIGEST,
        runtime_tree_sha256=RUNTIME_DIGEST,
        closure_evidence=_closure(),
        source_closure_repair_commit=REPAIR_COMMIT,
    )


def _config_v2() -> dict[str, object]:
    return contract.build_source_config_v2(component_objects=_components_v2())


def _canonical_digest(value: object, *, newline: bool = False) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload + (b"\n" if newline else b"")).hexdigest()


def _repair_intent() -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": "mastermind.executive_capacity_h0_source_repair_intent/v1",
        "operation": "side_by_side_non_promisor_rematerialization",
        "preparer_source_commit": E4_COMMIT,
        "topology_release_commit": E4_COMMIT,
        "source_closure_repair_commit": REPAIR_COMMIT,
        "generation_repair_commit": REPAIR_COMMIT,
        "source_release_commit": contract.PRODUCER_COMMIT,
        "expected_uid": 0,
        "expected_gid": 0,
        "filesystem_device": 16777234,
        "producer_material_source_digest": MATERIAL_DIGEST,
        "old_generation": {
            "generation_digest": OLD_GENERATION_DIGEST,
            "preparer_source_commit": E4_COMMIT,
            "topology_release_commit": E4_COMMIT,
            "outcome": "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED",
            "generation_artifact_sha256": dict(OLD_GENERATION_ARTIFACTS),
        },
        "observed_old_source_tree_sha256": "3" * 64,
        "candidate_transport_sha256": "4" * 64,
        "candidate_transport_manifest_sha256": "5" * 64,
        "candidate_object_count": 17,
        "candidate_object_inventory_sha256": "1" * 64,
        "candidate_source_tree_sha256": "2" * 64,
        "service_state": "definitions_installed_labels_disabled_unloaded",
        "socket_state": "definitions_installed_nodes_absent",
        "credential_state": "not_read_copied_or_created",
        "worker_execution_state": "held",
        "cf2_i_state": "held",
    }
    return {"intent_id": _canonical_digest(value), **value}


def _repair_receipt() -> dict[str, object]:
    intent = _repair_intent()
    return {
        "schema_version": "mastermind.executive_capacity_h0_source_repair/v1",
        "outcome": "H0_SOURCE_CLOSURE_REPAIRED_NOT_P0_ACCEPTED",
        "intent_id": intent["intent_id"],
        "preparer_source_commit": E4_COMMIT,
        "topology_release_commit": E4_COMMIT,
        "source_closure_repair_commit": REPAIR_COMMIT,
        "generation_repair_commit": REPAIR_COMMIT,
        "source_release_commit": contract.PRODUCER_COMMIT,
        "expected_uid": 0,
        "expected_gid": 0,
        "filesystem_device": 16777234,
        "producer_material_source_digest": MATERIAL_DIGEST,
        "prior_generation_digest": OLD_GENERATION_DIGEST,
        "archived_source_tree_sha256": "3" * 64,
        "archived_generation_tree_sha256": "6" * 64,
        "installed_source_tree_sha256": "2" * 64,
        "installed_object_count": 17,
        "installed_object_inventory_sha256": "1" * 64,
        "new_source_config_digest": _canonical_digest(_config_v2()),
        "new_component_manifest_digest": _canonical_digest(_components_v2()),
        "service_state": "definitions_installed_labels_disabled_unloaded",
        "socket_state": "definitions_installed_nodes_absent",
        "credential_state": "not_read_copied_or_created",
        "worker_execution_state": "held",
        "cf2_i_state": "held",
    }


def test_source_config_has_the_exact_cf2f_closed_shape_and_bounds() -> None:
    value = _config()
    assert set(value) == {
        "schema_version",
        "p0_source_kind",
        "source_contract_id",
        "source_release_commit",
        "source_executable_identity_digest",
        "source_entrypoint_identity_digest",
        "source_working_directory_identity_digest",
        "allowed_environment_names",
        "inventory_config_digest",
        "telemetry_config_digest",
        "timeout_seconds",
        "stdout_max_bytes",
        "stderr_retained_max_bytes",
        "no_shell",
        "network_denied",
        "write_denied",
    }
    assert value["schema_version"] == "mastermind.executive_capacity_source_config/v1"
    assert value["p0_source_kind"] == "grounded_cf1_git_release"
    assert value["source_contract_id"] == "grounded_cf1_git_subprocess/v1"
    assert value["source_release_commit"] == contract.PRODUCER_COMMIT
    assert value["timeout_seconds"] == 10
    assert value["stdout_max_bytes"] == 262144
    assert value["stderr_retained_max_bytes"] == 4096
    assert value["no_shell"] is True
    assert value["network_denied"] is True
    assert value["write_denied"] is True
    assert value["allowed_environment_names"] == sorted(
        set(value["allowed_environment_names"])
    )
    assert value["source_executable_identity_digest"] == contract.canonical_digest(
        _components()["source_executable_identity"]
    )
    assert value["inventory_config_digest"] == contract.canonical_digest(
        _components()["inventory_config"]
    )
    assert contract.validate_source_config(value, component_objects=_components()) == value


def test_environment_name_inventory_is_exact_sorted_and_secret_free() -> None:
    assert list(contract.ALLOWED_ENVIRONMENT_NAMES) == sorted(
        [
            "AI_COSTS_STATE_ROOT",
            "CODEX_ACCOUNT_HOMES",
            "GIT_CONFIG_COUNT",
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_KEY_0",
            "GIT_CONFIG_NOSYSTEM",
            "GIT_CONFIG_VALUE_0",
            "GIT_OPTIONAL_LOCKS",
            "GIT_TERMINAL_PROMPT",
            "LANG",
            "LC_ALL",
            "METABOLISM_STATE_ROOT",
            "PATH",
            "PYTHONDONTWRITEBYTECODE",
            "PYTHONNOUSERSITE",
        ]
    )


def test_component_objects_freeze_runtime_entrypoint_git_inventory_and_telemetry() -> None:
    components = _components()
    assert set(components) == {
        "source_executable_identity",
        "source_entrypoint_identity",
        "source_working_directory_identity",
        "inventory_config",
        "telemetry_config",
    }
    executable = components["source_executable_identity"]
    assert executable["python_version"] == "3.12.10"
    assert executable["python_binary_sha256"] == contract.BASE_PYTHON_BINARY_SHA256
    assert executable["pyyaml_version"] == "6.0.3"
    assert executable["pyyaml_wheel_sha256"] == contract.PYYAML_WHEEL_SHA256
    assert executable["pyyaml_record_sha256"] == RECORD_DIGEST
    assert executable["runtime_tree_sha256"] == RUNTIME_DIGEST

    entrypoint = components["source_entrypoint_identity"]
    assert entrypoint["repository"] == "mastermindx-market-intelligence/macro"
    assert entrypoint["commit"] == contract.PRODUCER_COMMIT
    assert entrypoint["material_source_digest"] == MATERIAL_DIGEST
    assert entrypoint["material_sources_match_commit"] is True
    assert entrypoint["entrypoint_git_blob"] == contract.ENTRYPOINT_GIT_BLOB
    assert entrypoint["entrypoint_sha256"] == contract.ENTRYPOINT_SHA256

    working = components["source_working_directory_identity"]
    assert working["git_directory_kind"] == "direct"
    assert working["checkout_scope"] == "accepted_cf1_material_only"
    assert working["head_detached"] is True
    assert working["worktree_clean"] is True
    assert working["remote_count"] == 0
    assert working["promisor_state"] == "offline_no_remote"
    assert working["lazy_fetch_denied"] is True

    inventory = components["inventory_config"]
    assert [row["capacity_capability_id"] for row in inventory["realms"]] == [
        "codex_account",
        "codex_account_2",
        "codex_account_3",
    ]
    assert [row["slot_id"] for row in inventory["realms"]] == [
        "codex-pro-01",
        "codex-pro-02",
        "codex-pro-03",
    ]
    assert [row["provider_home"] for row in inventory["realms"]] == [
        "/var/db/mastermind-executive/workers/codex-pro-01/provider-home",
        "/var/db/mastermind-executive/workers/codex-pro-02/provider-home",
        "/var/db/mastermind-executive/workers/codex-pro-03/provider-home",
    ]
    assert components["telemetry_config"] == {
        "schema_version": "mastermind.executive_capacity_telemetry_config/v1",
        "metabolism_state_root": "/var/db/mastermind-provider-control",
        "ai_costs_state_root": "/var/db/mastermind-provider-control",
        "source_owner": "macro_shared_ai_provider_control",
        "filesystem_owner": "root:wheel",
        "write_authority": "none_h0_read_only",
        "initial_state": "canonical_empty_absence_witness",
        "absence_semantics": "unknown_not_zero",
    }


def test_canonical_objects_contain_no_private_auth_or_provider_identity() -> None:
    encoded = contract.canonical_json(
        {"components": _components(), "source_config": _config()}
    )
    assert encoded == contract.canonical_json(json.loads(encoded))
    for forbidden in (
        "auth.json",
        "access_token",
        "refresh_token",
        "password",
        "email",
        "oauth_seat_ref",
        "multilogin",
        "browser_profile",
        "profile_id",
        "workspace_id",
        "worker_uid",
        "worker_user",
        "/users/",
    ):
        assert forbidden not in encoded.lower()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.__setitem__("unknown", True),
        lambda value: value.__setitem__("source_release_commit", "0" * 40),
        lambda value: value.__setitem__("timeout_seconds", True),
        lambda value: value.__setitem__("stdout_max_bytes", 1),
        lambda value: value["allowed_environment_names"].reverse(),
        lambda value: value["allowed_environment_names"].append("TOKEN"),
        lambda value: value.__setitem__("inventory_config_digest", "0" * 64),
    ],
)
def test_source_config_refuses_widening_reordering_and_digest_drift(mutation) -> None:
    value = copy.deepcopy(_config())
    mutation(value)
    with pytest.raises(contract.CapacitySourceContractError):
        contract.validate_source_config(value, component_objects=_components())


def test_component_construction_refuses_wrong_material_digest_and_reordered_realms() -> None:
    with pytest.raises(contract.CapacitySourceContractError, match="MATERIAL_DIGEST_MISMATCH"):
        contract.build_component_objects(
            material_source_digest="a" * 64,
            pyyaml_record_sha256=RECORD_DIGEST,
            runtime_tree_sha256=RUNTIME_DIGEST,
        )
    with pytest.raises(contract.CapacitySourceContractError, match="PYYAML_RECORD"):
        contract.build_component_objects(
            material_source_digest=MATERIAL_DIGEST,
            pyyaml_record_sha256="b" * 64,
            runtime_tree_sha256=RUNTIME_DIGEST,
        )
    with pytest.raises(contract.CapacitySourceContractError, match="RUNTIME_TREE"):
        contract.build_component_objects(
            material_source_digest=MATERIAL_DIGEST,
            pyyaml_record_sha256=RECORD_DIGEST,
            runtime_tree_sha256="d" * 64,
        )
    components = copy.deepcopy(_components())
    components["inventory_config"]["realms"].reverse()
    with pytest.raises(contract.CapacitySourceContractError, match="COMPONENT_OBJECTS_MISMATCH"):
        contract.validate_component_objects(components)


@pytest.mark.parametrize(
    "capability_ids",
    [
        ("codex_account", "codex_account_2"),
        ("codex_account", "codex_account_2", "codex_account_3", "extra"),
    ],
)
def test_component_construction_refuses_capability_cardinality_drift(
    monkeypatch: pytest.MonkeyPatch, capability_ids: tuple[str, ...]
) -> None:
    monkeypatch.setattr(contract, "CAPACITY_CAPABILITY_IDS", capability_ids)
    with pytest.raises(contract.CapacitySourceContractError, match="REALM_INVENTORY"):
        _components()


def test_h0_receipt_is_sanitized_and_explicitly_not_p0_acceptance() -> None:
    receipt = contract.build_host_receipt(
        source_config=_config(),
        component_objects=_components(),
        preparer_source_commit=MASTERMIND_COMMIT,
        broker_topology_digest="e" * 64,
        rollback_contract_digest="f" * 64,
        rollback_drill_receipt_digest="1" * 64,
    )
    assert receipt == {
        "schema_version": "mastermind.executive_capacity_host_preparation/v1",
        "outcome": "H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED",
        "preparer_source_commit": MASTERMIND_COMMIT,
        "source_release_commit": contract.PRODUCER_COMMIT,
        "producer_material_source_digest": MATERIAL_DIGEST,
        "source_config_digest": contract.canonical_digest(_config()),
        "component_manifest_digest": contract.canonical_digest(_components()),
        "broker_count": 3,
        "broker_topology_digest": "e" * 64,
        "rollback_contract_digest": "f" * 64,
        "rollback_drill_receipt_digest": "1" * 64,
        "service_state": "definitions_installed_labels_disabled_unloaded",
        "socket_state": "definitions_installed_nodes_absent",
        "control_state": "legacy_files_unchanged_services_disabled_unloaded",
        "credential_state": "not_read_copied_or_created",
        "worker_execution_state": "held",
        "cf2_i_state": "held",
    }
    encoded = contract.canonical_json(receipt)
    assert "p0_acceptance" not in encoded
    assert "/var/" not in encoded and "/library/" not in encoded.lower()
    assert contract.validate_host_receipt(
        receipt,
        source_config=_config(),
        component_objects=_components(),
    ) == receipt


def test_h0_receipt_refuses_extra_field_wrong_digest_and_invalid_commit() -> None:
    receipt = contract.build_host_receipt(
        source_config=_config(),
        component_objects=_components(),
        preparer_source_commit=MASTERMIND_COMMIT,
        broker_topology_digest="e" * 64,
        rollback_contract_digest="f" * 64,
        rollback_drill_receipt_digest="1" * 64,
    )
    with pytest.raises(contract.CapacitySourceContractError):
        contract.validate_host_receipt(
            dict(receipt, p0_acceptance_digest="d" * 64),
            source_config=_config(),
            component_objects=_components(),
        )
    with pytest.raises(contract.CapacitySourceContractError):
        contract.validate_host_receipt(
            dict(receipt, source_config_digest="d" * 64),
            source_config=_config(),
            component_objects=_components(),
        )
    with pytest.raises(contract.CapacitySourceContractError, match="COMMIT_INVALID"):
        contract.build_host_receipt(
            source_config=_config(),
            component_objects=_components(),
            preparer_source_commit="not-a-commit",
            broker_topology_digest="e" * 64,
            rollback_contract_digest="f" * 64,
            rollback_drill_receipt_digest="1" * 64,
        )


def test_v2_schema_constants_and_contract_owned_material_inventory_are_exact() -> None:
    assert contract.WORKING_DIRECTORY_IDENTITY_SCHEMA_V2 == (
        "mastermind.executive_capacity_working_directory_identity/v2"
    )
    assert contract.H0_GENERATION_IDENTITY_SCHEMA == (
        "mastermind.executive_capacity_h0_generation_identity/v1"
    )
    assert contract.SOURCE_CONFIG_SCHEMA_V2 == "mastermind.executive_capacity_source_config/v2"
    assert contract.HOST_RECEIPT_SCHEMA_V2 == (
        "mastermind.executive_capacity_host_preparation/v2"
    )
    assert contract.SOURCE_REPAIR_INTENT_SCHEMA == (
        "mastermind.executive_capacity_h0_source_repair_intent/v1"
    )
    assert contract.SOURCE_REPAIR_RECEIPT_SCHEMA == (
        "mastermind.executive_capacity_h0_source_repair/v1"
    )
    assert contract.PRODUCER_MATERIAL_PATHS == (
        "config/capability_manifest.yml",
        "config/metabolism_budget.yml",
        "engine/codex_lane/runner.py",
        "engine/codex_provider.py",
        "engine/llm_auth.py",
        "engine/metabolism/budget_gate.py",
        "engine/neuralweb/key_pool.py",
        "engine/provider_capacity.py",
        "engine/provider_health.py",
        "lib/ai_costs.py",
        "scripts/build_provider_capacity.py",
    )


def test_source_closure_evidence_is_frozen_and_refuses_nonpositive_or_false_counts() -> None:
    evidence = _closure()
    assert contract.validate_source_closure_evidence(evidence) == evidence
    with pytest.raises(dataclasses.FrozenInstanceError):
        evidence.object_count = 18  # type: ignore[misc]
    for count in (True, False, 0, -1):
        with pytest.raises(contract.CapacitySourceContractError, match="OBJECT_COUNT_INVALID"):
            contract.validate_source_closure_evidence(
                {
                    "object_count": count,
                    "object_inventory_sha256": "1" * 64,
                    "source_tree_sha256": "2" * 64,
                }
            )
    for field in ("object_inventory_sha256", "source_tree_sha256"):
        value = dataclasses.asdict(evidence)
        value[field] = "not-a-digest"
        with pytest.raises(contract.CapacitySourceContractError, match="DIGEST_INVALID"):
            contract.validate_source_closure_evidence(value)


def test_v2_components_preserve_e4_and_bind_complete_closure_and_repair_axes() -> None:
    components = _components_v2()
    assert set(components) == {
        "source_executable_identity",
        "source_entrypoint_identity",
        "source_working_directory_identity",
        "inventory_config",
        "telemetry_config",
        "h0_generation_identity",
    }
    working = components["source_working_directory_identity"]
    assert set(working) == {
        "schema_version",
        "repository",
        "commit",
        "working_directory",
        "git_directory_kind",
        "checkout_scope",
        "object_format",
        "object_closure",
        "object_count",
        "object_inventory_sha256",
        "head_detached",
        "worktree_clean",
        "worktree_file_count",
        "remote_count",
        "alternates_present",
        "shallow_present",
        "promisor_present",
        "partial_clone_filter_present",
        "sparse_checkout",
        "lazy_fetch_state",
    }
    assert "promisor_state" not in working
    assert working["object_count"] == 17
    assert working["object_inventory_sha256"] == "1" * 64
    assert working["worktree_file_count"] == len(contract.PRODUCER_MATERIAL_PATHS)
    assert working["lazy_fetch_state"] == "impossible_complete_offline_object_store"
    identity = components["h0_generation_identity"]
    assert set(identity) == {
        "schema_version",
        "preparer_source_commit",
        "topology_release_commit",
        "source_closure_repair_commit",
        "generation_repair_commit",
        "topology_state",
        "release_install_state",
        "rollback_drill_state",
    }
    assert identity["preparer_source_commit"] == E4_COMMIT
    assert identity["topology_release_commit"] == E4_COMMIT
    assert identity["source_closure_repair_commit"] == REPAIR_COMMIT
    assert identity["generation_repair_commit"] == REPAIR_COMMIT
    assert contract.validate_component_objects_v2(components) == components


@pytest.mark.parametrize(
    "mutation,match",
    [
        (
            lambda value: value["source_working_directory_identity"].__setitem__(
                "promisor_state", "offline_no_remote"
            ),
            "FIELDS_INVALID",
        ),
        (
            lambda value: value["h0_generation_identity"].__setitem__(
                "preparer_source_commit", REPAIR_COMMIT
            ),
            "H0_GENERATION_IDENTITY",
        ),
        (
            lambda value: value["h0_generation_identity"].__setitem__(
                "topology_release_commit", REPAIR_COMMIT
            ),
            "H0_GENERATION_IDENTITY",
        ),
        (
            lambda value: value["h0_generation_identity"].__setitem__(
                "generation_repair_commit", "f" * 40
            ),
            "REPAIR_COMMIT_MISMATCH",
        ),
    ],
)
def test_v2_component_validation_refuses_stale_promisor_or_identity_supersession(
    mutation, match: str
) -> None:
    components = copy.deepcopy(_components_v2())
    mutation(components)
    with pytest.raises(contract.CapacitySourceContractError, match=match):
        contract.validate_component_objects_v2(components)


def test_v2_source_config_has_exact_shape_and_repeats_composite_identity() -> None:
    config = _config_v2()
    assert set(config) == {
        "schema_version",
        "p0_source_kind",
        "source_contract_id",
        "source_release_commit",
        "source_executable_identity_digest",
        "source_entrypoint_identity_digest",
        "source_working_directory_identity_digest",
        "allowed_environment_names",
        "inventory_config_digest",
        "telemetry_config_digest",
        "timeout_seconds",
        "stdout_max_bytes",
        "stderr_retained_max_bytes",
        "no_shell",
        "network_denied",
        "write_denied",
        "preparer_source_commit",
        "topology_release_commit",
        "source_closure_repair_commit",
        "generation_repair_commit",
        "h0_generation_identity_digest",
    }
    assert config["schema_version"] == contract.SOURCE_CONFIG_SCHEMA_V2
    assert config["preparer_source_commit"] == E4_COMMIT
    assert config["topology_release_commit"] == E4_COMMIT
    assert config["source_closure_repair_commit"] == REPAIR_COMMIT
    assert config["generation_repair_commit"] == REPAIR_COMMIT
    assert config["h0_generation_identity_digest"] == _canonical_digest(
        _components_v2()["h0_generation_identity"]
    )
    assert contract.validate_source_config_v2(
        config, component_objects=_components_v2()
    ) == config


def test_source_repair_intent_and_receipt_exact_shapes_bind_forward_only() -> None:
    intent = _repair_intent()
    assert set(intent) == {
        "schema_version",
        "intent_id",
        "operation",
        "preparer_source_commit",
        "topology_release_commit",
        "source_closure_repair_commit",
        "generation_repair_commit",
        "source_release_commit",
        "expected_uid",
        "expected_gid",
        "filesystem_device",
        "producer_material_source_digest",
        "old_generation",
        "observed_old_source_tree_sha256",
        "candidate_transport_sha256",
        "candidate_transport_manifest_sha256",
        "candidate_object_count",
        "candidate_object_inventory_sha256",
        "candidate_source_tree_sha256",
        "service_state",
        "socket_state",
        "credential_state",
        "worker_execution_state",
        "cf2_i_state",
    }
    assert set(intent["old_generation"]) == {
        "generation_digest",
        "preparer_source_commit",
        "topology_release_commit",
        "outcome",
        "generation_artifact_sha256",
    }
    assert contract.validate_source_repair_intent(intent) == intent

    receipt = _repair_receipt()
    assert set(receipt) == {
        "schema_version",
        "outcome",
        "intent_id",
        "preparer_source_commit",
        "topology_release_commit",
        "source_closure_repair_commit",
        "generation_repair_commit",
        "source_release_commit",
        "expected_uid",
        "expected_gid",
        "filesystem_device",
        "producer_material_source_digest",
        "prior_generation_digest",
        "archived_source_tree_sha256",
        "archived_generation_tree_sha256",
        "installed_source_tree_sha256",
        "installed_object_count",
        "installed_object_inventory_sha256",
        "new_source_config_digest",
        "new_component_manifest_digest",
        "service_state",
        "socket_state",
        "credential_state",
        "worker_execution_state",
        "cf2_i_state",
    }
    assert "host_receipt_digest" not in receipt
    assert contract.validate_source_repair_receipt(receipt, intent=intent) == receipt


@pytest.mark.parametrize(
    "target,mutation,match",
    [
        (
            "intent",
            lambda value: value["old_generation"].pop("generation_artifact_sha256"),
            "OLD_GENERATION",
        ),
        (
            "intent",
            lambda value: value["old_generation"]["generation_artifact_sha256"].__setitem__(
                "components.json", "0" * 64
            ),
            "OLD_GENERATION",
        ),
        (
            "intent",
            lambda value: value.__setitem__("candidate_object_count", False),
            "OBJECT_COUNT_INVALID",
        ),
        (
            "intent",
            lambda value: value.__setitem__("generation_repair_commit", "f" * 40),
            "REPAIR_COMMIT_MISMATCH",
        ),
        (
            "receipt",
            lambda value: value.__setitem__("generation_repair_commit", "f" * 40),
            "REPAIR_COMMIT_MISMATCH",
        ),
        (
            "receipt",
            lambda value: value.__setitem__("host_receipt_digest", "0" * 64),
            "FIELDS_INVALID",
        ),
    ],
)
def test_source_repair_provenance_refuses_missing_old_truth_drift_or_circular_link(
    target: str, mutation, match: str
) -> None:
    intent = _repair_intent()
    value = intent if target == "intent" else _repair_receipt()
    mutation(value)
    with pytest.raises(contract.CapacitySourceContractError, match=match):
        if target == "intent":
            contract.validate_source_repair_intent(value)
        else:
            contract.validate_source_repair_receipt(value, intent=intent)


def test_v2_host_receipt_binds_repair_receipt_and_archived_generation_provenance() -> None:
    repair_receipt_digest = _canonical_digest(_repair_receipt(), newline=True)
    receipt = contract.build_host_receipt_v2(
        source_config=_config_v2(),
        component_objects=_components_v2(),
        source_repair_receipt_digest=repair_receipt_digest,
        broker_topology_digest=OLD_GENERATION_ARTIFACTS["broker-topology.json"],
        rollback_contract_digest=OLD_GENERATION_ARTIFACTS["rollback-contract.json"],
        rollback_drill_receipt_digest=OLD_GENERATION_ARTIFACTS[
            "rollback-drill-receipt.json"
        ],
    )
    assert set(receipt) == {
        "schema_version",
        "outcome",
        "preparer_source_commit",
        "topology_release_commit",
        "source_closure_repair_commit",
        "generation_repair_commit",
        "source_release_commit",
        "producer_material_source_digest",
        "source_config_digest",
        "component_manifest_digest",
        "source_closure_state",
        "source_repair_receipt_digest",
        "prior_generation",
        "broker_count",
        "broker_topology_digest",
        "rollback_contract_digest",
        "rollback_drill_receipt_digest",
        "service_state",
        "socket_state",
        "control_state",
        "credential_state",
        "worker_execution_state",
        "cf2_i_state",
    }
    assert receipt["preparer_source_commit"] == E4_COMMIT
    assert receipt["topology_release_commit"] == E4_COMMIT
    assert receipt["source_closure_repair_commit"] == REPAIR_COMMIT
    assert receipt["generation_repair_commit"] == REPAIR_COMMIT
    assert receipt["source_repair_receipt_digest"] == repair_receipt_digest
    assert receipt["prior_generation"] == {
        "status": "archived_superseded_generation_same_current_e4_topology_identity",
        "generation_digest": OLD_GENERATION_DIGEST,
        "generation_artifact_sha256": OLD_GENERATION_ARTIFACTS,
    }
    assert contract.validate_host_receipt_v2(
        receipt,
        source_config=_config_v2(),
        component_objects=_components_v2(),
    ) == receipt

    for mutation in (
        lambda value: value.pop("prior_generation"),
        lambda value: value["prior_generation"]["generation_artifact_sha256"].__setitem__(
            "source-config.json", "0" * 64
        ),
        lambda value: value.__setitem__("host_receipt_digest", "0" * 64),
    ):
        drifted = copy.deepcopy(receipt)
        mutation(drifted)
        with pytest.raises(contract.CapacitySourceContractError):
            contract.validate_host_receipt_v2(
                drifted,
                source_config=_config_v2(),
                component_objects=_components_v2(),
            )
