"""Synthetic inert packaging, no installation or real configuration writes."""
import hashlib,json,subprocess
from pathlib import Path
import pytest
from ops.research_read_tunnel import stage
from tests.research_read_mcp.test_stage import repository,UNIT
ROOT=Path(stage.__file__).parents[2]
SOURCES={p:(ROOT/p).read_text() for p in ('ops/research_read_tunnel/mastermind-research-citation.socket','ops/research_read_tunnel/mastermind-research-read-citation.conf','ops/research_read_tunnel/research-citation.tmpfiles.conf','ops/research_read/research_evidence_http.caddy.fragment')}
def params(**changes):
    v=dict(caddy_uid=999,caddy_gid=988,os_relay_port=3081);v.update(changes);return stage.CitationProposalParameters(**v)
def pair(tmp_path,changes=None):
    files={'common/__init__.py':'','control_plane/__init__.py':'','integrations/__init__.py':'',stage.SERVER_PATH:'# synthetic launcher\n',stage.LOCK_PATH:'# synthetic lock\n',stage.UNIT_PATH:UNIT,**SOURCES};files.update(changes or {})
    mm,mc,mt=repository(tmp_path/'mm',files);macro,ac,at=repository(tmp_path/'macro',{'engine/code.py':'SYNTHETIC=1\n'})
    return dict(mastermind_source=mm,mastermind_commit=mc,mastermind_tree=mt,macro_source=macro,macro_commit=ac,macro_tree=at,macro_roots=['engine'],output=tmp_path/'bundle')
@pytest.mark.parametrize('change',[{'caddy_uid':True},{'caddy_uid':0},{'caddy_uid':-1},{'caddy_uid':2**31},{'caddy_gid':'988'},{'caddy_gid':False},{'caddy_gid':0},{'os_relay_port':True},{'os_relay_port':0},{'os_relay_port':65536},{'os_relay_port':'3081'}])
def test_parameters_closed(change):
    with pytest.raises(stage.StageRefused):params(**change)
def test_render_exact_deterministic():
    for p,t in SOURCES.items():
        a=stage.render_citation_proposal(p,t,parameters=params(),commit='a'*40,lock_sha256='b'*64)
        assert a==stage.render_citation_proposal(p,t,parameters=params(),commit='a'*40,lock_sha256='b'*64)
        assert a==t.replace('__QUALIFIED_CADDY_UID__','999').replace('__QUALIFIED_CADDY_GID__','988').replace('__OS_RELAY_PORT__','3081').replace('@MASTERMIND_COMMIT@','a'*40).replace('@LOCK_SHA256@','b'*64)
        assert '__QUALIFIED_' not in a and '__OS_RELAY_PORT__' not in a and '@LOCK_' not in a and '@MASTERMIND_' not in a
        if p.endswith('.fragment'):assert 'no file-only reload' in a and 'Active/autosaved Caddy overlay' in a
@pytest.mark.parametrize('path,template',[('../secret','private'),('/etc/systemd/evil','private'),('ops/research_read_tunnel/mastermind-research-citation.socket',SOURCES['ops/research_read_tunnel/mastermind-research-citation.socket']+'ExecStartPost=/bin/true\n'),('ops/research_read/research_evidence_http.caddy.fragment',SOURCES['ops/research_read/research_evidence_http.caddy.fragment'].replace('unix//run/','unix//tmp/'))])
def test_changed_template_arbitrary_path_refused(path,template):
    with pytest.raises(stage.StageRefused):stage.render_citation_proposal(path,template,parameters=params(),commit='a'*40,lock_sha256='b'*64)
def test_members_hash_source_binding_roots_unchanged(tmp_path):
    k=pair(tmp_path);roots=stage.MASTERMIND_ROOTS;m=stage.prepare_bundle(**k,citation_parameters=params());p=json.loads((k['output']/'research-citation-proposals.json').read_text())
    assert stage.MASTERMIND_ROOTS==roots and len(m['files'])==8 and p['state']=='INERT_PROPOSAL' and len(p['members'])==4
    assert p['parameters']=={'caddy_uid':999,'caddy_gid':988,'os_relay_port':3081}
    assert not any(x['path'].startswith('ops/') for x in m['members']['mastermind'])
    for x in p['members']:
        raw=(k['output']/x['path']).read_bytes();assert x['source_sha256']==hashlib.sha256(SOURCES[x['source_path']].encode()).hexdigest();assert x['sha256']==hashlib.sha256(raw).hexdigest() and x['bytes']==len(raw)
        assert {z:x[z] for z in ('path','bytes','sha256')} in m['files'];assert (k['output']/x['path']).stat().st_mode&0o777==0o600
    assert json.loads((k['output']/'manifest.json').read_text())==m and k['output'].stat().st_mode&0o777==0o700
    with pytest.raises(stage.StageRefused,match='STAGE_OUTPUT_REFUSED'):stage.prepare_bundle(**k,citation_parameters=params())
