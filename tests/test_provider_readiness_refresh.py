"""Fail-closed refresh path tests for an EXPIRED provider-readiness receipt.

These tests cover the `reuse` exit-code-4 path and the `reserve --refresh-expired`
path that allow a historically passing device-auth receipt whose
``readiness_expires_at`` only fell past the current acceptance margin to be
re-bound to a fresh credential deadline, while every other receipt class
(reservation, adverse marker, tampered document, stale identity, non device-auth
credential kind) remains fail-closed.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ops.executive_os import provider_identity_policy as identity_policy


ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Module loader — mirrors tests/test_provider_identity_readiness.py
# ---------------------------------------------------------------------------


def _load(name: str, filename: str):
    path = ROOT / "ops" / "executive_os" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


readiness = _load("provider_readiness_refresh_test", "provider_readiness.py")
identity = _load("provider_identity_probe_refresh_test", "provider_identity_probe.py")

# Captures of the real implementations that the autouse fixture bypasses. Tests
# that need the genuine code paths (e.g. T11 exercising the storage-contract
# claim) re-bind these to the originals via monkeypatch.setattr.
ORIGINAL_READ_PROTECTED_RECEIPT = readiness._read_protected_receipt
ORIGINAL_LSTAT_IDENTITY = readiness.lstat_identity


# ---------------------------------------------------------------------------
# Reused fixtures (minimal copy from tests/test_provider_identity_readiness.py)
# ---------------------------------------------------------------------------


def _credential_expiry(hours: int = 12) -> str:
    return (
        datetime.now(UTC) + timedelta(hours=hours)
    ).isoformat(timespec="seconds").replace("+00:00", "Z")


def _auth_meta():
    return {
        "device": 1,
        "inode": 2,
        "uid": readiness.WORKER_UID,
        "gid": readiness.WORKER_GID,
        "mode": 0o600,
        "size": 123,
        "mtime_ns": 4,
        "ctime_ns": 5,
        "nlink": 1,
    }


def _binary_meta():
    return {
        **_auth_meta(),
        "uid": 0,
        "gid": 0,
        "mode": 0o555,
        "path": str(readiness.CODEX_BINARY),
        "version": readiness.CODEX_VERSION,
        "sha256": readiness.CODEX_SHA256,
        "team_identifier": readiness.CODEX_TEAM_ID,
    }


def _account(plan: str = "enterprise_cbp_automation", **extra):
    return {
        "account": {
            "type": "chatgpt",
            "planType": plan,
            "email": "must-never-persist@example.invalid",
            "accountId": "must-never-persist",
        },
        "requiresOpenaiAuth": True,
        **extra,
    }


def _canary(passed: bool = True):
    return {
        "schema_version": readiness.CANARY_SCHEMA,
        "canary_id": "canary-123456789abc",
        "observed_at": "2026-08-20T00:00:00Z",
        "codex_version": readiness.CODEX_VERSION,
        "codex_sha256": readiness.CODEX_SHA256,
        "codex_team_identifier": readiness.CODEX_TEAM_ID,
        "model": "gpt-5.6-sol",
        "exit_code": 0 if passed else 2,
        "timed_out": False,
        "terminal_event_class": "turn_completed" if passed else "invalid_workspace_selected",
        "result_valid": passed,
        "stdout_sha256": "a" * 64,
        "stderr_sha256": "b" * 64,
        "workspace_capability_outcome": "inert_untrusted_workspace",
        "workspace_selection_mechanism": "none",
        "forced_chatgpt_workspace_id_applied": False,
        "passed": passed,
        "refusal": None if passed else "invalid_workspace_selected",
    }


def _evaluate(*, mode="agentIdentity", plan="enterprise_cbp_automation", kind="service-account"):
    return identity.evaluate_identity(
        account_read=_account(plan),
        auth_mode=mode,
        expected_kind=kind,
        workspace_binding_class=identity.WORKSPACE_BINDING_CLASS,
    )


def _identity(kind: str = "service-account"):
    return {
        **_evaluate(kind=kind),
        "observed_at": "2026-08-20T00:00:00Z",
        "codex_binary": _binary_meta(),
        "credential_lstat": _auth_meta(),
        "forced_chatgpt_workspace_id_applied": False,
    }


def _personal_identity(uid: int = 454):
    return {
        **identity.evaluate_identity(
            account_read=_account("pro"),
            auth_mode="chatgpt",
            expected_kind="device-auth",
            workspace_binding_class=identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
        ),
        "observed_at": "2026-08-20T00:00:00Z",
        "codex_binary": _binary_meta(),
        "credential_lstat": {**_auth_meta(), "uid": uid, "gid": uid, "inode": 1000 + uid},
        "forced_chatgpt_workspace_id_applied": False,
    }


def _personal_auth_meta(uid: int = 454):
    return {**_auth_meta(), "uid": uid, "gid": uid, "inode": 1000 + uid}


def _build_receipt(
    *,
    expected_kind: str = "device-auth",
    workspace_binding_class: str = identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
    credential_lstat=None,
    binary_identity=None,
    identity_doc=None,
    expired: bool = False,
    worker_uid: int = 454,
    worker_gid: int = 454,
    extra_top_level: dict | None = None,
):
    cred_lstat = credential_lstat if credential_lstat is not None else _personal_auth_meta(worker_uid)
    binary = binary_identity if binary_identity is not None else _binary_meta()
    ident = identity_doc if identity_doc is not None else _personal_identity(worker_uid)
    receipt = readiness.compose_receipt(
        identity=ident,
        canary=_canary(),
        auth_identity=cred_lstat,
        binary_identity=binary,
        expected_kind=expected_kind,
        workspace_binding_class=workspace_binding_class,
        credential_expires_at=_credential_expiry(hours=12),
        worker_uid=worker_uid,
        worker_gid=worker_gid,
    )
    if expired:
        # observed must be in the past; readiness_expiry must be between observed
        # and max(observed+MAX_READINESS_AGE, credential_expiry) so the only
        # check that fires is the MIN_ACCEPTANCE_MARGIN one (the spec's
        # readiness_expired_or_insufficient_margin refusal).
        past_observed = (datetime.now(UTC) - timedelta(hours=1)).isoformat(timespec="seconds").replace("+00:00", "Z")
        future_credential = (datetime.now(UTC) + timedelta(hours=12)).isoformat(timespec="seconds").replace("+00:00", "Z")
        past_readiness = (datetime.now(UTC) - timedelta(minutes=5)).isoformat(timespec="seconds").replace("+00:00", "Z")
        receipt["observed_at"] = past_observed
        receipt["credential_expires_at"] = future_credential
        receipt["readiness_expires_at"] = past_readiness
        receipt["provider_identity"]["observed_at"] = past_observed
        receipt["inference_canary"]["observed_at"] = past_observed
    if extra_top_level:
        receipt.update(extra_top_level)
    return receipt


# ---------------------------------------------------------------------------
# Filesystem + CLI helpers
# ---------------------------------------------------------------------------


def _write_receipt(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _write_auth(path: Path, identity: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(identity or _auth_meta(), sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _write_personal_auth(path: Path, uid: int = 454) -> None:
    _write_auth(path, _personal_auth_meta(uid))


def _personal_pro_args(prefix: list[str], receipt_path: Path, auth_path: Path, identity_json: Path, credential_expires_at: str) -> list[str]:
    return [
        *prefix,
        "--receipt", str(receipt_path),
        "--auth", str(auth_path),
        "--binary", str(readiness.CODEX_BINARY),
        "--identity-json", str(identity_json),
        "--expected-kind", "device-auth",
        "--workspace-binding-class", identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
        "--credential-expires-at", credential_expires_at,
        "--worker-uid", "454",
        "--worker-gid", "454",
    ]


def _personal_pro_reuse_args(receipt_path: Path, auth_path: Path, credential_expires_at: str) -> list[str]:
    return [
        "reuse",
        "--receipt", str(receipt_path),
        "--auth", str(auth_path),
        "--binary", str(readiness.CODEX_BINARY),
        "--expected-kind", "device-auth",
        "--workspace-binding-class", identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
        "--credential-expires-at", credential_expires_at,
        "--worker-uid", "454",
        "--worker-gid", "454",
    ]


def _run_cli(argv: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[int, str, str]:
    """Invoke provider_readiness.main(argv) as a CLI call.

    Patches the storage contract / fsync helpers / fchown so a non-root tmp
    file passes the receipt directory / mode checks.
    """

    monkeypatch.setattr(readiness, "_validate_receipt_directory", lambda _path: None)
    monkeypatch.setattr(readiness, "_assert_no_macos_acl", lambda _path: None)
    monkeypatch.setattr(readiness, "_fsync_directory", lambda _path: None)

    captured_stderr = io.StringIO()
    captured_stdout = io.StringIO()
    rc = 99
    # argparse calls sys.argv when argv is None.  We pass our argv list directly.
    # The CLI exits via SystemExit, not return; we catch below.
    try:
        with redirect_stdout(captured_stdout), redirect_stderr(captured_stderr):
            rc = readiness.main(argv)
    except SystemExit as exc:  # argparse --help exits via SystemExit; not expected in normal CLI
        rc = int(exc.code) if exc.code is not None else 0
    return rc, captured_stdout.getvalue(), captured_stderr.getvalue()


@pytest.fixture(autouse=True)
def _patch_filesystem_guards(monkeypatch: pytest.MonkeyPatch):
    """Disable root-only filesystem guards so non-root tmp files pass."""
    monkeypatch.setattr(readiness, "_validate_receipt_directory", lambda _path: None)
    monkeypatch.setattr(readiness, "_assert_no_macos_acl", lambda _path: None)
    monkeypatch.setattr(readiness, "_fsync_directory", lambda _path: None)
    monkeypatch.setattr(readiness.os, "fchown", lambda _fd, _uid, _gid: None)

    def _read_receipt_bypass(path, *, workspace_binding_class=None, worker_gid=readiness.WORKER_GID):
        return json.loads(path.read_text(encoding="utf-8"))

    def _auth_identity_bypass(path, *, worker_uid=readiness.WORKER_UID, worker_gid=readiness.WORKER_GID):
        # Honor the inode/mtime/ctime the test wrote to the auth.json file
        # (if present); otherwise synthesize a fresh lstat identity.
        try:
            on_disk = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            on_disk = {}
        return {
            "device": int(on_disk.get("device", 1)),
            "inode": int(on_disk.get("inode", 2)),
            "uid": int(on_disk.get("uid", worker_uid)),
            "gid": int(on_disk.get("gid", worker_gid)),
            "mode": int(on_disk.get("mode", 0o600)),
            "size": int(on_disk.get("size", 123)),
            "mtime_ns": int(on_disk.get("mtime_ns", 4)),
            "ctime_ns": int(on_disk.get("ctime_ns", 5)),
            "nlink": int(on_disk.get("nlink", 1)),
        }

    def _binary_identity_bypass(path):
        return _binary_meta()

    monkeypatch.setattr(readiness, "_read_protected_receipt", _read_receipt_bypass)
    monkeypatch.setattr(readiness, "current_auth_identity", _auth_identity_bypass)
    monkeypatch.setattr(readiness, "current_binary_identity", _binary_identity_bypass)
    yield


# ---------------------------------------------------------------------------
# T1 — discriminating regression: expired PASSING device-auth receipt -> reuse 4
# ---------------------------------------------------------------------------


def test_t1_expired_device_auth_receipt_reuse_exits_4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Expired passing device-auth receipt (identity unchanged) -> reuse exits 4.

    On the untouched base this must FAIL with exit 2; after the refresh patch
    lands it must exit 4 (refresh-eligible).
    """
    receipt = _build_receipt(expired=True)
    receipt_path = tmp_path / "readiness.json"
    _write_receipt(receipt_path, receipt)

    auth_path = tmp_path / "auth.json"
    _write_personal_auth(auth_path, 454)

    rc, _, stderr = _run_cli(
        _personal_pro_reuse_args(receipt_path, auth_path, _credential_expiry(hours=12)),
        monkeypatch,
        tmp_path,
    )
    assert rc == 4, (
        "expired passing device-auth receipt must be classified as refresh-eligible "
        "(reuse exit 4); got rc=%d stderr=%r" % (rc, stderr)
    )


