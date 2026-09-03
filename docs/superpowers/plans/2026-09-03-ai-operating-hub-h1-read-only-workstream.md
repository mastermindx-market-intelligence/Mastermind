---
schema: mastermind.ai_operating_hub_h1_handoff.v1
operation_key: mastermind-ai-operating-hub-h0-current-estate-freeze-20260903-sol-001
h0_source: research/MASTERMIND_AI_OPERATING_HUB_H0_CURRENT_ESTATE_2026-09-03.md
h0_evidence: research/evidence/ai_operating_hub_h0_archaeology_2026-09-03.json
protected_master_at_freeze: 771a95586c7a31933ee612eafaa4d1471f57527b
workstream: WS:CHAIRMAN-CONTROL-ROOM
authorization_state: HELD
production_effect: NONE
---

# AI Operating Hub — H1 bounded read-only Workstream Workroom handoff

> **This document is a handoff specification, not authorization.** H1 is `HELD`. It receives
> implementation authority only after **both** the H0 record above **and** PR #326 are
> independently reviewed and merged into protected `master`. A worker that cannot verify both
> predecessors must return `BLOCKED SOURCE_PREDECESSOR_UNPROTECTED effect=NONE` and preserve its
> exact carrier. Starting any of the nine paths below — even the four that do not touch PR #326's
> files — before both predecessors protect would create a dark foundation PR rather than one
> independently useful user capability, and is not authorized.

## Observable mission

A real authorized user opens the local P0A Chairman Control Room and, for the reference workstream
`WS:CHAIRMAN-CONTROL-ROOM`, correctly answers — from one screen, with every answer auditable to its
canonical owner:

1. What is the outcome / user job?
2. What is the current capability state?
3. Who or what is currently bound to act?
4. What is the latest accepted proof?
5. What is the present blocker or decision?
6. How fresh is each source, and do any sources disagree?
7. What is the exact next owner and action?

**Read-only.** No action submission, no attention ranking, no new store, no second auth layer,
no LLM-authored status.

## Selected consumer

Local **P0A Chairman Control Room** (`scripts/chairman_control_room.py`, loopback `127.0.0.1:8787`).
Remote **X1 is out of scope for H1** and must not be modified. Its contract, redaction law, and
release attestation closure stay exactly as they are.

## Exact path ceiling — nine paths, dual-protection gate

Frozen by H0 §8. This is the complete set of paths H1 may touch — a **preferred shape**, subject to
a fresh collision census immediately before H1 START, since it is frozen in advance of PR #326
protecting.

**May create:**

| # | Path | Purpose |
|---|---|---|
| 1 | `control_plane/ai_operating_hub_workroom.py` | one typed, **pure** derived read-only contract |
| 2 | `app/static/chairman_control/hub_workroom.js` | one additive presentation module |
| 3 | `app/static/chairman_control/hub_workroom.css` | one additive stylesheet |
| 4 | `tests/test_ai_operating_hub_workroom.py` | deterministic contract tests |
| 5 | `tests/test_chairman_control_room_ai_hub.py` | Hub-specific Control Room integration tests |
| 6 | `tests/test_chairman_control_room_ui_ai_hub.py` | Hub-specific UI/browser-proof tests |
| 7 | `docs/superpowers/plans/2026-09-03-ai-operating-hub-h1-implementation-receipt.md` | H1 receipt |

**May modify — only once both H0 and PR #326 are protected:**

| # | Path | Permitted change |
|---|---|---|
| 8 | `scripts/chairman_control_room.py` | exactly one additive read-only route |
| 9 | `app/static/chairman_control/index.html` | exactly one additive mount point |

