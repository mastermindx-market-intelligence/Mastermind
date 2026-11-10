# T4b run book — the governed coding job, end to end, on dev instances

One command per journey scenario over the REAL pieces: dev Paperclip (3190),
dev T3 server (3790–3810), the scratch Executive door as its own process, the
REAL wake-carrier coding-job act (headless — the teammate's reply text is the
only trigger), ONE native launch through the t3-native adapter, the
execution-return seam with the `paperclip_task` transport, and the result
landing on the SAME task it came from. Design and decisions:
`T4B_DECISIONS.md`. Boundaries: `LANE_RULES_V4.md`.

## Prerequisites (once)

```bash
tools/mmos_dev/paperclip_dev.sh up     # dev Paperclip on 127.0.0.1:3190
tools/mmos_dev/t3_dev.sh start         # dev T3 server on its dev-range port
```

The worker project on the dev T3 server (`mcp:370a922f-6b11-4fa6-8f37-2d25a2ab37a8`,
workspace `~/.mastermind/mmos-dev/t3/mastermind-clone`) and the worker
`.gitconfig` under `~/.mastermind/mmos-dev/t3/claude-home/` were provisioned
once during bring-up; the journey reuses them and re-creates nothing.

## The journeys (from the repo root)

```bash
TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 \
  tools/mmos_coding_job/journey.py --scenario default
```

Swap `default` for `crash`, `wait`, or `undeliverable`. Add `--keep` to print
and keep the scratch root (door config, door.log, the Executive store, the
native-call census) for inspection. Each run creates its own task, its own
scratch root, and stops the door it started; nothing dials 3100/3780/3773.

Each scenario prints the summary block — **task id, job id, attempt id,
native launches (must be 1 for default/crash), phase, delivery, and where the
result landed** — then `PASS` or `FAIL`.

| scenario | proves | PASS means |
|---|---|---|
| `default` | goal 1+2: one task → ONE coding job → sealed → result comment on the SAME task, no window | phase `delivered`, native launches 1, a `paperclip-return-attempt:` comment on the task |
| `crash` | goal 3 (L1B3-5): door dies (exit 90) between launch receipt and process record; a FRESH door recovers the SAME attempt | same attempt id after recovery, native launches STILL 1, result still lands |
| `wait` | goal 4a: fleet queue full — the second task gets WAIT and a precise blocker comment, no job created | blocker body carries `CHILD_QUEUE_FLEET_READY_FULL`, no `job_id` for the waiting task |
| `undeliverable` | goal 4b: transport withheld — the refused receipt is surfaced as a blocker with its code | phase `delivery-refused`, blocker carries `ORIGIN_KIND_UNKNOWN` |

## What the worker does (dev shape)

The door's worker prompt asks the T3 worker to create
`integrations/mmos/canary/T4B_JOB_<attempt>.md`, commit only that file on its
job branch, push, and reply `T4B-JOB-OK <attempt> <sha>` — exactly the
canary's GitHub-evidence shape: a branch on the existing repo, no PR against
`master`, no new repository.

## Tests

```bash
TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
  -p no:cacheprovider tests/test_mmos_teammate_coding_job.py \
  tests/test_mmos_coding_job_door.py tests/test_paperclip_result_delivery.py
```
