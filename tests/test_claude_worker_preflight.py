from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parents[1]
_MODULE_PATH = _ROOT / "ops" / "executive_os" / "claude-worker-preflight.py"


def _load():
    spec = importlib.util.spec_from_file_location("claude_worker_preflight", _MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _receipt(module, **overrides):
    value = {
        "schema": module.SCHEMA,
        "realm_label": "claude-pro-01",
        "host_ref": "host-01234567",
        "os_principal_ref": "principal-01234567",
        "observed_at": "2026-08-27T23:30:00Z",
        "claude_binary_sha256": "a" * 64,
        "claude_version": "2.1.0",
        "auth_ready": True,
        "auth_method": "claudeai",
        "api_provider": "first_party",
        "auth_identity_confidence": "SLOT_ONLY",
        "macos_credential_isolation_basis": "OS_PRINCIPAL_KEYCHAIN",
        "execution_context": "INTERACTIVE_PRINCIPAL",
        "worker_id": None,
        "quota_class": None,
        "verdict": "INTERACTIVE_AUTH_READY",
        "reason_codes": [],
    }
    value.update(overrides)
    return value


def _executable(tmp_path: Path, body: bytes = b"#!/bin/sh\n") -> Path:
    binary = tmp_path / "claude"
    binary.write_bytes(body)
    binary.chmod(0o700)
    return binary


def _stdout_text(observation) -> str:
    stdout = observation.stdout
    return stdout.decode("utf-8") if isinstance(stdout, bytes) else str(stdout)


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_pid_exit(pid: int, *, timeout_seconds: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _pid_exists(pid):
            return True
        time.sleep(0.02)
    return not _pid_exists(pid)


def test_command_builder_allows_only_provider_work_free_observations(tmp_path: Path):
    module = _load()
    binary = _executable(tmp_path)

    assert module.build_allowed_argv(binary, "version") == (str(binary), "--version")
    assert module.build_allowed_argv(binary, "auth_status") == (
        str(binary),
        "auth",
        "status",
    )
    for forbidden in (
        "print",
        "prompt",
        "resume",
        "continue",
        "fork",
        "respawn",
        "agents",
        "mcp",
        "browser",
    ):
        with pytest.raises(module.PreflightError, match="COMMAND_NOT_ALLOWED"):
            module.build_allowed_argv(binary, forbidden)


def test_auth_status_normalizes_only_native_subscription_selection():
    module = _load()
    normalized = module.normalize_auth_status(
        {
            "loggedIn": True,
            "authMethod": "claude.ai",
            "apiProvider": "firstParty",
            "subscriptionType": "max",
        }
    )
    assert normalized == module.AuthObservation(
        auth_ready=True,
        auth_method="claudeai",
        api_provider="first_party",
        reason_codes=(),
    )

    not_native = module.normalize_auth_status(
        {
            "loggedIn": True,
            "authMethod": "api_key",
            "apiProvider": "firstParty",
        }
    )
    assert not_native.auth_ready is False
    assert "NATIVE_AUTH_NOT_SELECTED" in not_native.reason_codes


def test_native_login_managed_key_source_does_not_override_selected_native_auth():
    module = _load()
    normalized = module.normalize_auth_status(
        {
            "loggedIn": True,
            "authMethod": "claude.ai",
            "apiProvider": "firstParty",
            "subscriptionType": None,
            "apiKeySource": "/login managed key",
        }
    )
    assert normalized == module.AuthObservation(
        auth_ready=True,
        auth_method="claudeai",
        api_provider="first_party",
        reason_codes=(),
    )


def test_unknown_selected_auth_values_fail_closed():
    module = _load()
    normalized = module.normalize_auth_status(
        {
            "loggedIn": True,
            "authMethod": "future_auth_surface",
            "apiProvider": "futureProvider",
        }
    )
    assert normalized.auth_ready is False
    assert normalized.auth_method == "non_native"
    assert normalized.api_provider == "non_native"
    assert normalized.reason_codes == ("NATIVE_AUTH_NOT_SELECTED",)


def test_auth_status_fails_closed_on_unknown_wire_and_discards_pii():
    module = _load()
    with pytest.raises(module.PreflightError, match="AUTH_STATUS_UNSUPPORTED"):
        module.normalize_auth_status(
            {
                "loggedIn": True,
                "authMethod": "claude.ai",
                "apiProvider": "firstParty",
                "newCredentialMode": "surprise",
            }
        )

    normalized = module.normalize_auth_status(
        {
            "loggedIn": True,
            "authMethod": "claude.ai",
            "apiProvider": "firstParty",
            "email": "private@example.com",
            "organization": "private-org",
        }
    )
    assert normalized.auth_ready is True
    assert "private@example.com" not in repr(normalized)
    assert "private-org" not in repr(normalized)


def test_auth_status_exit_one_is_logged_out_not_transport_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(
            argv,
            1,
            stdout='{"loggedIn":false,"authMethod":"none","apiProvider":"firstParty"}',
            stderr="not logged in",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    observed = module.observe_auth(binary)
    assert observed == module.AuthObservation(
        auth_ready=False,
        auth_method="unknown",
        api_provider="unknown",
        reason_codes=("LOGIN_REQUIRED",),
    )


def test_auth_status_rejects_malformed_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv, 0, stdout="not-json", stderr="provider prose"
        ),
    )
    with pytest.raises(module.PreflightError, match="AUTH_STATUS_UNSUPPORTED"):
        module.observe_auth(binary)


def test_auth_status_rejects_unexpected_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv,
            2,
            stdout='{"loggedIn":false}',
            stderr="provider failed with private@example.com",
        ),
    )
    with pytest.raises(module.PreflightError, match="PROVIDER_COMMAND_FAILED") as exc:
        module.observe_auth(binary)
    assert "private@example.com" not in str(exc.value)


