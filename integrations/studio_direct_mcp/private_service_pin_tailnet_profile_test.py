"""Public exact Tailnet manifest states; no private config or host/runtime effects."""
import ast
import copy
import hashlib
import shlex
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import private_service as svc

PROFILES = json.loads(r'''[
  {
    "account": "fabric-design",
    "forward_config_sha256": "d8224ad799b9927b43026d07f2716f63b5ecbdb41580f0eb2e15ba7a0ba84750",
    "forward_canonical_manifest": "a1c9117bfd3d210072b16aacd8f4b32e0c23ecf08eb28406d6218f7cf590a25c",
    "old_canonical_manifest": "87de91f4fd0d51571c2350cf4fe53704ad035eba8f095c13b09352732307671c",
    "post_canonical_manifest": "b08c021b6c3c9cd9a1acdd57957fbf5e88b6d63daa11b963b7476d993b1a8b46",
    "post_config_sha256": "64dbdea9bd2dd7d3cba3df3c130d3095c8926c9424772146e9d31d58d7d66f52",
    "public_manifest": {
      "account": "fabric-design",
      "backend": "/Users/chriswong/.local/share/desktop-commander-service/vendor/node_modules/@wonderwhy-er/desktop-commander/dist/index.js",
      "backendHash": "a4145198dc75cd34e7c7452c2054b4cc0d29e199ae1459961a17e4da25a13500",
      "configHash": "529becd75ecbb401f7086e19bd61416b237014f107ab7e62eb0c275570d1e55a",
      "dependencyTreeHash": "91ce96dc69159edcabb3eee472e6ebafb18450b93a03addd6adf0df6dca47e29",
      "files": {
        "fleet-status.mjs": "a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780",
        "gateway.mjs": "970b47f1c6a15bc3f1175f1043c5dd4a59ad748c2374b586e384bbd6ba40ce5e",
        "git-publish.mjs": "9d50cd828e51d0c08a7be0ca7b18c89bfd8fb767a548bb1e4deaddaf185225ae",
        "output-budget.mjs": "5fb464cdb531adf944561ddda760b77856530bcc08f7ba48ef774d6750f5a071",
        "package-lock.json": "9a4e7398ddb45f44d6910fc05118bac425397f4b9869f33229da81f76ae262d0",
        "package.json": "25ab096e21ac6e8c3761ee896e69d175ba628c1fe5751bcfab452c304a4bb634",
        "paper-design.mjs": "e2162584ceab9941e7bcce51b73120c9a9aeb13c128cd5b217077c005f0f1c7e",
        "private-tunnel-auth.mjs": "fe8c9e5ba14fd7750fc26bbfe45ed3f77d4b96fa8ff639c6b5efdf653740e1c0",
        "private-tunnel-gateway.mjs": "225b1a592f5486c688efc6f5fc37184877a7e3e8022c2e831858c8989c6cca00",
        "tailnet-gateway.mjs": "bd46b40cfd5f2744f9b07be38ff2656676939707e753f6e846f4a2c578944d25"
      },
      "host": "127.0.0.1",
      "label": "com.mastermind.studio-direct-private.fabric-design",
      "node": "/Users/chriswong/.local/share/mastermind-runtime/node/bin/node",
      "nodeHash": "3fbe98203f8f4a86ce5b0b573a1a30aa4253064c4c2a0299c436d259b68e54b0",
      "plistHash": "8bb5a8e1aae02d07d47c47d0cea5f3ccc8def034b38bfffe6217e2c1aef1ec30",
      "port": 45118,
      "source": "/Users/chriswong/.local/share/studio-direct-mcp/source/pr1217-e79bd9ae/integrations/studio_direct_mcp",
      "version": 2
    },
    "application_config_sha256": "182dab20123410d0939eef3179ff24d38c773a28b82d31591403cac974ec9aa5",
    "application_canonical_manifest": "070cebf2c4b4bbd41eb7fd687347292e40e13519a98a303bafca13202e971e8c",
    "application_raw_manifest_sha256": "5c8c3f30f922c50e0f923bed4509785b5745bc2a7c05ef7d386befa9e6be67eb"
  },
  {
    "account": "fabric-read",
    "forward_config_sha256": "ab8443c18e485cd15107b2d87ac28455ed9754cd08dc5b6c90d24ac38a7e15c7",
    "forward_canonical_manifest": "6738294cefcca0be4d2696d51ebd41eb937e25a8515ca556f72c4b52d3f2f20c",
    "old_canonical_manifest": "f39e118cb770d4f793dd92c31e9f17f7153e7daef4e9703be7408fde702d40bb",
    "post_canonical_manifest": "328c25399daf9ab16c994ea30bd4a628ef40483e5f9af89fe34f191ac4f48819",
    "post_config_sha256": "e25f99f3d599f9bdabdb7e647474a0bb09869bb8982fef568012f916b8e4722c",
    "public_manifest": {
      "account": "fabric-read",
      "backend": "/Users/chriswong/.local/share/desktop-commander-service/vendor/node_modules/@wonderwhy-er/desktop-commander/dist/index.js",
      "backendHash": "a4145198dc75cd34e7c7452c2054b4cc0d29e199ae1459961a17e4da25a13500",
      "configHash": "02b2cddb81d9ca14ec5880f3a9e4444dfff60ebe0c4665f9d0f53226804fed02",
      "dependencyTreeHash": "91ce96dc69159edcabb3eee472e6ebafb18450b93a03addd6adf0df6dca47e29",
      "files": {
        "fabric-operator.mjs": "2ed7578ced90da1e17a95faa4df2e43c164ade42e832d307efbb3902aed42a00",
        "fleet-status.mjs": "a7ba88b02d7099d99d0e6d1e702b2faee6b7a05e7e6e6a49c86c567184e5c780",
        "gateway.mjs": "2a9038d802cdefeea3af4a3fbe45d2326fb894a42c72f3f4f946603419b93446",
        "git-publish.mjs": "9d50cd828e51d0c08a7be0ca7b18c89bfd8fb767a548bb1e4deaddaf185225ae",
        "output-budget.mjs": "5fb464cdb531adf944561ddda760b77856530bcc08f7ba48ef774d6750f5a071",
        "package-lock.json": "9a4e7398ddb45f44d6910fc05118bac425397f4b9869f33229da81f76ae262d0",
        "package.json": "25ab096e21ac6e8c3761ee896e69d175ba628c1fe5751bcfab452c304a4bb634",
        "paper-design.mjs": "e2162584ceab9941e7bcce51b73120c9a9aeb13c128cd5b217077c005f0f1c7e",
        "private-tunnel-auth.mjs": "fe8c9e5ba14fd7750fc26bbfe45ed3f77d4b96fa8ff639c6b5efdf653740e1c0",
        "private-tunnel-gateway.mjs": "225b1a592f5486c688efc6f5fc37184877a7e3e8022c2e831858c8989c6cca00",
        "tailnet-gateway.mjs": "89a3d1c972a31ab62f19205439d6f09bc24f4d51783ebc2e1bea788bcd9d817c"
      },
      "host": "127.0.0.1",
      "label": "com.mastermind.studio-direct-private.fabric-read",
      "node": "/Users/chriswong/.local/share/mastermind-runtime/node/bin/node",
      "nodeHash": "3fbe98203f8f4a86ce5b0b573a1a30aa4253064c4c2a0299c436d259b68e54b0",
      "plistHash": "46b85aa87a15b6b5094c63e87cce3f3c3615dcd0fcc741c59de46ea4b476c192",
      "port": 45117,
      "source": "/Volumes/Mastermind/evidence/fabric-reliability-codex-20261008/recovery-engineering/paid-operator-delegation-20261012/gateway-candidate",
      "version": 2
    },
    "application_config_sha256": "121600753ad7bf2f13f30006577e049401cd5e53023b1297dc03e20a0a00fe4c",
    "application_canonical_manifest": "32f76d5282f1187a3c355835bd5b34bb73f4e00fe05b9de9a84c958780ef9836",
    "application_raw_manifest_sha256": "c3000a6c60194ce50ca23f4901a351e28f4f93d37b0596e928b9d3fe65295ffc"
  }
]''')


