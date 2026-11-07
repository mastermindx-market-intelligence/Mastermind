# Preserving Studio native-pool pin transition

`private_service.py native-pool-pin` changes one existing
`fleetStatus.fabricLauncherSha256` and the sealed manifest's `configHash`.
It preserves every other config value, manifest field, gateway/backend/module,
plist, executable, dependency and original file mode. It does not enroll a seat,
rebuild capabilities, stop/start a service, alter pool/task ingress, select a
generation, invoke a provider, or dispatch a worker.

The exact ten-seat cohort is recorded in `NATIVE_POOL_PIN_ACCOUNTS`. Five previously
unsupported legacy profiles are recognized only by exact account, V2 schema and
complete module digest map. This compatibility permits preserving lifecycle and
pin operations; generic stage/upgrade of these profiles remains refused. It does
not ratify an unknown account or an arbitrary file collection. Existing source
pointers can be mutable and are not proof of historical producer bytes.

Use the **actual protected source owner**, not a modified control launcher or a
restaged gateway. The companion `private_service_pin.py` must be present in the
same protected source package. Run this native owner from the clean, full
protected source checkout owned by the native-kit user (UID501 on this M2).
The Root-owned installed Control SDK has different source custody; the native
successor verifier requires its launcher source to be owned by its caller.
Do not change ownership or copy an installed SDK to bypass that requirement.
No gateway/backend bytes are replaced.

The existing `fabric-design` and `fabric-read` seats retain their sealed
`tailnet-gateway.mjs` launchers. Pin and normal start/stop/seal dispatch recognize
only each account's exact original and pin-post canonical manifest states,
source/module map and complete existing config/plist/runtime/dependency seal.
Their argv remains exactly node, that seat's Tailnet launcher and its config.
The private verifier stays private-only; no arbitrary argv/profile fallback or
generic stage/upgrade admission is added. Both Tailnet wrappers fix backendMode
to shared-account before starting the backend; neither this source fact nor a
passing static seal clears retained results or proves runtime quiescence.

## Preconditions owned by the release operator

1. Preserve all known active/unknown operations, original generations, launchers,
   controller/result carriers and receipts. This is consequence-scoped, not a
   demand that all Fabric workers be idle.
2. Account for live work on each Studio seat before its normal stop. A loaded
   gateway is not an idle gateway. The installed `private-tunnel-gateway`
   wrappers (`fd4eb541…` / `225b1a59…`) normalize an absent `backendMode` to
   **shared-account** before `startGateway`; that overrides the bare gateway's
   default. Fixed private auth binds that seat's frontends to `tunnel:<account>`,
   sharing one healthy `BackendOwner` and local Desktop Commander handle map.
   The original local frontend's `list_sessions` and `list_searches` cover that
   shared backend generation, not other accounts or separately selected remote
   routes. `list_sessions` exposes active terminals, not retained completed
   output; `list_searches` includes retained search entries, including complete
   ones. Preserve known active/unknown operations and original result carriers,
   including completed but unread results, before a normal gateway stop destroys
   the shared backend. Reclaimable frontend shells can coexist with live shared
   handles: neither `active == reclaimable` nor `busy == 0` proves backend
   quiescence. `/readyz` counts are observations, not a drain barrier. No hot
   reload or new drain/control plane is added.
   Historical C3 adoption retains 512 unresolved slots and generation bindings;
   it has no all-ingress fence. Bind any concrete conflict to the actually loaded
   gateway generation/PID and original known handle carrier. Neither an empty C2
   handle projection nor a historical label clears those effects; do not retry
   old outputs to manufacture clearance.
3. Root's newly verified native M2/UID501 foreground carrier owns any new C2 stop
   and its return. Never stop the C2-hosted controller that owns an unsettled
   command. Preserve any concrete unknown recovery that a restart would destroy;
   do not invent permanent holds from hypothetical cached results.
4. Use the authentic retained native successor bundle. Its verifier qualifies
   original bootstrap/upgrade history, native payload and CURRENT/ingress state.
   The old consumer pin may already differ from the current pool: observed
   `95dad5ac…` versus current `8533800b…` is existing binding drift, not health
   proof. The operation binds its **new** pin to the verified future bridge; it
   does not require the stale old consumer pin to equal current pool bytes.

