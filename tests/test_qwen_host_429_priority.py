"""Qwen host 429 attribution and priority: no secrets, network or broker writes."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "ops/native_fabric/quota_continuity/candidate"


def load(name):
    path = SRC / (name + ".py")
    if not path.is_file():
        path = SRC.parent / "source" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Host429Probe(unittest.TestCase):
    def test_fresh_host_readiness_distinguishes_429_from_hard_denial(self):
        source = types.ModuleType("glm_host_account_source")
        source.owned_bytes = lambda path: b""
        with patch.dict(sys.modules, {"glm_host_account_source": source}):
            probe = load("glm_host_account_probe")
        fake = b"""import os
def _load_config(): return {'token-plan': {}}
def key_names(): return ['Ryan', 'Chris', 'Kris']
def _cooldown_path(name): return os.path.expanduser('~/lanes/ext/slots/bailian/') + name + '.cooldown'
"""
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            directory = home / "lanes/ext/slots/bailian"
            directory.mkdir(parents=True)
            (home / "lanes/ext/HOST_ENV.sh").write_text("\n")
            now = int(time.time())
            (directory / "Ryan.cooldown").write_text(f"{now+120} http_429\n")
            (directory / "Chris.cooldown").write_text(f"{now+120} access_denied\n")
            (directory / "Ryan.cooldown").chmod(0o600)
            (directory / "Chris.cooldown").chmod(0o600)
            cmd = probe.build_probe("ubuntu3", "ubuntu3-route",
                                    ["Ryan", "Chris", "Kris"], fake, mode="qwen")
            env = {**os.environ, "HOME": temp}
            result = subprocess.run(cmd, shell=True, text=True, capture_output=True,
                                    env=env, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            prefix, value = result.stdout.strip().split("=", 1)
            self.assertEqual(prefix, "bailian_local_account_readiness")
            obs = json.loads(value)
            self.assertEqual(obs["status"], "known")
            self.assertEqual(obs["accounts"], {"Ryan": True, "Chris": False, "Kris": True})
            self.assertEqual(obs["soft_429_accounts"], ["Ryan"])
            self.assertIs(obs["soft_429_checked"], True)

    def test_expired_cooldown_is_not_current(self):
        source = types.ModuleType("glm_host_account_source")
        source.owned_bytes = lambda path: b""
        with patch.dict(sys.modules, {"glm_host_account_source": source}):
            probe = load("glm_host_account_probe")
        fake = b"""import os
