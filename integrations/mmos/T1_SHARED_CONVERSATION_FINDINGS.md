# T1 — shared conversation findings (dev T3 server + stock web client)

Date: 2026-11-10. Lane T1 of `PROGRAM_PLAN_V4.md` (decision 2.1 under test).
Evidence: `~/.mastermind/mmos_evidence/t1-20261110/`. Scripts: `tools/mmos_dev/t3_dev.sh`,
`tools/mmos_dev/t3/*.js`, seed `tools/mmos_dev/t3/seed_dev_home.py`.

## Exact start command

```
python3 tools/mmos_dev/t3/seed_dev_home.py   # once: copies provider def file-to-file
tools/mmos_dev/t3_dev.sh start               # port from 3790 up, loopback, headless serve
tools/mmos_dev/t3_dev.sh status | stop | selftest
```

Home `~/.mastermind/mmos-dev/t3/home`, port 3790 (first free ≥3790; 3773/3774 refused),
`T3CODE_HOST=127.0.0.1 T3CODE_NO_BROWSER=1`, `t3 serve`. The startup banner (connection
string, one-time token, pairing URL) is captured to `run/access.txt` (0600), never printed.
Fabric route env (`ANTHROPIC_BASE_URL/AUTH_TOKEN/…`) rides the server process env from
`~/.mastermind/mmos-dev/t3/fabric.env` (0600); the provider instance's `environment` block
is empty — `mergeClaudeProcessEnvironment` inherits the server env into the claude child.

## Sign-in (one-time token → session cookie)

1. `t3 serve` prints `Pairing URL: http://127.0.0.1:3790/pair#token=…`.
2. Open that URL in the browser: the page auto-submits the hash token once, exchanges it
   for a cookie, then history-replaces to `/` and reloads (route `pair.tsx`,
   `PairingRouteSurface`). First visit lands on `/welcome` onboarding; "Close" skips it.
3. Cookie: name `t3_session_3790_<hash>` (per-port+instance name; `resolveSessionCookieName`),
   domain 127.0.0.1 — see `signin.json` (names only, no values recorded).
4. **Session duration:** the cookie is persistent in the browser profile and the session
   survives a **full server restart** (stopped pid, started new pid, same home): reopening
   the thread URL shows the messages with no `/pair` and no `/welcome`
   (`restart_proof.json`: STAYED_SIGNED_IN). So a window must simply persist its browser
   profile directory; no re-pairing after restarts. Pairing again requires a fresh token
   (each is one-time).

## Direct-to-thread and hiding the sidebar

- The stock client opens **directly on one thread by URL**: installed 0.1.7 serves threads
  at `/<environmentId>/<threadId>` (e.g. `/2ff6fec5-…/954fe061-…`; note: no `/chat/` prefix
  in the installed bundle — the pinned source's `_chat.$environmentId.$threadId` route id
  differs from the built routes). A window can load exactly this URL.
- The sidebar hides with the existing "Toggle main sidebar" button (`aria-label`, present in
  the header; state persists per client store — persistence across restarts not separately
  tested). So: **stock client can open on one thread and hide its sidebar without a fork**;
  only a *default-hidden* sidebar or a custom landing would need the fork (T3).

## Streaming — the central surprise (verdict FAIL for the canonical prompt)

`stream_proof_plain.json`: 1–2 DOM text changes for the counting prompt → **FAIL** by the
lane's rule, honestly recorded. Provider `capacity_fabric/glm-5.3` (claudeAgent). Cause,
verified at every layer (not the provider):

1. Router streams fine: direct `/v1/messages` SSE gave 50–119 `content_block_delta`
   events per answer (with thinking, with tools: still streams).
2. The claude CLI receives and forwards them (`--include-partial-messages` probe: 50 deltas).
3. **The T3 server applies only `thinking_delta` live** (`ClaudeAdapterV2.ts` ~9026:
   `content_block_start/delta/stop` handled for thinking only). **Text (`text_delta`) has
   no handler** — assistant text is emitted per *completed content block* from SDK
   `assistant` snapshots. `splitBufferedAssistantText` (settings `responseStreamingMode`:
   `paragraph` default) can only further delay, never accelerate.
4. Client result: while a turn runs you see live *activity* — working row, thinking row, a
   one-line live answer preview (`liveAnswerPreview`, zen mode, the 140-char `work-live`
   row) — but glm-5.3 emits one text block per turn, so **the answer text appears in one
   piece at turn end** (conversation-region sample: 284 → 2285 chars in one jump after 15 s).
   Multi-block turns (text, tool_use, text…) would surface sections as each completes.

Implication for plan V4: "the Chairman sees live text while the model writes" is true for
thinking/tool activity and for multi-block answers, but **not token-by-token answer text**,
on stock 0.1.7 with any provider through the claudeAgent driver. This is a server adapter
behavior, not a web-client or window problem. If token-level answer streaming matters for
Team, it needs a T3 server change (apply `text_delta` like thinking deltas), not a fork.

## Queue and steer (`queue_proof.json`)

While a long turn ran, the composer accepted a second message (submit enabled, no queue
chip, no "queue"/"steer" wording anywhere in the page). Server-side it queued: both turns
completed (2 user + 2 assistant messages, story and follow-up both present), no second
provider session file, 62.8 s total. The page shows the running turn; the queued message
just sits as a sent user message until the first turn completes.

## Two views of one thread (`two_views.json`)

Same profile, second page on the same thread URL: established connections to the port went
16 → 18 (one page ≈ one live WS), message counts identical in both pages, no duplicate
submission, no provider session start. **Team and Code can be two views of one client**;
they share one cookie and one server-side thread state.

## Other surprises

- `t3 project add <path>` works non-interactively against a chosen `T3CODE_HOME` — the dev
  server picked up the project immediately.
- Onboarding (`/welcome`) appears on a fresh profile even though the cookie was just set;
  "Close" exits it and it does not return.
- The provider event log (`userdata/logs/provider/events.<thread>.log`) **suppresses**
  `stream_event content_block_delta` and text `message.part.updated` lines
  (`EventNdjsonLogger`) — absence of deltas in logs proves nothing.
- The server banner can flush after the port answers; the start script polls for it
  (earlier access-file capture raced and came back empty).
- Environment: provider instances are settings records (`providerInstances.capacity_fabric`,
  driver `claudeAgent`, `config.homePath`, `customModels`); secrets live in
  `userdata/secrets/provider-env-*.bin`. The dev copy needs none of that — env inheritance
  suffices (see `seed_dev_home.py`).
- T3 commit for installed 0.1.7: **NOT KNOWN** — no build metadata or git sha in the app
  bundle (only file-integrity SHA256s).

## Verdict for the lane question

A browser client other than the T3 desktop app **can** sign in to a T3 server on this Mac,
open one thread, get live turn activity, queue while running, and survive a full restart
with the same profile — proven with artifacts. The one gap is token-level answer-text
streaming, which stock T3 (server side) does not emit for claudeAgent providers; the
canonical-prompt verdict is FAIL for that reason, with the provider and evidence named.
