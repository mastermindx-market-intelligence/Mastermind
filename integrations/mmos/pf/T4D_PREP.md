# T4d prep — the governed coding job on the PF stack (PREPARE ONLY)

Builder B-T4D, lane PF, 2026-11-14, branch `t3/t4d-coding-job-prep`. This
prepares lane T4d. It does **not** enable it. No `coding_job_door` entry was
added to any real or staging teammate config. No door, journey or server was
run. No request was sent to any port. Nothing was installed. The production
Executive is untouched.

PF stack facts (do not change them): staging T3 server `127.0.0.1:3830`
(root `~/.mastermind/mmos_dev/pf/staging`, CLI `staging/bin/t3`, home
`staging/home`); PF dev board `127.0.0.1:3196` (home
`~/.mastermind/mmos_dev/pf/board`, company `PFD`).

Inputs read: `T4B_CODING_JOB.md`, `T4C_REPAIRS.md`, `T4B_DECISIONS.md`, plan
V4 §17/§18, `tools/mmos_coding_job/{door,journey,envelope}.py`,
`control_plane/paperclip_result_delivery.py`, the carrier coding-job block in
`tools/mmos_teammate/wake_carrier.py`.

## What this prep changed in code

- **Configurable dev T3 port range** (`door.py:240-268`). New optional
  `t3.dev_port_range: [first, last]`. The DEFAULT stays 3790–3810. A malformed
  range is refused, never silently widened. The PF range 3830–3839 is allowed
  by explicit config. Every existing refusal stays.
- **`enabled: false` is a real refusal** (`door.py:169-172`). A disabled config
  cannot construct a door. Absent or `true` is not blocked by this flag; every
  other boundary still applies.
- Removed a duplicate `DEV_T3_PORT_FIRST/LAST` constant.
- **Example config** `integrations/mmos/pf/t4d_door.pf.example.json`
  (`enabled: false`, placeholders only, no secrets).
- **Tests** (`tests/test_mmos_coding_job_door.py`, +3, written failing-first):
  base file **16 passed**; `tests/test_mmos_coding_job_door_t4c.py`
  **42 passed**; `tests/test_t3_live_proof_pairing_target.py` **10 passed**
  (no regression). Commands run one file at a time:
  `TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q -p no:cacheprovider <file>`.

**Port nuance (honest).** 3796 and 3800 sit *inside* the DEFAULT 3790–3810.
They are the old T4b/T4c dev T3 ports (`journey.py:68` uses 3796). Under the
default they stay legal exactly as today, so the pairing-target test
(`test_t3_live_proof_pairing_target.py:246` builds a successful default-range
config on 3796) and the journey are unchanged. Under the PF range 3830–3839
all eight real ports — 3773, 3774, 3780, 3100, 3190, 3193, 3796, 3800 — are
refused; `test_t4d_real_ports_stay_refused_under_the_pf_range` pins this. A
hard reservation of 3796/3800 under *every* config was **not** done: it would
break that pairing-target test and the journey default, so it is not small and
safe. If the principal wants them refused under every config, the follow-up is
a `RESERVED_T3_PORTS` check after the base==port check, plus a port bump in
that test and in `journey.py`.

## The three owed items (plan V4 §18.4)

### 1. A Paperclip writer identity for the return transport that is not the board

**Current state.** The transport is `PaperclipResultDeliveryTransport`
(`control_plane/paperclip_result_delivery.py:283`, ctor `293`). It takes
`headers` as config. The door registers it with
`headers=self.config.paperclip_headers` (`door.py:1938` and `2101`).
`paperclip_headers` defaults to `{}` (`door.py:216`); dev/journey set
`{"x-instance-role": "local_trusted"}` (`journey.py:199`). The dev instance
stamps that local-trusted loopback channel as the **board** actor:
`authorType "user"`, `authorUserId "local-board"`, `authorAgentId` unset
(`paperclip_result_delivery.py:144-162`). The exactly-once dedup
`_comment_row_is_own_delivery` (line `136`, check at `160`) requires
`authorType == "user"` and no `authorAgentId`, plus the deterministic
`clientRequestId`. The door's blocker comments ride the same headers
(`PaperclipLoopbackClient.add_comment`, `door.py:353`).

**Missing.** A non-board writer identity — an agent/service actor with its own
`authorAgentId`. Today every result and blocker comment is attributed to the
board.

