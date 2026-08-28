# CF2-H0 final-review continuation progress

Plan: `docs/superpowers/plans/2026-08-27-executive-capacity-cf2-h0-final-review-continuation.md`

## Task 1 — complete

### Frozen carrier and procedure

- Worktree: `/Users/chriswong/Documents/Cluade/Mastermind-h0-source-closure-20260827`
- Branch: `codex/cf2-h0-source-closure-20260827`
- Pre-edit HEAD: `bb40b24838b0633e154d96db5074d517d644072f`
- Preserved merge parents: `1f1c29048af584f6e7fcf28453957bc84d6e057a` and protected master `af43f356f4f7f34cb3514d1d1099b50444af8487`
- Protected Skillpack pin: `mastermindx-market-intelligence/Mastermind@af43f356f4f7f34cb3514d1d1099b50444af8487`
- Loaded from that exact pin: `docs/sol_skills/INDEX.md`, `docs/sol_skills/COLD_START.md`, and `docs/sol_skills/REVIEW_RETURN.md`; each declares `mastermind.sol_skillpack.v1`, version `1.0.0`, compatible with project `bootstrap_major = 1`.
- Pre-edit baseline supplied by the coordinating reviewer: `scripts/ci_pytest.py --plan-only` reported `discovered=330 excluded=0 running=330`; the frozen seven-file pytest matrix reached 100% and exited 0 at `bb40b24838b0633e154d96db5074d517d644072f`.

### RED evidence

The first source/test edit was behavioral test coverage only. Exact command:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'pre_flags_recovery_v1 or recovery_v1_digest_preserves_exact_pre_flags or recovery_v1_digest_keeps_flags or complete_post_read_file_state_drift or rechecks_descriptor_security_after_file_read or true_traversal_ancestor_obeys_complete_security_law'
```

Result: exit 1; `27 failed, 1 passed, 170 deselected in 14.15s`.

The failures discriminated the current defects:

- both exact pre-flags recovery-v1 replay cases refused with `RECOVERY_TREE_DIGEST_MISMATCH`;
- the recovered v1 digest no longer matched the pre-flags canonical byte identity;
- post-read file type, mode, UID, GID, link-count, and BSD-flag drift was accepted;
- post-read ACL and xattr drift was accepted; and
- insecure true traversal-ancestor owner, mode, device, link, ACL, and xattr state at open, plus retained identity/security drift at revalidation, was accepted.

The one passing case was the retained negative law: a stable nonzero BSD flag is still refused as recovery-v1 security validation even though flags must not participate in the legacy digest identity.

After the native traversal policy was narrowed, the link-count distinction was added RED-first. Exact command:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'traversal_ancestor_tolerates_positive_link_count_churn or fixed_system_root_freezes_exact_link_count'
```

RED result: exit 1; `F. [100%]`; 1 failed and 1 passed. The positive traversal-ancestor churn case refused with `SOURCE_REPAIR_PARENT_DRIFT`; the fixed-system-root exact-link-count refusal already passed.

### Implemented law

- A regular file now has one authoritative before/after tuple: device, inode, file type, permission mode, UID, GID, link count, BSD flags, size, mtime, and ctime. ACL, xattr, and flag security validation is rerun after the descriptor content read.
- Retained traversal-only ancestors above the fixed H0 system root require directory type, a trusted owner, no group/other write, positive link count, no extended ACL, an approved native traversal xattr-name set, the required device relationship, and an exact retained parent/name relationship. Revalidation freezes device, inode, type, mode, UID, GID, the initially observed platform flags, and the exact initially observed xattr-name set.
- Traversal-only ancestor `nlink` is required to remain at least 1 but its numeric value and timestamps are not frozen. Shared native ancestors legitimately change link counts when unrelated processes create or remove siblings.
- The fixed H0 system root separately freezes the full descriptor directory state, including exact link count and timestamps, enforces literal zero BSD flags, forbids extended ACLs, permits only the existing approved H0 xattrs, and retains its exact parent/name relationship.
- Existing H0-owned transition parents keep their phase-derived link-count rules.
- Hermetic test-adapter traversal permits the fixture UID/GID in addition to root ownership; production passes the root UID/GID and therefore requires root ownership without hard-coding one platform GID.
- Only legacy pathname `_closed_tree_digest()` directory/file canonical rows omit `flags`. Zero-flags refusal remains a separate validation, and the descriptor-based source-repair v2 digest still emits `flags: 0`.

