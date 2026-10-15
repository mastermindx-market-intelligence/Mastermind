# Preserve recorded lineage while a Fabric worker is active

An active run reported null root and parent because the adapter populated those fields only from its terminal acceptance projection. Some artifact runs already retained a validated `LAUNCH_BINDING` before launch. This patch exposes that existing record in a separate `controller_lineage` object, with state `RECORDED_PRE_LAUNCH` and `is_authentication: false`. The original top-level root and parent remain null until their existing terminal verification succeeds. Acceptance stays `UNVERIFIED` and worker state stays `UNKNOWN`. This distinction preserves the native connector's existing root-verification and result-access checks.

The reader uses the existing local evidence reader, requires a private single-link file, and checks stable bytes and file identity. It requires exactly one complete binding with the original run and host, the existing schema and fields, and ordered reservation, lease and support events before the binding. Missing, partial, ambiguous, unsafe or changing evidence leaves lineage unverified. Plain packets and historical missing records are unchanged. It does not reconstruct provenance or modify an original run.

The companion diagnostic preserves the existing closed observation scopes and exit code 75, but reports `observation_scope_not_admitted` when that exact pre-transport check refuses a request. Other observation failures retain their current generic reason. No scope, transport, routing, lease, retry, result or acceptance operation is added.

## Qualification and release

`SOURCE_INTAKE.json` pins the installed preimages and unchanged dependencies. `candidate/` contains the two proposed files; `active-lineage.patch` is the exact zero-context delta (`git apply --unidiff-zero` after preimage verification). `SOURCE_VERIFICATION.json` records affected checks and tested hashes. The tests use the existing installed producer and public dependencies, with disposable private test data and no remote operations:

```sh
python3 -m pytest -q research/fabric_active_lineage_20261015/test_active_lineage.py
```

This is local qualification, not a claim that hosted CI contains the installed kit. Three discriminating checks fail on the installed baseline. Negatives cover missing and malformed bindings, conflicting identity and event ordering, partial logs, duplicate JSON keys, unsafe file metadata, changing reads, existing producer rejection, and uncertain-effect preservation. The source check confirms existing adapter functions are unchanged except the additive active projection, and all historical observation scope assignments are unchanged.

The candidate is uninstalled. Normal protected release, current preimage/custody reconciliation and the existing adapter installation path remain necessary. A changed adapter hash also needs the existing Stop-hook pin/trust workflow; this source change does not confer hook trust. It does not inspect or repair another parent's pending run, and it does not prove authenticated native same-chat delivery or acceptance.
