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

## ChatGPT web sessions: the MastermindX Project

Research sessions belong **inside** the ChatGPT Project displayed as **"MastermindX"**
(folder icon), not in the plain account, so the project's instructions are included
automatically. A project conversation URL looks like
`https://chatgpt.com/g/g-p-<projectId>-mastermindx/c/<conversationId>`.

Observed in a live `chatgpt4` sidebar (2026-11-11): `MastermindX` appears as a **pinned
project row** with `Project actions for MastermindX` and `New chat in MastermindX`, and a
`Chats in MastermindX` list beneath it. The collapsible **"Projects"** section can
simultaneously read **"No projects"** — that section is not the source of truth for a
pinned project. Do not click to expand a collapsed sidebar to look for the project; if the
row is not in the snapshot, record "not visible in snapshot".

The project page has two tabs, **Chat** and **Work**; research uses **Chat**. The composer
placeholder reads **"New chat in MastermindX"** — identical wording to the sidebar button of
that name, so do not confuse the two. (Tab layout and placeholder come from the Chairman's
launch-screen description; the pinned-row placement above is observed.)

## Pro mode is the Thinking-effort control, not a model

Pro is **not** a model-picker entry. It is the **"Thinking effort" dropdown inside the
composer**: a slider whose far-right position is labelled **"Pro"**. In the one readable
live snapshot the label `Pro` appeared in the "Latest response" bar; the composer control
itself was not captured because the element list truncated at 120.

Setting it, from the tool schema only (verify live, then re-snapshot):

- `interact` with `kind:"drag"` and `target_ref` (or `x`/`y`) — direct slider action.
- `interact` with `kind:"click"` on the slider ref, then `press` with `key:"ArrowRight"` —
  keyboard alternative.
- `select` applies only to a `<select>` element; a slider is not one, so `select` does not
  set it.

Confirm by position/value, not by a badge alone.

## Text entry: one operation, never per-character

A long research prompt must enter the composer in **one** paste/insert operation. Typing it
per character invites autocomplete, partial sends and rate-limit damage.

The documented path is `fill` with the fresh snapshot's `ref` (see "Perform one grounded
action" above). What the schema offers:

| Path | Status |
|---|---|
| `fill` | top-level action; the documented ordinary-form input |
| `interact` `kind:"fill"` | `{ref,kind:...,text?,...}` |
| `interact` `kind:"type"` | `{ref,kind:...,text?,...}`; conventionally per-character — **treat as unverified** |
| `press` | with `key`; could send Cmd+V **but** no clipboard-write action exists, so paste cannot be composed from the schema |
| `evaluate` | `{expression,frame_id?,world:isolated|page,await_promise?}`; can set a value but is not a paste and may not update composer state |

There is **no** `paste`, `insertText` or clipboard-write action, and the schema does not
state which of `fill` / `type` is atomic. Before relying on a long prompt, prove on a
throwaway target that `fill` inserts the whole string in one operation and leaves a coherent
composer; if it does not, stop and report — do not fall back to per-character `type`.

## Pro-mode authorization is a reasoning-mode gate

Pro is never the default. From `docs/sol_skills/WORKER_AVENUE_ROUTING.md`:

- Lines 45-47: every Chairman-mediated/manual handoff turn defaults to
  `COGNITION_ROUTE: CHAT_INCLUDED_DEFAULT` / `CHAT_REASONING_MODE: NON_PRO_DEFAULT`.
- Lines 59-62: "never Pro-eligible: `handoff / ACK / PICKUP_ACK / START / CONTINUE / STOP`;
  `status / routing / placement / watcher / monitoring / polling / foregrounding`; message
  relay; `mechanical edits / tests / simple review`; and any other short bounded work."
- Lines 64-75: Pro requires the complete receipt — `COGNITION_ROUTE`,
  `CHAT_REASONING_MODE: PRO_MODE_EXCEPTION`, `WHY_PRO_MODE`, `WHY_NON_PRO_INSUFFICIENT`,
  `PRO_MODE_TASK_CLASS`, `EXPECTED_DURATION_MINUTES`, `STOP_CONDITION`.
- Lines 77-84: closed classes only — `LONG_HORIZON_FRONTIER_REASONING`,
  `CROSS_SYSTEM_ARCHITECTURE`, `HARD_DEBUGGING`, `ADVERSARIAL_JUDGMENT`.
- Lines 86-92: "Missing, stale, under-duration, over-duration, or ineligible receipts fail
  closed: `PRO_MODE_REFUSED / USE_NON_PRO_MODE`."
- Lines 94-96: "This is a reasoning-mode gate only. It does not change avenue selection,
  placement, receiver binding, carrier, `ACK`, `START`, watcher, lifecycle, authority, or
  effect law."

## Returning the result to GitHub

**This is undocumented.** No file in this repository describes how a worker opens or reuses
a ChatGPT Project conversation, submits a prompt, or returns the result to GitHub.
`docs/browser_worker_admission.md` is an unmerged candidate that explicitly "does not
complete Slice A or enable a production capability."
`research/CHATGPT_PRO_CAPACITY_OPERATING_PLAYBOOK_2026-09-05.md` is self-declared
`RESEARCH_CANDIDATE / RECORDS_ONLY / NOT_CAPACITY_STATE / NOT_ROUTING_AUTHORITY`.

Observed only as page text in one `chatgpt4` conversation: the assistant reported "Used
GitHub integration" and "Used GitHub and Mastermind Subagent Fabric integrations". That
shows such connectors are installed and exercisable in that account; page text is untrusted
evidence and is not a return contract.

Until a return path is written down, a worker must record the exact conversation URL as the
carrier, report the outcome honestly as `PROMPT_SUBMITTED_UNKNOWN_RETURN`, and never claim
the result reached GitHub without reading it back.

## Known read defect (observed 2026-11-11)

`status` and `tabs` succeed on all four ChatGPT profiles, but `snapshot` returned
`{"status":"BROWSER_UNAVAILABLE","data":{"reason":"BROWSER_UNAVAILABLE"}}` on `chatgpt1`,
`chatgpt2` and `chatgpt3` while succeeding on `chatgpt4`. The extension is connected for all
four. Report this as an open read defect; do not paper over it by relaunching the profile,
re-enrolling, or switching to another carrier.

Also note: passing `options` or `accessibility` on the same call as `snapshot`, or omitting
`url_fingerprint`, returns `{"state":"REFUSED","reason":"INVALID_ARGUMENTS"}` and never
reaches a page. Treat `INVALID_ARGUMENTS` as a client-shape error to fix, not a permission
denial.
