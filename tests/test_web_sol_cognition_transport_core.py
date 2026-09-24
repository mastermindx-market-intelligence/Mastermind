"""Production-inert pure browser cognition transport core contract."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
NODE_TEST = ROOT / "tests/web_sol_cognition_transport_core.test.cjs"
CORE = ROOT / "integrations/chairman_surfaces/web_sol_extension/cognition_transport_core.js"


def test_cognition_transport_core_node_suite() -> None:
    node = shutil.which("node")
    assert node is not None
    completed = subprocess.run(
        [node, "--test", str(NODE_TEST)],
        cwd=ROOT,
        env={**__import__("os").environ, "COGNITION_CORE": str(CORE)},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_cognition_transport_core_is_pure_and_bounded() -> None:
    source = CORE.read_text(encoding="utf-8")
    assert len(source.encode("utf-8")) <= 24 * 1024
    for forbidden in (
        "document.querySelector",
        "fetch(",
        "chrome.runtime",
        "chrome.tabs",
        "localStorage",
        "sessionStorage",
        "document.cookie",
        "WebSocket",
        "XMLHttpRequest",
    ):
        assert forbidden not in source
    assert "SUBMIT_CONTINUATION" not in source
    assert "TYPED_REENTRY" not in source
