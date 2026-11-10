# RC CRITICAL review manifest — MMOS trunk candidate `8d4e24d12`

Pre-review manifest for the release-candidate CRITICAL review (lane L6 slice 6).
Author: GLM-5.3 pre-review sub-lead (slice reassigned from gemini-4-argon on provider
transport failure). `MODE: READ_ONLY` on all source; the only artifact produced by this
slice is this file. No PR, no CI dispatch, no push to protected branches.

What this is: the complete enumeration of CRITICAL-row deltas (auth, permissions,
exactly-once, release automation, identity pins) in the review window, each with the
question a release reviewer must answer, followed by this reviewer's own findings with
evidence. What this is not: a GitHub approval, an acceptance, or a substitute for the
CRITICAL-row review itself.

## 1. Review window

- **From-record:** `integrations/mmos/REVIEW9_GUARD_R13_OPUS_20261110.md` — the last
  review record under `integrations/mmos/`; **VERDICT: ACCEPT**, guard r13 reviewed at
  head `e6479f848` (its own delta window was `ce39d8daf..e6479f848`, guard file only).
  REVIEW2–REVIEW8 are earlier re-checks of the same guard row (REVIEW8 NEEDS_REWORK →
  closed by r13); REVIEW9 is the accepted frontier.
- **Window:** `e6479f848..8d4e24d12` — ancestry verified (`git merge-base --is-ancestor`
  OK). **60 commits, 140 changed files.** 61 of the 140 are docs/research/mmos-ledger
  markdown; the remainder are product UI (L2 lane), tests, and the code deltas below.
- **Trunk head:** `8d4e24d12` (= worktree HEAD, clean; `origin/feat/mmos-v1-integration-t3`).

## 2. CRITICAL deltas in the window

Categories: AUTH / PERMISSIONS / EXACTLY-ONCE / RELEASE AUTOMATION / IDENTITY PINS.
"Carried" rows name CRITICAL surfaces that did NOT change inside the window but are
explicitly in RC scope per the slice assignment (their last change predates `e6479f848`
and no accepted review record covers them end-to-end).

### AUTH

