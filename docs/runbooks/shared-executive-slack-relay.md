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

## Separate legacy Mastermind Relay — parked, not retired

The older `Mastermind Agent Relay` Slack app (historical app ID
`A0BUDHZ137A`) displays as **Mastermind Relay** (bot user
`U0BTF3QGABF`). It is **not** the shared Executive Relay bot above.
Its dedicated two-scope manifest at
`config/slack_agent_relay_app_manifest.yaml` is retained as a precise
legacy reference, *not* an instruction to install or use it for new A2
service enrollment.

The October 22, 2026 read-only census found both bots in public
`#agent-dispatch`; no operating post from the separate bot was found in
accessible indexed history. The native M2 A2 and C1 enrollment configs both
named shared bot `U0BT71H4FQE`; neither pointed at the separate bot.
Prior sampling found the legacy bot in additional channels. These results
**do not prove the separate app has no live users**: Slack app-admin token
inventory, Workflow Builder actions, DM/private histories and other-host
sender credentials were not fully attested. Recent bot channel joins are
membership activity, not evidence of an actual dialogue writer.

**Disposition: KEEP INSTALLED; DISCOURAGE NEW DEDICATED ENROLLMENT.**
No unattended remove, token rotation, channel leave or bot substitution is
admitted by this runbook. The A2 native `enroll-shared` remains the normal
path. The legacy `enroll` subcommand now refuses by default *before* TTY
inspection or token consumption. Only a separate deliberate invocation with
`--acknowledge-legacy-dedicated-app` can reach its existing narrow
two-scope, root/TTY/host-disarmed identity-verification ceremony. The flag
**is not** an approval to create another app or to bypass the Executive
lifecycle owner. It applies to `enroll` only; already installed legacy A2
enrollments still use the normal `verify` / `rebind-release` paths and
their original identity/credential. Never reenroll to force convergence.

A later Slack-admin **retirement** must be a separate approved effect, after
all of these are independently evidenced:

1. Inventory the installed app's exact app/bot IDs, token/connection use
   metadata (not token values), OAuth scopes, Workflow Builder/Events/
   webhook/Socket Mode bindings, all relevant channel/DM memberships and
   message use across the available audit window. Reconcile the observed
   October 22 additions to `#github-independent-reviews`,
   `#dotsandgroksecretary` and `#initiatives` with their real inviter
   and consumer.
2. Search authorized live hosts, GitHub organization/repository credential
   *names*, scheduled/CI actions and connected third-party automation owners
   for dedicated-bot writers, including offline hosts that can return later.
   Unknown credential bindings mean **KEEP**, not `no dependency`.
3. Close or migrate every distinct identified consumer under its own owner,
   and prove the shared C1 and A2 identities and real authorized dialogue
   send/read/return path. A source merge, bot membership or healthy daemon
   alone is not a canary.
4. Record the Chairman/Slack-admin disposition and a recovery plan. Only
   then can the authorized Slack admin uninstall the **dedicated** app
   while preserving the shared Executive Relay token and C1/A2 services.
   Recheck the shared path and record the uninstall receipt. A future
   reinstall may create a new token/identity; rollback is not presumed.

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

## Existing A2 enrollment after a release upgrade

For an already-enrolled A2 relay, preserve the token and use the installed
`a2_agent_relay_enrollment.py rebind-release` owner. Do not repeat either
`enroll` ceremony, rewrite the pair by hand, or copy a credential. The core
installer does not publish A2's generation.

This paired C1/A2 upgrade requires the existing shared lock namespace
`/Library/Application Support/MastermindExecutive/locks`: a real root:wheel
directory with mode 0700 and no ACL. The canonical C1 host preparation owner
(`prepare-c1-sol-state-relay.sh`) provisions and checks that namespace. Verify
this prerequisite before stopping A2. A2's initial enrollment preparation does
not provision it, and `rebind-release` refuses a missing or unsafe namespace
without creating or repairing it. Do not rerun enrollment preparation on an
already-enrolled relay or weaken the namespace checks.

After the exact accepted successor is installed, stop/disable A2 through
`service-control.sh stop-agent-relay` and verify its unloaded/disabled state.
Keep production execution disarmed under its existing owner. From the exact
installed `RELEASE_ROOT`, with the pinned Executive Python, run:

```text
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -I -S -B \
  ops/executive_os/a2_agent_relay_enrollment.py \
  rebind-release --expected-bot-user-id U0BT71H4FQE
```

The verb requires a coherent complete old generation. Under a private root
flock it attests the existing token's metadata without reading its bytes,
validates the old canonical config/plist, and replaces only their release
binding. With no flag, the existing admitted scope set and stored `w3c_enabled`
boolean are preserved; there is no policy override or provider call. An
already-current pair is a no-write success. Missing, mixed, unsafe or concurrently changed
artifacts fail closed. A failed publication restores only identities still
owned by that operation. `A2_REBIND_EFFECT_UNCERTAIN` or
`A2_REBIND_MIXED_GENERATION` requires same-carrier reconciliation; do not retry,
reenroll or start the relay to force convergence.

Each forward and rollback publication re-attests the staged name and held file
descriptor against the metadata sealed after writing, after all ACL and
destination checks. Lost staging identity stops further publication and
rollback; cleanup unlinks only the staged inode still owned by the operation.

If the relay becomes loaded during publication, rollback permission is lost.
Read-only identity reconciliation still distinguishes an operation-owned pair
that was not restored (`A2_REBIND_MIXED_GENERATION`) from changed or unprovable
identities (`A2_REBIND_EFFECT_UNCERTAIN`); neither permits another write.

For the separately admitted native-return phase, the existing rebind owner has
an explicit `rebind-release --enable-w3c` selection. Keep the relay disabled and
unloaded, and use the same expected bot and installed release. That opt-in
changes only the release binding and the stored W3C boolean to true, retaining
the exact bot, scope set and credential inode without reading or copying its
bytes. A false enrollment at the same release must converge to true; only an
already-current true pair is a no-write success. Omitting the flag preserves
both false and true states. It never disables a true enrollment, starts a
service, authorizes a Runtime writer or proves native delivery. The same file
CAS, rollback and uncertain-effect rules apply. Do not reenroll or modify the
pair manually to enable W3C.

After a successful rebind, use the installed `verify` with the expected bot.
Supply `--enable-w3c` when the rebound enrollment has W3C enabled; an ordinary
no-flag rebind of a false enrollment remains false. The verification requalifies the existing
Slack identity/history and exact release. Then use the separate installed
`start-agent-relay` owner after its ordinary admission gates, including the
existing logs/socket-parent prerequisites, and read back health. Rebinding
neither starts services nor proves reboot persistence.
