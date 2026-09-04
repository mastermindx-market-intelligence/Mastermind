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
    with module._retain_binary(binary) as retained:
        assert module.build_allowed_argv(retained, "version") == (
            retained.execution_path,
            "--safe-mode",
            "--setting-sources",
            "",
            "--version",
        )
        assert module.build_allowed_argv(retained, "auth_status") == (
            retained.execution_path,
            "--safe-mode",
            "--setting-sources",
            "",
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
                module.build_allowed_argv(retained, forbidden)

    with pytest.raises(module.PreflightError, match="BINARY_INVALID"):
        module.build_allowed_argv(binary, "version")


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
        return module.CommandObservation(
            1,
            '{"loggedIn":false,"authMethod":"none","apiProvider":"firstParty"}',
        )

    monkeypatch.setattr(module, "_run", fake_run)
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
        module,
        "_run",
        lambda argv, **kwargs: module.CommandObservation(0, "not-json"),
    )
    with pytest.raises(module.PreflightError, match="AUTH_STATUS_UNSUPPORTED"):
        module.observe_auth(binary)


def test_auth_status_rejects_unexpected_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)

    def fail(argv, **kwargs):
        raise module.PreflightError("PROVIDER_COMMAND_FAILED")

    monkeypatch.setattr(module, "_run", fail)
    with pytest.raises(module.PreflightError, match="PROVIDER_COMMAND_FAILED") as exc:
        module.observe_auth(binary)
    assert "private@example.com" not in str(exc.value)


def test_auth_status_timeout_is_typed_and_does_not_echo_provider_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)

    def timeout(argv, **kwargs):
        raise module.PreflightError("PROVIDER_TIMEOUT")

    monkeypatch.setattr(module, "_run", timeout)
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
        module,
        "_run",
        lambda argv, **kwargs: module.CommandObservation(
            1,
            '{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"firstParty"}',
        ),
    )
    with pytest.raises(module.PreflightError, match="AUTH_STATUS_UNSUPPORTED"):
        module.observe_auth(binary)


