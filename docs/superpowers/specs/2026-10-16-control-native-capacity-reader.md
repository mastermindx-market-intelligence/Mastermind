# Fixed Control acquisition of the existing native observation

The existing `AttendedControlProbeSource.native_observation(physical)` reads
one current same-host native observation through the fixed Bridge. No RPC,
environment, CLI, model output or caller JSON chooses a path, source, time,
identity, endpoint, status or callback. The current root Control definition and
attestation first identify the pinned Worker definition. That same owner reads
the already-published registration via the existing Capacity source reader.

The actual client reuses the existing protected socket namespace and kernel
peer UID contract. Only the client permits the Bridge-specific read operation;
the ordinary Worker Broker server gains no new operation or handler. The
request contains a fresh nonce only. There is one request and no read retry,
provider invocation, persistent cache, new listener or lifecycle owner.

The returned closed observation must match the nonce, host, current local
kernel boot, capability identity and generation, realm generation, source
receipt and B2 enrollment digest from the pinned definition/source. Recomputing
that public digest is a consistency check, not an independent issuer or bearer
authentication. Control/Worker source currentness and boot are checked again
before return. The entire query and revalidation interval must fit the existing
15-second observation lifetime, with the existing two-second clock tolerance.
Unknown provider facts remain unknown; neither this acquisition nor a source
hash grants availability, admission, a claim or authority to start work.

Worker-side custody remains with `SubscriptionRealmOwner`; Control does not
impersonate its UID, open its credential, or mint a Worker owner. A private
shared registration reader keeps the existing source parsing/digest/revocation
logic identical for the two real owners. Default installed Control startup does
not call this method or select the dormant native worker. No schema migration,
physical-policy activation, Runtime mutation, Desktop parent enrollment or
GUI writer-fence provider is introduced.

Tests execute the actual async client and Worker Bridge/realm/source producer,
with kernel identity and protected-file ownership virtualized. They reject a
foreign peer before sending bytes, altered nonce/scope/generation/digest, stale
or future time, source revocation, clock jumps, and expiry during revalidation.
Control startup validation retains its existing tests; its sealed definition
is a fixture boundary in the new read-path composition tests. These checks are
source qualification, not live Mac enrollment or an exact-parent result proof.
