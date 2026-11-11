"""Metadata-only protected mode in the incumbent economic/lease owner.

The existing operator bearer reserves an original child count. The installed
Control service subsequently matches that exact pre-input reservation, and the
real Broker acquires a NEW paid lease. No packet/result/key is accepted here.
Kernel/installed caller qualification belongs to the fixed paid bridge, not
these comparison dictionaries. No new table, scheduler, allowance or router.
"""
from __future__ import annotations
import json
import os
import re
import pool_ledger
import weakref
from dataclasses import dataclass

from fabric_operator_owner import OperatorOwner, canonical, digest, refuse, validate_child_admission
from lease_broker import Broker

SCHEMA = 'mastermind.protected_memory_economic.v1'
WRAPPER = 'mastermind.fabric_bound_child_authorization.v3'
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_INVOCATIONS=weakref.WeakKeyDictionary()

class RootEconomicInvocation:
    __slots__=('__weakref__',)
    def __new__(cls):refuse('protected_memory_root_helper_required')

@dataclass(frozen=True)
class _Invocation:
    connection:object
    peer:object
    scope:str
    pid:int

def root_helper_invocation(connection,request):
    """Kernel-root parent of this fixed helper, NOT Linux/source authority."""
    import socket
    from control_plane.executive_peer_identity import capture_peer_identity,_current_capture
    if os.geteuid()!=501 or type(connection) is not socket.socket:refuse('protected_memory_root_helper_required')
    actual=capture_peer_identity(connection)
    if actual.euid!=0 or actual.pid!=os.getppid():refuse('protected_memory_root_helper_required')
    _current_capture(actual)
    value=object.__new__(RootEconomicInvocation)
    _INVOCATIONS[value]=_Invocation(connection,actual,canonical(request),os.getpid())
    return value

def require_root_invocation(value,request):
    from control_plane.executive_peer_identity import _current_capture
    if type(value) is not RootEconomicInvocation or value not in _INVOCATIONS:refuse('protected_memory_root_helper_required')
    state=_INVOCATIONS[value]
    if state.pid!=os.getpid() or state.scope!=canonical(request):refuse('protected_memory_root_helper_required')
    _current_capture(state.peer)


def require_economic_policy(owner,request):
    import pick
    # Reuse the actual incumbent model-cost decision, not a copied cheap-model
    # allowlist or caller escalation/witness. Explicit fixed owner path avoids
    # a stale global picker cache or a root-release-relative config fallback.
    policy=pick.launch_policy('glm',request['task_class'],request['model'],
        task_complexity=request['task_complexity'],doc=pick.load_pools(
            str(owner.here.parent/'orch/fabric/pools.yaml')))
    if policy.get('allowed') is not True:refuse('protected_memory_economic_policy_refused')


def _hash(value):
    if type(value) is not str or _SHA.fullmatch(value) is None: refuse('protected_memory_economic_binding')


def validate_stored(value):
    if type(value) is not dict or set(value) != {'schema', 'economic'} or value['schema'] != WRAPPER:
        refuse('protected_memory_economic_binding')
    state = value['economic']
    if (type(state) is not dict or set(state) != {'schema', 'request', 'phase', 'input', 'launch', 'terminal'}
            or state['schema'] != SCHEMA or state['phase'] not in
            ('RESERVED', 'BOUND', 'CONSUMED', 'SETTLING', 'SETTLED')):
        refuse('protected_memory_economic_binding')
    for name in ('input', 'launch', 'terminal'):
        if state[name] is not None and type(state[name]) is not dict: refuse('protected_memory_economic_binding')
    if state['phase'] == 'RESERVED' and any(state[k] is not None for k in ('input', 'launch', 'terminal')):
        refuse('protected_memory_economic_binding')
    if state['phase']=='BOUND' and any(state[k] is not None for k in ('launch','terminal')):
        refuse('protected_memory_economic_binding')
    if state['phase']=='CONSUMED' and state['terminal'] is not None:refuse('protected_memory_economic_binding')
    if state['phase'] in ('SETTLING','SETTLED'):
        terminal=state['terminal']
        if (type(terminal) is not dict or set(terminal)!={'rc','result_sha256','result_bytes'}
                or type(terminal['rc']) is not int or not 0<=terminal['rc']<=255
                or type(terminal['result_bytes']) is not int or not 0<=terminal['result_bytes']<=65536):
            refuse('protected_memory_terminal_binding')
        _hash(terminal['result_sha256'])
    if state['phase'] != 'RESERVED':
        item = state['input']
        if type(item) is not dict or set(item) != {'input_sha256', 'input_bytes', 'body_sha256'}:
            refuse('protected_memory_economic_binding')
        _hash(item['input_sha256']); _hash(item['body_sha256'])
        if type(item['input_bytes']) is not int or not 1 <= item['input_bytes'] <= 65536:
            refuse('protected_memory_economic_binding')
    if state['phase'] in ('CONSUMED', 'SETTLING', 'SETTLED'):
        item = state['launch']
        if type(item) is not dict or set(item) != {'attempt_id', 'process_ref_sha256'}:
            refuse('protected_memory_economic_binding')
        from fabric_operator_owner import safe_id
        safe_id(item['attempt_id']); _hash(item['process_ref_sha256'])
    return state