# ---------------------------------------------------------------------------
# Helpers for receipt storage contract patching on persisted files
# ---------------------------------------------------------------------------


def _write_with_storage(path: Path, payload: dict) -> None:
    """Write a receipt file at a path the storage contract will accept.

    The patched `receipt_storage_contract` returns (0, 0, 0o400); we must
    chmod the file to match before the storage-contract check runs.  We then
    call fchown(fileno, 0, 0) on the descriptor — but tests run as a
    non-root user, so fchown would fail.  The autouse fixture already
    monkeypatches fchown to a no-op.  We just open the file in write mode
    with O_EXCL so the file is created with mode 0o644, then chmod 0o400.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o400)
    try:
        os.write(fd, (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(path, 0o400)


@pytest.fixture
def storage_contract_zero(monkeypatch: pytest.MonkeyPatch):
    """Patch `receipt_storage_contract` so non-root tmp files satisfy it.

    Also bypasses `lstat_identity`'s uid/gid/mode/ACL checks (a non-root test
    runner cannot chown a tmp file to uid=0).  The lstat info is still
    returned verbatim so atomic-replace identity comparisons keep working.
    """

    def _contract(*, workspace_binding_class=None, worker_gid=readiness.WORKER_GID):
        return 0, 0, 0o400

    real_lstat = readiness.lstat_identity

    def _lstat_bypass(
        path,
        *,
        expected_uid=None,
        expected_gid=None,
        expected_mode=None,
        require_nonempty=False,
    ):
        info = Path(path).lstat()
        mode = stat.S_IMODE(info.st_mode)
        if require_nonempty and info.st_size <= 0:
            raise readiness.ReadinessError("identity_empty")
        return {
            "device": int(info.st_dev),
            "inode": int(info.st_ino),
            "uid": int(info.st_uid),
            "gid": int(info.st_gid),
            "mode": mode,
            "size": int(info.st_size),
            "mtime_ns": int(info.st_mtime_ns),
            "ctime_ns": int(info.st_ctime_ns),
            "nlink": int(info.st_nlink),
        }

    monkeypatch.setattr(readiness, "receipt_storage_contract", _contract)
    monkeypatch.setattr(readiness, "lstat_identity", _lstat_bypass)
    yield
    # Restore for downstream tests (monkeypatch fixture handles teardown but
    # explicit restore keeps intent obvious if more fixtures compose later).
    _ = real_lstat


# ---------------------------------------------------------------------------
# T2 — reserve --refresh-expired: live reservation written, sibling persisted
# ---------------------------------------------------------------------------


def test_t2_refresh_expired_creates_new_reservation_and_supersedes_sibling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    storage_contract_zero,
) -> None:
    receipt = _build_receipt(expired=True)
    receipt_path = tmp_path / "readiness.json"
    _write_with_storage(receipt_path, receipt)

    new_deadline = _credential_expiry(hours=12)
    identity_payload = _personal_identity(454)
    identity_json = tmp_path / "identity.json"
    identity_json.write_text(json.dumps(identity_payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    auth_path = tmp_path / "auth.json"
    _write_personal_auth(auth_path, 454)

    rc, _, stderr = _run_cli(
        [
            "reserve", "--refresh-expired",
            "--receipt", str(receipt_path),
            "--auth", str(auth_path),
            "--binary", str(readiness.CODEX_BINARY),
            "--identity-json", str(identity_json),
            "--expected-kind", "device-auth",
            "--workspace-binding-class", identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
            "--credential-expires-at", new_deadline,
            "--worker-uid", "454",
            "--worker-gid", "454",
        ],
        monkeypatch,
        tmp_path,
    )
    assert rc == 0, "refresh-expired reserve must succeed; got rc=%d stderr=%r" % (rc, stderr)

    live = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert live["refusal"] == "canary_reserved"
    assert live["expected_credential_kind"] == "device-auth"
    assert live["passed"] is False
    new_deadline_dt = datetime.strptime(new_deadline, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    observed_dt = datetime.strptime(live["observed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    readiness_expiry_dt = datetime.strptime(live["readiness_expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    assert readiness_expiry_dt <= new_deadline_dt
    assert readiness_expiry_dt <= observed_dt + readiness.MAX_READINESS_AGE

    siblings = [p for p in tmp_path.iterdir() if p.name.startswith("readiness.json.superseded-")]
    assert len(siblings) == 1
    sibling_bytes = siblings[0].read_bytes()
    original_bytes = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode("utf-8")
    assert sibling_bytes == original_bytes
    # NB7: the superseded sibling must be persisted under the storage contract,
    # i.e. root-owned mode 0o400 (the contract returned by storage_contract_zero).
    assert stat.S_IMODE((tmp_path / siblings[0]).stat().st_mode) == 0o400, (
        "superseded sibling must be persisted at the storage-contract mode 0o400"
    )


# ---------------------------------------------------------------------------
# T3 — service-account / personal-access-token refresh must require rotation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["service-account", "personal-access-token"])
def test_t3_non_device_auth_expired_receipt_refresh_requires_credential_rotation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    storage_contract_zero,
    kind: str,
) -> None:
    # Build a passing-but-expired receipt with the requested non-device-auth
    # kind.  For service-account the COMPANY + enterprise plan passes; for
    # personal-access-token we hand-craft the receipt so we don't depend on
    # the identity-policy edge case binding PAT to PERSONAL_PRO.
    if kind == "service-account":
        receipt = _build_receipt(
            expected_kind="service-account",
            workspace_binding_class=identity_policy.COMPANY_WORKSPACE_BINDING_CLASS,
            worker_uid=readiness.WORKER_UID,
            worker_gid=readiness.WORKER_GID,
            credential_lstat=_auth_meta(),
            binary_identity=_binary_meta(),
            identity_doc=_identity(kind="service-account"),
            expired=True,
        )
        binding = identity_policy.COMPANY_WORKSPACE_BINDING_CLASS
    else:
        # Hand-craft a passing personal-access-token receipt against the
        # COMPANY workspace binding class (no live identity policy is
        # exercised; only the receipt document's top-level fields are
        # checked by classify_refresh_eligibility).
        receipt = _build_receipt(
            expected_kind="service-account",
            workspace_binding_class=identity_policy.COMPANY_WORKSPACE_BINDING_CLASS,
            worker_uid=readiness.WORKER_UID,
            worker_gid=readiness.WORKER_GID,
            credential_lstat=_auth_meta(),
            binary_identity=_binary_meta(),
            identity_doc=_identity(kind="service-account"),
            expired=True,
        )
        receipt["expected_credential_kind"] = "personal-access-token"
        binding = identity_policy.COMPANY_WORKSPACE_BINDING_CLASS

    receipt_path = tmp_path / "readiness.json"
    _write_with_storage(receipt_path, receipt)
    auth_path = tmp_path / "auth.json"
    _write_auth(auth_path, _auth_meta())

    rc, _, stderr = _run_cli(
        [
            "reuse",
            "--receipt", str(receipt_path),
            "--auth", str(auth_path),
            "--binary", str(readiness.CODEX_BINARY),
            "--expected-kind", kind,
            "--workspace-binding-class", binding,
            "--credential-expires-at", _credential_expiry(hours=12),
            "--worker-uid", str(readiness.WORKER_UID),
            "--worker-gid", str(readiness.WORKER_GID),
        ],
        monkeypatch,
        tmp_path,
    )
    assert rc == 2, "%s expired receipt reuse must be refused (2), got %d" % (kind, rc)

    identity_json = tmp_path / "identity.json"
    identity_json.write_text(json.dumps(_identity(kind="service-account"), sort_keys=True, indent=2) + "\n", encoding="utf-8")

    rc2, _, stderr2 = _run_cli(
        [
            "reserve", "--refresh-expired",
            "--receipt", str(receipt_path),
            "--auth", str(auth_path),
            "--binary", str(readiness.CODEX_BINARY),
            "--identity-json", str(identity_json),
            "--expected-kind", kind,
            "--workspace-binding-class", binding,
            "--credential-expires-at", _credential_expiry(hours=12),
            "--worker-uid", str(readiness.WORKER_UID),
            "--worker-gid", str(readiness.WORKER_GID),
        ],
        monkeypatch,
        tmp_path,
    )
    assert rc2 == 2, "%s reserve --refresh-expired must be refused (2), got %d" % (kind, rc2)
    # The CLI must refuse; either because classify_refresh_eligibility raises
    # refresh_requires_credential_rotation (the spec) or because the
    # subsequent compose_reservation refuses with a credential-kind refusal
    # — both are fail-closed outcomes.
    assert "refresh_requires_credential_rotation" in stderr2 or "credential_kind_mismatch" in stderr2 or "credential_kind_unknown" in stderr2, (
        "stderr must mention a credential-kind refusal; got %r" % stderr2
    )


# ---------------------------------------------------------------------------
# T4 — refresh refused when auth identity OR binary identity changed
# ---------------------------------------------------------------------------


def test_t4a_refresh_refused_when_auth_identity_changed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    storage_contract_zero,
) -> None:
    # The receipt was composed with uid/gid 454; lstat now returns uid=455.
    receipt = _build_receipt(expired=True)
    receipt_path = tmp_path / "readiness.json"
    _write_with_storage(receipt_path, receipt)
    auth_path = tmp_path / "auth.json"
    _write_personal_auth(auth_path, 454)

    def _auth_bypass_stale_uid(path, *, worker_uid=readiness.WORKER_UID, worker_gid=readiness.WORKER_GID):
        return {**_auth_meta(), "uid": 455, "gid": 455, "inode": 9999}

    monkeypatch.setattr(readiness, "current_auth_identity", _auth_bypass_stale_uid)

    rc, _, stderr = _run_cli(
        _personal_pro_reuse_args(receipt_path, auth_path, _credential_expiry(hours=12)),
        monkeypatch,
        tmp_path,
    )
    assert rc == 2, "stale auth identity reuse must be refused (2), got %d" % rc


def test_t4b_refresh_refused_when_binary_identity_changed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    storage_contract_zero,
) -> None:
    receipt = _build_receipt(expired=True)
    receipt_path = tmp_path / "readiness.json"
    _write_with_storage(receipt_path, receipt)
    auth_path = tmp_path / "auth.json"
    _write_personal_auth(auth_path, 454)

    def _binary_bypass_stale(path):
        return {**_binary_meta(), "sha256": "f" * 64}

    monkeypatch.setattr(readiness, "current_binary_identity", _binary_bypass_stale)

    rc, _, stderr = _run_cli(
        _personal_pro_reuse_args(receipt_path, auth_path, _credential_expiry(hours=12)),
        monkeypatch,
        tmp_path,
    )
    assert rc == 2, "stale binary identity reuse must be refused (2), got %d" % rc


# ---------------------------------------------------------------------------
# T5 — tampered / adverse / reservation must NOT be refresh-eligible
# ---------------------------------------------------------------------------


def test_t5a_tampered_receipt_extra_field_is_not_refresh_eligible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    storage_contract_zero,
) -> None:
    receipt = _build_receipt(expired=True, extra_top_level={"smuggled": True})
    receipt_path = tmp_path / "readiness.json"
    _write_with_storage(receipt_path, receipt)
    auth_path = tmp_path / "auth.json"
    _write_personal_auth(auth_path, 454)

    rc, _, _ = _run_cli(
        _personal_pro_reuse_args(receipt_path, auth_path, _credential_expiry(hours=12)),
        monkeypatch,
        tmp_path,
    )
    assert rc == 2, "tampered receipt must refuse (2), got %d" % rc


def test_t5b_passed_flipped_adverse_marker_is_not_refresh_eligible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    storage_contract_zero,
) -> None:
    receipt = _build_receipt(expired=True)
    receipt["passed"] = False
    receipt["refusal"] = "canary_receipt_malformed"
    receipt_path = tmp_path / "readiness.json"
    _write_with_storage(receipt_path, receipt)
    auth_path = tmp_path / "auth.json"
    _write_personal_auth(auth_path, 454)

    rc, _, _ = _run_cli(
        _personal_pro_reuse_args(receipt_path, auth_path, _credential_expiry(hours=12)),
        monkeypatch,
        tmp_path,
    )
    assert rc == 2, "adverse marker must refuse (2), got %d" % rc


def test_t5c_existing_canary_reservation_is_not_refreshed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    storage_contract_zero,
) -> None:
    reservation = readiness.compose_reservation(
        identity=_personal_identity(454),
        auth_identity=_personal_auth_meta(454),
        binary_identity=_binary_meta(),
        expected_kind="device-auth",
        workspace_binding_class=identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
        credential_expires_at=_credential_expiry(hours=12),
        worker_uid=454,
        worker_gid=454,
    )
    # Make the reservation "expired" so the timeline matches.
    past_observed = (datetime.now(UTC) - timedelta(hours=1)).isoformat(timespec="seconds").replace("+00:00", "Z")
    future_credential = (datetime.now(UTC) + timedelta(hours=12)).isoformat(timespec="seconds").replace("+00:00", "Z")
    past_readiness = (datetime.now(UTC) - timedelta(minutes=5)).isoformat(timespec="seconds").replace("+00:00", "Z")
    reservation["observed_at"] = past_observed
    reservation["credential_expires_at"] = future_credential
    reservation["readiness_expires_at"] = past_readiness
    reservation["provider_identity"]["observed_at"] = past_observed
    reservation_path = tmp_path / "readiness.json"
    _write_with_storage(reservation_path, reservation)
    auth_path = tmp_path / "auth.json"
    _write_personal_auth(auth_path, 454)

    rc, _, _ = _run_cli(
        _personal_pro_reuse_args(reservation_path, auth_path, _credential_expiry(hours=12)),
        monkeypatch,
        tmp_path,
    )
    assert rc == 2, "reservation receipt must refuse reuse (2), got %d" % rc


def test_t5d_symlink_receipt_is_not_refresh_eligible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # T5's spec mentions "a symlink receipt" must NOT be eligible.
    target = tmp_path / "real.json"
    target.write_text("{}", encoding="utf-8")
    symlink = tmp_path / "readiness.json"
    try:
        os.symlink(target, symlink)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this filesystem")
    auth_path = tmp_path / "auth.json"
    _write_personal_auth(auth_path, 454)

    rc, _, _ = _run_cli(
        _personal_pro_reuse_args(symlink, auth_path, _credential_expiry(hours=12)),
        monkeypatch,
        tmp_path,
    )
    # Symlink path: validate_receipt_file's lstat refuses with
    # readiness_receipt_metadata_unsafe; reuse should return 2, not 4.
    assert rc == 2, "symlink receipt must refuse (2), got %d" % rc


# ---------------------------------------------------------------------------
# T6 — reserve WITHOUT --refresh-expired still fails on existing receipt
# ---------------------------------------------------------------------------


def test_t6_reserve_without_refresh_expired_still_refuses_existing_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    storage_contract_zero,
) -> None:
    receipt = _build_receipt(expired=True)
    receipt_path = tmp_path / "readiness.json"
    _write_with_storage(receipt_path, receipt)
    identity_json = tmp_path / "identity.json"
    identity_json.write_text(json.dumps(_personal_identity(454), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    auth_path = tmp_path / "auth.json"
    _write_personal_auth(auth_path, 454)

    pre_bytes = receipt_path.read_bytes()

    # Spy: confirm the call actually reaches `persist_receipt` (the O_EXCL
    # check is the thing under test, not an earlier worker_identity_mismatch).
    persist_calls: list[tuple] = []
    real_persist = readiness.persist_receipt

    def _persist_spy(*args, **kwargs):
        persist_calls.append((args, kwargs))
        return real_persist(*args, **kwargs)

    monkeypatch.setattr(readiness, "persist_receipt", _persist_spy)

    rc, _, _ = _run_cli(
        [
            "reserve",
            "--receipt", str(receipt_path),
            "--auth", str(auth_path),
            "--binary", str(readiness.CODEX_BINARY),
            "--identity-json", str(identity_json),
            "--expected-kind", "device-auth",
            "--workspace-binding-class", identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
            "--credential-expires-at", _credential_expiry(hours=12),
            "--worker-uid", "454",
            "--worker-gid", "454",
        ],
        monkeypatch,
        tmp_path,
    )
    assert rc == 2, "reserve without --refresh-expired on existing receipt must refuse (2), got %d" % rc
    assert receipt_path.read_bytes() == pre_bytes, "live receipt must be untouched after refused reserve"
    assert persist_calls, "persist_receipt must be reached (so O_EXCL is what fires)"


# ---------------------------------------------------------------------------
# T7 — idempotency: a second refresh after success finds a reservation, refuses
# ---------------------------------------------------------------------------


def test_t7_refresh_expired_idempotent_second_run_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    storage_contract_zero,
) -> None:
    receipt = _build_receipt(expired=True)
    receipt_path = tmp_path / "readiness.json"
    _write_with_storage(receipt_path, receipt)
    identity_json = tmp_path / "identity.json"
    identity_json.write_text(json.dumps(_personal_identity(454), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    auth_path = tmp_path / "auth.json"
    _write_personal_auth(auth_path, 454)

    new_deadline = _credential_expiry(hours=12)
    args = [
        "reserve", "--refresh-expired",
        "--receipt", str(receipt_path),
        "--auth", str(auth_path),
        "--binary", str(readiness.CODEX_BINARY),
        "--identity-json", str(identity_json),
        "--expected-kind", "device-auth",
        "--workspace-binding-class", identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
        "--credential-expires-at", new_deadline,
        "--worker-uid", "454",
        "--worker-gid", "454",
    ]
    rc1, _, _ = _run_cli(args, monkeypatch, tmp_path)
    assert rc1 == 0, "first refresh must succeed; got %d" % rc1

    siblings_before = sorted(p.name for p in tmp_path.iterdir() if p.name.startswith("readiness.json.superseded-"))
    assert len(siblings_before) == 1
    sibling_before_bytes = (tmp_path / siblings_before[0]).read_bytes()

    rc2, _, _ = _run_cli(args, monkeypatch, tmp_path)
    assert rc2 == 2, "second refresh must refuse (2); got %d" % rc2

    siblings_after = sorted(p.name for p in tmp_path.iterdir() if p.name.startswith("readiness.json.superseded-"))
    assert siblings_after == siblings_before, "superseded sibling set must be unchanged"
    assert (tmp_path / siblings_before[0]).read_bytes() == sibling_before_bytes


# ---------------------------------------------------------------------------
# T8 — superseded sibling pre-existing with DIFFERENT bytes => conflict
# ---------------------------------------------------------------------------


def test_t8_superseded_sibling_with_different_bytes_conflicts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    storage_contract_zero,
) -> None:
    receipt = _build_receipt(expired=True)
    receipt_path = tmp_path / "readiness.json"
    _write_with_storage(receipt_path, receipt)

    # Pre-stage a sibling with DIFFERENT bytes.
    receipt_bytes = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode("utf-8")
    digest = __import__("hashlib").sha256(receipt_bytes).hexdigest()[:16]
    sibling_name = f"readiness.json.superseded-{digest}.json"
    sibling_path = tmp_path / sibling_name
    sibling_path.write_bytes(b"{" + b"  " + b'"unrelated": true' + b" }" + b"\n")
    # Make sure storage contract check would accept it.
    os.chmod(sibling_path, 0o400)

    identity_json = tmp_path / "identity.json"
    identity_json.write_text(json.dumps(_personal_identity(454), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    auth_path = tmp_path / "auth.json"
    _write_personal_auth(auth_path, 454)

    pre_bytes = receipt_path.read_bytes()

    rc, _, stderr = _run_cli(
        [
            "reserve", "--refresh-expired",
            "--receipt", str(receipt_path),
            "--auth", str(auth_path),
            "--binary", str(readiness.CODEX_BINARY),
            "--identity-json", str(identity_json),
            "--expected-kind", "device-auth",
            "--workspace-binding-class", identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
            "--credential-expires-at", _credential_expiry(hours=12),
            "--worker-uid", "454",
            "--worker-gid", "454",
        ],
        monkeypatch,
        tmp_path,
    )
    assert rc == 2, "superseded sibling conflict must refuse (2); got %d" % rc
    assert "superseded_receipt_conflict" in stderr, "stderr must mention superseded_receipt_conflict; got %r" % stderr
    assert receipt_path.read_bytes() == pre_bytes, "live receipt must be untouched after sibling conflict"


# ---------------------------------------------------------------------------
# T9 (supplement) — provision-worker-auth.sh accepts reuse status 4
# ---------------------------------------------------------------------------


def test_t9_provision_worker_auth_accepts_reuse_status_four_for_refresh() -> None:
    script = (ROOT / "ops" / "executive_os" / "provision-worker-auth.sh").read_text(encoding="utf-8")

    # Find the VERIFY_READY block — the one that calls `reuse` and gates on
    # reuse_status.  Look for the line that handles the missing-receipt case
    # (status 3) and ensure it now ALSO accepts status 4.
    verify_ready_marker = 'VERIFY_READY" = "true" ]'
    assert verify_ready_marker in script, "VERIFY_READY branch missing from script"
    verify_block = script.split('VERIFY_READY" = "true" ]', 1)[1]
    # The block is small; the next `fi` ends the gate.  Look for the pattern.
    assert 'reuse_status' in verify_block
    # The condition that gates continue-on-absent must now accept 4 too.
    assert '[ "$reuse_status" -eq 3 ] || [ "$reuse_status" -eq 4 ]' in verify_block or \
           '[ "$reuse_status" -eq 4 ] || [ "$reuse_status" -eq 3 ]' in verify_block, (
        "VERIFY_READY gate must accept reuse_status 4 in addition to 3"
    )
    # And only the 4 branch must pass --refresh-expired to `reserve`, now via
    # an array (refresh_args=()) so the unset case under `set -u` in bash 3.2
    # does not error.
    assert 'refresh_args=()' in verify_block, (
        "VERIFY_READY block must initialize refresh_args as an array"
    )
    assert '[ "$reuse_status" -eq 4 ]' in verify_block and \
           'refresh_args=(--refresh-expired)' in verify_block, (
        "VERIFY_READY block must gate refresh_args on reuse_status == 4"
    )
    # The bash-3.2-safe expansion (empty array must not error under set -u).
    assert '${refresh_args[@]+"${refresh_args[@]}"}' in verify_block, (
        "VERIFY_READY block must expand refresh_args in a bash-3.2-safe form"
    )
    assert 'refresh_flag=' not in verify_block, (
        "VERIFY_READY block must not retain the legacy refresh_flag string"
    )
    # And every existing exit-65 message must remain untouched.
    assert "existing provider readiness receipt is stale or invalid; fail closed" in script
    assert "provider canary reservation failed; no canary spent" in script
    assert "provider readiness failed closed after one inference canary" in script


# ---------------------------------------------------------------------------
# T10a — receipt credential_expires_at in the past blocks refresh
# ---------------------------------------------------------------------------


def test_t10a_credential_expires_at_in_past_blocks_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    storage_contract_zero,
) -> None:
    """The receipt's own credential deadline must still be valid at refresh time.

    Only the readiness deadline may be expired; the credential deadline is
    locally non-extendable.  With credential_expires_at in the past (and
    readiness also past), both `reuse` and `reserve --refresh-expired` must
    refuse with rc 2 and leave the live receipt untouched.
    """
    receipt = _build_receipt()  # build a passing receipt first
    # Force observed, credential, and readiness all into the past so step (a)
    # of classify_refresh_eligibility still passes (observed < credential,
    # readiness within bounds) but the new B1(i) refusal fires on
    # credential_expires_at <= now + MIN_ACCEPTANCE_MARGIN.
    past_observed = (datetime.now(UTC) - timedelta(hours=2)).isoformat(timespec="seconds").replace("+00:00", "Z")
    past_credential = (datetime.now(UTC) - timedelta(hours=1)).isoformat(timespec="seconds").replace("+00:00", "Z")
    past_readiness = (datetime.now(UTC) - timedelta(hours=2) + timedelta(seconds=10)).isoformat(timespec="seconds").replace("+00:00", "Z")
    receipt["observed_at"] = past_observed
    receipt["provider_identity"]["observed_at"] = past_observed
    receipt["inference_canary"]["observed_at"] = past_observed
    receipt["credential_expires_at"] = past_credential
    receipt["readiness_expires_at"] = past_readiness

    receipt_path = tmp_path / "readiness.json"
    _write_with_storage(receipt_path, receipt)
    auth_path = tmp_path / "auth.json"
    _write_personal_auth(auth_path, 454)

    pre_bytes = receipt_path.read_bytes()

    rc, _, _ = _run_cli(
        _personal_pro_reuse_args(receipt_path, auth_path, receipt["credential_expires_at"]),
        monkeypatch,
        tmp_path,
    )
    assert rc == 2, "receipt with credential_expires_at in the past must refuse reuse (2); got %d" % rc

    identity_json = tmp_path / "identity.json"
    identity_json.write_text(json.dumps(_personal_identity(454), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    rc2, _, _ = _run_cli(
        [
            "reserve", "--refresh-expired",
            "--receipt", str(receipt_path),
            "--auth", str(auth_path),
            "--binary", str(readiness.CODEX_BINARY),
            "--identity-json", str(identity_json),
            "--expected-kind", "device-auth",
            "--workspace-binding-class", identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
            "--credential-expires-at", receipt["credential_expires_at"],
            "--worker-uid", "454",
            "--worker-gid", "454",
        ],
        monkeypatch,
        tmp_path,
    )
    assert rc2 == 2, "receipt with credential_expires_at in the past must refuse refresh (2); got %d" % rc2
    assert receipt_path.read_bytes() == pre_bytes, "live receipt must be untouched after refused refresh"


# ---------------------------------------------------------------------------
# T10b — CLI --credential-expires-at LATER than receipt blocks refresh
# ---------------------------------------------------------------------------


def test_t10b_new_credential_later_than_receipt_blocks_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    storage_contract_zero,
) -> None:
    """Same auth identity cannot extend its own credential window.

    With receipt credential valid but CLI --credential-expires-at LATER than
    the receipt's, both `reuse` and `reserve --refresh-expired` must refuse
    with rc 2.  EQUAL or EARIER must remain eligible (rc 4 / rc 0).
    """
    receipt = _build_receipt(expired=True)
    receipt_path = tmp_path / "readiness.json"
    _write_with_storage(receipt_path, receipt)
    auth_path = tmp_path / "auth.json"
    _write_personal_auth(auth_path, 454)
    identity_json = tmp_path / "identity.json"
    identity_json.write_text(json.dumps(_personal_identity(454), sort_keys=True, indent=2) + "\n", encoding="utf-8")

    receipt_credential = receipt["credential_expires_at"]
    receipt_credential_dt = datetime.strptime(receipt_credential, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    later_credential = (receipt_credential_dt + timedelta(hours=1)).isoformat(timespec="seconds").replace("+00:00", "Z")
    earlier_credential = (receipt_credential_dt - timedelta(hours=1)).isoformat(timespec="seconds").replace("+00:00", "Z")

    # CLI LATER than receipt -> rc 2 for reuse and refresh
    rc, _, _ = _run_cli(
        _personal_pro_reuse_args(receipt_path, auth_path, later_credential),
        monkeypatch,
        tmp_path,
    )
    assert rc == 2, "CLI --credential-expires-at LATER than receipt must refuse reuse (2); got %d" % rc

    rc, _, _ = _run_cli(
        [
            "reserve", "--refresh-expired",
            "--receipt", str(receipt_path),
            "--auth", str(auth_path),
            "--binary", str(readiness.CODEX_BINARY),
            "--identity-json", str(identity_json),
            "--expected-kind", "device-auth",
            "--workspace-binding-class", identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
            "--credential-expires-at", later_credential,
            "--worker-uid", "454",
            "--worker-gid", "454",
        ],
        monkeypatch,
        tmp_path,
    )
    assert rc == 2, "CLI --credential-expires-at LATER than receipt must refuse refresh (2); got %d" % rc

    # CLI EQUAL to receipt -> reuse rc 4 (still eligible)
    rc, _, _ = _run_cli(
        _personal_pro_reuse_args(receipt_path, auth_path, receipt_credential),
        monkeypatch,
        tmp_path,
    )
    assert rc == 4, "CLI --credential-expires-at EQUAL to receipt must remain eligible (4); got %d" % rc

    # CLI EARLIER than receipt -> reuse rc 4 (still eligible; cannot extend)
    rc, _, _ = _run_cli(
        _personal_pro_reuse_args(receipt_path, auth_path, earlier_credential),
        monkeypatch,
        tmp_path,
    )
    assert rc == 4, "CLI --credential-expires-at EARLIER than receipt must remain eligible (4); got %d" % rc


# ---------------------------------------------------------------------------
# T11 — real protected read refuses symlink and wrong-mode
# ---------------------------------------------------------------------------


def test_t11_real_protected_read_refuses_symlink_and_wrong_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The storage-contract claim must be exercised through the real read.

    We patch ONLY `receipt_storage_contract` (returning the test runner's
    identity and mode 0o400) and `os.fchown` (no-op); the real
    `_read_protected_receipt` and real `lstat_identity` must run so the
    symlink / wrong-mode refusal is what gates the receipt.
    """
    monkeypatch.setattr(
        readiness, "receipt_storage_contract",
        lambda *, workspace_binding_class=None, worker_gid=readiness.WORKER_GID:
        (os.getuid(), os.getgid(), 0o400),
    )
    # Restore the real implementations that the autouse fixture bypasses.
    monkeypatch.setattr(readiness, "_read_protected_receipt", ORIGINAL_READ_PROTECTED_RECEIPT)
    monkeypatch.setattr(readiness, "lstat_identity", ORIGINAL_LSTAT_IDENTITY)

    receipt = _build_receipt(expired=True)
    auth_path = tmp_path / "auth.json"
    _write_personal_auth(auth_path, 454)
    identity_json = tmp_path / "identity.json"
    identity_json.write_text(json.dumps(_personal_identity(454), sort_keys=True, indent=2) + "\n", encoding="utf-8")

    # --- Case (i): symlink at the receipt path pointing to a valid expired receipt
    target = tmp_path / "real.json"
    _write_with_storage(target, receipt)
    symlink_receipt = tmp_path / "symlinked-readiness.json"
    try:
        symlink_receipt.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this filesystem")

    rc, _, _ = _run_cli(
        _personal_pro_reuse_args(symlink_receipt, auth_path, receipt["credential_expires_at"]),
        monkeypatch,
        tmp_path,
    )
    assert rc == 2, "(i) symlinked receipt reuse must refuse (2); got %d" % rc

    rc, _, _ = _run_cli(
        [
            "reserve", "--refresh-expired",
            "--receipt", str(symlink_receipt),
            "--auth", str(auth_path),
            "--binary", str(readiness.CODEX_BINARY),
            "--identity-json", str(identity_json),
            "--expected-kind", "device-auth",
            "--workspace-binding-class", identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
            "--credential-expires-at", receipt["credential_expires_at"],
            "--worker-uid", "454",
            "--worker-gid", "454",
        ],
        monkeypatch,
        tmp_path,
    )
    assert rc == 2, "(i) symlinked receipt refresh must refuse (2); got %d" % rc

    # --- Case (ii): regular receipt with mode 0o644 (must be refused)
    loose_receipt = tmp_path / "loose-readiness.json"
    _write_receipt(loose_receipt, receipt)
    os.chmod(loose_receipt, 0o644)

    rc, _, _ = _run_cli(
        _personal_pro_reuse_args(loose_receipt, auth_path, receipt["credential_expires_at"]),
        monkeypatch,
        tmp_path,
    )
    assert rc == 2, "(ii) mode-0o644 receipt reuse must refuse (2); got %d" % rc

    rc, _, _ = _run_cli(
        [
            "reserve", "--refresh-expired",
            "--receipt", str(loose_receipt),
            "--auth", str(auth_path),
            "--binary", str(readiness.CODEX_BINARY),
            "--identity-json", str(identity_json),
            "--expected-kind", "device-auth",
            "--workspace-binding-class", identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
            "--credential-expires-at", receipt["credential_expires_at"],
            "--worker-uid", "454",
            "--worker-gid", "454",
        ],
        monkeypatch,
        tmp_path,
    )
    assert rc == 2, "(ii) mode-0o644 receipt refresh must refuse (2); got %d" % rc

    # --- Case (iii): same receipt chmod 0o400 -> reuse rc 4 (contract is what gates it)
    os.chmod(loose_receipt, 0o400)
    rc, _, _ = _run_cli(
        _personal_pro_reuse_args(loose_receipt, auth_path, receipt["credential_expires_at"]),
        monkeypatch,
        tmp_path,
    )
    assert rc == 4, "(iii) mode-0o400 receipt reuse must succeed (4); got %d" % rc


