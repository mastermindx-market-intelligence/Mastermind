# Sol Capability Fabric — Capability-Package Identity Graph and Namespace Amendment

**Date:** 2026-09-01  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Operation:** `mastermind-sol-capability-fabric-package-generation-f0-20260901-sol-001`  
**Carrier:** Mastermind PR #317 / `sol/scf-package-generation-f0-20260901`  
**Protected source and Skillpack basis:** `187490f3d5676adf7a249d69afacedd00b3efcec`, `mastermind.sol_skillpack.v1` v1.0.1, bootstrap major 1  
**State:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / SELF-REVIEW REPAIR`

This amendment supplements and, where it conflicts, supersedes:

- `docs/superpowers/specs/2026-09-01-sol-capability-fabric-package-generation-design.md`;
- `docs/superpowers/plans/2026-09-01-sol-capability-fabric-package-generation.md`.

The package-content digest correction remains separately controlling for the exact value
`a9781411d2642569f8b56e33bd0e0d9808a69176ccaced86642cd23948a71306`.

The original product outcome, existing-owner boundary, effective Skill closure law, v3 compatibility,
production-inert split between `SCF-PKG1` and `CAP-S1`, and all protected no-edit surfaces remain
controlling. This amendment repairs two release-blocking contract defects and two source-verification
hardening gaps found during final Sol exact-head review.

---

## 1. Review findings

### 1.1 Circular digest graph

The first draft said both:

```text
package grant digest binds exact Skill grant digests
Skill grant digest binds package grant identity
```

That graph is circular. Neither side can be computed without the other unless an unreviewed fixed-point,
placeholder or post-hoc rewrite is introduced. Any of those would make the supposedly canonical identity
ambiguous and would give independent implementations room to disagree.

This is a release blocker. The corrected graph is acyclic and has separate source, Skill-grant and
package-generation layers.

### 1.2 Source packages were conflated with runtime plugin grants

The existing v3 policy already contains a root `plugins` field and profile-level `plugins` field. Current
source law requires those runtime plugin surfaces to remain empty until an immutable **installed** bundle,
app generation and runtime observation contract exists.

The first draft reused root `plugins` for source-only package generations even though `SCF-PKG1` expressly
installs nothing. That would blur:

```text
reviewed source bytes
installed provider bundle
Business app binding/import
effective runtime capability
```

This is also a release blocker. V4 introduces `capability_packages` for immutable source-package
generations and preserves `plugins={}` for the still-unavailable installed/runtime plugin surface.

### 1.3 Raw profile `skills` semantics were overloaded

V3 treats `profiles.<id>.skills` as provider-runtime names. The first V4 draft silently changed the same
field to capability IDs. Schema versioning makes that technically parseable, but the reuse is unnecessary
and increases migration and review risk.

V4 therefore adds `skill_capabilities` for exact grant IDs. Raw `skills` remains the legacy runtime-name
field and must be empty for a V4 exact company-Skill profile. The resolved Python profile retains
`skills` as the compatibility view of provider-runtime names and adds `skill_grants` as the exact typed
view.

### 1.4 First-pass enumeration did not close the complete-tree race

The first plan required file-level first/final `fstat`, but an extra package entry could be inserted after
the initial tree census without changing any already-open file descriptor. Verification must therefore
repeat the descriptor-relative complete-tree census and revalidate retained directory identities before
returning success.

---

## 2. Corrected V4 root namespace

The accepted V4 root shape is:

<!-- SCF_PKG1_V4_ROOT_BEGIN -->
```json
{
  "schema_version": "mastermind.executive_agent_capabilities/v4",
  "policy_version": "<bounded-id>",
  "lifecycle_authority": "executive_os",
  "production_armed": false,
  "mcp_servers": {},
  "resources": {},
  "capability_packages": {},
  "plugins": {},
  "profiles": {}
}
```
<!-- SCF_PKG1_V4_ROOT_END -->

Normative semantics:

- `capability_packages` is the closed map of immutable source-package generations.
- `plugins` remains the installed/runtime plugin grant namespace and must equal `{}` in `SCF-PKG1`.
- Profile-level `plugins` also remains empty.
- No package entry creates provider installation, Business app binding, workspace enrollment, OAuth,
  profile eligibility, route eligibility or host readiness.
- V3 root keys and normalized digest projection remain exactly current.
- V4 adds one root key; it does not reinterpret the existing runtime plugin field.
- `ExecutionCapabilityRegistry` gains `capability_packages`, not a second registry and not a
  `PluginRegistry`/`PackageStore` service.

The corrected Python registry view is conceptually:

```python
@dataclasses.dataclass(frozen=True)
class ExecutionCapabilityRegistry:
    schema_version: str
    policy_version: str
    lifecycle_authority: str
    production_armed: bool
    mcp_servers: Mapping[str, McpServerGrant]
    resources: Mapping[str, ResourceGrant]
    capability_packages: Mapping[str, CapabilityPackageGeneration]
    profiles: Mapping[str, ExecutionCapabilityProfile]
    policy_digest: str
    source_path: Path
