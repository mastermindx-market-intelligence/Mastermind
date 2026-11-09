# Native shared-pool policy change preflight

Programme: Mastermind #983 / WS:EXECUTIVE-CAPACITY-FABRIC. Task tree: `docs/SHARED_MODEL_POOL_CONTROL.md` on original PR #2109, nodes C2/C4. Source operation: `shared-pool-policy-plan-20261106-c4`; protected procedure/source base `609bc3a3e4117fed9b656a0552cecb8b8c7e3bf1`.

## User job and boundaries

Before adding a pool, changing a model, removing a pool, or changing routing policy, an operator needs an exact-source change classification and the next required native-owner steps. The existing `source/fabric_policy_snapshot.py` remains the authority for compatibility with immutable native routing snapshots. This command neither changes that owner nor substitutes its own eligibility policy.

Run the module from its qualified source checkout against **public routing-policy files only**, never account, credential, token or environment files:

```sh
python3 -B -m ops.native_fabric.quota_continuity.policy_change inspect \
  --policy /absolute/path/to/public/pools.yaml

python3 -B -m ops.native_fabric.quota_continuity.policy_change preview \
  --current-policy /absolute/path/to/public/pools.yaml \
  --candidate-policy /absolute/path/to/reviewed/candidate-pools.yaml \
  --expected-source-sha256 <source_sha256-returned-by-inspect>
```

The operator supplies local source paths. They are not accepted from a model-facing HTTP route or browser. Missing, malformed, moving, nonregular, oversized or symlink-final files fail with a fixed code and no source excerpt. The exact expected source digest prevents comparing a candidate against an unnoticed replacement. The command rechecks both source files after parsing and comparison; it does not claim a transactional publication lock across those observations.

## Results

- `UNCHANGED`: identical source bytes. No inferred need to refresh or activate anything.
- `SOURCE_ONLY_CHANGE`: source bytes differ but decoded content is unchanged.
- `NONCRITICAL_POLICY_CHANGE`: only fields excluded by the **incumbent owner's** critical fingerprint changed. Today these are the closed Grok expiring-priority flag and the owner's selected weekly observation fields. This is compatibility evidence, not a quota refresh or permission to publish.
- `CRITICAL_POLICY_CHANGE`: the existing native snapshot cannot be treated as compatible. A reviewed native generation is required, original admitted operation generations must be retained, and new admissions must be revalidated. Added/changed pools and models require qualification; removal or affected existing bindings requires draining or retention through the incumbent owners.

All successful previews retain `activation_authorized=false`, `writes_applied=false`, `original_operations_rebound=false`, `active_bindings=NOT_OBSERVED` and `account_configuration=NOT_READ`. Configured pool IDs are not a count of distinct paid accounts or currently usable capacity. No validation result grants a model, workload, account or service permission.

The preflight bounds YAML events/depth before invoking the existing decoder, refuses aliases/merge indirection in its own inputs, and rejects known credential fields/material before emitting digests. This is not a credential scanner or authority to inspect private files. The native owner itself is unchanged; its supported policy and immutable-generation contracts are not weakened by the stricter operator input boundary.

## Publication and original-request preservation

Preview and candidate authoring confer **no apply, rotate, enable, reload, reset or retry authority**. The opt-in compatible publication path below delegates to the selected original native publisher; it does not replace it with checkout code. The existing native generation builder, installer prepare/apply/reconcile operations, account/credential owner, physical admission lock, lease ledger and original application-turn owner retain their jobs. Do not copy an arbitrary candidate over installed `pools.yaml`, infer that old leases are absent, bind a replacement key to an active turn, or replay an unknown request based on this preview.

The original application-selection/enrollment migration and #2109 OS view retain their source writers. Inspection/staging do not edit their picker, broker, installer, authentication or UI files. The compatible-publication extension updates the original support publisher and its exact derived row in this candidate's default native manifest/inventory; it does not write an active root's APPLICATION generation variants or workspace. Those variants must be regenerated from the composed source before installation. Native model/pool activation, key-reference generation changes, drain/rollback and installed consumer proof remain separate required programme work.

## Evidence at authoring

