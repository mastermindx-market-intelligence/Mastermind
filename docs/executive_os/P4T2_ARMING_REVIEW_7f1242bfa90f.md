# P4.T2 independent arming review: Executive OS arm sequence @ 7f1242bfa90f

**Reviewer:** non-authoring, read-only Opus reviewer (ROUTE: review / AUDIT), commissioned by Meta-CEO seat 873aabd3 on 2026-11-02. **Source:** Mastermind worktree `exec-finish-lanes-873aabd3-7dda5e523cbfc1eb`, HEAD `7f1242bfa90f0f0448e66e400e054bd5aa5fa15a` (resolved from the gitdir ref file; worktree cleanliness UNVERIFIED). **Standard:** B2 ruling `B2_ARMING_RULING_f608f52f.md` (executive-os-bringup charter, 2026-10-24).

**Verdict: ARM_ADMISSIBLE_WITH_CONDITIONS.** No blocker found. Every step binds the expected SHA, requires root, and fails closed when a stale release, non-root caller, running service, partly armed config or missing finite delta is present. Four operator conditions C1–C4 must be met before the sequence is called safe and complete. This review is source-only: it changes nothing, waives nothing, and does not replace P3.T6 or the arm-time predicates.

## 1. Per-step predicate table (order as executed)

Paths are relative to the worktree. `AC` = `ops/executive_os/autonomy_control.py`, `FSL` = `ops/executive_os/finite_service_lifecycle.py`.