# ---------------------------------------------------------------------------
# T12 (NB2) — pre-existing superseded sibling that is a symlink blocks refresh
# ---------------------------------------------------------------------------


def test_t12_superseded_sibling_symlink_blocks_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A symlinked superseded sibling must be refused under the storage contract.

    The refresh path lstat-verifies any pre-existing sibling before comparing
    bytes; a symlink or wrong-mode sibling raises `superseded_receipt_conflict`
    and leaves the live receipt untouched.
    """
    # Use the real lstat_identity + the test-runner identity as the storage contract
    # so the receipt itself passes lstat, but the symlinked sibling fails.
    monkeypatch.setattr(
        readiness, "receipt_storage_contract",
        lambda *, workspace_binding_class=None, worker_gid=readiness.WORKER_GID:
        (os.getuid(), os.getgid(), 0o400),
    )
    monkeypatch.setattr(readiness, "_read_protected_receipt", ORIGINAL_READ_PROTECTED_RECEIPT)
    monkeypatch.setattr(readiness, "lstat_identity", ORIGINAL_LSTAT_IDENTITY)

    receipt = _build_receipt(expired=True)
    receipt_path = tmp_path / "readiness.json"
    _write_with_storage(receipt_path, receipt)

    # Pre-stage a sibling at the would-be superseded path, as a symlink to an
    # unrelated target.  The bytes match nothing, but NB2 catches the symlink
    # via lstat_identity before the byte compare is even attempted.
    receipt_bytes = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode("utf-8")
    digest = __import__("hashlib").sha256(receipt_bytes).hexdigest()[:16]
    sibling_name = f"readiness.json.superseded-{digest}.json"
    sibling_target = tmp_path / "sibling-target.json"
    sibling_target.write_text("unrelated bytes", encoding="utf-8")
    sibling_path = tmp_path / sibling_name
    try:
        sibling_path.symlink_to(sibling_target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this filesystem")

    auth_path = tmp_path / "auth.json"
    _write_personal_auth(auth_path, 454)
    identity_json = tmp_path / "identity.json"
    identity_json.write_text(json.dumps(_personal_identity(454), sort_keys=True, indent=2) + "\n", encoding="utf-8")

    pre_bytes = receipt_path.read_bytes()

    rc, _, stderr = _run_cli(
        [
            "reserve", "--refresh-expired",
            "--receipt", str(receipt_path),
            "--auth", str(auth_path),
            "--binary", str(readiness.CODEX_BINARY),
            "--identity-json", str(identity_json),
            "--expected-kind", "device-auth",
            "--workspace-binding-class", identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
            "--credential-expires-at", receipt["credential_expires_at"],
            "--worker-uid", "454",
            "--worker-gid", "454",
        ],
        monkeypatch,
        tmp_path,
    )
    assert rc == 2, "symlinked superseded sibling must refuse (2); got %d" % rc
    assert "superseded_receipt_conflict" in stderr, (
        "stderr must mention superseded_receipt_conflict; got %r" % stderr
    )
    assert receipt_path.read_bytes() == pre_bytes, "live receipt must be untouched after sibling refusal"
