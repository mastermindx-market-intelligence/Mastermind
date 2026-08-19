"""Load-bearing tests for attested macOS ambient principal isolation."""
from __future__ import annotations

import ast
import asyncio
import dataclasses
import json
import os
import signal
from pathlib import Path

import pytest

from control_plane.executive_ambient_process import (
    AMBIENT_CODESIGN_IDENTIFIER,
    AMBIENT_LAUNCHD_LABEL,
    AMBIENT_PLIST_PATH,
    AMBIENT_PROGRAM_PATH,
    AmbientClassification,
    AmbientProcessIdentity,
    DarwinDistnotedClassifier,
    NullAmbientClassifier,
    parse_distnoted_launchd_job,
)
from control_plane.executive_worker_broker import (
    BrokerStateError,
    DedicatedUIDSweeper,
    UIDSweepReceipt,
    UID_SWEEP_SCHEMA_VERSION,
    uid_sweep_receipt_is_passing,
)

ROOT = Path(__file__).resolve().parents[1]


def _identity(pid: int = 88688, uid: int = 451) -> AmbientProcessIdentity:
    return AmbientProcessIdentity(
        pid=pid,
        uid=uid,
        launchd_domain=f"user/{uid}",
        launchd_label=AMBIENT_LAUNCHD_LABEL,
        launchd_reported_pid=pid,
        plist_path=AMBIENT_PLIST_PATH,
        program_path=AMBIENT_PROGRAM_PATH,
        executable_path=AMBIENT_PROGRAM_PATH,
        executable_device=16777232,
        executable_inode=1152921500312576003,
        codesign_identifier=AMBIENT_CODESIGN_IDENTIFIER,
        codesign_verified=True,
    )


class _StaticClassifier:
    def __init__(self, classification: AmbientClassification) -> None:
        self.classification = classification
        self.calls = 0

    def classify(self, *, worker_uid: int) -> AmbientClassification:
        self.calls += 1
        assert worker_uid == 451
        return self.classification


def _launchctl_stdout(pid: int = 88688, uid: int = 451, **overrides: str) -> str:
    fields = {
        "path": AMBIENT_PLIST_PATH,
        "type": "LaunchAgent",
        "state": "running",
        "program": AMBIENT_PROGRAM_PATH,
        "domain": f"user/{uid}",
        "pid": str(pid),
    }
    fields.update(overrides)
    body = "\n".join(f"\t{key} = {value}" for key, value in fields.items())
    return f"user/{uid}/{AMBIENT_LAUNCHD_LABEL} = {{\n{body}\n}}\n"


def test_attested_launchd_pid_is_not_a_residual() -> None:
    signals: list[int] = []
    observed = (451, 88688)
    classifier = _StaticClassifier(
        AmbientClassification(status="attested", identities=(_identity(),))
    )
    sweeper = DedicatedUIDSweeper(
        451,
        current_uid=lambda: 451,
        current_pid=lambda: 451,
        process_lister=lambda _uid: observed,
        kill_fn=lambda pid, _sig: signals.append(pid),
        sleep_fn=lambda _seconds: None,
        ambient_classifier=classifier,
    )
    receipt = sweeper.sweep("run_terminal")
    assert receipt.schema_version == UID_SWEEP_SCHEMA_VERSION
    assert receipt.ambient_pids == (88688,)
    assert receipt.residual_pids_before == ()
    assert receipt.residual_pids_after == ()
    assert receipt.found_residuals is False
    assert receipt.passed is True
    assert receipt.ambient_attribution == "attested"
    assert signals == []
    assert uid_sweep_receipt_is_passing(receipt.to_dict())


def test_process_merely_named_distnoted_is_residual() -> None:
    """A fake process with no launchd identity is untrusted, name notwithstanding."""

    signals: list[int] = []
    snapshots = iter(((451, 777), (451,), (451,)))
    sweeper = DedicatedUIDSweeper(
        451,
        current_uid=lambda: 451,
        current_pid=lambda: 451,
        process_lister=lambda _uid: next(snapshots),
        kill_fn=lambda pid, _sig: signals.append(pid),
        sleep_fn=lambda _seconds: None,
        ambient_classifier=NullAmbientClassifier(),
    )
    receipt = sweeper.sweep("run_terminal")
    assert receipt.residual_pids_before == (777,)
    assert receipt.found_residuals is True
    assert receipt.ambient_pids == ()
    assert signals == [777]


