# GBL — Sources

Everything this lane relied on, 2026-11-11. Repo reads at branch `t3/t3-hermes-restart-recovery`
(worktree `t3-daae3d66`), read-only. Web sources read 2026-11-11 with this session's web tool;
vendor pages are time-sensitive capability evidence, not entitlement.

## Repository documents

- `docs/runbooks/grok-bot-operations-setup.md` — whole file (230 lines). Target bot shape
  (§2), Company Consultation connector + four tools (§5), webhook routine creation + secret
  custody (§6-7), pre-canary checks and rollback (§9-10), acceptance states (§11), and the
  external doc links (§12) this lane used as its research start.
- `docs/superpowers/specs/2026-08-28-grok-secretary-mastermind-mcp-openclaw-design.md` — §3
  (topology, MCP platform), §5 (versioned tool surfaces), §9 (public-edge auth law),
  §10 (idempotency/effect-unknown), §16 (no-rebuild list), §17 (primary-source links).
- `docs/superpowers/specs/2026-08-28-grok-secretary-mastermind-mcp-openclaw-current-source-amendment.md`
  — §4-6 (installed user-openclaw owner chain; single-path repair law) — read for the
  standing rule against second MCP identities on the Grok host.
- `docs/superpowers/specs/2026-09-14-grok-bot-autonomy-foreman-design.md` — §2 (capability
  ledger), §4 (permission ladder), §5 (account/computer boundary: bots share one computer),
  §6 (integration contracts), §8 (provider qualification, model managed by Cursor), §13
  (delivery order G0-G4), §15 (vendor refs V1-V9).
- `docs/superpowers/specs/2026-09-14-grok-bot-autonomy-infrastructure-amendment.md` — §3
  (architecture freeze: Wake in, Consultation out), §4 (grok-bot surface, RuntimeBinding,
  opaque webhook payload, HTTP-200 law), §5 (four-tool facet, OAuth remote composition),
  §8 (security posture, network ceiling), §10 (failure table), §12 (waves), §14 (holds).
- `docs/superpowers/specs/2026-09-16-grok-consultation-v3-identity-design.md` — whole file:
  v3 reserved for grok-bot QUESTION frames; surface law; proof contract; non-goals.
- `integrations/executive_wake/grok_bot_routine.py` — whole file (258 lines):
  `GrokBotRoutineWakeDispatcher` (transport `grok-computer`, surface `grok-bot`),
  observation/receipt/`EFFECT_UNKNOWN` law, `reconcile()`.
- `common/agent_dialogue_consultation_contract.py` — whole file (543 lines): v1/v2/v3
  schemas, surface tables (lines 59-72), budgets (97-102), fingerprints, packet
  render/parse, `classify_duplicate`.
- `control_plane/session_targets.py` — lines 1-90: schema, `REASONING_SURFACES` incl.
  `grok-bot` (60-62), two-key arming law (26-28).
- `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md` — whole file (428 lines): §1 exact-carrier root
  and delivery≠pickup, §2 explicit edges, §3 watcher classes/one-watcher/fresh-read,
  §5 symmetry, §7 new-wave law, §10 incident rationale.
- `integrations/mmos/PROGRAM_PLAN_V4.md` — §4 DONE_WHEN, §6 boundaries (Chairman's T3 app
  off-limits; credentials law), §8 live-text, §9 binding/wake decision, §10 T2 accepted
  (carrier is every edge; Paperclip is the trigger owner), §11 team-server decision, §24
  (RF scope, R2a finding 1), §26 (review panel ruling; Kimi scarcity), §27/§31 (XP; install
  order), §32 (server/window switched), §33 (deputy; RF repair 3; bridge release word).
- `integrations/mmos/T2_TEAMMATE_BINDING_AND_DISPATCH.md` — lines 1-80: teammate binding
  JSON, wake sequence steps 1-8, T3 send surface choice, what is not atomic/proven.
