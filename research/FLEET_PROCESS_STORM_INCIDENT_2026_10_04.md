# Fleet process-storm incident — 2026-10-04

**Disposition:** incident evidence + bounded hardening acceptance. This record does not create a scheduler, router, worker identity, queue, publication plane, or host-kill daemon.

**Protected Mastermind procedure pin used during recovery:** `5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f`.

## Incident finding

Mini2 rebooted after repeated Jetsam `low-swap` pressure followed by a watchdog panic.

The panic process census showed:

- 908 Python processes in one Jetsam coalition;
- about 30.6 GB of summed resident-memory accounting for those Python processes;
- one linear ancestry rooted in one launched session, including `claude.exe -> zsh -> Python -> Python -> ...`;
- 16 Codex-family processes were present, but they accounted for only about 3.0 GB of the tracked resident-memory sum. Codex was therefore not the dominant aggregate pressure source.

The local external-lane runtime already owned provider execution in a private process group/session and had identity-verified terminal cleanup. The defect was narrower: `run_owned_process()` waited for leader exit or timeout before doing a descendant/session census. A provider process tree could therefore grow unbounded during the run.

## Accepted containment

The incumbent `lane_runtime.py` owner was extended rather than adding a second watchdog.

Accepted runtime identity:

```text
sha256 a9eb2ea9aac751da0f618fcbbbc228c3ec558f08334cf0da43963491d4e4a061
```

Relevant behavior:

- finite live process-group ceiling: 256 members;
- in-run census cadence: 1 second;
- over-limit execution terminates through the existing identity-verified session cleanup;
- runtime-safety return code: 78;
- cleanup reason: `process_group_member_limit_exceeded`;
- terminal whole-session reconciliation remains unchanged;
- ambiguous group/session identity fails closed.

The previous vulnerable runtime was:

```text
sha256 8b2c28e8886fa695226b3ef3df1df05ba31fc286e7534b0bbac0ae9727cba3d9
```

Rollback copies of that preimage were preserved on the updated runtime surfaces.

## Verification

The candidate first passed focused process-fuse tests and was then behavior-verified live on both macOS and Linux:

- normal owned process: rc 0, `normal_completion`, cleanup proven;
- forced over-limit process group: rc 78, `process_group_member_limit_exceeded`, residual count 0, cleanup proven.

On the canonical M2 fabric kit, the affected lifecycle/publication suite was repaired for current import closure and then passed:

```text
61 passed
```

The repaired tests include a focused regression for over-limit termination, exactly-at-limit acceptance, and ambiguous-identity refusal.

## Canonical operational source

The machine-wide M2 `~/.local/bin/pool` wrapper identifies this existing kit as its single source of truth:

```text
~/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/
  handoff_kits/meta-ceo-b-2026-09-08
```

That kit was found to still contain the vulnerable runtime after the first downstream host rollout. It was corrected in place with exact preimage checks, backup, atomic replacement, compile, and readback.

Canonical runtime now reads back as `a9eb2ea9...`.

## Immutable support publication

The existing publisher is `ext/support_bundle.py`, schema `remote-support-code.v1`. It owns the fixed source closure, publication flock, content digest, sealed release tree, copied-byte rehash, and final release verification.

A hardened immutable code release was published on Mini2 without changing its independently drifted routing policy and without launching a provider task:

```text
support digest:
1eb2b17862186c7b5b4e4263ff1a73521a8122a030fc83e9608cb5a457f2328f

lane_runtime.py inside release:
a9eb2ea9aac751da0f618fcbbbc228c3ec558f08334cf0da43963491d4e4a061

release mode:
0555

fixed source files:
21
```

Normal `remote_sub.sh` computes the support digest, publishes the immutable bundle on the selected host, and launches `remote_sub_exec.py` from `support-releases/$SUPPORT_DIGEST/ext` before provider execution.

## M1 execution quarantine

M1's `~/lanes` is backed by `/Volumes/STORAGE`. The affected exact runtime and `active/` directory could not be read within repeated bounded probes, including a 15-second exact read. The volume is APFS/USB, nearly full, and macOS blocked an attended read-only `diskutil verifyVolume` attempt at the Files & Folders boundary.

Because neither the runtime preimage nor the idle/active state could be proven, no M1 runtime write was attempted.

The existing host-placement role model was used instead. M1's execution role was changed from:

```text
["ci-runner", "data-service", "lanes"]
```

to:

```text
["ci-runner", "data-service"]
```

This preserves CI and data-service duties while making the existing `host_pick` roles gate fail for lane placement.

The hold is present in the canonical M2 kit and in all readable current fabric registries that were updated in this recovery pass. M1's own unreadable external-volume copy was not modified.

Release condition for the hold:

1. prove M1's active execution census;
2. prove or install runtime `a9eb2ea9...`;
3. pass normal host admission/readiness gates;
4. deliberately restore the `lanes` role and prove routing eligibility.

## Recovery state

Mini2 itself returned to the canonical host-recovery `READY` state after FileVault/post-unlock recovery, power-policy repair, transport restoration, and disk-floor recovery. SSH, Tailscale, Screen Sharing/ARD and Desktop Commander were independently restored.

Do not redo the vulnerable-runtime rollout or re-enable M1 lanes merely because its storage path later becomes readable. Re-enter at the explicit M1 release conditions above.
