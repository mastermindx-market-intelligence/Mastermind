import json
import pytest

from integrations.mastermind_browser_plugin.native_host_install import (
    BrowserNativeHostInstallError,
    HOST_NAME,
    build_native_host_install_plan,
)

EXTENSION_ID = "abcdefghijklmnopabcdefghijklmnop"
PYTHON = "/opt/mastermind/runtime/bin/python3"
BRIDGE = "/opt/mastermind/browser-link/native/bridge.py"
CONFIG = "/Users/test/Library/Application Support/Mastermind/browser-link/enrollment.json"
SOCKET = "/Users/test/Library/Application Support/Mastermind/browser-link/owner.sock"


def plan():
    return build_native_host_install_plan(
        extension_id=EXTENSION_ID,
        python_executable=PYTHON,
        bridge_path=BRIDGE,
        enrollment_path=CONFIG,
        owner_socket_path=SOCKET,
    )


def test_plan_binds_exact_extension_origin_and_fixed_native_host_name():
    p = plan()
    assert HOST_NAME == "com.mastermind.browser_link"
    assert p.host_manifest == {
        "name": HOST_NAME,
        "description": "Mastermind Browser Link native host",
        "path": p.launcher_path,
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{EXTENSION_ID}/"],
    }
    assert p.enrollment == {
        "schema": "mastermind.browser_link.enrollment.v1",
        "extension_id": EXTENSION_ID,
        "socket_path": SOCKET,
    }
    assert p.is_installation is False
    assert p.requires_extension_distribution is True
    assert p.requires_auth0 is False


def test_launcher_pins_bridge_and_enrollment_and_only_forwards_chrome_origin_argv():
    p = plan()
    source = p.launcher_source
    assert source.startswith("#!")
    assert repr(PYTHON) in source
    assert repr(BRIDGE) in source
    assert repr(CONFIG) in source
    assert "os.execv" in source
    assert '"--config"' in source
    assert "sys.argv[1:]" in source
    assert "shell=True" not in source
    assert "subprocess" not in source
    assert "eval(" not in source


def test_install_modes_fail_closed_for_secret_and_executable_boundaries():
    p = plan()
    assert p.launcher_mode == 0o700
    assert p.enrollment_mode == 0o600
    assert p.host_manifest_mode == 0o644


@pytest.mark.parametrize(
    "extension_id",
    [
        "",
        "a" * 31,
        "a" * 33,
        "ABCDEFGHIJKLMNOPABCDEFGHIJKLMNOP",
        "qrstuvwxyzabcdefqrstuvwxyzabcdef",
        "a" * 31 + "0",
        None,
        42,
    ],
)
def test_extension_id_is_exact_chrome_id_alphabet(extension_id):
    with pytest.raises(BrowserNativeHostInstallError):
        build_native_host_install_plan(
            extension_id=extension_id,
            python_executable=PYTHON,
            bridge_path=BRIDGE,
            enrollment_path=CONFIG,
            owner_socket_path=SOCKET,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("python_executable", "python3"),
        ("python_executable", "/tmp/../python3"),
        ("bridge_path", "bridge.py"),
        ("bridge_path", "/tmp/../bridge.py"),
        ("enrollment_path", "enrollment.json"),
        ("enrollment_path", "/tmp/../enrollment.json"),
        ("owner_socket_path", "owner.sock"),
        ("owner_socket_path", "/tmp/../owner.sock"),
        ("owner_socket_path", "/"),
    ],
)
def test_all_host_paths_are_absolute_normalized(field, value):
    kwargs = {
        "extension_id": EXTENSION_ID,
        "python_executable": PYTHON,
        "bridge_path": BRIDGE,
        "enrollment_path": CONFIG,
        "owner_socket_path": SOCKET,
    }
    kwargs[field] = value
    with pytest.raises(BrowserNativeHostInstallError):
        build_native_host_install_plan(**kwargs)


def test_launcher_and_enrollment_paths_are_derived_not_model_selected():
    p = plan()
    assert p.launcher_path == CONFIG.rsplit("/", 1)[0] + "/mastermind-browser-link-host"
    value = p.to_dict()
    assert value["authority"] == {
        "install_plan_is_authority": False,
        "may_install_extension": False,
        "may_start_browser_owner": False,
        "may_mint_browser_grant": False,
        "may_link_auth0": False,
    }


def test_manifest_and_enrollment_are_json_serializable_and_secret_free():
    p = plan()
    rendered = json.dumps(
        {"manifest": p.host_manifest, "enrollment": p.enrollment},
        sort_keys=True,
    )
    for forbidden in (
        "api_key",
        "client_secret",
        "access_token",
        "refresh_token",
        "cookie",
        "password",
    ):
        assert forbidden not in rendered