def test_auth_status_timeout_is_typed_and_does_not_echo_provider_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)

    def timeout(argv, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=argv,
            timeout=kwargs.get("timeout", 1),
            output="private@example.com",
            stderr="sk-" + "x" * 30,
        )

    monkeypatch.setattr(module.subprocess, "run", timeout)
    with pytest.raises(module.PreflightError, match="PROVIDER_TIMEOUT") as exc:
        module.observe_auth(binary)
    assert "private@example.com" not in str(exc.value)
    assert "sk-" not in str(exc.value)


def test_auth_status_exit_code_must_match_logged_in_boolean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv,
            1,
            stdout='{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"firstParty"}',
            stderr="",
        ),
    )
    with pytest.raises(module.PreflightError, match="AUTH_STATUS_UNSUPPORTED"):
        module.observe_auth(binary)


def test_auth_status_discards_known_pii_and_raw_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)
    secretish = "Bearer " + "x" * 24

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(
                {
                    "loggedIn": True,
                    "authMethod": "claude.ai",
                    "apiProvider": "firstParty",
                    "email": "private@example.com",
                    "organization": "private-org",
                }
            ),
            stderr=secretish,
        ),
    )
    observed = module.observe_auth(binary)
    rendered = repr(observed)
    assert observed.auth_ready is True
    assert "private@example.com" not in rendered
    assert "private-org" not in rendered
    assert secretish not in rendered


def test_receipt_is_closed_secret_free_and_context_bound():
    module = _load()
    value = _receipt(module)
    assert module.validate_receipt(value) == value

    # The closed V1 wire already reserves future worker-context receipts. Wire
    # validation is not authority to mint one from an arbitrary shell.
    worker_value = _receipt(
        module,
        execution_context="WORKER_BROKER",
        worker_id="claude-worker-01",
        quota_class="default",
        verdict="WORKER_CONTEXT_AUTH_READY",
    )
    assert module.validate_receipt(worker_value) == worker_value

    with pytest.raises(module.PreflightError, match="RECEIPT_INVALID"):
        module.validate_receipt({**value, "email": "private@example.com"})
    with pytest.raises(module.PreflightError, match="RECEIPT_INVALID"):
        module.validate_receipt(
            {**value, "execution_context": "WORKER_BROKER", "worker_id": None}
        )
    with pytest.raises(module.PreflightError, match="SECRET_SHAPED_VALUE"):
        module.validate_receipt({**value, "realm_label": "sk-" + "x" * 30})


