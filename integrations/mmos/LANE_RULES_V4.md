# Rules for every lane and every child (plan V4, 2026-11-10)

Read this once before your first command. Your brief names your goal and your
write scope; this file is what never changes between lanes. If your brief and
this file disagree, this file wins and you say so in your return.

## What is not yours

| Thing | Rule |
|---|---|
| The Chairman's T3 Code app: `/Applications/T3 Code (Beta).app`, ports 3773 and 3774, `~/.t3/userdata` | Never restart, reconfigure, pair with, patch, send into or write to. Nothing under `~/.t3` is read, except running `~/.t3/bin/t3` against a dev home |
| The team server: launchd `com.mastermind.t3-team`, port 3780, `~/.mastermind/t3-team`, `~/.mastermind/t3-team-server` | Read files only. No request to port 3780, no build or edit in its source tree, no launchd load or unload. Changing it is the principal's act |
| The installed Paperclip: port 3100, `~/.paperclip/instances/default` | HTTP GET and file reads only. No issue, comment, agent, routine, plugin, run retry or database edit |
| Hermes: `~/.hermes` | Read only. Never restart the gateway. Never run `hermes doctor --fix` |
| The Chairman's installed `~/Applications/Mastermind OS.app` | Never rebuild, replace, quit or drive it. You work on the dev bundle `Mastermind OS Dev.app` (`com.mastermind.os.dev`) only |
| The production Executive, its Worker, its config, the VPS | No change, no stop, no disarm |
| Other launchd jobs, ports 3179, 3190, 3796, 3800 | Leave alone unless your brief says you own that instance |
| Protected `master`; PRs #2419, #2433, #2351, #2182, #2177, #2186, #2342 | No push, no edit |

Your own instances live under `~/.mastermind/mmos-dev/` (Paperclip dev instances on
their own ports), `~/.mastermind/mmos_dev/` (window and T3 dev roots) or a scratch
directory your brief names, each on a port you pick and state in your return.

## Credentials

- A pairing token, session cookie, connection string, run token, route key or API key is a
  credential. Read it from a 0600 file. Never print, log, commit, copy into evidence or pass
  it on a command line. In receipts write the sha256 only.
- Never print any `fabric.env`, `run/access.txt`, `routes.json`, `router.env`,
  `cutover-preimage.json` or a raw `run/server.log`.
- T3's pairing page shows the one-time token to accessibility dumps. Pair only from a 0600
  file at launch. No accessibility dump and no image of the pairing page.
- A browser profile or cookie store that holds a session is a credential: 0700, never in
  evidence, never committed.
- Never trust loopback TCP or request headers to admit a caller. Local admission is by Unix
  socket and kernel peer uid only.

## The desktop

- One child at a time drives a window. Time box 20 minutes per attempt.
- Captures are of the app's own window or one browser tab. Never the full screen.
- Do not send keystrokes through System Events: the Chairman is working on this Mac and they
  land in his window. Use accessibility actions on the target window's own elements, or a
  headless browser.
- No desktop work for `glm-5.3` children.

## The shared git store

- Never add or remove a remote. Never fetch with `--depth`. Never run `git gc`, `git prune`,
  `git stash`, `git worktree remove` or a force push.
- Work on the branch your brief names, created in the checkout you were started in. Push it to
  `origin` under that name. Do not push the trunk `feat/mmos-v1-integration-t3`; the principal
  merges.
- One writer per checkout.

## Children

- A driver may start at most two children, each with a model named explicitly:
  `target: {providerInstanceId: "capacity_fabric", model: <id>}`. Allowed: `glm-5.3`,
  `glm-5.3-flash`, `kimi-k3.1-pro`, `deepseek-v4.1-flash`, `minimax-m3`. Not allowed:
  `gemini-4-argon`, `grok-4.7`, any Claude or GPT model.
- An attack on a diff goes to a different model from the one that wrote it. The attacker gets
  this file's git rules word for word and the commit to read; it has no reason to fetch.
- A child that fails once on a gateway error is restarted in the same thread. A child that
  fails twice is replaced by you doing that part, after `task_status` then `task_cancel`.

## Returns

- "NOT DONE, because <reason>" is an accepted return. An invented result is not.
- A claim counts when the principal can open the artifact. Keep raw outputs in the evidence
  directory your brief names, with a `LEDGER.md` listing each claim and its file.
- Do not end your turn while your own background jobs or children still run.
- End your return with the literal output of: `git rev-parse HEAD`,
  `git ls-remote origin <your branch>`, `ls <your evidence dir>`, and the test command you ran
  with its last line.
- Tests: `TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q -p no:cacheprovider <files>`.
- Write for a reader who was not here: full sentences, the thing before its label, no arrows
  or invented abbreviations.
