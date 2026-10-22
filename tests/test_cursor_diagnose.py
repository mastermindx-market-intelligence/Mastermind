"""Pure read-only Cursor capability census and truthful-model evidence tests."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from integrations.cursor_agent_mastermind import diagnose, install


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    install.project(root, "apply")
    return root


def test_catalog_parsing_excludes_identity_and_errors() -> None:
    models = "Available models\n\ncomposer-2.5 - Composer\n" + (
        "grok-4.7-medium - Grok 4.7\n"
        "Ignore this: john@example.com login authorization\n"
        "composer-2.5 - duplicate\n"
    )
    assert diagnose.advertised_models(models) == ["composer-2.5", "grok-4.7-medium"]
    servers = "paper: ready\nmastermindStudio: ready\nAPI_KEY=redacted\n"
    assert diagnose.mcp_servers(servers) == {"paper": "ready", "mastermindStudio": "ready"}


def test_source_role_model_pins_match_expected_inventory() -> None:
    roles = diagnose.projected_agent_models(install.ROOT)
    assert roles["mmx-repo-explorer"] == "gemini-3.7-flash-high"
    assert roles["mmx-independent-reviewer"] == "grok-4.7-medium"
    assert roles["mmx-implementation-worker"] == "composer-2.5"
    assert roles["mmx-fabric-operator"] == "inherit"


def test_census_does_not_conflate_catalog_with_runtime(repo: Path, monkeypatch) -> None:
    outputs = {
        ("agent", "--version"): (0, "2026.10.12-d47ca18\n"),
        ("agent", "--list-models"): (0, "Available models\n\ncomposer-2.5 - Composer\n"
                                           "grok-4.7-medium - Grok\n"
                                           "gemini-3.7-flash-high - Gemini\n"),
        ("agent", "mcp", "list"): (0, "paper: ready\nmastermindStudio: ready\n"),
        ("agent", "mcp", "list-tools", "mastermindStudio"): (
            0, "Tools for mastermindStudio (2):\n- paper_inspect ()\n- studio_ping ()\n"),
    }
    monkeypatch.setattr(diagnose, "bounded_probe", lambda argv: outputs[tuple(argv)])
    result = diagnose.census(repo)
    assert result["workspace_project_state"] == "READY"
    assert result["model_catalog_state"] == "ADVERTISED_ONLY"
    assert result["studio_fabric_catalog_state"] == "READ_ONLY_OR_UNRELATED_MCP"
    assert result["fabric_dispatch_authorized"] is False
    assert result["native_task_started"] is False
    assert result["observed_actual_models"] is False
    assert result["advertised_model_count"] == 3
    assert result["role_models"]["mmx-fabric-operator"]["requested_model"] == "inherit"
    assert all(not item["actual_child_model_proven"] for item in result["role_models"].values())
    assert "@" not in json.dumps(result)


def test_missing_project_remains_unqualified(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(diagnose, "bounded_probe", lambda _: (1, ""))
    result = diagnose.census(tmp_path)
    assert result["workspace_project_state"] == "PROJECT_PROJECTION_UNQUALIFIED"
    assert result["model_catalog_state"] == "NOT_OBSERVED"
    assert result["mcp_servers"] == {}
    assert result["studio_fabric_catalog_state"] == "MCP_CATALOG_UNAVAILABLE"


def test_probe_is_allowlisted() -> None:
    with pytest.raises(ValueError, match="not admitted"):
        diagnose.bounded_probe(["agent", "login"])
    with pytest.raises(ValueError, match="not admitted"):
        diagnose.bounded_probe(["agent", "--yolo", "edit something"])
    with pytest.raises(ValueError, match="not admitted"):
        diagnose.bounded_probe(["agent", "mcp", "login", "mastermindStudio"])