def test_receipt_rejects_false_ready_contradiction():
    module = _load()
    contradictory = _receipt(
        module,
        auth_ready=False,
        auth_method="unknown",
        api_provider="unknown",
        verdict="INTERACTIVE_AUTH_READY",
        reason_codes=[],
    )
    with pytest.raises(module.PreflightError, match="RECEIPT_INVALID"):
        module.validate_receipt(contradictory)


def test_ready_receipt_rejects_unknown_credential_isolation_basis():
    module = _load()
    with pytest.raises(module.PreflightError, match="RECEIPT_INVALID"):
        module.validate_receipt(
            _receipt(module, macos_credential_isolation_basis="UNKNOWN")
        )


def test_receipt_requires_normalized_numeric_claude_version():
    module = _load()
    with pytest.raises(module.PreflightError, match="RECEIPT_INVALID"):
        module.validate_receipt(_receipt(module, claude_version="2.1.121 (Claude Code)"))


def test_builder_cannot_mint_worker_context_ready_before_broker_slice():
    module = _load()
    auth = module.AuthObservation(
        auth_ready=True,
        auth_method="claudeai",
        api_provider="first_party",
        reason_codes=(),
    )
    with pytest.raises(module.PreflightError, match="EXECUTION_CONTEXT_UNPROVEN"):
        module.build_ready_receipt(
            realm_label="claude-pro-01",
            host_ref="host-01234567",
            os_principal_ref="principal-01234567",
            execution_context="WORKER_BROKER",
            worker_id="claude-worker-01",
            quota_class="default",
            binary_sha256="a" * 64,
            version="2.1.0",
            auth=auth,
            observed_at="2026-08-27T23:30:00Z",
        )


def test_builder_cannot_mint_interactive_ready_without_identity_owner():
    module = _load()
    auth = module.AuthObservation(
        auth_ready=True,
        auth_method="claudeai",
        api_provider="first_party",
        reason_codes=(),
    )
    with pytest.raises(module.PreflightError, match="HOST_IDENTITY_SEAM_UNAVAILABLE"):
        module.build_ready_receipt(
            realm_label="claude-pro-01",
            host_ref="host-01234567",
            os_principal_ref="principal-01234567",
            execution_context="INTERACTIVE_PRINCIPAL",
            worker_id=None,
            quota_class=None,
            binary_sha256="a" * 64,
            version="2.1.0",
            auth=auth,
            observed_at="2026-08-27T23:30:00Z",
        )


def test_cli_refuses_caller_declared_identity_until_owner_seam_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)

    def provider_must_not_run(*args, **kwargs):
        pytest.fail("provider metadata commands ran before canonical identity ownership was proven")

    monkeypatch.setattr(module, "observe_binary", provider_must_not_run)
    monkeypatch.setattr(module, "observe_auth", provider_must_not_run)

    with pytest.raises(module.PreflightError, match="HOST_IDENTITY_SEAM_UNAVAILABLE"):
        module.main(
            [
                "--realm-label",
                "claude-pro-01",
                "--host-ref",
                "host-01234567",
                "--os-principal-ref",
                "principal-01234567",
                "--execution-context",
                "INTERACTIVE_PRINCIPAL",
                "--claude-binary",
                str(binary),
            ]
        )


