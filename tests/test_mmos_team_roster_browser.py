"""Lane TSR: static guards for roster_browser.js (no browser launched).

The rename mode was written with unit tests only and first run against a
real dev server by this lane: it died with ``CSS is not defined`` because
``CSS.escape`` (a browser global) was called in Node context while building
a locator. These tests pin the fix.
"""

import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DRIVER = REPO / "tools" / "mmos_team_server" / "roster_browser.js"


class TestRosterBrowserDriver:
    def test_no_browser_only_globals_in_node_context(self):
        code = "\n".join(line.split("//")[0] for line in DRIVER.read_text()
                         .splitlines())
        assert "CSS.escape" not in code, (
            "CSS.escape is a browser global; in Node it throws "
            "'CSS is not defined' and every rename fails (seen live on the "
            "TSR dev server). Escape attribute values in Node instead."
        )

    def test_node_syntax_ok(self):
        node = shutil.which("node")
        if not node:
            return  # browser tooling absent in this checkout; live runs need it
        proc = subprocess.run([node, "--check", str(DRIVER)],
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr
