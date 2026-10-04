# Claude Capability Hardening — implementation design and execution contract

**Design revision: 2026-10-04 / partial review candidate. Runtime activation: none.**

H1–H6 detailed packets and the cross-packet process are prepared. The attempted detailed H7
browser-packet write was blocked before dispatch and was not retried or rerouted; its original
handoff remains the acceptance basis. The design is therefore not claimed completely persisted.
The source register retains 36 verified entries; a later two-entry extension was also blocked
before dispatch. These are bounded tool-action gaps, not evidence of a platform-wide outage.

This package deepens the Chairman's seven original handoffs without replacing their outcomes.
It belongs to Mastermind #1236 and the existing candidate PR #1240, operation
`claude-capability-hardening-20261004-c4-001`, under `WS:EXECUTIVE-CAPACITY-FABRIC`.
The original [handoffs](../CLAUDE_CAPABILITY_HARDENING_BUILD_HANDOFFS_2026-10-04.md)
remain byte-exact. The containing Git commit pins this design; it is not protected runtime law.

## 1. What is pinned, and what is not

This package pins implementation decisions, current-owner seams, sequencing, failure handling,
acceptance obligations and release process. It distinguishes:

- **Source observation:** verified code at protected Mastermind
  `17b9fa1363db6071d338be3373a4fdb11fc0076d`, with immutable anchors in
  [SOURCE_REGISTER.md](SOURCE_REGISTER.md). Relevant source and loaded procedures are unchanged
  from the first slice's protected `521720b09be2921e996d9396b522b1c4ca62041c`.
- **Selected design:** this session's proposed implementation beneath current law. It can guide
  review and bounded implementation; it does not change current admission, permissions or custody.
- **Open qualification:** an exact native version, installed owner, current source writer or
  permission fact is not established by the source. The relevant action remains gated.
- **Executed proof:** only the actual tests/results recorded in VALIDATION.md. A planned
  acceptance case is not a test that passed or a native capability that exists.

No proprietary system is copied. No new lifecycle, registry, queue, memory plane, credential
store, retry owner or watcher daemon is proposed. New contract versions, when needed, belong to
existing owners and require their normal review; document IDs are traceability only.

## 2. Material corrections to the initiation plan

**F1 — A JSON profile is insufficient.** The current registry rejects every enabled
`claude-agent-sdk` profile [S01]. Its native projection, native policy observer and supervisor
also restrict the lane to Read/Glob/Grep with no MCP/skills/resources [S02–S04]. H1 therefore
requires a coordinated owner-qualified admission/observation change, not removal of one refusal.

**F2 — Current principal submission is not governed fanout.** Six COO tools exist [S06].
`submit_principal_intent` derives a bounded job through the principal schema. The v2 orchestration
root constructor is a different branch, and CooCycle requires aggregation-root provenance
[S08–S14]. Two successful principal submissions do not satisfy H4's parent/child requirement.

**F3 — The proof graph must fit its complete reservation.** Current policy reserves
`1 + sum(review ? (1 + 2) * (1 + 2) : 1)` descendants with a maximum of 16 [S15].
Two independently reviewed work steps reserve 19 and are rejected. A reviewed implementation
step plus a genuinely read-only evidence step reserves 11. Select that latter proof graph;
never mark a code-writing step unreviewed merely to fit the cap.

**F4 — Worker dialogue is not principal ruling.** The present Company MCP exposes bound-thread
read, ACK, progress, blocker, decision request and result tools [S18]. Its facade and the neutral
V2 contract also restrict COO actors to worker-style messages. H6 therefore needs a reviewed
commission-scoped semantic/binding extension as well as a principal-facing tool; merely adding a
CONTINUE/STOP method would still fail the current contract. See H6 for the exact additional
source locations. Do not globally promote COO actors to CEO or use authoritative-looking Slack prose.

**F5 — CI observation has a design, not an established live handle in this audit.** Delivery law
requires one exact-candidate observer [S26–S27]. The bounded source census did not resolve a
production-proven observer registration/return API. H5 begins by resolving that owner contract.
Do not describe an unlocated component as either proven live or definitively absent everywhere.

**F6 — Browser configuration is not native browser admission.** Existing browser resources and
receipts are substantial, but the observed supervisor's browser lane is Codex-specific and the
Claude lane excludes resources [S04, S23–S25]. H7 must join that existing resource to a separately
qualified Claude path, preserving the restricted lane.

**F7 — Provider isolation has version-sensitive edges.** Official provider documentation distinguishes
tool visibility from auto-approval, says strict MCP configuration excludes plugin-provided servers,
and documents a historical Python SDK empty-setting-source defect. These are qualification inputs,
not evidence of the installed version. See [EXTERNAL_NOTES.md](EXTERNAL_NOTES.md).

## 3. Selected architecture

`accepted mission + exact principal binding`
→ existing mandate/authority facts
→ existing capability/package registry
→ provider-specific projection
→ native observed policy/catalog + existing resource/source grants
→ existing Executive/Dialogue/Source/Browser owners
→ canonical receipts and exact-result consumption.

