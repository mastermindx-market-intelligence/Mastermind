from __future__ import annotations

import copy
import json
import unittest

from control_plane.codex_provider_realm import ALIBABA_TOKEN_PLAN
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
from control_plane.provider_protocols import (
    PROVIDER_PROTOCOLS,
    validate_provider_protocol,
    ProviderProtocolError,
)
from control_plane.subscription_provider_profiles import (
    ProviderProfileError,
    get_profile,
    load_profiles,
    validate_profiles,
)
from control_plane.worker_adapter import adapter_descriptor


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
            {"anthropic", "openai-chat", "responses"},
        )
        self.assertEqual(
            {binding.adapter_id for binding in minimax},
            {
                "claude-compatible-subscription",
                "codex-cli",
                "openai-compatible",
            },
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

    def test_alibaba_codex_binding_matches_reviewed_runtime_realm(self) -> None:
        binding = get_binding(
            "alibaba-token-plan-personal.codex-responses",
            document=self.catalog,
            profiles_document=self.profiles,
        )
        self.assertEqual(binding.harness_id, "codex-cli")
        self.assertEqual(binding.adapter_id, "codex-cli")
        descriptor = adapter_descriptor(binding.adapter_id)
        self.assertTrue(descriptor.implemented)
        self.assertEqual(binding.provider, ALIBABA_TOKEN_PLAN.provider_alias)
        self.assertEqual(binding.protocol, ALIBABA_TOKEN_PLAN.wire_api)
        self.assertEqual(binding.effective_base_url, ALIBABA_TOKEN_PLAN.base_url)

    def test_codex_cli_binding_must_resolve_reviewed_responses_realm(self) -> None:
        mutated = copy.deepcopy(self.raw)
        row = mutated["bindings"]["alibaba-token-plan-personal.codex-responses"]
        row["endpoint"]["base_url"] = "https://api.minimax.io/v1"
        with self.assertRaisesRegex(
            HarnessBindingError, "no exact reviewed Codex realm"
        ):
            validate_bindings(mutated, profiles_document=self.profiles)

        row["protocol"] = "openai-chat"
        row["endpoint"]["base_url"] = (
            "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
        )
        with self.assertRaisesRegex(
            HarnessBindingError, "not a reviewed Codex Responses lane"
        ):
            validate_bindings(mutated, profiles_document=self.profiles)

        row["protocol"] = "responses"
        row["implementation_state"] = "SPEC_ONLY"
        with self.assertRaisesRegex(
            HarnessBindingError, "not a reviewed Codex Responses lane"
        ):
            validate_bindings(mutated, profiles_document=self.profiles)

    def test_codex_cli_identity_must_agree(self) -> None:
        mutated = copy.deepcopy(self.raw)
        mutated["bindings"]["alibaba-token-plan-personal.codex-responses"][
            "harness_id"
        ] = "openai-compatible-coding-tool"
        with self.assertRaisesRegex(
            HarnessBindingError, "codex harness identity disagrees"
        ):
            validate_bindings(mutated, profiles_document=self.profiles)

    def test_mixed_case_codex_cli_identity_agrees_and_normalizes(self) -> None:
        mutated = copy.deepcopy(self.raw)
        row = mutated["bindings"]["alibaba-token-plan-personal.codex-responses"]
        row["harness_id"] = "Codex-CLI"
        row["adapter_id"] = "codex-cli"
        validate_bindings(mutated, profiles_document=self.profiles)
        binding = get_binding(
            "alibaba-token-plan-personal.codex-responses",
            document=mutated,
            profiles_document=self.profiles,
        )
        self.assertEqual(binding.harness_id, "codex-cli")
        self.assertEqual(binding.adapter_id, "codex-cli")

    def test_cased_codex_identity_disagreement_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.raw)
        row = mutated["bindings"]["alibaba-token-plan-personal.codex-responses"]
        row["harness_id"] = "CODEX-CLI"
        row["adapter_id"] = "openai-compatible-coding-tool"
        with self.assertRaisesRegex(
            HarnessBindingError, "codex harness identity disagrees"
        ):
            validate_bindings(mutated, profiles_document=self.profiles)

        row["harness_id"] = "openai-compatible-coding-tool"
        row["adapter_id"] = "CODEX-CLI"
        with self.assertRaisesRegex(
            HarnessBindingError, "codex harness identity disagrees"
        ):
            validate_bindings(mutated, profiles_document=self.profiles)

    def test_cased_codex_cli_openai_chat_binding_is_refused(self) -> None:
        mutated = copy.deepcopy(self.raw)
        row = mutated["bindings"]["alibaba-token-plan-personal.codex-responses"]
        row["harness_id"] = "Codex-cli"
        row["adapter_id"] = "CODEX-CLI"
        row["protocol"] = "openai-chat"
        with self.assertRaisesRegex(
            HarnessBindingError, "not a reviewed Codex Responses lane"
        ):
            validate_bindings(mutated, profiles_document=self.profiles)

    def test_cased_codex_cli_spec_only_binding_is_refused(self) -> None:
        mutated = copy.deepcopy(self.raw)
        row = mutated["bindings"]["alibaba-token-plan-personal.codex-responses"]
        row["harness_id"] = "Codex-cli"
        row["adapter_id"] = "CODEX-CLI"
        row["implementation_state"] = "SPEC_ONLY"
        with self.assertRaisesRegex(
            HarnessBindingError, "not a reviewed Codex Responses lane"
        ):
            validate_bindings(mutated, profiles_document=self.profiles)

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
            "glm-coding-plan.claude-code-anthropic",
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

    def test_extra_binding_key_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.raw)
        row = mutated["bindings"]["alibaba-token-plan-personal.codex-responses"]
        row["realm_id"] = "minimax-token-plan"
        with self.assertRaisesRegex(HarnessBindingError, "has invalid fields"):
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

    def test_openai_protocol_profile_binds_through_get_binding(self) -> None:
        self.assertEqual(PROVIDER_PROTOCOLS, {"anthropic", "openai-chat", "responses"})
        with self.assertRaises(ProviderProtocolError):
            validate_provider_protocol("openai-compatible")
        with self.assertRaises(ProviderProtocolError):
            validate_provider_protocol("unknown-wire")

        profiles = copy.deepcopy(self.profiles)
        profiles["profiles"]["minimax-token-plan"]["protocol"] = "unknown-wire"
        with self.assertRaisesRegex(ProviderProfileError, "unsupported protocol"):
            validate_profiles(profiles)

        profiles = copy.deepcopy(self.profiles)
        openai_row = copy.deepcopy(profiles["profiles"]["minimax-token-plan"])
        openai_row["protocol"] = "openai-chat"
        openai_row["base_url"] = "https://api.minimax.io/v1"
        profiles["profiles"]["minimax-openai-chat-plan"] = openai_row
        validate_profiles(profiles)
        bindings = copy.deepcopy(self.raw)
        row = copy.deepcopy(bindings["bindings"]["minimax-token-plan.openai-compatible"])
        row["profile_id"] = "minimax-openai-chat-plan"
        row["protocol"] = "openai-chat"
        row["endpoint"] = {"source": "profile"}
        bindings["bindings"]["minimax-openai-chat-plan.openai-chat"] = row
        binding = get_binding(
            "minimax-openai-chat-plan.openai-chat",
            document=bindings,
            profiles_document=profiles,
        )
        profile = get_profile("minimax-openai-chat-plan", document=profiles)
        self.assertEqual(binding.protocol, "openai-chat")
        self.assertEqual(binding.effective_base_url, profile.base_url)

        row["protocol"] = "unknown-wire"
        with self.assertRaisesRegex(HarnessBindingError, "protocol is unsupported"):
            validate_bindings(bindings, profiles_document=profiles)

    def test_no_subscription_binding_is_armed(self) -> None:
        armed = {
            binding_id
            for binding_id in self.catalog["bindings"]
            if get_binding(
                binding_id,
                document=self.catalog,
                profiles_document=self.profiles,
            ).autonomous_allowed
        }
        # control_plane/claude_subscription_worker.py:321-322 refuses to compose
        # any binding or profile with autonomous_allowed true ("subscription
        # profile may not self-arm autonomous routing"), so an armed row is a
        # row the reviewed worker rejects.
        self.assertEqual(armed, set())

    def test_minimax_codex_binding_loads_and_validates(self) -> None:
        # The production document itself validates: the row is present and the
        # reviewed MiniMax Responses realm lets it through load_bindings.
        self.assertIn("minimax-token-plan.codex-responses", self.raw["bindings"])
        validate_bindings(self.raw, profiles_document=self.profiles)
        binding = get_binding(
            "minimax-token-plan.codex-responses",
            document=self.catalog,
            profiles_document=self.profiles,
        )
        self.assertEqual(binding.profile_id, "minimax-token-plan")
        self.assertEqual(binding.provider, "minimax")
        self.assertEqual(binding.harness_id, "codex-cli")
        self.assertEqual(binding.protocol, "responses")
        self.assertEqual(binding.effective_base_url, "https://api.minimax.io/v1")
        self.assertEqual(
            binding.model_classes, ("routine", "hard", "fast", "subagent")
        )
        self.assertEqual(
            binding.activation_gates,
            (
                "adapter_implemented",
                "provider_realm_enrolled",
                "capacity_known",
                "real_canary_passed",
                "usage_policy_satisfied",
            ),
        )

    def test_minimax_codex_binding_uses_implemented_codex_cli_adapter(self) -> None:
        binding = get_binding(
            "minimax-token-plan.codex-responses",
            document=self.catalog,
            profiles_document=self.profiles,
        )
        self.assertEqual(binding.adapter_id, "codex-cli")
        descriptor = adapter_descriptor(binding.adapter_id)
        self.assertTrue(descriptor.implemented)

    def test_minimax_codex_binding_is_built_not_proven_and_disarmed(self) -> None:
        binding = get_binding(
            "minimax-token-plan.codex-responses",
            document=self.catalog,
            profiles_document=self.profiles,
        )
        self.assertEqual(binding.implementation_state, "BUILT_NOT_PROVEN")
        self.assertIs(binding.autonomous_allowed, False)
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
        self.assertIn(
            "real_canary_not_passed",
            autonomous_activation_blockers(
                binding,
                adapter_implemented=True,
                provider_realm_enrolled=True,
                capacity_known=True,
                real_canary_passed=False,
                usage_policy_satisfied=True,
            ),
        )

    def test_minimax_openai_compatible_row_stays_spec_only(self) -> None:
        # The openai-compatible adapter is declared implemented=False in
        # control_plane/worker_adapter.py, so this row may never claim more.
        descriptor = adapter_descriptor("openai-compatible")
        self.assertFalse(descriptor.implemented)
        openai_compatible = get_binding(
            "minimax-token-plan.openai-compatible",
            document=self.catalog,
            profiles_document=self.profiles,
        )
        self.assertEqual(openai_compatible.implementation_state, "SPEC_ONLY")
        self.assertIs(openai_compatible.autonomous_allowed, False)
        self.assertEqual(openai_compatible.adapter_id, "openai-compatible")

    def test_minimax_rows_carry_their_truthful_states(self) -> None:
        claude_anthropic = get_binding(
            "minimax-token-plan.claude-code-anthropic",
            document=self.catalog,
            profiles_document=self.profiles,
        )
        self.assertEqual(claude_anthropic.implementation_state, "BUILT_NOT_PROVEN")
        self.assertIs(claude_anthropic.autonomous_allowed, False)

        codex_responses = get_binding(
            "minimax-token-plan.codex-responses",
            document=self.catalog,
            profiles_document=self.profiles,
        )
        self.assertEqual(codex_responses.implementation_state, "BUILT_NOT_PROVEN")
        self.assertIs(codex_responses.autonomous_allowed, False)

        openai_compatible = get_binding(
            "minimax-token-plan.openai-compatible",
            document=self.catalog,
            profiles_document=self.profiles,
        )
        self.assertEqual(openai_compatible.implementation_state, "SPEC_ONLY")
        self.assertIs(openai_compatible.autonomous_allowed, False)


if __name__ == "__main__":
    unittest.main()
