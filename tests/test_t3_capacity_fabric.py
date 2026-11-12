"""Offline evidence for T3 Capacity Fabric registration. No live calls."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from integrations.t3_capacity_fabric import t3_config
from integrations.t3_capacity_fabric.endpoints import FabricEndpoint, default_endpoints, load_proxy_token
from integrations.t3_capacity_fabric.registration import (
    apply_registration,
    build_provider_instance,
    model_label,
    plan_registration,
    verify_registration,
)

CATALOG = ("claude-opus-5-5", "claude-fable-5.1", "claude-haiku-5-5")
TOKEN = "secret-token-value-123456"


def endpoint(tmp_path):
    return FabricEndpoint(
        endpoint_id="anthropic_oauth",
        instance_id="fabric_claude",
        display_name="Capacity Fabric Claude",
        base_url="http://127.0.0.1:8312",
        env_file=tmp_path / "gateway.env",
        preferred_fast_model="claude-haiku-5-5",
    )


def userhome(tmp_path):
    home = tmp_path / "home"
    userdata = home / ".t3" / "userdata"
    userdata.mkdir(parents=True)
    t3_config.settings_path(userdata).write_text(json.dumps({
        "defaultModelSelection": {"instanceId": "GLM2", "model": "glm-5.3"},
        "providerInstances": {
            "GLM2": {"driver": "acpRegistry", "displayName": "ZAI", "enabled": True},
        },
    }, indent=2) + "\n")
    return home


def healthy(monkeypatch, catalog=CATALOG):
    monkeypatch.setattr(
        "integrations.t3_capacity_fabric.registration.gateway_health",
        lambda e: {"endpoint_id": e.endpoint_id, "ok": True, "reason": None})
    monkeypatch.setattr(
        "integrations.t3_capacity_fabric.registration.fetch_catalog",
        lambda e, token, **kw: catalog)


def test_build_provider_instance_pins_fabric_boundary(tmp_path):
    instance = build_provider_instance(endpoint(tmp_path), CATALOG, TOKEN,
                                       home_root=tmp_path / "providers")
    assert instance["driver"] == "claudeAgent"
    assert instance["enabled"] is True
    env = {e["name"]: e for e in instance["environment"]}
    assert env["ANTHROPIC_BASE_URL"]["value"] == "http://127.0.0.1:8312"
    assert env["ANTHROPIC_AUTH_TOKEN"] == {
        "name": "ANTHROPIC_AUTH_TOKEN", "value": TOKEN, "sensitive": True}
    assert env["ANTHROPIC_SMALL_FAST_MODEL"]["value"] == "claude-haiku-5-5"
    models = instance["config"]["customModels"]
    assert [m["slug"] for m in models] == list(CATALOG)
    assert models[0]["name"] == "Claude Opus 5.5"
    effort = models[0]["capabilities"]["optionDescriptors"][0]
    assert effort["id"] == "effort" and effort["type"] == "select"
    assert [o["id"] for o in effort["options"]] == [
        "low", "medium", "high", "xhigh", "max"]
    assert instance["config"]["homePath"].endswith("fabric-anthropic-oauth")


def test_build_provider_instance_rejects_empty_inputs(tmp_path):
    with pytest.raises(ValueError):
        build_provider_instance(endpoint(tmp_path), (), TOKEN, home_root=tmp_path)
    with pytest.raises(ValueError):
        build_provider_instance(endpoint(tmp_path), CATALOG, "", home_root=tmp_path)


def test_model_labels():
    assert model_label("claude-opus-5-5") == "Claude Opus 5.5"
    assert model_label("glm-5.3-flash") == "GLM 5.3 Flash"
    assert model_label("minimax-m3") == "Minimax M3"


def test_apply_registers_instance_with_backup_and_is_idempotent(tmp_path, monkeypatch):
    home = userhome(tmp_path)
    userdata = home / ".t3" / "userdata"
    ep = endpoint(tmp_path)
    ep.env_file.write_text(f"FABRIC_PROXY_TOKEN={TOKEN}\nOTHER=x\n")
    healthy(monkeypatch)
    common = dict(userdata=userdata, home_root=home / ".t3" / "providers",
                  catalogues={"anthropic_oauth": CATALOG})

    reports = apply_registration((ep,), **common)
    assert [r.refusal for r in reports] == [None]
    assert reports[0].changed is True

    settings = json.loads(t3_config.settings_path(userdata).read_text())
    registered = settings["providerInstances"]["fabric_claude"]
    assert registered["displayName"] == "Capacity Fabric Claude"
    token_entry = [e for e in registered["environment"]
                   if e["name"] == "ANTHROPIC_AUTH_TOKEN"][0]
    assert token_entry["value"] == TOKEN
    assert settings["providerInstances"]["GLM2"]["driver"] == "acpRegistry"
    assert settings["defaultModelSelection"] == {"instanceId": "GLM2", "model": "glm-5.3"}
    provider_home = Path(registered["config"]["homePath"])
    assert provider_home.is_dir()

    backups = list((userdata / "capacity-fabric-backups").glob("settings.json.*.bak"))
    assert len(backups) == 1

    again = apply_registration((ep,), **common)
    assert again[0].changed is False
    assert len(list((userdata / "capacity-fabric-backups").glob("settings.json.*.bak"))) == 1


def test_apply_preserves_app_added_keys_on_existing_fabric_entry(tmp_path, monkeypatch):
    home = userhome(tmp_path)
    userdata = home / ".t3" / "userdata"
    ep = endpoint(tmp_path)
    ep.env_file.write_text(f"FABRIC_PROXY_TOKEN={TOKEN}\n")
    healthy(monkeypatch)
    common = dict(userdata=userdata, home_root=home / ".t3" / "providers",
                  catalogues={"anthropic_oauth": CATALOG})
    apply_registration((ep,), **common)

    settings = json.loads(t3_config.settings_path(userdata).read_text())
    settings["providerInstances"]["fabric_claude"]["userOrderKey"] = 7
    t3_config.settings_path(userdata).write_text(json.dumps(settings, indent=2))

    apply_registration((ep,), **common)
    merged = json.loads(t3_config.settings_path(userdata).read_text())
    assert merged["providerInstances"]["fabric_claude"]["userOrderKey"] == 7
    assert merged["providerInstances"]["fabric_claude"]["driver"] == "claudeAgent"


def test_apply_skips_unhealthy_gateway_without_writes(tmp_path, monkeypatch):
    home = userhome(tmp_path)
    userdata = home / ".t3" / "userdata"
    ep = endpoint(tmp_path)
    monkeypatch.setattr(
        "integrations.t3_capacity_fabric.registration.gateway_health",
        lambda e: {"endpoint_id": e.endpoint_id, "ok": False, "reason": "down"})
    reports = apply_registration((ep,), userdata=userdata,
                                 home_root=home / ".t3" / "providers",
                                 catalogues={"anthropic_oauth": CATALOG})
    assert reports[0].refusal == "gateway_unhealthy"
    settings = json.loads(t3_config.settings_path(userdata).read_text())
    assert "fabric_claude" not in settings["providerInstances"]


def test_verify_detects_drift_and_matches_registration(tmp_path, monkeypatch):
    home = userhome(tmp_path)
    userdata = home / ".t3" / "userdata"
    ep = endpoint(tmp_path)
    ep.env_file.write_text(f"FABRIC_PROXY_TOKEN={TOKEN}\n")
    healthy(monkeypatch)

    assert verify_registration((ep,), userdata=userdata)[0].refusal == "not_registered"
    apply_registration((ep,), userdata=userdata,
                       home_root=home / ".t3" / "providers",
                       catalogues={"anthropic_oauth": CATALOG})
    ok = verify_registration((ep,), userdata=userdata)
    assert ok[0].refusal is None and ok[0].models == CATALOG

    settings = json.loads(t3_config.settings_path(userdata).read_text())
    settings["providerInstances"]["fabric_claude"]["config"]["customModels"].pop()
    t3_config.settings_path(userdata).write_text(json.dumps(settings, indent=2))
    drifted = verify_registration((ep,), userdata=userdata)
    assert drifted[0].refusal == "catalogue_drift"

    settings = json.loads(t3_config.settings_path(userdata).read_text())
    entry = settings["providerInstances"]["fabric_claude"]
    entry["environment"] = [e for e in entry["environment"] if e["name"] != "ANTHROPIC_AUTH_TOKEN"]
    t3_config.settings_path(userdata).write_text(json.dumps(settings, indent=2))
    assert verify_registration((ep,), userdata=userdata)[0].refusal == "auth_token_missing"


def test_plan_writes_nothing(tmp_path, monkeypatch):
    home = userhome(tmp_path)
    userdata = home / ".t3" / "userdata"
    ep = endpoint(tmp_path)
    ep.env_file.write_text(f"FABRIC_PROXY_TOKEN={TOKEN}\n")
    healthy(monkeypatch)
    reports = plan_registration((ep,), userdata=userdata,
                                home_root=home / ".t3" / "providers",
                                catalogues={"anthropic_oauth": CATALOG})
    assert reports[0].changed is True and reports[0].models == CATALOG
    settings = json.loads(t3_config.settings_path(userdata).read_text())
    assert "fabric_claude" not in settings["providerInstances"]
    assert not (userdata / "capacity-fabric-backups").exists()


def test_load_proxy_token_requires_fabric_token(tmp_path):
    ep = endpoint(tmp_path)
    ep.env_file.write_text("OTHER=x\n")
    with pytest.raises(ValueError):
        load_proxy_token(ep.env_file)


@pytest.mark.parametrize("existing_unified", [False, True])
def test_default_registration_keeps_existing_gateway_owners_and_unrelated_entries(
        tmp_path, monkeypatch, existing_unified):
    home = userhome(tmp_path)
    userdata = home / ".t3" / "userdata"
    settings_path = t3_config.settings_path(userdata)
    before = json.loads(settings_path.read_text())
    if existing_unified:
        before["providerInstances"]["capacity_fabric"] = {
            "driver": "claudeAgent", "enabled": True,
            "displayName": "Existing owner entry", "config": {"retained": "original"}}
        settings_path.write_text(json.dumps(before))
    endpoints = default_endpoints(tmp_path / "gateway-fixtures")
    for ep in endpoints:
        ep.env_file.parent.mkdir(parents=True)
        ep.env_file.write_text(
            f"{ep.token_env_name}={TOKEN}\nEXPLABS_ANTHROPIC_MODELS={','.join(CATALOG)}\n")
    healthy(monkeypatch)
    reports = apply_registration(endpoints, userdata=userdata,
        home_root=home / ".t3" / "providers",
        catalogues={ep.endpoint_id: CATALOG for ep in endpoints})
    assert len(reports) == 2 and all(row.refusal is None for row in reports)
    after = json.loads(settings_path.read_text())
    assert after["defaultModelSelection"] == before["defaultModelSelection"]
    assert set(after["providerInstances"]) - set(before["providerInstances"]) == {
        "fabric_claude", "fabric_experiential"}
    for instance_id, original in before["providerInstances"].items():
        assert after["providerInstances"][instance_id] == original
    for instance_id, expected in [("fabric_claude", "http://127.0.0.1:8312"),
                                  ("fabric_experiential", "http://127.0.0.1:8311")]:
        env = {row["name"]: row["value"] for row in after["providerInstances"][instance_id]["environment"]}
        assert env["ANTHROPIC_BASE_URL"] == expected
        assert env["ANTHROPIC_AUTH_TOKEN"] == TOKEN
