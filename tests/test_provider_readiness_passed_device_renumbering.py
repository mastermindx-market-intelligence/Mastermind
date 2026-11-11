"""Bounded PASS revalidation after a paired filesystem device renumbering.

Provider observations are synthetic. Temporary receipt files exercise the real
archive, compare-and-swap, reservation and finalization owner; no credential,
provider process, service or network endpoint is accessed.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from datetime import timedelta
from pathlib import Path

import pytest

from ops.executive_os import provider_readiness as r
from tests.test_provider_native_probe_drift import T, case as native_case, stamp


FLAG = "--requalify-passed-device-renumbering-sha256"
OLD_DEVICE = 16777234
NEW_DEVICE = 16777232
SCRIPT = Path(__file__).resolve().parents[1] / "ops/executive_os/provision-worker-auth.sh"


@pytest.fixture
def case(native_case):
    value = copy.deepcopy(native_case["old"])
    for metadata in (
        value["credential_lstat"], value["codex_binary"],
        value["provider_identity"]["credential_lstat"],
        value["provider_identity"]["codex_binary"],
    ):
        metadata["device"] = OLD_DEVICE
    auth = {**value["credential_lstat"], "device": NEW_DEVICE}
    binary = {**value["codex_binary"], "device": NEW_DEVICE}
    fresh = copy.deepcopy(value["provider_identity"])
    fresh.update(observed_at=stamp(T), credential_lstat=dict(auth), codex_binary=dict(binary))
    return dict(old=value, auth=auth, binary=binary, fresh=fresh,
                deadline=stamp(T + timedelta(minutes=45)))


def inputs(case):
    return dict(auth_identity=case["auth"], binary_identity=case["binary"],
                expected_kind="device-auth",
                workspace_binding_class=r.COMPANY_WORKSPACE_BINDING_CLASS)


def validate(case, **changes):
    r.validate_passed_device_renumbering_predecessor_document(
        case["old"], **(inputs(case) | changes))


@pytest.mark.parametrize("minutes,allowed", [(30, False), (31, True), (45, True), (60, True), (61, False)])
def test_only_paired_change_with_bounded_fresh_deadline_is_eligible(case, minutes, allowed):
    before = copy.deepcopy(case)

    def classify():
        r.classify_passed_device_renumbering_requalification(
            case["old"], **inputs(case),
            new_credential_expires_at=stamp(T + timedelta(minutes=minutes)))

    if allowed:
        classify()
    else:
        with pytest.raises(r.ReadinessError, match="deadline_out_of_bounds"):
            classify()
    assert case == before


@pytest.mark.parametrize("defect", [
    "unchanged", "auth_only", "binary_only", "old_devices_differ", "new_devices_differ",
    "float_old_device", "float_new_device", "bool_new_device", "zero_new_device",
])
def test_device_change_must_be_typed_nonzero_and_coupled(case, defect):
    if defect == "unchanged":
        case["auth"]["device"] = case["binary"]["device"] = OLD_DEVICE
    elif defect == "auth_only":
        case["binary"]["device"] = OLD_DEVICE
    elif defect == "binary_only":
        case["auth"]["device"] = OLD_DEVICE
    elif defect == "old_devices_differ":
        case["old"]["codex_binary"]["device"] += 1
        case["old"]["provider_identity"]["codex_binary"]["device"] += 1
    elif defect == "new_devices_differ":
        case["binary"]["device"] += 1
    elif defect == "float_old_device":
        for metadata in (case["old"]["credential_lstat"], case["old"]["codex_binary"],
                         case["old"]["provider_identity"]["credential_lstat"],
                         case["old"]["provider_identity"]["codex_binary"]):
            metadata["device"] = float(OLD_DEVICE)
    else:
        value = {"float_new_device": float(NEW_DEVICE), "bool_new_device": True,
                 "zero_new_device": 0}[defect]
        case["auth"]["device"] = case["binary"]["device"] = value
    with pytest.raises(r.ReadinessError):
        validate(case)


@pytest.mark.parametrize("component", ["auth", "binary"])
@pytest.mark.parametrize("field", ["inode", "uid", "gid", "mode", "size", "mtime_ns", "ctime_ns", "nlink"])
def test_no_other_filesystem_identity_change_is_admitted(case, component, field):
    case[component][field] += 1
    with pytest.raises(r.ReadinessError):
        validate(case)


@pytest.mark.parametrize("component,field", [("auth", "inode"), ("binary", "mtime_ns")])
def test_numeric_equality_cannot_hide_untyped_metadata(case, component, field):
    case[component][field] = float(case[component][field])
    with pytest.raises(r.ReadinessError):
        validate(case)


@pytest.mark.parametrize("field,value", [
    ("path", "/tmp/unreviewed-codex"), ("version", r.REQUALIFICATION_PREDECESSOR_VERSION),
    ("sha256", r.REQUALIFICATION_PREDECESSOR_SHA256), ("team_identifier", "UNREVIEWED"),
])
def test_binary_pin_is_independent_of_device_continuity(case, field, value):
    # Even mutually consistent old/current metadata cannot nominate another binary.
    for binary in (case["binary"], case["old"]["codex_binary"],
                   case["old"]["provider_identity"]["codex_binary"]):
        binary[field] = value
    with pytest.raises(r.ReadinessError):
        validate(case)


@pytest.mark.parametrize("defect", [
    "not_expired", "adverse", "reserved", "failed_canary", "missing_canary",
    "identity_receipt_mismatch", "unexpected_field",
])
def test_other_predecessor_classes_cannot_acquire_pass_credit(case, defect):
    old = case["old"]
    if defect == "not_expired":
        old["credential_expires_at"] = stamp(T + timedelta(minutes=45))
    elif defect == "adverse":
        old.update(passed=False, refusal="provider_turn_failed")
    elif defect == "reserved":
        old.update(passed=False, refusal="canary_reserved", inference_canary=None)
    elif defect == "failed_canary":
        old["inference_canary"].update(passed=False, refusal="provider_turn_failed")
    elif defect == "missing_canary":
        old["inference_canary"] = None
    elif defect == "identity_receipt_mismatch":
        old["provider_identity"]["credential_lstat"]["inode"] += 1
    else:
        old["renewal_authorized"] = True
    with pytest.raises(r.ReadinessError):
        validate(case)


@pytest.mark.parametrize("changes", [
    {"expected_kind": "service-account"},
    {"workspace_binding_class": r.PERSONAL_PRO_WORKER_BINDING_CLASS},
    {"worker_uid": 454}, {"worker_gid": 454},
])
def test_route_cannot_be_relabelled_to_another_credential_or_slot(case, changes):
    with pytest.raises(r.ReadinessError, match="requires_company_device_auth"):
        validate(case, **changes)


def encoded(document):
    return (json.dumps(document, sort_keys=True, indent=2) + "\n").encode()


@pytest.fixture
def stored(case, tmp_path, monkeypatch):
    receipt = tmp_path / "readiness.json"
    receipt.write_bytes(encoded(case["old"]))
    receipt.chmod(0o600)
    auth = tmp_path / "opaque-auth.json"
    auth.write_bytes(b"synthetic opaque credential bytes: never parsed\n")
    identity = tmp_path / "identity.json"
    identity.write_bytes(encoded(case["fresh"]))
    storage_gid = receipt.stat().st_gid
    # Only platform observations/custody are substituted. The real transaction
    # reads and seals the temporary receipt, archives it and checks its identity.
    monkeypatch.setattr(r, "RECEIPT_PATH", receipt)
    monkeypatch.setattr(r, "AUTH_PATH", auth)
    monkeypatch.setattr(r.os, "geteuid", lambda: 0)
    monkeypatch.setattr(r, "receipt_storage_contract", lambda **kw: (os.getuid(), storage_gid, 0o600))
    monkeypatch.setattr(r, "_validate_receipt_directory", lambda path: None)
    monkeypatch.setattr(r, "current_auth_identity", lambda *a, **kw: dict(case["auth"]))
    monkeypatch.setattr(r, "current_binary_identity", lambda *a, **kw: dict(case["binary"]))
    return dict(case=case, receipt=receipt, auth=auth, identity=identity,
                raw=receipt.read_bytes(), digest=hashlib.sha256(receipt.read_bytes()).hexdigest())


def argv(stored, command, *, explicit=True, **changes):
    options = dict(receipt=stored["receipt"], auth=stored["auth"], binary=r.CODEX_BINARY,
                   expected_kind="device-auth", workspace_binding_class=r.COMPANY_WORKSPACE_BINDING_CLASS,
                   credential_expires_at=stored["case"]["deadline"])
    if explicit:
        options[FLAG[2:].replace("-", "_")] = stored["digest"]
    if command == "reserve":
        options["identity_json"] = stored["identity"]
    options.update(changes)
    return [command, *(item for key, value in options.items()
                       for item in ("--" + key.replace("_", "-"), str(value)))]


def assert_untouched(stored):
    assert stored["receipt"].read_bytes() == stored["raw"]
    assert list(stored["receipt"].parent.glob("*.superseded-*")) == []


def test_explicit_eligibility_is_readonly_and_is_not_ready_or_automatic(stored):
    assert r.main(argv(stored, "reuse", explicit=False)) == 2
    assert r.main(argv(stored, "reserve", explicit=False)) == 2
    assert r.main(argv(stored, "reuse")) == 11
    with pytest.raises(r.ReadinessError):
        r.validate_receipt_file(stored["receipt"], auth_path=stored["auth"])
    assert_untouched(stored)


def test_exact_preimage_is_generic_and_never_an_incident_hash_exemption(stored):
    # A second valid, differently serialized historical receipt needs its own
    # current hash; neither document depends on a privileged fixture hash.
    assert r.main(argv(stored, "reuse")) == 11
    replacement = json.dumps(stored["case"]["old"], sort_keys=True, separators=(",", ":")).encode()
    stored["receipt"].write_bytes(replacement)
    assert r.main(argv(stored, "reuse")) == 2
    digest = hashlib.sha256(replacement).hexdigest()
    assert digest != stored["digest"]
    assert r.main(argv(stored, "reuse", requalify_passed_device_renumbering_sha256=digest)) == 11
    assert stored["receipt"].read_bytes() == replacement
    assert list(stored["receipt"].parent.glob("*.superseded-*")) == []


@pytest.mark.parametrize("digest", ["a" * 64, "A" * 64, "short", r.NATIVE_PROBE_DRIFT_PREDECESSOR_SHA256])
def test_wrong_or_historical_preimage_never_archives(stored, digest):
    assert r.main(argv(stored, "reserve", requalify_passed_device_renumbering_sha256=digest)) == 2
    assert_untouched(stored)


@pytest.mark.parametrize("field", ["receipt", "auth", "binary"])
def test_explicit_route_rejects_noncanonical_paths(stored, field):
    assert r.main(argv(stored, "reserve", **{field: stored["receipt"].parent / "alternate"})) == 2
    assert_untouched(stored)


@pytest.mark.parametrize("command", ["reuse", "reserve"])
def test_worker_cannot_self_authorize_explicit_transition(stored, monkeypatch, capsys, command):
    monkeypatch.setattr(r.os, "geteuid", lambda: 451)
    assert r.main(argv(stored, command)) == 2
    assert "passed_device_renumbering_requires_root" in capsys.readouterr().err
    assert_untouched(stored)


@pytest.mark.parametrize("defect", ["stale", "future", "refused", "auth", "binary", "plan"])
def test_fresh_identity_must_match_before_any_archive(stored, defect):
    identity = copy.deepcopy(stored["case"]["fresh"])
    if defect in {"stale", "future"}:
        identity["observed_at"] = stamp(T + timedelta(minutes=-6 if defect == "stale" else 6))
    elif defect == "refused":
        identity["refusal"] = "credential_identity_changed_during_probe"
    elif defect == "auth":
        identity["credential_lstat"]["mtime_ns"] += 1
    elif defect == "binary":
        identity["codex_binary"]["inode"] += 1
    else:
        identity["plan_type"] = "enterprise"
    stored["identity"].write_bytes(encoded(identity))
    assert r.main(argv(stored, "reserve")) == 2
    assert_untouched(stored)


def finalize(stored, *, passed=True, **changes):
    canary = copy.deepcopy(stored["case"]["old"]["inference_canary"])
    canary.update(canary_id="canary-fedcba987654", observed_at=stamp(T))
    if not passed:
        canary.update(passed=False, refusal="provider_turn_failed", exit_code=1,
                      terminal_event_class="turn_failed", result_valid=False)
    canary_path = stored["receipt"].parent / "canary.json"
    canary_path.write_bytes(encoded(canary))
    return r.main(argv(stored, "finalize", explicit=False,
                       post_identity_json=stored["identity"], post_identity_command_status=0,
                       canary_json=canary_path, canary_command_status=0 if passed else 1,
                       **changes))


@pytest.mark.parametrize("passed", [True, False])
def test_one_reservation_requires_fresh_canary_and_preserves_original_evidence(stored, passed):
    auth_bytes = stored["auth"].read_bytes()
    assert r.main(argv(stored, "reserve")) == 0
    reservation_bytes = stored["receipt"].read_bytes()
    reservation = json.loads(reservation_bytes)
    assert reservation["passed"] is False and reservation["refusal"] == "canary_reserved"
    assert reservation["inference_canary"] is None
    assert reservation["credential_lstat"] == stored["case"]["auth"]
    assert reservation["codex_binary"] == stored["case"]["binary"]
    archive, = stored["receipt"].parent.glob("*.superseded-*")
    assert archive.read_bytes() == stored["raw"]
    assert r.main(argv(stored, "reserve")) == 2
    assert r.main(argv(stored, "reserve", requalify_passed_device_renumbering_sha256=
                       hashlib.sha256(reservation_bytes).hexdigest())) == 2
    assert stored["receipt"].read_bytes() == reservation_bytes
    assert finalize(stored, passed=passed) == (0 if passed else 2)
    terminal_bytes = stored["receipt"].read_bytes()
    terminal = json.loads(terminal_bytes)
    assert terminal["passed"] is passed
    assert terminal["inference_canary"]["canary_id"] == "canary-fedcba987654"
    assert terminal["credential_lstat"] == stored["case"]["auth"]
    assert terminal["codex_binary"] == stored["case"]["binary"]
    assert terminal["credential_expires_at"] == stored["case"]["deadline"]
    if passed:
        r.validate_receipt_document(terminal, **inputs(stored["case"]))
    assert finalize(stored, passed=passed) == 2
    assert r.main(argv(stored, "reserve", requalify_passed_device_renumbering_sha256=
                       hashlib.sha256(terminal_bytes).hexdigest())) == 2
    assert stored["receipt"].read_bytes() == terminal_bytes
    assert archive.read_bytes() == stored["raw"]
    assert stored["auth"].read_bytes() == auth_bytes


@pytest.mark.parametrize("race", ["auth", "binary", "receipt"])
def test_archive_boundary_drift_never_overwrites_newer_state(stored, monkeypatch, race):
    persist = r._persist_superseded_receipt
    foreign_bytes = stored["raw"] + b" "

    def change_after_archive(*args, **kwargs):
        persist(*args, **kwargs)
        if race == "receipt":
            stored["receipt"].write_bytes(foreign_bytes)
        else:
            stored["case"][race]["inode"] += 1

    monkeypatch.setattr(r, "_persist_superseded_receipt", change_after_archive)
    assert r.main(argv(stored, "reserve")) == 2
    assert stored["receipt"].read_bytes() == (foreign_bytes if race == "receipt" else stored["raw"])
    archive, = stored["receipt"].parent.glob("*.superseded-*")
    assert archive.read_bytes() == stored["raw"]


@pytest.mark.parametrize("drift", ["auth", "binary", "provider_identity"])
def test_post_canary_identity_drift_is_terminal_adverse(stored, drift):
    assert r.main(argv(stored, "reserve")) == 0
    if drift in {"auth", "binary"}:
        stored["case"][drift]["mtime_ns"] += 1
    else:
        fresh = copy.deepcopy(stored["case"]["fresh"])
        fresh["plan_type"] = "enterprise"
        stored["identity"].write_bytes(encoded(fresh))
    assert finalize(stored) == 2
    terminal = json.loads(stored["receipt"].read_bytes())
    assert terminal["passed"] is False and terminal["refusal"] != "canary_reserved"
    archive, = stored["receipt"].parent.glob("*.superseded-*")
    assert archive.read_bytes() == stored["raw"]


@pytest.mark.parametrize("other", [
    "--renew-device-revalidation-sha256", "--requalify-terminal-adverse-sha256",
    "--requalify-same-generation-terminal-sha256", "--requalify-company-device-drift-sha256",
    "--requalify-native-probe-drift-sha256", "--recover-current-pin-grant-sha256",
])
def test_explicit_modes_are_mutually_exclusive_before_effects(stored, other):
    with pytest.raises(SystemExit) as error:
        r.main([*argv(stored, "reserve"), other, "a" * 64])
    assert error.value.code == 2
    assert_untouched(stored)


def test_shell_routes_eligibility_to_fresh_proof_and_forwards_the_same_preimage():
    source = SCRIPT.read_text()
    branch = source.split('if [ "$VERIFY_READY" = "true" ]; then', 1)[1].split(
        'if [ "$ENROLL_SERVICE_ACCOUNT" = "true" ]; then', 1)[0]
    before_probe = branch.split("IDENTITY_RESULT=", 1)[0]
    assert FLAG in before_probe
    match = re.search(r'(?:if|elif) \[ -n "\$REQUALIFY_PASSED_DEVICE_RENUMBERING_SHA256" \]; then\n'
                      r'(?P<body>.*?)(?=\n  (?:elif|else|fi)\b)',
                      before_probe.split('provider_readiness.py" reuse', 1)[1], re.S)
    assert match is not None
    assert '[ "$reuse_status" -eq 11 ]' in match["body"]
    assert "exit 65" in match["body"]
    forwarding = '${requalification_args[@]+"${requalification_args[@]}"}'
    assert before_probe.count(forwarding) == 1
    reserve_to_canary = branch.split('provider_readiness.py" reserve', 1)[1].split("CANARY_RESULT=", 1)[0]
    assert forwarding in reserve_to_canary and "exit 65" in reserve_to_canary
    assert branch.index("IDENTITY_RESULT=") < branch.index('provider_readiness.py" reserve')
    assert branch.index('provider_readiness.py" reserve') < branch.index("CANARY_RESULT=")
    assert branch.index("CANARY_RESULT=") < branch.index('provider_readiness.py" finalize')
