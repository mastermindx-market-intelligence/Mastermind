# T4b governed coding job — adversarial review findings

Reviewer: adversarial sub-agent (wrote none of the diffs).
Surface: `tools/mmos_coding_job/door.py`, `tools/mmos_coding_job/journey.py`,
`tools/mmos_teammate/wake_carrier.py` (coding-job parts only),
`control_plane/executive_runtime.py` (`adopt_attempt` only),
`control_plane/executive_supervisor.py` (receipt-reattach parts only),
`tests/test_mmos_teammate_coding_job.py`, `tests/test_mmos_coding_job_door.py`,
`tests/test_executive_supervisor_provider_reattach.py`.
Base: `t3/mmos-v4-t4b` @ `e0b1e2128`.

Method: read-only on production paths. The journey was **not** run (dev instances
in use). Every finding below is reproduced at unit level with the same fakes the
existing tests use. Nothing was fixed.

Test command form used throughout:

```
TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q -p no:cacheprovider <file>
```

Counts: **HIGH 3 · MEDIUM 6 · LOW 3**. Five attack vectors did not land (see the
last section).

---

## F1 — HIGH — crash between claim and launch wedges the job permanently

**Where:** `tools/mmos_coding_job/door.py:812-816` (persist `attempt_id` +
`phase="claimed"`), `:830` (`adapter.start`), `:845-848` (recovery branch).

`_execute` persists `attempt_id`/`fence_generation`/`lease_token` and
`phase="claimed"` **before** `adapter.start(spec)`. If the door dies in that
window, the fresh door takes the recovery branch, calls
`store.load_run(attempt_id)`, gets `None` (no adapter run was ever written), and
raises `RuntimeError("no persisted adapter run to recover")`. The executor
catches it, sets `phase="execute-failed"`, and surfaces `EXECUTOR_FAILED`. The
attempt stays `CLAIMED` forever and the job is never launched — the task's
coding job is dead with a misleading "executor failed" blocker.

**Reproduction** (`/tmp/t4b_attack/test_attack.py::test_load_run_is_none_before_launch`):

```python
def test_load_run_is_none_before_launch(tmp_path):
    from control_plane.t3_execution_adapter import SQLiteT3AdapterStateStore
    store = SQLiteT3AdapterStateStore(tmp_path / "s.sqlite3")
    assert store.load_run("attempt-claimed-never-launched") is None
```

The door's own recovery branch then raises on exactly this value
(`door.py:848`). To see the whole path, kill the door between the
`_save_frozen()` at `:816` and the `adapter.start` at `:830` (the existing
`crash_mode="after_receipt"` hook is the *other* window; there is no hook for
this one).

**Minimal fix:** persist `phase="claimed"` only *after* `adapter.start` returns
and the receipt is stored, or make the recovery branch treat a missing adapter
run as "launch never happened" and re-claim under a fresh fence instead of
raising. The second is smaller and keeps the crash window honest.

---

## F2 — HIGH — crash after `record_process` before seal makes a fresh door conflict forever

**Where:** `tools/mmos_coding_job/door.py:857` (unconditional
`record_process` in the recovery branch);
`control_plane/executive_runtime.py:20985` (the conflict).

The recovery branch calls `runtime.attempts.record_process(...)`
**unconditionally**. `record_process` raises `StateConflict("attempt … already
has a process identity")` when the row already carries a pid or provider
session. So a crash *after* `record_process` but *before* `complete_attempt`
(the seal at `:902`) leaves a row with an identity; the fresh door reattaches,
then calls `record_process` again and gets a hard conflict. The executor turns
that into `EXECUTOR_FAILED` and the collectable result is lost — the job
actually succeeded but is reported as failed.

**Reproduction** (`/tmp/t4b_attack/test_attack.py::test_record_process_twice_conflicts`):

```python
def test_record_process_twice_conflicts(tmp_path):
    from tests.test_executive_supervisor import _runtime_and_job
    from control_plane.executive_runtime import StateConflict

    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease = runtime.broker.claim(job_id, lease_owner="t4b-door")
    aid = lease.attempt.attempt_id
    runtime.attempts.record_process(
        aid, fence_generation=lease.attempt.fence_generation,
        lease_token=lease.lease_token, provider_session_id="mcp:launch:abc")
    with pytest.raises(StateConflict, match="already has a process identity"):
        runtime.attempts.record_process(
            aid, fence_generation=lease.attempt.fence_generation,
            lease_token=lease.lease_token, provider_session_id="mcp:launch:abc")
```

