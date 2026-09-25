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
    workspace = text.index('WORKSPACE_INSTALLER="$SOURCE_REPO/scripts/install_"')
    assert "'mastermind'\"_workspace_cli.sh\"" in text[workspace:]
    assert '/bin/sh "$WORKSPACE_INSTALLER"' in text[workspace:]
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


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def test_protected_origin_refresh_precedes_identity_and_privilege() -> None:
    text = _source()
    env = text.index("GIT_ENV=(")
    remote = text.index('REMOTE_URL="$(')
    fetch = text.index('/usr/bin/git -C "$SOURCE_REPO" fetch')
    head = text.index('HEAD_SHA="$(')
    exact = text.index('[ "$HEAD_SHA" = "$REMOTE_SHA" ]')
    sudo = text.index("/usr/bin/sudo -v")
    assert env < remote < fetch < head < exact < sudo
    assert 'GIT_TERMINAL_PROMPT=0' in text[env:fetch]
    assert 'GIT_ASKPASS=/usr/bin/false' in text[env:fetch]
    assert 'SSH_ASKPASS=/usr/bin/false' in text[env:fetch]
    assert 'CANONICAL_REMOTE="https://github.com/mastermindx-market-intelligence/Mastermind.git"' in text
    assert 'protected origin/master refresh failed' in text


def test_stale_remote_tracking_ref_is_refreshed_and_refused_before_sudo(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    repo = tmp_path / "repo"
    sudo_marker = tmp_path / "sudo-called"
    fake_sudo = tmp_path / "sudo"
    fake_sudo.write_text(
        f"#!/bin/sh\nprintf called > {sudo_marker!s}\nexit 99\n", encoding="utf-8"
    )
    fake_sudo.chmod(0o755)
    fake_uname = tmp_path / "uname"
    fake_uname.write_text("#!/bin/sh\necho Darwin\n", encoding="utf-8")
    fake_uname.chmod(0o755)
    fake_id = tmp_path / "id"
    fake_id.write_text(
        "#!/bin/sh\nif [ \"$1\" = -u ]; then echo 501; elif [ \"$1\" = -un ]; then echo tester; else exit 64; fi\n",
        encoding="utf-8",
    )
    fake_id.chmod(0o755)

    _git("init", "--bare", str(remote))
    _git("init", "-b", "master", str(seed))
    _git("config", "user.email", "test@example.invalid", cwd=seed)
    _git("config", "user.name", "Test", cwd=seed)

    patched_source = _source().replace(
        'CANONICAL_REMOTE="https://github.com/mastermindx-market-intelligence/Mastermind.git"',
        f'CANONICAL_REMOTE="{remote}"',
    )
    patched_source = patched_source.replace("/usr/bin/sudo", str(fake_sudo))
    patched_source = patched_source.replace("/usr/bin/uname", str(fake_uname))
    patched_source = patched_source.replace("/usr/bin/id", str(fake_id))
    patched_source = patched_source.replace(
        "/private/tmp/mastermind-secondary-enroll.",
        f"{tmp_path}/mastermind-secondary-enroll.",
    )
    scripts = seed / "scripts"
    scripts.mkdir()
    (scripts / "enroll_secondary_host.sh").write_text(patched_source, encoding="utf-8")
    (seed / "README").write_text("one\n", encoding="utf-8")
    _git("add", ".", cwd=seed)
    _git("commit", "-m", "one", cwd=seed)
    _git("remote", "add", "origin", str(remote), cwd=seed)
    _git("push", "-u", "origin", "master", cwd=seed)
    _git("clone", str(remote), str(repo))

    # Advance the protected remote without refreshing the operator checkout.
    (seed / "README").write_text("two\n", encoding="utf-8")
    _git("add", "README", cwd=seed)
    _git("commit", "-m", "two", cwd=seed)
    _git("push", "origin", "master", cwd=seed)

    stale_head = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()
    stale_tracking = _git("rev-parse", "refs/remotes/origin/master", cwd=repo).stdout.strip()
    remote_head = _git("rev-parse", "HEAD", cwd=seed).stdout.strip()
    assert stale_head == stale_tracking
    assert stale_head != remote_head

    test_script = repo / "scripts" / "enroll_secondary_host.sh"
    result = subprocess.run(
        ["/bin/bash", str(test_script)], cwd=repo, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 65, result.stderr
    assert "source HEAD is not exact origin/master" in result.stderr
    assert not sudo_marker.exists()

    # The enrollment script must not update HEAD itself. Once the fixture is
    # explicitly advanced by the test operator, a fresh matching source may
    # proceed as far as the administrator boundary.
    fresh = _git("rev-parse", "refs/remotes/origin/master", cwd=repo).stdout.strip()
    _git("reset", "--hard", fresh, cwd=repo)
    result = subprocess.run(
        ["/bin/bash", str(test_script)], cwd=repo, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 99, result.stderr
    assert sudo_marker.read_text(encoding="utf-8").strip() == "called"
