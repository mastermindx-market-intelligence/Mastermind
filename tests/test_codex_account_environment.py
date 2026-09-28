from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from control_plane import codex_account_environment as account_environment
from control_plane.codex_account_environment import (
    CodexAccountError, account_readiness, native_codex_account_scope,
)


def auth(refresh="original"):
    return {"auth_mode": "chatgpt", "OPENAI_API_KEY": None, "tokens": {
        "access_token": "secret-access", "id_token": "secret-id",
        "refresh_token": refresh, "account_id": "account-one"}}


def private(path, value):
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    return path


@pytest.fixture
def home(tmp_path):
    path = tmp_path.resolve() / "provider"
    path.mkdir(mode=0o700)
    return path


def test_seed_once_preserves_native_refresh_and_never_reads_stale_seed(home, tmp_path):
    seed = private(tmp_path / "seed", auth())
    with native_codex_account_scope(home) as environment:
        assert environment.seed_if_missing(seed) == "SEEDED_ONCE"
        private(home / "auth.json", auth("native-refreshed"))
        seed.unlink()
        before = (home / "auth.json").read_bytes()
        assert environment.seed_if_missing(seed) == "PRESERVED_EXISTING"
        assert (home / "auth.json").read_bytes() == before
    assert list(home.glob(".native-auth-seed-*")) == []
    assert (home / "auth.json").stat().st_nlink == 1
    assert (home / "auth.json").stat().st_mode & 0o777 == 0o600


def test_seed_publication_cannot_clobber_a_concurrent_native_refresh(home, tmp_path, monkeypatch):
    seed = private(tmp_path / "seed", auth())
    real_link = os.link
    def race(source, destination, **kwargs):
        private(Path(destination), auth("concurrent-refresh"))
        return real_link(source, destination, **kwargs)
    monkeypatch.setattr(os, "link", race)
    with native_codex_account_scope(home) as environment:
        assert environment.seed_if_missing(seed) == "PRESERVED_CONCURRENT_PUBLICATION"
    assert json.loads((home / "auth.json").read_text())["tokens"]["refresh_token"] == "concurrent-refresh"
    assert list(home.glob(".native-auth-seed-*")) == []


def test_second_process_refused_then_admitted_without_deleting_lock(home):
    command = [sys.executable, "-c", "from pathlib import Path; "
               "from control_plane.codex_account_environment import native_codex_account_scope; "
               f"\nwith native_codex_account_scope(Path({str(home)!r})): print('ACQUIRED')"]
    with native_codex_account_scope(home):
        result = subprocess.run(command, text=True, capture_output=True)
        assert result.returncode != 0
        assert "ACCOUNT_REFRESH_WRITER_BUSY" in result.stderr
    inode = (home / ".executive-native-account.lock").stat().st_ino
    result = subprocess.run(command, text=True, capture_output=True)
    assert result.returncode == 0 and result.stdout.strip() == "ACQUIRED"
    assert (home / ".executive-native-account.lock").stat().st_ino == inode


@pytest.mark.parametrize("mode", [0o755, 0o750, 0o707])
def test_rejects_public_home(home, mode):
    home.chmod(mode)
    with pytest.raises(CodexAccountError, match="PRIVATE_DEDICATED"):
        with native_codex_account_scope(home):
            pytest.fail("public home admitted")


def test_rejects_symlink_home_and_symlink_ancestor(home, tmp_path):
    link = tmp_path / "alias"
    link.symlink_to(home, target_is_directory=True)
    with pytest.raises(CodexAccountError):
        with native_codex_account_scope(link):
            pytest.fail("alias admitted")
    child = home / "nested"
    child.mkdir(mode=0o700)
    with pytest.raises(CodexAccountError):
        with native_codex_account_scope(link / "nested"):
            pytest.fail("ancestor alias admitted")