Actual operator invocation read the existing public routing source selected from the incumbent installed pool launcher's kit. It returned ten configured IDs (`bailian`, `claude`, `claude-native`, `codex-native`, `cursor`, `glm`, `go`, `grok`, `minimax`, `ocfree`), source SHA256 `db4e4b1768809bd991003ef045568b480cdb42ea0715a6b73ea5353930bf90d8` and incumbent critical SHA256 `7433fc62d515d8872c68d4e1fb7a6fcbac0c07187cbaf1b6497df5dd0b7fca36`. A same-source preview returned `UNCHANGED`, no changed pools and no requirements. These are dated source observations, not permanent current revisions or live capacity proof.

Both new Python files passed AST parsing. Regression cases are authored for current/candidate drift, native critical/noncritical semantics, source formatting, pool/model changes, invalid graphs, credential material, symlinks and actual CLI composition. No discretionary test suite was executed under the Chairman's existing instruction. Hosted CI results must be read for the exact published head before claiming those cases passed. No account configuration, secret resolver, provider call, lease mutation, service installation or production deployment was performed by this slice.

## Author a model or pool change without editing the live file

The existing operator also supports `stage` and `verify-candidate`. They create or read back **one private candidate artifact**, not installed configuration. The authored policy is canonical JSON, which is valid YAML; existing comments/formatting are not retained. Untouched decoded policy values are preserved.

Use a closed JSON edit document. For example, to change an existing role to another model already declared in that pool's `model_capabilities`:

```json
{
  "schema": "mastermind.native_pool_policy_edits.v1",
  "model_assignments": {
    "glm": {"executor": "glm-5.3"}
  }
}
```

`model_assignments` retains every other role, capability, quota, policy and account-related reference. It refuses unknown pools, missing model maps, unknown roles or models not already declared in the pool's capability map. A declared capability is not proof of a paid entitlement or live suitability.

For intentional complete pool definitions, use `pool_upserts` (map from pool ID to the **complete** proposed pool row). For removal, use `pool_removals` (unique existing pool IDs). `routing`, when present, is the complete replacement routing object. No defaults, automatic enable flags, new credentials or added capacity are invented. An upsert is not a partial merge; preserve required fields deliberately. A model assignment cannot target the same pool as an upsert or removal. New/changed model definitions still require the original native owner's full qualification before admission.

Create the output directory yourself with private permissions, separate from the live policy directory, and choose an unused final name:

```sh
mkdir -m 700 /absolute/private/pool-candidates
python3 -B -m ops.native_fabric.quota_continuity.policy_change stage \
  --policy /absolute/path/to/public/pools.yaml \
  --edits /absolute/private/edits.json \
  --expected-source-sha256 <inspect-source-sha256> \
  --output /absolute/private/pool-candidates/candidate.json
```

The command validates the complete edit and native preview, rechecks the exact source and edit files, fsyncs a private scratch inode, and publishes the final name atomically with no replacement. It refuses pre-existing files, directories and symlinks, public/shared output directories, symlink parent paths, and output in the live source directory. No-op requests are refused rather than producing new artifacts. It neither unlinks nor replaces an existing destination, including one created concurrently.

Successful output is `state=STAGED`, `candidate_written=true`, the exact candidate/source digests and the original change preview. `live_policy_changed=false`, `activation_authorized=false` and `original_operations_rebound=false` remain explicit. This is an executable candidate-authoring path, not a policy activation receipt.

### Lost response or interrupted candidate publication

An error after attempting the final no-replace publication returns exit code 3 with `state=EFFECT_UNKNOWN` and the original candidate digest. The original target is retained. Never restage to another path to evade uncertainty. Read that exact target:

```sh
python3 -B -m ops.native_fabric.quota_continuity.policy_change verify-candidate \
  --candidate /absolute/private/pool-candidates/candidate.json \
  --expected-candidate-sha256 <original-candidate-digest>
```

This reports only `ARTIFACT_PRESENT_VERIFIED`: the exact candidate is available. It does not reconstruct the original invocation's success or authorize replay, activation, key changes or original-operation transfer. The existing native publisher must independently recheck its current source, grants, admission/drain state and generation before consuming the candidate.

### Authoring evidence

