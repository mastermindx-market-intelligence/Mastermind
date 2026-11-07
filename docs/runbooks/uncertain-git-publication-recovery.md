# Recovering interrupted Git branch publication without freezing delivery

**Status: proposed source procedure until protected acceptance and supported installed
publisher recovery.** This document authorizes no action on an existing uncertain
operation by itself. The governing owner is `docs/sol_skills/RECONCILE_STATE.md`
Step 4C; the existing managed publisher remains the sole publication carrier.

## Why this is narrower than blind retry but broader than historical replay holds

A missing callback from a Git push does not reveal whether the remote update
happened. The current remote ref *is* a useful state observation. We do not need to
reconstruct an old, never-logged syscall forever before making a genuinely new,
forward-only Git transition, **provided the original process cannot later write,
custody is established, and the installed publisher actually supports the contract**.
The old operation remains `EFFECT_UNKNOWN` for its historical result.

This exception does not cover trades, payments, releases, merges, deployments,
external messages, service restarts or destructive writes. An explicit permission
or safety refusal is never a technical retry hint. No rehoming, alternate account,
force push, source-lease theft or claim of CI/production acceptance is allowed.

## Decision procedure

1. **Identity** — Record original `operation_id`, `action_ref`, repository,
   branch, canonical origin, remote ref, intended commit, original error,
   remote old SHA and the installed publisher generation. Keep the original
   uncertainty unchanged. No new workspace or replacement branch.
2. **Liveness and custody** — Use installed operation/workspace status and
   existing effect/process evidence. Require the old push process to be
   definitively finished or fenced from another write. Verify no current
   competing writer/lease, controller, or pending source mutation. If evidence
   is unavailable, hold this affected source operation, not disjoint work.
3. **Present-state readback** — Read the exact remote ref and PR tip through the
   original authorized route, then the local commit graph and source/index.
   No negative activity-list inference. Already-contained intended commit
   means current-state adoption without a new publication or retroactive
   `APPLIED` historical receipt.
4. **Immutable candidate** — If remote has not advanced to the intended
   commit, create/qualify a new immutable head on the *same original managed
   workspace and branch*, preserving both the newest remote state and the
   historical intended source if still applicable. Check `merge-base
   --is-ancestor <fresh-remote-head> <candidate-head>` and inspect any
   semantic overlaps. Divergence means repair and retest before publication.
5. **New action** — Once the specific installed publisher supports the
   guarded-recovery schema, submit one *distinct* stable action referencing
   the old action. The new action carries exact expected remote SHA and
   candidate SHA, is restricted to the same origin/ref, and refuses protected
   targets. It re-reads remote before dispatch; Git's normal **non-forced**
   fast-forward push uses the remote-old object ID in the server's atomic
   ref transaction. If a third party changed the ref, the server refuses.
   Never use `--force`, `--force-with-lease`, `+<refspec>`, or a
   direct GitHub ref rewrite.
6. **Durable result** — Before dispatch, persist the new intent in the
   existing publisher's gitdir receipt storage. Record DISPATCHING and a
   terminal result when available. On lost response, reconcile by the exact
   new action ID and remote state; *do not* start a second recovery push.
7. **Release** — Verify source head and PR. Then use ordinary source review,
   current-head required CI, explicit hold disposition, protected merge,
   production deployment and authenticated real-path acceptance as separately
   gated operations. None is implied by successful publication.

## Engineering interface to add to the existing publisher

Extend PR #2070's incumbent publisher, not a parallel publisher:

- `studio_git_publish_status` continues as the read-only operation/head
  view, optionally returning its durable action receipt when installed.
- Add an **explicit guarded recovery request shape** on the same typed
  publisher; for example a `recovery` object containing
  `prior_action_ref`, `new_action_ref`, `expected_remote_head_sha`,
  and `expected_head_sha`. Exact final schema belongs to the existing
  owner and must appear in the installed advertised catalog before use.
- Validate that `prior_action_ref` is a known retained unknown or
  an explicitly qualified pre-journal legacy operation, with old active
  process ended/fenced, and that `new_action_ref` is fresh in the same
  operation's private durable receipt store. Duplicate new IDs reconcile,
  never repeat effects. Require an active authorized source writer.
- Read remote *fresh* with the existing origin, validate candidate ancestry
  and expected SHA, preserve relevant original commits, and perform only a
  non-forced fast-forward update. No additional remote selection, mutable
  policy override, git credentials, process launcher or bypass path.
- Persist original and new receipts independently; annotate historical
  state `UNKNOWN` even after the new publication is `APPLIED`.
  A terminal record with lost callback is not a retry invitation.
- Installer's sealed module/pin and original versioned upgrade transaction
  must be qualified; there is no out-of-band package replacement.

## Macro International #9596

At the last verified read, the original managed operation is
`intl-country-cockpit-20261018` on
`sol/web-intl-country-cockpit-20261018`. The old action is
`9533be2476ba264880c1aa067eb3af32f3d0703a794679a7818b9677f1838d15`;
local source `2dfae93b36fd2a8aad07be7f1ae996f21051e9ba` differs from
remote PR head `621bd44dfac13ea18671fe64c773aa8675928dd6`.
These are **historical observations**, not a current authorization to push.
The prepared Paper candidate and its test proof remain preserved in the
original PR #9596. Qualify current source, process/write custody,
latest-main integration and the published publisher version before recovery.
Even if publication succeeds, #9596 remains Draft/HOLD until its actual CI,
formal review/hold and protected release conditions are met.

## Negative/positive acceptance matrix

| Case | Required observation |
|---|---|
| Old push already applied, response lost | Remote contains commit; no new push; historical result stays truthful |
| Pre-dispatch technical failure verified | Original no-effect outcome; resume within ordinary permissions |
| Original action unknown, old process fenced, new forward head eligible | New explicit same-carrier guarded publish can succeed once |
| Remote changed after preflight | Atomic push rejects; no history overwrite |
| Original process might still write | Block dependent publication |
| Local head diverges from remote | Block until coherent tested descendant exists |
| Old committed content is omitted from new candidate | Block or explicitly reconcile material supersession |
| Wrong repository, branch, origin or expected SHA | Block without dispatch |
| Explicit safety/permission refusal | Hold refused effect; no new action under this exception |
| New recovery response lost after remote update | Exact action reconcile; no third push |
| Conflicting active writer or held protected release | No source/merge/release bypass |
| Current Studio schema lacks recovery inputs | No recovery mutation through legacy tool |

**Evidence ruler:** unit tests plus disposable Git-repository race fixtures, source
hashes and readback, actual hosted CI, accepted source, installer canary on the
intended profile and later real #9596 consumer proof. Fixtures are not installation.