```

There is no registry-level runtime plugin mapping in this wave. The raw `plugins={}` field is validated
and preserved as an unavailable reserved surface.

---

## 3. Corrected profile schema

For V4, existing profile keys remain and one exact field is added:

```json
{
  "enabled": true,
  "execution_surface": "codex-app-server",
  "auth_realm": "dedicated-worker-account",
  "sandbox_policy": "read-only",
  "approval_policy": "never",
  "network_policy": "disabled",
  "write_capable": false,
  "native_helper_policy": "disabled",
  "native_helper": null,
  "skills": [],
  "skill_capabilities": [
    "mastermind-operator.escalate-decision.v1",
    "mastermind-operator.finish-operation.v1",
    "mastermind-operator.receive-commission.v1",
    "mastermind-operator.return-progress.v1"
  ],
  "mcp_servers": [],
  "resources": [],
  "plugins": [],
  "forbidden": []
}
```

Rules:

- V3 has no `skill_capabilities` key and retains its existing `skills` behavior.
- V4 exact company-Skill profiles require `skills=[]` and use only `skill_capabilities`.
- `skill_capabilities` is sorted, unique and contains exact capability IDs.
- The loader resolves each ID to one non-revoked `EffectiveSkillGrant`.
- The resolved dataclass `profile.skills` contains sorted unique runtime names.
- The resolved dataclass `profile.skill_grants` contains exact grants in capability-ID order.
- Unknown IDs, duplicate IDs, multiple IDs resolving to one runtime name, revoked source generations,
  write-capable custom-Skill profiles, `codex-exec` custom-Skill profiles and non-empty runtime plugin
  fields refuse.
- `forbidden` remains provider-runtime names because the existing launch comparator observes runtime
  names.

This avoids one field meaning different identity layers in different schema generations.

---

## 4. Corrected acyclic identity graph

The normative dependency graph is machine-readable below. An edge means the value on the left is an
input to the digest on the right.

<!-- SCF_PKG1_IDENTITY_DAG_BEGIN -->
```text
file_rows -> package_content_digest
package_content_digest -> package_source_digest
package_provenance -> package_source_digest
package_source_digest -> skill_grant_digest
skill_closure_mapping -> skill_grant_digest
skill_content_digest -> skill_grant_digest
package_source_digest -> package_generation_digest
skill_grant_digest -> package_generation_digest
package_generation_state -> package_generation_digest
skill_grant_digest -> profile_digest
package_generation_digest -> profile_digest
profile_contract -> profile_digest
package_generation_digest -> policy_digest
profile_digest -> policy_digest
policy_contract -> policy_digest
```
<!-- SCF_PKG1_IDENTITY_DAG_END -->

There is no edge from `package_generation_digest` back to `skill_grant_digest`. No digest requires a
fixed point, placeholder, mutation after construction or iteration until convergence.

### 4.1 `package_content_digest`

Binds only the canonical complete package file rows:

```text
relative_path, sha256, byte_length, executable
```

It excludes repository, commit, generation, revocation and profile state.

### 4.2 `package_source_digest`

Uses schema `mastermind.capability_package_source/v1` and binds:

```text
package capability ID
package kind
repository
source commit
source tree OID
package root
manifest path
package_content_digest
required_app_references
```

It is immutable source/provenance identity. It excludes `generation`, `source_state`, `revoked` and
Skill-grant digests.

### 4.3 `skill_content_digest`

Remains the existing semantic digest of one finite effective Skill closure using
`mastermind.effective_skill_closure/v1`. It is the value compiled into OHF
`CapabilityIdentity.skill_content_digest`.

### 4.4 `skill_grant_digest`

Uses schema `mastermind.effective_skill_grant/v1` and binds:

```text
Skill capability ID
runtime name
entrypoint path
closure path mapping
skill_content_digest
package capability ID
package generation label
package_source_digest
```

It does **not** bind `package_generation_digest`.

### 4.5 `package_generation_digest`

Uses schema `mastermind.capability_package_generation/v1` and binds:

```text
package capability ID
package generation label
source_state
revoked
package_source_digest
ordered exact Skill capability IDs + skill_grant_digests
```

This is the complete reviewed generation identity. Revocation changes this digest while preserving
historical source and closure digests.

### 4.6 `profile_digest`

For each selected exact Skill, V4 profile normalization binds:

```text
Skill capability ID
skill_grant_digest
owning package_generation_digest
```

plus the existing profile contract. Therefore:

- closure movement changes the Skill grant, package generation, profile and policy identities;
- an unrelated package-file change preserves unaffected `skill_content_digest` but changes
  `package_source_digest`, all package-bound Skill grant identities, package generation, profile and
  policy provenance;
- revocation preserves source/closure/Skill-grant history but changes package generation, profile
  availability and policy identity;
- V3 valid-document normalized projections and exact current digests remain unchanged.

### 4.7 Corrected dataclass fields

```python
@dataclasses.dataclass(frozen=True)
class EffectiveSkillGrant:
    capability_id: str
    runtime_name: str
    entrypoint_path: str
    closure_paths: tuple[str, ...]
    skill_content_digest: str
    package_capability_id: str
    package_generation: str
    package_source_digest: str
    grant_digest: str


