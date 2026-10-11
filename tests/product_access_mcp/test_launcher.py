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
    assert packet["tools"] == ["product_diagnostics", "product_market_pulse"]
    assert packet["scope"] == "product.observe"
    assert packet["schema_sha256"] == (
        "62b935d4f89f6b377dc51eb5968e236fdd08ce03c4008be62377b83c168aebc6"
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
