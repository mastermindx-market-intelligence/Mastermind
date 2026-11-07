# Native host integration and account acceptance

The implementation runs through the existing Hermes and APPLICATION owners.
This document gives the source composition and concrete activation order. It
does not authorize a new credential store, account ledger, service or retry path.

## Fixed ownership

| Native role | APPLICATION profile/lane | Internal credential reference | Relay |
| --- | --- | --- | --- |
| mmsecretary | hermes-secretary | HERMES_SECRETARY_FABRIC_APPLICATION_TOKEN | 127.0.0.2:50142 |
| mmmeta | hermes-meta-ceo | HERMES_META_FABRIC_APPLICATION_TOKEN | 127.0.0.3:50142 |

The numeric addresses preserve the existing Linux role network isolation.
All three APPLICATION remotes, including the original 127.0.0.1:50142, use the
same incumbent tunnel client and native 127.0.0.1:4142 target. No public/provider
endpoint is placed in Hermes.

Source responsibilities:
- Adapter/host/tunnel: Mastermind #2155.
- Existing native enrollment extension: Mastermind #2186, stacked on #2175.
- Existing Macro factory/client declarations: Macro #10818, stacked on #10740.
- Final APPLICATION release/account/economic composition: #2175/#10740.
- Native worker delegation #2147, shared-pool policy #2109 and protected model
  packages keep their existing custody.

## Implemented host join

The existing installation v4 primary_application field holds a closed nonsecret
publication. It names the exact native role, enrollment request, principal,
held Macro root/commit, adapter package digest, model contract and token ceiling.
Optional Executive consumer composition and qualified vendor derivation remain
in their existing fields.

The native entry binds the adapter after native authority initialization.
The existing role/installation owner qualifies the publication and source.
host.py wraps the current native TurnRunner entry and cleanup:

1. Capture the actual enrolled session, native started admission, principal,
   authority epoch and execution generation. Native LOCAL source, approval owner
   and adopted-agent relationships must agree.
2. Make the original role-specific APPLICATION factory under its existing
   workload, qualification, entitlement and scope checks.
3. At the first real native request, bind once using native admission_id as
   APPLICATION operation_id; retain native session/task/turn/API IDs separately.
4. Recheck currentness and the keyless/fallback-free agent route before each call
   and before exposing executable tools.
5. Retain the same original owner through native facade rebuilds and recovery.
6. On exit, close only that owner. A local close or refused close does not prove
   provider cancellation, settlement or permission for a replacement turn.

The existing native result/session owner remains authoritative. Serving receipts
come from the original APPLICATION observation and are correlated to the exact
native request. A configured AUTO label, capability ID or provider profile is not
a physical-account receipt.

The closed primary publication supports three distinct forms:

| Publication | Native model | Owner contract |
| --- | --- | --- |
| v1 | Named fixed model | Original fixed inspection/binding |
| v2, routing.mode=auto | mastermind-fabric/auto | Null requested model, inspection/binding v2 |
| v3, routing.mode=exact | Concrete host-authorized model | with_requested_model before inspection, inspection/binding v3 |

V2/v3 routing also carries strict_pool, either null or a pool whose name must
match the owner's complete singleton scope. Hermes cannot narrow a broader
pool list itself. V3 never converts a concrete model to AUTO. Its original wire
model is unchanged, the selected and served models must match, and the original
owner's route v2 has routed_request_digest=null. Old v1/v2 publications are not
reinterpreted. The additional Qwen plaintext control form is not qualified for
Hermes tool conversations; unsupported reasoning kwargs still refuse.

## Existing dependency closure

The real held launch already supplies PyYAML 6.0.3 through
paid_yaml_runtime.held_yaml. release_manifest keeps that context alive around
native_gateway_entry.run, so the original Macro capability loader uses that
same verified module. Do not preload ambient YAML or add a second loader.
The isolated conversation harness does not enter that production bootstrap;
it installs the matching PyYAML version as an explicit fixture dependency.

Structured output additionally requires requirements.txt's jsonschema 4.26.0
and its complete resolved dependency set for the selected interpreter/platform.
The upstream Hermes lock does not guarantee those packages. Publish them in a
fresh immutable version of the existing third-party dependency tree, through
the current native import_roots and dependency_inventory fields. Preserve the
four-root limit and the exact held Macro root; do not edit a live qualified tree
or add a separate dependency registry. The current NativeSourceClosure verifies
all files and directory membership, including resolved native-extension bytes.

The existing release dependency preparation verifies a previously frozen
inventory; it does not download packages or bless new hashes discovered on the
host. Final installed proof must exercise both factory.inspect() in the held
YAML context and Draft202012Validator through that selected closure. An ordinary
venv import proves only the isolated source fixture. Missing schema support
already refuses before any provider request.

## Enrollment through the incumbent publisher

The closed v9 service specification has two forms: one fixed grant, or a typed
route scope plus bounded explicit grants. Both preserve role, principal, host,
APPLICATION purpose, site_interactive workload, lane, enabled state and the
original internal credential reference. The original accounts parser validates
models/accounts/grant overlap. The original operation owns token generation,
private binding, account publication and recovery.

For a fresh role, enroll its intended authorized scope once. The fixed factory
can run the first strict Go canary; later legitimate new turns can use AUTO with
that exact scope. A completed fixed slot cannot be rewritten into routed form.
No token remint, file deletion or remembered-ID replacement is an upgrade path.