@pytest.mark.parametrize(
    ("platform", "path", "canonical", "accepted"),
    [
        (
            "darwin",
            Path("/var/db/mastermind-executive/workers/codex-01/provider-home"),
            Path("/private/var/db/mastermind-executive/workers/codex-01/provider-home"),
            True,
        ),
        ("linux", Path("/var/db/provider-home"), Path("/private/var/db/provider-home"), False),
        ("darwin", Path("/tmp/provider-home"), Path("/private/tmp/provider-home"), False),
        ("darwin", Path("/var/db/provider-home"), Path("/private/var/other-home"), False),
    ],
)
def test_only_darwin_system_var_alias_is_admitted(
    monkeypatch, platform, path, canonical, accepted,
):
    monkeypatch.setattr(account_environment.sys, "platform", platform)
    assert account_environment._is_macos_var_alias(path, canonical) is accepted


def test_macos_var_alias_preserves_principal_home_refusal(home, monkeypatch):
    canonical = Path("/private/var/db/mastermind-executive/workers/codex-01/provider-home")
    original_resolve = Path.resolve

    def alias_resolve(path, strict=False):
        if path == home:
            return canonical
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", alias_resolve)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(
        account_environment,
        "_is_macos_var_alias",
        lambda path, observed: path == home and observed == canonical,
    )

    with pytest.raises(CodexAccountError, match="PRIVATE_DEDICATED"):
        account_environment._home(home)
    assert account_environment._home(home, principal_home_admitted=True) == home


@pytest.mark.parametrize("name", ["auth.json", ".executive-native-account.lock"])
def test_symlink_does_not_redirect_private_writes(home, tmp_path, name):
    target = private(tmp_path / "target", auth())
    (home / name).symlink_to(target)
    before = target.read_bytes()
    with pytest.raises(CodexAccountError):
        with native_codex_account_scope(home) as environment:
            environment.auth_metadata()
    assert target.read_bytes() == before


@pytest.mark.parametrize("mutation", ["api", "external", "missing", "wide", "hardlink", "invalid"])
def test_auth_refuses_unsafe_or_non_native_seed(home, tmp_path, mutation):
    seed = private(tmp_path / "seed", auth())
    if mutation == "api":
        value = auth(); value["OPENAI_API_KEY"] = "secret-api"; private(seed, value)
    elif mutation == "external":
        value = auth(); value["auth_mode"] = "chatgptAuthTokens"; private(seed, value)
    elif mutation == "missing":
        value = auth(); del value["tokens"]["refresh_token"]; private(seed, value)
    elif mutation == "wide":
        seed.chmod(0o644)
    elif mutation == "hardlink":
        os.link(seed, tmp_path / "alias")
    else:
        seed.write_text('broken secret-access')
    with native_codex_account_scope(home) as environment:
        with pytest.raises(CodexAccountError) as caught:
            environment.seed_if_missing(seed)
        assert "secret" not in str(caught.value)
    assert not (home / "auth.json").exists()


def test_environment_never_inherits_api_keys_or_provider_overrides(home, monkeypatch):
    private(home / "auth.json", auth())
    for key in ["OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_HOME", "HTTP_PROXY"]:
        monkeypatch.setenv(key, "secret-parent-override")
    with native_codex_account_scope(home) as environment:
        env = environment.process_environment()
        assert env["CODEX_HOME"] == str(home)
        assert env["HOME"] == str(home)
        assert not any("secret" in x for x in env.values())
        assert "OPENAI_API_KEY" not in env
        assert "tokens" not in environment.auth_metadata()
    with pytest.raises(CodexAccountError, match="SCOPE_CLOSED"):
        environment.process_environment()


def test_admitted_service_principal_home_is_supported_but_interactive_default_is_not(home, monkeypatch):
    monkeypatch.setenv("HOME", str(home))
    private(home / "auth.json", auth())
    with pytest.raises(CodexAccountError, match="PRIVATE_DEDICATED"):
        with native_codex_account_scope(home):
            pass
    with native_codex_account_scope(home, principal_home_admitted=True) as environment:
        assert environment.process_environment()["HOME"] == str(home)
    default = home / ".codex"
    default.mkdir(mode=0o700)
    with pytest.raises(CodexAccountError, match="PRIVATE_DEDICATED"):
        with native_codex_account_scope(default, principal_home_admitted=True):
            pass


