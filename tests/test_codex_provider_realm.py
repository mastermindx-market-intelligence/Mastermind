from __future__ import annotations

import hashlib
import json
import stat
import subprocess
from pathlib import Path

import pytest

from control_plane import codex_provider_realm as cpr
from control_plane import codex_worker as cw
from control_plane import opencode_go_pooled_transport
from control_plane.codex_provider_realm import (
    ALIBABA_TOKEN_PLAN,
    CANDIDATE_CODEX_PROVIDER_REALMS_SPEC_ONLY,
    MINIMAX_TOKEN_PLAN,
    OPENCODE_GO_TOKEN_PLAN,
    REVIEWED_CODEX_PROVIDER_REALMS,
    CodexProviderRealm,
    ProviderRealmError,
)
from scripts.executive_os_phase1c_worker import (
    WorkerConfigError,
    _resolve_subscription_binding,
)

EXECUTIVE_SYSTEM_ROOT = Path("/Library/Application Support/MastermindExecutive")
EXECUTIVE_CODEX_BINARY = EXECUTIVE_SYSTEM_ROOT / "bin/codex-0.147.0"


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


def test_subscription_realm_registry_reviews_minimax_and_quarantines_opencode_go() -> None:
    # MiniMax Token Plan is reviewed for transport after the canary receipt in
    # control_plane/codex_provider_realm.py; reviewing the realm arms no worker
    # binding (the minimax codex row stays BUILT_NOT_PROVEN).
    reviewed_minimax = REVIEWED_CODEX_PROVIDER_REALMS["minimax-token-plan"]
    assert reviewed_minimax is MINIMAX_TOKEN_PLAN
    assert reviewed_minimax.base_url == "https://api.minimax.io/v1"
    assert reviewed_minimax.provider_alias == "minimax"
    assert reviewed_minimax.wire_api == "responses"
    # OpenCode Go is still quarantined and still not reviewed.
    assert "opencode-go" not in REVIEWED_CODEX_PROVIDER_REALMS
    assert OPENCODE_GO_TOKEN_PLAN.realm_id not in REVIEWED_CODEX_PROVIDER_REALMS
    assert OPENCODE_GO_TOKEN_PLAN.realm_id in CANDIDATE_CODEX_PROVIDER_REALMS_SPEC_ONLY
    assert set(REVIEWED_CODEX_PROVIDER_REALMS) == {
        "minimax-token-plan", "alibaba-token-plan-sg",
    }
    assert set(CANDIDATE_CODEX_PROVIDER_REALMS_SPEC_ONLY) == {"opencode-go"}
    assert MINIMAX_TOKEN_PLAN.base_url == "https://api.minimax.io/v1"
    assert MINIMAX_TOKEN_PLAN.env_key == "MINIMAX_TOKEN_PLAN_KEY"
    assert MINIMAX_TOKEN_PLAN.wire_api == "responses"
    assert ALIBABA_TOKEN_PLAN.base_url == (
        "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
    )
    assert ALIBABA_TOKEN_PLAN.env_key == "ALIBABA_TOKEN_PLAN_KEY"
    assert ALIBABA_TOKEN_PLAN.wire_api == "responses"
    for realm in (MINIMAX_TOKEN_PLAN, ALIBABA_TOKEN_PLAN, OPENCODE_GO_TOKEN_PLAN):
        rendered = "\n".join(realm.config_overrides())
        assert realm.base_url in rendered
        assert realm.env_key in rendered
        assert "request_max_retries=0" in rendered
        assert "stream_max_retries=0" in rendered
        assert "sk-" not in rendered.lower()


