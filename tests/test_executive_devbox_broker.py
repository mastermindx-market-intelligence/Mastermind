from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path

import pytest

from control_plane.executive_worker_broker import (
    BrokerPolicy,
    BrokerProtocolError,
    BrokerStateError,
    ExecutiveWorkerBroker,
    PeerCredentials,
    UIDSweepReceipt,
)

GENERATION = "generation:" + "2" * 64
PROCESS = "process:" + "a" * 64


class Sweeper:
    def __init__(self):
        self.reasons: list[str] = []
        self.residual = False

    def sweep(self, reason: str) -> UIDSweepReceipt:
        self.reasons.append(reason)
        return UIDSweepReceipt(
            schema_version="mastermind.executive_uid_sweep/v2",
            observed_at="2026-09-12T00:00:00+00:00",
            reason=reason,
            worker_uid=os.geteuid(),
            broker_pid=os.getpid(),
            residual_pids_before=(999,) if self.residual else (),
            residual_pids_after=(),
            signal_name="SIGKILL",
            signal_sent=self.residual,
            quiescent_observations=2,
            ambient_pids=(),
            ambient_identities=(),
            ambient_attribution="absent",
        )


class DevBoxAdapter:
    def __init__(self):
        self.starts: list[dict] = []
        self.reads: list[dict] = []
        self.cancels: list[dict] = []
        self.terminal = False
        self.exit_code = None
        self.stdout = ""
        self.stderr = ""

    async def status(self):
        return {
            "workspace_source": "b" * 40,
            "working_tree_dirty": False,
        }

    async def start(self, *, process_ref, command_text, timeout_seconds, output_limit_bytes):
        self.starts.append(
            {
                "process_ref": process_ref,
                "command_text": command_text,
                "timeout_seconds": timeout_seconds,
                "output_limit_bytes": output_limit_bytes,
            }
        )
        return {
            "process_ref": process_ref,
            "effect_state": "APPLIED",
            "terminal": False,
        }

    async def read(self, *, process_ref, stdout_cursor, stderr_cursor, max_bytes):
        self.reads.append(
            {
                "process_ref": process_ref,
                "stdout_cursor": stdout_cursor,
                "stderr_cursor": stderr_cursor,
                "max_bytes": max_bytes,
            }
        )
        stdout = self.stdout[stdout_cursor : stdout_cursor + max_bytes]
        stderr = self.stderr[stderr_cursor : stderr_cursor + max_bytes]
        return {
            "process_ref": process_ref,
            "effect_state": "APPLIED",
            "terminal": self.terminal,
            "exit_code": self.exit_code,
            "timed_out": False,
            "cancel_requested": bool(self.cancels),
            "stdout": {
                "text": stdout,
                "start_cursor": stdout_cursor,
                "next_cursor": stdout_cursor + len(stdout),
                "total_bytes": len(self.stdout),
                "retained_bytes": len(self.stdout),
                "dropped_bytes": 0,
                "truncated": False,
                "gap_ranges": [],
            },
            "stderr": {
                "text": stderr,
                "start_cursor": stderr_cursor,
                "next_cursor": stderr_cursor + len(stderr),
                "total_bytes": len(self.stderr),
                "retained_bytes": len(self.stderr),
                "dropped_bytes": 0,
                "truncated": False,
                "gap_ranges": [],
            },
        }

    async def cancel(self, *, process_ref, reason):
        self.cancels.append({"process_ref": process_ref, "reason": reason})
        self.terminal = True
        self.exit_code = -15
        return {
            "process_ref": process_ref,
            "cancel_requested": True,
            "terminal": True,
        }


