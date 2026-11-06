---
name: mastermind-craft
description: Apply focused Mastermind role methods to a bounded assignment, or compile a complete worker brief. Use for orchestration, product design, frontend or backend implementation, primary-source research, data-science evaluation, adversarial review, and real-path verification. Select one role and load only its playbook. This complements existing Sol and Operator procedures; it does not install tools, grant permissions, start workers, or replace current source law.
---

# Mastermind Craft

Read `references/common.md`, then exactly the playbook matching the assigned work:

| Role | Read |
|---|---|
| Orchestrator | `references/orchestrator.md` |
| Product designer | `references/designer.md` |
| Frontend engineer | `references/frontend.md` |
| Backend/data engineer | `references/backend.md` |
| Research analyst | `references/researcher.md` |
| Data scientist | `references/data-scientist.md` |
| Adversarial reviewer | `references/reviewer.md` |
| Production verifier | `references/verifier.md` |

Keep the assignment narrow; these are methods, not eight agents to launch. Apply the
current protected Sol/Operator procedure before any company action. Do not infer
that a tool exists because a playbook names its capability.

For a handoff, read `references/brief-format.md`. Run the dependency-free compiler
only on non-secret authoring input:

```sh
python3 scripts/brief.py compile /path/to/brief.json --format markdown
```

The compiler writes only to standard output. It loads the common method and one
selected playbook, checks briefing completeness, and emits an explicitly
non-authoritative document. It never launches a worker, connects to an app, writes
a provider configuration, or certifies readiness. A compiled prompt is not an
installed Skill or an attested capability generation.

When code execution is unavailable, follow the same brief format manually and say
that the compiler did not run. Never fabricate its hashes or checks.

For native adoption, read `references/adoption.md`. Use the existing capability
registry and HF1 adapter owners. Do not inject this package into an exact four-Skill
canary or a sealed provider home without separate reviewed admission.

Return the actual artifact or result, material uncertainty, proof scope, and exact
next action. Do not substitute an audit, a plan, or a test count for the assigned
user or machine capability.