def test_scope_cannot_be_constructed_directly_or_follow_replaced_home(home, tmp_path):
    from control_plane.codex_account_environment import CodexAccountEnvironment
    with pytest.raises(CodexAccountError, match="SCOPE_REQUIRED"):
        CodexAccountEnvironment(home)
    private(home / "auth.json", auth())
    with native_codex_account_scope(home) as environment:
        home.rename(tmp_path / "old-provider")
        home.mkdir(mode=0o700)
        private(home / "auth.json", auth("replacement"))
        with pytest.raises(CodexAccountError, match="HOME_CHANGED"):
            environment.auth_metadata()


def test_adapter_factory_reuses_existing_implementation_and_exact_home(home, monkeypatch):
    from control_plane import codex_worker
    private(home / "auth.json", auth())
    observed = {}
    sentinel = object()
    def constructor(binary, **kwargs):
        observed.update(binary=binary, **kwargs)
        return sentinel
    monkeypatch.setattr(codex_worker, "CodexWorkerAdapter", constructor)
    with native_codex_account_scope(home) as environment:
        assert environment.worker_adapter(Path("/bin/codex"), binary_attestation="existing") is sentinel
        assert observed == {"binary": Path("/bin/codex"), "binary_attestation": "existing", "codex_home": home,
                            "allowed_versions": None, "required_team_identifier": "2DC432GLL2"}
        for key in ["codex_home", "provider_realm", "provider_credential_loader"]:
            with pytest.raises(CodexAccountError, match="OVERRIDE_FORBIDDEN"):
                environment.worker_adapter(Path("/bin/codex"), **{key: None})


def window(used=25):
    return {"usedPercent": used, "windowDurationMins": 300, "resetsAt": 2000}


ACCOUNT = {"account": {"type": "chatgpt", "planType": "pro", "email": "secret-email"}, "requiresOpenaiAuth": True}


def test_current_named_bucket_wins_over_legacy_or_other_model():
    result = account_readiness(ACCOUNT, {"rateLimits": {"primary": window(0), "secondary": window(0)},
        "rateLimitsByLimitId": {"codex": {"primary": window(100), "secondary": window(2)},
                                "another": {"primary": window(0)}}}, now=1000)
    assert result["capacity_state"] == "EXHAUSTED"
    assert result["windows"]["primary"]["remaining_percent"] == 0
    assert result["admission_granted"] is False
    assert "secret" not in json.dumps(result)


@pytest.mark.parametrize("bad", [{}, True, {"usedPercent": 0}, window(float('nan')),
                                      window(-1), window(101), {**window(), "resetsAt": 999}])
def test_missing_malformed_or_stale_window_is_not_available(bad):
    result = account_readiness(ACCOUNT, {"rateLimits": {"primary": bad, "secondary": window()}}, now=1000)
    assert result["capacity_state"] == "UNKNOWN"


def test_explicit_single_window_is_not_mistaken_for_missing_capacity():
    result = account_readiness(ACCOUNT, {"rateLimits": {"primary": window(), "secondary": None}}, now=1000)
    assert result["capacity_state"] == "AVAILABLE_OBSERVED"
    assert set(result["windows"]) == {"primary"}
    missing = account_readiness(ACCOUNT, {"rateLimits": {"primary": window()}}, now=1000)
    assert missing["capacity_state"] == "UNKNOWN"


def test_malformed_account_is_unknown_not_a_login_diagnosis():
    assert account_readiness({}, {})["auth_state"] == "UNKNOWN"


@pytest.mark.parametrize("message,expected", [
    ("401 secret-access", "LOGIN_REQUIRED"), ("refresh token secret-token", "LOGIN_REQUIRED"),
    ("429 secret", "QUOTA_UNAVAILABLE"), ("timeout secret", "TRANSPORT_TIMEOUT"),
    ("unclassified secret", "NATIVE_READ_UNAVAILABLE")])
def test_failure_classification_does_not_disclose_provider_text(message, expected):
    from control_plane.codex_account_environment import _failure_kind
    assert _failure_kind(RuntimeError(message)) == expected


def test_available_is_observation_not_admission_or_invoice():
    result = account_readiness(ACCOUNT, {"rateLimits": {"primary": window(25), "secondary": window(50)}}, now=1000)
    assert result["capacity_state"] == "AVAILABLE_OBSERVED"
    assert result["admission_granted"] is False
    assert result["windows"]["primary"]["remaining_percent"] == 75


