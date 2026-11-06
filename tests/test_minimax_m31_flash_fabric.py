"""No-provider regression for MiniMax M3.1 Flash within the incumbent Fabric.

Tests are read-only: no lease, account credential, host, policy publication,
worker launch, subscription spend, or installed native-generation mutation.
"""
from __future__ import annotations

import hashlib
import importlib.util
import shutil
import tempfile
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "ops/native_fabric"
SOURCE = NATIVE / "quota_continuity/source"
# Historical Grok/continuity sources are immutable release preimages.
# Test the NEW native candidate by applying the reviewed patch in a scratch
# directory; never edit, rehash, or overwrite those accepted snapshots.
BASES = {
    "pick.py": NATIVE / "quota_continuity/candidate/pick.py",
    "sub.sh": NATIVE / "grok47/overlay/sub.sh",
    "mm_codex_exec.sh": NATIVE / "quota_continuity/candidate/mm_codex_exec.sh",
    "host_pick.py": NATIVE / "quota_continuity/source/host_pick.py",
    "placement_view.py": NATIVE / "quota_continuity/source/placement_view.py",
}
PATCH = NATIVE / "patches/minimax_m31_flash_generation24.patch"
PREIMAGE_SHA256 = {
    "pick.py": "4311200ae485ffd19b2560434e46c0c01899fbb58f0793c198292dba6004503b",
    "sub.sh": "7ceaba75dc4375bb05742b779967ade294afcc969358f610ecdb43041fa2f7d2",
    "mm_codex_exec.sh": "0c31ceaa0467e4eb82f5220adb59328677e28e48a9ea7786a09bb0d78f1919f4",
    "host_pick.py": "e5a398a0a2178abd9a79c9f9693b2528cf3a6d8b21d5829541e01158f952a092",
    "placement_view.py": "315519caa4644f9b6a431153556c5ce2080f921ce9ec4b0ddbff172517e3feb3",
}
CANDIDATE_SHA256 = {
    "pick.py": "bdc8f9ea6484735ef6a9d3b6d94b1d9d30f6bd9079360b8e02928cf0469d5e47",
    "sub.sh": "9c3db528939245bfaef8c0cb96f10fc529b14b2fb258ce4fb5c3752ad6cbf536",
    "mm_codex_exec.sh": "b77b36c5aab464ed31988ac90ce09c90f74794a12f8344311a92f2d4de3a94cb",
    "host_pick.py": "8e76d4276e4b77b55ea6845de2f0e8d44509cc2e799a1f5818516c09cb161682",
    "placement_view.py": "51b46fb6160b35fc06b6e18a2e8d1e5a68da043f57882be74b64aef4c9373b88",
}


