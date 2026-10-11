"""Product MCP loopback launcher: approved-owner composition, never public network."""
from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

import pytest


def launcher():
    from scripts import mastermind_product_access_app
    return mastermind_product_access_app


def test_describe_is_inert_and_has_pinned_public_tools(capsys, monkeypatch):
    unit = launcher()
    monkeypatch.setattr(unit, "_load_policy", lambda *_: pytest.fail("policy read"))
    assert unit.main(["--describe", "--host", "0.0.0.0", "--port", "1"]) == 0
    packet = json.loads(capsys.readouterr().out)
    assert packet["schema"] == "mastermind.product_mcp_launcher_descriptor.v1"
    assert packet["capability_state"] == "BUILT_NOT_PROVEN"
    assert packet["server_version"] == "1.2.0"
    assert packet["tools"] == ["product_diagnostics", "product_market_pulse"]
    assert packet["scope"] == "product.observe"
    assert packet["schema_sha256"] == (
        "3f7d8141b1af5a56c6b7f6b480e1f5a2fb052a6d42e0710a7e7f1d276db614db"
    )


@pytest.mark.parametrize("args,reason", [
    ([], "PRODUCT_PORT_REQUIRED"),
    (["--port", "0"], "PRODUCT_PORT_REQUIRED"),
    (["--port", "65536"], "PRODUCT_PORT_REQUIRED"),
    (["--port", "8767", "--host", "0.0.0.0"], "PRODUCT_LOOPBACK_REQUIRED"),
    (["--port", "8767", "--host", "product.example"], "PRODUCT_LOOPBACK_REQUIRED"),
    (["--port", "8767"], "PRODUCT_OWNER_POLICY_AND_AUDIT_REQUIRED"),
])
def test_invalid_launch_coordinates_refuse_before_reading_policy(monkeypatch, args, reason):
    unit = launcher()
    monkeypatch.setattr(unit, "_load_policy", lambda *_: pytest.fail("unauthorized policy read"))
    with pytest.raises(SystemExit, match=reason):
        unit.main(args)


def sample_policy():
    from .test_deployment import policy
    return dataclasses.asdict(policy())


def make_policy(tmp_path: Path, payload=None) -> Path:
    file = tmp_path / "product-policy.json"
    file.write_text(json.dumps(payload if payload is not None else sample_policy()))
    file.chmod(0o600)
    return file


def test_policy_file_requires_canonical_nofollow_and_0600(tmp_path):
    unit = launcher()
    good = make_policy(tmp_path)
    assert unit._load_policy(str(good)).required_scopes == ("product.observe",)

    good.chmod(0o644)
    with pytest.raises(ValueError, match="POLICY_FILE_REFUSED"):
        unit._load_policy(str(good))
    good.chmod(0o600)

    linked = tmp_path / "linked-policy.json"
    linked.symlink_to(good)
    with pytest.raises(ValueError, match="OWNER_PATH_REFUSED"):
        unit._load_policy(str(linked))

    with pytest.raises(ValueError, match="OWNER_PATH_REFUSED"):
        unit._load_policy(str(good.relative_to(tmp_path)))


def test_policy_duplicate_keys_and_wrong_scope_refuse(tmp_path):
    unit = launcher()
    p = make_policy(tmp_path)
    p.write_text('{"schema":"duplicate","schema":"duplicate"}')
    with pytest.raises(ValueError, match="DUPLICATE_POLICY_FIELD"):
        unit._load_policy(str(p))
    altered = sample_policy()
    altered["required_scopes"] = ["workbench.action"]
    make_policy(tmp_path, altered)
    with pytest.raises(ValueError, match="PRODUCT_SCOPE_REQUIRED"):
        unit._load_policy(str(p))


def test_real_composition_binds_exact_resource_authority_and_borrowed_audit(
    tmp_path, monkeypatch,
):
    unit = launcher()
    import uvicorn

    policy_file = make_policy(tmp_path)
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir(mode=0o700)
    captured = {}

    def intercepted(app, **options):
        captured["app"] = app
        captured["options"] = options
        assert list(app.routes)

    monkeypatch.setattr(uvicorn, "run", intercepted)
    assert unit.main([
        "--policy-file", str(policy_file),
        "--audit-directory", str(audit_dir),
        "--port", "8767",
        "--allowed-origin", "https://product.example",
    ]) == 0

    assert captured["options"]["host"] == "127.0.0.1"
    assert captured["options"]["port"] == 8767
    assert captured["options"]["proxy_headers"] is False
    assert captured["options"]["limit_concurrency"] == 16
    assert (audit_dir / "auth-audit.jsonl").exists() or len(list(audit_dir.iterdir())) == 1


def test_invalid_origin_refuses_and_releases_audit_owner(tmp_path, monkeypatch):
    unit = launcher()
    import uvicorn
    p = make_policy(tmp_path)
    directory = tmp_path / "audit"
    directory.mkdir(mode=0o700)
    monkeypatch.setattr(uvicorn, "run", lambda *_args, **_kwargs: pytest.fail("listener"))
    with pytest.raises(ValueError, match="TRANSPORT_POLICY_INVALID"):
        unit.main([
            "--policy-file", str(p), "--audit-directory", str(directory),
            "--port", "8767", "--allowed-origin", "https://*.example",
        ])
    assert list(directory.iterdir()) == []


def test_no_service_acquisition_without_explicit_audit_owner(tmp_path, monkeypatch):
    unit = launcher()
    import uvicorn
    p = make_policy(tmp_path)
    monkeypatch.setattr(uvicorn, "run", lambda *_args, **_kwargs: pytest.fail("listener"))
    with pytest.raises(SystemExit):
        unit.main([
            "--policy-file", str(p), "--audit-directory", str(tmp_path / "missing"),
            "--port", "8767",
        ])


