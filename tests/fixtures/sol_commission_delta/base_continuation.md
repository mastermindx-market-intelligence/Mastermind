# Continuation commission — green corpus base (CONTINUATION_DELTA)

Historical evidence and prose may appear anywhere in a commission document.
Only the IDs inside `execution.ordered` / `execution.parallel` are executable
surface; `execution.held` is declared-but-not-executable.

```yaml
schema: mastermind.sol_commission.v1
handoff_mode: CONTINUATION_DELTA

identity:
  program_or_workstream: "WS:EXAMPLE-PROGRAM"
  repository: example-org/example-repo
  carrier:
    type: pull_request
    id: 4242
    branch: claude/example-wave
    pickup_sha: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
    completed_waves: [W1, W2]
  skillpack_sha: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb

sources:
  agentos_workstream:
    path: agentos/workstreams/WS-EXAMPLE-PROGRAM.md
    observed_sha: cccccccccccccccccccccccccccccccccccccccc
  latest_handoff:
    path: agentos/handoffs/WS-EXAMPLE-PROGRAM-2026-08-20.md
    observed_sha: "blob:dddddddddddddddddddddddddddddddddddddddd"
    status: present
  github:
    default_branch_sha: eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee
    carrier_head_sha: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

obligations:
  - id: DUR-01
    statement: Persist four final critic receipts
    disposition: DONE
    evidence:
      - "example-repo#4242 merge aaaaaaaa — receipts durable under reviews/"
  - id: DUR-02
    statement: Reconstruct predecessor verdict lineage from the squash history
    disposition: SUPERSEDED
    evidence:
      - "superseded by DEC:EXAMPLE-LINEAGE-RULING"
  - id: APP-01
    statement: Normalize visual receipt artifact SHA placement
    disposition: OPEN
    evidence:
      - current RIG finding rule_l5
  - id: APP-02
    statement: Ratify branch-side verdict amendments over the older squash
    disposition: OPEN
  - id: APP-R1
    statement: Re-run exact-head CI after approval records change the head
    disposition: REVALIDATE_REQUIRED
    prior_evidence:
      - "workflow:32727024895 green at head aaaaaaaa"
    invalidated_by:
      - approval-record commit changes the exact head
  - id: SUCC-01
    statement: Successor-wave condition work
    disposition: BLOCKED
    blocked_on: explicit Chairman/Sol authorization of the successor wave

do_not_redo_reconciliation:
  - source: agentos/handoffs/WS-EXAMPLE-PROGRAM-2026-08-20.md
    statement: "Do not re-derive the six-lane archaeology; extend, don't re-census."
    disposition: HONORED

execution:
  ordered:
    - APP-01
    - APP-02
    - APP-R1
  parallel: []
  held:
    - SUCC-01

stop_condition: >
  Stop after the approved reference is merged and post-merge verification is green.
```