"""Exact leased-account readiness without live configs, transport or providers."""
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

COMPONENT = Path(__file__).resolve().parents[1] / "integrations/session_bridge/glm_account_readiness"


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    ext = tmp_path / "ext"
    shutil.copytree(Path(__file__).parent / "fixtures/glm_account_readiness", ext)
    subprocess.run(["git", "apply", str(COMPONENT / "glm-account-readiness.patch")], cwd=ext,
                   check=True, capture_output=True, timeout=5)
    modules = []
    for name in ("glm_keys", "glm_bound_claude"):
        spec = importlib.util.spec_from_file_location(name, ext / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        modules.append(module)
    config = tmp_path / "fixture-config.json"
    monkeypatch.setenv("GLM_CONFIG", str(config))
    return ext, config, *modules


def test_generic_enabled_is_not_exact_account_readiness(candidate, capsys):
    _, config, keys, _ = candidate
    config.write_text(json.dumps(dict(api_key="legacy-fixture", model="glm-5.3",
        accounts={"leased": {"api_key": "selected-fixture"}})))
    assert keys.enabled() is True
    assert keys.cmd_account_ready(["absent"]) == 1
    assert capsys.readouterr().out == "0\n"
    assert keys.cmd_account_ready(["leased"]) == 0
    assert capsys.readouterr().out == "1\n"


@pytest.mark.parametrize("key", [None, "", 12, [], "secret\rvalue", "secret\nvalue", "secret\0value"])
def test_same_validator_rejects_bad_key_before_readiness_or_exec(candidate, key, tmp_path, capsys):
    _, config, keys, bound = candidate
    accounts = {"leased": {"api_key": key}, "other": {"api_key": "valid-sibling"}}
    config.write_text(json.dumps(dict(accounts=accounts)))
    assert keys.cmd_account_ready(["leased"]) == 1
    output = capsys.readouterr()
    assert output.out == "0\n" and output.err == ""
    with pytest.raises(bound.BindingRefused, match="account credential unavailable"):
        bound.launch(str(tmp_path), "glm-5.3-flash", "bounded packet", "", "{}", "1",
            environ=remote_env(), accounts=accounts, exec_fn=lambda *args: pytest.fail("must not exec"))


def remote_env():
    return dict(POOL_ACCOUNT="leased", POOL_LEASE_ID="original-lease", POOL_ORCHESTRATOR_ID="root",
                LANE_LEASED="1", REMOTE_SUB_RUN_ID="run", LANE_REMOTE_HOST="selected-host")


def test_actual_exec_uses_only_selected_key_and_keeps_lease_binding(candidate, tmp_path):
    _, _, _, bound = candidate
    captured = []
    accounts = {"leased": {"api_key": "selected-fixture"}, "other": {"api_key": "sibling-fixture"}}
    bound.launch(str(tmp_path), "glm-5.3", "packet", "", "{}", "1", environ=remote_env(),
                 accounts=accounts, exec_fn=lambda argv, env: captured.append((argv, env)))
    assert captured[0][1]["ANTHROPIC_AUTH_TOKEN"] == "selected-fixture"
    assert "selected-fixture" not in repr(captured[0][0])
    bad = remote_env(); bad.pop("POOL_LEASE_ID")
    with pytest.raises(bound.BindingRefused, match="binding missing"):
        bound.launch(str(tmp_path), "glm-5.3", "packet", "", "{}", "1", environ=bad,
                     accounts=accounts, exec_fn=lambda *args: pytest.fail("must not exec"))


def test_legacy_mapping_and_cli_are_bounded_and_secret_free(candidate, capsys):
    ext, config, keys, _ = candidate
    config.write_text(json.dumps(dict(api_key="fixture-never-printed")))
    assert keys.cmd_account_ready(["chairman-max"]) == 0
    assert capsys.readouterr().out == "1\n"
    assert keys.cmd_account_ready(["other"]) == 1
    assert capsys.readouterr().out == "0\n"
    r = subprocess.run([sys.executable, str(ext / "glm_keys.py"), "account-ready", "chairman-max"],
        capture_output=True, timeout=5, env=dict(os.environ, GLM_CONFIG=str(config)))
    assert (r.returncode, r.stdout, r.stderr) == (0, b"1\n", b"")


@pytest.mark.parametrize("contents", [None, "invalid JSON", "[]", '{"accounts":{"secret-name":null}}'])
def test_missing_malformed_configs_refuse_without_names_or_tracebacks(candidate, contents, capsys):
    _, config, keys, _ = candidate
    if contents is not None:
        config.write_text(contents)
    assert keys.cmd_account_ready(["leased"]) == 1
    output = capsys.readouterr()
    assert output.out == "0\n" and output.err == ""


@pytest.mark.parametrize("mode,response,rc,expected", [
    ("glm", "1", 0, 0), ("glm", "0", 1, 78), ("glm", "", 0, 78),
    ("glm", "true", 0, 78), ("glm", "1", 255, 78), ("glm-codex", "0", 1, 0)])
def test_controller_refuses_before_launch_without_account_or_host_substitution(candidate, tmp_path,
                                                                               mode, response, rc, expected):
    source = (candidate[0] / "remote_sub.sh").read_text()
    start = source.index("# The already leased GLM account")
    end = source.index("# GLM-Codex remote workers", start)
    assert source.index('log "SUPPORT_VERSION_READY') < start < source.index('log "LAUNCH stdout=')
    fake = tmp_path / "fake_transport.py"
    fake.write_text("#!/usr/bin/env python3\nimport os,sys,json\n"
                    "open(os.environ['TRACE'],'w').write(json.dumps(sys.argv[1:]))\n"
                    "print(os.environ['RESPONSE'])\nsys.exit(int(os.environ['RC']))\n")
    fake.chmod(0o700)
    trace = tmp_path / "trace.json"
    # Shell-looking account remains one quoted argument in the remote command, never executed here.
    account = "leased'; touch SHOULD_NOT_EXIST; '"
    script = 'log() { printf "%s\\n" "$*"; }\n' + source[start:end] + '\nprintf "REACHED_LAUNCH\\n"\n'
    env = dict(os.environ, MODE=mode, POOL_ACCOUNT=account, REMOTE_SUB_PYTHON=sys.executable,
        SSH_CMD=str(fake), SSH_ALIAS="original-host", SUPPORT_DIGEST="a"*64, RPATH=":", HOST_ENV=":",
        TRACE=str(trace), RESPONSE=response, RC=str(rc))
    r = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True, timeout=5)
    assert r.returncode == expected
    assert (b"REACHED_LAUNCH" in r.stdout) is (expected == 0)
    if expected == 78:
        # The incumbent adapter projects the controller's terminal rc, not the SSH rc.
        assert re.findall(rb"\brc=([0-9]+)", r.stdout) == [b"78"]
    if mode == "glm":
        import shlex
        args = json.loads(trace.read_text())
        assert args[-2] == "original-host"
        assert shlex.split(args[-1])[-1] == account
    else:
        assert not trace.exists()
    assert not (tmp_path / "SHOULD_NOT_EXIST").exists()


def test_full_controller_shell_syntax(candidate):
    subprocess.run(["bash", "-n", str(candidate[0] / "remote_sub.sh")], check=True, capture_output=True)


def test_controller_encoding_failure_has_terminal_rc_before_any_transport(candidate, tmp_path):
    source = (candidate[0] / "remote_sub.sh").read_text()
    block = source[source.index("# The already leased GLM account"):source.index("# GLM-Codex remote workers")]
    env = dict(os.environ, MODE="glm", POOL_ACCOUNT="leased", REMOTE_SUB_PYTHON="/usr/bin/false",
               SSH_CMD="/transport-must-not-run")
    result = subprocess.run(["bash", "-c", 'log() { printf "%s\\n" "$*"; }\n' + block],
        env=env, cwd=tmp_path, capture_output=True, timeout=5)
    assert result.returncode == 78
    assert result.stdout == b"GLM_ACCOUNT_READINESS_ENCODING_FAILED rc=78\n"
