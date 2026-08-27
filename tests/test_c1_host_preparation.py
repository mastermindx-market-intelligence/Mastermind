from __future__ import annotations

import plistlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "ops" / "executive_os"
PREP = OPS / "prepare-c1-sol-state-relay.sh"
PLIST = OPS / "com.mastermind.executive.sol-state-relay.plist.template"


def test_c1_host_preparation_is_fixed_credential_free_and_non_arming():
    text = PREP.read_text(encoding="utf-8")

    assert 'RELAY_USER="_mastermind_sol_relay"' in text
    assert 'RELAY_GROUP="_mastermind_sol_relay"' in text
    assert 'RELAY_UID="452"' in text
    assert 'RELAY_GID="452"' in text
    assert 'RELAY_LABEL="com.mastermind.executive.sol-state-relay"' in text
    assert 'CEO_INGRESS_SOCKET="/var/run/mastermind-executive/ceo-ingress.sock"' in text
    assert 'SOL_RUNTIME_CHANNEL_ID="C0BSGABKBFY"' in text
    assert "must run as root" in text
    assert "supports macOS only" in text
    assert "/usr/bin/false" in text
    assert "pwpolicy" in text

    # This preparation wave owns no credential ceremony and may not arm a daemon.
    forbidden = (
        "auth.test",
        "slack.com",
        "chat.postMessage",
        "chat.update",
        "conversations.history",
        "--token",
        "xoxb-",
        "launchctl enable",
        "launchctl bootstrap",
        "launchctl kickstart",
    )
    for needle in forbidden:
        assert needle not in text

    assert 'launchctl disable "system/$RELAY_LABEL"' in text
    assert 'launchctl bootout "system/$RELAY_LABEL"' in text


def test_c1_host_preparation_verifies_exact_release_and_unarmed_control_config():
    text = PREP.read_text(encoding="utf-8")

    assert 'RELEASE_MANIFEST="$RELEASE_ROOT/.executive-release-manifest.json"' in text
    assert '"mastermind.executive_release_manifest/v1"' in text
    assert 'value.get("commit_sha") != expected_commit' in text
    assert 'release_manifest.py" verify' in text
    assert '"proof_base_sha": release_sha' in text
    assert '"ceo_ingress_peer_uid": 452' in text
    assert '"ceo_ingress_launchd_socket_name": "CeoIngress"' in text
    assert 'if "ceo_ingress_armed" in value' in text
    assert "0000000000000000000000000000000000000000" not in text


def test_c1_host_preparation_patches_only_dedicated_ceo_socket_boundary():
    text = PREP.read_text(encoding="utf-8")

    assert "Sockets.CeoIngress.SockPathName" in text
    assert "Sockets.CeoIngress.SockPathOwner" in text
    assert "Sockets.CeoIngress.SockPathGroup" in text
    assert "Sockets.CeoIngress.SockPathMode" in text
    assert "Sockets.Operator.SockPathOwner" in text
    assert "Sockets.Operator.SockPathGroup" in text
    assert "Sockets.Operator.SockPathMode" in text
    assert '"$CONTROL_UID:$OPS_GID:432"' in text
    assert '"$CONTROL_UID:$RELAY_GID:432"' in text


def test_c1_relay_launchd_template_has_config_only_program_and_no_socket_or_secret_env():
    document = plistlib.loads(PLIST.read_bytes())

    assert document["Label"] == "com.mastermind.executive.sol-state-relay"
    assert document["UserName"] == "__RELAY_USER__"
    assert document["GroupName"] == "__RELAY_GROUP__"
    assert document["ProgramArguments"] == [
        "__PYTHON_BINARY__",
        "-I",
        "-S",
        "-B",
        "__RELAY_ENTRYPOINT__",
        "--config",
        "__RELAY_CONFIG__",
    ]
    assert "Sockets" not in document
    assert "KeepAlive" in document and document["KeepAlive"] is True
    assert "RunAtLoad" in document and document["RunAtLoad"] is True
    assert set(document["EnvironmentVariables"]) == {
        "HOME",
        "LANG",
        "LC_ALL",
        "NO_COLOR",
        "PATH",
        "PYTHONUNBUFFERED",
        "TZ",
    }
    serialized = PLIST.read_text(encoding="utf-8").lower()
    assert "token" not in serialized
    assert "slack" not in serialized
