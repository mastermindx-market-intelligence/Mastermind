# L. Exact Implementation Handoff

## FOLLOW-ON IMPLEMENTATION COMMISSION — REGIONAL EVIDENCE COVERAGE FOUNDATION, SHADOW ONLY

You are implementing the accepted first phase of **MastermindX Global / Regional Data Parity & Coverage Confidence**.

This is a **bounded implementation commission**. It does **not** authorize new portfolio/trading behavior, new source decision authority, commercial-data purchase, a second Decision Snapshot/control plane, or retrospective fabrication of historical data.

### Bootstrap and source law

Before modifying anything, follow the current Mastermind bootstrap/source-law procedure.

Do not use the research report's repository SHAs as current truth. Fetch and pin current protected Mastermind at implementation time, load the Skillpack from that same immutable basis, resolve current Macro/Terminal/research-vault identities and inspect open branches/PRs for collisions.

Preserve existing ownership for:
- portfolio/held_risk.py
- portfolio/lenses.py
- brain/signal_history
- existing prediction/outcome/shadow-book owners
- Macro China/HK source adapters
- China Prophet live infrastructure
- HK Prophet/board infrastructure
- theme/rotation owners
- Portfolio V3 Decision Snapshot architecture

Do not implement a parallel portfolio, research ledger, outcome ledger, market-regime engine, theme authority or Decision Snapshot.

### Objective

Implement a production-inert, inspectable regional coverage foundation such that every active US, Hong Kong and mainland-China decision candidate can carry a machine-readable statement of:
- what evidence families were expected;
- what was observed;
- what was missing;
- what was stale;
- what was structurally unavailable;
- what was rights-blocked;
- what was correction-uncertain;
- when each observation became lawfully known;
- whether a local evidence type is direct, equivalent, proxy-only or not comparable.

No missing source may be emitted as numerical zero unless zero is itself an observed source value.

### Required implementation scope

Implement and version:
- SecurityIdentityV1
- EvidenceObservationV1
- CoverageStateV1
- DecisionCoverageReceiptV1
- EvidenceEquivalenceRegistry

Every time-sensitive EvidenceObservationV1 must support:
- event_time
- as_of
- observed_at
- available_at
- ingested_at
- effective_from
- effective_to
- correction_generation
- supersedes_observation_id

Use available_at as the historical admissibility clock.

Required CoverageStateV1.coverage_state values:
- observed
- stale
- missing_expected
- structurally_unavailable
- not_applicable
- rights_blocked
- adapter_failed
- identity_uncertain
- correction_uncertain

Required equivalence classes:
- direct_local
- local_equivalent
- proxy
- context_only
- not_equivalent

### Existing-source instrumentation

Instrument existing sources first. Do not buy new data in this commission.

At minimum cover the active evidence available to:
- US autonomous portfolio path
- HK Brain
- China Brain
- US Prophet feed
- HK Prophet / standouts producer
- CN Prophet live / standouts producer

Produce family-level states for:
- fundamentals
- estimates_revisions
- filings
- news
- government_policy
- insider
- institutional_positioning
- derivatives
- short_positioning
- theme_membership
- macro
- corporate_actions
- credit
- market_microstructure
- alternative_data

Do not fabricate a family merely to fill the matrix.

### Prospective PIT capture

Add append-only prospective capture around already-existing HK and mainland fundamental stores and HK consensus observations.

Preserve current consumer-compatible materialized views where necessary, but ensure subsequent refreshes no longer destroy the historical sequence.

For the first captured observation, do not claim a pre-existing historical available_at that cannot be proven. Mark old/current-source-derived initial state honestly.

Do not reconstruct historical analyst revisions from current consensus. Do not back-project current theme membership.

### Regional equivalence invariants

Encode at minimum:
- HK CCASS participant holding != US 13F beneficial/institutional filing
- southbound flow != 13F
- mainland margin financing != US short interest
- analyst target upside != analyst revision
- CN reversal rev_z != analyst revision z-score
- missing != neutral
- stale != missing
- structurally unavailable != adapter failure

Preserve A/H and other cross-listing identity relationships explicitly.

### Coverage receipt

Emit a shadow DecisionCoverageReceiptV1 for every candidate passing through supported US/HK/China decision/research surfaces.

The receipt may expose:
- fully_evidenced
- reduced_evidence
- price_only
- abstain_due_coverage
- rights_blocked

In this commission these states are **observational only**. They must not:
- change target weights;
- change ADD/HOLD/TRIM/EXIT;
- remove or create a candidate;
- change Prophet promotion;
- alter an entry gate;
- mutate an account;
- alter portfolio settlement.

