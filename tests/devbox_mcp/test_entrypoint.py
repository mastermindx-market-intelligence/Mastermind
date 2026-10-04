from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from integrations.business_mcp_auth.contracts import subject_digest
from integrations.devbox_mcp.contracts import OBSERVE_SCOPE, OBSERVE_TOOL_NAMES
from ops.devbox.run_codespace_devbox import (
    DevBoxServiceConfigurationError,
    build_codespace_service,
    build_sanitized_service_environment,
    load_devbox_lease,
)

ISSUER = "https://identity.devbox.example"
REPOSITORY = "mastermindx-market-intelligence/Mastermind"
CLIENT = "b" * 64
PORT = 8767
CODESPACE = "silver-space-abc123"
DOMAIN = "app.github.dev"
RESOURCE = f"https://{CODESPACE}-{PORT}.{DOMAIN}/mcp"
SUBJECT = subject_digest(issuer=ISSUER, subject="pro-chairman-seat")
EXECUTE_SCOPE = "workbench.execute"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "Mastermind"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "entrypoint@example.invalid")
    _git(root, "config", "user.name", "Entrypoint")
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-qm", "baseline")
    return root


def _env() -> dict[str, str]:
    return {
        "CODESPACES": "true",
        "CODESPACE_NAME": CODESPACE,
        "GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN": DOMAIN,
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_TOKEN": "ambient-codespace-token",
    }


def _policy(
    path: Path,
    *,
    subject: str = SUBJECT,
    resource: str = RESOURCE,
    scope: str = EXECUTE_SCOPE,
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": "mastermind.business_mcp_auth_policy.v1",
                "policy_id": "mastermind.devbox." + scope.rsplit(".", 1)[-1] + ".v1",
                "resource": resource,
                "resource_metadata_url": resource.rsplit("/mcp", 1)[0]
                + "/.well-known/oauth-protected-resource/mcp",
                "issuer": ISSUER,
                "authorization_servers": [ISSUER],
                "jwks_uri": ISSUER + "/jwks",
                "required_scopes": [scope],
                "allowed_subject_digests": [subject],
                "allowed_algorithms": ["RS256"],
                "clock_skew_seconds": 0,
                "max_token_lifetime_seconds": 3600,
                "jwks_cache_ttl_seconds": 60,
                "unknown_kid_refresh_cooldown_seconds": 1,
                "fetch_failure_backoff_seconds": 1,
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)


def _lease(
    path: Path, repo: Path, *, scope: str = EXECUTE_SCOPE, **changes
) -> None:
    value = {
        "schema": "mastermind.devbox_lease.v1",
        "expected_subject_digest": SUBJECT,
        "expected_client_ref": CLIENT,
        "resource": RESOURCE,
        "required_scopes": [scope],
        "target_ref": "target:" + "1" * 64,
        "generation": "generation:" + "2" * 64,
        "owner_ref": "owner:" + "3" * 64,
        "repository": REPOSITORY,
        "committed_head": _git(repo, "rev-parse", "HEAD"),
        "lease_expires_at": 4_000_000_000,
    }
    value.update(changes)
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)


def test_load_lease_is_closed_and_exact(repo: Path, tmp_path: Path) -> None:
    path = tmp_path / "lease.json"
    _lease(path, repo)
    lease = load_devbox_lease(path)
    assert lease.repository == REPOSITORY
    assert lease.required_scopes == (EXECUTE_SCOPE,)
    assert lease.committed_head == _git(repo, "rev-parse", "HEAD")

    value = json.loads(path.read_text())
    value["model_can_choose_target"] = True
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(DevBoxServiceConfigurationError):
        load_devbox_lease(path)


