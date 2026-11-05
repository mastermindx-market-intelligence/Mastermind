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

## Audit return consumed and fenced-example repair qualified

This section supersedes the initial candidate's current qualification/counts, not
its historical test receipts. The original read-only Fabric audit completed rc0
with the exact root/parent and a 7,900-byte retained result, response SHA-256
`da7214641796c31109c994c61f8435a373d29df1dbc6e8e4b5e559df41740674`.
The full retained response was read through the existing result pager. It is a
bounded independent source audit of the protected baseline, not an independent
review or formal GitHub approval of this new implementation.

The audit identified a concrete defect: the existing projector can treat a
marker pair inside a fenced Markdown example as an installed managed block.
Parent independently reproduced this on both the protected projector and the
first additive renderer using a synthetic document, not installed host files.
Eight failing assertions were established by eight new fence scenarios (including
positive controls), then the renderer was repaired to refuse selection inside
backtick/tilde fences, including unclosed fences, short/different closers and
info-text false closers. A real block after a properly closed fence and fenced
content inside a managed body still work. The supplier-owned projector itself
was NOT changed concurrently; its exact finding was surfaced in the original
source-coordination thread for the actual #2064 writer.

Updated native brief adds explicit existing-installer and BOOTSTRAP_KERNEL
pointers while shrinking to **8,101 bytes / 134 lines**, **66.31%** below the
24,048-byte source brief. No automatic imports, extra bootstrap gate or live
instruction edit was added.

Final focused qualification: **102 tests PASS**, zero failures/skips:
47 compaction/source/writer tests, 12 existing projection, 28 discovery audit,
15 audit-check. Original process30093 exited0, 14.64 seconds. **Nine** syntax-valid
destructive mutants were caught, including deletion of the fence guard and
accepting a shorter closing fence. Source bytes remained unchanged during the
campaign. The same **47 tests PASS** with current #2064 supplier at
`698b665957b590b1e8c0062a85f91e80a5674e0f`, installer blob
`a4669c7b32748645ac7a6a5f7c7124964324f46b`; apply() AST is unchanged. This is isolated
composition, not adoption of the supplier's unmerged policy.

| Repaired source | UTF-8 bytes | SHA-256 |
|---|---:|---|
| docs/NATIVE_EXECUTION_BRIEF.md | 8101 | 879076942a3b81bac1a146a0812ce0d4e62ef219021a0bd95dfa785615d2a994 |
| scripts/native_instruction_compaction.py | 9336 | 998d66fa31aaf95ad57f923142828989356615069ec3572a8a118e833913f638 |
| tests/test_native_instruction_compaction.py | 17856 | 3643ee5334a46537af7643a5953856ef3ab708538bad1b0741dd6540e5c12ce7 |

Audit acceptance: the first acceptance call's max_bytes=4096 was smaller than
its 7900-byte result and returned RESULT_TOO_LARGE. Same-owner status was read
back as terminal NOT_ACCEPTED. One bounded payload-size correction on the same
run/root/digest succeeded; canonical readback is ACCEPTED/VALIDATED_OUTCOME,
accepted_by=reviewer. No worker retry, provider change or duplicate operation.
This parent adjudication accepts the scoped audit result only; it does not claim
atomic cryptographic attestation, independent review of the final diff or native
GitHub APPROVED. No watcher was created; the leaf assignment is terminal.

Source release was paused by making #2075 Draft during the real repair, not by
waiting for an invented reviewer. Secretary's existing thread
https://mastermindxgroup.slack.com/archives/C0CBC6AEAQZ/p1793860171608229 has a genuine
PICKUP_ACK for source-only coordination and the repair update; ACK is not START,
a queue receipt or installation. Parent retains source custody. The denied live
host read remains untouched and excluded from that commission. Native installation
and fresh task behavior remain unproved. Mission complete: false.
