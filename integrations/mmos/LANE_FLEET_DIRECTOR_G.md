# Lane ledger — Director G: T3 attempt-fleet visibility (`t3/attempt-fleet-visibility`)

Mission: DONE_WHEN row 3 observation layer — show, PER ATTEMPT, the
exactly-one invariant honestly (one T3 thread, one harness/provider process,
no duplicate direct DSH/Codex launcher beside the T3-owned run), with UNKNOWN
whenever the evidence is not readable. Branch base `7bbac9278`
(`t3/t3-hermes-restart-recovery`); no push, no PR, no other worktree touched.
Never launched/interrupted/sent to any T3 thread or process; the only real
effects were reads (`ps`, `lsof -nP -iTCP:3773`, one `mode=ro` sqlite open).

## Deliverables

| file | what |
| --- | --- |
| `control_plane/t3_attempt_fleet_projection.py` | pure `mastermind.t3_attempt_fleet/v1` projection + read-only `t3_adapter_runs` helper + fail-closed `validate_attempt` |
| `control_plane/t3_process_census.py` | the one real observer: bounded `ps -axo pid=,ppid=,lstart=,command=` (argv only, redacted) + pure table-tested `classify(argv)` |
| `scripts/t3_attempt_fleet_snapshot.py` | read-only CLI; composes projection+census; prints JSON; exit 0 always with honest unknowns/refusals |
| `tests/test_t3_attempt_fleet_projection.py` | invariant matrix incl. every adversarial row from the brief |
| `tests/test_t3_process_census.py` | table-driven classifier over argv shapes OBSERVED LIVE on this Mac + redaction/ps/census round-trip |
| `integrations/mmos/FLEET_ATTEMPT_CONTRACT_PROPOSAL.md` | TS contract mirror + verbatim src-tauri bridge/core hunks (NOT applied; integrator owns src-tauri) |

## Evidence ladder

