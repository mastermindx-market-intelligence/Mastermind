from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "enroll_secondary_host.sh"


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def test_shell_syntax_is_valid() -> None:
    result = subprocess.run(
        ["/bin/bash", "-n", str(SOURCE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_interface_is_closed_and_adds_no_new_effect_authority() -> None:
    text = _source()
    assert '[ "$#" -eq 0 ]' in text
    for forbidden in (
        "--host", "--action", "--command", "--provider", "--worker-id",
        "ops/executive_os/install.sh", "provision-worker-auth.sh",
        "remote-worker-gateway", "pmset ", "launchctl ",
    ):
        assert forbidden not in text


def test_exact_protected_source_is_frozen_before_sudo() -> None:
    text = _source()
    exact = text.index('[ "$HEAD_SHA" = "$REMOTE_SHA" ]')
    clean = text.index("source checkout is not clean")
    clone = text.index("git clone --no-hardlinks --no-checkout")
    no_lazy = text.index("GIT_NO_LAZY_FETCH=1")
    partial = text.index("staged checkout retains partial-clone authority")
    fsck = text.index("fsck --full --no-dangling")
    sudo = text.index("/usr/bin/sudo -v")
    assert exact < clean < clone
    assert no_lazy < clone < partial < fsck < sudo
    assert "refs/remotes/origin/master" in text
    assert "GIT_NO_REPLACE_OBJECTS=1" in text


def test_checkout_is_hardened_before_any_root_repository_script() -> None:
    text = _source()
    chown = text.index('/usr/bin/sudo -n /usr/sbin/chown -R root:wheel "$STAGING"')
    hardened = text.index("HARDENED=1", chown)
    first_repo_effect = text.index(
        '/usr/bin/sudo -n /bin/bash "$HARDENED_SOURCE/ops/executive_os/bootstrap-host.sh"'
    )
    assert chown < hardened < first_repo_effect
    assert "source HEAD is not exact origin/master" in text
    assert "hardened checkout is not direct" in text
    assert '"/private/tmp/mastermind-secondary-enroll.${RELEASE_SHA:0:12}.XXXXXX"' in text


def test_existing_root_owners_are_composed_in_order() -> None:
    text = _source()
    bootstrap = text.index("$HARDENED_SOURCE/ops/executive_os/bootstrap-host.sh")
    provision = text.index("$HARDENED_SOURCE/ops/executive_os/provision-python-runtime.sh")
    verify = text.index(
        '$HARDENED_SOURCE/ops/executive_os/provision-python-runtime.sh" --verify-only'
    )
    privileged = text.index(
        "$HARDENED_SOURCE/ops/executive_os/prepare-secondary-privileged-host.sh"
    )
    assert bootstrap < provision < verify < privileged
    assert text.count("prepare-secondary-privileged-host.sh") == 1


def test_power_effect_unknown_is_sticky_and_never_retried() -> None:
    text = _source()
    assert 'POWER_REQUEST_ID="fleet-secondary-enroll-power-${RELEASE_SHA:0:12}"' in text
    assert text.count('"$POWER_CLIENT" --request-id "$POWER_REQUEST_ID"') == 1
    assert 'if [ "$POWER_RC" -eq 75 ]; then' in text
    assert "EFFECT_UNKNOWN" in text
    assert "exit 75" in text
    power_block = text[
        text.index("POWER_CLIENT="):text.index("RELEASE_ROOT=", text.index("POWER_CLIENT="))
    ]
    assert "for " not in power_block
    assert "while " not in power_block


def test_canonical_preflight_and_workspace_install_are_required() -> None:
    text = _source()
    preflight = text.index("--profile fleet-secondary-host-preflight/v1")
    ready = text.index('[ "$PREFLIGHT_STATE" != "READY" ]')
    repro = text.index("operator source moved during enrollment")
    workspace = text.index("install_mastermind_workspace_cli.sh")
    storage = text.index('"$HOME/.local/bin/mmx-workspace" storage')
    assert preflight < ready < repro < workspace < storage
    assert "operator origin/master moved during enrollment" in text
    assert "operator source became dirty during enrollment" in text


def test_post_effect_failure_preserves_hardened_staging_for_reconciliation() -> None:
    text = _source()
    cleanup = text.split("cleanup_unhardened() {", 1)[1].split("}\ntrap", 1)[0]
    assert '[ "$HARDENED" = "0" ]' in cleanup
    assert '/bin/rm -rf -- "$STAGING"' in cleanup
    harden = text.index("HARDENED=1")
    success_cleanup = text.rindex('/usr/bin/sudo -n /bin/rm -rf -- "$STAGING"')
    storage = text.index("WORKSPACE_STORAGE=")
    assert harden < storage < success_cleanup
    assert 'case "$STAGING" in /private/tmp/mastermind-secondary-enroll.*)' in text


def test_success_claim_stops_before_worker_or_gateway_acceptance() -> None:
    text = _source()
    assert '"schema":"mastermind.secondary_host_base_enrollment/v1"' in text
    assert '"outcome":"READY_FOR_WORKER_AND_GATEWAY_ENROLLMENT"' in text
    for forbidden_claim in (
        '"ENROLLED"', '"WORKER_READY"', '"GATEWAY_READY"', '"FLEET_READY"',
        '"PROVIDER_READY"',
    ):
        assert forbidden_claim not in text