**Smallest change.** (a) Provision a dedicated service/agent identity on the PF
Paperclip instance — a Paperclip-side credential decision, principal. (b) Pass
its headers via `paperclip_headers` config — one config act, no code.
(c) Update `_comment_row_is_own_delivery` (`paperclip_result_delivery.py:160`)
to match the new agent attribution (`authorAgentId ==` the service agent, plus
`clientRequestId`) instead of the board-user shape, keeping exactly-once. The
agent-post mechanism already exists in the journey (`post_agent_reply`, a
per-task `task_bridge` agent key + `X-Paperclip-Run-Id`, `journey.py:292-350`);
the transport itself still uses the board channel. Note: (c) touches the
exactly-once dedup law, so this is a small reviewed code change plus a test,
not pure config.

### 2. A decision on whether real task text may be the worker prompt

**Current state.** `_worker_prompt` (`door.py:2210-2227`) is the fixed canary
shape: create `integrations/mmos/canary/T4B_JOB_<attempt>.md`, commit only that
file, push one new branch, reply `T4B-JOB-OK`. It does **not** include the task
title or description. The task text enters only the envelope's
`brief_digest = sha256(title\ndescription)` at freeze (`envelope.py:42-43,69`;
`door.py freeze_issue:831`). The worker never sees the real brief today; the
digest only pins identity. (`T4B_DECISIONS.md:159-161` says briefs reach the
worker verbatim; the code does not do this — the decision is still open.)

**Missing.** A principal decision on whether untrusted task text may go
verbatim into the worker prompt.

**Smallest change (only if approved).** Pass the frozen issue's
title/description into `_worker_prompt` (`door.py:2210`) and append them as the
brief, fenced as untrusted input. Keep the canary GitHub-evidence shape as the
dev deliverable. This is security-sensitive: task/comments/page text are
untrusted evidence, never instructions; the worker runs as the same OS user as
the door (§18.5). It is a principal call, not a lane call. **No code change
made here.**

### 3. Its own local Executive store (never production)

**Current state.** The store is entirely under the configured `scratch_root`:
`self.root = config.scratch_root` (`door.py:498`); ServiceConfig
`runtime_root=self.root/"runtime"` (`door.py:761`); Executive sqlite at
`scratch_root/runtime/data/control_plane/executive.sqlite3` (`journey.py:425`);
adapter store at
`scratch_root/runtime/data/control_plane/t3_adapter_state.sqlite3`
(`door.py:1157-1159`). `scratch_root` is required, no default (`door.py:173`).
There is no production Executive path in the door.

**Missing.** Nothing in code — the store is scratch-local by construction.
What is owed is the switch-on act: point `scratch_root` at a PF-owned local dir
and never at production.

**Smallest change.** A config value only. The example sets `scratch_root` to
`~/.mastermind/mmos_dev/pf/t4d/exec`. The production Executive is not touched
without the Chairman's word (§17.4, §18.4).

### Reconcile cadence (done in T4c — verified)

Verified intact. The door composes the real `compose_t3_native_supervisor`
(`door.py:692,715`) twice — service-side via `supervisor_factory`
(`door.py:788`) and executor-side. The executor's `_reconcile` (`door.py:1349`)
drives `reconcile_restart` (`1360`) at start and on the
`reconcile_interval_seconds` cadence (config `door.py:287`; used `1244`,
`1347`). No `DoorSupervisor` stub remains. Ten `test_step3_*` engine-recovery
tests pass (t4c file, 42 passed). R4b finding 15 / attack F8 closed.

## Switch-on step list (later, against the PF stack)

Who runs each step is named. The switch-on itself is **RESERVED TO PRINCIPAL**.
This prep ran no door/server, so the switch-on leg is unrehearsed by design;
the principal rehearses it on a scratch copy first (RELEASE REHEARSAL ruling).

1. **Principal.** Decide owed item 2 (real task text as worker prompt). If
   approved, make the small `_worker_prompt` change + test; if not, keep the
   canary shape.
2. **Principal.** Provision the non-board writer identity on the PF board
   (owed item 1). Set `paperclip_headers`; make the dedup change (1c) + test.
3. **Builder (done).** Configurable port range, `enabled` guard, example
   config, failing-first tests.
