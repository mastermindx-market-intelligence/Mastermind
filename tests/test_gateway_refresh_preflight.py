from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops.executive_os import gateway_refresh_preflight as preflight

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40


def _config() -> dict:
    policies = json.loads(
        (ROOT / "config/business_mcp/executive_policy.example.json").read_text(
            encoding="utf-8"
        )
    )
    return {
        "schema": "mastermind.executive_mcp_install.v1",
        "release_sha": SHA,
        "service_uid": 458,
        "ceo_ingress_socket_path":
            "/var/run/mastermind-executive/ceo-ingress.sock",
        "port": 8443,
        "policies": policies,
        "audit_root": "/var/log/mastermind-executive/mcp-auth",
        "executive_mcp_profile": "web_ceo_v3",
    }


def test_semantic_config_accepts_complete_web_ceo_v3_document():
    value = _config()
    assert preflight._semantic_config(value, SHA) == value


def test_semantic_config_refuses_primary_resource_in_additional_resources():
    primary = (
        "https://tunnel-service.gateway.unified-0.internal.api.openai.org/"
        "v1/mcp/tunnel_" + "1" * 32
    )
    value = _config()
    value["policies"]["read"]["resource"] = primary
    value["policies"]["submit"]["resource"] = primary
    value["executive_additional_resources"] = [primary]

    with pytest.raises(preflight.GatewayRefreshPreflightError):
        preflight._semantic_config(value, SHA)


def test_semantic_config_accepts_distinct_valid_additional_resource():
    additional = (
        "https://tunnel-service.gateway.unified-0.internal.api.openai.org/"
        "v1/mcp/tunnel_" + "2" * 32
    )
    value = _config()
    value["executive_additional_resources"] = [additional]

    assert preflight._semantic_config(value, SHA) == value


def test_semantic_config_refuses_submit_primary_resource_in_additional_resources():
    submit_primary = (
        "https://tunnel-service.gateway.unified-0.internal.api.openai.org/"
        "v1/mcp/tunnel_" + "3" * 32
    )
    value = _config()
    value["policies"]["submit"]["resource"] = submit_primary
    value["executive_additional_resources"] = [submit_primary]

    with pytest.raises(preflight.GatewayRefreshPreflightError):
        preflight._semantic_config(value, SHA)


@pytest.mark.parametrize("primary_policy", ["read", "submit"])
def test_semantic_config_refuses_os_resource_collision_with_primary(primary_policy):
    value = _config()
    value.update(
        os_executive_transport=True,
        os_executive_resource="https://mcp.mastermind-x.com/os/executive",
        os_commission_port=45025,
    )
    value["policies"][primary_policy]["resource"] = value["os_executive_resource"]

    with pytest.raises(preflight.GatewayRefreshPreflightError):
        preflight._semantic_config(value, SHA)


def test_semantic_config_accepts_distinct_additional_and_os_resources():
    additional = (
        "https://tunnel-service.gateway.unified-0.internal.api.openai.org/"
        "v1/mcp/tunnel_" + "4" * 32
    )
    value = _config()
    value.update(
        os_executive_transport=True,
        os_executive_resource="https://mcp.mastermind-x.com/os/executive",
        os_commission_port=45025,
        executive_additional_resources=[additional],
    )

    assert preflight._semantic_config(value, SHA) == value


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.pop("port"),
        lambda value: value.update(port=1),
        lambda value: value.update(
            ceo_ingress_socket_path="/private/tmp/other.sock"
        ),
        lambda value: value.update(executive_mcp_profile="unknown"),
        lambda value: value.update(policies={}),
        lambda value: value.update(release_sha="b" * 40),
    ],
)
def test_semantic_config_refuses_startup_invalid_documents(mutate):
    value = _config()
    mutate(value)
    with pytest.raises(preflight.GatewayRefreshPreflightError):
        preflight._semantic_config(value, SHA)


def test_qualifier_composes_existing_release_and_runtime_owners(monkeypatch):
    calls = []
    topology = SimpleNamespace(config_path="/fixed/config", config_mode=0o644,
                               config_gid=0)
    plist = SimpleNamespace(release=SHA)
    release = SimpleNamespace(manifest_digest="c" * 64)
    closure = SimpleNamespace(aggregate="d" * 64)

    monkeypatch.setattr(preflight.installed, "_role_topology",
                        lambda role: topology)
    monkeypatch.setattr(preflight.installed, "_Budget", lambda seconds: object())
    monkeypatch.setattr(preflight.installed, "_SERVICE_BUDGET_SECONDS", 25.0)
    def role_plist(*args, **kwargs):
        calls.append(("plist", kwargs.get("expected_release")))
        return plist

    monkeypatch.setattr(preflight.installed, "_verify_role_plist", role_plist)
    monkeypatch.setattr(
        preflight, "_read_config",
        lambda *args: (calls.append(("config", args[-1]))
                       or ("e" * 64, ("identity",))),
    )
    monkeypatch.setattr(
        preflight.installed, "_verify_release",
        lambda *args: (calls.append(("release", args[1])) or release),
    )
    monkeypatch.setattr(
        preflight.installed, "_verify_network_closure",
        lambda *args: (calls.append(("closure", None)) or closure),
    )
    monkeypatch.setattr(
        preflight.installed, "_recheck_release",
        lambda *args: calls.append(("release-recheck", None)),
    )
    monkeypatch.setattr(
        preflight.installed, "_recheck_network_closure",
        lambda *args: calls.append(("closure-recheck", None)),
    )

    result = preflight.qualify_gateway_refresh(SHA)
    assert result["release_sha"] == SHA
    assert result["release_manifest_sha256"] == "c" * 64
    assert result["network_closure_sha256"] == "d" * 64
    assert calls == [
        ("plist", SHA), ("config", SHA), ("release", SHA),
        ("closure", None), ("plist", SHA), ("config", SHA),
        ("release-recheck", None), ("closure-recheck", None),
    ]


def test_qualifier_refuses_drift_detected_by_incumbent_owner(monkeypatch):
    topology = SimpleNamespace(config_path="/fixed/config", config_mode=0o644,
                               config_gid=0)
    monkeypatch.setattr(preflight.installed, "_role_topology",
                        lambda role: topology)
    monkeypatch.setattr(preflight.installed, "_Budget", lambda seconds: object())
    monkeypatch.setattr(preflight.installed, "_SERVICE_BUDGET_SECONDS", 25.0)
    monkeypatch.setattr(
        preflight.installed, "_verify_role_plist",
        lambda *args, **kwargs: SimpleNamespace(release=SHA),
    )
    monkeypatch.setattr(
        preflight, "_read_config",
        lambda *args: ("e" * 64, ("identity",)),
    )
    monkeypatch.setattr(
        preflight.installed, "_verify_release",
        lambda *args: SimpleNamespace(manifest_digest="c" * 64),
    )
    monkeypatch.setattr(
        preflight.installed, "_verify_network_closure",
        lambda *args: SimpleNamespace(aggregate="d" * 64),
    )
    monkeypatch.setattr(
        preflight.installed, "_recheck_release",
        lambda *args: (_ for _ in ()).throw(RuntimeError("drift")),
    )

    with pytest.raises(preflight.GatewayRefreshPreflightError):
        preflight.qualify_gateway_refresh(SHA)