| Step | # | Predicate | Citation |
|---|---|---|---|
| wrapper (1,2,4,5,6) | w1 | verb in closed set | `autonomy-control.sh:9-15` |
| | w2 | euid 0, Darwin | `:17-24` |
| | w3 | exactly one 40-hex `--expected-sha`; the `=` form is refused | `:26-44` |
| | w4 | script resolves to `/Library/.../releases/<sha>` | `:46-52` |
| | w5 | control plist regular file, pinned Python 3.12, `-I -S -B` | `:54-66` |
| | w6 | duplicate argument refused (`_StoreOnce`) | `AC:972-1024` |
| **1 status** | 1a | Darwin and euid 0 | `AC:2709-2713` |
| | 1b | manifest `commit_sha`==sha, tree sha valid, `release_manifest.verify`; control/worker plists point at `releases/<sha>` | `AC:2715-2747` |
| | 1c | transaction marker absent or a safe root dir | `AC:2750-2766` |
| | 1d | the three arm bits are bool | `AC:2780-2788` |
| | 1e | receipt absent, or validated against both config digests | `AC:2890-2937` |
| | 1f | `service_state`: STOPPED when both labels report not loaded | `AC:2878-2882` |
| | 1g | classification | `control_plane/executive_autonomy.py:579-618` (UNARMED at `:606-607`) |
| | 1h | exit 0 for UNARMED **or** ARMED_READY | `AC:7916` |
| **2 arm-quiesce-control-uid** | 2a | root | `AC:7925` |
| | 2b | `require_exact_install` | `AC:2994-3001` |
| | 2c | acceptance dir owned by control uid/gid, mode 0700, no ACL; summary mode 0400; document check; carry receipt | `AC:3003-3039`, `:1858-1884`, `acceptance_maintenance.py:436-473` |
| | 2d | `load_unarmed_configs`: `proof_base_sha`==sha and the three bits False | `AC:3102-3128` |
| | 2e | runtime: quick_check ok, FK ok, WAL, no live attempt | `AC:3151-3182`, `:1900-1905` |
| | 2f | control/worker already unloaded; launchctl rc must be exactly 0 or 113, otherwise refused | `AC:3218-3230`, `:2811-2831` |
| | 2g | no transaction | `AC:3353-3355` |
| | 2h | SIGTERM then SIGKILL of Control UID PIDs only; two consecutive empty reads required | `AC:3232-3302` |
| | 2i | service UIDs quiescent: Control empty; worker empty or exactly one codesigned attested `distnoted` | `AC:3304-3351` |
| **3 start-finite** | 3a | wrapper: 5 args, 40-hex sha, 64-hex manifest; root; runs from `releases/<sha>` | `service-control.sh:683-685`, `:708-713` |
| | 3b | entry: isolated/no-site/no-bytecode flags, euid 0; release tree verified file by file before any import | `FSL:615-626`, `:209-274` |
| | 3c | euid 0; transaction absent; non-blocking flock on CONFIG_ROOT with inode identity check | `FSL:427-451` |
| | 3d | qualify: exact install | `FSL:339-340` |
| | 3e | qualify: no transaction | `FSL:341` |
| | 3f | qualify: control/worker stopped | `FSL:342` |
| | 3g | qualify: UIDs quiescent | `FSL:343` |
| | 3h | qualify: credential mutation disarmed | `FSL:344` |
| | 3i | qualify: **six bits explicitly False** | `FSL:349-353` |
| | 3j | qualify: runtime quiescent | `FSL:354` |
| | 3k | qualify: primary worker digest pinned | `FSL:355-356` |
| | 3l | qualify: backup unloaded | `FSL:357` |
| | 3m | qualify: gateway running | `FSL:358-363` |
| | 3n | qualify: principal uid/gid 470 and group set | `FSL:364-371` |
| | 3o | qualify: definition inventory and canonical artifacts | `FSL:372-407` |
| | 3p | qualify: finite delta staged | `FSL:408-411` |
| | 3q | qualify: activity directory 470:470 0700 | `FSL:412-416` |
| | 3r | transition: launchd absent and override disabled/default | `FSL:73-75` |
| | 3s | transition: idle (uid 470 PIDs, empty active dir, no socket) | `FSL:472-480` |
| | 3t | transition: recheck generation | `FSL:453-455` |
| | 3u | transition: enable → bootstrap → kickstart | `FSL:80-92` |
| | 3v | same-generation probe as uid 450: socket root:450 0660, no ACL, kernel peer euid 470 with matching pidversion | `FSL:94-102`, `:482-507`, `:562-612` |
| **4 arm --foreground-only --gate-b-receipt** | 4a | replay check `existing_arm`: exact install, status ARMED_READY, receipt digests match, foreground flag matches | `AC:1981-1983`, `:3913-3961` |
| | 4b | not `foreground_only` combined with `native_return` | `AC:1938-1940` |
| | 4c | credential kind, workspace class, expiry in the future | `AC:1908-1930` |
| | 4d | install | `AC:1942` |
| | 4e | acceptance (as 2c) | `AC:1943` |
| | 4f | Gate B: root:root 0600 file, schema, `passed`, `release_sha`==sha | `AC:3041-3054`, `:1887-1897`, `git_handoff_preflight.py:514-536` |
| | 4g | provider readiness: root 0400, `passed`, deadline ≥ now + margin | `AC:3056-3100` |
| | 4h | three bits False | `AC:1948` |
| | 4i | runtime quiescent | `AC:1949` |
| | 4j | services stopped (**may stop** control/worker) | `AC:3207-3216` |
| | 4k | UIDs quiescent | `AC:1951` |
| | 4l | no transaction | `AC:1952` |
| | 4m | derive: three bits True and `coo_foreground_only` True; `fabric_bridge_armed` untouched | `AC:1226-1230` |
| | 4n | transaction: write, replace, receipt, start worker then control, READY within 45 s | `AC:1994-2003`, `:4228-4242` |
| | 4o | rollback on ordinary failure; EFFECT_UNKNOWN preserved | `AC:2018-2042` |
| | 4p | Control boot publishes `minimax.attended` only when autonomy and foreground-only are both True and the alias is readonly; otherwise it raises | `control_plane/fabric_attended_routing.py:97-110` |
| **5 ceo-submit-arm** | 5a | sticky same-verb marker → EFFECT_UNKNOWN | `AC:2211-2214` |
| | 5b | root, sha format, install | `AC:2122-2127` |
| | 5c | App binding present; peer user pinned by name; binding/ACL/topology valid | `AC:2128-2141` |
| | 5d | `proof_base_sha`==sha | `AC:4549` |
| | 5e | `ceo_submit_armed` is bool False | `AC:2143-2147` |
| | 5f | **`ceo_ingress_app_armed` is True** | `AC:2157-2158` |
| | 5g | peer uids are ints, distinct, and equal to the live binding | `AC:2168-2176` |
| | 5h | coexistence: full flags plus a current runtime-guard receipt over both config digests | `AC:2181-2190`, `:1424-1446`, `:5527-5535` |
| | 5i | no transaction | `AC:2191-2194` |
| | 5j | write/rebind/replace/receipt, reconcile Control, prove admission bound, complete | `AC:2235-2247` |
| **6 ceo-submit-status** | 6a | root, install | `AC:2447-2452` |
| | 6b | CEO marker → EFFECT_UNKNOWN; other owner → hold | `AC:2457-2459` |
| | 6c | bool flag | `AC:2460-2463` |
| | 6d | `ceo_submit_sink_eligible` over sealed receipt, binding and full-autonomy receipt → ARMED, else ARMED_UNBOUND (exit 2) | `AC:2464-2492`, `:7833-7838` |

