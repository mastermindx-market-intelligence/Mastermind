"""Real generated HOST_ENV.sh semantics without SSH, provider, or credentials."""
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "integrations/session_bridge/grok_mac_qualification/bootstrap_host.sh"


def _hostenv(tmp_path: Path) -> tuple[Path, dict]:
    lines = BOOTSTRAP.read_text(encoding="utf-8").splitlines()
    starts = [
        index for index, line in enumerate(lines)
        if "cat >" in line and "HOST_ENV.sh" in line and "<<'HOST_ENV_EOF'" in line
    ]
    assert len(starts) == 1
    start = starts[0]
    end = lines.index("HOST_ENV_EOF", start + 1)
    assert lines[start + 1] == "$RPATH"
    # The outer double-quoted ENV_SCRIPT unescapes quotes and dollars, while
    # the remote quoted heredoc preserves variables for source-time expansion.
    body = "\n".join(lines[start + 2:end]).replace('\\\"', '"').replace('\\$', '$') + "\n"
    home = tmp_path / "owned-test-home"
    ext = home / "lanes" / "ext"
    ext.mkdir(parents=True)
    hostenv = ext / "HOST_ENV.sh"
    hostenv.write_text(body, encoding="utf-8")
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
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
