"""Offline successor preparation preserves supplied policy and has no publisher."""

import copy
import hashlib
import json
import os
from pathlib import Path
import stat

import pytest

from ops.executive_os import prepare_control_successor as prepare


OLD_SHA = "80f384b8f58b7ca46422d9783aa5c0613c7bf4b2"
NEW_SHA = "2" * 40
OLD_MACRO = "/approved/retained/Macro"
NEW_MACRO = "/approved/successor/Macro"


@pytest.fixture
def control_input():
    return {
        "schema_version": "mastermind.executive_control_config/v1",
        "runtime_root": "/var/db/mastermind-executive/control",
        "control_socket_path": "/var/run/mastermind-executive/control.sock",
        "launchd_socket_name": "Operator",
        "worker_broker_socket_path": "/var/run/mastermind-executive/worker.sock",
        "worker_provider_home": "/var/db/mastermind-executive/provider",
        "worker_runs_root": "/var/db/mastermind-executive/runs",
        "receipts_root": "/var/db/mastermind-executive/receipts",
        "proof_source_repository": "/var/db/mastermind-executive/control/admin-checkout/80f384b8f58b7ca46422d9783aa5c0613c7bf4b2",
        "proof_workspace_root": "/Volumes/Mastermind/agent-workspaces",
        "proof_base_sha": OLD_SHA,
        "backup_root": "/var/db/mastermind-executive/backups",
        "control_uid": 450,
        "worker_uid": 451,
        "worker_gid": 451,
        "worker_user": "_mastermind_worker",
        "shared_run_gid": 451,
        "allowed_peer_uids": [450, 501],
        "secret_canary_receipt_path": "/var/db/mastermind-executive/canary.json",
        "control_environment_attestation_path": "/var/db/mastermind-executive/environment.json",
        "ceo_ingress_socket_path": "/var/run/mastermind-executive/ceo-ingress.sock",
        "ceo_ingress_launchd_socket_name": "CeoIngress",
        "ceo_ingress_peer_uid": 452,
        "ceo_ingress_app_peer_uid": 456,
        "ceo_ingress_app_armed": True,
        "ceo_ingress_app_macro_root": OLD_MACRO,
        "model": "retained-reviewed-model",
        "effort": "xhigh",
        "proof_branch": "retained/operator-branch",
        "quota_class": "retained-capacity",
        "coo_autonomy_armed": False,
        "coo_operator_harness_armed": False,
        "ceo_submit_armed": False,
        "exact_worker_claim_target": {"mode": "disabled"},
        "privileged_readiness_armed": True,
        "privileged_broker_socket_path": "/var/run/mastermind-executive/privileged.sock",
        "operator_harness_binary_digest": "a" * 64,
        "operator_harness_version": "retained-installed-version",
        "python_runtime_provenance_digest": "b" * 64,
        "company_consultation": {
            "armed": False,
            "socket_path": "/var/run/mastermind-executive/company-consultation.sock",
            "launchd_socket_name": "CompanyConsultation",
        },
    }


def test_retargets_historical_checkout_to_installer_expected_source_and_preserves_policy(control_input):
    before = copy.deepcopy(control_input)
    result = prepare.build_successor(control_input, source_sha=NEW_SHA, macro_root=NEW_MACRO)
    assert control_input == before
    assert set(result) == set(before)
    assert {key for key in result if result[key] != before[key]} == {
        "proof_base_sha", "proof_source_repository", "ceo_ingress_app_macro_root"}
    # install.sh derives ADMIN_CHECKOUT from its fixed runtime root and the
    # selected release, then requires this exact field in --control-config.
    assert result["proof_source_repository"] == (
        f"/var/db/mastermind-executive/control/admin-checkout/{NEW_SHA}")
    assert result["ceo_ingress_app_armed"] is True
    assert result["privileged_readiness_armed"] is True
    result["company_consultation"]["armed"] = True
    assert control_input["company_consultation"]["armed"] is False


def test_no_runtime_reference_or_macro_reads(control_input, monkeypatch):
    from scripts import executive_os_phase1c as control

    control_input.update({
        "fabric_bindings_path": "/not-readable/fabric.json",
        "fabric_bindings_sha256": "c" * 64,
        "fabric_bridge_armed": False,
        "content_observer_profile_path": "/not-readable/content.json",
        "ceo_ingress_app_boot_python": "/not-readable/python3",
    })
    def unexpected(*args, **kwargs):
        pytest.fail("offline preparation attempted a runtime or Macro read")
    for name in ("load_control_config", "_staged_fabric_binding_source",
                 "_read_content_profile_document", "_sealed_root_executable",
                 "_attest_app_boot_runtime"):
        monkeypatch.setattr(control, name, unexpected)
    for name in ("open", "read_text", "read_bytes", "stat", "lstat", "resolve"):
        monkeypatch.setattr(Path, name, unexpected)
    successor = prepare.build_successor(control_input, source_sha=NEW_SHA, macro_root=NEW_MACRO)
    assert successor["content_observer_profile_path"] == control_input["content_observer_profile_path"]
    assert successor["fabric_bindings_path"] == control_input["fabric_bindings_path"]
    assert successor["ceo_ingress_app_boot_python"] == control_input["ceo_ingress_app_boot_python"]


