"""Read-only contract tests for original-sealed Paper v20 M2 fleet cohort data."""
import hashlib
import json
import unittest
from pathlib import Path
from unittest import mock

import paper_v20_fleet_cohorts as cohorts


def sha(data):
    return hashlib.sha256(data).hexdigest()


def as_bytes(obj):
    return json.dumps(obj, indent=2, sort_keys=True).encode()


class TestPaperV20SealedFleet(unittest.TestCase):
    def make_case(self, generation="v10"):
        home = Path("/synthetic-mmx-home")
        seat = "cohort-fixture"
        runtime = home / ".local/share/mastermind-paper/runtime" / generation
        paper = {
            "enabled": True,
            "pythonPath": str(runtime / "venv/bin/python"),
            "bridgePath": str(runtime / "source/bridge.py"),
            "bridgeSha256": cohorts.PREDECESSORS[generation],
            "appPath": str(home / "Applications/Paper.app"),
            "commandTimeoutMs": 70000,
        }
        config = {"host": "127.0.0.1", "nodeCommand": "sealed original", "paperDesign": paper}
        config_bytes = as_bytes(config)
        plist_bytes = b"sealed launchd synthetic plist\n"
        manifest = {
            "version": 2, "account": seat,
            "label": "com.mastermind.studio-direct-private." + seat,
            "files": {"private-tunnel-gateway.mjs": "a" * 64},
            "configHash": sha(config_bytes), "plistHash": sha(plist_bytes),
        }
        manifest_bytes = as_bytes(manifest)
        pin = {
            "generation": generation,
            "bridge_sha256": paper["bridgeSha256"],
            "manifest_sha256": sha(manifest_bytes),
            "config_sha256": sha(config_bytes),
            "plist_sha256": sha(plist_bytes),
            "nonpaper_sha256": cohorts._canonical_hash({k: v for k, v in config.items() if k != "paperDesign"}),
            "file_count": len(manifest["files"]),
        }
        return seat, home, config, manifest, pin, plist_bytes

    def invoke(self, case, *, change_config=None, change_manifest=None, change_plist=None,
               change_pins=None):
        seat, home, config, manifest, pin, plist_bytes = case
        if change_config:
            change_config(config)
        cbytes = as_bytes(config)
        if change_manifest:
            change_manifest(manifest)
        if change_plist:
            plist_bytes = change_plist(plist_bytes)
        mbytes = as_bytes(manifest)
        if change_pins:
            change_pins(pin, cbytes, mbytes, plist_bytes)
        with mock.patch.object(cohorts, "COHORTS", {seat: pin}):
            return cohorts.plan_selection(seat, manifest_bytes=mbytes,
                                          config_bytes=cbytes,
                                          plist_bytes=plist_bytes, home=home)

    def test_workspace_12file_successors_preserve_closed_original_cohort(self):
        self.assertEqual(
            set(cohorts.WORKSPACE_12FILE_SUCCESSORS),
            {"admin-business", "chatgpt3-w570f6f34", "chatgpt3-wa2a9e6f9"},
        )
        self.assertEqual(len(cohorts.COHORTS), 8)
        for seat, updated in cohorts.WORKSPACE_12FILE_SUCCESSORS.items():
            with self.subTest(seat=seat):
                original = cohorts.COHORTS[seat]
                self.assertEqual(updated["file_count"], 12)
                self.assertEqual(updated["generation"], "v10")
                self.assertEqual(updated["bridge_sha256"], cohorts.PREDECESSORS["v10"])
                self.assertEqual(updated["plist_sha256"], original["plist_sha256"])
                self.assertNotEqual(updated["manifest_sha256"], original["manifest_sha256"])
                self.assertNotEqual(updated["nonpaper_sha256"], original["nonpaper_sha256"])
                for field in ("config_sha256", "manifest_sha256", "nonpaper_sha256", "plist_sha256"):
                    self.assertEqual(len(updated[field]), 64)
                    int(updated[field], 16)

    def test_workspace_12file_exact_successor_cas_preserves_nonpaper(self):
        seat, home, config, manifest, original, plist = self.make_case()
        for i in range(11):
            manifest["files"][f"sealed-extra-{i:02d}.mjs"] = "a" * 64
        self.assertEqual(len(manifest["files"]), 12)
        pre_config = as_bytes(config)
        pre_manifest = as_bytes(manifest)
        newer = {**original, "file_count": 12, "manifest_sha256": sha(pre_manifest)}
        with mock.patch.object(cohorts, "COHORTS", {seat: original}), mock.patch.object(
                cohorts, "WORKSPACE_12FILE_SUCCESSORS", {seat: newer}):
            plan = cohorts.plan_selection(
                seat, manifest_bytes=pre_manifest, config_bytes=pre_config,
                plist_bytes=plist, home=home)
            self.assertEqual(plan["originalManifestSha256"], newer["manifest_sha256"])
            self.assertEqual(plan["preservedGatewayFiles"], 12)
            before = json.loads(pre_config)
            after = json.loads(plan["configBytes"])
            self.assertEqual({k: v for k, v in before.items() if k != "paperDesign"},
                             {k: v for k, v in after.items() if k != "paperDesign"})
            self.assertEqual(plan["manifest"]["files"], manifest["files"])
            self.assertEqual({k for k in before["paperDesign"]
                              if before["paperDesign"][k] != after["paperDesign"][k]},
                             {"bridgePath", "bridgeSha256", "pythonPath"})
            changed_manifest = {**manifest, "files": {**manifest["files"],
                                 "sealed-extra-00.mjs": "b" * 64}}
            with self.assertRaises(ValueError):
                cohorts.plan_selection(seat, manifest_bytes=as_bytes(changed_manifest),
                    config_bytes=pre_config, plist_bytes=plist, home=home)
            with self.assertRaises(ValueError):
                cohorts.plan_selection(seat, manifest_bytes=pre_manifest,
                    config_bytes=as_bytes({**config, "testMode": True}),
                    plist_bytes=plist, home=home)
            with self.assertRaises(ValueError):
                cohorts.plan_selection(seat, manifest_bytes=pre_manifest,
                    config_bytes=pre_config, plist_bytes=plist+b"changed", home=home)

    def test_all_real_cohorts_have_unique_fixed_original_identity(self):
        self.assertEqual(len(cohorts.COHORTS), 8)
        self.assertNotIn("fabric-read", cohorts.COHORTS)
        self.assertNotIn("fabric-design", cohorts.COHORTS)
        self.assertNotIn("chatgpt2-personal", cohorts.COHORTS)
        all_predecessors = [x["manifest_sha256"] for x in cohorts.COHORTS.values()]
        self.assertEqual(len(set(all_predecessors)), 8)
        for seat, pin in cohorts.COHORTS.items():
            with self.subTest(seat=seat):
                self.assertTrue(seat and seat == seat.lower())
                self.assertIn(pin["generation"], ("v10", "v12"))
                self.assertEqual(pin["bridge_sha256"], cohorts.PREDECESSORS[pin["generation"]])
                for k in ("manifest_sha256", "config_sha256", "plist_sha256", "nonpaper_sha256"):
                    self.assertEqual(len(pin[k]), 64)
                    int(pin[k], 16)
                self.assertTrue(10 <= pin["file_count"] <= 13)

    def test_publication_service_requalified_after_protected_publisher_rollout(self):
        """The actual Nov 4 M2 publication gateway has a newer sealed profile.

        The installed original M2 owner has 13/13 file hashes, node/backend
        and plist digests matching the current installed manifest. Its
        gitPublish/repositoryWorkspaces/fleetStatus non-Paper selection changed
        since the earlier accepted publication cohort; it remains untouched by
        the Paper-only v20 selector. Preserve the earlier manifest as a stale
        predecessor that can never be used for a CAS write.
        """
        publication = cohorts.COHORTS["mastermind-os-publication"]
        self.assertEqual(
            publication["manifest_sha256"],
            "bd9dfc4e315541085342c410f0575ddbba0d40afb9d0208709078bf9b3b0c9ed",
        )
        self.assertNotEqual(
            publication["manifest_sha256"],
            "aba7a5755ae71a12b9359890cb5d8cda7bd179b176fcb77d6119edd802809983",
        )
        self.assertEqual(
            publication["config_sha256"],
            "6b1f07a31e207828473f0f387515db02139731aaa1508bd8d34bc826a2753f11",
        )
        self.assertEqual(
            publication["plist_sha256"],
            "525ed99524c4fa060a8d8ada0967b06509c42f970270f8b2619537516ebfdb34",
        )
        self.assertEqual(publication["file_count"], 13)
        self.assertEqual(publication["generation"], "v12")
        self.assertEqual(
            publication["nonpaper_sha256"],
            "c0faa52703c8e670b47427bb66a74adbf24cb55ef0586164a70c9975e8234b8b",
        )

    def test_success_preserves_nonpaper_and_plist_and_original_bytes(self):
        for generation in ("v10", "v12"):
            with self.subTest(generation=generation):
                c = self.make_case(generation)
                before_c = as_bytes(c[2]); before_m = as_bytes(c[3]); before_p = c[5]
                plan = self.invoke(c)
                self.assertEqual(plan["fromGeneration"], generation)
                self.assertEqual(plan["toGeneration"], "v20")
                self.assertEqual(plan["bridgeSha256"], cohorts.TARGET_BRIDGE_SHA256)
                self.assertFalse(plan["serviceStarted"])
                self.assertEqual(plan["originalManifestSha256"], sha(before_m))
                future = json.loads(plan["configBytes"])
                original = json.loads(before_c)
                self.assertEqual({k: v for k, v in future.items() if k != "paperDesign"},
                                 {k: v for k, v in original.items() if k != "paperDesign"})
                self.assertEqual({k for k in future["paperDesign"]
                                  if future["paperDesign"][k] != original["paperDesign"][k]},
                                 {"pythonPath", "bridgePath", "bridgeSha256"})
                self.assertEqual({k: v for k, v in json.loads(plan["manifestBytes"]).items()
                                  if k != "configHash"},
                                 {k: v for k, v in json.loads(before_m).items() if k != "configHash"})
                self.assertEqual(json.loads(plan["manifestBytes"])["configHash"], sha(plan["configBytes"]))
                self.assertEqual(before_c, as_bytes(c[2]))
                self.assertEqual(before_m, as_bytes(c[3]))
                self.assertEqual(before_p, c[5])

    def test_c4_enrolled_alternate_retains_exact_eight_seat_boundary(self):
        self.assertEqual(len(cohorts.COHORTS), 8)
        self.assertEqual(cohorts.C4_POST_ENROLLMENT["manifest_sha256"],
                         "3648a9a8e9711bab7be9fc7a3950f73579ce7d78358a18c15ac7d39adf924a9f")
        self.assertEqual(cohorts.C4_POST_ENROLLMENT["file_count"], 12)
        self.assertEqual(cohorts.C4_POST_ENROLLMENT["config_sha256"],
                         "37680eb009b4199ffba209e0d88775b73e00a4ca0ca8f0785a22d33ec2d81d2b")
        self.assertNotIn("fabric-read", cohorts.COHORTS)
        self.assertNotIn("fabric-design", cohorts.COHORTS)

    def test_c4_post_enrollment_paper_only_inert_alternate_and_negative_cas(self):
        home = Path("/synthetic-c4-home")
        account = "chatgpt4"
        runtime = home / ".local/share/mastermind-paper/runtime/v12"
        paper = {
            "enabled": True,
            "pythonPath": str(runtime / "venv/bin/python"),
            "bridgePath": str(runtime / "source/bridge.py"),
            "bridgeSha256": cohorts.PREDECESSORS["v12"],
            "appPath": str(home / "Applications/Paper.app"),
            "commandTimeoutMs": 70000,
        }
        config = {
            "accountLabel": account, "paperDesign": paper,
            "gitPublish": {"commandTimeoutMs": 45000, "preserved": True},
            "repositoryWorkspaces": {
                "enabled": True,
                "allowedRepositories": ["mastermind", "macro", "terminal"],
            },
        }
        cbytes = as_bytes(config)
        plist = b"closed exact C4 launchd identity"
        manifest = {
            "version": 2, "account": account,
            "label": "com.mastermind.studio-direct-private." + account,
            "files": {str(i): "a" * 64 for i in range(12)},
            "configHash": sha(cbytes), "plistHash": sha(plist),
        }
        mbytes = as_bytes(manifest)
        enrolled = {
            "generation": "v12", "bridge_sha256": cohorts.PREDECESSORS["v12"],
            "manifest_sha256": sha(mbytes), "config_sha256": sha(cbytes),
            "plist_sha256": sha(plist),
            "nonpaper_sha256": cohorts._canonical_hash({
                k: v for k, v in config.items() if k != "paperDesign"}),
            "file_count": 12,
        }
        original = {"manifest_sha256": "0" * 64}
        def select(c=cbytes, m=mbytes, p=plist):
            with mock.patch.object(cohorts, "COHORTS", {account: original}), \
                 mock.patch.object(cohorts, "C4_POST_ENROLLMENT", enrolled):
                return cohorts.plan_selection(
                    account, manifest_bytes=m, config_bytes=c, plist_bytes=p, home=home)
        plan = select()
        changed = json.loads(plan["configBytes"])
        self.assertEqual(changed["gitPublish"], config["gitPublish"])
        self.assertEqual(changed["repositoryWorkspaces"], config["repositoryWorkspaces"])
        self.assertEqual(set(k for k in changed if changed[k] != config[k]), {"paperDesign"})
        self.assertEqual(json.loads(plan["manifestBytes"])["files"], manifest["files"])
        self.assertEqual(plan["preservedGatewayFiles"], 12)
        with self.assertRaisesRegex(ValueError, "CAS"):
            select(c=as_bytes({**config, "gitPublish": {"preserved": False}}))
        with self.assertRaisesRegex(ValueError, "CAS"):
            select(m=as_bytes({**manifest, "files": {**manifest["files"], "0": "b" * 64}}))
        with self.assertRaisesRegex(ValueError, "CAS"):
            select(p=plist + b"foreign")
        with mock.patch.object(cohorts, "COHORTS", {account: original}), \
             mock.patch.object(cohorts, "C4_POST_ENROLLMENT", enrolled):
            with self.assertRaisesRegex(ValueError, "not in the reviewed cohort"):
                cohorts.plan_selection(
                    "fabric-read", manifest_bytes=mbytes, config_bytes=cbytes,
                    plist_bytes=plist, home=home)

    def test_unknown_account_never_selects(self):
        c = self.make_case()
        with mock.patch.object(cohorts, "COHORTS", {c[0]: c[4]}):
            with self.assertRaisesRegex(ValueError, "not in the reviewed cohort"):
                cohorts.plan_selection("foreign-account", manifest_bytes=as_bytes(c[3]),
                                       config_bytes=as_bytes(c[2]), plist_bytes=c[5],home=c[1])

    def test_original_manifest_config_and_plist_cas_tampering_refused(self):
        c = self.make_case()
        for tamper in ("manifest", "config", "plist"):
            with self.subTest(tamper=tamper), self.assertRaisesRegex(ValueError, "CAS or service identity changed"):
                change = dict(change_manifest=(lambda x: x.update(version=3)) if tamper == "manifest" else None,
                              change_config=(lambda x: x.update(host="changed")) if tamper == "config" else None,
                              change_plist=(lambda x: x + b"foreign") if tamper == "plist" else None)
                self.invoke(c, **change)

    def test_nonpaper_drift_refuses_even_if_file_digests_are_reobserved(self):
        c = self.make_case()
        def change_config(x):
            x["host"] = "evil.example.invalid"
        def reobserve(pin, config_bytes, manifest_bytes, plist_bytes):
            pin["config_sha256"] = sha(config_bytes)
            pin["manifest_sha256"] = sha(manifest_bytes)
        c[3]["configHash"] = sha(as_bytes({**c[2], "host": "evil.example.invalid"}))
        with self.assertRaisesRegex(ValueError, "non-Paper configuration changed"):
            self.invoke(c, change_config=change_config, change_pins=reobserve)

    def test_unreviewed_paper_runtime_change_refused_with_selfconsistent_hashes(self):
        c = self.make_case()
        def change_config(x):
            x["paperDesign"]["bridgePath"] = "/another/bridge.py"
        c[3]["configHash"] = sha(as_bytes({**c[2], "paperDesign":{**c[2]["paperDesign"],"bridgePath":"/another/bridge.py"}}))
        def reobserve(pin, config_bytes, manifest_bytes, plist_bytes):
            pin["config_sha256"] = sha(config_bytes)
            pin["manifest_sha256"] = sha(manifest_bytes)
        with self.assertRaisesRegex(ValueError, "selected predecessor differs"):
            self.invoke(c, change_config=change_config,change_pins=reobserve)

    def test_unknown_predecessor_bridge_pin_refuses(self):
        c = self.make_case("v10")
        c[4]["bridge_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "predecessor bridge not reviewed"):
            self.invoke(c)

if __name__ == "__main__":
    unittest.main()
