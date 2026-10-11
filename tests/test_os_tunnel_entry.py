import copy
import json

import pytest

from ops.executive_os.os_tunnel_entry import ROOT, SCHEMA, SERVER, launch_spec

CONFIG = {"schema": SCHEMA, "binary_sha256": "a" * 64, "server_fingerprint": "a" * 43 + "=", "relay_port": 49152}
SECRET = b"mastermind-os:" + b"x" * 48


def test_fixed_reverse_bind_and_secret_only_in_auth_environment():
    binary, argv, env = launch_spec(CONFIG, SECRET)
    assert binary == str(ROOT / "transports/chisel" / ("a" * 64) / "chisel")
    assert argv == [binary, "client", "--fingerprint", CONFIG["server_fingerprint"],
                    "--keepalive", "20s", SERVER, "R:127.0.0.1:49152:127.0.0.1:8443"]
    assert env == {"PATH": "/usr/bin:/bin", "LANG": "C", "AUTH": SECRET.decode()}
    assert SECRET.decode() not in json.dumps([binary, argv, CONFIG])


@pytest.mark.parametrize("field,value", [
    ("relay_port", True), ("relay_port", "49152"), ("relay_port", 49151), ("relay_port", 50201),
    ("binary_sha256", "../escape"), ("server_fingerprint", ""), ("server_fingerprint", "unverified"),
    ("server", "http://foreign"), ("command", "sh"), ("credential", "inline"), ("schema", "other"),
])
def test_configuration_cannot_select_arbitrary_host_path_command_or_unpinned_server(field, value):
    config = {**CONFIG, field: value}
    with pytest.raises(ValueError):
        launch_spec(config, SECRET)


@pytest.mark.parametrize("secret", [b"", b"other:" + b"x" * 48, SECRET + b"\nextra", SECRET + b"\x00",
                                    SECRET + b" ", b"mastermind-os:short"])
def test_credential_is_exact_dedicated_principal_and_bounded(secret):
    with pytest.raises(ValueError):
        launch_spec(CONFIG, secret)


def test_one_private_file_newline_is_accepted_without_mutating_the_grant():
    before = copy.deepcopy(CONFIG)
    assert launch_spec(CONFIG, SECRET + b"\n")[2]["AUTH"] == SECRET.decode()
    assert CONFIG == before
