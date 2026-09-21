# Executive Web-CEO Fabric Read Amendment

**Status:** bounded architecture amendment for the Improve Agent Orchestration program.
**Operation:** `web-executive-fabric-view-mcp-20260917-sol-001`.
**Scope:** authenticated Web-CEO Fabric visibility only.

## Ruling

The protected BSC-E1 / EXEC-MCP-A public contract remains the immutable five-tool
Executive MCP generation at server version `1.0.0` and schema digest
`546b4345e30c24363a02ae3d4fc873e17559ffd569cde188a533fb628b284232`.

Web CEO Fabric visibility is **not** an in-place widening of that contract.
It is a separately versioned static profile, `web_ceo_v1`, over the same
Executive auth, App, CeoIngress, Runtime, lifecycle and result-envelope owners.

The Web-CEO profile uses server version `1.1.0`, retains the five legacy tools,
and adds exactly one read-only tool:

```text
executive_fabric
```

Its independently pinned schema digest is
`17e052ed734c2c4606094c49b0e9c057382a193fc181d595fc084da10809a5cd`.

## Why this profile exists

A Web CEO cannot orchestrate responsibly from one-job reads alone. It needs a
truthful bounded view of a parent Fabric root, its child Jobs and Attempts,
review, repair and accepted result without reconstructing lifecycle state from
text, Slack, or worker transcripts.

The canonical derivation owner remains `control_plane.fabric_job_view`.

## Composition law

`web_ceo_v1` creates no new server-side lifecycle or authority. It reuses:

- the existing A1 OAuth/resource policies and audit sink;
- the existing Mastermind Executive App and MCP transport composition;
- the existing dedicated CeoIngress AF_UNIX boundary;
- the existing Executive Runtime Job/Attempt/Event registries;
- the existing `mastermind.executive_mcp_result.v1` response envelope; and
- the existing canonical Fabric projector.

Profile choice is host/source composition, never request input. There is no
dynamic profile selection, dynamic tool registration, alternate queue, raw
provider spawn, second scheduler, or second Runtime.

## Internal reader versioning

The installed App-read frame is versioned explicitly:

- `mastermind.executive_ceo_ingress_app_read.v1`: immutable legacy four-reader
  BSC-E1 profile; it cannot request `executive_fabric`.
- `mastermind.executive_ceo_ingress_app_read.v2`: Web-CEO read profile; it
  admits those four readers plus `executive_fabric`.

`CeoIngressAppBinding` defaults to v1. A host must explicitly bind the v2 read
schema to activate the Web-CEO reader profile. The existing C1 peer, submission
schemas, admission path and submit caller shape are unchanged.

## Capability boundary

`executive_fabric` is visibility only. It does not dispatch, claim, lease,
spawn, cancel, terminate, retry, reassign, resume, wake, merge, deploy, read a
credential, choose a provider, or originate a review.

The first accepted journey is:

```text
authenticated Web CEO
→ existing submit_ceo_intent admission
→ one durable QUEUED Executive Job (dispatched=false)
→ Web-CEO v2 installed read
→ canonical Fabric root projection of that same Job
```

That journey proves truthful orchestration visibility, not execution.

## Production gate

Source acceptance does not install or activate `web_ceo_v1`. Production proof
requires the separately owned installed-read hardening to be accepted, an
explicit host/app generation using the v2 read binding, and one real
authenticated read of current Executive Runtime state. Worker execution remains
separately gated by provider readiness, placement, admission and supervisor
proof.

The older Astra external-delegation freeze remains controlling for its own
five-tool client generation. This amendment does not silently upgrade existing
clients or reinterpret historical production evidence.

## Static bounded-result profile: web_ceo_v2