def test_same_binary_without_trusted_launchd_pid_is_residual() -> None:
    signals: list[int] = []
    snapshots = iter(((451, 88688, 99999), (451, 88688), (451, 88688)))
    classifier = _StaticClassifier(
        AmbientClassification(status="attested", identities=(_identity(88688),))
    )
    sweeper = DedicatedUIDSweeper(
        451,
        current_uid=lambda: 451,
        current_pid=lambda: 451,
        process_lister=lambda _uid: next(snapshots),
        kill_fn=lambda pid, _sig: signals.append(pid),
        sleep_fn=lambda _seconds: None,
        ambient_classifier=classifier,
    )
    receipt = sweeper.sweep("run_terminal")
    assert receipt.ambient_pids == (88688,)
    assert receipt.residual_pids_before == (99999,)
    assert receipt.found_residuals is True
    assert 88688 not in signals
    assert signals == [99999]


def test_missing_or_ambiguous_attribution_fails_closed() -> None:
    signals: list[int] = []
    snapshots = iter(((451, 88688), (451,), (451,)))
    sweeper = DedicatedUIDSweeper(
        451,
        current_uid=lambda: 451,
        current_pid=lambda: 451,
        process_lister=lambda _uid: next(snapshots),
        kill_fn=lambda pid, _sig: signals.append(pid),
        sleep_fn=lambda _seconds: None,
        ambient_classifier=_StaticClassifier(AmbientClassification(status="failed_closed")),
    )
    receipt = sweeper.sweep("broker_startup")
    assert receipt.ambient_pids == ()
    assert receipt.residual_pids_before == (88688,)
    assert receipt.found_residuals is True
    assert receipt.ambient_attribution == "failed_closed"
    assert signals == [88688]


@pytest.mark.parametrize(
    "overrides",
    [
        {"path": "/tmp/com.apple.distnoted.xpc.agent.plist"},
        {"program": "/tmp/distnoted"},
        {"type": "LaunchDaemon"},
        {"state": "not running"},
        {"domain": "user/450"},
        {"pid": "0"},
    ],
)
def test_changed_path_signature_or_launchd_identity_fails_closed(overrides: dict[str, str]) -> None:
    parsed = parse_distnoted_launchd_job(
        _launchctl_stdout(**overrides),
        worker_uid=451,
    )
    assert parsed is None


def test_darwin_classifier_requires_matching_executable_and_codesign() -> None:
    identity = {
        "path": AMBIENT_PROGRAM_PATH,
        "codesign_identifier": AMBIENT_CODESIGN_IDENTIFIER,
        "codesign_verified": True,
        "device": 16777232,
        "inode": 1152921500312576003,
    }

    def launchctl_print(_spec: str) -> tuple[int, str, str]:
        return 0, _launchctl_stdout(), ""

    classifier = DarwinDistnotedClassifier(
        launchctl_print=launchctl_print,
        pid_executable=lambda pid: Path(AMBIENT_PROGRAM_PATH) if pid == 88688 else Path("/tmp/distnoted"),
        program_identity=lambda _path: identity,
    )
    attested = classifier.classify(worker_uid=451)
    assert attested.status == "attested"
    assert attested.identities[0].pid == 88688

    wrong_binary = DarwinDistnotedClassifier(
        launchctl_print=launchctl_print,
        pid_executable=lambda _pid: Path("/tmp/distnoted"),
        program_identity=lambda _path: identity,
    )
    assert wrong_binary.classify(worker_uid=451).status == "failed_closed"

    wrong_sign = DarwinDistnotedClassifier(
        launchctl_print=launchctl_print,
        pid_executable=lambda _pid: Path(AMBIENT_PROGRAM_PATH),
        program_identity=lambda _path: {
            "path": AMBIENT_PROGRAM_PATH,
            "codesign_identifier": "com.example.fake",
            "codesign_verified": True,
        },
    )
    assert wrong_sign.classify(worker_uid=451).status == "failed_closed"


def test_clean_terminal_sweep_matches_prior_contract() -> None:
    sweeper = DedicatedUIDSweeper(
        451,
        current_uid=lambda: 451,
        current_pid=lambda: 451,
        process_lister=lambda _uid: (451,),
        kill_fn=lambda _pid, _sig: pytest.fail("clean sweep must not signal"),
        sleep_fn=lambda _seconds: None,
    )
    receipt = sweeper.sweep("run_terminal")
    assert receipt.residual_pids_before == ()
    assert receipt.residual_pids_after == ()
    assert receipt.passed is True
    assert receipt.found_residuals is False
    assert receipt.signal_sent is False


