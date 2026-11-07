"""Public exact Tailnet manifest states; no private config or host/runtime effects."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import private_service as svc

PROFILES = json.loads(r'''[
  {
    "account": "fabric-design",
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
    }
  },
  {
    "account": "fabric-read",
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
    }
  }
]''')


def post(row):
    value = copy.deepcopy(row["public_manifest"])
    value["configHash"] = row["post_config_sha256"]
    return value


class TailnetPublicProfileTests(unittest.TestCase):
    def test_exact_old_and_native_pin_post_states(self):
        for row in PROFILES:
            for value, digest in ((row["public_manifest"], row["old_canonical_manifest"]),
                                  (post(row), row["post_canonical_manifest"])):
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

    def test_only_two_accounts_and_four_fixed_states_select_tailnet(self):
        self.assertEqual(set(svc._NATIVE_POOL_PIN_TAILNET_CANONICAL),
                         {row["account"] for row in PROFILES})
        for row in PROFILES:
            self.assertEqual(svc._NATIVE_POOL_PIN_TAILNET_CANONICAL[row["account"]],
                             frozenset((row["old_canonical_manifest"],
                                        row["post_canonical_manifest"])))


if __name__ == "__main__":
    unittest.main()
