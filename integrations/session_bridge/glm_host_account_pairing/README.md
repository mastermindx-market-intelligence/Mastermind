# Existing GLM host/account pairing

The host picker used launcher availability independently of the account broker. A host could therefore win placement despite not containing the exact selected GLM account. The earlier installed post-lease guard now refuses this safely, but cannot choose a compatible pair.

This component adds nonsecret readiness to the existing host collector, using the exact pinned validator code and original launcher PATH/HOST_ENV/GLM_CONFIG. No credentials move, provider request is made, account is provisioned or new collector is created. Held/invalid host modes do not receive the config observation. The same bounded stable owned observation is intersected with existing candidates in the picker and broker. The broker checks compatibility before capacity demand; actual model/account caps, fair share and ordering remain its existing logic. Explicit preference does not fall back. The post-lease guard remains installed to catch config changes after observation. GLM-Codex has a different authentication path and is unchanged.

Readiness is local configuration evidence, not provider authentication, a RuntimeBinding, Control issuer, WorkerRef or entitlement. Missing/stale/unsafe/foreign observations refuse new MODE glm pairs. Existing workers, leases and frozen failures are untouched. Normal other-provider routing remains available.

Apply the patch only to exact manifest preimages after review. Publish/refresh the existing collector and qualify actual observations before installing selector/broker gating; preserve the sole existing launchd service. This package is source qualification, not an installation claim. Do not install the separate unreviewed/held expiry-selector proposal #1365 or overwrite newer bytes.

The paid direct coordinator-to-worker return and coordinator correction are retained separately in the manifest; the corrected predicate contract has33 tests. The parent wiring tests cover real fixture projection through the broker, explicit preference, model room, root conservation, unavailable-vs-capacity behavior, unsafe sources and structural mode holds.

Frozen preimages and the inert predicate contract live under `tests/fixtures/glm_host_account_pairing/`; moving test inputs does not alter installed runtime bytes.
