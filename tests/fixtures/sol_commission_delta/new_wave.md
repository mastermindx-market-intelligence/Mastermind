# New-wave commission — green corpus (NEW_WAVE)

A genuinely new bounded wave: comprehensive context allowed, no prior carrier.

```yaml
schema: mastermind.sol_commission.v1
handoff_mode: NEW_WAVE

identity:
  program_or_workstream: "WS:EXAMPLE-NEW-PROGRAM"
  repository: example-org/example-repo
  carrier:
    type: branch
    branch: claude/example-new-wave
  skillpack_sha: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb

sources:
  github:
    default_branch_sha: eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee

obligations:
  - id: NW-01
    statement: Build the first bounded deliverable of the new wave
    disposition: NEW
  - id: NW-02
    statement: Attack-test the deliverable before returning it
    disposition: NEW

do_not_redo_reconciliation: []

execution:
  ordered:
    - NW-01
    - NW-02
  parallel: []
  held: []

stop_condition: >
  Stop after the deliverable and its attack tests are review-ready; return to Sol.
```