def test_genuine_detached_residual_still_fails_collection(tmp_path: Path) -> None:
    from tests.test_executive_worker_broker import FakeSweeper, _fixture, _request

    class ResidualSweeper(FakeSweeper):
        def sweep(self, reason: str) -> UIDSweepReceipt:
            receipt = super().sweep(reason)
            if reason != "run_terminal":
                return receipt
            return dataclasses.replace(receipt, residual_pids_before=(777,))

    async def scenario() -> None:
        broker, _adapter, _sweeper, peer, spec = _fixture(tmp_path)
        broker.sweeper = ResidualSweeper()
        _adapter.finished.set()
        await broker.execute(
            _request(
                "start",
                {"launch_spec": spec, "validation_commands": [["/usr/bin/true"]]},
            ),
            peer=peer,
        )
        with pytest.raises(BrokerStateError, match="detached same-UID process"):
            await broker.execute(_request("collect", {"run_id": "run-1"}), peer=peer)

    asyncio.run(scenario())


def test_ambient_only_collection_does_not_raise(tmp_path: Path) -> None:
    from tests.test_executive_worker_broker import FakeSweeper, _fixture, _request

    class AmbientSweeper(FakeSweeper):
        def sweep(self, reason: str) -> UIDSweepReceipt:
            receipt = super().sweep(reason)
            identity = _identity()
            return dataclasses.replace(
                receipt,
                ambient_pids=(identity.pid,),
                ambient_identities=(identity,),
                ambient_attribution="attested",
            )

    async def scenario() -> None:
        broker, _adapter, _sweeper, peer, spec = _fixture(tmp_path)
        broker.sweeper = AmbientSweeper()
        _adapter.finished.set()
        await broker.execute(
            _request(
                "start",
                {"launch_spec": spec, "validation_commands": [["/usr/bin/true"]]},
            ),
            peer=peer,
        )
        collected = await broker.execute(
            _request("collect", {"run_id": "run-1"}), peer=peer
        )
        assert collected["ok"] is True
        sweep = collected["result"]["uid_sweep"]
        assert sweep["ambient_pids"] == [88688]
        assert sweep["found_residuals"] is False
        assert sweep["residual_pids_before"] == []

    asyncio.run(scenario())


def test_startup_sweep_still_sanitizes_untrusted_residuals() -> None:
    signals: list[int] = []
    snapshots = iter(((451, 999), (451,), (451,)))
    sweeper = DedicatedUIDSweeper(
        451,
        current_uid=lambda: 451,
        current_pid=lambda: 451,
        process_lister=lambda _uid: next(snapshots),
        kill_fn=lambda pid, value: signals.append((pid, value)),
        sleep_fn=lambda _seconds: None,
    )
    receipt = sweeper.sweep("broker_startup")
    assert receipt.residual_pids_before == (999,)
    assert receipt.passed is True
    assert signals == [(999, signal.SIGKILL)]


def test_terminal_uid_sweep_survives_later_shutdown_receipt(tmp_path: Path) -> None:
    path = tmp_path / "uid-sweep.json"
    observed = (451,)
    sweeper = DedicatedUIDSweeper(
        451,
        receipt_path=path,
        current_uid=lambda: 451,
        current_pid=lambda: 451,
        process_lister=lambda _uid: observed,
        kill_fn=lambda _pid, _sig: pytest.fail("no residual"),
        sleep_fn=lambda _seconds: None,
    )
    sweeper.sweep("run_terminal")
    sweeper.sweep("broker_shutdown")
    latest = json.loads(path.read_text(encoding="utf-8"))
    terminal = json.loads((tmp_path / "uid-sweep-terminal.json").read_text(encoding="utf-8"))
    assert latest["reason"] == "broker_shutdown"
    assert terminal["reason"] == "run_terminal"
    assert terminal["schema_version"] == UID_SWEEP_SCHEMA_VERSION


def test_no_process_name_allowlist_exists() -> None:
    ambient = (ROOT / "control_plane" / "executive_ambient_process.py").read_text(
        encoding="utf-8"
    )
    broker = (ROOT / "control_plane" / "executive_worker_broker.py").read_text(
        encoding="utf-8"
    )
    worker = (ROOT / "scripts" / "executive_os_phase1c_worker.py").read_text(
        encoding="utf-8"
    )
    for source in (ambient, broker):
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                comparators = [
                    ast.literal_eval(item)
                    for item in node.comparators
                    if isinstance(item, ast.Constant)
                ]
                assert "distnoted" not in comparators
    assert "DarwinDistnotedClassifier()" in worker
    assert "comm=" not in ambient
    assert "if sweep.passed" not in broker


