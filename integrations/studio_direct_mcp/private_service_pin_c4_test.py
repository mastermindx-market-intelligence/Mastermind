"""Hermetic candidate qualification for exact C4 native-pin repository successor.

No installed profiles, Git remotes, ChatGPT credentials, launchd jobs or native
pool pointers are touched by these fixtures.
"""
from contextlib import contextmanager, nullcontext
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import private_service as installed_owner
spec = importlib.util.spec_from_file_location("c4_pin_candidate", HERE / "private_service_pin_c4.py")
c4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c4)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class Pin:
    SCHEMA = "mastermind.studio_native_pool_pin.v1"
    @staticmethod
    def decode(raw):
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("invalid")
        return value
    @staticmethod
    def directory(svc, path):
        if not path.is_dir() or path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != 0o700:
            raise ValueError("unsafe directory")
    @staticmethod
    def plan_sha(svc, plan):
        return digest(svc._fabric_release_json(plan))


class FakeOwner:
    FILE_MODE = 0o600
    DIR_MODE = 0o700
    def __init__(self, roots, suite):
        self.roots = roots
        self.suite = suite
        self.stopped = True
        self.fail_after = None
        self.fail_new_name = None
        self.writes = []
        self.DEPS = digest(b"deps")
    def _build_runtime_roots(self, account):
        assert account == "chatgpt4"
        return self.roots
    def _pin_owner_module(self):
        return Pin
    def _fabric_release_json(self, value):
        return json_bytes(value)
    def _fabric_release_bytes(self, path, **kw):
        path = Path(path)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("foreign file")
        return path.read_bytes()
    def _fabric_release_new(self, path, data):
        path = Path(path)
        if self.fail_new_name == path.name:
            self.fail_new_name = None
            raise OSError('simulated retained result failure')
        if path.exists() or path.is_symlink():
            raise ValueError("clobber refused")
        with path.open("xb") as stream:
            stream.write(data)
        path.chmod(0o600)
        self.writes.append(str(path))
    def _atomic_write_bytes(self, path, data, mode=0o600):
        path = Path(path)
        if path.is_symlink():
            raise ValueError("foreign symlink")
        if self.fail_after == path.name:
            self.fail_after = None
            raise OSError("simulated interruption")
        temporary = path.with_name(path.name + ".test-atomic")
        if temporary.exists():
            raise ValueError("foreign temp")
        temporary.write_bytes(data)
        temporary.chmod(mode)
        temporary.replace(path)
        self.writes.append(str(path))
    def _stable_regular_file_hash(self, path, label=None):
        return digest(Path(path).read_bytes())
    def _dependency_tree_hash(self, path):
        return self.DEPS
    def _verify_native_pin_install(self, account, label, roots):
        assert account == "chatgpt4"
        self.suite.assertFalse(roots["manifest"].is_symlink())
    def _native_pin_manifest_valid(self, data, account, label):
        return data["account"] == account
    def _fsync_dir(self, path):
        return None
    def _lifecycle_inspect(self, account, label, roots, require_positive=False):
        return None if self.stopped else {"pid":123}
    def _c2_lifecycle_mutex(self, account):
        assert account == "chatgpt4"
        return nullcontext()


