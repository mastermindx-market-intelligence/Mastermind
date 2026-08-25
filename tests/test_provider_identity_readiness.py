"""Deterministic provider identity and composite-readiness policy tests."""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ops.executive_os import provider_identity_policy as identity_policy


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str):
    path = ROOT / "ops" / "executive_os" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


identity = _load("provider_identity_probe_test", "provider_identity_probe.py")
readiness = _load("provider_readiness_test", "provider_readiness.py")


def test_readiness_receipt_is_fixed_root_only_and_exclusive_created() -> None:
    source = (
        ROOT / "ops" / "executive_os" / "provider_readiness.py"
    ).read_text(encoding="utf-8")
    assert str(readiness.RECEIPT_PATH).endswith(
        "/MastermindExecutive/config/provider-readiness-v2.json"
    )
    assert 'SCHEMA_VERSION = "mastermind.executive_provider_readiness/v2"' in source
    assert "os.O_EXCL" in source and 'getattr(os, "O_NOFOLLOW", 0)' in source
    assert "os.fchown(descriptor, 0, 0)" in source
    assert "os.fchmod(descriptor, 0o400)" in source
    assert "_fsync_directory(path.parent)" in source


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


def _evaluate(*, mode="agentIdentity", plan="enterprise_cbp_automation", kind="service-account"):
    return identity.evaluate_identity(
        account_read=_account(plan),
        auth_mode=mode,
        expected_kind=kind,
        workspace_binding_class=identity.WORKSPACE_BINDING_CLASS,
    )


def test_service_account_agent_identity_and_company_plan_passes_sanitized() -> None:
    result = _evaluate()
    assert result["passed"] is True
    assert result["auth_mode"] == "agentIdentity"
    assert result["plan_type"] == "enterprise_cbp_automation"
    rendered = json.dumps(result)
    assert "email" not in rendered
    assert "accountId" not in rendered
    assert "example.invalid" not in rendered


@pytest.mark.parametrize("plan", ["free", "go", "plus", "pro", "prolite", "unknown", "future"])
def test_consumer_unknown_and_unreviewed_plans_fail(plan: str) -> None:
    result = _evaluate(plan=plan)
    assert result["passed"] is False
    assert result["refusal"] == "company_plan_required"


@pytest.mark.parametrize(
    ("mode", "refusal"),
    [
        ("chatgpt", "auth_mode_policy_mismatch"),
        ("personalAccessToken", "auth_mode_policy_mismatch"),
        ("apikey", "auth_mode_missing_or_unknown"),
        ("chatgptAuthTokens", "auth_mode_missing_or_unknown"),
        ("headers", "auth_mode_missing_or_unknown"),
        ("bedrockApiKey", "auth_mode_missing_or_unknown"),
    ],
)
def test_service_policy_rejects_personal_api_key_and_other_auth_modes(
    mode: str, refusal: str
) -> None:
    result = _evaluate(mode=mode)
    assert result["passed"] is False
    assert result["refusal"] == refusal


def test_personal_token_fallback_is_explicitly_isolated() -> None:
    fallback = _evaluate(mode="personalAccessToken", kind="personal-access-token")
    primary = _evaluate(mode="personalAccessToken", kind="service-account")
    assert fallback["passed"] is True
    assert primary["passed"] is False


def test_personal_pro_device_identity_passes_only_under_dedicated_policy() -> None:
    personal = identity.evaluate_identity(
        account_read=_account("pro"),
        auth_mode="chatgpt",
        expected_kind="device-auth",
        workspace_binding_class=identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
    )
    company = identity.evaluate_identity(
        account_read=_account("pro"),
        auth_mode="chatgpt",
        expected_kind="device-auth",
        workspace_binding_class=identity_policy.COMPANY_WORKSPACE_BINDING_CLASS,
    )
    assert personal["passed"] is True
    assert personal["plan_type"] == "pro"
    assert personal["workspace_binding_class"] == (
        identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS
    )
    assert company["passed"] is False
    assert company["refusal"] == "company_plan_required"


