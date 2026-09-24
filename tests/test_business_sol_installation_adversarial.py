from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path

import pytest

from integrations.business_sol_installation import (
    InstallationContractError,
    compile_installation_bindings,
    preflight_installation,
    rollback_staged_compilation,
    stage_compilation,
    verify_staged_compilation,
)
from integrations.business_sol_installation import bindings as contract

SOURCE_COMMIT = "a" * 40
PACKAGE_DIGEST = "b" * 64
WORKSPACE_DIGEST = "c" * 64
RESOURCE_DIGEST = "d" * 64
OAUTH_DIGEST = "e" * 64
PLUGIN_ID = "Plugin_" + "1" * 32
STEWARD_ID = "asdk_app_" + "2" * 32
EXECUTIVE_ID = "asdk_app_" + "3" * 32


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def template() -> dict[str, object]:
    return {
        "schema": "mastermind.plugin_app_bindings_template.v1",
        "plugin": "mastermind-sol",
        "plugin_version": "0.1.0",
        "generated_file": ".app.json",
        "generated_by_wave": "BSC-U1",
        "bindings": [
            {
                "logical_name": "mastermind-steward",
                "required": True,
                "contract_owner": "integrations/mastermind_secretary_mcp/schemas.py",
                "app_id": None,
            },
            {
                "logical_name": "mastermind-executive",
                "required": True,
                "contract_owner": "integrations/executive_mcp/schemas.py",
                "app_id": None,
            },
        ],
    }


def app(logical_name: str) -> dict[str, object]:
    if logical_name == "mastermind-steward":
        app_id = STEWARD_ID
        display_name = "Mastermind Steward"
        server_name = "mastermind-steward"
        server_version = "2.0.0"
        tool_names = [
            "list_responsibilities",
            "get_responsibility",
            "get_attention",
            "get_current_runtime",
            "explain_blocker",
            "resolve_surface",
        ]
        tool_digest = "cde13b7d678427a230cfe40159be1d7aa0807df00324995a40d89b2b79c12047"
    elif logical_name == "mastermind-executive":
        app_id = EXECUTIVE_ID
        display_name = "Mastermind Executive"
        server_name = "mastermind-executive"
        server_version = "1.0.0"
        tool_names = [
            "executive_state",
            "executive_inbox",
            "executive_job",
            "ceo_intent_status",
            "submit_ceo_intent",
        ]
        tool_digest = "546b4345e30c24363a02ae3d4fc873e17559ffd569cde188a533fb628b284232"
    else:
        app_id = "asdk_app_" + "4" * 32
        display_name = "Mastermind Surface"
        server_name = "mastermind-surface"
        server_version = "1.0.0"
        tool_names = ["resolve_surface"]
        tool_digest = "f" * 64
    return {
        "logical_name": logical_name,
        "app_id": app_id,
        "approved_app_id_digest": digest_text(app_id),
        "display_name": display_name,
        "workspace_digest": WORKSPACE_DIGEST,
        "scope": "WORKSPACE",
        "publication_state": "PUBLISHED",
        "app_generation": logical_name + "-g1",
        "approved_app_generation": logical_name + "-g1",
        "server_name": server_name,
        "server_version": server_version,
        "resource_digest": RESOURCE_DIGEST,
        "approved_resource_digest": RESOURCE_DIGEST,
        "oauth_policy_digest": OAUTH_DIGEST,
        "approved_oauth_policy_digest": OAUTH_DIGEST,
        "tool_names": tool_names,
        "tool_contract_digest": tool_digest,
        "status": "ENABLED",
        "availability": "AVAILABLE",
        "installed": False,
        "connected": False,
    }


def request() -> dict[str, object]:
    return {
        "schema": "mastermind.business_sol_installation_request.v1",
        "generation": 1,
        "source_commit": SOURCE_COMMIT,
        "observed_source_commit": SOURCE_COMMIT,
        "plugin_package_digest": PACKAGE_DIGEST,
        "observed_plugin_package_digest": PACKAGE_DIGEST,
        "workspace_digest": WORKSPACE_DIGEST,
        "workspace_role": "OWNER",
        "plugin": {
            "name": "mastermind-sol",
            "version": "0.1.0",
            "registry_id": PLUGIN_ID,
            "approved_registry_id_digest": digest_text(PLUGIN_ID),
            "display_name": "Mastermind Sol",
            "scope": "WORKSPACE",
            "status": "ENABLED",
            "installation_policy": "INSTALLED_BY_DEFAULT",
            "scanned_generation": "mastermind-sol-g1",
            "approved_scanned_generation": "mastermind-sol-g1",
            "installed": False,
        },
        "apps": [app("mastermind-steward"), app("mastermind-executive")],
    }


