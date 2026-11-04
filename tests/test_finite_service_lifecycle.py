"""Hermetic fixed lifecycle tests; no actual service, root or provider effects."""
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import pytest

SOURCE = Path(__file__).resolve().parents[1]/'ops/executive_os/finite_service_lifecycle.py'
spec = importlib.util.spec_from_file_location('finite_lifecycle_subject', SOURCE)
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)
SHA = 'a'*40


class Host:
    def __init__(self, state='absent', override='default', fail=None):
        self.state, self.enabled = state, override
        self.pid = 812 if state == 'running' else None
        self.fail = fail
        self.calls = []
        self.sleeps = 0
        self.qualified = 0
        self.changed = False
        self.inert = False

    def hit(self, name):
        self.calls.append(name)
        if self.fail == name:
            raise subject.LifecycleError('injected')

    @contextmanager
    def qualified_interval(self, sha):
        self.hit('qualify')
        assert sha == SHA
        yield {'generation': 1}
        self.hit('unlock')

    def registration(self):
        self.hit('registration')
        return dict(state=self.state, pid=self.pid)

    def override(self):
        self.hit('override')
        return self.enabled

    def require_idle(self, snapshot, bridge_pid):
        self.hit('idle')
        assert bridge_pid in (None, 812)

    def recheck(self, snapshot):
        self.hit('recheck')
        if self.changed:
            raise subject.LifecycleError('source_changed')

    def modify(self, action):
        self.hit(action)
        if self.inert:
            return
        if action == 'enable': self.enabled = 'enabled'
        elif action == 'bootstrap': self.state = 'registered'
        elif action == 'kickstart': self.state, self.pid = 'running', 812
        elif action == 'disable': self.enabled = 'disabled'
        elif action == 'bootout': self.state, self.pid = 'absent', None

    def readiness(self, snapshot, current):
        self.hit('readiness')
        if current != dict(state='running', pid=812):
            raise subject.LifecycleError('not_ready')
        return {'pid': 812, 'generation': 22, 'groups': []}

    def pause(self): self.sleeps += 1


MODIFY = {'enable', 'bootstrap', 'kickstart', 'disable', 'bootout'}
def effects(host): return [x for x in host.calls if x in MODIFY]


def test_start_is_fixed_single_sequence_and_requires_live_readiness():
    host = Host()
    assert subject.run_lifecycle(host, 'start-finite', SHA)['state'] == 'READY'
    assert effects(host) == ['enable', 'bootstrap', 'kickstart']
    assert 'readiness' in host.calls and host.calls[-1] == 'unlock'


def test_stop_verifies_original_generation_and_proves_absence():
    host = Host('running', 'enabled')
    result = subject.run_lifecycle(host, 'stop-finite', SHA)
    assert result['state'] == 'ABSENT' and result['prior_readiness']['generation'] == 22
    assert effects(host) == ['disable', 'bootout']


@pytest.mark.parametrize('action,state,override', [
    ('start-finite','absent','enabled'), ('start-finite','running','enabled'),
    ('start-finite','registered','disabled'), ('stop-finite','absent','disabled'),
    ('stop-finite','running','disabled'), ('stop-finite','registered','enabled')])
def test_partial_or_occupied_state_is_not_adopted(action,state,override):
    host = Host(state,override)
    with pytest.raises(subject.LifecycleError) as error:
        subject.run_lifecycle(host,action,SHA)
    assert not error.value.effect_unknown and effects(host) == []


@pytest.mark.parametrize('failure', ['qualify','registration','override','idle','recheck'])
def test_each_precondition_fails_without_effect(failure):
    host = Host(fail=failure)
    with pytest.raises(subject.LifecycleError) as error:
        subject.run_lifecycle(host,'start-finite',SHA)
    assert not error.value.effect_unknown and effects(host) == []


@pytest.mark.parametrize('failure,expected', [('enable',['enable']),
    ('bootstrap',['enable','bootstrap']), ('kickstart',['enable','bootstrap','kickstart']),
    ('readiness',['enable','bootstrap','kickstart'])])
def test_start_failure_never_retries_cleans_up_or_proceeds(failure,expected):
    host = Host(fail=failure)
    with pytest.raises(subject.LifecycleError) as error:
        subject.run_lifecycle(host,'start-finite',SHA)
    assert error.value.effect_unknown and effects(host) == expected


