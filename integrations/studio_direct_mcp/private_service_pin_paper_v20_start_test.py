"""Native-pool selected seat may start after ONLY the reviewed Paper v20 CAS.

This leaves native-pool transaction state untouched and rejects unrelated drift.
"""
import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import private_service as svc
import private_service_pin as pin


def canonical(obj):
    return json.dumps(obj, indent=2, sort_keys=True).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class PaperV20PostpinStartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()
        self.roots = {}
        for n in ("config", "manifest"):
            p = self.home / (n + ".json")
            p.touch(mode=0o600)
            p.chmod(0o600)
            self.roots[n] = p
        self.account = svc.C2_PAPER_ACCOUNT
        self.pinned_cfg = {
            "accountLabel": self.account, "paperDesign": svc._paper_design_config(self.home),
            "fleetStatus": {"fabricLauncherSha256": "f" * 64},
            "otherExistingCapabilities": {"preserve": True},
        }
        self.old_bytes = canonical(self.pinned_cfg)
        self.original_manifest = {
            "account": self.account, "configHash": sha(self.old_bytes),
            "files": {"paper-design.mjs": "a" * 64}, "port": 45026,
        }
        self.raw = {
            "config.after.json": self.old_bytes,
            "manifest.after.json": canonical(self.original_manifest),
        }
        self.plan = {
            "manifest_after": svc.C2_PAPER_V12_MANIFEST_SHA256,
            "config_mode": 0o600, "manifest_mode": 0o600,
        }
        self.new_cfg = copy.deepcopy(self.pinned_cfg)
        self.new_cfg["paperDesign"] = svc._paper_design_config(
            self.home, rel=svc.PAPER_RUNTIME_V20_REL,
            bridge_sha256=svc.PAPER_V20_BRIDGE_SHA256)
        self.new_config = canonical(self.new_cfg)
        new_manifest = copy.deepcopy(self.original_manifest)
        new_manifest["configHash"] = sha(self.new_config)
        self.new_manifest = canonical(new_manifest)
        self.user_root = mock.patch.object(svc, "_user_root", return_value=self.home)
        self.user_root.start()
        self.addCleanup(self.user_root.stop)

    def accepted(self, **changes):
        opts = dict(svc=svc, account=self.account, roots=self.roots,
                    plan=self.plan, raw=self.raw,
                    current=self.new_config, manifest=self.new_manifest)
        opts.update(changes)
        return pin._c2_paper_v20_postpin_start(**opts)

    def test_exact_reviewed_successor_is_accepted(self):
        self.assertTrue(self.accepted())
        self.assertEqual(set(self.pinned_cfg) ^ set(self.new_cfg), set())
        self.assertEqual(
            [k for k in self.pinned_cfg if self.pinned_cfg[k] != self.new_cfg[k]],
            ["paperDesign"],
        )

    def test_unreviewed_accounts_and_predecessor_are_rejected(self):
        for account in ("chatgpt2-business", "chatgpt3", "fabric-read", "unknown"):
            with self.subTest(account=account):
                self.assertFalse(self.accepted(account=account))
        self.assertFalse(self.accepted(plan={**self.plan, "manifest_after": "f" * 64}))

    def test_drift_in_other_configuration_or_paper_target_is_rejected(self):
        for field, value in (
            ("fleetStatus", {"fabricLauncherSha256": "0" * 64}),
            ("otherExistingCapabilities", {"preserve": False}),
            ("paperDesign", {**self.new_cfg["paperDesign"], "bridgeSha256": "f" * 64}),
            ("paperDesign", {**self.new_cfg["paperDesign"], "bridgePath": "/tmp/foreign"}),
        ):
            with self.subTest(field=field, value=value):
                changed = {**self.new_cfg, field: value}
                self.assertFalse(self.accepted(current=canonical(changed)))

    def test_foreign_manifest_rollback_and_noncanonical_bytes_are_rejected(self):
        changed = json.loads(self.new_manifest)
        changed["port"] += 1
        self.assertFalse(self.accepted(manifest=canonical(changed)))
        changed = json.loads(self.new_manifest)
        changed["configHash"] = sha(self.old_bytes)
        self.assertFalse(self.accepted(manifest=canonical(changed)))
        self.assertFalse(self.accepted(current=json.dumps(self.new_cfg).encode()))
        self.assertFalse(self.accepted(manifest=self.raw["manifest.after.json"]))

    def test_wrong_modes_are_rejected(self):
        self.roots["config"].chmod(0o644)
        self.assertFalse(self.accepted())
        self.roots["config"].chmod(0o600)
        self.roots["manifest"].chmod(0o666)
        self.assertFalse(self.accepted())

    def test_real_start_gate_preserves_native_pin_result_and_pool_digest(self):
        """Exercise require_start itself with a synthetic sealed pin successor."""
        from contextlib import contextmanager
        state_root = self.home / "state"
        state_root.mkdir(mode=0o700)
        pin_root = state_root / "native-pool-pin"
        pin_root.mkdir(mode=0o700)
        roots = {**self.roots, "state": state_root}
        native_pool = self.home / "pool"
        native_pool.write_bytes(b"qualified-native-pool")
        pool_digest = sha(native_pool.read_bytes())
        plan = {
            **self.plan, "schema": pin.SCHEMA, "account": self.account,
            "uid": os.getuid(), "config_before": sha(b"native-pin-older-config"),
            "manifest_before": sha(b"native-pin-older-manifest"),
            "config_after": sha(self.old_bytes),
            "pool_target": str(native_pool), "pool_bridge": pool_digest,
            "successor_bundle": str(self.home / "successor"), "successor_digest": "a" * 64,
        }
        (pin_root / "plan.json").write_bytes(svc._fabric_release_json(plan))
        result = {"schema": pin.SCHEMA, "planSha256": pin.plan_sha(svc, plan),
                  "effect": "APPLIED"}
        (pin_root / "result.json").write_bytes(svc._fabric_release_json(result))

        @contextmanager
        def native(_args):
            yield {"phase": "SELECTED"}

        self.roots["config"].write_bytes(self.new_config)
        self.roots["manifest"].write_bytes(self.new_manifest)
        with mock.patch.object(svc, "_pin_native_context", native), \
                mock.patch.object(pin, "read_transaction", return_value=(plan, self.raw)):
            pin.require_start(svc, self.account, roots)
            with mock.patch.object(svc, "_stable_regular_file_hash", return_value="b" * 64):
                with self.assertRaisesRegex(SystemExit, "FUTURE_PIN_NOT_READY"):
                    pin.require_start(svc, self.account, roots)
            altered = copy.deepcopy(self.new_cfg)
            altered["fleetStatus"]["fabricLauncherSha256"] = "b" * 64
            self.roots["config"].write_bytes(canonical(altered))
            with self.assertRaisesRegex(SystemExit, "FUTURE_PIN_NOT_READY"):
                pin.require_start(svc, self.account, roots)




if __name__ == "__main__":
    unittest.main()