@pytest.mark.parametrize(
    ("mode", "kind", "expected_refusal"),
    [
        ("agentIdentity", "service-account", "personal_pro_device_auth_required"),
        (
            "personalAccessToken",
            "personal-access-token",
            "personal_pro_device_auth_required",
        ),
        ("chatgpt", "service-account", "auth_mode_policy_mismatch"),
    ],
)
def test_personal_pro_policy_rejects_non_device_credentials(
    mode: str, kind: str, expected_refusal: str
) -> None:
    result = identity.evaluate_identity(
        account_read=_account("pro"),
        auth_mode=mode,
        expected_kind=kind,
        workspace_binding_class=identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
    )
    assert result["passed"] is False
    assert result["refusal"] == expected_refusal


def test_missing_null_unknown_and_unreviewed_auth_modes_fail() -> None:
    for auth_mode in (None, "", "futureMode", "apikey", "chatgptAuthTokens"):
        result = identity.evaluate_identity(
            account_read=_account(),
            auth_mode=auth_mode,
            expected_kind="service-account",
            workspace_binding_class=identity.WORKSPACE_BINDING_CLASS,
        )
        assert result["passed"] is False


def test_spoofed_top_level_auth_mode_and_malformed_account_read_fail() -> None:
    spoofed = identity.evaluate_identity(
        account_read={"authMode": "agentIdentity", "planType": "enterprise"},
        auth_mode="agentIdentity",
        expected_kind="service-account",
        workspace_binding_class=identity.WORKSPACE_BINDING_CLASS,
    )
    assert spoofed["refusal"] == "account_read_spoofed_auth_mode"
    for malformed in (
        None,
        {},
        {"account": None, "requiresOpenaiAuth": True},
        {"account": {}, "requiresOpenaiAuth": "yes"},
    ):
        result = identity.evaluate_identity(
            account_read=malformed,
            auth_mode="agentIdentity",
            expected_kind="service-account",
            workspace_binding_class=identity.WORKSPACE_BINDING_CLASS,
        )
        assert result["passed"] is False


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        (b"Logged in using access token\n", "agentIdentity"),
        (b"Logged in using personal access token\n", "personalAccessToken"),
        (b"Logged in using ChatGPT\n", "chatgpt"),
    ],
)
def test_exact_pinned_login_status_is_the_auth_mode_source(
    stderr: bytes, expected: str
) -> None:
    assert identity.classify_login_status(returncode=0, stderr=stderr) == expected
    assert identity.classify_login_status(returncode=1, stderr=stderr) is None
    assert identity.classify_login_status(returncode=0, stderr=b"warning\n" + stderr) is None
    assert identity.classify_login_status(
        returncode=0, stderr=b"Logged in using an API key - redacted\n"
    ) is None


def _config_read(*, effective=None, origins=None, layers=None):
    return {
        "config": (
            {"cli_auth_credentials_store": "file"}
            if effective is None
            else effective
        ),
        "origins": (
            {
                "cli_auth_credentials_store": {
                    "name": {"type": "sessionFlags"},
                    "version": "1",
                }
            }
            if origins is None
            else origins
        ),
        "layers": (
            [
                {
                    "name": {"type": "user", "file": "/safe"},
                    "version": "1",
                    "config": {"cli_auth_credentials_store": "keyring"},
                },
                {
                    "name": {"type": "sessionFlags"},
                    "version": "1",
                    "config": {"cli_auth_credentials_store": "file"},
                },
            ]
            if layers is None
            else layers
        ),
    }