### Empirical macOS traversal exceptions

The initial literal-zero policy was invalid for traversal-only native ancestors. Exact observation command:

```text
/usr/bin/stat -f '%N flags=%f nlink=%l uid=%u gid=%g mode=%p dev=%d ino=%i' / /var /var/folders /private /Library /private/var/folders/sb
```

Observed platform flags were `/=1048576`, `/var=557056`, `/var/folders=1048576`, `/private=1081344`, `/Library=1048576`, and `/private/var/folders/sb=1048576`. `/var` is a symlink in the pathname observation; retained descriptor traversal still binds the resolved directory identities and relations.

Exact xattr-name observation command:

```text
/usr/bin/xattr / /private /private/var /private/var/folders /private/var/folders/sb /Library
```

Result: `/private/var/folders/sb: com.apple.rootless`; the other queried paths emitted no names. The traversal-local policy therefore permits `com.apple.rootless` only as an initially observed, exactly revalidated name; `_APPROVED_SYSTEM_XATTRS` was not broadened, extended ACLs remain forbidden, and no platform xattr is cleared or mutated.

An intermediate 47-case recovery/crash run reached 43 passes and 4 false refusals while an unrelated pytest process (PID 92054 in the Macro repository) created and deleted siblings below a retained native temp ancestor. Each of the four cases passed in isolation. This was the direct evidence for validating traversal `nlink >= 1` without freezing its numeric value. The fixed H0 system root and H0-owned transition objects were not weakened.

### GREEN evidence

Expanded focused selector:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'pre_flags_recovery_v1 or recovery_v1_digest_preserves_exact_pre_flags or recovery_v1_digest_keeps_flags or complete_post_read_file_state_drift or rechecks_descriptor_security_after_file_read or true_traversal_ancestor_obeys_complete_security_law or traversal_ancestor_tolerates_positive_link_count_churn or fixed_system_root_freezes_exact_link_count'
```

Result: exit 0; `............................. [100%]` (29 selected cases passed).

Exact recovery/crash matrix:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'recovery or crash'
```

Result: exit 0; `............................................... [100%]` (47 selected cases passed).

Complete Task 1 module:

```text
python3 -m pytest --collect-only -q tests/test_capacity_host_artifacts.py
```

Result: exit 0; `tests/test_capacity_host_artifacts.py: 274`.

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py
```

Result: exit 0; pytest reached `[100%]` with no failures (all 274 collected cases passed).

Apple system-Python compilation:

```text
/usr/bin/python3 -m py_compile ops/executive_os/capacity_host_artifacts.py tests/test_capacity_host_artifacts.py
```

Result: exit 0; no output.

```text
git diff --check
```

Result: exit 0; no output.

### Files and commit identity

- Modified: `ops/executive_os/capacity_host_artifacts.py`
- Modified: `tests/test_capacity_host_artifacts.py`
- Added SDD evidence: `.superpowers/sdd/2026-08-27-executive-capacity-cf2-h0-final-review-continuation/progress.md`
- Preserved and included continuation plan: `docs/superpowers/plans/2026-08-27-executive-capacity-cf2-h0-final-review-continuation.md`
- Narrow commit message: `fix(exec): close H0 descriptor state gaps`
- Commit identity: the single Task 1 commit containing this ledger. Its exact SHA is reported in the coordinating handoff after commit; a commit cannot embed its own SHA because changing this file changes that SHA.

### Scope boundary and caveats

- Task 2 was not started.
- No provider home, credential, service, OAuth, routing, WP/C1/Slack Relay, native/root, launchd, or host state was read or modified as part of the implementation.
- No branch, worktree, PR, push, deployment, or native install ceremony was created or performed.
- This is repository implementation and local verification evidence only; it is not an H0 native-host pass or CF2-P0 acceptance receipt.

## Task 1 independent-review follow-up

### Review finding and re-pin

- Re-pinned clean carrier HEAD `6dd8125edf1f2561e5c5a9c1c7f2115b5206a075` on `codex/cf2-h0-source-closure-20260827`; protected `origin/master` remained `af43f356f4f7f34cb3514d1d1099b50444af8487`.
- Independent review reproduced that a stable arbitrary user `stat.UF_NODUMP` bit on a traversal-only ancestor was accepted at initial open. The cause was that `_require_source_repair_ancestor()` enforced type, owner, mode, device, positive link count, and ACL rules but no initial flag allow-policy; the later exact snapshot therefore legitimized every initially observed bit.

### Review-fix RED

The behavioral tests were added before the production allow-policy. Exact command:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'traversal_ancestor_refuses_stable_user_flag_at_open or traversal_ancestor_accepts_observed_platform_flags'
```

