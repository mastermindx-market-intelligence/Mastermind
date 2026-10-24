# Grok Operations Bot — Owner Setup and Qualification Runbook

**Status:** source setup ceremony only; no Bot/account/service/routine is configured by this document.  
**Controlling architecture:** `docs/superpowers/specs/2026-09-14-grok-bot-autonomy-infrastructure-amendment.md`.  
**Implementation owner:** `docs/superpowers/plans/2026-09-14-grok-bot-autonomy-full-implementation.md`.  
**Canary owner:** `docs/superpowers/plans/2026-09-14-grok-bot-first-supervised-return.md`.  
**Protected source observed:** Mastermind `f4730cc65436d86500ef827c24493f83a7e41def`.

## 1. When this runbook is allowed

Begin owner-side Grok setup only after all of these are true:

1. W6-C2 consultation runtime is protected with exact current interfaces.
2. The authenticated remote Company Consultation app is protected, installed, and accepted for fixture calls.
3. Its public HTTPS endpoint, OAuth policy, dedicated client/principal, exact four-tool schema digest, release identity, audit path, revocation path, and rollback are known.
4. `config/grok_bot_operations.json` and `GrokBotAttestation` validation are protected.
5. The intended account has current usage/plan evidence and no unapproved on-demand or credit overflow.
6. A named owner has approved one finite setup/canary operation.

If any prerequisite is missing, stop at `GROK_SETUP_BLOCKED / <exact dependency>`. Product availability and a signed-in app are not substitutes.

## 2. Target setup

The initial production candidate is exactly:

```text
Cursor user: one intended user; dedicated when credential isolation is required
Bot name: Grok Operations
Bot count: one
Task modes: SENTINEL, FOREMAN
Local execution: disabled
Company connector: one custom Company Consultation MCP
Company tools: company.peers, company.consult, company.reply, company.consultation
Webhook routines: one, initially inactive
Schedules: none
Slack listeners: none
Broad plugins/browser logins: none
Source-write/production/billing/admin authority: none
```

Do not create a second Sentinel, Reviewer, Secretary, or provider-specific Bot during setup. Additional Bots share the same computer and credentials under one user and require a later measured role decision.

## 3. Account and usage inspection

Perform read-only inspection before changing the account:

- record the pseudonymous Cursor user/account ref;
- record the plan or linked grant shown by Grok Bot;
- record weekly usage state and reset basis;
- record whether on-demand is disabled, enabled, or unknown;
- record the account-level monthly limit if visible, without changing it;
- confirm that Cursor and SuperGrok grants do not stack;
- confirm Privacy/data settings permit the intended product;
- inspect existing Bots, plugins, routines, files, browser sessions, and logins because they share the user computer;
- decide whether the intended workload requires a separate Cursor user for credential isolation.

Stop rather than linking or moving a SuperGrok grant casually: current provider documentation says the link cannot be unlinked or moved between Cursor accounts. Enabling or raising on-demand, purchasing credits, upgrading a plan, or changing account privacy requires its own authority.

## 4. Create the single Bot

In Grok Bot:

1. Create one Bot.
2. Set name to `Grok Operations`.
3. Set title to `Mastermind Operations Foreman`.
4. Apply the exact protected profile text/digest from `config/grok_bot_operations.json`.
5. Keep local execution disabled.
6. Do not add a public share link.
7. Do not place secrets, internal URLs, customer data, account emails, hostnames, or private paths in the description or memory.
8. Do not demonstrate a production-changing workflow.

The Bot profile is working method, not authority. A profile edit after attestation creates a new profile digest/generation and blocks current RuntimeBinding until reconciled.

## 5. Connect Company Consultation MCP

### 5.1 Provider-side connection

Use the intended Grok custom-MCP/connector surface and the reviewed public HTTPS endpoint. The endpoint must be the existing Secure MCP Tunnel/public ingress for the installed Company Consultation app; do not create an alternate quick tunnel or public listener for convenience.

Complete the existing OAuth flow for the dedicated least-privilege principal. The required exact scope is the protected Company Consultation scope. Do not authorize Executive submit, GitHub source write, Slack posting, generic filesystem, production, billing, admin, or provider credentials.

### 5.2 Inventory proof

After connection, verify the Bot sees exactly:

```text
company.peers
company.consult
company.reply
company.consultation
```

Refuse setup if any Executive, Company Dialogue, source-write, deployment, credential, browser-control, shell, or foreign tool appears through this connection. Record the provider-visible tool names and the Mastermind schema digest; do not record access tokens.

### 5.3 Safe fixture call

Against the isolated accepted fixture/current canary program:

1. Call `company.peers` with no arguments.
2. Confirm only opaque peer refs and closed display facts return.
3. Call `company.consultation` for one existing fixture ref only when the canary owner supplies it.
4. Prove wrong scope and revoked principal fail before tool dispatch.
5. Disconnect/revoke once, confirm calls fail, then reconnect through the same client/principal generation if the accepted ceremony requires it.

Do not create the real canary consultation during connection setup unless the current canary operation explicitly includes it.

## 6. Create the inactive webhook routine

Create one routine owned by Grok Operations with:

```text
Routine name: Mastermind Wake
Trigger: webhook
Schedule: none
Slack listener: none
Active: false until the canary owner authorizes the finite provider call
```