def test_cli_refusal_never_claims_the_closed_receipt_schema(tmp_path: Path):
    missing = (tmp_path / "missing-claude").resolve()
    completed = subprocess.run(
        [
            sys.executable,
            str(_MODULE_PATH),
            "--realm-label",
            "claude-pro-01",
            "--host-ref",
            "host-01234567",
            "--os-principal-ref",
            "principal-01234567",
            "--execution-context",
            "INTERACTIVE_PRINCIPAL",
            "--claude-binary",
            str(missing),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    refusal = json.loads(completed.stdout)
    assert refusal == {"error": "HOST_IDENTITY_SEAM_UNAVAILABLE"}
    assert "schema" not in refusal
    assert completed.stderr == ""


@pytest.mark.parametrize(
    ("provider_output", "expected"),
    [
        ("2.1.121", "2.1.121"),
        ("2.1.121 (Claude Code)", "2.1.121"),
    ],
)
def test_binary_version_normalizes_only_reviewed_claude_code_forms(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_output: str,
    expected: str,
):
    module = _load()
    binary = _executable(tmp_path)
    monkeypatch.setattr(
        module,
        "_run",
        lambda argv, **kwargs: module.CommandObservation(0, provider_output),
    )
    _, version = module.observe_binary(binary)
    assert version == expected


@pytest.mark.parametrize(
    "provider_output",
    [
        "Claude Code 2.1.121",
        "2.1.121 beta",
        "2.1.121 (Claude Desktop)",
        "2.1.121 private@example.com",
    ],
)
def test_binary_version_rejects_unreviewed_prose(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_output: str,
):
    module = _load()
    binary = _executable(tmp_path)
    monkeypatch.setattr(
        module,
        "_run",
        lambda argv, **kwargs: module.CommandObservation(0, provider_output),
    )
    with pytest.raises(module.PreflightError, match="BINARY_INVALID"):
        module.observe_binary(binary)


def test_binary_observation_is_size_bounded_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path, b"123456789")
    monkeypatch.setattr(module, "MAX_BINARY_BYTES", 8, raising=False)

    def provider_must_not_run(*args, **kwargs):
        pytest.fail("oversized provider binary was executed")

    monkeypatch.setattr(module, "_run", provider_must_not_run)
    with pytest.raises(module.PreflightError, match="BINARY_INVALID"):
        module.observe_binary(binary)


def test_missing_binary_is_typed_refusal(tmp_path: Path):
    module = _load()
    with pytest.raises(module.PreflightError, match="BINARY_UNAVAILABLE"):
        module.observe_binary((tmp_path / "missing-claude").resolve())


def test_host_and_principal_refs_fail_closed_instead_of_being_invented():
    module = _load()
    with pytest.raises(module.PreflightError, match="HOST_IDENTITY_SEAM_UNAVAILABLE"):
        module.require_canonical_identity("local-unbound", "principal-01234567")
    with pytest.raises(module.PreflightError, match="PRINCIPAL_IDENTITY_SEAM_UNAVAILABLE"):
        module.require_canonical_identity("host-01234567", "")
    assert module.require_canonical_identity(
        "host-01234567", "principal-01234567"
    ) == ("host-01234567", "principal-01234567")


def test_f1_child_environment_is_constructive_not_inherited(
    monkeypatch: pytest.MonkeyPatch,
):
    module = _load()
    monkeypatch.setenv("MM_PREFLIGHT_POISON", "ambient-marker")
    monkeypatch.setenv("PYTHONPATH", "/ambient/python")
    monkeypatch.setenv("PATH", "/ambient/path")

    observed = module._run(
        (
            sys.executable,
            "-c",
            "import json,os; print(json.dumps(dict(os.environ), sort_keys=True))",
        )
    )
    child_environment = json.loads(_stdout_text(observed))

    assert "MM_PREFLIGHT_POISON" not in child_environment
    assert "PYTHONPATH" not in child_environment
    assert child_environment["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin"


def test_f1_provider_selector_refuses_before_child_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    marker = tmp_path / "child-started"
    secret = "sk-" + "x" * 30
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)

    with pytest.raises(module.PreflightError, match="^PROVIDER_ENV_REFUSED$") as exc:
        module._run(
            (
                sys.executable,
                "-c",
                f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')",
            )
        )

    assert not marker.exists()
    assert secret not in str(exc.value)


def test_f2_stdout_is_rejected_at_the_byte_ceiling(
    monkeypatch: pytest.MonkeyPatch,
):
    module = _load()
    monkeypatch.setattr(module, "MAX_STDOUT_BYTES", 32, raising=False)
    monkeypatch.setattr(module, "MAX_OUTPUT_LINE_BYTES", 64, raising=False)

    with pytest.raises(module.PreflightError, match="^PROVIDER_COMMAND_FAILED$"):
        module._run(
            (
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write(b'x' * 33); sys.stdout.flush()",
            )
        )


def test_f2_stderr_is_rejected_at_the_byte_ceiling(
    monkeypatch: pytest.MonkeyPatch,
):
    module = _load()
    monkeypatch.setattr(module, "MAX_STDERR_BYTES", 32, raising=False)
    monkeypatch.setattr(module, "MAX_OUTPUT_LINE_BYTES", 64, raising=False)

    with pytest.raises(module.PreflightError, match="^PROVIDER_COMMAND_FAILED$"):
        module._run(
            (
                sys.executable,
                "-c",
                "import sys; sys.stderr.buffer.write(b'x' * 33); sys.stderr.flush()",
            )
        )


@pytest.mark.skipif(os.name != "posix", reason="process-group ownership is POSIX-only")
def test_f2_timeout_kills_owned_descendant_and_reaps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    pid_path = tmp_path / "descendant.pid"
    monkeypatch.setattr(
        module, "_PROCESS_TERMINATE_GRACE_SECONDS", 0.15, raising=False
    )
    parent_code = (
        "import pathlib,signal,subprocess,sys,time; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],"
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid)); "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"
    )
    descendant_pid: int | None = None
    try:
        with pytest.raises(module.PreflightError, match="^PROVIDER_TIMEOUT$"):
            module._run(
                (sys.executable, "-c", parent_code, str(pid_path)),
                timeout_seconds=0.75,
            )
        assert pid_path.exists(), "the parent did not launch its descendant"
        descendant_pid = int(pid_path.read_text())
        assert _wait_for_pid_exit(descendant_pid), "owned descendant survived timeout"
    finally:
        if descendant_pid is not None and _pid_exists(descendant_pid):
            try:
                os.kill(descendant_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_f3_symlinked_parent_is_refused_before_leaf_acceptance(tmp_path: Path):
    module = _load()
    real_parent = tmp_path.resolve() / "real" / "bin"
    real_parent.mkdir(parents=True)
    _executable(real_parent)
    linked_parent = tmp_path.resolve() / "linked"
    linked_parent.symlink_to(real_parent.parent, target_is_directory=True)

    with pytest.raises(module.PreflightError, match="^BINARY_INVALID$"):
        module._require_binary(linked_parent / "bin" / "claude")


def test_f3_hardlinked_binary_is_refused(tmp_path: Path):
    module = _load()
    binary = _executable(tmp_path)
    os.link(binary, tmp_path / "claude-alias")

    with pytest.raises(module.PreflightError, match="^BINARY_INVALID$"):
        module._require_binary(binary)


def test_f3_group_or_world_writable_binary_is_refused(tmp_path: Path):
    module = _load()
    binary = _executable(tmp_path)
    binary.chmod(0o777)

    with pytest.raises(module.PreflightError, match="^BINARY_INVALID$"):
        module._require_binary(binary)


@pytest.mark.parametrize("replacement_body", [b"#!/bin/sh\n", b"#!/bin/no\n"])
def test_f4_atomic_replacement_is_refused_even_when_bytes_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement_body: bytes,
):
    module = _load()
    binary = _executable(tmp_path)
    replacement = tmp_path / "replacement"
    replacement.write_bytes(replacement_body)
    replacement.chmod(0o700)

    def replace_then_report_version(argv, **kwargs):
        os.replace(replacement, binary)
        return module.CommandObservation(0, "2.1.0")

    monkeypatch.setattr(module, "_run", replace_then_report_version)
    with pytest.raises(
        module.PreflightError, match="^BINARY_CHANGED_DURING_PREFLIGHT$"
    ):
        module.observe_binary(binary)


