"""Offline contract for local Grok Build default and historical explicit model pins."""
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parent / "overlay/sub.sh"
START = "# Normalise the already-qualified Grok Build default"
END = "# Additive economic filter; all physical/project/provider gates still apply."

def qualify(model: str):
    contents = SOURCE.read_text()
    assert contents.count(START) == 1 and contents.count(END) == 1
    decision = contents.split(START, 1)[1].split(END, 1)[0]
    with tempfile.TemporaryDirectory(prefix="grok-model-default-test-") as temp:
        script = Path(temp) / "model.sh"
        script.write_text(
            "#!/bin/bash\nPOOL=grok\nMODEL=\"$1\"\n" + decision +
            "\nprintf 'RESULT_MODEL=%s\\n' \"$MODEL\"\n"
        )
        run = subprocess.run(
            ["bash", str(script), model], capture_output=True, text=True, timeout=4
        )
        return run

class LocalGrokDefaultTests(unittest.TestCase):
    def test_unpinned_build_uses_47(self):
        run = qualify("")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), "RESULT_MODEL=grok-4.7")

    def test_explicit_historical_46_stays_46(self):
        run = qualify("grok-4.6")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), "RESULT_MODEL=grok-4.6")

    def test_explicit_47_stays_47(self):
        run = qualify("grok-4.7")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), "RESULT_MODEL=grok-4.7")

    def test_unknown_models_refuse_before_provider(self):
        for bad in ("grok-4.8", "grok-4.7-high", "cursor-grok-4.6-high"):
            with self.subTest(bad=bad):
                run = qualify(bad)
                self.assertEqual(run.returncode, 78)
                self.assertIn("LOCAL_GROK_MODEL_REFUSED", run.stderr)
                self.assertNotIn("RESULT_MODEL=", run.stdout)

    def test_model_reaches_existing_cost_and_native_cli_interfaces(self):
        contents = SOURCE.read_text()
        self.assertIn('--model "$MODEL"', contents)
        self.assertIn('command += ["-m", model]', contents)
        self.assertIn("if [ \"$POOL\" = grok ]; then", contents)

if __name__ == "__main__":
    unittest.main()