class ProtectedMemoryEconomicOwner:
    """Constructed only behind the qualified fixed paid bridge composition.

    Actual nominal owners are required; dictionaries or fake broker callbacks
    cannot stand in for the incumbent count, account/quota and fair-share law.
    This class by itself grants neither Control identity nor Linux source use.
    """
    def __init__(self, owner, broker):
        if (type(owner) is not OperatorOwner or type(broker) is not Broker
                or os.path.realpath(broker.db_path) != str(owner.db.resolve())
                or os.path.realpath(broker.lock_path) != str(owner.lock.resolve())):
            refuse('protected_memory_economic_owner')
        self.owner, self.broker, self.ledger = owner, broker, pool_ledger

    def _read(self, con, selector, *, active=True):
        if type(selector) is not dict or set(selector) != {'root', 'parent', 'run_id', 'pre_input_sha256', 'profile_sha256'}:
            refuse('protected_memory_economic_binding')
        from fabric_operator_owner import safe_id
        for key in ('root', 'parent', 'run_id'): safe_id(selector[key])
        for key in ('pre_input_sha256', 'profile_sha256'): _hash(selector[key])
        row = con.execute('SELECT * FROM operator_child_authorizations WHERE run_id=? AND root=? AND operator_run=?',
            (selector['run_id'], selector['root'], selector['parent'])).fetchone()
        if row is None: refuse('protected_memory_economic_missing')
        from fabric_memory_view import _stored_row
        row = dict(row); wrapper = _stored_row(row); state = validate_stored(wrapper)
        if any(state['request'].get(k) != v for k, v in selector.items()): refuse('protected_memory_economic_binding')
        if active:
            # Reuse exactly the incumbent parent/current-grant law. For an
            # already-consumed child we validate the immutable pre-input copy
            # without granting or replaying a new child/provider invocation.
            original_phase = state['phase']
            if original_phase in ('CONSUMED', 'SETTLING', 'SETTLED'):
                if original_phase == 'SETTLED': refuse('protected_memory_original_recovery_only')
                grant_row = con.execute('SELECT * FROM operator_grants WHERE operator_run=? AND root=?',
                    (selector['parent'], selector['root'])).fetchone()
                if grant_row is None: refuse('operator_parent_grant_missing')
                grant, launch = json.loads(grant_row['grant_json']), json.loads(grant_row['launch_json'])
                root = con.execute('SELECT * FROM operator_root_grants WHERE root=?', (selector['root'],)).fetchone()
                now = self.owner.clock()
                if root is None or now >= root['expires']: refuse('root_grant_expired')
                from fabric_operator_contract import validate_protected_launch
                validate_protected_launch(grant, self.owner.lease(con, grant['lease_id']), launch,
                    state['request'], now=now, used_children=0, root_children_remaining=1)
                self._lease(con, row, selector)
            else:
                validate_child_admission(con, selector['run_id'], selector['root'], now=self.owner.clock(),
                    admitted_lease_id=row['admitted_lease_id'])
        return row, wrapper, state

    def _lease(self, con, row, selector):
        if not row['admitted_lease_id']: refuse('protected_memory_paid_lease_missing')
        lease = self.owner.lease(con, row['admitted_lease_id']); now = self.owner.clock()
        if (lease['orchestrator_id'] != selector['root'] or lease['state'] not in ('held', 'rented')
                or lease['task_class'] != 'remote-glm'
                or not lease['last_heartbeat'] <= now < lease['last_heartbeat'] + lease['ttl']):
            refuse('protected_memory_paid_lease_unavailable')
        return lease

    def _provider_current(self, con, lease):
        # Reuse the incumbent exact-account readiness/cooldown readers before
        # consumption. Holding a slot never overrides a subsequently withdrawn
        # account/host/model authorization or a newly retained hard cooldown.
        import quota_circuit
        from glm_host_account_source import filter_observed_accounts
        accounts=self.broker.grantable_accounts(lease['pool'])
        paths={}
        if self.broker.host_state_dir is not None:paths['state_dir']=self.broker.host_state_dir
        if self.broker.host_validator_path is not None:paths['validator_path']=self.broker.host_validator_path
        available,_=filter_observed_accounts(accounts,host=lease['host'],model=lease['model'],
            now=self.owner.clock(),preferred=lease['account'],hosts_path=self.broker.hosts_path,mode='glm',**paths)
        if (not any(row['name']==lease['account'] for row in available)
                or quota_circuit.capacity_blockade(self.broker,con,lease['pool'],lease['account']) is not None):
            refuse('protected_memory_paid_readiness_withdrawn')

    @staticmethod
    def _save(con, row, wrapper):
        raw = canonical(wrapper)
        con.execute('UPDATE operator_child_authorizations SET request_json=?,request_digest=? WHERE run_id=? AND request_digest=?',
            (raw, digest(raw.encode()), row['run_id'], row['request_digest']))
        if con.execute('SELECT changes()').fetchone()[0] != 1: refuse('protected_memory_economic_changed')

    def acquire(self, selector, route, *, controller_pid,delegation,authority):
        if type(controller_pid) is not int or controller_pid<=0:refuse('protected_memory_economic_owner')
        if (type(route) is not dict or set(route) != {'account', 'model', 'host'}
                or route['host'] != self.broker.this_host or route['model'] not in ('glm-5.3','glm-5.3-flash')):
            # Keep the incumbent granted pool/model/host laws; no cheap-model
            # relabel, alternate host or fresh route can rescue a refusal.
            refuse('protected_memory_economic_route')
        if (type(delegation) is not dict or set(delegation)!={'token','task_class','task_complexity','model'}
                or delegation['model']!=route['model']):refuse('protected_memory_economic_binding')
        request=dict(schema='mastermind.fabric_protected_memory_pre_input.v1',**selector,
            model=route['model'],task_class=delegation['task_class'],task_complexity=delegation['task_complexity'])
        require_root_invocation(authority,request)
        # The helper is invoked ONLY after fresh v3 qualification. No earlier
        # unqualified preauthorization row/count is reused or silently adopted.
        self.owner.reserve_protected_memory(delegation['token'],request,authority=authority)
        with self.owner.transaction() as con:
            row, _, state = self._read(con, selector)
            if route['model']!=state['request']['model']:refuse('protected_memory_economic_route')
            require_economic_policy(self.owner,state['request'])
            if row['admitted_lease_id'] is not None or state['phase'] != 'RESERVED':
                refuse('protected_memory_original_recovery_only')
        acquired = self.broker.acquire(selector['root'], 'glm', account=route['account'],
            host=route['host'], model=route['model'], pid=controller_pid, ttl=660,
            task_class='remote-glm', operator_child_id=selector['run_id'], wait=0,
            deadline_ns=__import__('time').monotonic_ns()+20_000_000_000)
        if not acquired.ok: refuse('protected_memory_paid_admission_refused')
        with self.owner.transaction() as con:
            row, _, _ = self._read(con, selector)
            lease = self._lease(con, row, selector)
            if any(lease[k] != v for k, v in route.items()): refuse('protected_memory_economic_route')
            return self._receipt(row, selector, 'ADMITTED')

    @staticmethod
    def _receipt(row, selector, phase):
        return {'schema': 'mastermind.protected_memory_economic_receipt.v1', **selector,
                'lease_id': row['admitted_lease_id'], 'phase': phase, 'retry_authorized': False}

    def current(self, selector):
        with self.owner.transaction() as con:
            row, _, state = self._read(con, selector)
            self._lease(con, row, selector)
            return self._receipt(row, selector, state['phase'])

    def require_route(self, selector, route, *, ready=True):
        if type(route) is not dict or set(route)!={'account','model','host'}:refuse('protected_memory_economic_route')
        with self.owner.transaction() as con:
            row, _, state=self._read(con,selector)
            lease=self._lease(con,row,selector)
            if route['host']!=self.broker.this_host or any(lease[k]!=v for k,v in route.items()):
                refuse('protected_memory_economic_route')
            if ready:
                require_economic_policy(self.owner,state['request'])
                self._provider_current(con,lease)

    def bind_input(self, selector, input_binding):
        with self.owner.transaction() as con:
            row, wrapper, state = self._read(con, selector)
            self._lease(con, row, selector)
            if state['phase'] != 'RESERVED': refuse('protected_memory_original_recovery_only')
            state['input'] = input_binding; state['phase'] = 'BOUND'; validate_stored(wrapper)
            self._save(con, row, wrapper)
            return self._receipt(row, selector, 'BOUND')

    def consume(self, selector, launch_binding):
        with self.owner.transaction() as con:
            row, wrapper, state = self._read(con, selector)
            lease=self._lease(con, row, selector)
            if state['phase'] != 'BOUND': refuse('protected_memory_original_recovery_only')
            require_economic_policy(self.owner,state['request'])
            self._provider_current(con,lease)
            state['launch'] = launch_binding; state['phase'] = 'CONSUMED'; validate_stored(wrapper)
            self._save(con, row, wrapper)
            # Unique committed consumption precedes private FD/provider release.
            return self._receipt(row, selector, 'CONSUMED')

    def heartbeat(self, selector):
        value = self.current(selector)
        if not self.broker.heartbeat(value['lease_id']).ok: refuse('protected_memory_paid_lease_unavailable')
        return self.current(selector)

    def settle(self, selector, terminal):
        if (type(terminal) is not dict or set(terminal) != {'rc', 'result_sha256', 'result_bytes'}
                or type(terminal['rc']) is not int or not 0 <= terminal['rc'] <= 255
                or type(terminal['result_bytes']) is not int or not 0 <= terminal['result_bytes'] <= 65536):
            refuse('protected_memory_terminal_binding')
        _hash(terminal['result_sha256'])
        with self.owner.transaction() as con:
            row, wrapper, state = self._read(con, selector)
            if state['phase'] == 'CONSUMED':
                state['phase'] = 'SETTLING'; state['terminal'] = terminal
                self._save(con, row, wrapper)
                first = True
            elif state['phase'] == 'SETTLING' and state['terminal'] == terminal:
                first = False
            else: refuse('protected_memory_original_recovery_only')
            lease = self._lease(con, row, selector)
        signal = 'ok' if terminal['rc'] == 0 else 'other'
        if first:
            # Existing ledger and original IDs, no acceptance or fabricated
            # token estimate. A failed append remains SETTLING/unknown.
            if not self.ledger.append(pool=lease['pool'], key=lease['account'],
                    model=lease['model'], task_class='remote-glm',job_class=state['request']['task_class'],
                    rc=terminal['rc'], signal=signal, run_id=selector['run_id'],
                    root_id=selector['root'], parent_run_id=selector['parent'],
                    reason='protected_memory_original_terminal', accepted_by=None,
                    tokens=None, input_tokens=None, cached_tokens=None, output_tokens=None,
                    usage_source='not_observed_by_protected_owner',
                    wall_s=max(0, self.owner.clock() - row['authorized_at']), strict=True):
                refuse('protected_memory_accounting_unknown')
        retained = self.ledger.read_execution_identity(selector['run_id'], expected_rc=terminal['rc'], expected_signal=signal)
        if retained != {'root_id': selector['root'], 'parent_run_id': selector['parent'], 'lineage_state': 'VERIFIED_TERMINAL'}:
            refuse('protected_memory_accounting_unknown')
        with self.owner.transaction() as con:
            row, wrapper, state = self._read(con, selector)
            if state['phase'] != 'SETTLING' or state['terminal'] != terminal:
                refuse('protected_memory_terminal_binding')
            state['phase'] = 'SETTLED'; self._save(con, row, wrapper)
        # Actual terminal accounting precedes release. Failure never refunds a
        # consumed child authorization or permits another provider invocation.
        if not self.broker.release(row['admitted_lease_id'], selector['root']):
            refuse('protected_memory_release_unknown')
        return self._receipt(row, selector, 'SETTLED')