def test_auth_status_discards_known_pii_and_raw_stderr(
    tmp_path: Path,
):
    module = _load()
    secretish = "Bearer " + "x" * 24
    provider_json = json.dumps(
        {
            "loggedIn": True,
            "authMethod": "claude.ai",
            "apiProvider": "firstParty",
            "email": "private@example.com",
            "organization": "private-org",
        },
        separators=(",", ":"),
    )
    binary = _executable(
        tmp_path,
        (
            "#!/bin/sh\n"
            f"printf '%s\\n' '{provider_json}'\n"
            f"printf '%s\\n' '{secretish}' >&2\n"
        ).encode(),
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


@pytest.mark.parametrize(
    "selector",
    [
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_FEDERATION_RULE_ID",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_API_KEY_HELPER",
    ],
)
def test_f1_every_provider_control_selector_is_a_fixed_refusal(
    monkeypatch: pytest.MonkeyPatch, selector: str
):
    module = _load()
    monkeypatch.setenv(selector, "attacker-controlled")

    with pytest.raises(module.PreflightError, match="^PROVIDER_ENV_REFUSED$") as exc:
        module._run((sys.executable, "-c", "raise SystemExit(0)"))

    assert selector not in str(exc.value)


def test_f1_secret_shaped_allowed_path_value_is_not_forwarded():
    module = _load()
    secret = "/tmp/sk-" + "x" * 30

    with pytest.raises(module.PreflightError, match="^PROVIDER_ENV_REFUSED$") as exc:
        module._closed_child_environment({"HOME": secret})

    assert secret not in str(exc.value)


def test_f1_settings_and_customizations_are_fenced_in_one_private_empty_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    user_home = tmp_path / "user-home"
    project = tmp_path / "ambient-project"
    capture = tmp_path / "fake-cli-observations.jsonl"
    user_claude = user_home / ".claude"
    project_claude = project / ".claude"

    for claude_dir, provider_value in (
        (user_claude, "https://user-settings.invalid"),
        (project_claude, "https://project-settings.invalid"),
    ):
        claude_dir.mkdir(parents=True)
        (claude_dir / "settings.json").write_text(
            json.dumps(
                {
                    "env": {"ANTHROPIC_BASE_URL": provider_value},
                    "apiKeyHelper": "/bin/false",
                    "hooks": {"SessionStart": [{"hooks": []}]},
                }
            )
        )
        (claude_dir / "CLAUDE.md").write_text("ambient instructions")
        (claude_dir / "skills").mkdir()
        (claude_dir / "skills" / "ambient.md").write_text("ambient skill")
        (claude_dir / "plugins").mkdir()
        (claude_dir / "plugins" / "ambient.json").write_text("{}")

    (project_claude / "settings.local.json").write_text(
        json.dumps({"env": {"CLAUDE_CODE_API_KEY_HELPER": "/bin/false"}})
    )
    (project / "CLAUDE.md").write_text("ambient project instructions")
    (project / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "ambient": {"command": "/bin/false", "args": []}
                }
            }
        )
    )

    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    fake_cli = _executable(
        binary_dir,
        (
            f"#!{sys.executable}\n"
            "import json\n"
            "import os\n"
            "import sys\n"
            "from pathlib import Path\n"
            f"project = Path({str(project)!r})\n"
            f"capture = Path({str(capture)!r})\n"
            "args = sys.argv[1:]\n"
            "sources = {'user', 'project', 'local'}\n"
            "if '--setting-sources' in args:\n"
            "    index = args.index('--setting-sources')\n"
            "    raw_sources = args[index + 1]\n"
            "    sources = {item for item in raw_sources.split(',') if item}\n"
            "settings_paths = []\n"
            "if 'user' in sources:\n"
            "    settings_paths.append(Path(os.environ['HOME']) / '.claude' / 'settings.json')\n"
            "if 'project' in sources:\n"
            "    settings_paths.append(project / '.claude' / 'settings.json')\n"
            "if 'local' in sources:\n"
            "    settings_paths.append(project / '.claude' / 'settings.local.json')\n"
            "effective_env = {}\n"
            "helper = None\n"
            "consulted = []\n"
            "for settings_path in settings_paths:\n"
            "    if settings_path.exists():\n"
            "        consulted.append(str(settings_path))\n"
            "        settings = json.loads(settings_path.read_text())\n"
            "        effective_env.update(settings.get('env', {}))\n"
            "        helper = settings.get('apiKeyHelper', helper)\n"
            "if '--safe-mode' not in args:\n"
            "    customization_paths = [\n"
            "        Path(os.environ['HOME']) / '.claude' / 'CLAUDE.md',\n"
            "        Path(os.environ['HOME']) / '.claude' / 'skills',\n"
            "        Path(os.environ['HOME']) / '.claude' / 'plugins',\n"
            "        project / 'CLAUDE.md',\n"
            "        project / '.mcp.json',\n"
            "    ]\n"
            "    consulted.extend(str(path) for path in customization_paths if path.exists())\n"
            "cwd = Path.cwd()\n"
            "record = {\n"
            "    'argv': args,\n"
            "    'consulted': consulted,\n"
            "    'cwd': str(cwd),\n"
            "    'cwd_entries': sorted(path.name for path in cwd.iterdir()),\n"
            "    'effective_env': effective_env,\n"
            "    'helper': helper,\n"
            "}\n"
            "with capture.open('a') as stream:\n"
            "    stream.write(json.dumps(record, sort_keys=True) + '\\n')\n"
            "if '--version' in args:\n"
            "    print('2.1.259')\n"
            "elif args[-2:] == ['auth', 'status']:\n"
            "    if effective_env or helper is not None:\n"
            "        print(json.dumps({'loggedIn': True, 'authMethod': 'api_key', 'apiProvider': 'other'}))\n"
            "    else:\n"
            "        print(json.dumps({'loggedIn': True, 'authMethod': 'claude.ai', 'apiProvider': 'firstParty'}))\n"
            "else:\n"
            "    raise SystemExit(2)\n"
        ).encode(),
    )

    monkeypatch.setenv("HOME", str(user_home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(user_claude))
    monkeypatch.chdir(project)

    with module._retain_binary(fake_cli) as retained:
        _, version = module.observe_binary(retained)
        auth = module.observe_auth(retained)

    observations = [json.loads(line) for line in capture.read_text().splitlines()]
    assert version == "2.1.259"
    assert auth == module.AuthObservation(
        auth_ready=True,
        auth_method="claudeai",
        api_provider="first_party",
        reason_codes=(),
    )
    assert [item["argv"] for item in observations] == [
        ["--safe-mode", "--setting-sources", "", "--version"],
        ["--safe-mode", "--setting-sources", "", "auth", "status"],
    ]
    assert observations[0]["cwd"] == observations[1]["cwd"]
    assert Path(observations[0]["cwd"]) != project
    assert observations[0]["cwd_entries"] == observations[1]["cwd_entries"] == []
    assert observations[0]["consulted"] == observations[1]["consulted"] == []
    assert observations[0]["effective_env"] == observations[1]["effective_env"] == {}
    assert observations[0]["helper"] is observations[1]["helper"] is None
    assert not Path(observations[0]["cwd"]).exists()


def test_f1_unavoidable_managed_policy_auth_selection_is_observed_and_refused(
    tmp_path: Path,
):
    module = _load()
    binary = _executable(
        tmp_path,
        (
            "#!/bin/sh\n"
            "printf '%s\\n' "
            "'{\"loggedIn\":true,\"authMethod\":\"api_key\",\"apiProvider\":\"other\"}'\n"
        ).encode(),
    )

    observed = module.observe_auth(binary)

    assert observed == module.AuthObservation(
        auth_ready=False,
        auth_method="non_native",
        api_provider="non_native",
        reason_codes=("NATIVE_AUTH_NOT_SELECTED",),
    )


def test_f1_private_cwd_artifact_is_refused_and_removed(tmp_path: Path):
    module = _load()
    capture = tmp_path / "observation-cwd.txt"
    binary = _executable(
        tmp_path,
        (
            f"#!{sys.executable}\n"
            "from pathlib import Path\n"
            f"capture = Path({str(capture)!r})\n"
            "cwd = Path.cwd()\n"
            "capture.write_text(str(cwd))\n"
            "(cwd / 'unexpected-artifact').write_text('unexpected')\n"
            "print('2.1.259')\n"
        ).encode(),
    )
    observation_directory: Path | None = None

    try:
        with pytest.raises(
            module.PreflightError, match="^BINARY_CHANGED_DURING_PREFLIGHT$"
        ):
            module.observe_binary(binary)
        observation_directory = Path(capture.read_text())
        assert not observation_directory.exists()
        assert not observation_directory.parent.exists()
    finally:
        if observation_directory is None and capture.exists():
            observation_directory = Path(capture.read_text())
        if observation_directory is not None and observation_directory.parent.exists():
            observation_directory.parent.chmod(0o700)
            artifact = observation_directory / "unexpected-artifact"
            if artifact.exists() or artifact.is_symlink():
                artifact.unlink()
            if observation_directory.exists():
                observation_directory.rmdir()
            copied_binary = observation_directory.parent / "claude"
            if copied_binary.exists() or copied_binary.is_symlink():
                copied_binary.unlink()
            observation_directory.parent.rmdir()


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


def test_f2_one_output_line_cannot_exceed_its_own_ceiling(
    monkeypatch: pytest.MonkeyPatch,
):
    module = _load()
    monkeypatch.setattr(module, "MAX_STDOUT_BYTES", 64, raising=False)
    monkeypatch.setattr(module, "MAX_OUTPUT_LINE_BYTES", 32, raising=False)

    with pytest.raises(module.PreflightError, match="^PROVIDER_COMMAND_FAILED$"):
        module._run(
            (
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write(b'x' * 33); sys.stdout.flush()",
            )
        )


def test_f2_idle_timeout_is_independent_of_absolute_timeout(
    monkeypatch: pytest.MonkeyPatch,
):
    module = _load()
    monkeypatch.setattr(module, "_PROVIDER_IDLE_TIMEOUT_SECONDS", 0.1)
    started = time.monotonic()

    with pytest.raises(module.PreflightError, match="^PROVIDER_TIMEOUT$"):
        module._run(
            (sys.executable, "-c", "import time; time.sleep(5)"),
            timeout_seconds=2.0,
        )

    assert time.monotonic() - started < 1.5


def test_f2_idle_timeout_still_applies_after_both_output_streams_close(
    monkeypatch: pytest.MonkeyPatch,
):
    module = _load()
    monkeypatch.setattr(module, "_PROVIDER_IDLE_TIMEOUT_SECONDS", 0.1)
    child_code = "import os,time; os.close(1); os.close(2); time.sleep(5)"
    started = time.monotonic()

    with pytest.raises(module.PreflightError, match="^PROVIDER_TIMEOUT$"):
        module._run(
            (sys.executable, "-c", child_code),
            timeout_seconds=1.0,
        )

    assert time.monotonic() - started < 0.75


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


def test_f2_cleanup_failure_takes_precedence_over_timeout(
    monkeypatch: pytest.MonkeyPatch,
):
    module = _load()

    class FakeProcess:
        pid = 43210

    monkeypatch.setattr(module, "_closed_child_environment", lambda: {})
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())

    def timeout(*args, **kwargs):
        raise module.PreflightError("PROVIDER_TIMEOUT")

    monkeypatch.setattr(module, "_collect_bounded_output", timeout)
    monkeypatch.setattr(module, "_cleanup_owned_process", lambda *args: False)

    with pytest.raises(module.PreflightError, match="^PROVIDER_COMMAND_FAILED$"):
        module._run(("/safe/provider", "--version"))


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


