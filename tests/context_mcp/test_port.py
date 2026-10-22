from __future__ import annotations

import asyncio
import dataclasses

import pytest

from integrations.context_mcp.contracts import TOOL_NAMES
from integrations.context_mcp.model import ContextCaller, ContextPortRefused
from integrations.context_mcp.port import (
    ContextProjectBinding,
    create_context_port_bundle,
)


def _caller(**overrides):
    values = dict(
        subject_digest="a" * 64,
        client_ref="client:web",
        resource="https://context.example/mcp",
        scopes=("workbench.read",),
        expires_at=100,
    )
    values.update(overrides)
    return ContextCaller(**values)


class Owner:
    def __init__(self):
        self.now = 1000
        self.binding = ContextProjectBinding(
            caller=_caller(),
            project_ref="project:mastermind",
            generation="generation:1",
            repositories=("mastermindx-market-intelligence/Mastermind",),
            workspace_operations=("context-op",),
            tools=TOOL_NAMES,
        )
        self.calls = []

    def resolve(self, caller, project_ref):
        if caller != self.binding.caller or project_ref != self.binding.project_ref:
            return None
        return self.binding

    async def handler(self, caller, binding, request):
        self.calls.append((caller, binding, dict(request)))
        return {
            "status": "OK",
            "schema": "test.result.v1",
            "project_ref": binding.project_ref,
            "data": {"tool": request.get("term", "ok")},
            "degraded": [],
        }


def _bundle(owner):
    handlers = {name: owner.handler for name in TOOL_NAMES}
    return create_context_port_bundle(
        resolve_binding=owner.resolve,
        handlers=handlers,
        clock_ms=lambda: owner.now,
    )


def test_exact_handler_set_required():
    owner = Owner()
    with pytest.raises(TypeError, match="exact"):
        create_context_port_bundle(
            resolve_binding=owner.resolve,
            handlers={"resolve_context": owner.handler},
            clock_ms=lambda: owner.now,
        )


def test_atlas_search_requires_repository_in_existing_binding():
    owner = Owner()
    port, _final = _bundle(owner)
    good = {
        "project_ref": "project:mastermind",
        "repository": "mastermindx-market-intelligence/Mastermind",
        "term": "Context",
    }
    result = asyncio.run(port(_caller(), "atlas_search", good))
    assert result["project_ref"] == "project:mastermind"

    bad = dict(good, repository="other/repo")
    with pytest.raises(ContextPortRefused):
        asyncio.run(port(_caller(), "atlas_search", bad))


def test_workspace_overlay_requires_operation_in_existing_binding():
    owner = Owner()
    port, _final = _bundle(owner)
    request = {
        "project_ref": "project:mastermind",
        "operation_id": "context-op",
    }
    assert asyncio.run(port(_caller(), "workspace_overlay", request))["status"] == "OK"

    with pytest.raises(ContextPortRefused):
        asyncio.run(
            port(
                _caller(),
                "workspace_overlay",
                {
                    "project_ref": "project:mastermind",
                    "operation_id": "other-op",
                },
            )
        )


def test_tool_must_be_permitted_by_binding():
    owner = Owner()
    owner.binding = dataclasses.replace(
        owner.binding,
        tools=("resolve_context",),
    )
    port, _final = _bundle(owner)
    with pytest.raises(ContextPortRefused):
        asyncio.run(
            port(
                _caller(),
                "atlas_search",
                {
                    "project_ref": "project:mastermind",
                    "repository": "mastermindx-market-intelligence/Mastermind",
                    "term": "x",
                },
            )
        )


def test_binding_change_during_await_is_refused():
    owner = Owner()

    async def changing_handler(caller, binding, request):
        owner.binding = dataclasses.replace(
            owner.binding,
            generation="generation:2",
        )
        return {
            "status": "OK",
            "schema": "test.result.v1",
            "project_ref": binding.project_ref,
            "data": {},
            "degraded": [],
        }

    handlers = {name: owner.handler for name in TOOL_NAMES}
    handlers["resolve_context"] = changing_handler
    port, _final = create_context_port_bundle(
        resolve_binding=owner.resolve,
        handlers=handlers,
        clock_ms=lambda: owner.now,
    )
    with pytest.raises(ContextPortRefused, match="CONTEXT_BINDING_CHANGED"):
        asyncio.run(
            port(
                _caller(),
                "resolve_context",
                {
                    "project_ref": "project:mastermind",
                    "task": "recover",
                },
            )
        )


def test_final_authorization_detects_late_binding_change():
    owner = Owner()
    _port, final = _bundle(owner)
    request = {
        "project_ref": "project:mastermind",
        "task": "recover",
    }
    revalidate = final(_caller(), "resolve_context", request)
    owner.binding = dataclasses.replace(
        owner.binding,
        generation="generation:2",
    )
    with pytest.raises(ContextPortRefused, match="CONTEXT_BINDING_CHANGED"):
        revalidate()


def test_expired_caller_is_refused():
    owner = Owner()
    owner.now = 100_000
    port, _final = _bundle(owner)
    with pytest.raises(ContextPortRefused):
        asyncio.run(
            port(
                _caller(),
                "resolve_context",
                {
                    "project_ref": "project:mastermind",
                    "task": "recover",
                },
            )
        )


def test_handler_cannot_relabel_project():
    owner = Owner()

    async def wrong_project(caller, binding, request):
        return {
            "status": "OK",
            "schema": "test.result.v1",
            "project_ref": "project:other",
            "data": {},
            "degraded": [],
        }

    handlers = {name: owner.handler for name in TOOL_NAMES}
    handlers["resolve_context"] = wrong_project
    port, _final = create_context_port_bundle(
        resolve_binding=owner.resolve,
        handlers=handlers,
        clock_ms=lambda: owner.now,
    )
    with pytest.raises(ContextPortRefused, match="CONTEXT_SOURCE_CHANGED"):
        asyncio.run(
            port(
                _caller(),
                "resolve_context",
                {
                    "project_ref": "project:mastermind",
                    "task": "recover",
                },
            )
        )


def test_wrong_scope_is_refused():
    owner = Owner()
    port, _final = _bundle(owner)
    with pytest.raises(ContextPortRefused):
        asyncio.run(
            port(
                _caller(scopes=("other",)),
                "resolve_context",
                {
                    "project_ref": "project:mastermind",
                    "task": "recover",
                },
            )
        )
