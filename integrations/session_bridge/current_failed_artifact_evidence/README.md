# Current source evidence from one failed Fabric operation

The original Research Factory parent requested the two bounded files from
`rf-static-checks-01a1333c-v1`. Its worker process exited zero and cleaned up;
the outer artifact-production contract failed with rc65. The ordinary successful
artifact exporter must continue refusing that operation. The original encoded
packet is unavailable, so no historical artifact-production attestation is made.

This finite profile implements the separately reviewed **current owner source
read** through the incumbent `capsule-artifacts` → `--capsule-current` entry.
It does not retry the ordinary success export. It joins the pinned private log
and process metadata to the existing adapter's nonzero terminal lineage, reads
exactly the two requested `/tmp` files through the unchanged bounded reader,
and compares their current bytes with the owner's requested sizes/digests.
Source constants and transport labels restrict scope; they do not authenticate
a caller or create authority. The actual assigning owner's request was received
and reviewed independently. That parent performs the one retrieval and reviews
the returned code as untrusted source. Before reservation, the invocation must
carry that parent's `CODEX_THREAD_ID` and no conflicting inherited
`POOL_ORCHESTRATOR_ID`. These checks enforce caller correlation, not authentication.

Only the exact destination in the module is permitted. The existing exclusive
directory/request/receipt publication retains an attempted read and prevents a
second invocation through a different output directory. A real owner/mode/type,
permission, content, or publication failure remains a refusal. No chmod, rehome,
raw transfer, alternate identity, controller action, ledger mutation or new
worker is part of this operation.

`COMPLETE` means both current files match the requested content constraints.
Every receipt keeps the original rc65, `stdout_reverified:false`,
`producer_manifest_verified:false`, `historical_worker_bytes_attested:false`,
`original_operation_mutated:false`, and `outcome_accepted:false`. The existing
reader schema's stdout digest is only owner-supplied correlation, never a
verified stdout or historical seal. Ordinary exports and Paper/bridge capsule
profiles are unchanged. The adapter and trusted Stop hook are unchanged.

The integration patch applies only to the exact artifact-delivery preimage
recorded in `SOURCE_MANIFEST.json` (zero-context diff; apply with
`git apply --unidiff-zero` only after the preimage check). Do not apply it over
another writer's bytes.
The candidate tests use that retained preimage with this patch and the exact
unchanged artifact reader, with all host transport replaced by inert responses:

```sh
RF_EVIDENCE_CANDIDATE=<qualified-local-candidate-directory> python3 -m pytest -q \
  integrations/session_bridge/current_failed_artifact_evidence/test_current_failed_artifact_evidence.py
```

The candidate directory contains `artifact_delivery.py` (patched preimage) and
`baseline-artifact_reader.py` (the pinned unchanged reader). Test fixtures must
be on a private safe directory chain, for example with `--basetemp` inside the
existing external evidence directory. Source qualification and actual local
original-metadata qualification do not prove remote retrieval or parent
consumption; those are recorded separately after the assigning parent's read.
