# W-LIQ.3 adapter recovery and review handoff

## Mission and capability
Connect the existing transmission lab to the repaired W-LIQ.1 producer without
rebuilding monetary factors or manufacturing historical knowledge. This is a
necessary research dependency for the Aion-informed Mastermind upgrade, not a
future-liquidity forecast and not a deployed customer capability.

Status: **BUILT_NOT_PROVEN — candidate for independent review and hosted CI**.
Carrier: existing Mastermind PR #124, branch `codex/mas120-wliq3-20260822`.
Operation: `w-liq3-adapter-recovery-20260915-sol-001` (attended Web source custody).
No Executive Job, provider worker, watcher, release, or trading authority was created.

## Authority and exact sources
Current Chairman continuation authorizes the bounded repair. Constitution,
strategic state, and authority map remain above implementation evidence.
Protected Skillpack: Mastermind `7642aea155d2817219135b24246b55c1d7611c66`,
`mastermind.sol_skillpack.v1` / version 1.0.1 / bootstrap major 1.
The loaded cold-start, active-execution, reconciliation, and closeout skills
are from that same protected commit.
Workspace base: `8de062fb3b5a327466cd98cda0dc7d44b8fd229d`.
Original #124 head: `7bd6dbbc8d93bf2063a820cb93fa5c3cf92ce9da`.
The candidate integrates both histories without a force push or replacement PR.
Comparison to the protected pin found no changes in the governing source,
liquidity paths, selected direct dependencies, CI workflow, or dependency manifests.

W-LIQ.1 acceptance: Macro #6296 comment 5539622225; repaired head
`7fb785ee07b87abb14cfa6e6e35e481a1ccb6a24`, merge
`38fd57a676de07c361040eea7d5e5127034063e1` on 2026-09-04.
The old HOLD body is not current merge state. #123 comments and the Macro
Agent OS record still contain stale producer-hold prose; do not revive that work.
#124 review comment 5385315696 supplies the adapter and historical-evidence gates.
The exact old producer sample and its blob identity are documented beside the fixture.

## Implementation and machine journey
`adapt_producer_state(payload, as_of=...)` is the only new parser. It validates
schema, scope, versions, identity copies, raw/z units, evidence clocks, component
inventories and receipts, the two label vocabularies, finite numbers, and the
registered copied context. It copies into the existing `SourceStateRef`.
The existing `eventize` and `ShockRegistry` remain the episode and persistence path.
No factor recomputation, new collector, new ledger, API, scheduler or consumer is added.

Trustworthy observations alone may now reset an episode or bridge the gap between
observations. Stale, degraded, low-coverage or low-confidence readings can do neither.
Existing materiality, refractory and other policy semantics remain explicit and
without production defaults. The patch does not select an empirical threshold.

Valid warmup/zero-direction inputs produce no event reference rather than fake
zero values or signs. Missing required fields differ from explicit nulls.
Malformed input yields a typed ContractError, including malformed freshness on
an otherwise non-emitting observation. Corrections use the existing append-only
amendment path; exact replay cannot rewrite or duplicate the original record.

## Verification performed in this recovery
Native interpreter: Python 3.14.7; pytest 9.1.1; NumPy 2.5.2; pandas 3.0.5.
The final related regression set passed **285 tests**. It covers the six lab
suites plus outcome ledger, experiment registry, experiment maturity, governance
ledger, and liquidity quality. The lab subset contains 89 tests.

Discriminating red/green evidence: the eight new episode-quality regressions
failed before their repair; the ten copied-context/receipt regressions failed
before theirs; five additional null/type cases failed before the final repair.
The original adapter implementation also followed a 39-test failing baseline.
The exact unmodified producer sample goes through adapter -> eventizer with no
shock under the explicitly test-only threshold. A separately labeled synthetic
case proves adapter -> eventizer -> existing registry -> duplicate -> amendment
-> reopened original record, without changing the preserved original observation.
Targeted compilation and both staged/unstaged whitespace checks passed.
The fixture still hashes to Git blob `89a1ac142d4c9545b8ef1a1237430cf2cd7b35bd`.

