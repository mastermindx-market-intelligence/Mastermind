# Native host integration and account acceptance

The implementation runs through the existing Hermes and APPLICATION owners.
This document gives the source composition and concrete activation order. It
does not authorize a new credential store, account ledger, service or retry path.

## Fixed ownership

| Native consumer | APPLICATION profile/lane | Internal credential reference | Relay |
| --- | --- | --- | --- |
| mmsecretary | hermes-secretary | HERMES_SECRETARY_FABRIC_APPLICATION_TOKEN | 127.0.0.2:50142 |
| mmmeta | hermes-meta-ceo | HERMES_META_FABRIC_APPLICATION_TOKEN | 127.0.0.3:50142 |
| Ordinary attended | hermes-attended | HERMES_ATTENDED_FABRIC_APPLICATION_TOKEN | 127.0.0.1:50142 |

The attended row is the distinct relation from the original Macro owner. It
uses workload `hermes_attended`; the two role rows use `site_interactive`.
Published a577 keeps all five Hermes fixed/AUTO descriptors source-disabled.
The exact [source-support proposal](qualification/application_owner_support/README.md)
supplies their missing support declarations through that same owner; adoption
is pending. Source support alone does not enroll a service: the existing
qualification, capability, internal credential and admission checks still apply.
Neither a role credential nor the ordinary default Hermes profile substitutes
for the attended identity.

The numeric addresses preserve the existing Linux role network isolation.
All three APPLICATION remotes, including the original 127.0.0.1:50142, use the
same incumbent tunnel client and native 127.0.0.1:4142 target. No public/provider
endpoint is placed in Hermes.

Source responsibilities:
- Complete adapter/host/tunnel composition: Mastermind #2186, preserving the
  primary #2155 and attended #2166 contributions.
- Existing native enrollment extension: Mastermind #2186, stacked on #2175.
- Existing Macro factory/client declarations: original Macro #10740, including
  its incorporated #10818 repair and dedicated attended relation. #10832 adds
  qualification evidence without replacing that production owner.
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

The ordinary attended path instead uses the existing gateway admission and
the registered attended plugin. Its native core patch preserves the
`source=host_bound` marker through both gateway projections, outside constructor
kwargs. A marked route must pass the native profile/runtime checks and claim
its original admission before binding the attended APPLICATION factory. The
role-host paths above remain unmarked and do not consume an additional claim.
The ten-file patch and its exact pre/postimages are in `hermes_core/`; the plugin
does not patch the running checkout.

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
APPLICATION purpose, the role-specific workload, lane, enabled state and the
original internal credential reference. Secretary and meta-CEO retain
`site_interactive`; the dedicated attended relation uses `hermes_attended` in
both service scope and grant. The original accounts parser validates
models/accounts/grant overlap. The original operation owns token generation,
private binding, account publication and recovery.

For a fresh Secretary or meta-CEO role, enroll its intended authorized scope
once. The fixed factory can run the first strict Go canary; later legitimate
new turns can use AUTO with that exact scope. The current attended relation is
fixed-only; it must not inherit a role's AUTO transport or grant. A completed
fixed slot cannot be rewritten into routed form.
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

The [real binary protocol receipt](qualification/chisel_protocol_receipt.json)
qualifies Chisel v1.12.0 on a finite unprivileged Linux loopback fixture. Atomic
authfile replacement refreshes new reverse-client admission and new forward
channels on an existing authenticated SSH connection. It does **not** revoke an
already-open reverse listener or an accepted stream. The original client stop
below is therefore required before ACL replacement; reload alone is insufficient.
The receipt separately records the existing M2 and Ubuntu1 binary digests and
upstream source revision. It does not attest a production M2-to-Ubuntu1 session,
the original server fingerprint, or the root-qualified activation receipt.

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


## Ubuntu1 local application hop through the existing home client

The v2 reverse listeners above exist on the VPS. A role service on Ubuntu1
cannot reach them by opening its own loopback address. Complete that local
hop with the **existing** mm-chisel-home.service after the original v2
server grant and reverse listeners are qualified.

The fixed home successor preserves its existing SSH reverse and appends:

| Ubuntu1 listener | VPS destination | Added ACL on the existing home identity |
|---|---|---|
| 127.0.0.2:50142 | 127.0.0.2:50142 | ^127\.0\.0\.2:50142$ |
| 127.0.0.3:50142 | 127.0.0.3:50142 | ^127\.0\.0\.3:50142$ |

Normal-forward ACLs authorize the destination without an R: prefix. The
APPLICATION reverse identity remains unchanged. The home credential stays
in its original `/etc/chisel/mm-home.env`, owned by the existing `longr`
account resolved by name, with mode `0600`. The carried bundle contains only its digest. The VPS owner
must find exactly one existing matching key; it cannot create or rotate one.

Use the existing application_tunnel_control.py owner from the qualified
protected release:

1. stage-home validates the source/seal, original home launcher/unit/process,
   original credential file identity, exact binary/fingerprint qualification
   and carried v2 predecessor-server-receipt. Its v3 qualification additionally
   requires normal_remote_destination_acl and simultaneous_home_forwards.
2. Carry its fixed home-client/server-bundle.json to the original VPS carrier.
   apply-home-server retains the original role journals, verifies the complete
   authfile preimage and same server process, and requires all three reverse
   listeners to remain attributable to that server. It adds only the two
   normal-destination ACLs. This additive grant needs no M2 client stop.
