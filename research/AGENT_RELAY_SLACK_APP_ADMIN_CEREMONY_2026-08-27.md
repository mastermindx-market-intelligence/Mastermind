# Mastermind Agent Relay Slack App — A2 Native Admin Ceremony

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Status:** RECORDS + SECRET-FREE APP CONFIG ONLY / PRODUCTION DISARMED  
**Workstream:** `WS:CHAIRMAN-CONTROL-ROOM`  
**Protected Mastermind / Skillpack basis:** `ac1c045ed4cdf0b2b87fbc81760effa909271436`, `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1  
**ASD-A2 preflight receipt:** `asd-a2-host-preflight-revalidate-20260827-sol-002`  
**Canonical channel:** public `#agent-dispatch`, `C0BSBM78V1N`  
**Manifest:** `config/slack_agent_relay_app_manifest.yaml`

## 1. Outcome

Reduce the remaining ASD-A2 native-admin gate to one deterministic, least-privilege Slack ceremony:

```text
import reviewed app manifest
-> install one dedicated Mastermind Agent Relay app
-> invite its bot to #agent-dispatch
-> preserve its OAuth token only inside the reviewed native secret boundary
-> prove secret-free identity/scope/channel facts
-> later install/arm the existing Agent Relay service under the A2 release law
```

This record does **not** install the app, expose a token, arm Agent Relay, create a Wake service, create a Job, or make automatic Sol↔COO continuation live.

## 2. Why a dedicated app remains required

Current A2 revalidation proved no production Agent Relay Slack app/bot, private credential, launchd service, or intended AF_UNIX endpoint is installed. `#agent-dispatch` is a public channel. Worker Presence source law requires one governed Mastermind app principal for bounded agent dialogue while logical Sol/COO/Worker identity remains inside the typed dialogue contract; Slack identity is never Worker identity or lifecycle authority.

Do not reuse ChatGPT1/2/3 personal Slack principals, a Claude personal account, the Executive Relay app, or a generic workspace bot.

## 3. Least-privilege manifest ruling

For the reviewed V1/A2 path and the later WP-TW2 polling baseline, the dedicated bot is explicitly invited to the one public channel it uses. Therefore its required bot scopes are exactly:

```text
channels:history
chat:write
```

No user-token scopes are requested.

### Why these two scopes are sufficient

- Slack documents `channels:history` as the bot scope for `conversations.history` in public channels the bot has joined.
- Slack documents `channels:history` as the bot scope for `conversations.replies` in public-channel threads.
- Slack documents `chat:write` as the bot scope for `chat.postMessage`.
- The app is deliberately invited to `#agent-dispatch`, so `chat:write.public` is unnecessary.
- The exact channel ID is already governed configuration/evidence, so `channels:read` is not needed merely to discover arbitrary workspace channels.

Current Slack references checked on 2026-08-27:

- https://docs.slack.dev/reference/methods/conversations.history/
- https://docs.slack.dev/reference/methods/conversations.replies/
- https://docs.slack.dev/reference/methods/chat.postMessage/
- https://docs.slack.dev/reference/app-manifest/

Any future implementation that genuinely needs another Slack API method must return to Sol with the exact method/scope requirement. Do not widen OAuth scopes preemptively.

## 4. Explicitly disabled surfaces

The manifest intentionally keeps all of the following absent/off:

```text
Socket Mode                  OFF
Events API subscriptions     NONE
Interactivity                NONE
Incoming webhooks            NONE
Slash commands               NONE
chat:write.public            ABSENT
channels:read                ABSENT
user OAuth scopes            NONE
org-wide deployment          OFF
token rotation               OFF for this V1 secret contract
```

WP-TW2 source law specifically requires bounded Web API history/reply polling for its first proof and forbids adding Socket Mode, a webhook/event daemon, or a second app credential merely as an optimization.

Token rotation stays off in this V1 packet because the current Agent Relay secret boundary expects one opaque bot token and does not own a refresh-token/client-secret lifecycle. Enabling rotation later requires its own bounded secret-lifecycle review; do not silently add it during installation.

## 5. Chairman/native Slack-admin ceremony

This is the only portion that requires a Slack workspace admin/owner surface.

### Step A — Create from the reviewed manifest

1. Open Slack app management and choose **Create New App → From an app manifest**.
2. Select the Mastermind workspace.
3. Paste/import the exact contents of `config/slack_agent_relay_app_manifest.yaml` from the accepted repository revision.
4. Before creation, inspect Slack's preview and require exactly these bot scopes:

