# Sol Capability Fabric — CAP-S1 Complete Codex Skill-Set Vertical Amendment

**Date:** 2026-09-01  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Operation:** `mastermind-sol-capability-fabric-package-generation-f0-20260901-sol-001`  
**Carrier:** Mastermind PR #317 / `sol/scf-package-generation-f0-20260901`  
**Protected source and Skillpack basis:** `187490f3d5676adf7a249d69afacedd00b3efcec`, `mastermind.sol_skillpack.v1` v1.0.1, bootstrap major 1  
**Protected parent:** AOC-F0 merge `187490f3d5676adf7a249d69afacedd00b3efcec`  
**State:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / SELF-REVIEW REPAIR`

This amendment supplements and, where it conflicts, supersedes:

- `docs/superpowers/specs/2026-09-01-sol-capability-fabric-package-generation-design.md`;
- `docs/superpowers/plans/2026-09-01-sol-capability-fabric-package-generation.md`;
- the sequencing language in
  `docs/superpowers/specs/2026-09-01-sol-capability-fabric-package-identity-amendment.md`.

The package-content correction, acyclic identity graph, `capability_packages` namespace,
`skill_capabilities` profile field, duplicate-key refusal, source-verification hardening and all
existing-owner/no-rebuild boundaries remain controlling.

---

## 1. Final-review finding

The first SCF package plan split delivery into:

```text
SCF-PKG1  parser/verifier only, no provider consumer
CAP-S1    later default-policy migration and provider proof
```

That split is not compatible with the protected AOC-F0 owner amendment. The protected source says the
first implementation PR must still deliver the complete useful vertical—source digest, registry
compilation, runtime observation, launch refusal/allowance and real read-only provider proof—rather
than merge an unused digest library alone.

A parser-only `SCF-PKG1` could be technically correct and fully green while creating no capability an
operator or machine can exercise. That is infrastructure replacing product. It also makes the next
worker rediscover integration assumptions that should be falsified in the first vertical.

The correction is:

> **There is no independently releasable parser-only SCF-PKG1 operation or PR. SCF-PKG1 survives only
> as an internal implementation phase inside one CAP-S1 carrier that ends in a real isolated Codex
> four-Skill canary.**

---

## 2. Corrected execution sequence

<!-- SCF_CAP_S1_SEQUENCE_BEGIN -->
```text
SCF-PKG0 -> CAP-S1 -> CAP-PROMOTE1
```
<!-- SCF_CAP_S1_SEQUENCE_END -->

- `SCF-PKG0` is this records-only contract carrier.
- `CAP-S1` is one source + consumer + real-proof vertical on one fresh operation/branch/PR.
- `CAP-PROMOTE1` is a later separately reviewed default-policy/host/route promotion only after CAP-S1
  is accepted. The name is a local handoff alias, not a new lifecycle or Agent OS workstream.

No protected source accepts:

```text
SCF-PKG0 -> standalone parser PR -> merge -> later consumer PR
```

Internal commits and test phases are encouraged, but they stay on the same CAP-S1 carrier and are not
independent capability acceptance boundaries.

---

## 3. CAP-S1 observable mission

One real isolated read-only Codex App Server attempt must consume the exact protected
`mastermind-operator` source-package generation, expose exactly the four accepted Operator Skills,
prove their exact effective closure identities before the first work turn, complete the bounded
operator-method journey, and shut down cleanly.

The exact four Skills are:

```text
escalate-decision
finish-operation
receive-commission
return-progress
```

The observable journey is:

```text
exact reviewed source package
-> deterministic attempt-local Codex Skill projection
-> App Server exact extra-root configuration
-> provider skills/list observation
-> source + closure + loader-precedence attestation
-> Executive/OHF requested-vs-observed comparison
-> first work turn allowed only on exact match
-> real model receive -> progress -> decision/escalation -> finish/result behavior
-> typed evidence + process/resource cleanup
```

A fake App Server may prove protocol mechanics but cannot satisfy the terminal CAP-S1 proof.

---

## 4. Machine-readable vertical contract

<!-- SCF_CAP_S1_VERTICAL_BEGIN -->
```json
{
  "operation": "CAP-S1",
  "parent": "SCF-PKG0",
  "independent_implementation_prs": 1,
  "provider": "codex-app-server",
  "real_provider_required": true,
  "real_model_turn_required": true,
  "write_capable": false,
  "production_armed": false,
  "default_policy_migrated": false,
  "general_model_route_added": false,
  "skills": [
    "escalate-decision",
    "finish-operation",
    "receive-commission",
    "return-progress"
  ],
  "terminal_capability_state": "BUILT_NOT_PROVEN",
  "isolated_canary_state_when_all_proof_passes": "PROVEN_LIVE"
}
```
<!-- SCF_CAP_S1_VERTICAL_END -->

The overall capability remains `BUILT_NOT_PROVEN / PRODUCTION_UNARMED` because no default production
profile or route is promoted. The exact isolated canary path may be recorded as `PROVEN_LIVE` only
when the real Codex attempt, model behavior and cleanup receipts all pass on the accepted head. A
canary proof is not general fleet readiness.

---

## 5. Default policy remains V3 during CAP-S1

The first draft assigned default-policy migration to CAP-S1. That is superseded.

CAP-S1 uses one explicit immutable V4 canary policy supplied by server-owned composition. It does not
edit:

```text
config/executive_agent_capabilities.json
config/executive_worker_routes.json
control_plane/executive_autonomy.py expected digests
installed Executive configs or host receipts
```

Reasons:

1. A real consumer can be proven without invalidating every current Worker capability-policy binding.
2. Default-policy migration changes fleet eligibility and host receipt truth even when no new route is
   added; that is a separate promotion effect.
3. A canary policy path can be bounded to the exact CAP-S1 script and cannot be selected by a model,
   Job payload or provider response.
4. Existing valid V3 policy/profile digests remain exact during the falsifier.
5. The later promotion wave can explicitly rotate policy/autonomy digests, preserve old receipts as
   stale history, requalify exact hosts and decide whether any route becomes claimable.

`CAP-PROMOTE1` may migrate the checked-in default policy only after CAP-S1 acceptance. It must not
rewrite or auto-refresh historical installed receipts.

---

## 6. Canonical source and materialization boundary

### 6.1 Release closure is already available

The existing Executive installer owns release materialization. It creates:

```text
/Library/Application Support/MastermindExecutive/releases/<exact SHA>
```

from a full `git archive` of one accepted Mastermind commit, changes ownership to `root:wheel`, removes
group/other write permission and makes the release root mode `0755` so the control and worker service
UIDs can read and traverse it.

Therefore the tracked protected package path:

```text
plugins/mastermind-operator
```

is already part of the canonical exact-release source closure. CAP-S1 must consume an exact reviewed
release or an equally exact clean canary archive produced by the same source law. It must not point
Codex at a mutable provider home, arbitrary developer checkout, user-selected path, symlink or
network-fetched package.

### 6.2 Codex-only laboratory projection

AOC-F0 permits one explicitly provisioned Codex laboratory projection before provider-neutral HF1.
CAP-S1 may therefore create one attempt-subordinate projection with these constraints:

- source is one already-verified `CapabilityPackageGeneration`;
- all seven package files, including the shared dialogue reference, are consumed;
- projection root is created below the exact canary Attempt/workspace resource root;
- copied semantic bytes remain byte-identical;
- provider-native loader metadata is separate from Skill semantic identity;
- no credentials, OAuth, Business app binding, provider auth file or user home is copied;
- staging occurs before provider process start;
- no model input selects source or destination;
- receipt binds source generation, all source rows, staged rows, generated loader/config rows,
  destination identity and zero authoritative-workspace mutation;
- cleanup is subordinate to the Attempt and proven after process termination.

This is a Codex-specific falsifier, not the provider-neutral materializer owned by HF1. It must not
introduce a generic package installer, durable staging registry, plugin manager or cross-provider API.

---

## 7. CAP-S1 implementation scope

Current-source archaeology immediately before START may refine exact helper names, but the one carrier
must own the following capability surfaces:

### 7.1 Source identity and registry

```text
control_plane/executive_capability_packages.py
control_plane/executive_agent_capabilities.py
```

Implement the corrected V4 `capability_packages` / `skill_capabilities` contract, acyclic digest graph,
duplicate-key refusal and complete-tree no-follow verification.

### 7.2 Generic OHF exactness correction

```text
control_plane/operator_harness_contract.py
```

Required exact-Skill matching must refuse multiple observed rows with the same required name even
when one row matches. One name plus one exact identity is the only satisfier. This is a generic
requested-vs-observed correctness fix, not Codex policy.

### 7.3 Codex observation and exact extra root

```text
control_plane/codex_operator_adapter.py
scripts/ohf/protocol.py
```

The adapter must:

- accept exact server-authored canary Skill-root configuration, never arbitrary model input;
- call the real App Server `skills/extraRoots/set` contract;
- call grouped `skills/list` with the exact CWD/root;
- observe path/root/name information at the precision the current App Server actually exposes;
- derive each `ObservedCapabilityIdentity.skill_content_digest` from the already-verified staged root
  and exact provider resolution, not from provider name alone;
- refuse missing path precision, untrusted root, duplicate same-name rows, incomplete four-Skill set,
  extra unclassified custom Skills or hot-reload ambiguity before the first work turn.

If current App Server output cannot prove the resolved root/path relationship, CAP-S1 must isolate the
process so only the one staged root can supply custom Skills and prove the complete effective source
set externally. It may not lower identity precision to name-only success.

### 7.4 Attempt-subordinate Codex canary

Expected bounded source, subject to current archaeology:

```text
scripts/ohf/cap_s1_mastermind_operator_canary.py
scripts/ohf/capability_skill_projection.py
scripts/ohf/fixtures/executive_agent_capabilities_v4_mastermind_operator.json
tests/test_cap_s1_mastermind_operator_canary.py
tests/test_executive_capability_packages.py
tests/test_executive_agent_capabilities_v4.py
```

A reusable helper belongs under the existing OHF laboratory only when it remains Codex-canary scoped.
If implementation would become a provider-neutral materializer, STOP and return to Sol/HF1 rather
than silently absorbing that owner.

### 7.5 Existing compatibility tests

The vertical also extends current tests for:

```text
ExecutionCapabilityRegistry V3 exact digests
OHF comparator behavior
Codex adapter protocol fidelity
operator orchestration first-turn gate
process/resource cleanup
```

### 7.6 Protected no-edit surfaces

Unless a newly discovered direct contradiction makes the vertical impossible and returns to Sol:

```text
config/executive_agent_capabilities.json
config/executive_worker_routes.json
control_plane/executive_autonomy.py
scripts/executive_os_phase1c_worker.py production composition
ops/executive_os/install.sh
all Browser, Business, PPF, Capacity, MH1, Agent OS and deployment paths
all protected mastermind-operator source-package files
```

The canary may consume existing source bytes; it never edits them.

---

## 8. Deterministic, provider-observed and model-generated boundaries

### Deterministic

- package inventory and all SHA-256 identities;
- package/Skill/profile/policy digest construction;
- duplicate/path/symlink/hardlink/race/refusal behavior;
- attempt-local projection receipt;
- exact extra-root request and skills-list parsing;
- exact requested-vs-observed comparator decision;
- process/resource/artifact cleanup;
- canary evidence-envelope validation.

### Provider-observed

- App Server initialization and current protocol shapes;
- effective grouped Skill discovery;
- provider session/process identity;
- turn/event stream and terminal result;
- provider-reported model identity where available.

Provider observation is evidence, not organizational authority.

### Model-generated

The model performs one bounded behavioral journey and emits closed markers demonstrating that the
four Skills were usable together. Model prose cannot certify its own source bytes, loader root,
capability grant, execution authority, success or cleanup.

---

## 9. Real canary journey and evidence

The canary prompt must be bounded, synthetic and free of live company authority. It supplies one fake
commission with a deterministic decision branch and requires the model to demonstrate:

1. `receive-commission`: distinguish pickup ACK from START and preserve one exact operation;
2. `return-progress`: emit bounded progress without claiming completion;
3. `escalate-decision`: request one decision at the frozen ambiguity instead of inventing authority;
4. after a deterministic synthetic Sol ruling is delivered in the same provider session,
   `finish-operation`: return RESULT while preserving that RESULT is not acceptance/STOP.

The evidence receipt must bind:

```text
candidate commit/tree
canary operation ID
workspace and process generation
V4 canary policy digest
package source + generation digests
four Skill grant + closure digests
projection receipt digest
exact App Server config/security digest
skills/extraRoots/set request outcome
skills/list raw-shape digest and reduced exact observations
launch comparison decision
turn/event transcript digest with secret-free closed markers
served model observation
terminal process state
complete artifact inventory
cleanup receipt
```

Do not store unrestricted model chain-of-thought. Preserve only bounded turn text/artifacts needed to
prove the user-visible/operator-method behavior.

Exactly one real provider canary is attempted after all local/fake-server/security tests are green. A
timeout or uncertain provider/process effect is `EFFECT_UNKNOWN`; reconcile the same operation and do
not blind-retry or move to another account.

---

## 10. Required refusal matrix

Before the first real work turn, CAP-S1 must refuse:

```text
package entrypoint byte drift
shared dialogue reference byte drift
manifest or unrelated package-file drift against source generation
missing or extra package file
symlink, hardlink, non-regular file, case collision or raced complete tree
unknown/revoked Skill capability ID
duplicate JSON policy key
missing one of four Skills
extra unclassified custom Skill
same required name observed more than once
same name with wrong/unknown closure digest
Skill resolved outside the one staged root
provider path/root precision insufficient without process isolation proof
wrong sandbox, network, approval, auth realm, model or App Server config
hot-reload/source movement after attestation
first turn attempted before LaunchDecision.ALLOW
```

Each load-bearing refusal has a discriminating regression or mutation test.

---

## 11. Acceptance and stop law

CAP-S1 is accepted only when one exact final head has:

- complete package/closure/registry tests;
- V3 exact compatibility proof;
- real V4 four-Skill source and profile resolution;
- exact duplicate-same-name comparator refusal;
- fake App Server protocol tests;
- real read-only Codex App Server/model canary on the accepted candidate;
- complete process/resource cleanup;
- full repository CI and required security checks;
- independent exact-head source/security/product review;
- current-base, collision-free expected-head merge.

The capability ledger after successful source release is:

```text
package/registry/adapter source              BUILT_NOT_PROVEN / PRODUCTION_UNARMED
exact isolated Codex four-Skill canary path  PROVEN_LIVE
checked-in default V4 policy                 NOT_BUILT
fleet route / host readiness                 NOT_BUILT
provider-neutral materializer                SPEC_ONLY / HF1-GATED
non-Codex parity                              NOT_BUILT
```

Stop after CAP-S1. Do not migrate default policy, rotate host receipts, add a general Model Router
route, arm production, connect Business apps, claim Professional Practice competence, add browser
access or begin non-Codex parity on the same carrier.

---

## 12. Corrected next operator handoff

After PR #317 is protected, the next commission is one fresh CAP-S1 operation:

```text
PREFERRED_AVENUE: CTO Sol
WHY: difficult but bounded Python/OHF/App-Server security integration with a real provider falsifier
WHY NOT FABLE: product thesis, ownership and exact end-to-end mission are now frozen; no sustained
               cross-repository principal ambiguity remains
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
PLACEMENT_STATE: WAITING_CAPACITY / needs_placement
```

No worker-facing commission is emitted until a concrete eligible receiver is lawfully assigned. The
full CAP-S1 carrier remains one independently useful vertical; internal parser tasks do not become a
separate release.

This amendment creates no implementation START, provider process, Worker, Attempt, route, watcher,
host mutation, plugin install, Business effect, merge or production authority by itself.
