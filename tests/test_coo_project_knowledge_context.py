"""V3/v4/v5 context through the original App/client/Control/native decoder.

The duplex carrier below is explicitly in memory; no Unix listener, socket,
installed service, account or model request runs. The handler, client, retained
Runtime custody, signed resource checks and actual compiler remain unchanged.
"""
import asyncio
import dataclasses
import fcntl
import json
import os

import pytest
from mcp import types

from common import coo_agentos_context_contract as wire
from common import coo_discovery_contract as discovery
from common import coo_project_knowledge_contract as knowledge
from control_plane import executive_service as service_module
from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityRegistry,
    HERMES_NATIVE_CURRENT_CONTEXT_PROFILE_ID,
    HERMES_NATIVE_DISCOVERY_PROFILE_ID,
    HERMES_NATIVE_KNOWLEDGE_PROFILE_ID,
)
from control_plane.runtime_namespace_custody import ServiceRuntimeNamespaceCustody
from integrations.hermes_harness import native_executive_consumer as consumer
from integrations.hermes_harness.native_agentos_context import decode_context_result
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_harness.tests.test_native_current_agentos_context import signed, current_document
from integrations.mastermind_executive_app.coo import create_coo_app
from integrations.mastermind_executive_app.coo_installed import CooFactsClient
from tests import test_executive_current_agentos_context as app_tests
from tests.test_executive_principal_ingress import service
from tests.test_installed_current_agentos_context import joined, owner, env, isolated_git_env, identity

rsa_key = app_tests.rsa_key

VERSIONS = {
    3: (HERMES_NATIVE_CURRENT_CONTEXT_PROFILE_ID, wire.CURRENT_FRAME_SCHEMA,
        wire.CURRENT_RESULT_SCHEMA, wire.CURRENT_CATALOGUE,
        consumer.CURRENT_CONTEXT_CONSUMER_SCHEMA, consumer.CURRENT_CONTEXT_TOOLS_SCHEMA_DIGEST),
    4: (HERMES_NATIVE_DISCOVERY_PROFILE_ID, wire.DISCOVERY_FRAME_SCHEMA,
        wire.DISCOVERY_RESULT_SCHEMA, discovery.CATALOGUE,
        consumer.DISCOVERY_CONSUMER_SCHEMA, consumer.DISCOVERY_TOOLS_SCHEMA_DIGEST),
    5: (HERMES_NATIVE_KNOWLEDGE_PROFILE_ID, wire.KNOWLEDGE_FRAME_SCHEMA,
        wire.KNOWLEDGE_RESULT_SCHEMA, knowledge.CATALOGUE,
        consumer.KNOWLEDGE_CONSUMER_SCHEMA, consumer.KNOWLEDGE_TOOLS_SCHEMA_DIGEST),
}


def select(s, version):
    profile, *_ = VERSIONS[version]
    raw = json.loads(s["path"].read_bytes())
    raw["profiles"][profile]["enabled"] = True
    s["path"].write_text(json.dumps(raw))
    registry = ExecutionCapabilityRegistry.load(s["path"], source_root=app_tests.ROOT)
    actions = ((wire.CURRENT_ACTION,) if version == 3 else
        (wire.CURRENT_ACTION, discovery.READ_ACTION, discovery.CORRECTION_ACTION) if version == 4 else
        tuple(sorted(knowledge.REQUIRED_ACTIONS)))
    s["coo"]["missions"][0].update(capability_profile_id=profile,
        capability_profile_digest=registry.profiles[profile].profile_digest,
        principal_actions=sorted(actions))


