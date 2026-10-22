"""Finite attended credential-target compatibility; real resolvers, no secrets.

The composition tests run the real ``scripts.executive_os_phase1c_worker``
config resolver and the real reviewed subscription catalogue: only the
root-owner precondition is relaxed, because a non-root test principal can
never own the fixture config.  Schema fields, binding review, profile
identity, and the shared credential-format boundary are the actual code
paths.  No test reads or enrols a real credential and no provider, host, or
network is touched.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from control_plane import codex_provider_realm
from control_plane.codex_provider_realm import (
    ALIBABA_TOKEN_PLAN,
    MINIMAX_TOKEN_PLAN,
    REVIEWED_CODEX_PROVIDER_REALMS,
    CodexProviderRealm,
    ProviderRealmError,
    validate_provider_credential_format,
)
from ops.executive_os import subscription_provider_credential as credential
from scripts import executive_os_phase1c_worker as worker

FINITE_BINDING = "minimax-token-plan.claude-code-anthropic"
CODEX_BINDING = "minimax-token-plan.codex-responses"


class _Stream(io.BytesIO):
    def isatty(self) -> bool:
        return False


def _write_config(tmp_path: Path, value: dict) -> Path:
    path = tmp_path / "worker.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)
    return path


def _finite_definition(tmp_path: Path, **overrides: object) -> dict:
    value = dict(
        schema_version=worker.SUBSCRIPTION_CONFIG_SCHEMA_VERSION,
        control_uid=450,
        control_gid=450,
        worker_uid=460,
        worker_gid=460,
        allowed_supplementary_gids=[],
        worker_user="finite",
        worker_id="finite-1",
        workspace_root="/srv/executive/jobs/workspaces",
        run_root="/srv/executive/jobs/runs",
        provider_home=str(tmp_path / "provider-home"),
        claude_binary="/opt/bin/claude",
        claude_attestation_receipt="/etc/finite/claude-binary.json",
        claude_attestation_sha256="a" * 64,
        allowed_claude_versions=["2.1.0"],
        launchd_socket_name="Finite",
        uid_sweep_receipt="/etc/finite/sweep.json",
        require_secret_canary=True,
        operator_harness_armed=False,
        harness_binding_id=FINITE_BINDING,
        subscription_realm_enrollment={"generation": 1, "binding_id": FINITE_BINDING},
    )
    value.update(overrides)
    return value


def _codex_definition(tmp_path: Path) -> dict:
    return dict(
        schema_version=worker.SUBSCRIPTION_CONFIG_SCHEMA_VERSION,
        control_uid=450,
        worker_uid=460,
        worker_gid=460,
        allowed_supplementary_gids=[12, 61, 100],
        worker_user="codex",
        worker_id="codex-1",
        workspace_root="/srv/executive/jobs/workspaces",
        run_root="/srv/executive/jobs/runs",
        provider_home=str(tmp_path / "provider-home"),
        codex_binary="/opt/bin/codex",
        codex_attestation_receipt="/etc/finite/codex-binary.json",
        allowed_codex_versions=["0.154.0"],
        required_team_identifier="2DC432GLL2",
        launchd_socket_name="CodexFinite",
        uid_sweep_receipt="/etc/finite/sweep.json",
        require_secret_canary=True,
        operator_harness_armed=False,
        harness_binding_id=CODEX_BINDING,
    )


def _prepared_home(value: dict) -> Path:
    home = Path(str(value["provider_home"]))
    home.mkdir(mode=0o700)
    os.chown(home, os.getuid(), os.getgid())
    home.chmod(0o700)
    return home


@pytest.fixture
def real_resolver_without_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Relax only the root-owner precondition of the real config resolver."""
    real_load = worker._load_config

    def _non_root_owner(path, *, require_root_owner):
        assert require_root_owner is True
        return real_load(path, require_root_owner=False)

    monkeypatch.setattr(worker, "_load_config", _non_root_owner)


