"""Closed historical source binding; actual installed issuance remains integration-owned."""
from pathlib import Path
import pytest
from control_plane.agentos_project_creation_source import AgentOsProjectCreationReader
from control_plane.installed_project_read_binding import _issue_installed_project_read


class PrivateOwnerFixture:
    def __init__(self,tmp):
        self._source_root=tmp; self._macro_root=tmp; self._code_root=tmp
        self._python=Path('/synthetic/python'); self._expected_source_sha='a'*40
        self._allow_synthetic_fixture=True; self.calls=[]; self.change=False
    def read_project_creation_source(self, *,work_ref,record_commit):
        self.calls.append((work_ref,record_commit))
        if self.change: self._expected_source_sha='b'*40
        return {'synthetic_test_fixture':True}


def issued(tmp):
    reader=AgentOsProjectCreationReader(macro_root=tmp)
    owner=PrivateOwnerFixture(tmp)
    reader._installed_context_owner=owner
    reader._installed_context_binding=reader._context_binding(owner)
    reader._installed_reader_binding=_issue_installed_project_read(reader,owner=owner,
        kind='project_creation_source',qualified_owner=lambda value:type(value) is PrivateOwnerFixture)
    return reader,owner


def test_fixed_historical_tuple_and_mutation_bracket(tmp_path):
    reader,owner=issued(tmp_path)
    assert reader.read(work_ref='WS:TEST',record_commit='c'*40)=={'synthetic_test_fixture':True}
    assert owner.calls==[('WS:TEST','c'*40)]
    owner.change=True
    with pytest.raises(ValueError): reader.read(work_ref='WS:TEST',record_commit='c'*40)


def test_copied_binding_or_equal_foreign_owner_does_not_issue_a_reader(tmp_path):
    reader,owner=issued(tmp_path); other=AgentOsProjectCreationReader(macro_root=tmp_path)
    other._installed_context_owner=owner;other._installed_context_binding=reader._installed_context_binding
    other._installed_reader_binding=reader._installed_reader_binding
    with pytest.raises(ValueError):other.read(work_ref='WS:TEST',record_commit='c'*40)
    reader._installed_context_owner=PrivateOwnerFixture(tmp_path)
    with pytest.raises(ValueError):reader.read(work_ref='WS:TEST',record_commit='c'*40)
    assert owner.calls==[]


def test_unissued_and_caller_commit_assertions_fail_before_callback(tmp_path):
    reader,owner=issued(tmp_path)
    with pytest.raises(ValueError):reader.read(work_ref='WS:TEST',record_commit='main')
    unissued=AgentOsProjectCreationReader(macro_root=tmp_path)
    with pytest.raises(ValueError):unissued.read(work_ref='WS:TEST',record_commit='c'*40)
    assert owner.calls==[]
