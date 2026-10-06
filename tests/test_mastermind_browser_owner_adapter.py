from __future__ import annotations

import asyncio
from dataclasses import dataclass
import pytest

from integrations.mastermind_browser_plugin.catalog import SCHEMA_DIGEST
from integrations.mastermind_browser_plugin.facade import BrowserFacade, OwnerRefused
from integrations.mastermind_browser_plugin.owner_adapter import (
    BrowserCallerBinding,
    ManagedBrowserOwnerAdapter,
    OwnerToolCall,
)
from integrations.mastermind_browser_plugin.tab_ref import (
    BrowserTabRef,
    BrowserTabRefCodec,
    TAB_REF_SCHEMA,
    TabBackend,
)

NOW = 1_800_000_000_000
BACKEND_DIGEST = "e" * 64
KEY = b"k" * 32


@dataclass(frozen=True)
class Caller:
    subject_digest: str = "b" * 64
    client_ref: str = "client-a"
    resource: str = "browser-resource"


def caller_binding(caller):
    return BrowserCallerBinding(
        subject_digest=caller.subject_digest,
        client_ref=caller.client_ref,
        resource=caller.resource,
    )


def tab_value(**changes):
    values = dict(
        schema=TAB_REF_SCHEMA,
        backend=TabBackend.MANAGED.value,
        browser_ref="browser-resource-" + "a" * 64,
        subject_digest="b" * 64,
        client_ref="client-a",
        resource="browser-resource",
        host_ref="host-" + "c" * 64,
        boot_ref="boot-a",
        profile_ref="profile-a",
        browser_instance_ref="browser-a",
        connection_generation="generation-a",
        tab_locator=7,
        document_revision=3,
        consent_ref=None,
        allowed_actions=("click", "navigate", "screenshot", "snapshot", "type"),
        catalog_schema_digest=SCHEMA_DIGEST,
        backend_schema_digest=BACKEND_DIGEST,
        issued_at_ms=NOW,
        expires_at_ms=NOW + 60_000,
    )
    values.update(changes)
    return BrowserTabRef(**values)


def token(**changes):
    return BrowserTabRefCodec(KEY).encode(tab_value(**changes))


class Projector:
    def project_read(self, tab, action, args):
        assert action in {"snapshot", "screenshot"}
        return OwnerToolCall(
            tool_name={"snapshot": "browser_snapshot", "screenshot": "browser_take_screenshot"}[action],
            arguments={"page": tab.tab_locator, **args},
        )

    def project_action(self, tab, action, args):
        mapping = {
            "click": "browser_click",
            "type": "browser_type",
            "navigate": "browser_navigate",
        }
        if action not in mapping:
            raise OwnerRefused("ACTION_BACKEND_UNSUPPORTED")
        return OwnerToolCall(
            tool_name=mapping[action],
            arguments={"page": tab.tab_locator, **args},
        )


class EffectPort:
    def __init__(self):
        self.calls = []

    def call_read_tool(self, caller, browser_ref, tool, arguments):
        self.calls.append(("read", caller, browser_ref, tool, dict(arguments)))
        return {"kind": "native", "tool": tool}

    def prepare_action(self, caller, browser_ref, tool, arguments):
        self.calls.append(("prepare", caller, browser_ref, tool, dict(arguments)))
        return "owner-action-ref"

    def run_action(self, caller, browser_ref, action_ref):
        self.calls.append(("run", caller, browser_ref, action_ref))
        return {
            "status": "OK",
            "effect_state": "APPLIED",
            "observed_sha256": "d" * 64,
            "reconciled": False,
            "result": {"kind": "native-result"},
        }

    def reconcile_action(self, caller, browser_ref, action_ref):
        self.calls.append(("reconcile", caller, browser_ref, action_ref))
        return {
            "status": "OK",
            "effect_state": "EFFECT_UNKNOWN",
            "observed_sha256": None,
            "reconciled": True,
        }


def adapter(*, current=True, effect_port=None, fleet=None, tabs=None, now=NOW):
    effect = effect_port or EffectPort()
    validations = []

    def revalidate(caller, tab):
        validations.append((caller, tab))
        return current

    owner = ManagedBrowserOwnerAdapter(
        codec=BrowserTabRefCodec(KEY),
        clock_ms=lambda: now,
        caller_binding=caller_binding,
        revalidate_tab=revalidate,
        effect_port=effect,
        projector=Projector(),
        fleet_reader=fleet or (lambda caller, args: {"browsers": [], "caller": caller.client_ref}),
        tabs_reader=tabs or (lambda caller, args: {"tabs": [], "caller": caller.client_ref}),
        expected_catalog_schema_digest=SCHEMA_DIGEST,
        expected_backend_schema_digest=BACKEND_DIGEST,
    )
    return owner, effect, validations