def test_build_composes_exact_current_codespace_service(repo: Path, tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    lease = tmp_path / "lease.json"
    state = tmp_path / "state"
    _policy(policy)
    _lease(lease, repo)

    service = build_codespace_service(
        repo_root=repo,
        state_root=state,
        policy_file=policy,
        lease_file=lease,
        port=PORT,
        env=_env(),
        platform_name="linux",
        shell_path=Path("/bin/bash"),
    )
    try:
        assert service.preflight.forwarded_mcp_url == RESOURCE
        assert service.lease.resource == RESOURCE
        assert service.runtime.binding.committed_head == _git(repo, "rev-parse", "HEAD")
        assert service.port._lease == service.lease
        assert service.server.name == "Mastermind DevBox"
        assert (state / "auth-audit").is_dir()
        assert stat.S_IMODE((state / "auth-audit").stat().st_mode) == 0o700
    finally:
        service.close()


def test_build_composes_observe_policy_and_lease_without_second_service_profile(
    repo: Path, tmp_path: Path
) -> None:
    policy = tmp_path / "observe-policy.json"
    lease = tmp_path / "observe-lease.json"
    state = tmp_path / "observe-state"
    _policy(policy, scope=OBSERVE_SCOPE)
    _lease(lease, repo, scope=OBSERVE_SCOPE)

    service = build_codespace_service(
        repo_root=repo,
        state_root=state,
        policy_file=policy,
        lease_file=lease,
        port=PORT,
        env=_env(),
        platform_name="linux",
        shell_path=Path("/bin/bash"),
    )
    try:
        assert service.preflight.forwarded_mcp_url == RESOURCE
        assert service.policy.required_scopes == (OBSERVE_SCOPE,)
        assert service.lease.required_scopes == (OBSERVE_SCOPE,)
        assert service.port._allowed_tools == OBSERVE_TOOL_NAMES
        assert service.server.name == "Mastermind DevBox"
    finally:
        service.close()


@pytest.mark.parametrize(
    ("policy_scope", "lease_scope"),
    (
        (OBSERVE_SCOPE, EXECUTE_SCOPE),
        (EXECUTE_SCOPE, OBSERVE_SCOPE),
    ),
)
def test_policy_and_lease_scope_profiles_must_match(
    repo: Path,
    tmp_path: Path,
    policy_scope: str,
    lease_scope: str,
) -> None:
    policy = tmp_path / "policy.json"
    lease = tmp_path / "lease.json"
    _policy(policy, scope=policy_scope)
    _lease(lease, repo, scope=lease_scope)

    with pytest.raises(DevBoxServiceConfigurationError):
        build_codespace_service(
            repo_root=repo,
            state_root=tmp_path / "state",
            policy_file=policy,
            lease_file=lease,
            port=PORT,
            env=_env(),
            platform_name="linux",
            shell_path=Path("/bin/bash"),
        )


def test_head_resource_or_subject_mismatch_refuses_before_service(repo: Path, tmp_path: Path) -> None:
    for index, mutation in enumerate(
        (
            {"committed_head": "9" * 40},
            {"resource": "https://other.example/mcp"},
            {"expected_subject_digest": "e" * 64},
        )
    ):
        root = tmp_path / f"case-{index}"
        root.mkdir()
        policy = root / "policy.json"
        lease = root / "lease.json"
        _policy(policy)
        _lease(lease, repo, **mutation)
        with pytest.raises(DevBoxServiceConfigurationError):
            build_codespace_service(
                repo_root=repo,
                state_root=root / "state",
                policy_file=policy,
                lease_file=lease,
                port=PORT,
                env=_env(),
                platform_name="linux",
                shell_path=Path("/bin/bash"),
            )


def test_policy_resource_must_equal_real_forwarded_mcp_url(repo: Path, tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    lease = tmp_path / "lease.json"
    other = "https://static-devbox.example/mcp"
    _policy(policy, resource=other)
    _lease(lease, repo, resource=other)
    with pytest.raises(DevBoxServiceConfigurationError):
        build_codespace_service(
            repo_root=repo,
            state_root=tmp_path / "state",
            policy_file=policy,
            lease_file=lease,
            port=PORT,
            env=_env(),
            platform_name="linux",
            shell_path=Path("/bin/bash"),
        )


def test_config_file_symlink_or_world_writable_refuses(repo: Path, tmp_path: Path) -> None:
    policy = tmp_path / "policy-real.json"
    lease = tmp_path / "lease.json"
    _policy(policy)
    _lease(lease, repo)
    policy_link = tmp_path / "policy.json"
    policy_link.symlink_to(policy)
    with pytest.raises(DevBoxServiceConfigurationError):
        build_codespace_service(
            repo_root=repo,
            state_root=tmp_path / "state-a",
            policy_file=policy_link,
            lease_file=lease,
            port=PORT,
            env=_env(),
            platform_name="linux",
            shell_path=Path("/bin/bash"),
        )

    policy_link.unlink()
    policy.rename(policy_link)
    policy_link.chmod(0o666)
    with pytest.raises(DevBoxServiceConfigurationError):
        build_codespace_service(
            repo_root=repo,
            state_root=tmp_path / "state-b",
            policy_file=policy_link,
            lease_file=lease,
            port=PORT,
            env=_env(),
            platform_name="linux",
            shell_path=Path("/bin/bash"),
        )


def test_service_reexec_environment_is_strict_allowlist() -> None:
    import ops.devbox.run_codespace_devbox as service_module

    source = _env()
    source.update({
        "PATH": "/safe/bin",
        "HOME": "/home/codespace",
        "LANG": "C.UTF-8",
        "GH_TOKEN": "gh-secret",
        "OPENAI_API_KEY": "openai-secret",
        "AWS_SECRET_ACCESS_KEY": "aws-secret",
        "MY_RANDOM_SECRET": "other-secret",
        "SSH_AUTH_SOCK": "/tmp/agent",
        "PYTHONPATH": "/unsafe/injected",
    })
    cleaned = build_sanitized_service_environment(source)
    assert cleaned["PATH"] == "/safe/bin"
    assert cleaned["HOME"] == "/home/codespace"
    assert cleaned["CODESPACES"] == "true"
    assert cleaned["CODESPACE_NAME"] == CODESPACE
    assert cleaned["GITHUB_REPOSITORY"] == REPOSITORY
    assert cleaned["MASTERMIND_DEVBOX_ENV_SANITIZED"] == "1"
    assert cleaned["PYTHONPATH"] == str(
        Path(service_module.__file__).resolve().parents[2]
    )
    assert cleaned["PYTHONSAFEPATH"] == "1"
    assert cleaned["PYTHONNOUSERSITE"] == "1"
    rendered = json.dumps(cleaned, sort_keys=True)
    for forbidden in (
        "GITHUB_TOKEN", "GH_TOKEN", "OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY",
        "MY_RANDOM_SECRET", "SSH_AUTH_SOCK", "/unsafe/injected",
        "ambient-codespace-token", "gh-secret", "openai-secret", "aws-secret", "other-secret",
    ):
        assert forbidden not in rendered


def test_main_reexecs_before_service_build_with_sanitized_environment(monkeypatch) -> None:
    import ops.devbox.run_codespace_devbox as service_module

    source = _env()
    source.update({
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": "C.UTF-8",
        "GITHUB_TOKEN": "ambient-token",
        "GH_TOKEN": "ambient-gh-token",
        "SSH_AUTH_SOCK": "/tmp/agent",
        "OPENAI_API_KEY": "ambient-openai",
    })
    for key in list(os.environ):
        monkeypatch.delenv(key, raising=False)
    for key, value in source.items():
        monkeypatch.setenv(key, value)

    captured = {}

    class ReexecObserved(RuntimeError):
        pass

    def fake_execve(executable, argv, env):
        captured.update(executable=executable, argv=list(argv), env=dict(env))
        raise ReexecObserved()

    monkeypatch.setattr(service_module.os, "execve", fake_execve)
    with pytest.raises(ReexecObserved):
        service_module.main(["--policy-file", "/tmp/policy", "--lease-file", "/tmp/lease"])

    assert captured["executable"] == service_module.sys.executable
    assert captured["argv"][1:4] == [
        "-P",
        "-m",
        "ops.devbox.run_codespace_devbox",
    ]
    assert captured["env"]["MASTERMIND_DEVBOX_ENV_SANITIZED"] == "1"
    assert captured["env"]["CODESPACE_NAME"] == CODESPACE
    assert captured["env"]["PYTHONPATH"] == str(
        Path(service_module.__file__).resolve().parents[2]
    )
    assert captured["env"]["PYTHONSAFEPATH"] == "1"
    assert captured["env"]["PYTHONNOUSERSITE"] == "1"
    rendered = json.dumps(captured["env"], sort_keys=True)
    for forbidden in ("GITHUB_TOKEN", "GH_TOKEN", "SSH_AUTH_SOCK", "OPENAI_API_KEY",
                      "ambient-token", "ambient-gh-token", "ambient-openai"):
        assert forbidden not in rendered


def test_main_refuses_forged_sanitized_marker_with_ambient_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ops.devbox.run_codespace_devbox as service_module

    source = _env()
    source.update(
        {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
            "LANG": "C.UTF-8",
            "MASTERMIND_DEVBOX_ENV_SANITIZED": "1",
            "GITHUB_TOKEN": "forged-marker-token",
            "GH_TOKEN": "forged-marker-gh",
            "SSH_AUTH_SOCK": "/tmp/forged-agent",
            "PYTHONPATH": "/tmp/forged-pythonpath",
        }
    )
    for key in list(os.environ):
        monkeypatch.delenv(key, raising=False)
    for key, value in source.items():
        monkeypatch.setenv(key, value)

    monkeypatch.setattr(
        service_module.os,
        "execve",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("forged marker must not re-exec or reach service construction")
        ),
    )
    monkeypatch.setattr(
        service_module,
        "build_codespace_service",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("forged marker reached service construction")
        ),
    )

    with pytest.raises(
        DevBoxServiceConfigurationError,
        match="service environment sanitization was not proven",
    ):
        service_module.main(
            ["--policy-file", "/tmp/policy", "--lease-file", "/tmp/lease"]
        )


