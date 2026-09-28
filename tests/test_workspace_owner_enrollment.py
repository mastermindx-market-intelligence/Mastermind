"""Focused synthetic tests for the workspace owner binding compiler.

All fixtures are synthetic (no real Auth0 / OAuth / MCP / Runtime identity).
The tests cover the closed compile contract, the safety fences, the
exclusive-write dance, the redacted receipt, and the prohibition on
prohibited import effects.

The conftest pulls in non-trivial Mastermind fixtures; this module instead
installs a small in-test ``control_plane`` stub so the supplied
``common.executive_workspace_contract`` can import ``JOB_ID_RE`` without the
rest of the control-plane tree. The stub provides only what is needed.
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import re
import stat
import sys
import types
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Install the minimal ``control_plane`` stub required by the supplied
# ``common.executive_workspace_contract`` so that the contract imports without
# the rest of the Mastermind tree. Stubs are intentionally inert: no other
# attribute is reachable from the candidate source.
# ---------------------------------------------------------------------------


def _install_control_plane_stub() -> None:
    if "control_plane" in sys.modules:
        return
    package = types.ModuleType("control_plane")
    package.__path__ = []  # type: ignore[assignment]
    sys.modules["control_plane"] = package

    wake_events = types.ModuleType("control_plane.wake_events")

    def _job_id_re():
        return re.compile(r"^JOB-[0-9]{3,}$")

    wake_events.JOB_ID_RE = _job_id_re()
    package.wake_events = wake_events  # type: ignore[attr-defined]
    sys.modules["control_plane.wake_events"] = wake_events


_install_control_plane_stub()


# Capture the unpatched syscall references BEFORE the autouse fixture
# monkeypatches ``os.fstat`` / ``os.lstat``.  Tests that need real
# (non-faked) stat results opt out by re-monkeypatching with these.
_REAL_FSTAT = os.fstat
_REAL_LSTAT = os.lstat


# ---------------------------------------------------------------------------
# Synthetic root harness — per-test injection at the ``os.fstat`` /
# ``os.lstat`` syscall boundaries.  Only the uid is rewritten so the real
# mode, size, link count, and file-type bits still drive every fence.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _synthetic_root(monkeypatch):
    real_euid = os.geteuid() if hasattr(os, "geteuid") else 0
    monkeypatch.setattr(os, "geteuid", lambda: 0)

    if real_euid == 0:
        yield
        return

    real_fstat = os.fstat
    real_lstat = os.lstat

    def _rewrap(result):
        if result.st_uid == 0:
            return result
        return os.stat_result((
            result.st_mode, result.st_ino, result.st_dev, result.st_nlink,
            0, result.st_gid, result.st_size,
            result.st_atime, result.st_mtime, result.st_ctime,
        ))

    def _faked_fstat(fd, *args, **kwargs):
        return _rewrap(real_fstat(fd, *args, **kwargs))

    def _faked_lstat(path, *args, **kwargs):
        return _rewrap(real_lstat(path, *args, **kwargs))

    monkeypatch.setattr(os, "fstat", _faked_fstat)
    monkeypatch.setattr(os, "lstat", _faked_lstat)
    yield


from common.executive_workspace_contract import (
    BINDINGS_SCHEMA,
    RESOURCE,
    SCOPE,
    canonical,
)
from integrations.business_mcp_auth.contracts import (
    AUTH_POLICY_SCHEMA,
    load_resource_policy,
    subject_digest,
)
from integrations.mastermind_workspace_app.contract import (
    validate_workspace_bindings,
)
import ops.executive_os.workspace_owner_enrollment as compiler_module
from ops.executive_os.workspace_owner_enrollment import (
    PROFILE_ORDER,
    RECEIPT_SCHEMA,
    REQUEST_SCHEMA,
    WorkspaceOwnerCompilerError,
    _OutputCursor,
    _exclusive_create_in_parent,
    _open_parent_fd,
    _open_private_fd,
    _read_text_private,
    compile_bindings,
    _parse_argv,
    main,
    write_binding_document,
    _serialize_document,
)


# ---------------------------------------------------------------------------
# Synthetic Workspace policy + per-slot fixtures.
# ---------------------------------------------------------------------------


WORKSPACE_ISSUER = "https://mcp.mastermind-x.com/"
WORKSPACE_RESOURCE_METADATA = (
    "https://mcp.mastermind-x.com/.well-known/"
    "oauth-protected-resource/workspace/read"
)
WORKSPACE_JWKS = "https://mcp.mastermind-x.com/.well-known/jwks.json"

WEB_SUBJECT = "subject-web-opaque"
MAC_SUBJECT = "subject-mac-opaque"
WEB_CLIENT_ID = "client-web-opaque"
MAC_CLIENT_ID = "client-mac-opaque"
WEB_RECEIPT = b"web-receipt-bytes-v1"
MAC_RECEIPT = b"mac-receipt-bytes-v1"


def _workspace_policy_value(*, subjects=(WEB_SUBJECT, MAC_SUBJECT)):
    issuer = WORKSPACE_ISSUER
    allowed = sorted(
        subject_digest(issuer=issuer, subject=s) for s in subjects
    )
    return {
        "schema": AUTH_POLICY_SCHEMA,
        "policy_id": "mastermind-workspace-v1",
        "resource": RESOURCE,
        "resource_metadata_url": WORKSPACE_RESOURCE_METADATA,
        "issuer": issuer,
        "authorization_servers": [issuer],
        "jwks_uri": WORKSPACE_JWKS,
        "required_scopes": [SCOPE],
        "allowed_subject_digests": allowed,
        "allowed_algorithms": ["RS256"],
        "clock_skew_seconds": 30,
        "max_token_lifetime_seconds": 900,
        "jwks_cache_ttl_seconds": 300,
        "unknown_kid_refresh_cooldown_seconds": 30,
        "fetch_failure_backoff_seconds": 5,
    }


def _workspace_policy(*, subjects=(WEB_SUBJECT, MAC_SUBJECT)):
    return load_resource_policy(_workspace_policy_value(subjects=subjects))


def _values(*, web_enabled=True, mac_enabled=False):
    out = {}
    for name, enabled, subject, client_id, receipt in (
        ("web", web_enabled, WEB_SUBJECT, WEB_CLIENT_ID, WEB_RECEIPT),
        ("mac", mac_enabled, MAC_SUBJECT, MAC_CLIENT_ID, MAC_RECEIPT),
    ):
        if not enabled:
            out[name] = {
                "enabled": False,
                "client_id": None,
                "subject": None,
                "permission_receipt": None,
            }
            continue
        out[name] = {
            "enabled": True,
            "client_id": client_id,
            "subject": subject,
            "permission_receipt": receipt,
        }
    return out


def _stat(mode: int, *, uid: int = 0, size: int = 0, ino: int = 0,
          nlink: int = 1, dev: int = 0) -> os.stat_result:
    return os.stat_result(
        (mode, ino, dev, nlink, uid, 0, size, 0, 0, 0),
    )


def _private_file(directory: Path, name: str, data: bytes, *,
                  mode: int = 0o400) -> Path:
    path = directory / name
    path.write_bytes(data)
    os.chmod(path, mode)
    return path


# ---------------------------------------------------------------------------
# Pure compile contract.
# ---------------------------------------------------------------------------


def test_two_profile_round_trip_via_validator() -> None:
    policy = _workspace_policy()
    document = compile_bindings(policy, _values(web_enabled=True, mac_enabled=True))
    assert document == validate_workspace_bindings(document, policy)
    assert document["schema"] == BINDINGS_SCHEMA
    assert set(document["profiles"]) == {"web", "mac"}
    assert document["profiles"]["web"]["enabled"] is True
    assert document["profiles"]["mac"]["enabled"] is True
    for slot in document["profiles"].values():
        binding = slot["binding"]
        assert binding["policy_id"] == policy.policy_id
        assert binding["resource"] == RESOURCE
        assert binding["scopes"] == [SCOPE]
        assert re.fullmatch(r"[0-9a-f]{64}", binding["client_ref"]) is not None
        assert re.fullmatch(r"[0-9a-f]{64}", binding["issuer_digest"]) is not None
        assert re.fullmatch(r"[0-9a-f]{64}", binding["subject_digest"]) is not None
        assert re.fullmatch(r"[0-9a-f]{64}", binding["permission_digest"]) is not None


def test_one_profile_round_trip_disables_other_slot() -> None:
    policy = _workspace_policy(subjects=(WEB_SUBJECT,))
    document = compile_bindings(policy, _values(web_enabled=True, mac_enabled=False))
    assert document["profiles"]["web"]["enabled"] is True
    assert document["profiles"]["web"]["binding"] is not None
    assert document["profiles"]["mac"] == {"enabled": False, "binding": None}
    assert document == validate_workspace_bindings(document, policy)


def test_client_ref_is_64_lowercase_hex_exact_derivation() -> None:
    policy = _workspace_policy()
    document = compile_bindings(policy, _values(web_enabled=True, mac_enabled=False))
    expected = hashlib.sha256(
        (policy.issuer + "\nclient\n" + WEB_CLIENT_ID).encode("utf-8"),
    ).hexdigest()
    assert document["profiles"]["web"]["binding"]["client_ref"] == expected
    assert len(document["profiles"]["web"]["binding"]["client_ref"]) == 64
    assert document["profiles"]["web"]["binding"]["client_ref"] == expected.lower()


def test_permission_digest_is_exact_sha256_of_receipt_bytes() -> None:
    policy = _workspace_policy()
    document = compile_bindings(policy, _values(web_enabled=True, mac_enabled=False))
    assert document["profiles"]["web"]["binding"]["permission_digest"] == hashlib.sha256(
        WEB_RECEIPT,
    ).hexdigest()


def test_issuer_digest_is_exact_sha256_of_policy_issuer() -> None:
    policy = _workspace_policy()
    document = compile_bindings(policy, _values(web_enabled=True, mac_enabled=False))
    assert document["profiles"]["web"]["binding"]["issuer_digest"] == hashlib.sha256(
        policy.issuer.encode("utf-8"),
    ).hexdigest()


def test_subject_digest_matches_existing_public_function() -> None:
    policy = _workspace_policy()
    document = compile_bindings(policy, _values(web_enabled=True, mac_enabled=False))
    expected = subject_digest(issuer=policy.issuer, subject=WEB_SUBJECT)
    assert document["profiles"]["web"]["binding"]["subject_digest"] == expected


def test_raw_identities_absent_from_compiled_output() -> None:
    policy = _workspace_policy()
    document = compile_bindings(policy, _values(web_enabled=True, mac_enabled=True))
    rendered = repr(document)
    for forbidden in (WEB_SUBJECT, MAC_SUBJECT, WEB_CLIENT_ID, MAC_CLIENT_ID):
        assert forbidden not in rendered


# ---------------------------------------------------------------------------
# Closed request / closed value shape.
# ---------------------------------------------------------------------------


def test_compile_refuses_value_shape_with_unknown_profile() -> None:
    policy = _workspace_policy()
    values = dict(_values())
    values["android"] = values.pop("mac")
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        compile_bindings(policy, values)
    assert exc.value.code == "values_shape"


def test_compile_refuses_value_shape_with_extra_slot_key() -> None:
    policy = _workspace_policy()
    values = _values()
    values["web"]["extra"] = "no"
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        compile_bindings(policy, values)
    assert exc.value.code == "values_slot"


def test_compile_refuses_non_boolean_enabled() -> None:
    policy = _workspace_policy()
    values = _values()
    values["web"]["enabled"] = "yes"
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        compile_bindings(policy, values)
    assert exc.value.code == "values_enabled"


# ---------------------------------------------------------------------------
# Policy fence.
# ---------------------------------------------------------------------------


def test_compile_refuses_policy_with_wrong_resource() -> None:
    base = _workspace_policy_value()
    base["resource"] = "https://attacker.test/mcp/other"
    policy = load_resource_policy(base)
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        compile_bindings(policy, _values())
    assert exc.value.code == "workspace_fence"


def test_compile_refuses_policy_with_wrong_scopes() -> None:
    base = _workspace_policy_value()
    base["required_scopes"] = ["mastermind.executive.read"]
    policy = load_resource_policy(base)
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        compile_bindings(policy, _values())
    assert exc.value.code == "workspace_fence"


def test_compile_refuses_policy_with_extra_scopes() -> None:
    base = _workspace_policy_value()
    base["required_scopes"] = ["mastermind.executive.read", SCOPE]
    policy = load_resource_policy(base)
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        compile_bindings(policy, _values())
    assert exc.value.code == "workspace_fence"


def test_compile_refuses_non_resource_policy_object() -> None:
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        compile_bindings({"policy_id": "x"}, _values())
    assert exc.value.code == "policy_type"


# ---------------------------------------------------------------------------
# Allowlist fence + duplicate-client fence.
# ---------------------------------------------------------------------------


def test_allowlist_fence_refuses_subject_not_in_policy() -> None:
    policy = _workspace_policy(subjects=("other-opaque-subject",))
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        compile_bindings(policy, _values(web_enabled=True, mac_enabled=False))
    assert exc.value.code == "subject_not_allowlisted"


def test_duplicate_client_ref_across_slots_is_refused() -> None:
    policy = _workspace_policy()
    values = _values(web_enabled=True, mac_enabled=True)
    values["mac"]["client_id"] = WEB_CLIENT_ID
    values["mac"]["subject"] = MAC_SUBJECT
    values["mac"]["permission_receipt"] = MAC_RECEIPT
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        compile_bindings(policy, values)
    assert exc.value.code == "duplicate_client"


# ---------------------------------------------------------------------------
# Textual value + receipt fences.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mutation", ["empty", "whitespace", "control", "oversized"])
def test_client_id_text_fence_refuses(mutation) -> None:
    policy = _workspace_policy()
    values = _values()
    if mutation == "empty":
        values["web"]["client_id"] = ""
    elif mutation == "whitespace":
        values["web"]["client_id"] = "  client-web-opaque  "
    elif mutation == "control":
        values["web"]["client_id"] = "client\x01web"
    elif mutation == "oversized":
        values["web"]["client_id"] = "x" * 5000
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        compile_bindings(policy, values)
    assert exc.value.code.startswith("web_client_id_") or exc.value.code == "client_id_oversized" or exc.value.code == "client_id_blank" or exc.value.code == "client_id_control"


@pytest.mark.parametrize("mutation", ["empty", "whitespace", "control", "oversized"])
def test_subject_text_fence_refuses(mutation) -> None:
    policy = _workspace_policy()
    values = _values()
    if mutation == "empty":
        values["web"]["subject"] = ""
    elif mutation == "whitespace":
        values["web"]["subject"] = "\tsubject-web-opaque\n"
    elif mutation == "control":
        values["web"]["subject"] = "subject\x7fweb"
    elif mutation == "oversized":
        values["web"]["subject"] = "x" * 5000
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        compile_bindings(policy, values)
    assert exc.value.code.startswith("web_subject_") or exc.value.code == "subject_blank" or exc.value.code == "subject_control" or exc.value.code == "subject_oversized"


@pytest.mark.parametrize("mutation", ["empty", "oversized", "wrong_type"])
def test_receipt_fence_refuses(mutation) -> None:
    policy = _workspace_policy()
    values = _values()
    if mutation == "empty":
        values["web"]["permission_receipt"] = b""
    elif mutation == "oversized":
        values["web"]["permission_receipt"] = b"x" * (1 << 21)
    elif mutation == "wrong_type":
        values["web"]["permission_receipt"] = "not-bytes"
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        compile_bindings(policy, values)
    assert exc.value.code.startswith("web_receipt_") or exc.value.code == "receipt_empty" or "receipt" in exc.value.code


# ---------------------------------------------------------------------------
# Deterministic output formatting.
# ---------------------------------------------------------------------------


def test_serialize_document_is_sorted_indent2_utf8_trailing_lf() -> None:
    document = {"b": 1, "a": {"y": 2, "x": "é"}}
    payload = _serialize_document(document)
    text = payload.decode("utf-8")
    assert text.endswith("\n")
    assert "\n  " in text  # indent of 2 is present
    parsed = json.loads(text)
    assert parsed == document


def test_serialize_document_is_strict_no_nan() -> None:
    with pytest.raises((ValueError, TypeError)):
        _serialize_document({"x": float("nan")})


# ---------------------------------------------------------------------------
# Closed non-emitting parser.
# ---------------------------------------------------------------------------


def test_parse_argv_accepts_exact_six_args() -> None:
    policy, request, output = _parse_argv(
        ["--policy", "/p", "--request", "/r", "--output", "/o"],
    )
    assert policy == "/p"
    assert request == "/r"
    assert output == "/o"


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--policy"],
        ["--policy", "/p"],
        ["--policy", "/p", "--request"],
        ["--policy", "/p", "--request", "/r"],
        ["--policy", "/p", "--request", "/r", "--output"],
        ["--policy", "/p", "--request", "/r", "--output", "/o", "--help"],
        ["--help"],
        ["--policy", "/p", "--request", "/r", "--output", "/o", "extra"],
        ["--policy", "/p", "--output", "/o", "--request", "/r"],
    ],
)
def test_parse_argv_refuses_malformed(argv) -> None:
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        _parse_argv(argv)
    assert exc.value.code.startswith("argv_")


def test_parse_argv_refuses_none() -> None:
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        _parse_argv(None)
    assert exc.value.code == "argv_none"


# ---------------------------------------------------------------------------
# Authority-file fences (symlink, nonregular, nonroot, mode, oversize, JSON,
# replacement). Tests run as root-equivalent: mode is fixed, but ownership is
# enforced through descriptor fstat that reads the real st_uid from the
# fixture. Tests that require non-root ownership skip if running unprivileged.
# ---------------------------------------------------------------------------


def _require_root() -> None:
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        pytest.skip("requires real root for ownership enforcement")


def _can_chown() -> bool:
    try:
        os.chown("/tmp", 0, 0)
    except (PermissionError, OSError):
        return False
    return True


def _make_authority_files(tmp_path: Path) -> dict:
    work = tmp_path / "work"
    work.mkdir(mode=0o755)
    out_dir = tmp_path / "out"
    out_dir.mkdir(mode=0o755)
    policy_path = work / "policy.json"
    policy_path.write_text(json.dumps(_workspace_policy_value()))
    os.chmod(policy_path, 0o400)
    request_path = work / "request.json"
    client_id_path = _private_file(work, "client_id_web", WEB_CLIENT_ID.encode())
    subject_path = _private_file(work, "subject_web", WEB_SUBJECT.encode())
    receipt_path = _private_file(work, "receipt_web", WEB_RECEIPT)
    request_path.write_text(json.dumps({
        "schema": REQUEST_SCHEMA,
        "profiles": {
            "web": {
                "enabled": True,
                "client_id_file": str(client_id_path),
                "subject_file": str(subject_path),
                "permission_receipt_file": str(receipt_path),
            },
            "mac": {
                "enabled": False,
                "client_id_file": None,
                "subject_file": None,
                "permission_receipt_file": None,
            },
        },
    }))
    os.chmod(request_path, 0o400)
    return {
        "work": work,
        "out_dir": out_dir,
        "policy": policy_path,
        "request": request_path,
        "client_id": client_id_path,
        "subject": subject_path,
        "receipt": receipt_path,
        "output": out_dir / "bindings.json",
    }


def test_authority_file_symlink_refused(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    fixture = _make_authority_files(tmp_path)
    os.chmod(fixture["policy"], 0o644)
    fixture["policy"].unlink()
    real = tmp_path / "real_policy.json"
    real.write_text(json.dumps(_workspace_policy_value()))
    os.chmod(real, 0o400)
    fixture["policy"].symlink_to(real)
    rc = main([
        "--policy", str(fixture["policy"]),
        "--request", str(fixture["request"]),
        "--output", str(fixture["output"]),
    ])
    assert rc == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "workspace owner binding compiler refused\n"


def test_authority_file_nonregular_refused(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    fixture = _make_authority_files(tmp_path)
    os.chmod(fixture["policy"], 0o644)
    fixture["policy"].unlink()
    fixture["policy"].mkdir(mode=0o700)
    rc = main([
        "--policy", str(fixture["policy"]),
        "--request", str(fixture["request"]),
        "--output", str(fixture["output"]),
    ])
    assert rc == 1
    captured = capsys.readouterr()
    assert captured.err == "workspace owner binding compiler refused\n"


def test_authority_file_oversize_refused(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    fixture = _make_authority_files(tmp_path)
    os.chmod(fixture["policy"], 0o644)
    big = b"{" + b"x" * (1 << 21) + b"}"
    fixture["policy"].write_bytes(big)
    os.chmod(fixture["policy"], 0o400)
    rc = main([
        "--policy", str(fixture["policy"]),
        "--request", str(fixture["request"]),
        "--output", str(fixture["output"]),
    ])
    assert rc == 1
    assert "workspace owner binding compiler refused" in capsys.readouterr().err


def test_authority_file_invalid_json_refused(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    fixture = _make_authority_files(tmp_path)
    os.chmod(fixture["policy"], 0o644)
    fixture["policy"].write_bytes(b"{not-json")
    os.chmod(fixture["policy"], 0o400)
    rc = main([
        "--policy", str(fixture["policy"]),
        "--request", str(fixture["request"]),
        "--output", str(fixture["output"]),
    ])
    assert rc == 1
    assert "workspace owner binding compiler refused" in capsys.readouterr().err


def test_authority_file_unsafe_mode_refused(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    fixture = _make_authority_files(tmp_path)
    os.chmod(fixture["policy"], 0o644)
    rc = main([
        "--policy", str(fixture["policy"]),
        "--request", str(fixture["request"]),
        "--output", str(fixture["output"]),
    ])
    assert rc == 1
    assert "workspace owner binding compiler refused" in capsys.readouterr().err


@pytest.mark.parametrize(
    "mutation", ["symlink", "nonregular", "unsafe_mode", "oversize"],
)
def test_private_input_fences(
    tmp_path: Path, monkeypatch, capsys, mutation: str,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    fixture = _make_authority_files(tmp_path)
    target = fixture["client_id"]
    if mutation == "symlink":
        os.chmod(target, 0o644)
        replacement = tmp_path / "replacement"
        replacement.write_bytes(WEB_CLIENT_ID.encode())
        os.chmod(replacement, 0o400)
        target.unlink()
        target.symlink_to(replacement)
    elif mutation == "nonregular":
        os.chmod(target, 0o644)
        target.unlink()
        target.mkdir(mode=0o700)
    elif mutation == "unsafe_mode":
        os.chmod(target, 0o644)
    elif mutation == "oversize":
        os.chmod(target, 0o644)
        target.write_bytes(b"x" * 5000)
        os.chmod(target, 0o400)
    rc = main([
        "--policy", str(fixture["policy"]),
        "--request", str(fixture["request"]),
        "--output", str(fixture["output"]),
    ])
    assert rc == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "workspace owner binding compiler refused\n"


# ---------------------------------------------------------------------------
# Parser leakage under root and non-root.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--policy", "/p", "--request", "/r", "--output"],
        ["--policy", "/p", "--request", "/r"],
        ["--unknown", "/p"],
        ["--help"],
        ["--policy", "/p", "--request", "/r", "--output", "/o", "--help"],
        ["--policy", "/p", "--request", "/r", "--output", "/o", "extra"],
        ["--policy", "/p", "--output", "/o", "--request", "/r"],
    ],
)
def test_parser_refuses_malformed_as_root(argv, monkeypatch, capsys) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    rc = main(argv)
    assert rc == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    err = captured.err
    assert err == "workspace owner binding compiler refused\n"
    assert "Traceback" not in err
    # No path/value/program-name leakage.
    for forbidden in argv:
        if isinstance(forbidden, str) and forbidden.startswith("--"):
            continue
        if forbidden == "/p" or forbidden == "/r" or forbidden == "/o":
            assert forbidden not in err
    assert "workspace_owner_enrollment" not in err
    assert "usage" not in err.lower()


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--policy", "/p", "--request", "/r", "--output", "/o", "--help"],
        ["--unknown", "/p", "--request", "/r", "--output", "/o"],
        ["--policy", "/p", "--request", "/r", "--output", "/o", "leaked-path"],
    ],
)
def test_parser_refuses_malformed_as_non_root(argv, monkeypatch, capsys) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    rc = main(argv)
    assert rc == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "workspace owner binding compiler refused\n"
    assert "Traceback" not in captured.err
    for forbidden in argv:
        if forbidden == "/p" or forbidden == "/r" or forbidden == "/o" or forbidden == "leaked-path":
            assert forbidden not in captured.err
    assert "workspace_owner_enrollment" not in captured.err


def test_parser_root_then_non_root_message_identical(monkeypatch, capsys) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    main([])
    err_root = capsys.readouterr().err
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    main([])
    err_user = capsys.readouterr().err
    assert err_root == err_user


# ---------------------------------------------------------------------------
# CLI: not-root, non-absolute, existing output.
# ---------------------------------------------------------------------------


def test_cli_refuses_when_not_root(monkeypatch, capsys) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    rc = main(["--policy", "/p", "--request", "/r", "--output", "/o"])
    assert rc == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "workspace owner binding compiler refused\n"


def test_cli_refuses_non_absolute_output(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    rc = main([
        "--policy", str(tmp_path / "policy.json"),
        "--request", str(tmp_path / "request.json"),
        "--output", "relative/out.json",
    ])
    assert rc == 1
    assert capsys.readouterr().err == "workspace owner binding compiler refused\n"


def test_cli_refuses_existing_output(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    fixture = _make_authority_files(tmp_path)
    fixture["output"].write_text("pre-existing-content")
    os.chmod(fixture["output"], 0o400)
    rc = main([
        "--policy", str(fixture["policy"]),
        "--request", str(fixture["request"]),
        "--output", str(fixture["output"]),
    ])
    assert rc == 1
    assert capsys.readouterr().out == ""
    assert fixture["output"].read_text() == "pre-existing-content"


# ---------------------------------------------------------------------------
# CLI happy path: receipt shape, raw identities absent, exact bytes.
# ---------------------------------------------------------------------------


def test_cli_happy_path_receipt_and_exact_output_bytes(
    monkeypatch, tmp_path, capsys,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    fixture = _make_authority_files(tmp_path)
    rc = main([
        "--policy", str(fixture["policy"]),
        "--request", str(fixture["request"]),
        "--output", str(fixture["output"]),
    ])
    if rc != 0:
        raise AssertionError(f"main returned {rc}, stderr={capsys.readouterr().err}")
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert captured.err == ""
    receipt = json.loads(captured.out.strip())
    assert set(receipt) == {
        "schema", "status", "output_sha256", "enabled_profiles", "output_path",
    }
    assert receipt["schema"] == RECEIPT_SCHEMA
    assert receipt["status"] == "compiled"
    assert receipt["enabled_profiles"] == ["web"]
    assert receipt["output_path"] == str(fixture["output"])
    assert len(receipt["output_sha256"]) == 64
    # Raw identities must not appear in stdout.
    for forbidden in (WEB_CLIENT_ID, WEB_SUBJECT, MAC_CLIENT_ID, MAC_SUBJECT):
        assert forbidden not in captured.out

    document = json.loads(fixture["output"].read_text())
    assert document["schema"] == BINDINGS_SCHEMA
    assert document["profiles"]["web"]["enabled"] is True
    assert document["profiles"]["mac"]["enabled"] is False
    for forbidden in (WEB_CLIENT_ID, WEB_SUBJECT):
        assert forbidden not in fixture["output"].read_text()


def test_cli_receipt_emission_failure_refuses_without_traceback(
    monkeypatch, tmp_path, capsys,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    fixture = _make_authority_files(tmp_path)

    def fail_receipt(_receipt):
        raise OSError("synthetic stdout failure")

    monkeypatch.setattr(compiler_module, "_emit_receipt", fail_receipt)
    rc = main([
        "--policy", str(fixture["policy"]),
        "--request", str(fixture["request"]),
        "--output", str(fixture["output"]),
    ])
    assert rc == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "workspace owner binding compiler refused\n"
    assert "Traceback" not in captured.err
    assert fixture["output"].exists()


def test_output_bytes_are_sorted_indent2_utf8_trailing_lf(
    monkeypatch, tmp_path,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    fixture = _make_authority_files(tmp_path)
    rc = main([
        "--policy", str(fixture["policy"]),
        "--request", str(fixture["request"]),
        "--output", str(fixture["output"]),
    ])
    assert rc == 0
    raw = fixture["output"].read_bytes()
    assert raw.endswith(b"\n")
    text = raw.decode("utf-8")
    # indent-2 is present
    assert "\n  " in text
    parsed = json.loads(text)
    expected = json.dumps(
        parsed, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False,
    ) + "\n"
    assert raw == expected.encode("utf-8")


def test_receipt_bytes_are_compact_sorted_utf8_trailing_lf(
    monkeypatch, tmp_path, capsys,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    fixture = _make_authority_files(tmp_path)
    rc = main([
        "--policy", str(fixture["policy"]),
        "--request", str(fixture["request"]),
        "--output", str(fixture["output"]),
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.out.endswith("\n")
    expected = json.dumps(
        json.loads(captured.out.strip()),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    assert captured.out == expected


def test_output_is_root_owned_mode_0400_regular_one_link(
    monkeypatch, tmp_path,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    fixture = _make_authority_files(tmp_path)
    rc = main([
        "--policy", str(fixture["policy"]),
        "--request", str(fixture["request"]),
        "--output", str(fixture["output"]),
    ])
    assert rc == 0
    info = os.lstat(fixture["output"])
    assert info.st_uid == 0
    assert stat.S_ISREG(info.st_mode)
    assert stat.S_IMODE(info.st_mode) == 0o400
    assert info.st_nlink == 1


# ---------------------------------------------------------------------------
# Post-create failure injection: own-output cleanup, no parent outage.
# ---------------------------------------------------------------------------


def test_write_dance_preserves_entry_on_short_write(
    monkeypatch, tmp_path,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    out_dir = tmp_path / "out"
    out_dir.mkdir(mode=0o700)

    def short_write(fd, data):
        if len(data) > 1:
            raise OSError("simulated short write")
        return os.write(fd.real_fd if hasattr(fd, "real_fd") else fd, data)

    # Direct write injection: monkeypatch os.write.
    real_write = os.write

    def broken_write(fd, data):
        if len(data) > 1:
            raise OSError("simulated short write")
        return real_write(fd, data)

    monkeypatch.setattr(os, "write", broken_write)
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        write_binding_document(str(out_dir / "out.json"), b"hello-binding-document")
    assert exc.value.code == "short_write"
    assert (out_dir / "out.json").exists()


def test_write_dance_preserves_entry_on_readback_failure(
    monkeypatch, tmp_path,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    out_dir = tmp_path / "out"
    out_dir.mkdir(mode=0o700)
    target = out_dir / "out.json"

    real_open = os.open
    real_basename = target.name

    def is_readonly(flags: int) -> bool:
        return (flags & (os.O_WRONLY | os.O_RDWR)) == 0 and not (flags & os.O_CREAT)

    def corrupt_open(path, flags, *args, **kwargs):
        if (
            isinstance(path, str)
            and os.path.basename(path) == real_basename
            and is_readonly(flags)
            and kwargs.get("dir_fd") is not None
        ):
            raise OSError("readback blocked by test injection")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", corrupt_open)
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        write_binding_document(str(target), b"correct-payload")
    assert exc.value.code == "readback_open"
    assert target.exists()


def test_write_dance_preserves_entry_on_fchmod_failure(
    monkeypatch, tmp_path,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    out_dir = tmp_path / "out"
    out_dir.mkdir(mode=0o700)
    real_fchmod = os.fchmod

    def broken_fchmod(fd, mode):
        if mode == 0o400:
            raise OSError("simulated fchmod failure")
        return real_fchmod(fd, mode)

    monkeypatch.setattr(os, "fchmod", broken_fchmod)
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        write_binding_document(str(out_dir / "out.json"), b"hello-payload")
    assert exc.value.code == "output_fchmod"
    assert (out_dir / "out.json").exists()


def test_write_dance_preserves_entry_on_fsync_failure(
    monkeypatch, tmp_path,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    out_dir = tmp_path / "out"
    out_dir.mkdir(mode=0o700)
    real_fsync = os.fsync

    def broken_fsync(fd):
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(os, "fsync", broken_fsync)
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        write_binding_document(str(out_dir / "out.json"), b"hello-payload")
    assert exc.value.code == "output_fsync"
    assert (out_dir / "out.json").exists()


def test_write_dance_preserves_entry_on_parent_fsync_failure(
    monkeypatch, tmp_path,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    out_dir = tmp_path / "out"
    out_dir.mkdir(mode=0o700)
    real_fsync = os.fsync
    state = {"file_synced": False}

    def broken_fsync(fd):
        # Let the file fsync pass; break parent fsync.
        try:
            info = os.fstat(fd)
        except OSError:
            return real_fsync(fd)
        if stat.S_ISDIR(info.st_mode):
            raise OSError("simulated parent fsync failure")
        state["file_synced"] = True
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", broken_fsync)
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        write_binding_document(str(out_dir / "out.json"), b"hello-payload")
    assert exc.value.code == "parent_fsync"
    assert (out_dir / "out.json").exists()
    assert state["file_synced"]


def test_created_output_fstat_failure_refuses_and_preserves_entry(
    monkeypatch, tmp_path,
) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir(mode=0o700)
    target = out_dir / "out.json"
    real_open = os.open
    real_fstat = os.fstat
    created_fd = {"value": None}

    def tracking_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if flags & os.O_CREAT:
            created_fd["value"] = fd
        return fd

    def failing_fstat(fd):
        if fd == created_fd["value"]:
            raise OSError("synthetic created output fstat failure")
        return real_fstat(fd)

    monkeypatch.setattr(os, "open", tracking_open)
    monkeypatch.setattr(os, "fstat", failing_fstat)
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        write_binding_document(str(target), b"payload\n")
    assert exc.value.code == "output_create"
    assert target.exists()


def test_output_writer_close_failure_is_not_reported_as_success(
    monkeypatch, tmp_path,
) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir(mode=0o700)
    target = out_dir / "out.json"
    real_open = os.open
    real_close = os.close
    writer_fd = {"value": None}
    failed = {"value": False}

    def tracking_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if flags & os.O_CREAT:
            writer_fd["value"] = fd
        return fd

    def failing_close(fd):
        if fd == writer_fd["value"] and not failed["value"]:
            failed["value"] = True
            raise OSError("synthetic writer close failure")
        return real_close(fd)

    monkeypatch.setattr(os, "open", tracking_open)
    monkeypatch.setattr(os, "close", failing_close)
    try:
        with pytest.raises(WorkspaceOwnerCompilerError) as exc:
            write_binding_document(str(target), b"payload\n")
        assert exc.value.code == "output_close"
        assert failed["value"] is True
        assert target.exists()
    finally:
        if writer_fd["value"] is not None:
            try:
                real_close(writer_fd["value"])
            except OSError:
                pass


def test_owned_parent_close_failure_is_material(
    monkeypatch, tmp_path,
) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir(mode=0o700)
    target = out_dir / "out.json"
    real_open = os.open
    real_close = os.close
    parent_fd = {"value": None}
    failed = {"value": False}

    def tracking_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if path == str(out_dir) and flags & getattr(os, "O_DIRECTORY", 0):
            parent_fd["value"] = fd
        return fd

    def failing_close(fd):
        if fd == parent_fd["value"] and not failed["value"]:
            failed["value"] = True
            raise OSError("synthetic parent close failure")
        return real_close(fd)

    monkeypatch.setattr(os, "open", tracking_open)
    monkeypatch.setattr(os, "close", failing_close)
    try:
        with pytest.raises(WorkspaceOwnerCompilerError) as exc:
            write_binding_document(str(target), b"payload\n")
        assert exc.value.code == "parent_close"
        assert failed["value"] is True
        assert target.exists()
    finally:
        if parent_fd["value"] is not None:
            try:
                real_close(parent_fd["value"])
            except OSError:
                pass


def test_readback_close_failure_refuses_and_closes_writer(
    monkeypatch, tmp_path,
) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir(mode=0o700)
    target = out_dir / "out.json"
    real_open = os.open
    real_close = os.close
    read_fd = {"value": None}
    writer_fd = {"value": None}
    failed = {"value": False}

    def tracking_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if flags & os.O_CREAT:
            writer_fd["value"] = fd
        elif (
            path == target.name
            and kwargs.get("dir_fd") is not None
            and (flags & os.O_ACCMODE) == os.O_RDONLY
        ):
            read_fd["value"] = fd
        return fd

    def failing_close(fd):
        if fd == read_fd["value"] and not failed["value"]:
            failed["value"] = True
            raise OSError("synthetic readback close failure")
        return real_close(fd)

    monkeypatch.setattr(os, "open", tracking_open)
    monkeypatch.setattr(os, "close", failing_close)
    try:
        with pytest.raises(WorkspaceOwnerCompilerError) as exc:
            write_binding_document(str(target), b"payload\n")
        assert exc.value.code == "readback_close"
        assert failed["value"] is True
        with pytest.raises(OSError):
            os.fstat(writer_fd["value"])
        assert target.exists()
    finally:
        if read_fd["value"] is not None:
            try:
                real_close(read_fd["value"])
            except OSError:
                pass


def test_bounded_input_read_failure_closes_descriptor(
    monkeypatch, tmp_path,
) -> None:
    target = tmp_path / "private"
    target.write_bytes(b"value")
    os.chmod(target, 0o400)
    real_open = os.open
    real_read = os.read
    opened_fd = {"value": None}

    def tracking_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if path == str(target):
            opened_fd["value"] = fd
        return fd

    def failing_read(fd, size):
        if fd == opened_fd["value"]:
            raise OSError("synthetic bounded read failure")
        return real_read(fd, size)

    monkeypatch.setattr(os, "open", tracking_open)
    monkeypatch.setattr(os, "read", failing_read)
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        _open_private_fd(str(target), label="private", maximum=64)
    assert exc.value.code == "private_unreadable"
    with pytest.raises(OSError):
        os.fstat(opened_fd["value"])


def test_private_input_close_failure_is_material(
    monkeypatch, tmp_path,
) -> None:
    target = tmp_path / "private"
    target.write_bytes(b"value")
    os.chmod(target, 0o400)
    real_open = os.open
    real_close = os.close
    opened_fd = {"value": None}
    failed = {"value": False}

    def tracking_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if path == str(target):
            opened_fd["value"] = fd
        return fd

    def failing_close(fd):
        if fd == opened_fd["value"] and not failed["value"]:
            failed["value"] = True
            raise OSError("synthetic private close failure")
        return real_close(fd)

    monkeypatch.setattr(os, "open", tracking_open)
    monkeypatch.setattr(os, "close", failing_close)
    try:
        with pytest.raises(WorkspaceOwnerCompilerError) as exc:
            _read_text_private(str(target), label="private")
        assert exc.value.code == "private_input_close"
        assert failed["value"] is True
    finally:
        if opened_fd["value"] is not None:
            try:
                real_close(opened_fd["value"])
            except OSError:
                pass


def test_foreign_swap_during_abort_is_preserved(
    monkeypatch, tmp_path,
) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir(mode=0o700)
    target = out_dir / "out.json"
    foreign = b"foreign-replacement"
    real_write = os.write
    real_open = os.open
    state = {"swapped": False}

    def swap_then_fail(fd, data):
        if not state["swapped"]:
            state["swapped"] = True
            os.unlink(target)
            foreign_fd = real_open(
                str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400,
            )
            try:
                real_write(foreign_fd, foreign)
            finally:
                os.close(foreign_fd)
            raise OSError("synthetic write failure after foreign swap")
        return real_write(fd, data)

    monkeypatch.setattr(os, "write", swap_then_fail)
    with pytest.raises(WorkspaceOwnerCompilerError):
        write_binding_document(str(target), b"owned-payload")
    assert state["swapped"] is True
    assert target.read_bytes() == foreign


def test_write_dance_refuses_existing_output(
    monkeypatch, tmp_path,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    out_dir = tmp_path / "out"
    out_dir.mkdir(mode=0o700)
    pre = out_dir / "out.json"
    pre.write_bytes(b"do-not-replace")
    os.chmod(pre, 0o400)
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        write_binding_document(str(pre), b"new-content")
    assert exc.value.code == "output_create"
    assert pre.read_bytes() == b"do-not-replace"


def test_write_dance_writes_0400_and_verifies(
    monkeypatch, tmp_path,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    out_dir = tmp_path / "out"
    out_dir.mkdir(mode=0o700)
    payload = b"hello-binding-document\n"
    ino = write_binding_document(str(out_dir / "out.json"), payload)
    info = os.lstat(out_dir / "out.json")
    assert stat.S_ISREG(info.st_mode)
    assert info.st_uid == 0
    assert stat.S_IMODE(info.st_mode) == 0o400
    assert info.st_size == len(payload)
    assert info.st_ino == ino
    assert info.st_nlink == 1
    assert (out_dir / "out.json").read_bytes() == payload


# ---------------------------------------------------------------------------
# Output parent descriptor-binding + identity fences.
# ---------------------------------------------------------------------------


def test_open_parent_fd_rejects_symlink(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    real = tmp_path / "real_dir"
    real.mkdir(mode=0o700)
    link = tmp_path / "linked_dir"
    link.symlink_to(real)
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        _open_parent_fd(str(link))
    assert exc.value.code in {"parent_symlink", "parent_open"}


def test_open_parent_fd_rejects_nonroot(
    monkeypatch, tmp_path,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    # Override the autouse root-simulating fixture so fstat reports real uid.
    monkeypatch.setattr(os, "fstat", _REAL_FSTAT)
    if _can_chown():
        try:
            os.chown(tmp_path, 1000, -1)
        except (PermissionError, OSError):
            pass
        try:
            with pytest.raises(WorkspaceOwnerCompilerError) as exc:
                _open_parent_fd(str(tmp_path))
            assert exc.value.code == "parent_owner"
        finally:
            try:
                os.chown(tmp_path, 0, -1)
            except (PermissionError, OSError):
                pass
    else:
        pytest.skip("cannot chown")


def test_open_parent_fd_rejects_group_writable(
    monkeypatch, tmp_path,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    os.chmod(tmp_path, 0o770)
    try:
        with pytest.raises(WorkspaceOwnerCompilerError) as exc:
            _open_parent_fd(str(tmp_path))
        assert exc.value.code == "parent_writable"
    finally:
        os.chmod(tmp_path, 0o700)


def test_exclusive_create_refuses_existing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    target = tmp_path / "pre.json"
    target.write_bytes(b"hi")
    os.chmod(target, 0o400)
    parent_fd = os.open(str(tmp_path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(WorkspaceOwnerCompilerError) as exc:
            _exclusive_create_in_parent(parent_fd, "pre.json")
        assert exc.value.code == "output_create"
    finally:
        os.close(parent_fd)


# ---------------------------------------------------------------------------
# Output readback rejection: content mismatch.
# ---------------------------------------------------------------------------


def test_write_dance_refuses_content_mismatch(
    monkeypatch, tmp_path,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    out_dir = tmp_path / "out"
    out_dir.mkdir(mode=0o700)
    real_open = os.open
    target_name = "out.json"
    state = {"swapped": False}

    def is_readonly(flags: int) -> bool:
        return (flags & (os.O_WRONLY | os.O_RDWR)) == 0 and not (flags & os.O_CREAT)

    def swap_open(path, flags, *args, **kwargs):
        if (
            not state["swapped"]
            and isinstance(path, str)
            and path == target_name
            and is_readonly(flags)
            and kwargs.get("dir_fd") is not None
        ):
            state["swapped"] = True
            parent_fd = kwargs["dir_fd"]
            try:
                os.unlink(target_name, dir_fd=parent_fd)
            except OSError:
                pass
            fd = real_open(
                target_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o400,
                dir_fd=parent_fd,
            )
            os.write(fd, b"foreign-bytes-bytes")
            os.close(fd)
            return real_open(
                target_name,
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0),
                dir_fd=parent_fd,
            )
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", swap_open)
    with pytest.raises(WorkspaceOwnerCompilerError) as exc:
        write_binding_document(str(out_dir / target_name), b"correct-payload")
    assert exc.value.code in {
        "readback_identity", "readback_mismatch", "output_create",
    }
    assert (out_dir / target_name).exists()


# ---------------------------------------------------------------------------
# Descriptor-bound private-input replacement.
# ---------------------------------------------------------------------------


def test_private_input_replacement_after_open_uses_original_descriptor(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    fixture = _make_authority_files(tmp_path)
    real_target = fixture["client_id"]
    replacement_payload = b"replacement-client-raw"
    # After the first open, replace the file with different bytes; the
    # descriptor should not see those bytes.
    real_open = os.open
    real_fstat = os.fstat
    state = {"swapped": False}
    target_fd = {"value": None}

    def tracking_open(path, flags, *args, **kwargs):
        result = real_open(path, flags, *args, **kwargs)
        if (
            isinstance(path, str)
            and path == str(real_target)
            and (flags & os.O_ACCMODE) == os.O_RDONLY
            and not (flags & os.O_CREAT)
        ):
            target_fd["value"] = result
        return result

    def swap_after_fstat(fd):
        info = real_fstat(fd)
        if fd == target_fd["value"] and not state["swapped"]:
            state["swapped"] = True
            os.unlink(real_target)
            replacement_fd = real_open(
                str(real_target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400,
            )
            try:
                os.write(replacement_fd, replacement_payload)
            finally:
                os.close(replacement_fd)
        return info

    monkeypatch.setattr(os, "open", tracking_open)
    monkeypatch.setattr(os, "fstat", swap_after_fstat)
    rc = main([
        "--policy", str(fixture["policy"]),
        "--request", str(fixture["request"]),
        "--output", str(fixture["output"]),
    ])
    assert rc == 0
    assert state["swapped"] is True
    captured = capsys.readouterr()
    document = json.loads(fixture["output"].read_text())
    client_ref = document["profiles"]["web"]["binding"]["client_ref"]
    expected = hashlib.sha256(
        (WORKSPACE_ISSUER + "\nclient\n" + WEB_CLIENT_ID).encode(),
    ).hexdigest()
    replacement_ref = hashlib.sha256(
        (WORKSPACE_ISSUER + "\nclient\n" + replacement_payload.decode()).encode(),
    ).hexdigest()
    assert client_ref == expected
    assert client_ref != replacement_ref
    assert replacement_payload.decode() not in captured.out
    assert replacement_payload.decode() not in fixture["output"].read_text()


# ---------------------------------------------------------------------------
# Output parent descriptor replacement.
# ---------------------------------------------------------------------------


def test_output_parent_replacement_refused(
    monkeypatch, tmp_path,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    out_dir = tmp_path / "out"
    out_dir.mkdir(mode=0o700)

    # Validate the parent descriptor first.
    parent_fd, _ = _open_parent_fd(str(out_dir))

    # Race: rename the original directory and place a foreign replacement
    # at the same absolute path.
    new_dir = tmp_path / "out_new"
    out_dir.rename(new_dir)
    foreign = tmp_path / "out"
    foreign.mkdir(mode=0o700)

    # Writing via the captured parent_fd must target the original inode
    # (now at new_dir), never the foreign replacement at the original path.
    try:
        ino = write_binding_document(
            str(out_dir / "bindings.json"), b"hello-binding-document\n",
            parent_fd=parent_fd,
        )
    finally:
        os.close(parent_fd)
    assert ino > 0
    assert new_dir.joinpath("bindings.json").exists()
    assert not foreign.joinpath("bindings.json").exists()


# ---------------------------------------------------------------------------
# Prohibition audit on the module surface.
# ---------------------------------------------------------------------------


PROHIBITED_IMPORT_NAMES = {
    "control_plane",
    "subprocess",
    "launchctl",
    "keyring",
    "keychain",
    "requests",
    "urllib3",
    "httpx",
    "http",
    "http.client",
    "aiohttp",
    "mcp",
    "OAuth",
    "Runtime",
}


def test_module_has_no_prohibited_imports() -> None:
    source_path = (
        Path(__file__).resolve().parent.parent
        / "ops" / "executive_os" / "workspace_owner_enrollment.py"
    )
    tree = ast.parse(source_path.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    leaked = imported & PROHIBITED_IMPORT_NAMES
    assert not leaked, f"prohibited imports: {sorted(leaked)}"


def test_module_has_no_prohibited_runtime_calls() -> None:
    source_path = (
        Path(__file__).resolve().parent.parent
        / "ops" / "executive_os" / "workspace_owner_enrollment.py"
    )
    tree = ast.parse(source_path.read_text())
    prohibited_roots = {
        "subprocess", "launchctl", "keyring", "keychain", "requests",
        "urllib", "socket", "httpx", "http", "mcp", "Runtime",
        "control_plane",
    }
    leaked: list[str] = []

    def _root_name(node: ast.AST) -> str | None:
        current = node
        while isinstance(current, ast.Attribute):
            current = current.value
        if isinstance(current, ast.Name):
            return current.id
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            root = _root_name(node)
            if root in prohibited_roots:
                leaked.append(f"{root}.{node.attr}")
        elif isinstance(node, ast.Call):
            func = node.func
            root = _root_name(func) if isinstance(func, ast.Attribute) else (
                func.id if isinstance(func, ast.Name) else None,
            )
            if root in prohibited_roots:
                leaked.append(f"{root}()")
    assert not leaked, f"prohibited effects: {leaked}"


def test_compile_is_canonical_deterministic() -> None:
    policy = _workspace_policy()
    document = compile_bindings(policy, _values(web_enabled=True, mac_enabled=True))
    assert json.loads(canonical(document).decode("utf-8")) == document
