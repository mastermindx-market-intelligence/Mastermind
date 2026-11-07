# Four-host Fabric storage recovery — 2026-10-13

**Status:** Verified readback on each original Ubuntu host. Git worktree deletion was performed only on individually proven-clean, inactive, remotely reachable checkouts. No active source/worker, branch, origin ref, provider lease, thermal policy or worker session was deliberately changed by this cleanup.

## Outcome

| Ubuntu | Git worktrees removed | Initial free (GiB) | Final free (GiB) | Recovered (GiB) | Existing protected minimum (GiB) |
|---|---:|---:|---:|---:|---:|
| ubuntu0 | 10 | 219.29 | 321.03 | 101.74 | 300 |
| ubuntu1 | 2 | 132.84 | 152.30 | 19.46 | 150 |
| ubuntu2 | 15 | 2.54 | 155.24 | 152.70 | 150 |
| ubuntu3 | 5 | 166.50 | 217.29 | 50.79 | 300 |
| **Total** | **32** | | | **324.69** | |

These are **point-in-time** effects. Subsequent worker checkouts may consume space. The underlying 10+ GiB full-checkout recurrence has not yet been fixed by cleanup, and Ubuntu3 remains **below** its protected reserve. No disk threshold was lowered. The 15-worktree Ubuntu2 exact SHA/label list appears in [ubuntu2_disk_recovery.md](ubuntu2_disk_recovery.md).

### Ubuntu0 — 10 removed (101.74 GiB)

C19 wave 3 at HEAD `5267c66846e7733bc1eb30edc1524daff51598ca`: `c19-w3-h1-wp10-census`, `c19-w3-h4-wp15-precensus`, `c19-w3-h7-wp25-census`.

C19 wave 4 at HEAD `94c53929fb5e4e0fc0dd15e5a0ce44e2384ca130`: `c19-w4-i11-wp13-design-input`, `c19-w4-i12-wp14-design-input`, `c19-w4-i6-wp27-census`.

C19 wave 4 at HEAD `c5a79a69826eaa6c34b8d7a59ead6506c5f8888d`: `c19-w4-i7-wp28-census`, `c19-w4-i8-wp29-census`, `c19-w4-i9-wp31-census`.

