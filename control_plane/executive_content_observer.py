"""Control-UID content observations joined to the existing Runtime and broker.

Configuration is reread by the installed sealed-config loader; no read enrolls a
viewer. This owner does not load provider credentials or render source content.
"""
from dataclasses import asdict
from integrations.executive_content_contract import (
    ContentObserverProfile, ACCESS_SCHEMA, PAGE_SCHEMA, ERRORS, MAX_PAGE_BYTES,
    canonical, digest, epoch,
)


class ContentRefused(ValueError):
    def __init__(self, code):
        self.code = code if code in ERRORS else 'CONTENT_UNAVAILABLE'
        super().__init__(self.code)


class ExecutiveContentObserver:
    def __init__(self, *, runtime, broker_client, profile_loader, now):
        self.runtime = runtime
        self.broker = broker_client
        self.profile_loader = profile_loader
        self.now = now

    def _profile(self, *, allow_expired=False):
        try:
            value = self.profile_loader()
            p = value.validated() if type(value) is ContentObserverProfile else ContentObserverProfile.from_mapping(value)
            current = self.now()
            if type(current) is not int or (not allow_expired and current >= epoch(p.expires_at)):
                raise ContentRefused('ACCESS_DENIED')
            return p
        except ContentRefused:
            raise
        except Exception:
            raise ContentRefused('ACCESS_DENIED') from None

    def _join(self, p):
        # Exact bounded joins, never an App-supplied SQL/source selector. Both
        # TX-5 intent and acknowledged APPLIED must match this current writer.
        with self.runtime.store.read() as connection:
            row = connection.execute('''
                SELECT a.worker_id,a.status,a.fence_generation,a.lease_expires_at_ms,
                       a.execution_mode,j.current_attempt_id,j.status AS job_status,
                       e.state,e.worker_id AS epoch_worker,e.provider_session_id,
                       g.generation_number,g.worker_id AS generation_worker,
                       g.executive_writer_held,g.provider_writer_state,g.ended_at_ms
                FROM attempts a JOIN jobs j ON j.job_id=a.job_id
                JOIN harness_session_epochs e ON e.attempt_id=a.attempt_id
                JOIN process_generations g ON g.session_epoch_id=e.session_epoch_id
                WHERE a.job_id=? AND a.attempt_id=? AND e.session_epoch_id=?
                  AND g.process_generation_id=?
            ''',(p.job_id,p.attempt_id,p.session_epoch_id,p.process_generation_id)).fetchone()
            if (row is None or row['status'] not in ('RUNNING','CHECKPOINTED')
                    or row['job_status'] not in ('RUNNING','CHECKPOINTED')
                    or row['current_attempt_id'] != p.attempt_id
                    or row['execution_mode'] != 'OPERATOR_HARNESS'
                    or row['state'] != 'CURRENT' or not row['executive_writer_held']
                    or row['provider_writer_state'] != 'HELD' or row['ended_at_ms'] is not None
                    or row['worker_id'] != row['epoch_worker'] or row['worker_id'] != row['generation_worker']
                    or not row['provider_session_id']
                    or row['lease_expires_at_ms'] <= self.runtime.store.now_ms()):
                raise ContentRefused('GRANT_INVALIDATED')
            # A worker-wide quarantine is authoritative even when its latest
            # generation still appears current in a stale installation profile.
            if connection.execute("SELECT 1 FROM events WHERE event_type='OHF_RESTORE_INVALIDATED' AND worker_id=? LIMIT 1",(row['worker_id'],)).fetchone():
                raise ContentRefused('GRANT_INVALIDATED')
            turns = connection.execute('''
                SELECT aggregate_id,event_type,payload_json FROM events
                WHERE aggregate_type='operator_operation' AND attempt_id=?
                  AND event_type IN ('OPERATOR_OPERATION_INTENT','OPERATOR_OPERATION_APPLIED')
                  AND json_extract(payload_json,'$.operation_kind')='begin_turn'
                  AND json_extract(payload_json,'$.turn_id')=? LIMIT 3
            ''',(p.attempt_id,p.local_turn_id)).fetchall()
            import json
            if len(turns) != 2 or {t['event_type'] for t in turns} != {'OPERATOR_OPERATION_INTENT','OPERATOR_OPERATION_APPLIED'} or len({t['aggregate_id'] for t in turns}) != 1:
                raise ContentRefused('GRANT_INVALIDATED')
            native = None
            for t in turns:
                data = json.loads(t['payload_json'])
                if any(data.get(k) != v for k,v in {'attempt_id':p.attempt_id,'session_epoch_id':p.session_epoch_id,'process_generation_id':p.process_generation_id,'turn_id':p.local_turn_id}.items()):
                    raise ContentRefused('GRANT_INVALIDATED')
                if t['event_type']=='OPERATOR_OPERATION_INTENT' and (data.get('worker_id')!=row['worker_id'] or data.get('provider_session_id')!=row['provider_session_id']):
                    raise ContentRefused('GRANT_INVALIDATED')
                if t['event_type']=='OPERATOR_OPERATION_APPLIED':
                    if data.get('acknowledged') is not True:
                        raise ContentRefused('GRANT_INVALIDATED')
                    native = data.get('provider_native_turn_id')
            if not isinstance(native,str) or not 1<=len(native)<=256:
                raise ContentRefused('GRANT_INVALIDATED')
            if connection.execute("SELECT 1 FROM events WHERE aggregate_type='operator_operation' AND aggregate_id=? AND event_type='OPERATOR_OPERATION_EFFECT_UNKNOWN' LIMIT 1",(turns[0]['aggregate_id'],)).fetchone():
                raise ContentRefused('GRANT_INVALIDATED')
        return dict(attempt_id=p.attempt_id,session_epoch_id=p.session_epoch_id,
                    process_generation_id=p.process_generation_id,generation_number=row['generation_number'],
                    worker_id=row['worker_id'],local_turn_id=p.local_turn_id,native_turn_id=native)

    async def _access(self, p):
        key = self._join(p)
        status = await self.broker.request('ohf-observer-status',p.broker_payload())
        if (set(status) != {'status','reader_grant','turn_key','grant_generation'}
                or status['status']!='ACTIVE' or status['turn_key']!=key
                or not isinstance(status['reader_grant'],str) or not status['reader_grant']
                or not isinstance(status['grant_generation'],str) or not status['grant_generation']):
            raise ContentRefused('GRANT_INVALIDATED')
        if self._profile()!=p or self._join(p)!=key:
            raise ContentRefused('ACCESS_CHANGED')
        ticket = digest(dict(profile=asdict(p),turn_key=key,grant_generation=status['grant_generation']))
        return dict(ticket_digest=ticket,retained_scope=[key['process_generation_id'],key['native_turn_id']],expires_at=p.expires_at), status

    async def handle_frame(self, frame):
        try:
            if type(frame) is not dict or frame.get('schema') not in (ACCESS_SCHEMA,PAGE_SCHEMA):
                raise ContentRefused('INVALID_REQUEST')
            expected={'schema','profile_digest','source_ref','viewer_binding_digest'}
            if frame['schema']==PAGE_SCHEMA:
                expected |= {'access_ticket_digest','cursor','max_items'}
            if set(frame)!=expected:
                raise ContentRefused('INVALID_REQUEST')
            p = self._profile()
            if any(frame[k]!=p.frame(frame['schema'])[k] for k in ('profile_digest','source_ref','viewer_binding_digest')):
                raise ContentRefused('ACCESS_DENIED')
            before, status = await self._access(p)
            if frame['schema']==ACCESS_SCHEMA:
                return {'ok':True,'access':before}
            if (frame['access_ticket_digest'] != before['ticket_digest']
                    or type(frame['max_items']) is not int or not 1<=frame['max_items']<=64
                    or not (frame['cursor'] is None or type(frame['cursor']) is str and len(frame['cursor'])<=2048)):
                raise ContentRefused('INVALID_REQUEST')
            page = await self.broker.request('ohf-observe-turn',dict(p.broker_payload(),reader_grant=status['reader_grant'],cursor=frame['cursor'],max_items=frame['max_items']))
            after, _ = await self._access(p)
            if before != after:
                raise ContentRefused('ACCESS_CHANGED')
            result={'ok':True,'page':page}
            if len(canonical(result))+1>MAX_PAGE_BYTES:
                raise ContentRefused('OVER_BUDGET')
            return result
        except ContentRefused as exc:
            return {'ok':False,'error':{'code':exc.code}}
        except Exception:
            return {'ok':False,'error':{'code':'CONTENT_UNAVAILABLE'}}

    def _audit(self, p, phase, result=None):
        # Existing Runtime event owner; only opaque binding digests are payload.
        with self.runtime.store.transaction() as connection:
            self.runtime.store.append_event(connection,aggregate_type='content_observer',
                aggregate_id=digest(p.operation_id),event_type='CONTENT_OBSERVER_'+phase,
                job_id=p.job_id,attempt_id=p.attempt_id,payload={
                    'profile_digest':p.profile_digest,'permission_digest':p.permission_digest,
                    'viewer_binding_digest':p.viewer_binding_digest,
                    'result_digest':digest(result) if result is not None else None})

    async def _lifecycle(self, operation):
        p=self._profile(allow_expired=operation!='enroll')
        self._join(p)
        if operation=='enroll':
            with self.runtime.store.read() as connection:
                prior=connection.execute("SELECT 1 FROM events WHERE aggregate_type='content_observer' AND aggregate_id=? AND event_type='CONTENT_OBSERVER_ENROLL_INTENT' LIMIT 1",(digest(p.operation_id),)).fetchone()
            if prior:
                existing=await self.broker.request('ohf-observer-status',p.broker_payload())
                if existing.get('status')=='ABSENT':
                    raise ContentRefused('GRANT_INVALIDATED')
                return existing
        # Explicit calls only. Status has no mutation, while intent survives a
        # lost broker response and the same operation's status reconciles it.
        if operation!='status':
            self._audit(p,operation.upper()+'_INTENT')
        result=await self.broker.request('ohf-observer-'+operation,p.broker_payload())
        if operation!='status':
            self._audit(p,operation.upper()+'_RESULT',result)
        return result

    async def enroll(self):
        return await self._lifecycle('enroll')

    async def status(self):
        return await self._lifecycle('status')

    async def revoke(self):
        return await self._lifecycle('revoke')