def assert_refused(code: str, value: object, *, template_value: object | None = None) -> None:
    with pytest.raises(InstallationContractError) as captured:
        preflight_installation(template() if template_value is None else template_value, value)
    assert captured.value.code == code
    assert str(captured.value) == code


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.__setitem__("unexpected", True),
        lambda value: value["plugin"].__setitem__("unexpected", True),
        lambda value: value["apps"][0].__setitem__("unexpected", True),
        lambda value: value.__setitem__("generation", True),
        lambda value: value.__setitem__("generation", 2),
        lambda value: value.__setitem__(
            "schema", "mastermind.business_sol_installation_request.v2"
        ),
    ],
)
def test_closed_request_shape_and_exact_types_refuse(mutation) -> None:
    value = request()
    mutation(value)
    assert_refused("INVALID_INPUT", value)


class HostileDict(dict):
    pass


class HostileList(list):
    pass


class HostileString(str):
    pass


@pytest.mark.parametrize(
    "value",
    [
        HostileDict(request()),
        {**request(), "apps": HostileList(request()["apps"])},
        {**request(), "workspace_role": HostileString("OWNER")},
    ],
)
def test_hostile_container_and_string_subclasses_refuse(value: object) -> None:
    assert_refused("INVALID_INPUT", value)


@pytest.mark.parametrize(
    ("path", "secret_value"),
    [
        (("workspace_role",), "xoxb-super-secret"),
        (("plugin", "display_name"), "admin@example.test"),
        (("apps", 0, "display_name"), "https://private.example.test"),
        (("apps", 1, "app_generation"), "/Users/private/profile"),
        (("apps", 1, "server_name"), "Bearer top-secret"),
    ],
)
def test_secret_private_locator_and_url_shaped_inputs_refuse(path, secret_value) -> None:
    value = request()
    cursor: object = value
    for part in path[:-1]:
        cursor = cursor[part]  # type: ignore[index]
    cursor[path[-1]] = secret_value  # type: ignore[index]
    assert_refused("SECRET_SHAPED_INPUT", value)


def test_template_is_exact_and_cannot_embed_live_app_ids() -> None:
    bad = template()
    bad["bindings"][0]["app_id"] = STEWARD_ID
    assert_refused("TEMPLATE_MISMATCH", request(), template_value=bad)

    bad = template()
    bad["bindings"].append(copy.deepcopy(bad["bindings"][0]))
    assert_refused("TEMPLATE_MISMATCH", request(), template_value=bad)

    bad = template()
    bad["bindings"].reverse()
    assert_refused("TEMPLATE_MISMATCH", request(), template_value=bad)


@pytest.mark.parametrize(
    "field",
    ["observed_source_commit", "observed_plugin_package_digest"],
)
def test_source_or_package_drift_refuses(field: str) -> None:
    value = request()
    value[field] = ("f" * 40) if field.endswith("commit") else ("f" * 64)
    assert_refused("PLUGIN_SOURCE_MISMATCH", value)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("name", "other-plugin"),
        ("version", "0.2.0"),
        ("display_name", "Other Plugin"),
        ("scope", "USER"),
        ("status", "DISABLED"),
        ("installation_policy", "AVAILABLE"),
    ],
)
def test_plugin_identity_is_closed(field: str, replacement: str) -> None:
    value = request()
    value["plugin"][field] = replacement
    assert_refused("PLUGIN_IDENTITY_MISMATCH", value)


def test_plugin_registry_and_generation_drift_refuse() -> None:
    value = request()
    value["plugin"]["approved_registry_id_digest"] = "f" * 64
    assert_refused("PLUGIN_IDENTITY_MISMATCH", value)

    value = request()
    value["plugin"]["approved_scanned_generation"] = "mastermind-sol-g2"
    assert_refused("PLUGIN_GENERATION_MISMATCH", value)


@pytest.mark.parametrize("role", ["MEMBER", "ADMINISTRATOR", "", 1])
def test_workspace_role_is_exactly_admin_or_owner(role: object) -> None:
    value = request()
    value["workspace_role"] = role
    expected = "WORKSPACE_MISMATCH" if role in {"MEMBER", "ADMINISTRATOR"} else "INVALID_INPUT"
    assert_refused(expected, value)


