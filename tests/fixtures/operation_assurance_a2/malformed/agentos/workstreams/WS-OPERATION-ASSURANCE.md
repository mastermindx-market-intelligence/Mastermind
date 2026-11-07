---
schema: agentos.workstream.v1
key: OPERATION-ASSURANCE
title: Malformed fixture — status enum value is not recognized
objective: This record's status field carries a value outside the closed enum, on purpose.
status: not_a_real_status
program: cross-repo-contract-governance
repos: [mastermind]
owner: Fable principal (COO seat)
class: build
blast_radius: reversible
ambiguity: scoped
waves:
  - {id: R0, title: "Recover canonical truth", status: done}
next_action: This fixture exists only to exercise SOURCE_PARTIAL on a schema-invalid status value.
---

# Malformed fixture

Test-only record with an unrecognized `status` value.
