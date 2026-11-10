# Chris-Dot through the existing Mastermind Executive Slack app

**Status:** Source-only until the installed release, Chris account OAuth and actual Dot callback are proven. This runbook does not authorize installing another Slack app, rotating a refused token or starting an inactive runtime.

## Mission and owner boundaries

Chris-Dot remains the real OpenAI-hosted Dot with its memory, computer, tools and permissions. Executive carries one marked Slack message through the original A2 channel and the original Runtime signed callback path. There is no new Slack installation, new bot identity, event server, database, scheduler or queue.

Shared Slack workspace T0BRD2AQXQV, Executive bot U0BT71H4FQE, A2 channel C0BSBM78V1N (#agent-dispatch), C1 channel C0BSGABKBFY (#sol-runtime). The previously deleted dedicated legacy Relay must **not** be recreated.

Historical blocker: the installed A2/C1 credential formerly refused authorization. The Chairman subsequently restored the original bot's membership in both configured channels; fresh membership was verified. This does **not** prove the installed host token or Chris's OpenAI event subscription. A later native verifier invocation was explicitly denied by the tool's safety boundary; do not replay it through another carrier. Never create a replacement bot or copy a token.

## Implemented default-off source

- Merged PR #2199 supplies the canonical owner-only marked message projection.
- The original A2 Slack Web API client reads one complete history thread. The original peer-credentialed Unix socket exposes a narrow read_dot_canary operation only with explicit --enable-dot-canary; no Socket Mode or Slack Events API.
- The existing Executive MCP Events RPC discovers and subscribes the original canary event; the original Executive CeoIngress App peer owns subscription, revocation and a manual canary_deliver action.
- The existing Executive Runtime event table and AES-GCM key seal the callback URL, signing key and retained account grant. Canonical one-shot reservations refuse duplicate sends or blind retries.
- The original Standard Webhooks signer and pinned-TLS HTTPS sender provide verification and delivery; 2xx is only transport acceptance.

Existing OAuth scope mastermind.executive.read is retained exactly. The canary requires an **explicit Chris subject digest**, current account authorization, selected release/resource policy fingerprint, fixed Slack channel/sender, unexpired token, and enabled source/host flags. Other accounts cannot subscribe merely because they can read Executive.

## Exact activation after the human controls are restored

1. Slack admin confirms the **existing Executive Relay** app is installed and its original bot authorized; the incumbent native A2 and C1 verifiers must pass before starting any service. No token is pasted into a chat.
2. Existing Executive owner deploys a compatible released head with the original service principals. In the same root-sealed Executive MCP configuration, web_ceo_v3 and reply_events_armed must be installed, the existing Runtime/AEAD key owner selected, and a closed, explicit dot_canary enrollment authorized. Its fields are armed=true, subject_digest=(digest of **Chris's authenticated ChatGPT subject**, not guessed), workspace_id=T0BRD2AQXQV, channel_id=C0BSBM78V1N, relay_bot_user_id=U0BT71H4FQE, owner_slack_user_id=U0BRET6191C, and a fresh not_before_ts. The original full config, key and release custody remain intact.
3. The original A2 **native enrollment owner**, while the existing service is disabled/unloaded and its original bot authorization is freshly restored, performs the ordinary guarded `rebind-release --expected-bot-user-id U0BT71H4FQE --enable-dot-canary` operation. This atomically checks and updates the existing enrollment JSON plus the existing LaunchDaemon plist; no bot ID, token contents or Slack scope changes are permitted. The subsequent `verify --expected-bot-user-id U0BT71H4FQE --enable-dot-canary` must pass before activation. This is a new default-OFF flag only: the old canonical enrollment/plist bytes are preserved absent the flag. A combined `--enable-w3c --enable-dot-canary` enrollment is deliberately refused until the separate immutable W3C permission-review contract is changed through its own legitimate process. W3C is presently disabled and must stay so for this canary; no new listener is created.
4. Chris signs in to **his ChatGPT Business account** and authorizes the existing Mastermind Executive custom MCP plugin with normal OAuth. His actual Chris-Dot subscribes to the mastermind.slack_canary_message event for channel C0BSBM78V1N. Verify signed webhook challenge, original Runtime subscription readback, and real OpenAI subscription.
5. Chris posts one harmless channel-thread message with marker MMX_CHRIS_DOT_CANARY_V1:, captures its exact thread_ts and message_ts; a trusted Executive owner issues one private canary_deliver against those timestamps. No user-selected URL, sender, or message body is accepted.
6. Confirm the existing A2 client re-read complete history, one bounded webhook was sent, the real Chris-Dot reacted and posted an authorized reply into the original thread using its own connected Slack action if that action is available. If the connected action is unavailable, outbound parity has **not** passed. Compare Slack installed-app count before/after.
7. Verify wrong account/channel/sender, bot echo, edited/deleted/incomplete source, expiry, revocation, duplicate and ambiguous HTTP outcomes. No automatic replay after an unknown effect; verify unsubscribe.

## Native MCP gateway enrollment without an alternate config writer

The incumbent `plan-mcp-component` / `apply-mcp-component` transaction now supports one **optional paired** source-owned input: `--chris-dot-canary-input <root-sealed 0600 JSON file>` plus `--chris-dot-canary-sha256 <SHA-256 of its original bytes>`. Both absent preserve source-only release updates. One alone, an unsafe input, foreign workspace/bot/channel/sender or a new grant over an existing enrolled grant refuses before installed effects. A valid input contains exactly the original `dot_canary` fields (not credentials, callback secret or OAuth token) with `armed: true`, `subject_digest` from **Chris's real authenticated ChatGPT OAuth principal**, the fixed existing workspace/bot/channel/Slack sender and a fresh Slack cutoff timestamp.

This is a **new optional admission inside the original MCP component-update operation**, not a second issuer, sidecar, file store, or update transaction. The existing root-owned no-follow bounded input reader checks custody and byte digest. The original operator sees a plan containing only the enrollment-document digest, gateway before/after hashes and unchanged closed release effects. If the actual approved plan is applied, the original owner atomically installs `reply_events_armed: true` and exactly the closed `dot_canary` object alongside the normal new source SHA, retaining every old policy, resource, port and grant. The selected input is frozen in the incumbent transaction marker so `reconcile-mcp-component` never reopens it or takes new arguments. No service or grant is selected by the source merge itself.

A **separate original Control composition** must already be or become explicitly authorized with `reply_events.armed: true`, existing AEAD key custody and `dot_canary_enabled: true`; the MCP component update does **not** create, provision or turn on Control's event host. The native A2 `--enable-dot-canary` mode and actual Chris OAuth consent remain further separate gates. Do not directly edit either protected installed config, invent a subject digest or use a complete-configuration transplant to bypass these owners.

## Exact Executive two-sided opt-in (same owners, not a new auth plane)

The **existing** Executive control-plane `reply_events` config remains default OFF. For a properly enrolled canary, the incumbent Executive host source permits an additional exact boolean `reply_events.dot_canary_enabled: true` alongside its already-approved `armed`, `mcp_config_path`, `storage_key_path`, and `storage_key_id` values. It performs no additional canary-file read when absent/false. If explicitly true, that host **must read and validate the original sealed MCP document**, prove matching Executive release and service UID, and require an explicit `dot_canary.armed: true` with Chris's actual authenticated subject digest, existing fixed Slack channel/bot IDs and message cutoff. Neither side alone grants a subscription.

The sealed MCP profile remains `web_ceo_v3` with `reply_events_armed: true`; original `mastermind.executive.read` is the sole accepted read OAuth scope. The Chris-only subject allowlist and policy are **additional first-party host checks**, not a new OpenAI OAuth scope or a Slack permission. The A2 `--enable-dot-canary` mode is a separate third gate on the original service and cannot be derived from a model request.

Default OFF and failed policy selection are meaningful security states. A running C1 process, green CI, installed file, challenge 2xx, and a response accepted by an HTTP server do not establish actual Chris-Dot execution. Do not silently replay uncertain original deliveries.

## What this cannot claim

This first source canary is a one-shot operator-invoked event, **not** continuous unattended Slack monitoring. It cannot recreate the authentic native @Chris-Dot bot identity, DM inbox, or all OpenAI-native Slack experiences. A deployed source, healthy CI and an HTTP 2xx do not prove the Dot ran. A separate owner-preserving A2 observation admission would be needed for unattended triggering after the canary passes.

Current GitHub source carrier: https://github.com/mastermindx-market-intelligence/Mastermind/pull/2205 . Protocol: https://developers.openai.com/plugins/build/mcp-events
