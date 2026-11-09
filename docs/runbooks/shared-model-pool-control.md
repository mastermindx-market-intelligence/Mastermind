# Shared model-pool configuration inspection

Programme: [Mastermind #983](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983).
Task tree: [SHARED_MODEL_POOL_CONTROL.md](../SHARED_MODEL_POOL_CONTROL.md).

## Implemented command

From the authorized Mastermind source or installed release, use its Python environment:

```sh
python -m ops.executive_os.model_pool_control inspect --summary
python -m ops.executive_os.model_pool_control inspect
```

The command invokes the actual `ModelRouter` validator and capability registry. It returns logical provider aliases, model aliases, workload routes, a semantic configuration revision and the capability-policy digest. It does not read a second catalog or copy credentials. The summary omits source paths, account identifiers and raw configuration. Its `physical_account_pools: NOT_JOINED` and `live_capacity: NOT_OBSERVED` are deliberate: configured aliases do not prove current paid capacity, application permission, enrollment or an available worker.

To inspect a candidate created through the existing source/configuration workflow, copy the current `revision` from inspect into the expected-revision argument:

```sh
python -m ops.executive_os.model_pool_control preview \
  --candidate /absolute/path/to/reviewed-candidate-routes.json \
  --expected-revision <current-revision>
```

`--policy` and `--capabilities` select operator-owned source files when inspecting a particular release. `--candidate-capabilities` is explicit for a capability-source change. These are local host-admin inputs, not model-facing remote-tool arguments. No key-file, token, account override, provider endpoint, activation flag, or retry destination is accepted.

The command emits added/removed/changed provider and model aliases and workload routes. Changes to a provider affect its existing aliases; profile/capability changes are kept visible. Affected existing aliases require their incumbent operation owner to retain the original revision or drain work before rebinding. Newly executable/changed aliases require actual runtime/capacity/profile qualification. A valid preview always has `activation_authorized: false` and `writes_applied: false`.

`preview` of the current file is `UNCHANGED` and has no required change effects. A stale expected revision refuses. Errors are fixed codes without copied backend exception text, paths or source contents. Neither inspect nor preview publishes, reloads, starts a worker, acquires a lease, issues a model request, generates a key, or changes any original operation.

## Coherent source observation

The existing `ModelRouter.load` now reads bounded regular-file JSON through an open descriptor and checks file identity/size/mtime/ctime during the read and after validation. Duplicate keys, nonfinite values, malformed UTF-8, excessive size/depth and source movement are refused. It does not recover removed eligibility by substituting a cached policy. Configuration inspection additionally brackets the original capability-policy loader and verifies both source identities before releasing its response.

The revision is calculated from the normalized, owner-validated routing facts plus the capability-policy digest. Whitespace does not create a different semantic policy. Publication still needs the original publisher's exact source/blob fences; the semantic revision does not replace Git CAS, credential generation or Runtime admission.

## Safe operational change sequence

1. Inspect the current existing-owner revision and candidate impact.
2. Change the canonical provider/model/routing data through its current source/configuration publisher. Preserve the exact baseline and existing permission/qualification evidence. Unsupported adapters remain refused; arbitrary provider strings do not create implementations.
3. Publish and activate only through the original release/configuration owner. Let admitted operations retain their original identities and credential generation; do not reroute an unknown outcome. Existing active jobs are not changed by this command.
4. Inspect the resulting owner revision and separately verify runtime/account/capacity facts. A configuration change is not proof of a successful inference.

## Key rotation and native pools: separate remaining integration

This slice does **not** add a new key store or perform live key rotation. Provider credentials remain at their current account owners. Reference/generation changes must be joined through the existing native broker, application grant and finite enrollment transactions. Adding another copy of the same key does not add capacity and is not the solution.

The native picker/account configuration and application selection/enrollment are active under PR #2060 and its original #983 tasks. Their held source paths were not edited here. The broader programme still needs coherent native pool/account generations, shared account/lease limits, drain/rotation publication and the Mastermind OS management surface. This command is working configuration inspection/change preview, **not** a claim of a completed all-pool runtime migration.

## Evidence and run posture

The command was invoked against the actual checked-in policy: nine logical provider aliases, fifteen model aliases, five workload routes. An unchanged candidate preview returned `UNCHANGED`, preserving the same revision. No private credential or provider request was used. No discretionary test suite was run under the Chairman's current instruction. Existing required hosted CI/security rules remain in force; unrun safety cases and live activation are not reported as passing.

## Mastermind OS configured-routing read

The existing Fleet & Capacity view now mounts `ModelConfigurationRead`. It performs an explicit authenticated read of the fixed `/workspace/resources/models/current` route; no polling, local registry, credential input or model call is created. Web OAuth and the native Tauri reader use the incumbent Workspace acquisition identity, invalidation generation and before/after release checks. Sign-out, revocation or generation movement withholds the response and clears the rendered result.

The fixed route is composed through the existing Workspace App → App-peer Unix client → Executive service → WorkspaceReadService → ModelRouter configuration owner. It accepts no selectors, policy paths, provider credentials or mutable operation. The existing backend ModelRouter default source path is the same one used by its routing selectors, not the frontend checkout. The returned policy is still **configured routing**, not proof of the selected policy of every already-admitted Job/Attempt or a current physical paid account inventory.

The panel includes provider/model/workload counts, model/capability search, provider filtering, bounded incremental display, profile/capability source digests, workload tiers and policy revision. It labels native physical accounts as not joined and live capacity as not observed. Publication, draining, reference rotation and actual runtime admission remain outside this GET. The authenticated account permissions are unchanged; a Workspace member read does not gain COO submission or a provider key.

Actual source evidence for this vertical: the backend reader produced an AVAILABLE result validated by the closed public wire contract, retaining revision `39d5204a3357ab5873f307484b3aea19eb8d4540cc41b3370198e82d658ecc52` with 15 configured model aliases. The full web production build (`tsc -p tsconfig.build.json && vite build`) succeeded. Its existing large-chunk/dynamic-import warnings were not hidden. No discretionary test suite or live identity/provider call was performed. A successful source build is not deployed browser, desktop binary or installed authenticated HTTP proof; those remain release acceptance work.
