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
