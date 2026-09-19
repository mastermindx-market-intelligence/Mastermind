from __future__ import annotations

import json
import unittest
from dataclasses import replace

from control_plane.subscription_harness_bindings import get_binding
from ops.executive_os import provider_worker_slots as slots


class SubscriptionWorkerSlotsTest(unittest.TestCase):
    def test_legacy_codex_inventory_is_unchanged(self) -> None:
        self.assertEqual(
            tuple(row.slot_id for row in slots.all_slots()),
            ("codex-01", "codex-pro-01", "codex-pro-02", "codex-pro-03"),
        )
        self.assertEqual(
            tuple(row.worker_uid for row in slots.all_slots()),
            (451, 454, 455, 456),
        )

    def test_subscription_candidates_are_held_and_collision_free(self) -> None:
        catalog = slots.subscription_slots()
        self.assertEqual(
            tuple((row.slot_id, row.provider, row.worker_uid) for row in catalog),
            (
                ("alibaba-token-01", "alibaba", 458),
                ("minimax-token-01", "minimax", 459),
            ),
        )
        legacy = slots.all_slots()
        for row in catalog:
            self.assertEqual(row.worker_gid, row.worker_uid)
            self.assertEqual(row.admission_state, "HELD_FOR_REAL_CANARY")
            self.assertNotIn(row.worker_uid, {slot.worker_uid for slot in legacy})
            self.assertNotIn(row.worker_gid, {slot.worker_gid for slot in legacy})
            self.assertNotIn(row.provider_home, {slot.provider_home for slot in legacy})

    def test_candidates_point_to_reviewed_disarmed_bindings(self) -> None:
        for row in slots.subscription_slots():
            with self.subTest(slot_id=row.slot_id):
                binding = get_binding(row.harness_binding_id)
                self.assertEqual(binding.profile_id, row.profile_id)
                self.assertEqual(binding.provider, row.provider)
                self.assertEqual(binding.adapter_id, "codex-cli")
                self.assertEqual(binding.implementation_state, "BUILT_NOT_PROVEN")
                self.assertFalse(binding.autonomous_allowed)

    def test_public_descriptors_have_no_secret_host_or_capacity_identity(self) -> None:
        rendered = json.dumps(
            [row.public_descriptor() for row in slots.subscription_slots()]
        )
        for forbidden in (
            "provider_home",
            "worker_config",
            "credential",
            "api_key",
            "capacity_capability_id",
            "account_label",
            "token-plan.ap",
            "/var/db/",
            "/Library/",
            "@",
            "auth.json",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_mutations_cannot_alias_existing_principals_or_binding(self) -> None:
        catalog = list(slots.subscription_slots())
        row = catalog[0]
        for mutated in (
            replace(row, worker_uid=451),
            replace(row, worker_gid=457),
            replace(row, harness_binding_id="minimax-token-plan.openai-compatible"),
            replace(row, admission_state="READY"),
        ):
            with self.subTest(mutated=mutated):
                candidate = list(catalog)
                candidate[0] = mutated
                with self.assertRaises(slots.SlotCatalogError):
                    slots.validate_subscription_slots(candidate)

    def test_unknown_subscription_slot_refuses_without_fallback(self) -> None:
        with self.assertRaisesRegex(
            slots.SlotCatalogError, "unknown_subscription_slot"
        ):
            slots.get_subscription_slot("alibaba-token-02")


if __name__ == "__main__":
    unittest.main()