```text
channels:history
chat:write
```

5. Confirm Socket Mode is off and there are no event subscriptions, interactivity endpoints, incoming webhooks, slash commands, user scopes, or extra bot scopes.
6. Any unexpected permission, event surface, redirect URL, webhook, Socket Mode requirement, or app-name collision => STOP and return to Sol. Do not improvise.

### Step B — Install and bind the one channel

1. Install the app to the Mastermind workspace through the normal Slack OAuth approval screen.
2. Add/invite the resulting `Mastermind Relay` bot user to public channel `#agent-dispatch` (`C0BSBM78V1N`).
3. Do **not** grant workspace-wide posting simply to avoid the channel invite.
4. Do **not** post a canary yet unless the current A2 operator has re-pinned source law and explicitly entered the accepted canary step.

### Step C — Return only secret-free receipts

The admin/session may report only:

```text
Slack workspace/team ID
Slack app ID
Slack bot user ID
channel ID = C0BSBM78V1N
installed bot scopes = [channels:history, chat:write]
app installed = true/false
bot channel membership = true/false
```

Never paste or transcribe the bot OAuth token into ChatGPT, Claude, Slack messages, GitHub, Agent OS, Linear, shell history, command argv, screenshots, browser-visible notes, logs, or receipts.

## 6. Private credential boundary

After the app exists, the A2 host operator—not Slack prose and not a model-authored command—provisions the bot token through the currently reviewed native secret mechanism.

Hard requirements:

- secret bytes remain outside Git and model-visible state;
- do not place the token in command argv or checked-in environment/config files;
- use the existing credential-safe Agent Relay verification path rather than inventing a second token verifier;
- `integrations/slack_agent_dialogue/metadata_verifier.py` remains the secret-safe verifier: token enters through its private stdin boundary and output is restricted to allowlisted identity/scope facts or fixed errors;
- the verifier must match the exact workspace/app/bot/scope/channel expectations frozen by the accepted A2 release at action time;
- token verification is not service installation, transport readiness, or dialogue proof.

If the current A2 installer has no accepted secret-storage destination/label, stop before copying the token and return that exact gap to Sol. Do not create a new secret registry in Slack, Agent OS, or Executive OS.

## 7. WP-1 collision sequencing

Mastermind PR #178 currently owns `integrations/slack_agent_dialogue/service.py` while implementing the V2 protocol required by Worker Presence. Therefore:

- Slack app creation/install/invite is disjoint and may occur before WP-1 merges;
- secret-free app identity/scope verification is disjoint and may occur before WP-1 merges;
- do **not** install a stale V1 Agent Relay service and call A2 complete while #178 is changing the same service boundary;
- before service installation, re-pin protected `master`, require WP-1's accepted merge if #178 has completed, and use the current accepted service implementation;
- any need for A2 to edit WP-1-owned protocol/service semantics returns to Sol instead of widening A2.

This avoids proving an old service only to redeploy it immediately.

## 8. A2 production-proof boundary after the admin gate

Once the app + private credential exist and the current service pickup is reconciled, A2 continues on its already-released wave:

```text
exact protected/source re-pin
-> credential-safe metadata verification
-> smallest reviewed host install/config/service step
-> one harmless real request/ruling/readback on #agent-dispatch
-> hostile wrong-channel/wrong-thread/wrong-sender/effect-unknown checks
-> exact production receipt
-> return to Sol
```

A2 must remain Active-Session Dialogue transport only. It may not absorb:

- WP-TW1 turn classification;
- WP-TW2 observer/Wake composition;
- provider/native Wake #174;
- Executive Job/Attempt/Worker mutation;
- provider/account routing or PR #181 realm rebinding;
- a new Slack queue, inbox, cursor, watcher DB, session registry or retry plane.

## 9. Proof law

The following are separate facts and must remain separate:

```text
Slack app created          != app installed
app installed              != bot in channel
bot in channel             != credential provisioned
credential verifies        != Agent Relay service installed
service installed          != request delivered
Slack request delivered    != worker session consumed it
ASD round trip             != automatic turn watching
turn observed              != Wake delivered
Wake delivered             != TARGET_ACKNOWLEDGED
TARGET_ACKNOWLEDGED         != source resolved
```

## 10. Stop condition

This ceremony packet is complete when the manifest is accepted as the least-privilege configuration and the native admin action is reduced to import/install/invite plus private credential provisioning.

Do not claim ASD-A2, ASD-A3, Worker Presence, Wake, or the zero-manual Sol↔COO loop as live from this records/config wave.
