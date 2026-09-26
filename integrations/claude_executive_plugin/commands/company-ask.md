---
name: company-ask
description: Send one authorized bounded question to a current Mastermind teammate peer.
argument-hint: <peer-ref or unambiguous current peer name> <question>
disable-model-invocation: true
---

Read `${CLAUDE_PLUGIN_ROOT}/skills/cross-account-communication/SKILL.md` first.
Use only the admitted Company facet of the existing `mastermind-executive`
connector. This command does not elevate a COO to CEO or enable held scopes.

User request: $ARGUMENTS
Resolve its recipient against a fresh `company.peers` result. Do not use a supplied
account, session ID, thread, or profile path as routing authority. Refuse ambiguity.
Use the authorized question verbatim where practical, with bounded relevant evidence
and exact artifact revisions. Both lists are required even when empty.

This synthetic example documents the wire shape. Never send the example; substitute
the actual returned peer and authorized content before making the single call:

```json
{"tool":"company.consult","arguments":{"to":"peer-00000000000000000000000000000001","question":"Which exact source revision owns the current interface?","evidence_refs":[],"artifact_revisions":[]}}
```

Report the actual consultation reference, returned state, and any blocker. Creation
is not delivery, recipient ACK, reply, or acceptance. On `EFFECT_UNKNOWN` or a lost
response, preserve the original operation. Do not resend, change accounts, or mint
a replacement. Read the same consultation or recover its identity via the existing
owner; never infer safe absence from a timeout. No repeated polling or idle wake
is started by this command.
