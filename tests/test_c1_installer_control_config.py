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
C1_FIELDS = {
    "ceo_ingress_launchd_socket_name": "CeoIngress",
    "ceo_ingress_peer_uid": 452,
    "ceo_ingress_socket_path": "/var/run/mastermind-executive/ceo-ingress.sock",
}
BRIDGE_FIELDS = {
    "dialogue_observation_launchd_socket_name": "DialogueObservation",
    "dialogue_observation_peer_uid": 457,
    "dialogue_observation_socket_path": (
        "/var/run/mastermind-dialogue-observation/dialogue-observation.sock"
    ),
    "dialogue_bridge_armed": False,
    "dialogue_wake_retry_policy": {
        "max_delivery_attempts": None,
        "retry_cooldown_s": None,
        "accepted_ttl_s": None,
        "target_unavailable_backoff_s": None,
        "reenable_on_binding_rotation": True,
        "armed": False,
    },
}

APP_LEGACY_FIELDS = {
    "ceo_ingress_app_peer_uid": 458,
    "ceo_ingress_app_armed": True,
    "ceo_ingress_app_macro_root": (
        "/Library/Application Support/MastermindExecutive/macro-sources/" + "c" * 40
    ),
}
APP_READ_PYTHON = (
    "/Library/Application Support/MastermindExecutive/network-runtimes/"
    + "d" * 64
    + "/bin/python"
)


def _embedded_control_config_generator() -> str:
    source = INSTALL.read_text(encoding="utf-8")
    start_marker = "import json, os, pathlib, re, sys\nrelease_root = sys.argv.pop(1)\n"
    end_marker = '\nPY\n)\n/usr/sbin/chown "root:$CONTROL_GROUP" "$CONTROL_CONFIG"'
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def _run_default_control_config(
    tmp_path: Path,
    *,
    release_root: Path = ROOT,
    source: Path | None = None,
    app_read_python: str = "",
) -> tuple[subprocess.CompletedProcess[str], Path]:
    destination = tmp_path / "control.json"
    expected_sha = "a" * 40
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            _embedded_control_config_generator(),
            str(release_root),
            str(destination),
            str(source) if source is not None else "",
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
            app_read_python,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed, destination


def _render_default_control_config(
    tmp_path: Path,
    *,
    release_root: Path = ROOT,
) -> dict[str, object]:
    completed, destination = _run_default_control_config(
        tmp_path,
        release_root=release_root,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(destination.read_text(encoding="utf-8"))


def _synthetic_release_schema(
    tmp_path: Path,
    *,
    c1_keys: set[str],
    bridge_keys: set[str] | None = None,
) -> Path:
    release_root = tmp_path / "release"
    scripts = release_root / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "__init__.py").write_text("", encoding="utf-8")
    template_keys = set(json.loads(TEMPLATE.read_text(encoding="utf-8")))
    base_keys = template_keys - set(C1_FIELDS) - set(BRIDGE_FIELDS)
    optional_keys = sorted(base_keys | c1_keys | (bridge_keys or set()))
    (scripts / "executive_os_phase1c.py").write_text(
        "CONTROL_CONFIG_SCHEMA_VERSION = 'mastermind.executive_control_config/v1'\n"
        "_CONFIG_REQUIRED = frozenset()\n"
        f"_CONFIG_OPTIONAL = frozenset({optional_keys!r})\n",
        encoding="utf-8",
    )
    return release_root


def test_default_installer_control_config_matches_c1_unarmed_composition(tmp_path: Path) -> None:
    generated = _render_default_control_config(tmp_path)
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    prep = C1_PREP.read_text(encoding="utf-8")

    for key, value in C1_FIELDS.items():
        assert template[key] == value
        assert generated[key] == value
        assert f'"{key}"' in prep
    for key, value in BRIDGE_FIELDS.items():
        assert template[key] == value
        assert generated[key] == value
        assert f'"{key}"' in prep

    assert "ceo_ingress_armed" not in generated
    assert "ceo_ingress_armed" not in template


def test_installer_does_not_inject_c1_fields_into_pre_c1_release_schema(tmp_path: Path) -> None:
    release_root = _synthetic_release_schema(tmp_path, c1_keys=set())

    generated = _render_default_control_config(
        tmp_path,
        release_root=release_root,
    )

    assert set(C1_FIELDS).isdisjoint(generated)
    assert set(BRIDGE_FIELDS).isdisjoint(generated)
    assert "ceo_ingress_armed" not in generated


