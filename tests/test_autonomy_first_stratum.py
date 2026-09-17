"""Frozen contract parity and adversarial tests of the bytes-only reducer.

Synthetic call anchors below test checking, never caller authority. Golden input,
artifact and expected-output bytes are immutable and separately sealed in the bundle.
"""
from __future__ import annotations

import builtins
import copy
import datetime
import hashlib
import io
import json
import socket
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

from control_plane.autonomy_first_stratum import reduce_first_stratum


_BUNDLE = Path(__file__).parent / "fixtures/autonomy_first_stratum/accepted_contract_bundle.json"
_BUNDLE_SHA = "a09b8014b32e12e6d5a908c2c695cb564a05dd74f37d0a8dd00ec32038900216"
_CASES = tuple(f"E{i:02d}" for i in range(1, 18))


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _encode(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode()


def _unseal(record):
    raw = record["utf8"].encode("utf-8")
    assert len(raw) == record["bytes"]
    assert _sha(raw) == record["sha256"]
    return raw


@pytest.fixture(scope="module")
def bundle():
    raw = _BUNDLE.read_bytes()
    assert _sha(raw) == _BUNDLE_SHA
    return json.loads(raw)


def _load(bundle, case="E01"):
    call = bundle["calls"][case]
    prefix = call["prefix"]
    raw = _unseal(bundle["files"][prefix + ".input.json"])
    document = json.loads(_unseal(bundle["files"][prefix + ".artifacts.json"]))
    artifacts = {}
    for key, record in document.items():
        assert record["encoding"] == "UTF-8 canonical JSON, sorted keys, compact separators, trailing LF"
        encoded = _encode(record["content"])
        assert len(encoded) == record["bytes"]
        assert _sha(encoded) == record["sha256"]
        artifacts["synthetic:" + key] = encoded
    manifest = _unseal(call["trusted_manifest"])
    expected = json.loads(_unseal(bundle["files"][prefix + ".expected.json"]))
    return raw, artifacts, manifest, call["trusted_manifest"]["sha256"], expected


def _call(raw, artifacts, manifest, anchor):
    return reduce_first_stratum(raw, artifacts, trusted_manifest_bytes=manifest,
                               expected_trusted_manifest_sha256=anchor)


def _reanchor(raw, manifest):
    """Explicit test-only acceptance of a NEW synthetic control, never a golden edit."""
    capsule = json.loads(raw)
    trusted = json.loads(manifest)
    trusted["capsule_bytes"] = len(raw)
    trusted["capsule_sha256"] = _sha(raw)
    # Only reflect existing role locations when constructing new synthetic test calls.
    def at(pointer):
        value = capsule
        for part in pointer.split("/")[1:]:
            value = value[int(part)] if isinstance(value, list) else value[part]
        return value
    positions = {ref["capsule_ref_pointer"]: ref["role"] for ref in trusted["accepted_refs"]
                 if not ref["capsule_ref_pointer"].startswith("/inventory/members/")}
    for i, member in enumerate(capsule["inventory"]["members"]):
        positions[f"/inventory/members/{i}/decision_evidence_ref"] = "ADMISSION_DECISION"
        for j in range(len(member["claim_candidates"])):
            positions[f"/inventory/members/{i}/claim_candidates/{j}/authority_ref"] = "CANDIDATE_AUTHORITY"
    refs = []
    for position, role in positions.items():
        value = at(position)
        if value is not None:
            refs.append({"role": role, "capsule_ref_pointer": position, **value})
    trusted["accepted_refs"] = refs
    encoded = _encode(trusted)
    return encoded, _sha(encoded)


def _put(artifacts, ref, content):
    raw = _encode(content)
    artifacts[ref["uri"]] = raw
    ref.update(bytes=len(raw), sha256=_sha(raw), json_pointer="")


def _refresh(capsule, artifacts):
    for read in capsule["reads"].values():
        _put(artifacts, read["evidence_ref"], read["record"])
        _put(artifacts, read["invocation_ref"],
             {key: read[key] for key in ("reader", "arguments", "observation")})


def _changed_call(bundle, change, case="E01"):
    raw, artifacts, manifest, _, _ = _load(bundle, case)
    capsule = json.loads(raw)
    change(capsule)
    _refresh(capsule, artifacts)
    raw = _encode(capsule)
    manifest, anchor = _reanchor(raw, manifest)
    return _call(raw, artifacts, manifest, anchor)


def _ceiling(result):
    assert result["verdict"] == "HOLD"
    assert result["accepted_stage"] == "NONE"
    assert result["promotion_applied"] is False
    assert result["operational_qualified_count"] == 0
    assert result["accepted_budget_ms"] == dict.fromkeys(("p50", "p95", "max"))
    assert result["adverse_obligations"] == {"count": 18, "state": "NOT_RUN_THIS_OPERATION"}
    assert result["distribution_status"] == "NOT_QUALIFIED"
    assert all(v == {"state": "UNAVAILABLE", "p50": None, "p95": None, "max": None}
               for v in result["other_metrics"].values())


def _hold(result, reason=None):
    _ceiling(result)
    assert result["derivation_status"] == "HOLD_UNSUPPORTED"
    assert result["completed_recorded_intervals"] == 0
    assert result["distinct_contributing_roots"] == 0
    assert all(m["root_weight"] == 0 for m in result["member_results"])
    assert all(result["completed_sample_quantiles_ms"][k] is None for k in ("p50", "p95", "max"))
    if reason:
        assert reason in result["reason_codes"] + [r for m in result["member_results"] for r in m["reason_codes"]]


@pytest.mark.parametrize("case", _CASES)
def test_golden_case(bundle, case):
    raw, artifacts, manifest, anchor, expected = _load(bundle, case)
    assert _call(raw, artifacts, manifest, anchor) == expected


def test_unselected_operational_input(bundle):
    raw = _unseal(bundle["files"]["original/unselected-operational-input.template.json"])
    expected = json.loads(_unseal(bundle["files"]["original/unselected-operational-input.expected.json"]))
    assert _call(raw, {}, None, None) == expected


def test_fixture_seals_and_separate_synthetic_anchors(bundle):
    assert len(bundle["files"]) == 57
    for sealed in bundle["files"].values():
        _unseal(sealed)
    assert bundle["provenance"] == {
        "parent_manifest_sha256": "b3313b879258c16df9c540bced00a43c5e5be8193e84b5057b098b7bd4b182fd",
        "r1_manifest_sha256": "1af651252406ddd768d7f18d679aa253d432581558599b102bbefb2a600bb9b3",
        "r1_index_sha256": "50676bc4103aeb0f61d1b439366a57c43e6b0a21579bba165b2ee82fb4b03755",
    }
    for case in _CASES:
        raw, _, manifest, _, _ = _load(bundle, case)
        trusted = json.loads(manifest)
        assert trusted["evidence_class"] == "SYNTHETIC"
        assert trusted["capsule_sha256"] == _sha(raw)
        assert trusted["capsule_bytes"] == len(raw)


def test_fixed_anchor_coherent_timestamp_rewrite(bundle):
    raw, artifacts, manifest, anchor, _ = _load(bundle)
    capsule = json.loads(raw)
    read = capsule["reads"]["claim-ms"]
    read["record"]["created_at_ms"] = 1000251
    read["observation"]["read_finished_at_ms"] += 1
    _refresh(capsule, artifacts)
    attacked = _encode(capsule)
    for field in ("evidence_ref", "invocation_ref"):
        ref = read[field]
        assert _sha(artifacts[ref["uri"]]) == ref["sha256"]
        assert len(artifacts[ref["uri"]]) == ref["bytes"]
    assert _sha(attacked) != json.loads(manifest)["capsule_sha256"]
    _hold(_call(attacked, artifacts, manifest, anchor), "TRUST_ANCHOR_MISMATCH")


def test_fixed_anchor_per_read_closure_substitution(bundle):
    raw, artifacts, manifest, anchor, _ = _load(bundle)
    capsule = json.loads(raw)
    ref = {"uri": "synthetic:substituted-closure", "json_pointer": ""}
    _put(artifacts, ref, {"synthetic": True, "assumption": "closure", "complete": True})
    capsule["reads"]["child-events"]["observation"]["closure_ref"] = ref
    _refresh(capsule, artifacts)
    attacked = _encode(capsule)
    invocation = capsule["reads"]["child-events"]["invocation_ref"]
    assert json.loads(artifacts[invocation["uri"]])["observation"]["closure_ref"] == ref
    assert _sha(attacked) != json.loads(manifest)["capsule_sha256"]
    _hold(_call(attacked, artifacts, manifest, anchor), "TRUST_ANCHOR_MISMATCH")


@pytest.mark.parametrize("fault", ["missing", "digest", "bytes", "capsule_hash", "capsule_size",
                                    "bool_size", "missing_binding", "extra", "role", "duplicate_position"])
def test_manifest_anchor_failures(bundle, fault):
    raw, artifacts, manifest, anchor, _ = _load(bundle)
    if fault == "missing":
        _hold(_call(raw, artifacts, None, None), "TRUST_ANCHOR_UNAVAILABLE")
        return
    if fault == "digest":
        anchor = "0" * 64
    elif fault == "bytes":
        manifest += b" "
    else:
        value = json.loads(manifest)
        if fault == "capsule_hash": value["capsule_sha256"] = "0" * 64
        elif fault == "capsule_size": value["capsule_bytes"] += 1
        elif fault == "bool_size": value["capsule_bytes"] = True
        elif fault == "missing_binding": value.pop("capsule_sha256")
        elif fault == "extra": value["approved"] = True
        elif fault == "role": value["accepted_refs"][0]["role"] = "CANDIDATE_AUTHORITY"
        elif fault == "duplicate_position": value["accepted_refs"].append(copy.deepcopy(value["accepted_refs"][0]))
        manifest = _encode(value)
        anchor = _sha(manifest)
    _hold(_call(raw, artifacts, manifest, anchor), "TRUST_ANCHOR_MISMATCH")


@pytest.mark.parametrize("raw", [b'{"schema":1,"schema":2}', b'{"x":NaN}', b'{"x":1e999}',
                                 b'\xff', b'null', b'[]', b'{"x":"\\ud800"}'])
def test_strict_decoding_failures(raw):
    result = _call(raw, {}, None, None)
    _hold(result)
    assert result["input_sha256"] == _sha(raw)


@pytest.mark.parametrize("fault", ["extra", "missing", "bool_timestamp", "bool_event", "record_extra", "argument_extra", "wrong_reader", "source_pin"])
def test_strict_shape_failures(bundle, fault):
    def change(c):
        if fault == "extra": c["approved"] = True
        elif fault == "missing": c.pop("inventory")
        elif fault == "bool_timestamp": c["reads"]["claim-ms"]["record"]["created_at_ms"] = True
        elif fault == "bool_event": c["reads"]["root-full"]["record"]["event_id"] = True
        elif fault == "record_extra": c["reads"]["claim-ms"]["record"]["event_id"] = 30
        elif fault == "argument_extra": c["reads"]["jobs"]["arguments"]["root_job_id"] = "JOB-001"
        elif fault == "wrong_reader": c["reads"]["claim-ms"]["reader"] = "unapproved.reader"
        elif fault == "source_pin": c["source"]["commit"] = "0" * 40
    if fault == "missing":
        raw, artifacts, manifest, anchor, _ = _load(bundle)
        c = json.loads(raw); change(c)
        _hold(_call(_encode(c), artifacts, manifest, anchor))
    else:
        _hold(_changed_call(bundle, change))


@pytest.mark.parametrize("fault", ["missing", "hash", "pointer", "invocation", "instance", "read_order", "scope"])
def test_reader_reference_binding(bundle, fault):
    raw, artifacts, manifest, anchor, _ = _load(bundle)
    c = json.loads(raw); read = c["reads"]["claim-ms"]
    if fault == "missing": artifacts.pop(read["evidence_ref"]["uri"])
    elif fault == "hash": artifacts[read["evidence_ref"]["uri"]] += b" "
    elif fault == "pointer":
        read["evidence_ref"]["json_pointer"] = "/not~2valid"
    elif fault == "invocation":
        invocation = json.loads(artifacts[read["invocation_ref"]["uri"]])
        invocation["arguments"]["command_id"] = "substitution"
        _put(artifacts, read["invocation_ref"], invocation)
    else:
        if fault == "instance": read["observation"]["runtime_instance_epoch"] = "another-instance"
        elif fault == "read_order": read["observation"]["read_finished_at_ms"] = 1
        elif fault == "scope": read["observation"]["scope"] = {"command_id": "another-command"}
        _refresh(c, artifacts)
    raw = _encode(c); manifest, anchor = _reanchor(raw, manifest)
    _hold(_call(raw, artifacts, manifest, anchor))


@pytest.mark.parametrize("field,value", [("worker_id", "other"), ("quota_class", "other"),
                                          ("fence_generation", 4), ("attempt_number", 2),
                                          ("effective_grant_digest", "0" * 64),
                                          ("placement_snapshot_digest", "0" * 64)])
def test_historical_claim_identity(bundle, field, value):
    _hold(_changed_call(bundle, lambda c: c["reads"]["attempt"]["record"].update({field: value})))


def test_current_attempt_does_not_replace_historical_attempt(bundle):
    def change(c):
        c["reads"]["child-job"]["record"]["current_attempt_id"] = "ATT-later"
        c["reads"]["jobs"]["record"][1]["current_attempt_id"] = "ATT-later"
    result = _changed_call(bundle, change)
    assert result["completed_recorded_intervals"] == 1
    assert result["completed_sample_quantiles_ms"]["p50"] == 250


def test_replay_conflict_precedes_counting(bundle):
    result = _changed_call(bundle, lambda c: c["inventory"]["members"].reverse(), "E12")
    _hold(result, "REPLAY_CONFLICT")
    assert result["known_admitted_roots"] == 1


def test_input_immutability_and_repeatability(bundle):
    raw, artifacts, manifest, anchor, expected = _load(bundle)
    before = copy.deepcopy((raw, artifacts, manifest, anchor))
    assert _call(raw, artifacts, manifest, anchor) == expected
    assert _call(raw, artifacts, manifest, anchor) == expected
    assert (raw, artifacts, manifest, anchor) == before


@pytest.mark.parametrize("case", _CASES)
def test_no_promotion_ceiling(bundle, case):
    raw, artifacts, manifest, anchor, _ = _load(bundle, case)
    _ceiling(_call(raw, artifacts, manifest, anchor))


def test_import_and_invocation_purity(bundle, monkeypatch):
    raw, artifacts, manifest, anchor, expected = _load(bundle)
    source = (Path(__file__).parents[1] / "control_plane/autonomy_first_stratum.py").read_bytes()
    code = compile(source, "pure_reducer_under_tripwires", "exec")
    real_import = builtins.__import__
    allowed = {"__future__", "collections.abc", "typing", "json", "hashlib", "datetime", "re", "math"}
    def forbidden(*args, **kwargs):
        raise AssertionError("Target attempted an effect during import or invocation")
    class NoClockDateTime(datetime.datetime):
        now = utcnow = today = forbidden
    def checked_import(name, *args, **kwargs):
        if name not in allowed:
            raise AssertionError(f"Unapproved target import: {name}")
        return real_import(name, *args, **kwargs)
    # Prime allowed stdlib modules before loader guards; source evaluation is guarded.
    for name in allowed:
        real_import(name)
    with monkeypatch.context() as guard:
        for target, name in [(builtins, "open"), (io, "open"), (Path, "open"),
                             (socket, "socket"), (socket, "create_connection"),
                             (subprocess, "Popen"), (sqlite3, "connect"),
                             (time, "time"), (time, "monotonic"), (time, "perf_counter")]:
            guard.setattr(target, name, forbidden)
        guard.setattr(datetime, "datetime", NoClockDateTime)
        guard.setattr(builtins, "__import__", checked_import)
        namespace = {"__name__": "pure_reducer_under_tripwires"}
        exec(code, namespace)
        actual = namespace["reduce_first_stratum"](raw, artifacts, trusted_manifest_bytes=manifest,
                                                  expected_trusted_manifest_sha256=anchor)
    assert actual == expected


@pytest.mark.parametrize("resource", ["capsule", "manifest", "artifact", "aggregate", "depth", "nodes"])
@pytest.mark.parametrize("excess", [0, 1])
def test_input_resource_limits(resource, excess):
    mib = 1024 * 1024
    raw, artifacts, manifest = b"{}", {}, None
    if resource == "capsule":
        raw = b'"' + b"x" * (16 * mib - 2 + excess) + b'"'
    elif resource == "manifest":
        manifest = b"{}" + b" " * (mib - 2 + excess)
    elif resource == "artifact":
        artifacts["synthetic:large"] = b'"' + b"x" * (4 * mib - 2 + excess) + b'"'
    elif resource == "aggregate":
        item = b'"' + b"x" * (4 * mib - 2) + b'"'
        artifacts = {f"synthetic:{i}": item for i in range(16)}
        if excess:
            artifacts["synthetic:excess"] = b"0"
    elif resource == "depth":
        raw = b"[" * (64 + excess) + b"0" + b"]" * (64 + excess)
    else:
        raw = b"[" + b",".join([b"0"] * (999_999 + excess)) + b"]"
    result = _call(raw, artifacts, manifest, None)
    _hold(result)
    assert ("INPUT_RESOURCE_LIMIT" in result["reason_codes"]) == bool(excess)


def _set_claim_time(capsule, milliseconds):
    display = (datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
               + datetime.timedelta(seconds=milliseconds // 1000)).isoformat(timespec="seconds")
    capsule["reads"]["claim-ms"]["record"]["created_at_ms"] = milliseconds
    capsule["reads"]["claim-full"]["record"]["created_at"] = display
    for event in capsule["reads"]["child-events"]["record"]:
        if event["event_type"] == "JOB_CLAIMED":
            event["created_at"] = display


def test_equal_recorded_timestamps_do_not_assert_physical_zero(bundle):
    result = _changed_call(bundle, lambda c: _set_claim_time(c, 1_000_000))
    assert result["completed_sample_quantiles_ms"]["p50"] == 0
    assert result["clock_summary"]["physical_elapsed_accuracy"] == "NOT_ESTABLISHED"
    assert result["clock_summary"]["error_bound_ms"] is None


def test_display_projection_is_required(bundle):
    def change(c):
        c["reads"]["claim-full"]["record"]["created_at"] = "1970-01-01T00:16:41+00:00"
        c["reads"]["child-events"]["record"][1]["created_at"] = "1970-01-01T00:16:41+00:00"
    _hold(_changed_call(bundle, change), "EVENT_PAIR_DISPLAY_MISMATCH")


def _second_child(c):
    """Add an earlier Event-ID claim with a LATER recorded timestamp."""
    reads = c["reads"]
    old = c["inventory"]["members"][0]["claim_candidates"][0]
    candidate = copy.deepcopy(old)
    names = {name: "second-" + name for name in ("child-created", "child-job", "claim-full", "claim-ms", "attempt", "child-events")}
    replacements = {"JOB-002": "JOB-003", "ATT-synthetic01": "ATT-synthetic02",
                    "synthetic-child-create-001": "second-child-create",
                    "synthetic-claim-001": "second-claim"}
    def replace(value):
        if isinstance(value, dict): return {k: replace(v) for k, v in value.items()}
        if isinstance(value, list): return [replace(v) for v in value]
        if isinstance(value, str): return replacements.get(value, value)
        return value
    for old_name, new_name in names.items():
        read = replace(copy.deepcopy(reads[old_name]))
        read["evidence_ref"]["uri"] = "synthetic:" + new_name + "-record"
        read["invocation_ref"]["uri"] = "synthetic:" + new_name + "-invocation"
        read["observation"]["read_group"] = new_name
        reads[new_name] = read
    child = reads["second-child-job"]["record"]
    digest = _sha(_encode(child["orchestration_provenance"]).rstrip(b"\n"))
    child["orchestration_provenance_digest"] = digest
    creation = reads["second-child-created"]["record"]
    creation["event_id"] = 21
    creation["payload"]["orchestration_provenance_digest"] = digest
    claim = reads["second-claim-full"]["record"]
    claim["event_id"] = 29
    reads["second-claim-ms"]["record"]["created_at_ms"] = 1_000_800
    reads["second-child-events"]["record"] = [copy.deepcopy(creation), copy.deepcopy(claim)]
    reads["second-child-events"]["observation"]["prefix_last_event_id"] = 29
    reads["jobs"]["record"].append(copy.deepcopy(child))
    candidate.update(creation_read="second-child-created", job_read="second-child-job", attempt_read="second-attempt",
                     claim={"full_read": "second-claim-full", "millisecond_read": "second-claim-ms"})
    c["inventory"]["members"][0]["claim_candidates"].append(candidate)
    c["inventory"]["members"][0]["child_event_inventory_reads"].append("second-child-events")


def test_event_id_firstness(bundle):
    result = _changed_call(bundle, _second_child)
    assert result["completed_recorded_intervals"] == 1
    assert result["member_results"][0]["recorded_delta_ms"] == 800


def test_missing_earlier_claim_inventory_prevents_firstness(bundle):
    def change(c):
        _second_child(c)
        c["inventory"]["members"][0]["claim_candidates"].pop()
    _hold(_changed_call(bundle, change), "FIRST_CLAIM_NOT_ESTABLISHED")


def test_retry_population_does_not_inflate_roots(bundle):
    def change(c):
        c["inventory"]["members"] *= 100
    result = _changed_call(bundle, change)
    assert result["inventory_population"] == 1
    assert result["known_admitted_roots"] == 1
    assert result["completed_recorded_intervals"] == 1
    assert result["distinct_contributing_roots"] == 1
    _ceiling(result)


@pytest.mark.parametrize("fault", ["missing_root", "missing_claim", "filtered_scope", "unknown_scope", "missing_child"])
def test_membership_and_claim_coverage(bundle, fault):
    def change(c):
        if fault == "missing_root": c["reads"]["jobs"]["record"].pop(0)
        elif fault == "missing_child": c["reads"]["jobs"]["record"].pop()
        elif fault == "missing_claim":
            c["reads"]["child-events"]["record"].pop()
            c["reads"]["child-events"]["observation"]["prefix_last_event_id"] = 20
        elif fault == "unknown_scope": c["reads"]["child-events"]["observation"]["coverage"] = "UNKNOWN"
        else:
            r = c["reads"]["child-events"]
            r["arguments"]["command_id_prefix"] = "synthetic-"
            r["observation"]["scope"] = copy.deepcopy(r["arguments"])
    _hold(_changed_call(bundle, change))


def test_terminal_subjects_child_cancel_does_not_terminate_root(bundle):
    def change(c):
        for name in ("terminal-full", "terminal-ms"):
            r = c["reads"][name]["record"]
            r["job_id"] = "JOB-002"
            if "aggregate_id" in r: r["aggregate_id"] = "JOB-002"
        c["reads"]["root-events"]["record"].pop()
        c["reads"]["root-events"]["observation"]["prefix_last_event_id"] = 10
        c["reads"]["child-events"]["record"].append(copy.deepcopy(c["reads"]["terminal-full"]["record"]))
        c["reads"]["child-events"]["observation"]["prefix_last_event_id"] = 31
        c["reads"]["root-job"]["record"]["status"] = "QUEUED"
        c["reads"]["jobs"]["record"][0]["status"] = "QUEUED"
        c["inventory"]["members"][0]["lifecycle_subject_job_id"] = "JOB-002"
    result = _changed_call(bundle, change, "E15")
    _hold(result)
    member = result["member_results"][0]
    assert member["state"] == "RIGHT_CENSORED"
    assert member["outcome_retained"] == "CANCELLED"
    assert member["outcome_subject_job_id"] == "JOB-002"


def test_current_terminal_snapshot_cannot_date_cutoff(bundle):
    def change(c):
        c["inventory"]["members"][0]["lifecycle_evidence_reads"] = ["root-job"]
    _hold(_changed_call(bundle, change, "E15"), "OUTCOME_AT_CUTOFF_UNKNOWN")


@pytest.mark.parametrize("fault", ["backdated", "unknown_effect", "unclosed_prefix"])
def test_cutoff_is_not_a_filtered_watermark(bundle, fault):
    raw, artifacts, manifest, _, _ = _load(bundle, "E17")
    c = json.loads(raw)
    if fault == "unclosed_prefix":
        c["reads"]["child-events-at-cutoff"]["observation"]["coverage"] = "OBSERVED_PREFIX_ONLY"
    else:
        ref = c["inventory"]["closure_ref"]
        content = json.loads(artifacts[ref["uri"]])
        content["late_backdated_or_pending_pre_cutoff_claims"] = fault
        _put(artifacts, ref, content)
        c["run"]["cutoff"]["closure_ref"] = copy.deepcopy(ref)
        c["reads"]["child-events-at-cutoff"]["observation"]["closure_ref"] = copy.deepcopy(ref)
    _refresh(c, artifacts); raw = _encode(c); manifest, anchor = _reanchor(raw, manifest)
    _hold(_call(raw, artifacts, manifest, anchor))


def _multi_root_call(bundle, durations):
    raw, artifacts, manifest, _, _ = _load(bundle)
    base = json.loads(raw)
    combined = copy.deepcopy(base)
    combined["reads"] = {}
    combined["inventory"]["members"] = []
    all_jobs = []
    for i, duration in enumerate(durations):
        c = copy.deepcopy(base)
        _set_claim_time(c, 1_000_000 + duration)
        intent = f"test-intent-{i}"
        fingerprint = _sha(intent.encode())
        replacements = {"synthetic-root-001": intent, "ceo-intent:synthetic-root-001": "ceo-intent:" + intent,
                        "JOB-001": f"ROOT-{i}", "JOB-002": f"CHILD-{i}", "ATT-synthetic01": f"ATT-{i}",
                        "synthetic-child-create-001": f"create-{i}", "synthetic-claim-001": f"claim-{i}",
                        "a" * 64: fingerprint}
        def replace(value):
            if isinstance(value, dict): return {k: replace(v) for k, v in value.items()}
            if isinstance(value, list): return [replace(v) for v in value]
            if isinstance(value, str): return replacements.get(value, value)
            return value
        c = replace(c)
        root_job = c["reads"]["root-job"]["record"]
        root_digest = _sha(_encode(root_job["orchestration_provenance"]).rstrip(b"\n"))
        root_job["orchestration_provenance_digest"] = root_digest
        for name in ("root-full", "root-ms"):
            c["reads"][name]["record"]["payload"]["orchestration_provenance_digest"] = root_digest
        child = c["reads"]["child-job"]["record"]
        child["orchestration_provenance"]["source_digest"] = root_digest
        child_digest = _sha(_encode(child["orchestration_provenance"]).rstrip(b"\n"))
        child["orchestration_provenance_digest"] = child_digest
        c["reads"]["child-created"]["record"]["payload"]["orchestration_provenance_digest"] = child_digest
        c["reads"]["root-full"]["record"]["event_id"] = 100 * i + 10
        c["reads"]["child-created"]["record"]["event_id"] = 100 * i + 20
        c["reads"]["claim-full"]["record"]["event_id"] = 100 * i + 30
        c["reads"]["child-events"]["record"] = [copy.deepcopy(c["reads"][n]["record"]) for n in ("child-created", "claim-full")]
        c["reads"]["child-events"]["observation"]["prefix_last_event_id"] = 100 * i + 30
        all_jobs.extend([root_job, child])
        member = c["inventory"]["members"][0]
        renames = {name: f"r{i}-{name}" for name in c["reads"] if name != "jobs"}
        def rename_ids(value):
            if isinstance(value, dict): return {k: rename_ids(v) for k, v in value.items()}
            if isinstance(value, list): return [rename_ids(v) for v in value]
            if isinstance(value, str): return renames.get(value, value)
            return value
        combined["inventory"]["members"].append(rename_ids(member))
        for name, read in c["reads"].items():
            if name == "jobs": continue
            read["evidence_ref"]["uri"] = "synthetic:" + renames[name] + "-record"
            read["invocation_ref"]["uri"] = "synthetic:" + renames[name] + "-invocation"
            read["observation"]["read_group"] = renames[name]
            combined["reads"][renames[name]] = read
    combined["reads"]["jobs"] = copy.deepcopy(base["reads"]["jobs"])
    combined["reads"]["jobs"]["record"] = all_jobs
    _refresh(combined, artifacts)
    raw = _encode(combined)
    manifest, anchor = _reanchor(raw, manifest)
    return raw, artifacts, manifest, anchor


@pytest.mark.parametrize("durations,expected", [([], (None, None, None)), ([17], (17, 17, 17)),
    ([40, 10, 20, 30], (20, 40, 40)), (list(range(1, 21)), (10, 19, 20))])
def test_conditional_quantiles(bundle, durations, expected):
    result = _call(*_multi_root_call(bundle, durations))
    assert result["completed_recorded_intervals"] == len(durations)
    assert tuple(result["completed_sample_quantiles_ms"][k] for k in ("p50", "p95", "max")) == expected
    _ceiling(result)


def test_conflicting_group_does_not_quarantine_an_independent_root(bundle):
    raw, artifacts, manifest, _ = _multi_root_call(bundle, [10, 20])
    c = json.loads(raw)
    replay = copy.deepcopy(c["inventory"]["members"][0])
    replay["fingerprint"] = "d" * 64
    c["inventory"]["members"].append(replay)
    raw = _encode(c); manifest, anchor = _reanchor(raw, manifest)
    result = _call(raw, artifacts, manifest, anchor)
    assert result["known_admitted_roots"] == 2
    assert result["completed_recorded_intervals"] == 1
    assert result["completed_sample_quantiles_ms"]["p50"] == 20
    assert len(result["member_results"]) == 2


def test_fully_populated_synthetic_floor_still_has_no_authority(bundle):
    result = _call(*_multi_root_call(bundle, [250] * 100))
    assert result["completed_recorded_intervals"] == result["distinct_contributing_roots"] == 100
    _ceiling(result)


def test_retained_schema_parity(bundle):
    # jsonschema is already hash-locked in the repository's dev gate via MCP;
    # it is test-only. The target does not import it or read either schema.
    from jsonschema import Draft202012Validator
    input_validator = Draft202012Validator(json.loads(_unseal(bundle["files"]["original/input.schema.json"])))
    output_validator = Draft202012Validator(json.loads(_unseal(bundle["files"]["r1/output.schema.json"])))
    for case in _CASES:
        raw, artifacts, manifest, anchor, expected = _load(bundle, case)
        assert input_validator.is_valid(json.loads(raw)) == (case != "E13"), case
        output_validator.validate(expected)
        output_validator.validate(_call(raw, artifacts, manifest, anchor))
    for raw in (b"null", b"\xff", b"{}", b'{"x":NaN}'):
        output_validator.validate(_call(raw, {}, None, None))


def test_each_closed_envelope_and_reader_field_is_checked(bundle):
    raw, artifacts, manifest, anchor, _ = _load(bundle)
    base = json.loads(raw)
    paths = [(), ("source",), ("run",), ("run", "clock"), ("run", "cutoff"),
             ("run", "accepted_budget_ms"), ("inventory",), ("inventory", "members", 0),
             ("inventory", "members", 0, "root_admission"),
             ("inventory", "members", 0, "claim_candidates", 0),
             ("inventory", "members", 0, "claim_candidates", 0, "claim")]
    for name in base["reads"]:
        paths.extend([("reads", name), ("reads", name, "arguments"), ("reads", name, "observation"),
                      ("reads", name, "evidence_ref"), ("reads", name, "invocation_ref")])
        if base["reads"][name]["reader"] in ("RuntimeStore.find_event_by_command_id", "EventRegistry.get_event_by_command_id"):
            paths.append(("reads", name, "record"))
    for path in paths:
        target = base
        for key in path:
            target = target[key]
        for fault in ["__unknown_field__", *target]:
            if (fault != "__unknown_field__" and len(path) == 3 and path[0] == "reads"
                    and path[-1] == "arguments" and base["reads"][path[1]]["reader"] == "EventRegistry.list_events"):
                continue  # Native list-events filters are optional, unlike named lookups.
            c = copy.deepcopy(base)
            node = c
            for key in path:
                node = node[key]
            if fault == "__unknown_field__": node[fault] = True
            else: node.pop(fault)
            result = _call(_encode(c), artifacts, manifest, anchor)
            # A shape miss must not hide behind the otherwise inevitable fixed-
            # capsule mismatch. No stale hash can satisfy this assertion.
            assert "INPUT_SHAPE_INVALID" in result["reason_codes"], (path, fault, result["reason_codes"])


def test_open_owned_projection_preserves_extra_owner_fields(bundle):
    def change(c):
        for name in ("root-job", "child-job", "attempt", "receipt"):
            c["reads"][name]["record"]["owner_extension"] = {"opaque": [None, 1, "preserved"]}
    result = _changed_call(bundle, change)
    assert result["completed_recorded_intervals"] == 1


def test_unused_named_reader_identity_is_still_checked(bundle):
    def change(c):
        read = copy.deepcopy(c["reads"]["child-job"])
        read["arguments"]["job_id"] = "substituted-job"
        read["observation"]["scope"] = copy.deepcopy(read["arguments"])
        read["evidence_ref"]["uri"] = "synthetic:unused-record"
        read["invocation_ref"]["uri"] = "synthetic:unused-invocation"
        c["reads"]["unused"] = read
    _hold(_changed_call(bundle, change), "READER_ARGUMENT_IDENTITY_MISMATCH")


def test_same_attempt_identity_conflict_is_not_a_later_mutable_status(bundle):
    def change(c):
        read = copy.deepcopy(c["reads"]["attempt"])
        read["record"]["fence_generation"] += 1
        read["evidence_ref"]["uri"] = "synthetic:second-attempt-record"
        read["invocation_ref"]["uri"] = "synthetic:second-attempt-invocation"
        read["observation"]["read_group"] = "later-attempt-read"
        c["reads"]["later-attempt"] = read
    _hold(_changed_call(bundle, change))


def test_detailed_cutoff_cannot_hide_a_contradictory_pending_effect(bundle):
    raw, artifacts, manifest, _, _ = _load(bundle, "E17")
    c = json.loads(raw)
    ref = c["inventory"]["closure_ref"]
    content = json.loads(artifacts[ref["uri"]])
    content["pending_unknown_effect"] = True
    _put(artifacts, ref, content)
    c["run"]["cutoff"]["closure_ref"] = copy.deepcopy(ref)
    c["reads"]["child-events-at-cutoff"]["observation"]["closure_ref"] = copy.deepcopy(ref)
    _refresh(c, artifacts); raw = _encode(c); manifest, anchor = _reanchor(raw, manifest)
    result = _call(raw, artifacts, manifest, anchor)
    _hold(result)
    assert all(m["right_censor_lower_bound_ms"] is None for m in result["member_results"])


def test_selected_child_failure_cannot_be_omitted_from_outcome_ledger(bundle):
    def change(c):
        m = c["inventory"]["members"][0]
        m["lifecycle_outcome"] = "ACTIVE"
        m["lifecycle_subject_job_id"] = "JOB-001"
        m["lifecycle_evidence_reads"] = ["root-job"]
    _hold(_changed_call(bundle, change, "E16"), "OUTCOME_AT_CUTOFF_UNKNOWN")


def test_later_backdated_claim_invalidates_timestamp_cut_closure(bundle):
    def change(c):
        _second_child(c)
        c["reads"]["second-claim-ms"]["record"]["created_at_ms"] = 1_001_250
        c["reads"]["second-claim-full"]["record"]["created_at"] = "1970-01-01T00:16:41+00:00"
        c["reads"]["second-child-events"]["record"][1]["created_at"] = "1970-01-01T00:16:41+00:00"
    result = _changed_call(bundle, change)
    _hold(result, "CUTOFF_CLOSURE_UNPROVEN")
    assert result["member_results"][0]["raw_difference_ms"] == 1250
    assert result["member_results"][0]["right_censor_lower_bound_ms"] is None


@pytest.mark.parametrize("evidence_class", ["SYNTHETIC", "OWNER_EXPORTED"])
@pytest.mark.parametrize("wrapper_key,pointer", [("wrapped", "/wrapped"), ("wr/ap~ped", "/wr~1ap~0ped")])
def test_provenance_follows_dereferenced_evidence(bundle, evidence_class, wrapper_key, pointer):
    raw, artifacts, manifest, _, _ = _load(bundle)
    c = json.loads(raw)
    c["evidence_class"] = evidence_class
    invocation_uris = {r["invocation_ref"]["uri"] for r in c["reads"].values()}
    for uri, content in list(artifacts.items()):
        if uri not in invocation_uris:
            artifacts[uri] = _encode({wrapper_key: json.loads(content)})
    def replace_refs(value):
        if isinstance(value, dict):
            if set(value) == {"uri", "bytes", "sha256", "json_pointer"}:
                value["json_pointer"] = pointer + value["json_pointer"]
                if value["uri"] not in invocation_uris:
                    content = artifacts[value["uri"]]
                    value.update(bytes=len(content), sha256=_sha(content))
            else:
                for child in value.values(): replace_refs(child)
        elif isinstance(value, list):
            for child in value: replace_refs(child)
    replace_refs(c)
    for read in c["reads"].values():
        ref = read["invocation_ref"]
        content = _encode({wrapper_key: {k: read[k] for k in ("reader", "arguments", "observation")}})
        artifacts[ref["uri"]] = content
        ref.update(bytes=len(content), sha256=_sha(content))
    raw = _encode(c); manifest, _ = _reanchor(raw, manifest)
    trusted = json.loads(manifest)
    trusted["evidence_class"] = evidence_class  # Separate synthetic test call, never a real owner grant.
    manifest = _encode(trusted)
    result = _call(raw, artifacts, manifest, _sha(manifest))
    if evidence_class == "OWNER_EXPORTED":
        _hold(result, "SYNTHETIC_PROVENANCE_LAUNDERING")
        assert "SYNTHETIC_INPUT" in result["reason_codes"]
    else:
        assert result["completed_recorded_intervals"] == 1
        assert result["completed_sample_quantiles_ms"]["p50"] == 250


def test_inventory_only_failed_child_cannot_be_declared_active(bundle):
    def change(c):
        c["reads"].pop("terminal-full")
        c["reads"].pop("terminal-ms")
        m = c["inventory"]["members"][0]
        m["lifecycle_outcome"] = "ACTIVE"
        m["lifecycle_subject_job_id"] = "JOB-001"
        m["lifecycle_evidence_reads"] = ["root-job"]
    result = _changed_call(bundle, change, "E16")
    _hold(result, "OUTCOME_AT_CUTOFF_UNKNOWN")
    assert result["member_results"][0]["outcome_retained"] == "UNKNOWN"


def _job_snapshot_status(capsule, job_id, status, source):
    """Change a new synthetic control, retaining distinct native read groups."""
    for read in capsule["reads"].values():
        if read["reader"] == "JobRegistry.get_job" and source in ("named", "both"):
            records = [read["record"]]
        elif read["reader"] == "JobRegistry.list_jobs" and source in ("inventory", "both"):
            records = read["record"]
        else:
            continue
        for job in records:
            if job is not None and job["job_id"] == job_id:
                job["status"] = status


@pytest.mark.parametrize("status", ["FAILED", "CANCELLED", "LOST", "COMPLETED"])
@pytest.mark.parametrize("source", ["named", "inventory", "both"])
@pytest.mark.parametrize("selected", [True, False], ids=["selected", "omitted"])
@pytest.mark.parametrize("job_id", ["JOB-001", "JOB-002"], ids=["root", "claimed-child"])
def test_terminal_job_snapshot_selector_cannot_hide_outcome(bundle, status, source, selected, job_id):
    def change(c):
        _job_snapshot_status(c, job_id, status, source)
        member = c["inventory"]["members"][0]
        member["lifecycle_subject_job_id"] = job_id
        member["lifecycle_evidence_reads"] = ["root-job", "child-job", "jobs"] if selected else []
    result = _changed_call(bundle, change)
    _hold(result, "OUTCOME_AT_CUTOFF_UNKNOWN")
    member = result["member_results"][0]
    assert member["outcome_retained"] == "UNKNOWN"
    assert member["recorded_delta_ms"] is None
    assert member["raw_difference_ms"] == 250


@pytest.mark.parametrize("source", ["named", "inventory", "both"])
@pytest.mark.parametrize("selected", [True, False], ids=["selected", "omitted"])
def test_running_job_snapshot_selector_preserves_positive(bundle, source, selected):
    def change(c):
        _job_snapshot_status(c, "JOB-002", "RUNNING", source)
        c["inventory"]["members"][0]["lifecycle_evidence_reads"] = (
            ["root-job", "child-job", "jobs"] if selected else [])
    result = _changed_call(bundle, change)
    _ceiling(result)
    assert result["completed_recorded_intervals"] == 1
    assert result["member_results"][0]["recorded_delta_ms"] == 250
    assert result["member_results"][0]["outcome_retained"] == "ACTIVE"


@pytest.mark.parametrize("source", ["named", "inventory", "both"])
@pytest.mark.parametrize("job_id", ["JOB-001", "JOB-002"])
@pytest.mark.parametrize("subject", ["JOB-001", "JOB-002", None])
def test_terminal_job_snapshot_covers_measured_jobs_despite_subject(bundle, source, job_id, subject):
    def change(c):
        _job_snapshot_status(c, job_id, "FAILED", source)
        member = c["inventory"]["members"][0]
        member["lifecycle_evidence_reads"] = []
        member["lifecycle_subject_job_id"] = subject
    result = _changed_call(bundle, change)
    _hold(result, "OUTCOME_AT_CUTOFF_UNKNOWN")
    assert result["member_results"][0]["outcome_retained"] == "UNKNOWN"


def _later_claimed_sibling(capsule):
    _second_child(capsule)
    reads = capsule["reads"]
    # The original JOB-002 claim remains Event-ID first and measures 250 ms.
    reads["second-claim-full"]["record"]["event_id"] = 31
    reads["second-child-events"]["record"][1] = copy.deepcopy(reads["second-claim-full"]["record"])
    reads["second-child-events"]["observation"]["prefix_last_event_id"] = 31


@pytest.mark.parametrize("status", ["FAILED", "CANCELLED", "LOST", "COMPLETED"])
@pytest.mark.parametrize("source", ["named", "inventory", "both"])
@pytest.mark.parametrize("selected", [True, False], ids=["selected", "omitted"])
def test_terminal_job_snapshot_unrelated_sibling_does_not_poison_measurement(bundle, status, source, selected):
    def change(c):
        _later_claimed_sibling(c)
        _job_snapshot_status(c, "JOB-003", status, source)
        member = c["inventory"]["members"][0]
        member["lifecycle_subject_job_id"] = "JOB-001"
        member["lifecycle_evidence_reads"] = (
            ["root-job", "child-job", "second-child-job", "jobs"] if selected else [])
    result = _changed_call(bundle, change)
    _ceiling(result)
    assert result["completed_recorded_intervals"] == 1
    assert result["member_results"][0]["recorded_delta_ms"] == 250
    assert result["member_results"][0]["outcome_retained"] == "ACTIVE"
    assert result["member_results"][0]["outcome_subject_job_id"] == "JOB-001"


@pytest.mark.parametrize("source", ["named", "inventory", "both"])
def test_terminal_job_snapshot_explicit_sibling_subject_cannot_be_declared_active(bundle, source):
    def change(c):
        _later_claimed_sibling(c)
        _job_snapshot_status(c, "JOB-003", "CANCELLED", source)
        member = c["inventory"]["members"][0]
        member["lifecycle_subject_job_id"] = "JOB-003"
        member["lifecycle_evidence_reads"] = []
    _hold(_changed_call(bundle, change), "OUTCOME_AT_CUTOFF_UNKNOWN")


@pytest.mark.parametrize("status,outcome", [
    ("FAILED", "FAILED"), ("CANCELLED", "CANCELLED"),
    ("LOST", "LOST"), ("COMPLETED", "TERMINAL_OTHER"),
])
@pytest.mark.parametrize("selected", [True, False], ids=["selected", "omitted"])
def test_later_terminal_job_snapshot_preserves_causally_supported_interval(bundle, status, outcome, selected):
    def change(c):
        _job_snapshot_status(c, "JOB-002", status, "both")
        event_type = "JOB_" + status
        for read in c["reads"].values():
            records = ([read["record"]] if read["reader"] in (
                "EventRegistry.get_event_by_command_id", "RuntimeStore.find_event_by_command_id")
                else read["record"] if read["reader"] == "EventRegistry.list_events" else [])
            for record in records:
                if record is not None and record["event_type"] == "JOB_FAILED":
                    record["event_type"] = event_type
        member = c["inventory"]["members"][0]
        member["lifecycle_outcome"] = outcome
        member["lifecycle_evidence_reads"] = ["terminal-full", "terminal-ms"]
        if selected:
            member["lifecycle_evidence_reads"] += ["child-job", "jobs"]
    result = _changed_call(bundle, change, "E16")
    _ceiling(result)
    assert result["completed_recorded_intervals"] == 1
    assert result["member_results"][0]["recorded_delta_ms"] == 250
    assert result["member_results"][0]["outcome_retained"] == outcome


@pytest.mark.parametrize("status", ["FAILED", "CANCELLED", "LOST", "COMPLETED"])
@pytest.mark.parametrize("source_read", ["child-job", "jobs"])
@pytest.mark.parametrize("selected", [True, False], ids=["selected", "omitted"])
def test_terminal_job_snapshot_consistent_duplicate_preserves_refusal(bundle, status, source_read, selected):
    def change(c):
        _job_snapshot_status(c, "JOB-002", status, "both")
        read = copy.deepcopy(c["reads"][source_read])
        read["evidence_ref"]["uri"] = "synthetic:duplicate-terminal-snapshot-record"
        read["invocation_ref"]["uri"] = "synthetic:duplicate-terminal-snapshot-invocation"
        # Same declared group and consistent bytes do not create a conflict.
        c["reads"]["duplicate-terminal-snapshot"] = read
        c["inventory"]["members"][0]["lifecycle_evidence_reads"] = (
            ["duplicate-terminal-snapshot"] if selected else ["root-job"])
    result = _changed_call(bundle, change)
    _hold(result, "OUTCOME_AT_CUTOFF_UNKNOWN")
    assert result["member_results"][0]["outcome_retained"] == "UNKNOWN"


@pytest.mark.parametrize("source", ["named", "inventory", "both"])
@pytest.mark.parametrize("selected", [True, False], ids=["selected", "omitted"])
def test_terminal_job_snapshot_role_null_sibling_is_not_a_measured_child(bundle, source, selected):
    def change(c):
        read = copy.deepcopy(c["reads"]["child-job"])
        job = read["record"]
        job.update(job_id="JOB-role-null", orchestration_role=None,
                   orchestration_provenance=None, orchestration_provenance_digest=None,
                   status="CANCELLED", current_attempt_id=None)
        read["arguments"]["job_id"] = job["job_id"]
        read["observation"]["scope"] = copy.deepcopy(read["arguments"])
        read["observation"]["read_group"] = "role-null-sibling-snapshot"
        read["evidence_ref"]["uri"] = "synthetic:role-null-sibling-record"
        read["invocation_ref"]["uri"] = "synthetic:role-null-sibling-invocation"
        if source in ("named", "both"):
            c["reads"]["role-null-sibling"] = read
        if source in ("inventory", "both"):
            c["reads"]["jobs"]["record"].append(copy.deepcopy(job))
        member = c["inventory"]["members"][0]
        member["lifecycle_subject_job_id"] = "JOB-001"
        member["lifecycle_evidence_reads"] = ["root-job"]
        if selected:
            member["lifecycle_evidence_reads"] += ["jobs"]
            if source in ("named", "both"):
                member["lifecycle_evidence_reads"] += ["role-null-sibling"]
    result = _changed_call(bundle, change)
    _ceiling(result)
    assert result["completed_recorded_intervals"] == 1
    assert result["member_results"][0]["recorded_delta_ms"] == 250
    assert result["member_results"][0]["outcome_retained"] == "ACTIVE"


@pytest.mark.parametrize("container,behavior", [(kind, behavior)
    for kind in ("mapping", "dict-subclass") for behavior in ("empty", "one", "raising")])
def test_artifact_map_boundary_rejects_protocols_before_hooks(container, behavior):
    from collections.abc import Mapping

    markers = []

    def entered(hook):
        markers.append(hook)
        if behavior == "raising":
            raise RuntimeError("CONTROLLED_ARTIFACT_CONTAINER_HOOK")

    class HostileMapping(Mapping):
        def __iter__(self):
            entered("iter")
            return iter(("synthetic:inert",) if behavior == "one" else ())

        def __len__(self):
            entered("len")
            return int(behavior == "one")

        def __getitem__(self, key):
            entered("getitem")
            return b"{}"

    class HostileDict(dict):
        def items(self):
            entered("items")
            return ({"synthetic:inert": b"{}"} if behavior == "one" else {}).items()

    supplied = HostileMapping() if container == "mapping" else HostileDict()
    result = None
    escaped = None
    try:
        result = _call(b"{}", supplied, None, None)
    except RuntimeError as exc:
        escaped = exc
    assert markers == [], (container, behavior, markers)
    assert escaped is None
    _hold(result, "INPUT_ARGUMENT_TYPE")
    assert result["reason_codes"] == ["DRAFT_NOT_ACCEPTED", "INPUT_ARGUMENT_TYPE"]
    assert result["input_sha256"] == _sha(b"{}")


@pytest.mark.parametrize("invalid_part", ["key", "value"])
@pytest.mark.parametrize("position", ["first", "last"])
def test_artifact_map_boundary_rejects_entry_subclasses_without_hooks(invalid_part, position):
    markers = []
    armed = [False]

    def entered(name):
        if armed[0]:
            markers.append(name)
            raise RuntimeError("CONTROLLED_ARTIFACT_ENTRY_HOOK")

    class HostileKey(str):
        def __hash__(self):
            entered("key-hash")
            return str.__hash__(self)

        def __bool__(self):
            entered("key-bool")
            return True

        def __eq__(self, other):
            entered("key-equality")
            return str.__eq__(self, other)

        def encode(self, *args, **kwargs):
            entered("key-encode")
            return str.encode(self, *args, **kwargs)

    class HostileValue(bytes):
        def __len__(self):
            entered("value-len")
            return bytes.__len__(self)

        def __iter__(self):
            entered("value-iter")
            return bytes.__iter__(self)

        def decode(self, *args, **kwargs):
            entered("value-decode")
            return bytes.decode(self, *args, **kwargs)

    invalid = (HostileKey("synthetic:invalid"), b"{}") if invalid_part == "key" else (
        "synthetic:invalid", HostileValue(b"{}"))
    valid = ("synthetic:ordinary", b"{}")
    supplied = dict([invalid, valid] if position == "first" else [valid, invalid])
    # Building the test dictionary legitimately hashes its key; the boundary
    # assertion starts only when the reducer receives the already-built map.
    armed[0] = True
    result = _call(b"{}", supplied, None, None)
    assert markers == []
    _hold(result, "INPUT_ARGUMENT_TYPE")


def test_artifact_map_boundary_ordinary_dict_behavior(bundle):
    _hold(_call(b"{}", {}, None, None), "INPUT_SHAPE_INVALID")
    raw, artifacts, manifest, anchor, expected = _load(bundle)
    assert type(artifacts) is dict
    assert _call(raw, artifacts, manifest, anchor) == expected


def _owner_metadata_boundary_input(bundle):
    # A new synthetic diagnostic with a declared OWNER_EXPORTED category is
    # never an owner export or an operational trust-anchor acceptance.
    raw, artifacts, manifest, _, _ = _load(bundle)
    capsule = json.loads(raw)
    capsule["evidence_class"] = "OWNER_EXPORTED"
    return capsule, artifacts, manifest


def _assert_owner_metadata_neutral(result):
    _hold(result)
    assert result["evidence_class"] == "OWNER_EXPORTED"
    assert result["runtime_instance_epoch"] is None
    assert result["inventory_coverage"] == "UNKNOWN"
    assert result["clock_summary"]["comparability"] == "UNKNOWN"
    assert result["clock_summary"]["timestamp_order"] == "UNKNOWN"
    assert result["clock_summary"]["error_bound_ms"] is None
    assert result["read_scope_qualifiers"] == []


@pytest.mark.parametrize("fault", ["missing_both", "missing_manifest", "missing_anchor",
    "wrong_anchor", "manifest_bytes", "capsule_binding", "reference_binding"])
def test_owner_metadata_boundary_anchor_refusals(bundle, fault):
    capsule, artifacts, original_manifest = _owner_metadata_boundary_input(bundle)
    raw = _encode(capsule)
    manifest, anchor = _reanchor(raw, original_manifest)
    reason = "TRUST_ANCHOR_MISMATCH"
    if fault == "missing_both":
        artifacts, manifest, anchor = {}, None, None
        reason = "TRUST_ANCHOR_UNAVAILABLE"
    elif fault == "missing_manifest":
        manifest = None
        reason = "TRUST_ANCHOR_UNAVAILABLE"
    elif fault == "missing_anchor":
        anchor = None
        reason = "TRUST_ANCHOR_UNAVAILABLE"
    elif fault == "wrong_anchor":
        anchor = "0" * 64
    elif fault == "manifest_bytes":
        manifest += b" "
    else:
        value = json.loads(manifest)
        if fault == "capsule_binding":
            value["capsule_sha256"] = "0" * 64
        else:
            value["accepted_refs"][-1]["sha256"] = "0" * 64
        manifest = _encode(value)
        anchor = _sha(manifest)
    result = _call(raw, artifacts, manifest, anchor)
    assert reason in result["reason_codes"]
    if fault == "missing_both":
        assert result["reason_codes"] == ["DRAFT_NOT_ACCEPTED", reason]
    _assert_owner_metadata_neutral(result)


@pytest.mark.parametrize("position", ["first", "last"])
@pytest.mark.parametrize("fault,reason", [
    ("missing_artifact", "EVIDENCE_BYTES_MISSING"),
    ("artifact_hash", "EVIDENCE_BYTES_MISMATCH"),
    ("pointer", "EVIDENCE_POINTER_INVALID"),
    ("record", "READ_RECORD_MISMATCH"),
    ("invocation", "READER_INVOCATION_MISMATCH"),
    ("window", "READ_WINDOW_UNPROVEN"),
    ("epoch", "RUNTIME_INSTANCE_MISMATCH"),
])
def test_owner_metadata_boundary_evidence_refusals(bundle, position, fault, reason):
    capsule, artifacts, original_manifest = _owner_metadata_boundary_input(bundle)
    names = tuple(capsule["reads"])
    name = names[0] if position == "first" else names[-1]
    read = capsule["reads"][name]
    if fault == "missing_artifact":
        artifacts.pop(read["evidence_ref"]["uri"])
    elif fault == "artifact_hash":
        artifacts[read["evidence_ref"]["uri"]] += b" "
    elif fault == "pointer":
        read["evidence_ref"]["json_pointer"] = "/missing"
    elif fault == "record":
        _put(artifacts, read["evidence_ref"], {"different_record": True})
    elif fault == "invocation":
        invocation = json.loads(artifacts[read["invocation_ref"]["uri"]])
        invocation["arguments"] = {"different_argument": True}
        _put(artifacts, read["invocation_ref"], invocation)
    else:
        if fault == "window":
            read["observation"]["read_finished_at_ms"] = read["observation"]["read_started_at_ms"] - 1
        else:
            read["observation"]["runtime_instance_epoch"] = "different-instance"
        _refresh(capsule, artifacts)
    raw = _encode(capsule)
    manifest, anchor = _reanchor(raw, original_manifest)
    result = _call(raw, artifacts, manifest, anchor)
    assert reason in result["reason_codes"], (position, fault, result["reason_codes"])
    _assert_owner_metadata_neutral(result)


@pytest.mark.parametrize("artifacts_present", [False, True])
def test_owner_metadata_boundary_budget_shortcut(bundle, artifacts_present):
    raw, artifacts, manifest, _, _ = _load(bundle, "E13")
    capsule = json.loads(raw)
    capsule["evidence_class"] = "OWNER_EXPORTED"
    result = _call(_encode(capsule), artifacts if artifacts_present else {}, None, None)
    expected_reasons = ["DRAFT_NOT_ACCEPTED"] + (["SYNTHETIC_INPUT"] if artifacts_present else [])
    assert result["reason_codes"] == expected_reasons
    assert [m["reason_codes"] for m in result["member_results"]] == [["DRAFT_ACCEPTED_BUDGET_FORBIDDEN"]]
    _assert_owner_metadata_neutral(result)


@pytest.mark.parametrize("planted", ["inventory", "clock", "both"])
def test_owner_metadata_boundary_unselected_shortcut(bundle, planted):
    raw = _unseal(bundle["files"]["original/unselected-operational-input.template.json"])
    capsule = json.loads(raw)
    assert capsule["evidence_class"] == "OWNER_EXPORTED"
    if planted in ("inventory", "both"):
        capsule["inventory"]["coverage"] = "COMPLETE"
    if planted in ("clock", "both"):
        capsule["run"]["clock"]["comparability"] = "SUPPORTED_RECORDED_BASIS"
        capsule["run"]["clock"]["error_bound_ms"] = 0
    result = _call(_encode(capsule), {}, None, None)
    assert result["reason_codes"] == ["DRAFT_NOT_ACCEPTED", "OPERATIONAL_PARAMETERS_UNSELECTED",
                                      "INVENTORY_COVERAGE_UNKNOWN"]
    _assert_owner_metadata_neutral(result)


def test_owner_metadata_boundary_validated_laundering_retains_diagnostics(bundle):
    raw, artifacts, manifest, anchor, expected = _load(bundle, "E14")
    result = _call(raw, artifacts, manifest, anchor)
    assert result == expected
    assert result["evidence_class"] == "OWNER_EXPORTED"
    assert result["runtime_instance_epoch"] == "SYNTHETIC-INSTANCE-EPOCH-1"
    assert result["inventory_coverage"] == "COMPLETE"
    assert result["clock_summary"]["comparability"] == "SUPPORTED_RECORDED_BASIS"
    assert result["read_scope_qualifiers"]
    assert result["member_results"][0]["reason_codes"] == ["SYNTHETIC_PROVENANCE_LAUNDERING"]
    _ceiling(result)


def test_owner_metadata_boundary_synthetic_and_unselected_parity(bundle):
    raw, _, _, _, expected = _load(bundle, "E13")
    assert _call(raw, {}, None, None) == expected
    raw = _unseal(bundle["files"]["original/unselected-operational-input.template.json"])
    expected = json.loads(_unseal(bundle["files"]["original/unselected-operational-input.expected.json"]))
    assert _call(raw, {}, None, None) == expected


@pytest.mark.parametrize("mutation", ["add-key", "replace-value"])
def test_b1b2_artifact_snapshot_ignores_later_caller_mutation(mutation):
    import sys

    original = {"synthetic:a": b"0", "synthetic:b": b"0"}
    expected = _call(b"{}", original.copy(), None, None)
    changed = False

    def interleave(frame, event, _argument):
        nonlocal changed
        if (event == "line" and frame.f_code is reduce_first_stratum.__code__
                and frame.f_locals.get("uri") == "synthetic:a" and not changed):
            changed = True
            if mutation == "add-key":
                original["synthetic:c"] = b"0"
            else:
                original["synthetic:b"] = b"\xff"
        return interleave

    previous_trace = sys.gettrace()
    sys.settrace(interleave)
    try:
        actual = _call(b"{}", original, None, None)
    finally:
        sys.settrace(previous_trace)
    assert changed, "the deterministic interleaving must actually occur"
    assert sys.gettrace() is previous_trace
    assert actual == expected
    _hold(actual, "INPUT_SHAPE_INVALID")


def _b1b2_terminal_representation(capsule, representation):
    """Keep one terminal representation; FULL retains its mandatory MS pair."""
    reads = capsule["reads"]
    if representation != "FULL":
        reads.pop("terminal-full")
    if representation == "EVENTS":
        reads.pop("terminal-ms")
    else:
        read = reads["child-events"]
        read["record"] = [event for event in read["record"]
                          if event["event_type"] != "JOB_FAILED"]
        read["observation"]["prefix_last_event_id"] = 30
    _job_snapshot_status(capsule, "JOB-002", "RUNNING", "both")
    member = capsule["inventory"]["members"][0]
    member["lifecycle_outcome"] = "ACTIVE"
    member["lifecycle_evidence_reads"] = []
    return {"FULL": ["terminal-full", "terminal-ms"],
            "EVENTS": ["child-events"], "MS": ["terminal-ms"]}[representation]


def _b1b2_unknown_without_contribution(result, raw_difference):
    _hold(result, "OUTCOME_AT_CUTOFF_UNKNOWN")
    member = result["member_results"][0]
    assert member["state"] == "UNKNOWN"
    assert member["outcome_retained"] == "UNKNOWN"
    assert member["raw_difference_ms"] == raw_difference
    assert member["recorded_delta_ms"] is None
    assert member["root_weight"] == 0


@pytest.mark.parametrize("selected", [False, True], ids=["omitted", "selected"])
@pytest.mark.parametrize("terminal_type", [
    "JOB_FAILED", "JOB_CANCELLED", "JOB_LOST", "JOB_COMPLETED",
])
def test_b1b2_narrow_terminal_blocks_active_regardless_of_selector(bundle, terminal_type, selected):
    def change(capsule):
        selected_reads = _b1b2_terminal_representation(capsule, "MS")
        narrow = capsule["reads"]["terminal-ms"]
        narrow["record"]["event_type"] = terminal_type
        narrow["record"]["payload"] = {"synthetic_outcome": terminal_type.lower()}
        narrow["arguments"]["command_id"] = "synthetic-narrow-" + terminal_type.lower()
        narrow["observation"]["scope"] = copy.deepcopy(narrow["arguments"])
        member = capsule["inventory"]["members"][0]
        member["lifecycle_subject_job_id"] = "JOB-002"
        member["lifecycle_evidence_reads"] = selected_reads if selected else []

    _b1b2_unknown_without_contribution(_changed_call(bundle, change, "E16"), 250)



def _b1b2_assert_terminal_fixture(capsule, representation, subject, selected):
    reads = capsule["reads"]
    named = {read["record"]["job_id"]: read["record"]["status"]
             for read in reads.values()
             if read["reader"] == "JobRegistry.get_job" and read["record"] is not None}
    inventory = {job["job_id"]: job["status"] for job in reads["jobs"]["record"]}
    expected_jobs = {"JOB-001": "QUEUED", "JOB-002": "RUNNING", "JOB-003": "RUNNING"}
    assert named == inventory == expected_jobs
    member = capsule["inventory"]["members"][0]
    claim_order = sorted(
        (reads[candidate["claim"]["full_read"]]["record"]["event_id"],
         reads[candidate["job_read"]]["record"]["job_id"])
        for candidate in member["claim_candidates"]
    )
    assert claim_order == [(29, "JOB-003"), (30, "JOB-002")]
    terminal_reads = set()
    for read_id, read in reads.items():
        records = ([read["record"]] if read["reader"] in (
            "EventRegistry.get_event_by_command_id", "RuntimeStore.find_event_by_command_id")
            else read["record"] if read["reader"] == "EventRegistry.list_events" else [])
        for record in records:
            if record is not None and record["event_type"] in (
                    "JOB_FAILED", "JOB_CANCELLED", "JOB_LOST", "JOB_COMPLETED"):
                assert record["job_id"] == "JOB-002"
                terminal_reads.add(read_id)
    selectors = {"FULL": ["terminal-full", "terminal-ms"],
                 "EVENTS": ["child-events"], "MS": ["terminal-ms"]}[representation]
    assert terminal_reads == set(selectors)
    assert member["lifecycle_outcome"] == "ACTIVE"
    assert member["lifecycle_subject_job_id"] == subject
    assert member["lifecycle_evidence_reads"] == (selectors if selected else [])


@pytest.mark.parametrize("selected", [False, True], ids=["omitted", "selected"])
@pytest.mark.parametrize("representation", ["FULL", "EVENTS", "MS"])
def test_b1b2_explicit_nonfirst_terminal_subject_blocks_active(bundle, representation, selected):
    def change(capsule):
        _second_child(capsule)
        selected_reads = _b1b2_terminal_representation(capsule, representation)
        _job_snapshot_status(capsule, "JOB-003", "RUNNING", "both")
        member = capsule["inventory"]["members"][0]
        # JOB-003 now has the first Event-ID claim; JOB-002 is still an allowed
        # child and is the explicit lifecycle subject of the ACTIVE assertion.
        member["lifecycle_subject_job_id"] = "JOB-002"
        member["lifecycle_evidence_reads"] = selected_reads if selected else []
        _b1b2_assert_terminal_fixture(capsule, representation, "JOB-002", selected)

    _b1b2_unknown_without_contribution(_changed_call(bundle, change, "E16"), 800)


@pytest.mark.parametrize("subject", ["JOB-001", "JOB-003"], ids=["root", "first-child"])
@pytest.mark.parametrize("representation", ["FULL", "EVENTS", "MS"])
def test_b1b2_unselected_terminal_sibling_does_not_poison_interval(bundle, representation, subject):
    def change(capsule):
        _second_child(capsule)
        _b1b2_terminal_representation(capsule, representation)
        _job_snapshot_status(capsule, "JOB-003", "RUNNING", "both")
        capsule["inventory"]["members"][0]["lifecycle_subject_job_id"] = subject
        _b1b2_assert_terminal_fixture(capsule, representation, subject, False)

    result = _changed_call(bundle, change, "E16")
    _ceiling(result)
    assert result["completed_recorded_intervals"] == 1
    member = result["member_results"][0]
    assert member["state"] == "COMPLETE_RECORDED_INTERVAL"
    assert member["outcome_retained"] == "ACTIVE"
    assert member["raw_difference_ms"] == member["recorded_delta_ms"] == 800
    assert member["root_weight"] == 1


def _b3_same_child_claim(capsule, milliseconds=1_000_100):
    reads = capsule["reads"]
    member = capsule["inventory"]["members"][0]
    original = member["claim_candidates"][0]
    for old_name in ("claim-full", "claim-ms", "attempt"):
        name = "b3-earlier-" + old_name
        read = copy.deepcopy(reads[old_name])
        read["evidence_ref"]["uri"] = "synthetic:" + name + "-record"
        read["invocation_ref"]["uri"] = "synthetic:" + name + "-invocation"
        read["observation"]["read_group"] = "b3-" + name
        reads[name] = read
    for name in ("b3-earlier-claim-full", "b3-earlier-claim-ms"):
        read = reads[name]
        read["arguments"]["command_id"] = "b3-earlier-claim"
        read["observation"]["scope"] = copy.deepcopy(read["arguments"])
        read["record"]["payload"]["cycle_command_id"] = "b3-earlier-claim"
    earlier = reads["b3-earlier-claim-full"]["record"]
    earlier.update(event_id=25, sequence=2, command_id="b3-earlier-claim",
                   attempt_id="ATT-b3-earlier")
    reads["b3-earlier-claim-ms"]["record"]["created_at_ms"] = milliseconds
    earlier["created_at"] = (datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
                             + datetime.timedelta(seconds=milliseconds // 1000)).isoformat(timespec="seconds")
    attempt = reads["b3-earlier-attempt"]
    attempt["arguments"]["attempt_id"] = "ATT-b3-earlier"
    attempt["observation"]["scope"] = copy.deepcopy(attempt["arguments"])
    attempt["record"].update(attempt_id="ATT-b3-earlier", status="FAILED")
    # Preserve plausible per-Job order and historical-vs-current Attempt identity.
    reads["claim-full"]["record"]["sequence"] = 3
    for name in ("claim-full", "claim-ms"):
        reads[name]["record"]["payload"]["attempt_number"] = 2
    reads["attempt"]["record"]["attempt_number"] = 2
    reads["child-events"]["record"][1] = copy.deepcopy(reads["claim-full"]["record"])
    candidate = copy.deepcopy(original)
    candidate.update(attempt_read="b3-earlier-attempt", claim={
        "full_read": "b3-earlier-claim-full", "millisecond_read": "b3-earlier-claim-ms"})
    assert earlier["job_id"] == reads["claim-full"]["record"]["job_id"] == "JOB-002"
    assert 20 < earlier["event_id"] < reads["claim-full"]["record"]["event_id"]
    return candidate


def _b3_supplied_claim(capsule, milliseconds, representation):
    """Retain one relevant representation without selecting its claim."""
    candidate = _b3_same_child_claim(capsule, milliseconds)
    reads = capsule["reads"]
    earlier = reads["b3-earlier-claim-full"]["record"]
    later = reads["claim-full"]["record"]
    assert (earlier["event_id"], earlier["sequence"], later["event_id"], later["sequence"]) == (25, 2, 30, 3)
    assert earlier["payload"] == reads["b3-earlier-claim-ms"]["record"]["payload"]
    assert later["payload"] == reads["claim-ms"]["record"]["payload"]
    assert earlier["payload"]["attempt_number"] == reads["b3-earlier-attempt"]["record"]["attempt_number"] == 1
    assert later["payload"]["attempt_number"] == reads["attempt"]["record"]["attempt_number"] == 2
    assert reads["child-job"]["record"]["current_attempt_id"] == later["attempt_id"] != earlier["attempt_id"]
    assert all(job["status"] == ("QUEUED" if job["job_id"] == "JOB-001" else "RUNNING")
               for job in reads["jobs"]["record"])
    if representation == "EVENTS":
        read = copy.deepcopy(reads["child-events"])
        read["record"].insert(1, copy.deepcopy(earlier))
        read["evidence_ref"]["uri"] = "synthetic:b3-all-child-events-record"
        read["invocation_ref"]["uri"] = "synthetic:b3-all-child-events-invocation"
        read["observation"]["read_group"] = "b3-all-child-events"
        reads["b3-all-child-events"] = read
        assert [event["event_id"] for event in read["record"]] == [20, 25, 30]
    if representation != "PAIRED":
        if representation != "FULL":
            reads.pop("b3-earlier-claim-full")
        if representation != "MS":
            reads.pop("b3-earlier-claim-ms")
        reads.pop("b3-earlier-attempt")
    return candidate


def _b3_unknown_without_point(result):
    _hold(result, "FIRST_CLAIM_NOT_ESTABLISHED")
    member = result["member_results"][0]
    assert member["state"] == "UNKNOWN"
    assert member["reason_codes"] == ["FIRST_CLAIM_NOT_ESTABLISHED"]
    assert member["raw_difference_ms"] == 250
    assert member["recorded_delta_ms"] is None
    assert member["root_weight"] == 0


@pytest.mark.parametrize("representation", ["PAIRED", "FULL", "MS", "EVENTS"])
@pytest.mark.parametrize("milliseconds", [1_000_100, 1_000_800], ids=["100ms", "800ms"])
def test_b3_supplied_omitted_same_child_claim_prevents_firstness(bundle, milliseconds, representation):
    def change(capsule):
        _b3_supplied_claim(capsule, milliseconds, representation)
    _b3_unknown_without_point(_changed_call(bundle, change))


@pytest.mark.parametrize("milliseconds", [1_000_100, 1_000_800], ids=["100ms", "800ms"])
def test_b3_fully_reconciled_same_child_claim_uses_event_id(bundle, milliseconds):
    def change(capsule):
        candidate = _b3_supplied_claim(capsule, milliseconds, "PAIRED")
        capsule["inventory"]["members"][0]["claim_candidates"].append(candidate)
        earlier = capsule["reads"]["b3-earlier-claim-full"]["record"]
        capsule["reads"]["child-events"]["record"].insert(1, copy.deepcopy(earlier))
        assert [event["event_id"] for event in capsule["reads"]["child-events"]["record"]] == [20, 25, 30]
    result = _changed_call(bundle, change)
    _ceiling(result)
    member = result["member_results"][0]
    assert result["completed_recorded_intervals"] == result["distinct_contributing_roots"] == 1
    assert member["state"] == "COMPLETE_RECORDED_INTERVAL"
    assert member["root_weight"] == 1
    assert member["raw_difference_ms"] == member["recorded_delta_ms"] == milliseconds - 1_000_000


@pytest.mark.parametrize("milliseconds", [1_000_100, 1_000_800], ids=["100ms", "800ms"])
def test_b3_supplied_inventory_selector_does_not_change_firstness(bundle, milliseconds):
    results, supplied_reads = [], []
    for selected in (False, True):
        def change(capsule):
            _b3_supplied_claim(capsule, milliseconds, "EVENTS")
            if selected:
                capsule["inventory"]["members"][0]["child_event_inventory_reads"].append("b3-all-child-events")
            supplied_reads.append(_encode(capsule["reads"]))
        results.append(_changed_call(bundle, change))
    assert supplied_reads[0] == supplied_reads[1]
    for result in results:
        _b3_unknown_without_point(result)
    assert results[0]["member_results"] == results[1]["member_results"]
    assert results[0]["completed_sample_quantiles_ms"] == results[1]["completed_sample_quantiles_ms"]


@pytest.mark.parametrize("representation", ["PAIRED", "FULL", "MS", "EVENTS"])
def test_b3_unrelated_job_claim_does_not_poison_firstness(bundle, representation):
    def change(capsule):
        _b3_supplied_claim(capsule, 1_000_100, representation)
        for name, read in capsule["reads"].items():
            if not name.startswith("b3-"):
                continue
            if read["reader"] == "EventRegistry.list_events":
                read["record"] = [event for event in read["record"] if event["event_id"] == 25]
                read["arguments"] = {"job_id": "JOB-UNRELATED"}
                read["observation"]["scope"] = copy.deepcopy(read["arguments"])
                read["observation"]["prefix_last_event_id"] = 25
                records = read["record"]
            else:
                records = [read["record"]]
            for record in records:
                record["job_id"] = "JOB-UNRELATED"
                if "aggregate_id" in record:
                    record["aggregate_id"] = "JOB-UNRELATED"
                if "payload" in record:
                    record["payload"]["dispatch_job_id"] = "JOB-UNRELATED"
    result = _changed_call(bundle, change)
    _ceiling(result)
    member = result["member_results"][0]
    assert result["completed_recorded_intervals"] == result["distinct_contributing_roots"] == 1
    assert member["state"] == "COMPLETE_RECORDED_INTERVAL"
    assert member["root_weight"] == 1
    assert member["raw_difference_ms"] == member["recorded_delta_ms"] == 250