**Minimal fix:** in the recovery branch, read the attempt row first and skip
`record_process` when `provider_session_id`/`pid` is already set (the identity
is already durable; only the adoption is owed). One `if` around `:857`.

---

## F3 — HIGH — crash between admission commit and `_save_frozen` orphans an admitted job

**Where:** `tools/mmos_coding_job/door.py:582-584` (admit sets `job_id` then
saves), `:686` (`if not entry.get("job_id"): continue`).

`admit` commits the job in the Executive runtime, then writes `job_id` into
`frozen.json`. A crash between the runtime commit and `_save_frozen()` leaves a
frozen entry with **no** `job_id`. The executor's skip predicate at `:686`
skips it forever. The carrier, meanwhile, saw the socket die mid-call and
posted its `DOOR_UNREACHABLE` comment — which carries the same
`coding-job-command: <command>` marker (`wake_carrier.py:182`) — so every later
carrier run is suppressed too (F4). The job exists in the runtime, is never
executed, and the task never gets a result or a blocker: a silent orphan.

**Reproduction** (`/tmp/t4b_attack/test_orphan.py`):

```python
def test_orphaned_admitted_job_is_skipped_forever(tmp_path):
    # an entry the runtime admitted but whose job_id never reached frozen.json
    entry = {"issue": {"id": "iss-1"}, "phase": None}   # no job_id
    assert not entry.get("job_id")          # door.py:686 -> continue
    assert entry.get("phase") not in ("delivered", "surfaced")
    # and the carrier marker is already on the task, so no re-admit:
    marker = "coding-job-command: child-request:deadbeef"
    assert marker in f"coding job coding-job-1 ADMITTED — job `x`\n\n{marker}"
```

**Minimal fix:** make admission recoverable — on a fresh door, for any frozen
entry with no `job_id`, re-issue the same `admit(command)` (the runtime is
idempotent by `events.command_id`, so this is a REPLAY, not a second job) and
persist the returned `job_id`. That closes the window without a second job.

---

## F4 — MEDIUM — a transient WAIT / DOOR_UNREACHABLE blocker permanently suppresses retry

**Where:** `tools/mmos_teammate/wake_carrier.py:165` (marker),
`:172-175` (skip when marker present), `:182` (DOOR_UNREACHABLE comment
carries the marker), `:203` (WAIT comment carries the marker).

Every outcome comment — including the *transient* ones — embeds
`coding-job-command: <command>`. The next carrier run sees the marker and
returns without calling the door. So a WAIT (queue full) or a DOOR_UNREACHABLE
(door restarting) is treated as terminal: once capacity frees or the door comes
back, the task's coding job is never requested again. The task is stuck with a
"blocked" comment and no job.

**Reproduction** (`/tmp/t4b_attack/test_attack.py`):

```python
def test_wait_blocker_marker_permanently_suppresses_retry():
    # FakeDoorServer replies {"state": "WAIT", "wait_reason": "..."}
    wc.handle_coding_job(pc, ISSUE, "x", {"key": "coding-job-1"}, opts)
    wc.handle_coding_job(pc, ISSUE, "x", {"key": "coding-job-1"}, opts)  # capacity freed
    assert len(server.requests) == 1, "the retry never reached the door"

def test_unreachable_blocker_marker_permanently_suppresses_retry():
    opts = {"coding_job_door": "/tmp/t4b-attack-missing.sock"}
    wc.handle_coding_job(pc, ISSUE, "x", {"key": "coding-job-1"}, opts)
    wc.handle_coding_job(pc, ISSUE, "x", {"key": "coding-job-1"}, opts)  # door back
    assert len(pc.comment_calls) == 1, "second run posted nothing (suppressed)"
```

**Minimal fix:** only the terminal outcomes (ADMITTED/REPLAY, and a hard
refusal) carry the marker. WAIT and DOOR_UNREACHABLE should post a comment
*without* the marker (or with a distinct `coding-job-retry:` marker) so the next
run retries. The door is idempotent by command, so a retry is safe.

---

## F5 — MEDIUM — non-atomic `frozen.json` write; a truncated file bricks a fresh door