**Must not touch, unconditionally:** `control_plane/chairman_control_room.py`,
`control_plane/chairman_control_room_remote.py`, `scripts/chairman_control_room_remote.py`,
`app/static/chairman_control/remote.html`, `app/static/chairman_control/control_room.js`,
`app/static/chairman_control/control_room.css`,
`control_plane/autonomy_control_room_projection.py` and its dialogue/dispatch/watcher/evidence
classifiers, the protected Agent Dialogue Wake runtime — `integrations/slack_agent_dialogue/engine_v2.py`,
`integrations/slack_agent_dialogue/runtime.py`, `integrations/slack_agent_dialogue/turn_routing_facts.py`,
`integrations/slack_agent_dialogue/turn_runtime_primitives.py`,
`integrations/slack_agent_dialogue/wake_projection.py` (read-only consumption via an accepting
owner only — never reimplemented), `ops/control_room_remote/install.sh`,
`ops/control_room_remote/mastermind-control-room-remote.service`, and anything owned by PR #350.

A tenth path requires `DECISION_REQUEST / PATH_BOUNDARY_REQUIRED effect=NONE` before edit.

## Blocking precondition — dual protection, not a UI-only gate

PR #326 is `OPEN / DRAFT` at head `b59753a4deab4b7748b2896a518d9532762d8a74`, with **two unresolved
`CHANGES_REQUESTED` reviews** (latest: `5103135217`, 2026-09-03T14:24:15Z). Its five open blockers:
a dark/disconnected dispatch producer, unvalidated caller-controlled mapping input, terminal-Attempt
misclassified as a return, forgeable/non-causal watcher and decision proof, and unknown evidence
rendered as if it were current. Until independently re-reviewed and merged, its dispatch/status
output is an **unaccepted candidate**, not protected or live capability.

Consequences for H1, all mandatory:

1. **H1 START itself — not merely paths 8–9 — is held until both this H0 record and PR #326 are
   protected.** Building paths 1–7 early, while the real consumer paths that make the capability
   useful remain blocked, would be a dark foundation PR. That is not authorized.
2. **Do not re-derive card status, dispatch, dialogue, or watcher logic.** Once #326 merges, H1
   consumes its `query_status` / `is_actionable` vocabulary. Inventing a second derived-status,
   dispatch, or watcher authority is `REJECTED_BY_DESIGN`.
3. **Terminal Attempt state alone is never a worker return; nonblank watcher strings alone never
   prove a watcher; a decision edge must be causally after the return it claims to close.** These
   are the exact misclassifications PR #326's own review caught — H1 must not reintroduce them.
