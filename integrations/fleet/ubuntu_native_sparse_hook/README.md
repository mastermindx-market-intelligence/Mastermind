# Ubuntu user-level Claude sparse worktree fallback (review candidate)

**State:** SOURCE_READY / LOCAL_REAL_GIT_TESTS_PASS / NOT REVIEWED / NOT INSTALLED.

This is the Linux counterpart to the M2 user-level `WorktreeCreate` fallback. It is
**not** the already-live original Fabric `--new-macro-worktree` minter,
`remote_sub_exec.py`, a provider wrapper, a lifecycle registry, or a GC owner.

## Why it exists

On 2026-10-21, Ubuntu0-3 had 294 registered sparse Macro Fabric worktrees
under `~/lanes/wt`, with real workspace-mint receipts. That paid-Fabric path
works and must not be recreated. Separately, their global Claude native
`~/.claude/settings.json` lacked the M2-style `WorktreeCreate` fallback.
The shared primary Ubuntu1 Macro donor omitted its project-level Claude
and Codex hook directories. Native app sessions starting outside a project
with its own creation hook therefore have a distinct storage-protection gap.

This source is **narrowly for new native Claude worktrees without a
project-owned `WorktreeCreate` hook**. It cannot make raw `git worktree add`,
the Codex internal initial checkout, or unmarked paid Fabric commissions
sparse. Claiming that would be false.

## Proposed contract

- Consume one Claude `WorktreeCreate` JSON event on stdin, with exact
  `name`, `cwd`, and `session_id`. Emit only the created path on stdout.
- If an existing project-level `WorktreeCreate` hook applies, return success
  without minting, preserving the project hook (as on M2).
- Otherwise require Linux, the current OS user's owned, unmodified and
  non-group/world-writable source ancestry under HOME, a valid local commit
  and an owner-controlled sparse profile. No fetch or remote transport.
- Create under `~/.claude/worktrees/mmx-sparse/<repo-key>/<session-key>`.
  Within Git's own worktree registry, atomically mint using
  `git worktree add --no-checkout --lock`, apply cone sparse configuration,
  hydrate, and verify branch, locked identity, HEAD and clean status.
- Use `config/sparse_worktree.json` when present and enabled, excluding
  its named tracked heavy directories. Without that profile, hydrate every
  tracked top-level directory: this remains a sparse worktree mechanically
  but **does not promise storage savings for that repository**.
- Refuse unqualified input, source, branch, disk floor (20 GiB), profile and
  destination. An exact matching locked existing session can be reused.
  **Never remove, reset, force-prune, convert or silently adopt an incumbent.**
- If a failure follows `worktree add`, preserve the existing branch,
  worktree and lock for original-owner reconciliation. No retry/failover.

## Tests performed

```sh
python3 -m unittest -q integrations/fleet/ubuntu_native_sparse_hook/test_ubuntu_claude_worktree.py
```

Nine real-Git fixture cases passed in an isolated temporary Linux HOME.
Coverage includes sparse-first omission, linked worktree identity, exact
resume, project-hook deferral, missing identity, original source dirt,
disabled policy, unprofiled repository preservation, foreign path
preservation, and group-writable source refusal. No live worker, source
donor, provider, GitHub branch other than this review carrier, or
Ubuntu system configuration was modified by the tests.

## Qualification and release gates

This automatic native hook invokes Git against a user's local repository.
An independent security review is owed for Git local configuration,
filters, malicious submodules, ownership and symlink races, repeated
events, branch/lock effect uncertainty, and parity with current Claude
Code WorktreeCreate semantics. The Mac hook's working result is not a
Linux acceptance receipt. Passing fixtures alone is **not** permission to
install it.

After the source review and protected checks, use one original-owner
Ubuntu host installation, preserving existing `~/.claude/settings.json`
exact bytes and unrelated settings. First validate on a disposable Git
fixture, then bind a native session on one host, and verify real event,
single creation, sparse omissions, resumed identity and no second
project-hook mint. Only then extend to the other eligible Ubuntu hosts.
Do not change the selected Fabric generation, replace the legacy M2
`remote_sub.sh`, normalize Ubuntu1's dirty shared donor, or try to
enroll offline Ubuntu4 as a side effect of this work.

The requested end-to-end fleet outcome remains separate:
original paid Fabric sparse creation for Ubuntu0-3 is proven on observed
real runs; Ubuntu4 connectivity/admission and optional global native
Claude/Codex parity still need their own qualified delivery/proof.
