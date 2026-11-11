# Ubuntu 2 disk-reserve recovery — October 13, 2026

**Status: verified local cleanup on Ubuntu 2; NOT a blanket worktree-GC policy or authorization for unattended deletion.**

The existing M2 host picker refused placement on all four Ubuntu hosts due to protected disk reserve. Ubuntu 2 was most urgent: `/dev/nvme0n1p3` ext4 root had 2.54 GiB available (892 GiB volume, >99% utilized by `df`); inodes remained ~18% utilized. A read-only `du` census found `/home/ubuntu2/lanes/wt` ~640 GiB, with 115 worktree directories, 97 worktrees registered against `~/lanes/repos/macro`. Individual macro worktrees generally duplicated 10.17–10.28 GiB of `data/`, `mockups/`, `site/` and other checkout content. Other host-user caches were much smaller. **No worktree was older than 14 days; age alone was not accepted as deletion proof.**

## Safeguards actually required and checked for each removed checkout

1. Exact canonical path under `/home/ubuntu2/lanes/wt`, normal directory, owned by host user, no symlink. Git dir resolves under `/home/ubuntu2/lanes/repos/macro/.git/worktrees`; no Git worktree lock.
2. Detached `HEAD` with at least one matching `origin/*` remote-tracking ref containing that exact HEAD (commit is not an unpublished detached-only object). Git tracked and all untracked paths clean with `git status --porcelain=v1 -uall`, and `git clean -ndx` preview empty (no ignored files needing preservation).
3. No `~/lanes/ext/active/<id>` marker; no `/proc` CWD, root or open file descriptors referring to the checkout or its Git metadata. No live target process in the bounded census. The M2 Fabric controller `fabric_task status` had no corresponding exact run IDs; absence alone was **not** treated as runtime-terminal proof.
4. Removal only by `git -C /home/ubuntu2/lanes/repos/macro worktree remove -- <absolute path>` without `--force`; no `rm -rf` fallback, no other directory sweep. After each operation, return code 0, target path absence, Git worktree metadata absence, and OS filesystem free-space readback were all checked. Any failed/ambiguous operation would have stopped that batch, not replayed it.

## Exact removed checkouts

| Group | Removed working tree labels | Verified commit HEAD |
|---|---|---|
| Wave 3H | `c19-w3-h5-wp23-census`; `c19-w3-h8-wp26-census` | `5267c66846e7733bc1eb30edc1524daff51598ca` |
| Wave 4I | `c19-w4-i2-wp18-census`; `c19-w4-i4-wp20-census`; `c19-w4-i10-wp32-census` | `94c53929fb5e4e0fc0dd15e5a0ce44e2384ca130` |
| Wave 4I design | `c19-w4-i14-wp25-design-input` | `278bafeb8990b6081c16c245b1c6f34872bf6c7d` |
| Wave 5J | `c19-w5-j1-wp15-census`; `c19-w5-j2-wp15-design-input`; `c19-w5-j3-wp24-census`; `c19-w5-j4-wp24-design-input` | `7e8095168735d10a8010e0e5228e061cfacdb960` |
| Wave 5J audit | `c19-w5-j5-wp05-audit`; `c19-w5-j6-wp06-audit` | `fbcc00f0129511c1a1cc60589699807f7d14655d` |
| Wave 5S | `c19-w5s-wp14-census-20261012`; `c19-w5s-wp20-census-20261012`; `c19-w5s-wp23-census-20261012` | `f399f19b4fb8f51e8a382e4f925116b9df5cdc61` |

**Verified disk delta:** 2.54 GiB → 22.90 GiB after first two; 22.89 GiB → 155.24 GiB during the next 13. The combined 15-checkout reclamation was ~152.7 GiB. The 13-checkout batch printed all `REMOVED_BY_GIT` receipts and `GC_BATCH_TOTAL 13 of 13 delta_gib 132.35 free_after_gib 155.24`; no batch failure or uncertain effect.

**Preserved:** live or recently active Ubuntu2 worker worktrees, dirty/ignored/unpublished checkouts, the older `mo-ext-fix-orchf-v` checkout (16,646 untracked files, remote HEAD absent), the 11+ GiB `sni-e-review-20261011` and other non-whitelisted directories; all existing Git branches, remote refs, worker leases, host processes and source repositories. Reconstruction, if legitimately needed, is via the original qualified repository and preserved remote commit; removed checkout paths are **not** left as live usable directories.

## Remaining capacity defense

This was necessary emergency mitigation, not a permanent fix. New macro worktrees often occupy >10 GiB; a simple `disk_free >= min_free_gb` check with stale telemetry can launch another checkout immediately before dropping below reserve. The incumbent Fabric host-placement and physical admission owners should conservatively account for staged checkout footprint before allocating another workspace, without lowering protected disk floors or introducing an independent cleanup/queue/control service. Automatic deletion requires stronger owner/terminal-effect evidence than the above narrowly verified manual list.

Original thermal user outcome still needs OS/BIOS cooling proof, and the earlier Ubuntu 2 `powerprofilesctl set balanced` access denial remains binding. No elevated-privilege retry was performed.
