# TSR runbook — short teammate names on the REAL team server

Applies `Assurance — quality` and `Design Lead — product` on the real team
server (`com.mastermind.t3-team`, port 3780, root `~/.mastermind/t3-team`).
Everything below was proven end to end on a throwaway dev server by lane TSR
(evidence `~/.mastermind/mmos_evidence/tsr-20261111/`). Tool:
`tools/mmos_team_server/team_roster.py` (from a checkout at or after
`289f8dad7`). Work from the repo root.

Spec: `tools/mmos_team_server/specs/team_roster.json` — already carries the
short `role_line`s (`quality`, `product`), so no spec edit is needed to apply
the short names.

## 0. Check that no teammate run is live

```
python3 tools/mmos_team_server/team_roster.py status \
  tools/mmos_team_server/specs/team_roster.json
```

For each teammate the row shows the thread id, `threadCurrentTitle` (the long
title today) and `recoveryProblem: null`. Then confirm no run is active:

```
T3CODE_HOME=~/.mastermind/t3-team/home T3CODE_PORT=3780 \
  ~/.mastermind/t3-team-server/bin/t3 thread show <threadId-from-status> --json
```

`"status": "completed"` and `"activeRunId": null` mean the thread is at rest.
A rename only touches the thread title, but doing it while a turn is streaming
risks a confusing mid-flight sidebar. Repeat for both threads; if a run is
live, wait for it (or stop it in the web client) first.

## 1. A paired browser profile is required

Renaming exists only in the web client, so `apply` drives a headless browser
with an already-paired profile. The spec keys are `browser_profile` (the
profile directory; the real one is `~/.mastermind/t3-team/run/browser-profile`)
and, optionally, `browser_profile_root` (defaults to `server.root`; the
profile must be a private child of it, mode 0700).

If that profile is already paired (it was used to pin the threads in T7),
skip to step 2. To pair a fresh profile from the server's 0600 access file:

```
node tools/mmos_team_server/roster_browser.js pair \
  ~/.mastermind/t3-team/run/access.txt \
  ~/.mastermind/t3-team/run/browser-profile \
  3780 \
  /tmp/tsr_pair_out.json
```

The last-but-one argument is the team server's port: the pairing URL is
parsed and must be exactly the loopback team server (`http` on `127.0.0.1`
or `localhost` with that port); anything else is refused before a browser
opens. It prints `PAIR_DONE`. The pairing token is read in-process and never
printed. If pairing fails because the token in `access.txt` has expired
(tokens rotate on every server start), the current one is at the end of
`~/.mastermind/t3-team/run/server.log`. Do not grep or cat that log to a
terminal: the pairing line is the token (review R2a, finding 14). Copy the
two lines into a 0600 file without showing them, pair from that file, then
delete it:

```
umask 077
grep -E '^(Pairing URL|Token):' ~/.mastermind/t3-team/run/server.log \
  | tail -2 > /tmp/team_pair_lines.txt
node tools/mmos_team_server/roster_browser.js pair /tmp/team_pair_lines.txt \
  ~/.mastermind/t3-team/run/browser-profile 3780 /tmp/tsr_pair_out.json
rm -f /tmp/team_pair_lines.txt
```

## 2. Apply the short names

```
python3 tools/mmos_team_server/team_roster.py apply \
  tools/mmos_team_server/specs/team_roster.json
```

What it prints when it worked:

```
[team_roster] Assurance: thread mcp:… is titled 'Assurance — quality & security challenger'; the roster title is 'Assurance — quality'
[team_roster] Design Lead: thread mcp:… is titled 'Design Lead — product design lead'; the roster title is 'Design Lead — product'
[team_roster] Assurance: renamed 'Assurance — quality & security challenger' -> 'Assurance — quality'
[team_roster] Design Lead: renamed 'Design Lead — product design lead' -> 'Design Lead — product'
```

plus a final JSON report with `"renamed": true` for both and exit code 0.
Each rename is verified by reading the persisted title back from the server's
state database (a sidebar-only change does not count), and pin state before
and after is compared and must be unchanged.

## 3. Confirm no teammate has two threads

```
T3CODE_HOME=~/.mastermind/t3-team/home T3CODE_PORT=3780 \
  ~/.mastermind/t3-team-server/bin/t3 thread list \
  --project <projectId-from-apply> --json
```

You must see exactly the two teammate titles
(`Assurance — quality`, `Design Lead — product`) plus any known scratch
threads. Then:

```
python3 tools/mmos_team_server/team_roster.py status \
  tools/mmos_team_server/specs/team_roster.json
```

`recoveryProblem` must be `null` for both. If a third thread whose title
starts with `Assurance —` exists, `apply` refuses for that teammate with
"2 threads could be its primary … refusing to pick or create a primary
thread" and creates nothing. Recovery is a human decision: open both threads
in the web client, decide which is the real primary, and either delete the
other one, or record the real id in `~/.mastermind/t3-team/run/team_roster_state.json`
(`{"teammates": {"Assurance": {"threadId": "mcp:…"}}}` — one entry is
enough; the rest recover by provider instance). The next `apply` converges.

A harmless idempotence check: run `apply` again — it prints `unchanged`,
`untouched`, `"renamed": false`, creates nothing.

## 4. Going back (the undo)

Copy the spec, add `"allow_long_titles": true` at the top level and set the
role lines back to the long ones (`quality & security challenger`,
`product design lead`), then `apply` that copy. The tool warns on stderr that
the titles exceed the 24-character sidebar fit and will ellipsize, and prints
the same `renamed … -> …` lines plus `"renamed": true`. Same thread ids, pins
unchanged, nothing created. (This flag is also how you express the current
long-title state in `status` today.)

## 5. Adding a third teammate later

A new entry in the spec's `teammates` does exactly what the first apply did
for the other two, and nothing to them: their homes, instances, thread ids
and titles are untouched (no rename fires — their titles already match), no
new threads appear for them, and the saved state keeps their ids. The new
teammate gets a home, a provider instance (settings.json reloads live — no
server restart), and one new primary thread — which starts **unpinned**: pin
it once from the paired profile:

```
node tools/mmos_team_server/roster_browser.js pin \
  ~/.mastermind/t3-team/run/browser-profile \
  <new-teammate-url-from-~/.mastermind/t3-team/run/team_urls.json> \
  '<Name>' /tmp/tsr_pin_out.json /tmp/tsr_pin_shot.png
```

## Known limits

- Renames need the paired browser profile; without `browser_profile` in the
  spec, `apply` reports titles pending and exits nonzero rather than pretend.
- The pairing token in `access.txt` is one-time and rotates at every server
  start; pair right after a start if a fresh profile is needed.