def _fixture(tmp_path: Path):
    uid = os.geteuid()
    gid = os.getegid()
    control_uid = uid + 1000 if uid != 0 else 501
    roots = [tmp_path / name for name in ("workspaces", "runs", "provider-home")]
    for root in roots:
        root.mkdir(mode=0o700)
    policy = BrokerPolicy(
        control_uid=control_uid,
        worker_uid=uid,
        worker_gid=gid,
        worker_user="fixture-worker",
        worker_id="devbox-01",
        workspace_root=roots[0],
        run_root=roots[1],
        provider_home=roots[2],
        allowed_supplementary_gids=frozenset(set(os.getgroups()) - {gid}),
        require_secret_canary=False,
    )
    adapter = DevBoxAdapter()
    sweeper = Sweeper()
    broker = ExecutiveWorkerBroker(
        None,
        policy,
        sweeper,
        allowed_operations=frozenset(
            {"devbox-status", "devbox-start", "devbox-read", "devbox-cancel"}
        ),
        devbox_adapter=adapter,
        devbox_generation=GENERATION,
    )
    peer = PeerCredentials(uid=control_uid, gid=gid, pid=123)
    return broker, adapter, sweeper, peer


def _request(operation: str, payload: dict, *, request_id: str = "req-1") -> dict:
    return {
        "schema_version": "mastermind.executive_worker_broker_request/v1",
        "request_id": request_id,
        "operation": operation,
        "payload": payload,
    }


def _run(coro):
    return asyncio.run(coro)


def test_codespace_profile_exposes_only_devbox_operations(tmp_path: Path) -> None:
    broker, _adapter, _sweeper, peer = _fixture(tmp_path)
    status = _run(broker.execute(_request("devbox-status", {}), peer=peer))
    assert status["ok"] is True
    assert status["result"]["generation"] == GENERATION
    assert status["result"]["worker_uid"] == os.geteuid()

    for forbidden in ("start", "status", "collect", "cancel", "validate", "ohf-start"):
        with pytest.raises(BrokerProtocolError, match="profile"):
            _run(broker.execute(_request(forbidden, {}), peer=peer))


def test_devbox_start_is_at_most_once_within_generation(tmp_path: Path) -> None:
    broker, adapter, _sweeper, peer = _fixture(tmp_path)
    payload = {
        "generation": GENERATION,
        "operation_key": "codespace-op-1",
        "command_text": "printf once",
        "timeout_seconds": 30,
        "output_limit_bytes": 65536,
    }
    first = _run(broker.execute(_request("devbox-start", payload), peer=peer))["result"]
    second = _run(
        broker.execute(_request("devbox-start", dict(payload), request_id="req-2"), peer=peer)
    )["result"]

    assert first["process_ref"] == second["process_ref"]
    assert first["reconciled"] is False
    assert second["reconciled"] is True
    assert len(adapter.starts) == 1
    assert adapter.starts[0]["process_ref"] == first["process_ref"]
    assert first["process_ref"].startswith("process:")

    with pytest.raises(BrokerStateError, match="different payload"):
        _run(
            broker.execute(
                _request(
                    "devbox-start",
                    {**payload, "command_text": "printf changed"},
                    request_id="req-3",
                ),
                peer=peer,
            )
        )
    assert len(adapter.starts) == 1


def test_generation_mismatch_refuses_before_adapter(tmp_path: Path) -> None:
    broker, adapter, _sweeper, peer = _fixture(tmp_path)
    with pytest.raises(BrokerProtocolError, match="generation"):
        _run(
            broker.execute(
                _request(
                    "devbox-start",
                    {
                        "generation": "generation:" + "9" * 64,
                        "operation_key": "wrong-generation",
                        "command_text": "true",
                        "timeout_seconds": 30,
                        "output_limit_bytes": 65536,
                    },
                ),
                peer=peer,
            )
        )
    assert adapter.starts == []


def test_only_one_live_devbox_command_is_admitted(tmp_path: Path) -> None:
    broker, adapter, _sweeper, peer = _fixture(tmp_path)
    base = {
        "generation": GENERATION,
        "command_text": "sleep 30",
        "timeout_seconds": 30,
        "output_limit_bytes": 65536,
    }
    _run(
        broker.execute(
            _request("devbox-start", {**base, "operation_key": "one"}), peer=peer
        )
    )
    with pytest.raises(BrokerStateError, match="active"):
        _run(
            broker.execute(
                _request(
                    "devbox-start", {**base, "operation_key": "two"}, request_id="req-2"
                ),
                peer=peer,
            )
        )
    assert len(adapter.starts) == 1