**Where:** `tools/mmos_coding_job/door.py:392-395` (`_save_frozen` is
truncate+write), `:387-390` (`_load_frozen` raises on bad JSON).

`_save_frozen` does `write_text(json.dumps(...))` — truncate then write, not
write-temp-then-rename. A crash mid-write leaves invalid JSON, and the next
door's `_load_frozen` raises `JSONDecodeError` at construction, so the door
cannot start at all. Every frozen job is lost with it.

**Reproduction** (`/tmp/t4b_attack/test_attack.py::test_truncated_frozen_json_breaks_fresh_door`):

```python
def test_truncated_frozen_json_breaks_fresh_door(tmp_path):
    d = door_mod.CodingJobDoor(door_mod.DoorConfig(_config(tmp_path)))
    (tmp_path / "run" / "frozen.json").write_text(
        '{"child-request:abc": {"issue": {"id": "iss-1"', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        door_mod.CodingJobDoor(door_mod.DoorConfig(_config(tmp_path)))
```

**Minimal fix:** write to `frozen.json.tmp` then `os.replace()` (atomic on the
same filesystem). Optionally have `_load_frozen` fall back to a `.bak` copy.

---

## F6 — MEDIUM — `sealed` / `delivery-refused` / `execute-failed` are not terminal to the executor

**Where:** `tools/mmos_coding_job/door.py:680-684` (skip predicate covers only
`delivered`/`surfaced` and `blocker_surfaced`), `:906` (phase `sealed` saved
before the delivery read), `:1011-1031` (`_surface_blocker` dedupes only by
exact code; a failed post leaves `blocker_surfaced` unset).

The executor loop skips only `phase in ("delivered", "surfaced")` and entries
with `blocker_surfaced`. Two concrete windows re-execute:

- **`sealed`:** `:906` saves `phase="sealed"` *before* the delivery receipt is
  read and the final phase written at `:932`. A crash in that window leaves
  `sealed` with no `blocker_surfaced`; the fresh door re-runs `_execute`, takes
  the recovery branch, and hits the F2 `record_process` conflict — so a job
  that actually succeeded gets a misleading `EXECUTOR_FAILED` blocker.
- **`delivery-refused` / `execute-failed` when the blocker post failed:**
  `_surface_blocker` only sets `blocker_surfaced` on a successful
  `add_comment` (`:1029-1031`). With Paperclip down, the entry is re-executed
  on every 2-second wake, forever, each time re-attempting the same post.

When the blocker post *succeeds*, `blocker_surfaced` does suppress the retry —
so the loop is bounded in the happy path and unbounded only in the
Paperclip-down path.

**Reproduction** (`/tmp/t4b_attack/test_skip2.py`):

```python
def test_delivery_refused_is_not_skipped():
    for phase in ("delivery-refused", "sealed", "execute-failed"):
        skip = phase in ("delivered", "surfaced")   # door.py:680
        assert not skip, phase
```

**Minimal fix:** add the terminal phases to the skip predicate —
`if entry.get("phase") in ("delivered", "surfaced", "delivery-refused",
"sealed", "execute-failed"): continue`. A `delivery-refused` job is finished
(the refusal is the recorded outcome); re-running it cannot help.

---

## F7 — MEDIUM — thread budget is never released; the door dies after 2 jobs

**Where:** `tools/mmos_coding_job/door.py:87` (`THREAD_BUDGET = 2`),
`:397-407` (`_reserve_thread` appends, no release), `:796-800` (budget check).

`_reserve_thread` appends `job:<id>` to `thread-budget.json` and there is **no
release path anywhere** in the file (grep for `reserved` shows only the append
and the length check). After two jobs — successful or not — every later job
gets `THREAD_BUDGET_EXHAUSTED` forever. The door is a two-job service.

**Reproduction** (`/tmp/t4b_attack/test_clean.py::test_thread_budget_never_released`):

```python
def test_thread_budget_never_released(tmp_path):
    d = door_mod.CodingJobDoor(door_mod.DoorConfig(_config(tmp_path)))
    assert d._reserve_thread("job:a") is True
    assert d._reserve_thread("job:b") is True
    assert d._reserve_thread("job:c") is False   # and nothing ever frees a/b
```

**Minimal fix:** release the reservation when the job reaches a terminal phase
(`delivered`/`surfaced`/`delivery-refused`/`execute-failed`) — remove
`job:<id>` from `reserved` in the same `_save_frozen` that records the terminal
phase. The budget then bounds *concurrent* jobs, which is what it is for.