def test_finite_binding_identity_is_the_reviewed_catalogue_target() -> None:
    from control_plane.subscription_harness_bindings import get_binding

    assert worker._FINITE_ATTENDED_BINDING == FINITE_BINDING
    binding = get_binding(FINITE_BINDING)
    assert binding.adapter_id == "claude-compatible-subscription"
    assert binding.protocol == "anthropic"
    assert binding.autonomous_allowed is False
    assert binding.implementation_state != "SPEC_ONLY"
    assert binding.profile_id


def test_finite_target_resolves_attended_profile_not_codex_realm(
    tmp_path: Path,
    real_resolver_without_root,
) -> None:
    from control_plane.subscription_harness_bindings import get_binding

    value = _finite_definition(tmp_path)
    path = _write_config(tmp_path, value)
    config, authority = credential._load_reviewed_target_config(path)
    assert config == value
    assert isinstance(authority, credential.AttendedProfileCredentialFormat)
    assert not isinstance(authority, CodexProviderRealm)
    assert authority.binding_id == FINITE_BINDING
    assert authority.profile_id == get_binding(FINITE_BINDING).profile_id
    assert authority.validate_credential("opaque-token") == "opaque-token"


def test_codex_target_still_resolves_the_same_reviewed_realm(
    tmp_path: Path,
    real_resolver_without_root,
) -> None:
    value = _codex_definition(tmp_path)
    path = _write_config(tmp_path, value)
    config, realm = credential._load_reviewed_target_config(path)
    assert config == value
    assert realm is MINIMAX_TOKEN_PLAN
    assert realm is REVIEWED_CODEX_PROVIDER_REALMS["minimax-token-plan"]
    assert realm.validate_credential("opaque-token") == "opaque-token"


def test_non_v5_target_refuses_with_the_typed_v5_message(
    tmp_path: Path,
    real_resolver_without_root,
) -> None:
    value = _codex_definition(tmp_path)
    del value["harness_binding_id"]
    value["schema_version"] = worker.CONFIG_SCHEMA_VERSION
    path = _write_config(tmp_path, value)
    with pytest.raises(
        credential.SubscriptionCredentialError,
        match="must use worker config v5",
    ):
        credential._load_reviewed_target_config(path)


def test_unreviewed_binding_target_refuses_as_not_reviewed(
    tmp_path: Path,
    real_resolver_without_root,
) -> None:
    value = _finite_definition(tmp_path)
    value["harness_binding_id"] = FINITE_BINDING + "-typo"
    value["subscription_realm_enrollment"] = {
        "generation": 1,
        "binding_id": value["harness_binding_id"],
    }
    path = _write_config(tmp_path, value)
    with pytest.raises(
        credential.SubscriptionCredentialError,
        match="target config is not reviewed",
    ):
        credential._load_reviewed_target_config(path)


@pytest.mark.skipif(os.geteuid() == 0, reason="root owns every fixture config")
def test_target_resolution_still_requires_a_root_owned_config(tmp_path: Path) -> None:
    path = _write_config(tmp_path, _finite_definition(tmp_path))
    with pytest.raises(
        credential.SubscriptionCredentialError,
        match="target config is not reviewed",
    ):
        credential._load_reviewed_target_config(path)


