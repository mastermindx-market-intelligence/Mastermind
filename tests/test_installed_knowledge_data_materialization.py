"""Actual nominal DATA view → collector/CF1 child with explicit CODE C.

Grant/PR identity are explicit local fixtures. Real original Events, Git
landing/readback, fixed child, source seals and body bytes are exercised.
"""
from pathlib import Path
import pytest
from integrations.executive_mcp.installed import InstalledBootPacketCollector
from ops.executive_os.capacity_source_contract import PYTHON_BINARY
from tests.test_project_canonical_data import ready,env,isolated_git_env
from tests.test_workspace_project_git_publisher import git,rev_parse
ROOT=Path(__file__).resolve().parents[1]
pytestmark=pytest.mark.skipif(not Path(PYTHON_BINARY).is_file(),reason='native CF1 qualification runtime unavailable')


def test_ordinary_boot_packet_still_rejects_wrong_macro_sha(tmp_path):
    import json
    from tests.test_executive_installed_readers import _git_status_result
    from integrations.executive_mcp.schemas import GatewayError
    source,macro,code=[tmp_path/name for name in ('source','macro','code')]
    for root in (source,macro,code/'scripts'):root.mkdir(parents=True)
    (code/'scripts/ceo_boot_packet.py').write_text('# inert fixture\n')
    python=tmp_path/'python';python.write_text('fixture')
    packet={'schema':'mastermind.ceo_boot_packet.v1','mastermind':{'root':str(source),'sha':'a'*40},
        'macro':{'root':str(macro),'sha':'c'*40,'resolved_via':'flag','candidates_tried':[]}}
    def runner(argv,*,cwd,**kwargs):
        if str(argv[0])=='git':return _git_status_result('a'*40 if Path(cwd)==source else 'b'*40)
        return dict(code=0,stdout=json.dumps(packet),stderr='',timed_out=False,limit_exceeded=False,invalid_utf8=False)
    collector=InstalledBootPacketCollector(source_root=source,macro_root=macro,code_root=code,
        python_executable=python,runner=runner,expected_source_sha='a'*40,_allow_synthetic_fixture=True)
    with pytest.raises(GatewayError,match='SHA binding'):
        collector(repo_root=source,macro_root_flag=str(macro),now=None,timeout=5)


def installed(f,tmp_path,runner=None):
    source=tmp_path/'source';source.mkdir();(source/'README.md').write_text('Synthetic installed source identity\n')
    git(source,'init','-q');git(source,'add','.');git(source,'commit','-m','Source identity')
    return InstalledBootPacketCollector(source_root=source,macro_root=f.env.clone,code_root=ROOT,
        python_executable=Path(PYTHON_BINARY),expected_source_sha=rev_parse(source,'HEAD'),runner=runner)


def test_real_collector_materializes_data_only_after_canonical_landing_and_keeps_code_pin(ready,tmp_path):
    f=ready;collector=installed(f,tmp_path)
    reader=collector.project_knowledge_catalogue_reader(macro_root=f.env.clone)
    fixed=reader.read(work_ref='WS:DEMO')
    assert fixed['source']['commit']==f.base and 'data_observation' not in fixed
    proposal=f.publish()
    assert proposal['state']=='PROPOSAL_PUBLISHED'
    with collector.canonical_project_data_scope(f.observe(),work_ref='WS:DEMO'):
        before=reader.read(work_ref='WS:DEMO')
    assert before['source']['commit']==f.base
    f.land()
    view=f.observe()
    assert view.data_commit!=f.base
    with collector.canonical_project_data_scope(view,work_ref='WS:DEMO'):
        after=reader.read(work_ref='WS:DEMO')
    assert after['source']['commit']==view.data_commit
    assert after['data_observation']['executable_macro_commit']==f.base
    image=next(i for i in f.recipe['postimages'] if i['path'].startswith('agentos/project-files/'))
    row=next(i for i in after['project']['files'] if i['path']==image['path'])
    source_reader=collector.project_knowledge_source_reader(macro_root=f.env.clone)
    with collector.canonical_project_data_scope(f.observe(),work_ref='WS:DEMO'):
        body=source_reader.read(work_ref='WS:DEMO',source_ref=row['source_ref'],expected_revision=row['revision'])
    assert body['document']['content_utf8']==image['content_utf8']
    assert rev_parse(f.env.clone,'HEAD')==f.base
    assert reader.read(work_ref='WS:DEMO')==fixed


def test_nominal_data_scope_masks_late_grant_withdrawal_and_foreign_work(ready,tmp_path):
    f=ready;f.land();view=f.observe()
    collector=installed(f,tmp_path)
    with pytest.raises(ValueError):
        with collector.canonical_project_data_scope(view,work_ref='WS:FOREIGN'):pass
    from integrations.executive_mcp.installed import _default_packet_runner
    def runner(argv,**kwargs):
        result=_default_packet_runner(argv,**kwargs)
        if str(argv[0])!='git' and 'agentos_project_knowledge_entry.py' in str(argv[3]):f.state.data=False
        return result
    collector._runner=runner
    with pytest.raises(ValueError):
        with collector.canonical_project_data_scope(view,work_ref='WS:DEMO'):
            collector.read_project_knowledge_catalogue(work_ref='WS:DEMO')
    assert rev_parse(f.env.clone,'HEAD')==f.base
