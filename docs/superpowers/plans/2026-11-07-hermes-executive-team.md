# Hermes executive-team context implementation plan

**Goal:** Supply the live Hermes integration with a useful, role-scoped mission briefing and a quota-aware external-adviser recommendation using existing source/identity/execution owners.

**Spec:** Mastermind PR #2159 comment6699721779; implementation authorization and initial task tree comment6700014545. Existing WS:CHAIRMAN-CONTROL-ROOM. No new programme.

**Architecture:** `LeadershipReader` composes an existing authenticated `SecretaryAccessClient.read_mission()` with immutable role charters. A host-owned currentness guard and actual native session bind the reader before and after IO. One native read tool makes this callable without introducing submission, a store, queue, router or identity. The pure Grok budget function provides only an advisory preflight; Capacity must atomically recheck/reserve.

**Tech stack:** existing Python 3 standard library, existing httpx client, pytest and installed native Hermes PluginContext/registry APIs. No dependency installation.

**Operation:** hermes-executive-team-implementation-20261107-c3
**Base and procedure pin:** ad6275a9c4d237bce75e52d0d6a8f41264b4ded5
**Owned paths:** integrations/hermes_leadership/**, tests/test_hermes_leadership*.py, this plan, docs/hermes/EXECUTIVE_TEAM_CONTEXT.md.

## Global constraints

- Keep the two currently online GLM 5.3 bots, active OMH/Capacity/H24/#2134 source and the selected native memory provider intact.
- Native host supplies role, current session, fixed Workspace client and grant. Model arguments never select any of them. Guard and role names are not authentication by themselves.
- Consume incumbent mission summary; do not reimplement its projection or infer product acceptance from a result reference.
- Always preserve no-admission/no-dispatch/no-retry semantics. EFFECT_UNKNOWN remains an original-owner reconciliation obligation.
- No live config, subscription, credential, role identity, service restart, protected rule, merge or self-approval changes in the source packet.
- Hosted CI and live host composition remain separate acceptance evidence.

## Review focus

1. Binding changed during await: discard the returned mission, not merely add a warning.
2. Two principals with identical-looking mission titles: actual source selection and session must remain distinct.
3. Stale/future/source-partial mission: no apparently current actionable briefing from unavailable source.
4. Remaining quota and reservations: never subtract or add the same pool twice; policy recommendation is not reservation.
5. Native registry collision or ambiguous registration: preserve the original slot/lease and report uncertainty; no broad cleanup or retry.

## L1 — charters and authenticated mission consumer

Create `charters.py`, `reader.py`, package __init__, and tests. Public `charter_for(key)` returns a detached dict for meta_ceo, secretary, delivery, engineering, reliability, product, intelligence, assurance or grok_adviser. Use the existing ResponsibilityIntent constructor to validate role syntax. Charters are guidance, not grants or runtime identities.

`LeadershipReader(*, charter_key, session_id, access: SecretaryAccessClient, currentness_guard)` captures the exact current selection and Workspace transport. `await reader.read(session_id=...)` checks binding and guard before/after the one existing read. Always request full detail. Return bounded `mastermind.hermes_leadership_brief.v1`, one role charter, the unchanged validated mission summary and explicit unknowns/limits. Source refusal and stale/malformed/changed inputs carry no mission body. No mutable shared role context or cached facts.

- [x] Add failing tests for missing module, charter isolation, actual mission consumer, session mismatch, host changes, revoke during read and unavailable source.
- [x] Implement the bounded reader and validate with actual Workspace producer fixture plus authenticated client transport.
- [x] Run existing responsibility/mission/client suites and new tests.

## L2 — native read consumer

Create `native.py`, tests and operator example. Register only `mmx_leadership_brief`, empty closed model arguments, actual native session supplied through Hermes invocation metadata. Reuse incumbent native PluginContext, registration lifecycle coordinator and registry. Profile/session scope mismatch refuses. Exact readback and owned-lease unload, no global registry or broad unregister.

- [x] Red tests for invalid arguments, wrong session/profile, collision and registration/readback failure.
- [x] Implement async handler and registration through actual upstream APIs.
- [x] Run isolated actual installed-Hermes registration tests, including same-name tools in independent native scopes and lease disposal.

## L3 — seven-day external-adviser policy

Create `budget.py` and tests. Pure `evaluate_adviser_budget(snapshot, request, *, now)` returns recommendation only: 70% daily work, 10% weekly review, 20% urgent reserve; one verified meter/window; int basis points; fresh timezone-aware seven-day observation; spend/reservations validated; daily pacing and purpose bucket limits. Reject extra fields and unsupported types with value-free errors. No IO, provider call or state.

- [x] Red tests for thresholds, reservations, freshness, identity, reset/day rollover, malformed counts and no input mutation.
- [x] Implement policy and compose optional host-supplied budget recommendation into adviser context without changing admission.
- [x] Prove deterministic behavior and advisory-only output.

## L4 — evidence and publication

- [x] Run focused combined suites, actual native interface canary, compile and diff checks.
- [x] Run the repository test command with bounded retained output; disclose inherited/dependency failures, do not claim a full pass from focused tests.
- [ ] Self-check diff and source boundaries; publish via original managed publisher; create exact-head source PR and read back.
- [ ] Record current-head CI and next installed-owner integration action in parent #2159. Do not claim source as live deployment.

## Execution record

Initial baseline command: `python3 -m pytest -q -o addopts='' tests/test_executive_responsibility.py tests/test_secretary_team_mission.py tests/test_secretary_team_access.py --tb=short` (receipt recorded after completion).

Paid Fabric budget leaf run `hermes-executive-team-budget-20261107-c3-01`, controller99442: canonical status REQUEST_REFUSED_BEFORE_LAUNCH / EXECUTION_NOT_ELIGIBLE; exit75; request retained, no worker result, same-run replay false. No retry or provider change. Parent continues direct source work under NO_ELIGIBLE_PRE_EFFECT_WORKER. This does not alter the unrelated uncertain memory worker.

## Completion boundary

A verified callable native-context source slice is useful but does not complete the full redesign. Remaining live integration, OMH main inference/worker route, Grok routine cutover, Kimi evaluation and R2/H1–H8/natural-time reliability stay with their original programme owners and acceptance requirements.

## Source qualification milestone

- Baseline responsibility/Mission/client suite: 81 passed in 5.72s, exit0.
- Test-first missing package, budget module, native module, adviser composition, host-session resolver and CLI cases were observed failing before implementation.
- Initial concurrent-test failure was a test construction bug: multiplying two coroutine objects made asyncio.gather reuse two results. A minimal reproducer showed 2 versus 16 result identities; the test now creates 16 distinct reads. No product isolation guard was weakened.
- Registration uncertainty test found the inherited error class identified mmx_delegate instead of mmx_leadership_brief. The new package's error subclass now preserves its exact own tool name; shared source remains untouched.
- Ruling: use an injected existing-native-session resolver for a profile rather than one fixed reader per profile. This supports one Secretary with many isolated tasks without introducing another session registry. Reader identity is rechecked after await.
- Python 3.11.10 final focused/native/authenticated HTTP qualification: **201 passed in 29.23s**, exit0. Command in EXECUTIVE_TEAM_CONTEXT.md plus tests/test_secretary_team_access_http.py and tests/test_secretary_team_mission_http.py. Log /tmp/hermes-executive-team-final-py311-20261107-c3.log.
- Actual native API source: /Users/chriswong/.hermes/hermes-agent at 2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19. Tests use temporary profiles and synthetic source/auth fixtures, not the live bots.
- Offline CLI sample in integrations/hermes_leadership/examples/budget.json yields maximum_bps=1000 and ELIGIBLE_FOR_CAPACITY_CHECK, with admitted=false, reservation_created=false. It is synthetic input, not an observed account meter.
- Compileall and AST parsing passed. Final whitespace/path checks are repeated before publication.
- Broad repository command python3 -m pytest --maxfail=1 --tb=short stopped during collection at tests/context_mcp/test_authenticated_context_asgi.py because Python3.14 lacks jwt. Existing Python3.11 has jwt; that full command then stopped at tests/integration/test_fabric_chat_buffered_delivery.py because claude_agent_sdk is absent. No dependency installation, test exclusion or full-suite pass is claimed. Canonical hosted CI remains required.
- SELF_REVIEWED: currentness before/after IO, original result/acceptance distinction, actual native lease/collision/ambiguous-effect identity, budget reserve/accounting, output/argument bounds, no state/provider writes and unique path scope checked. No independent review or formal GitHub approval claimed.

Native composition and live activation remain unperformed. No source-only test is proof that the existing two live bots load this package, that a Grok budget is enforced, or that a specialist has been admitted to execution.

Current-master compatibility check before publication: protected-source candidate `5ca25e561ffaeacb4ef94bb08f507617f80d0607` has identical INDEX, governing execution/review laws, imported responsibility/Mission/native registration code, pytest/CI configuration and owned new paths relative to the retained pin. The only selected-file delta is DELIVERY_WORKFLOW's more explicit exact-PR merge receipt in the later deployment example. That was inspected; no deployment is attempted and it changes no source publication precondition. No ancestry-only rebase or live-writer edit was made.
