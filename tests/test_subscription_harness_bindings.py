from __future__ import annotations

import copy
import json
import unittest

from control_plane.subscription_harness_bindings import (
    DEFAULT_BINDINGS_PATH,
    HarnessBindingError,
    autonomous_activation_blockers,
    bindings_for_profile,
    canary_blockers,
    get_binding,
    load_bindings,
    validate_bindings,
)
from control_plane.subscription_provider_profiles import get_profile, load_profiles


class SubscriptionHarnessBindingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.profiles = load_profiles()
        self.catalog = load_bindings(profiles_document=self.profiles)
        self.raw = json.loads(DEFAULT_BINDINGS_PATH.read_text(encoding="utf-8"))

    def test_catalog_separates_provider_plan_from_harness(self) -> None:
        alibaba = bindings_for_profile(
            "alibaba-token-plan-personal",
            document=self.catalog,
            profiles_document=self.profiles,
        )
        self.assertEqual(
            {binding.adapter_id for binding in alibaba},
            {"claude-compatible-subscription", "codex-cli"},
        )
        minimax = bindings_for_profile(
            "minimax-token-plan",
            document=self.catalog,
            profiles_document=self.profiles,
        )
        self.assertEqual(
            {binding.protocol for binding in minimax},
            {"anthropic", "openai-chat"},
        )

    def test_profile_and_override_endpoints_resolve(self) -> None:
        anthropic = get_binding(
            "alibaba-token-plan-personal.claude-code-anthropic",
            document=self.catalog,
            profiles_document=self.profiles,
        )
        codex = get_binding(
            "alibaba-token-plan-personal.codex-responses",
            document=self.catalog,
            profiles_document=self.profiles,
        )
        profile = get_profile("alibaba-token-plan-personal", document=self.profiles)
        self.assertEqual(anthropic.effective_base_url, profile.base_url)
        self.assertEqual(
            codex.effective_base_url,
            "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
        )
        self.assertEqual(codex.model_for(profile, "hard"), "qwen3.8-max")

    def test_built_alibaba_codex_lane_can_reach_canary_gate_only(self) -> None:
        binding = get_binding(
            "alibaba-token-plan-personal.codex-responses",
            document=self.catalog,
            profiles_document=self.profiles,
        )
        self.assertEqual(
            canary_blockers(
                binding,
                adapter_implemented=True,
                provider_realm_enrolled=True,
                capacity_known=True,
                usage_policy_satisfied=True,
            ),
            (),
        )
        self.assertEqual(
            autonomous_activation_blockers(
                binding,
                adapter_implemented=True,
                provider_realm_enrolled=True,
                capacity_known=True,
                real_canary_passed=True,
                usage_policy_satisfied=True,
            ),
            ("implementation_not_proven_live", "source_policy_disarmed"),
        )

    def test_spec_only_lane_cannot_reach_canary(self) -> None:
        binding = get_binding(
            "minimax-token-plan.openai-compatible",
            document=self.catalog,
            profiles_document=self.profiles,
        )
        self.assertEqual(
            canary_blockers(
                binding,
                adapter_implemented=True,
                provider_realm_enrolled=True,
                capacity_known=True,
                usage_policy_satisfied=True,
            ),
            ("implementation_not_built",),
        )

    def test_provider_identity_mismatch_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.raw)
        row = mutated["bindings"]["minimax-token-plan.claude-code-anthropic"]
        row["provider"] = "alibaba"
        with self.assertRaisesRegex(HarnessBindingError, "provider disagrees"):
            validate_bindings(mutated, profiles_document=self.profiles)

    def test_credential_bearing_endpoint_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.raw)
        row = mutated["bindings"]["minimax-token-plan.openai-compatible"]
        row["endpoint"]["base_url"] = "https://user:secret@api.minimax.io/v1"
        with self.assertRaisesRegex(HarnessBindingError, "credential-free HTTPS"):
            validate_bindings(mutated, profiles_document=self.profiles)

    def test_unproven_lane_cannot_be_armed(self) -> None:
        mutated = copy.deepcopy(self.raw)
        row = mutated["bindings"]["alibaba-token-plan-personal.codex-responses"]
        row["autonomous_allowed"] = True
        with self.assertRaisesRegex(HarnessBindingError, "arms an unproven lane"):
            validate_bindings(mutated, profiles_document=self.profiles)

    def test_activation_gate_removal_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.raw)
        row = mutated["bindings"]["glm-coding-plan.claude-code-anthropic"]
        row["activation_gates"].remove("real_canary_passed")
        with self.assertRaisesRegex(HarnessBindingError, "weakens activation gates"):
            validate_bindings(mutated, profiles_document=self.profiles)

    def test_model_class_outside_profile_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.raw)
        row = mutated["bindings"]["alibaba-token-plan-personal.codex-responses"]
        row["model_classes"].append("nonexistent")
        with self.assertRaisesRegex(HarnessBindingError, "model classes disagree"):
            validate_bindings(mutated, profiles_document=self.profiles)

    def test_catalog_is_source_disarmed(self) -> None:
        for binding_id in self.catalog["bindings"]:
            binding = get_binding(
                binding_id,
                document=self.catalog,
                profiles_document=self.profiles,
            )
            self.assertFalse(binding.autonomous_allowed)


if __name__ == "__main__":
    unittest.main()
