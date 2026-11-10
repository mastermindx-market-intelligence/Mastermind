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

## Built-in T3 preview workflow

For an authorized development URL, use `preview_open` and retain the returned preview identity. Use `t3_preview_list` or `preview_status` to recover an existing preview instead of opening duplicates. Read each tool's live schema; preview identifiers and fleet browser identifiers are not interchangeable.

Use `preview_snapshot` to ground an interaction. For `preview_act` click and type actions, put the latest snapshot's reference in `locator`, formatted as `aria-ref=OBSERVED_REF`. The generic tool's `target` field is a drag destination. Supply the targeting fields for the selected action and retain the exact `tabId`.

To replace an editable field, use `type` with its fresh `locator`, the intended `text`, and `clear: true`. This fills the identified control directly; omit a preliminary focus click. Replace these symbolic values with the current observation:

```json
{"action":"type","tabId":"OBSERVED_TAB_ID","locator":"aria-ref=FIELD_REF_FROM_LATEST_SNAPSHOT","text":"EXPECTED_VALUE","clear":true}
```

After every successful input, take a fresh `preview_snapshot` before the next input. This includes a click used only to focus a control. Verify the field value or page state and use references from that new snapshot:

```json
{"action":"click","tabId":"OBSERVED_TAB_ID","locator":"aria-ref=BUTTON_REF_FROM_NEW_SNAPSHOT"}
```

Take another snapshot and verify the intended result. For `Provide exactly one target`, check the action-specific targeting fields. For `requires an editable target`, first check that the field was supplied through `locator`; the message alone does not establish that the observed field is disabled or read-only. Observe the original field using a fresh snapshot and, if needed, a bounded read-only `preview_evaluate`. Once the original outcome is reconciled, correct the arguments and make one freshly grounded attempt. Do not guess a focus click, alter the field's editability, or use evaluation to perform the input. Preserve the no-replay rule for uncertain effects.

Handle an expected dialog through `preview_dialog` and use `preview_resize` to check the requested viewport. Close only this task's preview through `t3_preview_close` after saving the result, then verify its absence with `t3_preview_list`. Keep unrelated previews and active development sessions intact.

On Linux, T3's existing server preview uses its own managed, verified Chrome Headless Shell, installed on first use. Diagnose sandbox, system-library or font errors through the installed `t3 browser setup --base-dir ACTUAL_T3_HOME` owner. If it reports an administrative prerequisite, use the existing authorized administration route; preserve any actual refusal. Keep Chrome's sandbox enabled. Do not select an unrelated cached browser or create a replacement launcher to hide a dependency failure. Setup success and a working preview are separate checks.

Preview input runs in its own browser surface and ordinarily needs no physical mouse takeover. It does not grant access to a fleet profile's authentication or native OS dialogs; use the route that owns those tasks.

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