## Per-seat sequence

Set `OWNER` to the protected `integrations/studio_direct_mcp/private_service.py`,
`ACCOUNT` to the intended existing account, and `M` to its freshly qualified raw
manifest SHA256. Root's current retained successor operand is
`/Volumes/Mastermind/evidence/mmos-commission-01a15741/b11-successor-8072eed8-28faaf10`,
plan `77c2c136852a783a1e2572c145af7536ee6cd0d7f443daa4c09795c333fd3dc7`.
These are source-linked operands, not a claim they still qualify at action time.

```sh
python3 -B "$OWNER" native-pool-pin --operation preview --account "$ACCOUNT" \
  --expected-manifest-sha256 "$M" --successor-bundle "$BUNDLE" \
  --successor-plan-sha256 "$SUCCESSOR_PLAN"
```

Preview is read-only DATA, may run while loaded, and emits a bounded plan digest
without config/args/env/grants. Retain the returned `planSha256` as `PIN_PLAN`.
After the operator's real per-seat quiescence qualification, use normal `stop`
through the native owner carrier and consume its actual completion. The pin
operation independently requires strict positive **unloaded** evidence.

```sh
python3 -B "$OWNER" native-pool-pin --operation apply --account "$ACCOUNT" \
  --expected-manifest-sha256 "$M" --successor-bundle "$BUNDLE" \
  --successor-plan-sha256 "$SUCCESSOR_PLAN" --expected-plan-sha256 "$PIN_PLAN"
```

Apply holds the existing seat lifecycle mutex and native publication lock;
requalifies the native successor/CURRENT/ingress, original seals and stopped
state; persists closed immutable plan/beforeimages/postimages/intent; changes
config; and commits the manifest last. The private directory and locks serialize
cooperative owners. They do not claim atomic CAS against an adversarial same UID.
No service is started. Starting a seat with an owned future-pin postimage is
refused until the native successor is selected and the actual pool bridge
matches. Untouched incumbent pin drift retains its previous start behavior.

## Lost response or interruption

Use the same account, bundle, original manifest and reviewed plan arguments with
`--operation status`. This is a read-only observation distinguishing OLD,
CONFIG_ONLY and COMPLETE; foreign or unsafe state is refused. OLD reports
`NOT_APPLIED`, CONFIG_ONLY reports `PARTIAL` (the config has changed), and
COMPLETE reports `APPLIED`. `receiptCommitted` separately identifies whether the
durable terminal receipt exists; a complete pair with a lost receipt still needs
same-transaction reconciliation before global successor execution. A terminal result
paired with reverted bytes is refused, never replayed. Repeating `apply` against
an existing transaction is refused. Missing/unreadable staging data is not proof
that an effect never occurred.

Only `--operation reconcile` may finish this exact intended transaction, after
fresh successor binding, strict stopped proof, complete before/postimage checks
and unchanged static seals. It never overwrites foreign drift or normalizes an
unrelated configuration. After-manifest receipt loss is completed without
rewriting the pair. Retain any unknown/foreign state on this original transaction;
no blind retry, new identity, raw config edit or generic upgrade is authorized.

## Global successor and resume

Ten seats are **not atomic**. Retain explicit per-seat results and completion
receipts; do not infer all-seat completion from a successful loop invocation or
from zero conflicting config pins while a seat transaction is unsettled. Only
after all intended seat results are settled may Root repeat the normal complete
Studio consumer census and execute the **same** qualified native successor.
Publication locking prevents the live manifest-last window from racing native
selection; a crash still requires original transaction reconciliation before the
operator proceeds. No bare `select` or replay of the old bootstrap/upgrade.

After actual native successor completion and receipt/CURRENT/ingress verification,
resume seats through normal `start` using the protected preserving owner. Its
future-pin fence authenticates the retained transaction and native selected
bridge before any bootstrap/kickstart. Consume actual outcomes and qualify the
new C2 tool path before releasing the native return carrier. The source protocol
and temp-seat tests do not prove host quiescence, service health, provider
readiness, native OAuth, a canary or product acceptance.
