"""Controller-PID observation cannot mutate leases or attest worker completion."""
import io
import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lease_broker


def snapshot(**changes):
    s = {"schema": "mastermind.provider_capacity.v1", "this_host": "m2studio",
         "pools": {}, "leases": [{"id": "lease-dead", "task_class": "remote-glm",
             "state": "held", "pid": 424242, "host": "ubuntu2", "pool": "glm",
             "account": "fake", "orchestrator_id": "orchestrator", "age_s": 40}],
         "waiters": []}
    s.update(changes)
    return s


def render(monkeypatch, status):
    broker = lease_broker.Broker.__new__(lease_broker.Broker)
    broker.this_host = "m2studio"
    values = []
    def fake_kill(pid, signal):
        values.append((pid,signal))
        if pid == 424242: raise ProcessLookupError()
        if pid == 525252: raise PermissionError()
        return None
    monkeypatch.setattr(lease_broker.os, 'kill', fake_kill)
    before = repr(status)
    with contextlib.redirect_stdout(io.StringIO()) as out:
        broker.print_status(status)
        text = out.getvalue()
    assert repr(status) == before  # Projection input unchanged, no lease mutation.
    return text, values


def test_dead_local_controller_pid_warns_but_never_reclaims(monkeypatch):
    output, pids = render(monkeypatch, snapshot())
    assert "CONTROLLER_PID_ABSENT count=1" in output
    assert "lease=lease-dead remote_worker=UNKNOWN no_release_or_retry=1" in output
    assert pids == [(424242, 0)]


def test_pid_permission_is_unverified_and_local_view_not_cross_host(monkeypatch):
    r = snapshot(leases=[dict(snapshot()['leases'][0],pid=525252)])
    output,pids=render(monkeypatch,r)
    assert "CONTROLLER_PID_ABSENT" not in output and pids==[(525252,0)]
    output,pids=render(monkeypatch,snapshot(this_host='ubuntu1'))
    assert "CONTROLLER_PID_ABSENT" not in output and pids==[]


def test_nonremote_rented_and_invalid_pid_ignore_without_claim(monkeypatch):
    base=snapshot()['leases'][0]
    r=snapshot(leases=[dict(base,task_class='ci'),dict(base,pid=0),
        dict(base,state='released')])
    output,pids=render(monkeypatch,r)
    assert "CONTROLLER_PID_ABSENT" not in output
    assert pids==[]
    assert lease_broker._broker_controller_pid_observation('untrusted') == 'UNVERIFIED'
