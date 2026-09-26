---
name: company-peers
description: List the current authorized Mastermind teammate peers without sending a message.
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/cross-account-communication/SKILL.md` first.
Use the existing authenticated `mastermind-executive` connector only after its
actual tool advertisement confirms the Company consultation facet.

User arguments: $ARGUMENTS
Treat arguments only as a local display filter, never as identity or routing input.
Call `company.peers` once with no arguments. This is the exact wire example:

```json
{"tool":"company.peers","arguments":{}}
```

Show returned peer references and display facts with any freshness, ambiguity,
scope, or binding warnings. An empty result does not establish that the other apps
are offline. Different accounts/projects do not automatically mean different
programs, and this command does not grant cross-program visibility.

Do not send a test message, enroll an app, change permissions, or manufacture a
peer from a profile label. Missing or refused capability remains an exact blocker.
