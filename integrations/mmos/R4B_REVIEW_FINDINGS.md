# R4b: independent read-only review of the governed coding job (2026-11-11)

Reviewer: claude-opus-5-5, read-only, wrote none of the code. Scope: `git diff 666352409 4ec9e58dd`
(lane T4b). The principal re-ran the reviewer's five reproductions on trunk; all five reproduce.
They are in the appendix. Line numbers are as of trunk `81bac7b0d`.

**Verdict: not safe to build on.** No path to a second native launch was found: the adapter's
durable launch-intent claim (`t3_execution_adapter.py:2102-2120`) refuses a second `start` for
the same run, and that is the real guard. But the new engine reattach strands the attempt, a
reconcile pass during a live launch would cancel the only native thread, and the door reports
some successful jobs as failed.

## Findings and what the principal decided

| # | Sev | State | Where | What goes wrong | Decision |
| --- | --- | --- | --- | --- | --- |
| 1 | HIGH | reproduced | `executive_supervisor.py:5475`, `:5014` | `_adopt_with_receipt_identity` calls `adopt_attempt`, which rotates the fence and returns a new lease token. The token is dropped, no running record is made, `take_recovered_runs()` returns nothing. Only `provider_session_id` is recorded: no `worker_recovery_binding`, no `execution_mode`. Every later pass sees presence UNKNOWN (`t3_native_composition.py:863`) and returns `IDENTITY_AMBIGUOUS`. Nobody can heartbeat, complete or fail the attempt; its quota class stays held; the result is never collected. Tests assert only the first reconcile's status. | Fix in T4c: reattach through the adapter's `reattach`, persist a `worker_recovery_binding` in the same transaction, hand the adopted lease to the recovered-runs list (the existing `_recover_existing_attempt` shape). |
| 2 | HIGH | reproduced at engine level | `executive_runtime.py:20510`, `executive_supervisor.py:5468-5480`, `:3236`, `:3304` | `adopt_attempt` adopts only unexpired leases. If `reconcile_restart` runs while a live `start_job` is between `put_launch_receipt` and `record_process`, the receipt branch rotates the fence away from the live launcher; its `record_process` raises `StateConflict`, and its exception path calls `adapter.cancel` on the job's only thread. Latent today because reconcile runs only at restart; real as soon as a periodic reconcile or a second supervisor exists. | Fix in T4c before any periodic reconcile: reattach only when the lease has expired or its owner is provably not a live instance (`adopt_attempt` takes an expected `lease_owner`, or an expired-lease variant). |
| 3 | HIGH | reproduced | `door.py:1085-1090`, seam at `executive_runtime.py:21562` | A crash after the seal commits but before `phase="sealed"` is saved (the window includes the whole Paperclip delivery, seconds long). On restart the entry is still `launched`; recovery calls `adopt_attempt` on a COMPLETED attempt, gets `StateConflict`, and records `EXECUTOR_FAILED`. If the comment had not landed, the result is lost. | Fix in T4c: at the top of the recovery branch read the attempt's status; if terminal, finish as sealed and drive the seam again when no receipt event exists (the receipt command id and the comment marker prevent a duplicate). |
| 4 | HIGH | confirmed | `paperclip_result_delivery.py:191`, `door.py:1063`, `journey.py:153`, `wake_carrier.py:959`, `:1004` | The return comment carries the worker's text verbatim (up to 8000 characters) and is written with the local board identity. The carrier quotes the newest board comment as "The board wrote on the issue" and passes board comments to the teammate as notes. The principal confirms the premise on the installed Paperclip: comments written with the `local_trusted` header are `authorType: "user"`. So worker-written text can reach a teammate as the board's words. | Fix in two places. T4c: every comment the door or the transport writes starts with the line `[coding-job]`, and worker text is fenced as quoted output. Carrier (lane CQ follow-up): comments starting with `[coding-job]` or `[t2-carrier]` are never board notes, never board feedback, never an answer. A scoped writer identity is a later Paperclip-side decision and is recorded as open. |
| 5 | MEDIUM | confirmed | `wake_carrier.py:765-777` | `last_result_comment` filters only `[t2-carrier]`. The carrier's own "coding job …" comment, the door's `[t4b-door]` blockers and the result comment all pass, so an asking teammate can receive a job comment as the answer. Ask children are also taught the job block. | Carrier (CQ follow-up): the common prefixes above; the carrier's own job comment becomes `[t2-carrier] …`; a teammate answering an ask is not offered the job block. |
| 6 | MEDIUM | reproduced | `door.py:392-399` | Two threads write `frozen.json` with no lock and the same temp name; `os.replace` raises `FileNotFoundError`. After `adapter.start` this parks a launched job as `execute-failed`. | Fix in T4c: one lock around every change and save, a unique temp name, fsync of file and directory. |
| 7 | MEDIUM | traced | `door.py:1029-1046`, `LEASE_SECONDS=900` | After more than 900 seconds of door downtime `adopt_attempt` refuses the expired lease; recovery records `EXECUTOR_FAILED` while the thread runs or has finished. | Fix in T4c with finding 2: one expired-lease recovery path. |
| 8 | MEDIUM | traced | `door.py:814`, `:727` | The dev pin checks that something answers on the proof URL. The pairing command picks its server from `T3CODE_HOME`. A wrong or stale home with anything listening in 3790 to 3810 still mints a code on the live app (3773). | Fix first in T4c, before any journey runs: read the home's runtime state and refuse unless it names the pinned port. |
| 9 | MEDIUM | reproduced | `door.py:100` | `loopback_only` is a string prefix: it accepts `http://127.0.0.1:80@example.com` (real host `example.com`) and the installed Paperclip on 3100. | Fix in T4c: parse the host; the Paperclip base must match an explicit `host:port` allowlist from config. |
| 10 | MEDIUM | traced | `local_operator.py:206`, `door.py` intake | Any process running as the same user can admit a job on any task: admission is by uid, the command is a public hash of the issue id, and the door freezes every issue in the company. | Partly fixed in T4c: the door freezes only issues assigned to enrolled teammates, and admits only when the task itself shows the request (the assignee is enrolled and its newest agent comment carries the job block for that key). A separate uid for workers is not in this program; recorded as open. |
| 11 | LOW | confirmed | `door.py:930`, `:397` | The lease token is in `frozen.json`, created with default modes. | Fix in T4c: file 0600, directories 0700. |
| 12 | LOW | confirmed | `wake_carrier.py` `deliver()` | A WAIT or unreachable-door retry needs a later wake, and none comes by itself once the issue is in review. | T4c: a WAIT is retried by the door when capacity frees (same command, so still one admission). An unreachable door's blocker line says what to do. |
| 13 | LOW | confirmed | `door.py:988` | A `launch-uncertain` attempt gives back its thread slot while its thread may still run. | Fix in T4c: the slot is held until the attempt is reconciled. |
| 14 | LOW | plausible | `paperclip_result_delivery.py:452` | Dedupe depends on a complete comment listing. If the endpoint pages, a duplicate result comment is possible. | T4c checks paging on the dev Paperclip and fixes it if it pages. |
| 15 | LOW | confirmed | `T4B_CODING_JOB.md`, `T4B_DECISIONS.md` | The runbook says the crash journey recovers through `reconcile_restart`. The door's supervisor stub returns `[]`; recovery is the door's own `record_process` plus `adopt_attempt`. No journey exercises the engine reattach. | T4c: one owner. The door recovers through the engine's path, runs a real reconcile, and a journey proves it. This also closes attack finding F8. |

