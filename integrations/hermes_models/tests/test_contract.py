"""Role map, ModelArk contract pin, and ModelRouter non-admission."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from integrations.hermes_models.contract import (  # noqa: E402
    CREDENTIAL_ENV_NAMES,
    CREDENTIAL_FILE_ENV_NAMES,
    MODELARK_CONTRACT,
    PERSONAL_PLAN_BASE_URLS,
    PROVIDERS,
    ROLES,
    ProviderSpec,
)
from integrations.hermes_models.router_binding import ContractDrift, bind_model_router  # noqa: E402


class ContractTests(unittest.TestCase):
    def test_chairman_role_mapping(self):
        self.assertEqual(ROLES["meta-ceo"].provider_ids[0], "zai.glm-5.3")
        self.assertEqual(ROLES["meta-ceo"].logical_model, "glm-5.3")
        self.assertEqual(ROLES["meta-ceo"].profile, "mmmeta")
        flash = (
            "byteplus-modelark.glm-5.3-flash",
            "byteplus-modelark.deepseek-v4.1-flash",
            "cursor-pool",
        )
        for role_id in ("secretary", "watcher", "implementation-subagent"):
            self.assertEqual(ROLES[role_id].provider_ids, flash)
            self.assertEqual(ROLES[role_id].profile, "mmsecretary")
            self.assertEqual(ROLES[role_id].logical_model, "glm-5.3-flash")
        for role_id in ("vision", "computer-use"):
            self.assertEqual(ROLES[role_id].provider_ids, ("minimax.attended", "cursor-pool"))
            self.assertEqual(ROLES[role_id].logical_model, "MiniMax-M3")
        for spec in ROLES.values():
            self.assertEqual(spec.provider_ids[-1], "cursor-pool")

    def test_modelark_contract_is_commercial_not_personal_plan(self):
        self.assertEqual(MODELARK_CONTRACT["source_pr"], 1824)
        self.assertEqual(MODELARK_CONTRACT["realm_id"], "byteplus-modelark-commercial")
        self.assertEqual(MODELARK_CONTRACT["provider_alias"], "byteplus-modelark")
        self.assertEqual(
            MODELARK_CONTRACT["base_url"],
            "https://ark.ap-southeast.bytepluses.com/api/v3",
        )
        self.assertEqual(MODELARK_CONTRACT["env_key"], "BYTEPLUS_MODELARK_API_KEY")
        self.assertEqual(
            MODELARK_CONTRACT["aliases"]["byteplus-modelark.glm-5.3-flash"],
            "glm-5-3-flash-260828",
        )
        self.assertEqual(
            MODELARK_CONTRACT["aliases"]["byteplus-modelark.deepseek-v4.1-flash"],
            "deepseek-v4-1-flash-261017",
        )
        for url in PERSONAL_PLAN_BASE_URLS:
            self.assertIn("/api/coding", url)
            with self.assertRaises(ValueError):
                ProviderSpec(
                    provider_id="rejected",
                    hermes_name="rejected",
                    display_name="rejected",
                    served_model="glm-5.3-flash",
                    base_url=url,
                    credential_env="BYTEPLUS_MODELARK_API_KEY",
                    credential_file_env="BYTEPLUS_MODELARK_API_KEY_FILE",
                )
        flash = PROVIDERS["byteplus-modelark.glm-5.3-flash"]
        deepseek = PROVIDERS["byteplus-modelark.deepseek-v4.1-flash"]
        self.assertEqual(flash.base_url, deepseek.base_url)
        self.assertEqual(flash.credential_env, "BYTEPLUS_MODELARK_API_KEY")
        self.assertNotIn("byteplus.attended", {item.provider_id for item in PROVIDERS.values()})

    def test_credential_names_are_pointers_only(self):
        self.assertEqual(
            CREDENTIAL_ENV_NAMES,
            (
                "BYTEPLUS_MODELARK_API_KEY",
                "CURSOR_API_KEY",
                "MINIMAX_TOKEN_PLAN_KEY",
                "ZAI_API_KEY",
            ),
        )
        self.assertEqual(
            CREDENTIAL_FILE_ENV_NAMES,
            (
                "BYTEPLUS_MODELARK_API_KEY_FILE",
                "CURSOR_API_KEY_FILE",
                "MINIMAX_TOKEN_PLAN_KEY_FILE",
                "ZAI_API_KEY_FILE",
            ),
        )

    def test_loaded_model_router_grants_no_authority(self):
        from control_plane.model_router import ModelRouter

        router = ModelRouter.load()
        before = (router.providers["byteplus"].enabled, router.providers["minimax"].enabled)
        report = bind_model_router(router)
        self.assertFalse(report["authority_granted"])
        self.assertFalse(report["production_armed"])
        self.assertFalse(report["capacity_claimed"])
        self.assertFalse(report["selection_is_commitment"])
        self.assertFalse(report["personal_coding_plan_used"])
        self.assertEqual(report["minimax_attended_model"], "MiniMax-M3")
        self.assertEqual(report["personal_coding_plan_alias"], "byteplus.attended")
        self.assertTrue(all(row["status"] == "absent_until_pr_1824_merges" for row in report["modelark_aliases"]))
        self.assertEqual(before, (router.providers["byteplus"].enabled, router.providers["minimax"].enabled))

    def test_router_model_drift_is_refused(self):
        class Alias:
            model = "glm-5.3-flash"
            provider_alias = "byteplus-modelark"
            worker_eligible = False

        class Router:
            policy_version = "test"
            model_aliases = {"byteplus-modelark.glm-5.3-flash": Alias()}
            providers = {}

        with self.assertRaises(ContractDrift):
            bind_model_router(Router())


if __name__ == "__main__":
    unittest.main()
