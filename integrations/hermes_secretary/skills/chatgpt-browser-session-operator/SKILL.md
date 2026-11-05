---
name: chatgpt-browser-session-operator
description: Tend ChatGPT browser sessions with paste-only nudges.
version: 2026.10.25
author: Chris Wong
license: LicenseRef-Mastermind-Internal
platforms: [macos]
metadata:
  hermes:
    tags: [secretary, chatgpt, browser, shadow]
    category: productivity
    related_skills: [mastermind-context, mastermind-fabric-secretary-local]
---

# ChatGPT Browser Session Operator Skill

Ports the Grok Secretary playbook for long-running ChatGPT Pro and Extra High browser sessions. The dated incident log is kept verbatim in `references/grok-secretary-source.md`. This file is the operative procedure. Standing guards here win when an older lesson disagrees, including any lesson that says to click Always allow.

This skill does not drive a browser. AppleScript, Peekaboo, Multilogin, and the `~/gwcap` helpers are not bundled. See `UNPORTED.md`.

## When to Use

Use on the `:05` and `:35` session watcher, or when a registered session is stalled, finished, aging, or waiting on a permission card. Do not use it to open Chris's own chats or `do_not_steer` chats.

## Prerequisites

- The session registry is the single source of truth for chain heads, replacements, and archives.
- Owed-return state comes from the owed-returns ledger. Open rows are the only rows that match.
- Input is paste-only. Approval cards use `Allow <tool> for this conversation` and no wider scope.
- A macOS computer-use grant on m2studio is required before any click. This package does not have that grant.

## How to Run

Service owed returns first, then the six oldest-checked registry rows. Record the decision. Do not post it to Slack from shadow mode.

## Quick Reference

- Running chat: leave it alone. Never message a running Pro chat.
- Finished: record an extract, set `returned_pending`, hand off `ACTION NEEDED RETURN`.
- Refusal: keep the text verbatim, never retry it, never replay it.
- Stalled: recover at most once per 30 minutes.
- Aging: 2 hours for Extra High, 6 hours for Pro, then `stalled_pending` and a handoff.
- Waiting on CI or review: do not force a nudge.
- Same chat: do not nudge again within 30 minutes.
- One ChatGPT tab per profile. Never open a chat in a new tab or by URL.
- Continue prompts are 1–3 sentences, pasted, not typed.

## Procedure

1. Read the owed-returns ledger before any other session.
2. Skip `chris_own` and `do_not_steer` rows without a nudge, archive, or card click.
3. For a finished row, record the last answer and its sha256 in the shadow decision. Do not write `~/gwcap` from this package.
4. For a refusal, store the exact text. A later prompt that repeats or paraphrases it is refused.
5. For a stall, recover once, then wait 30 minutes.
6. For aging past the tier threshold, set `stalled_pending` and hand off. Do not keep nudging.
7. Permission cards: open the Allow menu and choose `Allow <tool> for this conversation`. If that item is absent, stop. Do not choose Always allow or Allow once.
8. Blocker ladder, in order: ask the chat to decide; get fresh eyes from a Dot; delegate one Fabric task under the Fabric skill; hand off to a local Codex or Cursor session. Do not self-approve or merge.
9. Use Extra High for short or write-heavy work and Pro for big work. Business accounts have about 50 Pro turns a week.
10. Pace like a casual user. Rotate across chats. Keep one ChatGPT tab per profile, plus a Tencent console tab or a genuine mid-login tab.

## Pitfalls

- The verbatim lesson log still contains an older "Always allow" instruction. It is historical. The guard refuses it.
- A debugging-this-browser banner means skip that profile's tab sweep.
- Synthetic keypresses and speed-typing are refused. Paste, then stop if the frontmost window changed.
- Do not clear cookies. Do not call in-page `/backend-api`. Do not scrape tokens.

## Verification

The session decider and the standing-rule guards are covered by the offline tests in this package. A green test run is not proof that a Mac click happened.