## 2. Findings

There are no BLOCKER findings.

**C1 (CONDITION): step 5 has an unwired precondition.**
- **What:** `ceo-submit-arm` refuses `ceo_ingress_app_unarmed` unless control.json already has `ceo_ingress_app_armed: true` (`AC:2157-2158`).
- **Why it matters:** The template default is `false`, and D8 enforces that default (`tests/test_ceo_submit_armed_composition.py:2504`). None of steps 1–4 sets it. A grep of `ops/`, `scripts/` and `control_plane/` for an assignment to True found none (pattern-limited; treat as UNVERIFIED-negative).
- **What can go wrong:** On a template-default host the sequence fails closed at step 5. If the bit is instead set by a hand edit, that edit changes the control digest outside any reviewed transaction.
- **Condition:** Name the reviewed publication that sets this bit. It must run before step 3, so the bit is part of the disarmed bytes that steps 3/4 hash. Steps 3 and 4 do not check this key.

**C2 (CONDITION): nothing checks that the finite bridge is alive at or after arm.**
- **What:** `arm` never checks the finite label (B2 also says so). After step 4, `status-finite` cannot run, because `qualify` requires stopped services and all six bits False (`FSL:342`, `:349-353`).
- **What can go wrong:** If the bridge exits between step 3 and step 4, Control still publishes `minimax.attended` (`fabric_attended_routing.py:100-110`) against a dead socket.
- **Condition:** Run `status-finite --expected-sha S --expected-manifest-sha256 M` immediately before step 4 and require `READY` with the same `pid`/`process_instance` as step 3's output. After step 4, the only liveness evidence is outside this sequence (GAP).

**C3 (CONDITION): Gate B and acceptance are trusted by shape, not re-proven.**
- **Gate B:** `validate_receipt` checks only that the sub-predicate keys exist (`git_handoff_preflight.py:519-536`). It does not check that `worker_preflight_passed`, `persistent_config_unchanged` and `workspace_root_restored` are True, and it ignores `observed_at`. An old Gate B receipt for the same SHA is accepted forever.
- **Acceptance:** For a fresh acceptance, `validate_carry_receipt` returns early when there is no descriptor (`acceptance_maintenance.py:443-445`). The summary is then an unsealed file owned by the **Control service UID** (`AC:3014-3024`). `control_uid` and `worker_uid` are only type-checked and checked distinct, never compared with the live accounts (`AC:1876-1881`). No freshness check.
- **Mitigation present:** the Gate B file must be root-written, and Control is stopped and UID-quiesced at arm time, so a forgery would have to be planted in advance by a compromised Control.
- **Condition:** P3.T6 (section 6) must verify provenance and the values the code does not check, before step 2.

**C4 (CONDITION): no listener re-observation.**
- **What:** `no_public_listener` was observed once during acceptance (`ops/executive_os/acceptance.py:3315`). No step 1–6 re-observes TCP listeners. Steps 4n and 5j start and reconcile Control with a new config.
- **What exists:** the finite socket is AF_UNIX, root:450 0660, checked for no ACL (`FSL:573-576`).
- **Condition:** After step 6, run the acceptance listener assertion (or an equivalent `lsof -nP -iTCP -sTCP:LISTEN` read) and require no new public listener.

**N1 (NOTE): step 1 is advisory only.** Exit 0 also covers ARMED_READY (`AC:7916`); UNARMED allows a running service (`executive_autonomy.py:606-607`); `_loaded` treats any non-zero launchctl rc as "absent", so status fails open toward STOPPED (`AC:2799-2808`); status inspects only three bits, not `coo_foreground_only`, `ceo_submit_armed` or `fabric_bridge_armed`. Steps 2f and 3i enforce these properly. The operator must parse `status=="UNARMED" && service_state=="STOPPED"` and must not rely on the exit code.

