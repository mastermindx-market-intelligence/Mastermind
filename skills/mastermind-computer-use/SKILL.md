---
name: mastermind-computer-use
description: Operate native macOS apps from T3 using the installed quiet Peekaboo MCP tools. Use for screenshots, native windows, clicking, typing, scrolling, UI verification, permission diagnosis, and requests to work without taking over the user's mouse.
---

# Native apps without taking over the desktop

Use the installed `peekaboo` MCP server for native macOS windows. Use `mastermind-browser-use` for web page content and T3 preview tools for development previews. Prefer a purpose-built API or CLI when it directly accomplishes the task.

## Establish the actual execution surface

Discover the current tools before claiming capability. In T3, provider instances have separate configuration homes; the selected model's name does not identify its tools or computer. Remote environments execute on their own hosts. Resolve the target host, app process and exact window; do not assume the viewer Mac is the executor.

The qualified shared-Mac path is the existing quiet adapter backed by signed Peekaboo 4.9.8. It uses local execution and its own permission context. The unqualified `peekaboo` command on PATH may be older. Do not substitute it after an error or claim the GUI app's version is the CLI version.

Call `permissions` once when needed. Screen Recording, Accessibility and Event Synthesizing are distinct. A successful capture does not prove clicks work. An explicit OS/tool denial is a real boundary: report the specific missing grant and actual sender. Do not alter TCC, replace signing identities, use `cliclick`, AppleScript or another carrier to replay a denied action.

## Observe, act once, verify

1. Use `app` / `window` with `action: "list"` to locate the intended app and window. Prefer an exact PID and `window_id` over a broad title. For the installed `window` tool, pass a process as `app: "PID:OBSERVED_PID"`; a bare numeric string can be interpreted as an app name.
2. Call `see` or `inspect_ui` with that exact window. Request `include_elements: true` when useful. Read the screenshot and accessibility tree; copy the returned opaque snapshot and element IDs exactly.
3. Prefer `set_value` for an intended field replacement, `click` for a button, or `type` for text entry. Supply the fresh `snapshot` and target `on` element. Keep clicks background; global coordinates and foreground flags are not available through the quiet adapter.
4. Observe again after each mutation before using another element ID. A changed page, window bounds, focus or process can invalidate the earlier snapshot.
5. Verify the intended value or state with `verify_state`, a fresh observation or an app-native read. Tool dispatch, exit zero and a screenshot file's dimensions are not success evidence.

Examples use symbolic IDs: replace them with actual values from the current observation.

```json
{"action":"list","app":"com.apple.TextEdit"}
{"window_id":123,"include_elements":true}
{"snapshot":"OBSERVED_SNAPSHOT","on":"OBSERVED_FIELD","value":"Intended text"}
{"window_id":123,"pid":456,"predicates":[{"kind":"element_value","selector":{"identifier":"OBSERVED_IDENTIFIER"},"expected_value":"Intended text"}]}
```

These are arguments for `window`, `see`, `set_value` and `verify_state`, respectively. Read the current tool schema; do not translate CLI flags into MCP fields. Generic AX actions have different background rules: prefer the dedicated `click` tool rather than assuming `AXPress` is always background-safe.

## Mouse, focus and shared-state discipline

Background native input can avoid moving the physical pointer or activating an app for supported controls. It is not a universal independent macOS mouse. Two agents must not concurrently edit the same field or window even when both are background-safe. Retain the existing operation's target ownership; do not create another lock service or registry.

The quiet adapter deliberately excludes global pointer movement, drag, app/window manipulation, clipboard paste and global keyboard chords. If an app requires those operations, record the missing capability and use an independently authorized dedicated fleet desktop for NEW work, or an explicitly coordinated attended action through its existing owner. Do not silently widen this server or retry a refused/uncertain action through a different tool.

For a noninterference claim, measure the frontmost app and pointer before and after the actual action. Pointer restoration afterward is not isolation. If the user moves the pointer during a test, report the observation without attributing that movement to the tool.

## Recovery and completion

On a timeout, `EFFECT_UNKNOWN`, or Peekaboo's `dispatched_unverified` / `effect: "unverifiable"`, retain the original session, snapshot, target and request. A tool result can have `isError: true` while also reporting `mutation_dispatched: true`; do not interpret that as no effect. Observe the original target with `verify_state` or a fresh exact-window capture before deciding on the next action; do not replay the input. If `verify_state` explicitly requires another identical predicate observation to settle incomplete evidence, repeat that read only. A stale-target refusal permits a fresh read, not a blind replay or target substitution. An explicit permission refusal remains binding.

When MCP is absent, distinguish missing configuration, an unrefreshed agent session, startup/protocol failure and permissions. The qualified server supports MCP `2025-03-26`. Configuration changes affect fresh agent sessions; preserve running work. T3's **Restart agent session** keeps conversation history, but use it only when the target thread is idle and it is appropriate to restart its agent.

Report the observed result, host/window, tool route and remaining limitation. Treat installation, tool discovery and live action proof as separate facts.
