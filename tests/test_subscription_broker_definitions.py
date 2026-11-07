from __future__ import annotations

import json
import plistlib
import stat
from pathlib import Path

import pytest

from ops.executive_os import subscription_broker_definitions as definitions
from scripts.executive_os_phase1c_worker import (
    WorkerConfigError,
    _assert_service_activation_allowed,
    _load_config,
)


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "ops" / "executive_os" / "com.mastermind.executive.worker.codex.plist.template"
GIDS = {
    "alibaba-token-01": [12, 61, 100],
    "minimax-token-01": [12, 61, 100],
}


def _build():
    return definitions.build_definitions(
        release_root=Path("/opt/mastermind/release"),
        template_bytes=TEMPLATE.read_bytes(),
        supplementary_gids=GIDS,
    )


def test_definitions_render_two_held_v5_brokers_without_capacity_authority() -> None:
    manifest, configs, plists = _build()
    assert manifest["schema_version"] == definitions.DEFINITIONS_SCHEMA
    assert manifest["start_authority"] is False
    assert manifest["credential_authority"] is False
    assert manifest["capacity_authority"] is False
    assert manifest["route_authority"] is False
    assert tuple(row["slot_id"] for row in manifest["definitions"]) == (
        "alibaba-token-01",
        "minimax-token-01",
    )
    assert set(configs) == set(plists) == set(GIDS)
    rendered = json.dumps(manifest, sort_keys=True)
    for forbidden in (
        "capacity_capability_id",
        "capability_generation",
        "account_label",
        "provider-key",
        "api_key",
        "auth.json",
    ):
        assert forbidden not in rendered


@pytest.mark.parametrize(
    ("slot_id", "binding_id"),
    (
        ("alibaba-token-01", "alibaba-token-plan-personal.codex-responses"),
        ("minimax-token-01", "minimax-token-plan.codex-responses"),
    ),
)
def test_rendered_config_is_valid_v5_but_autonomous_serve_refuses(
    tmp_path: Path, slot_id: str, binding_id: str
) -> None:
    _manifest, configs, _plists = _build()
    value = json.loads(configs[slot_id])
    assert value["schema_version"] == definitions.WORKER_CONFIG_SCHEMA
    assert value["harness_binding_id"] == binding_id
    assert value["worker_id"] == slot_id
    assert value["require_secret_canary"] is True
    assert value["operator_harness_armed"] is False

    path = tmp_path / f"{slot_id}.json"
    path.write_bytes(configs[slot_id])
    path.chmod(0o440)
    loaded = _load_config(path, require_root_owner=False)
    with pytest.raises(WorkerConfigError, match="not armed for autonomous service"):
        _assert_service_activation_allowed(loaded)


def test_plists_bind_exact_principals_and_remain_definitions_only() -> None:
    manifest, _configs, plists = _build()
    rows = {row["slot_id"]: row for row in manifest["definitions"]}
    expected = {
        "alibaba-token-01": "_mastermind_alibaba_01",
        "minimax-token-01": "_mastermind_minimax_01",
    }
    for slot_id, user in expected.items():
        value = plistlib.loads(plists[slot_id])
        assert value["Label"] == f"com.mastermind.executive.worker.{slot_id}"
        assert value["UserName"] == user
        assert value["GroupName"] == user
        assert value["EnvironmentVariables"]["HOME"].endswith(
            f"/workers/{slot_id}/provider-home"
        )
        assert value["ProgramArguments"][-2:] == [
            "--config",
            rows[slot_id]["config_path"],
        ]
        assert value.get("RunAtLoad") is False
        assert value.get("KeepAlive") is False
        assert value.get("Disabled") is True
        assert rows[slot_id]["launchd_state"] == "disabled_unloaded"
        assert rows[slot_id]["worker_execution"] == "held_for_real_canary"
        assert rows[slot_id]["autonomous_allowed"] is False


def test_staging_writer_creates_only_private_inert_artifacts(tmp_path: Path) -> None:
    manifest, configs, plists = _build()
    destination = tmp_path / "stage"
    definitions.write_definitions(
        destination,
        manifest=manifest,
        configs=configs,
        plists=plists,
    )
    names = sorted(path.name for path in destination.iterdir())
    assert names == [
        "com.mastermind.executive.worker.alibaba-token-01.plist",
        "com.mastermind.executive.worker.minimax-token-01.plist",
        "subscription-broker-definitions.json",
        "worker-alibaba-token-01.json",
        "worker-minimax-token-01.json",
    ]
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o400 for path in destination.iterdir())
    _assert_artifact_bytes(destination, manifest, configs, plists)


@pytest.mark.parametrize(
    "gids",
    (
        {"alibaba-token-01": [12, 61, 100]},
        {**GIDS, "unexpected": [12, 61, 100]},
        {"alibaba-token-01": [12, 61, 100], "minimax-token-01": []},
    ),
)
def test_definitions_refuse_incomplete_extra_or_invalid_supplementary_gids(gids) -> None:
    with pytest.raises((definitions.SubscriptionBrokerDefinitionError, ValueError)):
        definitions.build_definitions(
            release_root=Path("/opt/mastermind/release"),
            template_bytes=TEMPLATE.read_bytes(),
            supplementary_gids=gids,
        )


