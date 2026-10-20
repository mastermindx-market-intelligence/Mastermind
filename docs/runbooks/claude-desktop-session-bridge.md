# Claude Desktop exact-session bridge

## Purpose

Mastermind can move one exact local Claude Code session into the Claude Desktop app without GUI scripting or creating a second session registry.

The identity source remains the existing `claude_code` surface binding: an absolute project directory plus the native Claude session UUID. The bridge verifies that transcript in Claude's local project store before any handoff.

## Supported native path

Anthropic's native handoff is:

```text
claude --desktop --resume <session-id>
```

Claude Code 2.1.285 or later is required. The command refuses redirected stdio, so Mastermind runs it through the PTY subprocess boundary in `integrations/chairman_surfaces/runner.py`.

A handoff is reported `verified=True` only when:
1. the bound transcript exists;
2. the configured bridge CLI is executable and reports >= 2.1.285;
3. the PTY command exits zero; and
4. Claude returns the exact native "Opening session ... in Claude Desktop" receipt.

No prompt is submitted by this bridge.

## M2 deployment

The Executive Claude worker remains independently qualified on its own binary. Do not replace that binary merely to gain Desktop handoff.

The M2 bridge runtime is isolated at:

```text
~/.local/share/mastermind/claude-desktop-bridge-install/.local/bin/claude
```

It was installed with an isolated `HOME`, so `~/.local/bin/claude` remains on the Executive-qualified version.

The Control Room defaults to the isolated path above. It can be overridden with `--claude-desktop-cli` for an explicitly qualified newer bridge CLI.

## Control Room

For a bound `claude_code` session, the Surfaces list and work detail render a **Desktop** action in addition to the normal terminal **Open** action.

The browser sends only:

```json
{"binding_id":"<binding uuid>","target_surface":"desktop"}
```

The browser never supplies the project path, Claude session id, CLI path, URL, or argv. Those are resolved server-side from the validated binding and server configuration.

## Multiple Parall Desktop accounts (October 19, 2026 repair)

Parall's numbered Claude wrappers can have distinct outer bundle identifiers
and private user-data-dir paths while their underlying Claude runtime still
uses the shared Anthropic Desktop identity. The wrappers also register
claude:// as the same URL scheme. A generic native Desktop handoff therefore
cannot reliably choose the account that owns a bound session.

On macOS hosts with at least two **distinct Claude Desktop app bundles**
(including a Default/Official plus one numbered Parall wrapper),
open_claude_code_in_desktop refuses the native Desktop handoff with
failure_kind=ambiguous before invoking the PTY handoff. Likewise,
open_claude_desktop refuses claude:// URLs before asking LaunchServices
to select a handler. Symlink aliases of the same bundle do not count as
separate accounts; an unreadable/missing application inventory refuses
closed rather than guessing which account owns the session. No app is launched or credential inspected, and there
is no retry under another account. The existing binding vocabulary has no
authorized exact Parall account selector: adding such a selector requires
explicit account-to-session qualification, not an arbitrary default.

Ordinary Claude Code CLI operations (claude, claude -p, claude --resume)
and HTTPS browser navigation are unchanged. The 2026-10-01 single-handler
Desktop handoff canary below predates this safety repair and must not be
interpreted as proof of multi-account selection. Source publication alone
is not installed-runtime acceptance.

### Existing M2 account-wide shell guard

The same repair extends the **existing** `mastermind_fabric_routing_guard.py`
used by Claude and Codex, not a second watcher or provider control plane.
It blocks generic Desktop launches, the shared Anthropic bundle-ID route,
raw Parall runtime launches, ambiguous `claude://` opens, and native
`claude --desktop` use within covered Mastermind shell calls. Ordinary
headless and resume CLI commands remain permitted. Its scope includes both
`/Volumes/Mastermind/agent-workspaces` and the current
`/Volumes/Mastermind 2/agent-workspaces` external SSD root.

The reviewed source fragments are under `ops/claude_parall_isolation/`.
The drift-checked installer operates only on the incumbent guard and the
two existing account instruction files. It defaults to read-only verification.
For an actual authorized installation, use:

```sh
python3 scripts/install_claude_parall_isolation.py
python3 scripts/install_claude_parall_isolation.py --apply --evidence /absolute/new/evidence-directory
```