def test_default_unchanged(tmp_path):
    m=stage.prepare_bundle(**pair(tmp_path));assert 'citation_proposals' not in m;assert [x['path'] for x in m['files']]==['mastermind-release.tar','macro-release.tar','mastermind-research-read.service']
def test_collision_retains_bytes_without_partial_output(tmp_path):
    k=pair(tmp_path);k['output'].mkdir();p=k['output']/'mastermind-research-citation.socket';p.write_text('RETAINED')
    with pytest.raises(stage.StageRefused,match='STAGE_OUTPUT_REFUSED'):stage.prepare_bundle(**k,citation_parameters=params())
    assert p.read_text()=='RETAINED' and list(k['output'].iterdir())==[p]
def test_dirty_still_refused(tmp_path):
    k=pair(tmp_path);(k['mastermind_source']/'untracked.env').write_text('SYNTHETIC')
    with pytest.raises(stage.StageRefused,match='STAGE_SOURCE_DIRTY'):stage.prepare_bundle(**k,citation_parameters=params())
    assert not k['output'].exists()
def test_changed_committed_template_no_partial_output(tmp_path):
    p=next(iter(SOURCES));k=pair(tmp_path,{p:SOURCES[p]+'# unreviewed\n'})
    with pytest.raises(stage.StageRefused,match='STAGE_PROPOSAL_REFUSED'):stage.prepare_bundle(**k,citation_parameters=params())
    assert not k['output'].exists()
def test_symlink_member_refused(tmp_path):
    k=pair(tmp_path);s=k['mastermind_source'];p=s/next(iter(SOURCES));p.unlink();p.symlink_to('mastermind-research-read.service');subprocess.run(['git','-C',str(s),'add','.'],check=True);subprocess.run(['git','-C',str(s),'-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-qm','symlink'],check=True)
    k['mastermind_commit']=subprocess.check_output(['git','-C',str(s),'rev-parse','HEAD']).decode().strip();k['mastermind_tree']=subprocess.check_output(['git','-C',str(s),'rev-parse','HEAD^{tree}']).decode().strip()
    with pytest.raises(stage.StageRefused,match='STAGE_PROPOSAL_REFUSED'):stage.prepare_bundle(**k,citation_parameters=params())
    assert not k['output'].exists()

def test_internal_member_name_collision_refuses_before_emission(tmp_path,monkeypatch):
    k=pair(tmp_path);rows=list(stage.CITATION_PROPOSALS);rows[1]=(rows[1][0],rows[0][1],rows[1][2]);monkeypatch.setattr(stage,'CITATION_PROPOSALS',tuple(rows))
    with pytest.raises(stage.StageRefused,match='STAGE_PROPOSAL_REFUSED'):stage.prepare_bundle(**k,citation_parameters=params())
    assert not k['output'].exists()

@pytest.mark.parametrize('mode',['missing','executable'])
def test_missing_or_executable_template_refuses_before_emission(tmp_path,mode):
    k=pair(tmp_path);s=k['mastermind_source'];p=s/next(iter(SOURCES))
    if mode=='missing':p.unlink()
    else:p.chmod(0o755)
    subprocess.run(['git','-C',str(s),'add','.'],check=True);subprocess.run(['git','-C',str(s),'-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-qm',mode],check=True)
    k['mastermind_commit']=subprocess.check_output(['git','-C',str(s),'rev-parse','HEAD']).decode().strip();k['mastermind_tree']=subprocess.check_output(['git','-C',str(s),'rev-parse','HEAD^{tree}']).decode().strip()
    with pytest.raises(stage.StageRefused,match='STAGE_PROPOSAL_REFUSED'):stage.prepare_bundle(**k,citation_parameters=params())
    assert not k['output'].exists()