The actual native full repository gate was also attempted, not represented as green:
`python3 scripts/ci_pytest.py` discovered 611 modules, excluded none, and stopped
with 36 collection errors. The isolated native environment lacks jwt (18 errors),
mcp (10), claude_agent_sdk (5), reportlab (1), and the pinned Macro import surface
(two errors: signal_archive / lib). No test exclusions, skips, dependency changes,
or CI workaround were introduced. All six lab suites are included by the existing
CI discovery gate. Hosted CI installs the project on Python 3.12 and checks out
its separately pinned Macro engine; its full result remains a release requirement.

## Limits, review focus, and stop condition
This is deterministic research plumbing, not predictive skill. No LLM, trained
model, forecast, ranking, sizing, portfolio action, or live publication is added.
The producer hash is an opaque identity reference, not authentication or proof
that factor arithmetic is correct. This adapter's explicit as_of prevents future
knowledge; the future admitted reader must separately enforce source freshness
at consumption. An old payload's original freshness label is never refreshed here.
Recorded first-known and conservative availability clocks are retained, not
upgraded to an independently attested historical or live publication claim.

An independent reviewer must inspect the canonical sample mapping, null/error
boundaries, copied-context restrictions, episode gap/reset semantics, and exact
current-base compatibility. Builder self-review is not that independent review.
No approved Executive submit app was exposed to this Web session; no raw provider
spawn was substituted and no reviewer pickup or running worker is claimed.
Keep #124 draft with no auto-merge until review and exact-head hosted CI pass.
Do not run a broad historical study or install a production event policy as part
of this repair. 2023–2026 BTC/BABA remains hypothesis-origin evidence, not an
untouched holdout. #119 and later consumers keep their separately commissioned gates.

## Continuation and do-not-redo
Publish this candidate by normal fast-forward on the existing #124 branch, record
its exact commit on #123, then resolve independent review and hosted CI.
After acceptance, freeze the bounded first study policy and admitted reader
contract; obtain real source-to-consumer proof before any live capability claim.
The Aion-inspired future-liquidity outlook is a distinct missing capability from
this asset-response lab. Expiry-aware options maps, level-change explanations,
conditional scenarios and Prophet-first delivery remain separate bounded work
under their existing owners. Do not hide them under this adapter or rebuild their
underlying stores. Macro Agent OS reconciliation remains owed in its owning repo.


## 2026-09-16 continuation — replay ambiguity repaired; release still held

Protected procedure remains `7642aea155d2817219135b24246b55c1d7611c66`.
The previous candidate was pushed as `e9310c71cb1541b85c1ff7205955fd462735a0af`.
Hosted run `35046156905`, attempt 1, job `104636300500` completed with FAILURE
at `2026-09-16T02:27:41Z` in the full repository test gate. CodeQL checks passed.
The structured annotation supplies only exit code 1, not failing test identities.
Raw-log retrieval hit a tool safety block; no alternate raw-log route or rerun
was used. The hosted failure's cause is UNKNOWN, not declared unrelated or fixed.
Independent review is still unassigned; no reviewer or provider was fabricated.

A separate local replay defect was reproduced: two different observations with
one state-family/first-known clock were silently selected by input order, or
could both emit. Six discriminating cases failed before the repair. Eventization
now refuses a conflicting same-clock pair before quality admission; equivalent canonical
observation replay remains idempotent. Corrections still use the amendment owner,
not an input-order tie-break. This is a pure check within the existing eventizer,
not a new deduplication store, lifecycle, policy threshold, or research programme.

The expanded related suites passed **292 tests on Python 3.12.13**, including
96 lab tests. This is a native regression result, not full hosted CI acceptance.
The source fixture is unchanged. No new market data, event policy, empirical
search, forecast, customer surface, or trading authority is introduced.
Continue on #124: independently review the new exact head, determine the old
hosted failure and inspect new-head CI; keep DRAFT/no auto-merge/no deployment.
