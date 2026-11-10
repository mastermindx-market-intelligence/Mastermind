# T4B decisions — the governed coding job joined to a Paperclip task

Lane T4b, 2026-11-10, branch `t3/mmos-v4-t4b`. Inputs: `CODING_JOB_REUSE_MAP.md`,
`LANE_RULES_V4.md`, plan V4 §4/§6/§9/§10/§15, plan V3 §8a, the T2/T45 carrier,
the L1 admitted canary. This file is the shape decision and the build-list map;
`T4B_CODING_JOB.md` (written with the code) is the run book.

## The shape chosen

The preferred shape holds, with one adjustment the engine's own law forces.

**One mechanism, third block.** The teammate's reply may end with a fenced
```paperclip-coding-job``` block (same family as `paperclip-ask` /
`paperclip-output`; only the teammate's own reply counts, a quoted example is
not taken, a malformed block is a plain answer). The block names at most a
`key:` (default `coding-job-1`) — which job of this task it is. The task itself
(title + description) is the job brief; the block is the trigger, not the brief.

**The carrier never carries the envelope.** The brief sketched "the carrier
builds the task-origin request and makes the one call". The admission frame
lane the engine already proved (L1B3-1, `tests/test_hermes_selected_child_
ingress.py`) requires the `ChildExecutionRequest.v1.2` envelope to be
**host-frozen** as `child_request_material` before the call, and the envelope
to never travel through the caller — the caller names a **command** only. So:

- The **builder** (`tools/mmos_coding_job/envelope.py`) runs host-side, at task
  intake: the dev Executive door watches the dev Paperclip company and freezes
  one envelope per new issue (triple `roots/paperclip-<issueId>` /
  `parents/paperclip-<issueId>` / `key=coding-job-1`, requester block
  `teammate_id=paperclip-agent:<agentId>`, `conversation_id=paperclip-issue:
  <issueId>`, `project_id=paperclip-company:<companyId>`,
  `carrier_kind=paperclip_task`, `brief_digest=sha256(title\ndescription)`).
  Freezing material admits nothing; it is registration.
- The **carrier** computes the same command id with a six-line stdlib mirror of
  `admission_command_id` (`"child-request:" + sha256(root \x1f parent \x1f
  key)` — pure function of the triple), and makes ONE call:
  `POST /paperclip/coding-job/admit {"command": …}` over the Unix socket door.
  A test pins the mirror byte-identical to the engine's function. The carrier
  stays stdlib-only (the installed teammates keep running it unchanged).
- The **door** is a dev harness process (`tools/mmos_coding_job/door.py`) that
  composes existing pieces only: a real `ExecutiveControlService` on a scratch
  root (the ingress tests' composition) with the CEO-ingress Unix socket, the
  real `CooApp.child_request_admit` (the existing admission entry, driven
  directly as its own tests drive it), and the real L4 `LocalOperatorListener`
  class bound at `<scratch>/local-operator.sock` — kernel peer-uid admission,
  no bearer, no header trust, no TCP. The App builds the private frame from
  its own providers; the Executive admits, refuses, or WAITs.

**Paperclip stays passive.** Paperclip never admits, schedules, retries or
accepts. The wake carrier is the only Paperclip-side actor, and its coding-job
act is exactly one admission call plus honest comments. The per-run Paperclip
token never leaves the carrier process; the door never sees it.

**Return transport.** A `paperclip_task` transport (`control_plane/
paperclip_result_delivery.py`, stdlib urllib only, refuses non-loopback bases
at construction) is registered in the `ResultDeliveryRegistry` at the seam
install site in the door (`install_execution_return_seam` with that registry
plus `GitHubEvidenceSource(repository=…, port=GhCliEvidencePort())`). When the
attempt seals, the seam projects `execution_return/v1` with real GitHub
evidence and the transport writes onto the SAME task named by the envelope's
requester block: one comment (result text + job/attempt ids + branch evidence)
and one issue document a person can open. Unknown kinds keep their typed
`ORIGIN_KIND_UNKNOWN` refusal (existing law). Delivery failures produce honest
refused receipts; the door's blocker surfacer then writes ONE blocker comment
on the task with code, reason and age — an Executive-side act, no retry loop.
Acceptance stays a human act on the task; this lane builds no confirmation and
changes no issue status in the transport.

**Blockers (goal 4).** Queue-full: the admission answer itself carries WAIT
with a precise reason; the carrier posts it as a blocker comment before its
run ends. Undeliverable return: the seam's refused receipt (e.g.
`ORIGIN_KIND_UNKNOWN` when the transport is deliberately not registered) is
surfaced on the task by the door. If Paperclip itself is unreachable, nothing
can write on the task; the receipt in the Executive store is then the record
and the journey prints it — that limit is honest, not papered over.

**Item 8 (L1B3-5), the engine fix.** Today an attempt crashed between
`put_launch_receipt` and `record_process` (CLAIMED, pid NULL, provider session
NULL, lease token lost with the dead process) cannot be adopted:
`adopt_attempt` refuses the missing identity, and `reconcile_restart`
classifies it for expiry → requeue → a SECOND launch. The fix adds exactly one
reattach path: `adopt_attempt(..., reattach_provider_session_id=…)` performs
the same CAS fence rotation and, in the same transaction, records the provider
session id taken from the **persisted adapter receipt** (durable evidence the
launch took effect) plus an `ATTEMPT_PROCESS_RECORDED` event; and
`ExecutiveSupervisor.reconcile_restart` consults an injected
`provider_receipt_reader` at the two classification points (unbound-claim
UNKNOWN, and the pid/provider-NULL branch) and recovers under a new fence
instead of expiring. Admission identity, fencing and the receipt rule are
untouched; the adapter's launch-claim still refuses any second start.

