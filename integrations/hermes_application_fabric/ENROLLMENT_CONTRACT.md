# Hermes attended APPLICATION enrollment contract

Prepared for the original APPLICATION integration in Macro #10740 and
Mastermind #983. This is a consumer contract, not a second owner or an enrollment.

Source anchors:
- Macro original PR head: `2ef828e569b683b9dfaa94f81116da3ac55f6186`.
- Macro retained AUTO source: `1d09f389b8e90bc579fc62511a76102fba73347d`.
- Hermes consumer #2155, attended follow-on #2166.

## Exact first consumer

| Field | Required value or meaning |
|---|---|
| Production mode | `shared_fabric` |
| Service record | `hermes_attended_fabric` |
| Lane | `hermes-attended` |
| Workload profile | `hermes_attended` |
| Execution surface | `inference` (Hermes still owns its agent/tools) |
| Provider order | Exactly `["fabric"]` |
| Protocol | Original `native_application_v1` |
| Operation ID | Original native Hermes admitted-input ID |
| Model | Exact owner-qualified GLM Flash model on OpenCode Go, initially strict |
| Physical account | Selected and atomically reserved by original native account owner |
| Service credential | Dedicated original owner credential; never a user-provider key copied into Hermes |
| Recovery | Original operation/session, no new admission after unknown effects |

The installed public Go model list contains `glm-5.3-flash` and `glm-5.3`.
That does not prove serving entitlement or usage accounting. The first useful
live slice must prove the GLM Flash route the user intends; a DeepSeek-only
canary would prove plumbing but not that product behavior.

## Changes to integrate in the active owner

The active original writer owns the central tables and native service principal.
Add the relation to `_SERVICE_FABRIC_RELATIONS`, the inference workload to
`config/provider_workloads.v1.json`, its closed transport identity to
`_APPLICATION_FABRIC_TRANSPORTS`, its capability in
`config/capability_manifest.yml`, and its matching application record in
`config/provider_production_modes.v1.json`.

Keep source qualification and application permission false, and config disabled,
until the real service route earns qualification through the original procedure.
The consumer cannot supply a qualification dictionary, URL, key or model override
to manufacture that result. No site/Brain/Ask identity may be reused for Hermes.

The inspected fixed native transports pin `deepseek-v4.1-flash` and
`http://127.0.0.1:50142/v1`. The complete endpoint selected by the attended
transport must be inspected and proved. Port 4142 alone is not that proof.

## Model constraint and account balancing

The fixed-model owner v1 binding contains `model`. The retained AUTO v2 owner
returns `schema/client/inspection`, requires `requested_model=None`, and
constrains pools. The current Hermes binding requires `inspected["model"]`
and `bound["model"]` and refuses strict_pool. These schemas cannot be joined by
configuration.

First qualify strict GLM Flash with original OpenCode C1/C2/C3 selection, atomic
shared capacity reservation, and observed account attribution. Subsequent model
routing requires an original owner contract that represents model and pool
constraints separately, commits both to request/inspection identity, and checks
them before ranking physical accounts. Alias models must share the same true
quota bucket; do not multiply capacity by listing the same account twice.

Official Z.AI GLM 5.3 requires its own application protocol/tool/usage and account
qualification through the existing GLM owner. The three discovered worker
accounts do not prove application eligibility, and one account's unknown cap
must not be counted as available headroom.

Experiential remains under its existing explicit/manual-use conditions. It was
absent from the inspected AUTO pool allowlist and its proxy was unqualified.
Do not make it automatic overflow as part of this enrollment.

## Acceptance owed

1. Exact installed source and admitted service/principal/workload/route receipts.
2. Real GLM Flash inference, a native Hermes tool request/result round trip, and
   usage/account attribution from the original owner.
3. Overlapping admitted turns demonstrating eligible physical-account selection,
   shared limits with worker traffic, and no account overcommit.
4. Pre-dispatch exhaustion/refusal and post-dispatch unknown-effect cases showing
   no replay, account switch, new operation or premature lease release.
5. Original close/settlement receipt, then normal CLI/gateway user-path proof.
6. A separate qualified GLM 5.3 slice; Experiential only under its accepted policy.

Original C1/C3/C4, collection and release holds are preserved. This source-linked
contract does not assign a new writer, arm merge, issue a grant or start a service.