def test_f3_nonsticky_world_writable_parent_is_refused(tmp_path: Path):
    module = _load()
    unsafe_parent = tmp_path.resolve() / "unsafe"
    unsafe_parent.mkdir()
    unsafe_parent.chmod(0o777)
    binary = _executable(unsafe_parent)

    with pytest.raises(module.PreflightError, match="^BINARY_INVALID$"):
        module._require_binary(binary)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO probe requires POSIX")
def test_f3_fifo_leaf_is_refused_without_blocking(tmp_path: Path):
    fifo = tmp_path.resolve() / "claude"
    os.mkfifo(fifo, 0o700)
    probe = "\n".join(
        (
            "import importlib.util, sys",
            "from pathlib import Path",
            "module_path = Path(sys.argv[1])",
            "spec = importlib.util.spec_from_file_location('fifo_preflight_probe', module_path)",
            "assert spec is not None and spec.loader is not None",
            "module = importlib.util.module_from_spec(spec)",
            "sys.modules[spec.name] = module",
            "spec.loader.exec_module(module)",
            "try:",
            "    module._require_binary(Path(sys.argv[2]))",
            "except module.PreflightError as exc:",
            "    raise SystemExit(0 if str(exc) == 'BINARY_INVALID' else 2)",
            "raise SystemExit(3)",
        )
    )

    completed = subprocess.run(
        (sys.executable, "-c", probe, str(_MODULE_PATH), str(fifo)),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
        timeout=1.0,
        check=False,
        env={
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C",
            "LC_ALL": "C",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )

    assert completed.returncode == 0


def test_f3_parent_coordinate_replacement_is_detected_after_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    parent = tmp_path.resolve() / "parent"
    parent.mkdir()
    binary = _executable(parent)
    moved = tmp_path.resolve() / "moved"

    def replace_parent_then_report(argv, **kwargs):
        parent.rename(moved)
        parent.symlink_to(moved, target_is_directory=True)
        return module.CommandObservation(0, "2.1.0")

    monkeypatch.setattr(module, "_run", replace_parent_then_report)
    with pytest.raises(
        module.PreflightError, match="^BINARY_CHANGED_DURING_PREFLIGHT$"
    ):
        module.observe_binary(binary)


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


def test_f4_observation_executes_private_exact_copy_not_source_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)
    invocation: dict[str, object] = {}

    def report_version(argv, **kwargs):
        invocation["argv"] = argv
        invocation["pass_fds"] = kwargs.get("pass_fds")
        invocation["launch_guard"] = kwargs.get("launch_guard")
        invocation["guard_path"] = Path(kwargs["launch_guard"].execution_path)
        return module.CommandObservation(0, "2.1.0")

    monkeypatch.setattr(module, "_run", report_version)
    _, version = module.observe_binary(binary)

    assert version == "2.1.0"
    called_argv = invocation["argv"]
    assert isinstance(called_argv, tuple)
    execution_path = Path(called_argv[0])
    assert execution_path != binary
    assert execution_path.name == "claude"
    assert execution_path.parent.name.startswith("mastermind-claude-preflight-")
    assert invocation["pass_fds"] is None
    launch_guard = invocation["launch_guard"]
    assert isinstance(launch_guard, module._RetainedExecutable)
    assert invocation["guard_path"] == execution_path
    assert not execution_path.exists()