def test_workspace_and_app_scope_mismatch_refuse() -> None:
    value = request()
    value["apps"][0]["workspace_digest"] = "f" * 64
    assert_refused("WORKSPACE_MISMATCH", value)

    value = request()
    value["apps"][0]["scope"] = "USER"
    assert_refused("APP_IDENTITY_MISMATCH", value)


def test_duplicate_binding_app_id_and_unexpected_surface_refuse() -> None:
    value = request()
    value["apps"] = [app("mastermind-steward"), app("mastermind-steward")]
    assert_refused("DUPLICATE_BINDING", value)

    value = request()
    value["apps"][1]["app_id"] = STEWARD_ID
    value["apps"][1]["approved_app_id_digest"] = digest_text(STEWARD_ID)
    assert_refused("DUPLICATE_APP_ID", value)

    value = request()
    value["apps"].append(app("mastermind-surface"))
    assert_refused("UNEXPECTED_BINDING", value)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("display_name", "Wrong"),
        ("server_name", "wrong-server"),
        ("server_version", "9.0.0"),
        ("tool_contract_digest", "f" * 64),
        ("resource_digest", "f" * 64),
        ("oauth_policy_digest", "f" * 64),
    ],
)
def test_app_contract_drift_refuses(field: str, replacement: str) -> None:
    value = request()
    value["apps"][0][field] = replacement
    assert_refused("APP_CONTRACT_MISMATCH", value)


def test_tool_census_order_and_generation_are_frozen() -> None:
    value = request()
    value["apps"][0]["tool_names"] = list(reversed(value["apps"][0]["tool_names"]))
    assert_refused("APP_CONTRACT_MISMATCH", value)

    value = request()
    value["apps"][0]["approved_app_generation"] = "mastermind-steward-g2"
    assert_refused("APP_IDENTITY_MISMATCH", value)


def test_app_id_digest_mismatch_or_malformed_id_refuses() -> None:
    value = request()
    value["apps"][0]["approved_app_id_digest"] = "f" * 64
    assert_refused("APP_IDENTITY_MISMATCH", value)

    value = request()
    value["apps"][0]["app_id"] = "app-not-approved"
    value["apps"][0]["approved_app_id_digest"] = digest_text("app-not-approved")
    assert_refused("APP_IDENTITY_MISMATCH", value)


def test_missing_or_unavailable_apps_are_held_without_artifact() -> None:
    value = request()
    value["apps"][0]["app_id"] = None
    value["apps"][0]["approved_app_id_digest"] = None
    result = preflight_installation(template(), value)
    assert result["status"] == "PREFLIGHT_HELD"
    assert {row["code"] for row in result["issues"]} == {"APP_ID_MISSING"}
    assert result["binding_document_digest"] is None

    value = request()
    value["apps"][0]["publication_state"] = "DRAFT"
    value["apps"][0]["status"] = "DISABLED"
    value["apps"][0]["availability"] = "UNAVAILABLE"
    result = preflight_installation(template(), value)
    assert result["status"] == "PREFLIGHT_HELD"
    assert {row["code"] for row in result["issues"]} == {
        "APP_NOT_PUBLISHED",
        "APP_DISABLED",
        "APP_UNAVAILABLE",
    }
    with pytest.raises(InstallationContractError, match="PREFLIGHT_HELD"):
        compile_installation_bindings(template(), value)


def test_installed_and_connected_observations_never_change_private_binding_bytes() -> None:
    baseline = compile_installation_bindings(template(), request())
    changed = request()
    changed["plugin"]["installed"] = True
    changed["apps"][0]["installed"] = True
    changed["apps"][0]["connected"] = True
    observed = compile_installation_bindings(template(), changed)
    assert observed.content == baseline.content
    assert observed.binding_digest == baseline.binding_digest
    assert observed.public_receipt["plugin_installed_observed"] is True
    assert observed.public_receipt["app_connected_observations"]["mastermind-steward"] is True


def test_public_receipts_never_emit_raw_registry_or_app_ids() -> None:
    compiled = compile_installation_bindings(template(), request())
    documents = [
        preflight_installation(template(), request()),
        compiled.public_receipt,
    ]
    for document in documents:
        rendered = json.dumps(document, sort_keys=True)
        assert PLUGIN_ID not in rendered
        assert STEWARD_ID not in rendered
        assert EXECUTIVE_ID not in rendered
        assert "production_acceptance_granted\": true" not in rendered.lower()