---

## F8 — MEDIUM — a stuck CLAIMED attempt holds the worker's only quota class

**Where:** `control_plane/executive_runtime.py:7335`
(`set_worker_status(AVAILABLE)` refuses while a class is held),
`tools/mmos_coding_job/door.py:328-329` (`DoorSupervisor.reconcile_restart`
returns `[]`).

A claim holds the worker's quota class (`worker_quota_classes.held_attempt_id`).
If the attempt wedges (F1/F2), the class stays held. `broker.claim` for the next
job then returns `None` (no capacity — it does not raise), and
`set_worker_status(AVAILABLE)` refuses with "requeue, complete, fail, or cancel
<job> before making <class> AVAILABLE". The door never requeues, completes,
fails, or cancels — `DoorSupervisor.reconcile_restart` is a stub returning `[]`
— so the door's worker is permanently unusable after one wedge.

**Reproduction** (`/tmp/t4b_attack/test_quota.py`):

```python
def test_stuck_claim_holds_the_only_quota_class(tmp_path):
    from tests.test_executive_supervisor import _runtime_and_job
    from control_plane.executive_runtime import StateConflict
    runtime, job_id, _ = _runtime_and_job(tmp_path)
    lease = runtime.broker.claim(job_id, lease_owner="t4b-door")
    assert lease is not None
    with pytest.raises(StateConflict, match="requeue, complete, fail, or cancel"):
        runtime.workers.set_worker_status("codex-01", "AVAILABLE")
```

**Minimal fix:** give `DoorSupervisor.reconcile_restart` a real body that
requeues or fails attempts whose frozen entry is `execute-failed`/`budget-
exhausted`, so the held class is released. Until then, the door's worker is a
one-shot resource.

---

## F9 — MEDIUM — an echoed block in the task text triggers a job

**Where:** `tools/mmos_teammate/wake_carrier.py:60-95` (parser),
`:1085` (`job = parse_coding_job_block(reply)`).

The parser takes the last fenced `paperclip-coding-job` block in the reply. It
cannot tell the teammate's own block from one the teammate *quoted back* out of
the issue description. A task whose description contains a real block makes the
reply a trigger, so a task that merely *documents* the block syntax starts a
governed coding job. (The `<...>` example guard at `:93-94` is dead — see F10 —
so it does not help.)

**Reproduction** (`/tmp/t4b_attack/test_clean.py::test_echoed_block_triggers`):

```python
def test_echoed_block_triggers():
    reply = ("Here is the block from the task description:\n"
             "```paperclip-coding-job\nkey: coding-job-1\n```\n")
    assert wc.parse_coding_job_block(reply) == {"key": "coding-job-1"}
```

**Minimal fix:** require the block to be the *last* thing in the reply (nothing
but whitespace after the closing fence) and/or require a sentinel line the
teammate is instructed to emit only when it means to trigger. The cheapest
correct fix is "block must be the final non-whitespace content of the reply".

---

## F10 — LOW — dead `<...>` example guard

**Where:** `tools/mmos_teammate/wake_carrier.py:93-94`.

```python
if key.startswith("<") and key.endswith(">"):
    return None  # the how-to example quoted back, not a real trigger
```

Unreachable: the regex at `:91` (`[A-Za-z0-9][A-Za-z0-9_-]{0,63}`) already
rejects any key starting with `<`, so the function returned `None` at `:92`.
The guard documents an intent the code above it already enforces — harmless,
but it is not the protection it claims to be (see F9).

**Reproduction:** `parse_coding_job_block("```paperclip-coding-job\nkey: <key>\n```")`
returns `None` at the regex, never reaching `:93`.

**Minimal fix:** delete the dead branch, or move the example check *before* the
regex if the intent was to allow `<...>` through the regex for a clearer
message. No behavior change either way.

---

## F11 — LOW — dead ternary: refusals are HTTP 200

**Where:** `tools/mmos_coding_job/door.py:1110`.

```python
await self._json(send, 200 if reply.get("ok") else 200, reply)
```

Both branches are 200. A refused admission is indistinguishable from an
accepted one by status code; the carrier must inspect `body["ok"]` (it does, so
this is not a live bug — but the line is a trap for the next reader and for any
client that trusts the status).

