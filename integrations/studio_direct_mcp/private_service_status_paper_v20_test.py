"""Hermetic Paper-v20 status successor compatibility and adversarial source proof.

Four accepted later Paper cohorts are exact extensions of the eight frozen
public status profiles. These tests use only temporary files and fake account
data; they do not load any installed profile, invoke Git or change a service.
"""
import copy
import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import private_service_status_successor as s


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(data):
    return json.dumps(data, sort_keys=True, indent=2).encode()


class PaperV20StatusSuccessorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name).resolve()
        self.account = "chatgpt1"
        self.old_status = b"original fleet status projection"
        self.new_status = b"protected public redacted fleet status"
        self.legacy_config = encode({"paperDesign": {"generation": "v10"},
                                     "gitPublish": {"preserve": True}})
        self.paper_config = encode({"paperDesign": {"generation": "v20"},
                                    "gitPublish": {"preserve": True}})
        self.legacy_manifest = {
            "version": 2, "account": self.account,
            "label": "com.mastermind.studio-direct-private." + self.account,
            "configHash": sha(self.legacy_config), "plistHash": sha(b"plist"),
            "files": {"fleet-status.mjs": sha(self.old_status),
                      "gateway.mjs": "a" * 64,
                      "paper-design.mjs": "b" * 64},
        }
        self.paper_manifest = copy.deepcopy(self.legacy_manifest)
        self.paper_manifest["configHash"] = sha(self.paper_config)
        self.after = copy.deepcopy(self.paper_manifest)
        self.after["files"]["fleet-status.mjs"] = sha(self.new_status)
        self.before_bytes = encode(self.paper_manifest)
        self.after_bytes = encode(self.after)
        self.original_bytes = encode(self.legacy_manifest)
        self.pinned = self.home / "state/native-pool-pin"
        self.pinned.mkdir(parents=True, mode=0o700)
        (self.pinned / "manifest.after.json").write_bytes(self.original_bytes)
        (self.pinned / "config.after.json").write_bytes(self.legacy_config)
        self.plist = self.home / "plist"
        self.plist.write_bytes(b"plist")
        self.config = self.home / "config"
        self.config.write_bytes(self.paper_config)
        self.roots = {"state": self.home / "state", "plist": self.plist,
                      "config": self.config}
        self.planner_calls = []
        def plan_selection(account, *, manifest_bytes, config_bytes, plist_bytes, home):
            self.planner_calls.append(account)
            if (account != self.account
                    or manifest_bytes != self.original_bytes
                    or config_bytes != self.legacy_config
                    or plist_bytes != b"plist"
                    or home != self.home):
                raise ValueError("original Paper v20 source not qualified")
            return {"manifestBytes": self.before_bytes,
                    "configBytes": self.paper_config}
        self.fake = SimpleNamespace(
            _frozen_paper_fleet_module=lambda: SimpleNamespace(
                plan_selection=plan_selection),
            _fabric_release_bytes=lambda path, limit=None: Path(path).read_bytes(),
            _user_root=lambda: self.home,
        )
        self.patches = (
            mock.patch.dict(s.PAPER_V20_PREDECESSOR_MANIFEST_SHA256,
                            {self.account: sha(self.before_bytes)}),
            mock.patch.dict(s.PAPER_V20_PREDECESSOR_CONFIG_SHA256,
                            {self.account: sha(self.paper_config)}),
            mock.patch.dict(s.PAPER_V20_POST_MANIFEST_RAW_SHA256,
                            {self.account: sha(self.after_bytes)}),
            mock.patch.dict(s.PAPER_V20_POST_MANIFEST_CANONICAL_SHA256, {
                self.account: sha(json.dumps(self.after, sort_keys=True,
                          separators=(",", ":")).encode())}),
            mock.patch.dict(s.LEGACY_MODULE_SHA256,
                            {self.account: sha(self.old_status)}),
            mock.patch.object(s, "TARGET_SOURCE_SHA256", sha(self.new_status)),
        )
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def project(self, **changes):
        inputs = {
            "manifest_bytes": self.before_bytes,
            "config_bytes": self.paper_config,
            "module_before_bytes": self.old_status,
            "source_module_bytes": self.new_status,
        }
        inputs.update(changes)
        return s.qualify_exact_predecessor(self.account, **inputs)

    def test_exact_paper_v20_cohort_accepts_only_status_module(self):
        before = s.manifest_from(self.before_bytes)
        projected = self.project()
        after = s.manifest_from(projected.manifest_after_bytes)
        self.assertEqual(after["files"]["fleet-status.mjs"],
                         sha(self.new_status))
        self.assertEqual({k:v for k,v in before["files"].items()
                          if k != "fleet-status.mjs"},
                         {k:v for k,v in after["files"].items()
                          if k != "fleet-status.mjs"})
        self.assertEqual(after["configHash"], before["configHash"])
        self.assertEqual(projected.manifest_after_bytes, self.after_bytes)
        self.assertTrue(projected.no_runtime_effect)

    def test_original_paper_selection_is_required_even_for_hash_pinned_manifest(self):
        self.assertIsNone(s._require_paper_v20_origin(
            self.fake, self.account, self.roots, self.before_bytes))
        self.assertEqual(self.planner_calls, [self.account])

    def test_changed_installed_config_fails_before_synthetic_selection(self):
        self.config.write_bytes(b'{"paperDesign": "foreign"}')
        with self.assertRaisesRegex(SystemExit, "PAPER_V20_ORIGIN_CHANGED"):
            s._require_paper_v20_origin(self.fake, self.account,
                                        self.roots, self.before_bytes)

    def test_lost_retained_native_origin_refuses(self):
        (self.pinned / "config.after.json").unlink()
        with self.assertRaises(FileNotFoundError):
            s._require_paper_v20_origin(self.fake, self.account,
                                        self.roots, self.before_bytes)

    def test_foreign_original_manifest_refuses_planner(self):
        (self.pinned / "manifest.after.json").write_bytes(b"unaccepted")
        with self.assertRaisesRegex(SystemExit, "PAPER_V20_ORIGIN_UNQUALIFIED"):
            s._require_paper_v20_origin(self.fake, self.account,
                                        self.roots, self.before_bytes)

    def test_paper_only_config_drift_and_unapproved_manifest_refuse(self):
        with self.assertRaisesRegex(s.SourceRefused, "PAPER_V20_CONFIG_CHANGED"):
            self.project(config_bytes=self.paper_config + b" ")
        with self.assertRaisesRegex(s.SourceRefused, "PREDECESSOR_MANIFEST_CHANGED"):
            self.project(manifest_bytes=self.before_bytes + b" ")

    def test_bad_target_status_module_refuses(self):
        with self.assertRaisesRegex(s.SourceRefused, "TARGET_SOURCE_NOT_ACCEPTED"):
            self.project(source_module_bytes=self.new_status + b"changed")

    def test_unapproved_paper_profile_not_admitted(self):
        for account in ("fabric-design", "chatgpt2-personal", "other"):
            with self.subTest(account=account):
                with self.assertRaises(s.SourceRefused):
                    s._cohort_pin(account, sha(self.before_bytes))

    def test_original_eight_frozen_pins_remain_separate(self):
        self.assertEqual(len(s.PREDECESSOR_MANIFEST_SHA256), 8)
        self.assertEqual(set(s.PAPER_V20_PREDECESSOR_MANIFEST_SHA256),
                         {"chatgpt1", "chatgpt2-business", "chatgpt3", "chatgpt4"})

    def test_c4_uses_original_enrollment_not_plain_native_manifest(self):
        account = "chatgpt4"
        enroll = self.home / "state/native-pool-pin-enrollment"
        enroll.mkdir()
        (enroll / "manifest.after").write_bytes(self.original_bytes)
        (enroll / "config.after").write_bytes(self.legacy_config)
        with mock.patch.dict(s.PAPER_V20_PREDECESSOR_MANIFEST_SHA256,
                             {account: sha(self.before_bytes)}), \
             mock.patch.dict(s.PAPER_V20_PREDECESSOR_CONFIG_SHA256,
                             {account: sha(self.paper_config)}):
            # The fake planner must also authenticate the alternate C4 original.
            self.fake._frozen_paper_fleet_module = lambda: SimpleNamespace(
                plan_selection=lambda a, **kwargs: {
                    "manifestBytes": self.before_bytes,
                    "configBytes": self.paper_config}
                    if a == account and kwargs["manifest_bytes"] == self.original_bytes
                    else (_ for _ in ()).throw(ValueError("foreign")))
            self.assertIsNone(s._require_paper_v20_origin(
                self.fake, account, self.roots, self.before_bytes))
            (enroll / "manifest.after").write_bytes(b"foreign")
            with self.assertRaisesRegex(SystemExit, "PAPER_V20_ORIGIN_UNQUALIFIED"):
                s._require_paper_v20_origin(
                    self.fake, account, self.roots, self.before_bytes)


if __name__ == "__main__":
    unittest.main()
