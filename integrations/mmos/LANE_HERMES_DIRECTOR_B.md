# Lane: Hermes always-on team / gateway / roster projections — Director B ledger

Branch `t3/hermes-roster-continuity` (worktree `~/.t3/worktrees/Mastermind/t3-1b947585`),
base `bbfad42da`, program pin `~/.hermes/profiles/engineering/mmos/` (T3_HANDOFF_V2 §3
Director B). This file is the B5 handoff ledger: what changed, what is PROVEN versus
SOURCE_ONLY, the exact human/owner gates, and open issues. Nothing here grants runtime,
account, credential or release authority.

## Work packages delivered

| WP | Deliverable | State |
|---|---|---|
| B1 | Real roster projection `mastermind.team_roster/v1`: `control_plane/team_roster_projection.py` (canonical producer), `app/mastermind_os/src/hermes-native/team-roster-contract.ts` (fail-closed parser), `team_roster` native operation wired through the existing port pattern (`contract.ts` op union + `bridge.py` + `core.rs` one match arm) | DONE (source; see PROVEN vs SOURCE_ONLY) |
| B2 | Typed bot-conversation continuity on the #2180 native path: `app/mastermind_os/src/hermes-native/continuity.ts` + Python mirror `integrations/session_bridge/hermes_native_continuity.py`; `failureReason` enrichment from the producer's stamped `bot_failure_reasons` classification in `bridge.py` | DONE (source) |
| B3 | TeamLink shapes ADOPTED from `TEAMLINK_DESIGN.md` (it appeared mid-lane; the adopt path, not the PROPOSED fallback): `control_plane/teamlink_contracts.py` + TS mirror `app/mastermind_os/src/hermes-native/teamlink-contract.ts` — `TeamLinkMessage.v1` / `ContextPacket.v1` field names verbatim, no transport | DONE (source) |
| B4 | Fresh WO-19 read-only snapshot into `integrations/mmos/wo19/20261109T090353Z/` via the existing scripts (`--out` only; re-audited read-only before running) | DONE (live read-only observation) |
| B5 | This ledger + `DIRECTOR_B_SHARED_PATH_PROPOSALS.md` | DONE |

## What the code does (one paragraph each)

**B1 roster** — enumerates real Hermes profiles the way the agent's own roster mechanism
does (`tools.bot_mode_probe._roster` predicates mirrored: identity markers, `PROFILE_ID_RE`,
`.deleted-profiles` tombstones, infra dirs excluded). Gateway evidence per profile with a
strict evidence ladder: control-socket `identify` (carries `hermes_home`; a home mismatch is
`degraded GATEWAY_HOME_MISMATCH`, never ready) beats `gateway.lock` + live `ps` verification
(command-line shape AND process start time within 300 s — the WO-19 §6 recycled-PID pitfall);
no lock ⇒ `unknown NO_GATEWAY_LOCK`. Activity from each profile's `state.db` (read-only
sqlite `mode=ro`), `last_activity_at/description`; unobserved ⇒ `null` + typed reason.
Never a fabricated bot count; secrets (`auth.json`, `.env`) never opened; all emitted text
scrubbed. `bridge.py` exposes it as a **read-only** native op after pinning the hermes-agent
source (`observed_code` commit + sha256 of `bot_mode_probe.py` / `bot_failure_reasons.py`;
drift ⇒ `NATIVE_ROSTER_SOURCE_CHANGED`).