@pytest.fixture
def original_ingress(signed, monkeypatch):
    s = signed
    runtime = s["j"]["runtime"]
    host = service(s["j"]["tmp_path"] / "context-service",
        s["j"]["tmp_path"] / "unused-socket-directory", armed=False)
    host.runtime = runtime
    factories = []
    def provider(selected):
        assert selected is runtime
        factories.append(selected)
        return s["provider"]
    host._ceo_ingress_app_binding = dataclasses.replace(
        host._ceo_ingress_app_binding, principal_facts_factory=provider)
    host._ceo_ingress_ready = True
    host._service_state = "READY"
    directory = runtime.store.path.parent
    lock = directory / "executive-service.lock"
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    marker = directory / "executive-service.running"
    marker.write_text(json.dumps({"instance_id": "context-fixture", "pid": os.getpid()}))
    marker.chmod(0o600)
    custody = ServiceRuntimeNamespaceCustody(runtime=runtime, service_lock_fd=fd,
        lock_path=lock, marker_path=marker, instance_id="context-fixture")
    custody.start()
    host._namespace_custody = custody
    peer = [host._ceo_ingress_app_binding.peer_uid]
    retained_connection = object()
    def peer_uid(connection):
        assert connection is retained_connection
        return peer[0]
    monkeypatch.setattr(service_module, "_peer_uid", peer_uid)
    client = CooFactsClient(s["j"]["tmp_path"] / "in-memory-context.sock")
    tasks, opens, client_writers, host_writers = [], [], [], []
    class Writer:
        def __init__(self, opposite, *, server=False):
            self.opposite, self.server = opposite, server
            self.transport, self.closed, self.sent = self, False, []
        def write(self, raw):
            assert not self.closed
            self.sent.append(raw)
            self.opposite.feed_data(raw)
        async def drain(self):
            pass
        def get_extra_info(self, name, default=None):
            return retained_connection if self.server and name == "socket" else default
        def is_closing(self):
            return self.closed
        def close(self):
            if not self.closed:
                self.closed = True
                self.opposite.feed_eof()
        async def wait_closed(self):
            pass
    async def in_memory(path, *, limit):
        assert path == str(client._context_socket_path)
        assert limit == wire.MAX_RESPONSE_BYTES
        opens.append((path, limit))
        to_client = asyncio.StreamReader(limit=limit)
        to_host = asyncio.StreamReader(limit=wire.MAX_REQUEST_BYTES)
        sender, responder = Writer(to_host), Writer(to_client, server=True)
        client_writers.append(sender)
        host_writers.append(responder)
        tasks.append(asyncio.create_task(host._handle_ceo_ingress_connection(to_host, responder)))
        return to_client, sender
    monkeypatch.setattr(asyncio, "open_unix_connection", in_memory)
    settings = dataclasses.replace(s["settings"],
        agentos_current_context_provider=client.agentos_current_context,
        agentos_discovery_context_provider=client.agentos_discovery_context,
        agentos_knowledge_context_provider=client.agentos_knowledge_context)
    s["settings"] = settings
    s["app"] = create_coo_app(settings, audit_sink=s["sink"], workspace_app=s["workspace_app"])
    value = dict(s=s, host=host, client=client, peer=peer, custody=custody,
        opens=opens, tasks=tasks, factories=factories,
        client_writers=client_writers, host_writers=host_writers)
    try:
        yield value
    finally:
        assert all(task.done() for task in tasks)
        custody.close()
        os.close(fd)


async def acquire(h):
    try:
        return await app_tests.request(h["s"])
    finally:
        if h["tasks"]:
            await asyncio.wait_for(asyncio.gather(*h["tasks"]), timeout=5)


