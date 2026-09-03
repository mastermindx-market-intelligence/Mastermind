---
schema: mastermind.ai_operating_hub_h1_handoff.v1
operation_key: mastermind-ai-operating-hub-h0-current-estate-freeze-20260903-sol-001
h0_source: research/MASTERMIND_AI_OPERATING_HUB_H0_CURRENT_ESTATE_2026-09-03.md
h0_evidence: research/evidence/ai_operating_hub_h0_archaeology_2026-09-03.json
protected_master_at_freeze: 642fa62540f0f2565ccc484a350f2cd0a2259015
workstream: WS:CHAIRMAN-CONTROL-ROOM
authorization_state: HELD
production_effect: NONE
---

# AI Operating Hub — H1 bounded read-only Workstream Workroom handoff

> **This document is a handoff specification, not authorization.** H1 is `HELD`. It receives
> implementation authority only after the H0 record above is independently reviewed and merged
> into protected `master`. A worker that cannot verify that predecessor must return
> `BLOCKED SOURCE_PREDECESSOR_UNPROTECTED effect=NONE` and preserve its exact carrier.

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

## Exact path ceiling

Frozen by H0 §8. This is the complete set of paths H1 may touch.

**May create:**

| # | Path | Purpose |
|---|---|---|
| 1 | `control_plane/ai_operating_hub_workroom.py` | one typed, **pure** derived read-only contract |
| 2 | `tests/test_ai_operating_hub_workroom.py` | deterministic contract tests |
| 3 | `app/static/chairman_control/hub_workroom.js` | one additive presentation module |
| 4 | `docs/superpowers/plans/2026-09-XX-ai-operating-hub-h1-implementation-receipt.md` | H1 receipt |

**May modify — only after PR #326 merges:**

| # | Path | Permitted change |
|---|---|---|
| 5 | `scripts/chairman_control_room.py` | exactly one additive read-only route |
| 6 | `app/static/chairman_control/index.html` | exactly one additive mount point |

**Must not touch, unconditionally:** `control_plane/chairman_control_room.py`,
`control_plane/chairman_control_room_remote.py`, `scripts/chairman_control_room_remote.py`,
`app/static/chairman_control/remote.html`, `app/static/chairman_control/control_room.js`,
`app/static/chairman_control/control_room.css`,
`control_plane/autonomy_control_room_projection.py`, `ops/control_room_remote/install.sh`,
`ops/control_room_remote/mastermind-control-room-remote.service`, and anything owned by PR #350.

A seventh path requires `DECISION_REQUEST / PATH_BOUNDARY_REQUIRED effect=NONE` before edit.

## Blocking precondition — PR #326

PR #326 is `OPEN / DRAFT` at head `2eb9d23b2f1fc116cd4071c1f4651da9e87366f2`. It owns
`control_plane/autonomy_control_room_projection.py` — schema `mastermind.autonomy_control_room.v1`,
its own `OUTPUT_KEYS`, and the `query_status` / `is_actionable` / worst-wins `_combine_status`
severity logic with per-source receipts — and it modifies `control_room.js`, `control_room.css`,
and `index.html`.

Consequences for H1, both mandatory:

1. **Do not re-derive card status.** Once #326 merges, H1 consumes its `query_status` /
   `is_actionable` vocabulary. Inventing a second derived-status authority is `REJECTED_BY_DESIGN`.
2. **Do not edit paths 5–6 while #326 is open.** If H1 begins before #326 merges, it is limited to
   paths 1–4 and must return `BLOCKED UI_PATHS_CONTENDED_BY_PR_326 effect=NONE` for paths 5–6.

## Sequence

1. Fresh-read protected `master`; confirm the H0 record is merged. If not, return
   `BLOCKED SOURCE_PREDECESSOR_UNPROTECTED effect=NONE`.
2. Load the Skillpack at that same SHA; verify `schema` / `skillpack_version` /
   `minimum_bootstrap_major` compatibility.
3. Re-run the duplicate/collision census over the six ceiling paths and the H1 branch name.
4. Re-check PR #326 state. Record its exact disposition; it selects the path budget (1–4, or 1–6).
5. Write path 1 as a **pure** function over an already-composed
   `mastermind.chairman_control_room.v1` document. No file I/O, no subprocess, no clock read, no
   environment read. `generated_at` is injected by the caller, never sampled inside.
6. Write path 2 red-first against fixtures, including every failure state below.
7. Write path 3 as an additive module. It renders only fields the contract emits; it must not
   compute status, rank items, or fetch from any source the contract did not already carry.
8. Only if #326 has merged: add one read-only route (path 5) and one mount point (path 6).
9. Run the repository test battery. Capture browser proof at the real loopback path at desktop and
   mobile breakpoints, covering every failure state.
10. Write path 4 as the receipt. Publish one Draft/HOLD PR. Return on the H1 carrier.

## Contract requirements for path 1

The derived contract must:

- consume an already-composed `mastermind.chairman_control_room.v1` document; never re-open or
  re-join canonical sources itself;
- preserve the compositor's four design laws unchanged — no synthetic overall status, bindings
  never create canonical facts, exact joins only, upstream key names never renamed;
- carry a closed `OUTPUT_KEYS` set asserted by test, as both the compositor and the remote
  projection already do;
- keep `observed_at` and `source_time` separate, and never conflate them;
- keep `degraded` a first-class output; an empty list means "no detected failure", never "healthy";
- preserve disagreements as disagreements — never average, vote, or pick a winner;
- emit `null` rather than a fabricated default for any absent identity;
- attach every rendered claim to its canonical owner and a deep link.

## Required failure states — all must be designed, built, tested, and shown in browser proof

`fresh` · `stale` · `unavailable` per source; source disagreement; permission denied; upstream
outage; no data; unknown/effect-unknown; degraded-but-partially-usable; and the bindings-file-absent
case (which must change only the binding branches, nothing else).

A state that is not reachable in the browser proof is not delivered.

## Tests

- deterministic, offline, fixture-driven; no network, no clock dependence
- byte-identical output for identical inputs including an identical injected `generated_at`
- closed `OUTPUT_KEYS` assertion
- one explicit test per failure state above
- an anti-duplication test asserting H1 does not define its own status-severity ranking
- a path-ceiling test asserting the H1 change set is a subset of the permitted paths

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