## Where this runs (instances and ports)

| Thing | Where |
|---|---|
| Dev Paperclip | existing dev instance `mmos-dev`, `127.0.0.1:3190`, root `~/.mastermind/mmos-dev/paperclip/` (`tools/mmos_dev/paperclip_dev.sh up`) |
| Dev T3 server | existing `t3-t2` root, port 3800, headless `t3 serve` via `tools/mmos_dev/t3_dev.sh` (`MMOS_T3_DEV_ROOT`) |
| Scratch Executive | `~/.cache/mmos-t4b-canary/` (the canary's scratch pattern): runtime, adapter store, CEO-ingress socket, `local-operator.sock` |
| Worker thread | the DEV T3 server only (never 3773/3774/3780), thread budget 2 reserved before minting (canary discipline), model `glm-5.3-flash` on the dev `capacity_fabric` instance |
| Worker source effect | exactly the canary's: one file, one commit, push to one new branch `t3/mmos-t4b-job-<digest8>`; no PR, no `master`, no new repository |

Production Executive, installed Paperclip (3100), team server (3780), the
Chairman's T3 app (3773/3774) and Hermes: never read for state, never written.

## Build-list map (item → file(s) → check)

| # | Item | Files | Check |
|---|---|---|---|
| 1 | Task-origin envelope builder | `tools/mmos_coding_job/envelope.py`; carrier mirror in `tools/mmos_teammate/wake_carrier.py` | `tests/test_mmos_teammate_coding_job.py`: envelope validates against the real contract; carrier command mirror byte-identical to `admission_command_id`; the carrier's door request carries the command only (never the envelope) |
| 2 | `paperclip_task` return transport | `control_plane/paperclip_result_delivery.py` (child: deepseek-v4.1-flash) | `tests/test_paperclip_result_delivery.py`: delivered receipt shape; exactly-once on retry; typed refusal codes; non-loopback base refused; unknown kind refused by the registry (existing law) |
| 3 | One admission call through the door | `tools/mmos_coding_job/door.py` + carrier client | `tests/test_mmos_coding_job_door.py`: ADMIT / REPLAY / digest-conflict / WAIT / unfrozen-command refusal round-trip on the scratch Executive (ingress-tests' `_admission_material` shape); live in the journey |
| 4 | Task-side reader of job state | door `GET /paperclip/coding-job/<command>` + journey output | journey prints task id, job id, attempt id, launch count, result location; the Paperclip module tab itself is L10 scope (see below) |
| 5 | Durable-state continuity, task ids | journey `--scenario crash` | fresh process recovers the SAME attempt through `reconcile_restart`, census shows exactly ONE native launch, receipt lands on the task |
| 6 | Blocker surfacing | carrier WAIT path + door blocker surfacer | journey `--scenario wait` and `--scenario undeliverable`: blocker comment visible on the task with reason and age |
| 7 | Scratch/dev boundary | door + transport config law | unit tests refuse a non-dev Paperclip base; the door binds its sockets under the scratch root only; no TCP listener exists (peer-uid socket only); journey never dials 3100/3780/3773/3774 (asserted in code paths) |
| 8 | L1B3-5 supervisor adopt | `control_plane/executive_runtime.py` (`adopt_attempt`), `control_plane/executive_supervisor.py` (`reconcile_restart`) (child: kimi-k3.1-pro) | `tests/test_executive_supervisor_provider_reattach.py`: the crash window recovers under a new fence with a persisted receipt, no second Job, old refusals unchanged; live in journey `--scenario crash` |

## What needs the principal

1. **The production freeze act.** In dev the door freezes
   `child_request_material` at task intake. In production that is the
   mastermind-coding module / Executive host's act (and the module tab, build
   item 4's UI, is L10). Nothing in this lane installs it.
2. **The transport's production credential.** The dev transport writes through
   the dev instance's local-trusted loopback surface. Production needs an
   instance-scoped Paperclip service credential decided Paperclip-side; the
   transport takes its writer as configuration, so the swap is one config act.
3. **Second-job policy.** One task admits one coding job (`coding-job-1`) per
   frozen digest; a requeue after a lost attempt re-claims the same Job, and a
   genuinely different task needs a new key (`coding-job-2`). Whether the task
   UI offers that key is a product decision for L10.
4. **The engine fix rides this branch.** Item 8 changes `control_plane` on a
   critical surface; the principal reviews it as such (small diff, failing
   test first, one reattach path only).

## Honest deviations / notes

- The frozen envelope's `brief_digest` is fixed at task intake; a task body
  edited afterwards does not reach the job through this path (the frozen
  material is authoritative — same law as the ingress tests).
- The teammate's reply comment is still delivered by the normal carrier path;
  the coding-job comment is additional and carries the job identity.
- The journey's worker prompt is the canary's shape (file + commit + push one
  branch), because that is the exact GitHub-evidence surface the return
  projection reads. Real task briefs reach the worker verbatim in the prompt
  text; the canary-shape file is what it is asked to produce in dev.
- The canary minted its OAuth client against the real T3 server (3773). This
  lane does NOT: the worker OAuth client is minted against the DEV server
  (3800) under V4's boundary, reusing the same pairing helper pointed at the
  dev base URL.