## Other things the review found

- `t3_live_proof.BASE` is fixed at import time and defaults to 3773 (`t3_live_proof.py:62`). It is
  safe only because the door imports it after setting its environment. T4c: the helper takes a
  required target and has no default.
- Neither the door nor the transport pins a Paperclip port (finding 9).
- The door sets `os.environ` for its whole process; every child inherits `T3CODE_*`.
- Of the lane's eleven "fixed" findings: F1, F2, F3, F7, F9, F10, F11 are closed. F4 is closed in
  the handler but its retry needs a wake (finding 12). F5 holds for one writer only (finding 6).
  F6 holds only for an entry already at `sealed` (finding 3). F12 is closed in
  `compose_t3_native_supervisor`, which the door does not use, and the path it wires strands the
  attempt (finding 1).
- Safe only because it is dev: the stub supervisor; the door doing the freeze act for every issue;
  the board identity as writer; uid-only admission with workers under the same uid; the fixed
  canary prompt (real issue text as a worker prompt is a prompt-injection channel and needs a
  decision); no Paperclip port pin; the 900-second lease.

## Not checked by the reviewer

Paperclip server code (comment paging, `clientRequestId` dedupe); the T3 command line's server
selection (it relied on the door's comment); `ExecutiveControlService` socket commands; SQLite
synchronous settings in the adapter store; all of `test_paperclip_result_delivery.py`; most of
`journey.py`. It ran no journey.

## Appendix: the reviewer's reproductions

Each test passes while the fault exists. Run from the repository root:
`TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q -p no:cacheprovider --rootdir=. <file>`.
`test_frozen_dump_races_intake` did not reproduce and is not a finding.

```python
"""Reviewer scratch reproductions (read-only on the checkout)."""
import json, threading, tempfile, urllib.parse
from pathlib import Path
from types import SimpleNamespace
import pytest

from tests.test_mmos_coding_job_door import _attack_door, _issue_row, scratch  # noqa: F401
from tests.test_executive_supervisor import _runtime_and_job, FakeAdapter, FakeInspector, _supervisor
from control_plane.executive_runtime import StateConflict
import control_plane.executive_supervisor as owner
from tools.mmos_coding_job import door as door_mod


def test_crash_after_seal_commit_before_phase_sealed_misreports(scratch, monkeypatch, tmp_path):
    """complete_attempt committed (seam fires after commit), door dies before
    phase='sealed' is saved. Fresh door routes to 'execute' -> recovery branch
    -> adopt_attempt on a COMPLETED attempt -> StateConflict -> EXECUTOR_FAILED."""
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease = runtime.broker.claim(job_id, lease_owner="t4b-door-dead")
    aid = lease.attempt.attempt_id
    runtime.attempts.record_process(aid, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, provider_session_id="mcp:launch:s")
    runtime.attempts.mark_running(aid, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token)
    runtime.attempts.complete_attempt(aid, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, payload={"summary": "ok", "artifacts": []})
    d = _attack_door(scratch, monkeypatch)
    command = d.freeze_issue(_issue_row("iss-x"))
    entry = d.frozen[command]
    entry.update({"job_id": "J", "attempt_id": aid, "phase": "launched",
                  "fence_generation": lease.attempt.fence_generation,
                  "lease_token": lease.lease_token})
    assert d._entry_action(entry) == "execute"   # not finish-sealed

    class _A:
        async def reattach(self, spec, binding):
            return SimpleNamespace(provider_session_id="mcp:launch:s")
    real_spec = d._launch_spec(run_id=aid, job_id="J",
        prompt=d._worker_prompt(aid, "t3/mmos-t4b-job-deadbeef"))
    fake_run = SimpleNamespace(spec=real_spec, original_ref=SimpleNamespace(
        provider_session_id="x", pid=None, run_id=aid))
    import control_plane.t3_execution_adapter as am
    monkeypatch.setattr(am, "SQLiteT3AdapterStateStore",
                        lambda _p: SimpleNamespace(load_run=lambda _r: fake_run))
    monkeypatch.setattr(d, "_compose_adapter", lambda *a, **k: (_A(), {}))
    with pytest.raises(StateConflict, match="cannot be adopted from COMPLETED"):
        d._execute(runtime, command, entry)


def test_receipt_adoption_discards_the_lease_and_wedges(tmp_path):
    """After the engine reattach, nobody holds the rotated token: a second
    reconcile is IDENTITY_AMBIGUOUS forever and the job never completes."""
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease = runtime.broker.claim(job_id, lease_owner="dead")
    adapter = FakeAdapter(FakeInspector())
    adapter.presence = lambda _a: owner.ProcessPresence.UNKNOWN
    adapter.absence_verified = lambda _a: False
    sup = _supervisor(runtime, tmp_path, adapter,
                      provider_receipt_reader=lambda _a: {"provider_session_id": "mcp:s"})
    first = sup.reconcile_restart(requeue_lost=True)
    assert [o.status for o in first] == [owner.ReconcileStatus.LIVE_QUARANTINED]
    assert list(sup.take_recovered_runs()) == []   # no ActiveRun kept the token
    second = sup.reconcile_restart(requeue_lost=True)
    assert [o.status for o in second] == [owner.ReconcileStatus.IDENTITY_AMBIGUOUS]
    row = runtime.attempts.get_attempt(lease.attempt.attempt_id)
    assert "worker_recovery_binding" not in row.launch_metadata


def test_receipt_reconcile_fences_out_a_live_launcher(tmp_path):
    """A reconcile pass that runs while the original launcher sits between
    put_launch_receipt and record_process rotates the fence away from it."""
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease = runtime.broker.claim(job_id, lease_owner="live-launcher")
    adapter = FakeAdapter(FakeInspector())
    adapter.presence = lambda _a: owner.ProcessPresence.UNKNOWN
    adapter.absence_verified = lambda _a: False
    sup = _supervisor(runtime, tmp_path, adapter,
                      provider_receipt_reader=lambda _a: {"provider_session_id": "mcp:s"})
    sup.reconcile_restart(requeue_lost=True)
    with pytest.raises(StateConflict):
        runtime.attempts.record_process(lease.attempt.attempt_id,
            fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token, provider_session_id="mcp:s")


def test_door_loopback_check_is_a_string_prefix():
    for url in ("http://127.0.0.1:3100", "http://127.0.0.1:80@example.com"):
        assert door_mod.loopback_only(url, "x")
    assert urllib.parse.urlsplit("http://127.0.0.1:80@example.com").hostname == "example.com"


def test_frozen_dump_races_intake(scratch, monkeypatch):
    d = _attack_door(scratch, monkeypatch)
    for i in range(2000):
        d.frozen[f"k{i}"] = {"x": "y" * 200}
    errors = []
    stop = threading.Event()
    def intake():
        i = 0
        while not stop.is_set():
            d.frozen[f"n{i % 50}"] = {"x": 1}
            d.frozen.pop(f"n{(i + 25) % 50}", None); i += 1
    t = threading.Thread(target=intake); t.start()
    try:
        for _ in range(100):
            try:
                d._save_frozen()
            except (RuntimeError, FileNotFoundError) as exc:
                errors.append(type(exc).__name__); break
    finally:
        stop.set(); t.join()
    assert errors, "no race observed this run"


def test_two_thread_saves_collide_on_tmp(scratch, monkeypatch):
    d = _attack_door(scratch, monkeypatch)
    for i in range(3000):
        d.frozen[f"k{i}"] = {"x": "y" * 100}
    errors = []
    def saver():
        for _ in range(30):
            try:
                d._save_frozen()
            except Exception as exc:  # noqa: BLE001
                errors.append(type(exc).__name__); return
    ts = [threading.Thread(target=saver) for _ in range(2)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert errors, "no collision this run"
    print(errors)
```
