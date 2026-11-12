# Real peekaboo captures (BCU panel, fields 1-9)

All files are real output of `/opt/homebrew/bin/peekaboo` 4.2.2 on 2026-11-11,
taken from this lane's own fixture window (`BCU slice fixture`, tkinter under
/usr/bin/python3, window id 98889). No other application's window content,
title, or path is included.

| file | source command | what the code reads from it |
|---|---|---|
| `see_fixture_window.json` | `see --window-id 98889 --json --no-remote` | `application_name` (top level), `window_title`, `ui_elements[]` (`id`, `role`, `label`, `bounds`), `coordinate_context.logical_bounds`, `snapshot_id`, `is_dialog`, `interactable_count` |
| `window_list_fixture.json` | `window list --pid 49829 --json --no-remote` | per-window `window_id`, `is_frontmost`, `is_key`, `window_index`, `bounds`, `window_title`, `layer`; `target_application_info` |
| `app_list_sanitized.json` | `app list --json --no-remote` | per-app `name`, `bundle_id`, `pid`, `is_active` (frontmost-app marker), `is_hidden`. Sanitized: filtered to a few innocuous entries — the shape matters, not the census |
| `ioreg_hididle.txt` | `ioreg -c IOHIDSystem` | `HIDIdleTime` (nanoseconds) — the presence gate input |

Sanitization performed: base64 screenshot payloads stripped from the `see`
capture (`screenshot_raw` / `screenshot_annotated` replaced by a size note);
`app list` filtered as above. Nothing else was altered; field names and
structure are exactly as emitted.

Later act captures (idle window, own fixture, 2026-11-11):

| file | source command | what it shows |
|---|---|---|
| `press_foreground_required_error.json` | `press Return --pid 49829 --json --no-remote` (no `--foreground`, no window receipt) | the foreground-consent refusal: `success:false`, `INTERACTION_FAILED`, "Raw key presses require explicit foreground consent unless a fresh exact receipt pins background delivery.", `mutation_dispatched:false` |
| `type_background_receipt.json` | `type "FG-PROBE" --pid 49829 --window-id 98889 --json --no-remote` | exact-window targeting permits native background dispatch: `deliveryMode:"background"`, `targetPID`, `targetWindowID`, `typedText`. NOTE: peekaboo reports success, but the fixture's Tk event log shows no FIELD line for this input — background-native typing did not fire the fixture's Tk `<<Modified>>` bind in this run. Delivery-verification therefore relies on the paste path (which the original live slice rehearsal verified) or on `set-value`, not on background `type` alone. |

Also learned from the same window (shape facts, no captures needed):
`see --no-screenshot` requires `--tree` (`VALIDATION_ERROR` otherwise) —
`see --tree` is the screenshot-less mode; `press` takes positional chords
(`press [<chord> ...]`), not `--on`; `--app Python` is ambiguous across
several Python processes — `--pid` is the stable targeting form; there is
no cross-app `window list` (requires `--app` or `--pid`).

Paste captures (idle window 2, own fixture, 2026-11-11):

| file | source command | what it shows |
|---|---|---|
| `paste_background_unconfirmed.json` | `paste --text … --pid 49829 --window-id 98889 --json --no-remote` | background paste refusal: `INTERACTION_FAILED` "Background text paste did not return a confirmed outcome.", **`mutation_dispatched:true`** — the post-dispatch uncertainty shape (H1). The pasteboard WAS restored to prior content afterward (M13). |
| `paste_foreground_unconfirmed_but_delivered.json` | same + `--foreground` | `INTERACTION_FAILED` "Paste hotkey did not return a confirmed outcome.", `mutation_dispatched:true` — **while the fixture log shows `FIXTURE FIELD CAPTURE-PASTE-FG`, i.e. the input landed.** Peekaboo can report an unconfirmed outcome for delivered input; the server must classify this as `EFFECT_UNKNOWN`, never `NOT_APPLIED` (decisive H1 evidence). |

M11 leading-dash argv captures (idle window 2, own fixture, 2026-11-11) —
peekaboo consumes `--text -rf /` as an option token; the `--text=VALUE`
equals-form is required and then delivers the text literally:

| file | source command | what it shows |
|---|---|---|
| `paste_leading_dash_space_form.json` | `paste --text -rf / --pid 49829 --window-id 98889 --json --no-remote` | the space form is consumed as an option token: `VALIDATION_ERROR`, missing `--text` value — the adapter must emit `--text=VALUE` |
| `paste_leading_dash_equals_form.json` | `paste --text=-rf / --pid 49829 --window-id 98889 --json --no-remote` (background) | equals-form accepted: the refusal is the H1 background-unconfirmed shape, not a validation error |
| `paste_leading_dash_equals_foreground_delivered.json` | same + `--foreground` | delivered: fixture log shows `FIXTURE FIELD -rf /` verbatim — equals-form pastes leading-dash text literally |

M10 chord-press capture (idle window 3, own fixture, 2026-11-11):

| file | source command | what it shows |
|---|---|---|
| `press_chord_window_background.json` | `press enter --window-id 98889 --json --no-remote` (no `--snapshot`) | rc=0 `success:true`, `deliveryMode:"background"`, `outcome.state:"dispatched_unverified"`, `mutation_dispatched:true`, `retry_safety:"unsafe"` — a chord press on an exact window delivers without `--foreground` and without a snapshot receipt, and reports the effect as unverifiable. The server's `keys` path (which adds `--snapshot <fresh-id>`) behaves differently — that shape is the remaining M10 live probe. |

M13 element-click captures (idle window 4, own fixture, 2026-11-12) — the
Tk Send button is AX-VISIBLE but not AX-ACTIONABLE; no element-targeted
click delivers on this fixture under either input strategy:

| file | source command | what it shows |
|---|---|---|
| `click_actiononly_no_ax_element.json` | `click --on elem_1 --window-id 98889 --snapshot S --json --foreground --input-strategy actionOnly --no-remote` | rc=1 `INTERNAL_SWIFT_ERROR` "No accessibility element is available for action invocation", `effect:"unverifiable"` — nothing was invoked (pre-dispatch) → server maps to typed `ELEMENT_NOT_ACTIONABLE` / NOT_APPLIED |
| `click_snapshot_stale_refused.json` | `click --on elem_1 --window-id 98889 --json --no-remote` (no snapshot) | rc=1 `SNAPSHOT_STALE` with **`effect:"refused"`** — peekaboo's explicit pre-dispatch refusal marker; `_refusal_proven_no_mutation` honors it alongside `mutation_dispatched:false` |
| `click_synth_success_nodelivery.json` | same + fresh `--snapshot` | rc=0 `success:true`, `effect:"unverifiable"` — but the fixture logged NO `SENT` line: the synthesized element click reports success without firing the Tk button. Only a bounds coordinate click would fire it, which is DENY_OVERLAY-gated while Terminal is visible (by design) |
