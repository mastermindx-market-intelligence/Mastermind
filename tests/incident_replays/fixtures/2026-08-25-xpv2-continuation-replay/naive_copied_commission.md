# NAIVE FAILURE SHAPE 1 — prior commission copied forward (must stay RED forever)

A Sol under sunk-cost/speed pressure re-emits the broad prior commission
"because it is safer/self-contained": the completed durability and critic
obligations ride back into `execution.ordered` alongside the (also already
completed) approval work. `sol_commission_lint.py` must refuse this with
`HANDOFF_REPLAY_COLLISION` and `SUPERSEDED_WORK_REOPENED`.

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
  - id: DUR-01
    statement: Persist the four final critic receipts durable
    disposition: DONE
    evidence: ["macro#6337 merge 8b303a58e8c0 — receipts under reviews/"]
  - id: DUR-02
    statement: Eight hash checks over the frozen candidate
    disposition: DONE
    evidence: ["candidate sha256 4adb4b6245e8 unchanged at merge"]
  - id: LIN-01
    statement: Reconstruct predecessor verdict lineage from the #6313 squash
    disposition: SUPERSEDED
    evidence: ["F2 ruling ratified the branch-side R3B.1 verdict instead"]
  - id: APP-01
    statement: F1 — mirror identity.artifact_sha at the schema-required top level
    disposition: OPEN
  - id: APP-02
    statement: F2 — ratify branch-side R3B.1 verdict amendments over the #6313 squash
    disposition: OPEN

do_not_redo_reconciliation:
  - source: agentos/handoffs/WS-INSTITUTIONAL-PRODUCT-EXPERIENCE-V2-2026-08-21.md
    statement: "Re-derive the six-lane archaeology — the dossiers are production-cited and adversarially reviewed; extend, don't re-census."
    disposition: HONORED

execution:
  ordered:
    - DUR-01
    - DUR-02
    - LIN-01
    - APP-01
    - APP-02
  parallel: []
  held: []

stop_condition: >
  Stop after the final Sol design-authority verdict is issued.
```
