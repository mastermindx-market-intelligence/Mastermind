# PART C — Presentation: setting the `presentation` key on the team server

PF-2 item 2. Writer: `tools/mmos_team_server/presentation_set.py` (python3.12
stdlib). Tests: `tests/test_mmos_presentation_set.py` (34 passed). Rehearsed
end to end on 2026-11-14 against a throwaway copy with the REAL root's path
shape and a 13-teammate roster (`~/.mastermind/mmos_dev/pf/realshape`, label
`com.mastermind.pf.realshape`, port 3832, release
`pfnext-0.1.7-pin0770446-f5248ab2-rs` packed from the pinned source — the
packed `dist/bin.mjs` sha256 `1d8b6a6e…4cf5d1` is byte-identical to staging's
`f5248ab2` build; no rebuild). Every step is ledgered with UTC/rc/seconds in
`~/.mastermind/mmos_evidence/pf-20261114/presentation/LEDGER.md`.

The writer edits ONLY the bytes of the top-level `presentation` member of
`settings.json` (replace its value span, or insert a new last member). Every
byte outside the member is unchanged — no whole-file `json.dump`. It reuses
`team_roster.atomic_write` (0600 temp, fsync, `os.replace`, staging under
`<root>/run`). Before the first write it checks the file's sha256 against
`--expect-sha256`, saves the exact preimage bytes 0600 plus a receipt JSON in
a 0700 receipt dir (a FRESH dir per apply — a dir that already holds a
receipt is refused), writes atomically with the file mode preserved, then
reads back and verifies parse, `presentation` equality, outside-member byte
equality and mode. Any mismatch exits nonzero. Immediately before
`os.replace` the writer re-reads and re-hashes the destination and aborts
(`PREIMAGE_CHANGED`, nothing written) if it changed — a window remains
between that re-hash and `os.replace` where a foreign write can still be
lost, and the tool cannot close it without the server's cooperation.
Precondition: part (c) is run with no live teammate run, straight after
part (b). `undo` restores the exact
preimage, but only while the current sha256 still equals the receipt's
after-sha (nobody else wrote since). File contents are never printed except
the presentation member (in `plan`'s diff). Any settings path at/under
`~/.mastermind/t3-team` is refused without the explicit `--real-root-ok`
flag — the principal's flag; the rehearsal never passed it.

## Step list for the principal (real root)

All commands below are the principal's to run. Placeholders:
`<TEAM_PROJECT_ID>` (step 0), `<SETTINGS_SHA>` (step 2's printed sha256).
`T3="env T3CODE_HOME=$HOME/.mastermind/t3-team/home T3CODE_PORT=3780
$HOME/.mastermind/t3-team-server/bin/t3"`: the real team server's CLI.

### 0. Get the real team project id (read-only)

```sh
env T3CODE_HOME="$HOME/.mastermind/t3-team/home" T3CODE_PORT=3780 \
  "$HOME/.mastermind/t3-team-server/bin/t3" thread list \
  --project "$HOME/.mastermind/t3-team/team-project" --json \
  | python3 -c 'import json,sys; print(sorted({t["projectId"] for t in json.load(sys.stdin)}))'
```

Every teammate primary thread carries the same `projectId`; that is the id
for `lockedProviderProjectIds`. (Rehearsal: this read returned exactly one
project id, `f2ea7f57-…`, for all 13 threads — ledger 09:49:58Z.)

### 0b. Lock census (read-only; RULING PF-2a precondition)

The value turns the picker lock on for the whole team project. Before the
first write, check that no conversation would be stuck and every teammate
primary is on its own instance:

```sh
/opt/homebrew/bin/python3.12 tools/mmos_team_server/lock_census.py \
  tools/mmos_team_server/specs/team_roster.json; echo rc=$?
```

Expected output: `"onMissingInstance": []`, `"primaryMismatch": []`,
`"ok": true`, `rc=0`; `"conversations"` 25 and `"byInstance"` as in the
principal's 14 Nov census (13 primaries on their own instances; non-primary:
7 `capacity_fabric`, 2 `assurance`, 2 `design-lead`, 1 `secretary`), plus
any conversations started since, plus the database `"journalMode"`. It
opens the state database with its own `mode=ro` connection (never
`immutable=1`), reads settings.json and the roster state file, and prints
counts and conversation IDs (plus, in `primaryMismatch`, the roster name and
instance ids of a mismatched teammate; no conversation text, title or secret). The main database file is never written;
on a WAL-mode database with the server running the `-wal`/`-shm` files
already exist and are the server's, and with the server stopped sqlite may
create them when the census opens its read-only connection. `"project"` is
the same id step 0 returns. A nonzero exit stops part (c): see
`LOCK_EXISTING_CONVERSATIONS.md`, "Not built".
Rehearsed on PF staging: rc=0, 3 conversations.

### 1. Write the value file

```sh
cat > "$HOME/.mastermind/t3-team/run/presentation-value.json" <<'JSON'
{
  "productName": "Mastermind OS",
  "teamMode": true,
  "lockedProviderProjectIds": ["<TEAM_PROJECT_ID>"],
  "links": [
    {"id": "work", "label": "Work",
     "url": "http://127.0.0.1:3100/MAS/issues"},
    {"id": "needs-you", "label": "Needs you",
     "url": "http://127.0.0.1:3100/MAS/inbox"}
  ]
}
JSON
```

The links are URL strings only; the writer sends nothing to 3100. Schema
(the server's `PresentationSettings`): `productName` nonempty string,
`teamMode` bool, `lockedProviderProjectIds` list of nonempty strings, `links`
list of `{id,label,url}` with `id` `^[a-z0-9-]{1,32}$` and an http(s) url.
All four keys are required; unknown keys are refused.

### 2. Plan (writes nothing)

```sh
python3.12 tools/mmos_team_server/presentation_set.py plan \
  --settings "$HOME/.mastermind/t3-team/home/userdata/settings.json" \
  --value-file "$HOME/.mastermind/t3-team/run/presentation-value.json" \
  --real-root-ok
```

Prints the current `sha256`, whether `presentation` is present, and a
unified diff of only that member. Copy the printed sha256 as
`<SETTINGS_SHA>`. If someone else may write the file concurrently, re-run
plan immediately before apply and use the fresh sha.

### 3. Apply (preimage-checked, receipt before write)

```sh
python3.12 tools/mmos_team_server/presentation_set.py apply \
  --settings "$HOME/.mastermind/t3-team/home/userdata/settings.json" \
  --value-file "$HOME/.mastermind/t3-team/run/presentation-value.json" \
  --expect-sha256 <SETTINGS_SHA> \
  --receipt-dir "$HOME/.mastermind/t3-team/run/presentation-receipts-1" \
  --real-root-ok
```

Use a FRESH receipt dir for every apply (`presentation-receipts-1`, `-2`,
…): the writer refuses a dir that already holds a receipt, so a second
apply can never overwrite the first preimage and destroy the first undo
path.

Refuses unless the current sha256 equals `--expect-sha256` (checked before
any write), refuses a symlinked settings path, and refuses without
`--real-root-ok` on this root. On success it prints before/after sha256 and
the receipt path. The receipt dir holds `preimage.bin` (0600, exact old
bytes) and `receipt.json` (before/after sha256, time, path) — written BEFORE
the settings write. Keep the receipt dir: it is the only way back.

### 4. Readback

The writer already read back and verified parse, `presentation == value`,
outside-member byte equality and mode before exiting 0. For a second look:

```sh
python3.12 tools/mmos_team_server/presentation_set.py plan \
  --settings "$HOME/.mastermind/t3-team/home/userdata/settings.json" \
  --value-file "$HOME/.mastermind/t3-team/run/presentation-value.json" \
  --expect-sha256 <AFTER_SHA_FROM_STEP_3> --real-root-ok
```

It should print `presentation: present`, `expect-sha256: MATCH`, and
`(presentation member unchanged)`.

### What a running session and an open window see at the write moment

- The server watches `settings.json` (fs.watch on the directory, ~100 ms
  debounce; `serverSettings.ts:1247-1318`), reloads it, and emits
  `settingsUpdated` to connected clients (`ws.ts` ~3409). **Observed in the
  rehearsal without any restart:** a cross-instance model-selection dispatch
  on a locked-project thread was ACCEPTED before the write and REFUSED ~1 s
  after it with exactly `This conversation belongs to Design Lead; other
  providers are not offered here.` — the picker lock is read per dispatch
  from the live settings (`Orchestrator.ts` ~14100). After `undo` the same
  dispatch was accepted again. Runner pid 17128 was constant throughout
  (ledger 09:48:28Z → 09:56:45Z). Evidence:
  `presentation/lock-setup.json`, `lock-after.json`, `lock-undo.json`.
- Window title/brand/links re-rendering without a reload: **not observed —
  no window in this wave** (no window driving is permitted for this lane).
  The `settingsUpdated` emit is the source-level mechanism; the visual
  re-render is untested here and belongs to the principal's window check.
- On load the server MAY rewrite the file itself when a migration changes it
  (`serverSettings.ts:786-930`). In the rehearsal the file's sha was still
  the after-sha 10 s after the write (ledger 09:54:34Z) — no migration
  rewrite occurred on this build. If a future build's migration rewrites the
  file, `undo` will (correctly) refuse; re-plan and re-apply instead.

- In a team-project conversation the provider picker offers only that
  conversation's current instance, live, without a reload (the window
  reads `presentation` from the pushed settings;
  `composerInstanceLock.logic.ts:13-26`). Choosing another **model inside
  the same instance** still works: the window filters instances, not models
  (`applyComposerInstanceLock`, `composerInstanceLock.logic.ts:32-60`), and
  the server allows a model change on the conversation's own instance
  (`ProviderInstanceLock.integration.test.ts`, "allows a model change on the
  thread's own instance"). Multi-model is off in a locked conversation.
  The Chairman's own conversation on `capacity_fabric` stays on
  `capacity_fabric` and keeps taking his turns (ruling 20;
  `LOCK_EXISTING_CONVERSATIONS.md`).

### Is a restart needed?

**No.** Rehearsal evidence: the lock appeared and disappeared on the running
server with the runner pid unchanged (proofs (c), (e), (f) below). Do not
restart the team server for this change.

### 5. Undo (if wanted)

```sh
python3.12 tools/mmos_team_server/presentation_set.py undo \
  --settings "$HOME/.mastermind/t3-team/home/userdata/settings.json" \
  --receipt-dir "$HOME/.mastermind/t3-team/run/presentation-receipts-1" \
  --real-root-ok
```

`--receipt-dir` is the dir of the apply being undone. Undo also refuses a
receipt whose `settings_path` is not this settings file (resolved path and
file identity must both match). Refuses unless the current sha256 equals
the receipt's after-sha — i.e. if
anyone (including a writing `team_roster.py apply` or a server migration)
wrote the file since the apply, undo refuses and changes nothing. Restore
the exact preimage atomically; reads back the sha. The lock is gone again
without restart (rehearsal proof (e)).

### 6. team_roster interaction (rehearsal proof (d))

- An **idempotent** `team_roster.py apply` after the presentation write
  performs **no write at all** ("settings.json untouched"): sha unchanged,
  presentation intact (ledger 09:54:51Z).
- A **writing** apply (any real spec delta) round-trips ALL top-level keys
  through `json.load`/`json.dumps`, so the presentation key **survives as
  data**, but the whole file is reformatted (`indent=2`, no trailing
  newline) and its sha changes (ledger 09:56:06Z: `1ac04bc6…` → `84edddad…`,
  presentation still equal to the value). Consequence: a later `undo`
  against the old receipt **refuses** (proved, ledger 09:56:17Z). If you
  need undo after a writing roster apply, re-plan and re-apply presentation
  first into a FRESH receipt dir (`presentation-receipts-<next>`; the writer
  refuses a dir that already holds a receipt) to get a fresh receipt.
- Recommended order for the real root: run any roster apply FIRST, then
  presentation LAST, so the presentation receipt matches the final bytes.

## Rehearsal result table (2026-11-14, UTC; full ledger in presentation/LEDGER.md)

Root `~/.mastermind/mmos_dev/pf/realshape` — shape `<R>/root/home/userdata/…`,
`<R>/root/run`, `<R>/root/team-project`; label `com.mastermind.pf.realshape`;
port 3832 (free before start, lsof rc 1); same fake-launchd harness as wave-1
(fake `launchctl`/`id`/`sleep`/`claude`, HOME override, own launchd-state).
The provider CLI was the harness fake — **no teammate model turn ran**; the
13 primary threads were created by `team_roster.py apply` exactly as in
wave-1/partc. The lock probe launched ONE extra idle thread with **no
message** (`runId: null` — no turn) and only changed its model selection.

| Step | UTC | rc | s |
|---|---|---|---|
| setup: dirs 0700 + fake bins; 3832 free, staging 3830 up (pid 59230) | 09:41:45 | 0 | 1 |
| tests failing-first (writer absent) | 09:44:19 | 1 | 6 |
| tests after implementation — 34 passed | 09:46:05 | 0 | 8 |
| node tree copy + receipt path rewrite (wave-1 method) | 09:46:46 | 0 | 2 |
| pack `…-f5248ab2-rs` (real HOME, no rebuild; bin.mjs sha identical to staging f5248ab2) | 09:47:12 | 0 | 5 |
| resolve node+serve | 09:47:28 | 0 | 6 |
| seed settings (sanitized capacity_fabric) + dummy fabric.env 0600 + bin/t3 | 09:47:50 | 0 | 0 |
| install (harness) | 09:48:17 | 0 | 14 |
| runner pid baseline 17128 | 09:48:28 | 0 | 1 |
| build 13-teammate spec (3 base + 10 partc; absolute paths after HOME finding) | 09:48:52–09:49:22 | 0 | — |
| roster apply: 14 instances, 13 primary threads, project f2ea7f57-… | 09:49:44 | 0 | 16 |
| MCP session issue (0600 file; subject mcp-client after 401 finding) | 09:50:25–09:53:05 | 0 | — |
| probe setup: idle thread (runId null) + configure ACCEPTED before write | 09:53:21 | 0 | 0 |
| plan (server RUNNING): sha 8c03fe2e…, presentation absent | 09:53:34 | 0 | 0 |
| apply: preimage-checked, receipt before write → sha 1ac04bc6… | 09:53:51 | 0 | 1 |
| (a) cmp prefix (59994 B) + suffix (3 B) outside member — IDENTICAL; 390 B inserted | 09:54:34 | 0 | 0 |
| (b) 10 s later sha still 1ac04bc6… — server did NOT rewrite | 09:54:34 | 0 | 10 |
| (c) probe AFTER: REFUSED "This conversation belongs to Design Lead; …" — live, no restart | 09:54:35 | 0 | 0 |
| (d) roster re-apply: NO write, sha unchanged, presentation intact | 09:54:51 | 0 | 2 |
| (e) undo: preimage sha 8c03fe2e… restored | 09:55:11 | 0 | 0 |
| (e) probe AFTER undo: ACCEPTED again — lock gone, no restart | 09:55:35 | 0 | 0 |
| (d2) writing roster apply (accent delta): presentation survives as data; whole-file reformat; sha 84edddad… | 09:56:06 | 0 | 2 |
| (d2) undo after foreign write: REFUSED (writer rc 2, expected) | 09:56:17 | 2 | 1 |
| (d2) original spec re-apply: accent restored, presentation intact | 09:56:18 | 0 | 1 |
| (f) final pid check: 17128 == baseline | 09:56:45 | 0 | 0 |
| stop (bootout, process group) | 09:56:46 | 0 | 1 |
| post-stop: 3832 free; no stray procs; no real launchd job; staging 3830 STILL LISTEN (pid 59230, never stopped/sent to) | 09:56:59 | 0 | 1 |

## Findings (rehearsal-only; no tool changed)

1. The harness HOME override expands `~` in spec paths into the fake home —
   the realshape spec uses absolute paths. The principal runs under the real
   HOME, so `~` paths are fine there.
2. `/mcp` accepts only sessions with subject `mcp-client`
   (`EnvironmentAuth.authenticateMcpClient`); a default `auth session issue`
   (subject `cli-issued-session`) gets HTTP 401. Issue with
   `--subject mcp-client --scope orchestration:read --scope orchestration:operate`.
3. `node_install.py resolve` needs `config/server-runtime.json` — pack before
   resolve (wave-1 order confirmed).

## Tests (34)

`TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q -p no:cacheprovider tests/test_mmos_presentation_set.py`

Failing-first run recorded (rc 1, writer absent; ledger 09:44:19Z), then 34
passed (09:46:05Z). Properties: preimage mismatch refused with no write;
byte-for-byte outside-member equality (independent scanner, prefix/suffix)
for insert AND replace on odd-whitespace/key-order files; symlink refused;
18 bad-value shapes refused; undo restores identical bytes; undo refused
after foreign write; real-root path refused without the flag (and unlocked
by it, under a tmp HOME); mode preserved 0600 (and 0640); plan writes
nothing; receipt contents/permissions (preimage 0600, dir 0700); tampered
receipt refused; duplicate presentation key refused; no argument defaults;
empty-object and compact-file inserts.

## Evidence

- Ledger: `~/.mastermind/mmos_evidence/pf-20261114/presentation/LEDGER.md`
- Roster spec: `presentation/team_roster.realshape13.json` (+ accent-demo variant)
- Value: `presentation/presentation-value.realshape.json`
- Lock observations: `presentation/lock-setup.json`, `lock-after.json`, `lock-undo.json`
- Writer outputs: `presentation/plan.out`, `apply.out`, `tests-pass.out`
- Receipts (preimage copies, never printed): `<realshape>/root/run/presentation-receipts-1/`, `-2/`
- Byte proofs: `<realshape>/root/run/byteproof-1/` (cmp rc 0/0)