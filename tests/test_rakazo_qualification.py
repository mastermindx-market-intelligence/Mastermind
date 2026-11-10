"""CI entry for the pinned Rakazo HC-P1B.T1 qualification."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUALIFICATION = ROOT / "integrations" / "rakazo_qualification"
RAKAZO_PIN = "c5e66e010ee3f3166d2ad216f928a75a0b9a2218"


def qualification_launcher_env(home: Path) -> dict[str, str]:
    """Environment for the first npm/Node process.

    PATH is the only value copied from the surrounding process.
    """
    cache = home / "npm-cache"
    temp = home / "tmp"
    cache.mkdir(parents=True)
    temp.mkdir(parents=True)
    npmrc = home / ".npmrc"
    npmrc.write_text("")
    return {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "TMPDIR": str(temp),
        "LC_ALL": "C",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "npm_config_userconfig": str(npmrc),
        "npm_config_globalconfig": "/dev/null",
        "npm_config_cache": str(cache),
        "npm_config_ignore_scripts": "true",
        "npm_config_audit": "false",
        "npm_config_fund": "false",
        "npm_config_update_notifier": "false",
    }


def test_rakazo_hc_p1b_qualification_observes_pinned_source() -> None:
    with tempfile.TemporaryDirectory(prefix="rakazo-qualification-launcher-") as owned:
        home = Path(owned) / "home"
        home.mkdir()
        canary_dir = Path(owned) / "canary"
        canary_dir.mkdir()
        canary = canary_dir / "canary.cjs"
        canary.write_text("console.error('CANARY_LOADED')\n")
        canary_npmrc = canary_dir / "canary-npmrc"
        canary_npmrc.write_text("registry=http://127.0.0.1:9/canary-registry\n")
        previous = {
            key: os.environ.get(key)
            for key in ("NODE_OPTIONS", "npm_config_registry", "npm_config_userconfig")
        }
        os.environ["NODE_OPTIONS"] = f"--require {canary}"
        os.environ["npm_config_registry"] = "http://127.0.0.1:9/canary-registry"
        os.environ["npm_config_userconfig"] = str(canary_npmrc)
        try:
            env = qualification_launcher_env(home)
            assert "NODE_OPTIONS" not in env
            assert "npm_config_registry" not in env
            assert env["npm_config_userconfig"] != str(canary_npmrc)
            assert env["GIT_CONFIG_GLOBAL"] == "/dev/null"
            assert env["GIT_NO_REPLACE_OBJECTS"] == "1"
            completed = subprocess.run(
                ["npm", "test"],
                cwd=QUALIFICATION,
                env=env,
                check=False,
                text=True,
                capture_output=True,
                timeout=420,
            )
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    output = f"{completed.stdout}\n{completed.stderr}"
    if completed.returncode != 0:
        raise AssertionError(
            f"rakazo qualification exited {completed.returncode}\n{output}"
        )
    assert "CANARY_LOADED" not in output
    assert "canary-registry" not in output
    assert "launcher-env leaked" not in output
    assert "launcher-env NODE_OPTIONS absent npm-config-canary absent" in completed.stdout
    assert RAKAZO_PIN in completed.stdout
    assert "tampered donor source is rejected before import" in completed.stdout
    assert "replacement refs and clean filters do not change the pinned tree" in completed.stdout
    assert "fsmonitor and local git config do not run during validation" in completed.stdout
    assert "a symlink root and an ignored transitive shadow are rejected before import" in completed.stdout
    assert "NOT_RUN" in completed.stdout