class C4RepositorySuccessorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        base = self.root / "chatgpt4"
        state = base / "state"
        state.mkdir(parents=True, mode=0o700)
        (base / "node_modules").mkdir()
        node = self.root / "node"
        backend = self.root / "backend"
        plist = self.root / "plist"
        for path, data in [(node,b"node"),(backend,b"backend"),(plist,b"plist")]:
            path.write_bytes(data)
        self.roots = {
            "base":base, "state":state, "node_modules":base / "node_modules",
            "node":node, "backend":backend, "plist":plist,
            "config":base / "config.json", "manifest":base / "manifest.json",
        }
        self.svc = FakeOwner(self.roots, self)
        self.secret = "SECRET_NOT_FOR_RESULTS"
        self.orig_cfg = {"accountLabel":"chatgpt4", "gitPublish":{"enabled":True,
                        "not_exported":self.secret}, "port":45024,
                         "paperDesign":{"enabled":True}, "fleetStatus":{"enabled":True}}
        self.pre_module = {}
        self.post_module = {}
        self.extra = [
            "fleet-routing.mjs", "fleet-status.mjs", "output-budget.mjs",
            "package-lock.json", "package.json", "paper-design.mjs",
            "private-tunnel-auth.mjs", "private-tunnel-gateway.mjs", "tailnet-gateway.mjs",
        ]
        for name in (*self.extra,"gateway.mjs","git-publish.mjs"):
            payload = ("original:" + name).encode()
            (base / name).write_bytes(payload)
            (base / name).chmod(0o600)
            self.pre_module[name] = digest(payload)
        for name in c4.CHANGED:
            payload = ("reviewed-target:" + name).encode()
            self.post_module[name] = payload
        self.pre_files = copy.deepcopy(self.pre_module)
        self.post_files = copy.deepcopy(self.pre_files)
        for name in c4.CHANGED:
            self.post_files[name] = digest(self.post_module[name])
        self.orig_manifest = {
            "account":"chatgpt4","version":2,
            "label":"com.mastermind.studio-direct-private.chatgpt4",
            "node":str(node), "backend":str(backend),
            "nodeHash":digest(node.read_bytes()),
            "backendHash":digest(backend.read_bytes()),
            "plistHash":digest(plist.read_bytes()),
            "dependencyTreeHash":self.svc.DEPS,
            "files":self.pre_files,
            "configHash":digest(json_bytes(self.orig_cfg)),
        }
        self.write_json(self.roots["config"],self.orig_cfg)
        self.write_json(self.roots["manifest"],self.orig_manifest)
        self.post_cfg=copy.deepcopy(self.orig_cfg)
        self.post_cfg["repositoryWorkspaces"]={"enabled":True,"allowedRepositories":["mastermind","macro","terminal"]}
        self.post_manifest=copy.deepcopy(self.orig_manifest)
        self.post_manifest["files"]=self.post_files
        self.post_manifest["configHash"]=digest(json_bytes(self.post_cfg))
        self.old_map={
            "PRE_FILES":self.pre_files,"POST_FILES":self.post_files,
            "ORIGINAL_CONFIG":digest(json_bytes(self.orig_cfg)),
            "POST_CONFIG":digest(json_bytes(self.post_cfg)),
            "ORIGINAL_MANIFEST":digest(json_bytes(self.orig_manifest)),
            "POST_MANIFEST":digest(json_bytes(self.post_manifest)),
        }
        self.patches=[mock.patch.object(c4,k,v) for k,v in self.old_map.items()]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        @contextmanager
        def original_pin_stub(_svc, _roots, *, modifying=False):
            yield "a"*64
        self.pin_patch=mock.patch.object(c4,"original_pin",original_pin_stub)
        self.pin_patch.start()
        self.addCleanup(self.pin_patch.stop)
        self.source_patch=mock.patch.object(c4,"source_bytes",lambda svc,source:self.post_module)
        self.source_patch.start()
        self.addCleanup(self.source_patch.stop)

    def write_json(self,path,value):
        path.write_bytes(json_bytes(value))
        path.chmod(0o600)

    def args(self,operation,plan=None):
        return SimpleNamespace(account="chatgpt4",operation=operation,
              source="/exact/reviewed/source",
              expected_manifest_sha256=c4.ORIGINAL_MANIFEST,
              expected_plan_sha256=plan)

    def preview(self):
        output=c4.run(self.svc,self.args("preview"))
        self.assertEqual(output["phase"],"PREVIEW")
        self.assertEqual(output["effect_state"],"NOT_APPLIED")
        self.assertFalse(output["resultCommitted"])
        return output["planSha256"]

    def apply(self):
        plan=self.preview()
        result=c4.run(self.svc,self.args("apply",plan))
        self.assertEqual(result["phase"],"COMPLETE")
        self.assertEqual(result["effect_state"],"APPLIED")
        return plan

    def test_readonly_preview_has_no_runtime_effects_or_secrets(self):
        before={p.name:p.read_bytes() for p in self.roots["base"].iterdir() if p.is_file()}
        self.preview()
        after={p.name:p.read_bytes() for p in self.roots["base"].iterdir() if p.is_file()}
        self.assertEqual(before,after)
        self.assertEqual(self.svc.writes,[])
        self.assertNotIn(self.secret,json.dumps(c4.run(self.svc,self.args("preview"))))

    def test_exact_manifest_last_install_and_original_pin_files_preserved(self):
        pin=self.roots["state"]/"native-pool-pin"
        pin.mkdir(mode=0o700)
        (pin/"historical-immutable-receipt").write_bytes(b"keep")
        plan=self.apply()
        self.assertEqual((pin/"historical-immutable-receipt").read_bytes(),b"keep")
        self.assertEqual(c4.current_state(self.svc,self.roots,c4.transaction(
            self.svc,self.roots,plan,"a"*64)[1]),("COMPLETE",5))
        self.assertEqual(self.roots["manifest"].read_bytes(),json_bytes(self.post_manifest))
        self.assertEqual(self.roots["config"].read_bytes(),json_bytes(self.post_cfg))
        self.assertTrue((self.roots["base"]/"workspace-access.mjs").is_file())
        self.assertTrue(self.svc.writes[-2].endswith("manifest.json"))
        c4.require_start(self.svc,self.roots)

    def test_interrupted_config_write_is_reconciled_only_in_original_transaction(self):
        plan=self.preview()
        self.svc.fail_after="config.json"
        with self.assertRaisesRegex(SystemExit,"NATIVE_POOL_C4_EFFECT_UNKNOWN"):
            c4.run(self.svc,self.args("apply",plan))
        state=c4.run(self.svc,self.args("status",plan))
        self.assertEqual(state["phase"],"PARTIAL")
        self.assertFalse(state["resultCommitted"])
        with self.assertRaisesRegex(SystemExit,"NATIVE_POOL_C4_START_REFUSED"):
            c4.require_start(self.svc,self.roots)
        repaired=c4.run(self.svc,self.args("reconcile",plan))
        self.assertEqual(repaired["effect_state"],"APPLIED")
        self.assertEqual(c4.run(self.svc,self.args("status",plan))["phase"],"COMPLETE")

    def test_interrupted_journal_is_completed_under_same_plan_before_any_module_write(self):
        plan = self.preview()
        self.svc.fail_new_name = "intent.json"
        with self.assertRaisesRegex(SystemExit, "NATIVE_POOL_C4_EFFECT_UNKNOWN"):
            c4.run(self.svc, self.args("apply", plan))
        self.assertEqual(self.roots["manifest"].read_bytes(),
                         json_bytes(self.orig_manifest))
        self.assertEqual(self.roots["config"].read_bytes(),
                         json_bytes(self.orig_cfg))
        journal = self.roots["state"] / c4.TX_NAME
        self.assertFalse((journal / "intent.json").exists())
        result = c4.run(self.svc, self.args("reconcile", plan))
        self.assertEqual(result["effect_state"], "APPLIED")
        c4.require_start(self.svc, self.roots)

    def test_foreign_partial_journal_is_never_overwritten(self):
        plan = self.preview()
        self.svc.fail_new_name = "intent.json"
        with self.assertRaisesRegex(SystemExit, "NATIVE_POOL_C4_EFFECT_UNKNOWN"):
            c4.run(self.svc, self.args("apply", plan))
        journal = self.roots["state"] / c4.TX_NAME
        target = journal / "gateway.mjs.after"
        original = target.read_bytes()
        target.write_bytes(b"foreign")
        with self.assertRaisesRegex(SystemExit, "NATIVE_POOL_C4_TRANSACTION_REFUSED"):
            c4.run(self.svc, self.args("reconcile", plan))
        self.assertEqual(target.read_bytes(), b"foreign")
        self.assertNotEqual(original, b"foreign")
        self.assertEqual(self.roots["manifest"].read_bytes(),
                         json_bytes(self.orig_manifest))

    def test_missing_plan_cannot_be_recreated_by_reconciliation(self):
        plan = self.preview()
        self.svc.fail_new_name = "intent.json"
        with self.assertRaisesRegex(SystemExit, "NATIVE_POOL_C4_EFFECT_UNKNOWN"):
            c4.run(self.svc, self.args("apply", plan))
        journal = self.roots["state"] / c4.TX_NAME
        (journal / "plan.json").unlink()
        with self.assertRaisesRegex(SystemExit, "NATIVE_POOL_C4_TRANSACTION_REFUSED"):
            c4.run(self.svc, self.args("reconcile", plan))
        self.assertFalse((journal / "plan.json").exists())

    def test_manifest_committed_without_result_refuses_start_until_original_reconcile(self):
        plan=self.preview()
        self.svc.fail_new_name="result.json"
        with self.assertRaisesRegex(SystemExit,"NATIVE_POOL_C4_EFFECT_UNKNOWN"):
            c4.run(self.svc,self.args("apply",plan))
        observation=c4.run(self.svc,self.args("status",plan))
        self.assertEqual(observation["phase"],"COMPLETE")
        self.assertFalse(observation["resultCommitted"])
        self.assertEqual(observation["effect_state"],"PARTIAL")
        with self.assertRaisesRegex(SystemExit,"NATIVE_POOL_C4_START_REFUSED"):
            c4.require_start(self.svc,self.roots)
        recovered=c4.run(self.svc,self.args("reconcile",plan))
        self.assertTrue(recovered["resultCommitted"])
        c4.require_start(self.svc,self.roots)

    def test_foreign_intent_refuses_same_tx_reconcile_without_touching_manifest(self):
        plan=self.apply()
        before=self.roots["manifest"].read_bytes()
        intent=self.roots["state"]/c4.TX_NAME/"intent.json"
        intent.write_bytes(b'{"schema":"foreign"}')
        with self.assertRaisesRegex(SystemExit,"NATIVE_POOL_C4_TRANSACTION_REFUSED"):
            c4.run(self.svc,self.args("reconcile",plan))
        self.assertEqual(self.roots["manifest"].read_bytes(),before)

    def test_missing_postmodule_is_not_silently_reinstalled_after_success(self):
        plan=self.apply()
        (self.roots["base"]/"workspace-access.mjs").unlink()
        with self.assertRaisesRegex(SystemExit,"NATIVE_POOL_C4_FOREIGN_STATE"):
            c4.require_start(self.svc,self.roots)
        with self.assertRaisesRegex(SystemExit,"NATIVE_POOL_C4_FOREIGN_STATE"):
            c4.run(self.svc,self.args("status",plan))

    def test_loaded_gateway_refuses_apply_but_readonly_preview_available(self):
        self.svc.stopped=False
        plan=self.preview()
        with self.assertRaisesRegex(SystemExit,"NATIVE_POOL_C4_SERVICE_LOADED"):
            c4.run(self.svc,self.args("apply",plan))
        self.assertFalse((self.roots["state"]/c4.TX_NAME).exists())

    def test_stale_plan_refuses_before_transaction_creation(self):
        self.preview()
        with self.assertRaisesRegex(SystemExit,"NATIVE_POOL_C4_PLAN_CAS_REFUSED"):
            c4.run(self.svc,self.args("apply","f"*64))
        self.assertFalse((self.roots["state"]/c4.TX_NAME).exists())

    def test_duplicate_apply_refuses_and_completed_reconcile_is_noop(self):
        plan=self.apply()
        before=len(self.svc.writes)
        with self.assertRaisesRegex(SystemExit,"NATIVE_POOL_C4_RECONCILIATION_REQUIRED"):
            c4.run(self.svc,self.args("apply",plan))
        result=c4.run(self.svc,self.args("reconcile",plan))
        self.assertEqual(result["phase"],"COMPLETE")
        self.assertEqual(before,len(self.svc.writes))

    def test_foreign_file_after_commit_refuses_start_and_status(self):
        plan=self.apply()
        self.roots["config"].write_bytes(b"foreign")
        with self.assertRaisesRegex(SystemExit,"NATIVE_POOL_C4_FOREIGN_STATE"):
            c4.require_start(self.svc,self.roots)
        with self.assertRaisesRegex(SystemExit,"NATIVE_POOL_C4_FOREIGN_STATE"):
            c4.run(self.svc,self.args("status",plan))

    def test_future_generic_publisher_hash_drift_cannot_invalidate_c4_receipt(self):
        self.apply()
        with mock.patch.dict(self.svc.__dict__,{"FLEET_V10_MERGE_PUBLISHER_PATCH_SHA256":{"git-publish.mjs":"f"*64}}):
            c4.require_start(self.svc,self.roots)

    def test_symlinked_publisher_module_is_rejected(self):
        path=self.roots["base"]/"git-publish.mjs"
        path.unlink()
        path.symlink_to(self.roots["base"]/"gateway.mjs")
        with self.assertRaises((SystemExit,ValueError)):
            self.preview()

    def test_manifest_validator_admits_only_exact_frozen_c4_postimage(self):
        manifest=copy.deepcopy(self.post_manifest)
        manifest.update({"source":"/accepted/canonical/source","host":"127.0.0.1","port":45024})
        identity={key:manifest[key] for key in ("host","port","nodeHash","backendHash","dependencyTreeHash")}
        with (mock.patch.object(installed_owner,"C4_PAPER_RUNTIME_IDENTITY",identity),
              mock.patch.object(installed_owner,"C4_REPOSITORY_POST_CONFIG_SHA256",manifest["configHash"]),
              mock.patch.object(installed_owner,"C4_REPOSITORY_POST_MANIFEST_CANONICAL_SHA256",
                                installed_owner._canonical_json_sha256(manifest))):
            self.assertTrue(installed_owner._valid_manifest(manifest,"chatgpt4",
                            "com.mastermind.studio-direct-private.chatgpt4"))
            changed=copy.deepcopy(manifest)
            changed["files"]["git-publish.mjs"]="f"*64
            self.assertFalse(installed_owner._valid_manifest(changed,"chatgpt4",
                             "com.mastermind.studio-direct-private.chatgpt4"))
            changed=copy.deepcopy(manifest)
            changed["port"]=45999
            self.assertFalse(installed_owner._valid_manifest(changed,"chatgpt4",
                             "com.mastermind.studio-direct-private.chatgpt4"))

    def test_wrong_account_is_not_an_install_selector(self):
        a=self.args("preview")
        a.account="chatgpt1"
        with self.assertRaisesRegex(SystemExit,"NATIVE_POOL_C4_ACCOUNT_REFUSED"):
            c4.run(self.svc,a)

    def test_absent_transaction_does_not_create_on_status(self):
        with self.assertRaisesRegex(SystemExit,"NATIVE_POOL_C4_TRANSACTION_REFUSED"):
            c4.run(self.svc,self.args("status","a"*64))
        self.assertFalse((self.roots["state"]/c4.TX_NAME).exists())


if __name__=="__main__":
    unittest.main()
