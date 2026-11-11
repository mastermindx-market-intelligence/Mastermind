# R2a: independent read-only review of the live carrier, cut-over tool and roster tool (2026-11-11)

Reviewer: claude-opus-5-5, read-only, wrote none of the code. Scope: `wake_carrier.py`,
`cutover_installed.py`, `setup_teammate.py`, `team_roster.py`, `roster_browser.js` and the
three real teammate specs, at trunk `5459b33fa`. Line numbers are as of that commit. The
principal re-ran the reviewer's probe for findings 2, 3 and 4; all reproduce
(`~/.mastermind/mmos_evidence/r2a-20261111/probe.py`, `probe_output.txt`).

**Verdict: safe to keep running; not safe to move more agents onto the carrier** until
findings 1 to 4 are fixed. The run token stays inside the carrier on every path traced. Every
serious failure needs issue text written to cause harm, text pasted from a thread by mistake,
or a rare crash or overlap. Today only the Chairman, the principal and the three teammates
write issues these teammates read.

## Findings and what the principal decided

| # | Sev | State | Where | What goes wrong | Decision |
| --- | --- | --- | --- | --- | --- |
| 1 | HIGH | confirmed | `team_roster.py:275-281`, `:301`, `:333` | A teammate's limits allow plain `Read` with no path limit, and `Write`/`Edit` anywhere in its home. Its home holds its own `tool-limits.json` and `CHARTER.md`. Issue text can steer it to read the pairing file, the browser profile's cookies or a cut-over preimage and quote it in its reply, which the carrier posts. It can also loosen its own limits or rewrite its charter. File mode 0600 does not help: the teammate is the same user. | **Fixed by the principal and live** (see below). Deny rules for reads of credential folders and other teammates' homes; deny rules for writes to its own limits, charter, carrier config and preimage. `WebFetch` stays for now and is decided with the lane RF return. |
| 2 | HIGH | reproduced | `wake_carrier.py:483-498` (`scan_marker`) | The turn marker counts anywhere inside any user message, and the last one wins. The marker is a hash of public text. If issue X's text (or a pasted thread excerpt) contains issue Y's marker, Y's carrier later takes X's answer as Y's, posts it on Y, and never sends Y's own task. Same for the `-ret` and `-rev` operations. | Lane RF: a marker counts only when a user message begins with exactly `[op]` and a newline, and the first such message wins. |
| 3 | HIGH | reproduced | `wake_carrier.py:332-338`, `:1410`, `:1464`, `:1497` | Any issue whose description contains `[pc-…-ask]` anywhere is treated as an ask child: the answer goes straight to `done` with no board confirmation. In a real child, a bracketed marker in the asker's own text wins over the carrier's trailing marker, so the return can deliver an old answer from another issue. | Lane RF: an issue is an ask child only when the carrier's marker is the last line of the description, the issue has a parent, and the marker is the one the carrier would compute for that parent. `handle_ask` removes any `[pc-` text from what the teammate wrote. |
| 4 | HIGH | reproduced | `wake_carrier.py:1493-1496`, `:1119` | Asks have no depth limit and a teammate can ask itself. One confused reply can start a chain between teammates that only a person stops. Each level costs a child issue and a run. | Lane RF: an asked child cannot ask (depth one); an ask to oneself is refused; at most three asks per issue (config key, default 3); the child lookup pages past 50. The message to an asked child says it cannot ask and should state what it needs in its answer. |
| 5 | MEDIUM | traced | `wake_carrier.py:1105`, `:1332` | `handle_return` and `handle_feedback` deliver without the ask-child flag, so a child goes to `in_review` and the asker stays blocked until the board accepts. | Lane RF: pass the flag on both calls. |
| 6 | MEDIUM | retry confirmed, duplicate plausible | `wake_carrier.py:522-544` | Every HTTP method is retried on 408, 429, 5xx or a lost connection, including the create of a child issue and of a confirmation. A saved-but-unanswered create makes a second child. A retried confirmation gets 409 and the carrier then moves a delivered issue back to `todo`. | Lane RF: retry only GET, PUT and PATCH. After a failed create, read the children (or the interactions) again and look for this operation's marker before posting again. A 409 on a confirmation that already exists for this operation is success. |
| 7 | MEDIUM | plausible | `wake_carrier.py:711-721`, `:946-966` | Two runs for one teammate on different issues share one thread. The second can send its message twice and post a waiting line about the first one's question. | Lane RF: first establish from the installed Paperclip's files (read-only) whether it runs two processes for one agent at once. Then a lock per thread from scan to delivery, with a wait bounded by the run budget. No change in behaviour when there is no overlap. |
| 8 | MEDIUM | traced | `wake_carrier.py:674`, `:963` | The `t3` subprocess timeout is fixed at 1,200 seconds, so a send after a 900-second question wait can run past the adapter's 1,500-second limit and Paperclip kills the carrier. | Lane RF: the subprocess timeout is the remaining run budget; a timeout is treated as still pending. |
| 9 | MEDIUM | traced | `cutover_installed.py:186-188`, `:71-73` | `apply` overwrites the shared carrier file in place, checking live runs only for the agent being moved. Moving a fourth agent from a newer checkout swaps the carrier under three running teammates, and a run starting mid-copy reads a cut-off file. | Lane RF: if the installed file exists and differs, refuse and point to `refresh-carrier`; otherwise staged copy and `os.replace`. |
| 10 | MEDIUM | traced | `cutover_installed.py:232-247` | `rollback` checks only live runs and restores the whole `metadata` object. Rolling back while a turn waits on a question or an ask child hands open issues to the old runtime, and later binding changes are lost. | Lane RF: `rollback` refuses on the same open-work blockers as `apply`, and removes only `metadata.teammate`. |
| 11 | MEDIUM | traced | `team_roster.py:370-373`, `setup_teammate.py:167` | `settings.json` is written in place while the server watches it and reloads about 100 ms after a change. A reload between truncate and write reads partial JSON. | Roster side: principal, after lane RF returns (same file as finding 12). `setup_teammate.py` side: lane RF. Temporary file in the same directory, 0600 from creation, fsync, `os.replace`. |
| 12 | MEDIUM | traced | `wake_carrier.py:983-987`, `team_roster.py:465-516` | The carrier sends to the agent's `primaryThreadId` in Paperclip; the roster tool keeps its own state file and never reads that field. If the roster's state is lost and recovery finds nothing, `apply` starts a second primary thread. The carrier also never checks that the bound thread belongs to the bound provider instance. | Carrier side, lane RF: check the thread's provider instance before sending, and refuse on a mismatch. Roster side, next lane: `apply` reads each agent's binding (one GET) and refuses to create a thread when a binding exists. |
| 13 | LOW | plausible | `wake_carrier.py:533-538`, `:687-689`, `:703`, `:1513`, `:1622`; `setup_teammate.py:63-64` | Up to 300 characters of an HTTP error body or of the `t3` command's error output are posted on the issue. The Paperclip address comes from the environment and is not pinned. | Lane RF: post only the error type and status code. The address is pinned from `carrier.json` (`paperclip_base`, already in the spec), loopback only, and a different `PAPERCLIP_API_URL` is refused. |
| 14 | LOW | confirmed | `TSR_SHORT_NAMES_RUNBOOK.md:53-56`, `roster_browser.js:144-148` | The runbook tells the operator to grep the server log for the pairing line, which prints the token. `pair` opens whatever URL its file names. | Next lane, with the roster side of 11 and 12: `pair` takes the line itself and requires the loopback team server. The runbook step is corrected now. |
| 15 | LOW | plausible | `wake_carrier.py:1412-1435` | If a person blocks a task without naming a blocker and its marker is already answered, the next wake delivers and moves it to `in_review`. | Lane RF: deliver from `blocked` only when the carrier itself blocked the task (its own waiting line) or an ask child exists. The unanswered-question journey proven on MAS-11 must still pass. |

