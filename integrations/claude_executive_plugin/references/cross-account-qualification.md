# Claude cross-account client qualification

Status: BUILT_NOT_PROVEN / source extension. Native matrix: NOT_RUN.
This document is an acceptance contract, not runtime state or an enrollment registry.

## Current host discovery — 2026-09-26

The four recently active isolated profile labels are Claude 2, Claude 3, Claude 5,
and Claude 6. These labels are not account identifiers or authorization claims.
All observed processes run under the same OS user on the M2 host.

- Claude 2: Desktop 2.7032.0, Claude Code 2.1.280; sampled launch denies
  `SubscribePR`, not `SendMessage`.
- Claude 3: Desktop 1.46388.4, Claude Code 2.1.260; sampled launch contains
  `--disallowedTools SendMessage`.
- Claude 5: Desktop 1.46388.4, Claude Code 2.1.260; sampled launch contains
  `--disallowedTools SendMessage`.
- Claude 6: Desktop 1.46388.4, Claude Code 2.1.260; sampled launch contains
  `--disallowedTools SendMessage`.

Anthropic's current native contract uses `ListAgents` + `SendMessage` for
same-machine Claude Code sessions. macOS requires v2.1.224 or later; delivery is
through a per-session local inbox and is independent of project identity when the
sessions can see the same per-user registration files. The Desktop app-local
session surface is narrower and only sees sessions that the same Desktop app runs.

Therefore the first native remediation is to upgrade or relaunch Claude 3/5/6 on
an accepted current Desktop runtime that does not suppress `SendMessage`, then
prove cross-profile `/list-agents` visibility before changing Company transport.
Do not patch live processes, write raw sockets, or copy messaging tokens.
Shared peer-file/socket visibility across these Parall profiles remains NOT_RUN:
two read-only host probes were refused before dispatch, so no result is inferred.


## Composition and ownership

Extend the existing `mastermind-executive` Claude plugin from #962; do not install
this partial directory as a second plugin. Its manifest uses the default commands
and skills directories, so these files compose without changing its owned files.
The release owner must reconcile/bump that plugin's version at integrated release;
this extension does not overwrite its manifest, README, or orchestration skill.

Consume the existing Company facet only after role-correct authenticated exposure
is accepted. #955 owns the Claude authenticated transport; its COO enrollment hold
and #633's unresolved DCR effect must remain intact. Do not grant CEO scopes to a
COO or create another OAuth client, token store, MCP registration, relay, or hook.
#1001 owns targeted physical carriage; its tests are not native app proof.
Existing runtime identity/peer adapters remain separately owned. This extension
cannot attest app identity, enable a disabled endpoint, or widen peer policy.

Required gates: integrated source acceptance, exact-head CI and independent review;
role-correct authentication; trusted current account/session binding; exact target
and reply carriage; advertised Wake acknowledgement and requester consumption.
Source tests alone close none of the last five production gates.

## Native proof matrix

A1 through A4 are temporary test aliases, not account identifiers. Resolve all four
actual native app profiles and current sessions from accepted owners before testing.
Do not derive identity from an app title, arbitrary environment value, or directory.
Each row requires a unique harmless nonce question and correlated answer, exact
canonical references, receiver ACK, requester consumption, and no duplicate effect.
Do not place credentials, full transcripts, or private account names in evidence.

| Initiator -> recipient | Qualification |
| --- | --- |
| A1 -> A2 | NOT_RUN |
| A1 -> A3 | NOT_RUN |
| A1 -> A4 | NOT_RUN |
| A2 -> A1 | NOT_RUN |
| A2 -> A3 | NOT_RUN |
| A2 -> A4 | NOT_RUN |
| A3 -> A1 | NOT_RUN |
| A3 -> A2 | NOT_RUN |
| A3 -> A4 | NOT_RUN |
| A4 -> A1 | NOT_RUN |
| A4 -> A2 | NOT_RUN |
| A4 -> A3 | NOT_RUN |

This matrix is deliberately not marked PASS by automated fixture tests.

## Required negative and continuity journeys

- Same-program cross-project peers must work; unauthorized cross-program peers
  must remain hidden/refused. A missing peer is not proof an app is offline.
- A disabled endpoint, stale binding, nonparty read, ambiguous target, or missing
  acknowledgement must fail before an unauthorized packet or answer is committed.
- App/session restart and account/session succession must preserve an admitted
  consultation's original target. A new question uses only a freshly resolved peer.
- A lost response / EFFECT_UNKNOWN must reconcile the original operation with
  no new question, new carrier, automatic retry, or silent provider/account switch.
- Busy, idle, paused, and closed native sessions need separate receipts. Notification
  delivery alone is not target consumption or proof an idle session resumes.
- Malicious message text must not approve permissions, execute shell commands,
  create a worker, or enlarge the receiver's commissioned scope.

Keep resulting evidence in the existing Runtime/Wake/GitHub owners, not this table
as a new live status store. Record exact release SHA, native versions, opaque
bindings, consultation refs, and observed effects. Claim four-account operation
only after the actual native journeys pass. No real account message was sent by
this source extension, and no new authentication, listener, or watcher is created.

## Source check and usage after accepted integration

Run `python3 -m pytest tests/test_claude_cross_account_plugin.py` in the integrated
source. Tests validate the shipped examples against the real Company schema and
check consumer boundary text. They do not measure model obedience or native loading.
After a separately accepted release/install, commands are namespaced under the
incumbent plugin: `/mastermind-executive:company-peers`, `:company-ask`,
`:company-read`, and `:company-reply`. Send commands require deliberate invocation;
the main skill can use already-authorized consultation tools within an admitted
mission without manufacturing a new human approval for each routine message.

Primary reference: https://code.claude.com/docs/en/plugins-reference
Desktop scope: https://code.claude.com/docs/en/desktop
Native CLI messaging: https://code.claude.com/docs/en/cross-session-messaging
