from __future__ import annotations

import hashlib
import json
import os
import plistlib
from pathlib import Path

import pytest

from ops.executive_os import compile_native_claude_worker_service as service
from ops.executive_os import compile_native_claude_v7_config as config_compiler
from scripts import executive_os_phase1c_worker as worker
from test_native_worker_factory import sealed_claude_config


def _config(root: Path) -> dict:
    value = sealed_claude_config(root)
    value.update(
        worker_user="_mastermind_claude_01",
        worker_uid=459,
        worker_gid=459,
        worker_id="claude8-native-01",
        provider_home="/var/db/mastermind-executive/workers/claude8-native-01/provider-home",
    )
    value["native_realm_enrollment"] = {
        "schema_version": "mastermind.native_provider_realm_enrollment/v1",
        "slot_id": "claude8-native-01",
        "enrollment_state": "enrolled",
        "generation": 2,
        "host_ref": "host-" + "1" * 64,
        "os_principal_ref": "principal-" + "2" * 64,
        "config_custody_ref": "custody-" + "3" * 64,
        "provider_binary_sha256": "4" * 64,
    }
    return value


def _template() -> bytes:
    root = Path(__file__).resolve().parents[1]
    return (
        root
        / "ops"
        / "executive_os"
        / "com.mastermind.executive.worker.codex.plist.template"
    ).read_bytes()


def test_render_reuses_existing_worker_plist_owner_for_native_slot(tmp_path: Path) -> None:
    config = _config(tmp_path)
    raw = config_compiler._canonical(config)
    sha = hashlib.sha256(raw).hexdigest()
    release_sha = "a" * 40
    root = Path(
        f"/Library/Application Support/MastermindExecutive/releases/{release_sha}"
    )

    plist_bytes, receipt = service.render_service(
        config,
        config_sha256=sha,
        release_root=root,
        expected_release_sha=release_sha,
        template_bytes=_template(),
    )
    plist = plistlib.loads(plist_bytes)

    assert plist["Label"] == "com.mastermind.executive.worker.claude8-native-01"
    assert plist["UserName"] == "_mastermind_claude_01"
    assert plist["GroupName"] == "_mastermind_claude_01"
    assert plist["InitGroups"] is False
    assert plist["WorkingDirectory"] == str(root)
    assert plist["ProgramArguments"] == [
        "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
        "-I",
        "-S",
        "-B",
        str(root / "scripts" / "executive_os_phase1c_worker.py"),
        "serve",
        "--config",
        "/Library/Application Support/MastermindExecutive/config/worker-claude8-native-01.json",
    ]
    assert plist["EnvironmentVariables"]["HOME"] == config["provider_home"]
    socket = plist["Sockets"]["WorkerBroker"]
    assert socket["SockPathName"] == (
        "/var/run/mastermind-executive/worker-claude8-native-01.sock"
    )
    assert socket["SockPathOwner"] == 450
    assert socket["SockPathGroup"] == 450
    assert socket["SockPathMode"] == 0o600
    assert receipt["launchd_state"] == "disabled_unloaded"
    assert receipt["socket_node_state"] == "absent"
    assert receipt["plist_sha256"] == hashlib.sha256(plist_bytes).hexdigest()
    assert receipt["config_sha256"] == sha


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.__setitem__("native_provider", "codex"),
        lambda value: value.__setitem__("operator_harness_armed", True),
        lambda value: value.__setitem__("schema_version", worker.NATIVE_CONFIG_SCHEMA_VERSION),
        lambda value: value["native_realm_enrollment"].__setitem__(
            "slot_id", "unknown-native-slot"
        ),
    ],
)
def test_render_refuses_nonsealed_or_unknown_native_slot(
    tmp_path: Path, mutation
) -> None:
    config = _config(tmp_path)
    mutation(config)
    raw = config_compiler._canonical(config)
    with pytest.raises(service.NativeClaudeServiceArtifactError):
        service.render_service(
            config,
            config_sha256=hashlib.sha256(raw).hexdigest(),
            release_root=Path(
                "/Library/Application Support/MastermindExecutive/releases/" + "a" * 40
            ),
            expected_release_sha="a" * 40,
            template_bytes=_template(),
        )


