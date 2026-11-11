"""Opaque installed issuance remains exact while core stays below integration."""
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from integrations.executive_mcp.installed import InstalledBootPacketCollector
from control_plane import agentos_project_plan as plan
from control_plane import agentos_project_journal as journal
from tests.test_installed_product_acceptance_context import fixture


@pytest.fixture(params=[(plan, "project_plan"), (journal, "project_journal")])
def issued(request, tmp_path, monkeypatch):
    module, kind = request.param
    collector, _, seen = fixture(tmp_path)
    monkeypatch.setattr(module, "_SOURCE_ROOT", seen["code"])
    calls = []
    marker = {"source": "qualified-fixed-owner"}
    def read(owner, *, work_ref):
        calls.append(work_ref)
        return marker
    monkeypatch.setattr(InstalledBootPacketCollector, "read_" + kind, read)
    reader = getattr(collector, kind + "_reader")(macro_root=seen["macro"])
    error = module.ProjectPlanSourceUnavailable if kind == "project_plan" else module.ProjectJournalSourceUnavailable
    reader_type = module.AgentOsProjectPlanReader if kind == "project_plan" else module.AgentOsProjectJournalReader
    return SimpleNamespace(module=module, kind=kind, collector=collector, seen=seen,
        reader=reader, calls=calls, marker=marker, error=error, reader_type=reader_type)


def test_actual_installed_factory_issues_one_fixed_read(issued):
    assert issued.reader.read(work_ref="WS:ONE") is issued.marker
    assert issued.calls == ["WS:ONE"]


@pytest.mark.parametrize("fake", ["bare", "forged", "copied"])
def test_no_bare_labelled_or_transferred_binding_can_read(issued, fake):
    reader = issued.reader_type(macro_root=issued.seen["macro"])
    reader._installed_context_owner = issued.collector
    reader._installed_context_binding = issued.reader._installed_context_binding
    if fake == "forged":
        reader._installed_reader_binding = SimpleNamespace(owner=issued.collector, kind=issued.kind, issued=True)
    elif fake == "copied":
        reader._installed_reader_binding = issued.reader._installed_reader_binding
    with pytest.raises(issued.error, match="SOURCE_UNAVAILABLE"):
        reader.read(work_ref="WS:ONE")
    assert issued.calls == []


def test_binding_cannot_be_rebound_to_another_equal_coordinate_owner(issued):
    issued.reader._installed_context_owner = copy.copy(issued.collector)
    with pytest.raises(issued.error): issued.reader.read(work_ref="WS:ONE")
    assert issued.calls == []


def test_changed_fixed_callback_is_refused_before_invocation(issued, monkeypatch):
    monkeypatch.setattr(InstalledBootPacketCollector, "read_" + issued.kind,
                        lambda owner, **kwargs: pytest.fail("rebound method was invoked"))
    with pytest.raises(issued.error): issued.reader.read(work_ref="WS:ONE")
    assert issued.calls == []


def test_owner_source_change_before_read_is_refused(issued):
    issued.collector._expected_source_sha = "f" * 40
    with pytest.raises(issued.error): issued.reader.read(work_ref="WS:ONE")
    assert issued.calls == []


def test_source_mutation_during_fixed_read_withholds_its_result(issued, monkeypatch):
    def mutate(owner, *, work_ref):
        issued.calls.append(work_ref)
        owner._macro_root = Path("/foreign/macro")
        return issued.marker
    monkeypatch.setattr(InstalledBootPacketCollector, "read_" + issued.kind, mutate)
    reader = getattr(issued.collector, issued.kind + "_reader")(macro_root=issued.seen["macro"])
    with pytest.raises(issued.error): reader.read(work_ref="WS:ONE")
    assert issued.calls == ["WS:ONE"]