The staged operator was exercised against the incumbent public ten-pool source at revision `db4e4b1768809bd991003ef045568b480cdb42ea0715a6b73ea5353930bf90d8`. A deliberately unactivated GLM executor change to its already-declared `glm-5.3` produced candidate `e1c0e3b2f00d315568e8fc7e6a9a39e145e8b35124af8d2952cd8d635e81d468`. CLI stage and readback returned exit0, with critical-policy/requalification/drain requirements preserved and the original live file byte-identical afterward. This was source-backed private candidate authoring, not a provider call, native generation install, account activation or model-choice recommendation.

The source regression cases cover closed edit semantics, model-map ownership, untouched values, no-op and stale revisions, credential rejection, private destinations, no-overwrite races, input drift, lost final-publication acknowledgment and actual subprocess CLI composition. They are authored for required hosted CI; no discretionary local suite was run.

## Publish compatible policy through the selected native owner

The `publish-compatible` and `publication-status` commands extend the same operator. They never load a new writer from a caller-supplied module or execute this checkout's candidate writer against the live kit. They select the current immutable native generation through `rollout/native_generation.py`, verify its complete code closure, require the original `ext/support_bundle.py` API version and adjacent policy validator, and hold the existing generation publication lock during the finite owner call. An older installed publisher returns `NATIVE_POLICY_PUBLISHER_UPGRADE_REQUIRED` without invoking a substitute implementation. Source merge is not installed enrollment.

Before any authorized change, retain the exact old **public policy** as a separate owner-writable regular artifact so the original owner can confirm its file/directory sync without changing bytes. The command never chmods a read-only source. Do not supply the live file itself or a hard link as rollback evidence. Both candidate and retained old bytes must match their expected digests. The original publisher revalidates the actual live preimage under its existing physical `.admission.lock`; a prior inspect outside the lock is insufficient. It confirms the retained rollback file and directory are synced before attempting the policy replacement.

```sh
python3 -B -m ops.native_fabric.quota_continuity.policy_change publish-compatible \
  --stable-ext /absolute/original/kit/ext \
  --expected-native-generation <current-qualified-generation> \
  --expected-current-sha256 <exact-old-public-policy-sha256> \
  --expected-candidate-sha256 <exact-new-public-policy-sha256> \
  --candidate /absolute/private/candidate.json \
  --rollback-source /absolute/private/retained-old-policy.yaml
```

Only the incumbent policy owner's **same critical fingerprint** is allowed on this path. New or removed pools, different models, entitlement/limit changes and other critical policy changes refuse with `CRITICAL_CHANGE_REQUIRES_NATIVE_GENERATION`. They require a separate coordinated native generation transition, not a momentary global edit that would make active snapshots incompatible. No pool/account/model grant is synthesized from this command. It neither refreshes provider quota nor sets model-serving authority.

For a nontrivial compatible update, the original owner requires its existing active directory to contain no unclosed workers or unrecognized entries. Qualified retained settlement metadata is classified by its existing validator; nothing is removed or reaped here. A busy lock, unsafe directory, changed source, symlink or multiply linked operand, changed target, missing retained preimage or mismatched generation fails closed. No missing installation, lock or state store is created.

After staging into the original target directory, the owner rechecks the held directory/lock identities, active entries, candidate, retained preimage and current target. One atomic replacement is followed by directory sync and exact new inode/content readback. The reply distinguishes `POLICY_PUBLISHED` from `UNCHANGED`; account/credential access, generation selection and original-operation rebinding remain false. Legacy three-argument native `ensure_policy` callers retain their existing contract; the strict behavior is opt-in.

### Uncertain publication and rollback

A missing, malformed or timed-out modifying response—or a failure after attempted replacement—returns `EFFECT_UNKNOWN` and no retry authority. Do not issue another publication, choose a new target, alter the expected revision, or switch the service to manufacture success. Observe the same original target through the same selected owner:

```sh
python3 -B -m ops.native_fabric.quota_continuity.policy_change publication-status \
  --stable-ext /absolute/original/kit/ext \
  --expected-native-generation <original-qualified-generation> \
  --expected-current-sha256 <original-old-public-policy-sha256> \
  --expected-candidate-sha256 <original-new-public-policy-sha256>
```