Where appropriate, surface the receipt through the existing data-quality/read path. Do not duplicate the V3 Decision Snapshot owner.

### Census observability

Make the system census or successor machine report reproducibly show, for current protected source:
- region;
- evidence family;
- producer;
- artifact;
- last successful observation;
- freshness SLA;
- current coverage count;
- historical start;
- PIT grade;
- rights state;
- consumers;
- capability state.

A census generated months before current protected master must visibly fail freshness rather than appear authoritative.

### Global estimates vendor bake-off support

Implement only a provider-neutral sample-evaluation interface and test-fixture format.

Do not sign a contract or purchase data.

The interface must test:
- historical consensus vintage at timestamp T;
- analyst-level or aggregate revision sequence;
- correction lineage;
- actuals;
- source record identity;
- cross-listing identity;
- availability timestamp;
- retention/derived-data rights metadata.

A vendor sample that cannot prove what value was available at historical timestamp T must return PIT_UNPROVEN and be ineligible for historical predictive testing.

### Deterministic-first implementation

The following remain deterministic:
- identity resolution;
- source freshness;
- missingness state;
- rights state;
- PIT admissibility;
- correction generation;
- numeric normalization;
- consensus/revision arithmetic;
- coverage state;
- semantic-equivalence classification from the governed registry.

LLMs may not originate or override those fields. No LLM is required for successful completion.

### Required tests

Include invariant/property tests demonstrating:
- missing observation never becomes 0;
- stale never becomes missing;
- current correction never leaks into an earlier historical snapshot;
- available_at > decision_time makes an observation inadmissible;
- rights_state unknown/blocked excludes that source from an admissible receipt;
- structurally_unavailable remains distinct from missing_expected;
- adapter failure cannot masquerade as neutral evidence;
- A/H identity resolves without collapsing the two listings;
- security identifier changes preserve historical identity;
- current consensus refresh produces a new generation rather than rewriting old state;
- cross-region equivalent types retain their semantic subtype.

Add a portfolio-behavior regression proving that enabling shadow coverage receipts causes **zero difference** in positions, target weights, orders, settlement and current live decision authority.

### Required fixtures

At minimum:
- one US issuer with amended SEC information;
- one HK issuer with current consensus coverage;
- one A/H cross-listed company;
- one mainland security in a limit/suspension or unavailable-style state;
- one deliberately stale source;
- one deliberately missing-expected source;
- one structurally unavailable family;
- one rights-blocked source;
- one corrected observation.

### Acceptance gates

Implementation is acceptable only when:
1. every active US/HK/China candidate processed by instrumented paths gets a coverage receipt, even when most families are missing;
2. every absent expected family has an explicit reason code;
3. no family silently substitutes zero for absence;
4. every historical observation used by a replay has a provable available_at;
5. later corrections preserve earlier generations;
6. current HK/CN fundamental/consensus refreshes begin accumulating prospective vintages;
7. rights state is explicit for every instrumented source;
8. region-specific evidence retains its local semantic type;
9. the census reports current source revision and freshness rather than silently serving a months-old snapshot;
10. portfolio/trading behavior is unchanged under the shadow feature;
11. no new production authority exists;
12. tests and source-law verification evidence are included in the implementation handoff.

### Stop conditions

Stop rather than route around the problem if:
- implementation requires changing portfolio authority;
- implementation requires buying a commercial feed;
- an adapter's rights cannot be resolved;
- an existing canonical owner already owns the same concept;
- historical values can only be obtained by projecting today's state backward;
- an identity join cannot be made reproducibly;
- a source cannot distinguish correction time from event time;
- integration would require a second Decision Snapshot/outcome/control plane.

Record the stop as an explicit limitation.

### Deliverables

Return:
- current source/repository pins;
- collision census;
- contracts/schema documentation;
- equivalence registry;
- existing-source adapters/instrumentation;
- prospective HK/CN PIT capture;
- shadow coverage receipts;
- current regional coverage report;
- automated census freshness output;
- provider-neutral estimates bake-off harness;
- tests and invariant evidence;
- behavior-invariance proof;
- rights/unknowns ledger;
- implementation-to-research traceability matrix.

End with a separate recommendation for whether the next commission should be:
- GLOBAL PIT ESTIMATES VENDOR TRIAL;
- HK REGULATORY/POSITIONING ADAPTERS;
- MAINLAND DISCLOSURE/POSITIONING ADAPTERS;
- or NO FURTHER BUILD.

**Do not promote any source or evidence family to trading authority in this commission.**