def test_output_must_be_disjoint_from_source_and_symlink_free(tmp_path: Path) -> None:
    source = tmp_path / "repo"
    source.mkdir()
    compiled = compile_installation_bindings(template(), request())

    with pytest.raises(InstallationContractError, match="OUTPUT_PATH_REFUSED"):
        stage_compilation(
            compiled,
            output_root=source / "staging",
            source_root=source,
            expected_preimage_digest="ABSENT",
        )

    with pytest.raises(InstallationContractError, match="OUTPUT_PATH_REFUSED"):
        stage_compilation(
            compiled,
            output_root=source.parent,
            source_root=source,
            expected_preimage_digest="ABSENT",
        )

    real_output = tmp_path / "real-output"
    real_output.mkdir()
    link_output = tmp_path / "link-output"
    link_output.symlink_to(real_output, target_is_directory=True)
    with pytest.raises(InstallationContractError, match="OUTPUT_SYMLINK_REFUSED"):
        stage_compilation(
            compiled,
            output_root=link_output,
            source_root=source,
            expected_preimage_digest="ABSENT",
        )

    target_link = real_output / ".app.json"
    foreign = tmp_path / "foreign"
    foreign.write_text("foreign\n", encoding="utf-8")
    target_link.symlink_to(foreign)
    with pytest.raises(InstallationContractError, match="OUTPUT_SYMLINK_REFUSED"):
        stage_compilation(
            compiled,
            output_root=real_output,
            source_root=source,
            expected_preimage_digest="ABSENT",
        )


def test_preimage_temp_conflict_and_readback_mismatch_refuse(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    output.mkdir()
    target = output / ".app.json"
    target.write_text("prior\n", encoding="utf-8")
    compiled = compile_installation_bindings(template(), request())

    with pytest.raises(InstallationContractError, match="PREIMAGE_CONFLICT"):
        stage_compilation(
            compiled,
            output_root=output,
            source_root=source,
            expected_preimage_digest="ABSENT",
        )

    target.unlink()
    (output / ".app.json.tmp").write_text("foreign temp\n", encoding="utf-8")
    with pytest.raises(InstallationContractError, match="TEMPORARY_PATH_CONFLICT"):
        stage_compilation(
            compiled,
            output_root=output,
            source_root=source,
            expected_preimage_digest="ABSENT",
        )

    (output / ".app.json.tmp").unlink()
    stage = stage_compilation(
        compiled,
        output_root=output,
        source_root=source,
        expected_preimage_digest="ABSENT",
    )
    target.write_text("changed\n", encoding="utf-8")
    with pytest.raises(InstallationContractError, match="READBACK_MISMATCH"):
        verify_staged_compilation(compiled, output_root=output, source_root=source)
    with pytest.raises(InstallationContractError, match="PREIMAGE_CONFLICT"):
        rollback_staged_compilation(stage)


def test_lost_replace_response_reconciles_exact_postimage_without_second_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    compiled = compile_installation_bindings(template(), request())
    real_replace = os.replace
    calls = 0

    def replace_then_raise(src, dst, *args, **kwargs):
        nonlocal calls
        calls += 1
        real_replace(src, dst, *args, **kwargs)
        raise OSError("lost response after rename")

    monkeypatch.setattr(contract.os, "replace", replace_then_raise)
    stage = stage_compilation(
        compiled,
        output_root=output,
        source_root=source,
        expected_preimage_digest="ABSENT",
    )
    assert calls == 1
    assert stage.stage_receipt["status"] == "STAGED_VERIFIED"
    assert (output / ".app.json").read_bytes() == compiled.content


def test_replace_failure_before_effect_is_fixed_effect_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    compiled = compile_installation_bindings(template(), request())

    def fail_replace(*_args, **_kwargs):
        raise OSError("private path should never escape")

    monkeypatch.setattr(contract.os, "replace", fail_replace)
    with pytest.raises(InstallationContractError) as captured:
        stage_compilation(
            compiled,
            output_root=output,
            source_root=source,
            expected_preimage_digest="ABSENT",
        )
    assert captured.value.code == "STAGE_EFFECT_UNKNOWN"
    assert "private path" not in str(captured.value)


def test_temp_write_oserror_is_fixed_and_payload_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    compiled = compile_installation_bindings(template(), request())

    def fail_write(*_args, **_kwargs):
        raise OSError("/private/secret/staging-path")

    monkeypatch.setattr(contract, "_write_temp", fail_write)
    with pytest.raises(InstallationContractError) as captured:
        stage_compilation(
            compiled,
            output_root=output,
            source_root=source,
            expected_preimage_digest="ABSENT",
        )
    assert captured.value.code == "STAGE_EFFECT_UNKNOWN"
    assert "/private/secret" not in str(captured.value)


def test_readback_oserror_is_fixed_and_payload_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    compiled = compile_installation_bindings(template(), request())
    stage_compilation(
        compiled,
        output_root=output,
        source_root=source,
        expected_preimage_digest="ABSENT",
    )

    real_read_bytes = Path.read_bytes

    def fail_target_read(path: Path):
        if path.name == ".app.json":
            raise PermissionError("/private/secret/readback")
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_target_read)
    with pytest.raises(InstallationContractError) as captured:
        verify_staged_compilation(compiled, output_root=output, source_root=source)
    assert captured.value.code == "READBACK_MISMATCH"
    assert "/private/secret" not in str(captured.value)