@pytest.mark.skipif(os.name != "posix", reason="private executable copies are POSIX-only")
def test_f4_private_copy_launches_a_real_native_executable(
    monkeypatch: pytest.MonkeyPatch,
):
    module = _load()
    native_executable = Path("/usr/bin/true")
    if not native_executable.is_file():
        pytest.skip("no stable native true executable")
    for key in tuple(os.environ):
        if module._provider_environment_key_is_denied(key):
            monkeypatch.delenv(key, raising=False)

    with module._retain_binary(native_executable) as retained:
        execution_path = Path(retained.execution_path)
        observed = module._run((retained.execution_path,), launch_guard=retained)
        assert observed == module.CommandObservation(0, b"")
        assert execution_path != native_executable

    assert not execution_path.exists()
    assert not execution_path.parent.exists()


def test_f4_main_reuses_one_retained_object_for_version_and_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    module = _load()
    binary = _executable(tmp_path)
    invocations: list[
        tuple[
            tuple[str, ...],
            tuple[int, ...] | None,
            object,
        ]
    ] = []
    monkeypatch.setattr(module, "require_current_identity_owner", lambda *args: None)

    def observe(argv, **kwargs):
        invocations.append(
            (argv, kwargs.get("pass_fds"), kwargs.get("launch_guard"))
        )
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
    execution_path = Path(invocations[0][0][0])
    assert execution_path != binary
    assert execution_path.parent.name.startswith("mastermind-claude-preflight-")
    assert invocations[0][1] == invocations[1][1]
    assert isinstance(invocations[0][2], module._RetainedExecutable)
    assert invocations[0][2] is invocations[1][2]
    assert not execution_path.exists()