def test_absent_named_bucket_cannot_fall_back_to_legacy():
    result = account_readiness(ACCOUNT, {"rateLimitsByLimitId": {}, "rateLimits": {
        "primary": window(), "secondary": window()}}, now=1000)
    assert result["capacity_state"] == "UNKNOWN"


def test_explicit_null_named_buckets_cannot_fall_back_to_legacy():
    result = account_readiness(ACCOUNT, {"rateLimitsByLimitId": None,
        "rateLimits": {"primary": window(), "secondary": window()}}, now=1000)
    assert result["capacity_state"] == "UNKNOWN"
    assert result["windows"] == {}


@pytest.mark.parametrize("target", ["home", "auth.json", ".executive-native-account.lock"])
def test_acl_refuses_even_with_private_mode_bits(home, monkeypatch, target):
    from control_plane import codex_account_environment as module
    private(home / "auth.json", auth())
    monkeypatch.setattr(module, "has_macos_acl", lambda p, **kw:
        Path(p) == (home if target == "home" else home / target))
    with pytest.raises(CodexAccountError, match="ACL_FORBIDDEN"):
        with native_codex_account_scope(home) as environment:
            environment.auth_metadata()


def test_concurrent_invalid_seed_winner_is_refused_not_preserved(home, tmp_path, monkeypatch):
    seed = private(tmp_path / "seed", auth())
    real_link = os.link
    def race(source, destination, **kwargs):
        private(Path(destination), {"OPENAI_API_KEY": "foreign-secret"})
        return real_link(source, destination, **kwargs)
    monkeypatch.setattr(os, "link", race)
    with native_codex_account_scope(home) as environment:
        with pytest.raises(CodexAccountError, match="MANAGED_CHATGPT_AUTH_REQUIRED"):
            environment.seed_if_missing(seed)
    assert json.loads((home / "auth.json").read_text()) == {"OPENAI_API_KEY": "foreign-secret"}
    assert list(home.glob(".native-auth-seed-*")) == []


@pytest.mark.parametrize("failure", ["construct", "start", "read", "close", "unproven"])
def test_probe_sanitizes_all_transport_boundaries_and_preserves_cleanup_uncertainty(home, monkeypatch, failure):
    from scripts.ohf import laboratory
    from control_plane.codex_account_environment import probe_native_account
    private(home / "auth.json", auth())
    class Client:
        def __init__(self, *args, **kwargs):
            if failure == "construct":
                raise RuntimeError("Authorization: Bearer secret-token")
        def start(self):
            if failure == "start":
                raise RuntimeError("Authorization: Bearer secret-token")
        def request(self, method, *args, **kwargs):
            if failure == "read":
                raise RuntimeError("Authorization: Bearer secret-token")
            return ACCOUNT if method == "account/read" else {}
        def notify(self, *args):
            pass
        def graceful_close(self):
            if failure == "close":
                raise RuntimeError("Authorization: Bearer secret-token")
            return laboratory.AppServerStopProof(
                controller_returncode=0, private_group_id=12345,
                private_group_empty=failure != "unproven",
                leader_exit_confirmed_graceful=True,
                survivors_detected_after_controller_exit=False,
                termination_outcome="fixture")
    monkeypatch.setattr(laboratory, "AppServerClient", Client)
    with native_codex_account_scope(home) as environment:
        result = probe_native_account(environment, Path("/not-launched"))
    assert "secret" not in json.dumps(result)
    assert result["state"] != "NATIVE_READS_COMPLETED"
    if failure in {"close", "unproven"}:
        assert result["state"] == "NATIVE_CLEANUP_UNPROVEN"
        assert result["stop"]["private_group_empty"] is False


@pytest.mark.parametrize("account,expected", [({"account": None}, "LOGIN_REQUIRED"),
    ({"account": {"type": "apiKey"}}, "NATIVE_CHATGPT_AUTH_REQUIRED")])
def test_missing_and_api_auth_are_not_native_capacity(account, expected):
    result = account_readiness(account, {"rateLimits": {"primary": window(), "secondary": window()}}, now=1000)
    assert result["auth_state"] == expected
    assert result["capacity_state"] == "UNKNOWN"