**B2 continuity** — separates WHY a conversation stopped into nine typed states
(`idle`, `turn_running`, `native_terminal`, `model_limited`, `gateway_busy`,
`viewer_disconnected`, `auth_changed`, `effect_unknown`, `unclassified`) instead of one
"error". Model 429/quota (`provider_rate_limit` / `provider_quota_limit`, taken ONLY from
the producer's stamped failure classification — never guessed client-side) is
`model_limited` with `retryPolicy: never_auto`. `effect_unknown` permits exactly one
continuation: recover the ORIGINAL operation key (the port replays the original
requestId+sessionId — it never mints a session or a fresh request id). Fresh send is legal
only from `idle`. Stop/steer are honestly declared `not_exposed_by_native_port` (the gateway
owns `prompt.cancel`/`prompt.steer_queued`/`session.interrupt`; the native port wires none).
Python mirror keeps `integrations/session_bridge` consumers on the same closed vocabulary.

**B3 TeamLink** — the design doc's actual schemas, not invented ones: the 15-field message
(WO-17 correlation block verbatim, all-nullable; `kind`/`intent` closed; body ≤4096;
refs-only `context_refs`; hop math) and the 12-field references-only context packet
(mandatory `EFFECT_UNKNOWN` rows; `source_revision`; ownership leases; expiring cache).
Pure rules encoded: deterministic `tlm-` id mint with fixed cross-language parity vectors,
same-key-changed-content ⇒ REFUSED, monotonic delivery chain with `unknown` OUTSIDE it
(never auto-retries; reconciles on the original operation key), hop breach + expiry kill
actionable chains, informational never wakes, echo guard, answers settle. **No transport,
queue, store or retry loop exists in this module — by design §6.**

## PROVEN vs SOURCE_ONLY

**PROVEN (run on this machine, this branch):**
- `env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest` on the acceptance set — **306 passed**:
  `tests/test_teamlink_contracts.py` (64), `tests/test_team_roster_projection.py` (21),
  `tests/test_session_bridge_native_continuity.py` (16), plus the pre-existing
  `tests/test_session_bridge_native*.py` set and `tests/test_session_bridge_installed.py`.
- `cd app/mastermind_os && npm ci && npm run typecheck` — green; `npx vitest run src/hermes-native`
  — **82 passed / 7 files** (5 new suites + pre-existing contract/port/panel suites).
- B4 artifacts are real script outputs reading the live profile home (read-only).

**SOURCE_ONLY (not proven live; needs the integrator):**
- `bridge.py` `team_roster` / `failureReason` behavior inside the Tauri app: the bridge is
  embedded via `include_str!`; no Rust build/app install was performed in this lane.
  `core.rs` change (`team_roster` field-set arm + test asserts) needs `cargo test`.
- The TS native-port roster path is tested against stubs, not a real Tauri host.
- No UI consumes the roster/continuity types yet (Director D owns views).
- Development-time gateway observations (control-socket identify on the primary home, `ps`,
  read-only `state.db` queries) informed the producer's design; they were read-only probes,
  not proofs of the shipped path.

## Exact human/owner gates (not mine to flip)

1. **WO-19 delegation.backend flip** — stays PREPARED-NOT-EXECUTED. B4 dryrun:
   `cutover_performed: false`, `guard_armed: false`, backend `mmx-router` unchanged.
   Owner: Chairman / gateway owner per WO-19_PREP.md.
2. **Plugin enable / gateway start-stop / `hermes update`** — gateway owner; this lane
   started and stopped nothing.
3. **Rust build + protected release of the app** (carrying bridge.py/core.rs) — the
   integrating principal; see DIRECTOR_B_SHARED_PATH_PROPOSALS.md.
4. **TeamLink transports** — both are configuration-gated per the design's open item
   (Executive MCP seam on 8731 dead: server not started, `MCP_MMX_EXECUTIVE_API_KEY`
   placeholder). Reviving it is a config action, not code.

## Open issues

1. **`ruamel` missing under the snapshot interpreter**: B4 dryrun
   `backend_availability: probe-failed (ModuleNotFoundError: No module named 'ruamel')` —
   the import-only backend probe could not load; recorded honestly, not retried elsewhere.
2. **Named profiles have no local `gateway.sock`** (multiplexer serves them from the
   primary home): per-profile readiness rests on `gateway.lock` + `ps` verification unless
   a per-profile identify path is added later. The producer reports this as evidence-grade
   truth (lock-verified ready), not control-socket truth.
3. **Roster source pin**: `require_roster_source` pins the hermes-agent commit + file
   hashes; a hermes update will produce `NATIVE_ROSTER_SOURCE_CHANGED` until re-pinned —
   intended fail-closed behavior, but the integrator should expect it after updates.
4. **`record()` default in `contract.ts`** — adding `failureReason` to a receipt's allowed
   keys initially made it required (`required` defaults to `allowed`), breaking existing
   suites; fixed by passing an explicit required list. Noted so future field additions to
   `record()` callers don't repeat it.
5. **TeamLink A1–A7 acceptance tests** require both transports configured; they are design
   acceptance criteria, not runnable in this lane (see gate 4).

## Test commands (exact)

```
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
  tests/test_teamlink_contracts.py tests/test_team_roster_projection.py \
  tests/test_session_bridge_native_continuity.py \
  $(ls tests/test_session_bridge_native*.py) tests/test_session_bridge_installed.py
# → 306 passed

cd app/mastermind_os && npm ci && npm run typecheck && npx vitest run src/hermes-native
# → typecheck green; 7 files, 82 tests passed
```
