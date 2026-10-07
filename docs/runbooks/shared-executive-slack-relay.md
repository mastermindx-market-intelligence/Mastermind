# Shared Executive Slack Relay migration

## Purpose

Use the already-installed **Mastermind Executive Relay** Slack app for both
existing C1 `MMX/SOL_STATE_V1` publication and A2 Agent Dialogue transport.
This is a Slack-app-capacity consolidation only. Executive OS remains lifecycle
authority, Agent OS remains organizational continuity, and the C1/A2 local
service principals, channel allowlists, schemas, sockets, and effect fences stay
separate.

## Fixed Slack contract

Workspace: `T0BRD2AQXQV`

Existing bot identity: action-time verified bot user currently observed as
`U0BT71H4FQE` (`Mastermind Executive Relay`).

Allowed bot scopes after migration are exactly:

```text
channels:history
chat:write
groups:history
```

Channels remain role-separated:

```text
#sol-runtime    C0BSGABKBFY  -> C1 state publication / private history
#agent-dispatch C0BSBM78V1N  -> A2 dialogue transport / public history
```

No Socket Mode, Events API subscription, incoming webhook, slash command,
interactivity surface, user OAuth scope, `chat:write.public`, `channels:read`,
or workspace-wide channel-management scope is introduced by this migration.

## Safe sequencing

1. Install a Mastermind release containing the shared-relay source.
2. Slack admin edits the **existing Mastermind Executive Relay app** only:
   add bot scope `channels:history`, preserve `chat:write` and
   `groups:history`, then reinstall/approve the app in the existing workspace.
   Do not create another app and do not remove a Dot app.
3. Confirm the existing bot remains a member of both channels above.
4. On the native Executive host, with A2 still disabled/unloaded, run:

```text
python3 ops/executive_os/a2_agent_relay_enrollment.py \
  enroll-shared \
  --expected-bot-user-id U0BT71H4FQE \
  --enable-w3c
```

`enroll-shared` reads the already-enrolled C1 credential locally from its
attested private file, proves the same bot identity, proves the exact shared
three-scope set, proves `#agent-dispatch` history access, and writes the normal
A2 private token/config/plist files. No Slack token is copied into chat, argv,
Slack, GitHub, logs, or a model-visible surface.

5. Run the normal A2 `verify --enable-w3c`, then the existing reviewed
   `start-agent-relay` lifecycle only after its normal release/admission gates.

## Migration compatibility

Before A2 is enrolled, C1 accepts either the legacy exact two-scope set
`chat:write + groups:history` or the shared exact three-scope set above. It
accepts no other widening. A2 shared enrollment requires the three-scope set
exactly, so dialogue cannot activate before the Slack admin scope migration.

The two services receive separate local copies of the same Slack bot credential
under their existing owner/mode boundaries. This is credential reuse inside the
native host, not a second Slack credential or a new credential authority.