def test_policy_refuses_extended_acl_on_file(tmp_path, monkeypatch):
    """Darwin ACL entries are independent of visible 0600 mode bits."""
    unit = launcher()
    candidate = make_policy(tmp_path)
    seen = []

    def acl_reader(path, *, expected_identity, descriptor):
        seen.append(Path(path))
        return Path(path) == candidate

    monkeypatch.setattr(unit, "has_macos_acl", acl_reader)
    with pytest.raises(ValueError, match="POLICY_FILE_REFUSED"):
        unit._load_policy(str(candidate))
    assert candidate in seen


def test_policy_refuses_extended_acl_on_ancestor(tmp_path, monkeypatch):
    unit = launcher()
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    candidate = make_policy(private)

    def acl_reader(path, *, expected_identity, descriptor):
        return Path(path) == private

    monkeypatch.setattr(unit, "has_macos_acl", acl_reader)
    with pytest.raises(ValueError, match="POLICY_DIRECTORY_REFUSED"):
        unit._load_policy(str(candidate))


def test_policy_refuses_untrusted_writable_parent(tmp_path):
    unit = launcher()
    private = tmp_path / "unsafe-parent"
    private.mkdir(mode=0o700)
    candidate = make_policy(private)
    private.chmod(0o777)
    try:
        with pytest.raises(ValueError, match="POLICY_DIRECTORY_REFUSED"):
            unit._load_policy(str(candidate))
    finally:
        private.chmod(0o700)


def test_verified_directory_walk_rejects_ancestor_symlink_swap(tmp_path):
    unit = launcher()
    parent = tmp_path / "policy-parent"
    parent.mkdir(mode=0o700)
    candidate = make_policy(parent)
    canonical = unit._canonical_path(str(candidate))
    renamed = tmp_path / "original-parent"
    parent.rename(renamed)
    alternate = tmp_path / "alternate-parent"
    alternate.mkdir(mode=0o700)
    parent.symlink_to(alternate, target_is_directory=True)
    # This simulates the change *after* the original canonical-path check.
    with pytest.raises((OSError, ValueError)):
        unit._open_verified_directory(canonical.parent)


def test_policy_refuses_same_length_in_place_rewrite(tmp_path, monkeypatch):
    unit = launcher()
    candidate = make_policy(tmp_path)
    original_read = unit._read_policy_fd

    def racing_read(fd):
        raw = original_read(fd)
        altered = raw.replace(b'"policy_id"', b'"policy_iD"')
        assert altered != raw and len(altered) == len(raw)
        with candidate.open("r+b") as stream:
            stream.write(altered)
            stream.flush()
            os.fsync(stream.fileno())
        # A deliberate metadata epoch change makes the race deterministic
        # on filesystems whose timestamp resolution is coarser than one write.
        prior = candidate.stat()
        os.utime(candidate, ns=(prior.st_atime_ns, prior.st_mtime_ns + 2_000_000_000))
        return raw

    monkeypatch.setattr(unit, "_read_policy_fd", racing_read)
    with pytest.raises(ValueError, match="POLICY_FILE_CHANGED"):
        unit._load_policy(str(candidate))


def test_policy_refuses_post_read_named_file_replacement(tmp_path, monkeypatch):
    unit = launcher()
    candidate = make_policy(tmp_path)
    original_read = unit._read_policy_fd

    def racing_read(fd):
        raw = original_read(fd)
        replacement = tmp_path / "other-policy.json"
        replacement.write_bytes(raw)
        replacement.chmod(0o600)
        replacement.replace(candidate)
        return raw

    monkeypatch.setattr(unit, "_read_policy_fd", racing_read)
    with pytest.raises(ValueError, match="POLICY_FILE_CHANGED"):
        unit._load_policy(str(candidate))


def test_audit_directory_acl_refuses_before_durable_acquisition(tmp_path, monkeypatch):
    unit = launcher()
    import uvicorn

    candidate = make_policy(tmp_path)
    audit = tmp_path / "audit"
    audit.mkdir(mode=0o700)

    def acl_reader(path, *, expected_identity, descriptor):
        return Path(path) == audit

    monkeypatch.setattr(unit, "has_macos_acl", acl_reader)
    monkeypatch.setattr(unit.DurableAuthAuditSink, "open",
                        lambda *_args, **_kwargs: pytest.fail("audit owner acquired"))
    monkeypatch.setattr(uvicorn, "run",
                        lambda *_args, **_kwargs: pytest.fail("listener started"))
    with pytest.raises(SystemExit, match="PRODUCT_AUDIT_DIRECTORY_REFUSED"):
        unit.main([
            "--policy-file", str(candidate),
            "--audit-directory", str(audit),
            "--port", "8767",
        ])
    assert list(audit.iterdir()) == []


def test_borrowed_audit_owner_is_closed_when_uvicorn_fails(tmp_path, monkeypatch):
    unit = launcher()
    import uvicorn

    candidate = make_policy(tmp_path)
    audit = tmp_path / "audit"
    audit.mkdir(mode=0o700)
    closed = []
    real_close = unit.DurableAuthAuditSink.close

    def observed_close(self):
        closed.append(True)
        return real_close(self)

    monkeypatch.setattr(unit.DurableAuthAuditSink, "close", observed_close)

    def fail_listener(_app, **_options):
        raise RuntimeError("SYNTHETIC_LISTENER_FAILURE")

    monkeypatch.setattr(uvicorn, "run", fail_listener)
    with pytest.raises(RuntimeError, match="SYNTHETIC_LISTENER_FAILURE"):
        unit.main([
            "--policy-file", str(candidate),
            "--audit-directory", str(audit),
            "--port", "8767",
        ])
    assert closed == [True]
