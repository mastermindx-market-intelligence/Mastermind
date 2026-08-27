# Executive Wake Fabric PR3 — Native Codex/Claude Transport Commission

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Chairman authority:** explicit current authorization to accelerate the approved hybrid Executive Workforce build  
**Operation key:** `wake-pr3-native-transports-20260827-sol-001`  
**Protected pickup / Skillpack:** `Mastermind@6f1bc3dd39f1ebecd3c22e44aa11ca7a13fa5182`, `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1  
**Source architecture:** PR #172 / squash merge `6f1bc3dd39f1ebecd3c22e44aa11ca7a13fa5182`  
**Transport/ACK boundary amendment:** `docs/superpowers/specs/2026-08-27-wake-pr3-transport-ack-boundary-split-design.md`  
**Implementation plan:** `docs/superpowers/plans/2026-08-27-hybrid-workforce-wake-pr3-native-transports.md`  
**Carrier:** this branch / PR #174 only; do not fork a second Wake PR3 carrier

## Observable mission

Make the already-reviewed Executive Wake Fabric capable of delivering one authenticated, bounded, opaque wake nudge to the **exact runtime-bound Codex-Sol reasoning surface**, and either prove or explicitly refuse the corresponding installed-version Claude/Fable native-resume transport, while preserving the existing Wake obligation/delivery/ACK/source-resolution separation and creating no scheduler, queue, session database, Slack lifecycle, or provider runtime authority.

PR #174 is the provider-native **delivery transport** wave. Target reasoning-session ACK ingress and source-resolution proof are later-wave capabilities under the Chairman-approved transport/ACK boundary split. PR #174 must never convert transport delivery into acknowledgement.

## Why it matters

Executive OS can already represent canonical attention/wake obligations, but production delivery remains globally unarmed. Without a real provider-native continuation transport, a completed child Job or material decision can be canonically known yet still depend on Chris to locate and resume the right parent session. PR3 creates the missing delivery edge without turning Slack, tmux, native apps, or provider threads into lifecycle truth.

## Authority / document precedence

1. Current Chairman approval in the governing Sol conversation, including the approved Option A transport/ACK split.
2. Current protected Skillpack loaded at each modifying action.
3. `docs/superpowers/specs/2026-08-27-executive-workforce-hybrid-role-topology-design.md` from #172.
4. `docs/superpowers/specs/2026-08-27-wake-pr3-transport-ack-boundary-split-design.md`.
5. Existing `docs/EXECUTIVE_WAKE_FABRIC.md` and the merged PR-1/PR-2 Wake contracts/ledger/reconciliation, except only where the boundary-split spec explicitly supersedes #174's old canary completion clause.
6. `docs/superpowers/plans/2026-08-27-hybrid-workforce-wake-pr3-native-transports.md`.
7. Existing OHF / Codex App Server provider-session contracts for reuse only; they do not transfer lifecycle authority into Wake.
8. Current Claude provider source law for installed-version/native-resume probing only.

A newer material source-law or overlapping carrier on Wake/session-target/dispatcher/App-Server authority stops the colliding point for Sol reconciliation; do not overwrite, rebase blindly, or create a replacement carrier.

## Verified current state / collision fence

At release:

- Wake PR-1 contracts and PR-2 ledger/reconciliation exist; production remains globally unarmed.
- `control_plane/session_targets.py` separates target seat, reasoning surface, transport and runtime-only `RuntimeBinding`.
- `control_plane/wake_dispatcher.py` owns typed `WakeDispatcher`, `WakeNudge`, `TransportReceipt` and strict authenticated/retry semantics; `WakeNudge` contains opaque wake/attempt identities rather than worker prose.
- Existing OHF/Codex App Server code provides the provider-native App Server control substrate; reuse/factor it rather than minting a second Codex session manager.
- Mastermind #173 is the separate, accepted Codex-Sol identity conformance carrier and does not transfer Wake implementation ownership.
- #162 fresh-Sol evaluation, #153 Worker Browser, C1/B2/C2, #170 Session Truth and #171 Project Recovery remain separate authority surfaces.
- PR #174 remains the only Wake PR3 implementation carrier.

## Exact implementation scope

Expected primary paths are those frozen in the checked-in plan:

- `control_plane/session_targets.py`
- `control_plane/wake_transport.py`
- `control_plane/wake_dispatcher.py` only for generic registry/composition changes required by the plan
- `integrations/executive_wake/**`
- `ops/executive_os/claude-wake-preflight.py`
- Wake-focused tests and `docs/EXECUTIVE_WAKE_FABRIC.md`

The worker may factor a **narrow existing App Server client primitive** from the accepted OHF surface only if direct reuse is impossible; any need to redesign OHF/session identity is a Sol return boundary.

Target reasoning-session ACK ingress is explicitly out of scope for #174. It must later reuse the existing Wake acknowledgement law and Executive `events`; #174 may not implement or simulate that ingress.

## Explicit non-goals

No RF1/HF1/PF1/MH1 implementation; no CF2 changes; no Worker/provider placement; no new Executive Job/Attempt/Worker/Event schema; no Wake database/table/queue/daemon/cron/session registry; no Slack Agent Relay/C1/B2/C2 change; no generic remote shell; no GUI automation; no Chairman browser/session mutation; no provider credential read/copy/create; no production target enabling or `production_armed=true` in this implementation carrier; no target ACK ingress; no synthetic source resolution.

## Complete machine journey

### Codex-Sol path owned by PR #174

```text
canonical harmless Executive/Inbox source fact
→ existing WakeObligation
→ existing route resolution to target_seat=ceo
→ SessionTarget reasoning_surface=codex
→ exact RuntimeBinding native handle/generation
→ DeliveryAttempt / NudgeAttempt
→ one Codex App Server wake dispatcher call
→ authenticated exact-thread DELIVERED receipt
→ reconstructed DELIVERED_UNACKNOWLEDGED
→ STOP for PR #174
```

`TARGET_ACKNOWLEDGED` and `SOURCE_RESOLVED` are not authored by this transport wave. They remain later-wave capabilities requiring a real target reasoning-session ACK ingress under separate reviewed architecture.

### Claude/Fable path

Before code assumes a resume command, run the checked-in secret-free host preflight against the **installed** Claude Code version. A positive transport requires exact background-session discovery/binding, same-conversation resurrection, and one scriptable bounded same-conversation nudge ingress. If any sub-capability is unproven, return the exact unsupported verdict and leave `claude-code-session` unimplemented. Do not replace missing native resume with polling/tmux/Slack/GUI automation or another session manager.

Any optional Claude canary under #174 proves delivery only and likewise stops at `DELIVERED_UNACKNOWLEDGED`.

## Identity / data / time / null / correction law

- Wake obligation identity comes from the existing canonical source fact and is independent of runtime route.
- `RuntimeBinding` native handle, binding id and generation are runtime-only; native provider thread/session ids never enter Git config.
- Different runtime binding/destination changes delivery identity, not executive seat or source obligation.
- `WakeNudge` stays opaque/bounded; no objective/result body/free-form authority is transported.
- `ACCEPTED != DELIVERED != TARGET_ACKNOWLEDGED != SOURCE_RESOLVED`.
- Missing binding/provider transport is explicit unavailable/unroutable, never an invented new session.
- External delivery is at-least-once plus idempotent consumption/reconciliation; exactly-once execution is not claimed.
- Timeout/disconnect/effect uncertainty stays on the same wake attempt/destination reconciliation path. Never auto-failover to another provider/session.
- Provider/account/host/native handle does not grant executive authority.
- A dispatcher, provider response, canary harness, Slack message or model output cannot author target ACK or source resolution.

## Deterministic vs model-generated behavior

All wake identity, route resolution, destination digest, delivery attempt identity, nudge grouping, receipt authentication and retry/reconciliation are deterministic code. Existing ACK/source-resolution law also remains deterministic, but its production target-session ingress is not part of #174. The wake message delivered to a reasoning surface is fixed/bounded procedure telling it to recover canonical state for opaque wake identities. Model-generated prose has zero authority over wake routing, seat, retries, acknowledgement, completion or source resolution.

## Failure states

Fail closed on wrong/missing RuntimeBinding, stale generation/ABA mismatch, wrong reasoning surface/transport, unsupported or absent provider-native resume, provider timeout/effect unknown, malformed or forged receipt, destination/hash mismatch, transport attempting `ALREADY_DELIVERED`, secret-shaped output, unexpected source prose leakage, missing provider version capability, any attempt to synthesize ACK/source resolution, or any need for a second session/wake store.

## Ordered implementation sequence

1. Re-pin current protected head and open collision paths immediately before every modifying step.
2. Preserve the existing Claude reasoning/transport vocabulary while production remains disarmed.
3. Close the explicit integration-layer dispatcher registry identity blocker; no arbitrary plugin discovery.
4. Bind Codex App Server Wake to the accepted provider-session substrate using exact native-thread resume and one bounded turn.
5. Prove focused Codex/Wake/OHF tests and exact receipt authentication; keep production unarmed/targets disabled.
6. Run the Claude installed-version preflight. Implement Claude transport only on a positive exact contract; otherwise preserve unsupported/unimplemented state.
7. Pin hybrid wake source/seat/reasoning-surface law in tests/docs as needed.
8. Run complete relevant tests, compile/diff checks, hosted CI/security checks and independent adversarial review.
9. Run one harmless dedicated Codex-Sol **delivery-only** canary and reconstruct `DELIVERED_UNACKNOWLEDGED`; run a Claude delivery canary only if its native transport was actually proven.
10. Return to Sol. ACK ingress remains `NOT_BUILT`; do not absorb it, MH1 or provider routing into #174.

## Acceptance tests / real proof

The exact-head return must include:

- discriminating Wake contract/registry/dispatcher tests;
- Codex App Server nudge fake + authenticated receipt matrix;
- existing OHF/broker regressions green;
- stale/wrong binding, ABA generation, forged receipt, accepted-vs-delivered and no-retry falsifiers;
- secret-shape and nudge-payload boundedness proof;
- Claude preflight receipt proving supported or exact unsupported state without credentials/session ids;
- exact-head hosted CI/security checks and independent adversarial verdict;
- live Codex Wake obligation → route → exact-thread delivery identities from one harmless dedicated canary;
- reconstructed canonical status `DELIVERED_UNACKNOWLEDGED` for that canary;
- if Claude supported, the same bounded **delivery-only** proof for one dedicated safe Claude/Fable session;
- static/runtime proof of no new Wake queue/table/session DB/scheduler and zero production arming in the code merge;
- explicit proof that no provider response, canary harness or model output authored `TARGET_ACKNOWLEDGED` or `SOURCE_RESOLVED`.

ACK/source resolution remain later-wave capabilities. PR #174 must prove that no transport success, provider response, canary harness or model output can author them.

## Stop condition

Stop when the Codex App Server delivery edge is implementation-complete and proven by one harmless exact-thread `DELIVERED_UNACKNOWLEDGED` canary, Claude is either host-proven and separately implemented on this same carrier or explicitly retained `UNSUPPORTED / UNIMPLEMENTED`, exact-head hosted/security gates are green, independent adversarial review is clean, and checked-in production remains disarmed. Return to Sol with ACK ingress still `NOT_BUILT`.

## Required continuation handoff

Return exact base/head SHA, changed files, current protected pickup at completion, dispatcher/transport descriptors, tests/hosted runs, adversarial review, host-preflight result, sanitized live canary delivery identities, any collisions, remaining gates and explicit confirmation that no provider credentials or native session ids were persisted. State explicitly that target reasoning-session ACK ingress/source resolution remain later-wave `NOT_BUILT` and production Wake remains disarmed.