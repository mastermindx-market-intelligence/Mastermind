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
