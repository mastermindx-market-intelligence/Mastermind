# Hermes gateway external drain — lifecycle discipline for native enrollment

Read this before holding a Hermes gateway external drain during a native-worker enrollment,
scoped activation, config swap or restart-gated maintenance step. It exists because of the
2026-11-09 M2 incident (`h4-native-worker-enrollment-20261109`, #983): an enrollment
controller engaged the drain, then ran a >1h qualification/diagnostic phase without
keep-alive or release. The gateway's 3600-second marker-expiry safeguard restored admission
exactly as designed, and the owner released the marker one minute later — but for that whole
hour every new turn on the shared multiplexer was refused while no gated mutation was
actually in progress. The safeguard is a backstop, not the plan.

## What the drain is (existing contract, do not rebuild it)

- The begin/cancel control path writes/removes `~/.hermes/.drain_request.json`
  (`gateway/drain_control.py`; dashboard route `POST /api/gateway/drain` with
  `{"action":"drain"|"cancel"}`). The gateway's own watcher polls the marker at 1s and
  flips admission; in-flight turns always finish. Never delete or edit the marker file
  manually — use the control path so identity and logging stay coherent.
- A marker older than `DRAIN_REQUEST_MAX_AGE_SECONDS` (3600s) is ignored as stale and the
  gateway re-accepts turns **mid-maintenance**. Long holds stay legitimate only by
  re-writing the marker (keep-alive bumps `requested_at`).
- `/api/status` exposes a `gateway_drain` advisory (`marker_present`, `active`, `stale`,
  `stale_reason`, `age_s`; `principal`/`requested_at` on loopback). Poll it while you hold
  a drain, and check it before assuming a "draining" gateway is yours to keep.

## Engage — last, not first

1. Finish planning, custody attribution and MCP/diagnostics FIRST. A drain held across a
   long diagnostic phase is the incident: the marker ages toward expiry while nothing is
   being mutated and every other profile's new turns are refused.
2. Engage only immediately before the actual gated mutation (scoped activation, shared
   config swap, or restart). Snapshot a drain intent recording the principal, target
   gateway identity (pid/start_time/served profiles) and the exact pending mutation — the
   H4 `drain-intent.json` shape is the precedent to keep.
3. Record whether the gated action ends in a gateway restart. The marker carries an
   instantiation epoch so one that survives a restart reads stale; still release explicitly
   on your side.

## Hold — keep it alive or shorten it

- If the gated phase can exceed ~30 minutes, re-write the marker on a cadence well under
  the 3600s max age, or split the maintenance so each drain covers only the minutes it
  needs.
- Never leave a drain engaged while you re-plan. If qualification changes the approach
  (for example: shared-host restart becomes profile-scoped activation that preserves other
  writers), release the drain at that decision, then re-acquire only if a later step still
  needs one.

## Release — always, immediately, through the control path

- Release on completion, on failure, and on plan change that removes the gated mutation.
  Verify `marker_present_after: false` and gateway state back to running (the H4
  `scoped-activation-drain-release.json` shape: owner result, marker check, status echo).
- Do not rely on the expiry safeguard to end your drain. Expiry re-opens admission while
  your maintenance may still be mid-flight; that races your own gated mutation with new
  turns — the reverse failure of the one this discipline prevents.

## Observe — make leaks visible early

- While holding: poll `/api/status` `gateway_drain` (`age_s` climbing toward `max_age_s`
  means keep-alive is missing). A `stale: true` with `stale_reason: "expired"` means the
  gateway already ignored your marker — reconcile immediately: either the maintenance is
  done (release) or still needed (re-engage and continue).
- Attribution: the advisory's `principal` (loopback) and the gateway log breadcrumb
  `drain-control: ignoring expired drain marker (… principal=…)` name the owning operation
  so a later responder chases the real owner instead of restarting the gateway.
