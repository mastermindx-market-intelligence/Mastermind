"""Hermetic source/native integration regressions: never run a provider CLI."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "control_plane"))
sys.path.insert(0, str(ROOT / "ops/native_fabric/quota_continuity/source"))
sys.path.insert(0, str(ROOT / "ops/native_fabric/catalog_readiness"))

from native_catalog_guard import (  # noqa: E402
    GrokCatalogRefused, GrokCatalogUnsettled,
    qualify_owned_grok_worker, qualify_custodied_grok_worker,
)
from ops.native_fabric.catalog_readiness.qualify_current import (  # noqa: E402
    apply_native_remote, apply_remote_executor,
    verify_accepted_delta, verify_compatible_selected,
    ACCEPTED_DELTA, CRITICAL_CONTRACT,
)


def model_list(models=("grok-4.7", "grok-4.6"), default="grok-4.7"):
    rows = [
        ("  * " + model + " (default)" if model == default else "  - " + model)
        for model in models
    ]
    return (
        "You are logged in with grok.com.\n\nDefault model: " + default
        + "\n\nAvailable models:\n" + "\n".join(rows) + "\n"
    )


class NativeCatalogGuardTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="catalog-native-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.here = self.root / "ext"
        self.lanes = self.here / "lanes"
        self.lanes.mkdir(parents=True)
        self.run_id = "qualified-native-catalog-test"
        self.key_home = self.lanes / (self.run_id + ".grok")
        self.key_home.mkdir(mode=0o700)
        (self.key_home / "config.toml").write_text("model = 'grok-4.7'\n")
        self.auth = self.root / "auth.json"
        self.auth.write_text("{}\n")
        self.auth.chmod(0o600)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.grok = self.bin / "grok"
        self.grok.write_text("#!/bin/sh\nexit 0\n")
        self.grok.chmod(0o700)
        self.env = {
            "PATH": str(self.bin),
            "GROK_HOME": str(self.key_home),
            "GROK_AUTH_PATH": str(self.auth),
            "LANE_REMOTE_HOST": "ubuntu3",
            "LANE_LEASED": "1",
            "POOL_ACCOUNT": "default",
            "POOL_LEASE_ID": "lease-actual",
            "REMOTE_SUB_RUN_ID": self.run_id,
        }
        self.command = ["grok", "-p", "held worker", "-m", "grok-4.7"]
        self.calls = []
        self.output = model_list()
        self.returncode = 0
        self.cleanup_proven = True
        self.alter_hash = False
        self.fail_before_receipt = False

    def runner(self, argv, *, cwd, env, timeout, nice, label, receipt_path, capture_limit_bytes):
        self.calls.append((tuple(argv), label, timeout))
        self.assertEqual(tuple(argv), (str(self.grok.resolve()), "models"))
        self.assertEqual(env, self.env)
        self.assertLessEqual(timeout, 15)
        self.assertEqual(capture_limit_bytes, 8192)
        if self.fail_before_receipt:
            raise OSError("synthetic process uncertainty")
        raw = self.output.encode("utf-8")
        cleanup = {
            "census_proven": self.cleanup_proven,
            "identity_verified": self.cleanup_proven,
            "residual_count": 0 if self.cleanup_proven else 1,
            "status": "not_needed" if self.cleanup_proven else "unproven",
        }
        receipt = {
            "schema": "mastermind.local_owned_process_receipt.v1",
            "label": label, "returncode": self.returncode,
            "timed_out": False, "stdout_truncated": False,
            "stderr_truncated": False,
            "stdout_bytes": len(raw),
            "stdout_sha256": ("0" * 64 if self.alter_hash else hashlib.sha256(raw).hexdigest()),
            "cleanup": cleanup,
        }
        receipt_path.write_text(json.dumps(receipt) + "\n")
        return SimpleNamespace(
            stdout=self.output, stderr="", returncode=self.returncode,
            timed_out=False, stdout_truncated=False, stderr_truncated=False,
            cleanup_proven=self.cleanup_proven,
        )

    def qualify(self, model="grok-4.7"):
        return qualify_owned_grok_worker(
            key=self.run_id, model=model, here=self.here,
            cwd=str(self.root), env=self.env, command=self.command,
            timeout=60, nice=0, runner=self.runner,
        )

    def test_qualified_model_uses_exact_same_host_launcher(self):
        result = self.qualify()
        self.assertEqual(result, [str(self.grok.resolve()), *self.command[1:]])
        self.assertEqual(len(self.calls), 1)
        self.assertTrue((self.lanes / (self.run_id + ".model-catalog.process.jsonl")).exists())

    def test_real_owned_process_uses_fake_catalog_utility_only(self):
        """Exercise actual process-group receipt with a fake local executable."""
        from lane_runtime import run_owned_process

        self.grok.write_text(
            "#!/bin/sh\n"
            "test \"$1\" = models || exit 2\n"
            "printf '%s\\n' 'You are logged in with grok.com.' '' "
            "'Default model: grok-4.7' '' 'Available models:' "
            "'  * grok-4.7 (default)' '  - grok-4.6'\n"
        )
        self.grok.chmod(0o700)
        command = qualify_owned_grok_worker(
            key=self.run_id, model="grok-4.7",
            here=self.here, cwd=str(self.root),
            env=self.env, command=self.command,
            timeout=60, nice=0, runner=run_owned_process,
        )
        self.assertEqual(command[0], str(self.grok.resolve()))
        record = json.loads(
            (self.lanes / (self.run_id + ".model-catalog.process.jsonl")).read_text()
        )
        self.assertEqual(record["returncode"], 0)
        self.assertTrue(record["cleanup"]["census_proven"])
        self.assertEqual(record["cleanup"]["residual_count"], 0)

    def test_unavailable_model_fails_before_worker(self):
        self.output = model_list(models=("grok-4.6",), default="grok-4.6")
        with self.assertRaisesRegex(GrokCatalogRefused, "MODEL_UNAVAILABLE"):
            self.qualify()
        self.assertEqual(len(self.calls), 1)

    def test_failed_cli_and_forged_capture_refuse(self):
        self.returncode = 1
        with self.assertRaisesRegex(GrokCatalogRefused, "UTILITY_UNQUALIFIED"):
            self.qualify()
        self.assertEqual(len(self.calls), 1)

    def test_mismatched_output_digest_refuses(self):
        self.alter_hash = True
        with self.assertRaisesRegex(GrokCatalogRefused, "UTILITY_UNQUALIFIED"):
            self.qualify()

    def test_not_authenticated_banner_fails_closed(self):
        self.output = self.output.replace(
            "You are logged in with grok.com.", "You are not authenticated.")
        with self.assertRaisesRegex(GrokCatalogRefused, "GRAMMAR_REFUSED"):
            self.qualify()

    def test_prior_run_receipt_blocks_new_effect(self):
        (self.lanes / (self.run_id + ".process.jsonl")).write_text("{}")
        with self.assertRaisesRegex(GrokCatalogRefused, "PRIOR_RUN_EXISTS"):
            self.qualify()
        self.assertFalse(self.calls)

    def test_credential_scope_mismatch_blocks_new_effect(self):
        self.env["POOL_ACCOUNT"] = "unexpected"
        with self.assertRaisesRegex(GrokCatalogRefused, "SCOPE_UNQUALIFIED"):
            self.qualify()
        self.assertFalse(self.calls)

    def test_symlinked_auth_blocks_before_utility(self):
        self.auth.unlink()
        self.auth.symlink_to(self.key_home / "config.toml")
        with self.assertRaisesRegex(GrokCatalogRefused, "AUTH_IDENTITY_INVALID"):
            self.qualify()
        self.assertFalse(self.calls)

    def test_unproven_cleanup_is_not_normal_refusal(self):
        self.cleanup_proven = False
        with self.assertRaisesRegex(GrokCatalogUnsettled, "CLEANUP_UNPROVEN"):
            self.qualify()

    def test_unknown_process_exception_remains_unsettled(self):
        self.fail_before_receipt = True
        with self.assertRaisesRegex(GrokCatalogUnsettled, "EFFECT_UNKNOWN"):
            self.qualify()


    @staticmethod
    def lease_stub():
        class OriginalLeaseStub:
            def __init__(self):
                self.holds = []

            def hold_for_reconciliation(self, reason):
                self.holds.append(reason)
        return OriginalLeaseStub()

    def test_custody_clean_proof_allows_worker_command(self):
        lease = self.lease_stub()
        state = {"started": False}
        command = qualify_custodied_grok_worker(
            state=state, lease=lease,
            key=self.run_id, model="grok-4.7", here=self.here,
            cwd=str(self.root), env=self.env, command=self.command,
            timeout=60, nice=0, runner=self.runner,
        )
        self.assertEqual(command[0], str(self.grok.resolve()))
        self.assertEqual(state["catalog_unsettled"], False)
        self.assertEqual(lease.holds, [])

    def test_custody_proved_nonstart_clears_before_refusal(self):
        lease = self.lease_stub()
        state = {"started": False}
        self.env["POOL_ACCOUNT"] = "unqualified"
        with self.assertRaisesRegex(GrokCatalogRefused, "SCOPE_UNQUALIFIED"):
            qualify_custodied_grok_worker(
                state=state, lease=lease,
                key=self.run_id, model="grok-4.7", here=self.here,
                cwd=str(self.root), env=self.env, command=self.command,
                timeout=60, nice=0, runner=self.runner,
            )
        self.assertFalse(state["catalog_unsettled"])
        self.assertFalse(lease.holds)
        self.assertFalse(self.calls)

    def test_custody_unproven_utility_retains_original_lease(self):
        lease = self.lease_stub()
        state = {"started": False}
        self.cleanup_proven = False
        with self.assertRaisesRegex(GrokCatalogUnsettled, "CLEANUP_UNPROVEN"):
            qualify_custodied_grok_worker(
                state=state, lease=lease,
                key=self.run_id, model="grok-4.7", here=self.here,
                cwd=str(self.root), env=self.env, command=self.command,
                timeout=60, nice=0, runner=self.runner,
            )
        self.assertTrue(state["catalog_unsettled"])
        self.assertEqual(lease.holds, ["grok_catalog_utility_unsettled"])
        self.assertFalse(state["started"])

    def _assert_interrupted_original_custody(self, interruption, *, signal_callback):
        """Simulate a catalog process START with unproven original receipt."""
        lease = self.lease_stub()
        state = {"started": False}
        marker = self.lanes / (self.run_id + ".model-catalog.process.jsonl")
        def interrupted_runner(argv, *, receipt_path, **kwargs):
            self.calls.append(tuple(argv))
            receipt_path.write_text(json.dumps({
                "schema": "mastermind.local_owned_process_receipt.v1",
                "label": self.run_id + "-models",
                "returncode": None,
                "cleanup": {
                    "census_proven": False, "identity_verified": False,
                    "residual_count": None, "status": "process_census_unproven",
                },
            }) + "\n")
            if signal_callback:
                # The incumbent signal handler holds the same LaneLease.
                lease.hold_for_reconciliation("synthetic_signal_unproven")
            raise interruption
        with self.assertRaises(type(interruption)) as caught:
            qualify_custodied_grok_worker(
                state=state, lease=lease,
                key=self.run_id, model="grok-4.7", here=self.here,
                cwd=str(self.root), env=self.env, command=self.command,
                timeout=60, nice=0, runner=interrupted_runner,
            )
        self.assertIs(caught.exception, interruption)
        self.assertEqual(state, {"started": False, "catalog_unsettled": True})
        self.assertTrue(lease.holds)
        self.assertEqual(lease.holds[-1], "grok_catalog_utility_unsettled")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0], (str(self.grok.resolve()), "models"))
        self.assertTrue(marker.exists())
        # Run the exact terminal patch against a temporary per-run directory,
        # not installed code, and verify no false cleanup or workspace removal.
        source = ROOT / "ops/native_fabric/grok47/overlay/native_remote.py"
        patched = apply_native_remote(source.read_bytes())
        namespace = {"__name__": "native_catalog_terminal_fixture",
                     "__file__": str(source)}
        exec(compile(patched, str(source), "exec"), namespace)
        namespace["terminal"](
            self.here, self.run_id, "grok", "grok-4.7", self.env,
            False, 78, catalog_unsettled=state["catalog_unsettled"],
        )
        terminal = json.loads(
            (self.lanes / (self.run_id + ".native-terminal.json")).read_text()
        )
        self.assertIs(terminal["catalog_utility_unsettled"], True)
        self.assertIs(terminal["cleanup_proven"], False)
        self.assertTrue(self.key_home.is_dir())

    def test_systemexit_after_catalog_start_never_reports_clean(self):
        self._assert_interrupted_original_custody(
            SystemExit(143), signal_callback=False,
        )

    def test_keyboard_interrupt_after_catalog_start_never_reports_clean(self):
        self._assert_interrupted_original_custody(
            KeyboardInterrupt(), signal_callback=False,
        )

    def test_signal_callback_and_systemexit_preserve_original_receipt(self):
        self._assert_interrupted_original_custody(
            SystemExit(143), signal_callback=True,
        )

    def test_signal_callback_and_keyboard_interrupt_preserve_original_receipt(self):
        self._assert_interrupted_original_custody(
            KeyboardInterrupt(), signal_callback=True,
        )


class NativePatchContractTest(unittest.TestCase):
    def test_accepted_gen27_delta_keeps_new_diagnostics_without_overlay(self):
        previous = {"ext/fabric_task.py": "previous-task",
                    "ext/pick.py": "previous-pick",
                    "ext/remote_sub_exec.py": "unchanged-executor",
                    "ext/native_remote.py": "unchanged-remote"}
        current = dict(previous, **ACCEPTED_DELTA)
        verify_accepted_delta(previous, current)
        for mutated in (
            dict(current, **{"ext/remote_sub_exec.py": "changed"}),
            dict(current, **{"ext/pick.py": "unreviewed"}),
            {k: v for k, v in current.items() if k != "ext/native_remote.py"},
        ):
            with self.subTest(mutated=mutated):
                with self.assertRaisesRegex(ValueError, "INCUMBENT_"):
                    verify_accepted_delta(previous, mutated)

    def test_forward_compatible_native_generation_requires_stable_contract(self):
        baseline = dict(CRITICAL_CONTRACT, **{
            "ext/pick.py": "gen27-selector",
            "ext/fabric_task.py": "gen27-admission",
        })
        newer = dict(baseline, **{
            "ext/pick.py": "gen28-selector",
            "ext/fabric_task.py": "gen28-diagnostics",
        })
        verify_compatible_selected(baseline, newer)
        for altered in (
            dict(newer, **{"ext/lane_runtime.py": "changed-cleanup"}),
            dict(newer, **{"ext/native_remote.py": "changed-auth"}),
            dict(newer, **{"ext/remote_sub_exec.py": "changed-executor"}),
            dict(newer, **{"ext/unreviewed_new.py": "unexpected"}),
        ):
            with self.subTest(altered=altered):
                with self.assertRaisesRegex(ValueError, "NEW_GENERATION_"):
                    verify_compatible_selected(baseline, altered)

    def test_remote_preimage_requires_exact_native_anchor(self):
        with self.assertRaisesRegex(ValueError, "PREIMAGE_MISMATCH"):
            apply_native_remote(b"tampered native terminal code")
        with self.assertRaisesRegex(ValueError, "PREIMAGE_MISMATCH"):
            apply_remote_executor(b"tampered remote task entrypoint")

    def test_patched_owner_preserves_distinct_catalog_cleanup(self):
        preimage = (
            "def terminal(here, key, mode, model, env, started, rc, *, timing=None, output_binding=None):\n"
            "                 cleanup_proven=not started or cleanup_receipt_is_proven(cleanup or {}))\n"
        )
        patched = apply_native_remote(preimage.encode("utf-8")).decode("utf-8")
        self.assertIn("and not catalog_unsettled", patched)
        self.assertIn('catalog_utility_unsettled', patched)


if __name__ == "__main__":
    unittest.main()
