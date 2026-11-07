"""Finite realm branch with explicit root-config/binary fixture seams.

Credential metadata is real; these fixtures do not claim actual enrollment.
"""
import dataclasses
import hashlib
import json
from contextlib import contextmanager
from types import SimpleNamespace
import os

import pytest

from control_plane import codex_provider_realm as realm
from control_plane import codex_worker
from tests.test_subscription_realm_owner import enrolled


@pytest.fixture
def attended(enrolled,monkeypatch):
    c=enrolled.config;bid='minimax-token-plan.claude-code-anthropic'
    c.update(harness_binding_id=bid,control_gid=450,
        subscription_realm_enrollment={'generation':2,'binding_id':bid},
        claude_binary=c['codex_binary'],claude_attestation_receipt=c['codex_attestation_receipt'],
        allowed_claude_versions=['2.1.0'])
    p=realm.Path(c['claude_binary']);st=p.stat()
    binary=dict(path=str(p),real_path=str(p),version='2.1.0',sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
        team_identifier=None,size=st.st_size,device=st.st_dev,inode=st.st_ino,mode=0o555,uid=0,gid=460,mtime_ns=st.st_mtime_ns)
    receipt=realm.Path(c['claude_attestation_receipt']);raw=json.dumps({'schema_version':'mastermind.attended_claude_binary/v1','binary':binary}).encode();receipt.write_bytes(raw);receipt.chmod(0o440)
    c['claude_attestation_sha256']=hashlib.sha256(raw).hexdigest()
    real_fstat=os.fstat;receipt_inode=receipt.stat().st_ino
    def root_receipt_fstat(fd):
        info=real_fstat(fd)
        if info.st_ino==receipt_inode:
            return SimpleNamespace(**{key:getattr(info,key) for key in dir(info) if key.startswith('st_') and key!='st_gid'},st_gid=460)
        return info
    monkeypatch.setattr(os,'fstat',root_receipt_fstat)
    original=realm._native_open
    @contextmanager
    def root_receipt(path,**kw):
        with original(path,**kw) as (fd,info):
            if path==receipt:info=SimpleNamespace(**{key:getattr(info,key) for key in dir(info) if key.startswith('st_') and key!='st_gid'},st_gid=460)
            yield fd,info
    monkeypatch.setattr(realm,'_native_open',root_receipt)
    monkeypatch.setattr(codex_worker,'_assert_binary_unchanged',lambda a:None)
    monkeypatch.delenv('CODEX_HOME',raising=False)
    return enrolled


def test_finite_observer_preserves_exact_nonsecret_abi(attended):
    value=attended.load().observe()
    assert set(value)=={'worker_id','control_uid','binding_id','profile_id','adapter_id','realm_config_sha256','realm_generation','catalog_digest'}
    assert value['adapter_id']=='claude-compatible-subscription'
    assert value['binding_id']=='minimax-token-plan.claude-code-anthropic'


@pytest.mark.parametrize('fault',['receipt_digest','receipt_schema','binary_drift','wrong_control_gid','version','claude_home','generation','public_credential','wrong_home'])
def test_finite_realm_refuses_exact_owner_drift(attended,monkeypatch,fault):
    c=attended.config
    if fault=='receipt_digest':c['claude_attestation_sha256']='0'*64
    if fault=='receipt_schema':
        p=realm.Path(c['claude_attestation_receipt']);p.unlink();p.write_text('{}')
    if fault=='binary_drift':monkeypatch.setattr(codex_worker,'_assert_binary_unchanged',lambda a:(_ for _ in ()).throw(codex_worker.BinaryAttestationError('fixture drift')))
    if fault=='wrong_control_gid':c['control_gid']=c['worker_gid']
    if fault=='version':c['allowed_claude_versions']=['wrong']
    if fault=='claude_home':monkeypatch.setenv('CLAUDE_CONFIG_DIR',str(attended.home.parent))
    if fault=='generation':c['subscription_realm_enrollment']['generation']=True
    if fault=='public_credential':attended.credential.chmod(0o644)
    if fault=='wrong_home':monkeypatch.setenv('HOME',str(attended.home.parent))
    with pytest.raises(realm.ProviderRealmError):attended.load()


@pytest.mark.parametrize('mode',[0o4555,0o2555,0o10555])
def test_privilege_changing_or_invalid_binary_mode_refuses(attended,mode):
    c=attended.config;p=realm.Path(c['claude_attestation_receipt'])
    row=json.loads(p.read_bytes());row['binary']['mode']=mode
    raw=json.dumps(row).encode();p.chmod(0o600);p.write_bytes(raw);p.chmod(0o440)
    c['claude_attestation_sha256']=hashlib.sha256(raw).hexdigest()
    with pytest.raises(realm.ProviderRealmError):attended.load()
