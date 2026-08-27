# Executive Wake Fabric PR3 — Native Codex/Claude Transport Commission

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Chairman authority:** explicit current authorization to accelerate the approved hybrid Executive Workforce build  
**Operation key:** `wake-pr3-native-transports-20260827-sol-001`  
**Protected pickup / Skillpack:** `Mastermind@6f1bc3dd39f1ebecd3c22e44aa11ca7a13fa5182`, `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1  
**Source architecture:** PR #172 / squash merge `6f1bc3dd39f1ebecd3c22e44aa11ca7a13fa5182`  
**Implementation plan:** `docs/superpowers/plans/2026-08-27-hybrid-workforce-wake-pr3-native-transports.md`  
**Carrier:** this branch / one future PR only; do not fork a second Wake PR3 carrier

## Observable mission

Make the already-reviewed Executive Wake Fabric capable of delivering one authenticated, bounded, opaque wake nudge to the **exact runtime-bound Codex-Sol reasoning surface**, and either prove or explicitly refuse the corresponding installed-version Claude/Fable native-resume transport, while preserving the existing Wake obligation/delivery/ACK/source-resolution lifecycle and creating no scheduler, queue, session database, Slack lifecycle, or provider runtime authority.

## Why it matters

Executive OS can already represent canonical attention/wake obligations, but production delivery remains globally unarmed and PR3 transport is unbuilt. Without a real provider-native continuation transport, a completed child Job or material decision can be canonically known yet still depend on Chris to locate and resume the right parent session. PR3 creates the missing delivery edge without turning Slack, tmux, native apps, or provider threads into lifecycle truth.

## Authority / document precedence

1. Current Chairman approval in the governing Sol conversation: hybrid Sol/Codex/Fable architecture is approved and implementation should proceed quickly.
2. Current protected Skillpack at `6f1bc3dd39f1ebecd3c22e44aa11ca7a13fa5182`.
3. `docs/superpowers/specs/2026-08-27-executive-workforce-hybrid-role-topology-design.md` from #172.
4. Existing `docs/EXECUTIVE_WAKE_FABRIC.md` and the merged PR-1/PR-2 Wake contracts/ledger/reconciliation.
5. `docs/superpowers/plans/2026-08-27-hybrid-workforce-wake-pr3-native-transports.md`.
6. Existing OHF / Codex App Server provider-session contracts for reuse only; they do not transfer lifecycle authority into Wake.
7. Current Claude provider source law for installed-version/native-resume probing only.

A newer material source-law or overlapping carrier on Wake/session-target/dispatcher/App-Server authority stops the colliding point for Sol reconciliation; do not overwrite, rebase blindly, or create a replacement carrier.

## Verified current state / collision fence

At release:

- Wake PR-1 contracts and PR-2 ledger/reconciliation exist; production remains globally unarmed; no accepted PR3 transport implementation is live.
- `control_plane/session_targets.py` already separates target seat, reasoning surface, transport and runtime-only `RuntimeBinding`; `codex` reasoning surface and `codex-app-server` transport already exist as vocabulary.
- `control_plane/wake_dispatcher.py` already owns typed `WakeDispatcher`, `WakeNudge`, `TransportReceipt` and strict authenticated/retry semantics; `WakeNudge` contains opaque wake/attempt identities rather than worker prose.
- `control_plane/remote_codex_operator_adapter.py` / existing broker/OHF code already provides the provider-native App Server control substrate; reuse/factor it rather than minting a second Codex session manager.
- Mastermind #173 is a separate Codex-Sol **identity conformance** carrier and has been narrowed so it does not edit Wake Fabric implementation/tests/docs.
- #162 fresh-Sol evaluation harness touches its own `scripts/ohf/fresh_sol_eval.py` / test surface and may consume App Server behavior, but does not own Wake PR3 paths.
- #153 Worker Browser, #155 C1 SOL_STATE, #170 Session Truth and #171 Project Recovery remain separate.
- No other open Wake PR3 implementation carrier was found at release.

## Exact implementation scope

Expected primary paths are those frozen in the checked-in plan:

- `control_plane/session_targets.py`
- `control_plane/wake_transport.py`
- `control_plane/wake_dispatcher.py` only for generic registry/composition changes required by the plan
- `integrations/executive_wake/**`
- `ops/executive_os/claude-wake-preflight.py`
- Wake-focused tests and `docs/EXECUTIVE_WAKE_FABRIC.md`

The worker may factor a **narrow existing App Server client primitive** from the accepted OHF/broker surface only if direct reuse is impossible; any need to redesign OHF/session identity is a Sol return boundary.

## Explicit non-goals

No RF1/HF1/PF1/MH1 implementation; no CF2 changes; no Worker/provider placement; no new Executive Job/Attempt/Worker/Event schema; no Wake database/table/queue/daemon/cron/session registry; no Slack Agent Relay/C1/B2/C2 change; no generic remote shell; no GUI automation; no Chairman browser/session mutation; no provider credential read/copy/create; no production target enabling or `production_armed=true` in this implementation carrier.

## Complete machine journey

### Codex-Sol path

```text
canonical Executive/Inbox source fact
→ existing WakeObligation
→ existing route resolution to target_seat=ceo
→ current SessionTarget reasoning_surface=codex
→ exact RuntimeBinding native handle/generation
→ DeliveryAttempt / NudgeAttempt
→ one Codex App Server wake dispatcher call
→ ACCEPTED or authenticated DELIVERED receipt
→ existing TARGET_ACKNOWLEDGED path
→ parent retrieves canonical state and continues
→ SOURCE_RESOLVED only when source fact is actually resolved
```

### Claude/Fable path

Before code assumes a resume command, run the checked-in secret-free host preflight against the **installed** Claude Code version. If it proves an exact non-interactive resume-by-session-id contract, implement that exact transport and canary it. If it does not, return `CLAUDE_WAKE_UNSUPPORTED` and leave `claude-code-session` unimplemented. Do not replace missing native resume with polling/tmux/Slack as permanent Wake.

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

## Deterministic vs model-generated behavior

All wake identity, route resolution, destination digest, delivery attempt identity, nudge grouping, receipt authentication, retry/reconciliation, ACK and source resolution are deterministic code. The wake message delivered to a reasoning surface is fixed/bounded procedure telling it to recover canonical state for opaque wake identities. Model-generated prose has zero authority over wake routing, seat, retries, completion or source resolution.

## Failure states

Fail closed on wrong/missing RuntimeBinding, stale generation/ABA mismatch, wrong reasoning surface/transport, unsupported or absent provider-native resume, provider timeout/effect unknown, malformed or forged receipt, destination/hash mismatch, transport attempting `ALREADY_DELIVERED`, secret-shaped output, unexpected source prose leakage, missing provider version capability, or any need for a second session/wake store.

## Ordered implementation sequence

1. Re-pin current protected head and open collision paths immediately before the first write.
2. Follow Task 1 of the merged plan: add Claude reasoning/transport vocabulary while all transports remain unimplemented/disarmed.
3. Add the explicit integration-layer dispatcher registry; no arbitrary plugin discovery.
4. Implement Codex App Server Wake by reusing/factoring the accepted provider-session substrate.
5. Prove focused Codex/Wake/OHF tests and exact receipt authentication; only then mark the Codex transport descriptor implemented. Keep production unarmed/targets disabled.
6. Build and run the Claude installed-version resume preflight. Implement Claude transport only on a positive exact contract; otherwise preserve unsupported state.
7. Pin hybrid wake source/seat/reasoning-surface law in tests/docs.
8. Run complete relevant tests, compile/diff checks, hosted CI/CodeQL and independent adversarial review.
9. Only after code acceptance, run one harmless dedicated Codex-Sol live Wake canary; run Claude canary only if native resume was proven.
10. Return to Sol. Do not absorb MH1/provider routing.

## Acceptance tests / real proof

The exact-head return must include:

- discriminating Wake contract/registry/dispatcher tests;
- Codex App Server nudge fake + authenticated receipt matrix;
- existing OHF/broker regressions green;
- stale/wrong binding, ABA generation, forged receipt, accepted-vs-delivered and no-retry falsifiers;
- secret-shape and nudge-payload boundedness proof;
- Claude preflight receipt proving supported or exact unsupported state without credentials/session ids;
- exact-head hosted CI/CodeQL and independent adversarial verdict;
- live Codex Wake obligation → route → delivery → ACK → source-resolution identities from one harmless dedicated canary;
- if Claude supported, same bounded proof for one dedicated safe Claude/Fable session;
- static/runtime proof of no new Wake queue/table/session DB/scheduler and zero production arming in the code merge.

## Stop condition

Stop when Codex App Server Wake is implementation-complete and production-proven through one harmless dedicated canary, Claude native resume is either production-proven or explicitly retained `UNSUPPORTED / UNIMPLEMENTED`, and the existing Wake source/delivery/ACK/source-resolution law survives intact. Do not implement MH1, RF1/HF1/PF1, or generic Slack wake.

## Required continuation handoff

Return exact base/head SHA, changed files, current protected pickup at completion, dispatcher/transport descriptors, tests/hosted runs, adversarial review, host-preflight result, live canary safe identities, any collisions, remaining gates and explicit confirmation that no provider credentials or native session ids were persisted.