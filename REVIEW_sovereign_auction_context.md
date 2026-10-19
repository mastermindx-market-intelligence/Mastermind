# Mastermind sovereign auction consumer — bounded review receipt

**Recommendation: ready for the canonical workspace's native API and browser gates.**
Source-only review is complete within this assignment. This receipt is not merge,
deployment, live publication, historical PIT completeness, predictive validation,
or risk-authority acceptance.

## Binding and scope

The candidate uses Mastermind base `c7e47c859eb2925c5626931fd511800773ba09ac`.
The reviewer inspected the exact captured originals of `app/web.py`,
`app/static/market_view.html`, `config/contracts.yml`, the bounded consumer
contract, the final W1 producer, all candidate source/test files and fixtures.
All edits in this review were limited to `mastermind_patch`. No remote repository,
branch, commit, PR, provider job or production state was changed by the reviewer.
Root retains canonical source custody and final adjudication.

The original shared event-calendar fixture remains byte-identical:
`b3e7eb3b5ca32e0ebe3d23011d9fa917841f38e9fb436c73c8ca62b53b01d0cb`.
`SOURCE_CANDIDATE_HASHES.json` binds every final candidate file and the exact
preimages of the three existing modified files. The verification receipt binds
the final producer and consumer module digests plus the four actual capture
receipt digests.

## Findings repaired inside the bounded candidate

1. **Medium — lifecycle labels could contradict the cutoff.** The original pure
   reader accepted a real October 13 future Bill as `AWAITING_RESULT` at the
   October 8 producer cutoff, and accepted `TENTATIVE` as its physical state
   despite explicit announced source evidence. It now checks the lifecycle
   transition against the producer cutoff and the event's actual deadline or
   elapsed ET date. The issue-calendar label uses the same ET cutoff date;
   passage does not become observed payment or settlement.
2. **Medium — temporal metadata could contradict its own evidence.** The reader
   accepted first-observed later than selected known-at, receipt evidence later
   than the latest source attempt, and age zero where cutoff minus receipt was
   157.585171 seconds. It now rejects those contradictions and a row whose known-at
   exceeds the overall valid source observation. A later page request preserves
   the producer-cutoff age and the `Freshness unassessed` label.
3. **Medium — normalized class could contradict original Treasury fields.** A
   raw Bill with both explicit type and normalized class changed to Note was
   accepted. The reader now reconciles retained raw security type, explicit type,
   and CMB/TIPS/FRN flags, including their permitted base classes. Null/blank flags
   retain the producer's unknown semantics. This repair incorporates the sibling
   Terminal review's cross-check; it does not modify the W1 source owner.

These repairs have targeted regression coverage. Because the reviewer authored
the repairs after finding them, their passing checks are bounded repair evidence;
the canonical runtime and release review remain separate owner gates.

## Verified behavior

- `python3 -m unittest discover -s tests -p 'test_sovereign_auction*.py' -v`:
  19 pure validator/reader tests passed. The API class is explicitly skipped
  because this scratch environment has no FastAPI. Its four methods are unrun
  here, not counted as four passes.
- `node tests/test_sovereign_auction_renderer.cjs`: actual page renderer function
  checks passed for EN/ZH copy, exact fixture amounts and clocks, scheduled-first
  grouping with 43 past results and three future rows, counts/expansion, awaiting
  and unknown fields, escaped malicious text/attributes, official source links,
  unsafe-link suppression and unavailable states.
- Final W1 `snapshot` of the actual four-source capture, then final consumer
  validation at `2026-10-08T23:00:00Z`: available, 74 episodes and four source
  health records. The classes were 56 Bills, 10 Notes, four Bonds, two TIPS and
  two FRNs. This is current observed context, not a historical prediction test.
- An empty eligible receipt set stays unavailable with zero displayed rows.
  A separately labeled synthetic later transport-failure control retained all
  74 previously observed rows while showing degraded status and the later
  failure. It did not refresh source observation time.
- Source diff inspection confirms that the only existing application behavior
  change is a response-only sibling after existing rotation enrichment. It never
  fills the stored `event_calendar` plane, writes Market View, imports decision
  engines into the reader, or adds `auction_stress`/`treasury_auctions` aliases.
  Unknown `band`, `stressed` and other non-allowlisted fields are excluded.
  Existing TreasuryContext, prompt, risk, PM/strategist and sizing sources are
  unchanged. Runtime invariance of their outputs is still a native API test gate.

## Exact next dependency

Apply the frozen files to the already acquired Mastermind operation workspace,
checking base identity and existing-file preimages. Run the same Python tests
with the repository's real dependencies, which include FastAPI, Pydantic,
`portfolio.registry`, `brain.anticipation`, `brain.decision_context` and
`brain.pm_conviction`; do not substitute missing application modules. Run the
actual native route and relevant existing tests, then inspect responsive EN/ZH
light/dark browser rendering. The HTML function test does not prove layout,
accessibility, served HTTP behavior, authenticated publication or the deployed
`vendor/macro` data path. No deployment is authorized by this receipt.
