"""Opt-in native parser test. Never starts a provider turn or reads real auth."""
import json
import os
from pathlib import Path
import re
import subprocess

import pytest

from ops.codex_fabric.orchestrator_bundle import (
    configuration_overrides, inspect_bundle, install_bundle,
)

CODEX = os.environ.get("MASTERMIND_CODEX_NATIVE_PROBE")


@pytest.mark.skipif(not CODEX, reason="explicit native Codex binary required")
def test_native_override_ceiling_survives_trusted_project_config(tmp_path):
    root = tmp_path.resolve()
    home = root / "home"; home.mkdir()
    codex_home = home / "codex"; codex_home.mkdir()
    project = root / "project"; project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True, timeout=10)
    (project / ".codex").mkdir()
    (project / ".codex/config.toml").write_text(
        '[agents]\nenabled = true\nmax_concurrent_threads_per_session = 3\n'
        'default_subagent_model = "gpt-5.6-terra"\n'
        'default_subagent_reasoning_effort = "medium"\n'
    )
    (codex_home / "config.toml").write_text(
        'cli_auth_credentials_store = "file"\n'
        'mcp_oauth_credentials_store = "file"\n'
        f'[projects.{json.dumps(str(project))}]\ntrust_level = "trusted"\n'
    )
    receipt = inspect_bundle(codex_home)
    install_bundle(codex_home, expected_bundle_digest=receipt["bundle_digest"])
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "HOME": str(home), "CODEX_HOME": str(codex_home)}

    def render(overrides):
        argv = [CODEX, "-p", "mastermind-orchestrators"]
        for item in overrides: argv.extend(["-c", item])
        argv.extend(["debug", "prompt-input", "Configuration-only diagnostic."])
        result = subprocess.run(argv, cwd=project, env=env,
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        texts = [piece.get("text", "") for msg in payload
                 for piece in msg.get("content", []) if isinstance(piece, dict)]
        multi = "\n".join(t for t in texts if "<multi_agent_role>" in t)
        slots = re.findall(r"There are (\d+) available concurrency slots", multi)
        return texts, slots

    _, uncontrolled_slots = render(())
    assert uncontrolled_slots == ["4"], "fixture no longer demonstrates project precedence"
    overrides = configuration_overrides(codex_home, expected_bundle_digest=receipt["bundle_digest"])
    texts, bounded_slots = render(overrides)
    assert bounded_slots == ["2"]
    assert any("principal, not the default worker" in text for text in texts)
    assert receipt["role_selection_proven"] is False
    assert receipt["child_enforcement_proven"] is False
    assert not (codex_home / "auth.json").exists()


@pytest.mark.skipif(not CODEX, reason="explicit native Codex binary required")
def test_native_attended_launcher_consumes_bundle_under_trusted_project(tmp_path, monkeypatch):
    from ops.codex_fabric.attended_parent import prepare_launch
    import sys

    root = tmp_path.resolve()
    home = root / 'home'; home.mkdir()
    native_home = home / 'codex'; native_home.mkdir()
    project = root / 'project'; project.mkdir()
    subprocess.run(['git', 'init', '-q', str(project)], check=True, timeout=10)
    (project / '.codex').mkdir()
    (project / '.codex/config.toml').write_text(
        'sandbox_mode="workspace-write"\n'
        'developer_instructions="PROJECT_OVERRIDE_MUST_NOT_WIN"\n'
        '[agents]\nenabled=true\nmax_concurrent_threads_per_session=3\n'
        'default_subagent_model="gpt-5.6-terra"\n'
    )
    config = native_home / 'config.toml'
    config.write_text('cli_auth_credentials_store="file"\n'
        'mcp_oauth_credentials_store="file"\n'
        '[mcp_servers.mastermind-executive]\nurl="http://127.0.0.1:18766/mcp"\n'
        f'[projects.{json.dumps(str(project))}]\ntrust_level="trusted"\n')
    initial = config.read_bytes()
    receipt = inspect_bundle(native_home)
    install_bundle(native_home, expected_bundle_digest=receipt['bundle_digest'])
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
           'HOME': str(home), 'CODEX_HOME': str(native_home)}
    # _run inherits the process environment. Replacing only Python's mapping
    # does not change the native child environment; set/unset the actual keys.
    for key in tuple(os.environ):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    source = Path(__file__).resolve().parents[1]
    plan = prepare_launch('http://127.0.0.1:18766/mcp', codex_bin=CODEX,
        python_bin=sys.executable, project_dir=project, source_root=source,
        expected_bundle_digest=receipt['bundle_digest'])
    assert plan.launch_allowed is False
    assert plan.native_auth_status in {'unsupported', 'unknown'}
    assert plan.codex_home == str(native_home)
    assert config.read_bytes() == initial
    prefix = 'mcp_servers.mastermind-executive.http_headers_helper='
    # Prompt rendering is not a model turn, but does initialize MCP. Replace the
    # auth helper before any native diagnostic so Keychain is never reached.
    argv = [prefix + json.dumps('/usr/bin/false') if value.startswith(prefix) else value
            for value in plan.argv]
    diagnostic = ['debug', 'prompt-input', 'Configuration-only diagnostic.']
    result = subprocess.run(argv + diagnostic, env=env, cwd=project, capture_output=True,
                            text=True, timeout=30)
    # Native prompt inspection initializes enabled MCP servers. The intentionally
    # unavailable fixture must refuse; this is not an authenticated launch proof.
    assert result.returncode != 0
    assert 'required MCP servers failed to initialize' in result.stderr
    # Inspect only the exact parent configuration, with the fixture connection
    # explicitly disabled. No real helper, account, server or model is contacted.
    result = subprocess.run(argv + ['-c', 'mcp_servers.mastermind-executive.enabled=false']
                            + diagnostic, env=env, cwd=project, capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    texts = [piece.get('text', '') for message in payload
             for piece in message.get('content', []) if isinstance(piece, dict)]
    multi = '\n'.join(text for text in texts if '<multi_agent_role>' in text)
    assert re.findall(r'There are (\d+) available concurrency slots', multi) == ['2']
    assert any('principal, not the default worker' in text for text in texts)
    assert not any('PROJECT_OVERRIDE_MUST_NOT_WIN' in text for text in texts)
    assert config.read_bytes() == initial
    assert not (native_home / 'auth.json').exists()
    assert plan.to_dict()['worker_dispatch_authorized'] is False

    legacy = prepare_launch('http://127.0.0.1:18766/mcp', codex_bin=CODEX,
        python_bin=sys.executable, project_dir=project, source_root=source)
    legacy_argv = [prefix + json.dumps('/usr/bin/false') if value.startswith(prefix) else value
                   for value in legacy.argv]
    result = subprocess.run(legacy_argv + ['-c', 'mcp_servers.mastermind-executive.enabled=false']
                            + diagnostic, env=env, cwd=project, capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert '<multi_agent_role>' not in result.stdout
    assert config.read_bytes() == initial
