"""Real generated HOST_ENV.sh semantics without SSH, provider, or credentials."""
import os
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "integrations/session_bridge/grok_mac_qualification/bootstrap_host.sh"


def _real_emitter_script(tmp_path: Path) -> str:
    """Capture the exact dry-run ENV_SCRIPT payload, without remote dispatch."""
    hosts = tmp_path / "hosts.json"
    hosts.write_text(json.dumps({"fixture": {"ssh_alias": "fixture.invalid",
                                             "min_free_gb": 0}}), encoding="utf-8")
    env = dict(os.environ, BOOTSTRAP_HOSTS_JSON=str(hosts),
               BOOTSTRAP_SSH_CMD="false", BOOTSTRAP_RSYNC_CMD="false",
               TMPDIR=str(tmp_path))
    dry = subprocess.run(
        ["bash", str(BOOTSTRAP), "fixture", "--dry-run", "--runtime-only"],
        env=env, cwd=tmp_path, capture_output=True, text=True,
        timeout=15, check=False,
    )
    assert dry.returncode == 0, dry.stderr[-1500:]
    rows = [line.removeprefix("REMOTE HOST_ENV: ")
            for line in dry.stdout.splitlines()
            if line.startswith("REMOTE HOST_ENV: ")]
    assert len(rows) == 1, "dry-run emitted no unique host-env action"
    # Original dry-run uses bash printf %q on exactly three argv words.
    # Parse the quoted words with bash but DO NOT execute the supplied command.
    captured = subprocess.run(
        ["bash", "-c", 'set -- ' + rows[0] + '; printf "%s" "$3"'],
        env=env, cwd=tmp_path, capture_output=True, text=True,
        timeout=5, check=False,
    )
    assert captured.returncode == 0, captured.stderr[-1000:]
    script = captured.stdout
    assert '<<\'HOST_ENV_EOF\'' in script, "source-time HOME expansion guard moved"
    assert script.count("HOST_ENV_EOF") == 2
    return script


def _hostenv(tmp_path: Path) -> tuple[Path, dict]:
    # Execute only the actual locally generated shell payload in an isolated
    # fake HOME. No remote host, rsync, broker, provider or credential invoked.
    script = _real_emitter_script(tmp_path)
    home = tmp_path / "owned-test-home"
    home.mkdir(exist_ok=True)
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    generated = subprocess.run(
        ["bash", "-c", script], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=5, check=False,
    )
    assert generated.returncode == 0, generated.stderr[-1000:]
    hostenv = home / "lanes/ext/HOST_ENV.sh"
    assert hostenv.is_file(), "host-env generator failed to write local fixture"
    return hostenv, env

def _run(hostenv: Path, env: dict, command: str = '. "$HOME/lanes/ext/HOST_ENV.sh"'):
    return subprocess.run(
        ["bash", "-c", command],
        cwd=hostenv.parent, env=env, capture_output=True,
        text=True, timeout=5, check=False,
    )


def test_generated_host_environment_is_valid_shell(tmp_path):
    # Verify the outer SSH bootstrap quoting as well as the emitted script.
    outer = subprocess.run(["bash", "-n", str(BOOTSTRAP)],
                           capture_output=True, text=True, timeout=5, check=False)
    assert outer.returncode == 0, outer.stderr
    hostenv, env = _hostenv(tmp_path)
    result = subprocess.run(["bash", "-n", str(hostenv)], env=env,
                            capture_output=True, text=True, timeout=5, check=False)
    assert result.returncode == 0, result.stderr


def test_missing_optional_token_is_success_not_authentication_or_minimax_bypass(tmp_path):
    hostenv, env = _hostenv(tmp_path)
    result = _run(hostenv, env)
    assert result.returncode == 0, result.stderr
    # In a second source, the immutable checkout gate remains unopened.
    observed = _run(hostenv, env,
        '. "$HOME/lanes/ext/HOST_ENV.sh" && test -z "${MINIMAX_GIT_OBJECT_ROOT:-}"')
    assert observed.returncode == 0, observed.stderr


def test_present_failing_token_script_still_propagates_failure(tmp_path):
    hostenv, env = _hostenv(tmp_path)
    token = hostenv.parent / ".host_glm_token.sh"
    token.write_text("false\n", encoding="utf-8")
    assert _run(hostenv, env).returncode == 1


def test_present_good_optional_script_is_sourced(tmp_path):
    hostenv, env = _hostenv(tmp_path)
    token = hostenv.parent / ".host_glm_token.sh"
    token.write_text("export MMX_FIXTURE_MARKER=present\n", encoding="utf-8")
    r = _run(hostenv, env,
        '. "$HOME/lanes/ext/HOST_ENV.sh" && test "${MMX_FIXTURE_MARKER:-}" = present')
    assert r.returncode == 0, r.stderr
