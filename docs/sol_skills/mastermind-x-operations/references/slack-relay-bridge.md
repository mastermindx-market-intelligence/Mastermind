# Slack relay bridge — Executive Relay app

One app, one bot identity, multiple agent profiles. Governs provisioning, scopes, token handling, and rotation for the org workspace Slack transport.

## Why a bridge (standing)
- Slack platform limit: one app = one bot user = one bot token. The workspace sits on the free-plan 10-app cap with zero removable apps (several serve the ChatGPT fleet) — so no second app. Multi-agent over the one app = ONE roster unit owning the token (`hermes-runtime-mmrelay.service`, env `~/hermes-migration/secrets/mmrelay.secrets.env`) plus internal routing. Never list the same `HERMES_SLACK_BOT_USER_ID` on two roster units — roster.py's fail-closed collision guard rejects it, and the guard stays unweakened.
- Routing/attribution: `hermes_secretary/relay_mux.py` PLANS DMs → secretary profile, exec channels → Meta-CEO, @-mention overrides — it maps surfaces to roles but sends nothing itself (see In-repo state below). `chat:write.customize` sets per-message `username`/`icon_url` so each profile renders its own name/avatar while the roster still sees the single bot ID; bold-header fallback (`*Meta-CEO ·*` / `*Secretary ·*`) if the scope is ever revoked.

## In-repo state (roster + mux — the transport seam exists)
- `hermes_secretary/roster.json`: single `hermes_agents` row `hermes-mmrelay` (unit `hermes-runtime-mmrelay.service`, secrets `mmrelay.secrets.env`, envs `HERMES_SLACK_BOT_USER_ID` / `HERMES_SLACK_BOT_TOKEN`), `sibling_hermes_agent_ids: []`. `roster.py` validates a minimum of one row; the fail-closed collision guard and distinct-user-service guard are unchanged and test-covered against the chris and groksecretary plates.
- `hermes_secretary/relay_mux.py` maps the ONE bot identity to the TWO logical roles. Routing: DMs and `#dotsandgroksecretary` → `mmsecretary`; `#metaceo` → `mmmeta`; an explicit role handle ("secretary" / "meta-ceo") inside a bot @-mention overrides; both handles → refusal (`ambiguous-role`); any unrouted surface → refusal (`unrouted-surface`). Attribution kwargs: `Mastermind Secretary`/`:scroll:`, `Meta-CEO`/`:crown:`; bold-header fallback (`*Secretary ·*` / `*Meta-CEO ·*`) when customize is unavailable.
- The mux is data-only by construction: it loads no token, holds no Slack client, sends nothing; channel ids resolve via `roster.channel_names()` (never code constants); every plan re-runs `default_roster`'s guard so a planned post can never carry a human/commissioner/peer id. A source-scan test enforces the boundary — the suite fails if `chat_postMessage` or an `xoxb-` literal appears in the module. Carrying out a plan still requires the Chairman cutover grant; shadow/read-only remain the only live surfaces.
- The runtime role plane (`mmsecretary`/`mmmeta` profiles, ~85 files incl. `native_dialogue_consumer.ROLES`) is deliberately NOT part of the transport lane — both roles persist behind the single bridge identity.

## Provisioning (user-executed — automate nothing here)
Automated browser self-serve on slack.com is bot-blocked (login walls, throttled magic-code). The Chairman drives the UI; you verify from the local machine:
1. api.slack.com/apps → Google SSO as workspace owner → Executive Relay (App ID `A0BTCKA7GSY`) → **OAuth & Permissions**. The App Credentials page (Client/Signing/Verification secrets) is the WRONG page — the integration uses none of them; the needed value is the **Bot User OAuth Token** (`xoxb-`).
2. Bot Token Scopes (least privilege): `chat:write`, `channels:history`, `groups:history`, `im:history` (DM routing), `users:read` (roster identity), `chat:write.customize` (per-profile attribution). `chat:write.public` only if Slack grants it; otherwise `/invite @Mastermind Executive Relay` into each posting channel. User Token Scopes are irrelevant to the runtime — recommend deleting them (kills the `xoxp` at next reinstall). Never store an `xoxp`: it posts as the owner, the largest blast radius in the workspace.
3. App Home → Show Tabs → Messages Tab → enable "Allow users to send … messages from the messages tab" — without it, DMs never reach the bot.
4. Any scope change requires Reinstall App, which ROTATES the token — always copy the post-reinstall value; an earlier copy is stale.
5. Store via masked `read -s` one-liner, or one terminal write that never echoes the value. If the scaffolded env file already holds empty-valued lines, rewrite in place (python dict, then `chmod 600`) — appending duplicates keys and dotenv load order decides which copy wins.
6. Derive identity server-side: `auth.test` with the token → `user_id`/`user`/`team`; write `HERMES_SLACK_BOT_USER_ID`. Print only non-secret fields.
7. If a token value transited chat or screenshots: rotate before cutover — delete User Token Scopes + reinstall (kills xoxp), Regenerate the bot token, re-store masked. Re-derivation is idempotent; the bot user ID never changes.

## Identity (provisioned, verified via auth.test)
- Bot user `U0BT71H4FQE` (`mastermind_executive_`), app bot `B0BT4SFK57F`, team `T0BRD2AQXQV`, workspace `mastermindxgroup.slack.com` (NOT mastermind-x.slack.com).
- Human plates: chris `U0BRET6191C` (owner), metaceo082 `U0CF8E78FJB`, groksecretary `U0BTCHX8HMF`.

## Scope discipline
Add a scope ONLY when a lane PR needs it (candidate triggers: `app_mentions:read` → Events API mention routing; `files:read` → attachment ingestion; `reactions:read` → emoji ACKs). A future add costs two minutes (Add → Reinstall → re-paste), so never front-load — leaked-token blast radius grows linearly with the scope list.
