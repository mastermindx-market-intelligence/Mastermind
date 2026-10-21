# Market perception publication and decision custody

MAS-258 / Grey Deer / Risk Radar / Risk On–Risk Off continues through the existing
Market View and decision-context contracts. This implementation does not create a
new event store, numerical model, policy authority, cohort or portfolio schedule.

## Lifecycle and capture

The existing `app.scheduler._macro_refresh_job` remains the sole active lifecycle
owner. It invokes the publisher once after `refresh_and_check`. That result
distinguishes an externally managed source checkout from a failed owned refresh;
`stale=false` alone is not evidence of a successful capture. The old Flagship
phase2 calls now construct unpublished previews with `write=False`.

The publisher reads four fixed paths from immutable objects at one Macro Git
revision and checks that the selected working files match those bytes before and
after capture. It performs no fetch, reset, data collection, model fit or portfolio
run. A partial checkout, changed revision, changed selected file, malformed JSON
or missing required source refuses publication.

| Source | Role | Input path |
| --- | --- | --- |
| Regime, including Radar and MTF | Required voting source | `data/regime/latest.json` |
| Sector cycles | Required voting source | `site/sectordata/sector_cycles.json` |
| RRG | Optional advisory source | `site/marketdata/subsector_rotation.json` |
| Group flow | Optional advisory source | `site/basketdata/flow.json` |

All adapters consume this captured object set at one assessment clock. Each plane
retains its own source date. A regime date cannot refresh an old MTF observation.
Radar, MTF and cycles must all remain eligible, present, directional and validated.
The typed contract retains its context-market-date boundary. Its eligible voter
set must exactly match its governor and the Market View contributors. A source
that is fresh at capture but later than the regime date refuses publication;
current readers also withdraw such an inconsistent legacy pair. Dates are never
relabelled and no dissenting contributor is dropped to restore confirmation.
An expired dissenting voter cannot disappear into a newly favorable consensus.
A refusal preserves the last committed pair; the serving-time reader continues
withdrawing eligibility from that older publication as its evidence expires.

Book-specific distribution is explicitly unavailable. The publisher does not read
holdings or substitute an empty account. Regime nowcast, rotation tensor,
anticipation, Neural Web, liquidity transmission and budget provenance are
explicitly excluded from this bounded capture. Embedded advisory organs in the
regime retain their existing meanings and own dates.

## Identity and one commit point

`source_identity` describes the captured evidence, excluding known publication
and transport clocks. A changed repository head or scheduled invocation alone
does not advance sequence or manufacture a new observation. Same-day source
corrections do advance sequence. Own market dates, source health and known-at
evidence remain part of the identity. Capture clocks must be aware and not future.
A distinct observation must have a strictly later capture clock than the committed
generation, so a delayed older capture cannot overwrite newer admitted evidence.

The publisher serializes under the lock in the existing Market View directory.
The previous parsed publication and its comparison bytes come from one read.
It prepares content-addressed immutable JSON copies in the existing Market View
and decision-context directories. The Market View copy names the exact typed
companion filename and SHA256. The typed copy carries the same generation
metadata without a circular hash reference.

Every ancestor link needed to reach the artifact directories is synchronized,
including links left by an interrupted setup. Both immutable artifact entries
are then synchronized before publication. Reused immutable files are individually
synchronized too: readable orphan bytes do not prove an interrupted file sync
completed. A parent-link synchronization failure
prevents a new commit. The publisher checks the previous latest-file bytes again
before the single atomic rename of `market_view/latest.json`, which is the commit point. Readers follow
that file's named typed copy, verify its digest and shared generation metadata,
and refuse a malformed reference. They never scan orphan prepared files or fall
back from a bad new-format reference to `decision_context/latest.json`.

The latter file is a compatibility copy written only after commit. It is not
authority for a new-format current publication. Legacy publications retain their
existing pair qualification until naturally replaced.

| Result | Meaning |
| --- | --- |
| `published` | Exact committed pair and directory durability acknowledged |
| `unchanged` | Same admitted evidence; existing exact pair verified and synchronized |
| `refused` | Capture/admission/preparation failed without a new committed publication |
| `effect_unknown` | A possible commit occurred but its reply, readback or durability was not established |

A post-rename error is not reported as no effect. The next ordinary invocation can
read back and reconcile the same evidence without creating a duplicate sequence.
No manual rebuild or timer-based clock refresh is required for that reconciliation.

Current PM, strategist and MCP composition also binds the actual Market View
file hash, in addition to its asof/built_at/sequence identity. Interleaving two
generations withdraws the combined typed assessment.

## Evidence at decision time

The autonomous runner records the actual current-perception projection and the
risk section rendered into its initial prompt, then seals the receipt before
provider dispatch. The receipt carries the final prompt hash and is retained in
the existing decision log from the trusted runner result. Provider or
model-submitted provenance cannot replace it. Missing or invalid original
assessment clocks make the projection unavailable; sealing never invents one.

This scope is the initial prompt's market-perception section. It does not assert
which later MCP observations a model obtained or how it used an input. The receipt
is an integrity value inside the existing trusted writer boundary, not a signature
or a new authority service.

Existing self-mirror rows carry that receipt, original decision timestamp and
decision ID into journal drafting. Historical entry planes require a valid bound
receipt whose actual decision day agrees with the existing entry day. The UTC
date check is conservative where only a date-labelled cohort is available; it
does not infer an earlier entry from a later run. A later date-only file cannot
establish which intraday publication a decision saw. The complete receipt stays
in decision_perception with decision_evidence_scope set to initial_prompt_projection_only,
even when planes_at_entry is unknown. Historical rows without a receipt remain
unknown. Resolution-time
context is separately labelled and is never relabelled as entry-time evidence.
This changes attribution, not grading, existing IDs, accepted target custody or
the established forward cohort.

## Qualification and activation boundary

Synthetic tests cover incomplete and stale voting sources, same-day corrections,
unrelated source revisions, duplicate/concurrent triggers, pre-commit failures,
lost post-commit acknowledgements, directory durability failures, corrupted pair
references, scheduler result handling, pre-dispatch custody and historical
attribution. They do not prove market predictive performance or production use.

A read-only actual-input check at 2026-10-21T05:38:37Z captured Macro revision
`7e118c4ad59c15a97ef5ff6908ed8b8ecac56a25` and ran only local pure projection.
Radar and cycles were dated 2026-10-19, while MTF's own date was 2026-08-05.
The required-voter gate therefore remains closed for those bytes. No producer,
refresh, model, portfolio, nightly or grading job was invoked. The completeness
gate must not be loosened to make this stale input pass.

Source admission does not authorize production deployment. Activation requires
qualified exact-release custody, the reserved production decision, intact
existing cohorts, eligible upstream evidence and actual installed-consumer proof.
The wider MAS-258 research, source-purpose, warning/recovery, prospective-maturity
and capital-policy holds remain in force.