Result: exit 1; `F... [100%]`. `test_source_repair_traversal_ancestor_refuses_stable_user_flag_at_open` failed with `Failed: DID NOT RAISE CapacityHostArtifactError`; the three positive cases for the actually observed macOS platform flag combinations passed.

### Bounded review fix

- Traversal-only ancestors now permit only the union of the platform-managed bits required by the observed native states: `SF_NOUNLINK` (`0x00100000`), `SF_RESTRICTED` (`0x00080000`), and `UF_HIDDEN` (`0x00008000`). Any other initial bit, including stable `UF_NODUMP`, refuses with `SOURCE_REPAIR_PARENT_INVALID`.
- Each stat constant is loaded through `getattr`; Darwin-only numeric fallbacks preserve Apple system-Python compatibility where `stat.SF_RESTRICTED` is absent. Non-Darwin platforms use a zero allowed mask.
- The allowed initial value is still exactly snapshotted, so any later flag drift refuses. The fixed H0 system-root zero-flags law and all H0-owned zero-flags laws remain unchanged.
- `_APPROVED_SYSTEM_XATTRS` and the traversal-local xattr-name policy are unchanged.

### Added legacy-v1 directory fixture

Final spec review requested an exact nested recovery-v1 identity fixture in addition to the flat-file cases. A real nested directory/file tree is observed through deterministic fixed UID/GID/link metadata and asserted against the literal pre-flags v1 digest `1da4f381e08384e9cc388a87d845788a08cfafb12c0f1c76a1218ffb737c3e70`.

Exact characterization command before any further source change:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'recovery_v1_digest_preserves_committed_nested_pre_flags_fixture'
```

Result: exit 0; `. [100%]`. The implementation already preserved nested legacy-v1 byte identity, so this addition was test-only.

### Review-fix GREEN

Expanded Task 1 focused selector:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'pre_flags_recovery_v1 or recovery_v1_digest_preserves_exact_pre_flags or recovery_v1_digest_keeps_flags or committed_nested_pre_flags or complete_post_read_file_state_drift or rechecks_descriptor_security_after_file_read or true_traversal_ancestor_obeys_complete_security_law or traversal_ancestor_tolerates_positive_link_count_churn or fixed_system_root_freezes_exact_link_count or traversal_ancestor_refuses_stable_user_flag_at_open or traversal_ancestor_accepts_observed_platform_flags'
```

Result: exit 0; `.................................. [100%]` (34 selected cases passed).

Recovery/crash selector, now including the nested recovery fixture:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'recovery or crash'
```

Result: exit 0; 48 selected cases reached `[100%]` with no failures.

Complete module:

```text
python3 -m pytest --collect-only -q tests/test_capacity_host_artifacts.py
```

Result: exit 0; `tests/test_capacity_host_artifacts.py: 279`.

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py
```

Result: exit 0; all 279 collected cases reached `[100%]` with no failures.

Apple system-Python compilation and guarded-mask proof:

```text
/usr/bin/python3 -m py_compile ops/executive_os/capacity_host_artifacts.py tests/test_capacity_host_artifacts.py
```

Result: exit 0; no output.

```text
/usr/bin/python3 -c 'from ops.executive_os import capacity_host_artifacts as artifacts; print(artifacts._TRAVERSAL_ANCESTOR_ALLOWED_FLAGS)'
```

Result: exit 0; `1605632`, exactly `0x00100000 | 0x00080000 | 0x00008000`.

```text
git diff --check
```

Result: exit 0; no output.

### Review-fix files and commit identity

- Modified: `ops/executive_os/capacity_host_artifacts.py`
- Modified: `tests/test_capacity_host_artifacts.py`
- Appended: `.superpowers/sdd/2026-08-27-executive-capacity-cf2-h0-final-review-continuation/progress.md`
- Narrow follow-up message: `fix(exec): restrict H0 traversal ancestor flags`
- Commit identity: the follow-up commit containing this appended ledger. Its exact SHA is reported after commit because embedding a commit's own SHA changes that SHA.

### Review-fix scope boundary

