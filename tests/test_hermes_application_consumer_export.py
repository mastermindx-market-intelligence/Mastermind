"""Consumer evidence through the actual original enrollment and grant owners."""
import copy
import json
from pathlib import Path
import sys
import time
from unittest import mock

import pytest

from tests.test_hermes_primary_application_enrollment import (
    builds, native_stage, g, installer, loaded_entry, native_module_namespace,
    go_owner, source_owners, owner, service_owner, prepare, selected_purpose,
    unchanged_ingress, isolated_native_service_imports, select_role, routed_role,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops/native_fabric/quota_continuity/rollout"))
import export_application_consumer as consumer


def enroll(case, *, automatic=False):
    if automatic:
        routed_role(case, "hermes-attended")
    else:
        select_role(case, "hermes-attended")
    prepare(case)
    installer.apply_go_service_enrollment(case.service_bundle)
    return case


@pytest.mark.parametrize("automatic", [False, True])
def test_consumer_observation_uses_completed_owner_and_current_grants_without_writes(
        service_owner, monkeypatch, automatic):
    case = enroll(service_owner, automatic=automatic)
    before = {path: path.read_bytes() for path in (
        case.binding, case.intent, case.service_receipt, case.accounts)}
    private = json.loads(before[case.binding])
    with mock.patch.object(installer.generation, "atomic_bytes",
                           side_effect=AssertionError("observation wrote owner state")):
        result = consumer.observe_application_consumer(case.go_bundle, "hermes-attended")
    assert result["schema"] == consumer.SCHEMA
    assert result["enrollment"]["operation_id"] == private["operation_id"]
    assert result["selection"]["kind"] == ("auto" if automatic else "fixed")
    assert result["scope"]["credential_ref"] == "HERMES_ATTENDED_FABRIC_APPLICATION_TOKEN"
    expected = json.loads(case.accounts.read_bytes())["application_grants"]
    assert result["eligibility"]["qualified_until"] == min(row["expires_at"] for row in expected)
    assert result["eligibility"]["routes"]
    from ops.executive_os.hermes_attended_configuration import validate_observation
    assert validate_observation(result, result["observation_sha256"]) == result
    rendered = json.dumps(result)
    assert private["credential"] not in rendered
    assert str(case.profile) not in rendered
    assert "binding_sha256" not in rendered and "account-a" not in rendered
    assert result["authority"] == {
        "grant_issued": False, "credential_included": False, "capacity_reserved": False,
        "provider_readiness_proven": False, "admission_required": True}
    assert all(path.read_bytes() == raw for path, raw in before.items())


@pytest.mark.parametrize("change", ["expired", "revoked", "absent", "ambiguous", "credential"])
def test_consumer_observation_cannot_turn_historical_receipt_into_current_authority(
        service_owner, change):
    case = enroll(service_owner)
    document = json.loads(case.accounts.read_bytes())
    grants = document["application_grants"]
    if change == "expired":
        grants[0]["expires_at"] = time.time() - 1
    elif change == "revoked":
        grants[0]["enabled"] = False
    elif change == "absent":
        del document["application_grants"]
    elif change == "ambiguous":
        other = copy.deepcopy(grants[0])
        other["grant_id"] += "-ambiguous"
        grants.append(other)
    else:
        grants[0]["credential_ref"] = "FOREIGN_APPLICATION_REFERENCE"
    case.accounts.write_text(json.dumps(document))
    with pytest.raises(ValueError):
        consumer.observe_application_consumer(case.go_bundle, "hermes-attended")
    # The same historical enrollment still authenticates original recovery.
    with loaded_entry(case.published, clean_yaml=True) as entry:
        startup = entry.inspect(verified_root=case.published.release, verified_metadata=case.published.meta)
        assert len(entry.load_completed_application_startup(startup, "hermes-attended")[0]) == 1


def test_consumer_observation_cannot_substitute_another_role(service_owner):
    case = enroll(service_owner)
    with pytest.raises(ValueError):
        consumer.observe_application_consumer(case.go_bundle, "hermes-secretary")
