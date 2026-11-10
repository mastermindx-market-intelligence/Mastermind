# LANE_HERMES — Director B2 (gateway code-pin policy)

Owner: Director B2, Hermes-native lane (successor of Director B on this seam),
Fable COO principal. Worktree branch `t3/hermes-code-pin-policy` (local only;
no push, no PR — integrator owns publication). All observations below were
read-only; nothing under `~/.hermes` was edited, restarted or reconfigured.

## 1. Observed live facts (2026-11-09, m2studio)

Probe method: reproduced `NativeRuntime.identify()` exactly — one line
`{"protocol":1,"id":1,"verb":"identify"}` over the private control socket via
`hermes_cli.gateway_client.private_control_query` (same 3 s budget), plus
read-only reads of the gateway's own state files, `ps`, and git in
`~/.../hermes-agent`.

- Gateway pid **75879**, `gateway run --quiet`, started Sun Nov 8 14:33:54 2026
  (~16 h up at observation time). Lock and `gateway_state.json` agree; the
  state file was live-updating (fresh `updated_at`).
- **The identify RPC does not answer.** Two probes (3 s bridge-faithful, 20 s
  diagnostic budget) both connected to `~/.hermes/gateway.sock` and then timed
  out at recv. The socket holds 5+ established connections; the handler
  (`gateway/control_socket.py`, byte-identical across `2bd378ed`, `09ccb0db`,
  `ba4ddf99`) dispatches through the shared default executor, so a
  blocked/saturated pool stalls new answers. Consequence: today the bridge
  fails every operation at identify with `UNAVAILABLE`/`NATIVE_UNAVAILABLE`
  (generic timeout path), *not* with the source-changed refusal.
- **Served code identity** (from the gateway-written `gateway_state.json`,
  which stamps `get_code_identity()` — cached process-wide at first call, i.e.
  the startup snapshot): `code_sha 09ccb0db84968b92821568bb9adb78efbf0b5ff1`,
  `code_version 0.23.0`. That commit is *neither* the pin `2bd378ed…` *nor*
  the checkout HEAD — the running gateway predates both advances.