## What the review confirmed is sound

- The run token: the argument list carries only the config path, `PAPERCLIP_*` is removed
  from the `t3` child's environment, and no message, log line or comment carries it.
- The cut-over preimage is written before the patch with exclusive create and mode 0600, a
  second `apply` cannot overwrite it, and `refresh-carrier` never touches it. No command
  prints it. `refresh-carrier` swaps the carrier atomically.
- The rename path: the profile path comes from the spec and must be a 0700 directory under
  the server root; the URL is the loopback team server with ids read from the server, never
  from thread content; arguments go as a list with no shell; the result file and the evidence
  line hold no credential.

## Safe only because this is one person on one Mac

Recorded as open; none is fixed in this program.
- Paperclip trusts any loopback request with the `local_trusted` header as the board, so any
  local process can edit bindings, create issues and comment as a person.
- Machine text and a person's words are told apart by a text prefix.
- Teammates, the carrier and the Chairman are one user. Finding 1's deny rules are the
  teammate's own tool limits, not an operating-system boundary.
- The `t3` command line can drive any thread of the server its home names.
- Exactly-once relies on the carrier's own checks; a second host needs a lease per thread.
- Issue and thread links are loopback http only.
- The roster tool reads the server's database and writes its settings file directly.

## Finding 1, fixed and applied (principal, 02:45 UTC)

