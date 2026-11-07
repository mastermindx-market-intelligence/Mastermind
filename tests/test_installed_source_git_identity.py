"""Dormant fixed service identity: closed config, exact commands, no live gh.

Only filesystem sealing and authenticated API responses are explicit fixtures.
The actual constructor/currentness/qualifier/PR owner logic is exercised. This
is not credential, receipt installation or live GitHub proof.
"""
import copy
import hashlib
import json
from pathlib import Path

import pytest
from integrations.mastermind_workspace_app.project_git_identity import (
    InstalledProjectGitIdentity, validate_publisher_selection, _git_environment)
from control_plane.workspace_project_git_publisher import PrLookupForeign, PrLookupAmbiguous, PrOwnerUnknownOutcome


@pytest.fixture
def identity(tmp_path, monkeypatch):
    from ops.executive_os import executive_mcp_entry
    gh=tmp_path/'gh';gh.write_text('#!/bin/sh\nexit 99\n');gh.chmod(0o700)
    clone=tmp_path/'publisher-clone';clone.mkdir()
    value={'schema':'mastermind.workspace_source_publisher.v1','worktree':str(clone),
        'default_branch':'main','github_login':'service-bot','gh_binary':str(gh),
        'gh_sha256':hashlib.sha256(gh.read_bytes()).hexdigest(),'source_author_receipt_sha256':'a'*64}
    config=tmp_path/'control.json';config.write_text(json.dumps({'workspace_source_publication':value}))
    # The real root-sealing rejection is a separate negative below. This
    # fixture cannot qualify an installed principal/receipt/credential.
    monkeypatch.setattr(executive_mcp_entry,'require_sealed_path',lambda p:None)
    owner=InstalledProjectGitIdentity(config_path=config,expected_config_sha256=hashlib.sha256(config.read_bytes()).hexdigest())
    return owner,config,gh,value


def test_bare_user_owned_configuration_is_not_installed_authority(tmp_path):
    config=tmp_path/'control.json';config.write_text('{}')
    with pytest.raises((ValueError,OSError)):
        InstalledProjectGitIdentity(config_path=config,expected_config_sha256=hashlib.sha256(config.read_bytes()).hexdigest())


@pytest.mark.parametrize('field,value',[('worktree','relative'),('github_login','user/other'),('gh_binary','gh'),
    ('gh_sha256','g'*64),('source_author_receipt_sha256',None),('default_branch','main:other'),('schema','other')])
def test_closed_private_publisher_selection(identity,field,value):
    owner,config,gh,raw=identity
    with pytest.raises(ValueError):validate_publisher_selection(raw|{field:value})
    with pytest.raises(ValueError):validate_publisher_selection(raw|{'actor':'client'})


def test_changed_sealed_selection_or_executable_withholds_owner(identity):
    owner,config,gh,raw=identity
    gh.write_text('#!/bin/sh\nexit 0\n')
    assert owner.qualify(owner.binding) is False
    config.write_text(json.dumps({'workspace_source_publication':raw|{'github_login':'foreign'}}))
    with pytest.raises(ValueError):owner._current()


def test_git_selector_environment_is_sanitized_without_credential_output(monkeypatch):
    for key in ['GIT_DIR','GIT_WORK_TREE','GIT_CONFIG_COUNT','GIT_CONFIG_KEY_0','GIT_CONFIG_VALUE_0']:
        monkeypatch.setenv(key,'hostile')
    env=_git_environment()
    assert not any(k in env for k in ['GIT_DIR','GIT_WORK_TREE','GIT_CONFIG_COUNT','GIT_CONFIG_KEY_0','GIT_CONFIG_VALUE_0'])
    assert env['GIT_NO_REPLACE_OBJECTS']=='1' and env['GIT_TERMINAL_PROMPT']=='0'


def test_git_and_gh_identity_must_match_same_configured_account(identity,monkeypatch):
    owner,config,gh,raw=identity
    monkeypatch.setattr(owner,'_has_unsafe_git_config',lambda:False)
    calls=[]
    def process(argv,**kwargs):
        calls.append(argv)
        return ('!'+str(gh)+' auth git-credential\n').encode() if argv[0]=='/usr/bin/git' else b'service-bot\n'
    monkeypatch.setattr(owner,'_process',process)
    assert owner.qualify(owner.binding)
    assert calls[-1]==[str(gh),'api','--hostname','github.com','user','--jq','.login']
    monkeypatch.setattr(owner,'_process',lambda argv,**kw: b'foreign\n')
    assert not owner.qualify(owner.binding)
    monkeypatch.setattr(owner,'_has_unsafe_git_config',lambda:True)
    assert not owner.qualify(owner.binding)


def test_fixed_pr_lookup_and_post_never_expose_private_content(identity,monkeypatch):
    owner,config,gh,raw=identity
    digest='b'*64;branch='mmos/knowledge-'+'c'*64
    item={'number':12,'html_url':'https://github.com/mastermindx-market-intelligence/macro/pull/12',
        'body':'Mastermind source operation SHA256: '+digest,
        'head':{'ref':branch,'sha':'d'*40,'repo':{'full_name':owner.binding.repository}},
        'base':{'ref':'main','repo':{'full_name':owner.binding.repository}}}
    calls=[]
    def api(path,*,payload=None):calls.append((path,payload));return [item] if payload is None else item
    monkeypatch.setattr(owner,'_api',api)
    assert owner.find(owner.binding,branch,digest)['number']==12
    assert 'per_page=2' in calls[-1][0] and calls[-1][1] is None
    assert owner.create(owner.binding,branch,'e'*40,digest)['head_commit']=='d'*40
    assert set(calls[-1][1])=={'head','base','title','body'}
    assert digest in calls[-1][1]['body']
    foreign=copy.deepcopy(item);foreign['head']['repo']['full_name']='foreign/repo'
    monkeypatch.setattr(owner,'_api',lambda *a,**kw:[foreign])
    with pytest.raises(PrLookupForeign):owner.find(owner.binding,branch,digest)
    monkeypatch.setattr(owner,'_api',lambda *a,**kw: (_ for _ in ()).throw(ValueError('private diagnostics')))
    with pytest.raises(PrLookupAmbiguous):owner.find(owner.binding,branch,digest)
    with pytest.raises(PrOwnerUnknownOutcome):owner.create(owner.binding,branch,'e'*40,digest)


@pytest.mark.parametrize('variable',['GIT_SSL_NO_VERIFY','GIT_SSL_CAINFO','GIT_SSL_CAPATH','GIT_PROXY_COMMAND'])
def test_ambient_connection_override_cannot_qualify_installed_identity(identity,monkeypatch,variable):
    owner,*_=identity
    monkeypatch.setenv(variable,'unqualified')
    with pytest.raises(ValueError):owner._current()
