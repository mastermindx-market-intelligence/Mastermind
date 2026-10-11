# Bot autonomy renewal implementation plan

> For agentic workers: use `superpowers:executing-plans` for permitted inline work or the existing admitted Fabric for separable bounded outcomes. Never fabricate a worker dispatch.

**Goal:** Recover the protected Portfolio V3 program and deliver its missing evidence foundation before granting adaptive research any authority.
**Architecture:** Extend the existing September 15 V3 architecture. Keep research, risk construction and paper execution separate. Reuse Executive/Model Router/Capacity for eventual model execution; no new provider control plane.
**Tech stack:** Existing Python, canonical JSON serializer, pytest, FastAPI and dashboard, with no new mandatory dependency.
**Spec:** `docs/superpowers/specs/2026-10-11-bot-autonomy-fabric-renewal.md`; underlying specification and detailed S0 plan remain the September 15 files.

## Global constraints

- Source basis `cbc7503536b6853ec7c35c2192abdfaccb87b561`; own workspace/branch `bot-intelligence-renewal-20261011` / `sol/bot-intelligence-renewal-20261011`.
- Current assignment permits independent isolated source work. Do not use historical S0 operation names to replay or transfer an incumbent action.
- No active account, pending target, settlement, provider, secret, model, scheduler or production change.
- Preserve S0 v1 schemas, byte/row limits and canonical serializer owner.
- No additional queue, dispatcher, credential selection, market-risk score, learning ledger or runtime status machine.
- No merge/release until current collision, exact-head checks and independent review are proven.
- Source files on existing shared UI/auth/provider surfaces remain held while their current collisions and dependencies are unreconciled. New candidate files do not displace an incumbent writer.
- Retain actual tool refusals and original uncertain effects; do not retry blocked actions on another carrier.

## Review focus

1. Forged complete coverage despite missing, future, malformed, stale or rights-blocked inputs.
2. Booleans masquerading as numbers; NaN/Infinity; duplicate identities; unbounded nesting or payloads.
3. Digest validity mistaken for authenticity, market correctness or portfolio execution authority.
4. Cutoff/known-at mismatch, recording before decision, and correction references that create false hindsight.
5. Source and API paths that permit traversal, symlink escape, account recovery or hidden runtime writes.

## Task 1 — pure closed snapshot contract

Create `portfolio/decision_snapshot_contracts.py` and `tests/test_decision_snapshot_contracts.py`.
Consume only `control_plane.wake_events.canonical_json_bytes` from project source. Produce the exact constants and validator/seal functions specified by September 15 S0 Task 1.

- [ ] Write factories and tests for canonical seal, tampering, immutable-copy behavior and round-trip verification.
- [ ] Prove the tests fail because the new module is absent.
- [ ] Implement exact-key/type/enum/count/clock/digest/authority and cross-reference validation with bounded canonical JSON.
- [ ] Test missing/extra keys, bool counts, duplicate source/domain identities, out-of-cutoff available sources, rights/authority escalation, inconsistent summary/generations, NaN and payload bounds.
- [ ] Run focused tests, compile and diff checks. Record actual results.

Ruling: do not change `config/contracts.yml` until the source-capture consumer and shared-file collision gate are verified. The new pure contract is useful and independently testable; it neither claims source capture nor completes all of S0.

## Task 2 — fixed source capture and immutable store

Use September 15 S0 Tasks 2–3 for exact `capture_all`, `capture_book_state`, `capture_external_sources`, `compose`, `persist`, `load`, status and section contracts. Inspect those exact interfaces before implementation. Fixed paths only, bounded stable reads, explicit clocks, immutable content-addressed create-only storage under `data/shadow/decision_snapshots/autonomous/`.

- [ ] Verify fixed source contracts and register required inputs through the existing contracts owner when its write surface is clear.
- [ ] Write failure tests before implementing capture, clock qualification, source closure, bounded projections and absent-versus-empty semantics.
- [ ] Test store creation, same-content replay, tampering/correction detection, atomic visibility and traversal/symlink refusal.
- [ ] Verify no imports/calls can trigger existing account recovery or provider execution.

## Task 3 — explicit CLI and read-only product projection

Use September 15 S0 Tasks 4–7, not a second snapshot service. CLI composition takes explicit cutoff/recorded clocks; read APIs inspect only already-materialized records. Preserve current identity-plane protection.

- [ ] Implement CLI tests and operator runbook with real temporary-fixture compose/readback.
- [ ] Integrate API/UI only after exact overlapping source carriers are reconciled.
- [ ] Test paper/V2/provider/settlement no-effect invariants and error/corrected/partial states.

