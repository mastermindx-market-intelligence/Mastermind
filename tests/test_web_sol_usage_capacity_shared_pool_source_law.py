from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AMENDMENT = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-09-02-web-sol-shared-capacity-pool-amendment.md"
)


def _text() -> str:
    return AMENDMENT.read_text(encoding="utf-8").lower()


def test_shared_pool_amendment_is_spec_only_same_operation():
    text = _text()

    assert "web-sol-pro-usage-observability-20260902-sol-001" in text
    assert "spec_only / production_inert" in text
    assert "shared pool topology amendment" in text


def test_realm_slots_and_capacity_resources_are_distinct():
    text = _text()

    assert "capacityrealmslot" in text
    assert "capacityresourcepool" in text
    assert "browser realm identity and capacity-resource identity are separate" in text
    assert "one shared resource may serve multiple realms" in text


def test_shared_balance_is_not_cloned_per_realm():
    text = _text()

    assert "do not copy a shared pool balance into every slot" in text
    assert "shared resource balances are stored once canonically and referenced" in text
    assert "duplicating quota horizons into every slot" in text


def test_slot_to_shared_pool_membership_requires_evidence():
    text = _text()

    assert "slot-to-resource links require proof" in text
    assert "matching browser profile names" in text
    assert "matching slack principals" in text
    assert "guessed seat ordinal" in text
    assert "unknown linkage remains unknown" in text


def test_included_allowance_and_shared_credits_are_not_collapsed():
    text = _text()

    assert "included allowance and purchased credits are sequential resources, not one sum" in text
    assert "remaining = included_remaining + workspace_credits" in text
    assert "included allowance, shared credits, usage limits and provider restrictions are not arithmetically collapsed" in text


def test_available_capacity_does_not_grant_spend_authority():
    text = _text()

    assert "capacity is not spend authority" in text
    assert "spend_authorized=false" in text
    assert "available purchased credits do not grant spend authority" in text


def test_provider_control_remains_single_owner_and_v1_is_not_patched():
    text = _text()

    assert "macro shared ai provider control remains the one owner" in text
    assert "current provider capacity v1 is not patched in place" in text
    assert "creating a web-sol-local workspace credit database" in text
    assert "adding a second capacity service" in text
