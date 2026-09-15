from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ops.executive_os import submit_arm_receipt as receipt


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, object]]:
    release = tmp_path / "release"
    release.mkdir()
    manifest = release / ".executive-release-manifest.json"
    manifest.write_text(json.dumps({"commit_sha": "a" * 40}) + "\n", encoding="utf-8")
    config = tmp_path / "control.json"
    config.write_text(json.dumps({"control_uid": os.geteuid(), "release_commit_sha": "a" * 40}) + "\n", encoding="utf-8")
    target = tmp_path / "receipt.json"
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    return target, config, release, {"now": now, "commit": "a" * 40}


def test_d6_verify_distinct_absent_stale_principal_release_and_success(tmp_path: Path) -> None:
    target, config, release, values = _fixture(tmp_path)
    with pytest.raises(receipt.SubmitArmReceiptError, match="receipt_absent"):
        receipt.verify(target, config, release, now=values["now"])

    document = receipt.make_receipt(config, release, principal_uid=os.geteuid(), now=values["now"])
    target.write_text(json.dumps(document) + "\n", encoding="utf-8")
    assert receipt.verify(target, config, release, now=values["now"])["armed_scope"] == "ceo_submit"

    stale = dict(document)
    stale["observed_at"] = (values["now"] - timedelta(seconds=receipt.RECEIPT_MAX_AGE_SECONDS + 1)).isoformat(timespec="seconds")
    target.write_text(json.dumps(stale) + "\n", encoding="utf-8")
    with pytest.raises(receipt.SubmitArmReceiptError, match="receipt_stale"):
        receipt.verify(target, config, release, now=values["now"])

    wrong_principal = dict(document)
    wrong_principal["principal"] = {"effective_uid": 999, "effective_gid": 999}
    target.write_text(json.dumps(wrong_principal) + "\n", encoding="utf-8")
    with pytest.raises(receipt.SubmitArmReceiptError, match="receipt_wrong_principal"):
        receipt.verify(target, config, release, now=values["now"])

    wrong_release = dict(document)
    wrong_release["release_commit_sha"] = "b" * 40
    target.write_text(json.dumps(wrong_release) + "\n", encoding="utf-8")
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


def test_d6_no_host_absolute_paths_and_atomic_private_shape() -> None:
    source = Path(__file__).parents[1] / "ops" / "executive_os" / "submit_arm_receipt.py"
    text = source.read_text(encoding="utf-8")
    assert "/var/" not in text and "/private/var" not in text and "/Library/" not in text
