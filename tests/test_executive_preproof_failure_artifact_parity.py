"""Cross-lane parity: the optional pre-proof failure artifact in
acceptance_maintenance must agree with the real acceptance writer.

The acceptance-maintenance module admits a bounded optional
``host-service-status-failure.txt`` inside a pre-proof prefix (see
``_PREPROOF_OPTIONAL_ARTIFACTS``). That name is the only artifact the
acceptance harness writes for the ``"host service status"`` label
(``Acceptance._run_recorded`` -> ``_FAILURE_ARTIFACTS["host service status"]``).
The behavioural refusal ``final host status`` MUST stay outside the optional
admission so the candidate is never silently widened to a post-proof prefix
(``tests/test_executive_acceptance_supersede_preproof.py::test_r12_final_host_status_failure_txt_refuses``).

These checks pin the contract that links the two lanes' output against each
other; if either side drifts the parity check catches it before any release
build ships.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]

_ACCEPTANCE_SPEC = importlib.util.spec_from_file_location(
    "_acceptance_for_parity", ROOT / "ops" / "executive_os" / "acceptance.py"
)
assert _ACCEPTANCE_SPEC is not None and _ACCEPTANCE_SPEC.loader is not None
acceptance = importlib.util.module_from_spec(_ACCEPTANCE_SPEC)
sys.modules[_ACCEPTANCE_SPEC.name] = acceptance
_ACCEPTANCE_SPEC.loader.exec_module(acceptance)

from ops.executive_os import acceptance_maintenance as m
from tests.test_executive_acceptance_supersede_unstarted import (
    S, _fixture as _unstarted_fixture,
)
from tests.test_executive_acceptance_supersede_preproof import (
    write_full_preproof_root,
)


# --- (a) ------------------------------------------------------------------

def test_preproof_optional_artifacts_are_exactly_the_pre_proof_status_artifact():
    """The maintenance module admits exactly the artifact that the host-service
    status label writes; no other name is admitted."""
    expected = frozenset({acceptance._FAILURE_ARTIFACTS["host service status"]})
    assert m._PREPROOF_OPTIONAL_ARTIFACTS == expected


# --- (b) ------------------------------------------------------------------

def test_failure_artifact_bound_fits_the_preproof_admission():
    """The real failure-artifact size bound must fit inside the pre-proof bound
    the maintenance module admits."""
    assert acceptance._FAILURE_ARTIFACT_LIMIT <= m._MAX_PREPROOF_FAILURE_ARTIFACT_BYTES


# --- (c) ------------------------------------------------------------------

def test_final_status_artifact_is_never_a_preproof_artifact():
    """``final host status`` is the post-proof label; it must never appear in the
    optional pre-proof set (the behavioural guard is r12 in the supersede-preproof
    test module)."""
    assert (
        acceptance._FAILURE_ARTIFACTS["final host status"]
        not in m._PREPROOF_OPTIONAL_ARTIFACTS
    )


# --- (d) ------------------------------------------------------------------

class _FakePw:
    def __init__(self, uid: int) -> None:
        self.pw_uid = uid


class _FakeGr:
    def __init__(self, gid: int) -> None:
        self.gr_gid = gid


def _acceptance_pointed_at_bundle(tmp_path, monkeypatch):
    """Build an Acceptance instance whose receipt_root points at the same
    candidate directory preproof_evidence walks for ``S``.

    Reuses ``_unstarted_fixture`` so ``m.preproof_evidence`` is hermetic:
    RUNTIME_ROOT is monkeypatched to ``tmp_path/runtime`` and the acceptance
    directory lives at ``runtime/control/acceptance/S``. The eight core
    pre-proof receipts plus the one probe are stamped exactly the way
    ``test_a5_optional_failure_artifact_present_changes_evidence_digest``
    stamps them, so the preproof walker only needs the failure artifact on
    top."""
    candidate, selected, before, artifacts, canary, bundle, runtime = _unstarted_fixture(
        tmp_path, monkeypatch
    )
    acceptance_root = write_full_preproof_root(runtime, selected, monkeypatch)
    instance = object.__new__(acceptance.Acceptance)
    instance.receipt_root = acceptance_root
    instance.control_identity = _FakePw(os.geteuid())
    instance.worker_identity = _FakePw(os.geteuid())
    instance.control_group = _FakeGr(os.getegid())
    instance.worker_group = _FakeGr(os.getegid())
    instance.operator_identity = _FakePw(os.geteuid())
    instance.config = {
        "runtime_root": str(runtime),
        "receipts_root": str(runtime / "control" / "receipts"),
        "worker_runs_root": str(tmp_path / "wr"),
        "proof_workspace_root": str(tmp_path / "ws"),
        "proof_source_repository": str(tmp_path / "src"),
        "worker_provider_home": str(tmp_path / "workerhome"),
    }
    instance.release = tmp_path / "release"
    instance.release.mkdir(parents=True, exist_ok=True)
    instance.canary_value = ""
    instance._sentinel_sources = lambda: []
    return instance, acceptance_root, candidate, selected, before, artifacts, canary


def test_preproof_admits_the_artifact_acceptance_actually_writes(tmp_path, monkeypatch):
    """The real acceptance writer must produce an artifact the preproof walker
    accepts, with the same size and mode the maintenance module already admits
    (the validation a5 calls)."""
    instance, acceptance_root, candidate, selected, before, artifacts, canary = (
        _acceptance_pointed_at_bundle(tmp_path, monkeypatch)
    )
    failing_script = "echo diagnostic line; exit 7\n"
    with pytest.raises(acceptance.CommandFailure) as raised:
        instance._run_recorded(
            ["/bin/bash", "-c", failing_script],
            label="host service status",
        )
    assert raised.value.returncode == 7

    artifact = acceptance_root / "host-service-status-failure.txt"
    assert artifact.exists()
    info = artifact.lstat()
    assert info.st_uid == os.geteuid()
    assert info.st_gid == os.getegid()
    assert (info.st_mode & 0o777) == 0o400
    assert info.st_size <= m._MAX_PREPROOF_FAILURE_ARTIFACT_BYTES

    # Same validation a5 calls: m.preproof_evidence walks the directory,
    # ingests host-service-status-failure.txt as a bounded optional, and
    # returns the manifest digest plus the parsed envelope.
    evidence_digest, envelope_value = m.preproof_evidence(S)
    assert isinstance(evidence_digest, str)
    assert len(evidence_digest) == 64
    assert isinstance(envelope_value, dict)