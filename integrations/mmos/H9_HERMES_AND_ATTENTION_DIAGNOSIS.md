# H9 — Hermes and attention diagnosis, 2026-11-10

Read-only. Paperclip on 127.0.0.1:3100 was GET only with `x-instance-role: local_trusted`;
`~/.hermes` and `~/.paperclip` were read only; nothing was started, stopped or restarted. Evidence:
`~/.mastermind/mmos_evidence/h9-20261110/` with `LEDGER.md`; long random strings are `<redacted>`.

## Q1. Does an existing Hermes agent still work?

**The last successful `hermes_local` run** (observed, `02-runs.txt`, `04-run-logs.txt`):
Secretary, run `cc70684e`, 2026-11-10T01:30:56Z to 01:34:24Z, exit 0, `on_demand`/`manual`, no
issue attached. It produced a correct refusal: the wake body was literally `null`, so it
reported "no task in it" and changed nothing — a healthy run of an empty task, not a
demonstration of work. Engineering `451f3a58` at 00:14:54Z is the same shape; both show the
gateway, the model route and the adapter working end to end.

**Is there a successful Hermes run after 20:32 UTC?** No — and no Hermes run of any kind after
10:30:11Z (observed). The last gateway inbound is 10:24:35Z and the last `response ready` is
10:27:36Z (`05-hermes-gateway.txt`). Nothing asked, so nothing ran: not a failure, silence. The
20:32 and 20:44 cut-overs touched only Assurance and Design Lead, `process` agents that never
used the Hermes gateway.

**The smallest act that would prove a Hermes agent still works** (inferred, from the run
records above): create one issue assigned to **Intelligence**
(`970ec1e3-10e7-47d9-977b-aa3c9a7ac146`). It is safest: status `idle`, zero runs in its whole
history, no assigned issue, and `heartbeat.enabled = false` so no timer can fire a second run.
The body should need no tools, e.g. "Reply with the word ready and stop."

