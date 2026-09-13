from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from control_plane import codex_worker as cw
from control_plane.codex_provider_realm import (
    ALIBABA_TOKEN_PLAN,
    CANDIDATE_CODEX_PROVIDER_REALMS_SPEC_ONLY,
    MINIMAX_TOKEN_PLAN,
    REVIEWED_CODEX_PROVIDER_REALMS,
    CodexProviderRealm,
    ProviderRealmError,
)


def _binary(tmp_path: Path) -> tuple[Path, cw.BinaryAttestation]:
    path = tmp_path / "codex"
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o700)
    info = path.lstat()
    return path, cw.BinaryAttestation(
        path=str(path), real_path=str(path.resolve()), version="test-0",
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(), team_identifier=None,
        size=info.st_size, device=info.st_dev, inode=info.st_ino,
        mode=stat.S_IMODE(info.st_mode), uid=info.st_uid, gid=info.st_gid,
        mtime_ns=info.st_mtime_ns,
    )


def _spec(tmp_path: Path) -> cw.WorkerLaunchSpec:
    workspace = tmp_path / "workspace"
    run_dir = tmp_path / "run"
    workspace.mkdir(exist_ok=True)
    run_dir.mkdir(exist_ok=True)
    return cw.WorkerLaunchSpec(
        run_id="run-1", job_id="job-1", worker_id="worker-1",
        workspace_path=workspace, run_dir=run_dir, prompt="read only",
        result_schema_path=run_dir / "schema.json", authorities=("READ",),
        model="fixture-model", reasoning_effort="high", worker_user="fixture",
    )


def test_subscription_realm_registry_quarantines_minimax_candidate() -> None:
    assert "minimax-token-plan" not in REVIEWED_CODEX_PROVIDER_REALMS
    assert set(REVIEWED_CODEX_PROVIDER_REALMS) == {"alibaba-token-plan-sg"}
    assert set(CANDIDATE_CODEX_PROVIDER_REALMS_SPEC_ONLY) == {"minimax-token-plan"}
    assert MINIMAX_TOKEN_PLAN.base_url == "https://api.minimax.io/v1"
    assert MINIMAX_TOKEN_PLAN.env_key == "MINIMAX_TOKEN_PLAN_KEY"
    assert MINIMAX_TOKEN_PLAN.wire_api == "responses"
    assert ALIBABA_TOKEN_PLAN.base_url == (
        "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
    )
    assert ALIBABA_TOKEN_PLAN.env_key == "ALIBABA_TOKEN_PLAN_KEY"
    assert ALIBABA_TOKEN_PLAN.wire_api == "responses"
    for realm in (MINIMAX_TOKEN_PLAN, ALIBABA_TOKEN_PLAN):
        rendered = "\n".join(realm.config_overrides())
        assert realm.base_url in rendered
        assert realm.env_key in rendered
        assert "request_max_retries=0" in rendered
        assert "stream_max_retries=0" in rendered
        assert "sk-" not in rendered.lower()


def test_provider_realm_rejects_chat_wire_api() -> None:
    with pytest.raises(ProviderRealmError, match='wire_api = "responses"'):
        CodexProviderRealm(
            realm_id="chat-realm", provider_alias="provider", display_name="Chat Realm",
            base_url="https://provider.invalid/v1", env_key="PROVIDER_KEY",
            wire_api="chat",
        )


def test_provider_realm_refuses_unsafe_identity_endpoint_and_retry() -> None:
    with pytest.raises(ProviderRealmError):
        CodexProviderRealm(
            realm_id="bad realm", provider_alias="bad", display_name="bad",
            base_url="https://example.invalid/v1", env_key="BAD_KEY", wire_api="responses",
        )
    with pytest.raises(ProviderRealmError):
        CodexProviderRealm(
            realm_id="bad", provider_alias="bad", display_name="bad",
            base_url="http://example.invalid/v1", env_key="BAD_KEY", wire_api="responses",
        )
    with pytest.raises(ProviderRealmError):
        CodexProviderRealm(
            realm_id="bad", provider_alias="bad", display_name="bad",
            base_url="https://example.invalid/v1", env_key="BAD_KEY", wire_api="responses",
            request_max_retries=1,
        )


