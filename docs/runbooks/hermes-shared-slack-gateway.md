# Hermes shared Slack gateway — actual deployment and continuity acceptance

Status: SOURCE CANDIDATE; NOT A PRODUCTION CUTOVER.
Owner: incumbent M2 Hermes Engineering Slack gateway. Parent: #2198 / #2159.
Candidate: PR #2342, branch \`sol/slack-hermes-virtual-identity-ingress-20261108-c1\`.
Base pin: \`Mastermind@06ef56a39c085af72bcbf0866db8e43f99cd6034\`.

## The real incumbent (verified November 8, 2026)

- M2 host: \`~/.hermes/bin/slack_gateway.py\`, launchd \`com.mastermindx.hermes.slack-gateway\`, single Socket Mode owner for the existing \`A0BTCKA7GSY\` app (native bot \`U0BT71H4FQE\`).
- Pre-change on-host file SHA-256: \`8585d2b0fc8d390ada537cdb4fb7158af13bad6ae596917c9a54a8f26043415d\`. Not the SHA of the source candidate.
- Configuration: \`~/.hermes/slack-fleet/agents.json\`, 0600. Original runtime state \`relay-state.json\`, 0600. Agent credentials remain on host under \`~/.hermes/secrets\` and MUST NOT enter GitHub, logs or a chat.
- Nine routable display identities (Engineering, Assurance, Delivery, Intelligence, Product, Reliability, Chief of Staff, Secretary, Meta-CEO); nine \`/mx-*\` slash commands are configured. Real bot/user ID aliases require separate Slack principals; one app provides one native bot ID, not nine.
- M2 audit sample had 14 thread bindings but zero saved native Hermes session IDs, plus multiple failed/timeout Secretary turns. The Hermes CLI \`hermes chat -Q\` writes \`session_id: ...\` to stderr, not stdout. This source candidate fixes receipt parsing and also rejects unrelated mention wake-ups and rejected-event rate-limit poisoning.
- The installed gateway performs direct subprocess dispatch. It is not proof of canonical Executive/Agent Dialogue authority, cross-agent handoff, durable native admission or production acceptance.

## Reconciliation and delivery gates

1. Qualify exact-source branch, source diff, all required CI and review/release controls. Do not run this candidate as a SECOND Socket Mode listener. Do not migrate original threads or overwrite active native sessions.
2. Original M2 host/admin owner must verify current installed SHA, live writer and any in-flight effects immediately before installation. Stop/replace only the original launchd gateway within its approved release lane, never an alternate receiver. Keep the exact installed file for rollback with secure permissions.
3. Install **only from accepted exact GitHub source** and verify installed SHA/content and service restart. Current M2 host code may have changed since the pre-change SHA above. CAS/check beforehand; any drift requires reconciliation and renewed focused testing.
4. Keep existing one-app credentials, 0600 registry, native profiles and unchanged Slack channel authorization. Never paste an xapp/xoxb/xoxp/xoxe credential into source or command arguments. Test the authenticated loopback \`/health\` with an existing secret held locally, without emitting the secret.
5. Use a **fresh** Slack thread, after original admission, to prove a real human \`@Mastermind Executive Relay secretary: ...\` or \`/mx-secretary\` causes one accepted Hermes turn and one attributed reply in the same thread. Read the canonical Hermes session receipt from stderr. Confirm the gateway saved that thread's native session ID, not just the role binding.
6. Send a follow-up in that same thread with no mention; prove the exact same Hermes session ID was supplied to \`--resume\` and its result returned, not a new session. Test two different roles / independent threads and preserve role memory isolation.
7. Test dual Slack event delivery \`app_mention\` + \`message.channels\`, revoked/unallowed sender, unrelated user mention, bot echo, Slack restart/reconnect, and timeouts. Confirm no second turn, no unknown-effect blind retries, no model tokens when idle.
8. **Source-only enhancements needing real canary:** the candidate now holds a bounded, in-memory per-thread mutual exclusion gate so overlapping same-thread workers serialize (independent threads do not wait). Explicit \`<@shared bot> engineering: ...\` role selectors in an existing thread switch the current role and isolate the native session key by \`thread+role\`; an unmentioned follow-up stays with the latest selected role. Failed/ambiguous dispatches do not advance the saved session ID. Validate under real Slack traffic, including restart with waiting messages, before claiming production correctness. The in-memory gate is NOT a durable queue, cannot repair a crash-lost turn and must not replace canonical Executive/Agent Dialogue admission.
9. **Still open:** autonomous agent-to-agent task requests, background nudges routed through canonical Runtime/Agent Dialogue, session-currentness on installed generation, original-effect repair after a gateway crash and real multi-turn thread/role-switch proof. Hermes native \`peer\` supports peer-gateway DMs and run/status, and Hermes Kanban supports profile collaboration, but both are separate surfaces. Reuse only under the already authorized Executive/Agent Dialogue owner, not as an unadmitted second control plane.

## Evidence and rollback

- Before any mutating step: exact GitHub commit, current M2 installed file hash, launchd state, live gateway PID, current \`relay-state.json\` presence and active session consumers.
- After: versioned install SHA, service health, actual Slack message link and reply, original native session IDs (redact sensitive context), same-thread resume proof and negative-path receipts.
- Roll back through the incumbent owner using the saved original exact file with the same launchd service; do not destroy \`relay-state.json\`, native Hermes databases or pending jobs. Reconcile any ambiguous Slack posts rather than reposting after an unknown effect.

**Do not call this deployment complete on CI alone.**

## Native profile isolation — required in accepted release

The older M2 Socket Mode launcher set `HERMES_PROFILE=role` but did not
select a Hermes home; installed Hermes `get_hermes_home()` selects
`HERMES_HOME` or the pre-parser `hermes --profile <real-name>` flag.
Without the flag a Slack role can silently reuse the machine's default profile,
memory, and model credentials even if the message is labeled differently.
**The candidate now passes the actual role as a native `--profile` selector
before `chat`**, while keeping `HERMES_PROFILE` as the task attribution label.

The installed 0600 M2 roster uses a legacy `meta-ceo.profile=hermes` value
and the native profile `hermes` does **not** exist; the authentic Meta-CEO
charter is in the enrolled `meta-ceo-uncensored` profile's `SOUL.md`.
Only `meta-ceo:hermes` is normalized **in memory** to that valid native home
for compatibility; other role mappings are not silently rewritten and the
original roster remains unchanged. Candidate defaults now directly name
`meta-ceo-uncensored`. Verify `hermes --profile secretary profile show
secretary`, `--profile engineering`, and `--profile meta-ceo-uncensored`
on the intended host without model execution before cutover.

**Hard acceptance:** same-thread continuity is not sufficient if all personas
share the same native home. Read the exact distinct native session bindings,
profile/homes, and same-thread role switch across Secretary and Engineering.
A virtual Slack persona is not a separate native Slack `@user` identity.