@pytest.mark.parametrize("drift", ["mode", "link"])
def test_f4_mode_and_link_drift_are_refused_after_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drift: str
):
    module = _load()
    binary = _executable(tmp_path)

    def drift_then_report_version(argv, **kwargs):
        if drift == "mode":
            binary.chmod(0o755)
        else:
            os.link(binary, tmp_path / "late-alias")
        return module.CommandObservation(0, "2.1.0")

    monkeypatch.setattr(module, "_run", drift_then_report_version)
    with pytest.raises(
        module.PreflightError, match="^BINARY_CHANGED_DURING_PREFLIGHT$"
    ):
        module.observe_binary(binary)


def test_f4_observation_executes_retained_descriptor_not_source_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)
    invocation: dict[str, object] = {}

    def report_version(argv, **kwargs):
        invocation["argv"] = argv
        invocation["pass_fds"] = kwargs.get("pass_fds")
        return module.CommandObservation(0, "2.1.0")

    monkeypatch.setattr(module, "_run", report_version)
    _, version = module.observe_binary(binary)

    assert version == "2.1.0"
    called_argv = invocation["argv"]
    assert isinstance(called_argv, tuple)
    assert called_argv[0].startswith("/dev/fd/")
    passed = invocation["pass_fds"]
    assert isinstance(passed, tuple) and len(passed) == 1 and type(passed[0]) is int


