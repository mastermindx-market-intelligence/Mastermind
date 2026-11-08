"""Original Hermes role recovery after the owner's completed retained-Go ingress.

Reuse the accepted retained-owner fixtures. These cases add the two service
publication interruption boundaries and preserve strict historical status.
All owners and credentials are disposable; no live/provider effect is claimed.
"""
import json
from pathlib import Path
from unittest import mock

import pytest

from test_hermes_primary_application_enrollment import PROFILES, select_role, isolated_native_service_imports
from test_go_native_stage import builds, native_stage, g, installer
from test_go_native_install import retained_go_owner
from test_native_launcher_successor_transition import source_owners, owner
from test_go_service_enrollment import prepare, reseal_modified_entry_for_disposable_fixtures
from test_retained_go_service_enrollment import retained_service_owner, retained_ingress_unchanged


def test_completed_retained_ingress_does_not_relabel_or_replay_old_history(retained_service_owner):
    case = retained_service_owner
    paths = (case.go_bundle / "PLAN.json",
             case.store / "bootstrap/.go-application-ingress-v1.json",
             case.store / "bootstrap" / (case.go_plan["digest"] + ".go.json"))
    before = {path: (path.read_bytes(), path.stat().st_ino) for path in paths}
    with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("inspection wrote")), \
            mock.patch.object(g, "_select_locked", side_effect=AssertionError("inspection selected")):
        assert installer._completed_go_for_service(case.go_bundle)[0] == case.go_plan
        assert installer.reconcile_retained_go(case.go_bundle) == case.go_receipt
        for action in (installer.read_go, installer.apply_go, installer.reconcile_go):
            with pytest.raises(ValueError):
                action(case.go_bundle)
        # The historical status reader must keep authenticating the OLD bridges.
        with pytest.raises(ValueError):
            installer.read_retained_successor_after_bootstrap_prune(case.successor)
    assert {path: (path.read_bytes(), path.stat().st_ino) for path in paths} == before
    retained_ingress_unchanged(case)


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("boundary", ["binding-ack", "missing-receipt"])
def test_retained_role_recovery_uses_the_original_token_and_published_inode(
        retained_service_owner, profile, boundary):
    case = retained_service_owner
    select_role(case, profile)
    prepare(case)
    original_replace = installer.os.replace
    original_write = g.atomic_bytes
    original_secret = installer.secrets.token_urlsafe
    interrupted = []

    def replace(source, target):
        original_replace(source, target)
        if boundary == "binding-ack" and Path(target) == case.binding and not interrupted:
            interrupted.append(True)
            raise OSError("fixture original binding acknowledgement lost")

    def write(path, raw, mode):
        if boundary == "missing-receipt" and Path(path) == case.service_receipt and not interrupted:
            interrupted.append(True)
            raise OSError("fixture original receipt absent")
        return original_write(path, raw, mode)

    with mock.patch.object(installer.secrets, "token_urlsafe", wraps=original_secret) as minted:
        with mock.patch.object(installer.os, "replace", side_effect=replace), \
                mock.patch.object(g, "atomic_bytes", side_effect=write), \
                pytest.raises(OSError, match="fixture original"):
            installer.apply_go_service_enrollment(case.service_bundle)
    assert interrupted == [True] and minted.call_count == 1
    original_binding = (case.binding.read_bytes(), case.binding.stat().st_ino)
    assert not case.service_receipt.exists()

    def receipt_only(path, raw, mode):
        assert Path(path) == case.service_receipt, "reconciliation rewrote a settled target"
        return original_write(path, raw, mode)

    with mock.patch.object(installer.secrets, "token_urlsafe", side_effect=AssertionError("recovery minted")), \
            mock.patch.object(g, "_select_locked", side_effect=AssertionError("recovery selected")):
        if boundary == "binding-ack":
            with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("partial inspection wrote")):
                assert installer.reconcile_go_service_enrollment(case.service_bundle)["disposition"] == "partial"
            receipt = installer.apply_go_service_enrollment(case.service_bundle)
        else:
            with mock.patch.object(g, "atomic_bytes", side_effect=receipt_only):
                receipt = installer.reconcile_go_service_enrollment(case.service_bundle)
        with mock.patch.object(g, "atomic_bytes", side_effect=AssertionError("completed recovery wrote")):
            assert installer.apply_go_service_enrollment(case.service_bundle) == receipt
            assert installer.reconcile_go_service_enrollment(case.service_bundle) == receipt
    assert (case.binding.read_bytes(), case.binding.stat().st_ino) == original_binding
    assert json.loads(case.accounts.read_bytes())["application_grants"] == [case.specification["grant"]]
    retained_ingress_unchanged(case)
