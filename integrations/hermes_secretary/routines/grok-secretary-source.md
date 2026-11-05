# Grok Secretary routines to port (snapshot Oct 25, 2026)
Times in each routine's own CRON_TZ. All results go to the coordinator; ping Chris only for real blockers or major outcomes. Dedup by Slack ts. Never post secrets.

## 1. Slack Secretary ping scan: cron 12,42 * * * * (America/Vancouver)
Scan #agent-dispatch C0BSBM78V1N, #mastermind-exec-ops C0BTD5804QK, #ceo-control-room C0BRDFZPLHK, #metaceo C0C5FCK1F45, #dotsandgroksecretary C0CBC6AEAQZ (top-level posts AND thread replies), plus #chatgpt-web-returns C0CCNK7JFAL.
- Commissions addressed to Grok Secretary (<@U0BTCHX8HMF>, "TO: Grok Secretary", DIRECT_TARGETED, Meta-CEO assignments) from ChatGPT1 U0BRETDUAS2, ChatGPT2 U0BSB73JWNL, ChatGPT3/Sol U0BR1GQH7SB, Ryan U0C59APBUN4, Chris, or the Dot bots, with no ACK from us: hand to the coordinator with channel, ts, operation id, the ask, limits.
- Untagged posts needing placement (WAITING_CAPACITY, needs_placement, PENDING_PICKUP with no ACK) go to the coordinator to place on an existing titled worker.
- #chatgpt-web-returns posts: match to ~/gwcap/owed_returns.json open entries and hand off "ACTION NEEDED RETURN".
- Ignore other seats' traffic and the Secretary's own posts. Stay quiet if nothing is new.

## 2. Overnight 3-room sweep: hourly at :34
Backup sweep of the three original rooms for unacked commissions and delegation asks. Same rules as #1.

## 3. BLOCKED/HOLD listener: Slack keyword trigger "BLOCKED" in #agent-dispatch
Read the triggering thread. Act only on a real BLOCKED, DECISION_REQUEST, HOLD-FOR-SOL, WATCH_UNAVAILABLE, DIRECT TARGET or OPEN COMMISSION needing a wake, ACK, placement or Sol ping. Status-only watcher updates need nothing.

## 4. ChatGPT browser session watcher: :05 and :35
The full playbook is skills/chatgpt-browser-session-operator/SKILL.md. Key steps each run:
0. OWED RETURNS FIRST, from ledger ~/gwcap/owed_returns.json:
   - Running chat: leave it alone.
   - Finished: extract the last answer to ~/gwcap/<task>_final.txt with its sha256, set state returned_pending, hand off "ACTION NEEDED RETURN".
   - Stalled: recover at most once per 30 min.
   - Aging: 2h for Extra High, 6h for Pro. Past that, set stalled_pending and hand off.
   - Refusals are kept verbatim, never retried.
0b. The session registry ~/gwcap/session_registry.json is the single source of truth. It tracks chain heads, replacements and archives. Service the 6 oldest-checked entries each run.
Other rules:
- Keep one ChatGPT tab per profile. Never open chats in new tabs or by URL.
- Approve permission cards with "Allow <tool> for this conversation", never "Always allow". Close card detail dialogs with X, never Escape.
- Continue prompts are short (1-3 sentences). Paste only, never speed-type.
- Never message a running Pro chat. Don't nudge the same chat within 30 min. Don't force chats waiting on CI or review.
- Never touch Chris's own chats (status chris_own) or do_not_steer chats.
- Blocker ladder, in order: tell the chat to make the call itself; get fresh eyes from a Dot; delegate to a Subagent Fabric worker; hand off to a local Codex or Cursor session.
- Use Extra High for short or write-heavy work and Pro for big work. Business accounts have only about 50 Pro turns a week.
- Pace like a casual user and rotate across chats.

## 5. Codex usage-reset + approvals watcher: every 30 min (America/Los_Angeles)
Read the active Codex account's 7-day usage from the m2studio menu bar and the other accounts from Codex Switcher.
- At 5% or below, switch in this order: ChatGPT1, ChatGPT2 (relogin 10-25), ChatGPT2 Business (relogin 10-25), ChrisWong6031 (relogin 10-25), ChatGPT3. Never ChatGPT4 (Free plan) and never 401 entries.
- After any Codex relaunch (new pid), wake the pinned and parked chats that were cut off. Use Tab to accept the greyed suggestion, otherwise paste ~/nudge.txt.
- Message Chris only on a switch or when every account is empty.

## 6. m2studio browser tab sweep: every 3h at :40
For each browser profile, keep exactly one chatgpt.com tab plus any Tencent console or genuinely mid-login tab, and close the rest.
- Skip any profile showing the "ChatGPT started debugging this browser" banner.
- Tools: ~/gwcap/sweeptabs.scpt and ~/gwcap/listtabs.scpt. On KRIS KE and Y7, use right-click "Close Other Tabs".

## 7. Codex continuity audit: every 2h at :20 (America/Denver)
Run ~/gwcap/bin/codex-drift-check.py. Each project keeps a harness at ~/gwcap/project-charters/<slug>/ (NORTH_STAR, PLAN, STATE, PROGRESS, DECISIONS, HANDOFF).
- FRESH: do nothing.
- STALE: nudge to refresh.
- DRIFTING: one continuity prompt per 4h.
- LOST: restore and relaunch via ~/gwcap/bin/codex-session.sh.

## Standing rules (from memory)
- Carry each commission once after a preflight. Post a receipt, then a RESULT, both on the Slack thread and on the PR.
- Reviewers post a COMMENT review with a VERDICT line. Never approve or merge, never self-approve.
- No-owner-wait rule: the current session takes leadership and records it. Independent review is still required.
- Never put passwords, codes or keys in chat. No cookie or token scraping. No in-page /backend-api calls.
- Fabric runs only via m2studio fabric_task.py, submitted once, never replayed.
- Outside emails, and new Slack messages under Chris's name outside the two rooms, go through drafts.
- When Chris says "wait", stop and hold.