**N2 (NOTE): misleading refusal codes, no unsafe effect.** Step 2 run as non-root raises `HostControlError` (`AC:1141`), caught by the bare `except` and reported as `service_uid_process_unknown` (`AC:7952-7958`). In step 4, a read-only `HostControlError` from `collect_status` inside `existing_arm` (`AC:3917`) is reported as `effect_unknown` though no mutation happened (`AC:8041-8048`). Both push the operator toward reconciliation, which is conservative.

**N3 (NOTE): idempotency and replay.**
- Step 2: safe to re-run (`replayed` = nothing signalled, `AC:7941`); safe after step 3 because uid 470 is never targeted.
- Step 3: a failure after `enable` is EFFECT_UNKNOWN (exit 75, `FSL:139-141`, `:634-638`). An enabled-but-absent leftover permanently blocks `start-finite` ("never adopt", `FSL:73-75`), and `stop-finite` requires enabled+running (`FSL:109-110`). No in-tree reconcile verb exists for that state; it needs a manual launchctl override reconciliation (GAP).
- Step 4: re-running after success returns `already_armed` only when every digest and the foreground flag match (`AC:3933-3953`). A failed arm rolls back control/worker but **leaves the finite bridge running** (`AC:2018-2034`). Safe recovery order: `ceo-submit-disarm` (if armed), then `disarm`, then `stop-finite`.
- Step 5: never re-run. A second call refuses `ceo_submit_already_armed` with `CEO_SUBMIT_UNVERIFIED`, exit 2 (`AC:2146-2147`, `:7870-7877`). An interrupted run leaves a sticky marker, so the next call reports EFFECT_UNKNOWN (`AC:2211-2214`); recovery is `ceo-submit-reconcile` (`AC:7851-7853`). Classify outcomes with step 6 only.

**N4 (NOTE): TOCTOU between concurrent root operators.** `arm` admission (`AC:1933-1972`) runs without the CONFIG_ROOT flock that `start-finite` holds (`FSL:439-449`). A concurrent arm between the finite `recheck` and `modify('enable')` (`FSL:77-82`) could flip bits. Run the steps serially from one root shell.

**N5 (NOTE): secret handling is clean in the reviewed paths.** No step takes a secret argument; the CLI carries only credential kind/class/expiry (`AC:983-990`). Every CLI output is the fixed `operation_document`/`status_document` set of codes, digests, states and ids (`AC:2496-2533`). Child process output is discarded (`AC:4049-4050`, `:3196-3198`, `:2861`) or captured and never printed (`FSL:193-198`). The finite READY output contains pids, uids and digests only. `provider_readiness.validate_receipt_file` internals were not reviewed (UNVERIFIED).

**N6 (NOTE): reach of the D8 guard.** `test_d8_template_topology_and_protected_defaults` (`tests/test_ceo_submit_armed_composition.py:2499-2541`) binds the template topology (`allowed_peer_uids`, `ceo_ingress_peer_uid`, `ceo_ingress_app_peer_uid`, `ceo_ingress_app_armed` False) and a no-new-identity-literal diff scan against `merge-base origin/master HEAD`. The armed composition stays consistent with it: step 5 pins the App peer by name (`AC:2134`), reads peer uids from config (`AC:2168-2176`), and the protected template default stays false. D8 is a source/CI guard, not a runtime guard, and needs git plus `origin/master`, so it cannot run on an installed release. It must not be weakened; C1 must be resolved without changing the template default.

## 3. Delta from B2 (f608f52f) to current source (7f1242bf)

**Anchors.** Every B2 anchor re-checked is at the **same line numbers** at 7f1242bf, with the semantics B2 describes: `AC` 976-994, 1226-1230, 1259-1267, 1432-1446, 1887-1897, 1933-1972, 1975-2003, 2111-2201, 2185-2189, 2243-2246, 2435-2493, 2496-2513, 2709-2713, 2715-2747, 2750-2766, 2780-2788, 2878-2882, 2890-2937, 2939-2982, 2994-3001, 3003-3035, 3041-3054, 3056-3100, 3102-3120, 3151-3178, 3207-3216, 3218-3230, 3232-3302, 3304-3351, 3321-3329, 3353-3355, 4228-4229, 5527-5535, 7906-7916, 7922-7935; `executive_autonomy.py` 579-618, 606-607; `FSL` 72-107, 327-421, 349-353, 408-411, 472-480; `service-control.sh` 683-685, 708-713, 719-724; `fabric_attended_routing.py` 97-110.

