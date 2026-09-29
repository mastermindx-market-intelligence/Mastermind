from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "ops/macos_screen_share/mmx-screen-share").read_text()
INSTALL = (ROOT / "ops/macos_screen_share/install.sh").read_text()


def test_screen_sharing_never_reads_or_embeds_password_material() -> None:
    assert "find-internet-password" in SCRIPT
    assert "find-internet-password -w" not in SCRIPT
    assert "setvncpw" not in SCRIPT
    assert "vnclegacy" not in SCRIPT
    assert "killall" not in SCRIPT


def test_screen_sharing_is_single_flight_and_pid_scoped() -> None:
    assert "SCREEN_SHARING_BUSY_UNMANAGED" in SCRIPT
    assert "write_lease" in SCRIPT
    assert 'close_pid "$LEASE_PID"' in SCRIPT
    assert 'screen_pid_valid "$LEASE_PID"' in SCRIPT


def test_screen_sharing_has_bounded_cleanup() -> None:
    assert "DEFAULT_TTL=1800" in SCRIPT
    assert "MAX_TTL=14400" in SCRIPT
    assert "PROMPT_GRACE=300" in SCRIPT
    assert "CANCELLED stale auth prompt" in SCRIPT


def test_screen_sharing_checks_route_and_remote_identity() -> None:
    assert '[[ "$banner" == RFB\\ 003.* ]]' in SCRIPT
    assert "route_pinned" in SCRIPT
    assert "ssh_hostkey_identity" in SCRIPT
    assert "ssh-keyscan" in SCRIPT
    assert "ssh-keygen -F" in SCRIPT
    assert '.ssh/known_hosts' in SCRIPT
    assert "StrictHostKeyChecking=accept-new" not in SCRIPT


def test_expected_fleet_targets_are_closed() -> None:
    for target, vnc, ssh in (
        ("mini1", "15901", "12201"),
        ("mini2", "15902", "12202"),
        ("mini3", "15903", "12203"),
        ("mini4", "15904", "12204"),
        ("m1studio", "15911", "12211"),
        ("m2studio", "15912", "12212"),
    ):
        assert f'{target}) echo "{target} {vnc}' in SCRIPT
        assert ssh in SCRIPT


def test_installer_uses_user_launchagent() -> None:
    assert "com.mastermind.screen-share-janitor" in INSTALL
    assert "<integer>30</integer>" in INSTALL
    assert "<string>reap</string>" in INSTALL
    assert "launchctl bootstrap" in INSTALL
