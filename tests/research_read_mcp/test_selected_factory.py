"""Selected launcher proof with synthetic authority and transports, never live."""
from dataclasses import dataclass, replace
import time

import pytest

from integrations.research_read_mcp.contracts import ContractViolation
from integrations.research_read_mcp.port_adapter import CanonicalReadContext, compose_selected_macro_service
from integrations.research_read_mcp.selected_delivery import GuardedOperation
from integrations.research_read_mcp.selected_factory import SelectedMacroComposition, SelectedReadOptions
from tests.research_read_mcp.test_app import Harness, KNOWN_REPORT, _assert_error, _result
from tests.research_read_mcp.test_launcher import launcher
from tests.research_read_mcp.test_port_adapter import Service, TEXT
from tests.research_read_mcp.test_runtime import parsed, write_grant


@pytest.fixture
def anyio_backend():
    return "asyncio"


class Unavailable(Exception):
    pass


@dataclass(frozen=True)
class MacroResult:
    value: object
    delivery_guard: object
    selection_identity: tuple


class Provider:
    def __init__(self):
        self.current = True
        self.prepares = self.calls = self.guards = self.refreshes = 0

    def prepare(self):
        self.prepares += 1
        if not self.current:
            raise Unavailable("private-preparation-reason")

    def refresh(self):
        self.refreshes += 1
        if not self.current:
            raise Unavailable("private-refresh-reason")

    def guard(self):
        self.guards += 1
        if not self.current:
            raise Unavailable("private-generation-reason")

    def run(self, operation):
        self.guard()
        self.calls += 1
        return MacroResult(operation(), self.guard, ("private-epoch", "version", "c" * 64, 1700000000))


def composition():
    provider, service = Provider(), Service()
    return SelectedMacroComposition(service, CanonicalReadContext, {}, provider, MacroResult, Unavailable), provider


def test_bridge_preserves_value_guard_and_identity_by_name():
    selected, provider = composition()
    result = selected.run(lambda: {"ok": True})
    assert type(result) is GuardedOperation
    assert result.value == {"ok": True}
    assert result.selection_identity[0] == "private-epoch"
    result.delivery_guard()
    assert provider.guards == 2
    selected.refresh()
    assert provider.refreshes == 1 and provider.prepares == 0
    provider.current = False
    with pytest.raises(ContractViolation, match="SOURCE_UNAVAILABLE"):
        selected.refresh()
    with pytest.raises(ContractViolation, match="SOURCE_UNAVAILABLE"):
        selected.run(lambda: pytest.fail("source call after invalidation"))
    assert selected.ready() is False
    with pytest.raises(ContractViolation, match="SOURCE_UNAVAILABLE"):
        selected.prepare()


def test_ready_never_prepares_or_claims_success_for_foreign_envelope():
    selected, provider = composition()
    assert selected.ready() is True
    assert provider.prepares == 0
    provider.run = lambda operation: {"value": operation()}
    assert selected.ready() is False


@pytest.mark.parametrize("change", [
    {"expected_producer_commit": "not-a-commit"}, {"writer_policy": True},
    {"max_age_seconds": True}, {"max_age_seconds": 3601},
    {"refresh_interval_seconds": 0}, {"refresh_interval_seconds": True},
    {"refresh_interval_seconds": 301},
    {"max_reuse_seconds": 301}, {"corpus_byte_budget": 0},
    {"corpus_byte_budget": 192 * 1024 * 1024 + 1},
    {"image_admission_bytes": 768 * 1024 * 1024 + 1},
])
def test_invalid_options_refuse_before_import_or_release_verification(change):
    options = replace(SelectedReadOptions("a" * 40, lambda: False), **change)
    with pytest.raises(ContractViolation, match="SOURCE_UNAVAILABLE"):
        compose_selected_macro_service("/missing/" + "b" * 40, "b" * 40, "c" * 40,
            release_verifier=lambda *args: pytest.fail("invalid options reached verifier"),
            options=options, clock=lambda: 1700000000)


@pytest.mark.anyio
@pytest.mark.parametrize("move", [False, True])
async def test_actual_launcher_binds_same_selected_owner_through_http_and_citations(tmp_path, monkeypatch, move):
    from integrations.research_read_mcp import port_adapter
    from integrations.business_mcp_auth import jwt_verifier
    selected, provider = composition()
    h, module = Harness(), launcher()
    h.clock = int(time.time())
    path = tmp_path.resolve() / "grant.json"
    write_grant(path, h.policy.policy_id, h.full.subject_digest, expires=h.clock + 100)
    deployment = parsed(grant_path=str(path), policy_id=h.policy.policy_id)
    options = SelectedReadOptions("a" * 40, lambda: provider.current)
    calls = []
    def factory(*args, **kwargs):
        assert kwargs["options"] is options and callable(kwargs["clock"])
        calls.append(args)
        selected.prepare()
        return selected
    monkeypatch.setattr(port_adapter, "compose_selected_macro_service", factory)
    monkeypatch.setattr(port_adapter, "compose_macro_service", lambda *a, **k: pytest.fail("ordinary factory"))
    monkeypatch.setattr(jwt_verifier, "JwtAuthenticator", lambda **kwargs: h.auth)
    class Verifier:
        receipts = ({"state": "SYNTHETIC_SOURCE_ONLY"},)
        def __call__(self, *args):
            return None
    verify = h.auth.verify_authorization_header
    async def final_change(*args, **kwargs):
        result = await verify(*args, **kwargs)
        if move and selected.service.calls:
            provider.current = False
        return result
    h.auth.verify_authorization_header = final_change
    h.app = module.create_runtime(deployment, Verifier(), h.policy,
                                  audit_sink=h.audit, selected_options=options)
    assert len(calls) == provider.prepares == 1
    bindings = h.app.state.research_bindings
    assert bindings.service is selected.service
    assert bindings.adapter._operation_runner.__self__ is selected
    assert h.app.state.research_selection_owner is selected
    assert h.app.state.research_refresh_owner.selection is selected
    await h.start()
    try:
        assert (await h.client.get("/readyz")).status_code == 200
        assert provider.prepares == 1
        response = await h.call("research_fetch", {"report_id": KNOWN_REPORT}, token=h.token())
        if move:
            _assert_error(response, "SOURCE_UNAVAILABLE")
            assert TEXT not in response.text
            assert (await h.client.get("/readyz")).status_code == 503
        else:
            assert _result(response)["isError"] is False
        assert "private-epoch" not in response.text and "private-generation-reason" not in response.text
        assert provider.prepares == 1
    finally:
        await h.stop()


def test_selected_factory_requires_refresh_capability_before_building_store():
    from types import SimpleNamespace
    from integrations.research_read_mcp.selected_factory import build_selected
    class PriorProvider:
        def prepare(self):
            pass
    options = SelectedReadOptions("a" * 40, lambda: True)
    store = SimpleNamespace(build_store=lambda: pytest.fail("incompatible source reached store construction"))
    with pytest.raises(ContractViolation, match="SOURCE_UNAVAILABLE"):
        build_selected(None, None, SimpleNamespace(QualifiedReadProvider=PriorProvider),
                       store, options, lambda: 1700000000)