**Moved functions:** none observed. **Content diff:** UNVERIFIED — a read-only `git diff f608f52f HEAD` was refused by the session isolation guard and not retried. Identical anchors strongly suggest the reviewed functions did not change but do not prove it.

**Corrections and additions to B2:** step 3 requires `qualify` at `:339-340` (B2 says `:338-340`; 338 is an import); step 4's prior-stop is shell `stop` with control first (`service-control.sh:725-729`); B2 omitted C1–C4 and N3's finite EFFECT_UNKNOWN dead end.

## 4. Re-binding recipe

This review applies to the final release S only if these paths are byte-identical between `7f1242bfa90f0f0448e66e400e054bd5aa5fa15a` and S.

**Reviewed (working-tree blob shas, first 12):**

| Blob sha | Path |
|---|---|
| `7d8f2d04c463` | `ops/executive_os/autonomy-control.sh` |
| `4aa3207c0eb1` | `ops/executive_os/autonomy_control.py` |
| `4f7a0290c483` | `ops/executive_os/finite_service_lifecycle.py` |
| `5fef62563ab5` | `ops/executive_os/service-control.sh` |
| `65f9a3ddf96c` | `control_plane/executive_autonomy.py` |
| `ef5a84c50772` | `ops/executive_os/attended_control_staging.py` |
| `69c3206063f7` | `ops/executive_os/credential_rotation_interlock.py` |
| `4ff1d11d5629` | `control_plane/fabric_attended_routing.py` |
| `8dd4fd4a257b` | `ops/executive_os/git_handoff_preflight.py` |
| `8b03670cd5f6` | `ops/executive_os/acceptance_maintenance.py` |
| `d15e2ed1f660` | `ops/executive_os/acceptance.py` |
| `9e56d9532d10` | `ops/executive_os/attended_worker_definition.py` |
| `d44d4b5ef80d` | `ops/executive_os/control.json.template` |
| `41c9526a145b` | `ops/executive_os/release_manifest.py` |
| `23d6eaa58c22` | `tests/test_ceo_submit_armed_composition.py` |

**Imported but unreviewed (any change also voids carry-over):** `control_plane/executive_worker_broker.py`, `control_plane/executive_ambient_process.py`, `ops/executive_os/provider_readiness.py`, `scripts/executive_os_phase1c.py`, `scripts/executive_os_phase1c_control_wrapper.py`, `control_plane/executive_fabric_bridge_broker.py`, `control_plane/executive_runtime.py`, `ops/executive_os/gateway_refresh_preflight.py`.

**One check command:**

```
git diff --quiet 7f1242bfa90f0f0448e66e400e054bd5aa5fa15a <S> -- ops/executive_os/autonomy-control.sh ops/executive_os/autonomy_control.py ops/executive_os/finite_service_lifecycle.py ops/executive_os/service-control.sh control_plane/executive_autonomy.py ops/executive_os/attended_control_staging.py ops/executive_os/credential_rotation_interlock.py control_plane/fabric_attended_routing.py ops/executive_os/git_handoff_preflight.py ops/executive_os/acceptance_maintenance.py ops/executive_os/acceptance.py ops/executive_os/attended_worker_definition.py ops/executive_os/control.json.template ops/executive_os/release_manifest.py tests/test_ceo_submit_armed_composition.py control_plane/executive_worker_broker.py control_plane/executive_ambient_process.py ops/executive_os/provider_readiness.py scripts/executive_os_phase1c.py scripts/executive_os_phase1c_control_wrapper.py control_plane/executive_fabric_bridge_broker.py control_plane/executive_runtime.py ops/executive_os/gateway_refresh_preflight.py && echo REVIEW_CARRIES
```

Before relying on it: confirm the blob shas above with `git ls-tree 7f1242bf -- <path>` (worktree cleanliness was not verified), and on the host confirm that the installed `.executive-release-manifest.json` `sha256` rows for those paths match S.

