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


## Continued mini-helper safety implementation

Protected source pin: `fa47667800877e89263d00261cb7252667c1cf8a`; INDEX blob `4b0189a75d559d963365097485e8509a49c70e23`. The original operation and registered Web workspace are reused; no replacement worktree was minted. #1099 is merged at `9935fcdb1fb3dc3c133a514c7efff1c65f34e49d`, and #939 at `0f960bcd287cea2d10f8d0e0b741140b5fa27d12`. Neither merge is installed-generation proof. #929 remains an independently review-gated carrier at `84c7dad17478632e7aa4523e9aecac2fc75fcf38`; its full hosted CI has now succeeded.

### Observed defects and implemented behavior

The merged mini helper checked free space only on `hot_root` and only before bootstrap. Its object-store volume could be full; clone/fetch/materialization could consume the reserve; and a new worktree could still be added afterward. The revised existing admission helper observes both `hot_root` and `store_root`, refuses unknown/invalid telemetry, and refreshes observations after clone, before and after store hydration, before new worktree creation, and after workspace hydration. It preserves the partial carrier on post-effect refusal rather than deleting evidence or advertising retry safety. These are observations, not atomic reservations or projected peak-byte accounting.

Git custody is now acquired atomically with `git worktree add --no-checkout --lock`. New locks use `mastermind-mini-hot:v2`; the existing per-worktree Git config records `mastermind.miniPrepared` only after exact head/branch/lock validation and final space checks. The marker must exactly equal the current operation lock and occur once. A v2 worktree without valid completed-preparation evidence cannot be resumed as ready, even if space later recovers. Its census row remains UNKNOWN/PARTIAL. This is local construction evidence in the existing Git owner, not a new lifecycle or lease database.

Successful old v1 sessions remain locally resumable with their original lock identity. Resume does not retrofit files, fetch, or demand new-allocation free space. An old helper must not be used to operate a new v2 workspace: its stricter old lock matching will refuse rather than adopt the new generation.

The existing census now reports both free-space observations and a separate `storage` object with READY/LOW_SPACE/UNKNOWN, `new_allocation_allowed`, a reason and `reservation:false`. This is storage eligibility only; it grants no placement, source ownership, provider, release or deletion authority. Unknown disk telemetry does not erase registered workspace rows. Missing-path and incomplete-preparation diagnostics remain distinct.

### Verification and evidence boundaries

Allocation RED: 12 failures and 1 existing-recovery pass. Early-lock/preparation RED: 8 failures and 1 legacy-recovery pass. Allocation + preparation and existing tests then reached 62/62. The six additional census discriminators all failed on their preimage. The packaged-process canary uses the real installer in a disposable home and consumes a fixture created by the real constructor, with all Git network protocols disabled during resume. It proves installed-process clean/dirty resume, missing-preparation refusal and PARTIAL census; it is not a production host installation or a new-allocation network canary.

The first package-fixture attempt was rejected because Git expanded an `insteadOf` rewrite into a different remote identity. The origin guard correctly refused it. The test was corrected without weakening source identity validation. The full local repository test attempt remains blocked at collection by missing `jwt`, `claude_agent_sdk`, and `mcp`; no complete local-suite pass is claimed. Complete hosted verification and independent source review remain release gates.

### Remaining actual rollout gates

Current M2 and all four mini connector profiles exclude the canonical installation targets (`~/.local/bin`, `~/.local/share/mastermind/mini-worktree`, `~/.config/mastermind`, and the configured mini store/hot roots). No permission profile was widened and no alternative installation location or shell bypass was used. MacBook and M1 are currently reported offline. Earlier platform-refused app/settings and legacy-maintenance actions remain held; a new chat does not clear them.

The installed Executive read-only runtime still reports release `c7407c6c77ef82cc6590401e80cc8f1868dc9085`, not the newly merged sparse constructor. Actual per-host installation, authenticated Macro configuration, provider/native-app bindings, broader operator/fabric consumer proof, and safe runner-object-store maintenance remain unproven. Preserve the old no-retrofit/no-personal-data/no-live-repack rules.

Machine evidence under the existing evidence root includes `tests/allocation-red.log`, `tests/allocation-green.log`, `tests/preparation-red.log`, `tests/mini-hardening-final.log`, `tests/storage-projection-red.log`, `tests/mini-packaged-proof.log`, `tests/mini-packaged-resume-proof.log`, and `tests/mini-hardening-project-test.log`. The final qualification result and immutable published head are recorded separately after completion.