- **Healthy** (observed, Engineering's run): `succeeded`, `exitCode 0`, a log with `[hermes]
  Starting Hermes Agent (model=..., provider=auto ...)`, a reply, `[hermes] Exit code: 0`.
- **Broken** (observed, the 10:27 runs): `exitCode 1` with `No reply: every provider in the
  fallback chain kept failing over` or `Hermes couldn't start the model connection: Gateway ...`.

I did not take that act.

## Q2. Why are Secretary and Meta-CEO in `error`?

**Last three runs each** (observed, `02-runs.txt`):

| Agent | Run | Status | Exit | Error text |
|---|---|---|---|---|
| Secretary | 10:27:33Z | failed | 1 | `Hermes exited with code 1` |
| Secretary | 08:43:48Z | failed | 1 | `Hermes exited with code 1` |
| Secretary | 07:56:13Z | failed | 1 | `Hermes exited with code 1` |
| Meta-CEO | 10:27:47Z | failed | 1 | `Hermes exited with code 1` |
| Meta-CEO | 08:31:15Z | cancelled | — | `Cancelled before issue reassignment` |
| Meta-CEO | 08:27:18Z | failed | 1 | `Hermes exited with code 1` |

**The first failing run** is not the same event for both: Secretary's is 07:00:50Z
(`c9580bfe`), Meta-CEO's 08:14:45Z (`bd82d845`) — both precede the 10:27 pair, different cause.

**The 10:27 pair — the runs that set the current `error` status — share one cause.** Both logs
end with the identical line (observed, `04-run-logs.txt`):

```
⚠️ No reply: every provider in the fallback chain kept failing over, so the turn stopped
instead of retrying forever. Send `continue` or switch provider.
```

The evidence line for the cause (observed, `05-hermes-gateway.txt`, `errors.log` 10:27:08):

```
Error code: 502 - {'error': {'message': 'upstream transport failure; result may be ambiguous',
'type': 'fabric_route_error', 'route': 'glm_chairman_4'}}
```

The capacity-fabric router at 127.0.0.1:8313 returned 502 on route `glm_chairman_4`. The
fallback chain could not cover it: `byteplus-coding` returns 429 `AccountQuotaExceeded`
("weekly usage quota ... will reset at 2026-11-16 00:00:00 +0800") and the `experientiallabs`
pools are "exhausted (every entry in cooldown)", so the turn had nowhere to go.

**It is not the agent's configuration.** Both are `hermes_local`, model `glm-5.3`, `provider:
auto`, identical to the nine idle agents not in error (`01-agents.txt`). **It is not the gateway
being down**: it served a glm-5.3 turn from 10:24:35Z to 10:27:36Z (`05-hermes-gateway.txt`).

**The earlier failures are a different cause** (observed, `04-run-logs.txt`): 07:27 `Gateway
starting: deadline`, 08:25 and 08:43 `Gateway connection failed; no local fallback
(TimeoutError)`, 08:22 and 08:27 `Gateway did not answer session.create`, 08:14 `Gateway
disconnected; turn outcome is unknown` — all around the 07:30:22Z and 11:12Z restarts. So the
10:27 pair is route saturation; 07:27–08:45 is gateway availability. Same symptom, two causes.

**Would a new wake fail the same way?** (inferred) Probably not: the router listens on 8313, the
gateway has run as pid 31513 since 13:26:58Z, and a glm-5.3 turn completed at 10:27:35Z. But the
fallback chain stays degraded until 2026-11-16, so a repeat 502 would again have no net.

**Smallest fix and who can make it.** Nothing on the agent needs changing; it leaves `error` on
its next successful run, so the smallest fix is one successful wake — the principal's act, the
same as Q1. The deeper fix is the fallback chain: wait for the byteplus weekly quota to reset on
2026-11-16, or add a healthy provider to `fallback_providers` in `~/.hermes/config.yaml`. That
file is the Chairman's; a gateway restart is his to order and is not needed for the agent to
recover.

**Two-model check.** The observation that would prove me wrong is a glm-5.3 turn that succeeded
inside the failure window. It exists (`08-q2-falsifier.txt`): at 10:27:08 the same 502 hit a
Mastermind CEO turn, the retry at 10:27:17 succeeded, and the turn completed at 10:27:35 —
between Secretary's start (10:27:33) and its failure (10:29:50). The route was intermittent, not
dead, so the claim is "transient route saturation plus an exhausted fallback chain", not "the
route is broken".

## Q3. The attention items

The list holds **8** items, not 6 (observed, `03-attention.txt`): the six the brief counted plus
two `issue_thread_interaction` rows.

| # | Kind | Points at | Raised | Asking for | Clearing action | Verdict |
|---|---|---|---|---|---|---|
| 0 | `issue_thread_interaction` | MAS-7 confirmation | 20:48:56Z | Accept or decline Design Lead's completion | `POST /api/issues/7897297c.../interactions/06eb554d.../resolve` or the Confirm button | **The program's — must stay** |
| 1 | `agent_error_alert` | Meta-CEO | 00:14:14Z, activity 10:30:11Z | Inspect or dismiss the agent error | one successful run, or Dismiss | **Caused by Q2** |
| 2 | `agent_error_alert` | Secretary | 00:14:16Z, activity 10:29:51Z | Inspect or dismiss the agent error | one successful run, or Dismiss | **Caused by Q2** |
| 3 | `blocker_attention` | MAS-4 | 07:33:26Z, activity 10:28:13Z | Teamlink acceptance is blocked on runtime identity isolation | Unblock/Reassign/Nudge; needs PR #2403 and #2419 resolved | **Real, needs a decision — the integration owner, then the Chairman** |
| 4 | `blocker_attention` | MAS-4 (again) | 07:33:26Z, activity 08:31:52Z | Same issue, second dedup key `blocked-owner:...` | clears when MAS-4 leaves `blocked` | **Stale duplicate of #3** |
| 5 | `blocker_attention` | MAS-1 | 2026-11-08T08:02:23Z | Onboarding is blocked on a dead owner | Reassign to a live agent, or close | **Stale — the assignee is `terminated`** |
| 6 | `recovery_action` | MAS-1 stranded issue | 2026-11-08T08:04:20Z | Board operator must retry, reassign or resolve | Resolve/Reassign/Cancel | **Stale — same root as #5** |
| 7 | `issue_thread_interaction` | MAS-1 questions | 2026-11-08T08:02:23Z | "What would you like to do?" from the first-task skill | Respond, or cancel with #5 | **Stale — asked by a terminated agent** |

MAS-1's assignee `cbf16e10-5848-4b3e-877a-bf9110785864` is a *different* agent also named
Meta-CEO, status `terminated`, `lifecycleHolds: ["manual"]` (observed, `07-agent-cbf.txt`), which
is why items 5, 6 and 7 cannot clear themselves.

## Q4. What else would look broken to someone opening the app today

- **MAS-2 is `in_progress` with no run since 03:13:11Z** (observed, `06-issues.txt`): its last run was cancelled by a board operator and nothing followed — about 18 hours.
- **Product fails on a skill collision** (observed, `02-runs.txt`): three runs at 01:47–01:49 failed because `.../profiles/product/skills/complain` is occupied by another installation.
- **A stale `~/.hermes/.hermes-update-in-progress.lock` from 05:37** is still present; it
  produced the 07:00 run's `an update is still running` error (observed).
- **The gateway restarted four times today** — 03:18, 07:30, 11:12 and 13:26 UTC (observed,
  `gateway-exit-diag.log`). Each restart is a window in which a wake fails with "Gateway
  starting: deadline" or "did not answer session.create", as the 07:27–08:45 runs did.
- **Seven agents have never run at all** — Reliability, Marketing, Delivery, Chief of Staff,
  Mastermind CEO, Autonomy CEO, Intelligence (observed, `02-runs.txt`). Idle, not broken. No live
  runs at the time of reading (`live-runs.json` is `[]`), so nothing is stuck.

## Acts for the principal

Safest first. None of these were taken by this lane.

1. **Prove Hermes still works.** Create one issue assigned to Intelligence
   (`970ec1e3-10e7-47d9-977b-aa3c9a7ac146`) with the body "Reply with the word ready and stop.",
   then read `GET .../heartbeat-runs?agentId=970ec1e3-...&limit=5` for `succeeded` / exit 0.
2. **Clear the two error alerts** by waking Secretary and Meta-CEO once each, the same way. A
   success clears the alert; the same 502 means the fallback chain, not the agent.
3. **Dismiss the stale MAS-1 rows** (items 5, 6, 7) after reassigning MAS-1 to a live agent, or
   close MAS-1 as abandoned. The owner is terminated and cannot act.
4. **Leave MAS-7's confirmation open.** It is the program's own item and the Chairman's to
   accept or decline.
5. **Decide MAS-4** (items 3 and 4). It is blocked on PR #2403 and #2419, a real engineering
   dependency, not a stale row.
6. **Remove the stale update lock** `~/.hermes/.hermes-update-in-progress.lock` (from 05:37) —
   the Chairman's file, and a gateway restart is his to order. The duplicate-key warning is from
   2026-11-09 and the file now reads `backends:` at line 305, so it is fixed.