@dataclasses.dataclass(frozen=True)
class CapabilityPackageGeneration:
    capability_id: str
    kind: str
    repository: str
    source_commit: str
    source_tree_sha: str
    package_root: str
    manifest_path: str
    generation: str
    source_state: str
    revoked: bool
    package_content_digest: str
    package_source_digest: str
    files: tuple[CapabilityPackageFile, ...]
    skills: tuple[EffectiveSkillGrant, ...]
    required_app_references: tuple[str, ...]
    package_generation_digest: str
```

The first plan's `EffectiveSkillGrant.package_grant_digest` and ambiguous
`CapabilityPackageGeneration.grant_digest` are superseded.

---

## 5. Corrected parser and canonical-JSON law

### 5.1 Duplicate JSON object keys

V4 package/profile maps are authority-bearing policy identities. The loader must reject duplicate keys
at every JSON object depth rather than silently accepting the last value.

The implementation may use one shared duplicate-rejecting `object_pairs_hook` for both V3 and V4.
This is permitted only with the explicit compatibility statement:

```text
all valid V3 documents retain identical normalized objects, profile digests and policy digests;
ambiguous duplicate-key JSON was never a valid reviewed capability policy and now refuses.
```

Tests must cover duplicate root, package, file-row, Skill and profile keys. Error text is bounded and
must not echo arbitrary values.

### 5.2 Declared digests are checked, not trusted

Construction order is:

```text
validate rows and fields
-> recompute package_content_digest
-> recompute package_source_digest
-> recompute each skill_content_digest
-> recompute each skill_grant_digest
-> recompute package_generation_digest
-> resolve profiles and recompute profile digests
-> recompute policy digest
```

Every declared digest must equal the corresponding recomputed value. No constructor accepts a caller-
supplied verdict or post-construction digest rewrite.

### 5.3 Empty regular files

The generic contract permits a declared zero-byte regular file. Bounds are:

```text
0 <= byte_length <= MAX_PACKAGE_FILE_BYTES
```

The exact protected `mastermind-operator` generation currently contains no zero-byte file. Empty
entrypoints/manifests may still be rejected by the existing package/source validator where their own
format requires content.

---

## 6. Complete-tree no-follow verification amendment

The first plan's file-level race checks remain required and gain the following terminal fence:

1. Preserve the lexical source-root path before any `resolve()` call; never erase symlink evidence by
   resolving first.
2. Open and retain descriptor-relative handles for source/package directories with `O_NOFOLLOW` and
   `O_DIRECTORY`.
3. Record bounded identity tuples for every retained directory.
4. Perform the initial complete-tree enumeration without following links.
5. Open/hash/final-`fstat` every declared file and require exact set, type, nlink, size, digest and
   executable-bit equality.
6. Perform a second complete-tree enumeration through the retained package-root descriptor.
7. Require initial and final normalized entry sets to be identical and equal the declaration.
8. Final-`fstat` every retained directory and require its identity tuple, including size, mtime and
   ctime where supplied by the platform, to match the initial tuple.
9. Close every descriptor on success and every refusal.
10. Return success only after this terminal fence.

Tests must insert/remove/rename an extra entry after the first census through an injected deterministic
seam and prove refusal. Sleeps and probabilistic races are not acceptable.

The receipt proves the exact opened source snapshot. It does not claim the provider later loaded those
bytes; CAP-S1 must separately bind provider materialization/loader precedence and pre-turn observation.

---

## 7. Exact task corrections

Where the first implementation plan says root `plugins` stores source packages, read
`capability_packages`; root and profile `plugins` remain empty.

Where it says raw V4 `profiles.<id>.skills` stores exact capability IDs, read:

```text
skills = []
skill_capabilities = [exact Skill capability IDs]
```

Where it says `EffectiveSkillGrant.package_grant_digest`, read
`EffectiveSkillGrant.package_source_digest`.

Where it says the package's final `grant_digest`, read `package_generation_digest` and use the acyclic
construction order in this amendment.

Task 4 must add exact V3/V4 root-key dispatch, duplicate-key refusal and `capability_packages` parsing.
Task 5 must resolve `skill_capabilities`. Task 6 still compiles only `skill_content_digest` into the
existing OHF identity. Task 7 must prove the corrected digest cascade and absence of any cycle.

The expected implementation path set remains:

```text
control_plane/executive_capability_packages.py
control_plane/executive_agent_capabilities.py
tests/fixtures/executive_agent_capabilities_v4_mastermind_operator.json
tests/test_executive_capability_packages.py
tests/test_executive_agent_capabilities.py
tests/test_executive_agent_capabilities_v4.py
```

No current default config, route, autonomy, OHF comparator, Codex adapter, worker composition,
package-source, Browser, Business, PPF, Agent OS, host or deployment path is added to `SCF-PKG1`.

---

## 8. Corrected acceptance matrix

`SCF-PKG1` implementation is acceptable only when exact tests prove:

- the identity graph above is acyclic and every digest is deterministic;
- the corrected package-content digest is used;
- `capability_packages` and reserved-empty runtime `plugins` cannot be confused;
- raw `skill_capabilities` and resolved runtime `skills` cannot be confused;
- valid V3 policy/profile digests remain exact;
- duplicate JSON keys refuse;
- missing/extra/symlink/hardlink/non-regular/case-collision/oversized/raced source refuses;
- terminal complete-tree recensus detects post-census insertion/removal/rename;
- entrypoint/shared-reference/unrelated-file/revocation changes produce the exact corrected digest
  cascade;
- four exact closure digests compile into the existing OHF identity;
- no provider consumer, route, host receipt, package install or production state is created.

The capability state remains:

```text
SCF-PKG1 = BUILT_NOT_PROVEN / PRODUCTION_INERT
```

---

## 9. Release consequence and next action

After this amendment and exact-head source-law tests pass, PR #317 may protect only the corrected
records contract:

```text
SCF-PKG0 = SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT / PROTECTED
```

The next independent operation remains the bounded `SCF-PKG1` implementation in the existing
`ExecutionCapabilityRegistry`. It must use a fresh branch/carrier, preserve default V3 policy, and stop
before `CAP-S1` provider loading.

This amendment authorizes no implementation START, provider process, runtime plugin grant, Business
installation, host change, route, Worker, Attempt, browser action, merge or production arming by itself.
