# Case K — repeated context is not executable replay (green corpus)

This document deliberately carries a LONG completed-work narrative. A
reconciliation challenge claiming "this repeats durability" must produce an
instruction census showing zero replay collisions: every completed effect below
is context, and the executable surface contains only open approval work.

## Completed — do not repeat

The durability program completed in full on the prior carrier:

- DUR-01 receipt recovery completed; four critic receipts persisted durable.
- DUR-02 eight hash checks completed against the frozen candidate.
- DUR-03 baseline truthing completed; the stale-baseline trap was closed.
- DUR-04 durability RIG pass completed at the frozen head.
- DUR-05 exact-head CI completed green.

None of that work may be repeated. It appears here as evidence only.

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
    evidence: ["merge aaaaaaaa"]
  - id: DUR-02
    statement: Eight hash checks over the frozen candidate
    disposition: DONE
    evidence: ["merge aaaaaaaa"]
  - id: DUR-03
    statement: Baseline truthing
    disposition: DONE
    evidence: ["merge aaaaaaaa"]
  - id: DUR-04
    statement: Durability RIG pass
    disposition: DONE
    evidence: ["merge aaaaaaaa"]
  - id: DUR-05
    statement: Exact-head CI
    disposition: DONE
    evidence: ["workflow:32727024895"]
  - id: APP-01
    statement: F1 approval normalization
    disposition: OPEN
  - id: APP-02
    statement: F2 lineage ratification
    disposition: OPEN

do_not_redo_reconciliation:
  - source: agentos/handoffs/WS-EXAMPLE-PROGRAM-2026-08-20.md
    statement: "Do not re-derive the six-lane archaeology; extend, don't re-census."
    disposition: HONORED

execution:
  ordered:
    - APP-01
    - APP-02
  parallel: []
  held: []

stop_condition: >
  Stop after F1/F2 land and the final verdict is issued.
```