- Task 2 and Task 3 were not started.
- No native/root/provider/service/credential/OAuth/routing/WP/C1/Slack Relay state was touched.
- No new native flag bit was observed or silently added; the live full-module path completed under the explicit reviewed mask.

## Task 2 — in progress

### Frozen pickup and independent e4 identity

- Exact pickup HEAD: `90420a97e9a9ddd4aef6abb83fadf0a12f22481e` on the existing clean `codex/cf2-h0-source-closure-20260827` carrier.
- Protected `origin/master` and Skillpack pin: `af43f356f4f7f34cb3514d1d1099b50444af8487`.
- Loaded from that exact pin: `docs/sol_skills/INDEX.md`, `docs/sol_skills/COLD_START.md`, and `docs/sol_skills/REVIEW_RETURN.md`; schema `mastermind.sol_skillpack.v1`, version `1.0.0`, compatible with project `bootstrap_major = 1`.
- Independently derived from direct Git objects without executing installed/repository payload code: e4 commit `e4e44867ace335ac9208a3990a10c163e199492d`, tree `ee1b95af3341a49151890cec1a6a31997f632aec`, canonical manifest SHA-256 `ecb9a58eec12890126c291a451921ab0dd738baee765c61aae3a42fd74a31fc9`, byte length `190196` including one final LF, and `1122` entries.

### RED evidence

The first Task 2 filesystem edit changed tests only. Exact command:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'trusted_e4 or self_authored_payload or wrong_trusted_e4_tree or basename_relation or preserved_semantic_reads or absolute_evidence_view'
```

Result: exit 1; `FFFFFFFFFF [100%]` (10 failed).

The failures discriminated the current defects:

- no reviewed e4 tree/manifest trust constants existed;
- an arbitrary payload plus self-authored internally matching manifest under the exact e4 basename was accepted;
- a canonically shaped manifest carrying the wrong e4 tree was accepted;
- an exact release-basename swap was accepted when descriptor-metadata side effects were held constant, proving the retained root was not rebound to its parent/name relation;
- runtime, generation, topology, rollback, and legacy semantic views had no descriptor-read capability, so the preserved verifier could not use the retained graph as its read authority; and
- an absolute evidence view had no retained-descriptor read capability and opened its absolute parent directly instead of starting at a retained `/` and traversing component by component.

The installed-release sentinel test remains present and continues to forbid execution of installed `release_manifest.py` payload bytes.

The live adversarial controller then required deeper retained-graph coverage. Those tests were also added before their production capabilities. Exact command:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'unrelated_retained_view or approved_xattr_name_set_drift or optional_absence or forbidden_stable_ancestor_flags or fixed_macos_root_alias or supplied_retained_semantic_views'
```

Result: exit 1; `FFFFFFF [100%]` (7 failed).

The additional RED failures proved that an unrelated retained release view could be injected, an approved xattr name could appear after a semantic read without refusal, optional absence had no retained-parent capability, absolute-view ancestors accepted a stable forbidden user flag, native `/var` and `/tmp` symlink components had no authenticated traversal, and the preserved verifier body had no retained-view input contract and therefore could not be proven free of pathname reads.

The first full-module attempt was interrupted by the controller after 45m51s because it exceeded the 279-case pre-change baseline by more than threefold; it is not acceptance evidence. Deterministic profiling isolated repeated retained-repository graph revalidation, not e4 manifest traversal: one source-repair test spent 21.917s across 619 `_RepositoryView.revalidate` calls, including 78,613 `_revalidate_object` calls and 25,379 retained-parent capability checks. A performance regression test was added before optimizing the graph walk. Exact RED command:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'full_revalidation_walks_retained_parent_capability_once'
```

Result: exit 1; `F [100%]`. The one full retained-graph revalidation performed 18 parent-capability checks instead of the required two (one explicit outer check and one identity-bound root relation check), proving repeated ancestor recursion across sibling/descendant objects.

The RED was strengthened to a branching three-level graph with an exact per-object xattr-audit counter and paired with a refusal-path descriptor-ownership regression. Exact command:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'full_revalidation_walks_retained_parent_capability_once or closes_guard_descriptor_when_initial_guard_audit_refuses'
```

Result: exit 1; `FF [100%]`. The branching graph performed 20 parent-capability checks instead of two, and the initial `/` guard descriptor was opened but never closed when its security audit refused.

### GREEN evidence

