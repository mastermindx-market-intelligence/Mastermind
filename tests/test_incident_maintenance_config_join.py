"""Real arm policy and strict parser joined to inert trusted-reader leaves."""
import hashlib
import json
import time
from types import SimpleNamespace as S

import pytest

from control_plane import executive_incident_maintenance as m
from ops.executive_os import acceptance_maintenance as a


def configuration_world(monkeypatch, control=None, worker=None, *, drift=False):
    control = control if control is not None else {
        "ceo_submit_armed": False, "coo_autonomy_armed": False,
        "coo_operator_harness_armed": False,
    }
    worker = worker if worker is not None else {"operator_harness_armed": False}
    raws = [json.dumps(value).encode() for value in (control, worker)]
    artifacts = [S(raw=raw, digest=hashlib.sha256(raw).hexdigest()) for raw in raws]
    observed = S(roles=tuple(S(content=S(configuration_digest=(
        "0" * 64 if drift else artifact.digest))) for artifact in artifacts))
    reads = []
    def read(path, mode, gid, budget):
        index = next(i for i, spec in enumerate(m.release._SPECS[:2]) if spec.config == path)
        spec = m.release._SPECS[index]
        assert (mode, gid) == (spec.config_mode, spec.config_gid)
        reads.append(path)
        return artifacts[index]
    monkeypatch.setattr(m.release, "_artifact", read)
    return observed, reads


def test_real_closed_arm_dependency_accepts_trusted_matching_configuration(monkeypatch):
    observed, reads = configuration_world(monkeypatch)
    m._require_closed_arms(observed, m.release._Budget(time.monotonic_ns() + 2_000_000_000))
    assert reads == [spec.config for spec in m.release._SPECS[:2]]


@pytest.mark.parametrize("flag", ["ceo_submit_armed", "coo_autonomy_armed", "coo_operator_harness_armed"])
@pytest.mark.parametrize("value", [True, None, 0])
def test_real_control_policy_rejects_non_false_flags(monkeypatch, flag, value):
    config = dict(ceo_submit_armed=False, coo_autonomy_armed=False, coo_operator_harness_armed=False)
    config[flag] = value
    observed, _ = configuration_world(monkeypatch, control=config)
    with pytest.raises(a.MaintenanceError, match="all control intake arms closed"):
        m._require_closed_arms(observed, m.release._Budget(time.monotonic_ns() + 2_000_000_000))


@pytest.mark.parametrize("worker", [{}, {"operator_harness_armed": True}, {"operator_harness_armed": 0}])
def test_worker_arm_is_a_separate_obligation(monkeypatch, worker):
    observed, _ = configuration_world(monkeypatch, worker=worker)
    with pytest.raises(m.BrokerMaintenanceError, match="WORKER_ARMED"):
        m._require_closed_arms(observed, m.release._Budget(time.monotonic_ns() + 2_000_000_000))


def test_config_bytes_must_match_observed_content(monkeypatch):
    observed, reads = configuration_world(monkeypatch, drift=True)
    with pytest.raises(m.BrokerMaintenanceError, match="CONTENT_DRIFT"):
        m._require_closed_arms(observed, m.release._Budget(time.monotonic_ns() + 2_000_000_000))
    assert len(reads) == 1
