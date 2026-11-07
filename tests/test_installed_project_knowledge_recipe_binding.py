"""Actual nominal issued binding; child capture qualification is a separate join."""
from pathlib import Path
from types import SimpleNamespace
import copy

import pytest

from integrations.executive_mcp.installed import InstalledBootPacketCollector
from control_plane import installed_project_knowledge_compiler as facade
from tests.test_installed_product_acceptance_context import fixture


@pytest.fixture
def issued(tmp_path, monkeypatch):
    collector, _, seen = fixture(tmp_path)
    monkeypatch.setattr(facade, "_SOURCE_ROOT", seen["code"])
    calls = []
    marker = {"private_capture": "fixed qualified child dependency"}
    def read(owner, **kwargs):
        calls.append(kwargs)
        return marker
    monkeypatch.setattr(InstalledBootPacketCollector, "read_project_knowledge_recipe", read)
    reader = collector.project_knowledge_recipe_reader(macro_root=seen["macro"])
    args = {"actor_ref": "workspace:" + "a" * 64, "permission_binding_digest": "b" * 64,
            "decision_date": "2026-11-04"}
    return SimpleNamespace(collector=collector, seen=seen, calls=calls, marker=marker,
                           reader=reader, args=args)


def test_nominal_factory_issues_fixed_prepare_and_original_restore(issued):
    x = issued
    assert x.reader.compile({"request_id": "test"}, **x.args) is x.marker
    assert x.calls[0]["mode"] == "prepare" and x.calls[0]["initial_snapshot"] is None
    snapshot = {"decision_date": "2026-11-03"}
    assert x.reader.restore({"request_id": "test"}, actor_ref=x.args["actor_ref"],
        permission_binding_digest=x.args["permission_binding_digest"], initial_snapshot=snapshot,
        source_binding={"compiler": "original"}) is x.marker
    assert x.calls[1]["mode"] == "restore" and x.calls[1]["decision_date"] == "2026-11-03"


@pytest.mark.parametrize("mode", ["bare", "forged", "copied", "foreign_owner"])
def test_unissued_or_transferred_binding_cannot_call_a_compiler(issued, mode):
    x = issued
    reader = facade.InstalledProjectKnowledgeCompiler(macro_root=x.seen["macro"])
    reader._installed_context_owner = x.collector
    reader._installed_context_binding = x.reader._installed_context_binding
    if mode == "forged":
        reader._installed_reader_binding = SimpleNamespace(issued=True)
    elif mode in {"copied", "foreign_owner"}:
        reader._installed_reader_binding = x.reader._installed_reader_binding
        if mode == "foreign_owner": reader._installed_context_owner = copy.copy(x.collector)
    with pytest.raises(ValueError, match="project_knowledge_recipe_unavailable"):
        reader.compile({}, **x.args)
    assert x.calls == []


def test_invalid_private_actor_date_or_restore_shape_is_refused_before_callback(issued):
    x = issued
    for change in ({"actor_ref": "workspace:label"}, {"decision_date": "2026-02-30"},
                   {"permission_binding_digest": "b" * 63}):
        with pytest.raises(ValueError): x.reader.compile({}, **(x.args | change))
    with pytest.raises(ValueError):
        x.reader.restore({}, actor_ref=x.args["actor_ref"], permission_binding_digest=x.args["permission_binding_digest"],
                         initial_snapshot=None, source_binding={})
    assert x.calls == []


def test_callback_replacement_and_coordinate_drift_withhold_capture(issued, monkeypatch):
    x = issued
    monkeypatch.setattr(InstalledBootPacketCollector, "read_project_knowledge_recipe",
                        lambda *a, **kw: pytest.fail("replacement callback invoked"))
    with pytest.raises(ValueError): x.reader.compile({}, **x.args)
    assert x.calls == []


def test_drift_during_callback_withholds_private_capture(issued, monkeypatch):
    x = issued
    def read(owner, **kwargs):
        x.calls.append(kwargs)
        owner._macro_root = Path("/foreign/macro")
        return x.marker
    monkeypatch.setattr(InstalledBootPacketCollector, "read_project_knowledge_recipe", read)
    reader = x.collector.project_knowledge_recipe_reader(macro_root=x.seen["macro"])
    with pytest.raises(ValueError): reader.compile({}, **x.args)
    assert len(x.calls) == 1
