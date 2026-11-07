"""Nominal source capture is separate from any actual execution grant."""
import copy
import pytest
from control_plane.instruction_work_source import InstructionWorkSource,_issue_instruction_work_source,validate_instruction_work_source
from control_plane.agentos_project_instructions import AgentOsProjectInstructionsReader
from tests.test_installed_project_instructions_context import bound


def test_only_real_issued_current_reader_and_guard_can_bind_source(tmp_path,monkeypatch):
    collector,seen=bound(tmp_path,monkeypatch);reader=collector.project_instructions_reader(macro_root=seen['macro'])
    body=reader.read(work_ref='WS:ONE');row=body['instructions'][0];guards=[]
    def guard():guards.append('checked')
    args=dict(reader=reader,work_ref='WS:ONE',instruction_ref=row['instruction_ref'],revision=row['revision'],source=body['source'],principal_guard=guard)
    source=_issue_instruction_work_source(**args);material=source.material();source.check()
    assert len(guards)==4 and 'text' not in material and material['revision']==row['revision']
    detached=source.material();detached['source']['commit']='f'*40;assert source.material()==material
    unissued=AgentOsProjectInstructionsReader(macro_root=seen['macro']);unissued.read=lambda **kwargs:body
    for bad in [unissued,object()]:
        with pytest.raises(ValueError):_issue_instruction_work_source(**{**args,'reader':bad})
    with pytest.raises(ValueError):InstructionWorkSource(object(),reader,b'{}',guard)
    for field,value in [('revision','f'*64),('instruction_ref','INS:OTHER'),('source',{**body['source'],'commit':'f'*40})]:
        with pytest.raises(ValueError):_issue_instruction_work_source(**{**args,field:value})
    collector._expected_source_sha='f'*40
    with pytest.raises(ValueError):source.check()


def test_host_guard_revocation_and_later_content_revision_fail_the_capture_without_granting_work(tmp_path,monkeypatch):
    collector,seen=bound(tmp_path,monkeypatch);reader=collector.project_instructions_reader(macro_root=seen['macro']);body=reader.read(work_ref='WS:ONE');row=body['instructions'][0];allowed=[True]
    def guard():
        if not allowed[0]:raise ValueError('revoked')
    args=dict(reader=reader,work_ref='WS:ONE',instruction_ref=row['instruction_ref'],revision=row['revision'],source=body['source'],principal_guard=guard)
    source=_issue_instruction_work_source(**args);allowed[0]=False
    with pytest.raises(ValueError):source.check()
    for bad in [None,lambda:True]:
        with pytest.raises(ValueError):_issue_instruction_work_source(**{**args,'principal_guard':bad})
    assert source.material()['work_ref']=='WS:ONE' # Historical identity is not current permission.