@pytest.mark.parametrize('failure,expected', [('disable',['disable']), ('bootout',['disable','bootout'])])
def test_stop_failure_never_retries_or_restarts(failure,expected):
    host = Host('running','enabled',failure)
    with pytest.raises(subject.LifecycleError) as error:
        subject.run_lifecycle(host,'stop-finite',SHA)
    assert error.value.effect_unknown and effects(host) == expected


@pytest.mark.parametrize('state,override,expected', [('absent','disabled','ABSENT'), ('running','enabled','READY')])
def test_reconciliation_status_has_no_effect(state,override,expected):
    host = Host(state,override)
    assert subject.run_lifecycle(host,'status-finite',SHA)['state'] == expected
    assert not effects(host)


def test_registered_is_not_readiness():
    host = Host('registered','enabled')
    with pytest.raises(subject.LifecycleError): subject.run_lifecycle(host,'status-finite',SHA)
    assert not effects(host)


def test_zero_return_without_enable_postcondition_is_unknown():
    host = Host();host.inert = True
    with pytest.raises(subject.LifecycleError) as error: subject.run_lifecycle(host,'start-finite',SHA)
    assert error.value.effect_unknown and effects(host) == ['enable']


@pytest.mark.parametrize('action,state,override', [('start-finite','absent','default'), ('stop-finite','running','enabled')])
def test_async_observation_has_bounded_wait_and_no_repeat(action,state,override):
    host=Host(state,override);original=host.modify
    def modify(verb):
        if verb in {'kickstart','bootout'}: host.hit(verb)
        else: original(verb)
    host.modify=modify
    with pytest.raises(subject.LifecycleError) as error:subject.run_lifecycle(host,action,SHA)
    assert error.value.effect_unknown and host.sleeps == 30
    assert len(effects(host)) == len(set(effects(host)))


def test_source_change_after_start_is_unknown_and_not_rolled_back():
    host=Host();original=host.readiness
    def ready(*args):host.changed=True;return original(*args)
    host.readiness=ready
    with pytest.raises(subject.LifecycleError) as error:subject.run_lifecycle(host,'start-finite',SHA)
    assert error.value.effect_unknown and effects(host)==['enable','bootstrap','kickstart']


@pytest.mark.parametrize('action,sha', [('arbitrary',SHA),('start-finite','x'*40),('start-finite',1),('start-finite',SHA+'\n')])
def test_argument_drift_never_touches_host(action,sha):
    host=Host()
    with pytest.raises(subject.LifecycleError):subject.run_lifecycle(host,action,sha)
    assert not host.calls


def listing(state='running',pid='812',path=None,label=None):
    text=f'system/{label or subject.LABEL} = {{\n\tpath = {path or subject.PLIST}\n\tstate = {state}\n'
    return text+(f'\tpid = {pid}\n' if pid is not None else '')+'}\n'


def test_registration_parser_binds_fixed_path_label_and_pid():
    assert subject.parse_registration(listing())==dict(state='running',pid=812)
    assert subject.parse_registration(listing('waiting',None))==dict(state='registered',pid=None)


@pytest.mark.parametrize('raw', [listing(path='/tmp/foreign.plist'),listing(label='com.other'),
    listing(pid='0'),listing(pid='8 12'),listing().replace('\tpid = 812','\tpid = 812\n\tpid = 812'),
    listing().replace('running','waiting'), listing()+'}\n',listing().replace('\tpath =','\t\tpath =')])
def test_registration_parser_refuses_ambiguous_or_foreign_identity(raw):
    with pytest.raises(subject.LifecycleError):subject.parse_registration(raw)


@pytest.mark.parametrize('value,expected',[('true','disabled'),('disabled','disabled'),('false','enabled'),('enabled','enabled')])
def test_override_parser(value,expected):
    assert subject.parse_override('disabled services = {\n"'+subject.LABEL+'" => '+value+'\n}')==expected


@pytest.mark.parametrize('raw',['','garbage','disabled services = {\nwrong\n}',
    'disabled services = {\n"x" => true\n"x" => false\n}','disabled services = {\n}\nnoise'])
def test_override_parser_requires_complete_unambiguous_document(raw):
    with pytest.raises(subject.LifecycleError):subject.parse_override(raw)