def test_config_policy_proves_no_forced_workspace_or_login_in_any_layer() -> None:
    assert identity.config_has_no_forced_auth_policy(_config_read()) is True
    for value in (
        _config_read(effective={"cli_auth_credentials_store": "keyring"}),
        _config_read(origins={}),
        _config_read(
            effective={
                "cli_auth_credentials_store": "file",
                "forced_chatgpt_workspace_id": ["workspace"],
            }
        ),
        _config_read(
            effective={
                "cli_auth_credentials_store": "file",
                "forced_login_method": "chatgpt",
            }
        ),
        _config_read(
            origins={
                "cli_auth_credentials_store": {
                    "name": {"type": "sessionFlags"},
                    "version": "1",
                },
                "forced_chatgpt_workspace_id": {"name": {"type": "mdm"}},
            }
        ),
        _config_read(
            layers=[
                {
                    "name": {"type": "system", "file": "/etc/codex/config.toml"},
                    "version": "1",
                    "config": {"forced_login_method": None},
                },
                {
                    "name": {"type": "sessionFlags"},
                    "version": "1",
                    "config": {"cli_auth_credentials_store": "file"},
                },
            ]
        ),
        _config_read(
            layers=[
                {
                    "name": {"type": "project", "dotCodexFolder": "/project/.codex"},
                    "version": "1",
                    "config": {},
                },
                {
                    "name": {"type": "sessionFlags"},
                    "version": "1",
                    "config": {"cli_auth_credentials_store": "file"},
                },
            ]
        ),
        {"config": {}, "origins": {}, "layers": None},
    ):
        assert identity.config_has_no_forced_auth_policy(value) is False

    source = (ROOT / "ops" / "executive_os" / "provider_identity_probe.py").read_text(
        encoding="utf-8"
    )
    app_server = source.split("argv = [", 1)[1].split("client = _Client", 1)[0]
    assert app_server.index('cli_auth_credentials_store="file"') < app_server.index(
        '"app-server"'
    )


def _credential_expiry() -> str:
    return (
        datetime.now(UTC) + timedelta(hours=12)
    ).isoformat(timespec="seconds").replace("+00:00", "Z")


def _auth_meta():
    return {
        "device": 1,
        "inode": 2,
        "uid": 451,
        "gid": 451,
        "mode": 0o600,
        "size": 123,
        "mtime_ns": 4,
        "ctime_ns": 5,
        "nlink": 1,
    }


def _personal_auth_meta(uid: int = 454):
    return {**_auth_meta(), "uid": uid, "gid": uid, "inode": 1000 + uid}


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


def _identity():
    return {
        **_evaluate(),
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
        "credential_lstat": _personal_auth_meta(uid),
        "forced_chatgpt_workspace_id_applied": False,
    }


def _receipt():
    return readiness.compose_receipt(
        identity=_identity(),
        canary=_canary(),
        auth_identity=_auth_meta(),
        binary_identity=_binary_meta(),
        expected_kind="service-account",
        workspace_binding_class=readiness.WORKSPACE_BINDING_CLASS,
        credential_expires_at=_credential_expiry(),
    )


def test_composite_receipt_binds_current_credential_and_binary() -> None:
    receipt = _receipt()
    readiness.validate_receipt_document(
        receipt, auth_identity=_auth_meta(), binary_identity=_binary_meta()
    )
    assert receipt["passed"] is True
    assert receipt["provider_identity"]["auth_mode"] == "agentIdentity"
    assert receipt["inference_canary"]["canary_id"] == "canary-123456789abc"
    assert receipt["codex_binary"]["team_identifier"] == readiness.CODEX_TEAM_ID


def test_personal_pro_receipt_binds_one_worker_uid_and_rejects_cross_slot_reuse() -> None:
    auth = _personal_auth_meta(454)
    receipt = readiness.compose_receipt(
        identity=_personal_identity(454),
        canary=_canary(),
        auth_identity=auth,
        binary_identity=_binary_meta(),
        expected_kind="device-auth",
        workspace_binding_class=identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
        credential_expires_at=_credential_expiry(),
        worker_uid=454,
        worker_gid=454,
    )
    readiness.validate_receipt_document(
        receipt,
        auth_identity=auth,
        binary_identity=_binary_meta(),
        expected_kind="device-auth",
        workspace_binding_class=identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
        worker_uid=454,
        worker_gid=454,
    )
    with pytest.raises(readiness.ReadinessError, match="worker_identity_mismatch"):
        readiness.validate_receipt_document(
            receipt,
            auth_identity=_personal_auth_meta(455),
            binary_identity=_binary_meta(),
            expected_kind="device-auth",
            workspace_binding_class=identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
            worker_uid=455,
            worker_gid=455,
        )


def test_company_receipt_cannot_be_relabelled_as_personal_pro() -> None:
    receipt = _receipt()
    with pytest.raises(
        readiness.ReadinessError,
        match="expected_kind_mismatch|workspace_binding_mismatch",
    ):
        readiness.validate_receipt_document(
            receipt,
            auth_identity=_auth_meta(),
            binary_identity=_binary_meta(),
            expected_kind="device-auth",
            workspace_binding_class=identity_policy.PERSONAL_PRO_WORKER_BINDING_CLASS,
            worker_uid=451,
            worker_gid=451,
        )


