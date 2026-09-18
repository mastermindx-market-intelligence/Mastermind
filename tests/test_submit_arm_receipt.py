from __future__ import annotations

import json
import os
import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

import pytest

from control_plane import executive_ceo_ingress
from ops.executive_os import submit_arm_receipt as receipt


def _submit_frame() -> dict[str, object]:
    return {
        "schema": executive_ceo_ingress.SUBMIT_SCHEMA_V2,
        "request_ref": "req-replay-1",
        "observed_grounding": {
            "mastermind_sha": "a" * 40,
            "macro_sha": "b" * 40,
            "boot_packet_schema": executive_ceo_ingress.BOOT_PACKET_SCHEMA,
        },
        "request": {
            "objective": "test", "workstream": "WS:REPLAY",
            "department": "executive-infrastructure", "priority": 10,
            "execution_profile": "research_only",
        },
    }


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, object]]:
    release = tmp_path / ("a" * 40)
    release.mkdir()
    manifest = release / ".executive-release-manifest.json"
    manifest.write_text(json.dumps({"commit_sha": "a" * 40}) + "\n", encoding="utf-8")
    config = tmp_path / "control.json"
    config.write_text(json.dumps({"control_uid": os.geteuid()}) + "\n", encoding="utf-8")
    parent = tmp_path / "receipt-parent"
    parent.mkdir()
    parent.chmod(0o700)
    target = parent / "receipt.json"
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    return target, config, release, {"now": now, "commit": "a" * 40}


def test_d6_verify_distinct_absent_stale_principal_release_and_success(tmp_path: Path) -> None:
    target, config, release, values = _fixture(tmp_path)
    with pytest.raises(receipt.SubmitArmReceiptError, match="receipt_absent"):
        receipt.verify(target, config, release, now=values["now"])

    document = receipt.make_receipt(config, release, principal_uid=os.geteuid(), now=values["now"])
    target.write_text(json.dumps(document) + "\n", encoding="utf-8")
    target.chmod(0o400)
    assert receipt.verify(target, config, release, now=values["now"])["armed_scope"] == "ceo_submit"

    stale = dict(document)
    stale["observed_at"] = (values["now"] - timedelta(seconds=receipt.RECEIPT_MAX_AGE_SECONDS + 1)).isoformat(timespec="seconds")
    target.chmod(0o600)
    target.write_text(json.dumps(stale) + "\n", encoding="utf-8")
    target.chmod(0o400)
    with pytest.raises(receipt.SubmitArmReceiptError, match="receipt_stale"):
        receipt.verify(target, config, release, now=values["now"])

    wrong_principal = dict(document)
    wrong_principal["principal"] = {"effective_uid": 999, "effective_gid": 999}
    target.chmod(0o600)
    target.write_text(json.dumps(wrong_principal) + "\n", encoding="utf-8")
    target.chmod(0o400)
    with pytest.raises(receipt.SubmitArmReceiptError, match="receipt_wrong_principal"):
        receipt.verify(target, config, release, now=values["now"])

    wrong_release = dict(document)
    wrong_release["release_commit_sha"] = "b" * 40
    target.chmod(0o600)
    target.write_text(json.dumps(wrong_release) + "\n", encoding="utf-8")
    target.chmod(0o400)
    with pytest.raises(receipt.SubmitArmReceiptError, match="receipt_wrong_release"):
        receipt.verify(target, config, release, now=values["now"])


def test_d6_emit_refuses_non_root_and_release_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target, config, release, values = _fixture(tmp_path)
    monkeypatch.setattr(receipt.os, "geteuid", lambda: 501)
    with pytest.raises(receipt.SubmitArmReceiptError, match="emit_requires_root"):
        receipt.emit(target, config, release, now=values["now"])
    monkeypatch.setattr(receipt.os, "geteuid", lambda: 0)
    (release / ".executive-release-manifest.json").write_text(json.dumps({"commit_sha": "b" * 40}), encoding="utf-8")
    with pytest.raises(receipt.SubmitArmReceiptError, match="release_mismatch"):
        receipt.emit(target, config, release, now=values["now"])

    wrong_name = tmp_path / ("c" * 40)
    wrong_name.mkdir()
    (wrong_name / ".executive-release-manifest.json").write_text(json.dumps({"commit_sha": "a" * 40}), encoding="utf-8")
    with pytest.raises(receipt.SubmitArmReceiptError, match="release_mismatch"):
        receipt.emit(target, config, wrong_name, now=values["now"])

    non_sha_name = tmp_path / "release"
    non_sha_name.mkdir()
    (non_sha_name / ".executive-release-manifest.json").write_text(json.dumps({"commit_sha": "a" * 40}), encoding="utf-8")
    with pytest.raises(receipt.SubmitArmReceiptError, match="release_mismatch"):
        receipt.emit(target, config, non_sha_name, now=values["now"])

    with pytest.raises(receipt.SubmitArmReceiptError, match="emit_requires_root"):
        monkeypatch.setattr(receipt.os, "geteuid", lambda: 501)
        receipt.emit(target, config, release, now=values["now"])