def _load_config(): return {'token-plan': {}}
def key_names(): return ['Ryan']
def _cooldown_path(name): return os.path.expanduser('~/lanes/ext/slots/bailian/') + name + '.cooldown'
"""
        with tempfile.TemporaryDirectory() as temp:
            h = Path(temp)
            (h / "lanes/ext/slots/bailian").mkdir(parents=True)
            (h / "lanes/ext/HOST_ENV.sh").write_text("\n")
            (h / "lanes/ext/slots/bailian/Ryan.cooldown").write_text("1 http_429\n")
            env = {**os.environ, "HOME": temp}
            cmd = probe.build_probe("ubuntu3", "ubuntu3-route", ["Ryan"], fake, mode="qwen")
            got = subprocess.run(cmd, shell=True, text=True, capture_output=True,
                                 env=env, timeout=10)
            self.assertEqual(got.returncode, 0, got.stderr)
            obj = json.loads(got.stdout.strip().split("=",1)[1])
            self.assertEqual(obj["accounts"]["Ryan"], True)
            self.assertEqual(obj["soft_429_accounts"], [])


class Host429Readiness(unittest.TestCase):
    def setUp(self):
        self.observation = load("glm_host_account_readiness")
        self.registry = {"ubuntu3": {
            "ssh_alias": "ubuntu3-route", "roles": ["lanes"],
            "allowed_modes": ["qwen"], "qualification_only_modes": [],
        }}
        self.clock = time.time()
        self.keybytes = b"test-attested-validator-no-secrets"
        self.flags = {
            "schema":"mastermind.bailian_local_account_readiness.v1",
            "host":"ubuntu3", "transport_alias":"ubuntu3-route",
            "mode":"qwen", "config_scope":"launcher_bailian_config.v1",
            "validator_sha256":hashlib.sha256(self.keybytes).hexdigest(),
            "observed_at":self.clock, "status":"known", "cooldown_checked":True,
            "soft_429_checked":True,
            "accounts":{"Ryan":True,"Chris":False,"Kris":True},
            "soft_429_accounts":["Ryan"],
        }
        self.doc = {"host":"ubuntu3", "reachable":True, "ts":self.clock,
                    "bailian_local_account_readiness":self.flags}
        self.rows = [{"name": name, "_eff_cap": 7} for name in ("Ryan","Chris","Kris")]
        hostpick = types.ModuleType("host_pick")
        hostpick.MODE_TOOLS = {"qwen": ["qwen"], "glm": ["glm"]}
        bindings = types.ModuleType("native_runtime_bindings")
        bindings.owner_path = lambda path, root: Path(path)
        self.stub = patch.dict(sys.modules, {
            "host_pick": hostpick, "glm_host_account_readiness": self.observation,
            "native_runtime_bindings": bindings,
        })
        self.stub.start()
        self.source = load("glm_host_account_source")
        self.original = self.source.owned_bytes

        def bytes_for(path):
            path = str(path)
            if path.endswith("hosts.json"): return json.dumps(self.registry).encode()
            if path.endswith("ubuntu3.json"): return json.dumps(self.doc).encode()
            if path.endswith("bailian_keys.py"): return self.keybytes
            raise ValueError("unmapped synthetic file")

        self.source.owned_bytes = bytes_for

    def tearDown(self):
        self.source.owned_bytes = self.original
        self.stub.stop()

    def choose(self, preferred=None):
        return self.source.filter_observed_accounts(
            self.rows, host="ubuntu3", model="qwen3.8-flash", now=self.clock,
            preferred=preferred, hosts_path="hosts.json", state_dir="/fixtures",
            validator_path="bailian_keys.py", mode="qwen",
        )

    def test_host_ranks_preserve_hard_denial_exclusion(self):
        selected, reason = self.choose()
        self.assertEqual(reason,"ok")
        self.assertEqual([(x["name"],x["_host_qwen_429_rank"]) for x in selected],
                         [("Ryan",2),("Kris",0)])
        self.assertNotIn("_host_qwen_429_rank", self.rows[0])

    def test_exact_account_qualified_but_unsubstituted(self):
        selected, _ = self.choose(preferred="Ryan")
        self.assertEqual([(x["name"],x["_host_qwen_429_rank"]) for x in selected],
                         [("Ryan",2)])
        selected, _ = self.choose(preferred="Chris")
        self.assertEqual(selected, [])

    def test_old_probe_metadata_is_unknown_not_healthy(self):
        del self.flags["soft_429_checked"]
        del self.flags["soft_429_accounts"]
        selected, _ = self.choose()
        self.assertEqual([r["_host_qwen_429_rank"] for r in selected],[1,1])

    def test_forged_cooldown_names_fail_closed(self):
        self.flags["soft_429_accounts"]=["Missing"]
        selected, reason = self.choose()
        self.assertEqual(selected, [])
        self.assertEqual(reason, "host_account_cooldown_invalid")

    def test_duplicate_cooldown_names_fail_closed(self):
        self.flags["soft_429_accounts"]=["Ryan","Ryan"]
        selected, reason = self.choose()
        self.assertEqual((selected, reason), ([], "host_account_cooldown_invalid"))

    def test_stale_host_projection_still_refuses(self):
        self.doc["ts"]=self.clock-700
        selected, reason=self.choose()
        self.assertEqual(selected, [])
        self.assertNotEqual(reason,"ok")

    def test_wrong_validator_hash_still_refuses(self):
        self.flags["validator_sha256"]="0"*64
        selected, reason=self.choose()
        self.assertEqual(selected, [])
        self.assertNotEqual(reason,"ok")

    def test_unknown_accounts_stay_unqualified(self):
        self.flags["accounts"]["Ryan"]=None
        selected, reason=self.choose()
        self.assertEqual([r["name"] for r in selected],["Kris"])
        self.assertEqual(reason,"ok")


if __name__ == "__main__":
    unittest.main()