def test_duplicate_same_identity_validates_but_stale_auth_or_binary_fails_closed() -> None:
    receipt = _receipt()
    readiness.validate_receipt_document(
        receipt, auth_identity=_auth_meta(), binary_identity=_binary_meta()
    )
    stale_auth = {**_auth_meta(), "inode": 99}
    stale_binary = {**_binary_meta(), "mtime_ns": 99}
    with pytest.raises(readiness.ReadinessError, match="credential_stale"):
        readiness.validate_receipt_document(
            receipt, auth_identity=stale_auth, binary_identity=_binary_meta()
        )
    with pytest.raises(readiness.ReadinessError, match="binary_stale"):
        readiness.validate_receipt_document(
            receipt, auth_identity=_auth_meta(), binary_identity=stale_binary
        )


def test_passing_canary_cannot_mask_wrong_provider_identity() -> None:
    receipt = _receipt()
    receipt["provider_identity"] = {
        **receipt["provider_identity"],
        "auth_mode": "personalAccessToken",
    }
    with pytest.raises(readiness.ReadinessError, match="auth_mode_mismatch"):
        readiness.validate_receipt_document(
            receipt, auth_identity=_auth_meta(), binary_identity=_binary_meta()
        )


def test_failed_canary_creates_adverse_nonpassing_composite() -> None:
    receipt = readiness.compose_receipt(
        identity=_identity(),
        canary=_canary(False),
        auth_identity=_auth_meta(),
        binary_identity=_binary_meta(),
        expected_kind="service-account",
        workspace_binding_class=readiness.WORKSPACE_BINDING_CLASS,
        credential_expires_at=_credential_expiry(),
    )
    assert receipt["passed"] is False
    assert receipt["refusal"] == "invalid_workspace_selected"
    with pytest.raises(readiness.ReadinessError, match="not_passing"):
        readiness.validate_receipt_document(
            receipt, auth_identity=_auth_meta(), binary_identity=_binary_meta()
        )


def test_mismatch_and_identifier_injection_are_rejected_before_receipt() -> None:
    with pytest.raises(readiness.ReadinessError, match="credential_kind_mismatch"):
        readiness.compose_receipt(
            identity=_identity(), canary=_canary(), auth_identity=_auth_meta(),
            binary_identity=_binary_meta(), expected_kind="personal-access-token",
            workspace_binding_class=readiness.WORKSPACE_BINDING_CLASS,
            credential_expires_at=_credential_expiry(),
        )
    tainted = {**_identity(), "email": "leak@example.invalid"}
    with pytest.raises(readiness.ReadinessError, match="unreviewed_fields"):
        readiness.compose_receipt(
            identity=tainted, canary=_canary(), auth_identity=_auth_meta(),
            binary_identity=_binary_meta(), expected_kind="service-account",
            workspace_binding_class=readiness.WORKSPACE_BINDING_CLASS,
            credential_expires_at=_credential_expiry(),
        )


def test_forced_workspace_and_wrong_binary_canary_are_rejected() -> None:
    forced = {**_canary(), "forced_chatgpt_workspace_id_applied": True}
    with pytest.raises(readiness.ReadinessError, match="forced_workspace"):
        readiness.compose_receipt(
            identity=_identity(), canary=forced, auth_identity=_auth_meta(),
            binary_identity=_binary_meta(), expected_kind="service-account",
            workspace_binding_class=readiness.WORKSPACE_BINDING_CLASS,
            credential_expires_at=_credential_expiry(),
        )
    wrong = {**_canary(), "codex_sha256": "0" * 64}
    with pytest.raises(readiness.ReadinessError, match="canary_binary_mismatch"):
        readiness.compose_receipt(
            identity=_identity(), canary=wrong, auth_identity=_auth_meta(),
            binary_identity=_binary_meta(), expected_kind="service-account",
            workspace_binding_class=readiness.WORKSPACE_BINDING_CLASS,
            credential_expires_at=_credential_expiry(),
        )


