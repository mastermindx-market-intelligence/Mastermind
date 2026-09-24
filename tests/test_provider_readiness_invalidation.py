from __future__ import annotations

from pathlib import Path

import pytest

from ops.executive_os import provider_readiness as readiness


def _personal_slot_gids() -> list[int]:
    return [
        slot.worker_gid
        for slot in readiness.provider_worker_slots.all_slots()
        if slot.workspace_binding_class == readiness.PERSONAL_PRO_WORKER_BINDING_CLASS
    ]


def _receipt(tmp_path: Path) -> Path:
    path = tmp_path / "provider-readiness-v2.json"
    path.write_text("{}\n", encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("binding", "gid_kind", "expected_mode"),
    [
        (readiness.PERSONAL_PRO_WORKER_BINDING_CLASS, "personal", 0o440),
        (readiness.COMPANY_WORKSPACE_BINDING_CLASS, "company", 0o400),
    ],
)
def test_invalidate_uses_storage_contract_then_unlinks_and_fsyncs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    binding: str,
    gid_kind: str,
    expected_mode: int,
) -> None:
    personal_gids = _personal_slot_gids()
    assert personal_gids
    worker_gid = personal_gids[0] if gid_kind == "personal" else readiness.WORKER_GID
    expected_gid = worker_gid if gid_kind == "personal" else 0
    receipt = _receipt(tmp_path)
    observed: dict[str, object] = {}

    monkeypatch.setattr(readiness, "_validate_receipt_directory", lambda path: observed.setdefault("parent", path.parent))

    def _lstat(path: Path, *, expected_uid: int, expected_gid: int, expected_mode: int, require_nonempty: bool = False):
        observed["identity"] = (path, expected_uid, expected_gid, expected_mode, require_nonempty)
        return {"inode": 1}

    monkeypatch.setattr(readiness, "lstat_identity", _lstat)
    monkeypatch.setattr(readiness, "_fsync_directory", lambda path: observed.setdefault("fsync", path))

    readiness.invalidate_readiness_receipt(
        receipt,
        workspace_binding_class=binding,
        worker_gid=worker_gid,
    )

    assert not receipt.exists()
    assert observed["parent"] == tmp_path
    assert observed["identity"] == (receipt, 0, expected_gid, expected_mode, False)
    assert observed["fsync"] == tmp_path


def test_invalidate_wrong_reviewed_personal_slot_gid_refuses_without_unlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gids = _personal_slot_gids()
    if len(gids) < 2:
        pytest.skip("requires at least two reviewed Personal-Pro slots")
    selected_gid, wrong_gid = gids[:2]
    receipt = _receipt(tmp_path)
    monkeypatch.setattr(readiness, "_validate_receipt_directory", lambda path: None)

    def _lstat(path: Path, *, expected_uid: int, expected_gid: int, expected_mode: int, require_nonempty: bool = False):
        assert expected_gid == wrong_gid
        assert expected_gid != selected_gid
        assert expected_mode == 0o440
        raise readiness.ReadinessError("identity_group_mismatch")

    monkeypatch.setattr(readiness, "lstat_identity", _lstat)
    with pytest.raises(readiness.ReadinessError, match="identity_group_mismatch"):
        readiness.invalidate_readiness_receipt(
            receipt,
            workspace_binding_class=readiness.PERSONAL_PRO_WORKER_BINDING_CLASS,
            worker_gid=wrong_gid,
        )
    assert receipt.exists()


def test_invalidate_arbitrary_personal_gid_refuses_before_lstat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _receipt(tmp_path)
    monkeypatch.setattr(readiness, "_validate_receipt_directory", lambda path: None)
    called = False

    def _lstat(*args, **kwargs):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(readiness, "lstat_identity", _lstat)
    arbitrary_gid = max(_personal_slot_gids() or [1000]) + 10000
    with pytest.raises(readiness.ReadinessError, match="readiness_receipt_reader_invalid"):
        readiness.invalidate_readiness_receipt(
            receipt,
            workspace_binding_class=readiness.PERSONAL_PRO_WORKER_BINDING_CLASS,
            worker_gid=arbitrary_gid,
        )
    assert not called
    assert receipt.exists()