def test_installer_refuses_partial_c1_release_schema(tmp_path: Path) -> None:
    release_root = _synthetic_release_schema(
        tmp_path,
        c1_keys={"ceo_ingress_socket_path"},
    )

    completed, destination = _run_default_control_config(
        tmp_path,
        release_root=release_root,
    )

    assert completed.returncode != 0
    assert "partial CeoIngress control-config schema" in completed.stderr
    assert not destination.exists()


def test_installer_refuses_partial_dialogue_bridge_release_schema(
    tmp_path: Path,
) -> None:
    release_root = _synthetic_release_schema(
        tmp_path,
        c1_keys=set(C1_FIELDS),
        bridge_keys={"dialogue_observation_socket_path"},
    )

    completed, destination = _run_default_control_config(
        tmp_path,
        release_root=release_root,
    )

    assert completed.returncode != 0
    assert "partial Executive Dialogue Bridge control-config schema" in completed.stderr
    assert not destination.exists()


def test_installer_migrates_legacy_three_field_app_binding_with_explicit_read_python(
    tmp_path: Path,
) -> None:
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    legacy = _render_default_control_config(base_dir)
    legacy.update(APP_LEGACY_FIELDS)
    legacy.pop("ceo_ingress_app_read_python", None)
    source = tmp_path / "legacy-control.json"
    source.write_text(json.dumps(legacy), encoding="utf-8")

    output_dir = tmp_path / "migrated"
    output_dir.mkdir()
    completed, destination = _run_default_control_config(
        output_dir, source=source, app_read_python=APP_READ_PYTHON,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    migrated = json.loads(destination.read_text(encoding="utf-8"))
    for key, value in APP_LEGACY_FIELDS.items():
        assert migrated[key] == value
    assert migrated["ceo_ingress_app_read_python"] == APP_READ_PYTHON


def test_installer_refuses_app_read_python_without_existing_app_binding(
    tmp_path: Path,
) -> None:
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    source_doc = _render_default_control_config(base_dir)
    source = tmp_path / "no-app-control.json"
    source.write_text(json.dumps(source_doc), encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    completed, destination = _run_default_control_config(
        output_dir, source=source, app_read_python=APP_READ_PYTHON,
    )

    assert completed.returncode != 0
    assert "App read Python requires an existing App binding" in completed.stderr
    assert not destination.exists()


def test_installer_refuses_noncanonical_app_read_python_migration(
    tmp_path: Path,
) -> None:
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    legacy = _render_default_control_config(base_dir)
    legacy.update(APP_LEGACY_FIELDS)
    source = tmp_path / "legacy-control.json"
    source.write_text(json.dumps(legacy), encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    completed, destination = _run_default_control_config(
        output_dir, source=source, app_read_python="/tmp/python",
    )

    assert completed.returncode != 0
    assert "App read Python path is invalid" in completed.stderr
    assert not destination.exists()


def test_installer_declares_app_read_python_option() -> None:
    source = INSTALL.read_text(encoding="utf-8")
    assert '--ceo-ingress-app-read-python)' in source


def test_installer_reuses_already_migrated_app_binding_idempotently(
    tmp_path: Path,
) -> None:
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    full = _render_default_control_config(base_dir)
    full.update(APP_LEGACY_FIELDS)
    full["ceo_ingress_app_read_python"] = APP_READ_PYTHON
    source = tmp_path / "full-control.json"
    source.write_text(json.dumps(full), encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    completed, destination = _run_default_control_config(
        output_dir, source=source, app_read_python=APP_READ_PYTHON,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(destination.read_text(encoding="utf-8")) == full


def test_installer_refuses_changed_read_python_for_existing_full_binding(
    tmp_path: Path,
) -> None:
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    full = _render_default_control_config(base_dir)
    full.update(APP_LEGACY_FIELDS)
    full["ceo_ingress_app_read_python"] = APP_READ_PYTHON
    source = tmp_path / "full-control.json"
    source.write_text(json.dumps(full), encoding="utf-8")
    other = (
        "/Library/Application Support/MastermindExecutive/network-runtimes/"
        + "e" * 64
        + "/bin/python"
    )
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    completed, destination = _run_default_control_config(
        output_dir, source=source, app_read_python=other,
    )

    assert completed.returncode != 0
    assert "App read Python differs from the existing binding" in completed.stderr
    assert not destination.exists()