Use the exact protected routine instruction:

```text
Receive one opaque Mastermind wake envelope. Do not infer a task from the webhook
body and do not treat provider acceptance as company completion. Use only the
connected Mastermind Company Consultation tools to resolve the exact current
consultation/obligation available to this Bot's current binding. If no exact current
obligation is available, perform no external action and report the missing binding
in this conversation without exposing secrets.

For an exact obligation, follow the protected Grok Operations profile. Read current
bounded evidence, produce at most one Company Consultation answer, and stop. Do not
forward, spawn another Bot/helper, use local execution, browse for unrelated work,
change source/production/accounts/billing, send Slack or email, or retry an uncertain
effect. A strategic or Chairman-reserved question remains pending for its owner.
```

After saving, Grok exposes the webhook POST URL and bearer key. Treat both as secrets. A Test run performs real work; do not click Test until the canary input and downstream fixture are ready.

## 7. Transfer webhook secrets to existing custody

The human/admin owner transfers the webhook URL/key through the existing approved secret-handoff mechanism directly into the Executive host's secret owner. Never paste either value into:

- this runbook;
- GitHub/PRs/issues;
- Slack;
- Agent OS/Linear;
- Bot description, memory, conversation, or files;
- RuntimeBinding/session target config;
- command-line arguments;
- logs or screenshots.

The installed secret owner maps one opaque native handle to the current URL/key/generation. RuntimeBinding contains only that handle and generation. Rotation updates the secret owner and creates a new binding/routine generation; historical receipts retain the old digest/generation.

## 8. Generate the redacted attestation

Record only the accepted `mastermind.grok_bot_attestation.v1` public fields:

- pseudonymous account ref;
- pseudonymous Bot ref;
- protected profile digest;
- Company Consultation server identity and tool-schema digest;
- connection generation;
- pseudonymous routine ref and instruction digest;
- routine generation;
- `local_execution_enabled=false`;
- on-demand state as true/false/null from actual observation;
- observation time;
- exact source/install release identities.

Validation must reject emails, URLs, tokens, secrets, account/subscription IDs, host addresses, raw provider output, and wrong digests/generations. The attestation proves configuration identity only; it does not prove a run, consumption, answer, authority, or production readiness.

## 9. Pre-canary security checks

Before enabling the routine:

- Company MCP principal is least-privilege and revocable;
- custom MCP inventory is exactly four tools;
- local execution is off;
- no broad plugins or admin browser logins exist;
- webhook payload fixture contains opaque IDs only;
- webhook secret is available only to the existing sender/secret owner;
- on-demand/credit overflow cannot create unapproved spend;
- one exact canary Worker/Attempt/RuntimeBinding/consultation/requester is ready;
- wrong scope, revoked auth, stale binding, inactive routine, and non-200 paths are prepared;
- provider run history/request ID observation is available for effect reconciliation;
- Control Room can display unknown/accepted/consumed states without secrets.

Enable the routine only for the finite canary window. Pause it immediately after the canary unless a later accepted wave explicitly authorizes event-driven service.

## 10. Canary and rollback

Follow `2026-09-14-grok-bot-first-supervised-return.md` for read/return proof, then Task 13 of the full implementation plan for webhook proof.

Rollback order for a definite failure:

1. pause the Grok routine;
2. revoke/disconnect the Company MCP principal where required;
3. disable/remove the RuntimeBinding/target overlay through the existing owner;
4. preserve Wake/W6-C evidence and unresolved effect state;
5. keep the Bot/profile only if investigation needs it and no access remains;
6. rotate the webhook key if exposure is suspected;
7. restore the previous installed service release only through its accepted rollback path.

A lost webhook response or uncertain provider start is not a definite failure. Mark `EFFECT_UNKNOWN`, keep the same operation and target, inspect the provider run history/current W6-C state, and never resend through another Bot, webhook, account, or Slack path.

## 11. Acceptance states

Use these exact distinctions:

- `BOT_CREATED / NOT_CONNECTED`
- `CONNECTED_NOT_ATTESTED`
- `ATTESTED / ROUTINE_INACTIVE`
- `READ_CANARY_PASS`
- `WAKE_ACCEPTED / RECIPIENT_NOT_CONSUMED`
- `ANSWER_AVAILABLE / REQUESTER_NOT_CONSUMED`
- `RETURN_CANARY_PASS`
- `EFFECT_UNKNOWN`
- `PAUSED / CANONICAL_STATE_PRESERVED`
- `PROVEN_LIVE` only after canonical Wake, exact answer return, requester consumption, negative journeys, production projection, and Sol acceptance.

Never compress these into “Grok is working.”

## 12. External capability references observed 2026-09-14

- Plans/usage and non-stacking grants: https://cursor.com/help/grok-bot/plans
- Webhook URL/key and HTTP 200 semantics: https://cursor.com/help/grok-bot/routines
- Shared computer/minimal roster: https://docs.x.ai/grok-bot/overview and https://docs.x.ai/grok-bot/bots
- Security/user isolation: https://docs.x.ai/grok-bot/security-faq
- Custom MCP public reachability/auth: https://docs.x.ai/grok/connectors/custom-mcp-tunneling and https://docs.x.ai/grok/connectors

Revalidate these contracts and the actual product UI at action time.