def test_reservation_is_exclusive_nonpassing_and_binds_pre_canary_identity() -> None:
    reservation = readiness.compose_reservation(
        identity=_identity(),
        auth_identity=_auth_meta(),
        binary_identity=_binary_meta(),
        expected_kind="service-account",
        workspace_binding_class=readiness.WORKSPACE_BINDING_CLASS,
        credential_expires_at=_credential_expiry(),
    )
    assert reservation["passed"] is False
    assert reservation["refusal"] == "canary_reserved"
    assert reservation["inference_canary"] is None
    safe = readiness.validate_reservation_document(
        reservation,
        expected_kind="service-account",
        workspace_binding_class=readiness.WORKSPACE_BINDING_CLASS,
        credential_expires_at=reservation["credential_expires_at"],
    )
    assert safe["credential_lstat"] == _auth_meta()
    with pytest.raises(readiness.ReadinessError, match="reservation_kind_mismatch|reservation_malformed"):
        readiness.validate_reservation_document(
            {**reservation, "expected_credential_kind": "personal-access-token"},
            expected_kind="personal-access-token",
            workspace_binding_class=readiness.WORKSPACE_BINDING_CLASS,
            credential_expires_at=reservation["credential_expires_at"],
        )


def test_command_status_and_nested_receipt_truth_cannot_be_overridden() -> None:
    with pytest.raises(readiness.ReadinessError, match="command_status_conflict"):
        readiness.compose_receipt(
            identity=_identity(), canary=_canary(), auth_identity=_auth_meta(),
            binary_identity=_binary_meta(), expected_kind="service-account",
            workspace_binding_class=readiness.WORKSPACE_BINDING_CLASS,
            credential_expires_at=_credential_expiry(),
            canary_command_status=2,
        )
    receipt = _receipt()
    receipt["inference_canary"] = {**receipt["inference_canary"], "passed": False, "refusal": "failed"}
    with pytest.raises(readiness.ReadinessError, match="canary_not_passing|terminal_mismatch"):
        readiness.validate_receipt_document(
            receipt, auth_identity=_auth_meta(), binary_identity=_binary_meta()
        )


def test_pre_post_identity_stability_rejects_refresh_and_account_switch() -> None:
    before = _identity()
    refreshed = {
        **before,
        "observed_at": "2026-08-20T00:01:00Z",
        "credential_lstat": {**_auth_meta(), "inode": 99},
    }
    assert readiness._identity_stability_tuple(before) != readiness._identity_stability_tuple(
        refreshed
    )
    switched = {**refreshed, "auth_mode": "personalAccessToken"}
    assert readiness._identity_stability_tuple(before) != readiness._identity_stability_tuple(
        switched
    )


def test_readiness_expiry_is_bounded_and_requires_acceptance_margin() -> None:
    receipt = _receipt()
    observed = readiness._timestamp(
        receipt["observed_at"], code="test_timestamp_malformed"
    )
    readiness_expiry = readiness._timestamp(
        receipt["readiness_expires_at"], code="test_expiry_malformed"
    )
    credential_expiry = readiness._timestamp(
        receipt["credential_expires_at"], code="test_credential_expiry_malformed"
    )
    assert readiness_expiry <= credential_expiry
    assert readiness_expiry <= observed + readiness.MAX_READINESS_AGE
    expired = {
        **receipt,
        "credential_expires_at": "2026-01-01T00:00:00Z",
        "readiness_expires_at": "2026-01-01T00:00:00Z",
    }
    with pytest.raises(readiness.ReadinessError, match="expiry"):
        readiness.validate_receipt_document(
            expired, auth_identity=_auth_meta(), binary_identity=_binary_meta()
        )


def test_adverse_finalization_marker_is_never_reusable_as_ready() -> None:
    reservation = readiness.compose_reservation(
        identity=_identity(), auth_identity=_auth_meta(), binary_identity=_binary_meta(),
        expected_kind="service-account",
        workspace_binding_class=readiness.WORKSPACE_BINDING_CLASS,
        credential_expires_at=_credential_expiry(),
    )
    adverse = readiness.compose_adverse_from_reservation(
        reservation, refusal="canary_receipt_malformed"
    )
    assert adverse["passed"] is False
    assert adverse["refusal"] == "canary_receipt_malformed"
    with pytest.raises(readiness.ReadinessError, match="not_passing"):
        readiness.validate_receipt_document(
            adverse, auth_identity=_auth_meta(), binary_identity=_binary_meta()
        )
