# INSTALL_RUNBOOK: W1 release (Option A), Tue 2026-11-10 04:10–05:40Z (rev 3.8; first drafted for Fri 2026-10-23)

PBR #1693, RUNTIME lane. **Commands only.** RUNTIME executed nothing on the host while writing this runbook.

| | |
|---|---|
| Approval | Seat ruling 2026-10-22: Option A, conditional; needrestart exclusion approved as a release-row item; the SDK pin is NOT in this window. **Rev 3 (2026-11-02, seat takeover of the RUNTIME lane):** the 2026-10-23 window was lost (the seat session died at the Fable usage limit 18:02Z 10-22 before its 03:25Z wake; no s0 ran; nothing was installed: `.deployed_git_sha` = OLD on 11-02 01:19Z). Re-run Mon 2026-11-02 with `PBR_DAY=2026-11-02` on s0 (same timeline, same gates, same hold); G7b widened by seat ruling D-G7B-1 and a git-only `g7b-selftest` step added; the s0 worktree-helper call drops `-I` (Python 3.14 isolated mode implies `-P`, which hides the helper's sibling `pool_storage` module, so rev 2 failed at s0 step 0.1 on the seat Mac); nothing else changed. **Rev 3.1 (2026-11-02, after independent review r1 = PASS_WITH_MINORS, no MAJOR):** the pyproject/lock line filters now count column-0 option lines (`-r`, `--index-url`, `-e`) as body lines and drop only the `---`/`+++` diff headers; the s0 helper call runs under `-E -s -B` (env and user-site isolation kept, the script directory still visible); `PBR_DAY=YYYY-MM-DD` is required (the stale 2026-10-23 default is gone); the selftest gains c9 (SDK floor outside the 0.2 series → STOP) and c10 (column-0 lock option line → STOP) and removes its temp dir on any stop. **Rev 3.2 (2026-11-02 03:50Z, after s1 ABORTed at `run_events read` on the live file's 10 pre-existing unparsed rows):** `events_tail` gains the D-EVT-1 pre-filter (G1 row, §7 note 10); nothing else changed. **Rev 3.3 (2026-11-02, after independent review r3 of rev 3.2 = PASS_WITH_MINORS, no MAJOR):** pre-filter hardening only — non-UTF-8 bytes pass through the pre-filter unchanged and such a row counts as unparsed (r3 MINOR-2: strict decoding would have crashed the step on a corrupt row that D-EVT-1 means to tolerate); the trusted `"ts"` prefix must carry the host's `+00:00` suffix (r3 NIT); and whenever the pre-filter reports `dropped_before_threshold > 0` the seat records the `DROPPED` head bytes from `logs/unparsed_rows.log` in the ledger after s1 and after s2 (r3 MINOR-1: a drop is tamper-evident, never silent). Nothing else changed. **Rev 3.4 (2026-11-03, seat ruling D-G7B-2):** the 2026-11-03 window was skipped at the 03:00Z precheck — `g7b-selftest` c8_live STOPped because #1362 (`0b3708856943ba9479c4ad968399d85c5bfc65a9`) added `requirements/executive-control-aead-macos-arm64-py312.{in,lock}` to master, a file pair outside the trio; no step ran and nothing touched the host. G7b now admits a requirements file *added* since OLD (absent at OLD; renames are split into delete + add) named `<stem>-macos-arm64-py312.{in,lock}` directly under `requirements/` and not named `gate-*`: the Linux deploy never pip-installs (T2 must show an unchanged venv) and `scripts/deploy_code_to_vps.sh` rsyncs with `--exclude='*.lock'`, so such a file cannot change the VPS runtime. s0 lists the admitted paths in `gates/G7b.RULING`. The non-comment lock-line count now reads only the two gate locks. The selftest gains c11–c19 (20 cases). Re-run Wed 2026-11-04 with `PBR_DAY=2026-11-04`. Nothing else changed. **Rev 3.5 (2026-11-05, seat ruling D-G7B-3, after independent review r5o of rev 3.4 = PASS_WITH_MINORS, no MAJOR):** the 2026-11-04 window was missed (the host slept through the session wakes) and the 2026-11-05 window was skipped at the 04:09Z precheck — `g7b-selftest` c8_live STOPped because #1909 (`7d6acb68`) regenerated both gate locks with header-comment-only changes while `pyproject.toml` stayed unchanged since OLD, a drift set outside the trio; no step ran and nothing touched the host. G7b now sends a drift that is a non-empty subset of the two gate locks (pyproject unchanged) to the existing non-comment lock-line check alone: 0 lines → `T2_MODE=equal`, any pin/extra/hash/option line → STOP. Folded r5o findings: the D-G7B-2 `comm` step must exit 0 and drop exactly as many lines as it admitted, else STOP (MINOR 1); the G7b row's rename wording is corrected (MINOR 2); the `gate-*` exclusion is case-insensitive; the `-U0` diffs run `--text --no-textconv --no-ext-diff`; and the s0 RULING text notes that an admitted `.in` is rsynced but never consumed (only `*.lock` is rsync-excluded). The selftest gains c20–c22 (23 cases). Re-run Fri 2026-11-06 with `PBR_DAY=2026-11-06`. Nothing else changed. **Rev 3.6 (2026-11-06, seat ruling D-G7A-1, after independent review r6 of rev 3.5 = PASS_WITH_MINORS, no MAJOR):** the 2026-11-06 window ABORTed at s0 G7a (03:38:37Z; no host step ran and nothing touched the host): #1422 (`b796d4505`) changed `portfolio/forward_evaluation.py` between OLD and SHA (blob `46031e40` → `13d15e91`, one hunk in `_current_exposure_metrics` on the `build_snapshot` path), which is a MECH path. The seat traced the hunk and found it inert: no deploy probe in `scripts/deploy_code_to_vps.sh` (status, init, finalize) reaches it, nor do this runbook's G4/G6 mirrors; `statuses` always carries `latest` (evidence `runtime-rev36-build-20261106T0607Z/G7A_forward_evaluation_trace.md`). G7a now admits exactly that mode+blob pair at OLD/SHA (`G7A_MODE=D-G7A-1`, recorded in `gates/G7a.RULING`). Any other blob or mode for that file, a change to any other MECH path, or a failed git read still STOPs. Folded r6 findings: the pyproject and gate-lock diff pipelines now check `PIPESTATUS`, so a git failure STOPs instead of reading as an empty diff (MINOR); the gate-lock diff runs with `--no-renames` (NIT); the s0 step-6 wording now says no non-comment lock line changed (NIT). A git-only `g7a-check` step joins the precheck. The selftest gains c23–c25 and a1–a14 (40 cases). Re-run Mon 2026-11-09 with `PBR_DAY=2026-11-09`. Nothing else changed. |
| Executor | The seat. The deploy key is Mac-held. |
| Source amendment | **Rev 3.7 (2026-11-07, D-G7A-2 and conditional D-G7B-4):** the assigned integration session adds one exact six-path OLD/SHA manifest for the three adjudicated mechanics changes. The old `none` and D-G7A-1 cases remain. The exact already-locked jsonschema declaration gains fresh same-interpreter conditions at s1/prelaunch/s4; T2 stays equal with no package installation. This is source qualification; it does not release the November 9 window, G7b/G8, live-idle/WAL/outbox, overnight, marker or authority gates. See the fixed manifest and qualification below. **Rev 3.8 (2026-11-09, seat rulings D-G7A-3 and D-G7B-5, after fabric review r8c of rev 3.7 + §A = PASS_WITH_MINORS, no MAJOR):** the 2026-11-09 window was skipped at the self-gate (rev 3.7 was unreviewed and its driver pinned a seat worktree path the precheck could not use; nothing touched the host). Master then moved: #2175 (`7a3c0b78`) changed `app/main.py` and `app/scheduler.py` again on top of the D-G7A-2 bundle, and #2228 (`28cbe35a`) + #2297 (`3652d890`) extended the D-G7B-4 pyproject/gate-lock change and added one test-only requirements file. G7a now also admits the exact D-G7A-3 six-path manifest and G7b the exact D-G7B-5 four-path manifests (sections below); D-G7B-5 carries the D-G7B-4 runtime condition unchanged. `rb health` additionally requires `reasoning_backend=waterfall` and `reasoning_policy=codex_first_claude_oauth_fallback`, so a Fabric-selected service fails the deploy health gate. §A: the driver's `SEAT_WT` is the RUNTIME worktree. Folded r8c findings: both driver-hash sites updated (MINOR 1); s0 STOPs when the frozen dependency source is unreadable instead of recording `legacy` (MINOR 2); the D-G7A-2 provenance cites the actual qualified source (MINOR 3); the s4 T2 hold message names its actual trigger (NIT 1); the fixture and the selftest ran at one driver hash (NIT 2). The selftest gains 13 D-G7A-3 and 23 D-G7B-5 cases (122); the runtime fixture gains 3 tests (15). Run on Tue 2026-11-10 with `PBR_DAY=2026-11-10`. Nothing else changed. |
| Inputs | `INSTALL_PROOF_PLAN.md` §1 (T1–T4), §2, §4, §5 and §7. |
| Driver | `runbook/install_w1.sh`. One subcommand per step. State lives in `$PBR_EV/state.env`, so every step runs from a fresh, stateless shell. |

## 0. What is installed, and what must not move