def test_exact_sanitized_marker_environment_is_accepted_without_reexec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ops.devbox.run_codespace_devbox as service_module

    source = _env()
    source.update(
        {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
            "LANG": "C.UTF-8",
        }
    )
    cleaned = service_module.build_sanitized_service_environment(source)
    for key in list(os.environ):
        monkeypatch.delenv(key, raising=False)
    for key, value in cleaned.items():
        monkeypatch.setenv(key, value)

    class FakeServer:
        @staticmethod
        def streamable_http_app():
            return object()

    class FakeService:
        server = FakeServer()
        preflight = type(
            "Preflight", (), {"forwarded_mcp_url": RESOURCE}
        )()

        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    fake_service = FakeService()
    observed: dict[str, object] = {}
    monkeypatch.setattr(
        service_module.os,
        "execve",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("exact sanitized environment must not re-exec")
        ),
    )

    def fake_build_codespace_service(**kwargs):
        observed["build"] = kwargs
        return fake_service

    monkeypatch.setattr(
        service_module,
        "build_codespace_service",
        fake_build_codespace_service,
    )

    class FakeUvicorn:
        @staticmethod
        def run(app, **kwargs):
            observed["app"] = app
            observed["uvicorn"] = kwargs

    monkeypatch.setitem(sys.modules, "uvicorn", FakeUvicorn())
    assert (
        service_module.main(
            ["--policy-file", "/tmp/policy", "--lease-file", "/tmp/lease"]
        )
        == 0
    )
    assert observed["build"]["policy_file"] == "/tmp/policy"
    assert observed["build"]["lease_file"] == "/tmp/lease"
    assert observed["uvicorn"]["host"] == "127.0.0.1"
    assert fake_service.closed is True