def load_picker(path: Path):
    sys.path.insert(0, str(SOURCE))
    spec = importlib.util.spec_from_file_location("minimax_m31_test_" + path.parent.name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MiniMaxM31FlashRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="minimax-m31-native-test-")
        cls.stage = Path(cls._tmp.name)
        ext = cls.stage / "ext"
        ext.mkdir()
        for name, source in BASES.items():
            raw = source.read_bytes()
            assert hashlib.sha256(raw).hexdigest() == PREIMAGE_SHA256[name], name
            (ext / name).write_bytes(raw)
        for args in (["git", "apply", "--check", str(PATCH)],
                     ["git", "apply", str(PATCH)]):
            action = subprocess.run(args, cwd=cls.stage, capture_output=True,
                                    text=True, timeout=15)
            assert action.returncode == 0, action.stderr
        for name, expected in CANDIDATE_SHA256.items():
            assert hashlib.sha256((ext / name).read_bytes()).hexdigest() == expected, name
        cls.pickers = (ext / "pick.py",)
        cls.shells = (ext / "sub.sh",)
        cls.codex = ext / "mm_codex_exec.sh"

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self.policy = {
            "pools": {
                "minimax": {"default_model": "MiniMax-M3"},
                "glm": {"models": {"executor": "glm-5.3-flash", "operator": "glm-5.3"}},
            },
        }

    def selected(self, picker, model=None, pool="minimax"):
        # Preserve native picker model resolution and emission, but isolate
        # host/quality/capacity readers so this test cannot commission work.
        with (
            patch.object(picker, "load_pools", return_value=self.policy),
            patch.object(picker, "policy_allows", return_value=(True, "ok")),
            patch.object(picker, "_needs_ok", return_value=(True, "ok")),
            patch.object(picker, "_subject_ok", return_value=(True, "ok")),
            patch.object(picker, "hard_filter", return_value=(True, "ok")),
            patch.object(picker, "floor_demotes", return_value=False),
            patch.object(picker, "is_execute_class", return_value=False),
            patch.object(picker, "launch_policy", return_value={"allowed": True}),
        ):
            return picker._format_pick("fix_build", pool=pool,
                                       requested_model=model,
                                       host_modes={"minimax": "minimax",
                                                   "glm": "glm"})

    def test_native_patch_preserves_old_default_and_admits_only_exact_pin(self):
        for path in self.pickers:
            with self.subTest(path=path):
                picker = load_picker(path)
                self.assertEqual(
                    picker._selection_model("minimax", "fix_build",
                                            self.policy, model="MiniMax-M3.1-Flash")[0],
                    "MiniMax-M3.1-Flash",
                )
                self.assertEqual(
                    picker._selection_model("minimax", "fix_build",
                                            self.policy, model="minimax-m3")[0],
                    "MiniMax-M3",
                )
                default = self.selected(picker)
                self.assertIn("MODEL=MiniMax-M3 ", default)
                new = self.selected(picker, "MiniMax-M3.1-Flash")
                self.assertIn("POOL=minimax ", new)
                self.assertIn("MODEL=MiniMax-M3.1-Flash ", new)
                old = self.selected(picker, "MiniMax-M3")
                self.assertIn("MODEL=MiniMax-M3 ", old)

    def test_wrong_pool_and_unreviewed_model_fail_closed(self):
        for path in self.pickers:
            with self.subTest(path=path):
                picker = load_picker(path)
                for model, pool in (
                    ("MiniMax-M3.1-Flash", "glm"),
                    ("MiniMax-M3.1-Flash", None),
                    ("MiniMax-M3.1-Pro", "minimax"),
                    ("MiniMax-M3.1-Flash-Other", "minimax"),
                ):
                    with self.subTest(model=model, pool=pool):
                        result = self.selected(picker, model, pool)
                        self.assertTrue(result.startswith("NONE reason="), result)

    def test_native_host_preview_never_treats_minimax_pin_as_glm_model(self):
        for path in self.pickers:
            with self.subTest(path=path):
                picker = load_picker(path)
                original_selection = picker._selection_model
                glm_inputs = []

                def selected_model(pool, task_class, doc=None, needs=None, model=None):
                    if pool == "glm":
                        glm_inputs.append(model)
                        return "glm-5.3-flash", ""
                    if pool == "bailian":
                        return "qwen3.8-flash", ""
                    return original_selection(pool, task_class, doc, needs, model=model)

                with (
                    patch.object(picker, "load_pools", return_value=self.policy),
                    patch.object(picker, "_selection_model", side_effect=selected_model),
                    patch.object(picker, "_eligible_host_routes",
                                 return_value={"minimax": ("fixture-host", "minimax")}),
                    patch.object(picker, "policy_allows", return_value=(True, "ok")),
                    patch.object(picker, "_needs_ok", return_value=(True, "ok")),
                    patch.object(picker, "_subject_ok", return_value=(True, "ok")),
                    patch.object(picker, "hard_filter", return_value=(True, "ok")),
                    patch.object(picker, "floor_demotes", return_value=False),
                    patch.object(picker, "is_execute_class", return_value=False),
                    patch.object(picker, "launch_policy", return_value={"allowed": True}),
                ):
                    result = picker._format_pick_host(
                        "fix_build", host="auto", pool="minimax",
                        requested_model="MiniMax-M3.1-Flash",
                    )
                self.assertIn("MODEL=MiniMax-M3.1-Flash ", result)
                self.assertIn("HOST=fixture-host MODE=minimax", result)
                self.assertEqual(glm_inputs, [None])

    def test_claude_profiles_keep_1m_context_and_compaction_headroom(self):
        for path in self.shells:
            with self.subTest(path=path):
                text = path.read_text()
                body = text.split("CLAUDE_WORKER_MAX_TURNS=120\n", 1)[1]
                body = body.split("\n}\n", 1)[0] + "\n}\n"
                program = ('CLAUDE_WORKER_MAX_TURNS=120\n' + body
                           + '\n_claude_worker_profile "minimax" "$1" || exit $?\n'
                           + 'printf "%s %s %s\\n" "$CLAUDE_CODE_MAX_CONTEXT_TOKENS" '
                           + '"$CLAUDE_CODE_AUTO_COMPACT_WINDOW" "$CLAUDE_WORKER_MAX_TURNS"\n')
                for model, expected in (("MiniMax-M3", "1000000 900000 240"),
                                        ("MiniMax-M3.1-Flash", "1000000 524288 240")):
                    result = subprocess.run(
                        ["/bin/bash", "-c", program, "fixture", model],
                        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                             "POOL_TASK_COMPLEXITY": "C0_MECHANICAL"},
                        text=True, capture_output=True, timeout=8,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), expected)

    def test_m31_claude_code_uses_official_1m_model_qualifier_after_key_gate(self):
        for path in self.shells:
            with self.subTest(path=path):
                text = path.read_text()
                start = text.index('python3 "$HERE/slot.py" minimax --wait')
                guard = text.index('MINIMAX_M31_SUBSCRIPTION_KEY_REQUIRED', start)
                cli = text.index('_mm_cli_model="$2"', guard)
                self.assertLess(start, guard)
                self.assertLess(guard, cli)
                mode_start = text.index('case "$2" in', cli)
                mode_end = text.index('\nesac', mode_start) + len('\nesac')
                program = '_mm_cli_model="$2"\n' + text[mode_start:mode_end] + (
                    '\nprintf "%s\\n" "$_mm_cli_model"\n'
                )
                for supplied, expected in (
                    ("MiniMax-M3.1-Flash", "MiniMax-M3.1-Flash[1m]"),
                    ("minimax-m3.1-flash", "MiniMax-M3.1-Flash[1m]"),
                    ("MiniMax-M3", "MiniMax-M3"),
                ):
                    result = subprocess.run(
                        ["/bin/bash", "-c", program, "fixture", "fixture-cwd", supplied],
                        capture_output=True, text=True, timeout=8,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), expected)
                # Both normal and restricted vision helpers consume the exact
                # Claude Code qualifier. Provider accounting/preflight remain
                # on the original bare model and subscription key must pass first.
                finish = text.index('> "$_json" || _rc=$?', cli)
                launch = text[cli:finish]
                self.assertEqual(launch.count('--model "$_mm_cli_model"'), 2)
                self.assertNotIn('--model "$2"', launch)
                self.assertIn('capacity_preflight.py" minimax "$2"', launch)
                self.assertIn("compact=524288", text)
                self.assertIn("compact=900000", text)

    def test_m31_plan_key_gate_refuses_payg_but_preserves_legacy_m3(self):
        for path in self.shells:
            with self.subTest(path=path):
                text = path.read_text()
                self.assertLess(
                    text.index('python3 "$HERE/slot.py" minimax --wait'),
                    text.index("MINIMAX_M31_SUBSCRIPTION_KEY_REQUIRED"),
                )
                start = 'case "$2" in\n  MiniMax-M3.1-Flash|minimax-m3.1-flash)'
                clause = start + text.split(start, 1)[1]
                clause = clause.split("export ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN", 1)[0]
                program = ('ANTHROPIC_AUTH_TOKEN="$1"\n' + clause
                           + '\nprintf "ADMITTED\n"\n')
                for token, model, expected in (
                    ("sk-cp-fixture", "MiniMax-M3.1-Flash", 0),
                    ("sk-api-fixture", "MiniMax-M3.1-Flash", 78),
                    ("sk-api-fixture", "MiniMax-M3", 0),
                ):
                    test = subprocess.run(
                        ["/bin/bash", "-c", program, "fixture", token, model],
                        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                        capture_output=True, text=True, timeout=8,
                    )
                    self.assertEqual(test.returncode, expected, test.stderr)
                    self.assertNotIn(token, test.stdout + test.stderr)

        text = self.codex.read_text()
        self.assertLess(text.index("export MINIMAX_API_KEY="),
                        text.index("MINIMAX_M31_SUBSCRIPTION_KEY_REQUIRED"))
        start = 'case "$MODEL" in\n  MiniMax-M3.1-Flash|minimax-m3.1-flash)'
        clause = start + text.split(start, 1)[1]
        clause = clause.split("\nesac", 1)[0] + "\nesac\n"
        program = 'MODEL="$1"\nMINIMAX_API_KEY="$2"\n' + clause + 'echo ADMITTED\n'
        for model, token, expected in (
            ("MiniMax-M3.1-Flash", "sk-cp-fixture", 0),
            ("MiniMax-M3.1-Flash", "sk-api-fixture", 78),
            ("MiniMax-M3", "sk-api-fixture", 0),
        ):
            test = subprocess.run(
                ["/bin/bash", "-c", program, "fixture", model, token],
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                capture_output=True, text=True, timeout=8,
            )
            self.assertEqual(test.returncode, expected, test.stderr)
            self.assertNotIn(token, test.stdout + test.stderr)

    def test_codex_profile_recognizes_m31_and_rejects_excess_context(self):
        source = self.codex.read_text()
        segment = source.split("CODEX_CONTEXT_ARGS=()\n", 1)[1]
        segment = segment.split("\nSTUDIO_MCP_CODEX_OVERRIDE=", 1)[0]
        program = ('MODEL="$1"\nCODEX_CONTEXT_ARGS=()\n' + segment
                   + '\nprintf "%s\\n" "${CODEX_CONTEXT_ARGS[*]}"\n')
        for model in ("MiniMax-M3", "MiniMax-M3.1-Flash"):
            result = subprocess.run(
                ["/bin/bash", "-c", program, "fixture", model],
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                text=True, capture_output=True, timeout=8,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("model_context_window=1000000", result.stdout)
            self.assertIn("model_auto_compact_token_limit=900000", result.stdout)
        refusal = subprocess.run(
            ["/bin/bash", "-c", program, "fixture", "MiniMax-M3.1-Flash"],
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                 "POOL_MAX_CONTEXT_TOKENS": "1000001"},
            text=True, capture_output=True, timeout=8,
        )
        self.assertEqual(refusal.returncode, 78)
        self.assertIn("window_out_of_bounds", refusal.stderr)


if __name__ == "__main__":
    unittest.main()