def test_render_refuses_stale_config_digest_or_noncanonical_release(tmp_path: Path) -> None:
    config = _config(tmp_path)
    raw = config_compiler._canonical(config)
    good_sha = hashlib.sha256(raw).hexdigest()

    with pytest.raises(service.NativeClaudeServiceArtifactError, match="digest"):
        service.render_service(
            config,
            config_sha256="0" * 64,
            release_root=Path(
                "/Library/Application Support/MastermindExecutive/releases/" + "a" * 40
            ),
            expected_release_sha="a" * 40,
            template_bytes=_template(),
        )
    with pytest.raises(service.NativeClaudeServiceArtifactError, match="release root"):
        service.render_service(
            config,
            config_sha256=good_sha,
            release_root=tmp_path / ("a" * 40),
            expected_release_sha="a" * 40,
            template_bytes=_template(),
        )


def test_cli_emits_plist_and_secret_free_receipt(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config_path = (tmp_path / "worker.json").resolve()
    raw = config_compiler._canonical(config)
    config_path.write_bytes(raw)
    release_sha = "b" * 40
    template_path = (
        Path(__file__).resolve().parents[1]
        / "ops"
        / "executive_os"
        / "com.mastermind.executive.worker.codex.plist.template"
    )
    plist_out = (tmp_path / "worker.plist").resolve()
    receipt_out = (tmp_path / "receipt.json").resolve()

    rc = service.main(
        [
            "--config",
            str(config_path),
            "--expected-config-sha256",
            hashlib.sha256(raw).hexdigest(),
            "--release-root",
            f"/Library/Application Support/MastermindExecutive/releases/{release_sha}",
            "--expected-release-sha",
            release_sha,
            "--template",
            str(template_path),
            "--plist-out",
            str(plist_out),
            "--receipt-out",
            str(receipt_out),
        ]
    )

    assert rc == 0
    plist = plistlib.loads(plist_out.read_bytes())
    assert plist["Label"].endswith("claude8-native-01")
    receipt_text = receipt_out.read_text()
    assert "credential" not in receipt_text.lower()
    assert "token" not in receipt_text.lower()


def _cli_inputs(root: Path):
    config = root / "worker.json"
    template = root / "template.plist"
    config.write_bytes(config_compiler._canonical(_config(root)))
    template.write_bytes(_template())
    return config, template


def _cli_args(config: Path, template: Path, plist: Path, receipt: Path):
    release_sha = "b" * 40
    return [
        "--config", str(config),
        "--expected-config-sha256", hashlib.sha256(config.read_bytes()).hexdigest(),
        "--release-root", "/Library/Application Support/MastermindExecutive/releases/" + release_sha,
        "--expected-release-sha", release_sha,
        "--template", str(template),
        "--plist-out", str(plist), "--receipt-out", str(receipt),
    ]


@pytest.mark.parametrize("link_kind", ["same", "resolved", "symlink", "hardlink"])
@pytest.mark.parametrize("destination,target", [
    ("plist", "receipt"),
    ("plist", "config"),
    ("plist", "template"),
    ("receipt", "config"),
    ("receipt", "template"),
])
def test_cli_rejects_artifact_aliases_before_writing(
    tmp_path: Path, destination: str, target: str, link_kind: str
) -> None:
    config, template = _cli_inputs(tmp_path)
    paths = {"config": config, "template": template,
             "plist": tmp_path / "worker.plist", "receipt": tmp_path / "receipt.json"}
    alias, original = paths[destination], paths[target]
    if link_kind == "same":
        paths[destination] = original
    elif link_kind == "resolved":
        (tmp_path / "alias-parent").mkdir()
        paths[destination] = tmp_path / "alias-parent" / ".." / original.name
    elif link_kind == "symlink":
        alias.symlink_to(original)
    else:
        if not original.exists():
            original.write_bytes(b"existing artifact must survive\n")
        os.link(original, alias)
    before = {path: path.read_bytes() for path in paths.values() if path.is_file()}
    rc = service.main(_cli_args(config, template, paths["plist"], paths["receipt"]))
    assert all(path.read_bytes() == raw for path, raw in before.items())
    assert rc == 2


@pytest.mark.parametrize("format_name", ["no_lf", "crlf", "pretty", "extra_lf"])
def test_cli_refuses_noncanonical_config_bytes_with_their_actual_digest(
    tmp_path: Path, format_name: str
) -> None:
    config, template = _cli_inputs(tmp_path)
    canonical = config.read_bytes()
    variants = {
        "no_lf": canonical[:-1],
        "crlf": canonical[:-1] + b"\r\n",
        "pretty": (json.dumps(json.loads(canonical), indent=2) + "\n").encode(),
        "extra_lf": canonical + b"\n",
    }
    raw = variants[format_name]
    config.write_bytes(raw)
    plist, receipt = tmp_path / "worker.plist", tmp_path / "receipt.json"
    assert service.main(_cli_args(config, template, plist, receipt)) == 2
    assert config.read_bytes() == raw
    assert not plist.exists() and not receipt.exists()


def test_cli_consumes_real_producer_artifact_and_receipt_unchanged(tmp_path: Path) -> None:
    from test_compile_native_claude_v7_config import _validation

    source = _config(tmp_path)
    source["schema_version"] = worker.NATIVE_CONFIG_SCHEMA_VERSION
    for field in (
        "sealed_worker_model", "managed_policy_generation",
        "validation_codex_binary", "validation_codex_attestation_receipt",
        "validation_allowed_codex_versions", "validation_required_team_identifier",
    ):
        del source[field]
    source_path, validation_path = tmp_path / "source-v6.json", tmp_path / "validation.json"
    source_raw = config_compiler._canonical(source)
    validation_raw = config_compiler._canonical(_validation(tmp_path))
    source_path.write_bytes(source_raw)
    validation_path.write_bytes(validation_raw)
    config_path, config_receipt = tmp_path / "produced-v7.json", tmp_path / "producer-receipt.json"
    assert config_compiler.main([
        "--source-v6", str(source_path),
        "--expected-source-sha256", hashlib.sha256(source_raw).hexdigest(),
        "--validation-config", str(validation_path),
        "--expected-validation-sha256", hashlib.sha256(validation_raw).hexdigest(),
        "--managed-policy-generation", "1",
        "--out", str(config_path), "--receipt-out", str(config_receipt),
    ]) == 0
    produced = config_path.read_bytes()
    producer_receipt = json.loads(config_receipt.read_bytes())
    assert produced.endswith(b"\n")
    assert producer_receipt["compiled_v7_sha256"] == hashlib.sha256(produced).hexdigest()
    template_path = tmp_path / "template.plist"
    template_path.write_bytes(_template())
    plist, receipt = tmp_path / "worker.plist", tmp_path / "service-receipt.json"
    args = _cli_args(config_path, template_path, plist, receipt)
    args[args.index("--expected-config-sha256") + 1] = producer_receipt["compiled_v7_sha256"]
    assert service.main(args) == 0
    assert config_path.read_bytes() == produced
    result = json.loads(receipt.read_bytes())
    assert result["config_sha256"] == producer_receipt["compiled_v7_sha256"]
    assert result["plist_sha256"] == hashlib.sha256(plist.read_bytes()).hexdigest()
    assert result["launchd_state"] == "disabled_unloaded"
    assert result["socket_node_state"] == "absent"
    assert source_path.read_bytes() == source_raw
    assert validation_path.read_bytes() == validation_raw
