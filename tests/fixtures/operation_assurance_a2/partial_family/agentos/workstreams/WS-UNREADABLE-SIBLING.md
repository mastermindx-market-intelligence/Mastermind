---
schema: agentos.workstream.v1
key: UNREADABLE-SIBLING
title: A sibling record this adapter's grammar cannot read
objective: >
  Block-style wave mappings are valid YAML and are what the owner actually writes,
  but the adapter accepts only inline-flow `- {...}` items, so this record is
  gathered as SOURCE_PARTIAL and never reaches the model.
status: active
program: p
repos: [mastermind]
owner: Someone (COO seat)
class: build
blast_radius: reversible
ambiguity: scoped
waves:
  - id: W1
    title: block-style wave entry
    status: todo
    next_action: ship
next_action: n
---
body