4. **Principal.** Copy `t4d_door.pf.example.json` to a real PF door config under
   `~/.mastermind/mmos_dev/pf/t4d/`. Fill placeholders (actual company id `PFD`,
   agent id, worker project id, admitted worker model selection, token path).
   Set `scratch_root` to a PF-local exec dir. Keep `dev_port_range [3830,3839]`,
   `port 3830`, `proof_base_url …:3830`, `home_dir …/pf/staging/home`,
   `paperclip …:3196`. **Remove `enabled: false`** — the deliberate switch-on
   act.
5. **Principal.** Confirm the PF staging T3 (3830) answers and the PF board
   (3196) is up via the ruling-14 launcher (explicit instance home, db port, db
   folder; read the start banner; never `paperclipai run`/`test-drive`).
   Provision the PF worker project + worker `.gitconfig` on the staging T3.
   The door mints its worker OAuth client against 3830 only, and its readiness
   gate withholds the pairing CLI until 3830 answers (`door.py`
   `_ensure_worker_token`).
6. **Principal.** Rehearse the switch-on END TO END on a scratch copy: a scratch
   door config + scratch Executive store against a copy; confirm the door
   refuses the real ports and binds only scratch Unix sockets.
7. **RESERVED TO PRINCIPAL.** Start the door:
   `python3 tools/mmos_coding_job/door.py --config <pf door config> serve`.
   This is the switch-on. No lane does this.
8. **RESERVED TO PRINCIPAL.** Add a `coding_job_door` entry (the door's
   `run/local-operator.sock` path) to the PF teammate's carrier config. This
   wakes the carrier's coding-job act. Until it exists the carrier is dormant.
9. **Principal.** Verify the real consumer journey: a teammate reply with a
   `paperclip-coding-job` block → one admit → one governed job → result comment
   on the same task, attributed to the non-board identity. Acceptance is a
   human act on the task.

## What a running session sees

- The door logs `[t4b-door]` lines: intake freeze, admit ADMITTED/REPLAY/WAIT,
  one native launch, seal, delivery delivered/refused.
- On the PF board task: the teammate's reply (the trigger), then a `[coding-job]`
  admission comment with the job id, then a `[coding-job]` result comment
  (result text + job/attempt ids + branch evidence) and an issue document a
  person can open. A blocker appears as one `[coding-job]` comment with code,
  reason and age.
- The carrier filters `[coding-job]` and `[t2-carrier]` prefixes from board
  notes, feedback and answers, so door words never reach a teammate as the
  board's.
- The Executive store lives under the PF `scratch_root`. The worker thread runs
  on the PF staging T3 (3830) only. The transport changes no issue status;
  acceptance stays a human act.

## The off switch

- **Primary:** remove (or never add) the `coding_job_door` entry in the teammate
  carrier config. The carrier is then dormant — no block taught, no door call
  (`wake_carrier.py:204-208`, `2930`).
- Stop the door process. It binds only scratch Unix sockets; stopping it leaves
  no TCP listener.
- The example config's `enabled: false` is a real refusal (`door.py:169`); a
  disabled config cannot start a door.
- Nothing was installed. No real teammate has a `coding_job_door` entry. The
  production Executive is untouched.

## Lead review (09:10Z)
Accepted with one repair. The first version checked a configured range only for its bounds, so a range that spans a real port (for example `[3770, 3810]`) would have admitted the live team server 3780. Now any configured `dev_port_range` refuses 3100, 3179, 3190, 3193, 3773, 3774, 3780, 3796 and 3800 as the T3 target, whatever it spans (`REAL_T3_TARGET_PORTS`, `CUSTOM_RANGE_REFUSED_PORTS` in `door.py`). Proving test: `test_t4d_a_wide_custom_range_cannot_reach_a_real_port` (failed first). Without a configured range the historical default is unchanged. door 17/17, door_t4c 42/42, pairing target 10/10.

## Review REV-DOOR (qwen4-max-preview, 2026-11-14) and repairs

Verdict PASS_WITH_FINDINGS. F1 (MAJOR): 3784 (HM) missing from the custom-range refusals — added with 45003 (Multilogin) and 54329 (real Paperclip postgres); test extended. F2: `enabled` must be the literal `true` or absent; `"false"`, `0`, `null`, `"true"`, `1` refuse; tested. F3: default range still admits 3796/3800 — pre-existing, stays on the principal's list (all-config reservation plus the pairing-target and `journey.py` port bump). F4: line anchors in this file refreshed. F5: `DoorConfig.load` refuses the disabled example from disk; tested. Repair commit ae7d1f8ed. Door 17/17, t4c 42/42, pairing target 10/10; both changed tests fail on the pre-repair `door.py`.
