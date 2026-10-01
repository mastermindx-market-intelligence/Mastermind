# Fleet storage ingress and lifecycle repair

**Goal:** Prevent repeated full materialization at every supported creation boundary, reconcile existing host cleanup installations, and safely recover capacity without losing resumable work.

**Assignment:** Chairman's current 2026-09-30 end-to-end storage mandate. Operation `fleet-storage-ingress-20260930-sol-c3-001`, attended Web workspace, Studio Direct carrier. Protected Mastermind base `0d73b1b9f4345110fa9fb732896cd20ac76ad5ef`. Organizational owner remains Macro `WS:FLEET-STORAGE-LIFECYCLE`.

**Architecture:** Reuse repository `config/sparse_worktree.json`, installed host storage policy, mini hot-tier helper, Git-native workspace custody, and the existing cleanup/health owners. Constructor code sets sparsity before checkout; app hooks are adapters, not the security or storage boundary. Trusted attended trees share objects. Executive workers keep independent credentialless Git stores. Existing active trees are never retrofitted automatically.

**Non-negotiable preservation:** No automatic reclamation of human Web/Sol/review roots, no age-only deletion, no destruction of dirty/local-only work, no pruning live shared stores, no photo/library/browser-profile cleanup, no runner maintenance without a drained listener. Existing 300 GiB external reserve and mini 50/70 GiB policy are not lowered. Sparse does not solve historical Git pack storage.

## Source slice
- [x] Add real-Git regression tests in `tests/test_workspace_sparse_materialization.py`: first materialization, exact-base profile, invalid policy, source-config isolation, worker-private metadata, granted write paths, reuse with dirty edits, and construction failure cleanup.
- [x] Update only creation seams in `control_plane/executive_workspace.py`: strict exact-base profile read, explicit no-checkout, per-worktree sparse setup, exact-base hydration. Absence/explicit disable preserves legacy semantics rather than fabricating coverage.
- [ ] Run new tests RED then GREEN and existing workspace/service tests. Inspect installed CLI dependency closure before packaging. Keep #1014 release changes and #929 enrollment changes disjoint; do not replace their owners.

## Host repair slice
- [x] Test and install the already-merged Macro GC wrapper upgrade with backup, exact preimage and readback. Do not broaden deletion roots or re-enable sparse retrofit.
- [ ] Audit actual installed mini helper and app bindings, including mini4 and MacBook. Preserve hooks/settings, exact account paths and assigned workspace identity. No provider spawn for testing.
- [ ] Reconcile old cleanup/repack safety before invocation; use existing maintenance owners. Audit known 44.19 GiB proof clones freshly before any bounded reclaim. Never touch personal photo data.
- [ ] Bind deterministic health to existing scheduling: missed schedules, genuine failures, free-space admission, installation drift and creation coverage; no second lifecycle database.

## Acceptance
Source tests alone are BUILT_NOT_PROVEN. Record exact installed hashes, host/app/constructor canaries, actual reclaimed bytes separately from estimates, and remaining held/unreachable paths. Publish scoped PR and cumulative checkpoint; no fleet-wide completion claim until each avenue has real proof.

## Initial verified findings
- Studio: Mastermind external 85% used / 570 GiB free; Worktrees 87% / 130 GiB free. Worktrees is mostly personal data, not a blanket cleanup target.
- Installed attended launcher uses old `ac6180d0...`; its constructor does a full `worktree add`. Executive constructor clones without checkout then immediately performs a full checkout; ignores global Git config intentionally.
- #939 mini helper installed at `0d2203d6...` on mini1/2/3; absent at tested paths on mini4. mini2 free ~50.5 GiB; do not allocate a large clone there.
- Current Mastermind tracked workspace is only 69 MiB; its Git store ~67 MiB packed. Macro/runner objects, not this tree, drive the largest costs.
- Macro GC installed wrapper hash `6c7cb824...` predates merged timeout/last-attempt fixes. Existing sparse-retrofit agent is not loaded and remains disabled.
- Old `repack_repo.py` checks `/` rather than target volume and unlinks indexless packs without a writer/age fence. Do not run it on active repositories.

Direct execution is justified by principal integration judgment and the currently proven Studio/SSH access. No worker has been dispatched by this operation.


## Execution checkpoint — 2026-09-30

### Decisions and verified effects

Ruling: Retain direct constructor implementation (`PRINCIPAL_JUDGMENT` / `UNIQUE_APPROVED_ACCESS`). The installed Executive MCP is read-only; no independent worker has been admitted and no raw-provider workaround is authorized. Keep the organizational lifecycle owner and existing rollout carriers.

Ruling: The code uses the exact-base **existing repository profile**, not a copied hard-coded Macro policy. Absence or explicit disable stays legacy/full; malformed present policy refuses. This prevents policy split but means repositories without a profile are not newly claimed sparse.