`team_roster.py` `tool_limits` now writes, for each teammate:
- read denies for the server's `run`, `home`, `config`, `claude-home` and `fabric.env`, every
  other teammate's home, its own `cutover-preimage.json`, the paths in the spec's
  `deny_read_roots`, and (with `deny_read_root_siblings`) every other entry beside the server
  root;
- write and edit denies for its own `tool-limits.json`, `CHARTER.md`, `carrier.json`,
  `cutover-preimage.json` and `cutover-result.json`. Its memory `CLAUDE.md` stays writable.

The real spec names the credential folders of this Mac. Applied to all three teammates with
no run live; titles, threads and pins unchanged. This diff is on the credentials surface and
was written by the principal, so it goes into the next independent review with lane RF's diff.

## Finding 1, second part: the home is the configuration folder (principal, 02:50 UTC)

Found by the principal's own live checks, not by the review. A teammate's home is also its
Claude configuration folder, and its limits allowed creating any new file there. Assurance,
asked to try, created `settings.json`, `.mcp.json` and `skills/probe/SKILL.md` in its home
(MAS-16). A settings file can carry a hook command and an MCP entry can name a program, so a
steered teammate could give itself a shell on its next start, which the `Bash` deny is meant
to prevent. Whether the runtime loads those files from the home is being established on a dev
server by lane RL; the fix does not wait for the answer.

`team_roster.py` `HOME_CONFIG`: write and edit denies for the configuration file and folder
names in the home (`settings.json`, `.mcp.json`, `.claude.json`, `skills`, `agents`,
`commands`, `hooks`, `rules`, `plugins` and the rest). Applied to all three teammates.

**Limits bind at process start, not on file change.** A teammate session is one long-lived
process per thread. MAS-16 ran in a process started before the new file was written, so the
new denies did not bind there; the first fix bound in MAS-14 only because that process started
after the file was written. The earlier sentence in the plan that tightening needs no restart
is wrong. Lane RL adds a report line to `apply` and the safe restart procedure.

**Live checks so far** (`~/.mastermind/mmos_evidence/r2a-20261111/LEDGER.md`):
- MAS-14: Read and Edit obey the deny rules; own memory stays writable.
- MAS-15: Grep, Glob and whole-file Write obey them too.
- MAS-16: configuration names in the home were creatable under the first fix.
- Owed: the same attempts after Assurance's process restarts under the second fix.

Lane RL (GLM 5.3, started 02:50 UTC) builds the stronger design: reads allowed only from named
roots, writes only to the memory file and one notes folder, proven on its own dev server; plus
the roster side of findings 11, 12 and 14.
