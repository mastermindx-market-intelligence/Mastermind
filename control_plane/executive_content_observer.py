"""Control-UID content observations joined to the existing Runtime and broker.

Configuration is reread by the installed sealed-config loader; no read enrolls a
viewer. This owner does not load provider credentials or render source content.
"""
from dataclasses import asdict
from common.executive_content_contract import (
    ContentObserverProfile, ContentObserverProfiles, ContentProfileKey,
    load_content_profiles, ACCESS_SCHEMA, PAGE_SCHEMA, ERRORS, MAX_PAGE_BYTES,
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

    def _profile(self, *, profile_key=None, profile_digest=None, allow_expired=False):
        try:
            value = load_content_profiles(self.profile_loader())
            if type(value) is ContentObserverProfile:
                if profile_key is not None:
                    raise ContentRefused('INVALID_REQUEST')
                profile = value
            else:
                if profile_digest is not None:
                    matches = [
                        slot.profile for slot in (value.web, value.mac)
                        if slot.enabled and slot.profile is not None
                        and slot.profile.profile_digest == profile_digest
                    ]
                    if len(matches) != 1:
                        raise ContentRefused('ACCESS_DENIED')
                    profile = matches[0]
                else:
                    if type(profile_key) is not ContentProfileKey:
                        raise ContentRefused('INVALID_REQUEST')
                    slot = getattr(value, profile_key.value)
                    if slot.profile is None or not slot.enabled and not allow_expired:
                        raise ContentRefused('ACCESS_DENIED')
                    profile = slot.profile
            if profile_digest is not None and profile.profile_digest != profile_digest:
                raise ContentRefused('ACCESS_DENIED')
            if not allow_expired:
                current = self.now()
                if type(current) is not int or current >= epoch(profile.expires_at):
                    raise ContentRefused('ACCESS_DENIED')
            return profile
        except ContentRefused:
            raise
        except Exception:
            raise ContentRefused('ACCESS_DENIED') from None

    def _join(self, p, *, live=True):
        # Exact bounded joins, never an App-supplied SQL/source selector. Both
        # TX-5 intent and acknowledged APPLIED must match this current writer.
        # ``live=False`` is the explicit status/revoke reconcile shape: the
        # durable identity rows must still bind this exact profile, but a lease
        # that expired or a writer/turn that since ceased does not hide an
        # existing bound grant from its owner. Enrollment and every read keep
        # ``live=True``; nothing ever enrolls or reads on a stale Runtime.
        with self.runtime.store.read() as connection:
            row = connection.execute('''
                SELECT a.worker_id,a.status,a.fence_generation,a.lease_expires_at_ms,
                       a.execution_mode,a.quota_class,j.current_attempt_id,j.status AS job_status,
                       e.state,e.worker_id AS epoch_worker,e.provider_session_id,
                       g.generation_number,g.worker_id AS generation_worker,
                       g.executive_writer_held,g.provider_writer_state,g.ended_at_ms,
                       q.held_attempt_id,q.fence_counter
                FROM attempts a JOIN jobs j ON j.job_id=a.job_id
                JOIN harness_session_epochs e ON e.attempt_id=a.attempt_id
                JOIN process_generations g ON g.session_epoch_id=e.session_epoch_id
                LEFT JOIN worker_quota_classes q ON q.worker_id=a.worker_id AND q.quota_class=a.quota_class
                WHERE a.job_id=? AND a.attempt_id=? AND e.session_epoch_id=?
                  AND g.process_generation_id=?
            ''',(p.job_id,p.attempt_id,p.session_epoch_id,p.process_generation_id)).fetchone()
            if (row is None
                    or row['execution_mode'] != 'OPERATOR_HARNESS'
                    or row['worker_id'] != row['epoch_worker'] or row['worker_id'] != row['generation_worker']):
                raise ContentRefused('GRANT_INVALIDATED')
            if live and (row['current_attempt_id'] != p.attempt_id
                    or row['status'] not in ('RUNNING','CHECKPOINTED')
                    or row['job_status'] not in ('RUNNING','CHECKPOINTED')
                    or row['state'] != 'CURRENT' or not row['executive_writer_held']
                    or row['provider_writer_state'] != 'HELD' or row['ended_at_ms'] is not None
                    or not row['provider_session_id']
                    or row['lease_expires_at_ms'] <= self.runtime.store.now_ms()
                    # Canonical capacity parity: the quota class this attempt
                    # occupies must still hold exactly this attempt at exactly
                    # the attempt's current fence.
                    or row['held_attempt_id'] != p.attempt_id
                    or row['fence_counter'] != row['fence_generation']):
                raise ContentRefused('GRANT_INVALIDATED')
            # A worker-wide quarantine is authoritative even when its latest
            # generation still appears current in a stale installation profile.
            if live and connection.execute("SELECT 1 FROM events WHERE event_type='OHF_RESTORE_INVALIDATED' AND worker_id=? LIMIT 1",(row['worker_id'],)).fetchone():
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
            if live and connection.execute("SELECT 1 FROM events WHERE aggregate_type='operator_operation' AND aggregate_id=? AND event_type='OPERATOR_OPERATION_EFFECT_UNKNOWN' LIMIT 1",(turns[0]['aggregate_id'],)).fetchone():
                raise ContentRefused('GRANT_INVALIDATED')
        # The turn key keeps the canonical TurnKey field set (never a lease
        # token); the current fence travels beside it into the access ticket.
        key = dict(attempt_id=p.attempt_id,session_epoch_id=p.session_epoch_id,
                   process_generation_id=p.process_generation_id,generation_number=row['generation_number'],
                   worker_id=row['worker_id'],local_turn_id=p.local_turn_id,native_turn_id=native)
        return key, row['fence_generation']

    async def _access(self, p):
        key, fence = self._join(p)
        status = await self.broker.request('ohf-observer-status',p.broker_payload())
        if (set(status) != {'status','reader_grant','turn_key','grant_generation'}
                or status['status']!='ACTIVE' or status['turn_key']!=key
                or not isinstance(status['reader_grant'],str) or not status['reader_grant']
                or not isinstance(status['grant_generation'],str) or not status['grant_generation']):
            raise ContentRefused('GRANT_INVALIDATED')
        if self._profile(profile_digest=p.profile_digest)!=p or self._join(p)!=(key,fence):
            raise ContentRefused('ACCESS_CHANGED')
        # The current fence is part of the ticket and of the before/after page
        # snapshot: a fence moved during a page refuses that page, while a
        # later fresh read may still observe the same turn once the current
        # lease and held writer reconcile.
        ticket = digest(dict(profile=asdict(p),turn_key=key,grant_generation=status['grant_generation'],
                             fence_generation=fence))
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
            p = self._profile(profile_digest=frame['profile_digest'])
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

    async def _lifecycle(self, operation, profile_key: ContentProfileKey | None = None):
        # Enrollment requires enabled profile; status/revoke allow disabled with retained binding.
        allow_disabled = operation != 'enroll'
        p = self._profile(profile_key=profile_key, allow_expired=allow_disabled)
        # Only enrollment demands the live writer. Explicit status/revoke
        # reconcile the exact existing bound grant across a Runtime whose
        # lease has since expired or whose turn has ceased; they never mint.
        self._join(p, live=operation == 'enroll')
        if operation == 'enroll':
            with self.runtime.store.read() as connection:
                prior = connection.execute(
                    "SELECT 1 FROM events WHERE aggregate_type='content_observer' AND aggregate_id=? AND event_type='CONTENT_OBSERVER_ENROLL_INTENT' LIMIT 1",
                    (digest(p.operation_id),)
                ).fetchone()
            if prior:
                existing = await self.broker.request('ohf-observer-status', p.broker_payload())
                if existing.get('status') == 'ABSENT':
                    raise ContentRefused('GRANT_INVALIDATED')
                return existing
        # Explicit calls only. Status has no mutation, while intent survives a
        # lost broker response and the same operation's status reconciles it.
        if operation != 'status':
            self._audit(p, operation.upper() + '_INTENT')
        result = await self.broker.request('ohf-observer-' + operation, p.broker_payload())
        if operation != 'status':
            self._audit(p, operation.upper() + '_RESULT', result)
        return result

    async def enroll(self, profile_key: ContentProfileKey | None = None):
        return await self._lifecycle('enroll', profile_key)

    async def status(self, profile_key: ContentProfileKey | None = None):
        return await self._lifecycle('status', profile_key)

    async def revoke(self, profile_key: ContentProfileKey | None = None):
        return await self._lifecycle('revoke', profile_key)
