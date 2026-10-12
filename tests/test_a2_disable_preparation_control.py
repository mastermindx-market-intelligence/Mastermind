"""Real global transaction archives with injected host-only launchctl effects."""
import dataclasses
import json
import subprocess
from types import SimpleNamespace

import pytest

from ops.executive_os import autonomy_control as owner
from ops.executive_os import a2_disable_preparation_control as a2
from tests.test_executive_autonomy_control import SHA, _inprocess_marker_host


def configure(host, monkeypatch, state):
    monkeypatch.setattr(host, "effective_uid", lambda: 0)
    monkeypatch.setattr(host, "require_exact_install", lambda sha: sha)
    def absent():
        if state.artifact:
            raise owner.TransactionEffectUnknown()
    def unloaded():
        if state.loaded:
            raise owner.TransactionEffectUnknown()
    def disabled():
        if state.unreadable:
            raise owner.TransactionEffectUnknown()
        return state.disabled
    def disable():
        assert host._manifest()["phase"] == "A2_DISABLE_DISPATCHED"
        assert host._transaction_owner_fd is not None
        state.calls += 1
        state.disabled = state.post_disabled
        state.loaded = state.post_loaded
        state.unreadable = state.post_unreadable
        if state.lost_response:
            raise subprocess.TimeoutExpired("fixed disable", 10)
        return 5  # even an unsuccessful command response is not the postcondition
    monkeypatch.setattr(host, "assert_artifacts_absent", absent)
    monkeypatch.setattr(host, "assert_unloaded", unloaded)
    monkeypatch.setattr(host, "disabled_override", disabled)
    monkeypatch.setattr(host, "disable_once", disable)
    return host


@pytest.fixture
def installed(monkeypatch, tmp_path):
    root, marker = _inprocess_marker_host(monkeypatch, tmp_path)
    state = SimpleNamespace(disabled=None, unreadable=False, artifact=False, loaded=False,
        post_disabled=True, post_loaded=False, post_unreadable=False, calls=0, lost_response=False)
    host = configure(a2.ProductionA2DisablePreparationHost(), monkeypatch, state)
    yield SimpleNamespace(root=root, marker=marker, host=host, state=state,
        control=owner.CONTROL_CONFIG.read_bytes(), worker=owner.WORKER_CONFIG.read_bytes())
    if host._transaction_owner_fd is not None:
        host._release_transaction_owner()


@pytest.mark.parametrize("lost", [False, True])
def test_positive_postcondition_recovers_failed_or_lost_disable_response(installed, lost):
    s = installed
    s.state.lost_response = lost
    assert a2.execute_preparation(s.host, SHA).startswith("autonomy-")
    assert s.state.calls == 1 and not s.marker.exists()
    assert owner.CONTROL_CONFIG.read_bytes() == s.control
    assert owner.WORKER_CONFIG.read_bytes() == s.worker
    assert a2.execute_preparation(s.host, SHA) is None
    assert s.state.calls == 1


@pytest.mark.parametrize("fault", ["false", "absent", "unreadable", "loaded"])
def test_uncertain_effect_is_sticky_and_restart_only_reconciles(installed, monkeypatch, fault):
    s = installed
    if fault == "false":
        s.state.post_disabled = False
    elif fault == "absent":
        s.state.post_disabled = None
    elif fault == "unreadable":
        s.state.post_unreadable = True
    else:
        s.state.post_loaded = True
    with pytest.raises(owner.TransactionEffectUnknown):
        a2.execute_preparation(s.host, SHA)
    manifest = s.host._manifest()
    assert manifest["operation"] == a2.OPERATION
    assert manifest["phase"] == "A2_DISABLE_DISPATCHED"
    assert s.state.calls == 1
    s.host._release_transaction_owner()
    recovered = configure(a2.ProductionA2DisablePreparationHost(), monkeypatch, s.state)
    try:
        with pytest.raises(owner.CeoSubmitAdmissionError):
            a2.execute_preparation(recovered, SHA)
        with pytest.raises(owner.TransactionEffectUnknown):
            recovered.recover_preparation(SHA)
        assert s.marker.exists() and s.state.calls == 1
        recovered._release_transaction_owner()  # next invocation reclaims the retained marker
        s.state.disabled, s.state.loaded, s.state.unreadable = True, False, False
        assert recovered.recover_preparation(SHA) == manifest["transaction_id"]
        assert s.state.calls == 1 and not s.marker.exists()
        assert owner.CONTROL_CONFIG.read_bytes() == s.control
        assert owner.WORKER_CONFIG.read_bytes() == s.worker
    finally:
        if recovered._transaction_owner_fd is not None:
            recovered._release_transaction_owner()


