from __future__ import annotations

import hashlib
import plistlib
from pathlib import Path

import pytest

from ops.executive_os import compile_native_claude_worker_service as service
from ops.executive_os.capacity_broker_topology import canonical_json
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
    raw = canonical_json(config)
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
    raw = canonical_json(config)
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
    raw = canonical_json(config)
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
    raw = canonical_json(config)
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