Additionally `mi-br-8807-base` (HEAD `e966b10bd92ab348f317b279adc4a8666d5b124d`) after checking [Macro PR #8807](https://github.com/mastermindx-market-intelligence/macro/pull/8807) merged October 11.

### Ubuntu1 — 2 removed (19.46 GiB)

`idr-cat-census` at HEAD `565f2d70ac44dd7be9a828dae07bb19e531917d8`, verified clean detached and origin-containing, age ~9.5 days.

`mi-aer-8812-base` at HEAD `e966b10bd92ab348f317b279adc4a8666d5b124d`, baseline of merged [Macro PR #8812](https://github.com/mastermindx-market-intelligence/macro/pull/8812). The latter removal's free-space readback was 142.18 GiB → 152.30 GiB.

### Ubuntu3 — 5 removed (50.79 GiB)

C19 wave 3 at HEAD `5267c66846e7733bc1eb30edc1524daff51598ca`: `c19-w3-h3-wp14-census`, `c19-w3-h6-wp24-census`, `c19-w3-h9-wp30-census`. Free-space readback: 166.50 → 197.04 GiB.

`mi-dxr-8816-base` at HEAD `c2fd1cb74d5753a95862f63dc8c1ec2977779814` and `mi-doptr-8818-base` at HEAD `734ab8571d48a4e28ed12eef74643654cd2ee813`, associated respectively with merged [Macro PR #8816](https://github.com/mastermindx-market-intelligence/macro/pull/8816) and [Macro PR #8818](https://github.com/mastermindx-market-intelligence/macro/pull/8818). Final free-space readback 217.29 GiB.

## Safety evidence applied on original host

Every removed target satisfied these requirements immediately before its exact effect:

- User-owned real directory under the host's existing `~/lanes/wt`, registered Git metadata under `~/lanes/repos/macro/.git/worktrees`, no symlink and no `locked` marker; exact host was Ubuntu0/1/2/3, not an unrelated SSD.
- Detached HEAD and at least one existing `origin/*` remote-tracking ref containing that commit; no unique local worktree commit depended only on a detached HEAD.
- `git status --porcelain=v1 -uall` empty **and** `git clean -ndx` preview empty. The latter prevents deletion of ignored/unique local artifacts. Branch-bound and dirty checkout candidates were explicitly preserved.
- No corresponding `~/lanes/ext/active/<id>` marker, and no observed process CWD/file-descriptor reference to the worktree or its Git metadata. Explicit "not found" controller status was not treated as proof of terminal work.
- Mutation via only `git -C <host-original-macro-repo> worktree remove -- <exact-checkout>`. No `--force`, no `rm -rf` fallback and no global prune. Each result was checked for exit code 0, absence of both checkout directory and Git registration, and filesystem available-space increase.

The batch for Ubuntu2 was detailed separately. Ubuntu0's nine C19 checks yielded `BATCH 9 of 9 freed_gib 91.62 free_gib 310.9`. Ubuntu3's three C19 checks yielded `BATCH 3 of 3 reclaimed_gib 30.54 free_gib 197.04`. Individual PR-baseline cleanup receipts all reported success. No uncertain effects remain for this exact set.

## Unfinished constraints

The most important prevention gap is that many other agents create full Macro worktrees with `data/`, `site/`, `mockups/` (roughly 10 GiB per checkout), even though one `lane2.py` route already establishes a pre-checkout sparse profile. Do not pretend its scoped behavior covers every provider/worker worktree. Prevent recurrent full checkout at the **existing** worktree-storage owner and admission seam, after verifying who is still modifying those sources. A correctly placed size-aware reservation must preserve the existing host resource floor while accounting for expected checkout materialization; no new queue, daemon, source lifecycle or homebrew GC authority.

Ubuntu3 remains protected by its `min_free_gb=300` policy. Some remaining trees are branch-attached, dirty, unpublished, or have ignored outputs, so this inspection did **not** authorize deleting them merely to satisfy the reserve. Host power-profile adjustment on Ubuntu2 also remains blocked by the earlier explicit DBus AccessDenied; no sudo/failover attempt was made. Physical temperature/throughput proof is still pending.

## Subsequent verified recovery — same-day continuation

At 13:xx–14:xx UTC, another three C19 checkouts on **Ubuntu 2** passed the same full non-force Git safety validation and were removed by the original host using `git worktree remove -- <exact_path>`:

- `c19-w4-i5-wp22-census`
- `c19-w4-i3-wp19-census`
- `c19-w4-i1-wp17-census`

All three had identical remote-contained HEAD `c5a79a69826eaa6c34b8d7a59ead6506c5f8888d`, clean tracked/untracked/ignored state, detached checkout, no active-marker and no process file/CWD references, with path and Git registration absent after removal. The return was `BATCH 3 of 3 reclaimed_gib 30.54 free_gib 185.63`; previous free was ~155.09 GiB. Subsequent concurrent worker activity reduced that reading again, so do not treat the recovery point as permanent free-space entitlement.

**Updated exact fleet total:** **35** individually verified removals; approximately **355.23 GiB** cumulatively reclaimed (prior 32 / 324.69 GiB plus these 3 / 30.54 GiB). All existing branch identities and original remote HEADs were preserved. Admission storage thresholds were not lowered; the installed 15 GiB staging buffer remains separately enforced by host picker plus physical LaneLease check. The owner must prevent recurrence of full 10.3 GiB checkouts to make the disk reserve durable.

## Evening continuation: verified Git garbage and sparse-preserving recovery

**Observed 2026-10-14T00:50Z onward (evening October 13 in America/New_York).** Four fresh Ubuntu telemetry states were initially all cool (Tctl approximately 42.5/55/61.9/35.9°C, ubuntu0/1/2/3) but only Ubuntu1 was barely above its 165 GiB precheckout free-disk floor: ubuntu0 248.6 versus 315 GiB; ubuntu1 165.2 versus 165; ubuntu2 156.8 versus 165; ubuntu3 240.3 versus 315. This is an operational **space-recurrence** failure, not proof of current thermal throttling. The earlier Git-only cleanup total **35 worktrees / ~355.23 GiB** remains the source-recognized count, not mixed with subsequent in-place sparse conversion.

**Exact Git orphan pack cleanup, no registered objects touched:**

- Ubuntu0, repository `/home/ubuntu0/lanes/repos/macro`: `git count-objects -vH` reported `garbage:3 / size-garbage:4.97 GiB`. After age, ownership, single-link, actual Git-process and open-FD checks, exactly `tmp_pack_F2yDog` (4.071 GiB), `tmp_pack_EOrG7x` (0.755 GiB) and `tmp_pack_3VRxyW` (0.145 GiB) were unlinked under `.git/objects/pack`. Free disk **248.59 → 253.56 GiB**. Follow-up Git census reported `garbage:0 / 0 bytes`; HEAD and **109** registered worktrees unchanged.
- Ubuntu2, repository `/home/ubuntu2/lanes/repos/macro`: `count-objects` reported `garbage:11 / size-garbage:6.21 GiB`, all exact `tmp_pack_*`/`tmp_idx_*`/`tmp_rev_*` objects (largest 3.774 GiB and 1.61 GiB) aged ≥6h. After the same targeted no-open-FD/no-pack-writer checks, those **11** unregistered temporary objects were unlinked. Free disk **166.92 → 173.14 GiB**; follow-up Git census `garbage:0 / 0 bytes`, HEAD and **97** worktree registrations unchanged. These are readings at the actual effect boundary, not promises of continuing space availability.
- Total new Git orphan cleanup: **14 temporary objects, 11.18 GiB**. No `pack-<digest>.pack` or `.idx` registered object was touched; no repack/GC was run.

**Safer alternative to deleting unpublished detached review HEADs — first three successful in-place sparse conversions on Ubuntu0:**

A read-only census found 105 lane worktrees consuming ~406 GiB, many ~10.17–10.33 GiB, particularly SNI and DataOS workers. `c19-w3-g1-review` and `c19-w3-g2-review` had clean detached HEADs not currently contained by a local `origin/*` branch; `mi-br-8807` had a GitHub-published merged PR head but no matching local remote-tracking ref. Deleting such a checkout could discard an otherwise unique local commit, so **no deletion was attempted**.

For each target, actual host preflight proved user-owned non-symlink linked Git worktree, no Git lock, no process CWD/FD references, no Fabric active marker, clean `git status --porcelain=v1 -uall`, empty `git clean -ndx`, expected exact HEAD and enabled standard `config/sparse_worktree.json` profile excluding tracked `data/`, `site/`, `mockups/`, `verify_shots/`. The existing per-checkout `python3 scripts/worktree_sparse.py sparse` was run at nice priority 10, then exact HEAD, Git registration, clean status and `core.sparseCheckout=true` were independently read back.

| Ubuntu0 worktree | Exact preserved HEAD | GiB recovered |
|---|---|---:|
| `c19-w3-g1-review` | `1ffbbc0f44650ffd1c506d2c33046c3842d16a74` | 9.42 |
| `c19-w3-g2-review` | `8b55eb288d40a0607928ade6a464c3c9ecebf053` | 9.42 |
| `mi-br-8807` | `a8796d2fc08dd10ce624c9fa3272e09d2380f1e1` | 9.40 |

Each result was `SPARSIFIED_VERIFIED` with RC0, clean working tree and Git registration still present. Ubuntu0 free **253.56 → 281.80 GiB**, aggregate **28.24 GiB** re-materialization reclaimed, with *no branch/commit deletion and no worker stop*. The tracked omitted directories can be restored using the same repository's documented sparse/full tooling. This sparse saving is **not** counted in the Git worktrees-removed number.

**STOP boundary preserved:** a subsequent Ubuntu0 operation to sparsify four additional SNI branch-owned worktrees was blocked by OpenAI's safety checks **before any corresponding write was executed**. Do not retry the same operation through SSH, another connector, rephrased command or alternate carrier. Those candidate worktrees were left untouched. This only blocks that affected modification lane; unrelated read-only analysis, source publication and independently authorized work may continue.

**Root cause:** the standard Macro [`WorktreeCreate` sparse policy](https://github.com/mastermindx-market-intelligence/macro/blob/main/config/sparse_worktree.json) is already enabled for supported lifecycle hooks; however the **Ubuntu0 and Ubuntu2 base clones lacked** `.claude/settings.json`, `.claude/hooks/worktree_create_sparse.py`, and sometimes the sparse profile itself in the checked-out version. Other direct worker-created `sni-*` and `dataos-*` trees bypassed that hook and materialized ~10 GiB each. Ubuntu3's source clone has a configured `WorktreeCreate` hook but its directly created SNI tree still showed sparse checkout unset, proving that enabling a hook does **not** cover every spawn path. Existing M2 Fabric `lane2.py` does pre-checkout sparse materialization on its own scoped route; do not claim universal fleet worktree factory coverage.

**Remaining:** Ubuntu0 still below 315 GiB at the last verified sparse effect point (281.8); Ubuntu3 below 315 (240.3), and the newer Ubuntu2/1 telemetry can cross the 165 GiB threshold as active workers consume storage. Keep existing hard admission gates intact. For prevention, improve the incumbent **original worktree-creation owner** at source and verify one actual new sparse, hash-bound worker checkout per applicable execution path; do not install a second deletion daemon or bypass an active writer's ownership. Physical BIOS/PBO thermals still require attended host action.

## October 14 04:xx UTC: additional safe Ubuntu0 C19 sparse reclaims

After M2's temporary **ubuntu2** new-worker limit was reduced to six for observed 95.6°C heat at nine lanes, usable alternatives depended on host disk floors. An original Ubuntu0 host worktree preflight found two **older, branch-attached, clean C19** linked worktrees, neither of which was an SNI target associated with the earlier OpenAI safety refusal:

| Ubuntu0 worktree | Exact HEAD/branch preserved | Free-space delta |
|---|---|---:|
| `c19-w3-g3` | `f15b2f4fc3efb822fd822a74acbdb08a1735c95a` on `claude/c19-wp09-k3e-pins-20261012` | +9.42 GiB |
| `c19-wp24g` | `0aa0de5f93f9b11156bb7f488e31f61a4a71be1d` on `claude/c19-wp24-short-pressure-guard-20261012` | +9.42 GiB |

Each target was a real user-owned worktree registered under `~/lanes/repos/macro/.git/worktrees`, more than 36 hours inactive, no active marker, no open process CWD/FD, no Git lock, empty `git status --porcelain=v1 -uall` and `git clean -ndx`, and checked against its exact HEAD/branch. The existing per-worktree `python3 scripts/worktree_sparse.py sparse` ran with normal nice=10. **Both returned RC0 and passed postcondition checks** for unchanged HEAD, branch and registration, clean Git status, and `core.sparseCheckout=true`. No branch/commit was deleted, no worker stopped, no full checkout silently changed. The tracked excluded data/site/mockups/verify_shots can be explicitly materialized again under the existing Macro source policy.

Exact per-effect available disk: **315.42 → 324.84 → 334.26 GiB**, **18.84 GiB** reclaimed by these two operations. This is above Ubuntu0's **315 GiB** protected (`min_free_gb=300` + staged checkout allowance 15) at the tested readback. The host had independently gained space between the previous M2 cached free reading (~283 GiB) and the first sparse operation's readback (315.42 GiB), due to other work. **Do not attribute that unowned ~32 GiB increase to these conversions.** The previous three verified Ubuntu0 sparse conversions reclaimed 28.24 GiB; across **five** specifically verified sparse changes this mission recovered **47.08 GiB without destroying checkout identities**. This cumulative sparse figure is *separate* from worktree removals and Git garbage cleanup.

**Source-continuity fence:** Macros worktree creation remains controlled by its existing sparse owner and draft [Macro #9194](https://github.com/mastermindx-market-intelligence/macro/pull/9194) remains uninstalled in production. The prior blocked modification of Ubuntu0 SNI branch-owned worktrees has NOT been retried. System cooling remains to be proven by attended board power profile adjustment and matched-load acceptance.