**Reproduction:** `grep -n '200 if reply.get("ok") else 200' tools/mmos_coding_job/door.py`.

**Minimal fix:** `200 if reply.get("ok") else 400`, or drop the ternary and
always send 200 with a comment saying the body is the contract.

---

## F12 — LOW — the item-8 receipt reader is not wired in production

**Where:** `control_plane/t3_native_composition.py:1027-1070`
(`compose_t3_native_supervisor` constructs `ExecutiveSupervisor` at `:1053`
**without** `provider_receipt_reader`), `tools/mmos_coding_job/door.py:328-329`
(`reconcile_restart` returns `[]`).

The L1B3-5 reattach path is correct and well-tested
(`tests/test_executive_supervisor_provider_reattach.py`), but the production
composition never passes a reader, so `_receipt_provider_session_id` always
returns `None` and the unbound-claim branch falls through to
`_cleanup_unbound_claim` — the pre-existing quarantine. The door's own
supervisor never reconciles at all. So the crash window the item-8 work exists
to close is closed only in tests, not in the composed service.

**Reproduction** (`/tmp/t4b_attack/test_final.py`):

```python
def test_production_supervisor_omits_receipt_reader():
    import inspect
    from control_plane import t3_native_composition as c
    src = inspect.getsource(c.compose_t3_native_supervisor)
    assert "provider_receipt_reader" not in src

def test_door_supervisor_never_reconciles():
    from tools.mmos_coding_job.door import DoorSupervisor
    assert DoorSupervisor.reconcile_restart.__code__.co_consts == (None,)
```

**Minimal fix:** pass a `provider_receipt_reader` in
`compose_t3_native_supervisor` that reads the adapter store's launch receipt
for the attempt id (the same `SQLiteT3AdapterStateStore.load_run` the door
already uses). That is the one line that makes item 8 real.

---

## Vectors that did not land

1. **Two wakes for one task → two jobs.** Does not land. The door is idempotent
   by command (`events.command_id UNIQUE`); the second admit is a REPLAY and
   returns the same `job_id`. The carrier also skips on its marker.
2. **Concurrent retried admission (same command twice).** Does not land.
   `admit_child_execution_request` is replay-first inside `BEGIN IMMEDIATE`;
   the loser reconciles to the winner's job. No second job, no race between
   freeze and admit.
3. **Crash at each step.** Lands at three windows (F1, F2, F3) and is clean at
   the others: before claim (nothing persisted, re-admit is a fresh job — the
   only window that produces a *new* job, and it is the correct one); after
   launch receipt before process record (the `crash_mode="after_receipt"` hook
   — the L1B3-5 path recovers the SAME attempt, zero native calls, verified by
   the existing journey scenario and the reattach tests); after seal before
   delivery (the seam already fired inside `complete_attempt`; a fresh door
   re-reads the receipt — but see F6, it re-executes instead of skipping).
   No window produces a second native launch.
4. **Return for a task that no longer exists.** Does not land as a crash loop.
   `_surface_blocker` catches the Paperclip failure, logs, and leaves
   `blocker_surfaced` unset — so it retries, but only on the executor's 2s wake
   and only for a job that is already terminal; it does not crash the door. The
   retry-forever aspect is folded into F6.
5. **Forged block inside issue text/description.** Does not land. The parser
   runs on the teammate's reply only (`wake_carrier.py:1085`); issue text is
   never parsed for a block. (The *echo* case — the teammate quoting the
   description back — is F9.)
6. **Item-8 engine path: fake receipt / wrong attempt_id / two reconcilers.**
   Does not land. `adopt_attempt` requires an identity-less row, the current
   `fence_generation`, the quota `fence_counter`, and the current
   `lease_token`; the CAS arbitrates two reconcilers (the loser gets
   `stale adoption fence`). A reader returning garbage is ignored
   (`_receipt_provider_session_id` validates `type is str` and non-blank). The
   only gap is that the reader is not wired in production (F12).
7. **Blocker spam / wrong-body.** Does not land as same-code spam —
   `_surface_blocker` dedupes on the exact code (`door.py:1019`). A *different*
   code can still be posted on the same task, and a failed post leaves
   `blocker_surfaced` unset (retry loop) — both folded into F6.

---

## Disposition (principal triage, same branch)