def test_d6_verify_rejects_non_private_receipt(tmp_path: Path) -> None:
    target, config, release, values = _fixture(tmp_path)
    document = receipt.make_receipt(config, release, principal_uid=os.geteuid(), now=values["now"])
    target.write_text(json.dumps(document) + "\n", encoding="utf-8")
    target.chmod(0o666)
    with pytest.raises(receipt.SubmitArmReceiptError, match="receipt_not_private"):
        receipt.verify(target, config, release, now=values["now"])


def test_d6_receipt_parent_privacy_and_descriptor_discriminators(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    current_uid = os.geteuid()
    target, config, release, values = _fixture(tmp_path)
    document = receipt.make_receipt(config, release, principal_uid=current_uid, now=values["now"])
    target.write_text(json.dumps(document) + "\n", encoding="utf-8")
    target.chmod(0o400)

    target.parent.chmod(0o755)
    with pytest.raises(receipt.SubmitArmReceiptError, match="receipt_parent_not_private"):
        receipt.verify(target, config, release, now=values["now"])
    monkeypatch.setattr(receipt.os, "geteuid", lambda: 0)
    with pytest.raises(receipt.SubmitArmReceiptError, match="receipt_parent_not_private"):
        receipt.emit(target, config, release, now=values["now"])

    target.parent.chmod(0o400)
    other_uid = current_uid + 1
    config.write_text(json.dumps({"control_uid": other_uid}) + "\n", encoding="utf-8")
    with pytest.raises(receipt.SubmitArmReceiptError, match="receipt_parent_not_private"):
        receipt.verify(target, config, release, now=values["now"])

    target.parent.chmod(0o700)
    config.write_text(json.dumps({"control_uid": current_uid}) + "\n", encoding="utf-8")
    target.unlink()
    target.symlink_to(release / ".executive-release-manifest.json")
    with pytest.raises(receipt.SubmitArmReceiptError, match="receipt_not_private"):
        receipt.verify(target, config, release, now=values["now"])

    target.unlink()
    target.mkdir()
    with pytest.raises(receipt.SubmitArmReceiptError, match="receipt_not_private"):
        receipt.verify(target, config, release, now=values["now"])

    target.rmdir()
    target.write_text(json.dumps(document) + "\n", encoding="utf-8")
    target.chmod(0o400)
    assert receipt.verify(target, config, release, now=values["now"]) == document

    target.unlink()
    target.symlink_to(config)
    with pytest.raises(receipt.SubmitArmReceiptError, match="receipt_not_private"):
        receipt.verify(target, config, release, now=values["now"])


def test_d6_atomic_private_receipt_shape_and_no_host_absolute_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = Path(__file__).parents[1] / "ops" / "executive_os" / "submit_arm_receipt.py"
    text = source.read_text(encoding="utf-8")
    assert "/var/" not in text and "/private/var" not in text and "/Library/" not in text
    target, config, release, values = _fixture(tmp_path)
    parent = target.parent
    monkeypatch.setattr(receipt.os, "geteuid", lambda: 0)
    receipt.emit(target, config, release, now=values["now"])
    info = target.lstat()
    assert info.st_mode & 0o777 == 0o400
    assert info.st_mode & 0o170000 == 0o100000
    assert not target.is_symlink()
    assert not list(parent.glob(f".{target.name}.*"))
    assert {entry.name for entry in parent.iterdir()} == {target.name}


def test_d5_v2_replay_does_not_reobserve_grounding() -> None:
    frame = _submit_frame()
    runtime = mock.Mock()
    runtime.store.find_event_by_command_id.return_value = {"durable": True}
    grounding = mock.Mock()
    sink_receipt = {"dispatched": False, "duplicate": True}

    async def exercise() -> dict[str, object]:
        with mock.patch.object(executive_ceo_ingress, "_submit", new=mock.AsyncMock(return_value=sink_receipt)) as sink:
            result = await executive_ceo_ingress.handle_frame(
                frame, runtime=runtime, grounding_provider=grounding,
                workspace_root="/tmp", service_state="READY", ceo_ingress_armed=True,
            )
            assert sink.await_count == 1
            return result

    result = asyncio.run(exercise())
    assert result == sink_receipt
    grounding.observe.assert_not_called()