def test_f4_in_place_same_size_content_drift_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path, b"#!/bin/sh\n")
    original = binary.stat()

    def rewrite_then_report(argv, **kwargs):
        binary.write_bytes(b"#!/bin/no\n")
        os.utime(binary, ns=(original.st_atime_ns, original.st_mtime_ns))
        return module.CommandObservation(0, "2.1.0")

    monkeypatch.setattr(module, "_run", rewrite_then_report)
    with pytest.raises(
        module.PreflightError, match="^BINARY_CHANGED_DURING_PREFLIGHT$"
    ):
        module.observe_binary(binary)


def test_f4_mutated_private_copy_is_refused_and_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)
    execution_path: Path | None = None

    def mutate_copy_then_report(argv, **kwargs):
        nonlocal execution_path
        execution_path = Path(argv[0])
        execution_path.parent.chmod(0o700)
        execution_path.chmod(0o700)
        execution_path.write_bytes(b"#!/bin/no\n")
        return module.CommandObservation(0, "2.1.0")

    monkeypatch.setattr(module, "_run", mutate_copy_then_report)
    try:
        with pytest.raises(
            module.PreflightError, match="^BINARY_CHANGED_DURING_PREFLIGHT$"
        ):
            module.observe_binary(binary)
        assert execution_path is not None
        assert not execution_path.exists()
        assert not execution_path.parent.exists()
    finally:
        if execution_path is not None and execution_path.parent.exists():
            execution_path.parent.chmod(0o700)
            if execution_path.exists() or execution_path.is_symlink():
                execution_path.unlink()
            execution_path.parent.rmdir()