def test_reads_decode_exact_caller_revalidate_and_delegate_to_existing_port():
    owner, effect, validations = adapter()
    result = asyncio.run(owner.browser_snapshot(Caller(), {"tab_ref": token()}))
    assert result["tool"] == "browser_snapshot"
    assert len(validations) == 1
    assert effect.calls == [
        (
            "read",
            Caller(),
            tab_value().browser_ref,
            "browser_snapshot",
            {"page": 7},
        )
    ]


def test_wrong_caller_schema_or_live_generation_refuses_before_effect_owner():
    for kwargs, code in [
        ({"caller": Caller(client_ref="client-b")}, "CALLER_BINDING_CHANGED"),
        ({"tab": {"catalog_schema_digest": "f" * 64}}, "CATALOG_SCHEMA_CHANGED"),
        ({"tab": {"backend_schema_digest": "f" * 64}}, "BACKEND_SCHEMA_CHANGED"),
    ]:
        owner, effect, _ = adapter()
        with pytest.raises(OwnerRefused, match=code):
            asyncio.run(
                owner.browser_snapshot(
                    kwargs.get("caller", Caller()),
                    {"tab_ref": token(**kwargs.get("tab", {}))},
                )
            )
        assert effect.calls == []


def test_live_revalidation_is_required_before_read_prepare_and_run():
    owner, effect, validations = adapter(current=False)
    for call in [
        lambda: owner.browser_snapshot(Caller(), {"tab_ref": token()}),
        lambda: owner.prepare_browser_action(
            Caller(),
            {
                "tab_ref": token(),
                "action": "click",
                "args": {"element_ref": "element-a"},
            },
        ),
        lambda: owner.run_browser_action(
            Caller(),
            {"tab_ref": token(), "action_ref": "owner-action-ref"},
        ),
    ]:
        with pytest.raises(OwnerRefused, match="TAB_BINDING_CHANGED"):
            asyncio.run(call())
    assert len(validations) == 3
    assert effect.calls == []


def test_prepare_delegates_once_and_returns_only_existing_owner_action_ref():
    owner, effect, _ = adapter()
    result = asyncio.run(
        owner.prepare_browser_action(
            Caller(),
            {
                "tab_ref": token(),
                "action": "click",
                "args": {"element_ref": "element-a"},
            },
        )
    )
    assert result == {"action_ref": "owner-action-ref"}
    assert effect.calls[0][0] == "prepare"
    assert effect.calls[0][2] == tab_value().browser_ref
    assert effect.calls[0][3] == "browser_click"


def test_run_translates_existing_owner_effect_receipt_without_redispatch():
    owner, effect, _ = adapter()
    result = asyncio.run(
        owner.run_browser_action(
            Caller(),
            {"tab_ref": token(), "action_ref": "owner-action-ref"},
        )
    )
    assert result == {
        "effect": "APPLIED",
        "status": "OK",
        "observed_sha256": "d" * 64,
        "reconciled": False,
        "result": {"kind": "native-result"},
    }
    assert [row[0] for row in effect.calls] == ["run"]


def test_reconcile_accepts_expired_signed_tab_without_live_tab_revalidation():
    owner, effect, validations = adapter(now=NOW + 60_000)
    result = asyncio.run(
        owner.reconcile_browser_action(
            Caller(),
            {"tab_ref": token(), "action_ref": "owner-action-ref"},
        )
    )
    assert result["effect"] == "EFFECT_UNKNOWN"
    assert result["reconciled"] is True
    assert validations == []
    assert [row[0] for row in effect.calls] == ["reconcile"]


def test_expired_ref_cannot_prepare_or_run_a_new_effect():
    owner, effect, _ = adapter(now=NOW + 60_000)
    for call in [
        lambda: owner.prepare_browser_action(
            Caller(),
            {"tab_ref": token(), "action": "click", "args": {"element_ref": "a"}},
        ),
        lambda: owner.run_browser_action(
            Caller(),
            {"tab_ref": token(), "action_ref": "owner-action-ref"},
        ),
    ]:
        with pytest.raises(OwnerRefused, match="TAB_REF_EXPIRED"):
            asyncio.run(call())
    assert effect.calls == []


def test_shared_human_ref_is_not_routed_into_managed_effect_port():
    owner, effect, _ = adapter()
    with pytest.raises(OwnerRefused, match="BACKEND_MISMATCH"):
        asyncio.run(
            owner.browser_snapshot(
                Caller(),
                {"tab_ref": token(backend=TabBackend.SHARED_HUMAN.value, consent_ref="consent-a")},
            )
        )
    assert effect.calls == []


