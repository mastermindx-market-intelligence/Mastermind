"""Exercise the actual legacy local Cursor branch without a provider or broker."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "overlay" / "sub.sh"

def cursor_branch() -> str:
    text = SOURCE.read_text()
    start = text.index("\n  cursor)\n")
    end = text.index("\n  *) echo \"pool must", start)
    return text[start + 1:end]

def make_stub(directory: Path) -> None:
    (directory / "slot.py").write_text(
        "import subprocess,sys\n"
        "index=sys.argv.index('--')\n"
        "raise SystemExit(subprocess.run(sys.argv[index+1:]).returncode)\n"
    )
    (directory / "pool_ledger.py").write_text("pass\n")
    agent = directory / "cursor-agent"
    agent.write_text(
        "#!/usr/bin/env python3\nimport json,os,sys\n"
        "with open(os.environ['CURSOR_ARG_CAPTURE'],'w') as fd:"
        " json.dump(sys.argv[1:],fd)\n"
    )
    agent.chmod(0o755)

def simulate(requested_model: str):
    with tempfile.TemporaryDirectory(prefix="fabric-local-cursor-fixture-") as raw:
        root = Path(raw)
        make_stub(root)
        script = root / "exercise.sh"
        script.write_text(
            "#!/usr/bin/env bash\nset -u\n"
            'HERE="$1"; CWD="$1"; PROMPT="fixture-input"; MODEL="$2"; POOL=cursor\n'
            "case \"$POOL\" in\n" + cursor_branch()
            + "\n  *) exit 98 ;;\nesac\n"
        )
        script.chmod(0o755)
        arg_path = root / "capture.json"
        env = dict(os.environ, CURSOR_ARG_CAPTURE=str(arg_path),
                   PATH=str(root) + os.pathsep + os.environ.get("PATH", ""))
        run = subprocess.run(["bash", str(script), str(root), requested_model],
                             env=env, cwd=root, capture_output=True,
                             text=True, timeout=7)
        return run, json.loads(arg_path.read_text()) if arg_path.exists() else None

class LegacyCursorForwardingTests(unittest.TestCase):
    def test_qualified_legacy_grok_is_explicit(self):
        result, argv = simulate("cursor-grok-4.6-high")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(argv[argv.index("--model") + 1], "cursor-grok-4.6-high")
        self.assertEqual(argv[-1], "fixture-input")

    def test_existing_composer_model_forwarded(self):
        result, argv = simulate("composer-2.5")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(argv[argv.index("--model") + 1], "composer-2.5")

    def test_missing_pin_preserves_existing_default_behavior(self):
        result, argv = simulate("")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("--model", argv)
        self.assertEqual(argv[-1], "fixture-input")

    def test_new_grok47_alias_not_armed_by_forwarding_fix(self):
        for invalid in ("grok-4.7-high", "grok-4.7-xhigh",
                        "cursor-grok-4.7-high", "unknown", '$(touch bad)'):
            with self.subTest(requested=invalid):
                result, argv = simulate(invalid)
                self.assertEqual(result.returncode, 78)
                self.assertIsNone(argv)
                self.assertIn("LOCAL_CURSOR_MODEL_REFUSED", result.stderr)

    def test_distinct_remote_provider_allowlist_not_expanded(self):
        remote = (HERE / "overlay" / "native_remote.py").read_text()
        self.assertIn('"cursor": {"composer-2.5", "cursor-grok-4.6-high"}', remote)
        self.assertNotIn('"cursor": {"composer-2.5", "cursor-grok-4.6-high", "grok-4.7-high"}', remote)

if __name__ == "__main__":
    unittest.main()