def test_symlink_output_parent_refuses_without_touching_target(tmp_path):
    k=pair(tmp_path);target=tmp_path/'target';target.mkdir();link=tmp_path/'link';link.symlink_to(target,target_is_directory=True);k['output']=link/'candidate'
    with pytest.raises(stage.StageRefused,match='STAGE_OUTPUT_REFUSED'):stage.prepare_bundle(**k,citation_parameters=params())
    assert list(target.iterdir())==[]

@pytest.mark.parametrize('commit,lock',[('unresolved','b'*64),('a'*40,'@LOCK_SHA256@'),(True,'b'*64)])
def test_invalid_pin_fields_refused(commit,lock):
    p=next(iter(SOURCES))
    with pytest.raises(stage.StageRefused,match='STAGE_PROPOSAL_REFUSED'):stage.render_citation_proposal(p,SOURCES[p],parameters=params(),commit=commit,lock_sha256=lock)


def test_closed_manifest_existing_release_verifier_accepts_extra_hashed_files(tmp_path):
    import io,os,tarfile
    from integrations.research_read_mcp.release_identity import verify_archive_release,_MANIFEST_FIELDS
    k=pair(tmp_path);m=stage.prepare_bundle(**k,citation_parameters=params())
    assert set(m)==_MANIFEST_FIELDS
    release=tmp_path/'installed-fixture'/k['macro_commit'];release.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO((k['output']/'macro-release.tar').read_bytes())) as archive:archive.extractall(release,filter='data')
    receipt=verify_archive_release(path=str(release),commit=k['macro_commit'],tree=k['macro_tree'],project='macro',manifest_path=str(k['output']/'manifest.json'),expected_manifest_sha256=hashlib.sha256((k['output']/'manifest.json').read_bytes()).hexdigest(),manifest_owner_uid=os.geteuid(),release_owner_uid=os.geteuid())
    assert receipt['state']=='ARCHIVE_BYTES_VERIFIED'
    # Installed-source verifier checks archive members, not proposal installation.
    assert receipt['member_count']==len(m['members']['macro'])


def argv(k):
    result=[]
    for name in ('mastermind_source','mastermind_commit','mastermind_tree','macro_source','macro_commit','macro_tree','output'):
        result+=['--'+name.replace('_','-'),str(k[name])]
    return result+['--macro-root','engine']

@pytest.mark.parametrize('enabled',[False,True])
def test_cli_same_bundle_and_explicit_optional_fields(tmp_path,capsys,enabled):
    k=pair(tmp_path);args=argv(k)
    if enabled:args+=['--caddy-uid','999','--caddy-gid','988','--os-relay-port','3081']
    assert stage.main(args)==0
    m=json.loads(capsys.readouterr().out);assert m==json.loads((k['output']/'manifest.json').read_text())
    assert set(m)=={'schema','state','mastermind_commit','mastermind_tree','macro_commit','macro_tree','dependency_lock_sha256','macro_import_closure','files','members'}
    assert len(m['files'])==(8 if enabled else 3)

@pytest.mark.parametrize('partial',[['--caddy-uid','999'],['--caddy-gid','988','--os-relay-port','3081']])
def test_partial_cli_parameters_refuse_before_source_io(tmp_path,monkeypatch,partial):
    k=pair(tmp_path);monkeypatch.setattr(stage,'qualify_source',lambda *a:pytest.fail('partial CLI performed source IO'))
    with pytest.raises(SystemExit) as error:stage.main(argv(k)+partial)
    assert error.value.code==2 and not k['output'].exists()

def test_module_cli_entrypoint_emits_the_same_inert_bundle(tmp_path):
    import sys
    k=pair(tmp_path)
    result=subprocess.run([sys.executable,'-m','ops.research_read_tunnel.stage',*argv(k),'--caddy-uid','999','--caddy-gid','988','--os-relay-port','3081'],capture_output=True,text=True,check=True,timeout=30)
    manifest=json.loads(result.stdout)
    assert manifest==json.loads((k['output']/'manifest.json').read_text())
    assert manifest['state']=='INERT_CANDIDATE' and len(manifest['files'])==8