def _expected_artifacts(manifest, configs, plists):
    expected = {
        "subscription-broker-definitions.json": definitions.canonical_json(manifest, pretty=True)
    }
    for slot_id in sorted(configs):
        expected[f"worker-{slot_id}.json"] = configs[slot_id]
        expected[f"com.mastermind.executive.worker.{slot_id}.plist"] = plists[slot_id]
    return expected


def _assert_artifact_bytes(destination, manifest, configs, plists):
    import hashlib

    expected = _expected_artifacts(manifest, configs, plists)
    assert {path.name for path in destination.iterdir()} == set(expected)
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    for name, payload in expected.items():
        assert (destination / name).read_bytes() == payload
    for row in manifest["definitions"]:
        slot_id = row["slot_id"]
        assert hashlib.sha256((destination / f"worker-{slot_id}.json").read_bytes()).hexdigest() == row["config_sha256"]
        assert hashlib.sha256((destination / f"com.mastermind.executive.worker.{slot_id}.plist").read_bytes()).hexdigest() == row["plist_sha256"]


def test_staging_writer_completes_repeated_short_writes(tmp_path, monkeypatch):
    manifest, configs, plists = _build()
    destination = tmp_path / "short"
    real_write = definitions.os.write
    observed = []

    def short_write(descriptor, payload):
        count = real_write(descriptor, payload[:17])
        observed.append((len(payload), count))
        return count

    with monkeypatch.context() as patch:
        patch.setattr(definitions.os, "write", short_write)
        definitions.write_definitions(destination, manifest=manifest, configs=configs, plists=plists)
    assert len(observed) > 5
    assert any(written < requested for requested, written in observed)
    _assert_artifact_bytes(destination, manifest, configs, plists)


@pytest.mark.parametrize("prefix_written", [False, True])
def test_staging_writer_refuses_zero_progress_without_fsync_or_continuation(
    tmp_path, monkeypatch, prefix_written
):
    manifest, configs, plists = _build()
    destination = tmp_path / "zero"
    payload = definitions.canonical_json(manifest, pretty=True)
    real_write = definitions.os.write
    real_close = definitions.os.close
    real_fsync = definitions.os.fsync
    calls, closed, synced = [], [], []

    def no_progress(descriptor, remaining):
        calls.append((descriptor, bytes(remaining)))
        if prefix_written and len(calls) == 1:
            return real_write(descriptor, remaining[:7])
        if len(calls) == (2 if prefix_written else 1):
            return 0
        raise AssertionError("writer continued after zero progress")

    def close(descriptor):
        closed.append(descriptor)
        return real_close(descriptor)

    def fsync(descriptor):
        synced.append(descriptor)
        return real_fsync(descriptor)

    with monkeypatch.context() as patch:
        patch.setattr(definitions.os, "write", no_progress)
        patch.setattr(definitions.os, "close", close)
        patch.setattr(definitions.os, "fsync", fsync)
        with pytest.raises(OSError, match="subscription_definition_write_no_progress"):
            definitions.write_definitions(destination, manifest=manifest, configs=configs, plists=plists)
    assert len(calls) == (2 if prefix_written else 1)
    descriptor = calls[0][0]
    assert closed == [descriptor]
    assert synced == []
    with pytest.raises(OSError):
        definitions.os.fstat(descriptor)
    assert sorted(path.name for path in destination.iterdir()) == ["subscription-broker-definitions.json"]
    assert (destination / "subscription-broker-definitions.json").read_bytes() == (payload[:7] if prefix_written else b"")
    if prefix_written:
        assert calls[1] == (descriptor, payload[7:])


def test_cli_write_error_reports_refusal_without_success_digest(tmp_path, monkeypatch, capsys):
    gids = tmp_path / "gids.json"
    gids.write_text(json.dumps(GIDS), encoding="utf-8")
    destination = tmp_path / "failed"
    real_write = definitions.os.write
    real_close = definitions.os.close
    calls, closed = [], []

    def fail_after_prefix(descriptor, remaining):
        calls.append(descriptor)
        if len(calls) == 1:
            return real_write(descriptor, remaining[:7])
        raise OSError("injected short-write failure")

    def close(descriptor):
        closed.append(descriptor)
        return real_close(descriptor)

    with monkeypatch.context() as patch:
        patch.setattr(definitions.os, "write", fail_after_prefix)
        patch.setattr(definitions.os, "close", close)
        status = definitions.main([
            "--release-root", "/opt/mastermind/release",
            "--template", str(TEMPLATE),
            "--supplementary-gids-json", str(gids),
            "--destination", str(destination),
        ])
    captured = capsys.readouterr()
    assert status == 65
    assert captured.out == ""
    assert captured.err == "subscription broker definitions refused: OSError\n"
    assert len(calls) == 2 and calls[0] == calls[1]
    assert closed == [calls[0]]
    with pytest.raises(OSError):
        definitions.os.fstat(calls[0])
    assert sorted(path.name for path in destination.iterdir()) == ["subscription-broker-definitions.json"]
    assert (destination / "subscription-broker-definitions.json").stat().st_size == 7