## Task 4 — Bot research-to-Fabric vertical

Do not implement a speculative runtime endpoint. Inspect the existing admitted research request, profile, job and result contracts under their canonical owner, then map the Bot's snapshot-bound request into them. The Bot creates no lifecycle store and chooses no credential/provider host.

- [ ] Freeze the exact existing interface mapping and separate Bot service admission from attended Astra client enrollment #633.
- [ ] Use suitable economical workers for routine research and a frontier witness for exceptional judgment; retain root-grant budget, independence and read-only tool fences.
- [ ] Add contract tests for wrong snapshot/root/result generation, late result, duplicate receipt, timeout after effect, refused provider and unavailable capacity.
- [ ] Prove actual eligible worker and frontier execution, retained result, validation and consumption by the original decision. Queue acceptance or mocks do not satisfy this item.

## Task 5 — release and product acceptance

Publish a truthful draft candidate with exact-head evidence; hosted CI is a release dependency, not a reason to stop independent work. Do not deploy or enable trading/provider flags. Carry remaining snapshot/Fabric/product obligations forward explicitly.

- [ ] Inspect the owned diff and secret-free changed-file set.
- [ ] Commit and publish only this operation's own branch through normal reviewed mechanisms, then verify remote identity.
- [ ] Obtain independent review and exact-base release qualification.
- [ ] Only a separately authorized rollout may prove deployed browser, natural-session paper and forward-evaluation acceptance.

## Execution record

2026-10-11: recovered protected V3/#658, current #548/#398/#633/#994/#1293 states, owned isolated workspace and architecture amendment. Executive read unavailable; some exact source/network/collision actions refused pre-dispatch and not replayed. No child dispatched; no production effect. Direct principal work is retained for cross-system architectural judgment and this small pure contract while actual eligible worker admission is not observed. Reassess at the next separable delivery boundary.

## Task 6 — repair the independently reproduced US calendar disagreement

Source diagnosis: `market_sessions.py` already contains the six published 2025–2027 shortened US sessions, but its underlying `market_calendar.py` ignores early closes. `bot/settle.py` resolves the latter for the autonomous book. Local `is_open` returned True at 14:00 ET on November 27 and December 24, 2026. The account helper probe separately raises AttributeError on missing `auth._supabase_decode`; do not guess an identity-plane replacement.

- [ ] Add failing tests for all six 13:00 ET boundaries, UTC conversion, next-open behavior, and the January 9, 2025 exceptional NYSE closure.
- [ ] Move the existing US early-close table into `market_calendar.py`, exposing `is_early_close(date)` and `session_close_time(date)`; use the same owner from `market_sessions.py` rather than retaining duplicate facts.
- [ ] Prove the unchanged regular-day, Hong Kong and China contracts plus the corrected US display/settlement calendar agree.
- [ ] Record primary NYSE/ICE source references and exact local verification. Do not deploy or rewrite any historical account/experiment record.

The newly needed calendar lane was checked with a focused open-PR calendar search and the exact eight-file list for known overnight PR #1293. No returned candidate claims these two calendar files; #1293 instead changes `portfolio/market_clock.py` and Self-Directed paths. This is a bounded candidate-collision check, not a complete repository lease census. Release remains held for independent current-base reconciliation.

Milestone: snapshot contract/storage core passed 87 local tests after clock-basis, aggregate JSON size, concurrent publication, disappearing-record and uncertain-durability regressions. Source-capture implementation write was refused before dispatch and its target absence verified. Its existing RED acceptance tests are preserved as `2026-10-11-bot-autonomy-source-capture.acceptance.py.txt`, not collected or represented as passed implementation. No retry of the blocked write is authorized by this move.

Task 6 continuation: the same underlying defect was reproduced in HK. Thirteen new RED cases show the raw HK calendar reopening at 13:00 on all nine existing 2025–2027 half-days, plus phantom Lunar New Year afternoon wakes; the dashboard already masks these defects. Move the existing HK half-day facts into `china_calendar.py` and make both `is_open` and `next_open` respect them. Preserve the current continuous-session-only paper mandate: HKEX's closing auction can continue after noon, but this repair does not enable auction execution. Official HKEX CT/063/24 and CT/075/25 page-two half-day lists were visually verified, together with HKEX's 2027 calendar and Securities Market hours. A focused open-PR `china_calendar` search returned no result; full source-lease/release qualification remains separate. Preserve mainland-China behavior and use the existing calendar owner; no new session service.
