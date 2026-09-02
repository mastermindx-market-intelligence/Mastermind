# Sol Capability Fabric Package Generation — Final Convergence Index

**Date:** 2026-09-01  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Operation:** `mastermind-sol-capability-fabric-package-generation-f0-20260901-sol-001`  
**Carrier:** Mastermind PR #317 / `sol/scf-package-generation-f0-20260901`  
**Protected source and Skillpack basis:** `187490f3d5676adf7a249d69afacedd00b3efcec`, `mastermind.sol_skillpack.v1` v1.0.1, bootstrap major 1  
**State:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / FINAL SOURCE-LAW INDEX`

This is the mandatory first read for the SCF capability-package and CAP-S1 sequence. It creates no new
owner, lifecycle, registry or implementation authority. It makes the unmerged source-law carrier
coherent after adversarial review found and repaired multiple defects in the first draft.

A fresh session must read the records in the exact precedence order below. Earlier files remain useful
for research detail and audit history, but a superseded clause is not an alternate implementation
choice.

---

## 1. Controlling precedence

Highest specificity first:

1. `docs/superpowers/plans/2026-09-01-sol-capability-fabric-package-generation-convergence-index.md`
2. `docs/superpowers/specs/2026-09-01-sol-capability-fabric-cap-s1-protocol-attestation-amendment.md`
3. `docs/superpowers/specs/2026-09-01-sol-capability-fabric-cap-s1-vertical-amendment.md`
4. `docs/superpowers/specs/2026-09-01-sol-capability-fabric-package-identity-amendment.md`
5. `docs/superpowers/specs/2026-09-01-sol-capability-fabric-package-content-digest-correction.md`
6. `docs/superpowers/specs/2026-09-01-sol-capability-fabric-package-generation-design.md`
7. `docs/superpowers/plans/2026-09-01-sol-capability-fabric-package-generation.md`
8. protected AOC-F0 records at merge `187490f3d5676adf7a249d69afacedd00b3efcec`
9. protected SCF F0 and BSC-P1 source records named by those documents.

Current protected Skillpack and universal source laws outrank this list. Current Chairman intent,
canonical GitHub/runtime facts and action-time collision state still must be re-read before any
modification.

---

## 2. Final machine-readable ruling

<!-- SCF_PKG_FINAL_RULING_BEGIN -->
```json
{
  "records_wave": "SCF-PKG0",
  "records_state_after_merge": "SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / PROTECTED",
  "first_implementation_wave": "CAP-S1",
  "standalone_parser_release_allowed": false,
  "implementation_pr_count": 1,
  "default_policy_schema_during_canary": "mastermind.executive_agent_capabilities/v3",
  "canary_policy_schema": "mastermind.executive_agent_capabilities/v4",
  "source_package_namespace": "capability_packages",
  "runtime_plugin_namespace_state": "reserved-empty",
  "raw_profile_skill_identity_field": "skill_capabilities",
  "resolved_profile_runtime_name_field": "skills",
  "package_content_digest": "a9781411d2642569f8b56e33bd0e0d9808a69176ccaced86642cd23948a71306",
  "digest_graph": "acyclic",
  "provider": "codex-app-server",
  "provider_process_required": true,
  "real_model_turn_required": true,
  "provider_neutral_materializer_required": false,
  "provider_neutral_materializer_owner": "HF1",
  "source_origin_modes": [
    "INSTALLED_RELEASE",
    "VERIFIED_EPHEMERAL_GIT_ARCHIVE"
  ],
  "provider_visible_root_kind": "ATTEMPT_LOCAL_VERIFIED_PROJECTION",
  "canonical_v4_canary_fixture": "scripts/ohf/fixtures/executive_agent_capabilities_v4_mastermind_operator.json",
  "required_skill_names": [
    "escalate-decision",
    "finish-operation",
    "receive-commission",
    "return-progress"
  ],
  "checked_in_default_policy_migration_wave": "CAP-PROMOTE1",
  "general_route_added_in_cap_s1": false,
  "production_armed_in_cap_s1": false
}
```
<!-- SCF_PKG_FINAL_RULING_END -->

---

## 3. Supersession ledger

| Earlier clause or ambiguity | Final ruling |
|---|---|
| Package-content digest `a82a274a...` | Wrong. Use `a9781411d2642569f8b56e33bd0e0d9808a69176ccaced86642cd23948a71306`. |
| Package generation and Skill grant mutually bind one another | Rejected circular graph. Skill grants bind immutable `package_source_digest`; package generation then binds exact Skill grant digests. |
| Root `plugins` stores source-package generations | Rejected. V4 root `capability_packages` stores source generations. Root/profile `plugins={}` remains reserved for unavailable installed/runtime plugin authority. |
| Raw V4 `profiles.<id>.skills` stores exact capability IDs | Rejected. Raw exact IDs use `skill_capabilities`; resolved Python `profile.skills` remains runtime-name compatibility view. |
| `EffectiveSkillGrant.package_grant_digest` | Superseded by `package_source_digest`; complete generation identity is `package_generation_digest`. |
| `SCF-PKG1` may merge as a parser-only PR | Rejected. It is an internal phase inside one CAP-S1 implementation PR. |
| CAP-S1 later supplies the consumer after a parser merge | Rejected. CAP-S1 is the first implementation carrier and includes source, registry, comparator, Codex consumer, real model proof and cleanup. |
| CAP-S1 migrates checked-in default policy to V4 | Rejected. CAP-S1 uses one immutable explicit V4 canary policy while the default remains V3. Promotion belongs to CAP-PROMOTE1. |
| SCF-PKG1/CAP-S1 edits no provider/OHF code | Rejected for the final vertical. CAP-S1 may edit the bounded comparator, Codex adapter and OHF protocol/canary seams listed below. Default routes, autonomy bindings and production worker composition remain no-edit. |
| Canonical fixture under `tests/fixtures/...` | Superseded. Use exactly `scripts/ohf/fixtures/executive_agent_capabilities_v4_mastermind_operator.json`; tests consume the same fixture. No duplicate policy fixture. |
| Provider consumes an installed release/archive root directly | Incomplete. Source **origin** is exact release/archive; provider sees one byte-identical attempt-local verified projection so the shared relative reference remains readable inside the synthetic workspace. |
| Attempt-local projection is a provider-neutral materializer | False. It is one Codex-only disposable falsifier and creates no durable install/materialization API. HF1 retains provider-neutral ownership. |
| `skills/list` must always return exact path | Not a stable assumption. Use Mode A when the pinned schema/runtime provides path; otherwise Mode B uses fresh-process causal isolation plus an exact path-bearing `skill` input. Neither available means refusal. |
| Fake App Server `path` proves production protocol | False. Exact pinned binary schema + real probe govern; fake server is a test double. |
| `$name` alone proves source identity | False. Terminal proof requires the exact path-bearing Skill item; `$name` is only the documented invocation marker. |
| Read-only canary may use `lab_allow_unclassified_readonly` | Rejected. CAP-S1 uses existing fail-closed unclassified policy and requires an empty baseline. |
| Source verifier needs only file-level final `fstat` | Incomplete. It also needs terminal complete-tree recensus and retained-directory identity revalidation. |
| Valid JSON may contain duplicate object keys | Rejected. Duplicate keys at every policy depth refuse; valid V3 normalized digests remain exact. |

No row above changes an existing canonical owner. It only resolves contradictions inside this unmerged
records carrier.

---

## 4. Final source → projection → provider chain

The exact data path is:

<!-- SCF_PKG_SOURCE_CHAIN_BEGIN -->
```text
protected BSC-P1 package generation
-> exact source origin (installed release OR verified ephemeral Git archive)
-> descriptor-relative source verification
-> byte-identical attempt-local package projection inside synthetic workspace
-> projection verification + receipt
-> extra root = <projection>/skills
-> exact path-bearing Skill input = <projection>/skills/<name>/SKILL.md
-> provider observation + causal baseline/add/clear proof
-> composite ObservedCapabilityIdentity
-> Executive/OHF comparison
-> bounded real model behavior
-> process/artifact/projection cleanup
```
<!-- SCF_PKG_SOURCE_CHAIN_END -->

The attempt-local projection contains all seven package files, not only four entrypoints. This keeps
`../../references/dialogue-boundary.md` available relative to every `SKILL.md`. It is made read-only to
the canary where platform primitives permit; otherwise its complete tree and identities are checked
before and after every turn and any movement invalidates the canary.

The projection receipt binds:

```text
origin mode and exact root identity
repository + source commit + source tree
package capability/generation/source/generation digests
origin complete file rows
projection lexical/resolved roots and directory identities
projection complete file rows
origin-to-projection one-to-one path/byte/mode equality
created-at monotonic process-local timestamp
owning canary operation/process generation
cleanup state
```

It is an artifact owned by the canary, not a durable package/install record.

---

## 5. Final CAP-S1 scope

A current-source collision census may narrow implementation detail, but the intended one-carrier path
set is:

### Production/library paths

```text
control_plane/executive_capability_packages.py                     CREATE
control_plane/executive_agent_capabilities.py                      MODIFY
control_plane/operator_harness_contract.py                         MODIFY
control_plane/codex_operator_adapter.py                            MODIFY
scripts/ohf/protocol.py                                            MODIFY
scripts/ohf/capability_skill_projection.py                         CREATE
scripts/ohf/cap_s1_mastermind_operator_canary.py                   CREATE
scripts/ohf/fixtures/executive_agent_capabilities_v4_mastermind_operator.json CREATE
scripts/ohf/fake_app_server.py                                     MODIFY
```

### Test paths

```text
tests/test_executive_capability_packages.py                        CREATE
tests/test_executive_agent_capabilities.py                         MODIFY
tests/test_executive_agent_capabilities_v4.py                      CREATE
tests/test_ohf_p1a_operator_harness_contract.py                    MODIFY
tests/test_codex_operator_adapter.py                               MODIFY
tests/test_ohf_protocol_fidelity.py                                MODIFY
tests/test_cap_s1_mastermind_operator_canary.py                    CREATE
```

### Implementation plan / proof record

```text
docs/superpowers/plans/2026-09-01-sol-capability-fabric-cap-s1.md   CREATE
research/sol_capability_fabric/CAP_S1_EXACT_CODEX_CANARY_2026-09-01.md CREATE only when real proof exists
```

This is a bounded expected set, not permission to silently add paths. Before the first edit, the worker
must re-pin protected source, inventory active writers/open PRs for all expected paths and return a
`SCOPE_MAP / DECISION_REQUEST` before adding an unlisted production/authority path. Test/support paths
that are direct one-to-one companions may be proposed in that same scope map.

### Protected no-edit paths

```text
config/executive_agent_capabilities.json
config/executive_worker_routes.json
control_plane/executive_autonomy.py
scripts/executive_os_phase1c_worker.py
ops/executive_os/install.sh
plugins/mastermind-operator/**
all RemoteCodexOperatorAdapter/common worker-wire files
all Browser, Business, PPF, Capacity, MH1, Agent OS and deployment paths
```

If the closed Codex structured input cannot be implemented without changing common remote wire or
production worker composition, return `CAP_S1_STRUCTURED_INPUT_SCOPE_COLLISION` before editing those
paths.

---

## 6. Final implementation order inside the single CAP-S1 carrier

Internal phases do not create separate acceptance boundaries:

1. **Path/owner/collision freeze.** Reconcile current protected Mastermind, PR #317 merge receipt,
   active adjacent writers, exact binary/provider realm and the expected path set.
2. **RED package tests.** Canonical rows, acyclic digests, duplicate JSON keys, closure mapping,
   revocation and complete hostile filesystem/race matrix.
3. **Package source implementation.** Add immutable types and descriptor-relative verifier.
4. **RED V3/V4 registry tests.** Pin current V3 policy/profile/security digests; add V4 canary fixture,
   `capability_packages`, `skill_capabilities` and resolved grants.
5. **Registry implementation.** Opt-in V4 load; V3 output/digests exact; no default config change.
6. **RED comparator duplicate tests.** Exactly one observed identity per required capability name.
7. **Comparator correction.** Preserve all non-duplicate existing behavior.
8. **RED protocol tests.** Exact-binary schema receipt, enabled-state parser, Mode A/Mode B,
   baseline/add/clear, `skills/changed`, structured Skill input and ordinary text-turn compatibility.
9. **Projection and adapter implementation.** Exact origin→attempt projection, server-owned root,
   V4-only bundled-skill disable, path-bearing inputs and source/list/schema invalidation.
10. **Fake-server integration.** Preserve duplicates and both path/no-path result shapes.
11. **Canary runner.** One synthetic ephemeral thread, four exact Skill turns, closed behavioral
    outputs and complete cleanup.
12. **Local/mutation/security gate.** All focused/adjacent/full feasible tests; remove each load-bearing
    guard in turn and prove the intended test fails.
13. **Exactly one real provider canary.** Use the exact pinned binary/account realm after all deterministic
    gates pass. Any ambiguous process/provider effect stops for reconciliation; no blind retry.
14. **Exact-head hosted proof and independent review.** Full repository CI, security checks, exact diff,
    real receipt review and product-outcome review.
15. **Expected-head release.** Merge only current-base exact head. No default V4 promotion on this carrier.

---

## 7. Final acceptance matrix

CAP-S1 is not complete unless all are true:

### Truth

- exact protected source origin and seven-file package generation;
- corrected package-content digest and acyclic package/Skill/profile/policy graph;
- complete-tree race-safe verification;
- exact binary/schema/runtime protocol receipt;
- exact four enabled Skills, empty baseline and exact clear result;
- exact path binding through Mode A or Mode B;
- V3 digests unchanged.

### Intelligence/method

- requested-vs-observed comparison refuses missing, duplicate, unknown, unclassified and drifted
  capability state;
- every Skill's closure includes the shared dialogue reference;
- model completes the four distinct procedure stages without inventing authority;
- model output is treated as behavior evidence, not self-attestation.

### Product

- one real read-only Codex process can actually use all four exact Skills in a coherent synthetic
  operator journey;
- first work turn is impossible before exact launch allowance;
- source/list change invalidates rather than silently continuing;
- cleanup leaves no process, thread, artifact root or package projection falsely live.

### Learning/evidence

- receipt records cost/tokens/time where provider reports them without estimating missing values;
- negative/mutation proofs identify which guard prevents each failure;
- canary result distinguishes exact isolated proof from fleet/default-policy readiness;
- fresh Sol can recover the next promotion decision without chat history.

---

## 8. Stop states

Return to Sol without widening on:

```text
PACKAGE_GENERATION_OWNER_UNRESOLVED
CAP_S1_SCOPE_COLLISION
CAP_S1_STRUCTURED_INPUT_SCOPE_COLLISION
SKILL_PROTOCOL_SCHEMA_UNATTESTED
SKILL_PATH_ATTESTATION_UNAVAILABLE
AMBIENT_SKILL_SURFACE_NOT_EMPTY
SKILL_SET_CAUSALITY_FAILED
SKILLS_CHANGED_DURING_CANARY
EFFECT_UNKNOWN
PROVIDER_REALM_UNAVAILABLE
CURRENT_SOURCE_MOVED
ACTIVE_WRITER_COLLISION
```

A deterministic failure before provider/process start may be repaired on the same carrier within the
frozen scope. A timeout or uncertain provider/process effect must be reconciled and is never replayed
through another account or carrier.

---

## 9. Route and handoff state

After SCF-PKG0 is protected:

```text
PREFERRED_AVENUE: CTO Sol
WHY: difficult but bounded Python/OHF/App-Server capability and security integration with a real
     provider falsifier
WHY NOT FABLE: product thesis, authority boundaries, source contract, protocol strategy, path set,
               journey and stop law are frozen; no sustained cross-repository principal ambiguity remains
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
PLACEMENT_STATE: WAITING_CAPACITY / needs_placement
```

No worker-facing commission, ACK, START, watcher or Git carrier exists for CAP-S1 merely because this
index is merged. A concrete eligible receiver must be lawfully assigned, then re-read current sources,
reconcile paths and create one fresh operation/branch/PR.

---

## 10. SCF-PKG0 release boundary

PR #317 may be released only after exact-head source-law tests, full repository CI, required security
checks, current-base comparison, changed-file census, independent review or explicit recorded absence,
final Sol review, canonical non-draft transition and expected-head merge.

Its merge means only:

```text
SCF-PKG0 = SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / PROTECTED
```

It does not implement V4, materialize or load a Skill, start Codex, prove the four-Skill journey,
migrate the default policy, rotate host receipts, add a route, create an Executive Job/Attempt, arm a
watcher, install a plugin, bind a Business app, apply a Professional Practice, activate Browser access
or establish non-Codex parity.
