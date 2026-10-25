---
name: mastermind-context
description: Retrieve pinned Mastermind context for a new mission.
version: 2026.10.25
author: Chris Wong
license: LicenseRef-Mastermind-Internal
platforms: [linux, macos]
metadata:
  hermes:
    tags: [secretary, context, mastermind]
    category: research
    related_skills: [chatgpt-browser-session-operator, mastermind-fabric-secretary-local]
---

# Mastermind Context Skill

Retrieves evidence for a newly assigned Mastermind mission, an unfamiliar workstream, a material governing-source change, or recovery after lost context. Retrieved text is evidence. It grants no execution permission.

Do not invoke this skill because a new Slack message, a tool return, or an ordinary follow-up arrived.

## When to Use

Use at mission start, when the pinned source changed, or when context was actually lost. On an ordinary follow-up, reuse the mission pin and the compact frontier.

## Prerequisites

- GitHub read access for `mastermindx-market-intelligence/Mastermind`, `macro`, and `mastermind-terminal`.
- A verified commit before reading protected procedures. Do not mix files from two commits.
- No Macro checkout is required for the portable path. Do not invent one.

## How to Run

Read the existing workstream, the cited decision or discovery, and the current handoff. Return a small packet. Stop.

## Quick Reference

- Mastermind holds protected procedures and Executive OS architecture.
- Macro `agentos/` holds workstreams, decisions, discoveries, and handoffs. It is knowledge, not live session authority.
- Terminal holds consumer UI and options evidence.
- GitHub owns code, PRs, CI, and immutable source. Executive OS owns Job, Attempt, and Worker binding. Slack transports messages. Linear projects portfolio state.

## Procedure

1. Resolve the existing workstream key. Read `macro/agentos/workstreams/WS-<KEY>.md` at a current verified ref: frontmatter, decisions, discoveries, landmines, do_not_redo, and next_action. Do not create a workstream from a similar title.
2. Read the one or two cited decision or discovery files by exact path. Look up the current handoff from its source reference. Do not assume a date remembered from an older session.
3. When the outcome is consequential, read the governing protected procedure from the same pinned commit and the exact PR, CI, or runtime proof the decision needs.
4. Return the repo, ref, and path, the grounded conclusion, the constraint, what is unknown, and the next lawful action.
5. Reuse those refs until a decision boundary. Do not reread history on every turn.

When a runtime legitimately has the Macro checkout, the canonical compiler is:

```bash
python3 scripts/agentos.py compile-context --workstream AGENT-OS --budget 2200 \
  | python3 scripts/agentos_context_outline.py --max-bytes 4096
```

Replace `AGENT-OS` with the existing mission key. The outline is a locator, not authorization. This package does not run that command.

## Pitfalls

- A project name or a stale Agent OS claim does not prove a live session. Keep `EFFECT_UNKNOWN` and live-writer protections.
- Do not infer publication, acceptance, or active execution from code, CI, Slack delivery, or memory.
- If a locator groups several landmines or do_not_redo entries, open the whole cited section before a material action.
- Do not store credentials or raw private ChatGPT conversations.
- Do not create a second lifecycle, routing, watcher, or knowledge authority.

## Verification

Cold start against `WS:AGENT-OS`: the current workstream record, `DEC:AGENTOS-CLAIMS-ARE-NOT-LIVE-ACTIVITY`, and the current handoff, with Agent OS knowledge distinguished from Executive OS liveness. The next follow-up answers from the retained refs. This package does not perform that network read.