| claim | grade | evidence |
| --- | --- | --- |
| Classifier matches real T3 harness argv (claude + glm/opus/fable/deepseek models, `/bin/sh` wrapper) | **OBSERVED_LIVE** | live `take_census()` 2026-11-09T09:41:32Z: 1745 processes → 26 `t3_harness` = 13 wrapper+child pairs, all children of T3 desktop server pid 73267 (port 3773, `lsof`), one pair per `~/.t3/worktrees/Mastermind/t3-*`; 63 `codex_cli` (ChatGPT-tunnel `app-server`s, argv carries no worktree → uncorrelated); 3 `dsh_direct` (attended `launch_attended.mjs` + `bin.js web` + one more) |
| Wrapper+exec-child collapse to ONE harness tree | **OBSERVED_LIVE** | every pair is (wrapper ppid=73267, claude child ppid=wrapper); `_harness_roots` counts 13 trees from 26 processes |
| Full pipeline end-to-end on this machine | **OBSERVED_LIVE** | `t3_attempt_fleet_snapshot.py --adapter-state /tmp/demo_t3_state.sqlite3` (synthetic row for THIS session's worktree `t3-41e8c18e`, live census): both invariants PROVEN, harness pid 56532/provider claude/model glm-5.3, duplicate observed=false — redacted output below |
| Default adapter-state path snapshot | **OBSERVED_LIVE** | `t3_attempt_fleet_snapshot.py` → `{attempts: [], notes: ["ADAPTER_STATE_EMPTY"]}` — no durable `t3_adapter_state.sqlite3` composed on this checkout yet (honest empty, not an error) |
| Two threads under one (key, namespace) → VIOLATED | **PROVEN_BY_TEST** | `test_two_threads_same_key_and_namespace_is_violated` |
| Same key, different namespace → two attempts, not a violation | **PROVEN_BY_TEST** | `test_same_key_different_namespace_is_two_attempts_not_a_violation` |
| Missing harness → UNKNOWN not VIOLATED | **PROVEN_BY_TEST** | `test_missing_harness_is_unknown_not_violated` (count 0 + `HARNESS_NOT_OBSERVED`) |
| Stale census → UNKNOWN everywhere process-side | **PROVEN_BY_TEST** | `test_stale_census_is_unknown_everywhere_on_the_process_side` |
| Direct DSH beside a T3 run → duplicate observed `dsh_direct` | **PROVEN_BY_TEST** | `test_dsh_direct_beside_t3_run_is_duplicate_launcher` |
| Uncorrelated dsh/codex processes do NOT fire duplicates | **PROVEN_BY_TEST** | `test_uncorrelated_dsh_direct_is_not_a_duplicate_for_this_attempt` (the 63 tunnel codex servers must not cry wolf) |
| Secret-like substrings redacted before storage | **PROVEN_BY_TEST** | `test_token_like_substrings_redacted`, `test_secret_like_never_enters_the_projection` (`[A-Za-z0-9_-]{32,}` on slash-free tokens; path segments preserved; team-roster `scrub` everywhere; classification stable under redaction) |
| Malformed row / foreign echo → typed refusal | **PROVEN_BY_TEST** | `test_malformed_row_is_typed_refusal`, `test_receipt_echoing_foreign_key_is_typed_refusal`, `test_intent_run_id_mismatch_is_typed_refusal` (real `SQLiteT3AdapterStateStore` schema in fixtures) |
| src-tauri bridge/core hunks compile & the TS parser accepts the doc | **SOURCE_ONLY** | proposed verbatim in `FLEET_ATTEMPT_CONTRACT_PROPOSAL.md`; NOT applied (integrator owns src-tauri); no Rust/vitest run in this lane |

## Exact commands + counts

```
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
  tests/test_t3_attempt_fleet_projection.py tests/test_t3_process_census.py
→ 82 passed in 1.20s   (52 projection rows + 30 census rows)

env -u PYTHONPATH /opt/homebrew/bin/python3.12 scripts/t3_attempt_fleet_snapshot.py
→ exit 0, {"attempts": [], "notes": ["ADAPTER_STATE_EMPTY"], ...}

env -u PYTHONPATH /opt/homebrew/bin/python3.12 scripts/t3_attempt_fleet_snapshot.py \
  --adapter-state /tmp/demo_t3_state.sqlite3      # synthetic row, LIVE census
→ exit 0, attempt below (ids redacted for this ledger)
```

### Redacted live demo output (2026-11-09T09:41:57Z, live ps)

```json
{
 "attempt_id": "runs/demo-att-1",
 "idempotency": {"key": "cccccccc…<redacted>", "namespace": "mastermind.control_plane.t3_execution_adapter/v1"},
 "t3_thread": {"thread_id": "mcp:launch:99999999…<redacted>", "run_id": "run:thread:demo:ordinal:1", "state": null, "unknown_reason": null},
 "harness_process": {"pid": 56532, "provider": "claude", "model": "glm-5.3", "start_time": "2026-11-09T09:24:30+00:00", "unknown_reason": null},
 "thread_count_for_key": 1, "harness_count_for_thread": 1,
 "duplicate_launcher": {"observed": false, "kinds": [], "evidence_refs": ["adapter_state:read", "adapter_state:key:cccccccccccc", "census:pid:56532"], "unknown_reason": null},
 "invariant": {"exactly_one_thread": "PROVEN", "exactly_one_harness": "PROVEN"},
 "freshness": {"adapter_state": "fresh", "census": "fresh", "thread_read": "absent"}
}
```

(pid 56532 is THIS session's own T3 harness wrapper — the projection found it
through the real `ps`; `t3_thread.state` is honestly null: no thread read was
supplied and no result reference was ledgered.)

## API gaps in `t3_execution_adapter.py` (read-only lane; Director A3 reworking it)

1. **No read-only open.** `SQLiteT3AdapterStateStore.__init__` runs
   `mkdir` + `CREATE TABLE` — a writer. Observers must not construct it against
   the live file, so my helper opens the table itself with a `mode=ro` URI.
   Proposal: a `SQLiteT3AdapterStateStore.open_read_only(path)` classmethod (or
   module-level `read_run_rows(path)`).
2. **No by-key query.** `run_ids()` + `load_run()` exist, but the fleet view
   needs "all rows sharing (client_request_id, request_namespace)" to detect a
   second thread minted under one idempotency identity; today that is a full
   scan + my own grouping.
3. **No wall-clock in rows.** `updated_ms` is `time.monotonic_ns()`-based —
   deliberately not comparable across processes; the projection therefore
   reports adapter-state freshness as "read happened at snapshot time" and
   never fabricates a wall-clock age from it.
4. **No thread→harness fact.** Nothing durable records which local harness pid
   (if any) serves a thread; argv workspace correlation is the only join (see
   limits below).

## Honest limits (render, don't hide)

- **Workspace-grain join**: multiple live attempts sharing one worktree each
  count ALL harness trees in it (observed: `t3-c4bdadf2` hosted 3 pairs —
  deepseek-v4.1-flash + glm-5.3-flash + glm-5.3). Displayed as VIOLATED with
  count; durable fix needs a thread-id→pid fact from T3 upstream.
- **Remote / exited harness** → count 0 → UNKNOWN, never VIOLATED.
- **Classifier coverage** is the two marker families OBSERVED on m2studio
  (`mcp__t3-code__*` + `/.t3/worktrees/`, and the dsh ACP profile rows). A
  future provider harness lacking both markers classifies `other` → harness
  UNKNOWN (safe direction, documented in the module docstring).
- The desktop's ad-hoc threads (not adapter-minted runs) are not attempts;
  with no durable store the fleet is honestly empty.

## What the integrator must wire

1. Apply the two src-tauri hunks verbatim from
   `FLEET_ATTEMPT_CONTRACT_PROPOSAL.md` §2 (core.rs `valid_fields` +
   `valid_attempt_id`; bridge.py `ATTEMPT_ID`/FIELDS/normalize/dispatch +
   `NativeRuntime.t3_attempt_fleet` composing the three modules off-thread);
   run `cargo test` in `src-tauri` (not run here — SOURCE_ONLY).
2. Add `t3-attempt-fleet-contract.ts` (`parseT3AttemptFleet`) mirroring
   `validate_attempt`; it rides the existing non-mutating native-port path —
   zero `native-port.ts` edits, like `team_roster`.
3. Director D: per-attempt "T3 attempt fleet" block in the Fleet & Capacity
   route (details in the proposal §3) — attempt_id = the Fabric-catalog run id;
   PROVEN/VIOLATED/UNKNOWN(+reason) chips, duplicate kinds when observed.

## Not done, and why

- No PR/push (brief forbids; integrator consumes the branch).
- No Rust or vitest execution (src-tauri/React untouched; hunks SOURCE_ONLY).
- No live thread-read proof: the brief allows only a SAVED read
  (`--thread-read-json`), and none exists yet on this machine; `t3_thread.state`
  stays honestly null in the demo. The path is exercised by tests with
  injected ports (fresh/stale/unreachable/malformed).
- No attempt was made to enumerate `~/.t3/userdata` threads as attempts:
  without durable adapter rows that would fabricate attempt identity.
