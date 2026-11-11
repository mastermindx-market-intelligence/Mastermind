"""Only seven selected native-pool seats may compose frozen Paper v20 CAS.

Synthetic owned files and qualified in-memory cohort stand in for private M2
snapshots. Never include live credentials or host config in repository tests.
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

SEVEN_PINNED = (
    "admin-business", "chatgpt1", "chatgpt2-business", "chatgpt3",
    "chatgpt3-w570f6f34", "chatgpt3-wa2a9e6f9", "chatgpt4",
)


def bytes_for(obj):
    return json.dumps(obj, indent=2, sort_keys=True).encode("utf-8")


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


class FakeCohort:
    def __init__(self, account, original_config, original_manifest, plist, successor_config):
        self.account = account
        self.old_config = original_config
        self.old_manifest = original_manifest
        self.old_plist = plist
        self.successor_config = successor_config
        self.COHORTS = {account: {
            "config_sha256": sha(original_config),
            "manifest_sha256": sha(original_manifest),
        }}
        self.calls = []

    def plan_selection(self, account, *, manifest_bytes, config_bytes, plist_bytes, home):
        self.calls.append((account, str(home)))
        if (account != self.account or config_bytes != self.old_config
                or manifest_bytes != self.old_manifest or plist_bytes != self.old_plist):
            raise ValueError("sealed fleet predecessor changed")
        manifest = json.loads(self.old_manifest)
        manifest["configHash"] = sha(self.successor_config)
        return {"configBytes": self.successor_config,
                "manifestBytes": bytes_for(manifest)}


class FleetPostPinStartTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.home = Path(t.name).resolve() / "home"
        self.home.mkdir(mode=0o700)
        self.roots = {}
        for n in ("config", "manifest", "plist"):
            p = self.home / (n + ".json")
            p.touch(mode=0o600)
            p.chmod(0o600)
            self.roots[n] = p
        self.old_config_dict = {
            "accountLabel": "pinned",
            "paperDesign": {"bridgeSha256": "1" * 64, "generation": "v10"},
            "fleetStatus": {"fabricLauncherSha256": "a" * 64},
            "authMode": "existing",
        }
        self.old_config = bytes_for(self.old_config_dict)
        self.old_plist = b"sealed existing launchd exact bytes"
        self.old_manifest = bytes_for({
            "version": 2, "account": "pinned",
            "files": {"gateway.mjs": "2" * 64},
            "configHash": sha(self.old_config), "plistHash": sha(self.old_plist),
        })
        self.next_config_dict = copy.deepcopy(self.old_config_dict)
        self.next_config_dict["paperDesign"] = {
            "bridgeSha256": svc.PAPER_V20_BRIDGE_SHA256,
            "generation": "v20",
        }
        self.next_config = bytes_for(self.next_config_dict)
        future = json.loads(self.old_manifest)
        future["configHash"] = sha(self.next_config)
        self.next_manifest = bytes_for(future)
        self.roots["config"].write_bytes(self.next_config)
        self.roots["manifest"].write_bytes(self.next_manifest)
        self.roots["plist"].write_bytes(self.old_plist)
        self.plan = {"manifest_after": sha(self.old_manifest),
                     "config_mode": 0o600, "manifest_mode": 0o600}
        self.raw = {"manifest.after.json": self.old_manifest,
                    "config.after.json": self.old_config}
        self.fake = FakeCohort("chatgpt1", self.old_config, self.old_manifest,
                               self.old_plist, self.next_config)
        p = mock.patch.object(svc, "_frozen_paper_fleet_module", return_value=self.fake)
        p.start()
        self.addCleanup(p.stop)
        u = mock.patch.object(svc, "_user_root", return_value=self.home)
        u.start()
        self.addCleanup(u.stop)

    def qualified(self, account="chatgpt1", **kw):
        state = dict(svc=svc, account=account, roots=self.roots,
                     plan=self.plan, raw=self.raw,
                     current=self.next_config, manifest=self.next_manifest)
        state.update(kw)
        return pin._fleet_paper_v20_postpin_start(**state)

    def test_all_seven_static_cohorts_are_enrolled_and_publication_unpinned(self):
        self.assertEqual(
            set(svc.FLEET_V20_ENROLLED_ACCOUNTS),
            set(SEVEN_PINNED) | {"mastermind-os-publication"},
        )
        for account in SEVEN_PINNED:
            with self.subTest(account=account):
                self.fake.account = account
                self.fake.COHORTS = {account: self.fake.COHORTS.get(
                    "chatgpt1", {"config_sha256": sha(self.old_config),
                                 "manifest_sha256": sha(self.old_manifest)})}
                self.assertTrue(self.qualified(account=account))
        self.assertEqual(len(self.fake.calls), 7)

    def test_no_external_paper_account_or_publication_is_admitted(self):
        for account in ("chatgpt2-personal", "fabric-read", "fabric-design",
                        "mastermind-os-publication", "unknown-seat"):
            with self.subTest(account=account):
                self.assertFalse(self.qualified(account=account))
        self.assertEqual(self.fake.calls, [])

    def test_exact_pinned_postimage_is_required(self):
        self.assertFalse(self.qualified(plan={**self.plan, "manifest_after": "0" * 64}))
        raw = {**self.raw, "config.after.json": b"unreviewed"}
        self.assertFalse(self.qualified(raw=raw))
        raw = {**self.raw, "manifest.after.json": b"unreviewed"}
        self.assertFalse(self.qualified(raw=raw))
        self.fake.COHORTS["chatgpt1"]["manifest_sha256"] = "0" * 64
        self.assertFalse(self.qualified())
        self.assertEqual(self.fake.calls, [])

    def test_only_exact_paper_and_manifest_postimage_are_admitted(self):
        self.assertTrue(self.qualified())
        mutated = copy.deepcopy(self.next_config_dict)
        mutated["fleetStatus"]["fabricLauncherSha256"] = "b" * 64
        self.assertFalse(self.qualified(current=bytes_for(mutated)))
        mutated = copy.deepcopy(self.next_config_dict)
        mutated["paperDesign"]["bridgeSha256"] = "0" * 64
        self.assertFalse(self.qualified(current=bytes_for(mutated)))
        mutated = json.loads(self.next_manifest)
        mutated["configHash"] = sha(self.old_config)
        self.assertFalse(self.qualified(manifest=bytes_for(mutated)))
        mutated = json.loads(self.next_manifest)
        mutated["files"]["gateway.mjs"] = "0" * 64
        self.assertFalse(self.qualified(manifest=bytes_for(mutated)))

    def test_plist_change_or_file_permission_drift_refuses(self):
        self.roots["plist"].write_bytes(b"tampered service identity")
        self.assertFalse(self.qualified())
        self.roots["plist"].write_bytes(self.old_plist)
        self.roots["config"].chmod(0o644)
        self.assertFalse(self.qualified())
        self.roots["config"].chmod(0o600)
        self.roots["manifest"].chmod(0o664)
        self.assertFalse(self.qualified())
        self.roots["manifest"].chmod(0o600)
        self.assertTrue(self.qualified())

    def test_successor_checker_is_readonly_and_retains_original_pin(self):
        before = {n: p.read_bytes() for n,p in self.roots.items()}
        self.assertTrue(self.qualified())
        self.assertEqual(before, {n: p.read_bytes() for n,p in self.roots.items()})
        self.assertEqual(self.plan["manifest_after"], sha(self.old_manifest))
        self.assertEqual(self.fake.calls, [("chatgpt1", str(self.home))])


if __name__ == "__main__":
    unittest.main()