This read can report `CANDIDATE_BYTES_OBSERVED`, `PREVIOUS_BYTES_OBSERVED` or `OTHER_POLICY_OBSERVED`. It deliberately retains `original_publication_proven=false` and `retry_authorized=false`; present bytes alone cannot reconstruct a lost invocation or prove an earlier write never happened. Unknown third-party content is neither printed nor hashed into public output. A different selected generation must be reconciled through its existing owner rather than bypassing the original selection fence.

An authorized rollback after a **confirmed** publication is the same compatible publisher in reverse: retained old bytes become the candidate, the confirmed current digest becomes the expected prior revision, and the retained newer candidate is its rollback preimage. It rechecks original locks, compatibility and idle state. There is no force flag, new rollback journal, pointer rewind, credential copy or implicit replay after uncertainty.

### Source and installed boundary

The strict native functionality is in the original `candidate/support_bundle.py`; its historical `source/` preimage and existing installer/generation schemas are unchanged. The operator transport is `policy_publication.py`. The active application integration has separate support membership and generated closure manifests: compose these function-disjoint changes into that exact current source and regenerate its actual closure through the existing builder before installation. Never rewrite an installed sealed file or reuse a manifest that omits these new bytes.

At authoring, the current native selection was sequence34, generation `a7671e6e0f275e25b296e8d0c972c2c45f68d8cb737152cb4a282d3bc450a775`. A real **read-only** `publication-status` call returned exit2 / `NATIVE_POLICY_PUBLISHER_UPGRADE_REQUIRED`, `writes_applied=false` and no reconciliation/retry authority. No live policy change, key rotation, lease action or service installation occurred. The command did not fall back to source-checkout code. This identifies the exact native rollout dependency, not a user-credential requirement.

Regression source covers under-lock expected-current CAS, critical-change refusal, retained preimage, active/unknown marker preservation, symlinks and unsafe files, source movement, replacement acknowledgment loss, directory-sync failure, read-only observations, reverse CAS, legacy-call compatibility and actual selected native owner subprocess composition. Local validation is limited to syntax/diff and the stated real read-only command; regression execution must be established by the exact hosted CI receipt, not inferred from authored cases.

## Native application packaging of this publisher successor

The publication owner is an existing member of the native107 closure. Updating its
actual bytes also changes that closure's identity. The Go/application builder now
recognizes **one exact publisher-only successor**, with new publisher SHA256
`bd8058657f884ee4fb7fbad1d937c24041e6d4c204fb1e3dc00953f7482bf3b3` and complete
107-member predecessor manifest SHA256
`815ec3c880b5f66590b7dcc04ac42c6c5384ba296b44e83af7e96c23326f6347`.
It verifies every original member before feeding a private predecessor copy into
the unchanged historical Go validator. The actual candidate object and emitted
manifests retain the new publisher hash. Partial namespaces, mixed cohorts, changed
other members and unknown publisher hashes do not receive compatibility.

The current default107 manifest/inventory bind the actual publisher. The separate
historical102 fixture restores its original protected19070-byte module from
`rollout/preimages/support_bundle_e5e6153.py`, identical to the integration root's
retained preimage. Historical95 already carries its own distinct module; its
manifest and assertions remain unchanged. This is not permission to relabel a
historical installed generation.

After the evidenced build failure at `validate_go_base_manifest`, the source-only
Go109 and HTTP112 builds completed successfully. Their manifests retain the new
publisher module, with SHA256 `c7871dc79fcd64f38ded3ef6afc1700356e5fefa9eff0e8bd3af96fb768218f9`
and `df8f18de6ce2f6c248344a01b2314f98f0900595d3c457a15e013b74fd7d9210`, respectively.
These are this isolated candidate's build receipts, **not** the active APPLICATION
root's different107/109/112 composition, installation or service qualification.
The final joined source must preserve both contributions and be regenerated by the
existing root. Authored regression coverage checks exact-cohort recognition,
unchanged caller manifests, legacy validation, mixed-source refusal and unknown
publisher rejection; it is not claimed executed before hosted CI concludes.