def test_target_resolution_never_opens_any_descriptor(
    tmp_path: Path,
    real_resolver_without_root,
) -> None:
    value = _finite_definition(tmp_path)
    home = _prepared_home(value)
    secret = home / codex_provider_realm.PROVIDER_CREDENTIAL_FILENAME
    secret.write_bytes(b"opaque-enrolled-secret")
    os.chown(secret, os.getuid(), os.getgid())
    secret.chmod(0o600)
    path = _write_config(tmp_path, value)

    def refuse(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("target resolution must not open any descriptor")

    with mock.patch.object(credential.os, "open", refuse), mock.patch.object(
        codex_provider_realm.os, "open", refuse
    ):
        _, authority = credential._load_reviewed_target_config(path)
    assert isinstance(authority, credential.AttendedProfileCredentialFormat)
    assert secret.read_bytes() == b"opaque-enrolled-secret"


def _reviewed_binding(**overrides: object) -> SimpleNamespace:
    value = dict(
        binding_id=FINITE_BINDING,
        adapter_id="claude-compatible-subscription",
        harness_id="claude-code",
        protocol="anthropic",
        autonomous_allowed=False,
        implementation_state="BUILT_NOT_PROVEN",
        profile_id="minimax.anthropic",
    )
    value.update(overrides)
    return SimpleNamespace(**value)


@pytest.mark.parametrize(
    "overrides",
    [
        {"binding_id": "minimax-token-plan.other-anthropic"},
        {"binding_id": None},
        {"adapter_id": "codex-cli"},
        {"adapter_id": None},
        {"harness_id": "codex-cli"},
        {"harness_id": None},
        {"protocol": "responses"},
        {"protocol": None},
        {"autonomous_allowed": True},
        {"autonomous_allowed": None},
        {"implementation_state": "SPEC_ONLY"},
        {"profile_id": ""},
        {"profile_id": "  minimax.anthropic  "},
        {"profile_id": None},
        {"profile_id": 7},
    ],
)
def test_unreviewed_attended_profiles_refuse(overrides: dict) -> None:
    with pytest.raises(
        credential.SubscriptionCredentialError,
        match="profile is not reviewed",
    ):
        credential._resolve_attended_profile_credential(
            _reviewed_binding(**overrides), FINITE_BINDING
        )


def test_missing_profile_attribute_refuses() -> None:
    binding = _reviewed_binding()
    del binding.profile_id
    with pytest.raises(
        credential.SubscriptionCredentialError,
        match="profile is not reviewed",
    ):
        credential._resolve_attended_profile_credential(binding, FINITE_BINDING)


def test_attended_branch_is_pinned_to_the_exact_finite_binding() -> None:
    with pytest.raises(
        credential.SubscriptionCredentialError,
        match="profile is not reviewed",
    ):
        credential._resolve_attended_profile_credential(
            _reviewed_binding(), "other-finite-binding"
        )


def test_attended_authority_carries_no_codex_realm_interpretation() -> None:
    authority = credential._resolve_attended_profile_credential(
        _reviewed_binding(), FINITE_BINDING
    )
    assert isinstance(authority, credential.AttendedProfileCredentialFormat)
    assert not isinstance(authority, CodexProviderRealm)
    for forbidden in (
        "wire_api",
        "base_url",
        "env_key",
        "codex_provider_id",
        "config_overrides",
    ):
        assert not hasattr(authority, forbidden)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("opaque-token", "opaque-token"),
        ("  opaque-token  ", "opaque-token"),
        ("a" * 4096, "a" * 4096),
    ],
)
def test_shared_format_boundary_accepts(value: object, expected: str) -> None:
    authority = credential.AttendedProfileCredentialFormat(
        binding_id=FINITE_BINDING, profile_id="minimax.anthropic"
    )
    assert validate_provider_credential_format(value) == expected  # type: ignore[arg-type]
    assert authority.validate_credential(value) == expected  # type: ignore[arg-type]
    assert MINIMAX_TOKEN_PLAN.validate_credential(value) == expected  # type: ignore[arg-type]
    assert ALIBABA_TOKEN_PLAN.validate_credential(value) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "a" * 4097,
        "opaque\ntoken",
        "opaque\rtoken",
        "opaque\x00token",
        123,
        None,
        b"opaque-token",
    ],
)
def test_shared_format_boundary_refuses(value: object) -> None:
    authority = credential.AttendedProfileCredentialFormat(
        binding_id=FINITE_BINDING, profile_id="minimax.anthropic"
    )
    for validate in (
        validate_provider_credential_format,
        authority.validate_credential,
        MINIMAX_TOKEN_PLAN.validate_credential,
        ALIBABA_TOKEN_PLAN.validate_credential,
    ):
        with pytest.raises(ProviderRealmError):
            validate(value)


