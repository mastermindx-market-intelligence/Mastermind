from __future__ import annotations

from pathlib import Path
import shlex
import subprocess

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
        (None, "company", 0o400),
    ],
)
def test_invalidate_uses_storage_contract_rechecks_then_unlinks_and_fsyncs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    binding: str | None,
    gid_kind: str,
    expected_mode: int,
) -> None:
    personal_gids = _personal_slot_gids()
    assert personal_gids
    worker_gid = personal_gids[0] if gid_kind == "personal" else readiness.WORKER_GID
    expected_gid = worker_gid if gid_kind == "personal" else 0
    receipt = _receipt(tmp_path)
    observed: dict[str, object] = {"identities": []}

    monkeypatch.setattr(
        readiness,
        "_validate_receipt_directory",
        lambda path: observed.setdefault("parent", path.parent),
    )

    def _lstat(
        path: Path,
        *,
        expected_uid: int,
        expected_gid: int,
        expected_mode: int,
        require_nonempty: bool = False,
    ) -> dict[str, int]:
        observed["identities"].append(
            (path, expected_uid, expected_gid, expected_mode, require_nonempty)
        )
        return {"device": 1, "inode": 2, "ctime_ns": 3}

    monkeypatch.setattr(readiness, "lstat_identity", _lstat)
    monkeypatch.setattr(
        readiness,
        "_fsync_directory",
        lambda path: observed.setdefault("fsync", path),
    )

    readiness.invalidate_receipt_file(
        receipt,
        workspace_binding_class=binding,
        worker_gid=worker_gid,
    )

    identity_call = (receipt, 0, expected_gid, expected_mode, False)
    assert observed["identities"] == [identity_call, identity_call]
    assert observed["parent"] == tmp_path
    assert observed["fsync"] == tmp_path
    assert not receipt.exists()


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
        readiness.invalidate_receipt_file(
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
        readiness.invalidate_receipt_file(
            receipt,
            workspace_binding_class=readiness.PERSONAL_PRO_WORKER_BINDING_CLASS,
            worker_gid=arbitrary_gid,
        )
    assert not called
    assert receipt.exists()


@pytest.mark.parametrize(
    ("binding", "expected_mode"),
    [
        (readiness.PERSONAL_PRO_WORKER_BINDING_CLASS, 0o440),
        (readiness.COMPANY_WORKSPACE_BINDING_CLASS, 0o400),
    ],
)
def test_invalidate_binding_specific_wrong_mode_refuses_without_unlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    binding: str,
    expected_mode: int,
) -> None:
    receipt = _receipt(tmp_path)
    worker_gid = _personal_slot_gids()[0] if binding == readiness.PERSONAL_PRO_WORKER_BINDING_CLASS else readiness.WORKER_GID
    monkeypatch.setattr(readiness, "_validate_receipt_directory", lambda path: None)

    def _lstat(path: Path, *, expected_uid: int, expected_gid: int, expected_mode: int, require_nonempty: bool = False):
        assert expected_mode == (0o440 if binding == readiness.PERSONAL_PRO_WORKER_BINDING_CLASS else 0o400)
        raise readiness.ReadinessError("identity_mode_mismatch")

    monkeypatch.setattr(readiness, "lstat_identity", _lstat)
    with pytest.raises(readiness.ReadinessError, match="identity_mode_mismatch"):
        readiness.invalidate_receipt_file(
            receipt,
            workspace_binding_class=binding,
            worker_gid=worker_gid,
        )
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
        readiness.invalidate_receipt_file(
            receipt,
            workspace_binding_class=readiness.COMPANY_WORKSPACE_BINDING_CLASS,
            worker_gid=readiness.WORKER_GID,
        )
    assert receipt.exists()


