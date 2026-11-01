"""Exact public C4 pin postimage; no private config or host/runtime proof.

Projection e49e065a binds the original raw manifest 5b7e4ea4 and the normal
renderer's one-field config postimage. All reads below use synthetic temp files.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import private_service as svc

ORIGINAL = json.loads(r'''{
  "account": "chatgpt4",
  "backend": "/Users/chriswong/.local/share/desktop-commander-service/vendor/node_modules/@wonderwhy-er/desktop-commander/dist/index.js",
  "backendHash": "a4145198dc75cd34e7c7452c2054b4cc0d29e199ae1459961a17e4da25a13500",
  "configHash": "e6c1495c7552241a847b3d541f99913e6a74838e0fb5aee9477b861e92d2a48b",
  "dependencyTreeHash": "639c904d1d5832baa832eac8519cf2304073d3d72fdacc03fd879281068e6211",
  "files": {
    "fleet-routing.mjs": "dc98537e5ade635f5c9fa3a89ab99ae9ea57f549d2856832d01f90c1e61c1533",
    "fleet-status.mjs": "a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780",
    "gateway.mjs": "92e7f38f9eb53a5b140d0f3809b3381a4d35cea86bbb2e20229f108792ec30c8",
    "git-publish.mjs": "9d50cd828e51d0c08a7be0ca7b18c89bfd8fb767a548bb1e4deaddaf185225ae",
    "output-budget.mjs": "5fb464cdb531adf944561ddda760b77856530bcc08f7ba48ef774d6750f5a071",
    "package-lock.json": "9a4e7398ddb45f44d6910fc05118bac425397f4b9869f33229da81f76ae262d0",
    "package.json": "25ab096e21ac6e8c3761ee896e69d175ba628c1fe5751bcfab452c304a4bb634",
    "paper-design.mjs": "e2162584ceab9941e7bcce51b73120c9a9aeb13c128cd5b217077c005f0f1c7e",
    "private-tunnel-auth.mjs": "fe8c9e5ba14fd7750fc26bbfe45ed3f77d4b96fa8ff639c6b5efdf653740e1c0",
    "private-tunnel-gateway.mjs": "fd4eb541590cafc3c92a0b0ac1f7080baa76193704a2219e58b02462ef4d5540",
    "tailnet-gateway.mjs": "9dd75992ba0b5c658582779ebeb71a06f13ec0a3475aa83d62753e22832b906b"
  },
  "host": "127.0.0.1",
  "label": "com.mastermind.studio-direct-private.chatgpt4",
  "node": "/Users/chriswong/.local/share/mastermind-runtime/node/bin/node",
  "nodeHash": "3fbe98203f8f4a86ce5b0b573a1a30aa4253064c4c2a0299c436d259b68e54b0",
  "plistHash": "b63dcc9017b61553888b95d9ffc68c572020ef02b74e73ee60c990ed1f89fe16",
  "port": 45024,
  "source": "/Volumes/Mastermind/agent-workspaces/web/studio-direct-fleet-routing-concurrency-20261004-sol-001/integrations/studio_direct_mcp",
  "version": 2
}''')
POST_CONFIG_SHA256 = "f02e385e234f7f88619058485b61f17834d3cfc33896ce3f5606bd64fcecce21"
POST_CANONICAL_SHA256 = "e10730454cd343b8774929b9c6d39f5dfbf1c9b7e83bfdc82636b8e54d0437a0"
LABEL = "com.mastermind.studio-direct-private.chatgpt4"


def postimage():
    value = copy.deepcopy(ORIGINAL)
    value["configHash"] = POST_CONFIG_SHA256
    return value


class C4NativePinPostimageTests(unittest.TestCase):
    def test_original_profile_remains_admitted(self):
        self.assertEqual(svc._canonical_json_sha256(ORIGINAL),
                         "2252819766e266ac0be6b30c94694b503aad4634d8de184f62611542fb581bd0")
        self.assertTrue(svc._valid_manifest(ORIGINAL, "chatgpt4", LABEL))

    def test_exact_postimage_is_admitted(self):
        future = postimage()
        self.assertEqual(svc._canonical_json_sha256(future), POST_CANONICAL_SHA256)
        self.assertEqual([k for k in ORIGINAL if ORIGINAL[k] != future[k]], ["configHash"])
        self.assertTrue(svc._valid_manifest(future, "chatgpt4", LABEL))

    def test_normal_manifest_reader_accepts_exact_postimage(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_bytes(svc._fabric_release_json(postimage()))
            self.assertEqual(svc._read_manifest(path, "chatgpt4", LABEL, required=True),
                             postimage())

    def test_only_reviewed_canonical_states_are_admitted(self):
        self.assertEqual(svc.C4_PAPER_MANIFEST_CANONICAL_SHA256, frozenset((
            "e0e7865965285af6372fdf27ee70ae27f494b37fe19e1f5af763406295a96ec2",
            "2252819766e266ac0be6b30c94694b503aad4634d8de184f62611542fb581bd0",
            POST_CANONICAL_SHA256,
        )))
        self.assertNotIn(frozenset(ORIGINAL["files"]), svc.KNOWN_MANIFEST_FILESETS)

    def test_unknown_config_seal_is_refused(self):
        future = postimage()
        future["configHash"] = "a" * 64
        self.assertFalse(svc._valid_manifest(future, "chatgpt4", LABEL))

    def test_other_identity_changes_are_refused(self):
        variants = {
            "backendHash": "a" * 64, "nodeHash": "a" * 64,
            "dependencyTreeHash": "a" * 64, "plistHash": "a" * 64,
            "host": "0.0.0.0", "port": 45025, "version": 1,
            "source": ORIGINAL["source"] + "-other",
            "node": ORIGINAL["node"] + "-other",
            "backend": ORIGINAL["backend"] + "-other",
        }
        for key, changed in variants.items():
            with self.subTest(field=key):
                future = postimage()
                future[key] = changed
                self.assertFalse(svc._valid_manifest(future, "chatgpt4", LABEL))

    def test_other_accounts_and_labels_are_refused(self):
        for account in ("chatgpt2-personal", "fabric-design", "unknown-seat"):
            with self.subTest(account=account):
                future = postimage()
                future["account"] = account
                future["label"] = "com.mastermind.studio-direct-private." + account
                self.assertFalse(svc._valid_manifest(future, account, future["label"]))
        self.assertFalse(svc._valid_manifest(postimage(), "chatgpt4", LABEL + "-other"))

    def test_changed_module_map_is_refused(self):
        for name in ORIGINAL["files"]:
            with self.subTest(module=name):
                future = postimage()
                future["files"][name] = "a" * 64
                self.assertFalse(svc._valid_manifest(future, "chatgpt4", LABEL))
        for action in ("add", "remove"):
            with self.subTest(action=action):
                future = postimage()
                if action == "add":
                    future["files"]["unreviewed.mjs"] = "a" * 64
                else:
                    del future["files"]["gateway.mjs"]
                self.assertFalse(svc._valid_manifest(future, "chatgpt4", LABEL))

    def test_added_or_missing_manifest_fields_are_refused(self):
        future = postimage()
        future["unreviewed"] = True
        self.assertFalse(svc._valid_manifest(future, "chatgpt4", LABEL))
        for name in ORIGINAL:
            with self.subTest(missing=name):
                future = postimage()
                del future[name]
                self.assertFalse(svc._valid_manifest(future, "chatgpt4", LABEL))


if __name__ == "__main__":
    unittest.main()