## 5. Verdict

**ARM_ADMISSIBLE_WITH_CONDITIONS.** Conditions: C1 (name and complete the `ceo_ingress_app_armed` publication before step 3), C2 (`status-finite` READY with the same generation immediately before step 4), C3 (P3.T6 PASS on acceptance plus Gate B), C4 (post-step-6 listener re-observation). Operators follow N1 (parse JSON, not exit codes) and N3 (never re-run steps 3 or 5 after an ambiguous result). The verdict carries over only if the section 4 check succeeds.

## 6. P3.T6 standby protocol (independent acceptance-receipt review)

Key names, types and predicates only; never record values in the review.

**A. Container.** `<RUNTIME_ROOT>/control/acceptance/<S>/` is a directory, not a symlink, owned by the control uid and gid, mode 0700, no ACL. `acceptance-summary.json` is a regular file, nlink 1, mode 0400, owned by the control uid and gid, no ACL, within the size cap.

**B. Summary keys:** exactly this set, no extras (`AC:1822-1841`).

| Key | Type | Predicate |
|---|---|---|
| `schema_version` | str | equals the fixed constant |
| `passed` | bool | True |
| `observed_at` | str | non-empty ISO-8601; reviewer: later than install of S and earlier than Gate B `observed_at` |
| `exact_origin_master_sha` | str | 40-hex, equals S |
| `release_root` | str | equals the releases path for S |
| `control_uid` | int | reviewer: equals the live uid of the control account (code does not check) |
| `worker_uid` | int | not equal to `control_uid`; reviewer: equals the live codex-01 worker uid |
| `success_job_id` | str | non-empty; reviewer: exists as COMPLETED in the runtime store |
| `interrupted_requeued_job_id` | str | non-empty; reviewer: exists and differs from the success id |
| `detached_session_cleanup` | str | the fixed PASS literal |
| `terminal_assignment_sealing` | str | the fixed PASS literal |
| `lost_workspace_rotation_boundary` | str | the fixed PASS literal |
| `backup_restore` | str | the fixed PASS literal |
| `no_public_listener` | str | the fixed PASS literal |
| `credential_leakage_scan` | str | the fixed PASS literal |
| `financial_scheduler_activation` | str | the fixed not-touched literal |

**C. Provenance.** Sibling artefacts written by the same run exist in the same directory, including `final-host-status.txt` and `nonexecutive-launchd-after.json` (`acceptance.py:3305-3320`). The summary's sha256 is the digest `arm` records as `acceptance_receipt_sha256`.

**D. Carry receipt** (only if `descriptor_for(S)` is non-null), keys in `carry-forward.json`: `schema_version` (str, equals the descriptor's); `passed` (bool True); `descriptor_sha256` (str, equals `digest(descriptor)`); `acceptance_summary_sha256` (str, equals the summary sha256); `baseline_preserved` (bool True); `schema_upgrade_evidence_sha256` and `acceptance_restore_evidence_sha256` (str, migration schemas only; checked per `acceptance_maintenance.py:450-473`).

**E. Gate B receipt** (because of C3). Root:root 0600; `schema_version` str; `passed` bool True; `release_sha` str equal to S; present and True (the code does not check these): `persistent_config_unchanged`, `worker_preflight_passed`, `workspace_root_restored`; present as objects: `control`, `worker`, `workspace`, `git`, the three `index_*` keys, `stimulus`, plus `stimulus_used`; `observed_at` str later than the acceptance `observed_at`.

## 7. Gaps and evidence

- D8 collection at HEAD: `python3 -B -m pytest "tests/test_ceo_submit_armed_composition.py::test_d8_template_topology_and_protected_defaults" --collect-only -q -p no:cacheprovider` → `tests/test_ceo_submit_armed_composition.py: 1` (test at line 2499).
- Not reviewed: `provider_readiness.validate_receipt_file`, `reconcile_control_service` / `prove_control_admission_bound`, `ceo_submit_sink_eligible` internals, `build_finite_control_delta`, `attended_control_staging` predicates (B2 `:34-39`, `:219-227`).
- No in-tree reconcile for a finite enabled-but-absent EFFECT_UNKNOWN (N3); no post-arm finite liveness read (C2).
- The search for a writer of `ceo_ingress_app_armed=true` was a limited-pattern grep only.
