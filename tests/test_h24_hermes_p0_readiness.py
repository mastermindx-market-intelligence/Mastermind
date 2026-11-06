"""Fake original-owner receipts only: no host, key, service or provider effects."""
from __future__ import annotations

import builtins
import copy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
import subprocess
from types import SimpleNamespace
from unittest import mock

import unittest

from ops.executive_os import hermes_p0_readiness as checker
from integrations.hermes_runtime import isolation_probe as probe
from integrations.hermes_runtime.tests.test_isolation_probe import make_profile, identity
from ops.executive_os.release_manifest import validate_hermes_runtime_installation


NOW = 1793959200
LAW = "88a8b103a5a69e4b4e870a184655dde9fd5875c3"
ISSUER = "e" * 64
HOST = {"machine_id": "1" * 32, "boot_id": "11111111-2222-3333-4444-555555555555",
        "netns": [4, 5], "kernel": "fixture-kernel"}
EXPECTED = checker.ExpectedSource(checker.BASE_SHA, LAW, checker.BASE_SHA, ISSUER,
    original_operations={k: "original-" + k for k in ("origin", "workers", "c25", "c26")})


def stamp(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def fixture_file(role):
    uid = 2101 if role == "mmsecretary" else 2102
    return {"path": f"/srv/hermes/{role}/state/qualification/synthetic.txt",
            "sha256": checker.MARKER_SHA256,
            "facts": {"device": 1, "inode": uid, "uid": uid, "gid": uid,
                      "mode": "0o600", "nlink": 1, "size": len(checker.MARKER),
                      "mtime_ns": 10, "ctime_ns": 10}}


def listener(host, port):
    return {"kind": "owned_current_listener", "sufficient": True, "pid": 501,
            "start_ticks": 5000, "socket_fd": 7, "socket_inode": 333,
            "host": host, "port": port}


def native_report(role, run, end, sources, peer_digest=None):
    """Exercise the incumbent v2 report producer, not a look-alike report schema."""
    profile = make_profile(role)
    own, peer = fixture_file(role), fixture_file("mmmeta" if role == "mmsecretary" else "mmsecretary")
    ident = identity(role)
    guards = [{"name": name, "status": "PASS", "code": None} for name in probe.GUARD_ORDER]
    provenance = {"qualification_id": "h24-fake-q", "host": copy.deepcopy(HOST),
                  "sources": sources, "profile_sha256": ("a" if role == "mmsecretary" else "b") * 64,
                  "profile_file": {"device": 1, "inode": 2},
                  "profile_resolved": f"/srv/hermes/{role}/profile.yaml"}
    args = SimpleNamespace(_provenance=provenance, _profile_semantic={"fixture": True},
        external_address_fixtures=True, _context_stable=True, qualification_id="h24-fake-q",
        _observational_recheck={"observed_identity": copy.deepcopy(ident), "guards": guards[:3],
            "identity_matched": True, "guards_matched": True, "provenance_matched": True},
        own_file=Path(own["path"]), peer_file=Path(peer["path"]))
    records = {}
    for case in probe._bind_cases(role, profile.gateway_port, profile.backend_port, 45151):
        witness = {"sufficient": True}
        observed, code, symptom = case.expected, None, "connected"
        if case.case_id in checker.EXTERNAL:
            witness = {"sufficient": False, "external_positive_required": True}
            if case.case_id == "file.peer.read":
                if run == "A1":
                    observed, symptom = "UNAVAILABLE", ""
                else:
                    code, symptom = 13, "refused_immediately"
                    peer_role = "mmmeta" if role == "mmsecretary" else "mmsecretary"
                    witness.update(artifact_qualified=True, peer_report_sha256=peer_digest,
                        peer_role=peer_role, peer_file_path=peer["path"], peer_file_sha256=peer["sha256"],
                        peer_file_facts=peer["facts"])
            else:
                code, symptom = 11, "timed_out"
        elif case.case_id.startswith(("tcp.", "exec.")):
            w = listener(case.host, case.port)
            witness = {"sufficient": True, "before": w, "after": copy.deepcopy(w),
                       "pre_landlock_reached": True, "pre_landlock_exec": ["connected", None]}
            if case.case_id in checker.DENIED:
                code, symptom = 13, "refused_immediately"
        elif case.case_id.startswith("bind."):
            if "ephemeral" in case.case_id:
                witness = {"sufficient": True, "baseline": {"bound": True}}
                code, symptom = 13, "refused_immediately"
            else:
                witness = listener(case.host, case.port)
        elif case.case_id == "file.own.read":
            witness = {"kind": "bounded_synthetic_fd", "sufficient": True, **own}
        outcome = probe._Outcome(observed, errno=code, errno_name={1: "EPERM", 11: "EAGAIN", 13: "EACCES"}.get(code),
            symptom=symptom, witness=witness,
            target={"path": own["path"] if case.case_id == "file.own.read" else peer["path"]}
                   if case.case_id.startswith("file.") else None)
        records[case.case_id] = probe._case_record(case, outcome, selected=True)
    with mock.patch.object(probe, "_path_facts", return_value={"fixture_metadata_only": True}), \
         mock.patch.object(probe, "_utc_now", return_value=stamp(end)):
        return probe._build_report(profile, role, args.peer_file.parts[3], ident, guards, records,
            set(records), frozenset([profile.gateway_port, profile.backend_port]),
            frozenset([profile.gateway_port, profile.backend_port, checker.PORTS[role][3]]),
            45151, args, {"cleanup_complete": True}, {})


def unit(role, pin):
    name = f"hermes-runtime-{role}.service"
    return {"unit": name, "User": role, "Group": role, "FragmentPath": "/etc/systemd/system/" + name,
        "LoadState": "loaded", "NeedDaemonReload": "no", "Transient": "no", "DropInPaths": [],
        "fragment_sha256": pin["fragment_sha256"], "exec_start_sha256": pin["exec_start_sha256"],
        "root_custody_verified": True, "UnitFileState": "disabled", "MainPID": 0, "ControlPID": 0,
        "job_pending": False, "ActiveState": "failed" if role == "mmsecretary" else "inactive"}


def qualification_documents():
    roles = {}
    for role in checker.ROLES:
        uid = 2101 if role == "mmsecretary" else 2102
        roles[role] = {"uid": uid, "gid": uid, "state_dir": f"/srv/hermes/{role}/state",
            "profile_sha256": ("a" if role == "mmsecretary" else "b") * 64,
            "fragment_sha256": digest((role + "fragment").encode()),
            "exec_start_sha256": digest((role + "exec").encode()), "image_sha256": "4" * 64}
    binary = {"path": "/usr/bin/python3.12", "real_path": "/usr/bin/python3.12", "sha256": "4" * 64}
    runtime = {"schema": "mastermind.hermes_runtime_installation/v1",
        "bootstrap_python": binary, "launch_python": binary.copy(),
        "startup": {"profile": "cpython-3.12-linux-root-prefix-nosite.v1", "prefix": "/usr",
            "exec_prefix": "/usr", "base_prefix": "/usr", "base_exec_prefix": "/usr"},
        "roles": [{"role": role, "uid": roles[role]["uid"], "gid": roles[role]["gid"],
            "state_dir": roles[role]["state_dir"], "restart_sec": 2, "start_limit_burst": 5,
            "start_limit_interval_sec": 60} for role in ("mmmeta", "mmsecretary")]}
    # Fixture recipe really satisfies the incumbent closed validator.
    runtime = validate_hermes_runtime_installation(runtime)
    manifest = {"schema_version": checker.MANIFEST_SCHEMA, "commit_sha": checker.BASE_SHA,
                "tree_sha": "2" * 40, "entries": [{"path": "fixture.py", "size": 1, "sha256": "3" * 64}],
                "hermes_runtime": runtime}
    sources = {key: digest(key.encode()) for key in checker.PROBE_SOURCE_KEYS}
    source = {"implementation_sha": checker.BASE_SHA, "protected_law_sha": LAW,
        "upstream_sha": checker.UPSTREAM_SHA, "issuer_sha256": ISSUER,
        "immutable": True, "protected_pin_verified": True, "source_prepared": True,
        "tree_sha": "2" * 40, "manifest_sha256": digest(encoded(manifest)),
        "installed_inventory_sha256": "5" * 64, "probe_sources": sources, "roles": roles}
    effects = {k: {"operation_id": "original-" + k, "state": "RECONCILED", "denied": False,
                   "active_writer": False} for k in ("origin", "workers", "c25", "c26")}
    effects["new_authority_granted"] = False
    incumbents = {"observed_at_utc": stamp(NOW - 250)}
    for index, role in enumerate(("Control", "Worker")):
        record = {"pid": 100 + index, "start_ticks": 1000 + index, "boot_id": "control-boot",
                  "invocation_id": "incumbent-" + role, "implementation_sha": "6" * 40,
                  "config_sha256": "7" * 64, "running": True}
        incumbents[role] = {"before": record, "after": record.copy()}
    docs = {"source": source, "manifest": manifest, "effects": effects,
        "release": {"pr": {"number": 2120, "head_sha": checker.BASE_SHA, "merged": True,
            "state": "closed", "merge_commit_sha": checker.BASE_SHA}, "selected_commit": checker.BASE_SHA,
            "protected_release_accepted": True},
        "c25": {"operation_id": "original-c25", "implementation_sha": checker.BASE_SHA,
            "original_effect": "RECONCILED", "diagnostic": "UNRELATED_REF_BAD_TREE", "repair_accepted": True,
            "stage": {"staged_admin_checkout": True, "commit_sha": checker.BASE_SHA,
                      **{k: False for k in ("selection_changed", "services_changed", "configs_changed",
                                           "receipt_changed", "transaction_changed")}},
            "normalization": {"schema": "mastermind.executive_admin_checkout_normalization.v1",
                "commit": checker.BASE_SHA, "reachable_object_count": 20, "normalized_promisor_markers": 1}},
        "installation": {"implementation_sha": checker.BASE_SHA, "sealed": True, "staged_inert": True,
            "manifest": {"expected_sha256": source["manifest_sha256"], "observed_sha256": source["manifest_sha256"]},
            "inventory": {"expected_sha256": "5" * 64, "observed_sha256": "5" * 64}},
        "incumbents": incumbents,
        "units": {"implementation_sha": checker.BASE_SHA, "observed_at_utc": stamp(NOW - 250),
            "boot_id": HOST["boot_id"], "machine_id": HOST["machine_id"],
            "roles": {r: unit(r, roles[r]) for r in roles}},
        "qualification": {"implementation_sha": checker.BASE_SHA, "qualification_id": "h24-fake-q",
            "operation_id": "original-c26", "observed_at_utc": stamp(NOW - 100), "host": copy.deepcopy(HOST),
            "sources": sources, "runs": {}, "external_acceptance": "ACCEPTED_FOR_QUALIFICATION_ONLY"}}
    for index, (run, role) in enumerate(checker.RUNS.items()):
        start, end = NOW - 200 + index * 20, NOW - 190 + index * 20
        predecessor = {"B1": "A1", "A2": "B1"}.get(run)
        peer_digest = digest(encoded(docs[predecessor])) if predecessor else None
        docs[run] = native_report(role, run, end, sources, peer_digest)
        run_digest, invocation = digest(encoded(docs[run])), str(index + 1) * 32
        facts = {"role": role, "report_sha256": run_digest, "invocation_id": invocation,
            "pid": 800 + index, "start_ticks": 8000 + index, "started_at_utc": stamp(start),
            "finished_at_utc": stamp(end), "unit_fragment_sha256": roles[role]["fragment_sha256"], "external": {}}
        actual_unit = {"unit": f"hermes-runtime-{role}.service", "boot_id": HOST["boot_id"],
            "InvocationID": invocation, "ExecMainPID": facts["pid"], "start_ticks": facts["start_ticks"],
            "fragment_sha256": roles[role]["fragment_sha256"], "uid": roles[role]["uid"], "gid": roles[role]["gid"]}
        facts["unit_start"] = {**actual_unit, "MainPID": facts["pid"]}
        facts["unit_terminal"] = {**actual_unit, "MainPID": 0, "ExecMainStatus": 78}
        for case in sorted(checker.EXTERNAL):
            if run == "A1" and case == "file.peer.read":
                continue
            peer = "mmmeta" if role == "mmsecretary" else "mmsecretary"
            if case == "file.peer.read":
                before = {r: fixture_file(r) for r in checker.ROLES}
            else:
                host = checker.PORTS[peer][0] if "sibling" in case else "127.0.0.1"
                before = {**listener(host, checker.PORTS[role][1]), "outside_role_cgroup": True,
                          "connected": True, "uid": 0, "cgroup": "/operator-fixture"}
            ext = {"report_sha256": run_digest, "invocation_id": invocation, "boot_id": HOST["boot_id"],
                "before_at_utc": stamp(start - 1), "attempt_at_utc": stamp(start + 2), "after_at_utc": stamp(end + 1),
                "before": before, "after": copy.deepcopy(before)}
            if peer_digest:
                ext.update(peer_report_sha256_before=peer_digest, peer_report_sha256_after=peer_digest)
            facts["external"][case] = ext
        docs["qualification"]["runs"][run] = facts
    docs["cleanup"] = {"operation_id": "original-c26", "boot_id": HOST["boot_id"],
        "completed_at_utc": stamp(NOW - 140),
        "report_sha256": {k: digest(encoded(docs[k])) for k in checker.RUNS},
        **{k: True for k in ("terminal_processes", "no_residual_children", "external_sockets_closed",
            "exact_overrides_removed", "original_properties_restored", "credentials_untouched")}, "serving_started": False}
    return docs


def later_documents(docs):
    docs["enrollment"] = {"implementation_sha": checker.BASE_SHA, "upstream_sha": checker.UPSTREAM_SHA,
        "accepted_at_utc": stamp(NOW - 90),
        "issuer_sha256": ISSUER, "principal_enrolled": True, "principal_id": "existing-native-principal",
        "issuer_entitlement": "ACCEPTED", "credential_contents_included": False,
        **{k: {"accepted": True, "implementation_sha": checker.BASE_SHA} for k in ("C29", "C30", "C31")},
        "roles": {r: {"uid": docs["source"]["roles"][r]["uid"], "credential_metadata_sha256": "a" * 64,
            "provider_binding_sha256": "b" * 64, "credential_enrollment": "ACCEPTED",
            "provider_entitlement": "ACCEPTED", "source_entitlement": "ACCEPTED"} for r in checker.ROLES}}
    docs["edge"] = {"implementation_sha": checker.BASE_SHA, "observed_at_utc": stamp(NOW - 20),
        **{k: True for k in ("C34_accepted", "incumbent_proxy_identity_verified", "tls_verified",
                            "vendor_connect_acl_verified", "cross_role_denial_verified")}, "edge_metadata_sha256": "c" * 64}
    docs["serving"] = {"implementation_sha": checker.BASE_SHA, "observed_at_utc": stamp(NOW - 10),
        "authorized_release": True, "edge_metadata_sha256": "c" * 64, "boot_id": HOST["boot_id"],
        "issuer_sha256": ISSUER, "enrollment_receipt_sha256": digest(encoded(docs["enrollment"])),
        "qualification_cleanup_sha256": digest(encoded(docs["cleanup"])), "release_id": "original-service-release",
        "authorized_at_utc": stamp(NOW - 80), "interval_start_utc": stamp(NOW - 60), "roles": {}}
    for index, r in enumerate(checker.ROLES):
        pin = docs["source"]["roles"][r]
        before = unit(r, pin)
        before.update(ActiveState="active", SubState="running", MainPID=950 + index,
            start_ticks=9500 + index, invocation_id=str(7 + index) * 32, uid=pin["uid"], gid=pin["gid"],
            image_sha256=pin["image_sha256"], manifest_sha256=docs["source"]["manifest_sha256"],
            boot_id=HOST["boot_id"], invocation_started_at_utc=stamp(NOW - 70))
        if r == "mmsecretary":
            before.update(gateway_listener={"host": "127.0.0.2", "port": 8765, "inode": "333"},
                gateway_kernel_listeners=[{"host": "127.0.0.2", "port": 8765, "inode": 333}],
                main_only_status_verified=True)
        docs["serving"]["roles"][r] = {"before": before, "after": copy.deepcopy(before)}
    docs["useful_turn"] = {"implementation_sha": checker.BASE_SHA, "principal_id": "existing-native-principal",
        "issuer_sha256": ISSUER, "authenticated": True, "original_operation_consumed": True,
        "useful_result_accepted": True, "browser_path_accepted": True, "operation_id": "original-turn",
        "result_sha256": "d" * 64, "serving_receipt_sha256": digest(encoded(docs["serving"])),
        "role": "mmsecretary", "invocation_id": "7" * 32, "session_id": "original-native-session",
        "serving_release_id": "original-service-release", "started_at_utc": stamp(NOW - 40),
        "completed_at_utc": stamp(NOW - 30), "accepted_at_utc": stamp(NOW - 25)}
    docs["cutover"] = {"implementation_sha": checker.BASE_SHA, "explicit_authorization": True,
        "accepted": True, "rollback_proven": True, "useful_turn_operation_id": "original-turn",
        "completed": True, "incumbent_transition_verified": True, "operation_id": "original-cutover",
        "useful_turn_sha256": digest(encoded(docs["useful_turn"])), "completed_at_utc": stamp(NOW - 5),
        "serving_release_id": "original-service-release"}
    return docs


def refresh_report_bindings(docs):
    """Re-sign changed fake evidence without repairing the tested semantic defect."""
    for run in checker.RUNS:
        if run not in docs:
            continue
        report = docs[run]
        report["context_fingerprint"] = digest(encoded({"context": report["context"], "selected": sorted(report["selected_matrix"])}))
        predecessor = {"B1": "A1", "A2": "B1"}.get(run)
        if predecessor and predecessor in docs:
            peer_hash = digest(encoded(docs[predecessor]))
            for row in report["matrix"]:
                if row["case_id"] == "file.peer.read":
                    row["witness"]["peer_report_sha256"] = peer_hash
        report_hash = digest(encoded(report))
        facts = docs["qualification"]["runs"].get(run)
        if facts:
            facts["report_sha256"] = report_hash
            for ext in facts["external"].values():
                ext["report_sha256"] = report_hash
                if predecessor and predecessor in docs:
                    ext["peer_report_sha256_before"] = peer_hash
                    ext["peer_report_sha256_after"] = peer_hash
    docs["cleanup"]["report_sha256"] = {k: digest(encoded(docs[k])) for k in checker.RUNS if k in docs}


def trusted_expected(docs, template=EXPECTED):
    return replace(template, receipt_bindings={k: checker.ReceiptBinding(
        "fake-original-owner://" + k, digest(encoded(v))) for k, v in docs.items()})


def run_check(docs, *, target="actual_unit_qualified", expected=EXPECTED, bad_signature=None,
              bad_custody=None, unknown_auth=None, raw_override=None, frozen_bindings=None):
    raw = {k: encoded(v) for k, v in docs.items()}
    signatures = {k: hmac.digest(b"fake-test-authority-only", v, "sha256") for k, v in raw.items()}
    if raw_override:
        raw.update(raw_override)

    def verify(slot, value):
        if slot == unknown_auth:
            return None
        valid = slot != bad_signature and hmac.compare_digest(signatures[slot], hmac.digest(b"fake-test-authority-only", value, "sha256"))
        return checker.ReceiptVerification(checker.OWNERS[slot], "fake-original-owner://" + slot,
            digest(value), "VERIFIED" if valid else "INVALID", slot != bad_custody)

    selected = trusted_expected(docs, expected)
    if frozen_bindings is not None:
        selected = replace(selected, receipt_bindings=frozen_bindings)
    return checker.compile_readiness(raw, expected=selected, verify=verify, now=NOW, target=target)


def codes(result):
    return {i["code"] for i in result["blockers"]}


def case(docs, run, case_id):
    return next(r for r in docs[run]["matrix"] if r["case_id"] == case_id)


class TestHermesP0Readiness(unittest.TestCase):

    def test_good_documented_aba_qualification_preserves_native_incomplete_reports(self):
        docs = qualification_documents()
        original = copy.deepcopy(docs)
        result = run_check(docs)
        assert result["state"] == checker.READY, result["blockers"]
        assert result["raw_probe_status"] == {k: "INCOMPLETE" for k in checker.RUNS}
        assert all(docs[k]["counts"] == {"pass": 10, "fail": 0, "unavailable": 3, "not_run": 0} for k in checker.RUNS)
        assert all(docs[k]["qualified"] is False for k in checker.RUNS)
        assert docs == original
        assert result["gates"]["serving"]["state"] == checker.MISSING
        assert result["authorization_granted"] is False

    def test_original_eight_pass_five_unavailable_stays_incomplete(self):
        docs = qualification_documents()
        for name in ("tcp.own_alias.denied_port", "exec.own_alias.denied_port"):
            row = case(docs, "A1", name)
            row.update(status="UNAVAILABLE", observed="UNAVAILABLE", witness={"sufficient": False})
        docs["A1"]["counts"] = {"pass": 8, "fail": 0, "unavailable": 5, "not_run": 0}
        docs["A1"]["context_rechecked"] = False
        docs["A1"]["observational_recheck"]["provenance_matched"] = False
        refresh_report_bindings(docs)
        result = run_check(docs)
        assert result["state"] == checker.INCOMPLETE
        assert {"LOCAL_CASE_INCOMPLETE", "CONTEXT_OR_CLEANUP_INCOMPLETE"} <= codes(result)

    def test_missing_same_socket_witness(self):
        for run in ["A1", "B1", "A2"]:
            for field in ["socket_fd", "socket_inode"]:
                with self.subTest(run=run, field=field):
                    docs = qualification_documents()
                    case(docs, run, "tcp.own_alias.denied_port")["witness"]["before"].pop(field)
                    case(docs, run, "tcp.own_alias.denied_port")["witness"]["after"].pop(field)
                    refresh_report_bindings(docs)
                    result = run_check(docs)
                    assert result["state"] == checker.INCOMPLETE
                    assert "SAME_SOCKET_FD_INODE_WITNESS_MISSING" in codes(result)

    def test_drift_and_aba_refuse(self):
        for drift in ["boot", "invocation", "source", "profile", "root_fragment", "aba_pid", "ctime"]:
            with self.subTest(drift=drift):
                docs = qualification_documents()
                facts = docs["qualification"]["runs"]["A2"]
                ext = facts["external"]["tcp.sibling_alias.gateway_port"]
                if drift == "boot":
                    docs["A2"]["context"]["provenance"]["host"]["boot_id"] = "9" * 36
                elif drift == "invocation":
                    ext["invocation_id"] = "9" * 32
                elif drift == "source":
                    docs["A2"]["context"]["provenance"]["sources"] = {"wrong": "0" * 64}
                elif drift == "profile":
                    docs["A2"]["context"]["provenance"]["profile_sha256"] = "0" * 64
                elif drift == "root_fragment":
                    docs["units"]["roles"]["mmmeta"]["fragment_sha256"] = "0" * 64
                elif drift == "aba_pid":
                    ext["after"]["start_ticks"] += 1
                else:
                    facts["external"]["file.peer.read"]["after"]["mmmeta"]["facts"]["ctime_ns"] += 1
                refresh_report_bindings(docs)
                result = run_check(docs)
                assert result["state"] == checker.REFUSED
                assert "IDENTITY_OR_SOURCE_DRIFT" in codes(result)

    def test_named_missing_original_receipts(self):
        for slot in ["c25", "B1", "A2", "cleanup", "manifest"]:
            with self.subTest(slot=slot):
                docs = qualification_documents()
                docs.pop(slot)
                result = run_check(docs)
                assert result["state"] in {checker.MISSING, checker.INCOMPLETE}
                assert slot in result["missing_receipts"]

    def test_c25_source_repair_does_not_imply_checkout(self):
        docs = qualification_documents()
        docs["c25"].pop("stage")
        result = run_check(docs)
        assert result["state"] == checker.INCOMPLETE
        assert "C25_CHECKOUT_MISSING" in codes(result)

    def test_original_c25_unknown_or_denied_is_never_retried(self):
        for state in ["EFFECT_UNKNOWN", "RUNNING", "DENIED", "garbage"]:
            with self.subTest(state=state):
                docs = qualification_documents()
                docs["c25"]["original_effect"] = state
                result = run_check(docs)
                assert result["state"] == checker.REFUSED
                assert "C25_ORIGINAL_EFFECT_UNKNOWN" in codes(result)
                assert result["next_permitted_read"]["action"] == "READ_ORIGINAL_RETAINED_RECEIPT"

    def test_unexpected_live_role_refuses(self):
        for field, value in [("MainPID", 88), ("ControlPID", 88), ("job_pending", True), ("ActiveState", "active")]:
            with self.subTest(field=field, value=value):
                docs = qualification_documents()
                docs["units"]["roles"]["mmsecretary"][field] = value
                result = run_check(docs)
                assert result["state"] == checker.REFUSED
                assert "UNEXPECTED_LIVE_ROLE" in codes(result)

    def test_invalid_signature_or_custody_refuses(self):
        for slot in ["source", "c25", "A2", "qualification", "cleanup"]:
            with self.subTest(slot=slot):
                docs = qualification_documents()
                for kw in ({"bad_signature": slot}, {"bad_custody": slot}):
                    result = run_check(docs, **kw)
                    assert result["state"] == checker.REFUSED
                    assert "SIGNATURE_CUSTODY_OR_ORIGIN_INVALID" in codes(result)

    def test_missing_authentication_is_not_a_verified_json_boolean(self):
        docs = qualification_documents()
        docs["c25"]["verified"] = True
        result = run_check(docs, unknown_auth="c25")
        assert result["state"] == checker.INCOMPLETE
        assert "AUTHENTICATION_RECEIPT_MISSING" in codes(result)

    def test_secret_paths_and_all_host_io_are_never_accessed(self):
        docs = qualification_documents()
        for run in checker.RUNS:
            docs[run]["context"]["secrets_file"] = "/do-not-open/real-secret.env"
        refresh_report_bindings(docs)
        def denied(*_args, **_kwargs):
            raise AssertionError("Unexpected I/O")
        with mock.patch.object(builtins, "open", denied), mock.patch.object(Path, "open", denied), \
             mock.patch.object(Path, "read_bytes", denied), mock.patch.object(Path, "read_text", denied), \
             mock.patch.object(os, "open", denied), mock.patch.object(os, "stat", denied), \
             mock.patch.object(subprocess, "run", denied), mock.patch.object(subprocess, "Popen", denied), \
             mock.patch.object(socket, "socket", denied):
            result = run_check(docs)
        assert result["state"] == checker.READY, result["blockers"]
        assert "/do-not-open" not in json.dumps(result)

    def test_changed_upstream_or_issuer_refuses(self):
        for field, value in [("upstream_sha", "0" * 40), ("issuer_sha256", "0" * 64)]:
            with self.subTest(field=field, value=value):
                docs = later_documents(qualification_documents())
                docs["enrollment"][field] = value
                result = run_check(docs, target="enrolled")
                assert result["state"] == checker.REFUSED

    def test_c29_unaccepted_does_not_gain_authority_from_other_sources(self):
        docs = later_documents(qualification_documents())
        docs["enrollment"]["C29"]["accepted"] = False
        docs["serving"]["enrollment_receipt_sha256"] = digest(encoded(docs["enrollment"]))
        result = run_check(docs, target="serving")
        assert result["state"] == checker.INCOMPLETE
        assert "C29_NOT_ACCEPTED" in codes(result)

    def test_source_inert_qualified_enrolled_serving_useful_and_cutover_remain_distinct(self):
        docs = qualification_documents()
        result = run_check(docs)
        assert all(result["gates"][k]["state"] == checker.READY for k in
                   ("source_prepared", "source_released", "c25_checkout", "staged_inert", "actual_unit_qualified"))
        assert all(result["gates"][k]["state"] == checker.MISSING for k in
                   ("enrolled", "serving", "authenticated_useful_turn", "cutover"))
        result = run_check(later_documents(docs), target="cutover")
        assert result["state"] == checker.READY, result["blockers"]
        assert result["authorization_granted"] is False

    def test_disabled_unit_does_not_mean_serving_but_disabled_can_be_running(self):
        docs = later_documents(qualification_documents())
        # Disabled is enable-on-boot policy, not actual process state.
        assert run_check(docs, target="serving")["state"] == checker.READY
        for role in checker.ROLES:
            for snapshot in docs["serving"]["roles"][role].values():
                snapshot.update(MainPID=0, ActiveState="inactive", SubState="dead")
        result = run_check(docs, target="serving")
        assert result["state"] == checker.INCOMPLETE
        assert "ACTUAL_ROLE_NOT_SERVING" in codes(result)

    def test_missing_edge_metadata_blocks_serving(self):
        for absent in ["edge", "edge_metadata_sha256"]:
            with self.subTest(absent=absent):
                docs = later_documents(qualification_documents())
                if absent == "edge":
                    docs.pop("edge")
                else:
                    docs["edge"].pop(absent)
                result = run_check(docs, target="serving")
                assert result["state"] != checker.READY
                assert "EDGE_METADATA_MISSING" in codes(result) or "RECEIPT_MISSING" in codes(result)

    def test_dual_role_cannot_inherit_peer_test(self):
        docs = qualification_documents()
        docs["B1"] = copy.deepcopy(docs["A2"])
        refresh_report_bindings(docs)
        result = run_check(docs)
        assert result["state"] == checker.REFUSED

    def test_sequence_and_matrix_fail_closed(self):
        for mutation in ["stale", "duplicate_invocation", "overlap", "subset", "duplicate_case", "relabeled_pass"]:
            with self.subTest(mutation=mutation):
                docs = qualification_documents()
                if mutation == "stale":
                    docs["qualification"]["observed_at_utc"] = stamp(NOW - 901)
                elif mutation == "duplicate_invocation":
                    docs["qualification"]["runs"]["A2"]["invocation_id"] = "1" * 32
                elif mutation == "overlap":
                    docs["qualification"]["runs"]["B1"]["started_at_utc"] = docs["qualification"]["runs"]["A1"]["started_at_utc"]
                elif mutation == "subset":
                    docs["A2"]["selected_matrix"].pop()
                elif mutation == "duplicate_case":
                    docs["A2"]["matrix"][-1] = copy.deepcopy(docs["A2"]["matrix"][0])
                else:
                    docs["A2"].update(status="PASS", qualified=True)
                refresh_report_bindings(docs)
                assert run_check(docs)["state"] != checker.READY

    def test_unrelated_address_errors_never_become_policy_proof(self):
        for code, symptom in [(111, "refused_immediately"), (5, "refused_immediately"), (13, "refused_immediately"), (110, "generic_timeout")]:
            with self.subTest(code=code, symptom=symptom):
                docs = qualification_documents()
                row = case(docs, "A2", "tcp.sibling_alias.gateway_port")
                row.update(errno=code, symptom=symptom)
                refresh_report_bindings(docs)
                result = run_check(docs)
                assert result["state"] == checker.INCOMPLETE
                assert "ADDRESS_DENIAL_NOT_PROVEN" in codes(result)

    def test_successful_forbidden_read_remains_refused_despite_external_acceptance(self):
        docs = qualification_documents()
        row = case(docs, "A2", "file.peer.read")
        row.update(observed="ALLOWED", status="FAIL")
        docs["A2"].update(status="FAIL", counts={"pass": 10, "fail": 1, "unavailable": 2, "not_run": 0})
        refresh_report_bindings(docs)
        assert run_check(docs)["state"] == checker.REFUSED

    def test_malformed_untrusted_receipts_refuse(self):
        for raw in [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e9999}', b'[]', b'\xff', b'{}' * 600000]:
            with self.subTest(raw=raw):
                result = run_check(qualification_documents(), raw_override={"c25": raw})
                assert result["state"] == checker.REFUSED

    def test_missing_bundle_is_closed_and_names_next_original_owner_read(self):
        result = run_check({})
        assert result["state"] == checker.MISSING
        assert result["next_permitted_read"] == {"receipt": "source", "owner": "release-owner",
            "action": "READ_ORIGINAL_RETAINED_RECEIPT", "reason": "RECEIPT_MISSING"}

    def test_source_prepared_is_not_original_pr_release(self):
        docs = qualification_documents()
        docs["release"]["pr"].update(merged=False, state="open", merge_commit_sha=None)
        result = run_check(docs)
        assert result["gates"]["source_prepared"]["state"] == checker.READY
        assert result["state"] == checker.INCOMPLETE
        assert "ORIGINAL_PR_NOT_RELEASED" in codes(result)

    def test_exact_original_pr_head_is_required(self):
        docs = qualification_documents()
        docs["release"]["pr"]["head_sha"] = "0" * 40
        assert run_check(docs)["state"] == checker.REFUSED

    def test_inventory_and_incumbent_identity_changes_refuse(self):
        docs = qualification_documents()
        docs["installation"]["inventory"]["observed_sha256"] = "0" * 64
        docs["incumbents"]["Control"]["after"]["start_ticks"] += 1
        assert run_check(docs)["state"] == checker.REFUSED

    def test_dependency_graph_is_finite_closed_and_ordered(self):
        result = run_check(qualification_documents())
        seen = set()
        for node in result["dependency_graph"]:
            assert set(node["depends_on"]) <= seen
            assert node["state"] in checker.STATES
            seen.add(node["gate"])
        assert seen == set(checker.DEPENDENCIES)
        assert run_check({}, target="install_now")["state"] == checker.REFUSED

    def test_bool_is_not_pid_or_uid(self):
        docs = qualification_documents()
        docs["source"]["roles"]["mmmeta"]["uid"] = True
        assert run_check(docs)["state"] != checker.READY

    def test_independent_expectations_cannot_be_changed_by_candidate(self):
        docs = qualification_documents()
        assert run_check(docs, expected=replace(EXPECTED, implementation_sha="0" * 40))["state"] == checker.REFUSED

    def test_custody_only_original_reports_do_not_need_invented_signatures(self):
        docs = qualification_documents()
        raw = {k: encoded(v) for k, v in docs.items()}
        result = checker.compile_readiness(raw, expected=trusted_expected(docs), now=NOW,
            verify=lambda slot, value: checker.ReceiptVerification(checker.OWNERS[slot],
                "fake-original-owner://" + slot, digest(value), "NOT_APPLICABLE", True))
        assert result["state"] == checker.READY, result["blockers"]

    def test_actual_unit_invocation_is_not_an_unbound_string(self):
        for mutation in ("missing", "stale", "wrong_pid"):
            with self.subTest(mutation=mutation):
                docs = qualification_documents()
                facts = docs["qualification"]["runs"]["A2"]
                if mutation == "missing":
                    facts.pop("unit_start")
                elif mutation == "stale":
                    facts["unit_terminal"]["InvocationID"] = "0" * 32
                else:
                    facts["unit_start"]["ExecMainPID"] += 1
                result = run_check(docs)
                assert result["state"] == (checker.INCOMPLETE if mutation == "missing" else checker.REFUSED)

    def test_external_listener_must_be_root_owned_outside_both_roles(self):
        for field, value in (("uid", 2101), ("cgroup", "/system.slice/hermes-runtime-mmmeta.service")):
            with self.subTest(field=field):
                docs = qualification_documents()
                ext = docs["qualification"]["runs"]["A2"]["external"]["tcp.sibling_alias.gateway_port"]
                ext["before"][field] = ext["after"][field] = value
                result = run_check(docs)
                assert result["state"] == checker.INCOMPLETE
                assert "OUTSIDE_CGROUP_OWNER_UNQUALIFIED" in codes(result)

    def test_later_phase_cannot_borrow_stale_enrollment_or_serving(self):
        for slot, field, target in (("serving", "enrollment_receipt_sha256", "serving"),
                                    ("useful_turn", "serving_receipt_sha256", "authenticated_useful_turn"),
                                    ("useful_turn", "invocation_id", "authenticated_useful_turn"),
                                    ("cutover", "useful_turn_sha256", "cutover")):
            with self.subTest(slot=slot, field=field):
                docs = later_documents(qualification_documents())
                docs[slot][field] = "0" * (32 if field == "invocation_id" else 64)
                assert run_check(docs, target=target)["state"] == checker.REFUSED

    def test_cutover_plan_is_not_executed_cutover(self):
        docs = later_documents(qualification_documents())
        docs["cutover"]["completed"] = False
        result = run_check(docs, target="cutover")
        assert result["state"] == checker.INCOMPLETE
        assert "CUTOVER_EFFECT_NOT_PROVEN" in codes(result)

    def test_current_probe_source_set_is_closed(self):
        docs = qualification_documents()
        docs["source"]["probe_sources"] = {"isolation_probe": "1" * 64}
        result = run_check(docs)
        assert result["state"] != checker.READY
        assert "PROBE_SOURCE_PINS_MISSING" in codes(result)

    def test_serving_uses_incumbent_secretary_listener_and_exact_kernel_row(self):
        for rows in ([], [{"host": "0.0.0.0", "port": 8765, "inode": 333}],
                     [{"host": "127.0.0.2", "port": 8765, "inode": 444}]):
            with self.subTest(rows=rows):
                docs = later_documents(qualification_documents())
                for sample in docs["serving"]["roles"]["mmsecretary"].values():
                    sample["gateway_kernel_listeners"] = rows
                assert run_check(docs, target="serving")["state"] == checker.REFUSED

    def test_unknown_target_types_return_closed_refusal(self):
        for target in (None, True, [], {}):
            with self.subTest(target=target):
                assert run_check({}, target=target)["state"] == checker.REFUSED

    def test_an_authentic_other_operation_cannot_replace_original_c25(self):
        docs = qualification_documents()
        docs["c25"]["operation_id"] = "another-authentic-successful-c25"
        docs["effects"]["c25"]["operation_id"] = "another-authentic-successful-c25"
        result = run_check(docs)
        assert result["state"] == checker.REFUSED
        assert "IDENTITY_OR_SOURCE_DRIFT" in codes(result)

    def test_authentic_receipts_require_independent_exact_origin_selection(self):
        docs = qualification_documents()
        anchors = trusted_expected(docs).receipt_bindings
        docs["c25"]["normalization"]["reachable_object_count"] += 1
        result = run_check(docs, frozen_bindings=anchors)
        assert result["state"] == checker.REFUSED
        assert "ORIGINAL_RECEIPT_DIGEST_MISMATCH" in codes(result)
        anchors = trusted_expected(docs).receipt_bindings
        anchors["c25"] = replace(anchors["c25"], source_ref="different-original-object://c25")
        result = run_check(docs, frozen_bindings=anchors)
        assert result["state"] == checker.REFUSED
        assert "ORIGINAL_RECEIPT_REFERENCE_MISMATCH" in codes(result)

    def test_missing_original_selection_is_incomplete_even_with_valid_authentication(self):
        docs = qualification_documents()
        result = run_check(docs, frozen_bindings={})
        assert result["state"] == checker.INCOMPLETE
        assert "ORIGINAL_RECEIPT_BINDING_MISSING" in codes(result)
        result = run_check(docs, expected=replace(EXPECTED, original_operations={}))
        assert result["state"] == checker.INCOMPLETE
        assert "EXPECTED_ORIGINAL_OPERATION_MISSING" in codes(result)

    def test_future_phase_order_cannot_be_repaired_by_matching_digests(self):
        for scenario in ("cleanup_after_serving", "enroll_before_qualification", "release_before_enrollment",
                         "old_role_invocation", "turn_before_serving", "turn_after_observation", "early_cutover"):
            with self.subTest(scenario=scenario):
                docs = later_documents(qualification_documents())
                if scenario == "cleanup_after_serving":
                    docs["cleanup"]["completed_at_utc"] = stamp(NOW - 5)
                    docs["qualification"]["observed_at_utc"] = stamp(NOW - 4)
                elif scenario == "enroll_before_qualification":
                    docs["enrollment"]["accepted_at_utc"] = stamp(NOW - 110)
                elif scenario == "release_before_enrollment":
                    docs["serving"]["authorized_at_utc"] = stamp(NOW - 95)
                elif scenario == "old_role_invocation":
                    for sample in docs["serving"]["roles"]["mmmeta"].values():
                        sample["invocation_started_at_utc"] = stamp(NOW - 81)
                elif scenario == "turn_before_serving":
                    docs["useful_turn"]["started_at_utc"] = stamp(NOW - 61)
                elif scenario == "turn_after_observation":
                    docs["useful_turn"]["accepted_at_utc"] = stamp(NOW - 9)
                else:
                    docs["cutover"]["completed_at_utc"] = stamp(NOW - 26)
                # Keep every digest join internally consistent: ordering itself
                # must reject this signed but causally obsolete chain.
                docs["serving"]["qualification_cleanup_sha256"] = digest(encoded(docs["cleanup"]))
                docs["serving"]["enrollment_receipt_sha256"] = digest(encoded(docs["enrollment"]))
                docs["useful_turn"]["serving_receipt_sha256"] = digest(encoded(docs["serving"]))
                docs["cutover"]["useful_turn_sha256"] = digest(encoded(docs["useful_turn"]))
                result = run_check(docs, target="cutover")
                assert result["state"] == checker.REFUSED, result
                assert any("ORDER" in code or "PRECEDES" in code or "BEFORE" in code
                           or "OUTSIDE_SERVING" in code or "LATER_CLEANUP" in code for code in codes(result))

    def test_a1_without_peer_report_does_not_invent_peer_read_proof(self):
        profile = make_profile("mmsecretary")
        raw_case = next(c for c in probe._case_catalog() if c.case_id == "file.peer.read")
        with mock.patch.object(probe, "_load_peer_report", return_value=(None, "no peer report supplied")), \
             mock.patch.object(probe, "_file_outcome_peer", side_effect=AssertionError("must not read")) as read:
            result = probe._file_outcome(raw_case, profile, 2101, 2101,
                Path(fixture_file("mmsecretary")["path"]), Path(fixture_file("mmmeta")["path"]), None)
        assert result.observed == "UNAVAILABLE"
        read.assert_not_called()

    def test_malformed_status_and_role_names_are_not_echoed(self):
        docs = qualification_documents()
        docs["A2"]["status"] = {"private": "do-not-echo-input"}
        docs["units"]["roles"]["do-not-echo-input"] = {}
        refresh_report_bindings(docs)
        result = run_check(docs)
        assert result["state"] == checker.REFUSED
        assert result["raw_probe_status"]["A2"] == "INVALID"
        assert "do-not-echo-input" not in json.dumps(result)


if __name__ == "__main__":
    unittest.main()