- hermes-agent checkout: HEAD `ba4ddf9945a2…` ("test(delegation): pin service
  scope…"), pinned commit `2bd378ed1b…` = the `v0.23.0` tag checkout.
  Working tree is dirty (88 modified files) but **none of the pinned files**.
- **Pinned file hashes** (all four sets): every pinned hermes-agent module
  (recovery 3, history 8, roster 2, capacity 2 in-repo, `model_tools.py`) and
  the OMH plugin pins are **byte-identical at the working tree, at
  `2bd378ed`, and at HEAD `ba4ddf99`**. The only real drift is
  `~/.hermes/bridges/fabric_capacity_mcp.py`:
  live `242c19aec6f1…` ≠ pin `4d3f88a1b0ef…` — so `readonly_capacity_qualified()`
  is already False today on genuine file drift, correctly, independent of the
  commit question. (Capacity `canSend` degrades; roster/recovery unaffected.)
- Documented pin rationale (profile `mmos/LANE_HERMES.md` + Director B ledger
  open issue 3): the commit equality was intended fail-closed behavior after
  hermes updates, with the known cost that "a hermes update will produce
  `NATIVE_ROSTER_SOURCE_CHANGED` until re-pinned". The profile lane docs
  (`~/.hermes/profiles/engineering/mmos/LANE_HERMES.md`, `TEAMLINK_CENSUS.md`)
  document the lane/seam context; neither names the commit literal.

Net diagnosis: the commit literal is a proxy that fires on every commit
advance even when the mechanism (imported file contents) is unchanged, while
the actual mechanism pin (file hashes) already does the real work and already
caught the one genuine drift.

## 2. Policy implemented (chosen: allowlist tripwire + version line; file hashes are the only hard source gate)

In `app/mastermind_os/src-tauri/src/hermes_native/bridge.py`:

- New module constants, each literal exactly once:
  `GATEWAY_CODE_PINS = {"2bd378ed1b…", "ba4ddf9945a…"}` (explicitly qualified
  generations — the #2180 qualification and the 2026-11-08 advance, whose
  pinned mechanism files are byte-identical) and `GATEWAY_CODE_VERSION =
  "0.23.0"`.
- New `NativeRuntime.gateway_code_qualified()`: a pinned commit passes; any
  other **well-formed** 40-hex `code_sha` passes **only while the identify
  answer still reports the qualified version line**. Missing/malformed
  `code_sha`, or an advance onto a different version line, is not qualified.
- The four former call sites (`require_recovery_source`,
  `require_roster_source`, `readonly_capacity_qualified`,
  `readonly_omh_qualified`) all call that one helper; the hard-coded literals
  appear nowhere else.
- Refusal semantics, mechanism-first: a pinned **file hash** mismatch (or a
  pinned file that disappeared) refuses `NATIVE_RECOVERY_SOURCE_CHANGED` /
  `NATIVE_ROSTER_SOURCE_CHANGED` / history code / capacity-False **before the
  code-identity question is even asked**, so real drift is never masked by an
  identity technicality — regardless of which commit the gateway answers.
  Only when the imported bytes match does the identity gate run: an
  unqualified generation (well-formed sha off the version line, or a
  missing/malformed identity) is a distinct typed
  `NATIVE_GATEWAY_CODE_UNQUALIFIED` (or `False` for the two read-only
  qualifications) so the integrator can tell "re-pin the files" from
  "gateway generation outside the qualified line". No new envelope state, so
  `src/hermes-native/contract.ts` needed no change (`code` is a free-form
  `[A-Za-z][A-Za-z0-9_]*` field; `sourceRevision` already surfaces the live
  gateway commit to the UI).
- `identify()` now records `observed_version` next to `observed_code`.
- The inline pin dicts were lifted to module constants
  (`RECOVERY_SOURCE_PINS`, `HISTORY_SOURCE_PINS`, `ROSTER_SOURCE_PINS`,
  `CAPACITY_SOURCE_PINS`) — same digests, same resolved paths; this is the
  established test seam (`OMH_READONLY_PINS` pattern) and keeps the diff
  additive. `CAPACITY_SOURCE_PINS` keys are home-relative so the fabric
  bridge pin lives in the same table.

Why this shape (vs the alternatives): dropping the identity question entirely
(option b pure) would accept any gateway that answers nothing about its
generation; keeping the exact literal (status quo / option c) refuses every
unrelated advance and is what the gap audit flagged. The chosen rule accepts
exactly the advances that cannot change this adapter's mechanism
(byte-identical pinned files, same version line) and still fails closed on a
version-line change — the honest boundary of what this adapter was qualified
against. The commit allowlist itself is the fast path and the audit record of
which generations were verified.

## 3. Tests

New `tests/test_hermes_native_gateway_code_pins.py` (9 tests): pinned
generation qualifies without a version answer; **commit advance with
identical file hashes does not refuse**; **file-hash drift refuses for pinned
and advanced commits alike** (recovery + roster); advance onto a different
version line is refused with `NATIVE_GATEWAY_CODE_UNQUALIFIED` across all
four gates; **file drift outranks an unqualified code identity**
(SOURCE_CHANGED wins); missing/malformed identity refused; capacity contrast
test (control qualifies with fixture pins + config, drift removes it,
unqualified code removes it); `identify()` records sha + version
(wire-shaped fake); source-shape test that each literal occurs exactly once
and all four gates read the helper.

Updated `tests/test_hermes_native_os_bridge.py` literal usages to the
constant; the upgrade/tamper test now proves the mechanism-first refusal for
an unqualified code, a pinned code and a well-formed advance alike.

Results:
- `env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q` on
  `test_hermes_native_os_bridge.py`, `test_hermes_native_os_history.py`,
  `test_hermes_native_gateway_code_pins.py`,
  `test_team_roster_projection.py`,
  `test_session_bridge_native_continuity.py`,
  `test_hermes_h4_native_preparation.py` → **99 passed, 79 subtests passed**.
- `cd app/mastermind_os && npx vitest run src/hermes-native` → **91 passed
  (91)** after `npm ci` in the fresh worktree.
- `MM_SOURCE_REVISION=$(git rev-parse HEAD) MM_BUILD_IDENTITY=b2-local
  MM_NATIVE_REFRESH_ENABLED=1 cargo test --locked --all-targets
  --manifest-path app/mastermind_os/src-tauri/Cargo.toml` → **264 passed,
  0 failed (8 ignored) + 14 further tests passed, exit 0**, run against the
  final bridge.py (re-run after the last edit; core.rs embeds bridge.py via
  `include_str!`).

## 4. What the integrator must do before the next gateway restart

The restart itself is Hermes-owned; this lane restarts nothing.

1. Nothing is required for roster/recovery to survive the restart at current
   HEAD: `ba4ddf99` is pinned and all mechanism files match, so after the
   restart `team_roster`, history and recovery paths qualify as soon as
   identify answers again.
2. The **live control socket not answering identify** is the real outage to
   fix at restart time: with the listener wedged, every bridge operation
   returns `NATIVE_UNAVAILABLE`. If the restart does not clear it, inspect
   the blocked executor/held connections in the new process before touching
   pins.
3. `fabric_capacity_mcp.py` drifted (`4d3f88a1b0ef…` pinned → `242c19aec6f1…`
   live). Read-only capacity `canSend` stays correctly disabled until the
   integrator either re-qualifies the new bridge content (update
   `CAPACITY_SOURCE_PINS`) or restores the pinned content. This is a real
   mechanism decision, deliberately not auto-accepted here.
4. On the next Hermes advance that changes a pinned file, expect the
   `NATIVE_*_SOURCE_CHANGED` refusals again — that is the mechanism working;
   re-pin by reviewing and updating the single constants block. On a
   version-line bump (0.24.x), expect `NATIVE_GATEWAY_CODE_UNQUALIFIED` until
   this adapter is re-qualified for the new line.

## 5. Receipts

- Branch `t3/hermes-code-pin-policy`, single commit (see git log for sha).
- Files changed: `bridge.py` (policy + constants), the two bridge test files,
  new `tests/test_hermes_native_gateway_code_pins.py`, this ledger.
- No secrets or user-home paths in the commit; live paths are recorded as
  `~`-redacted here only.

— Director B2, 2026-11-09.