| Item | Value |
|---|---|
| OLD (installed now) | `ff16c192cc7b932e59c28c4fe30aeaf27bcb7595`. s1 proves it with T1(pre). |
| SHA (to install) | `origin/master` at window open. s0 fixes it, and G8 re-proves it at s2 and s3. On 2026-10-22 13:10Z master was `3a6d165fe398507bac179ab76b4ee01aa13116db`: 181 changed paths vs OLD, no deletions. That is the wave-1 merges (#1711 #1715 #1716 #1718 #1734 and ECON/RESEARCH merges) plus, since `fc4db8de`, non-bot `ops/native_fabric/grok47`, Executive OS edge/assets and docs. At 14:27Z master was `3d1cd77dfe84fee87922eb970e1a84cfdd9a0555` (+4 paths: #1719, the Self-Directed `unavailable` rendering in `app/web.py` and `app/static/index.html`, plus its test and evidence): 184 paths vs OLD, no deletions, G7a/G7b still empty. The SHA keeps moving until the hold; only G7a/G7b decide eligibility. |
| G7a (deploy/runtime mechanics drift OLD→SHA) | Empty (re-checked at `3d1cd77d`): `scripts/deploy_code_to_vps.sh`, `deploy_from_git.sh`, `refresh_datadog_release_tag.sh`, `app/main.py`, `portfolio/forward_evaluation.py`, `app/scheduler.py`. **Rev 3.6 / D-G7A-1:** one change is admitted: `portfolio/forward_evaluation.py` as the only changed MECH path, exactly `100644 blob 46031e40a2510b49cd4d3dce23a5ed05cc759213` at OLD → `100644 blob 13d15e91823d2b46b97dd4057c04d6c8628a29e0` at SHA (#1422 `b796d4505`). That is one hunk in `_current_exposure_metrics`, which only `build_snapshot` reaches; no deploy probe or runbook mirror reaches it. It sets `G7A_MODE=D-G7A-1` and writes `gates/G7a.RULING`. Any other blob or mode for that file → STOP. That covers deleted, added, reverted, re-edited or made executable. Another MECH path changed alongside it → STOP. A failed git diff or ls-tree read → STOP. On 2026-11-06 03:38Z, `ff16c192..44b7a471` was exactly that pair, and rev 3.5 stopped at s0. |
| G7b (dependency drift) | Empty → `T2_MODE=equal`. The #1714 trio with the `claude-agent-sdk>=0.2` floor → `T2_MODE=floor_pending` (the venv is still not upgraded in this window; T2 must show an unchanged venv). **Rev 3 / D-G7B-1:** the trio carrying only #1899's dev-only pytest bound (`"pytest>=8,<10"` → `"pytest>=8,<9.2"`, comment lines aside) with comment-only lock changes (every pin, extra and hash unchanged; pytest stays 9.1.1) → `T2_MODE=equal`; s0 always records `identity/dep_drift.diff` and records `gates/G7b.RULING` when the drift is non-empty. Any other non-comment pyproject line, any non-comment lock line without the SDK floor (column-0 option lines included, rev 3.1), or any file beyond the trio → STOP. On 2026-11-02 01:30Z `ff16c192..origin/master` was exactly the dev-bound case (rev 2 would have stopped at s0). **Rev 3.4 / D-G7B-2:** a file *added* since OLD (`--no-renames --diff-filter=A`) matching `requirements/<stem>-macos-arm64-py312.{in,lock}` (no subdirectory, not `gate-*`) is platform-scoped: it is admitted, listed in `gates/G7b.RULING`, and does not change `T2_MODE`. A modified or deleted pre-existing file of that shape, a `gate-*` name, a subdirectory or any other platform suffix still STOPs. Renames are split into delete + add (rev 3.5, r5o MINOR 2): a rename from another `requirements/` file or `pyproject.toml` STOPs (its delete half stays in the drift set); a move in from outside `requirements/` counts as an add and is admitted. The non-comment lock-line count reads only `requirements/gate-linux-x86_64-py312.lock` and `requirements/gate-macos-arm64-py312.lock`. On 2026-11-03 03:00Z `ff16c192..origin/master` was the dev-bound case plus #1362's added AEAD macOS pair (rev 3.3 stopped at the precheck selftest). **Rev 3.5 / D-G7B-3:** with `pyproject.toml` unchanged since OLD, a remaining drift set that is a non-empty subset of the two gate locks takes the same non-comment lock-line count alone: 0 → `T2_MODE=equal`, otherwise STOP. The trio path and D-G7B-2 are unchanged. On 2026-11-05 04:09Z `ff16c192..origin/master` was #1909's header-only regeneration of both gate locks plus #1362's added AEAD macOS pair (rev 3.4 stopped at the precheck selftest). |
| Forward-evaluation marker | Active: `start.json`, `deployment_sha=3c4ef7f8…`, `evaluation_start=2026-08-11`. G6 passes. The deploy takes the FORWARD_START_ACTIVE path (no init/finalize), and the marker must stay byte-identical (checked in s4). |
| Merge-queue hold | **No merge to `master` from 03:30Z until s3 has launched (to be safe, until 05:40Z).** Master is shared with non-PBR work (fabric and Executive OS merged at ~13:00Z on 10-22). If master moves after s0, G8 fails at s2/s3, and the wrapper would refuse anyway (rc 2). Recovery before 05:20Z: a new `s0` (new evidence dir), `s1`, then `s2`. |
| Never | Touch `/opt/mastermind-live-data`; rsync/scp toward the VPS outside the repo's deploy script; re-run s3; deploy a third SHA; copy `.env`/keys; run the SDK pin. |

### D-G7A-2: exact six-path source ruling (rev 3.7)

This additional case admits exactly the following OLD/target modes and blobs,
with **only** the first three paths changed. Every entry on both sides must be
present and its blob readable. It preserves the old `none` and sole D-G7A-1
cases; it does not allow arbitrary combinations or caller-selected hashes.

| Path | Mode on both sides | OLD blob | Target blob |
|---|---|---|---|
| `app/main.py` | `100644` | `fdb22dc1a2650ff57d50a1c9c1cfebcf10521da4` | `6106ff3dd2d55ba4f9eebe0440388fe2e446931c` |
| `app/scheduler.py` | `100644` | `ec2546731d69289b5af4837a6d1eefe59caf9b37` | `50dca31c852e9abe332bd9e191ff900e6c1fcdb3` |
| `portfolio/forward_evaluation.py` | `100644` | `46031e40a2510b49cd4d3dce23a5ed05cc759213` | `13d15e91823d2b46b97dd4057c04d6c8628a29e0` |
| `scripts/deploy_code_to_vps.sh` | `100755` | `f871e88815e70338a646008dbe77dfcc1727e978` | `f871e88815e70338a646008dbe77dfcc1727e978` |
| `scripts/deploy_from_git.sh` | `100755` | `f40e7895e88b0cd755fb7ef9b41a4783a1df4ed9` | `f40e7895e88b0cd755fb7ef9b41a4783a1df4ed9` |
| `scripts/refresh_datadog_release_tag.sh` | `100755` | `a7a32713ef1477d1b84398ff24c6b9fda938831e` | `a7a32713ef1477d1b84398ff24c6b9fda938831e` |

At protected source `f32ad4eb198c9562be74f5bc051a8afbd3a049c6` (rev 3.8, r8c
MINOR 3: rev 3.7 cited `320611cb` here; the evidence JSON and the
qualification run name `f32ad4eb`), these are the exact manifests against installed OLD
`ff16c192cc7b932e59c28c4fe30aeaf27bcb7595`. This is a qualification target,
not the future deployment SHA: the next window's s0 (rev 3.8: November 10) must freeze and re-evaluate its
actual target, and G8 must still prove it remains current.

`app/main.py` changes `/chat` and `/research` dispatch/recovery behavior.
`_runtime_health`, `_start_scheduler`, `health` and `ready` retain their source;
the W1 probes do not invoke the changed handlers. `app/scheduler.py` changes
Self-Directed daily-mark failure handling: a failed or unavailable mark skips
publication and retains the existing FREEZE event path, with cleanup in the
existing `finally` block. Schedule registration, startup, cohort and deployment
probes are unchanged. This later business-job behavior is intentional; the
release as a whole is not inert. The forward-evaluation hunk keeps the existing
D-G7A-1 rationale.

s0 writes the actual OLD and SHA, all six mode/blob pairs, changed and unchanged
paths, the bounded impact rationale and retained gates to `gates/G7a.RULING`.
The positive `g7a-check` uses the same classifier. G7b, G8, the W1
window, live-idle/WAL/outbox checks, overnight duties, active forward marker and
authority bytes remain required. A source PASS does not update `PIN.accepted`,
rebind a wake or authorize s3. Runtime dependency drift remains G7b's separate
decision, including the newly declared `jsonschema>=4.26,<5` at this source.

### D-G7B-4: exact already-locked declaration; runtime condition pending (rev 3.7)

The fixed declaration added by #2060 (`32a354c3dd77751e206a80b2abc4e497efdbe5e6`)
is `jsonschema>=4.26,<5`, including its exact inline comment. Both OLD gate
locks already pin `jsonschema==4.26.0`. The complete mode/blob pairs below are
required; all six blobs must be readable, the remaining dependency path set
must be exactly the trio after D-G7B-2 additions, no SDK-floor change may
accompany it, and the existing fail-closed non-comment lock comparison must
still pass. This does not admit other declarations, lock regenerations or a
caller-selected package/version.

| Path | Mode on both sides | OLD blob | Target blob |
|---|---|---|---|
| `pyproject.toml` | `100644` | `7f97e053ea7afd287ceec36d33a37faea85283eb` | `622259d33f04d40907075430c5228d6fbba2bae1` |
| `requirements/gate-linux-x86_64-py312.lock` | `100644` | `d7a925849235a42f088ba359e0308847a9316fcd` | `87471eec3fe0d41a1655411ec05be5e6519ab584` |
| `requirements/gate-macos-arm64-py312.lock` | `100644` | `3db3c9bdee75dd0212f24a252a8d002cf6f73992` | `53d9429e5f8bdf701f98d798b34fdf79afaf003c` |

s0 records `T2_MODE=equal`, distinct `G7B_MODE=D-G7B-4` and **RUNTIME CONDITION
PENDING** in the existing attempt. The previous G7b cases remain `G7B_MODE=legacy`.
The condition is re-derived from frozen OLD/SHA at each affected runtime step;
missing or mismatched attempt state cannot downgrade it to ordinary equality.

The original ledger-linked November 2 capture
`install-20261102T0338Z_19cb00cf/identity/pre/dists.txt` (1,390 bytes,
SHA256 `d9350e8738ee374d4393d968b7f2cf98f1b8687abbc6f5919c5e6164d9d2bcab`)
records `jsonschema==4.26.0` under the pinned `remote_dists.py` and service
venv. This proves historical metadata only. It does not prove current presence,
imports or equality to the locks; its `rpds-py` version differs from the locks.
The release preserves the actual installed venv, without pip or an SDK change.

At s1, the existing fresh T2 distribution list must contain exactly one
`jsonschema==4.26.0` entry. A fixed library-only fragment uses
`/opt/mastermind/.venv/bin/python -I -B`, verifies that interpreter and the
service's actual ExecStart path, imports `Draft202012Validator`/`FormatChecker`,
constructs a Draft 2020-12 schema and exercises valid/invalid values for the
Sector consumer's structural checks and `as_of` date format. The existing
nullable decision cutoff is null. The exact-session consumer uses its stdlib
clock/date checks without a FormatChecker; an optional RFC3339 date-time
checker is not a new installation requirement. This fragment never imports the
application or reads/writes portfolio state and makes no provider call.

Before s3, it freshly reads distributions again, requires complete equality to
s1, validates the prior proof's attempt/target/source bindings and repeats the
compatibility probe with a new nonce. **The existing `gates_all` runs after
this added work**, followed by the final host-clock/window check; only then
may `DEPLOY_T0` and `deploy.started` be written. The remote fragment has a
15-second timeout and local transport a 40-second timeout. Each response must
match the current nonce, attempt, phase, target, driver/program/distribution
hashes, interpreter identity and exact result shape; a stale-only or copied
response cannot satisfy the condition.

s4 repeats compatibility alongside full pre/post distribution equality. A T2
failure retains the existing no-rollback-without-seat disposition even when
another post-install proof also fails. Proofs stay in the original attempt's
`identity/{pre,prelaunch,post}/jsonschema.compatibility.json`; no new owner,
scheduler, retry or installation path is created. The W1 window, G7a,
G8, live-idle/WAL/outbox, overnight and marker/authority gates remain unchanged.
Actual post-install Sector consumption is still separate acceptance evidence.

### D-G7A-3: the D-G7A-2 bundle plus #2175 (rev 3.8)

#2175 (`7a3c0b78710ffa66140228b6e2af53036c78d63e`) changed `app/main.py` and
`app/scheduler.py` again. G7a admits exactly this six-path manifest as a
separate case: the same three changed paths, the same OLD manifest as
D-G7A-2, and new target blobs for the two app files. A mix of D-G7A-2 and
D-G7A-3 target blobs, any other blob or mode, an extra mechanics path, a
reverse, or an unreadable object STOPs.

| Path | Mode on both sides | OLD blob | Target blob |
|---|---|---|---|
| `app/main.py` | `100644` | `fdb22dc1a2650ff57d50a1c9c1cfebcf10521da4` | `ca6886c3ee02e6d58f992e6917be2739ce678ab9` |
| `app/scheduler.py` | `100644` | `ec2546731d69289b5af4837a6d1eefe59caf9b37` | `eb9840ad6086848e0ad3e44bc972fd7e7b67d7fe` |
| `portfolio/forward_evaluation.py` | `100644` | `46031e40a2510b49cd4d3dce23a5ed05cc759213` | `13d15e91823d2b46b97dd4057c04d6c8628a29e0` |
| `scripts/deploy_code_to_vps.sh` | `100755` | `f871e88815e70338a646008dbe77dfcc1727e978` | `f871e88815e70338a646008dbe77dfcc1727e978` |
| `scripts/deploy_from_git.sh` | `100755` | `f40e7895e88b0cd755fb7ef9b41a4783a1df4ed9` | `f40e7895e88b0cd755fb7ef9b41a4783a1df4ed9` |
| `scripts/refresh_datadog_release_tag.sh` | `100755` | `a7a32713ef1477d1b84398ff24c6b9fda938831e` | `a7a32713ef1477d1b84398ff24c6b9fda938831e` |

At protected source `3652d8907df1738de551dd3032b42aa2a2acb482` (#2297) and at
`6696153d323e3ab712884fa60cdf7bda6dbe5ce6`, these are the exact manifests
against OLD. As with D-G7A-2, this is a qualification target: s0 freezes and
re-evaluates the actual target.

#2175 adds a Fabric portfolio path. It is selected only by
`MM_PROVIDER_APPLICATION_MODE` in the service environment or a configured
fabric `cli_bridge` backend. Under the legacy selection with no runlog
original, `fabric_portfolio.caller_kwargs` is empty, so the job call shapes
and the `/health` values equal D-G7A-2. In `app/main.py` the `/health`
handler source changes: it gains a Fabric branch, and the legacy branch still
reports `reasoning_backend=waterfall` and
`reasoning_policy=codex_first_claude_oauth_fallback`. Rev 3.8 `rb health`
requires both values, so a Fabric-selected service fails the deploy health
gate (G4/T-health) rather than passing as legacy. Manual wait-runs use
`brain.fabric_chat._observe_thread` and end the ledger run on
`BaseException`; manual responses add `run_id` and `fabric_held`.

In `app/scheduler.py`, a `fabric_held` result maps to FREEZE
(`fabric_effect_unsettled`). Autonomous/china/hk whole-book retries are skipped
when a runlog original exists or Fabric is selected. Brain jobs pass
`caller_kwargs`. The overnight `watch_us`/`watch_asia` jobs pass the run
handle, re-raise a watch failure and record per-book ledger status instead of
an unconditional `ok`. `maybe_first_*` readiness accepts a runlog original,
Fabric availability (when Fabric is selected) or `cli_bridge` availability.
Schedule registration, startup, cohort and the deploy probes are unchanged.
This is intended later business-job behavior, not an inert release. The
forward-evaluation hunk keeps the D-G7A-1 rationale.

s0 writes the actual OLD and SHA, all six pairs, the rationale and the retained
gates to `gates/G7a.RULING` and records `G7A_MODE=D-G7A-3`. `g7a-check` uses
the same classifier and must print `g7a-check PASS (... G7A_MODE=D-G7A-3)` on
the expected master.

### D-G7B-5: D-G7B-4 plus #2228/#2297 (rev 3.8)

#2228 (`28cbe35a87a2575b57d8a2d7a4721dcdf13a5d6a`) and #2297
(`3652d8907df1738de551dd3032b42aa2a2acb482`) moved the D-G7B-4 sources. G7b
admits exactly these four-path manifests. The OLD side equals D-G7B-4, and
`requirements/hermes-transport-observation-test.in` must be absent at OLD.

| Path | Mode | OLD blob | Target blob |
|---|---|---|---|
| `pyproject.toml` | `100644` | `7f97e053ea7afd287ceec36d33a37faea85283eb` | `55d202a8847c2ca88f94943e8d1417623adb28bc` |
| `requirements/gate-linux-x86_64-py312.lock` | `100644` | `d7a925849235a42f088ba359e0308847a9316fcd` | `41b7b36a0ba8514475c4546003025f2a5324d12b` |
| `requirements/gate-macos-arm64-py312.lock` | `100644` | `3db3c9bdee75dd0212f24a252a8d002cf6f73992` | `3526e8fa0a7c9d8772969a75a5ec52071fa58c84` |
| `requirements/hermes-transport-observation-test.in` | `100644` (target) | absent | `39170f2e6bb26a824008615ccc93b57e40a6eb51` |

The non-comment pyproject drift must be exactly the D-G7B-4
`jsonschema>=4.26,<5` declaration plus this stanza:

```
[tool.setuptools.package-data]
"integrations.hermes_github_plugin" = ["plugin.yaml"]
```

The deploy never builds or pip-installs the project, so the package-data
stanza is inert on the VPS. Both gate-lock bodies change in comments only, and
the existing fail-closed non-comment lock count must still be 0. The test-only
`.in` is rsynced but never consumed. D-G7B-2 added macOS-arm64 files remain
admitted alongside. Any other path set, a missing, renamed, pre-existing or
executable `.in`, the pyproject without the package-data stanza, an SDK line,
any wrong OLD or target blob, a reverse, or an unreadable source blob STOPs.

`T2_MODE=equal`, and s0 records `G7B_MODE=D-G7B-5` with **RUNTIME CONDITION
PENDING**. The D-G7B-4 runtime condition above applies unchanged at s1,
prelaunch and s4. Its proofs carry `"ruling": "D-G7B-5"`. A baseline proof
recorded under a different ruling refuses with "D-G7B-5 runtime condition
REFUSED". `g7b_runtime_mode` re-derives D-G7B-4/D-G7B-5 from the frozen
OLD/SHA at every runtime step. An unreadable source (`g7b_ruled_mode` rc 1)
STOPs at s0 and at every later step; it is never treated as `legacy`.

## 1. Bootstrap, pins and conventions

### Pins

These are sha256 values. s0 re-verifies the three helpers; a mismatch aborts.

| File | sha256 |
|---|---|
| `runbook/install_w1.sh` | `3dd869109715307eb5ba90df69f3ef169be71e482e4ff81f41def2bc6ec39482` |
| `runbook/pbr_rb.py` | `e7d9a16b3dbe5e9ed085d0de7ece79590046f3b3a363cc41b84b84c93030c68a` |
| `runbook/remote_blob_manifest.py` | `49b3ca7d8b53074f1b6491eccc6371c8b214c75f86c6b75c6f126a6dcd4852bf` |
| `runbook/remote_dists.py` | `b15841d63d3480ea5b8af68ab2d321f2f65d546fa74365153979e127c32776e0` |

### Bootstrap

Run this in bash or zsh; it is plain POSIX.

```sh
SEAT_WT=/Volumes/Mastermind/agent-workspaces/claude/44ff44e73b840f81/pbr-runtime-rev3-22e74a0f5c56c38e
RB=research/commission_pbr_fable_masterplan/2026-10-22/lanes/RUNTIME/runbook
B=$(mktemp -d)
git -C "$SEAT_WT" fetch -q origin claude/ssd-pbr-runtime-85f3de87bc7b8894
git -C "$SEAT_WT" show "FETCH_HEAD:$RB/install_w1.sh" > "$B/install_w1.sh"
echo "3dd869109715307eb5ba90df69f3ef169be71e482e4ff81f41def2bc6ec39482  $B/install_w1.sh" | shasum -a 256 -c -      # expect: <path>: OK   (anything else: STOP)
env -u PBR_EV OPERATOR_SESSION_ID=<executing session id> PBR_DAY=2026-11-10 /opt/homebrew/bin/bash --noprofile --norc "$B/install_w1.sh" s0
# s0's last line prints:  export PBR_EV=/Volumes/Mastermind/evidence/pbr/install-<UTCyyyymmddThhmmZ>_<sha8>
```

### Every later step

```sh
PBR_EV=<dir printed by s0> /opt/homebrew/bin/bash --noprofile --norc "$PBR_EV/tools/install_w1.sh" <step>
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Step PASS (`GATE <x> PASS` / `<step> PASS` lines). |
| `1` | ABORT. The reason is on stdout and appended to `$PBR_EV/logs/stops.log`. Nothing after an ABORT ran. |
| `2` | Usage error. |
| `4` | The deploy (or R-c) is still running. |
| `5` | HOLD (s4a only). Report the listed evidence to the seat. A HOLD is not a rollback trigger by itself. |

### Conventions

**Host contact.** Every host contact is `ssh -o BatchMode=yes` to `root@146.190.142.17` with the deploy key, pipe-only.

**Read and write steps.**
- Read-only steps: s1, s2, s3-result, s4, s4a, s6, cycle, restart-check, needrestart-check, proof-old, status.
- Steps that change the host:
  - **s3**: the repo's deploy wrapper.
  - **s5 / s5-revert**: `/etc/needrestart` only.
  - **rollback-b / rollback-c**: seat-gated.

**Environment guard.** s0, s3 and rollback-c refuse when any `MASTERMIND_VPS_*`, `MASTERMIND_SERVE_ONLY`, `MASTERMIND_GIT_REMOTE`, `MASTERMIND_BASE_BRANCH` or `MASTERMIND_DEPLOY_*` variable is set, because the deploy scripts would honour it.

**Tool limits.** Each step finishes well inside the seat's 600 s tool timeout. The deploy is launched detached (`setsid` + `nohup`), so it survives the calling shell. It records its rc atomically in `logs/deploy.rc`.

## 2. Timeline (UTC, Tue 2026-11-10)

| When | Step | Host effect |
|---|---|---|
| 03:30 | Merge-queue hold begins | none |
| 03:40–04:05 | `s0` (local only: worktree at origin/master, evidence dir, pins, G7/G7a/G7b) | none |
| right after s0 | `s1` pre-change capture | read |
| 04:10, then every 10 min until PASS (last attempt 05:20) | `s2` gates | read |
| immediately after an s2 PASS, **before 05:30** | `s3` deploy (exactly once) | **write (deploy wrapper)** |
| every 60–90 s until exit ≠ 4 (expect 2–6 min) | `s3-result` | read |
| right after s3-result PASS | `s4` T1–T4 + /health + app_started + snapshot + marker | read |
| right after s4 PASS | `s4a` account-load check (D-ACCT-1), label `post-restart` | read |
| after s4 PASS (or after proof-old if the seat wants the row anyway), before 05:40 | `s5` needrestart row | **write (/etc/needrestart)** |
| after s5 | `s6` close (manifest + redaction scan) | none |
| 06:15, then every ~15 min while it says "not yet" (apt-daily-upgrade fires 06:00–07:00 and runs ~5–10 min) | `needrestart-check` | read |
| 07:05 | `cycle watch_us_overnight 06:20 autonomous`, then `s4a after-watch_us_overnight` | read |
| 08:40 | `restart-check 08:30` | read |
| 08:45 | `cycle china_daily 08:00 china`, then `s4a after-china_daily` | read |
| 09:45 | `cycle hk_daily 09:00 hk`, then `s4a after-hk_daily` | read |
| 15:45 | `cycle settle_pending 15:00 autonomous` (+G4 read) | read |
| 23:55 | `cycle autonomous_daily 23:10 autonomous` | read |
| Wed 11-11 02:20 | `cycle settle_brain_asia 01:35 china 2026-11-11` and `… hk 2026-11-11` | read |
| Wed 11-11 15:45 | `cycle settle_pending 15:00 autonomous 2026-11-11` (closes the US chain) | read |

If s2 has not passed by 05:20Z, the window is lost. Do not run s3. Report to the seat. A new window needs a new s0, because each evidence dir is spent per deploy attempt.

## 3. Steps

### s0: compose (03:40Z, local)

```sh
env -u PBR_EV OPERATOR_SESSION_ID=<id> PBR_DAY=2026-11-10 /opt/homebrew/bin/bash --noprofile --norc "$B/install_w1.sh" s0
```

**What it does**
1. Runs the environment guard. Requires `OPERATOR_SESSION_ID`. `PBR_DAY=YYYY-MM-DD` is required (rev 3.1: no default) and must be a weekday. Runs the epoch self-check (04:10 = `1792728600`, 05:30 = `1792733400`) only when `PBR_DAY=2026-10-23`. Checks for the deploy key and the tools.
2. Creates a fresh worktree from `origin/master` via `worktree_storage.py create` (external SSD policy). HEAD must equal `git ls-remote origin refs/heads/master`, and the tree must be clean.
3. Creates `$EV=/Volumes/Mastermind/evidence/pbr/install-<cid>` and records `CAPTURE_ID`, `SHA`, `WT` and `DAY`.
4. Extracts the three helpers from `origin/claude/ssd-pbr-runtime-85f3de87bc7b8894` and runs `shasum -a 256 -c` against the pins. Copies the driver to `$EV/tools/`.
5. Records tool versions and runs a local-only rsync flag probe.
6. Runs the composition gates:
   - **G7**: OLD is an ancestor of SHA.
   - **G7a**: the mechanics diff is empty (`G7A_MODE=none`), the existing sole D-G7A-1 forward-evaluation pair, the complete D-G7A-2 manifest above (`G7A_MODE=D-G7A-2`), or (rev 3.8) the complete D-G7A-3 manifest above (`G7A_MODE=D-G7A-3`). The latter two require exactly three changed paths, both full six-path mode/blob manifests and readable referenced blobs. s0 records actual frozen OLD/SHA, all six pairs and the bounded impact rationale in `gates/G7a.RULING`. The precheck runs the same classifier through `g7a-check`; it is Git-only, reads SEAT_WT `origin/master`, and must print `g7a-check PASS`.
   - **G7b**: dependency drift is empty, exactly the #1714 trio with only the `claude-agent-sdk>=0.2` floor changed, or (rev 3, D-G7B-1) the trio with only the dev pytest bound and comment-only gate locks; (rev 3.4, D-G7B-2) any of these plus added macOS-arm64 platform files; (rev 3.5, D-G7B-3) with pyproject unchanged, one or both gate locks changed with no non-comment lock line changed (comment-only or metadata-only). This sets `T2_MODE`. The exact D-G7B-4 pair and (rev 3.8) the exact D-G7B-5 manifest additionally require the conditional T2 checks above; an unreadable frozen dependency source STOPs. Run `g7b-selftest` (122 cases: 40 retained, 23 D-G7A-2, 23 D-G7B-4, 13 D-G7A-3 and 23 D-G7B-5 discriminators; no host contact) before s0; it must print `g7b-selftest PASS`.
7. Writes `identity/old_to_sha.name-status.txt`.

**PASS output**

```
GATE G7 PASS
s0 PASS: SHA=<40 hex> T2_MODE=equal|floor_pending G7A_MODE=none|D-G7A-1|D-G7A-2|D-G7A-3 G7B_MODE=legacy|D-G7B-4|D-G7B-5 WT=<path>
export PBR_EV=<path>
```

Check that SHA equals the master the seat expects at the hold. Check that `$PBR_EV/identity/old_to_sha.name-status.txt` has no `D` rows. Then skim its `bot/ brain/ app/*.py portfolio/ data_layer/ config/` rows for anything beyond the merges the seat has accepted. (On 13:10Z the count was 181 paths.) An unexpected runtime path is a seat question before s3, not a driver failure.

**ABORT conditions**

| Condition | Action |
|---|---|
| Environment override, missing session id, weekend day | Fix and re-run s0. |
| Worktree creation failed, or HEAD != remote master (master moved during s0) | Remove the new worktree and re-run s0. |
| Helper pin mismatch | STOP, ask RUNTIME. |
| G7a non-empty outside the exact D-G7A-1 pair or complete D-G7A-2/D-G7A-3 manifest; a mix of D-G7A-2 and D-G7A-3 target blobs; any foreign/missing mode/blob, additional mechanics path or Git/object read failure | STOP for a source ruling. The runbook's mechanics mirrors are not admitted. |
| G7b drift beyond the trio (other than D-G7B-2 added macOS-arm64 platform files) and beyond the D-G7B-3 gate-lock subset, a non-comment gate-lock change without the SDK floor, a D-G7B-2 `comm` failure or count mismatch, a pyproject line other than the SDK floor / the ruled dev bound / the complete exact D-G7B-4 pair / the complete exact D-G7B-5 manifest, (rev 3.6, r6 MINOR) a failed pyproject or gate-lock diff, or (rev 3.8, r8c MINOR 2) an unreadable frozen G7b source | STOP, seat. |

### s1: pre-change capture (read-only)

```sh
PBR_EV=… /opt/homebrew/bin/bash --noprofile --norc "$PBR_EV/tools/install_w1.sh" s1
```

**What it reads (§2)**

| Read | Saved as |
|---|---|
| `systemctl show mastermind.service` (12 props) | `captures/pre/systemctl_show.txt` |
| The ExecStart path, and the EnvironmentFiles **names only** | |
| T3: sha256 of the unit fragment + drop-ins | `identity/pre/unit_sha256.txt` |
| T2: venv dist list | `identity/pre/dists.txt`; must contain `claude-agent-sdk==` and `anthropic==`. D-G7B-4/D-G7B-5 additionally requires `jsonschema==4.26.0` and fresh `identity/pre/jsonschema.compatibility.json`. |
| T1: blob manifest of `/opt/mastermind`, compared with `git ls-tree OLD` | `rb t1 … --sha OLD` must PASS with `marker_claim_matches: true` |
| T1 against SHA, as a prediction | `identity/pre_vs_sha/` (expected FAIL: differing+missing are the paths the deploy will write) |
| Book state: sha256/stat of account, fills, decisions, pending_target and paper_transaction for autonomous/china/hk, plus receipt counts | `captures/pre/book_state.txt` |
| `start.json` sha256 + mtime (never its content) | |
| `.deploy_prev` snapshot listing | |
| `df` under `/opt/mastermind` (≥ 1 GiB free) | |
| pending_target per book | |
| Decisions in the last 48 h, trimmed | |
| run_events tail (20000 lines, `extra.flags` dropped) | |
| pid-1 journal for the unit (24 h) | |
| `systemctl list-timers --all` | |

**PASS output**

```
GATE PRE PASS
s1 PASS: pre-change capture complete; predicted deploy delta: {...}
```

**ABORT conditions**

| Condition | Action |
|---|---|
| Service not active | Seat. |
| T1(pre) vs OLD FAIL, or the marker does not claim OLD | Seat; the host is not OLD (see `identity/pre/identity_manifest.tsv`). |
| SDK/anthropic dists missing | Seat. |
| Less than 1 GiB free | Seat. |
| ssh failure | Fix the transport only; never switch key/host. |

### s2: gates (read-only, repeat until PASS)

```sh
PBR_EV=… /opt/homebrew/bin/bash --noprofile --norc "$PBR_EV/tools/install_w1.sh" s2
```

| Gate | PASS condition | On fail |
|---|---|---|
| G5 | Host clock in `[04:10, 05:30)` | Wait (before 04:10) or abandon the window (after 05:30). |
| G8 | `ls-remote origin master == SHA` | Seat. Hold, or start over from s0 with a new evidence dir. |
| G1 | `watch_us_overnight` 02:20 has `run_finished`. The run_events tail must cover the window, and every row must parse — **rev 3.2 / D-EVT-1:** a row that does not parse is dropped (and recorded in `logs/unparsed_rows.log`) only when its leading `"ts"` prefix parses and is strictly before the running process's `ActiveEnterTimestamp` (`gates/process_active_enter.txt`; while that file is missing or empty, 00:00Z two days before DAY); any other unparsed row still stops the step. Rev 3.3: the prefix must end in `+00:00`, a row carrying invalid UTF-8 bytes counts as unparsed, and when `dropped_before_threshold > 0` the seat ledgers the `DROPPED` head bytes from `logs/unparsed_rows.log`. | Hold and re-run s2 every 10 min. **Seat-only waiver:** `PBR_WAIVE_G1='<ruling ref>'` (written to `gates/G1.WAIVER`). |
| G2E | No `run_started` without `run_finished` since the service's `ActiveEnterTimestamp` | Hold and re-run. `prewarm_marks` is ledgered and fires every 2 min (`*/2`, hours 1–9 and 13–21 UTC, mon–fri), so an open `prewarm_marks` run is the expected cause of a G2E hold in the window: re-run s2 after ~2 min instead of 10. A row older than its job's normal duration is a ledger anomaly. **Seat-only waiver:** `PBR_WAIVE_G2E='<ruling ref>'` (`gates/G2E.WAIVER`). The cgroup check below still applies. |
| G2 | No `claude`/`node`/`codex` process in the service cgroup (no LLM run in flight) | Hold and re-check. Not waivable. |
| G3 | `apt-daily`/`apt-daily-upgrade` inactive or failed; 0 unattended-upgrade/needrestart/apt/dpkg processes; `fuser` lock holders = no; `apt-daily-upgrade.timer` next elapse ≥ 05:55Z, read as the raw D-Bus property `NextElapseUSecRealtime` (`busctl get-property … Timer NextElapseUSecRealtime` → `t <µs>`), because systemd 255 prints `systemctl show` timer values as dates even with `--timestamp=unix` | Hold and re-check. If the next elapse is < 05:55, 0 or unknown: seat ruling. |
| G4 | Settlement state `clean` (a read-only mirror of the deploy's rc 21/22/23 checks: no `paper_transaction.json`, no `settlement_receipts/*.json`) | Seat ruling. **Never "repair" live data.** |
| G6 | `python3 -B -m portfolio.forward_evaluation status` rc 0 against the live root, and the `start.json` marker present | Seat. The deploy would init/finalize a marker. |

**PASS output:** `GATE G5 … G6 PASS`, then `s2 PASS: all gates clear - run s3 now`.

Waivers are environment variables read at gate time. If the seat waived a gate at s2, the same variable must be set again for **s3**, which re-runs every gate.

### s3: the deploy (exactly once)

```sh
PBR_EV=… /opt/homebrew/bin/bash --noprofile --norc "$PBR_EV/tools/install_w1.sh" s3
```

The step:
1. Refuses if `logs/deploy.started` exists.
2. Runs the environment guard.
3. Re-runs every s2 gate.
4. Records `DEPLOY_T0` from the host clock, which must be before 05:30.
5. Launches, detached, exactly this command (do not type it by hand):

```sh
cd "$WT" && MASTERMIND_DEPLOY_LOG="$PBR_EV/logs/deploy.log" ./scripts/deploy_from_git.sh <SHA>
# stdout/stderr -> $PBR_EV/logs/deploy.stdout ; rc -> $PBR_EV/logs/deploy.rc ; pid -> $PBR_EV/logs/deploy.pid
```

**Expected output:** `deploy LAUNCHED pid=<n> DEPLOY_T0=<epoch> sha=<SHA> - expect 2-6 min; poll with s3-result; never interrupt`.

`deploy.log` timestamps are Mac local time. The evidence uses UTC everywhere else.

### s3-result: classify the deploy (read-only; poll)

```sh
PBR_EV=… /opt/homebrew/bin/bash --noprofile --norc "$PBR_EV/tools/install_w1.sh" s3-result
```

Foreground sleep is blocked, so the seat can wait between polls with a `Monitor` until-loop on `test -f "$PBR_EV/logs/deploy.rc"`.

| Evidence | Verdict | Next |
|---|---|---|
| No rc file, pid alive | exit 4 `deploy still running` | Poll again. Never interrupt. |
| No rc file, pid gone | **EFFECT UNKNOWN** | Do not re-run. Read `logs/deploy.log`. Seat decides R-b (§4). |
| rc 0 + `deploy OK: mastermind.service healthy at commit <SHA>` | `GATE DEPLOY PASS` | s4 |
| rc 0 + `deploy no-op` | ABORT: host already at SHA although T1(pre) said OLD | Seat |
| rc 2 | Refused before any host change | Nothing touched. Seat decides retry/next window (new s0). |
| rc 1/130/143, no `; rolling back` line | Failed before the service stop | Nothing touched. Seat. |
| rc 1/130/143 + `code rollback verified; health returned …; runtime data retained` | **R-a**: automatic rollback verified | `proof-old`, then the seat |
| rc 1/130/143 otherwise | Rollback INCOMPLETE | R-b decision table (§4) |

### s4: post-install proof (read-only; §4 of the plan)

```sh
PBR_EV=… /opt/homebrew/bin/bash --noprofile --norc "$PBR_EV/tools/install_w1.sh" s4
```

| Check | PASS condition |
|---|---|
| **T1** | The blob manifest equals `git ls-tree SHA`, and `.deployed_git_sha` claims SHA (`identity/post/t1_verdict.json`). |
| **T2** | `identity/pre/dists.txt` == `identity/post/dists.txt`. The deploy never touches `.venv`. D-G7B-4/D-G7B-5 also requires fresh same-interpreter post-install compatibility; any T2 failure keeps the no-rollback hold. Rev 3.8 (r8c NIT 1): a compatibility failure prints its own reason in the T2 STOP message instead of the dist-list mismatch text. |
| **T3** | Unit and drop-in hashes are unchanged, except `81-datadog-version.conf`. That file must hash to `[Service]\nEnvironment=DD_VERSION=<SHA>\n` (when `80-datadog.conf` exists). `NeedDaemonReload=no`. |
| **T4** | The loaded process started at or after `DEPLOY_T0`, from the T1-proven tree (`rb t4`). |
| /health | Reports SHA. |
| app_started | A `startup/app_started` run_event with `git_sha=SHA` since `DEPLOY_T0`, plus the cutover preflight rows. |
| Snapshot | Exactly one new `.deploy_prev/snapshot.*`, `complete=1`, `sha=OLD`. It is recorded as `SNAP` for R-b. |
| Forward marker | `start.json` sha256 unchanged, and `forward_evaluation status` rc 0. |

**PASS output:** `GATE PROOF PASS` and `s4 PASS: installed = <SHA> …`. `INSTALLED=<SHA>` is recorded.

**ABORT conditions**

| Condition | Action |
|---|---|
| app_started not yet visible | Re-run s4 once after 60 s. |
| T2 FAIL | **STOP**. The venv changed outside the deploy; no rollback without the seat. |
| Any other FAIL | R-b decision table (§4) with the seat. |

A `quarantined` cutover preflight is printed as an INCIDENT. It does not fail the proof; report it to the seat.

### s4a: account-load check (D-ACCT-1; read-only)

Run this right after s4 PASS, and again after each book's first natural cycle (see s7):

```sh
PBR_EV=… /opt/homebrew/bin/bash --noprofile --norc "$PBR_EV/tools/install_w1.sh" s4a                        # label: post-restart
PBR_EV=… /opt/homebrew/bin/bash --noprofile --norc "$PBR_EV/tools/install_w1.sh" s4a after-china_daily      # one new label per read
```

**Why.** #1747 (D-ACCT-1, `portfolio/paper_account.py`) makes an existing-but-invalid `account.json` fail closed. The load raises `AccountStateInvalid`. Before raising, it does three things:
- writes a byte-for-byte copy `account.quarantine.<sha16>.json` beside the original;
- appends one row to `account_quarantine.jsonl`;
- emits one `account_state_invalid` run_event.

If #1747 lands before s0, the install carries this behaviour. The proof is that the active books load without `AccountStateInvalid`.

**Scope.** Four books are active. Three of them (autonomous, china, hk) load through `paper_account`. **self_directed does not.** It has its own engine and account file (`portfolio/self_directed.py`, `data/portfolio/self_directed/account.json`). `app/scheduler.py` excludes it from the paper_account books (the `_MARK_BOOK_IDS` note). `AccountStateInvalid` therefore cannot arise for it, and s4a reports it as `self_directed=n/a(own-engine)`.

| Check | PASS condition |
|---|---|
| Quarantine census | No `account.quarantine.*.json` and no `account_quarantine.jsonl` in any paper_account data dir. The dirs scanned are the legacy `/opt/mastermind-live-data/portfolio/` and every `/opt/mastermind-live-data/portfolios/*/`, archived books included, because a load quarantines beside the original. Only `test`, `sha256sum` and `stat` run. The census must finish (`census_done`) and must list autonomous, china and hk. |
| run_events | No `kind=account_state_invalid` row with `ts ≥ DEPLOY_T0`. An unparseable `ts` counts as after the deploy. |
| Journal | No `account_state_invalid` / `AccountStateInvalid` line in the unit journal since `DEPLOY_T0`. |
| Classification | autonomous, china and hk each classify VALID. INVALID is a HOLD. MISSING is also a HOLD, because the next load of an active book would seed a fresh one. |

**How classification works.**
- It runs only when SHA contains `class AccountStateInvalid`.
- It uses SHA's own read-only `account_file_status(path=…)`, run on the Mac from `git archive SHA`.
- Each `account.json` is read over ssh into a 0600 temp file and deleted right after classification.
- Nothing is imported on the host, so the host `.env` is never loaded.
- `status.<book>.json` holds only the status, sha256, size and problem codes (ticker labels at most).

If SHA does not contain #1747, s4a prints `classification skipped` and runs the other three checks.

**PASS output:** `GATE ACCT_<label> PASS` and `s4a PASS (<label>): no quarantine file, no account_state_invalid event/journal line since DEPLOY_T0; autonomous=VALID china=VALID hk=VALID self_directed=n/a(own-engine)`.

**HOLD (exit 5).** Any quarantine file, event, journal line, or INVALID/MISSING classification writes `gates/ACCT_<label>.HOLD`. The expected result is that no book is quarantined.

A HOLD is **not a rollback trigger by itself**:
- Report `proof/account_load/<label>/` to the seat.
- The affected book stays halted by design. Do not "repair" the account, reset it, or delete the quarantine file.
- Clearing the quarantine is a human action outside this runbook.
- s5/s6 may proceed unless the seat says otherwise.

**ABORT (exit 1).** Any of the following is a read failure, not a verdict; re-run s4a with a new label:
- the census, run_events, journal or `account.json` read fails;
- the census is incomplete or lacks an active paper_account book's dir;
- the run_events tail is empty;
- the label already exists.

### s5: needrestart release row (writes `/etc/needrestart` only)

```sh
PBR_EV=… /opt/homebrew/bin/bash --noprofile --norc "$PBR_EV/tools/install_w1.sh" s5
```

**Order of operations**
1. Requires `PROOF` or `PROOF_OLD`.
2. Confirms that `needrestart.conf` includes `conf.d/*.conf`.
3. `verify_before` must be rc 3 (no mastermind override).
4. Backup (host): `cp -a /etc/needrestart /root/needrestart.backup.<CAPTURE_ID>`, followed by `diff -r` and a sha256 list, saved to `needrestart/backup_sha256.txt`. It refuses if the backup path already exists.
5. Writes the drop-in. This is the exact content of `/etc/needrestart/conf.d/99-mastermind-no-autorestart.conf`, mode 0644, written atomically via `mktemp` + `mv`. It refuses if the file or a symlink already exists.

   ```perl
   # PBR #1693 W1 release row (seat-approved 2026-10-22): needrestart must never auto-restart mastermind.service.
   # Restarts happen only via the deploy script or mastermind-restart.timer. Revert: rm this file.
   # Backup of /etc/needrestart: /root/needrestart.backup.<CAPTURE_ID>
   $nrconf{override_rc}{qr(^mastermind(?:\.service)?$)} = 0;
   ```

6. The hash read back must equal the local file.
7. `verify_after` must be rc 0. The verify loads the real `needrestart.conf` (with its `conf.d` loop) in perl and checks that `mastermind.service` matches an `override_rc` key with value 0. The key matches `mastermind.service` and `mastermind`, but not `mastermind-restart.service`. If verify_after is not rc 0, the drop-in is removed automatically and the step ABORTs.

**PASS output:** `GATE NEEDRESTART PASS` and `s5 PASS: restart_mode=<…> override=(?^:^mastermind(?:\.service)?$) value=0`.

**Revert**

```sh
PBR_EV=… …/install_w1.sh s5-revert
```

This runs `rm -f /etc/needrestart/conf.d/99-mastermind-no-autorestart.conf` and then verifies rc 3. Full restore from the backup, by hand and seat only:

```sh
ssh … 'rsync -a --delete /root/needrestart.backup.<CAPTURE_ID>/ /etc/needrestart/'
```

Apt-timer bounding is **deferred** (not in this window).

### s6: close (local)

```sh
PBR_EV=… …/install_w1.sh s6
```

This writes `manifest.json` (the sha256 of every evidence file) and runs a redaction scan. `tools/` is hashed only. **PASS output:** `s6 PASS: {"check": "close", …}`. On a redaction hit, redact the listed files before sharing anything.

### s7: first natural cycles (read-only)

```sh
PBR_EV=… …/install_w1.sh cycle <job> <HH:MM> [book] [YYYY-MM-DD]
PBR_EV=… …/install_w1.sh restart-check [HH:MM] [YYYY-MM-DD]
PBR_EV=… …/install_w1.sh needrestart-check [YYYY-MM-DD]
```

`cycle` refuses before fire + 45 min. It writes `cycles/<day>T<HHMM>Z_<job>[_<book>]/`, containing:
- the run_events tail and the cycle verdict (`rb cycle --since fire-5min`): run_started/run_finished, `extra.target_status`, `restarts_in_window`, `disposition_hint`;
- the trimmed decision rows for the book;
- `/health` vs `INSTALLED`;
- the pid-1 journal since `DEPLOY_T0`;
- for `settle_*` jobs, the G4 settlement read.

Every due cycle maps to exactly one §5 disposition: `not_due`, `disabled`, `started`, `accepted_no_change`, `accepted_change`, `rejected`, `failed` or `incomplete_uncertain`. The hint is the RUNTIME reading; the seat records the final disposition. An `incomplete_uncertain` requires an incident note naming the missing evidence.

**Known hazard:** the 08:30Z `mastermind-restart.timer` can cut an in-flight `china_daily` (fired at 08:00). If `restarts_in_window>0`, record it.

**Account load at the cycle.** A book's `account.json` is definitively loaded by its first natural cycle, not necessarily at startup. After each first cycle read (`watch_us_overnight` for autonomous, `china_daily`, `hk_daily`), run `s4a after-<job>`. self_directed is outside D-ACCT-1 (own engine). An s4a HOLD is reported to the seat; it is not a rollback trigger by itself.

`restart-check` refuses before fire + 10 min. It requires an `app_started` with `INSTALLED` after the timer, plus /health. A failure is an incident; it does not trigger a rollback.

**needrestart-check (§6 #1, first real proof of the s5 row).** It refuses unless `NEEDRESTART.PASS` exists and s5 was not reverted. Its baseline is `rollback/proof/systemctl_show.txt` when `PROOF_OLD.PASS` exists, else s4's `captures/post/systemctl_show.txt`. The cut is `<day>T05:40Z`. It stops with exit 1 and "not yet" until `apt-daily-upgrade.service` has started after the cut and finished (`ActiveState` inactive/failed with an exit time); re-run it. It also stops if the host clock is not `+0000`, because the dpkg log is in host local time. It then reads, all pipe-only:
- `/var/log/unattended-upgrades/unattended-upgrades-dpkg.log`, where needrestart writes its report (on 10-22 the journal carried none; see §6 #1). The driver keeps only the `Log started:` blocks at or after the cut.
- `unattended-upgrades.log` since the cut, the journal since the cut filtered to `needrestart` (normally empty), and the pid-1 journal for `mastermind.service` since cut − 5 min.
- `systemctl show mastermind.service` and the s5 perl verify.

Matching is by exact token (`(^|\s)mastermind\.service(\s|$)`), so `mastermind-restart.service` and `mastermind-control-room-remote.service` never count. Verdicts:

| Verdict | Exit | Meaning |
|---|---|---|
| `PROVEN` | 0 | `mastermind.service` is under `Service restarts being deferred:` and nothing restarted it. §6 #1 is proven. |
| `LISTED` | 0 | Only under `Services to be restarted:` (list mode) and nothing restarted it. The restart-mode override was not exercised. |
| `VACUOUS` | 0 | No needrestart block since the cut names `mastermind.service` (no relevant library upgrade). §6 #1 is still unproven; re-run on a later day with `needrestart-check <day>` (each run covers from that day's 05:40Z). |
| `FAIL` | 1 | Any of: `mastermind.service` under `Restarting services...`; a pid-1 Stopping/Stopped/Starting/Started/Deactivated/Killing/Scheduled-restart line inside an unattended-upgrade interval (`[apt start − 5 s, apt exit + 120 s]` and each dpkg block `[start − 5 s, end + 120 s]`, so a run outside apt-daily-upgrade counts too); `ActiveEnterTimestamp` inside such an interval or unreadable; `NRestarts` higher than the baseline or unreadable; `ActiveState` not active; the s5 verify not rc 0. |

A FAIL is an **INCIDENT**: report it to the seat with the evidence dir. It is not a rollback trigger, and s5-revert does not undo a restart that already happened. Notes (not failures) record an `InvocationID` change, an `NRestarts` decrease (a manual restart resets it) and an interval overlapping the 08:30Z `mastermind-restart.timer`.

## 4. Rollback decision table

This follows the seat's rule: rollback = the deploy script's `rollback_release` to the `.deploy_prev` snapshot, and never touches `/opt/mastermind-live-data`.

| Situation | Route | Commands |
|---|---|---|
| s3-result says R-a (automatic rollback verified) | **R-a**: nothing more on the host | `…/install_w1.sh proof-old` (read-only: T1 vs OLD + marker, T4, /health=OLD, app_started=OLD, start.json unchanged), then report to the seat. |
| Rollback incomplete, EFFECT UNKNOWN, or s4 FAIL (not T2) and the seat says roll back | **R-b**: manual mirror of `rollback_release` (lines 205–229 of `deploy_code_to_vps.sh`) | `PBR_CONFIRM=R-b PBR_EV=… …/install_w1.sh rollback-b`, then ≥ 60 s later `…/install_w1.sh proof-old` |
| No usable snapshot (R-b preconditions fail) and the seat rules OLD must be restored | **R-c**: transactional re-deploy of OLD through `deploy_code_to_vps.sh` from `git archive OLD` | `PBR_SEAT_RULING='<ref>' PBR_EV=… …/install_w1.sh rollback-c`, poll `…/install_w1.sh rollback-c-result` (exit 4 = running), then `proof-old` |
| T2 FAIL | **STOP**: no rollback without the seat | none |

### R-b preconditions (enforced)

R-b runs only when all of the following hold:
- exactly one new snapshot, `complete=1`, `sha=OLD`;
- G4 `clean` (new code wrote no v2 WAL/receipts; otherwise a seat ruling is required);
- no open run since `DEPLOY_T0`. `prewarm_marks` (every 2 min, ledgered) can be the open run at the instant of the check. That stop happens before any host change, so re-run `rollback-b` after ~2 min;
- `EXC` parsed from `$WT/scripts/deploy_code_to_vps.sh` has 29 entries, including `data` and `.deploy_prev`.

### R-b host commands, as sent

`<snap>` = `/opt/mastermind/.deploy_prev/snapshot.<id>`. `$EXC` = the deploy's 29 `--exclude=` args, shell-quoted.

```sh
systemctl stop mastermind.service; systemctl show mastermind.service -p ActiveState -p MainPID   # must be inactive|failed and MainPID=0, else ABORT (source NOT restored)
set -e
rsync -ac --delete $EXC '<snap>/tree/' '/opt/mastermind/'
difference=$(rsync -acn --delete --itemize-changes $EXC '<snap>/tree/' '/opt/mastermind/'); [ -z "$difference" ]
# restore .deployed_git_sha from <snap>/deployed_git_sha (or remove it if <snap>/deployed_git_sha.absent)
# if <snap>/datadog.enabled: restore 81-datadog-version.conf from <snap>/datadog_version (or remove it), then systemctl daemon-reload
echo restore_verified
systemctl restart mastermind.service
```

If the restore verification fails, the service is left **stopped** (never boot a mixed tree), and the seat decides.

### R-c host effect

R-c runs:

```sh
MASTERMIND_DEPLOY_SOURCE=<archive of OLD>/ MASTERMIND_DEPLOY_EXPECT_SHA=ff16c192… <archive>/scripts/deploy_code_to_vps.sh
```

It is launched detached and logs to `rollback/rc.deploy.log`. It is classified like s3: `deploy OK … ff16c192…`, R-a or incomplete.

## 5. Evidence layout (`$PBR_EV` = `/Volumes/Mastermind/evidence/pbr/install-<UTCyyyymmddThhmmZ>_<sha8>/`)

```
state.env                    CAPTURE_ID SHA WT DAY T2_MODE G7A_MODE G7B_MODE DEPLOY_T0 DEPLOY_RC SNAP INSTALLED ROLLED_BACK
tools/                       install_w1.sh + the 3 pinned helpers
logs/                        runbook.log stops.log pins.txt tools.txt rsync_flag_check.txt
                             deploy.log deploy.stdout deploy.rc deploy.pid deploy.started close_verdict.json
gates/                       <G>.PASS markers, G1_G2.json, run_events.gates.jsonl, G2_cgroup.txt, G3_apt.txt,
                             G4_settlement.txt, G5_host_epoch.txt, G6_forward_status.json, G6_marker.txt, G8_origin_master.txt, *.WAIVER
identity/old_to_sha.name-status.txt
identity/pre/                installed_manifest.jsonl t1_verdict.json t1_summary.json identity_manifest.tsv dists.txt dists_key.txt unit_sha256.txt
identity/pre_vs_sha/         predicted deploy delta (T1 vs SHA before the change)
identity/post/               installed_manifest.jsonl t1_verdict.json t4_verdict.json dists.txt dists.diff unit_sha256.txt unit.diff
captures/pre/                systemctl_show execstart_path environment_file_names book_state forward_marker deploy_prev df
                             pending_target.<book>.json decisions.<book>.trimmed.jsonl run_events.tail.jsonl journal_pid1_unit timers
captures/post/               systemctl_show health.json health_verdict app_started_verdict run_events.tail deploy_prev forward_marker forward_status
needrestart/                 conf_include verify_before backup_sha256 99-mastermind-no-autorestart.conf dropin_sha256 verify_after [verify_after_revert]
cycles/<day>T<HHMM>Z_<job>[_<book>]/  run_events.tail cycle.json decisions.trimmed health(+verdict) journal_pid1_unit [settlement_state]
cycles/<day>T0540Z_needrestart/  host_clock apt_upgrade_show systemctl_show nr_verify_now dpkg_needrestart_blocks uu_log
                             journal_needrestart journal_pid1_unit verdict.json   (raw log copies are deleted after judging)
proof/account_load/<label>/  quarantine_census.txt run_events.tail.jsonl account_state_invalid_events.jsonl journal_hits.txt
                             status.<book>.json src/ (SHA's paper_account.py + package inits; account bytes deleted)
gates/ACCT_<label>.PASS|HOLD  s4a verdict per label
rollback/                    rb_* / rc.* / proof/ (only if used)
manifest.json                sha256 of every file (s6)
```

**Redaction.** Account content appears only as hashes/stats. EnvironmentFiles are recorded by name only. `extra.flags` is dropped from run_events. `start.json` is recorded by hash only. Raw captures stay in the evidence tree, never in git; commit only the capture-id.

## 6. Uncertainties and residual risks (read before 03:30Z)

1. **needrestart host semantics are unverified until `needrestart-check` returns PROVEN.** The perl verify proves the config parses and the key matches. It does not prove that the installed needrestart (3.6-7ubuntu4.5; apt hook `/usr/lib/needrestart/apt-pinvoke -m u`) honours `override_rc` in its configured restart mode. Host facts from read-only observation on 10-22, which shape the s7 step:
   - **The report is not in the journal.** It is written to `/var/log/unattended-upgrades/unattended-upgrades-dpkg.log` (root:adm 0644, rotated monthly) inside each `Log started: …` / `Log ended: …` block, under flush-left `Restarting services...` / `Service restarts being deferred:` headings, one indented line per command. The journal had 0 needrestart lines 05:40–06:30Z.
   - **It restarted the bot on 10-22.** The 06:01:57 block lists `systemctl restart … mastermind.service …` under `Restarting services...`; pid 1 logged Stopping at 06:02:14.33Z and Started at 06:02:15.68Z. A second block (06:07:19) restarted nothing, and unattended-upgrades started again at 06:24:31 outside the apt-daily-upgrade run (06:01:03–06:07:38Z), so runs are not confined to that unit.
   - **`NRestarts` does not see it.** It counts only `Restart=` auto-restarts; it stayed 0 across the 06:02 restart. A check of "no needrestart lines in the journal and `NRestarts` unchanged" would therefore have PASSed on 10-22. `needrestart-check` gates on the dpkg log, the pid-1 journal and `ActiveEnterTimestamp` instead, and keeps `NRestarts` as a secondary check. Replayed read-only against the real host for 10-22, it returns FAIL naming the 06:01:57Z block and the four pid-1 lines.
2. **Timer next-elapse values are redrawn every 3 minutes.** NextElapseUSecRealtime includes the `RandomizedDelaySec` draw (observed: `apt-daily-upgrade.timer` `t 1792737190710641` = Fri 06:33:10Z at 14:21Z for `OnCalendar=6:00`, `RandomizedDelaySec=60m`). The host's `macro-update` cron job runs `systemctl daemon-reload` 10 times every 3 minutes (2857 reloads 00:00–14:25Z on 10-22), and each reload redraws the delay (`FixedRandomDelay` unset): the same timer read 06:53:33Z at 14:24Z. Two consequences:
   - G3's ≥ 05:55Z test stays sound: every draw for apt-daily-upgrade lies in `[06:00, 07:00]` Fri.
   - The delay collapses toward the calendar time. Once a draw lands in the past, the timer fires, so apt-daily-upgrade (unattended-upgrade, then needrestart) is expected at ~06:00–06:10Z, about 20 min after the window closes; on 10-22 it started at 06:01:02Z. `apt-daily` (`6,18:00`, 12 h delay; update/download only, no install) is expected to fire soon after 18:00Z Thu, so it is unlikely to land in W1. If it does run at s2, the G3 idle check holds; re-check.
3. **#1714 pre-landing.** If #1714 lands before s0, `T2_MODE=floor_pending`. The installed venv still holds the old SDK, and the pyproject floor is pending until the separate T2 step. Its linux gate lock was generated on Darwin with pip-tools for linux/x86_64 py3.12; it is unexercised on the host.
4. **Master moving** between s0 and s3 makes G8, or the wrapper (rc 2), refuse. Hence the merge-queue hold.
5. **Preflight quarantine** at startup is possible (`pending_target_cutover_preflight` = `quarantined`). It is reported as an incident and is not a proof failure.
6. **Authority-bytes hazard.** The deploy re-hashes the live authority files under its flock. A startup-time write to an autonomous account/fills between the baseline and the re-hash fails safe into the automatic rollback (R-a). `prewarm_marks` never writes `account.json` (with G4 clean there is no transaction to recover). With #1747 in SHA, an INVALID account makes its load write the quarantine copy, one `account_quarantine.jsonl` row and one run_events entry beside it, once; s4a reports that as a HOLD.
7. **R-b after a v2 settle** (WAL/receipts written by the new code) is refused by the precondition. It needs a seat ruling.
8. **Schedule hours are env-overridable.** The timeline assumes defaults (`US_WATCH_UTC_HOURS=2,6,11`, `CHINA_DAILY_UTC_HOUR=8`, …). s1's `timers.txt` and the run_events tail are the check.
9. **Snapshots accumulate.** Each deploy adds a full code snapshot under `.deploy_prev`. s1 requires ≥ 1 GiB free.
10. **Tail coverage.** G1/G2E and the cycle reads use a 20000-line run_events tail. If it does not reach back to the process start or fire time, the step ABORTs (G1/G2E) or the cycle is read once more and otherwise recorded as `incomplete_uncertain`. **Unparsed rows (rev 3.2, D-EVT-1):** the live file carries interleaved-write rows that do not parse (on 2026-11-02: 10 rows dated 2026-10-07..10-16 inside the tail, all before the 2026-11-01 08:30Z process start); `events_tail` drops such a row only when its `"ts"` prefix is strictly before the process start (or, while `process_active_enter.txt` is missing or empty, 00:00Z two days before DAY) and logs it; an unparsed row at or after the threshold is kept and still fails the step closed, since it could hide a run started since process start. Rev 3.3: the trusted prefix must end in `+00:00` (the host's only suffix), a row with invalid UTF-8 bytes is handled as unparsed rather than crashing the read, and whenever `dropped_before_threshold > 0` the seat reads `logs/unparsed_rows.log` after s1 and after s2 and ledgers the count, the ts range and the `DROPPED` head bytes.
11. **run_id formats** differ between decision rows and run_events (handed to RESEARCH). RUNTIME passes run identity. `replace_for_asof` identity loss is ruled correction-as-new-record, owned by RESEARCH as a wave-2 P0.
12. **Seat-tool kill.** The detach (`setsid` + `nohup`) is tested locally. If it fails anyway, s3-result classifies "pid gone, no rc" as EFFECT UNKNOWN; it never re-runs the deploy.
13. **Forward marker** is active (deployment_sha `3c4ef7f8…`). G6 re-proves it at the gate time; a different status means STOP, not init.
14. **Host import loads `.env`.** s4's `forward_evaluation status` (and G6) runs `python -m portfolio.forward_evaluation` on the host. `portfolio/__init__.py` imports `bot`, and `bot/__init__.py` loads `.env`/`.env.local` into that process's environment. Nothing is printed or captured, but the process does hold them. s4a deliberately classifies on the Mac to avoid a second host import.
15. **D-ACCT-1 timing.** s4a's classification needs #1747 in SHA. If #1747 lands after s0, the window installs the old load path; s4a then only runs the census/event/journal checks, and the fail-closed behaviour arrives with the next release.
16. **self_directed is not covered by D-ACCT-1.** It keeps its own lenient loader (`portfolio/self_directed.py` `_load_account`), which falls back to a fresh $1M book on a bad file. A corrupt self_directed account would not fail closed and is not detected by s4a. #1719 (in master since `3d1cd77d`) already makes `/api/self_directed` render `unavailable` on a read failure. The engine's fallback is tracked as ECON E13. It is not a W1 proof item.

## 7. Verification of this runbook (offline, by RUNTIME)

**Checks run**
- `bash -n`.
- s0 refusals: environment override, missing session id, `PBR_EV` set, weekend day. Also step-without-`PBR_EV` and bad step (rc 2). All were verified to refuse before any side effect.
- s3 refuses on an environment override before writing `deploy.started`.
- `classify`: all branches, against fake deploy logs/rcs.
- `launch_detached`: survival of the parent, atomic rc, and that the environment prefix reaches the child.
- needrestart verify: a fake conf gives rc 3 before, rc 0 after, rc 4 on a parse error. The regex matches `mastermind(.service)`, not `mastermind-restart.service`.
- `pbr_rb` gates/app-started/t1/t4/health/cycle/close against dated fixtures.
- G1/G2E waiver paths.
- `g7b-selftest`: c0 worktree helper imports under `-E -s -B`; c1 unrelated → equal; c2 SDK floor → floor_pending; c3 dev bound + header-only locks → equal; c4 dev bound + lock pin → STOP; c5 other dependency → STOP; c6 extra requirements file → STOP; c7 SDK + dev → floor_pending; c9 SDK floor 0.3 → STOP; c10 column-0 `--index-url` lock line → STOP; (rev 3.4) c11 added macOS-arm64 `.in`/`.lock` pair → equal; c12 dev bound + header-only gate locks + added macOS pair (the 2026-11-03 master shape) → equal; c13 SDK floor + added macOS pair → floor_pending; c14 added `-linux-x86_64-py312.lock` → STOP; c15 added `gate-extra-macos-arm64-py312.lock` → STOP; c16 pre-existing macOS lock modified → STOP; c17 pre-existing macOS `.in` deleted → STOP; c18 `extra.txt` renamed onto a macOS lock name → STOP; c19 macOS lock in a subdirectory → STOP; (rev 3.5) c20 both gate locks header-only, pyproject unchanged (the 2026-11-05 #1909 shape) → equal; c21 one gate lock header-only → equal; c22 gate-lock pin change, pyproject unchanged → STOP; (rev 3.6, r6 MINOR/NIT) c23 gate-lock blob unreadable at SHA → STOP; c24 pyproject blob unreadable at SHA → STOP; c25 one gate lock moved onto the other gate-lock name (delete + add) → STOP; c8 live OLD→origin/master → not STOP; (rev 3.6, D-G7A-1, the G7a classifier) a1 unrelated change → none; a2 the exact `forward_evaluation.py` pair → D-G7A-1; a3 the pair plus an unrelated change → D-G7A-1; a4 another new blob → STOP; a5 another old blob → STOP; a6 the pair plus `app/main.py` → STOP; a7 `app/main.py` alone → STOP; a8 file deleted → STOP; a9 file added → STOP; a10 the pair with mode 100755 → STOP; a11 the pair reversed → STOP; a12 a bad OLD revision (git failure) → STOP; a13 live OLD→#1422 `b796d4505` → D-G7A-1; a14 live OLD→origin/master → not STOP. Rev 3.6 checked exactly 40 cases; rev 3.7 retains them and requires exactly 86 after 23 G7a and 23 G7b additional cases; rev 3.8 requires exactly 122 after 13 D-G7A-3 and 23 D-G7B-5 cases. Rev 3.6 mutation check: 10 one-edit mutants of the new guards each fail on their predicted cases. One equivalent mutant survives: dropping the ls-tree rc guards changes nothing, because an empty entry still STOPs (evidence `runtime-rev36-build-20261106T0607Z/mutation-table.md`).
- **Rev 3.7 D-G7A-2 cases:** exact bundle and unrelated changes pass; each of the three changed paths with a wrong OLD or target blob refuses; wrong OLD/target mode, add, delete, individual revert, rename and reverse bundle refuse; extra mechanics, a foreign stable script on both sides and a stable script absent on both sides refuse; bad OLD/target revisions and unavailable OLD/target/stable blobs refuse. Existing a1–a14 remain unchanged. `a14_live` accepts ANY non-STOP outcome and does not replace a positive exact-target `g7a-check`. The full selftest remains a live composition gate: an unrelated G7b refusal is retained, not changed into a fixture PASS.
- **Rev 3.7 D-G7B-4 cases:** exact trio, added admitted macOS files and unrelated files pass; each wrong OLD/target source, modes, extra requirement/dependency/SDK drift, lock pin/option, delete/rename/reverse, bad revisions and unreadable source blobs refuse. The live composition case is unchanged.
- **Rev 3.7 conditional runtime suite:** `runbook/test_install_w1_jsonschema.py` uses a local fake SSH executable and the real installed validator, with no host contact. It covers valid pre/prelaunch/post proofs; missing/wrong/duplicate metadata; import/API/date-format/interpreter/service failures; malformed/oversized/stale response; missing/copied/mismatched baseline/state; prelaunch distribution drift; repeated current compatibility before launch; unchanged final live-gate/clock ordering; lost window; and exactly-once launch. Previous qualification results below describe their original revisions, not new live execution.
- **Rev 3.8 D-G7A-3 cases (13):** the exact bundle and unrelated changes → D-G7A-3; a wrong target blob on each changed path (3), main.py at D-G7A-3 with scheduler at D-G7A-2 and the reverse mix, a target mode change, an extra mechanics path, the reverse bundle, D-G7A-2→D-G7A-3 as the OLD side and an unavailable target blob → STOP; `a15_live_pr2175` OLD→#2175 `7a3c0b78` → D-G7A-3.
- **Rev 3.8 D-G7B-5 cases (23):** the exact manifest, plus unrelated changes, plus an added admitted macOS file → equal; each wrong target (4) or OLD (3) blob, the `.in` present at OLD, missing, renamed or executable, the pyproject without the package-data stanza, an extra SDK line, the reverse and an unreadable `.in` → STOP. The ruled-mode cases re-derive D-G7B-5, D-G7B-4 and legacy from frozen OLD/SHA, STOP on an unreadable source (r8c MINOR 2), and `g5_ruled_live` OLD→origin/master gives ANY non-STOP.
- **Rev 3.8 runtime fixture:** `runbook/test_install_w1_jsonschema.py` adds 3 tests (15): the D-G7B-5 ruling binds pre/prelaunch/post proofs; a D-G7B-5 source with wrong, missing or unreadable state refuses; and a baseline proof recorded under the other ruling refuses.
- **Rev 3.8 `pbr_rb health`:** besides the existing checks, it requires `reasoning_backend=waterfall` and `reasoning_policy=codex_first_claude_oauth_fallback`; a Fabric-selected body fails.
- `g7a-check` (rev 3.6): runs s0's G7a classifier on SEAT_WT `origin/master` (git only). On 2026-11-06 06:25Z it printed `g7a-check PASS (origin/master@c09866e6: G7A_MODE=D-G7A-1)`. Rev 3.8: on 2026-11-09 09:42Z it printed `g7a-check PASS (origin/master@6696153d: G7A_MODE=D-G7A-3)`.
- G3 against a fake host with systemd-255-shaped stubs (`systemctl show` prints a date whatever the flags; `busctl` prints `t <µs>`), 9/9 cases plus 4 assertions:
  - the observed 14:21Z value (06:33:10Z) → PASS; the redrawn 14:24Z value (06:53:33Z) → PASS; exactly 05:55:00Z → PASS;
  - 05:54:59.999Z → stop; 04:40Z (inside W1) → stop; `t 0` → stop; a `busctl` error → stop; a non-`t` reply → stop;
  - `apt-daily.service` activating → stop on the idle check;
  - the evidence file carries both the µs and the date lines; `G3.PASS` is written only on a pass; the stop message names the 05:55Z floor.
  - Teeth: the reviewed driver (`ec8b5db9`) fails the three PASS cases (always `unknown`), reproducing review MAJOR-1 offline.
- s4a against a fake host (`VPS=(fakessh)` rewriting the live-data root, fake `journalctl`), 16/16 cases:
  - clean (3 VALID, self_directed n/a) → 0, with no account bytes retained;
  - a quarantine file in an archived book's dir → 5, and in the legacy `portfolio/` → 5;
  - an active book's dir absent → 1, and its `account.json` MISSING → 5;
  - a reused label → 1;
  - a quarantine file → 5;
  - an `account_state_invalid` event after `DEPLOY_T0` → 5, and one before `DEPLOY_T0` → 0;
  - an unparseable `account.json` → 5, naming the book;
  - a journal hit → 5, and a journal read failure → 1;
  - SHA without #1747 (`3a6d165f`) → classification skipped, 0;
  - no `PROOF.PASS` → 1;
  - a bad label → 1;
  - the `after-china_daily` label → 0.

- needrestart-check against a fake host (fake `date`/`systemctl`/`journalctl`/`perl`, synthetic dpkg and unattended-upgrades logs), 42/42 assertions over 23 cases:
  - PROVEN (deferred, with the 10-22 restart block before the cut excluded) → 0, keeping only the blocks since the cut, cutting the uu log, deleting the raw copies, an exact evidence file list and no restart hit from `mastermind-restart.service`/`mastermind-control-room-remote.service` lines; an InvocationID change near 08:30 → 0 with a note; VACUOUS, an absent dpkg log, LISTED, a failed apt-daily-upgrade, an `NRestarts` decrease (note) and the proof-old baseline → 0;
  - `mastermind.service` under `Restarting services...` → 1; the same in a 06:24 block outside the apt-daily-upgrade run → 1; a pid-1 Stopping/Started inside an interval → 1; `ActiveEnterTimestamp` inside an interval → 1; `NRestarts` going 0 → 1 → 1; inactive → 1; s5 verify rc 3 → 1;
  - apt-daily-upgrade not started since the cut, or still running → 1 "not yet"; host offset `+0800` → 1; a journal read failure → 1; no `NEEDRESTART.PASS`, s5 reverted, a bad day → 1; dispatch reaches the step.
  - Every failing case was checked to fail for its own reason. Teeth: the previous driver (`37d67e70`, @ 6ba45237) answers `needrestart-check` with usage (rc 2) and fails 41 of the 42 assertions.
  - Real-host replay (read-only, scratch evidence dir, 10-22 at 14:48Z): FAIL, as it must be: restart hit at the 06:01:57Z block, four pid-1 lines 06:02:14–06:02:15Z, and the s5 verify rc 3 (no drop-in yet). `journal_needrestart` was empty.
- The G3 and s4a fixtures were re-run against this driver: G3 9/9 (+4 assertions), s4a 16/16.

**Read-only host observations (2026-10-22):** 13:41Z, the forward marker is active. 14:21–14:27Z, systemd 255.4-1ubuntu8.18, TZ `Etc/UTC`; the new G3 timer probe returns `upgrade_timer_next_usec=1792738413683088` (Fri 06:53:33Z, a PASS); the reload churn in §6 #2 is from `journalctl _PID=1` and the cron journal.

14:30–14:48Z, needrestart 3.6-7ubuntu4.5, the dpkg-log report format and the 10-22 06:02 restart in §6 #1 (`dpkg -s`, `unattended-upgrades-dpkg.log`, `unattended-upgrades.log`, `journalctl _PID=1`, `systemctl show`).

**Not tested:** anything on the real host beyond those reads. The first live run is the seat's s0/s1; the first PROVEN needs a library upgrade that touches a library the bot maps.