def test_attended_profile_authority_installs_and_verifies_like_a_realm(
    tmp_path: Path,
) -> None:
    value = _finite_definition(
        tmp_path, worker_uid=os.getuid(), worker_gid=os.getgid()
    )
    _prepared_home(value)
    authority = credential.AttendedProfileCredentialFormat(
        binding_id=FINITE_BINDING, profile_id="minimax.anthropic"
    )
    path = credential.install_provider_credential(
        value,
        authority,
        credential=b"opaque-test-only-key",
        replace_existing=False,
    )
    assert path.read_bytes() == b"opaque-test-only-key"
    assert credential.verify_provider_credential(value) == path
    with pytest.raises(
        credential.SubscriptionCredentialError,
        match="explicit replacement",
    ):
        credential.install_provider_credential(
            value,
            authority,
            credential=b"opaque-test-only-key",
            replace_existing=False,
        )


def test_verify_only_finite_target_passes_metadata_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_resolver_without_root,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = _finite_definition(
        tmp_path,
        worker_uid=os.getuid(),
        worker_gid=os.getgid(),
        control_uid=os.getuid() + 1,
        control_gid=os.getgid() + 1,
    )
    home = _prepared_home(value)
    secret = home / codex_provider_realm.PROVIDER_CREDENTIAL_FILENAME
    secret.write_bytes(b"opaque-enrolled-secret")
    os.chown(secret, os.getuid(), os.getgid())
    secret.chmod(0o600)
    path = _write_config(tmp_path, value)
    monkeypatch.setattr(credential.os, "geteuid", lambda: 0)
    assert credential.main(["--config", str(path), "--verify-only"]) == 0
    out = capsys.readouterr().out
    assert "metadata passed" in out and "not READY" in out
    assert secret.read_bytes() == b"opaque-enrolled-secret"


def test_enroll_finite_target_enforces_profile_format_and_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_resolver_without_root,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = _finite_definition(
        tmp_path,
        worker_uid=os.getuid(),
        worker_gid=os.getgid(),
        control_uid=os.getuid() + 1,
        control_gid=os.getgid() + 1,
    )
    home = _prepared_home(value)
    path = _write_config(tmp_path, value)
    monkeypatch.setattr(credential.os, "geteuid", lambda: 0)
    monkeypatch.setattr(credential, "_assert_global_autonomy_disarmed", lambda: None)
    monkeypatch.setattr(credential, "_assert_worker_quiescent", lambda worker_uid: None)
    monkeypatch.setattr(
        credential.sys,
        "stdin",
        SimpleNamespace(buffer=_Stream(b"opaque-enrolled-token\n")),
    )
    assert credential.main(["--config", str(path), "--enroll"]) == 0
    assert "not READY" in capsys.readouterr().out
    enrolled = home / codex_provider_realm.PROVIDER_CREDENTIAL_FILENAME
    assert enrolled.read_bytes() == b"opaque-enrolled-token"

    monkeypatch.setattr(
        credential.sys,
        "stdin",
        SimpleNamespace(buffer=_Stream(b"opaque-rotated-token\n")),
    )
    assert credential.main(["--config", str(path), "--enroll"]) == 2
    assert enrolled.read_bytes() == b"opaque-enrolled-token"
    # Each CLI invocation owns its own stdin; the refused request consumed the prior one.
    monkeypatch.setattr(credential.sys, "stdin", SimpleNamespace(buffer=_Stream(b"opaque-rotated-token\n")))
    assert credential.main(["--config", str(path), "--enroll", "--replace-existing"]) == 0
    assert enrolled.read_bytes() == b"opaque-rotated-token"

    monkeypatch.setattr(
        credential.sys,
        "stdin",
        SimpleNamespace(buffer=_Stream(b"opaque\nrotated\n")),
    )
    assert credential.main(["--config", str(path), "--enroll", "--replace-existing"]) == 2
    assert enrolled.read_bytes() == b"opaque-rotated-token"
