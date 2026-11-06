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

There is deliberately **no apply, rotate, enable, reload, reset or retry command** here. The existing native generation builder, installer prepare/apply/reconcile operations, account/credential owner, physical admission lock, lease ledger and original application-turn owner retain their jobs. Do not copy an arbitrary candidate over installed `pools.yaml`, infer that old leases are absent, bind a replacement key to an active turn, or replay an unknown request based on this preview.

The original #2060/#10740 application-selection/enrollment migration and #2109 OS view retain their source writers. This additive module, its focused tests and this runbook do not edit their picker, broker, installer, generation manifests, authentication or UI files. Native model/pool activation, key-reference generation changes, drain/rollback and installed consumer proof remain separate required programme work.

## Evidence at authoring

Actual operator invocation read the existing public routing source selected from the incumbent installed pool launcher's kit. It returned ten configured IDs (`bailian`, `claude`, `claude-native`, `codex-native`, `cursor`, `glm`, `go`, `grok`, `minimax`, `ocfree`), source SHA256 `db4e4b1768809bd991003ef045568b480cdb42ea0715a6b73ea5353930bf90d8` and incumbent critical SHA256 `7433fc62d515d8872c68d4e1fb7a6fcbac0c07187cbaf1b6497df5dd0b7fca36`. A same-source preview returned `UNCHANGED`, no changed pools and no requirements. These are dated source observations, not permanent current revisions or live capacity proof.

Both new Python files passed AST parsing. Regression cases are authored for current/candidate drift, native critical/noncritical semantics, source formatting, pool/model changes, invalid graphs, credential material, symlinks and actual CLI composition. No discretionary test suite was executed under the Chairman's existing instruction. Hosted CI results must be read for the exact published head before claiming those cases passed. No account configuration, secret resolver, provider call, lease mutation, service installation or production deployment was performed by this slice.