def test_f4_private_copy_creation_failure_is_a_fixed_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)
    private_detail = "private@example.com"

    def fail_to_create_scratch(*args, **kwargs):
        raise OSError(private_detail)

    monkeypatch.setattr(module.tempfile, "mkdtemp", fail_to_create_scratch)

    with pytest.raises(module.PreflightError, match="^BINARY_INVALID$") as exc:
        module._require_binary(binary)

    assert private_detail not in str(exc.value)


def test_f4_partial_private_copy_cleanup_retries_transient_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)
    real_mkdtemp = module.tempfile.mkdtemp
    real_unlink = module.os.unlink
    created_directory: Path | None = None
    attempts = 0

    def capture_mkdtemp(*args, **kwargs):
        nonlocal created_directory
        created_directory = Path(real_mkdtemp(*args, **kwargs))
        return str(created_directory)

    def refuse_fsync(descriptor: int):
        raise OSError("synthetic copy failure")

    def fail_once(path, *, dir_fd=None):
        nonlocal attempts
        if path == "claude" and dir_fd is not None:
            attempts += 1
            if attempts == 1:
                raise OSError("private@example.com")
        return real_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(module.tempfile, "mkdtemp", capture_mkdtemp)
    monkeypatch.setattr(module.os, "fsync", refuse_fsync)
    monkeypatch.setattr(module.os, "unlink", fail_once)
    try:
        with pytest.raises(module.PreflightError, match="^BINARY_INVALID$"):
            module._require_binary(binary)
        assert attempts == 2
        assert created_directory is not None
        assert not created_directory.exists()
    finally:
        monkeypatch.setattr(module.os, "unlink", real_unlink)
        if created_directory is not None and created_directory.exists():
            created_directory.chmod(0o700)
            execution_path = created_directory / "claude"
            if execution_path.exists() or execution_path.is_symlink():
                execution_path.unlink()
            created_directory.rmdir()


def test_f4_private_copy_cleanup_continues_after_chmod_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)
    retained = module._retain_binary(binary)
    execution_path = Path(retained.execution_path)
    execution_directory_fd = retained.execution_directory_fd
    real_fchmod = module.os.fchmod

    def chmod_then_fail(descriptor: int, mode: int):
        real_fchmod(descriptor, mode)
        if descriptor == execution_directory_fd and mode == 0o700:
            raise OSError("synthetic cleanup failure")

    monkeypatch.setattr(module.os, "fchmod", chmod_then_fail)
    try:
        retained.close()
        assert not execution_path.exists()
        assert not execution_path.parent.exists()
    finally:
        monkeypatch.setattr(module.os, "fchmod", real_fchmod)
        if execution_path.parent.exists():
            execution_path.parent.chmod(0o700)
            if execution_path.exists() or execution_path.is_symlink():
                execution_path.unlink()
            execution_path.parent.rmdir()