def post(row):
    value = copy.deepcopy(row["public_manifest"])
    value["configHash"] = row["post_config_sha256"]
    return value


def forward(row):
    value = post(row)
    value["configHash"] = row["forward_config_sha256"]
    return value


def application(row):
    value = forward(row)
    value["configHash"] = row["application_config_sha256"]
    return value


class TailnetPublicProfileTests(unittest.TestCase):
    def test_exact_old_native_pin_forward_and_application_states(self):
        for row in PROFILES:
            for value, digest in ((row["public_manifest"], row["old_canonical_manifest"]),
                                  (post(row), row["post_canonical_manifest"]),
                                  (forward(row), row["forward_canonical_manifest"]),
                                  (application(row), row["application_canonical_manifest"])):
                with self.subTest(account=row["account"], state=digest):
                    self.assertEqual(svc._canonical_json_sha256(value), digest)
                    self.assertTrue(svc._native_pin_manifest_valid(
                        value, row["account"], value["label"]))

    def test_unknown_config_state_is_not_a_tailnet_profile(self):
        for row in PROFILES:
            with self.subTest(account=row["account"]):
                value = post(row)
                value["configHash"] = "a" * 64
                # Generic legacy shape was already recognized; transport
                # admission additionally requires an exact known canonical state.
                self.assertTrue(svc._valid_manifest(value, row["account"], value["label"]))
                self.assertFalse(svc._native_pin_manifest_valid(
                    value, row["account"], value["label"]))

    def test_other_identity_fields_cannot_select_tailnet(self):
        for row in PROFILES:
            for key in ("nodeHash", "backendHash", "dependencyTreeHash", "plistHash",
                        "source", "node", "backend", "host", "port"):
                with self.subTest(account=row["account"], field=key):
                    value = post(row)
                    value[key] = 1 if key == "port" else "a" * 64
                    self.assertFalse(svc._native_pin_manifest_valid(
                        value, row["account"], value["label"]))

    def test_other_account_or_module_identity_is_refused(self):
        for row in PROFILES:
            value = post(row)
            value["account"] = "unreviewed-seat"
            value["label"] = "com.mastermind.studio-direct-private.unreviewed-seat"
            self.assertFalse(svc._native_pin_manifest_valid(
                value, value["account"], value["label"]))
            for name in row["public_manifest"]["files"]:
                with self.subTest(account=row["account"], module=name):
                    value = post(row)
                    value["files"][name] = "a" * 64
                    self.assertFalse(svc._native_pin_manifest_valid(
                        value, row["account"], value["label"]))

    def test_only_two_accounts_and_eight_fixed_states_select_tailnet(self):
        self.assertEqual(set(svc._NATIVE_POOL_PIN_TAILNET_CANONICAL),
                         {row["account"] for row in PROFILES})
        for row in PROFILES:
            self.assertEqual(svc._NATIVE_POOL_PIN_TAILNET_CANONICAL[row["account"]],
                             frozenset((row["old_canonical_manifest"],
                                        row["post_canonical_manifest"],
                                        row["forward_canonical_manifest"],
                                        row["application_canonical_manifest"])))


    def test_application_state_reproduces_public_manifest_hashes(self):
        # Config hashes are opaque authenticated native evidence. Public inputs
        # reproduce complete manifest hashes, not the private config preimages.
        for row in PROFILES:
            with self.subTest(account=row["account"]):
                value = application(row)
                self.assertEqual({k: v for k, v in value.items() if k != "configHash"},
                                 {k: v for k, v in row["public_manifest"].items() if k != "configHash"})
                self.assertEqual(svc._canonical_json_sha256(value),
                                 row["application_canonical_manifest"])
                self.assertEqual(hashlib.sha256(svc._fabric_release_json(value)).hexdigest(),
                                 row["application_raw_manifest_sha256"])

    def test_application_state_keeps_every_identity_and_account_fence(self):
        for row in PROFILES:
            for field in ("configHash", "nodeHash", "backendHash", "dependencyTreeHash",
                          "plistHash", "source", "node", "backend", "host", "port",
                          "account", "label"):
                with self.subTest(account=row["account"], field=field):
                    value = application(row)
                    value[field] = 1 if field == "port" else "foreign"
                    self.assertFalse(svc._native_pin_manifest_valid(
                        value, row["account"], row["public_manifest"]["label"]))
            for name in row["public_manifest"]["files"]:
                with self.subTest(account=row["account"], module=name):
                    value = application(row)
                    value["files"][name] = "a" * 64
                    self.assertFalse(svc._native_pin_manifest_valid(
                        value, row["account"], value["label"]))
            other = next(item for item in PROFILES if item["account"] != row["account"])
            value = application(row)
            value["configHash"] = other["application_config_sha256"]
            self.assertFalse(svc._native_pin_manifest_valid(
                value, row["account"], value["label"]))

    def test_original_bridge_source_binds_exact_application_launcher(self):
        root = Path(__file__).resolve().parents[2]
        rollout = root / "ops/native_fabric/quota_continuity/rollout"
        source = (rollout / "native_install.py").read_text()
        nodes = []
        for node in ast.parse(source).body:
            if (isinstance(node, ast.FunctionDef) and node.name == "shell_bridge"
                    or isinstance(node, ast.Assign) and any(
                        isinstance(target, ast.Name) and target.id == "BRIDGE_MARKER"
                        for target in node.targets)):
                nodes.append(node)
        self.assertEqual(len(nodes), 2)
        namespace = {"shlex": shlex}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "<original-shell-bridge>", "exec"),
             namespace)
        store = Path("/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/native-code-releases")
        python = "/opt/homebrew/Cellar/python@3.14/3.14.7/Frameworks/Python.framework/Versions/3.14/bin/python3.14"
        old = "fb516277cca4f77654454fe3bbf82dca4c1c03f5ee2c9abb379b68f84312dfea"
        current = "b602bfeb2dff3216b18417f1673f308221594d2c3274bb59bc7be1fe4c65c1ec"
        self.assertEqual(hashlib.sha256((rollout / "native_generation.py").read_bytes()).hexdigest(),
                         current)
        for launcher, wanted in (
            (old, "e99c71661c116ea2e53511d28ef9fe78c8366c7136831482ad63fad3688ef9bf"),
            (current, "b17b1c008bfea2a3841bccbcf360a3cc5dd0d4bc38f1842a573f1a1885e1bd00"),
        ):
            bridge = namespace["shell_bridge"](
                python, store / "launchers" / (launcher + ".py"), store, "pool")
            self.assertEqual(len(bridge), 547)
            self.assertEqual(hashlib.sha256(bridge).hexdigest(), wanted)


if __name__ == "__main__":
    unittest.main()
