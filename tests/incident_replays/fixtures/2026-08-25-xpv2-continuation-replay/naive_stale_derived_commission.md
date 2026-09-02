# NAIVE FAILURE SHAPE 2 — lawfully derived from stale records (the harder one; must stay RED forever)

This is the C2' shape: the author did everything the pre-amendment procedure
asked. They read the CURRENT workstream record (repaired hours earlier by
#6388), found R3B.2 `in_progress` with a precise next_action, and derived a
clean-looking delta: resolve F1/F2, re-run gates, issue the final verdict,
surface the five conditions as open work. Every one of those effects had
already completed inside merged #6337.

No disposition in THIS manifest is self-contradictory — the replay is only
visible against the repaired organizational do_not_redo set. Linted with
`current_context_bundle.json`, this must fail `DNR_COVERAGE_MISSING` (none of
the seven current binding statements is reconciled).

```yaml
schema: mastermind.sol_commission.v1
handoff_mode: CONTINUATION_DELTA

identity:
  program_or_workstream: "WS:INSTITUTIONAL-PRODUCT-EXPERIENCE-V2"
  repository: mastermindx-market-intelligence/macro
  carrier:
    type: pull_request
    id: 6337
    branch: claude/xpv2-sector-r3b-2
    pickup_sha: 90ce21ac977209370b57b2ef1af7331cebb25861
  skillpack_sha: 51f9942733b86e550bb9169d2a43462bd28e774f

sources:
  agentos_workstream:
    path: agentos/workstreams/WS-INSTITUTIONAL-PRODUCT-EXPERIENCE-V2.md
    observed_sha: "blob:0000000000000000000000000000000000000000"
  latest_handoff:
    path: agentos/handoffs/WS-INSTITUTIONAL-PRODUCT-EXPERIENCE-V2-2026-08-21.md
    observed_sha: "blob:1111111111111111111111111111111111111111"
    status: present
  github:
    default_branch_sha: 15ce6525dd6447e7c0625bb24a1190b43cb9f86f
    carrier_head_sha: 90ce21ac977209370b57b2ef1af7331cebb25861

obligations:
  - id: F1
    statement: Normalize the Visual/Taste receipt by mirroring identity.artifact_sha at the schema-required top level
    disposition: OPEN
    evidence: ["workstream R3B.2 next_action (observed at pickup)"]
  - id: F2
    statement: Ratify that the branch-side R3B.1 verdict amendments supersede the older #6313 squash
    disposition: OPEN
    evidence: ["workstream R3B.2 next_action (observed at pickup)"]
  - id: GATES-R1
    statement: Re-run RIG + exact-head hosted CI on the resulting head
    disposition: REVALIDATE_REQUIRED
    prior_evidence: ["workflow:32727024895 green at head 90ce21ac"]
    invalidated_by: ["F1/F2 conflict resolution will change the exact head"]
  - id: VERDICT-01
    statement: Issue the final Sol design-authority verdict
    disposition: OPEN
  - id: COND-01
    statement: Address colour-field legibility measurement (heatmap)
    disposition: OPEN
  - id: COND-02
    statement: Address auth/premium access representation follow-through
    disposition: OPEN

do_not_redo_reconciliation:
  - source: agentos/handoffs/WS-INSTITUTIONAL-PRODUCT-EXPERIENCE-V2-2026-08-21.md
    statement: "Re-derive the six-lane archaeology — the dossiers are production-cited and adversarially reviewed; extend, don't re-census."
    disposition: HONORED
  - source: agentos/handoffs/WS-INSTITUTIONAL-PRODUCT-EXPERIENCE-V2-2026-08-21.md
    statement: "Treat the R2 candidate HTML as source authority (authority precedence is frozen in the pack README)."
    disposition: HONORED

execution:
  ordered:
    - F1
    - F2
    - GATES-R1
    - VERDICT-01
  parallel:
    - COND-01
    - COND-02
  held: []

stop_condition: >
  Stop after the final Sol design-authority verdict is issued and recorded.
```