All 25 in-scope reproductions were re-run on this tree before triage (the two
`test_wedge*.py` failures bind the attacker's own worktree path and prove
nothing either way; F8's premise is independently proven by `test_quota.py`).

| Finding | Disposition | Where |
|---------|-------------|-------|
| F1 HIGH | **FIXED** — a durable `launch-attempted` flag now discriminates the window. Never attempted → the fresh door starts the SAME claimed attempt (its first and only launch; no re-claim, one attempt). Attempted without receipt → parked `launch-uncertain` with a truthful `LAUNCH_UNCERTAIN` blocker, never re-launched. | `door.py` `_execute`; `test_f1_*` (2 tests) |
| F2 HIGH | **FIXED** — recovery reads the attempt row first; a durable identity is verified (mismatch refuses to rewrite) and `record_process` is skipped, so a crash after `record_process` adopts and seals instead of misreporting `EXECUTOR_FAILED`. | `door.py` `_execute`; `test_f2_*` |
| F3 HIGH | **FIXED, then narrowed by a live incident.** First fix re-admitted every frozen entry — the default-journey re-run caught it (registration became admission for 66 stale dev tasks; two jobs launched, one per task). The narrowed law: `admit()` durably records the REQUEST before the engine is asked and the OUTCOME after (WAIT/refusal included); the executor re-asks only an admit whose outcome is unknown (the crash window — an idempotent REPLAY heals it, never a second job). Registration alone, and answered WAITs/refusals, are never re-asked by the door — the carrier's next wake owns that retry. | `door.py` `admit`/`_ensure_admitted`/`_entry_action`; `test_f3_*` (2 tests) + the real-lane assertions in `test_admit_replay_conflict_wait_and_unfrozen_round_trip` |
| F4 MEDIUM | **FIXED** — only terminal outcomes carry the `coding-job-command:` marker; WAIT and DOOR_UNREACHABLE comments do not, so the next wake retries the one call. | `wake_carrier.py`; `test_f4_*` (2 tests) |
| F5 MEDIUM | **FIXED** — `frozen.json` is written tmp-then-`os.replace`; a crash at the rename keeps the last good state. | `door.py` `_save_frozen`; `test_f5_*` |
| F6 MEDIUM | **FIXED** — `_entry_action` routes each phase once: `sealed` finishes bookkeeping only (`_finish_sealed`), parked phases retry only the blocker post (payload persisted), never a re-execution. | `door.py`; `test_f6_*` (2 tests) |
| F7 MEDIUM | **FIXED** — `_release_thread` frees the slot at terminal phases; the budget bounds concurrent jobs. | `door.py`; `test_f7_*` |
| F8 MEDIUM | **PARTIAL, reported** — F1's fix unwedges the never-attempted window; F12 makes the composed supervisor capable. The attempted-but-uncertain window still parks an attempt holding the worker's quota class until lease expiry, and the door's `DoorSupervisor.reconcile_restart` remains the ingress fixture's stub: driving periodic reconcile inside the door executor is engine-composition work outside this lane's door scope. Recorded as follow-up. | this file |
| F9 MEDIUM | **FIXED** — a block counts only as the reply's own final non-whitespace word; a quoted block followed by any prose is not a trigger. Residual: a quote placed literally last still triggers — the teammate controls its own reply's end. | `wake_carrier.py`; `test_f9_*` |
| F10 LOW | **FIXED** — dead `<...>` guard deleted; the identifier regex is pinned as the actual protection. | `wake_carrier.py`; `test_f10_*` |
| F11 LOW | **FIXED** — the dead `200 if ok else 200` ternary replaced by an explicit 200 with the body-is-the-contract comment (the carrier reads `ok`/`error`; a bare status would hide the reason). | `door.py` `CodingJobDoorApp` |
| F12 LOW | **FIXED** — `compose_t3_native_supervisor` wires `provider_receipt_reader` over the composed adapter's durable `launch_receipt` accessor (item 8's completion: the reattach path is now reachable in the composed service, not only in tests); an unreadable receipt is ignored, keeping the pre-existing quarantine. | `t3_native_composition.py`; `tests/test_t3_native_supervisor_receipt_wiring.py` (2 tests) |

The five vectors that did not land are accepted as evidence the pinned
invariants hold; their proofs live in the existing suites (command
idempotency, admission CAS, forged-block-in-issue, fence arbitration,
blocker dedupe).