| # | Files | Commit | What changed | Question the release reviewer must answer |
|---|---|---|---|---|
| A1 | `app/mastermind_os/src-tauri/src/auth.rs` (T3AttemptFleetSelection, `t3_attempt_id_valid`, `read_t3_attempt_fleet`), `src-tauri/src/main.rs:194` | `f6bfac18b` | New `read_t3_attempt_fleet` Tauri command: fixed-URL signed GET `/workspace/resources/t3/attempts/current?attempt_id=…`, attempt-id grammar (alnum head, ≤160, `_./:%=-` bytes, secret-token refusal incl. `sk-`+16), 16,384-byte bounded JSON, `mastermind.t3_attempt_fleet/v1` schema gate, token-generation recheck via `release_allowed` after the read. | Can any `attempt_id` that passes `t3_attempt_id_valid` make the host fetch anything other than the one fixed path with that id as a single-decoded query value — and does every refusal path (grammar, cap, schema, auth-generation) surface as a typed error rather than a transport success? |
| A2 | `app/mastermind_os/src/host.ts` (readT3AttemptFleet), `src/code/attempt-fleet-read.ts`, `src/App.tsx`, `src/code/CodeWorkspace.tsx`; fix `e844a5e7b` | `781df5736`, `51a93f1ed`, `e844a5e7b` | Read-only reader wired into the host read allowlist + HC07 workbench; Fleet→Code attempt context (`codeAttemptId`) with clear-at-entry (`e844a5e7b` closed a stale-attempt workbench leak on Team/Projects/nav-rail Code entries — verified: all three `setActive("Code")` sites clear or deliberately set the id, `App.tsx:5536,5908,5925`). | Does the new host entry stay a pure read (no launch/send/interrupt authority added to `createNativeClient`'s read union), and can a stale `codeAttemptId` survive any navigation path into the Code view? |
| A3 (carried) | `integrations/mastermind_workspace_app/t3_attempt_fleet.py`, `…/app.py` (route + `_RawPathFence`) | `108e84da3` (pre-window; unchanged in window) | Server side of A1: `_authenticate`, body refusal, strict v2 single-key query decode, `wire.attempt_id` grammar, control-room permission stamps, post-await recheck of authorizer/client/permission stamps + `now < principal.expires_at`, typed 200 refusal documents, `no-store`. | Can a non-control-room principal or an expired token obtain an attempt-fleet frame, and can the awaited `client.request` result bypass the post-await permission/expiry recheck (`t3_attempt_fleet.py:40-58`)? |

### PERMISSIONS

| # | Files | Commit | What changed | Question the release reviewer must answer |
|---|---|---|---|---|
| P1 | `ops/executive_os/provider_orchestrator_guard.py`, `tests/test_guard_r13_documented_limits.py` | `1b943fc4e`, merge `5a4e39918` | **Docstring-only** addition of the r13 documented limits (env -S escape class; escaped-quote-before-newline over-refusal) + 2 pin tests. Window diff on the guard file is exactly one module-docblock hunk — r13 code is byte-identical to the ACCEPTed `e6479f848`. | Confirm the guard's executable behavior is unchanged from the ACCEPTed r13 (diff the window hunk: docblock only) and that the two pinned MINORs match REVIEW9 findings #1/#2 verbatim — no limit quietly widened? |
| P2 | `brain/bot_mcp.py`, `tests/test_bot_mcp.py` | `14ec0660f` (#495, via master merge) | Strict JSON transport boundary for MCP tool responses: `MCP_RESPONSE_TOO_LARGE` / `MCP_RESPONSE_NOT_JSON` typed `is_error` results replace malformed sliced JSON; 5-level compaction ladder; ~27 qualification keys kept whole; scalar fallback preserving qualification+freshness fences. | Can a consumer mistake an `is_error` transport result for data, and does any honest result now lose a fence it previously (malformedly) carried — i.e. is every path that used to emit invalid JSON now either valid JSON or a typed error? |
| P3 (carried) | `control_plane/executive_service.py:6809-6824, 6944-7024` (`_handle_child_request_admit_frame`, `admit_child_execution_request`), `control_plane/child_request_admission.py`, `child_execution_contracts.py` | last touched pre-window (`108e84da3` and earlier) | The `child_request_admit` host ingress (assignment-required): envelope retrieved from host-frozen `app_binding.child_request_material[command]`, never through the model; `require_current` + `principal_admission_armed` + service READY guard before admission; `from_dict` verifies supplied digest against payload (tamper check, `child_execution_contracts.py:1013-1016`); digest conflict → typed `conflict`; queue-full → WAIT with precise reason; post-admission currentness failure returns `internal_error` with "admission may have committed" reconciliation-by-resubmit. | Can an unattested or model-shaped envelope reach `admit_child_execution_request`, and after a post-admission `internal_error` does resubmitting the same frozen command provably reconcile as REPLAY (same triple + digest) rather than mint a second Job? |
| P4 | `integrations/session_bridge/t3_native_client.py`, `t3_shared_notes.py`, `t3_mission_brief.py` (+ `docs/T3_SESSION_CONTROL_V3.md`) | `0450fba70` (#2374, via master merge) | Capacity-only T3 session-control client over an injected authorized connection: no listener/auth/subprocess/db/retry owner; secret-refusing text validators; mutating ops (`stop`, `set_model`, `queue_change`, `answer_question`) carry request ids + provider/scope identity rechecks; `answer_question` is user_input-only per the native handler, answers bounded 1–32 and secret-scanned. | `answer_question` cannot itself verify the question `kind` (the client's `read_question` returns only id+question) — is the native-handler user_input-only law the sole fence, and is that fence attested anywhere this repo can test, or is it LIVE_ONLY trust in the T3 server? |

### EXACTLY-ONCE

| # | Files | Commit | What changed | Question the release reviewer must answer |
|---|---|---|---|---|
| E1 | `tests/test_mmos_nm09_nm10.py` (new), `integrations/mmos/NEGATIVE_MATRIX_V1.md` | `ad04bc624`, merges `b9c0d6e9c`/`5a4e39918`, matrix `63ed19a7d` | NM-09 no-fallback law pinned end-to-end: lose-ACK start → `T3LaunchEffectUnknownError` with intent retained; different-route replacement → no second Job, original route survives, one launch envelope forever; other OAuth client → `T3LaunchClaimConflictError` before any native call; reattach → `PRINCIPAL_MISMATCH`. 4 tests pass at HEAD. | After an effect-unknown launch, is there ANY path (admission, adapter, or UI) that mints a second Job or switches principal/route before the original is reconciled — and does the pinned test cover the adapter AND the composition layer together? |
| E2 (carried shape, newly pinned) | `control_plane/child_request_execution_composition.py:44-52, 84-127`; `child_execution_contracts.py:943-969`; pinned by `tests/test_mmos_nm09_nm10.py:113-171` | shape pre-window; pin `ad04bc624` | **The NM-09 REPLAY shape** (assignment-required): the idempotency digest covers the request envelope's semantic fields only; the placement spec (route) lives in Job `constraints["child_placement"]`, keyed by `sha256(triple)` alone. A route-only change under the same triple + envelope digest reconciles **silently as REPLAY**: admission state REPLAY, `placement_created=False`, the original Job (original route) survives, the replacement spec is discarded with no typed signal naming the spec delta. | Is silent REPLAY-with-discarded-spec acceptable for every compose caller — specifically, does each caller surface "your spec was NOT adopted" (compare against `job.constraints["child_placement"]`) so an operator correcting a quota-blocked route cannot believe the correction took effect while every future claim launches the original route? |
| E3 | `tests/test_mmos_nm09_nm10.py` (NM-10 rows), `NEGATIVE_MATRIX_V1.md` | `ad04bc624`, `b9c0d6e9c` | NM-10 source laws: continuation vocabulary ⊆ {recover, read, status, send}; fresh send only from IDLE; recover only for EFFECT_UNKNOWN on the original key; banned-token walk (`restart/reconnect/remake/resubmit/relaunch`) over every row name+value; outage → typed errors, launch_count stays 1. 4 tests pass. | Can any classified state express an evasion verb in ANY field (the walk lowercases name=value pairs — does it cover every field future rows may add), and does a read outage truly advance no cursor/launch anywhere in the adapter? |
| E4 | `integrations/session_bridge/hermes_native_continuity.py`, `tests/test_mmos_nm06_gateway_stopped.py` (new), `tests/test_mmos_negative_matrix.py` | `0d2ba107e`, merge `0b17ce139`, why-string fix `411843199` | NM-06: `GATEWAY_STOPPED` state with closed `_STOPPED_CODES` table ({NATIVE_GATEWAY_STOPPED, NATIVE_GATEWAY_NOT_RUNNING}), status-only continuation, why-string "its owner starts it — automatic gateway recovery is not offered here" (post-`411843199`, contains no banned token; xfail tripwire removed to a passing assert). | Do the two stopped codes remain the complete closed table (a third gateway-stopped code arriving later would fall to UNCLASSIFIED), and does the why-string stay inside the NM-10 vocabulary walk after future edits? |
| E5 | `portfolio/predictions.py`, `tests/test_prediction_ledger_persistence_truth.py` (new) | `62db688ed` (#812, via master merge) | Crash-safe prediction ledger: `fcntl.flock` + threading RLock around read-modify-write, atomic `tempfile`→`os.replace` with fsync, strict-by-default reads (`strict=True` default flip), failures propagate to the scheduler boundary instead of masquerading as empty. Call sites verified wrapped: `app/scheduler.py:1125-1129` (`_step_failed_event`), `app/web.py:2951-2960` (typed unavailable). | Can two processes still interleave a lost update (is every ledger mutation inside `_ledger_lock` — including `record()`'s open/label/resolve phases), and does any pre-existing caller still assume `record()` never raises? |
| E6 | `brain/interim_marks.py`, `tests/test_interim_marks_persistence_truth.py` (new) | `3673c03b1` (#810, via master merge) | Same crash-safe pattern for interim marks: flock + atomic replace, keep-first per (thesis_id, checkpoint) preserved, missing price labels stay a no-op, corrupt evidence fails closed at the scheduler boundary (`app/scheduler.py:1153-1158` verified). | Does KEEP-FIRST survive the atomic-replace rewrite (no path where a rewrite resurrects an earlier mark), and does a corrupt jsonl row now halt marking rather than silently dropping marks? |

### RELEASE AUTOMATION

| # | Files | Commit | What changed | Question the release reviewer must answer |
|---|---|---|---|---|
| R1 | `integrations/mmos/OPERATING_METHOD_V2.md` (+ method commits) | `d042c13d8`, `85f0f91af`, `8d4e24d12` | Operating method V2: leads land their own lane, CI once at release candidate, review stop rule, evidence rule for every return. **Prose only** — no `.github/`, workflow, script or queue file changed in the window (verified by name-diff). | Which machine control actually enforces "CI once at RC" and the review stop rule — if none, name the gap explicitly in the RC record rather than letting the doc read as an enforced gate? |
| R2 | `ops/native_fabric/quota_continuity/tests/test_application_{registered_pool_composition,registered_pool_selection,turn_selection_admission}.py` | `ebc48690f` (#2387) | Test infra: private (0600) ledger fixtures for permissive runner umasks + new `LedgerPermissionFenceTests` asserting `_strict_open` refuses unsafe modes (0620/0602/0664/0666) without normalizing them and without touching retained bytes. | Do the private fixtures hold under the actual runner umask set (022/002/077), and does the fence still refuse a pre-existing group/world-writable ledger rather than repairing it in place? |

### IDENTITY PINS

| # | Files | Commit | What changed | Question the release reviewer must answer |
|---|---|---|---|---|
| I1 | `tests/executive_fabric_release_identity_review.py` | `b73748116` (#2377, master), `5257967eb` (#2386), trunk-merge convergence in-window | Pin-bookkeeping for `integrations/hermes_attended_fabric/native.py` reviewed-site tokens (two `500` operands at 57/65-68 and 280/60-63) after #2365 moved them nine lines; trunk and master independently re-pinned, converging at the same value. **The reviewed source itself is byte-identical across the window** (sha256 at HEAD = `7b6d14ea2e04…a0bf` = the pin; verified by recomputation, not by test-run alone). | Is the converged pin value recomputed against the MERGED native.py (both line sites and full-file hash — shown above), and would the pin test still fail on genuine drift of either operand or of any other reviewed site? |
| I2 | `tests/test_hermes_fabric_native_identity_review.py` | `5257967eb` (#2386) | Same convergence in the second pin consumer; comments corrected to record that master re-pinned independently (#2377/#2386) so the origin/master merge required no trunk-side pin change. | Does this test assert the same sites/value as I1 (no skew between the two pin files that a future move could split), and do both consumers run in the RC's required check set? |

### Reviewed in-window, judged NOT CRITICAL-row (for completeness)

- `06c10c973` (#754) — research-evidence read failures stay unavailable: `app/web.py` `/api/research` now returns a typed 500 `research_feed_unavailable` document instead of `[]`; `app/static/index.html` consumer verified to map non-ok responses and non-array payloads to the unavailable state (`_researchFetch`/`_applyResearchFeed`, index.html:5635-5655). Evidence-honesty, not a CRITICAL row.
- `4745aad7c` (#2385) — `verify_source_materialization.py` robust across Git versions (batch-check exit-status variants); test-only hardening of a qualification witness.
- L2 product-UI lane (`01c153fe9`…`deced831c`, ~70 files): read-only panels and CSS; the one adversarial fix (`e844a5e7b`) is folded into A2.
- Remaining 55+ files: docs/research/mmos ledgers (paper migrations, design doctrine, lane ledgers, REVIEW9 record itself).

## 3. Pre-review findings (this reviewer, evidence-verified)

**BLOCKER: none found.** No delta in the window breaks an auth, exactly-once, release or
identity control I could drive to a concrete failure by reading the code and running the
pinned tests.

**MAJOR: none found.** (The two candidates that could have been MAJOR — the REPLAY
spec-discard path and the ledger fail-closed flip — are pinned/verified respectively, and
are recorded below as MINOR/verified.)

**MINOR (2):**

1. **NM-09 route-only REPLAY discards the replacement spec with no typed non-adoption
   signal.** `control_plane/child_request_execution_composition.py:44-52` mints the
   placement command id from `sha256(triple)` alone; `:84-127` stores the caller's spec
   only in Job constraints and, on the `create_job` StateConflict, reconciles to the
   existing Job. A re-compose with a different route under the same triple+envelope digest
   returns `admission.state == "REPLAY"`, `placement_created == False` and the ORIGINAL
   Job's route — the replacement spec is silently dropped (pinned deliberately by
   `tests/test_mmos_nm09_nm10.py:113-171`). Failure scenario: a lead corrects a
   quota-blocked route; compose answers REPLAY; unless the caller diffs its spec against
   `job.constraints["child_placement"]`, it reports the correction accepted while every
   future claim launches the original, quota-refusing route forever. This is the
   documented no-fallback law (NEGATIVE_MATRIX_V1.md NM-09 observation), so it is a
   design-accepted MINOR — but the RC review must confirm every compose caller surfaces
   non-adoption (see E2's question).
2. **bot_mcp terminal `MCP_RESPONSE_TOO_LARGE` loses ALL qualification fields when
   qualifier mass alone exceeds the 8,000-byte budget.** `brain/bot_mcp.py:129-195`: the
   final ladder stages keep every `_JSON_TRANSPORT_QUALIFICATION_KEYS`/freshness value at
   FULL size (`k in required` bypasses compaction at every level, including the
   ranked-prefix pass), so a payload whose qualifiers alone exceed 8KB — e.g. a very
   degraded day with a `failed_sources` list of ~30 long source names, or one giant
   `error` string — falls through all five compaction levels and both fallbacks to the
   bare `{"error":"MCP_RESPONSE_TOO_LARGE"}` with zero evidence attached. The comment
   names the trade ("an explicit transport error is safer than losing a fence"), so this
   is an accepted-cost MINOR: the consumer cannot distinguish "huge honest degraded
   evidence" from "broken serialization".

**Verified non-findings (checked, no defect):** guard r13 byte-identical in-window
(docstring-only hunk); `native.py` pin matches merged content by independent sha256;
`predictions.record()`/`interim_marks.record()` fail-closed flips land on wrapped
scheduler boundaries (`app/scheduler.py:1125-1129, 1153-1158`) and a typed web response
(`app/web.py:2951-2960`); `/api/research` 500 shape handled by its only frontend consumer;
all three Code-view entries clear or deliberately set `codeAttemptId` (`App.tsx:5536,
5908, 5925`); gateway_stopped why-string contains no banned evasion token; Rust id-grammar
byte-slicing is ASCII-safe because the grammar check precedes the `sk-` scan.

## 4. Verification log (what this review actually did)

- Read: REVIEW9 verdict/coverage; the full `e6479f848..8d4e24d12` name-diff (140 files)
  and the substantive diffs cited above (auth.rs, main.rs, host.ts, App.tsx, web.py,
  bot_mcp.py, hermes_native_continuity.py, predictions.py, interim_marks.py, guard
  docblock, both identity-pin test files, quota/verify_source_materialization tests,
  t3_native_client/t3_shared_notes/t3_mission_brief).
- Read (carried surfaces): `executive_service.py` admit paths, `child_request_admission.py`,
  `child_execution_contracts.py` (triple/digest/from_dict verification),
  `child_request_execution_composition.py`, `mastermind_workspace_app/t3_attempt_fleet.py`.
- Ran at HEAD (all pass): `test_mmos_nm09_nm10.py` (4), `test_mmos_nm06_gateway_stopped.py`
  (5), `test_hermes_fabric_native_identity_review.py` (2), `executive_identity_review.py`
  (2), `test_guard_r13_documented_limits.py` (2), `test_t3_native_client.py` +
  `test_t3_shared_notes.py` + `test_t3_mission_brief.py` (56),
  `test_mmos_negative_matrix.py` (6), `test_prediction_ledger_persistence_truth.py` +
  `test_interim_marks_persistence_truth.py` + `test_research_evidence_unavailable_truth.py`
  (91).
- Environment gap (honest): `tests/test_bot_mcp.py` could NOT be collected here —
  `claude_agent_sdk` is not installed in this worktree's interpreter, and a direct import
  probe of `brain/bot_mcp.py` stops on its `import bot` dependency. P2's assessment is
  from source reading only; the RC's required CI check owns that test's execution proof.
- Recomputed: `shasum -a 256 integrations/hermes_attended_fabric/native.py` =
  `7b6d14ea2e041f98573627925340f00c4b6e6c3cfde5a16e297aa3a52079a0bf` (equals the I1/I2
  pin; `e6479f848`'s copy is identical — the reviewed site did not move inside the window).

## 5. Delta count summary

auth 3 (2 in-window, 1 carried) · permissions 4 (3 in-window, 1 carried) · exactly-once 6
(5 in-window, 1 carried shape) · release automation 2 · identity pins 2 — **17 CRITICAL
rows total**; window `e6479f848..8d4e24d12`, 60 commits.

## 6. Post-window deltas (lane L6 landings after `8d4e24d12`, added by the lane lead)

- **IDENTITY PINS — NewGroupPanel registry pin** (`169bc08ae`, landed on trunk via lane
  merge at `58540296a`): `tests/executive_fabric_release_identity_review.py` gains one
  `REVIEWED_FILES` entry masking exactly the reviewed 600-char textarea bound in
  `app/mastermind_os/src/team/NewGroupPanel.tsx` (whole-file sha256
  `b84219e6…`, single span `(187, 25, 28)`). Reviewer question: is a D8-masked UI input
  bound with whole-file hash + single-span qualification an acceptable pin, and does any
  caller path let a masked span hide a real identity literal? Lead-verified: hash matches
  the file byte-for-byte; any byte drift drops the pin (`drift drops pin: True`);
  unregistered paths and second literals still flag; D8 suite 321/321 green. The grok-4.7
  cross-check return was REJECTED as evidence (missing transcript, fabricated file
  excerpt) — this row stands on the lead's own reproductions.
- Non-CRITICAL post-window landings (master merge `fe4265176` via `376c66d38`, NM-06 TS
  mirror `a392b8a7f`, install ledger `f9ae7aa6f`, this manifest): no auth/permission/
  exactly-once/release-automation/identity-pin surface beyond the row above.
