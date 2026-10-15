"""Composition boundary of ExecutiveSupervisor for the installed Context reader.

Only a reader composed by the sealed installed collector, bound to the same
macro root the supervisor is given, may be retained; every other composition
is rejected before any review owner exists.
"""

from __future__ import annotations

import pytest

from control_plane import agentos_product_acceptance_basis as basis
from control_plane.executive_runtime import Runtime
from control_plane.executive_supervisor import ExecutiveSupervisor, SupervisorError
from control_plane.product_acceptance_review_owner import (
    ProductAcceptanceReviewBasisOwner,
)
from tests.test_executive_supervisor import FakeAdapter, FakeInspector
from tests.test_installed_product_acceptance_context import fixture as collector_fixture

SOURCE_ROOT_MESSAGE = "installed acceptance Context requires its source root"
QUALIFIED_MESSAGE = "installed acceptance Context requires its qualified reader"


@pytest.fixture()
def runtime(tmp_path):
    return Runtime.at(tmp_path / "runtime")


@pytest.fixture()
def adapter(runtime):
    return FakeAdapter(FakeInspector())


def build(runtime, adapter, **changes):
    return ExecutiveSupervisor(runtime=runtime, adapter=adapter, **changes)


def installed_reader(tmp_path, monkeypatch):
    """Compose the exact reader the sealed installed collector produces."""
    collector, _packet, seen = collector_fixture(tmp_path)
    monkeypatch.setattr(basis, "_SOURCE_ROOT", seen["code"])
    reader = collector.product_acceptance_basis_reader(
        macro_root=collector._macro_root
    )
    return collector, reader


def test_reader_without_source_root_is_rejected(tmp_path, runtime, adapter, monkeypatch):
    _collector, reader = installed_reader(tmp_path, monkeypatch)
    with pytest.raises(SupervisorError) as err:
        build(runtime, adapter, product_acceptance_context_reader=reader)
    assert SOURCE_ROOT_MESSAGE in str(err.value)


@pytest.mark.parametrize("impostor", [lambda **kwargs: None, object()])
def test_non_reader_compositions_are_rejected(tmp_path, runtime, adapter, impostor):
    with pytest.raises(SupervisorError) as err:
        build(
            runtime,
            adapter,
            product_acceptance_macro_root=tmp_path / "macro",
            product_acceptance_context_reader=impostor,
        )
    assert QUALIFIED_MESSAGE in str(err.value)


def test_unqualified_bare_reader_is_rejected(tmp_path, runtime, adapter):
    root = tmp_path / "macro"
    bare = basis.AgentOsProductAcceptanceBasisReader(macro_root=root)
    assert bare._installed_context_owner is None
    assert bare._installed_context_binding is None
    with pytest.raises(SupervisorError) as err:
        build(
            runtime,
            adapter,
            product_acceptance_macro_root=root,
            product_acceptance_context_reader=bare,
        )
    assert QUALIFIED_MESSAGE in str(err.value)


def test_reader_bound_to_foreign_macro_root_is_rejected(
    tmp_path, runtime, adapter, monkeypatch
):
    _collector, reader = installed_reader(tmp_path, monkeypatch)
    with pytest.raises(SupervisorError) as err:
        build(
            runtime,
            adapter,
            product_acceptance_macro_root=tmp_path / "foreign",
            product_acceptance_context_reader=reader,
        )
    assert QUALIFIED_MESSAGE in str(err.value)


def test_no_reader_composes_the_unbound_development_reader(tmp_path, runtime, adapter):
    root = tmp_path / "macro"
    supervisor = build(runtime, adapter, product_acceptance_macro_root=root)
    owner = supervisor._product_acceptance_review_owner
    assert type(owner) is ProductAcceptanceReviewBasisOwner
    assert owner.runtime is runtime
    assert type(owner.reader) is basis.AgentOsProductAcceptanceBasisReader
    assert owner.reader._macro_root == root
    assert owner.reader._installed_context_owner is None
    assert owner.reader._installed_context_binding is None


def test_collector_reader_identity_is_retained_by_review_owner(
    tmp_path, runtime, adapter, monkeypatch
):
    collector, reader = installed_reader(tmp_path, monkeypatch)
    supervisor = build(
        runtime,
        adapter,
        product_acceptance_macro_root=collector._macro_root,
        product_acceptance_context_reader=reader,
    )
    owner = supervisor._product_acceptance_review_owner
    assert type(owner) is ProductAcceptanceReviewBasisOwner
    assert owner.reader is reader
    assert owner.reader._installed_context_owner is collector
    assert owner.reader._installed_context_binding == reader._context_binding(collector)


def test_plain_supervisor_keeps_no_review_owner(runtime, adapter):
    supervisor = build(runtime, adapter)
    assert supervisor._product_acceptance_review_owner is None