It upgrades only historically pinned exact guard versions (including the
merged PR #1647 version) and accepts only their committed fixture hashes.
Unrecognized host drift refuses without replacing another owner's
configuration; applies use private backups and atomic per-file writes. No
background daemon, CLI binary change, provider login, or Parall account
data modification occurs. The covered shell guard now recursively inspects
common execution prefixes (env, sudo, nohup, exec, command, nice and nested
sh/bash/zsh -c up to a bound), but does not parse all possible shell scripts
or guard a native Electron auto-updater. Claude CLI -p, --resume, and prompts
*describing* GUI commands remain allowed. Do not claim OS-wide enforcement.

### Native updater residual risk and account-safe vendor migration

At 2026-10-19 16:08:49 PDT macOS recorded a Claude 6 application exit,
at 16:08:52-53 replacement app-bundle file events, at 16:08:54.452 a ShipIt
(standard Electron/Squirrel.Mac update helper) LaunchServices event, and at
16:08:54.650 a replacement Claude runtime. That runtime PID 82118 had
**Claude Default** Parall data files open, not the managed Claude 6 profile.
The correlation strongly suggests a native updater-to-legacy-launcher collision;
the identity of any originating agent is unproven. Neither the Control Room
adapter nor a shell PreToolUse hook can intercept the Electron updater.

The M2 had Parall 2.4.0 and 11 legacy Claude shortcut bundles, with all 11
existing ParallDataStorage settings mapped to their correct distinct account
directories. Parall's newer native-launch handling requires **updating the
vendor application AND editing/saving each existing shortcut in place**;
updating the app alone does not rebuild old shortcuts. The App Store CLI
attempt was denied with ISErrorDomain -128 (No purchase was requested), and
must not be silently retried under another account/carrier.

For a human-authorized maintenance window, first upgrade Parall through its
own signed-in App Store account. Preserve each original app name, bundle
identity, shortcut destination and data storage path; do not delete any
Application Support directories. On the M2, the private read-only manifest
and 11 hash-verified wrapper backups are held under
/Volumes/Mastermind 2/evidence/claude-parall-isolation-20261019-v2/.
Prove one idle shortcut's new launcher opens exactly its own storage profile
before updating the remaining shortcuts one by one. Do not regenerate an
active numbered Claude account or terminate PID 82118 just to silence an
unattributed process; first reconcile account and unsaved session state.
The 2026-10-19 native updater mechanism remains a **separate vendor
dependency** until this is completed and observed in use.

## Remote-use boundary

This handoff is local to the Mac that runs Claude Desktop. It is the path for remotely commanding the M2 to open an M2-local Desktop session.

For a Claude Desktop UI running on a travel MacBook while code executes on the M2, use Claude Desktop's separate SSH environment feature. Anthropic does not support `--desktop` handoff from an SSH-hosted Claude Code session into a different machine's Desktop app.

## 2026-10-01 M2 proof

A live canary on `m2studio` used the isolated 2.1.285 runtime against an existing dormant Mastermind Claude Code session. The production bridge contract returned:

```text
ok=true
action=opened_desktop
provider=claude_code
verified=true
```

No model prompt, provider message, account mutation, or Executive worker-binary change was made by the canary.

## Outcome and interruption semantics

The existing seven-field OpenOutcome response remains the interface. As defined
by the shared navigation contract, `verified=true` proves native session
existence plus an accepted handoff. It does not prove visible app state,
execution ownership, a model turn, or a completed mission.

`failure_kind=effect_unknown` means the handoff command was invoked but its
successful completion could not be established. The app may already have opened:
inspect the original bound session before retrying. An explicitly observed
process-start failure remains `runner_error`. Missing or malformed receipts,
truncated output, timeouts and lost responses do not prove non-delivery.
Neither the adapter nor the browser automatically repeats a handoff. The normal
button retains an accessible inline uncertainty/failure message rather than
refreshing it away; a lost HTTP response is also displayed as unknown.

The PTY runner retains only its bounded output prefix while draining the child.
Post-exit draining uses the same deadline as normal capture. On timeout/error it
signals its own private process group and uses two bounded reap waits. Its
`process_reaped` fact covers the direct child only; it is not proof of Desktop
termination or of no navigation effect. Invalid timeout/output bounds refuse
before opening a PTY. This does not change the ordinary non-PTY runner.