- `integrations/mmos/XP_CROSS_PROJECT_CHILD.md` — lines 1-120: cross-project child law and
  admission checks (context for environment/project addressing).
- `docs/REUSE_FIRST_ENGINEERING.md` — by reference (law, no findings cited).
- `docs/plans/2026-11-08-mmos-team-delivery-integration.md`, `control_plane/teamlink_contracts.py`,
  `app/mastermind_os/src/hermes-native/teamlink-contract.ts` — read by reader 3 (below);
  PR #2419 deliberately not opened, built or copied.

## Reader reports (deepseek-v4.1-flash, capacity_fabric_worker, effort max, 2026-11-11)

- Reader 1 map of `integrations/company_consultation_dispatch.py` (3,024 lines) — entry
  points (`:1151-1163`, `:1102-1104`), state/events, deterministic id mint (`:689-724`),
  replay law (`:1416-1548`), result envelope (`:2734-2767`), process-identity auth
  (`company_consultation_host_authorization.py:26-88`), answer wake (`:2508-2570`),
  `grok_bot_http.py` adapter. Filed as FACTS.md B13.
- Reader 2 summary of `docs/runbooks/shared-executive-slack-relay.md` and
  `docs/sol_skills/mastermind-x-operations/references/slack-relay-bridge.md` (+ the engine
  files they name) — app/scopes (`runbook:14-25`), polling-only inbound (`:34-36`), channel
  surface, gated widening (`:58-70,129-131`). Filed as FACTS.md B14.
- Reader 3 inventory of the TeamLink contracts and plan doc — `TeamLinkMessage.v1`
  (`teamlink_contracts.py:19-99,151-199,232-265`), states, idempotency, both-files-pure-schema,
  doc leaves transport unqualified (`:444-446,765,842`). Filed as FACTS.md B15.

## Web sources (primary, vendor)

- https://docs.x.ai/grok-bot/overview — bots share one cloud computer; Slack named among
  connectors; "interact with any MCP or API"; bots collaborate; primary-bot aggregation.
- https://docs.x.ai/grok-bot/bots — bot creation, duplication semantics; "Files and
  sign-ins on the shared computer aren't isolated per Bot"; bot-to-bot context passing.
- https://cursor.com/help/grok-bot/routines — trigger types incl. Slack and webhook; POST
  URL/key/header; 200 = started-not-finished; no auto-retry; 300/200 runs-per-hour; Slack
  app posts as the connected user; "A Slack trigger is part of a routine, not the Slack app."
- https://docs.x.ai/grok-bot/skills-routines-and-automations — trigger options and scoping;
  "Only new activity counts"; Bearer header; rate limits; 50 routines/bot; 5-minute floor.
- https://docs.x.ai/grok-bot/security-faq — "A Bot has no identity of its own"; per-user
  microVM; bots share the user's computer; no outbound-request signature mechanism documented.
- https://docs.x.ai/grok/connectors — connector classes; custom MCP "must be reachable over
  the public internet"; OAuth on our side.
- https://docs.x.ai/grok/connectors/custom-mcp-tunneling — public-internet requirement,
  localhost rejection, ngrok/Cloudflare, "you will still complete that flow in Grok".
- https://cursor.com/help/grok-bot/plans — weekly grant resets, shared pool, metered on
  Cursor account, on-demand, "can finish past the monthly limit", grants do not stack.
- (checked, now 404) https://docs.x.ai/docs/guides/grok-bot-slack — a separate @grok Slack
  assistant guide; not the Grok Bot Slack app; excluded from evidence.
- (secondary, via search) docs.x.ai navigation confirms no dedicated Grok-Bot Slack-app page
  beyond the routines/skills pages above.

## Live checks still owed (FACTS.md §C)

- A3 Slack thread trigger/post semantics; A14 long MCP tool-call behavior; A10 connector
  scope across bots of one account.
