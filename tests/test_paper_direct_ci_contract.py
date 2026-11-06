"""CI contract for the Paper direct runtime's independently pinned MCP SDK."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github/workflows/ci.yml"


def test_ci_runs_paper_direct_sdk_suite_in_exact_pinned_environment():
    text = CI.read_text(encoding="utf-8")
    assert "Verify Paper direct pinned MCP SDK" in text
    assert "integrations/paper_desktop/requirements-mcp.txt" in text
    assert "test_paper_direct*.py" in text
    assert "test_paper_mcp_results.py" in text
    assert "paper-direct-mcp-ci" in text


def test_sdk_gate_requires_explicit_dedicated_lane(monkeypatch):
    import paper_direct_test_support as support
    monkeypatch.setattr(support.importlib.metadata, "version", lambda name: "1.30.0")
    monkeypatch.delenv("PAPER_DIRECT_PINNED_SDK_TESTS", raising=False)
    assert support.has_pinned_mcp_sdk() is False
    monkeypatch.setenv("PAPER_DIRECT_PINNED_SDK_TESTS", "1")
    assert support.has_pinned_mcp_sdk() is True


def test_ci_marks_only_dedicated_paper_sdk_commands():
    text = CI.read_text(encoding="utf-8")
    assert text.count("PAPER_DIRECT_PINNED_SDK_TESTS=1") == 2
    assert "PAPER_DIRECT_PINNED_SDK_TESTS=1 \"$PAPER_MCP_VENV/bin/python\" -I -m unittest discover -s tests -p 'test_paper_direct*.py'" in text
    assert "PAPER_DIRECT_PINNED_SDK_TESTS=1 \"$PAPER_MCP_VENV/bin/python\" -I -m unittest discover -s tests -p 'test_paper_mcp_results.py'" in text
