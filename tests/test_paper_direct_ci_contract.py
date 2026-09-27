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
