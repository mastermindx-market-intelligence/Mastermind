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