The rich principal is an orchestrator, not an unrestricted desktop user. Its authority is the
intersection of mission delegation, principal policy, admitted capability generation, resource
permission, source custody and current effect gates. A plugin cannot make that intersection larger.

Use the existing Agent SDK adapter as the first *proposed* qualified rich execution surface,
because the current source already models `claude-agent-sdk` in the native adapter/supervisor.
This is an implementation target, not a provider/account placement decision or launch permission.
CLI configuration parity continues independently. Desktop, inline helper and bundled-plugin MCP
parity remain separately qualified; one successful SDK run never certifies them.

Start with one narrowly reviewed principal profile generation; add capability families by explicit
new reviewed generations. Do not ship seven broadly enabled profiles or hot-add newly discovered
tools. Read-only context first, then bounded COO submission, then source/dialogue/delegation,
then browser and separately scoped Studio/Paper access. Each increment preserves prior negative
controls and records exact removed as well as added capabilities.

## 4. Detailed packets

| Packet | Implementation contract | First decisive gate |
| --- | --- | --- |
| H1 | [Rich principal](H1_RICH_PRINCIPAL.md) | Trusted native policy observation and exact-profile admission across registry, adapter and supervisor. |
| H2 | [Projection parity](H2_PROJECTION_PARITY.md) | Distinguish expected, projected, shipped and observed generations; never promote static H2-A into launch authority. |
| H3 | [COO plugin](H3_COO_PLUGIN.md) | Six existing role-correct tools, closed principal scopes, exact request/status reconciliation. |
| H4 | [Fabric delegation](H4_FABRIC.md) | Existing orchestration-root admission becomes lawfully consumable by this principal without impersonating CEO. |
| H5 | [CI continuation](H5_CI_CONTINUATION.md) | Resolve one existing observer owner/API and exact native return target. |
| H6 | [Agent OS and dialogue](H6_CONTEXT_DIALOGUE.md) | Principal ruling and context writes through existing owners, not worker messages or a new inbox. |
| H7 | [Original browser handoff](../CLAUDE_CAPABILITY_HARDENING_BUILD_HANDOFFS_2026-10-04.md) — detailed packet write held | Exact Claude profile/resource generation, origin guard and cleanup proof; no replacement artifact is claimed. |

Read [SHARED_CONTRACTS.md](SHARED_CONTRACTS.md) before packet implementation.
[EXECUTION_AND_RELEASE.md](EXECUTION_AND_RELEASE.md) defines the ordered work packages and review
barriers. [ACCEPTANCE_CASES.json](ACCEPTANCE_CASES.json) is a test-design inventory, not a live test
registry or execution scheduler. IDs are local to this package.

## 5. What builders must not assume

There is no source-only shortcut to native enforcement. Current toolkit names do not establish
installed tools. CLI allowed-tools flags are not a security boundary. Root-sealed identity does
not establish exact conversation isolation. An installed package does not prove it is selected.
A status response's `mode: readonly` describes that read; it does not characterize every sibling
route. A successful submission receipt does not prove dispatch, start, completion or acceptance.

Do not add raw provider, account, model, host, realm, branch, worktree, actor or seat selectors to
COO public requests. Do not introduce an ambient shell to bypass a missing source/binding/API
capability. Do not borrow the Chairman's browser or credential-bearing home. A failed permission
check is not an invitation to try another carrier.

No shared runtime/profile/plugin source path is assigned away from its incumbent by this package.
Earlier #676/#955/#600 bodies/comments retrieval was denied before dispatch and was not replayed.
Protected-source analysis is independent; current incumbent custody remains a separate prerequisite
for edits to their lanes. #962/#992/#919/#660 remain reuse pointers, not live execution receipts.

## 6. Concrete resolution duties

The assigned integration role retains responsibility for resolving these; the Chairman does not
need to choose worker accounts or answer routine implementation questions.

1. **H1 admission owner:** qualify an exact native rich-profile observer and provider generation;
   keep all current denied profiles denied until that accepted dependency exists.
2. **H4 admission owner:** approve the versioned principal-to-existing-orchestration-root contract;
   do not overload today's bounded-job receipt with fanout semantics.
3. **H5 process/CI owner:** identify the existing observer registration, reconciliation and return
   handle; if only a design exists, implement the bounded adapter inside that owner, not a daemon.
4. **H6 dialogue owner:** bind a principal's allowed ruling types and exact commission carrier;
   source/Agent OS writes remain governed repository changes until an accepted equivalent exists.
5. **Installation/enrollment owner:** perform reserved authentication or administrative ceremonies
   only when exact reviewed artifacts and preflight are ready. No ceremony is requested now.

These are named engineering/qualification gates, not unspecified future work. Each packet states
the evidence that closes its gate and what may proceed independently.

## 7. Definition of complete

Design completeness means every original handoff has an owner map, exact current seam, selected
implementation, compatibility handling, failure matrix, proof plan and release boundary, with
unverified facts visible. Production completeness is stricter: all seven original DONE WHEN clauses
must hold on real admitted paths, at exact accepted revisions, with independent review and no
unresolved effect or cleanup obligation. The latter remains unproven.