def test_f4_main_reuses_one_retained_object_for_version_and_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    module = _load()
    binary = _executable(tmp_path)
    invocations: list[tuple[tuple[str, ...], tuple[int, ...] | None]] = []
    monkeypatch.setattr(module, "require_current_identity_owner", lambda *args: None)

    def observe(argv, **kwargs):
        invocations.append((argv, kwargs.get("pass_fds")))
        if argv[-1] == "--version":
            return module.CommandObservation(0, "2.1.0")
        return module.CommandObservation(
            0,
            '{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"firstParty"}',
        )

    monkeypatch.setattr(module, "_run", observe)
    assert (
        module.main(
            [
                "--realm-label",
                "claude-pro-01",
                "--host-ref",
                "host-01234567",
                "--os-principal-ref",
                "principal-01234567",
                "--execution-context",
                "INTERACTIVE_PRINCIPAL",
                "--claude-binary",
                str(binary),
            ]
        )
        == 0
    )
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["schema"] == module.SCHEMA
    assert len(invocations) == 2
    assert invocations[0][0][0] == invocations[1][0][0]
    assert invocations[0][0][0].startswith("/dev/fd/")
    assert invocations[0][1] == invocations[1][1]


@pytest.mark.parametrize(
    "raw",
    [
        '{"loggedIn":false,"loggedIn":true,"authMethod":"claude.ai","apiProvider":"firstParty"}',
        '{"loggedIn":true,"authMethod":"api_key","authMethod":"claude.ai","apiProvider":"firstParty"}',
        '{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"other","apiProvider":"firstParty"}',
        '{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"firstParty","email":"a@example.com","email":"b@example.com"}',
    ],
)
def test_f5_auth_json_rejects_duplicate_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw: str
):
    module = _load()
    binary = _executable(tmp_path)
    monkeypatch.setattr(
        module,
        "_run",
        lambda argv, **kwargs: module.CommandObservation(0, raw),
    )

    with pytest.raises(module.PreflightError, match="^AUTH_STATUS_UNSUPPORTED$"):
        module.observe_auth(binary)


def test_f5_auth_json_is_byte_bounded_before_normalization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)
    monkeypatch.setattr(module, "MAX_AUTH_JSON_BYTES", 128, raising=False)
    raw = json.dumps(
        {
            "loggedIn": True,
            "authMethod": "claude.ai",
            "apiProvider": "firstParty",
            "email": "a" * 256,
        }
    )
    monkeypatch.setattr(
        module,
        "_run",
        lambda argv, **kwargs: module.CommandObservation(0, raw),
    )

    with pytest.raises(module.PreflightError, match="^AUTH_STATUS_UNSUPPORTED$"):
        module.observe_auth(binary)


@pytest.mark.parametrize(
    "private_value",
    [
        {"nested": "private@example.com"},
        ["private@example.com"],
        float("nan"),
    ],
)
def test_f5_auth_json_rejects_nonprimitive_private_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    private_value,
):
    module = _load()
    binary = _executable(tmp_path)
    raw = json.dumps(
        {
            "loggedIn": True,
            "authMethod": "claude.ai",
            "apiProvider": "firstParty",
            "email": private_value,
        }
    )
    monkeypatch.setattr(
        module,
        "_run",
        lambda argv, **kwargs: module.CommandObservation(0, raw),
    )

    with pytest.raises(module.PreflightError, match="^AUTH_STATUS_UNSUPPORTED$"):
        module.observe_auth(binary)


def test_f5_auth_json_rejects_malformed_utf8_without_echo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)
    raw = b'{"loggedIn":true,"email":"\xff"}'
    monkeypatch.setattr(
        module,
        "_run",
        lambda argv, **kwargs: module.CommandObservation(0, raw),
    )

    with pytest.raises(module.PreflightError, match="^AUTH_STATUS_UNSUPPORTED$") as exc:
        module.observe_auth(binary)
    assert "\\xff" not in str(exc.value)
