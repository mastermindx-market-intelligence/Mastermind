# Shared Executive Slack Relay consolidation

**Date:** 2026-10-06
**Status:** CURRENT SOURCE AMENDMENT / SOURCE IMPLEMENTATION; PRODUCTION EFFECT SEPARATE
**Chairman intent:** use existing Slack capacity instead of consuming another app slot for Agent Relay
**Protected basis:** Mastermind `7c12c394b38f52cf6bfc953379535eb2c7a496f2`, Skillpack `mastermind.sol_skillpack.v1` 1.0.1

## Ruling

The current Slack workspace cannot spend another app slot on a dedicated
Mastermind Agent Relay because those slots are intentionally reserved for the
Dot estate. For the current Executive Autonomy / parenting-loop path, the older
requirement that C1 Executive Relay and A2 Agent Relay use different Slack apps
and different bot tokens is superseded.

The accepted shape is now:

```text
one existing Mastermind Executive Relay Slack app + one Slack bot credential
  -> #sol-runtime: C1 state publication
  -> #agent-dispatch: A2 Agent Dialogue transport

separate native service principals, configs, sockets, schemas, channel allowlists
and Executive/Dialogue effect owners remain unchanged
```

This is not a merger of C1 and A2 lifecycle authority. Slack identity remains
transport provenance only. Executive OS still owns Job/Attempt/Worker/Event
lifecycle; RuntimeBinding/SessionTarget owns the exact execution surface;
Agent Dialogue / Wake owns attention and continuation semantics.

## Current observed identity and channels

At the commissioning read, the existing `Mastermind Executive Relay` bot user
is `U0BT71H4FQE`. It is already a member of both:

- private `#sol-runtime` — `C0BSGABKBFY`;
- public `#agent-dispatch` — `C0BSBM78V1N`.

The action-time enrollment must still verify the actual current bot user ID; the
observed ID above is not permission to skip native verification.

## Exact Slack scope union

The shared app's accepted bot scope set is exactly:

```text
channels:history
chat:write
groups:history
```

This is the union of the existing C1 private-channel state needs and the A2
public-channel dialogue needs. No other scope is authorized by this amendment.

C1 accepts its legacy exact set (`chat:write`, `groups:history`) during the
migration window so the existing state publisher is not broken before the Slack
admin reinstall. It also accepts the exact shared three-scope set. A2 admission
requires the shared three-scope set exactly. Therefore the app scope migration
is mechanically required before A2 can enroll or activate.

## Credential handling

Do not ask the Chairman to retrieve or paste the existing Executive Relay bot
token. The new native `enroll-shared` A2 operation consumes the already-enrolled
C1 credential from its attested native secret file, verifies the same bot
identity + exact shared scopes + `#agent-dispatch` history access, then creates
the normal A2 service-private credential/config/plist under the existing
A2 service-owner boundary.

The secret never passes through ChatGPT, Slack, GitHub, argv, logs, receipts or
model-visible state. C1 and A2 keep separate local service-private copies so
neither non-root service principal is granted filesystem access to the other's
credential file.

## Human gate reduced to one UI action

No new Slack app is created. No Dot app is removed.

After source installation, the Slack workspace admin only needs to edit the
existing Mastermind Executive Relay app, add `channels:history` while preserving
`chat:write` + `groups:history`, and reinstall/approve that existing app.
Channel membership is then re-read; no new bot invitation is expected because
the existing bot is already present in both channels.

The exact native sequence is in `docs/runbooks/shared-executive-slack-relay.md`.

## Supersession

For this current execution path, this amendment supersedes the narrower
"different apps/tokens" and "do not reuse Executive Relay" requirements in:

- `research/AGENT_RELAY_SLACK_APP_ADMIN_CEREMONY_2026-08-27.md`;
- `research/MASTERMIND_ACTIVE_SESSION_EXECUTIVE_DIALOGUE_F0_ARCHITECTURE_AND_FABLE01_COMMISSION_2026-08-22.md`;
- the dedicated-app wording in `research/EXECUTIVE_OS_PERSONAL_PRO_C1_SOL_STATE_PRODUCTION_IMPLEMENTATION_COMMISSION_2026-08-25.md`.

All other authority, channel, runtime, effect, proof and least-privilege
boundaries in those records remain in force.

## Acceptance

Source acceptance requires:

1. C1 continues to accept the old exact scope set and the exact shared scope set,
   while refusing any other missing/extra scope set.
2. A2 `enroll-shared` needs no stdin token and reuses only the current C1 bot
   identity/credential.
3. A2 independently proves the exact three scopes and public channel access
   before creating A2 files.
4. A2 rollback/disarmed semantics remain unchanged.
5. No Slack app, host enrollment, service start, Runtime mutation or parenting
   canary is claimed from source merge alone.

Production acceptance remains later: existing app scope reinstall -> host
`enroll-shared --enable-w3c` -> verify -> normal Agent Relay activation ->
target re-census -> the already-governed parenting-loop canary.