def test_invalidate_identity_change_before_unlink_refuses_and_preserves_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = _receipt(tmp_path)
    monkeypatch.setattr(readiness, "_validate_receipt_directory", lambda path: None)
    identities = iter(
        [
            {"device": 1, "inode": 2, "ctime_ns": 3},
            {"device": 1, "inode": 4, "ctime_ns": 5},
        ]
    )
    monkeypatch.setattr(readiness, "lstat_identity", lambda *args, **kwargs: next(identities))
    monkeypatch.setattr(readiness, "_fsync_directory", lambda path: pytest.fail("fsync must not run after refusal"))

    with pytest.raises(readiness.ReadinessError, match="readiness_receipt_changed_before_invalidation"):
        readiness.invalidate_receipt_file(
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
        readiness.invalidate_receipt_file(
            receipt,
            workspace_binding_class=readiness.COMPANY_WORKSPACE_BINDING_CLASS,
            worker_gid=readiness.WORKER_GID,
        )
    assert receipt.exists()


def test_invalidate_cli_forwards_explicit_personal_policy_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = tmp_path / "receipt.json"
    captured: dict[str, object] = {}

    def _invalidate(path: Path, *, workspace_binding_class: str | None, worker_gid: int) -> None:
        captured.update(path=path, binding=workspace_binding_class, worker_gid=worker_gid)

    monkeypatch.setattr(readiness, "invalidate_receipt_file", _invalidate)
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


def test_invalidate_cli_omits_binding_for_legacy_company_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = tmp_path / "receipt.json"
    captured: dict[str, object] = {}

    def _invalidate(path: Path, *, workspace_binding_class: str | None, worker_gid: int) -> None:
        captured.update(path=path, binding=workspace_binding_class, worker_gid=worker_gid)

    monkeypatch.setattr(readiness, "invalidate_receipt_file", _invalidate)
    rc = readiness.main(
        [
            "invalidate",
            "--receipt",
            str(receipt),
            "--worker-gid",
            str(readiness.WORKER_GID),
        ]
    )
    assert rc == 0
    assert captured == {
        "path": receipt,
        "binding": None,
        "worker_gid": readiness.WORKER_GID,
    }


def test_shell_invalidation_omits_empty_binding_and_has_no_literal_policy() -> None:
    script = Path("ops/executive_os/provision-worker-auth.sh").read_text(encoding="utf-8")
    block = script.split("invalidate_readiness_receipt() {", 1)[1].split("\n}\n\nprepare_explicit_replacement()", 1)[0]
    assert 'receipt_binding_args=()' in block
    assert 'if [ -n "$WORKSPACE_BINDING_CLASS" ]; then' in block
    assert 'receipt_binding_args=(--workspace-binding-class "$WORKSPACE_BINDING_CLASS")' in block
    assert '[ -e "$READINESS_RECEIPT" ] || [ -L "$READINESS_RECEIPT" ]' in block
    assert 'provider_readiness.py" invalidate' in block
    assert '--receipt "$READINESS_RECEIPT"' in block
    assert '--worker-gid "$WORKER_GID"' in block
    assert '${receipt_binding_args[@]+"${receipt_binding_args[@]}"}' in block
    assert "0:0:400:1" not in block
    assert "stat -f" not in block
    assert "/bin/rm" not in block



def _run_shell_invalidation_delegate(
    tmp_path: Path, *, workspace_binding_class: str, worker_gid: int
) -> list[str]:
    script = Path("ops/executive_os/provision-worker-auth.sh").read_text(encoding="utf-8")
    function = "invalidate_readiness_receipt() {" + script.split(
        "invalidate_readiness_receipt() {", 1
    )[1].split("\n}\n\nprepare_explicit_replacement()", 1)[0] + "\n}\n"
    receipt = tmp_path / "provider-readiness.json"
    receipt.write_text("{}\n", encoding="utf-8")
    argv_log = tmp_path / "argv.txt"
    python_stub = tmp_path / "python-stub.sh"
    python_stub.write_text(
        "#!/bin/bash\nprintf '%s\\n' \"$@\" > " + shlex.quote(str(argv_log)) + "\nexit 0\n",
        encoding="utf-8",
    )
    python_stub.chmod(0o755)
    harness = function + "\n" + "\n".join(
        [
            f"READINESS_RECEIPT={shlex.quote(str(receipt))}",
            f"WORKSPACE_BINDING_CLASS={shlex.quote(workspace_binding_class)}",
            f"WORKER_GID={worker_gid}",
            f"PYTHON_BINARY={shlex.quote(str(python_stub))}",
            f"SCRIPT_DIR={shlex.quote(str(tmp_path))}",
            "invalidate_readiness_receipt",
        ]
    ) + "\n"
    completed = subprocess.run(
        ["/bin/bash", "-c", harness], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
    return argv_log.read_text(encoding="utf-8").splitlines()


def test_shell_legacy_company_invalidation_omits_binding_argument(tmp_path: Path) -> None:
    argv = _run_shell_invalidation_delegate(
        tmp_path,
        workspace_binding_class="",
        worker_gid=readiness.WORKER_GID,
    )
    assert argv[:4] == ["-I", "-S", "-B", str(tmp_path / "provider_readiness.py")]
    assert argv[4:6] == ["invalidate", "--receipt"]
    assert "--workspace-binding-class" not in argv
    assert argv[-2:] == ["--worker-gid", str(readiness.WORKER_GID)]


def test_shell_personal_pro_invalidation_passes_explicit_class_and_gid(tmp_path: Path) -> None:
    personal_gid = _personal_slot_gids()[0]
    argv = _run_shell_invalidation_delegate(
        tmp_path,
        workspace_binding_class=readiness.PERSONAL_PRO_WORKER_BINDING_CLASS,
        worker_gid=personal_gid,
    )
    class_index = argv.index("--workspace-binding-class")
    assert argv[class_index + 1] == readiness.PERSONAL_PRO_WORKER_BINDING_CLASS
    gid_index = argv.index("--worker-gid")
    assert argv[gid_index + 1] == str(personal_gid)