def test_cli_ready_held_stage_verify_and_fixed_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts import mastermind_business_installation as cli

    template_path = tmp_path / "template.json"
    request_path = tmp_path / "request.json"
    template_path.write_text(json.dumps(template()), encoding="utf-8")
    request_path.write_text(json.dumps(request()), encoding="utf-8")

    assert cli.main(["--template", str(template_path), "--request", str(request_path)]) == 0
    ready = json.loads(capsys.readouterr().out)
    assert ready["status"] == "READY_TO_COMPILE"

    held = request()
    held["apps"] = [app("mastermind-executive")]
    request_path.write_text(json.dumps(held), encoding="utf-8")
    assert cli.main(["--template", str(template_path), "--request", str(request_path)]) == 3
    held_output = json.loads(capsys.readouterr().out)
    assert held_output["status"] == "PREFLIGHT_HELD"
    assert held_output["binding_document_digest"] is None

    request_path.write_text(json.dumps(request()), encoding="utf-8")
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    assert cli.main(
        [
            "--template", str(template_path),
            "--request", str(request_path),
            "--mode", "stage",
            "--source-root", str(source),
            "--output-root", str(output),
            "--expected-preimage-digest", "ABSENT",
        ]
    ) == 0
    stage_output = json.loads(capsys.readouterr().out)
    assert stage_output["stage_receipt"]["status"] == "STAGED_VERIFIED"
    assert PLUGIN_ID not in json.dumps(stage_output)
    assert STEWARD_ID not in json.dumps(stage_output)

    assert cli.main(
        [
            "--template", str(template_path),
            "--request", str(request_path),
            "--mode", "verify",
            "--source-root", str(source),
            "--output-root", str(output),
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "READBACK_VERIFIED"

    secret = request()
    secret["workspace_role"] = "xoxb-private-value"
    request_path.write_text(json.dumps(secret), encoding="utf-8")
    assert cli.main(["--template", str(template_path), "--request", str(request_path)]) == 2
    refusal = json.loads(capsys.readouterr().err)
    assert refusal == {
        "code": "SECRET_SHAPED_INPUT",
        "oauth_effect_applied": False,
        "production_acceptance_granted": False,
        "schema": "mastermind.business_sol_installation_error.v1",
        "status": "REFUSED",
        "workspace_effect_applied": False,
    }


def test_replace_failure_with_exact_existing_postimage_cleans_owned_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    output.mkdir()
    compiled = compile_installation_bindings(template(), request())
    target = output / ".app.json"
    target.write_bytes(compiled.content)
    target.chmod(0o600)

    def fail_before_replace(*_args, **_kwargs):
        raise OSError("rename unavailable")

    monkeypatch.setattr(contract.os, "replace", fail_before_replace)
    stage = stage_compilation(
        compiled,
        output_root=output,
        source_root=source,
        expected_preimage_digest=compiled.binding_digest,
    )
    assert stage.stage_receipt["status"] == "STAGED_VERIFIED"
    assert target.read_bytes() == compiled.content
    assert not (output / ".app.json.tmp").exists()


def test_rollback_lost_unlink_response_reconciles_absence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    compiled = compile_installation_bindings(template(), request())
    stage = stage_compilation(
        compiled,
        output_root=output,
        source_root=source,
        expected_preimage_digest="ABSENT",
    )
    real_unlink = Path.unlink

    def unlink_then_raise(path: Path, *args, **kwargs):
        real_unlink(path, *args, **kwargs)
        raise OSError("lost unlink response")

    monkeypatch.setattr(Path, "unlink", unlink_then_raise)
    result = rollback_staged_compilation(stage)
    assert result["status"] == "ROLLBACK_VERIFIED"
    assert result["restored_state"] == "ABSENT"
    assert not stage.target_path.exists()


def test_rollback_lost_replace_response_reconciles_exact_prior_bytes_and_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    output.mkdir()
    target = output / ".app.json"
    prior = b'{"prior":true}\n'
    target.write_bytes(prior)
    # Preimage capture requires read access under an ordinary, non-root user.
    target.chmod(0o400)
    compiled = compile_installation_bindings(template(), request())
    stage = stage_compilation(
        compiled,
        output_root=output,
        source_root=source,
        expected_preimage_digest=hashlib.sha256(prior).hexdigest(),
    )
    real_replace = os.replace
    replace_calls = []

    def replace_then_raise(src, dst, *args, **kwargs):
        replace_calls.append((src, dst))
        real_replace(src, dst, *args, **kwargs)
        raise OSError("lost rollback response")

    monkeypatch.setattr(contract.os, "replace", replace_then_raise)
    result = rollback_staged_compilation(stage)
    assert result["status"] == "ROLLBACK_VERIFIED"
    assert target.read_bytes() == prior
    assert target.stat().st_mode & 0o777 == 0o400
    assert len(replace_calls) == 1
    assert not (output / ".app.json.rollback.tmp").exists()


def test_zero_mode_rollback_preserves_mode_and_refuses_unreadable_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    output.mkdir()
    target = output / ".app.json"
    prior = b'{"prior":true}\n'
    target.write_bytes(prior)
    target.chmod(0o400)
    compiled = compile_installation_bindings(template(), request())
    captured = stage_compilation(
        compiled,
        output_root=output,
        source_root=source,
        expected_preimage_digest=hashlib.sha256(prior).hexdigest(),
    )
    # Model an already-captured zero-mode preimage without requiring privilege
    # to capture one on this host. Zero must not fall back to FILE_MODE.
    stage = replace(captured, prior_mode=0)
    real_read_bytes = Path.read_bytes
    real_replace = os.replace
    replace_calls = []
    written_modes = []

    def prepared_zero_mode_temp(path: Path, content: bytes, mode: int) -> None:
        # Supply the prepared zero-mode fixture at the write seam: the real
        # writer also cannot read back mode 000 without privilege. This case
        # independently exercises the subsequent lost-replace reconciliation.
        assert path == output / ".app.json.rollback.tmp"
        written_modes.append(mode)
        with path.open("xb") as stream:
            stream.write(content)
        path.chmod(mode)

    def unreadable_zero_mode(path: Path) -> bytes:
        if path == target and path.stat().st_mode & 0o777 == 0:
            raise PermissionError("synthetic unreadable restored preimage")
        return real_read_bytes(path)

    def replace_then_raise(src, dst, *args, **kwargs):
        replace_calls.append((src, dst))
        real_replace(src, dst, *args, **kwargs)
        raise OSError("lost rollback response")

    monkeypatch.setattr(Path, "read_bytes", unreadable_zero_mode)
    monkeypatch.setattr(contract, "_write_temp", prepared_zero_mode_temp)
    monkeypatch.setattr(contract.os, "replace", replace_then_raise)
    with pytest.raises(InstallationContractError, match="ROLLBACK_EFFECT_UNKNOWN"):
        rollback_staged_compilation(stage)
    assert len(replace_calls) == 1
    assert written_modes == [0]
    assert target.stat().st_mode & 0o777 == 0
    assert not (output / ".app.json.rollback.tmp").exists()
    # Only the test now makes its fixture readable to inspect the real bytes;
    # production correctly withheld a verified result and did not retry.
    target.chmod(0o400)
    assert real_read_bytes(target) == prior


def test_unreadable_preimage_refuses_before_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    output.mkdir()
    target = output / ".app.json"
    prior = b'{"prior":true}\n'
    target.write_bytes(prior)
    target.chmod(0o400)
    real_read_bytes = Path.read_bytes
    replace_calls = []

    def unreadable_preimage(path: Path) -> bytes:
        if path == target:
            raise PermissionError("synthetic unreadable preimage")
        return real_read_bytes(path)

    def unexpected_replace(*args, **kwargs):
        replace_calls.append((args, kwargs))
        raise AssertionError("refused preimage must not be replaced")

    monkeypatch.setattr(Path, "read_bytes", unreadable_preimage)
    monkeypatch.setattr(contract.os, "replace", unexpected_replace)
    compiled = compile_installation_bindings(template(), request())
    with pytest.raises(InstallationContractError, match="OUTPUT_PATH_REFUSED"):
        stage_compilation(
            compiled,
            output_root=output,
            source_root=source,
            expected_preimage_digest=hashlib.sha256(prior).hexdigest(),
        )
    assert replace_calls == []
    assert set(output.iterdir()) == {target}
    assert target.stat().st_mode & 0o777 == 0o400
    assert real_read_bytes(target) == prior

# Raw-file contract regressions: exercise the real CLI before any stage effect.
# Dict-only tests cannot observe duplicate JSON members discarded by a decoder.
_RAW_JSON_LIMIT = 1_048_576
_RAW_JSON_DEPTH = 64


def _raw_cli_case(case: str) -> tuple[bytes, bytes]:
    template_text = json.dumps(template(), separators=(",", ":"))
    request_text = json.dumps(request(), separators=(",", ":"))
    if case == "duplicate-source":
        request_text = '{"source_commit":"' + "f" * 40 + '",' + request_text[1:]
    elif case == "identical-duplicate":
        request_text = '{"generation":1,' + request_text[1:]
    elif case == "escaped-duplicate":
        request_text = '{"workspace_\\u0072ole":"MEMBER",' + request_text[1:]
    elif case == "duplicate-app-id":
        request_text = request_text.replace('"app_id":', '"app_id":"foreign-id","app_id":', 1)
    elif case == "duplicate-required":
        template_text = template_text.replace('"required":true', '"required":false,"required":true', 1)
    elif case == "discarded-secret":
        secret = "sk-" + "proj-" + "syntheticOnlyNotARealCredential"
        request_text = '{"source_commit":' + json.dumps(secret) + ',' + request_text[1:]
    elif case == "duplicate-app-census":
        request_text = '{"apps":[],' + request_text[1:]
    elif case in {"nan", "positive-infinity", "negative-infinity"}:
        raw_number = {"nan": "NaN", "positive-infinity": "Infinity", "negative-infinity": "-Infinity"}[case]
        request_text = '{"generation":' + raw_number + ',' + request_text[1:]
    elif case == "decoder-depth":
        request_text = "[" * 10000 + "0" + "]" * 10000
    elif case == "oversized-integer":
        request_text = '{"generation":' + "1" * 5000 + ',' + request_text[1:]
    elif case == "over-byte-limit":
        request_text += " " * (_RAW_JSON_LIMIT + 1 - len(request_text.encode("utf-8")))
    elif case == "invalid-utf8":
        return template_text.encode("utf-8"), b"\xff\xfe\xfa"
    else:
        raise AssertionError("unknown test case")
    return template_text.encode("utf-8"), request_text.encode("utf-8")


@pytest.mark.parametrize("mode", ("preflight", "stage", "verify"))
@pytest.mark.parametrize("case", (
    "duplicate-source", "identical-duplicate", "escaped-duplicate",
    "duplicate-app-id", "duplicate-required", "discarded-secret",
    "duplicate-app-census", "nan", "positive-infinity", "negative-infinity",
    "decoder-depth", "oversized-integer", "over-byte-limit", "invalid-utf8",
))
def test_raw_cli_refuses_ambiguous_or_unbounded_input_before_effect(tmp_path: Path, mode: str, case: str) -> None:
    import subprocess
    import sys

    raw_template, raw_request = _raw_cli_case(case)
    template_path, request_path = tmp_path / "template.json", tmp_path / "request.json"
    template_path.write_bytes(raw_template)
    request_path.write_bytes(raw_request)
    source_root, output_root = tmp_path / "source", tmp_path / "staging"
    source_root.mkdir()
    result = subprocess.run([
        sys.executable, "-m", "scripts.mastermind_business_installation",
        "--template", str(template_path), "--request", str(request_path),
        "--mode", mode, "--source-root", str(source_root),
        "--output-root", str(output_root), "--expected-preimage-digest", "ABSENT",
    ], cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, timeout=10)
    assert result.returncode == 2, (case, mode, result.returncode)
    assert result.stdout == ""
    assert json.loads(result.stderr) == {
        "schema": "mastermind.business_sol_installation_error.v1",
        "status": "REFUSED", "code": "INVALID_INPUT",
        "workspace_effect_applied": False, "oauth_effect_applied": False,
        "production_acceptance_granted": False,
    }
    assert not output_root.exists()
    assert list(source_root.iterdir()) == []
    assert template_path.read_bytes() == raw_template
    assert request_path.read_bytes() == raw_request


@pytest.mark.parametrize("input_name", ("template", "request"))
def test_raw_cli_reads_at_most_limit_plus_one_byte(tmp_path: Path, monkeypatch, input_name: str) -> None:
    import io
    import scripts.mastermind_business_installation as cli

    class ObservedReader(io.BytesIO):
        observed_sizes = []

        def read(self, size=-1):
            self.observed_sizes.append(size)
            assert size == _RAW_JSON_LIMIT + 1
            return super().read(size)

    reader = ObservedReader(b" " * (_RAW_JSON_LIMIT + 1))
    with monkeypatch.context() as patcher:
        patcher.setattr(Path, "open", lambda *_args, **_kwargs: reader)
        with pytest.raises(InstallationContractError, match="INVALID_INPUT"):
            cli._json_file(tmp_path / (input_name + ".json"))
    assert reader.observed_sizes == [_RAW_JSON_LIMIT + 1]


@pytest.mark.parametrize("field", ("template", "request"))
def test_raw_cli_exact_byte_limit_is_not_rejected(tmp_path: Path, field: str) -> None:
    import subprocess
    import sys

    data = {"template": json.dumps(template()), "request": json.dumps(request())}
    data[field] += " " * (_RAW_JSON_LIMIT - len(data[field].encode("utf-8")))
    for name, text in data.items():
        (tmp_path / (name + ".json")).write_text(text, encoding="utf-8")
    result = subprocess.run([
        sys.executable, "-m", "scripts.mastermind_business_installation",
        "--template", str(tmp_path / "template.json"),
        "--request", str(tmp_path / "request.json"),
    ], cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, timeout=10)
    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout)["status"] == "READY_TO_COMPILE"


def test_raw_cli_container_depth_bound_is_deterministic(tmp_path: Path) -> None:
    import scripts.mastermind_business_installation as cli

    target = tmp_path / "nested.json"
    target.write_text("[" * _RAW_JSON_DEPTH + "0" + "]" * _RAW_JSON_DEPTH)
    assert cli._json_file(target) is not None
    target.write_text("[" * (_RAW_JSON_DEPTH + 1) + "0" + "]" * (_RAW_JSON_DEPTH + 1))
    with pytest.raises(InstallationContractError, match="INVALID_INPUT"):
        cli._json_file(target)


@pytest.mark.parametrize("literal", ("NaN", "Infinity", "-Infinity", "1" * 65, "-" + "1" * 65))
def test_raw_cli_numeric_decoder_is_bounded_before_contract_validation(tmp_path: Path, literal: str) -> None:
    import scripts.mastermind_business_installation as cli

    path = tmp_path / "number.json"
    path.write_text(literal)
    with pytest.raises(InstallationContractError, match="INVALID_INPUT"):
        cli._json_file(path)


def test_raw_cli_bounded_integer_control_remains_valid(tmp_path: Path) -> None:
    import scripts.mastermind_business_installation as cli

    path = tmp_path / "number.json"
    path.write_text("1" * 64)
    assert cli._json_file(path) == int("1" * 64)


@pytest.mark.parametrize("relative_output", ("new-output", "deep/nested/output"))
def test_rejected_in_source_output_does_not_create_directories(tmp_path: Path, relative_output: str) -> None:
    source_root = tmp_path / "protected-source"
    source_root.mkdir()
    marker = source_root / "unchanged.txt"
    marker.write_bytes(b"protected preimage\n")
    output_root = source_root / relative_output
    before = sorted(p.relative_to(source_root).as_posix() for p in source_root.rglob("*"))
    compilation = compile_installation_bindings(template(), request())
    with pytest.raises(InstallationContractError, match="OUTPUT_PATH_REFUSED"):
        stage_compilation(compilation, output_root=output_root, source_root=source_root,
                          expected_preimage_digest="ABSENT")
    assert not output_root.exists()
    assert sorted(p.relative_to(source_root).as_posix() for p in source_root.rglob("*")) == before
    assert marker.read_bytes() == b"protected preimage\n"


def test_disjoint_new_output_directory_still_stages_and_rolls_back(tmp_path: Path) -> None:
    source_root = tmp_path / "protected-source"
    source_root.mkdir()
    output_root = tmp_path / "private" / "nested-staging"
    compilation = compile_installation_bindings(template(), request())
    staged = stage_compilation(compilation, output_root=output_root, source_root=source_root,
                               expected_preimage_digest="ABSENT")
    assert (output_root / ".app.json").read_bytes() == compilation.content
    assert verify_staged_compilation(compilation, output_root=output_root,
                                     source_root=source_root)["status"] == "READBACK_VERIFIED"
    rollback_staged_compilation(staged)
    assert not (output_root / ".app.json").exists()
    assert not list(source_root.iterdir())