def test_current_codex_native_config_rejects_chat_and_loads_responses(
    tmp_path: Path,
) -> None:
    binary_path = shutil.which("codex")
    if binary_path is None:
        pytest.skip("codex binary is unavailable")

    def run(realm: CodexProviderRealm) -> subprocess.CompletedProcess[str]:
        home = tmp_path / f"codex-home-{realm.realm_id}"
        workspace = tmp_path / f"workspace-{realm.realm_id}"
        home.mkdir()
        workspace.mkdir()
        process = subprocess.run(
            [
                binary_path,
                "exec",
                "--skip-git-repo-check",
                "-C",
                str(workspace),
                "x",
                *(
                    argument
                    for override in realm.config_overrides()
                    for argument in ("-c", override)
                ),
            ],
            env={
                **os.environ,
                "CODEX_HOME": str(home),
                realm.env_key: "native-proof-unused",
            },
            capture_output=True,
            text=True,
            timeout=20,
        )
        output = process.stdout + process.stderr
        assert f"CODEX_HOME={home}" not in output
        return process

    chat_realm = CodexProviderRealm(
        realm_id="chat-native-proof", provider_alias="provider",
        display_name="Chat Native Proof",
        base_url="https://provider.invalid/v1", env_key="PROVIDER_KEY",
        wire_api="responses",
    )
    object.__setattr__(chat_realm, "wire_api", "chat")
    chat_result = run(chat_realm)
    assert chat_result.returncode != 0
    combined_chat_output = chat_result.stdout + chat_result.stderr
    assert '`wire_api = "chat"` is no longer supported' in combined_chat_output
    assert "responses" in combined_chat_output

    responses_realm = CodexProviderRealm(
        realm_id="responses-native-proof", provider_alias="provider",
        display_name="Responses Native Proof",
        base_url="https://provider.invalid/v1", env_key="PROVIDER_KEY",
        wire_api="responses",
    )
    object.__setattr__(responses_realm, "base_url", "http://127.0.0.1:9/v1")
    responses_result = run(responses_realm)
    assert responses_result.returncode != 0
    combined_responses_output = responses_result.stdout + responses_result.stderr
    assert "no longer supported" not in combined_responses_output
    assert any(
        marker in combined_responses_output.lower()
        for marker in ("connection refused", "connection error", "error sending request")
    )


def test_external_realm_home_needs_no_openai_auth_marker(tmp_path: Path) -> None:
    binary, attestation = _binary(tmp_path)
    home = tmp_path / "provider-home"
    home.mkdir(mode=0o700)
    adapter = cw.CodexWorkerAdapter(
        binary, codex_home=home, binary_attestation=attestation,
        required_team_identifier=None, provider_realm=ALIBABA_TOKEN_PLAN,
        provider_credential_loader=lambda: "subscription-fixture-key",
    )
    assert adapter._validated_codex_home() == home.resolve()
    assert not (home / "auth.json").exists()


def test_default_openai_realm_still_requires_auth_marker(tmp_path: Path) -> None:
    binary, attestation = _binary(tmp_path)
    home = tmp_path / "provider-home-default"
    home.mkdir(mode=0o700)
    adapter = cw.CodexWorkerAdapter(
        binary, codex_home=home, binary_attestation=attestation,
        required_team_identifier=None,
    )
    with pytest.raises(cw.LaunchValidationError, match="auth.json"):
        adapter._validated_codex_home()


def test_provider_key_is_top_level_only_and_never_argv(tmp_path: Path) -> None:
    binary, attestation = _binary(tmp_path)
    home = tmp_path / "provider-home"
    home.mkdir(mode=0o700)
    secret = "subscription-fixture-key"
    adapter = cw.CodexWorkerAdapter(
        binary, codex_home=home, binary_attestation=attestation,
        required_team_identifier=None, provider_realm=ALIBABA_TOKEN_PLAN,
        provider_credential_loader=lambda: secret,
    )
    spec = _spec(tmp_path)
    process_home = tmp_path / "process-home"
    process_tmp = tmp_path / "process-tmp"
    process_home.mkdir(); process_tmp.mkdir()
    env = adapter._environment(spec, process_home, process_tmp, home)
    assert env[ALIBABA_TOKEN_PLAN.env_key] == secret
    argv = adapter._argv(
        spec, spec.workspace_path, spec.result_schema_path,
        spec.run_dir / "result.json", process_home, process_tmp, home,
    )
    rendered = "\n".join(argv)
    assert secret not in rendered
    assert ALIBABA_TOKEN_PLAN.env_key in rendered
    shell_policy = next(value for value in argv if value.startswith("shell_environment_policy="))
    assert ALIBABA_TOKEN_PLAN.env_key not in shell_policy