def test_v1_receipt_is_not_silently_accepted() -> None:
    v1 = {
        "schema_version": "mastermind.executive_uid_sweep/v1",
        "passed": True,
        "residual_pids_before": [],
        "residual_pids_after": [],
        "broker_pid": 42419,
        "worker_uid": 451,
        "ambient_pids": [],
        "ambient_identities": [],
        "ambient_attribution": "absent",
        "found_residuals": False,
    }
    assert uid_sweep_receipt_is_passing(v1) is False


def _passing_v2_receipt(**overrides: object) -> dict:
    identity = _identity()
    receipt: dict = {
        "schema_version": UID_SWEEP_SCHEMA_VERSION,
        "observed_at": "2026-08-11T00:00:01+00:00",
        "reason": "run_terminal",
        "worker_uid": 451,
        "broker_pid": 42419,
        "residual_pids_before": [],
        "residual_pids_after": [],
        "signal_name": "SIGKILL",
        "signal_sent": False,
        "quiescent_observations": 2,
        "ambient_pids": [identity.pid],
        "ambient_identities": [identity.to_dict()],
        "ambient_attribution": "attested",
        "passed": True,
        "found_residuals": False,
    }
    receipt.update(overrides)
    return receipt


def _malformed_ambient_cases() -> list[tuple[str, dict]]:
    identity = _identity().to_dict()
    attested = _passing_v2_receipt()
    absent = _passing_v2_receipt(
        ambient_pids=[],
        ambient_identities=[],
        ambient_attribution="absent",
    )
    incomplete = dict(identity)
    incomplete.pop("codesign_verified")
    mismatched_pid = dict(identity)
    mismatched_pid["launchd_reported_pid"] = identity["pid"] + 1
    mismatched_uid = dict(identity)
    mismatched_uid["uid"] = 450
    return [
        (
            "attested_empty_pids_with_identities",
            {**attested, "ambient_pids": []},
        ),
        (
            "attested_empty_identities_with_pids",
            {**attested, "ambient_identities": []},
        ),
        (
            "absent_with_ambient_pids",
            {**absent, "ambient_pids": [88688]},
        ),
        (
            "failed_closed_with_identities",
            {
                **absent,
                "ambient_attribution": "failed_closed",
                "ambient_identities": [identity],
                "ambient_pids": [88688],
            },
        ),
        (
            "pid_set_does_not_match_identities",
            {**attested, "ambient_pids": [99999]},
        ),
        (
            "identity_is_not_a_mapping",
            {**attested, "ambient_identities": [identity["pid"]]},
        ),
        (
            "identity_missing_reviewed_fields",
            {**attested, "ambient_identities": [incomplete]},
        ),
        (
            "identity_pid_not_launchd_reported_pid",
            {**attested, "ambient_identities": [mismatched_pid]},
        ),
        (
            "identity_uid_not_worker_uid",
            {**attested, "ambient_identities": [mismatched_uid]},
        ),
        (
            "duplicate_ambient_pids",
            {**attested, "ambient_pids": [88688, 88688]},
        ),
        (
            "duplicate_identity_pids",
            {
                **attested,
                "ambient_identities": [identity, dict(identity)],
            },
        ),
        (
            "ambient_overlaps_broker",
            {
                **attested,
                "ambient_pids": [42419],
                "ambient_identities": [
                    {**identity, "pid": 42419, "launchd_reported_pid": 42419}
                ],
            },
        ),
        (
            "ambient_overlaps_residual_before",
            {
                **attested,
                "residual_pids_before": [88688],
                "found_residuals": True,
            },
        ),
        (
            "extra_identity_pid_not_in_ambient",
            {
                **attested,
                "ambient_identities": [
                    identity,
                    {
                        **identity,
                        "pid": 99999,
                        "launchd_reported_pid": 99999,
                    },
                ],
            },
        ),
    ]


@pytest.mark.parametrize(
    "label,payload",
    _malformed_ambient_cases(),
    ids=[label for label, _payload in _malformed_ambient_cases()],
)
def test_malformed_v2_ambient_projection_fails_closed(label: str, payload: dict) -> None:
    from ops.executive_os.acceptance import _uid_sweep_is_passing

    assert uid_sweep_receipt_is_passing(payload) is False, label
    assert _uid_sweep_is_passing(payload) is False, label


def test_coherent_attested_and_absent_v2_receipts_pass_both_validators() -> None:
    from ops.executive_os.acceptance import _uid_sweep_is_passing

    attested = _passing_v2_receipt()
    absent = _passing_v2_receipt(
        ambient_pids=[],
        ambient_identities=[],
        ambient_attribution="absent",
    )
    assert uid_sweep_receipt_is_passing(attested) is True
    assert _uid_sweep_is_passing(attested) is True
    assert uid_sweep_receipt_is_passing(absent) is True
    assert _uid_sweep_is_passing(absent) is True
