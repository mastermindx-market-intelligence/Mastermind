import asyncio
import dataclasses
from datetime import datetime, timezone
import pytest
from integrations.executive_content_contract import ContentObserverProfile, digest, ACCESS_SCHEMA, PAGE_SCHEMA
from control_plane.executive_content_observer import ExecutiveContentObserver


def profile(**changes):
    data = dict(schema='mastermind.executive_content_profile.v1',installation_id='install',installation_generation='one',
        permission_digest='b'*64,policy_id='content',content_resource='https://app/content',content_scope='mastermind.workspace.content.read',issuer_digest='c'*64,subject_digest='d'*64,client_ref='client',
        source_ref='managed-window:canary',job_id='job',attempt_id='attempt',session_epoch_id='epoch',
        process_generation_id='generation',local_turn_id='local',operation_id='owner-op',
        expires_at='2026-09-22T00:00:00Z',content_decision='allowed_visible_response',release_sha='e'*40)
    data.update(changes)
    data['viewer_binding_digest'] = digest({k:data[k] for k in ('policy_id','issuer_digest','subject_digest','client_ref')})
    data['profile_digest'] = digest(data)
    return ContentObserverProfile.from_mapping(data)


def test_profile_rejects_mutation_unavailable_client_and_unknown_fields():
    good = dataclasses.asdict(profile())
    for changed in (dict(good,source_ref='managed-window:other'),dict(good,client_ref='oauth-client-unavailable'),dict(good,extra=True)):
        with pytest.raises(ValueError):
            ContentObserverProfile.from_mapping(changed)


def test_unavailable_runtime_and_malformed_reads_never_enroll():
    class Broker:
        async def request(self,*args):
            raise AssertionError('must not reach broker without Runtime')
    observer = ExecutiveContentObserver(runtime=None, broker_client=Broker(), profile_loader=profile, now=lambda:1789977600)
    async def run():
        assert (await observer.handle_frame({'schema':ACCESS_SCHEMA}))['error']['code'] == 'INVALID_REQUEST'
        p=profile()
        request=dict(schema=ACCESS_SCHEMA,profile_digest=p.profile_digest,source_ref=p.source_ref,viewer_binding_digest=p.viewer_binding_digest)
        assert (await observer.handle_frame(request))['error']['code']=='CONTENT_UNAVAILABLE'
    asyncio.run(run())