@pytest.mark.parametrize("version", [3, 4, 5])
def test_original_ingress_version_returns_exact_compiler_bytes_to_native(original_ingress, version):
    h = original_ingress
    s = h["s"]
    select(s, version)
    before = s["j"]["runtime"].events.list_events()
    response = asyncio.run(acquire(h))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    _, frame_schema, result_schema, catalogue, native_schema, digest = VERSIONS[version]
    assert data["schema"] == result_schema and data["catalogue"] == catalogue
    document = current_document(data, s["coo"]["binding"]["binding"], data["workspace_principal"])
    document.update(schema=native_schema, tools_schema_digest=digest)
    publication = consumer.publication_from_document(document)
    sdk = types.CallToolResult(content=[types.TextContent(type="text", text=response.text)], isError=False)
    raw, receipt = decode_context_result(sdk, publication)
    assert raw == s["calls"][0][1]["stdout"].encode()
    assert receipt["compiler_code_commit"] == s["j"]["code"] != receipt["data_commit"] == s["j"]["current"]
    assert receipt["data_observation"]["source_operation"]["event_id"] == s["j"]["status"]["receipt"]["event_id"]
    assert len(h["opens"]) == len(h["factories"]) == len(h["host_writers"]) == 1
    sent = h["client_writers"][0].sent
    assert len(sent) == 1 and wire.decode(sent[0], limit=wire.MAX_REQUEST_BYTES)["schema"] == frame_schema
    assert len(h["host_writers"][0].sent) == 1
    assert all(w.closed for w in h["client_writers"] + h["host_writers"])
    assert not h["host"]._ceo_ingress_tasks
    assert s["j"]["runtime"].events.list_events() == before
    assert not s["j"]["runtime"].jobs.list_jobs()
    assert all(token.encode() not in sent[0] for token in (s["token"], s["second"]))
    for other in set(VERSIONS) - {version}:
        alternate = dict(document, schema=VERSIONS[other][4], tools_schema_digest=VERSIONS[other][5])
        with pytest.raises(RuntimeRefusal):
            decode_context_result(sdk, consumer.publication_from_document(alternate))


@pytest.mark.parametrize("change", ["binding", "peer", "custody", "client", "workspace"])
def test_v5_retained_owner_drift_discards_completed_context(original_ingress, change):
    h = original_ingress
    s = h["s"]
    select(s, 5)
    def after():
        if change == "binding":
            h["host"]._ceo_ingress_app_binding = dataclasses.replace(h["host"]._ceo_ingress_app_binding)
        elif change == "peer":
            h["peer"][0] += 1
        elif change == "custody":
            h["host"]._namespace_custody = None
        elif change == "client":
            h["client"]._client.socket_path = s["j"]["tmp_path"] / "changed-not-opened.sock"
        else:
            s["j"]["document"]["profiles"][s["j"]["document"]["primary_profile"]]["binding"]["permission_digest"] = "f" * 64
    s["after"][0] = after
    response = asyncio.run(acquire(h))
    assert response.status_code in {403, 503} and "data" not in response.json(), response.text
    assert len(s["calls"]) == len(h["opens"]) == 1
    assert all(w.closed for w in h["client_writers"] + h["host_writers"])
    assert not h["host"]._ceo_ingress_tasks
    assert not s["j"]["runtime"].jobs.list_jobs()


@pytest.mark.parametrize("deferred", [False, True])
def test_v5_release_keeps_exact_existing_workspace_oauth_derivation(deferred):
    from integrations.hermes_harness.tests.test_native_executive_consumer import _installation
    from ops.executive_os import release_manifest as release
    from tests.test_hermes_vendor_derivation import derivation
    document = current_document()
    document.update(schema=consumer.KNOWLEDGE_CONSUMER_SCHEMA,
        tools_schema_digest=consumer.KNOWLEDGE_TOOLS_SCHEMA_DIGEST)
    installation = _installation(consumer=document)
    native = next(row["native_gateway"] for row in installation["roles"] if row["role"] == "mmsecretary")
    native["vendor_derivation"] = derivation("workspace_oauth_privacy")
    qualified = release.validate_hermes_runtime_installation(installation, _defer_consumer=deferred)
    actual = next(row["native_gateway"] for row in qualified["roles"] if row["role"] == "mmsecretary")
    assert actual["executive_consumer"] == document
    for wrong in (None, "diagnostic_privacy", "computer_env_guard"):
        if wrong is None:
            native.pop("vendor_derivation", None)
        else:
            native["vendor_derivation"] = derivation(wrong)
        with pytest.raises(release.ReleaseManifestError):
            release.validate_hermes_runtime_installation(installation, _defer_consumer=deferred)
