from __future__ import annotations

import os
from pathlib import Path
import shutil
import shlex
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install_datadog_vps.sh"


def _render(**overrides: str) -> subprocess.CompletedProcess[str]:
    assignments = " ".join(
        f"{key}={shlex.quote(value)}" for key, value in sorted(overrides.items())
    )
    command = f"{assignments} bash scripts/install_datadog_vps.sh --render-only".strip()
    return subprocess.run(
        ["bash", "-lc", command],
        text=True,
        capture_output=True,
        cwd=ROOT,
        env=os.environ.copy(),
        check=False,
    )
@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_rendered_config_correlates_host_logs_and_apm() -> None:
    result = _render()
    assert result.returncode == 0, result.stderr
    assert "Environment=DD_SERVICE=mastermind-api" in result.stdout
    assert 'DD_SITE="${DD_SITE:-us5.datadoghq.com}"' in SCRIPT.read_text(encoding="utf-8")
    assert "Environment=DD_ENV=production" in result.stdout
    assert "Environment=DD_LOGS_INJECTION=true" in result.stdout
    assert "service:mastermind-api" in result.stdout
    assert "team:mastermind" in result.stdout
    assert "role:authoritative-vps" in result.stdout
    assert "type: journald" in result.stdout
    assert "- mastermind.service" in result.stdout
    assert "DD_API_KEY" not in result.stdout


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_rendered_config_accepts_bounded_overrides() -> None:
    result = _render(
        DD_ENVIRONMENT="staging",
        DD_SERVICE_NAME="mastermind-canary",
        DD_TEAM="platform",
        DD_ROLE="canary-vps",
    )
    assert result.returncode == 0, result.stderr
    assert "DD_SERVICE=mastermind-canary" in result.stdout
    assert "env:staging" in result.stdout
    assert "team:platform" in result.stdout


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_render_only_rejects_unbounded_tag_values() -> None:
    result = _render(DD_SERVICE_NAME="mastermind api")
    assert result.returncode != 0
    assert "invalid tag/service token" in result.stderr


def test_installer_never_enables_high_authority_datadog_features() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "DD_APPSEC_ENABLED=true" not in text
    assert "DD_IAST_ENABLED=true" not in text
    assert "DD_PROFILING_ENABLED=true" not in text
    assert "set -x" not in text
    assert "install_script_agent7.sh" in text
    assert "DD_APM_INSTRUMENTATION_ENABLED=host" in text
    assert "DD_APM_INSTRUMENTATION_LIBRARIES" in text


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_rendered_config_tags_exact_release_sha() -> None:
    sha = "a" * 40
    result = _render(DD_RELEASE_SHA=sha)
    assert result.returncode == 0, result.stderr
    assert f"Environment=DD_VERSION={sha}" in result.stdout


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="Linux bash required")
def test_release_tag_refresher_is_optional_and_atomic(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "refresh_datadog_release_tag.sh"
    sha = "b" * 40
    env = os.environ.copy()
    env.update({"SYSTEMD_ROOT": tmp_path.as_posix(), "SYSTEMCTL_BIN": "true"})
    result = subprocess.run(["bash", "scripts/refresh_datadog_release_tag.sh", sha], cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    dropin = tmp_path / "mastermind.service.d" / "81-datadog-version.conf"
    assert not dropin.exists()

    base = dropin.parent / "80-datadog.conf"
    base.parent.mkdir(parents=True)
    base.write_text("[Service]\n", encoding="utf-8")
    result = subprocess.run(["bash", "scripts/refresh_datadog_release_tag.sh", sha], cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert dropin.read_text(encoding="utf-8") == f"[Service]\nEnvironment=DD_VERSION={sha}\n"


def test_deploy_keeps_datadog_version_aligned_with_release_and_rollback() -> None:
    deploy = (ROOT / "scripts" / "deploy_code_to_vps.sh").read_text(encoding="utf-8")
    assert "refresh_datadog_release_tag.sh' '$EXPECTED_SHA'" in deploy
    assert "Environment=DD_VERSION=%s" in deploy
    assert "'$PREVIOUS_SHA'" in deploy
    assert "systemctl daemon-reload" in deploy
