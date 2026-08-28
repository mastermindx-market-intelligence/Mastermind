from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "ops" / "executive_os"
INSTALL = OPS / "install.sh"
TEMPLATE = OPS / "control.json.template"
C1_PREP = OPS / "prepare-c1-sol-state-relay.sh"


def _embedded_control_config_generator() -> str:
    source = INSTALL.read_text(encoding="utf-8")
    start_marker = "import json, os, pathlib, re, sys\nrelease_root = sys.argv.pop(1)\n"
    end_marker = '\nPY\n)\n/usr/sbin/chown "root:$CONTROL_GROUP" "$CONTROL_CONFIG"'
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def _render_default_control_config(tmp_path: Path) -> dict[str, object]:
    destination = tmp_path / "control.json"
    expected_sha = "a" * 40
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            _embedded_control_config_generator(),
            str(ROOT),
            str(destination),
            "",
            "/private/runtime",
            "/private/admin-checkout",
            "/private/workspaces",
            expected_sha,
            "/private/backups",
            "/private/receipts",
            "/private/provider-home",
            "/private/runs",
            "/private/canary.json",
            "/private/control-environment.json",
            "450",
            "451",
            "451",
            "501",
            "b" * 64,
            "0.147.0",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(destination.read_text(encoding="utf-8"))


def test_default_installer_control_config_matches_c1_unarmed_composition(tmp_path: Path) -> None:
    generated = _render_default_control_config(tmp_path)
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    prep = C1_PREP.read_text(encoding="utf-8")
    expected = {
        "ceo_ingress_launchd_socket_name": "CeoIngress",
        "ceo_ingress_peer_uid": 452,
        "ceo_ingress_socket_path": "/var/run/mastermind-executive/ceo-ingress.sock",
    }

    for key, value in expected.items():
        assert template[key] == value
        assert generated[key] == value
        assert f'"{key}"' in prep

    assert "ceo_ingress_armed" not in generated
    assert "ceo_ingress_armed" not in template
