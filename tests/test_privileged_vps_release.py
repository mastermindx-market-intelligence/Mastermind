from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BROKER_DEPLOY = ROOT / "ops" / "executive_os" / "deploy-mastermind-vps.sh"
TRANSACTIONAL_DEPLOY = ROOT / "scripts" / "deploy_code_to_vps.sh"


def _broker_source() -> str:
    return BROKER_DEPLOY.read_text(encoding="utf-8")


def _transaction_source() -> str:
    return TRANSACTIONAL_DEPLOY.read_text(encoding="utf-8")


def test_privileged_vps_release_scripts_parse() -> None:
    for path in (BROKER_DEPLOY, TRANSACTIONAL_DEPLOY):
        result = subprocess.run(
            ["/bin/bash", "-n", str(path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert result.returncode == 0, result.stderr


def test_privileged_vps_release_has_closed_target_and_credential_coordinates() -> None:
    source = _broker_source()
    assert 'REMOTE="https://github.com/mastermindx-market-intelligence/Mastermind.git"' in source
    assert 'SOURCE_REPO="/Users/chriswong/Documents/GitHub/Mastermind"' in source
    assert 'BOXHOST="root@146.190.142.17"' in source
    assert 'DPATH="/opt/mastermind"' in source
    assert 'KEY="/Users/chriswong/.ssh/macro_dashboard_deploy_v2"' in source
    assert 'KNOWN_HOSTS="/Users/chriswong/.ssh/known_hosts"' in source
    assert "MASTERMIND_VPS_HOST:-" not in source
    assert "MASTERMIND_VPS_KEY:-" not in source
    assert "SSH_ORIGINAL_COMMAND" not in source


def test_privileged_vps_release_binds_current_master_and_installed_executor() -> None:
    source = _broker_source()
    assert '/usr/bin/sudo -H -u chriswong' in source
    assert 'GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false' in source
    assert '-c core.hooksPath=/dev/null' in source
    assert source.count('refs/heads/$BASE_BRANCH:refs/remotes/mmx-release/$BASE_BRANCH') == 2
    assert '[ "$REMOTE_SHA" = "$TARGET_SHA" ]' in source
    assert '"${GIT_OWNER[@]}" archive "$TARGET_SHA"' in source
    assert 'INSTALLED_DEPLOY="$RELEASE_ROOT/scripts/deploy_code_to_vps.sh"' in source
    assert '/usr/bin/cmp -s "$INSTALLED_DEPLOY" "$TARGET_DEPLOY"' in source
    assert 'MASTERMIND_DEPLOY_SOURCE="$TMP_ROOT/stage/"' in source
    assert 'MASTERMIND_DEPLOY_EXPECT_SHA="$TARGET_SHA"' in source
    assert 'REMOTE_SHA_BEFORE_EFFECT=' in source


def test_privileged_vps_release_preserves_effect_uncertainty() -> None:
    source = _broker_source()
    assert 'FINAL_SHA="$(remote_marker)"' in source
    assert 'remote_health_for "$TARGET_SHA"' in source
    assert 'remote_health_for "$PREVIOUS_SHA"' in source
    assert source.count("exit 75") >= 2
    assert "rollback to prior healthy release is proven" in source
    assert "final production effect is uncertain" in source


def test_transactional_deploy_supports_pinned_known_hosts_without_weakening_legacy_callers() -> None:
    source = _transaction_source()
    assert 'KNOWN_HOSTS="${MASTERMIND_VPS_KNOWN_HOSTS:-}"' in source
    assert '-o IdentitiesOnly=yes' in source
    assert 'SSH+=(-o "UserKnownHostsFile=$KNOWN_HOSTS" -o StrictHostKeyChecking=yes)' in source
    assert "printf -v RSYNC_SSH '%q ' \"${SSH[@]}\"" in source