def test_backend_unsupported_action_refuses_without_prepare():
    owner, effect, _ = adapter()
    with pytest.raises(OwnerRefused, match="ACTION_BACKEND_UNSUPPORTED"):
        asyncio.run(
            owner.prepare_browser_action(
                Caller(),
                {
                    "tab_ref": token(allowed_actions=("scroll",)),
                    "action": "scroll",
                    "args": {"delta_x": 0, "delta_y": 1},
                },
            )
        )
    assert effect.calls == []


def test_fleet_and_tabs_are_existing_owner_reads_not_new_registry_state():
    owner, effect, validations = adapter()
    assert asyncio.run(owner.browser_fleet(Caller(), {"limit": 3}))["caller"] == "client-a"
    assert asyncio.run(owner.browser_tabs(Caller(), {"browser_ref": "browser-resource-a"}))["caller"] == "client-a"
    assert effect.calls == []
    assert validations == []


def test_effect_port_exception_is_never_retried():
    class Broken(EffectPort):
        def run_action(self, *args):
            self.calls.append(("run",))
            raise RuntimeError("transport lost")

    effect = Broken()
    owner, _, _ = adapter(effect_port=effect)
    facade = BrowserFacade(owner=owner, caller_resolver=lambda: Caller())
    result = asyncio.run(
        facade.call(
            "run_browser_action",
            {"tab_ref": token(), "action_ref": "owner-action-ref"},
        )
    )
    assert result["effect"] == "EFFECT_UNKNOWN"
    assert result["retry_allowed"] is False
    assert effect.calls == [("run",)]


def test_reconcile_survives_current_catalog_and_backend_schema_upgrade():
    historical = token(
        catalog_schema_digest="f" * 64,
        backend_schema_digest="a" * 64,
    )
    owner, effect, validations = adapter(now=NOW + 60_000)
    result = asyncio.run(
        owner.reconcile_browser_action(
            Caller(),
            {"tab_ref": historical, "action_ref": "owner-action-ref"},
        )
    )
    assert result["effect"] == "EFFECT_UNKNOWN"
    assert result["reconciled"] is True
    assert validations == []
    assert [row[0] for row in effect.calls] == ["reconcile"]

    live_owner, _, _ = adapter()
    with pytest.raises(OwnerRefused, match="CATALOG_SCHEMA_CHANGED"):
        asyncio.run(
            live_owner.browser_snapshot(
                Caller(),
                {"tab_ref": token(catalog_schema_digest="f" * 64)},
            )
        )
    with pytest.raises(OwnerRefused, match="BACKEND_SCHEMA_CHANGED"):
        asyncio.run(
            live_owner.run_browser_action(
                Caller(),
                {
                    "tab_ref": token(backend_schema_digest="a" * 64),
                    "action_ref": "owner-action-ref",
                },
            )
        )


def test_workbench_projector_maps_only_the_safe_high_level_subset():
    from integrations.mastermind_browser_plugin.owner_adapter import WorkbenchManagedProjector

    projector = WorkbenchManagedProjector()

    assert projector.project_read(tab_value(), "snapshot", {}) == OwnerToolCall(
        tool_name="browser_snapshot",
        arguments={},
    )
    assert projector.project_read(tab_value(), "screenshot", {}) == OwnerToolCall(
        tool_name="browser_take_screenshot",
        arguments={"scale": "css"},
    )
    assert projector.project_action(
        tab_value(), "click", {"element_ref": "1_2"}
    ) == OwnerToolCall(
        tool_name="browser_click",
        arguments={"target": "1_2"},
    )
    assert projector.project_action(
        tab_value(), "type", {"element_ref": "1_4", "text": "Mastermind"}
    ) == OwnerToolCall(
        tool_name="browser_type",
        arguments={
            "target": "1_4",
            "text": "Mastermind",
            "slowly": False,
            "submit": False,
        },
    )
    assert projector.project_action(
        tab_value(), "navigate", {"url": "https://example.test/next"}
    ) == OwnerToolCall(
        tool_name="browser_navigate",
        arguments={"url": "https://example.test/next"},
    )


def test_workbench_projector_rejects_scroll_and_argument_smuggling():
    from integrations.mastermind_browser_plugin.owner_adapter import WorkbenchManagedProjector

    projector = WorkbenchManagedProjector()
    with pytest.raises(OwnerRefused, match="ACTION_BACKEND_UNSUPPORTED"):
        projector.project_action(
            tab_value(allowed_actions=("scroll",)),
            "scroll",
            {"delta_x": 0, "delta_y": 1},
        )

    for action, args in [
        ("click", {"element_ref": "1_2", "button": "right"}),
        ("type", {"element_ref": "1_4", "text": "x", "submit": True}),
        ("navigate", {"url": "file:///etc/passwd"}),
    ]:
        with pytest.raises(OwnerRefused):
            projector.project_action(tab_value(), action, args)

    with pytest.raises(OwnerRefused):
        projector.project_read(tab_value(), "snapshot", {"filename": "leak.md"})
