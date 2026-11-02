# MiniMax M3.1 Flash in Subagent Fabric — scoped delivery plan

**Authoritative procedure pin:** mastermindx-market-intelligence/Mastermind `master@1f1b30d1352d2a975624e558bd9da097e4cba417`, Sol Skillpack `mastermind.sol_skillpack.v1/1.0.1`.
**Chairman objective (2026-11-01):** Make MiniMax M3.1 Flash callable from the existing Fabric using the already-paid MiniMax plan, without creating a second provider, billing path, routing/capacity plane, or weakening existing safety/custody controls.
**Implementation carrier:** `sol/minimax-m31-flash-fabric-20261101` in Mastermind. A new source branch is not proof of installed runtime.
**Organizational parent:** Resolve existing Agent OS Fabric/provider workstream and latest dated handoff before organizational projection; do not mint a lookalike WS. **DONE_WHEN:** a valid admitted Fabric invocation selects native `MiniMax-M3.1-Flash` using the existing subscription credential, runs a bounded real worker to a retained response, and preserves quota, host, effect and review gates, with independent exact-head review and applicable normal release/installation proof.

## Source facts and guardrails
- MiniMax announced M3.1 Flash 2026-10-19. Official MiniMax M Plan docs list M3.1 Flash; provider-native ID is `MiniMax-M3.1-Flash`; supported Anthropic endpoint is `https://api.minimax.io/anthropic`. Existing MiniMax profile at this pin still selects `MiniMax-M3`.
- Fabric native `minimax` pool, ModelRouter's distinct **disabled** `minimax.attended` alias, and Codex MiniMax runner are separate integration gates. Never turn `enabled`, `autonomous_allowed` or `worker_eligible` on just to make a test pass.
- Keep existing subscribed `sk-cp` credential binding private; never print, replace, or move it to pay-as-you-go. Unknown entitlement or exhaustion is not permission to use paid API or another account.
- Preserve model-specific 1M context/compaction with safe headroom, reasoning/tool protocol and correct model-ID case. A new public alias must map deterministically to the provider ID; expose optional pin and only allow AUTO when model has qualified capacity.
- Existing MiniMax-M3 jobs, source custody, reviewer identity and all `EFFECT_UNKNOWN` operations remain undisturbed. No rerouting an already-started operation. No worker-source edits without exact writer and host permission.
- Relevant overlapping drafts: Mastermind #947 (held attended MiniMax), #1365 (native model/host routing selector), #1788 (native source composition). Check exact changed paths and current writers before edits.

## Task tree (editorial labels, not runtime Job state)
### P1 — source/host census and safe plan integration (in_progress)
Dependencies: none. Owner: current assigned coordinator; existing Fabric source/Capacity owners retain their domains. Confirm native pool model allowlist, launcher, subscription key source, profile, host availability, review/CI contract, and writer collision. Evidence: source paths and revisions, one defensible canonical implementation surface; no secrets.

### P2 — implement M3.1 Flash qualified model path (ready after P1)
Dependencies: P1. Owner: one enrolled source worker or current accountable implementation writer, not concurrent writers of the same files. Extend existing provider/pool model registry and required launcher model validation plus associated fixtures. Preserve `MiniMax-M3` legacy route if necessary for active jobs. Add opt-in exact-model selection and eligible AUTO decision only after qualification; do not change general policy from held to enabled. Evidence: exact changed files, deterministic routing assertions, negative unsupported-model/credential/host/error tests, CI/test receipt.

### P3 — runtime and billing-boundary canary (blocked until P2)
Dependencies: P2, installed native generation, valid plan subscription and host grants. Run a real bounded `minimax` Fabric task pinned to `MiniMax-M3.1-Flash`; verify selected model, retained response, successful worker start/return, quota class, and no pay-as-you-go route. Verify unknown/denied quota fails closed. No fabricated live proof. Evidence: sanitized request/worker receipt and installed generation.

### P4 — independent review and normal release (blocked until P2/P3 evidence)
Dependencies: P2, P3 according to owning rollout gates. Independent non-author review on exact head, tests/CI and approved install path. No self-approval or self-merge. Evidence: PR, review, CI, released/installed SHA, and real-path result. If runtime proof is delayed, report `BUILT_NOT_PROVEN` honestly.

## Continuation frontier
As of plan creation: native M3.1 Flash registration/installation/worker proof NOT VERIFIED; only official entitlement and the old M3 source path have been confirmed. Next action: read exact current native source/allowlist and select the one legitimate writer for P2, while preserving any actual host eligibility refusals. This plan is repository implementation evidence and becomes an Agent OS handoff only after its lawful projection.
