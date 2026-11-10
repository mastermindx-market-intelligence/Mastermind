---
name: mastermind-browser-use
description: Control authorized browser tabs across the Mastermind fleet from T3 with the existing mmx-browser MCP extension bridge, or test a local web app with T3 preview tools. Use for browser navigation, DOM/forms, screenshots, frames, console/network inspection, uploads/downloads, and noninterfering browser input.
---

# Choose the browser that owns the task

| Task | Existing route |
| --- | --- |
| Build or test a local web app | T3 preview/browser tools and that development session's browser |
| Use an authenticated fleet profile or its existing tabs | `mmx-browser` MCP tool `mmx_browser` |
| Native app, browser toolbar or OS dialog | `mastermind-computer-use` and its exact native window |
| Structured service operation with an appropriate API | The service's existing connector or CLI |

Do not create another CDP listener, browser launcher, profile clone, credential store or browser registry. The Mastermind Browser extension, installed native host and existing bindings own fleet browser identity and transport. T3's private preview is a different browser from the user's Chrome profile.

## Discover and bind

1. Call `mmx_browser` with `{"action":"browsers"}` and, when needed, `{"action":"hosts"}`. Inventory membership or `LOADED` does not prove an active connection.
2. Select the authorized host/profile using returned `host_ref`, `browser_id` and label. Preserve exact identity; never pick the first, newest or personal/default profile merely because it is available. Do not print account details unnecessarily.
3. Call `status` on that browser, then `tabs`. Retain returned connection identity and the exact task tab. Use `options: {"probe": true}` on inventory only when a live census is actually needed; it can contact remote hosts.
4. For an existing tab, call ordinary `snapshot` first with the exact connection, tab and URL fingerprint. Advanced `dom`, `accessibility` and `locate` require an attached CDP session; they cannot bootstrap it. Preserve the returned snapshot/reference IDs and frame identity. A tab ID alone is insufficient after navigation or reconnection.

Minimal discovery examples (substitute actual returned IDs):

```json
{"action":"browsers"}
{"action":"status","host_ref":"OBSERVED_HOST","browser_id":"OBSERVED_BROWSER"}
{"action":"tabs","host_ref":"OBSERVED_HOST","browser_id":"OBSERVED_BROWSER","connection_id":"OBSERVED_CONNECTION"}
```

## Perform one grounded action

For ordinary forms, use `click` / `fill` / `select` with the fresh snapshot's `ref`. Every action after `status` needs `connection_id`; tab actions also need `tab_id` and `url_fingerprint`. Ordinary input additionally needs `snapshot_id` and `ref`. The installed bridge rejects unexpected or missing fields, so do not send empty optional arguments indiscriminately.

For advanced browser work, follow the actual attachment lifecycle:

1. Obtain an ordinary `snapshot` of the exact task tab.
2. Call `cdp_attach` with that same tab identity, its fresh `snapshot_id`, and `options: {}`. Verify the returned attachment; attachment consumes the ordinary snapshot. Never invent a snapshot ID to get around a failed read.
3. Use bounded advanced reads such as `frames`, `dom`, `accessibility`, `locate`, `network` and `events`, with their required `options` object. These reads do not take the ordinary `snapshot_id`. A `CDP_SESSION_REQUIRED` result is a missing prerequisite, not a reason to attach an ambient debugging port.
4. Before advanced mutation, obtain a fresh ordinary snapshot and a fresh semantic node reference for the same document. `interact` takes the node `ref` inside `options`, alongside `kind`; the ordinary `snapshot_id` stays at the top level. Each mutation consumes its ordinary snapshot. Re-observe the actual result before another action.
5. Use `cdp_detach` with the same connection/tab/URL identity and `options: {}` when this task is finished. It does not require a snapshot. Verify cleanup before closing this task's tab.

For frames, explicitly bind the observed `frame_id` in the advanced locator/read options; do not guess iframe offsets or reuse a reference in another frame. A Chrome API failure during ordinary snapshot blocks the dependent attachment/input sequence until diagnosed. It does not authorize changing browser grants or substituting another execution route.

Read the live schema. The installed bridge includes snapshots, screenshots, DOM/accessibility, locators, frames, events, network/response-body observations, dialogs, uploads/downloads, capture/PDF and controlled CDP. Tool exposure is not evidence that the selected host/profile grants every action. `cdp_attach`, browser focus/launch, file access and extension/site access can have separate consent or ownership requirements.

Prefer DOM/state assertions for correctness and screenshots for appearance. Use `capture` for full-page evidence when supported. Read the expected form value, URL, element state, saved object or download receipt after an action; a click receipt alone is not completion. Keep payloads small with result pagination and bounded network/event queries.

For uploads, use files on the actual execution host within the adapter's approved roots. A local path on another host is not an upload. Verify download identity and location; keep private content and authentication data out of logs and shared artifacts.

## Noninterference and concurrency

Page-local browser input normally avoids the physical desktop pointer. It does not make sharing the same tab safe. Keep one modifying operation on its existing tab/connection and use a separate task-owned tab when appropriate. Ask for focus only if the task actually requires visible foreground interaction. Do not activate a tab, switch Spaces or move native windows just to read content.

Native app foreground-only tasks belong on an independently authorized dedicated worker desktop. Drawing or restoring a cursor is not a second mouse. Never move an already-started or unknown operation to another host to evade its state or permission boundary.

## Exact recovery

Distinguish offline host, closed browser, unconnected extension, missing site permission, stale connection/reference, protocol failure and unknown effect. Preserve the original request and use `result` or an original-target observation before any decision after a timeout. Do not automatically replay input, reattach a different profile, or alter Chrome Preferences, startup flags or extension consent to make a refused action succeed.

Extension-owned **Load unpacked**, page-controls/site-access and browser/OS permission ceremonies must use their legitimate owner. Report only the exact missing step after exhausting useful independent work. A stale installed environment note is not a live fleet census.

Clean up only tabs/artifacts this task created, and only after the outcome is verified. Leave pre-existing tabs, other agents' work and the user's browser session intact.
