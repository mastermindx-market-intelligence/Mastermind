import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_slack_agent_relay_app_manifest.py"
MANIFEST = ROOT / "config" / "slack_agent_relay_app_manifest.yaml"
SCHEMA = "mastermind.slack_agent_relay_manifest_check.v1"


def _run(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--manifest", str(path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _write_mutation(tmp_path: Path, mutate) -> Path:
    document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    mutate(document)
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def test_reviewed_agent_relay_manifest_passes() -> None:
    completed = _run(MANIFEST)

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert json.loads(completed.stdout) == {"schema": SCHEMA, "status": "PASS"}


def test_scope_widening_is_refused(tmp_path: Path) -> None:
    path = _write_mutation(
        tmp_path,
        lambda document: document["oauth_config"]["scopes"]["bot"].append(
            "chat:write.public"
        ),
    )

    completed = _run(path)

    assert completed.returncode == 2
    assert completed.stderr == ""
    assert json.loads(completed.stdout) == {
        "error": "MANIFEST_SCOPE_REFUSED",
        "schema": SCHEMA,
        "status": "ERROR",
    }


def test_transport_surface_widening_is_refused(tmp_path: Path) -> None:
    def mutate(document: dict) -> None:
        document["settings"]["socket_mode_enabled"] = True
        document["settings"]["event_subscriptions"] = {
            "bot_events": ["message.channels"]
        }

    completed = _run(_write_mutation(tmp_path, mutate))

    assert completed.returncode == 2
    assert completed.stderr == ""
    assert json.loads(completed.stdout) == {
        "error": "MANIFEST_SURFACE_REFUSED",
        "schema": SCHEMA,
        "status": "ERROR",
    }


def test_duplicate_mapping_key_is_refused(tmp_path: Path) -> None:
    malicious_settings = """settings:
  org_deploy_enabled: false
  socket_mode_enabled: true
  token_rotation_enabled: false
  is_hosted: false
"""
    text = MANIFEST.read_text(encoding="utf-8").replace(
        "settings:\n",
        malicious_settings + "settings:\n",
        1,
    )
    path = tmp_path / "duplicate-key.yaml"
    path.write_text(text, encoding="utf-8")

    completed = _run(path)

    assert completed.returncode == 2
    assert completed.stderr == ""
    assert json.loads(completed.stdout) == {
        "error": "MANIFEST_INVALID",
        "schema": SCHEMA,
        "status": "ERROR",
    }
