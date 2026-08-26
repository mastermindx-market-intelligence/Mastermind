from __future__ import annotations

import copy
import json

import pytest

from ops.executive_os import capacity_source_contract as contract


MATERIAL_DIGEST = "35931b4ef965c5d67a7e01444dd483804e48671784716ea8196c94e925466650"
RECORD_DIGEST = contract.PYYAML_RECORD_SHA256
RUNTIME_DIGEST = contract.RUNTIME_TREE_SHA256
MASTERMIND_COMMIT = "c" * 40


def _components() -> dict[str, dict[str, object]]:
    return contract.build_component_objects(
        material_source_digest=MATERIAL_DIGEST,
        pyyaml_record_sha256=RECORD_DIGEST,
        runtime_tree_sha256=RUNTIME_DIGEST,
    )


def _config() -> dict[str, object]:
    return contract.build_source_config(component_objects=_components())


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