4. **Agent Dialogue evidence (PR #357, protected) is read-only via an accepting owner.** H1 never
   becomes a second dialogue/dispatch classifier over `integrations/slack_agent_dialogue/*`.

## Exact local route, security, cache, and threat boundary

H1 may expose **exactly one** fixed read route:

- **Route:** `GET /api/hub/workstream/chairman-control-room`, resolving server-side to the literal
  workstream `WS:CHAIRMAN-CONTROL-ROOM` — no arbitrary workstream parameter, no fuzzy match.
- **Data source:** the existing process-memory cached `mastermind.chairman_control_room.v1`
  composed document only. No request-time re-gather, network call, subprocess, file discovery, or
  second compositor.
- **Preserved exactly as on `/api/state`:** loopback-only binding, `Host`/`Origin` header checks,
  CSP, request/response body bounds, and the same `X-CCR-Token` gate.
- **Token honesty law.** `X-CCR-Token` is a per-process browser-origin/CSRF capability nonce,
  not authentication against another same-user local process; `GET /` intentionally bootstraps
  that nonce. H1 must state this honestly and must not claim a verified user identity or
  public/remote authorization from this token.

## Sequence

1. Fresh-read protected `master`; confirm **both** the H0 record and PR #326 are merged. If either
   is missing, return `BLOCKED SOURCE_PREDECESSOR_UNPROTECTED effect=NONE`.
2. Load the Skillpack at that same SHA; verify `schema` / `skillpack_version` /
   `minimum_bootstrap_major` compatibility.
3. Re-run the duplicate/collision census over all nine ceiling paths and the H1 branch name.
4. Confirm PR #326's merged status and read its accepted dispatch/status vocabulary; do not assume
   the shape frozen in this document without re-reading the merged source.
5. Write path 1 as a **pure** function over an already-composed
   `mastermind.chairman_control_room.v1` document, plus the accepted PR #326 projection once
   merged. No file I/O, no subprocess, no clock read, no environment read. `generated_at` is
   injected by the caller, never sampled inside.
6. Write paths 4–6 red-first against fixtures, including every failure state below.
7. Write paths 2–3 as additive modules. They render only fields the contract emits; they must not
   compute status, rank items, or fetch from any source the contract did not already carry.
8. Add the one read-only route (path 8) and the one mount point (path 9).
9. Run the repository test battery. Capture browser proof at the real loopback path at desktop and
   mobile breakpoints, covering every failure state.
10. Write path 7 as the receipt. Publish one Draft/HOLD PR. Return on the H1 carrier.

## Contract requirements for path 1

The derived contract must:

- consume an already-composed `mastermind.chairman_control_room.v1` document and, once merged, the
  accepted PR #326 projection; never re-open or re-join canonical sources itself;
- preserve the compositor's four design laws unchanged — no synthetic overall status, bindings
  never create canonical facts, exact joins only, upstream key names never renamed;
- carry a closed `OUTPUT_KEYS` set asserted by test, as both the compositor and the remote
  projection already do;
- keep `observed_at` and `source_time` separate, and never conflate them;
- keep `degraded` a first-class output; an empty list means "no detected failure", never "healthy";
- preserve disagreements as disagreements — never average, vote, or pick a winner;
- emit `null` rather than a fabricated default for any absent identity;
- attach every rendered claim to its canonical owner and a deep link, or, where no lawful deep link
  exists, emit `NOT_AVAILABLE` / `NOT_APPLICABLE` with the owner/source identity — never a
  fabricated URL.

## Required failure states — all must be designed, built, tested, and shown in browser proof

`fresh` · `stale` · `unavailable` per source; source disagreement; permission denied; upstream
outage; no data; unknown/effect-unknown; degraded-but-partially-usable; the bindings-file-absent
case (which must change only the binding branches, nothing else); terminal Attempt without a
validated return; a decision edge older than the return it claims to close; and unmatched dispatch
evidence rendered as freshness-unknown, never as current.

A state that is not reachable in the browser proof is not delivered.

## Tests

- deterministic, offline, fixture-driven; no network, no clock dependence
- byte-identical output for identical inputs including an identical injected `generated_at`
- closed `OUTPUT_KEYS` assertion
- one explicit test per failure state above
- an anti-duplication test asserting H1 does not define its own status-severity ranking or
  dialogue/dispatch classifier
- a path-ceiling test asserting the H1 change set is a subset of the nine permitted paths
- a fabricated-deep-link test: any field typed as a deep link is either a real, resolvable URL or
  exactly `NOT_AVAILABLE`/`NOT_APPLICABLE` with owner attribution

## Proof obligations

Green CI is not acceptance. H1 is complete only with: passing deterministic tests; browser proof at
the real loopback path at desktop and mobile breakpoints covering every failure state; and a
production read-back or an explicit, named statement that no production path exists yet.

## Non-goals

No action submission or CEO continuation control (that is H2). No attention ranking or admission
policy (H3). No instrumentation or learning metrics (H4). No new database, cache, queue, retry, or
failover. No second auth or identity layer. No generic dashboard framework. No LLM-authored status,
ranking, suppression, or closure. No remote X1 change. No deployment. No `WS:AI-HUB`.

## Stop condition

Stop after the H1 return with one Draft/HOLD PR and a truthful receipt. Do not mark Ready, merge,
self-review, or advance to H2. Await an explicit Sol edge.

## Organizational ownership

Durable owner remains the existing `WS:CHAIRMAN-CONTROL-ROOM`. H1 creates no new workstream and no
parallel lifecycle. Corrections and discoveries go to Agent OS under that existing workstream.