v1–v8 family readers remain unchanged. Startup aggregates only completed role
slots and original family receipts, including absence snapshots. Partial
publication, conflicting physical owner or credential identity collision refuses.

## Same-owner tunnel successor

Use the original application_tunnel_control commands under their existing
authorized deploy carrier. The v2 selection is the closed --role-aliases flag;
there is no arbitrary address/port/destination input.

Before the successor:
- Retain the existing v1 client stage and apply receipts, server bundle/receipt,
  original credential bytes AND file identity, and lifecycle outcome.
- Qualify the exact existing Chisel client/server binaries for simultaneous
  closed remotes as well as the original authfile reload semantics.
- Build/verify the sealed source release carrying both compatible generations.

Finite sequence:
1. Stage v2 with --role-aliases and --predecessor-server-receipt. No --credential
   is accepted. The source-selected stage-hermes-v2 slot commits original receipt
   identities and retains the existing credential. Client staging consumes only
   the carried server receipt; it never reads the server's filesystem.
2. Stop/reconcile the original v1 client through its existing stop-client owner
   while its original config/plist still exist. A qualified absent observation
   after the original stop intent can settle an uncertain stop; it never causes
   another stop command. An uncertain original start remains held.
3. Carry the exact v2 server bundle to the original server owner. apply-server
   verifies the original server journal, account-independent transport identity,
   unchanged server process and exact authfile preimage. It preserves unrelated
   ACLs and adds only the .2/.3 rules to the original application identity.
   Existing listeners must be absent for the first ACL publication.
4. apply-client --role-aliases publishes the successor config/plist only after
   the original client is proven stopped. The credential is never replaced;
   equal bytes on a different inode are refused.
5. start-client --role-aliases uses the same launchd label and original
   credential, exact three-remotes argv and successor journal.
6. Reconcile the selected original journal after any lost reply. Committed
   writes with missing receipts are read back; no second ACL write, new
   credential, substitute service or repeated provider operation follows.

V1 and v2 share their existing purpose lock and retain separate immutable
generation journals beneath the same owner. V2 recovery uses its captured
preimages and candidates after the first write; it does not demand obsolete v1
live files. Empty/partial/full alias listeners are different from authenticated
APPLICATION success. A grant-file receipt does not assert tunnel/provider proof.

## Source integration and live qualification order

The proposals are reviewable source; tests do not activate their held transports.

1. Reconcile current #2175/#10740 and native/role writers, original request
   effects and existing release holds. Compose exact reviewed source into those
   original carriers, preserving newer protected changes and all historical
   native generations.
2. Obtain required protected-source/CI/release authorization under the existing
   rules. Do not self-approve, self-merge or repurpose another role's factory.
3. Build and qualify the existing native/release closures with role enrollment,
   factory/client, host adapter and compatible tunnel source. Private runtime
   credentials remain in their original owners.
4. Qualify one actual account and route, then publish the internal role grant
   through the original enrollment transaction and install through existing
   native/Hermes/tunnel lifecycle owners.
5. Enroll the actual Hermes session through the existing authenticated native
   command and perform the bounded original admission.
6. Execute and reconcile the acceptance journey below. Source success,
   STARTED, deployment and acceptance remain separate observations.

No part of this sequence authorizes bypassing active/unknown effects.

## Financial boundary required before the canary

The provider owner must supply a fresh receipt connecting the actual selected
physical account to the qualifying Go transport/configuration, Extra Usage OFF,
included headroom and its validity window. The source default Go endpoint is
https://opencode.ai/zen/go/v1, but GO_UPSTREAM_BASE is configurable; account
identity alone does not establish the financial boundary.

The existing owner must bind this policy to the original request/admission.
Hermes must not assert it via prompt text, headers or model arguments. The
declared quota scope can join multiple accounts/products, so another account's
receipt is insufficient. Do not record a missing monetary amount as zero.

Final monetary acceptance needs original-owner reservation/settlement, durable
dispatch-correlated usage, physical/shared-account treatment across models and
consumers, and holds that survive unknown effects. A capacity cooldown is not an
economic hold: it can expire and allow a probe.

## Acceptance journey

| Step | Required original-owner evidence |
| --- | --- |
| Role/admission | Qualified dedicated role/session/principal, grant/entitlement, native admission and original request IDs. |
| Selection | Actual provider, selected AND served model, physical account, applicable shared allowance scope, policy/recipe/configuration and original lease. |
| Primary turn | Real authenticated APPLICATION dispatch through that account, bounded usable native output, observed usage. No provider credential inside Hermes. |
| Tool continuation | Offered native tool ID, exactly one harmless read-only tool execution, original result in the next native request, same original owner/account commitment. |
| Budget denial | Deterministic existing-owner refusal before dispatch at the applicable budget/entitlement limit. Do not consume a real account just to exhaust it. |
| Settlement | Durable original dispatch/request-linked usage and financial interpretation, original reservation/lease/close disposition. |
| Recovery | Original result/unknown-effect readback after a controlled disruption, no second provider submission or duplicate tool effect. |
| AUTO/strict policy | Eligible capability/complexity/latency/headroom/cost selection and strict model/pool refusal before effects, through the incumbent contract. |

Public responses need not carry every financial field if canonical owner
evidence provides exact request-linked readback. Never relabel a model, profile
or capability as a physical account. No synthetic fixture count qualifies as
live usage. Record source/result references without secrets.