The retained graph now uses one shared `seen` set per complete temporal gate, so every retained object, relation, exact xattr-name set, BSD-flag state, and ACL state is audited once while semantic reads still recheck their complete ancestor chain before and after reading. Guard descriptor ownership is registered before its first security audit, and retained runtime file hashes are reused within one authenticated runtime verification.

The two performance/refusal regressions turned green:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'full_revalidation_walks_retained_parent_capability_once or closes_guard_descriptor_when_initial_guard_audit_refuses'
```

Result: exit 0; `.. [100%]` (2 selected cases passed). The branching three-level graph performs exactly two retained-parent capability checks and exactly one xattr-name audit per retained object for the full gate.

The representative source-repair test used for deterministic timing improved from `25.42s` before the shared graph walk to `9.72s` after it:

```text
python3 -m pytest -vv --durations=5 -o addopts='' tests/test_capacity_host_artifacts.py::test_source_repair_host_commits_generation_last_and_verify_is_zero_mutation
```

Result: exit 0; 1 passed in `10.77s`, with the test call reported as `9.72s`.

The complete discriminating Task 2 selector, including the performance and refusal-path regressions:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'unrelated_retained_view or approved_xattr_name_set_drift or optional_absence or forbidden_stable_ancestor_flags or fixed_macos_root_alias or supplied_retained_semantic_views or trusted_e4 or self_authored_payload or wrong_trusted_e4_tree or basename_relation or preserved_semantic_reads or absolute_evidence_view or inert_release_manifest_verifier_never_executes_installed_payload or full_revalidation_walks_retained_parent_capability_once or closes_guard_descriptor_when_initial_guard_audit_refuses'
```

Result: exit 0; `.................... [100%]` (20 selected cases passed).

Preserved-invariant and source-repair compatibility gate:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'preserved or source_repair'
```

Result: exit 0; all selected cases reached `[100%]` with no failures in about 81 seconds, down from about 176 seconds before the shared graph walk.

Complete module with explicit elapsed time:

```text
/usr/bin/time -p python3 -m pytest -q tests/test_capacity_host_artifacts.py
```

Result: exit 0; all 298 collected cases reached `[100%]`; `real 1148.81`, `user 476.21`, `sys 513.97`. This bounded 19m08.81s run replaces the interrupted 45m51s non-evidence run.

Final collection, Apple system-Python compilation, and diff gates:

```text
python3 -m pytest --collect-only -q tests/test_capacity_host_artifacts.py
```

Result: exit 0; `tests/test_capacity_host_artifacts.py: 298`.

```text
/usr/bin/python3 -m py_compile ops/executive_os/capacity_host_artifacts.py tests/test_capacity_host_artifacts.py
```

Result: exit 0; no output.

```text
git diff --check
```

Result: exit 0; no output.

### Task 2 files and scope boundary

- Modified: `ops/executive_os/capacity_host_artifacts.py`
- Modified: `tests/test_capacity_host_artifacts.py`
- Appended: `.superpowers/sdd/2026-08-27-executive-capacity-cf2-h0-final-review-continuation/progress.md`
- Task 3 was not started.
- No native/root/provider/service/credential/OAuth/routing/WP/C1/Slack Relay state was touched.
- No installed release payload was executed; the strengthened sentinel authenticates its manifest first and then refuses changed payload bytes without launching any subprocess.
- Task 2 remains repository implementation proof only, not native H0, CF2-P0, merge, deploy, or production acceptance.

## Task 2 review-fix follow-up (2026-08-27)

Exact clean pickup was `c1eb17720054e8b538250af8d875b3968b5921f3`
with parent `90420a97e9a9ddd4aef6abb83fadf0a12f22481e`. Current protected
master `b901dee0272a99b8a1d60385848b99b7273e8261` supplied the compatible
`INDEX`, `REVIEW_RETURN`, `RECONCILE_STATE`, and `COMMISSION_WAVE` procedures.

### RED evidence

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'preserved_fd_budget or absolute_component_validation or native_alias_descriptor_is_owned or stably_unsafe_regular or generation_parent_capability or retained_prior_generation'
```

Result: exit 1; `FFFFFFFFFFFFFFF [100%]` (15 selected failures). The exact
failures proved the FD-budget constant/gate absent, absolute-component
validator absent, all four alias audit-stage descriptors leaked, stable 0666
and hardlinked files were accepted into a retained graph, lifecycle parent
selection was absent, and retained prior-generation inventory/hash
authentication was absent.

The first complete-module review-fix run exposed one integration-level error
contract regression at 44% and was stopped immediately after the failure:

```text
/usr/bin/time -p python3 -m pytest -q tests/test_capacity_host_artifacts.py
```

Result: exit 1 after interruption; the existing
`test_root_created_carrier_is_immune_to_preopened_operator_write_descriptor`
expected `REPAIR_CARRIER_INVALID`, but the newly strengthened generic retained
view rejected the injected carrier hardlink during construction with the
internal `SOURCE_METADATA_INVALID` reason. This proved that constructor-time
retained-view refusals escaped the public repair-carrier error boundary.

### GREEN evidence

The preserved repair-carrier hardlink refusal remains enforced at retained
view construction, while the public verifier now normalizes that internal
refusal to its stable carrier contract and closes any partially constructed
view:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py::test_root_created_carrier_is_immune_to_preopened_operator_write_descriptor
```

Result: exit 0; `. [100%]`.

The complete new review-fix selector passed:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'preserved_fd_budget or absolute_component_validation or native_alias_descriptor_is_owned or stably_unsafe_regular or generation_parent_capability or retained_prior_generation or role_security_policy or release_manifest_bad_manifest_never_opens_payload or release_manifest_unexpected_child_never_opens_payload or release_manifest_metadata_mismatch_precedes_hash or production_preserved_invariant_callers_use_source_repair_parents or fixed_parent_approved_xattr_name_set_drift'
```

Result: exit 0; `................ [100%]` (16 selected cases passed).

The positive FD-budget subprocess was also run directly so its captured
resource receipt was explicit. It began at soft limit 256, authenticated the
reviewed uplift before constructing the exact-scale graph, retained all 1,122
children plus the graph root, and revalidated successfully:

```text
{"actual": 16384, "count": 1123, "observed": 16384, "peak": 1137}
```

Result: exit 0. The reviewed fixed minimum is therefore 16,384 descriptors;
the exact-scale retained graph peaked at 1,137 open descriptors in the isolated
subprocess.

The prior Task 2 focused set remained green:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'unrelated_retained_view or approved_xattr_name_set_drift or optional_absence or forbidden_stable_ancestor_flags or fixed_macos_root_alias or supplied_retained_semantic_views or trusted_e4 or self_authored_payload or wrong_trusted_e4_tree or basename_relation or preserved_semantic_reads or absolute_evidence_view or inert_release_manifest_verifier_never_executes_installed_payload or full_revalidation_walks_retained_parent_capability_once or closes_guard_descriptor_when_initial_guard_audit_refuses'
```

Result: exit 0; `.................... [100%]` (20 selected cases passed).

The preserved/source-repair compatibility gate passed:

```text
/usr/bin/time -p python3 -m pytest -q -x tests/test_capacity_host_artifacts.py -k 'preserved or source_repair'
```

Result: exit 0; all selected cases reached `[100%]`; `real 74.54`,
`user 31.99`, `sys 33.49`.

The complete module then passed from an unchanged production/test source
state:

```text
/usr/bin/time -p python3 -m pytest -q -x tests/test_capacity_host_artifacts.py
```

Result: exit 0; all 325 cases reached `[100%]`; `real 1044.23`,
`user 461.86`, `sys 454.41`. This is faster than the accepted 298-case Task 2
run (`real 1148.81`) despite 27 additional review-fix regressions and replaces
the interrupted 44% integration run.

Final collection, Apple system-Python compilation, and diff gates:

```text
python3 -m pytest --collect-only -q tests/test_capacity_host_artifacts.py
```

Result: exit 0; `tests/test_capacity_host_artifacts.py: 325`.

```text
/usr/bin/python3 -m py_compile ops/executive_os/capacity_host_artifacts.py tests/test_capacity_host_artifacts.py
```

Result: exit 0; no output.

```text
git diff --check
```

Result: exit 0; no output.

### Review-fix files and boundary

- Modified: `ops/executive_os/capacity_host_artifacts.py`
- Modified: `tests/test_capacity_host_artifacts.py`
- Appended: `.superpowers/sdd/2026-08-27-executive-capacity-cf2-h0-final-review-continuation/progress.md`
- Exact parent for the single follow-up commit:
  `c1eb17720054e8b538250af8d875b3968b5921f3`.
- Task 3 remains held. No native/root/provider/service/credential/OAuth/routing,
  WP/C1/Slack Relay, PR, merge, push, deployment, or installed payload execution
  occurred. This is repository implementation proof only.
