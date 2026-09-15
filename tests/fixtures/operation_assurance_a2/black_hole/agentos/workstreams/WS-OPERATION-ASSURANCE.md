---
schema: agentos.workstream.v1
key: OPERATION-ASSURANCE
title: Synthetic organizational black hole for the OLS-A2 no-progress detection fixture
objective: >
  A synthetic workstream authoring exactly one wave with no depends_on, no wait, and no
  next_action — the organizational analogue of a NO_PROGRESS state the OLS-A2 compiler must
  detect as a real witness, per design Section 5.
status: active
program: cross-repo-contract-governance
repos: [mastermind]
owner: Fable principal (COO seat)
class: build
blast_radius: reversible
ambiguity: scoped
waves:
  - {id: R0, title: "Recover canonical truth", status: done, pr: 279}
  - {id: STUCK, title: "Orphaned wave with no dependency, wait, or next_action", status: in_progress}
  - {id: DOWNSTREAM, title: "Depends on STUCK, so its required start transition is permanently dead", status: todo, depends_on: [STUCK], next_action: "Start once STUCK resolves — it never does, on purpose"}
next_action: >
  This is a synthetic fixture; the workstream owner has not authored a next_action for the
  STUCK wave, which is the point of the fixture. DOWNSTREAM exists so the resulting
  NO_DEAD_REQUIRED_TRANSITION witness carries a non-empty source_refs pointing back at this
  exact record (a witness at the very first, zero-transition state carries no transition to
  attribute — see the OLS-A2 packet DEVIATIONS for why DOWNSTREAM is needed).
do_not_redo:
  - "Do not delete this fixture; it is the OLS-A2 organizational-black-hole negative case."
landmines:
  - "Do not add a next_action, depends_on, or wait to the STUCK wave; that would defeat the fixture."
---

# Synthetic black-hole fixture

Test-only record. The STUCK wave has no way forward: no dependency to satisfy, no external gate
or intentional wait, and no declared next_action. The OLS-A2 compiler maps this to a wave state
variable with zero outgoing transitions, so the operation can never reach its terminal outcome —
a real, source-attributed witness, not an invented one.
