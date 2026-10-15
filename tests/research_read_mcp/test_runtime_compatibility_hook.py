"""Optional composition hook proof; callbacks are synthetic and never enabled by the launcher."""
import asyncio
import os

import pytest

from integrations.research_read_mcp.compatibility_v1 import CompatibilityPortV1
from integrations.research_read_mcp.port_adapter import CanonicalReadContext
from integrations.research_read_mcp.runtime import RuntimeRefused, compose_runtime
from tests.research_read_mcp.test_app import CLOCK, Harness, _result
from tests.research_read_mcp.test_runtime import parsed, write_grant


ITEM = "rvitem.v1." + "a" * 64
VALUE = dict(id=ITEM, title="Synthetic bounded item", text="文本", url=
    "https://mcp.mastermind-x.com/os/research/evidence/" + ITEM,
    metadata={"coverage": "COMPLETE_BOUNDED_ITEM"})


class Adapter:
    context_type = CanonicalReadContext

    async def __call__(self, *args):
        raise AssertionError("synthetic public port unused")

    async def search_items(self, **kwargs):
        assert type(kwargs["caller_context"]) is self.context_type
        return dict(state="QUALIFIED", results=[{k: VALUE[k] for k in ("id", "title", "url")}])

    async def resolve_item(self, **kwargs):
        assert type(kwargs["caller_context"]) is self.context_type
        assert kwargs["item_id"] == ITEM
        return VALUE


def setup(tmp_path, *, factory=None):
    harness = Harness()
    adapter = Adapter()
    grant = tmp_path.resolve() / "grant.json"
    write_grant(grant, harness.policy.policy_id, harness.subjects["reader"], quote=1000)
    deployment = parsed(grant_path=str(grant), policy_id=harness.policy.policy_id)
    app = compose_runtime(deployment, release_verifier=lambda *_: None,
        policy_loader=lambda _: harness.policy, authenticator_factory=lambda _: harness.auth,
        read_service_factory=lambda _: harness, adapter_factory=lambda *_: adapter,
        context_factory=lambda ent: CanonicalReadContext(ent.subject_digest, "pro",
            frozenset({"status", "search", "fetch", "find_evidence"}), "mcp"),
        readiness=lambda _: False, mount_health_routes=lambda *_: None,
        audit_sink=harness.audit, clock=lambda: CLOCK, owner_uid=os.geteuid(),
        compatibility_factory=factory)
    harness.app = app
    return harness, adapter


def test_default_remains_absent(tmp_path):
    harness, _ = setup(tmp_path)
    async def run():
        await harness.start()
        try:
            response = await harness.rpc("tools/list", {}, token=harness.token())
            tools = _result(response)["tools"]
            assert {tool["name"] for tool in tools} == {
                "research_status", "research_search", "research_fetch", "research_find_evidence"}
        finally:
            await harness.stop()
    asyncio.run(run())


@pytest.mark.parametrize("foreign", ["context", "search", "resolve", "type"])
def test_foreign_callback_or_context_refused(tmp_path, foreign):
    def factory(adapter):
        other = Adapter()
        if foreign == "type":
            return object()
        return CompatibilityPortV1(
            other.search_items if foreign == "search" else adapter.search_items,
            other.resolve_item if foreign == "resolve" else adapter.resolve_item,
            dict if foreign == "context" else adapter.context_type)
    with pytest.raises(RuntimeRefused, match="COMPATIBILITY_COMPOSITION_REFUSED"):
        setup(tmp_path, factory=factory)


def test_existing_compatibility_port_composed_with_same_adapter(tmp_path):
    captured = []
    def factory(adapter):
        captured.append(adapter)
        return CompatibilityPortV1(adapter.search_items, adapter.resolve_item, adapter.context_type)
    harness, adapter = setup(tmp_path, factory=factory)
    assert captured == [adapter]
    async def run():
        await harness.start()
        try:
            search = _result(await harness.call("search", {"query": "Synthetic"}, token=harness.token()))
            fetch = _result(await harness.call("fetch", {"id": ITEM}, token=harness.token()))
            assert search["isError"] is False and fetch["isError"] is False
            assert search["structuredContent"]["results"][0]["id"] == ITEM
            assert fetch["structuredContent"] == VALUE
        finally:
            await harness.stop()
    asyncio.run(run())