The additive `web_ceo_v2` profile uses server `1.2.0`, static schema digest
`df6bfc6ead2177f6487a51f4bbc2a5ef660d4d6ab248bee2e727e416d0678975`,
and App-read `mastermind.executive_ceo_ingress_app_read.v3`. The legacy five-tool
and historical `web_ceo_v1` schemas and digests above remain unchanged. Profile
selection stays in host composition; request input cannot choose a profile.

The existing `executive_fabric` tool has three mutually exclusive selections:

- `roots`: optional bounded rendering `limit`; uses the accepted
  `list_roots_v2_from_runtime` producer. One retained discovery observation
  supplies its finalized generation and snapshot digest. Creation provenance
  remains explicitly `PARTIAL`; enumeration performs no creation-Event or
  result-detail fanout. Acquisition unavailability retains the producer's
  explicit unknown generation, unknown total and named degradation.
- `root`: exact `root_job_id`; uses the existing bounded Fabric v2 detail owner.
- `result`: exact `root_job_id`, `job_id`, `attempt_id` and
  `result_envelope_digest`, with no limit, cursor, path, budget or extra field.
  Job IDs are `JOB-` followed by 1–9 digits; Attempt IDs are `ATT-` followed by
  32 lowercase hexadecimal characters; the envelope digest is 64 lowercase
  hexadecimal characters. No whitespace normalization is performed.

The existing reader exposes a host-only, one-time `bind_fabric_source` method.
It stores an inert trusted zero-argument Runtime getter and copied, immutable
public armed/identity facts. Rebinding, binding after the first call and binding
following close are refused. Each physical read evaluates the getter once
inside the existing executor. There is no legacy Runtime factory or path-open
fallback. The parent supplies the actual retained-service getter before
admission and drains the same reader before relinquishing Runtime custody.

A result read selects one bounded canonical result on that retained Runtime,
then obtains the observation receipt after physical close. It verifies the
requested tuple and uses the shared `fabric_result_projection` owner. The
snapshot's non-null observation identity must match the finalized receipt;
`UNKNOWN` never becomes `SAME` through presentation. The canonical envelope
lookup digest remains distinct from the reviewed work's role-result digest.

The permitted result contains structured role result, summary and next actions,
with exact identity, counts and omission metadata. It does not expose raw
provider transcripts, execution-principal material or arbitrary file contents.
A review describes only its selected reviewed Job/Attempt/digest; latest-revision
currentness remains `UNPROVEN`, and acceptance is `NOT_PROJECTED`.

The complete CeoIngress success wrapper `{ok:true,result:ExecutiveMcpEnvelope}`
plus LF must fit **16,384 actual UTF-8 bytes**, including final profile metadata.
After successful canonical acquisition, presentation overflow selects the shared
`CONTENT_OVER_BUDGET` document with null content and validated counts; the full
fallback wrapper is measured again. Oversized fallback metadata is a typed
refusal. Acquisition-budget failure is an error without result material or
validated counts. Generic preview conversion is not used for result content.

The actual escaped MCP JSON-RPC/TextContent transport retains its independent
**256 KiB cap** and its existing maximum-request-ID reservation. The full MCP
wire is not advertised as 16 KiB. Legacy/global framing limits are unchanged.

The existing company-read JWT authenticator verifies before invocation and again
before response release for this new profile. The same immutable principal must
be verified twice. A token that expires during acquisition is denied and the
acquired material is discarded. This is company-read permission, not a per-root
ACL or a new dynamic revocation authority.

Focused tests cover the actual JWT → App-read v3 socket → retained Runtime
result path, the six-node review/repair lineage, exact tuple refusals, bounded
roots without Event fanout, one getter per read, immutable binding and drain,
closed schema parity, legacy digests, exact Unicode 16 KiB boundaries, fallback
remeasurement and actual MCP escaping with a large request ID. Local fixtures
and source acceptance do not establish installation or live provider execution.
Complete oversized findings remain unavailable: no pagination or second result
store is introduced. Parent foundation publication, installed host composition
and the authenticated live first vertical remain separate release gates.
