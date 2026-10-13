"""Installed entry composition only, with installation and listener mocked.

The real installed bridge class and canonical reply tool are constructed;
their socket is never contacted. No root path, credential or runtime is read.
"""
import json
from types import SimpleNamespace

import pytest
import uvicorn

from tests.test_executive_mcp_entry import _module
from tests import test_mastermind_os_session_transport as leaf
from integrations.executive_mcp import server
from integrations.mastermind_executive_app import gateway
from integrations.session_bridge import installed


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("coo", [False, True])
def test_entry_passes_one_existing_bridge_under_original_enable_switch(tmp_path, monkeypatch, enabled, coo):
    module = _module()
    release = "a" * 40
    module.__file__ = str(tmp_path / release / "ops/executive_os/executive_mcp_entry.py")
    monkeypatch.setattr(module, "sys", SimpleNamespace(flags=SimpleNamespace(isolated=True), dont_write_bytecode=True, path=[]))
    monkeypatch.setattr(module, "require_sealed_path", lambda *a, **kw: None)
    monkeypatch.setattr(module.os, "geteuid", lambda: 458)
    raw = dict(schema=module.CONFIG_SCHEMA, release_sha=release, service_uid=458,
               ceo_ingress_socket_path="/var/run/mastermind-executive/ceo-ingress.sock", port=8443,
               policies={}, audit_root="/var/log/mastermind-executive/mcp-auth", executive_mcp_profile="web_ceo_v3")
    if enabled:
        raw.update(os_executive_transport=True, os_executive_resource=module.OS_EXECUTIVE_RESOURCE,
                   os_commission_port=45025)
    config = tmp_path / "installed.json"
    config.write_text(json.dumps(raw))
    policies = gateway.AppPolicies(read=leaf.auth_fixture._read_policy(), submit=leaf.auth_fixture._submit_policy())
    monkeypatch.setattr(gateway, "load_app_policies", lambda _: policies)
    monkeypatch.setattr(module, "build_optional_apps", lambda *a: {})
    sentinel_coo = object()
    monkeypatch.setattr(module, "build_installed_coo_settings", lambda *a: sentinel_coo if coo else None)
    closed = []
    sink = SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr(module, "PolicyAuditSink", lambda *a, **kw: sink)
    created = []
    original_init = installed.InstalledSessionBridgeClient.__init__
    def record(self, *a, **kw):
        original_init(self, *a, **kw)
        created.append(self)
    monkeypatch.setattr(installed.InstalledSessionBridgeClient, "__init__", record)
    calls = []
    app = object()
    def factory(settings, **kw):
        calls.append((settings, kw))
        return app
    def wrong(*a, **kw):
        pytest.fail("wrong CEO/COO builder")
    monkeypatch.setattr(server, "build_web_ceo_v3_mcp_app", wrong if coo else factory)
    monkeypatch.setattr(server, "build_web_ceo_v3_with_coo_mcp_app", factory if coo else wrong)
    listeners = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: listeners.append((a, kw)))
    assert module.main(["--config", str(config)]) == 0
    assert len(created) == len(calls) == len(listeners) == 1
    _, kw = calls[0]
    bridge = created[0]
    assert kw["os_session_bridge_client"] is (bridge if enabled else None)
    assert kw["session_target_projector"] == bridge.targets
    assert kw["session_reply_handler"] == bridge.send
    assert kw["session_summon_handler"] == bridge.summon
    assert kw["session_reply_read_tool"]._reader == bridge.reply_read
    assert kw["enable_os_executive_transport"] is enabled
    assert kw["os_executive_resource"] == (module.OS_EXECUTIVE_RESOURCE if enabled else None)
    assert (kw.get("coo_settings") is sentinel_coo) is coo
    assert closed == [True]
    assert listeners == [((app,), dict(host="127.0.0.1", port=8443, access_log=False,
                                      proxy_headers=True, forwarded_allow_ips="127.0.0.1"))]
