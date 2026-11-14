---
schema: agentos.workstream.v1
key: OPERATION-ASSURANCE
title: Synthetic external-gate/wait fixture
objective: >
  A synthetic workstream authoring one wave with a schema-valid wait mapping, to exercise the
  design Section 5 "schema-valid wait object -> typed external gate / intentional wait" mapping.
  No live agentos record uses a wait field today; this fixture is synthetic-only (see DEVIATIONS).
status: active
program: cross-repo-contract-governance
repos: [mastermind]
owner: Fable principal (COO seat)
class: build
blast_radius: reversible
ambiguity: scoped
waves:
  - {id: R0, title: "Recover canonical truth", status: done}
  - {id: GATED, title: "Waits on an external Sol acceptance gate", status: in_progress, wait: {kind: EXTERNAL_GATE, condition: "Sol acceptance"}}
next_action: This fixture exists only to exercise the wait-mapping compiler path.
---

# Synthetic wait/gate fixture
