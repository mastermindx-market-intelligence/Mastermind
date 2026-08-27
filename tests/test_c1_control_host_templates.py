from __future__ import annotations

import json
import plistlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "ops" / "executive_os"


def test_control_config_template_binds_dedicated_unarmed_ceo_ingress_peer():
    document = json.loads((OPS / "control.json.template").read_text(encoding="utf-8"))

    assert document["ceo_ingress_socket_path"] == "/var/run/mastermind-executive/ceo-ingress.sock"
    assert document["ceo_ingress_launchd_socket_name"] == "CeoIngress"
    assert document["ceo_ingress_peer_uid"] == 452
    assert "ceo_ingress_armed" not in document


def test_control_launchd_uses_dedicated_ceo_ingress_group_not_operator_group():
    document = plistlib.loads(
        (OPS / "com.mastermind.executive.control.plist.template").read_bytes()
    )
    sockets = document["Sockets"]

    assert set(sockets) == {"Operator", "CeoIngress"}
    assert sockets["Operator"]["SockPathOwner"] == 450
    assert sockets["Operator"]["SockPathGroup"] == 453
    assert sockets["Operator"]["SockPathMode"] == 0o660
    assert sockets["CeoIngress"]["SockPathOwner"] == 450
    assert sockets["CeoIngress"]["SockPathGroup"] == 452
    assert sockets["CeoIngress"]["SockPathMode"] == 0o660
    assert sockets["CeoIngress"]["SockPathName"] == "__CEO_INGRESS_SOCKET__"
    assert sockets["Operator"]["SockPathName"] != sockets["CeoIngress"]["SockPathName"]