@pytest.mark.parametrize(
    "reason",
    [
        "identity_not_regular",
        "identity_acl_unsafe",
        "identity_link_count_mismatch",
        "identity_owner_mismatch",
        "identity_group_mismatch",
        "identity_mode_mismatch",
    ],
)
def test_invalidate_metadata_refusal_never_unlinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
) -> None:
    receipt = _receipt(tmp_path)
    monkeypatch.setattr(readiness, "_validate_receipt_directory", lambda path: None)
    monkeypatch.setattr(readiness, "_fsync_directory", lambda path: pytest.fail("fsync must not run after refusal"))

    def _lstat(*args, **kwargs):
        raise readiness.ReadinessError(reason)

    monkeypatch.setattr(readiness, "lstat_identity", _lstat)
    with pytest.raises(readiness.ReadinessError, match=reason):
        readiness.invalidate_readiness_receipt(
            receipt,
            workspace_binding_class=readiness.COMPANY_WORKSPACE_BINDING_CLASS,
            worker_gid=readiness.WORKER_GID,
        )
    assert receipt.exists()


def test_invalidate_unsafe_parent_refuses_before_identity_or_unlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _receipt(tmp_path)
    monkeypatch.setattr(
        readiness,
        "_validate_receipt_directory",
        lambda path: (_ for _ in ()).throw(readiness.ReadinessError("readiness_parent_unsafe")),
    )
    monkeypatch.setattr(readiness, "lstat_identity", lambda *args, **kwargs: pytest.fail("identity must not run"))
    with pytest.raises(readiness.ReadinessError, match="readiness_parent_unsafe"):
        readiness.invalidate_readiness_receipt(
            receipt,
            workspace_binding_class=readiness.COMPANY_WORKSPACE_BINDING_CLASS,
            worker_gid=readiness.WORKER_GID,
        )
    assert receipt.exists()


def test_invalidate_cli_forwards_closed_receipt_policy_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = tmp_path / "receipt.json"
    captured: dict[str, object] = {}

    def _invalidate(path: Path, *, workspace_binding_class: str | None, worker_gid: int) -> None:
        captured.update(path=path, binding=workspace_binding_class, worker_gid=worker_gid)

    monkeypatch.setattr(readiness, "invalidate_readiness_receipt", _invalidate)
    rc = readiness.main(
        [
            "invalidate",
            "--receipt",
            str(receipt),
            "--workspace-binding-class",
            readiness.PERSONAL_PRO_WORKER_BINDING_CLASS,
            "--worker-gid",
            "454",
        ]
    )
    assert rc == 0
    assert captured == {
        "path": receipt,
        "binding": readiness.PERSONAL_PRO_WORKER_BINDING_CLASS,
        "worker_gid": 454,
    }


def test_shell_invalidation_delegates_without_literal_receipt_policy() -> None:
    script = Path("ops/executive_os/provision-worker-auth.sh").read_text(encoding="utf-8")
    block = script.split("invalidate_readiness_receipt() {", 1)[1].split("\n}\n\nprepare_explicit_replacement()", 1)[0]
    assert '[ -e "$READINESS_RECEIPT" ] || [ -L "$READINESS_RECEIPT" ]' in block
    assert 'provider_readiness.py" invalidate' in block
    assert '--receipt "$READINESS_RECEIPT"' in block
    assert '--workspace-binding-class "$WORKSPACE_BINDING_CLASS"' in block
    assert '--worker-gid "$WORKER_GID"' in block
    assert "0:0:400:1" not in block
    assert "stat -f" not in block
    assert "/bin/rm" not in block
