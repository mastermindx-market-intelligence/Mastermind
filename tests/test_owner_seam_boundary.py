from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FORGE_PROBE = """
import json
import os
import sys

sys.path.insert(0, os.environ["MASTERMIND_REPO"])

import control_plane.codex_provider_realm as realm
import control_plane.model_router as model_router
from control_plane.executive_steward import CapacityState

results = {}

results["capacity_name_absent"] = not hasattr(
    model_router, "_CAPACITY_OWNER_TEST_KEY"
)

try:
    model_router.set_capacity_owner_test_key(b"attacker-capacity-key-1234567890")
except Exception as exc:
    results["capacity_setter"] = f"{type(exc).__name__}: {exc}"

try:
    model_router.export_capacity_owner_fact(
        worker_id="attacker-99",
        state=CapacityState.AVAILABLE,
        generation=999,
    )
except Exception as exc:
    results["capacity_mint"] = f"{type(exc).__name__}: {exc}"

results["realm_names_absent"] = not hasattr(
    realm, "_PROVIDER_REALM_TEST_KEY"
) and not hasattr(realm, "_PROVIDER_REALM_TEST_ENROLLMENT")

try:
    realm.set_provider_realm_test_key(b"attacker-realm-key-1234567890")
except Exception as exc:
    results["realm_key_setter"] = f"{type(exc).__name__}: {exc}"

try:
    realm.set_provider_realm_test_enrollment("enrolled")
except Exception as exc:
    results["realm_enrollment_setter"] = f"{type(exc).__name__}: {exc}"

try:
    realm.issue_provider_realm_enrollment_receipt(
        binding_id="glm-coding-plan.claude-code-anthropic",
        generation=999,
    )
except Exception as exc:
    results["realm_mint"] = f"{type(exc).__name__}: {exc}"

try:
    realm._realm_receipt_seal({"attacker": True})
except Exception as exc:
    results["realm_key"] = f"{type(exc).__name__}: {exc}"

print(json.dumps(results))
"""

EXPECTED = {
    "capacity_name_absent": True,
    "capacity_setter": "RoutingPolicyError: capacity owner test key is test-only",
    "capacity_mint": "RoutingPolicyError: capacity owner key is not available",
    "realm_names_absent": True,
    "realm_key_setter": (
        "ProviderRealmError: provider-realm owner test key is test-only"
    ),
    "realm_enrollment_setter": (
        "ProviderRealmError: provider-realm test enrollment is test-only"
    ),
    "realm_mint": (
        "ProviderRealmFactError: enrollment_state is not observed by "
        "the provider-realm owner"
    ),
    "realm_key": "ProviderRealmError: provider-realm owner key is not available",
}


def test_owner_seam_has_no_non_pytest_attribute_or_mint_path():
    env = os.environ.copy()
    env["MASTERMIND_REPO"] = os.fspath(ROOT)
    env.pop("PYTEST_CURRENT_TEST", None)
    completed = subprocess.run(
        [sys.executable, "-c", FORGE_PROBE],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    observed = json.loads(completed.stdout)
    assert observed == EXPECTED
