# T3 Code — registration with existing Capacity Fabric gateways

This package prepares native T3 Code provider entries for two existing local
gateway owners. It uses T3's `providerInstances` configuration and preserves
unrelated providers and the current default model selection.

## Ownership boundary

Each entry is a `claudeAgent` instance whose `ANTHROPIC_BASE_URL` points to an
existing gateway. That gateway retains its admission, credential and dispatch
rules. The registration adapter does not select between pools, create model
family aliases, maintain cooldown eligibility or dispatch with vendor keys.
A gateway refusal returns to the original caller; registration configures no
fallback or retry ladder.

The adapter reads the local gateway token and writes a `sensitive` environment
value through the existing T3 settings format. It does not author Keychain
records or create another credential store. Native runtime activation and
consumer acceptance remain separate from these source interfaces.

## Default endpoint bindings

| Endpoint | T3 instance | Gateway | Catalogue source |
|---|---|---|---|
| `anthropic_oauth` | `fabric_claude` | `http://127.0.0.1:8312` | Existing gateway's authenticated catalogue |
| `experiential` | `fabric_experiential` | `http://127.0.0.1:8311` | Exact operator-deployed `EXPLABS_ANTHROPIC_MODELS` list, or the existing authenticated catalogue path |

Additional providers require a qualified existing serving owner and its
original release/admission authority. Adding a configuration record does not
supply that authority. Current model counts and installed health must come
from the original gateway observations.

## Commands and effects

```bash
python -m integrations.t3_capacity_fabric status
python -m integrations.t3_capacity_fabric plan
python -m integrations.t3_capacity_fabric apply
python -m integrations.t3_capacity_fabric verify
```

`status` and `verify` observe the selected gateways and registration.
`plan` computes proposed changes without writing. An authorized `apply`
backs up `settings.json`, writes through the existing atomic configuration
path and creates separate provider home directories. It refuses unhealthy
gateways and preserves unrelated provider entries. These commands are source
capabilities; this PR's source recovery does not claim to have run them on an
installed runtime or prove that an existing T3 session consumed a new entry.

## Existing gateway wire contract

| Gateway | Wire | Admission owner |
|---|---|---|
| `127.0.0.1:8312` | Anthropic Messages | Existing Anthropic gateway and its account policy |
| `127.0.0.1:8311` | Anthropic Messages and the incumbent OpenAI endpoints | Existing Experiential durable per-key/shared RPM and request-policy owner |

The Experiential Anthropic surface admits only exact slugs in its deployed
catalogue. Its helpers live in
`ops/native_fabric/experiential_proxy/anthropic_policy.py` and reuse the
sealed policy's strict JSON/refusal primitives. Empty admission configuration,
routing overrides and unadmitted models are refused before reservation.
The existing optional Anthropic policy-digest header and required OpenAI
policy binding retain their original semantics. No historical native policy
or profile commitment is advanced by this protocol extension.

## Excluded proposal and runtime boundary

The earlier branch proposed a separate all-pools service and a default
`capacity_fabric` entry on port8313. That independent placement/direct-key
implementation is excluded from this delivery. Its historical source remains
at commit `ecbbbc0563c74db0945972ac4cd4481f0853a55f`.

Removing the source/default does not prove that any installed service stopped
or migrate an existing provider entry. Such effects must be reconciled with
the original owner and receipts. Broader cross-pool routing belongs with the
incumbent placement/admission owners. The read-only Capacity Fabric view
continues to report `admission_authorized=false`.
