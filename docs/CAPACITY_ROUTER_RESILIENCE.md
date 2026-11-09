# Unified Capacity Fabric router: resilience and intelligent selection

Parent: Mastermind #983 / WS:EXECUTIVE-CAPACITY-FABRIC.
Operation: capacity-router-resilience-20261109-c4.
Procedure: protected master ff6d5ab67c3535056d69f603fac0d95c058baad8, Skillpack 1.0.1.
Source input: a58c34f1d935ee06e5ef45e77aa5705185398d77 (PR #2367).
This is a scoped extension of the installed unified router, not a replacement allocator,
quota registry, credential store, queue or Executive runtime.

## Outcome and acceptance

Make the shared M2 routing edge reliable under concurrent Hermes, DeepSeek Harness
and T3 traffic, with truthful health, bounded overload and deterministic recovery.
DONE_WHEN: the qualified source passes affected regressions; the normal protected
release path admits it; the installed generation exposes the new behavior; all
three consumers retain their existing endpoint/model contracts and real-path proof.
Source qualification, merge, installed generation and consumer acceptance are separate.

## Recovered live facts

The M2 launchd service ai.mastermind.fabric-router listens on 127.0.0.1:8313.
Its SOURCE.json identifies a58c34f1 and generation
80141f9373320f8d8f337c8475551bc40665a9676aa0c9776685bee281609035.
Read-only health/status/catalog requests succeeded: 14 routes and 45 catalog entries.
The shared source checkout is clean at that commit; no edits are made there.
This operation uses the canonical mmx-workspace isolated branch, not the #2367 writer.
Existing #2338 backend integration, #2351 OS projection, #2366 Anthropic gateway and
#2182 unresolved publication retain their distinct scopes and effects.

## Task tree

| Task | Work | Acceptance | Dependency |
|---|---|---|---|
| UR1 | Verify installed source, current routing and failure behavior | Exact generation, endpoint observations, concrete source findings | None |
| UR2 | Extend existing RouteState selection and circuit control | Tier/weight/affinity contract, load bounds, one half-open probe, provider retry timing, concurrency regressions | UR1 |
| UR3 | Unify request settlement and streaming cleanup | Success only after completion; cancellation/transport/protocol failure closes resources; no invisible replay | UR2 |
| UR4 | Make route health and decisions inspectable | Monotonic cooldowns, in-flight/circuit/counters/latency, bounded safe reason codes; no credentials or prompts | UR2–3 |
| UR5 | Qualify and publish one owned diff | Existing and new adversarial tests, exact-head diff, Ready source PR with dependency/holds preserved | UR2–4 |
| UR6 | Protected release and installed consumer acceptance | Exact approved release, graceful installation, Hermes/DSH/T3 real-path evidence | UR5 and upstream release |

## Concrete source findings to repair

- /statusz uses wall-clock time against monotonic cooldown values.
- Several forwarding paths declare success at HTTP headers before stream completion.
- Anthropic passthrough closes upstream only on normal completion, not cancellation.
- Selection has no local in-flight pressure or bounded half-open recovery.
- OpenAI and Responses streaming paths can emit successful terminal frames at EOF
  without verifying the provider's actual completion.
- OAuth Responses forwarding retries across accounts after 5xx, contrary to the
  documented no-replay-after-possible-effect boundary.
- Refresh helper constructs its client from an out-of-scope variable.

All findings require focused reproductions before their repairs are claimed.

## Design constraints and reuse decision

Keep hard admission, quotas and account identity with their incumbent owners.
The router may limit its own process concurrency and health probes; these are local
bulkheads, not claims of remaining five-hour/weekly/monthly provider allowance.
Preserve exact-model constraints and current priority tiers. Affinity cannot override
an unavailable or saturated route. Add measured latency only as a bounded tie-breaker
after eligibility; never promote an unknown lower-quality model.

Reuse httpx/FastAPI and the current route/state/service interfaces. LiteLLM/Envoy
patterns inform this extension; importing a second gateway would duplicate live
credential and policy owners. Atomic shared-account quota integration remains with
the existing Capacity/Executive lanes, not a guessed quota ledger here.

No new paid provider, credential import, default model change, provider-limit bypass,
duplicate watcher, or request replay is authorized by this plan.

## Execution ownership

Principal retains this coupled source/stream-lifecycle repair: PRINCIPAL_JUDGMENT
and LOWER_TOTAL_OVERHEAD while freezing the exact-effect boundary. A separate native
reasoning reviewer covers architecture and adversarial analysis, not routine labor.
WHY NOT FABLE: the bounded router extension has a concrete source and test surface;
it does not need another principal or a cross-program handoff.

## Evidence and release frontier

Initial workspace creation was NOT_APPLIED / INVALID_ARGUMENT because the canonical
source object was not yet serviceable. A read of that exact commit materialized it;
the same owner then acquired the same operation successfully. No source effect was
replayed or moved. Implementation, tests, publication and installation are pending.