def test_f4_private_copy_cleanup_retries_a_transient_unlink_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)
    retained = module._retain_binary(binary)
    execution_path = Path(retained.execution_path)
    execution_directory_fd = retained.execution_directory_fd
    real_unlink = module.os.unlink
    attempts = 0

    def fail_once(path, *, dir_fd=None):
        nonlocal attempts
        if path == retained.execution_name and dir_fd == execution_directory_fd:
            attempts += 1
            if attempts == 1:
                raise OSError("private@example.com")
        return real_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(module.os, "unlink", fail_once)
    try:
        retained.close()
        assert attempts == 2
        assert not execution_path.exists()
        assert not execution_path.parent.exists()
    finally:
        monkeypatch.setattr(module.os, "unlink", real_unlink)
        if execution_path.parent.exists():
            execution_path.parent.chmod(0o700)
            if execution_path.exists() or execution_path.is_symlink():
                execution_path.unlink()
            execution_path.parent.rmdir()


def test_f4_private_copy_cleanup_failure_is_fixed_and_non_echoing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)
    retained = module._retain_binary(binary)
    execution_path = Path(retained.execution_path)
    execution_directory_fd = retained.execution_directory_fd
    real_unlink = module.os.unlink
    private_detail = "private@example.com"

    def refuse_unlink(path, *, dir_fd=None):
        if path == retained.execution_name and dir_fd == execution_directory_fd:
            raise OSError(private_detail)
        return real_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(module.os, "unlink", refuse_unlink)
    try:
        with pytest.raises(
            module.PreflightError, match="^BINARY_CHANGED_DURING_PREFLIGHT$"
        ) as exc:
            retained.close()
        assert private_detail not in str(exc.value)
    finally:
        monkeypatch.setattr(module.os, "unlink", real_unlink)
        if execution_path.parent.exists():
            execution_path.parent.chmod(0o700)
            if execution_path.exists() or execution_path.is_symlink():
                execution_path.unlink()
            execution_path.parent.rmdir()


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


@pytest.mark.parametrize(
    ("field", "private_value"),
    [
        ("apiKeySource", "/Users/private/.claude/credentials.json"),
        ("email", "sk-" + "x" * 30),
    ],
)
def test_f5_auth_json_rejects_private_locators_and_secret_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    private_value: str,
):
    module = _load()
    binary = _executable(tmp_path)
    raw = json.dumps(
        {
            "loggedIn": True,
            "authMethod": "claude.ai",
            "apiProvider": "firstParty",
            field: private_value,
        }
    )
    monkeypatch.setattr(
        module,
        "_run",
        lambda argv, **kwargs: module.CommandObservation(0, raw),
    )

    with pytest.raises(module.PreflightError, match="^AUTH_STATUS_UNSUPPORTED$") as exc:
        module.observe_auth(binary)
    assert private_value not in str(exc.value)


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


def test_f5_auth_json_rejects_lone_surrogate_as_fixed_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)
    raw = (
        b'{"loggedIn":true,"authMethod":"claude.ai",'
        b'"apiProvider":"firstParty","email":"\\ud800"}'
    )
    monkeypatch.setattr(
        module,
        "_run",
        lambda argv, **kwargs: module.CommandObservation(0, raw),
    )

    with pytest.raises(module.PreflightError, match="^AUTH_STATUS_UNSUPPORTED$"):
        module.observe_auth(binary)


def test_f5_auth_json_rejects_a_second_frame(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load()
    binary = _executable(tmp_path)
    raw = (
        b'{"loggedIn":true,"authMethod":"claude.ai",'
        b'"apiProvider":"firstParty"}\n{}'
    )
    monkeypatch.setattr(
        module,
        "_run",
        lambda argv, **kwargs: module.CommandObservation(0, raw),
    )

    with pytest.raises(module.PreflightError, match="^AUTH_STATUS_UNSUPPORTED$"):
        module.observe_auth(binary)
