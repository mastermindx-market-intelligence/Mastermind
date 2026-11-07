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
    chain_for,
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
        with self.assertRaises(KeyError):
            chain_for("meta-ceo", provider_id="byteplus-modelark.glm-5.3-flash")
        self.assertEqual(
            [item.provider_id for item in chain_for("meta-ceo")],
            ["zai.glm-5.3", "cursor-pool"],
        )

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
        before = (dict(router.providers), dict(router.model_aliases))
        before_flags = {name: (provider.enabled, provider.autonomous_allowed)
                        for name, provider in router.providers.items()}
        report = bind_model_router(router)
        self.assertFalse(report["authority_granted"])
        self.assertFalse(report["production_armed"])
        self.assertFalse(report["capacity_claimed"])
        self.assertFalse(report["selection_is_commitment"])
        self.assertFalse(report["personal_coding_plan_used"])
        self.assertEqual(report["minimax_attended_model"], "MiniMax-M3")
        self.assertEqual(report["personal_coding_plan_alias"], "byteplus.attended")
        rows = {row["alias"]: row for row in report["modelark_aliases"]}
        self.assertEqual(len(report["modelark_aliases"]), len(MODELARK_CONTRACT["aliases"]))
        self.assertEqual(set(rows), set(MODELARK_CONTRACT["aliases"]))
        for alias, served in MODELARK_CONTRACT["aliases"].items():
            with self.subTest(alias=alias):
                self.assertEqual(rows[alias]["served_model"], served)
                self.assertFalse(rows[alias]["worker_eligible"])
                if alias in router.model_aliases:
                    self.assertEqual(rows[alias]["status"], "present")
                    self.assertFalse(rows[alias]["provider_enabled"])
                    provider = router.providers[MODELARK_CONTRACT["provider_alias"]]
                    self.assertFalse(provider.enabled)
                    self.assertFalse(provider.autonomous_allowed)
                else:
                    self.assertEqual(rows[alias]["status"], "absent_until_pr_1824_merges")
                    self.assertNotIn("provider_enabled", rows[alias])
        self.assertEqual(before, (router.providers, router.model_aliases))
        self.assertEqual(before_flags, {name: (provider.enabled, provider.autonomous_allowed)
                                        for name, provider in router.providers.items()})

    def test_catalog_presence_and_eligibility_are_not_authority(self):
        from types import SimpleNamespace

        # Exercise both sides of the source merge without depending on the
        # checkout date. Even an eligible catalog cannot grant admission.
        for present, eligible in ((False, False), (True, False), (True, True)):
            with self.subTest(present=present, eligible=eligible):
                aliases = {
                    alias: SimpleNamespace(
                        model=served,
                        provider_alias="byteplus-modelark",
                        worker_eligible=eligible,
                    )
                    for alias, served in MODELARK_CONTRACT["aliases"].items()
                } if present else {}
                providers = {
                    "byteplus-modelark": SimpleNamespace(enabled=eligible)
                } if present else {}
                router = SimpleNamespace(
                    policy_version="test", model_aliases=aliases, providers=providers
                )
                report = bind_model_router(router)
                expected = []
                for alias, served in MODELARK_CONTRACT["aliases"].items():
                    row = {
                        "alias": alias,
                        "status": "present" if present else "absent_until_pr_1824_merges",
                        "served_model": served,
                        "worker_eligible": eligible,
                    }
                    if present:
                        row["provider_enabled"] = eligible
                    expected.append(row)
                self.assertEqual(report["modelark_aliases"], expected)
                for field in (
                    "authority_granted", "production_armed", "capacity_claimed",
                    "selection_is_commitment", "personal_coding_plan_used",
                ):
                    self.assertIs(report[field], False)

    def test_legacy_absent_modelark_catalog_still_grants_no_authority(self):
        from types import SimpleNamespace
        from control_plane.model_router import ModelRouter

        current = ModelRouter.load()
        legacy = SimpleNamespace(policy_version=current.policy_version, providers=current.providers,
            model_aliases={name: profile for name, profile in current.model_aliases.items()
                           if name not in MODELARK_CONTRACT["aliases"]})
        report = bind_model_router(legacy)
        self.assertEqual(report["modelark_aliases"], [
            {"alias": alias, "status": "absent_until_pr_1824_merges", "served_model": served,
             "worker_eligible": False}
            for alias, served in MODELARK_CONTRACT["aliases"].items()
        ])
        self.assertFalse(report["authority_granted"])
        self.assertFalse(report["production_armed"])
        self.assertFalse(report["capacity_claimed"])

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
