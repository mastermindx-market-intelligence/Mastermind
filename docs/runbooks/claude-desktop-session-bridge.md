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