@pytest.mark.parametrize("change", [
    lambda value: value.pop("runtime_root"),
    lambda value: value.pop("ceo_ingress_app_peer_uid"),
    lambda value: value.update(unreviewed_setting=True),
    lambda value: value.update(schema_version="unsupported"),
    lambda value: value.update(proof_source_repository="relative/source"),
    lambda value: value.update(proof_source_repository=None),
    lambda value: value.update(proof_source_repository="/invalid/\x00/source"),
    lambda value: value.update(ceo_ingress_app_peer_uid=value["control_uid"]),
    lambda value: value.update(ceo_ingress_app_armed="true"),
    lambda value: value.update(worker_uid=value["control_uid"]),
    lambda value: value.update(control_uid=True),
    lambda value: value.update(fabric_bridge_armed=True),
    lambda value: value.update(workspace_acquisition={}, workspace_resource_policy={},
                              workspace_control_room={"port": 8123}),
    lambda value: value.update(content_observer={"invalid": "profile"}),
])
def test_existing_source_contract_refuses_invalid_inputs(control_input, change):
    change(control_input)
    with pytest.raises(prepare.PreparationError):
        prepare.build_successor(control_input, source_sha=NEW_SHA, macro_root=NEW_MACRO)


@pytest.mark.parametrize("source_sha,macro_root", [
    ("short", NEW_MACRO), ("A" * 40, NEW_MACRO), (NEW_SHA, "relative/Macro"),
    (NEW_SHA, "/approved/../Macro"), (NEW_SHA, "/approved//Macro"),
    (NEW_SHA, "//approved/Macro"),
])
def test_invalid_successor_paths_and_sha_refused_before_validation(source_sha, macro_root):
    with pytest.raises(prepare.PreparationError):
        prepare.build_successor({}, source_sha=source_sha, macro_root=macro_root)


@pytest.mark.parametrize("raw", [
    b'{"same": 1, "same": 2}', b'{"nested": {"same": 1, "same": 2}}',
    b'{"value": NaN}', b'{"value": Infinity}', b'{"value": 1e400}', b'[]', b'\xff',
])
def test_strict_json_input(raw):
    with pytest.raises(prepare.PreparationError):
        prepare._parse(raw)


def test_output_is_new_private_file_and_input_is_untouched(tmp_path, control_input):
    source, output = tmp_path / "input.json", tmp_path / "successor.json"
    raw = (json.dumps(control_input, indent=4) + "\n").encode()
    source.write_bytes(raw)
    result = prepare.prepare(input_path=str(source), output_path=str(output),
                             source_sha=NEW_SHA, macro_root=NEW_MACRO)
    assert source.read_bytes() == raw
    successor = json.loads(output.read_bytes())
    assert successor["proof_base_sha"] == NEW_SHA
    assert successor["proof_source_repository"] == (
        f"/var/db/mastermind-executive/control/admin-checkout/{NEW_SHA}")
    assert successor["ceo_ingress_app_macro_root"] == NEW_MACRO
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert result["input_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert result["macro_seal_verified"] is False
    assert result["installed_configuration_changed"] is False
    assert result["changed_fields"] == [
        "ceo_ingress_app_macro_root", "proof_base_sha", "proof_source_repository"]
    assert result["unchanged_fields"] == len(control_input) - 3
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        prepare.prepare(input_path=str(source), output_path=str(output),
                        source_sha=NEW_SHA, macro_root=NEW_MACRO)
    assert output.read_bytes() == before


def test_validation_refusal_creates_no_output(tmp_path, control_input):
    source, output = tmp_path / "input.json", tmp_path / "successor.json"
    control_input.pop("worker_uid")
    source.write_text(json.dumps(control_input))
    with pytest.raises(prepare.PreparationError):
        prepare.prepare(input_path=str(source), output_path=str(output),
                        source_sha=NEW_SHA, macro_root=NEW_MACRO)
    assert not output.exists()


def test_installed_path_refused_before_open(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("installed configuration must never be opened")
    monkeypatch.setattr(os, "open", unexpected)
    with pytest.raises(prepare.PreparationError, match="offline"):
        prepare.prepare(input_path=str(prepare._LIVE_CONFIG_ROOT / "control.json"),
                        output_path="/staging/output.json", source_sha=NEW_SHA, macro_root=NEW_MACRO)


def test_input_symlink_and_hardlink_refused(tmp_path):
    source = tmp_path / "supplied.json"
    source.write_text("{}")
    link = tmp_path / "input.json"
    link.symlink_to(source)
    with pytest.raises(OSError):
        prepare._read(link)
    link.unlink()
    os.link(source, link)
    with pytest.raises(prepare.PreparationError, match="single-link"):
        prepare._read(link)


@pytest.mark.parametrize("direction", ["input", "output"])
def test_installed_path_alias_refused_before_open(tmp_path, monkeypatch, direction):
    protected = tmp_path / "protected-config"
    protected.mkdir()
    monkeypatch.setattr(prepare, "_LIVE_CONFIG_ROOT", protected)
    alias = tmp_path / "config-alias"
    alias.symlink_to(protected, target_is_directory=True)
    source = alias / "control.json" if direction == "input" else tmp_path / "input.json"
    output = alias / "output.json" if direction == "output" else tmp_path / "output.json"
    def unexpected(*args, **kwargs):
        pytest.fail("an installed configuration alias must never be opened")
    monkeypatch.setattr(os, "open", unexpected)
    with pytest.raises(prepare.PreparationError, match="alias"):
        prepare.prepare(input_path=str(source), output_path=str(output),
                        source_sha=NEW_SHA, macro_root=NEW_MACRO)