Ruling: Per-worktree Git configuration must be host-enrolled before sparse linked construction. Constructors refuse rather than mutate a shared source configuration. Credentialless worker clones remain physically independent, with no hardlinks/alternates/remotes introduced.

Ruling: No active workspace is retrofitted. Exact-operation reuse returns before sparse setup, preserving intentional hydration and uncommitted edits. New linked creation now takes the custody lock in `worktree add --no-checkout --lock`, before materialization.

**Source verification:** 15 new real-Git cases first produced 14 failures / 1 expected pass on the preimage. The final constructor, CLI, existing workspace and commission-preparation battery passed **78/78** under the existing fixtures' explicit test-only umask 022. Python compile and diff whitespace checks passed. Full repository collection was attempted, but this host lacks `jwt`, `claude_agent_sdk`, and `mcp`; that is an environment gap, not a full-suite pass.

**Live Macro canary:** exact `88804ed7079700c598bb8e04aa64307d1335402d`, normal external-storage admission at the unchanged 300 GiB floor, canonical operation lock, empty Git status, all four configured artifact roots absent, source common Git configuration byte-identical. Allocation **648,464 KiB** versus **8,961,316 KiB** of working files in the full proof clone at the same commit: **92.8% smaller working copy**. Historical Git objects are excluded from that comparison. Exact-session reuse passed; the unchanged clean canary was released through the canonical owner and its branch history retained. This is a canary, not proof of installed coverage on every avenue.

**Installed GC repair:** qualified Macro source `71f72e3525042009d6ef9ae608089e57781f534e` with 30 wrapper/liveness tests; atomic backed-up wrapper replacement and byte-identical readback. Wrapper SHA-256 `16748a9310845a026ab15198026e9974e7ba2db426ae071c889403d4d4877a99`. Source timeout/last-attempt fixes are now installed; deletion policy, roots, limits and daily schedule are unchanged.

**Independent schedule witness:** installed canonical read-only `worktree_gc_liveness.py`, SHA-256 `778292579dcbdb98c8ec6e9b52ea9c7b01a861c38a82f8d27fa96705e9fa7444`; loaded `com.macro.worktree-gc-liveness` every 1,800 seconds. The first system-Python/LaunchAgent execution exited 0 and correctly identified all due starts in the three-day window. It detects missing starts, not every semantic sweep failure or a proven user-alert delivery. Existing armed GC was started once without restart/kill at 09:27:40 UTC; completion/reclaimed bytes must be consumed separately from its fresh receipt.

### Remaining rollout boundaries — not waived

- **Application bindings:** a remote app-settings inspection received a platform safety refusal. No settings changed. Do not retry that inspection through a different carrier/actor or claim app hook coverage.
- **M1 Studio:** SSH execution failed and connected Desktop Commander reports offline; no M1 install is claimed.
- **Minis:** mini1/2/3 still carry old `0d2203d6...` helper; mini4 has no helper at inspected paths. Mini2 had about 50.5 GiB free. The repaired #939 exact head `e91b276d...` is independently being assessed; it is not installed by this operation. Its installer intentionally refuses to overwrite the old unauthenticated Macro configuration. Preserve authenticated identity and owner reconciliation rather than copying the unsafe old generation to mini4.
- **Installed workspace CLI:** current launcher is an older payload. #929 owns storage enrollment and the missing `common.commission_ref` packaging closure; this constructor change does not duplicate or bypass that work. #1014 owns published-branch release improvements; release code is unchanged here.
- **Runtime/fabric:** inspected Executive service proof construction and interrupted-attempt rotation both call the changed private-clone constructor. Other fabric/operator factories and native app creation require separate actual consumer proof; the installed Executive service was not replaced.
- **Capacity recovery:** the 41.76 GiB PR979 proof clone is clean, with no local refs/untracked files, and its PR merged. It remains held until dependencies of the installed Macro source at the same SHA are excluded. The Prophet proof clone has 85 ignored artifacts; clean `status` alone is not reclamation permission. No blanket deletion or primary/runner Git repack was performed.
- **Git maintenance:** the old installed `repack_repo.py` checks `/` instead of its target volume and unlinks indexless packs without a writer/age fence. Do not invoke it unchanged on active stores. Use drained-runner maintenance and existing lifecycle owners; retain the explicit no-prune/no-personal-data boundaries.

### Durable evidence

`/Volumes/Mastermind/evidence/fleet-storage-ingress-20260930-sol-c3-001/` contains the backed-up wrapper, GC and liveness installation receipts, the Macro creation/reuse/release canaries, proof-clone preflight, source-qualified helper copies, and actual test logs. This operation does not create another storage lifecycle database or deletion daemon.

**Source status at this checkpoint: BUILT_NOT_INSTALLED, independent review and exact-head hosted checks required. Installed status: GC wrapper and read-only schedule witness repaired on M2 Studio only.**