@pytest.mark.parametrize("fault", ["artifact", "loaded", "unreadable", "configs"])
def test_unproven_preconditions_cannot_dispatch(installed, monkeypatch, fault):
    s = installed
    if fault == "configs":
        monkeypatch.setattr(s.host, "load_ceo_submit_configs",
            lambda sha: (_ for _ in ()).throw(ValueError("missing installed configs")))
    else:
        setattr(s.state, fault, True)
    with pytest.raises(Exception):
        a2.execute_preparation(s.host, SHA)
    assert s.state.calls == 0 and not s.marker.exists()


def test_foreign_global_owner_cannot_be_erased_or_adopted(installed, monkeypatch):
    s = installed
    prior = s.host.load_ceo_submit_configs(SHA)
    tx = owner.TransactionContext(s.host.new_transaction_id(), SHA, prior,
        a2.unchanged_candidate(prior), None)
    s.host._create_marker(tx, operation="ARM")
    before = s.host._manifest()
    s.host._release_transaction_owner()
    recovered = configure(a2.ProductionA2DisablePreparationHost(), monkeypatch, s.state)
    try:
        with pytest.raises(owner.TransactionEffectUnknown):
            recovered.recover_preparation(SHA)
        assert recovered._manifest() == before
        assert s.state.calls == 0
    finally:
        if recovered._transaction_owner_fd is not None:
            recovered._release_transaction_owner()


def test_changed_preimages_after_unknown_are_never_overwritten(installed, monkeypatch):
    s = installed
    s.state.post_disabled = False
    with pytest.raises(owner.TransactionEffectUnknown):
        a2.execute_preparation(s.host, SHA)
    s.host._release_transaction_owner()
    prior = s.host.load_ceo_submit_configs(SHA)
    recovered = configure(a2.ProductionA2DisablePreparationHost(), monkeypatch, s.state)
    monkeypatch.setattr(recovered, "load_ceo_submit_configs",
        lambda sha: dataclasses.replace(prior, worker_bytes=b"foreign"))
    try:
        with pytest.raises(owner.TransactionEffectUnknown):
            recovered.recover_preparation(SHA)
        assert s.marker.exists() and s.state.calls == 1
    finally:
        if recovered._transaction_owner_fd is not None:
            recovered._release_transaction_owner()


@pytest.mark.parametrize("raw,expected", [
    (b'disabled services = {\n}\n', None),
    (b'disabled services = {\n"com.mastermind.executive.agent-relay" => false\n}\n', False),
    (b'disabled services = {\n"com.mastermind.executive.agent-relay" => true\n}\n', True),
    (b'disabled services = {\n"com.mastermind.executive.agent-relay" => disabled\n}\n', True),
])
def test_a2_closed_parser_distinguishes_absence_from_false_and_positive(monkeypatch, raw, expected):
    monkeypatch.setattr(owner.ProductionCeoSubmitHost,
        "_capture_control_launchd_disabled_output", staticmethod(lambda: raw))
    assert a2.ProductionA2DisablePreparationHost().disabled_override() is expected


@pytest.mark.parametrize("raw", [
    b'', b'{}', b'disabled services = {\n"com.mastermind.executive.agent-relay" => true junk\n}\n',
    b'disabled services = {\n"com.mastermind.executive.agent-relay" => true\n"com.mastermind.executive.agent-relay" => false\n}\n',
    b'disabled services = {\n"other" => unknown\n}\n',
])
def test_a2_ambiguous_disabled_table_is_unknown(monkeypatch, raw):
    monkeypatch.setattr(owner.ProductionCeoSubmitHost,
        "_capture_control_launchd_disabled_output", staticmethod(lambda: raw))
    with pytest.raises(owner.TransactionEffectUnknown):
        a2.ProductionA2DisablePreparationHost().disabled_override()


@pytest.mark.parametrize("scenario", ["success", "replay", "unknown", "preflight"])
def test_cli_emits_closed_result_and_releases_only_owned_lock(installed, capsys, scenario):
    s = installed
    if scenario == "replay":
        s.state.disabled = True
    elif scenario == "unknown":
        s.state.post_unreadable = True
    elif scenario == "preflight":
        s.state.artifact = True
    args = SimpleNamespace(command="a2-disable-prepare", expected_sha=SHA)
    assert a2.run_command(args, host=s.host) == (2 if scenario in {"unknown", "preflight"} else 0)
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == ("EFFECT_UNKNOWN" if scenario in {"unknown", "preflight"}
                                else "A2_DISABLE_PREPARED")
    assert s.host._transaction_owner_fd is None
    assert s.marker.exists() == (scenario == "unknown")
