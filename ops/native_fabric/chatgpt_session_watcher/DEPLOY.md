# Enable the ChatGPT web session watcher on m2studio

This is the enablement note. It does not start the watcher, install a launch agent, or call the live fabric. The default mode is observe. Live browser effects stay off until `MMX_WATCHER_ALLOW_LIVE=1` is set on m2studio by a person who can see the windows.

The worker kind is `chatgpt_web_session_watcher`. The fabric task class is `chatgpt_session_watch`. The reasoning pool is `minimax` and the model is `MiniMax-M2.7`. The process has to run on m2studio (`61f4e9d7-b202-4cda-85ed-36904689931e`), because that is where the Multilogin and Chrome windows are.

## What is already on the machine

- The fabric owner script is the installed `fabric_task.py` under the meta-ceo handoff kit. Readiness is `http://127.0.0.1:45119/readyz`.
- Browser hooks live in `~/gwcap`. The copies under `hooks/gwcap/` in this package match the helper kit this worker was written against (`cjs.sh`, `mjs.sh`, `jsend.sh`, `jallow.sh`, `vt.sh`, `vmain.js`, and the rest). `mjs_core.js` still expects the existing `~/gwcap/gpt_sel.js`. Do not replace a newer installed hook with an older copy.
- The MiniMax key stays in `~/.minimax/config.json`. The client reads it in process. It is never put on argv and never printed. Do not debug the process with `pgrep -f`, `pgrep -a`, or a full `ps` command line.

## Source that has to be on m2studio

Use the merged commit of this change. Do not copy a dirty worktree. The two paths the facade needs are:

- `ops/native_fabric/chatgpt_session_watcher/cli.py`
- `integrations/studio_direct_mcp/fabric-backend.mjs`

The installed fabric facade has to be the build that knows `task_class: chatgpt_session_watch`. Until that facade is the one listening on port 45119, a request for this class will not reach the watcher. Restarting the gateway is a separate, explicit step. This document does not do it.

## State directory

```sh
mkdir -p "$HOME/.local/share/mastermind/chatgpt-session-watcher"
chmod 700 "$HOME/.local/share/mastermind/chatgpt-session-watcher"
```

That directory holds `registry.json`, `owed_returns.json`, `lessons.json`, `metrics.json`, and `runs/`. It is local memory. Do not commit it.

To start from the attached sample rather than an empty registry, copy a full registry export into `registry.json` only after checking it has no secrets. The package fixture is a 4-row sample of the 1047-row shape, not the live registry.

## Observe, first

From the repository root on m2studio, with the fabric readiness check as a read:

```sh
/usr/bin/curl -fsS --connect-timeout 2 --max-time 5 http://127.0.0.1:45119/readyz
python3 ops/native_fabric/chatgpt_session_watcher/cli.py register
python3 ops/native_fabric/chatgpt_session_watcher/cli.py cycle \
  --state-dir "$HOME/.local/share/mastermind/chatgpt-session-watcher" \
  --mode observe
```

`cycle` without fixtures only records the accounts you pass in. A real census is a live-mode hook plan. In observe, `cycle` and `spawn` do not click, paste, or send, even if the packet says `"mode": "live"`.

A fabric parent requests one observe cycle with the existing tool:

```text
fabric_request
  task_class: chatgpt_session_watch
  task_complexity: C1_ROUTINE_BOUNDED
  pool: minimax          # optional; any other pool is refused
  model: MiniMax-M2.7    # optional; auto selects MiniMax-M2.7
  work_packet: {"mode":"observe","brief":"one census pass"}
```

`CONTROLLER_CREATED` means the facade started the process. It does not mean a browser was touched. `fabric_accept` returns `WATCHER_ACCEPT_UNSUPPORTED` for this kind. Read the controller output.

`fabric_request` runs one cycle and exits. A periodic loop is:

```sh
python3 ops/native_fabric/chatgpt_session_watcher/cli.py serve \
  --state-dir "$HOME/.local/share/mastermind/chatgpt-session-watcher" \
  --mode observe \
  --max-cycles 1 \
  --interval-seconds 1800
```

Raise `--max-cycles` only after an observe report looks right. The interval is 30 minutes, the same cool-off as a Pro chat. Do not install a launch agent from this note.

## Live, only after observe

Live is a second switch. Both are required:

1. The process environment contains `MMX_WATCHER_ALLOW_LIVE=1`.
2. The command or the work packet sets `"mode": "live"`.

Without the environment variable, a live request is downgraded to observe and the report says `live_refused`.

Before the first live cycle:

- Confirm one ChatGPT tab per profile: ModernLuxe/ChatGPT1, KRIS KE/ChatGPT2, Y7/ChatGPT3, FashionBird/ChatGPT4, Chris-Dot, Ryan-Dot.
- Leave Flovia, personal chats, and any registry row with `do_not_steer` alone.
- Chris's own chats (`chris_own`) may only get a card click, a Retry, or the bare line `Please continue.`
- Peekaboo runs only when the Mac is actually idle. The AppleScript and JXA hooks do not take focus.
- GitHub write cards get Allow once after See details matches. Other cards get Allow for this conversation. Always allow is acceptable on those other cards. Nothing presses Escape.
- The watcher does not merge, approve, label, enqueue, mark Ready, or self-review. It does not type passwords or click auto-reload.

Set the hook directory if `~/gwcap` is not the default the shell already uses:

```sh
export MMX_WATCHER_ALLOW_LIVE=1
export MMX_GWCAP="$HOME/gwcap"
```

The Python tool layer calls the hooks by name. It does not shell `pgrep -f` or `ps` with a full command line. Policy-sensitive clicks go through `allow_card.js` and Pro sends go through `send_keep_pro.js`. `jsend.sh` is the Extra High paste path, because that installed hook forces Extra High. Do not point a Pro continue at `jallow.sh`; that script prefers Always allow and would skip the GitHub Allow-once rule.

## Reflection

A reflection writes a markdown proposal under the state directory. It does not edit `policy.py`, the prompt templates, or the decision rules. Those change only through a reviewed pull request. Prefer tactics whose metrics show they restarted the chat or completed the recovery.

## Turn it back off

Unset `MMX_WATCHER_ALLOW_LIVE`. The next cycle is observe even if a packet still says live. Stop the `serve` process if one was started. Do not kill browser processes as part of turning the watcher off.