3. Carry the resulting nonsecret receipt back to the same Ubuntu1 operation.
   apply-home-client --server-receipt publishes only the existing launcher.
   The unit and credential remain untouched. Its separate publication intent
   precedes the write; matching bytes alone cannot adopt another writer's file.
4. After preserving the independent control return path, restart-home-client
   verifies the original effective unit/process/credential, executable launcher
   custody and absence of active consumer streams, then records and issues
   **one** restart of mm-chisel-home.service. It never runs daemon-reload.
   Existing NeedDaemonReload state is retained rather than silently adopting
   unrelated unit changes.
5. reconcile-home-server and reconcile-home-client recover the same original
   operation. A missing acknowledgement is not permission to repeat an ACL
   write, launcher write or restart. RESTART_UNRESOLVED remains held; the
   command is not reissued even when a previous return explicitly failed.

Both Linux phases reuse the existing /etc/chisel/application-tunnel purpose
lock and private publication machinery. The home client uses home-client;
the VPS uses operation-hermes-home. These are fixed phases beneath the
incumbent owner, with no new client, relay service, credential registry or
arbitrary endpoint/port/unit selector.

The [home protocol receipt](qualification/home_forward_protocol_receipt.json)
records a real v1.12.0 binary test across **three separate network namespaces**:
a synthetic native application, the VPS, and the home host. Both local aliases
reached the application once; removing normal-forward permissions denied new
requests while retaining the synthetic SSH return, and restoring them worked
on the same authenticated connections. The test uses an internal Docker
network, no host ports, disposable credentials and a synthetic SSH backend
on port 22220. It proves protocol/topology behavior, not a production SSH login,
TLS deployment, native APPLICATION admission or a provider result. All owned
containers, the network and synthetic credentials are removed after the proof.

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
   native/Hermes/tunnel lifecycle owners. For Ubuntu1, complete the original
   v2 reverse and fixed home-forward successor before the role service can use
   its own .2/.3 loopback APPLICATION address.
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

The [current provider documentation](https://opencode.ai/docs/console/go)
distinguishes included allowance from Extra Usage and documents different
defaults for Go Teams. Teams service accounts are not covered by that plan;
the upstream account type must therefore be verified. A Mastermind internal
service identity does not establish the upstream provider account type. Current
[inference documentation](https://opencode.ai/docs/console/api/inference/)
describes a newer endpoint and separate cost, billing-source and allowance
fields. Qualify the actual installed endpoint; do not silently migrate it or
equate allowance consumption with billed USD. The original Go APPLICATION
transport already emits its identifiable User-Agent and a stable provider
session derived from the admitted lease, across all tool steps. Hermes adds no
provider-selected header or alternate session owner.

The existing owner must bind this policy to the original request/admission.
Hermes must not assert it via prompt text, headers or model arguments. The
declared quota scope can join multiple accounts/products, so another account's
receipt is insufficient. Do not record a missing monetary amount as zero.

For this one included-plan canary, the authoritative hard spending boundary and
the original Broker's durable per-dispatch SQLite token-usage settlement can
satisfy budget and usage acceptance. A new general USD reservation feature is
not a prerequisite. Preserve any stricter applicable existing account or service
budget; a prepaid balance without a verified hard no-overage boundary is not
enough. Report monetary cost as unknown when no qualified cost receipt exists.
Provider [request-start budget checks](https://opencode.ai/docs/console/budgets/)
can permit in-flight overshoot; a displayed budget alone is not proof of a
strict no-overage ceiling. This qualification uses the applicable existing
owner receipts and policy, not a new runtime finance payload or ledger.

On-demand or broader pooled rollout still needs its applicable original-owner
budget admission and settlement, accurate physical/shared-account treatment and
holds across uncertain effects. Optional JSONL/spend-report defects remain
separate known limits. A capacity cooldown may expire and permit a probe; it
cannot stand in for a required unresolved economic hold. Missing price evidence
alone is not proof that the provider request itself has an unknown outcome.

## Acceptance journey

| Step | Required original-owner evidence |
| --- | --- |
| Role/admission | Qualified dedicated role/session/principal, grant/entitlement, native admission and original request IDs. |
| Selection | Actual provider, selected AND served model, physical account, applicable shared allowance scope, policy/recipe/configuration and original lease. |
| Primary turn | Real authenticated APPLICATION dispatch through that account, bounded usable native output, observed usage. No provider credential inside Hermes. |
| Tool continuation | Offered native tool ID, exactly one harmless read-only tool execution, original result in the next native request, same original owner/account commitment. |
| Budget enforcement | Fresh owner evidence of the selected account's hard spending boundary and applicable admission policy, plus deterministic refusal evidence at its entitlement/budget limit. Do not consume a real account just to exhaust it. |
| Settlement | Durable original dispatch/request-linked SQLite usage and truthful financial interpretation, original lease/close and any applicable reservation disposition. |
| Recovery | Original result/unknown-effect readback after a controlled disruption, no second provider submission or duplicate tool effect. |
| AUTO/strict policy | Eligible capability/complexity/latency/headroom/cost selection and strict model/pool refusal before effects, through the incumbent contract. |

Public responses need not carry every financial field if canonical owner
evidence provides exact request-linked readback. Never relabel a model, profile
or capability as a physical account. No synthetic fixture count qualifies as
live usage. Record source/result references without secrets.

