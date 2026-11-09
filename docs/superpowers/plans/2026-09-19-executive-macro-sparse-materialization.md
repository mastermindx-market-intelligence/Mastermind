# Executive Macro Sparse Materialization Implementation Plan

> **For Sol:** Execute inline under test-driven-development and systematic-debugging. Preserve the incumbent PR #834 carrier.

**Goal:** Make the real installed Executive boot-packet collector complete within its single 28-second budget without weakening repository, mutation, topology, or output-integrity gates.

**Spec:** `docs/EXECUTIVE_MCP.md` (trusted grounding and installed read boundaries), plus PR #834's exact-head review contract.

**Architecture:** Keep the canonical full clean-snapshot proof before the child and the mutation-generation proof after it. Replace the blind full-worktree clone with a dependency-complete sparse materialization: the exact Agent OS brief byte-read closure plus every existing Macro path whose existence is consulted by `artifacts` / `owns_paths`. Copy only immutable Git object/ref metadata required by `rev-parse`, `log`, and `worktree list`; omit mutable index, hooks, logs, locks, and transport state. Run independent Mastermind and Macro pre/post observations in parallel under the same cumulative deadline. Synthetic fixtures retain their existing sequential path.

**Global constraints**

- Owned paths remain `integrations/executive_mcp/installed.py`, `tests/test_executive_installed_readers.py`, and `tests/test_executive_installed_snapshot_hardening.py`, plus this plan.
- No new OS, database, queue, provider controller, identity registry, dispatcher, PR, or carrier.
- No ambient PyYAML dependency in `installed.py`; parse the closed frontmatter subset fail-closed with the standard library.
- The materialized JSON must be semantically identical to the canonical checkout for the same `--now` and sibling bindings.
- One cumulative deadline governs pre-proof, materialization, child, post-proof, and cleanup.
- Existing mutate/restore, missing object, unsafe Git topology, no-lazy-fetch, packet-root/SHA, and output-limit controls stay green.

## Task 1: Dependency-complete sparse Macro snapshot

**Files:**
- Modify: `integrations/executive_mcp/installed.py`
- Test: `tests/test_executive_installed_snapshot_hardening.py`
- Test: `tests/test_executive_installed_readers.py`

**Produces:** a verified materialization plan containing exact tracked leaves and required directories, a minimal direct `.git` read database, and sparse-aware snapshot verification.

1. Add failing tests proving:
   - fixed brief bytes and direct record files are present;
   - existing Macro artifact files and glob-base directories preserve `Path.exists()` semantics;
   - missing and non-Macro paths are not invented;
   - unsupported path-list YAML or symlink probes fail closed;
   - `.git/index`, hooks, logs, locks, and transport-only files are not copied;
   - `git rev-parse`, `git log -- <record>`, and `git worktree list` still work;
   - sparse verification rejects omitted required leaves, extra leaves, changed bytes, and mutation/restore.
2. Run the new tests and observe RED against the full-tree materializer.
3. Implement the smallest strict frontmatter-list parser, tracked-tree closure derivation, allowlisted Git database clone, sparse materializer, and sparse-aware verifier.
4. Run the new tests GREEN.
5. Run all existing materialization/snapshot hardening tests.

**Expected:** exact dependency semantics with no full-worktree clone and no ambient YAML import.

## Task 2: Parallel full observations under one deadline

**Files:**
- Modify: `integrations/executive_mcp/installed.py`
- Test: `tests/test_executive_installed_snapshot_hardening.py`
- Test: `tests/test_executive_installed_readers.py`

**Consumes:** Task 1's materialization plan and sparse observation.

1. Add failing tests proving:
   - real Mastermind and Macro pre-observations overlap;
   - real post-generation observations overlap;
   - the child starts only after both pre-observations and sparse verification succeed;
   - any parallel proof failure refuses the packet;
   - timeout is cumulative and futures cannot extend it;
   - synthetic fixtures keep deterministic sequential call counts.
2. Run the new tests and observe RED.
3. Implement bounded pair observation with `ThreadPoolExecutor(max_workers=2)` only for direct-Git roots; resolve both results before progressing and translate all failures to the existing fail-closed errors.
4. Pass the remaining deadline into sparse materialization and child exactly once; preserve the inner settlement margin.
5. Run the new tests GREEN, then the full installed-reader/hardening battery.

**Expected:** no proof weakening, one Macro history walk, and elapsed wall time governed by the slower repository in each pair rather than their sum.

## Task 3: Exact production-scale proof and carrier update

1. Run formatting/static checks applicable to the owned files.
2. Run:
   - `python3 -m pytest -q tests/test_executive_installed_readers.py tests/test_executive_installed_snapshot_hardening.py`
   - the incumbent owning battery recorded by the branch if broader.
3. Run one exact installed-host collector against Macro `54b2fc0181635aa78967e17978a10210fd0544ed` with the sealed CF1 interpreter and a 28-second cumulative budget.
4. Verify packet root/SHA projection, non-fixture mode, semantic equality discriminator, no mutation, and elapsed time below the contract.
5. Commit on the incumbent #834 branch, push the exact descendant, and inspect exact-head CI/review state. Do not merge without independent exact-head acceptance.

## Review focus

- Parser drift from Agent OS `_home_repo` / `_resolve_path` semantics.
- Symlink or path traversal escaping the canonical Macro root.
- A copied Git file that re-enables hooks, alternates, helpers, lazy fetch, or mutable index influence.
- Races hidden by parallel observation or exceptions lost in futures.
- Sparse verification accepting a path/type/byte set different from the derived closure.
- Deadline accounting accidentally resetting at a phase boundary.
