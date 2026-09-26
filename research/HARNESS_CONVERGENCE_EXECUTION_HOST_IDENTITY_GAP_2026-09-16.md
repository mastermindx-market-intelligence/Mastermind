# Harness convergence: execution-host identity gap

**Disposition:** DRAFT / RECORDS ONLY / AUTHOR-SIDE DISCOVERY / PRODUCTION INERT. This record continues `harness-convergence-dsh-teardown-20260916-sol-001` and narrows the A2 factor-identity claim. It does not create a host registry, runtime identity, provider turn, route, Worker, Capacity grant, Agent OS write, merge authority or production capability.

**Protected source basis:** Mastermind `8ba7deedde164c90298d3e88785d98e02fa5e2d2`, Skillpack `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap major 1.

## 1. Discovery

Current protected source contains all of the following pieces, but not one canonical proof that joins them into a causal execution-host identity:

1. **Capacity / MH1 host identity.** MH1 binds an already-selected opaque `host_ref` to the existing Job/Attempt/Worker/operation transport. The remote transport is explicitly forbidden from creating or changing host identity.
2. **Host-capacity evidence.** `mastermind.host_capacity_snapshot/v1` binds caller-supplied `host_ref` + `boot_ref` to a bounded host observation. The host-pressure/capacity runbooks explicitly state that those refs must come from an existing authorized host/Runtime binding owner; the probe does not derive organizational identity from hostname, serial, address or process title.
3. **Executive process identity.** sealed Worker and rich OHF paths already observe real `pid`, `pgid`, `process_start_identity`, and OS `boot_id`/boot-session identity. `mastermind.operator_materialization_receipt/v1` durably binds that process identity to Attempt/Worker/process-generation/provider-session and observed harness/auth evidence.
4. **Agent Evaluation run identity.** run v1 has content-addressed evidence plus process/native-session fingerprints, but it does not carry a canonical Executive Job/Attempt/Worker/host binding.
5. **Fresh-Sol reference producer weakness.** `scripts/ohf/fresh_sol_eval.py` currently writes a synthetic `process_start_identity` built from PID/PGID/run id for its historical lab artifact. That is not the same proof as the boot-scoped OS process identity used by Executive Worker/OHF Runtime.

The missing seam is therefore not “collect host metrics” and not “add host fields to Agent Eval.” It is:

```text
existing authorized host_ref
+ existing OS boot/process identity
+ exact Executive/OHF execution identity
-> owner-native, content-addressed execution-host attestation
```

No accepted protected source observed in this review currently proves the mapping from the raw process boot identity to the opaque `boot_ref` used by host-capacity evidence, nor proves a direct Fresh-Sol run process belongs to the supplied host snapshot merely because that snapshot digest is attached to the run.

## 2. Consequence for PR #692

Implementation PR #692 (`[AGENT-EVAL][A2] Verify host-generation evidence locks`) is intentionally narrower after this discovery.

Its valid claim is:

```text
HOST_FACTOR_EVIDENCE_LOCK_VERIFIED
= both finalized run receipts immutably bind owner-valid host-capacity snapshot bytes
  AND those snapshots identify the same host_ref + boot_ref.
```

It must **not** be interpreted as:

```text
EXECUTION_HOST_FACTOR_LOCK_VERIFIED
PROCESS_EXECUTED_ON_HOST_PROVEN
MODEL_EFFECT_READY
HARNESS_EFFECT_READY
```

A run can bind a valid snapshot digest without that alone proving the run process executed on the referenced host. The verifier correctly treats that as an evidence relationship, not causal process-host proof.

## 3. Owner boundary

Do not fix this by:

- hashing hostname/serial/IP/MAC inside Agent Evaluation;
- letting the host probe mint `host_ref` or `boot_ref`;
- adding a second host registry;
- adding provider-private host fields to Agent Eval configuration/run v1;
- trusting a caller-supplied snapshot path or host label;
- treating MH1 network endpoint/certificate identity as Capacity host identity;
- treating the Fresh-Sol lab's synthetic process identity as equivalent to Executive process identity.

The eventual producer must compose existing owners:

- **Capacity / Runtime binding** supplies the already-authorized opaque `host_ref`;
- **Executive Worker/OHF process owner** supplies boot-scoped process identity;
- **host identity owner** supplies or validates the opaque `boot_ref` generation mapping;
- **Agent Evaluation** only content-addresses and verifies the resulting evidence.

If current protected architecture truly has no accepted owner for the `boot_id -> boot_ref` mapping, that is a Runtime/Capacity identity gap to implement once at its canonical owner, not an Agent Evaluation exception.

## 4. Experiment qualification ruling

Until the missing owner-native execution-host attestation exists:

- `HOST_FACTOR_EVIDENCE_LOCK_VERIFIED` is useful for detecting obvious host-snapshot drift and for preregistered evidence completeness;
- it is **insufficient by itself** to label a comparison `MODEL_EFFECT`, `HARNESS_EFFECT`, or crossed `INTERACTION` when execution-host equality is load-bearing;
- a comparison may still proceed as `SYSTEM_REALISTIC` / `WHOLE_SYSTEM` if normal host variation is intentionally part of the treatment and actual observed host evidence is reported honestly;
- no favorable result may promote itself post hoc from whole-system evidence to a cleaner causal class.

## 5. Lane-specific forward path

Do not force every backend through one host proof mechanism.

### Rich Operator / OHF

The strongest current producer substrate is `mastermind.operator_materialization_receipt/v1`, which already binds:

- Attempt/Worker/session epoch/process generation;
- real process identity including boot id;
- provider session;
- observed harness/config/auth attestation;
- process principal and provider-home identity.

A later Runtime/Capacity bridge can bind the canonical host generation to that receipt without changing OHF v1 or Agent Eval v1.

### Sealed Worker

Use existing Worker launch/process/Attempt evidence plus the already-selected Worker/Capacity `host_ref`; do not fake an OHF materialization receipt for a sealed process.

### Direct laboratory runners

A direct lab that cannot consume canonical Runtime/Capacity host identity remains laboratory evidence. It does not gain execution-host causal authority by accepting a `--host-ref` argument.

## 6. Next implementation order

1. Let #692 prove only the immutable host-snapshot evidence lock and keep it production inert.
2. Continue A2 on dimensions whose owner-native evidence already exists end-to-end, especially provider/auth realm identity from OHF materialization receipts.
3. Separately reconcile the canonical Runtime/Capacity owner for execution-host generation identity before implementing a generic process-to-host attestation.
4. Once that owner exists, add one producer + one real Agent Eval consumer and negative tests; do not merely add fields.
5. Only after all preregistered load-bearing factors have owner-native proof may a factor block use `MODEL_EFFECT`, `HARNESS_EFFECT`, or `INTERACTION` labels.

## 7. Capability state

- host-capacity evidence source: **BUILT / protected source**;
- Executive/OHF process identity: **BUILT / protected source**;
- #692 run-to-host-snapshot evidence lock: **BUILT_NOT_PROVEN** pending exact-head hosted CI at time of this record;
- canonical process-to-opaque-host-generation attestation: **NOT_BUILT / owner gap not yet reconciled**;
- causal execution-host factor equality for harness convergence: **NOT_PROVEN**.