def test_terminal_read_runs_canonical_uid_sweep_once_and_releases_slot(tmp_path: Path) -> None:
    broker, adapter, sweeper, peer = _fixture(tmp_path)
    start_payload = {
        "generation": GENERATION,
        "operation_key": "terminal",
        "command_text": "printf done",
        "timeout_seconds": 30,
        "output_limit_bytes": 65536,
    }
    started = _run(broker.execute(_request("devbox-start", start_payload), peer=peer))["result"]
    adapter.terminal = True
    adapter.exit_code = 0
    adapter.stdout = "done"

    read_payload = {
        "generation": GENERATION,
        "process_ref": started["process_ref"],
        "stdout_cursor": 0,
        "stderr_cursor": 0,
        "max_bytes": 65536,
    }
    first = _run(broker.execute(_request("devbox-read", read_payload), peer=peer))["result"]
    second = _run(
        broker.execute(_request("devbox-read", read_payload, request_id="req-2"), peer=peer)
    )["result"]
    assert first["terminal"] is True and first["exit_code"] == 0
    assert second["terminal"] is True and second["exit_code"] == 0
    assert sweeper.reasons.count("devbox_terminal") == 1

    next_start = {**start_payload, "operation_key": "after-terminal", "command_text": "true"}
    _run(
        broker.execute(_request("devbox-start", next_start, request_id="req-3"), peer=peer)
    )
    assert len(adapter.starts) == 2


def test_terminal_residual_is_cleaned_but_result_is_not_false_green(tmp_path: Path) -> None:
    broker, adapter, sweeper, peer = _fixture(tmp_path)
    started = _run(
        broker.execute(
            _request(
                "devbox-start",
                {
                    "generation": GENERATION,
                    "operation_key": "residual",
                    "command_text": "true",
                    "timeout_seconds": 30,
                    "output_limit_bytes": 65536,
                },
            ),
            peer=peer,
        )
    )["result"]
    adapter.terminal = True
    adapter.exit_code = 0
    sweeper.residual = True
    with pytest.raises(BrokerStateError, match="detached"):
        _run(
            broker.execute(
                _request(
                    "devbox-read",
                    {
                        "generation": GENERATION,
                        "process_ref": started["process_ref"],
                        "stdout_cursor": 0,
                        "stderr_cursor": 0,
                        "max_bytes": 65536,
                    },
                ),
                peer=peer,
            )
        )


def test_cancel_is_exact_generation_and_terminal_swept(tmp_path: Path) -> None:
    broker, adapter, sweeper, peer = _fixture(tmp_path)
    started = _run(
        broker.execute(
            _request(
                "devbox-start",
                {
                    "generation": GENERATION,
                    "operation_key": "cancel-me",
                    "command_text": "sleep 30",
                    "timeout_seconds": 60,
                    "output_limit_bytes": 65536,
                },
            ),
            peer=peer,
        )
    )["result"]
    result = _run(
        broker.execute(
            _request(
                "devbox-cancel",
                {
                    "generation": GENERATION,
                    "process_ref": started["process_ref"],
                    "reason": "attended stop",
                },
            ),
            peer=peer,
        )
    )["result"]
    assert result["cancel_requested"] is True
    assert adapter.cancels == [
        {"process_ref": started["process_ref"], "reason": "attended stop"}
    ]
    assert sweeper.reasons.count("devbox_terminal") == 1


def test_process_ref_is_bound_to_generation_and_operation_key(tmp_path: Path) -> None:
    broker, _adapter, _sweeper, peer = _fixture(tmp_path)
    payload = {
        "generation": GENERATION,
        "operation_key": "stable-key",
        "command_text": "true",
        "timeout_seconds": 30,
        "output_limit_bytes": 65536,
    }
    observed = _run(broker.execute(_request("devbox-start", payload), peer=peer))["result"][
        "process_ref"
    ]
    expected = "process:" + hashlib.sha256(
        (GENERATION + "\0" + "stable-key").encode("utf-8")
    ).hexdigest()
    assert observed == expected
