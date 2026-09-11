---
schema: agentos.workstream.v1
key: OPERATION-ASSURANCE
title: Probe-p10-shaped fixture — a wave already ACTIVE despite declaring depends_on
objective: >
  A wave whose own status is already in_progress (ACTIVE) while it also declares
  depends_on — the record's own status is authoritative for CURRENT position; the
  start-via-dependency transition must never be authored as required_reachable=True
  from a PENDING guard when the initial marking is never PENDING (repair FIX 1).
status: active
program: cross-repo-contract-governance
repos: [mastermind]
owner: Fable principal (COO seat)
class: build
blast_radius: reversible
ambiguity: scoped
waves:
  - {id: W1, title: "Already done", status: done}
  - {id: W2, title: "Already active despite depends_on: [W1]", status: in_progress, depends_on: [W1], next_action: "go"}
next_action: This fixture exists only to exercise FIX 1 (no false NO_DEAD_REQUIRED_TRANSITION).
---

# Probe-p10-shaped fixture
