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

1. Install the exact accepted Mastermind release containing both the shared-relay
   source and the reviewed C1 release-rebind owner. The standard Executive
   installer deliberately leaves C1/control services stopped; it does not
   rewrite an already-enrolled C1 relay plist or config.

   Let `RELEASE_ROOT` denote the installer-verified
   `/Library/Application Support/MastermindExecutive/releases/<accepted-sha>`.
   Every native command below must execute from that exact installed release
   with the pinned Executive Python; never run the ceremony from an operator
   source checkout.

2. **Before changing Slack scopes or starting C1**, keep Executive control and
   the C1 relay unloaded and keep the relay explicitly disabled. Rebind the
   coherent existing C1 enrollment to the exact installed release:

```text
cd "$RELEASE_ROOT"
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -I -S -B \
  ops/executive_os/c1_relay_enrollment.py \
  rebind-release \
  --expected-bot-user-id U0BT71H4FQE
```

`rebind-release` validates the old plist/config as one coherent enrolled
generation, stages the exact installed-release plist/config pair, preserves and
attests the existing credential without outputting or rewriting it, and
converges the two files transactionally.

A mixed or uncertain outcome is a hard stop. Reconcile the same carrier and do
not start either relay.

3. Slack admin edits the **existing Mastermind Executive Relay app** only:
   add bot scope `channels:history`, preserve `chat:write` and
   `groups:history`, then reinstall/approve the app in the existing workspace.
   Do not create another app and do not remove a Dot app.

4. Confirm the existing bot remains a member of both channels above.

5. While C1 remains disabled/unloaded, verify its rebound enrollment against the
   post-migration Slack identity:

```text
cd "$RELEASE_ROOT"
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -I -S -B \
  ops/executive_os/c1_relay_enrollment.py \
  verify \
  --expected-bot-user-id U0BT71H4FQE
```

This verification must prove the same workspace/bot, the exact shared
three-scope set, and `#sol-runtime` history access before the C1 lifecycle is
resumed. The existing C1 read-side/control lifecycle remains its own owner; this
runbook does not grant start authority.

6. On the native Executive host, with A2 still disabled/unloaded, run:

```text
cd "$RELEASE_ROOT"
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -I -S -B \
  ops/executive_os/a2_agent_relay_enrollment.py \
  enroll-shared \
  --expected-bot-user-id U0BT71H4FQE \
  --enable-w3c
```

`enroll-shared` reads the already-enrolled C1 credential locally from its
attested private file, proves the same bot identity, proves the exact shared
three-scope set, proves `#agent-dispatch` history access, and writes the normal
A2 private token/config/plist files. No Slack token is copied into chat, argv,
Slack, GitHub, logs, or a model-visible surface.

7. Run the normal A2 `verify --enable-w3c`. Resume the existing reviewed C1
   read-side/control lifecycle and the separate `start-agent-relay` lifecycle
   only after each owner's normal release/admission gates.

Neither verification is permission to start the other service.

## Migration compatibility

Before A2 is enrolled, C1 accepts either the legacy exact two-scope set
`chat:write + groups:history` or the shared exact three-scope set above. It
accepts no other widening. A2 shared enrollment requires the three-scope set
exactly, so dialogue cannot activate before the Slack admin scope migration.

The two services receive separate local copies of the same Slack bot credential
under their existing owner/mode boundaries. This is credential reuse inside the
native host, not a second Slack credential or a new credential authority.
