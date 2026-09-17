"""Installer must fence the dedicated C1 Relay across generation changes."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "ops" / "executive_os" / "install.sh"
RELAY_LABEL = "com.mastermind.executive.sol-state-relay"


def _slice(source: str, start: str, end: str) -> str:
    start_index = source.index(start)
    end_index = source.index(end, start_index)
    return source[start_index:end_index]


def test_installer_fences_relay_before_any_release_mutation() -> None:
    source = INSTALL.read_text(encoding="utf-8")
    assert f'RELAY_LABEL="{RELAY_LABEL}"' in source, (
        "missing dedicated C1 Relay label"
    )

    cleanup = _slice(
        source,
        "leave_installed_services_stopped() {",
        "}\ntrap leave_installed_services_stopped EXIT",
    )
    mutation = _slice(
        source,
        "trap leave_installed_services_stopped EXIT",
        'if [ ! -d "$RELEASE_ROOT" ]; then',
    )
    relay_disable = '/bin/launchctl disable "system/$RELAY_LABEL"'
    control_disable = '/bin/launchctl disable "system/$CONTROL_LABEL"'
    relay_bootout = '/bin/launchctl bootout "system/$RELAY_LABEL"'
    control_bootout = '/bin/launchctl bootout "system/$CONTROL_LABEL"'

    for block in (cleanup, mutation):
        assert relay_disable in block
        assert relay_bootout in block
        assert block.index(relay_disable) < block.index(control_disable)
        assert block.index(relay_bootout) < block.index(control_bootout)

    relay_loaded = 'print "system/$RELAY_LABEL"'
    control_loaded = 'print "system/$CONTROL_LABEL"'
    assert relay_loaded in mutation
    assert mutation.index(relay_loaded) < mutation.index(control_loaded)
    assert "relay LaunchDaemon remained loaded after bootout" in mutation

    archive = '/usr/bin/git -C "$SOURCE_REPO" archive'
    assert source.index(relay_loaded) < source.index(archive)
    assert 'RELAY_PLIST=' not in source
    assert '/bin/launchctl bootstrap "system/$RELAY_LABEL"' not in source


if __name__ == "__main__":
    test_installer_fences_relay_before_any_release_mutation()