def test_opencode_go_candidate_realm_is_spec_only_and_matches_transport_constant() -> None:
    assert OPENCODE_GO_TOKEN_PLAN.base_url == (
        opencode_go_pooled_transport.OPENCODE_GO_BASE_URL.rstrip("/")
    )
    assert OPENCODE_GO_TOKEN_PLAN.env_key == "OPENCODE_GO_KEY"
    assert OPENCODE_GO_TOKEN_PLAN.wire_api == "responses"
    assert OPENCODE_GO_TOKEN_PLAN.realm_id not in REVIEWED_CODEX_PROVIDER_REALMS
    assert (
        OPENCODE_GO_TOKEN_PLAN.realm_id
        in CANDIDATE_CODEX_PROVIDER_REALMS_SPEC_ONLY
    )
    with pytest.raises(WorkerConfigError):
        _resolve_subscription_binding("opencode-go")
    with pytest.raises(WorkerConfigError):
        _resolve_subscription_binding("minimax-token-plan")


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
    if not EXECUTIVE_SYSTEM_ROOT.exists():
        pytest.skip("MastermindExecutive system root is unavailable (hosted CI)")
    assert EXECUTIVE_SYSTEM_ROOT.is_dir()
    assert EXECUTIVE_CODEX_BINARY.is_file()

    version_result = subprocess.run(
        [str(EXECUTIVE_CODEX_BINARY), "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert version_result.returncode == 0
    assert version_result.stdout.strip() == "codex-cli 0.147.0"

    def run(realm: CodexProviderRealm) -> subprocess.CompletedProcess[str]:
        home = tmp_path / f"codex-home-{realm.realm_id}"
        workspace = tmp_path / f"workspace-{realm.realm_id}"
        home.mkdir()
        workspace.mkdir()
        process = subprocess.run(
            [
                str(EXECUTIVE_CODEX_BINARY),
                "debug",
                "models",
                *(
                    argument
                    for override in realm.config_overrides()
                    for argument in ("-c", override)
                ),
            ],
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": str(home),
                "CODEX_HOME": str(home),
                "HTTP_PROXY": "http://127.0.0.1:9",
                "HTTPS_PROXY": "http://127.0.0.1:9",
                "ALL_PROXY": "http://127.0.0.1:9",
                "http_proxy": "http://127.0.0.1:9",
                "https_proxy": "http://127.0.0.1:9",
                "all_proxy": "http://127.0.0.1:9",
                "NO_PROXY": "",
                "no_proxy": "",
                realm.env_key: "native-proof-unused",
            },
            cwd=workspace,
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
    assert "connect failed" not in combined_chat_output.lower()
    assert "connection refused" not in combined_chat_output.lower()
    assert "error sending request" not in combined_chat_output.lower()

    responses_realm = CodexProviderRealm(
        realm_id="responses-native-proof", provider_alias="provider",
        display_name="Responses Native Proof",
        base_url="https://provider.invalid/v1", env_key="PROVIDER_KEY",
        wire_api="responses",
    )
    object.__setattr__(responses_realm, "base_url", "http://127.0.0.1:9/v1")
    responses_result = run(responses_realm)
    assert responses_result.returncode == 0
    combined_responses_output = responses_result.stdout + responses_result.stderr
    assert "no longer supported" not in combined_responses_output
    assert "connect failed" not in combined_responses_output.lower()
    assert "connection refused" not in combined_responses_output.lower()
    assert "error sending request" not in combined_responses_output.lower()
    assert "https://provider.invalid/v1" not in combined_responses_output.lower()
    assert isinstance(json.loads(responses_result.stdout), dict)


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


def test_minimax_realm_promotion_is_bound_to_sanitized_in_repo_evidence() -> None:
    evidence_path = (
        Path(__file__).resolve().parents[1]
        / "review_evidence/provider_realms/minimax_codex_responses_20260915.json"
    )
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert set(evidence) == {
        "schema",
        "source_receipt_schema",
        "source_receipt_sha256",
        "observation_started_at",
        "observation_finished_at",
        "wall_milliseconds",
        "harness_id",
        "harness_version",
        "realm_id",
        "candidate_binding_id",
        "candidate_binding_executed",
        "observed_slot_pool",
        "candidate_slot_pool",
        "provider",
        "base_url",
        "wire_api",
        "requested_model",
        "served_model",
        "return_code",
        "output_sha256",
        "output_bytes",
        "transport_reachability",
        "governed_canary",
        "provider_capacity_observed",
        "usage_policy_satisfied",
        "autonomous_routing_authorized",
        "credential_material_present",
    }
    assert evidence == {
        "schema": "mastermind.minimax_codex_responses_reachability/v1",
        "source_receipt_schema": "minimax_codex_canary_receipt/v1",
        "source_receipt_sha256": (
            "84771422af5ef24e12f6ec0e82a2b107763fceaca77f1c7c7915493802bee3dd"
        ),
        "observation_started_at": "2026-09-15T06:08:24Z",
        "observation_finished_at": "2026-09-15T06:08:28Z",
        "wall_milliseconds": 4500,
        "harness_id": "codex-cli",
        "harness_version": "0.154.0",
        "realm_id": "minimax-token-plan",
        "candidate_binding_id": "minimax-token-plan.codex-responses",
        "candidate_binding_executed": False,
        "observed_slot_pool": "minimax",
        "candidate_slot_pool": "minimax-codex",
        "provider": "minimax",
        "base_url": "https://api.minimax.io/v1",
        "wire_api": "responses",
        "requested_model": "MiniMax-M3",
        "served_model": "MiniMax-M3",
        "return_code": 0,
        "output_sha256": (
            "95784973cc639977bff93619700168505cb8f7855e44fa643d34622a43706c87"
        ),
        "output_bytes": 4,
        "transport_reachability": True,
        "governed_canary": False,
        "provider_capacity_observed": False,
        "usage_policy_satisfied": False,
        "autonomous_routing_authorized": False,
        "credential_material_present": False,
    }
    forbidden_keys = {
        "key_fingerprint",
        "key_fingerprint_sha256_12",
        "key_type",
        "key_type_tag",
        "credential",
        "credential_value",
        "authorization",
    }
    assert forbidden_keys.isdisjoint(evidence)
    rendered = json.dumps(evidence, sort_keys=True).lower()
    for forbidden in ("bearer ", "sk-", "/users/", "/home/"):
        assert forbidden not in rendered
    source = Path(cpr.__file__).read_text(encoding="utf-8")
    assert evidence_path.relative_to(Path(__file__).resolve().parents[1]).as_posix() in source
    assert evidence["source_receipt_sha256"] in source
    assert cpr.REVIEWED_CODEX_PROVIDER_REALMS[evidence["realm_id"]] is cpr.MINIMAX_TOKEN_PLAN
    assert evidence["candidate_binding_id"] == "minimax-token-plan.codex-responses"
    assert evidence["candidate_binding_executed"] is False
    assert evidence["observed_slot_pool"] != evidence["candidate_slot_pool"]
    assert evidence["governed_canary"] is False
    assert evidence["autonomous_routing_authorized"] is False
