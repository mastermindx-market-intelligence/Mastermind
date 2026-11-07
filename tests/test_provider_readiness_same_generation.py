"""Explicit same-generation terminal requalification: current pin, same credential, >=24h."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops.executive_os import provider_readiness as r

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ops" / "executive_os" / "provision-worker-auth.sh"
FLAG = "--requalify-same-generation-terminal-sha256"


def iso(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def canary(passed=False):
    return {
        "schema_version": r.CANARY_SCHEMA, "canary_id": "canary-123456789abc",
        "observed_at": r.now_iso(), "codex_version": r.CODEX_VERSION,
        "codex_sha256": r.CODEX_SHA256, "codex_team_identifier": r.CODEX_TEAM_ID,
        "model": r.PRODUCTION_MODEL, "exit_code": 0 if passed else 1,
        "timed_out": False, "terminal_event_class": "turn_completed" if passed else "provider_turn_failed",
        "result_valid": passed, "stdout_sha256": "a" * 64, "stderr_sha256": "b" * 64,
        "provider_error_message_count": 0, "provider_error_message_sha256": None,
        "provider_error_terms": [], "workspace_capability_outcome": "inert_untrusted_workspace",
        "workspace_selection_mechanism": "none", "forced_chatgpt_workspace_id_applied": False,
        "passed": passed, "refusal": None if passed else "provider_turn_failed",
    }


def write_json(path, value):
    if path.exists():
        path.chmod(0o600)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    path.chmod(0o400)


def age(document, observed):
    """Re-date a closed failure and its components to one observation time."""
    d = copy.deepcopy(document)
    d.update(observed_at=iso(observed),
             credential_expires_at=iso(observed + timedelta(hours=12)),
             readiness_expires_at=iso(observed + timedelta(hours=12)))
    d["provider_identity"]["observed_at"] = iso(observed)
    d["inference_canary"]["observed_at"] = iso(observed)
    return d


@pytest.fixture
def state(tmp_path, monkeypatch):
    os.chown(tmp_path, -1, os.getgid())  # macOS inherits the parent directory group.
    auth = dict(device=1, inode=2, uid=451, gid=451, mode=0o600,
                size=123, mtime_ns=4, ctime_ns=5, nlink=1)
    current = {**auth, "uid": 0, "gid": 0, "mode": 0o555,
               "path": str(r.CODEX_BINARY), "version": r.CODEX_VERSION,
               "sha256": r.CODEX_SHA256, "team_identifier": r.CODEX_TEAM_ID}
    old = {**current, "path": str(r.CODEX_BINARY.with_name("codex-0.147.0")),
           "version": r.REQUALIFICATION_PREDECESSOR_VERSION,
           "sha256": r.REQUALIFICATION_PREDECESSOR_SHA256}
    identity = {
        "schema_version": r.IDENTITY_SCHEMA, "passed": True, "refusal": None,
        "expected_credential_kind": "device-auth", "auth_mode": "chatgpt",
        "account_type": "chatgpt", "plan_type": "self_serve_business_prolite",
        "requires_openai_auth": True, "workspace_binding_class": r.WORKSPACE_BINDING_CLASS,
        "observed_at": r.now_iso(), "codex_binary": current, "credential_lstat": auth,
        "forced_chatgpt_workspace_id_applied": False,
    }
    deadline = iso(datetime.now(UTC) + timedelta(minutes=55))
    # Historical failure on the CURRENT pin with the SAME credential lstat.
    document = age(r.compose_receipt(
        identity=identity, canary=canary(), auth_identity=auth, binary_identity=current,
        expected_kind="device-auth", workspace_binding_class=r.WORKSPACE_BINDING_CLASS,
        credential_expires_at=deadline, canary_command_status=1,
    ), datetime.now(UTC) - timedelta(days=2))
    receipt = tmp_path / "readiness.json"
    identity_path = tmp_path / "identity.json"
    write_json(receipt, document)
    write_json(identity_path, identity)
    # Only OS principal/ACL and installed-binary observation are substituted.
    # Real file bytes, chmod, lstat, fsync, archive and atomic CAS run unchanged.
    monkeypatch.setattr(r, "_validate_receipt_directory", lambda path: None)
    monkeypatch.setattr(r, "_assert_no_macos_acl", lambda path: None)
    monkeypatch.setattr(r, "receipt_storage_contract", lambda **kw: (os.getuid(), os.getgid(), 0o400))
    monkeypatch.setattr(r, "current_auth_identity", lambda *a, **k: dict(auth))
    monkeypatch.setattr(r, "current_binary_identity", lambda *a, **k: dict(current))
    result = SimpleNamespace(auth=auth, current=current, old=old, identity=identity, document=document,
                             receipt=receipt, identity_path=identity_path, deadline=deadline, tmp=tmp_path)
    result.digest = hashlib.sha256(receipt.read_bytes()).hexdigest()
    return result


def cli(s, command, *, flag=FLAG, **kwargs):
    args = [command, "--receipt", str(s.receipt), "--expected-kind", "device-auth",
            "--workspace-binding-class", r.WORKSPACE_BINDING_CLASS,
            "--credential-expires-at", kwargs.get("deadline", s.deadline)]
    if command == "reserve":
        args += ["--identity-json", str(s.identity_path)]
    if flag is not None:
        args += [flag, kwargs.get("digest", s.digest)]
    return r.main(args)


def refusal(s, document, *, deadline=None):
    with pytest.raises(r.ReadinessError) as caught:
        r.classify_same_generation_terminal_requalification(
            document, auth_identity=r.current_auth_identity(), binary_identity=r.current_binary_identity(),
            expected_kind="device-auth", workspace_binding_class=r.WORKSPACE_BINDING_CLASS,
            new_credential_expires_at=deadline or s.deadline,
        )
    return str(caught.value)


def replace(s, document):
    write_json(s.receipt, document)
    return s.receipt.read_bytes(), hashlib.sha256(s.receipt.read_bytes()).hexdigest()


def assert_untouched(s, original):
    assert s.receipt.read_bytes() == original
    assert list(s.tmp.glob("*.superseded-*")) == []


def finalize(s, passed):
    canary_path = s.tmp / "canary.json"
    write_json(canary_path, canary(passed))
    return r.main([
        "finalize", "--receipt", str(s.receipt),
        "--post-identity-json", str(s.identity_path), "--post-identity-command-status", "0",
        "--canary-json", str(canary_path), "--canary-command-status", "0" if passed else "1",
        "--expected-kind", "device-auth", "--workspace-binding-class", r.WORKSPACE_BINDING_CLASS,
        "--credential-expires-at", s.deadline,
    ])


# 1
def test_default_reuse_stays_closed(state):
    original = state.receipt.read_bytes()
    assert cli(state, "reuse", flag=None) == 2
    assert cli(state, "reserve", flag=None) == 2
    assert_untouched(state, original)


# 2
def test_upgrade_option_refuses_same_generation_failure(state, monkeypatch):
    monkeypatch.setattr(r, "_attested_predecessor_identity", lambda: dict(state.old))
    original = state.receipt.read_bytes()
    assert cli(state, "reuse", flag="--requalify-terminal-adverse-sha256") == 2
    assert cli(state, "reserve", flag="--requalify-terminal-adverse-sha256") == 2
    assert_untouched(state, original)


# 3
def test_explicit_reuse_returns_nine_and_is_read_only(state):
    original = state.receipt.read_bytes()
    assert cli(state, "reuse") == 9
    assert_untouched(state, original)


# 4
@pytest.mark.parametrize("digest", ["", "a" * 63, "A" * 64, "z" * 64, "a" * 64])
def test_digest_fence_refuses_without_effect(state, digest):
    original = state.receipt.read_bytes()
    assert cli(state, "reuse", digest=digest) == 2
    assert cli(state, "reserve", digest=digest) == 2
    assert_untouched(state, original)


# 5
@pytest.mark.parametrize(("minutes", "status"), [(20, 2), (61, 2), (45, 9)])
def test_deadline_is_thirty_to_sixty_minutes(state, minutes, status):
    deadline = iso(datetime.now(UTC) + timedelta(minutes=minutes))
    assert cli(state, "reuse", deadline=deadline) == status
    if status == 2:
        assert refusal(state, state.document, deadline=deadline) == "requalification_deadline_out_of_bounds"


# 6
def test_predecessor_binary_failure_is_not_same_generation(state):
    d = copy.deepcopy(state.document)
    d["codex_binary"] = state.old
    d["provider_identity"]["codex_binary"] = state.old
    d["inference_canary"].update(codex_version=state.old["version"], codex_sha256=state.old["sha256"])
    original, digest = replace(state, d)
    assert refusal(state, d) == "requalification_same_generation_binary_mismatch"
    assert cli(state, "reuse", digest=digest) == 2
    assert cli(state, "reserve", digest=digest) == 2
    assert_untouched(state, original)


# 7
def test_changed_live_credential_refuses(state, monkeypatch):
    changed = {**state.auth, "inode": state.auth["inode"] + 1}
    monkeypatch.setattr(r, "current_auth_identity", lambda *a, **k: dict(changed))
    original = state.receipt.read_bytes()
    assert refusal(state, state.document) == "requalification_same_generation_credential_changed"
    assert cli(state, "reuse") == 2
    assert cli(state, "reserve") == 2
    assert_untouched(state, original)


# 8
@pytest.mark.parametrize("change", ["passing", "reserved"])
def test_passing_receipt_or_reservation_refuses(state, change):
    d = copy.deepcopy(state.document)
    if change == "passing":
        d.update(passed=True, refusal=None)
    else:
        d.update(refusal="canary_reserved", inference_canary=None)
    original, digest = replace(state, d)
    assert refusal(state, d) == "requalification_requires_terminal_adverse"
    assert cli(state, "reuse", digest=digest) == 2
    assert cli(state, "reserve", digest=digest) == 2
    assert_untouched(state, original)


# 9
@pytest.mark.parametrize(("hours", "status"), [(23, 2), (25, 9)])
def test_failure_must_be_at_least_one_day_old(state, hours, status):
    d = age(state.document, datetime.now(UTC) - timedelta(hours=hours))
    original, digest = replace(state, d)
    assert cli(state, "reuse", digest=digest) == status
    if status == 2:
        assert refusal(state, d) == "requalification_same_generation_failure_too_recent"
    assert_untouched(state, original)


# 10
def test_unreviewed_live_binary_refuses(state, monkeypatch):
    unreviewed = {**state.current, "sha256": "a" * 64}
    monkeypatch.setattr(r, "current_binary_identity", lambda *a, **k: dict(unreviewed))
    original = state.receipt.read_bytes()
    assert refusal(state, state.document) == "requalification_current_binary_unreviewed"
    assert cli(state, "reuse") == 2
    assert cli(state, "reserve") == 2
    assert_untouched(state, original)


# 11
@pytest.mark.parametrize(("change", "reason"), [
    ("stale_identity", "requalification_fresh_identity_required"),
    ("future_identity", "requalification_fresh_identity_required"),
    ("identity_plan", "requalification_provider_identity_changed"),
])
def test_reserve_requires_fresh_unchanged_identity(state, capsys, change, reason):
    value = copy.deepcopy(state.identity)
    if change == "stale_identity":
        value["observed_at"] = iso(datetime.now(UTC) - timedelta(minutes=10))
    elif change == "future_identity":
        value["observed_at"] = iso(datetime.now(UTC) + timedelta(minutes=10))
    else:
        value["plan_type"] = "enterprise"
    write_json(state.identity_path, value)
    original = state.receipt.read_bytes()
    capsys.readouterr()
    assert cli(state, "reserve") == 2
    assert f"provider readiness refused: {reason}\n" in capsys.readouterr().err
    assert_untouched(state, original)


# 12
def test_one_reservation_archives_exact_old_bytes(state):
    old_bytes = state.receipt.read_bytes()
    assert cli(state, "reserve") == 0
    reserved = state.receipt.read_bytes()
    assert json.loads(reserved)["refusal"] == "canary_reserved"
    archive, = state.tmp.glob("*.superseded-*")
    assert archive.name == f"{state.receipt.name}.superseded-{state.digest[:16]}.json"
    assert archive.read_bytes() == old_bytes
    assert archive.stat().st_mode & 0o777 == 0o400
    assert cli(state, "reserve") == 2
    assert state.receipt.read_bytes() == reserved
    assert archive.read_bytes() == old_bytes


# 13
def test_passing_canary_finalizes_valid_receipt(state):
    assert cli(state, "reserve") == 0
    assert finalize(state, True) == 0
    final = json.loads(state.receipt.read_bytes())
    assert final["passed"] is True
    r.validate_receipt_file(
        state.receipt, expected_kind="device-auth",
        workspace_binding_class=r.WORKSPACE_BINDING_CLASS, credential_expires_at=state.deadline,
    )


# 14
def test_failing_canary_is_one_shot_for_a_day(state):
    old_bytes = state.receipt.read_bytes()
    assert cli(state, "reserve") == 0
    assert finalize(state, False) == 2
    final = state.receipt.read_bytes()
    document = json.loads(final)
    assert document["passed"] is False and document["refusal"] == "provider_turn_failed"
    assert refusal(state, document) == "requalification_same_generation_failure_too_recent"
    digest = hashlib.sha256(final).hexdigest()
    assert cli(state, "reuse", digest=digest) == 2
    assert cli(state, "reserve", digest=digest) == 2
    assert state.receipt.read_bytes() == final
    archive, = state.tmp.glob("*.superseded-*")
    assert archive.read_bytes() == old_bytes


# 15
@pytest.mark.parametrize(("command", "other"), [
    ("reuse", ["--requalify-terminal-adverse-sha256", "a" * 64]),
    ("reserve", ["--requalify-terminal-adverse-sha256", "a" * 64]),
    ("reserve", ["--refresh-expired"]),
])
def test_option_is_mutually_exclusive(state, command, other):
    args = [command, "--receipt", str(state.receipt), "--expected-kind", "device-auth",
            "--workspace-binding-class", r.WORKSPACE_BINDING_CLASS,
            "--credential-expires-at", state.deadline, FLAG, state.digest, *other]
    with pytest.raises(SystemExit) as caught:
        r.main(args)
    assert caught.value.code == 2


# 16
def test_shell_forwards_same_digest_and_requires_only_rc9() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "--requalify-same-generation-terminal-sha256 SHA256" in source.split("usage() {", 1)[1].split("}", 1)[0]
    assert ('[ -z "$REQUALIFY_SAME_GENERATION_TERMINAL_SHA256" ] '
            '|| explicit_count=$((explicit_count + 1))') in source
    branch = source.split('if [ "$VERIFY_READY" = "true" ]; then', 1)[1].split(
        'if [ "$ENROLL_SERVICE_ACCOUNT" = "true" ]; then', 1
    )[0]
    initialization, after_reuse = branch.split('provider_readiness.py" reuse', 1)
    chain = ('elif [ -n "$REQUALIFY_SAME_GENERATION_TERMINAL_SHA256" ]; then\n'
             '    requalification_args=(--requalify-same-generation-terminal-sha256 '
             '"$REQUALIFY_SAME_GENERATION_TERMINAL_SHA256")')
    assert chain in initialization
    assert initialization.index(chain) < initialization.index(
        'elif [ -n "$REQUALIFY_TERMINAL_ADVERSE_SHA256" ]; then')
    gates = after_reuse.split("IDENTITY_RESULT=", 1)[0]
    gate = ('elif [ -n "$REQUALIFY_SAME_GENERATION_TERMINAL_SHA256" ]; then\n'
            '    # Status 9 admits only a >=24h-old closed terminal failure recorded on the\n'
            '    # exact current pin with the exact unchanged credential lstat.\n'
            '    [ "$reuse_status" -eq 9 ] || {\n'
            '      /bin/echo "explicit same-generation terminal requalification is not eligible; '
            'no canary spent" >&2\n'
            '      exit 65\n'
            '    }\n')
    assert gate in gates
    assert gates.index(gate) < gates.index('[ "$reuse_status" -eq 5 ]')
    forwarding = '${requalification_args[@]+"${requalification_args[@]}"}'
    assert branch.count(forwarding) == 2


@pytest.mark.skipif(os.geteuid() == 0, reason="the usage path must be exercised as non-root")
@pytest.mark.parametrize(("extra", "status"), [
    (["--requalify-terminal-adverse-sha256", "b" * 64], 64),
    ([], 77),
])
def test_shell_counts_option_as_one_explicit_transition(extra, status) -> None:
    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), "--verify-ready", "--expected-credential-kind", "device-auth",
         "--workspace-binding-class", "company-workspace-admin-attested",
         "--credential-expires-at", "2026-10-11T12:00:00Z", FLAG, "a" * 64, *extra],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == status
    if status == 77:
        assert "root" in result.stderr


# 17
@pytest.mark.parametrize("changes", [
    {"timed_out": True},
    {"exit_code": 0}, {"exit_code": 2}, {"exit_code": -9}, {"exit_code": None},
    {"exit_code": "1"}, {"exit_code": True}, {"exit_code": 1.0},
    {"result_valid": True},
    {"terminal_event_class": "turn_completed"}, {"terminal_event_class": None},
    {"refusal": "provider_timeout"},
], ids=lambda changes: ",".join(f"{key}={value!r}" for key, value in changes.items()))
def test_canary_must_record_a_closed_terminal_failure(state, changes):
    d = copy.deepcopy(state.document)
    d["inference_canary"].update(changes)
    original, digest = replace(state, d)
    assert refusal(state, d) == "requalification_effect_not_closed_terminal"
    assert cli(state, "reuse", digest=digest) == 2
    assert cli(state, "reserve", digest=digest) == 2
    assert_untouched(state, original)


# 18
SKEW_PAST = r.MAX_CLOCK_SKEW + timedelta(minutes=1)


@pytest.mark.parametrize(("component", "offset", "status"), [
    ("provider_identity", SKEW_PAST, 2),
    ("provider_identity", -SKEW_PAST, 2),
    ("inference_canary", SKEW_PAST, 2),
    ("inference_canary", -SKEW_PAST, 2),
    ("provider_identity", r.MAX_CLOCK_SKEW, 9),
    ("inference_canary", -r.MAX_CLOCK_SKEW, 9),
])
def test_component_timestamps_must_match_the_failure(state, component, offset, status):
    d = copy.deepcopy(state.document)
    d[component]["observed_at"] = iso(datetime.fromisoformat(d["observed_at"]) + offset)
    original, digest = replace(state, d)
    assert cli(state, "reuse", digest=digest) == status
    if status == 2:
        assert refusal(state, d) == "requalification_component_timestamp_conflict"
        assert cli(state, "reserve", digest=digest) == 2
    assert_untouched(state, original)


# 19
@pytest.mark.parametrize("field", ["codex_binary", "credential_lstat"])
def test_identity_component_must_carry_the_failure_lstat(state, field):
    d = copy.deepcopy(state.document)
    changed = d["provider_identity"][field]
    d["provider_identity"][field] = {**changed, "inode": changed["inode"] + 1}
    original, digest = replace(state, d)
    assert refusal(state, d) == "requalification_identity_mismatch"
    assert cli(state, "reuse", digest=digest) == 2
    assert cli(state, "reserve", digest=digest) == 2
    assert_untouched(state, original)


# 20
def test_privileged_broker_does_not_forward_the_option() -> None:
    from control_plane.executive_privileged_action import (
        REQUEST_SCHEMA, PrivilegedActionError, validate_request,
    )

    def request(args):
        return {"schema": REQUEST_SCHEMA, "request_id": "req-same-gen-001",
                "action": "executive.worker_auth.verify_ready", "args": args}

    company = {"expected_credential_kind": "device-auth",
               "workspace_binding_class": r.WORKSPACE_BINDING_CLASS,
               "credential_expires_at": "2026-10-11T12:00:00Z"}
    validate_request(request(company))
    validate_request(request({**company, "requalify_terminal_adverse_sha256": "a" * 64}))
    with pytest.raises(PrivilegedActionError, match="verify_ready arguments must select"):
        validate_request(request({**company, "requalify_same_generation_terminal_sha256": "a" * 64}))


# 21
def test_admin_client_rejects_the_option_before_transport(monkeypatch, capsys) -> None:
    from scripts import mmx_admin

    monkeypatch.setattr(mmx_admin, "send_request", lambda *a, **k: pytest.fail("transport reached"))
    argv = ["executive.worker_auth.verify_ready", "--expected-credential-kind", "device-auth",
            "--workspace-binding-class", r.WORKSPACE_BINDING_CLASS,
            "--credential-expires-at", "2026-10-11T12:00:00Z", "--request-id", "req-same-gen-001"]
    assert mmx_admin.build_request(argv)["action"] == "executive.worker_auth.verify_ready"
    capsys.readouterr()
    with pytest.raises(SystemExit) as caught:
        mmx_admin.main([*argv, FLAG, "a" * 64])
    assert caught.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err
