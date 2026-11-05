# Native instruction compaction: source qualification

Parent: Mastermind #917; operation native-instruction-compaction-20261105-web-001.
Protected source pin: cb390bfc5a4b85a59a1005bfd3824305a5a4bfee.
Skillpack mastermind.sol_skillpack.v1 1.0.1 / bootstrap major 1.
Plan extension was published and read back at 088cd26ca9484b9f9569def90d18a5a9467ef288.

## Implemented and verified

- Additive compact native profile, pure renderer and advisory diagnostics. No default
  installer, root AGENTS.md/CLAUDE.md, review policy or runtime path was changed.
  #2064 retains those active supplier paths. The existing projector is the sole writer.
- 39 new compaction/source/real-writer integration tests PASS on the actual isolated
  M2 source workspace. 12 existing projection tests, 28 discovery-audit tests and
  15 audit-check tests PASS: **94 focused tests**, zero failures or skips.
  Commands: python3 -B -m unittest discover -s tests -p NAME -q, with
  NAME=test_native_instruction_compaction.py, test_execution_brief_projection.py,
  test_execution_instruction_audit.py, test_instruction_audit_check.py.
  Original Desktop Commander test process: PID 91008, terminal exit 0.
- Isolated real-source roundtrip: wrapped the pinned 24,048-byte canonical account
  brief plus a host-specific sentinel, rendered the 8,162-byte native brief, and
  used the existing project_execution_brief.apply writer. Exact readback, private
  backup, sentinel preservation and exact-hash rollback all passed. No installed
  native instruction file was changed. Source brief reduction: **66.06%**; not
  a total-context or speed measurement.
- Seven syntax-valid destructive mutants were all caught: whole-file preimage,
  source-brief identity, managed-block identity, retired-block identity, protected
  marker refusal, duplicate-main refusal and nested-comment refusal. All mutations
  ran in isolated temporary source copies. Original source remained unchanged.
- git diff --check passed. Hosted current-head CI and protected release are separate.

## Exact source identities at initial qualification

| Source | UTF-8 bytes | SHA-256 |
|---|---:|---|
| docs/NATIVE_EXECUTION_BRIEF.md | 8162 | ba38705449585c608c7a03c733522935bc523608555f7eb26be0e0412329d0fd |
| scripts/native_instruction_compaction.py | 8393 | 3b991192b4b0b5b7bbbc4df45b01c2729f547586dacd0f18db0831325e1698bd |
| tests/test_native_instruction_compaction.py | 15859 | f656cde244dd09e817d13cd4c5905fe1f19cd3c98e40800d710f1ce2983f03c6 |
| Same-pin full account brief | 24048 | a6d9cf8950523c01fce9623418b95e414180006cf4f9d2a388f192d8cc892004 |

## Boundaries that remain real

The new source is an opt-in native rendering profile, not an accepted new policy
or installed fleet release. It reuses mandatory owner procedures and does not
change the signed automatic host, native GitHub approval, CI or release guards.
Normal default-installer integration remains a supplier-owned follow-on; this
slice deliberately avoids the active #2064 source-writer collision.

One targeted read of five historical blocks in the M2 global Codex instruction
file was explicitly blocked by OpenAI safety checks. That exact read was not
retried, shortened, encoded or delegated through another carrier. No subsequent
read or mutation of those installed instruction blocks was performed. The cause
was not diagnosed as a transient error. This holds dependent on-host retirement;
it does not invalidate independent repository-source work or the isolated tests.
No live installation, native trust change, source merge, provider launch or fresh
Codex/Claude instruction-loading/behavior result is claimed.

The separately admitted read-only audit request uses existing Fabric run
native-instruction-compaction-audit-20261105-01, root/parent
native-instruction-compaction-20261105-web-001, controller PID 74332. At the last
observation its result/root lineage was still unverified and no result was
available. It was not duplicated or accepted. Source tests are self-qualification,
not a fictional independent review. Reconcile that original return separately.

## Acceptance still owed

Protected source release, normal consumer selection/default integration without
supplier collision, permitted exact-preimage host installation, and fresh native
behavior cases in docs/runbooks/native-instruction-compaction.md. Keep installed,
loaded and behavior-proven evidence separate. No automatic/background completion
is implied by this record. Preserve existing native host controls and the original
unknown/refused effects. Mission complete: false.
