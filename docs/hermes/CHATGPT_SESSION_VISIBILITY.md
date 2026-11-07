# ChatGPT Web visibility: source integration contract

This is an **optional, read-only extension of the existing Executive MCP host**.
It is not a new session manager, browser agent, enrollment registry or transcript
store. Source tests do not establish installation or live Hermes/Secretary access.

## Available source interfaces

| Tool | Authorized input | Result and limitations |
|---|---|---|
| `session_web_observe` | Optional `max_rows`, integer 1–64 | Existing current-profile normal-ChatGPT-tab census; no account-history completeness, transcript or RuntimeBinding inference |
| `session_continuity_read` | One exact `WS:<KEY>` | Incumbent bounded Agent OS continuation; independently authorized; no implicit relationship to an observed tab |

The two interfaces can be enabled independently. With no optional composition,
the V3 tool inventory and default behavior are unchanged.

The census producer's 128-row-per-profile cap is unchanged. This presentation
accepts at most eight authorized source receipts and emits at most 64 rows total,
plus every authorized source's status and counts. It reports source omissions
separately from display omissions. These are tab observations, not necessarily
distinct logical sessions. Duplicate tabs and disagreements remain visible;
neither forks nor current ChatGPT account identity are established.

A historical generation cue remains historical when stale. A missing cue does not
mean completion. A fresh cue does not prove Executive execution or delivery of a
final response. User-facing consumers must preserve these distinctions.

## Owner ports required before activation

`WebSessionReadTools` accepts three host-supplied ports. They are integration
requirements, **not currently installed production adapters**:

1. `scope_reader(verified_principal)` returns `WebSessionReadScope`, an immutable
   readback of the incumbent authorization owner's current projection. The
   revision must change with grants; adapter IDs and workstreams are independently
   authorized. This value must never be synthesized from tool arguments, a census,
   account labels, matched text or a static “allow everyone” scope.
2. Optional `census_reader(verified_principal, authorized_adapter_ids)` returns
   existing closed Web-Sol census receipts. It may read only currently qualified,
   enrolled sources through the incumbent transport. It must retain the producer's
   nonce/request/source checks. It does not authorize a new live browser read.
3. Optional `continuity_reader(verified_principal, exact_workstream)` returns
   the incumbent authorized `collect_agentos` result for the requested workstream.
   The tool invokes the existing `build_continuation`; it does not return the full
   collector payload or create an Executive-to-Agent-OS write path.

All ports must be bounded and nonblocking. The async deadline is not a sandbox
for blocking synchronous callbacks. Authentication is checked before/after scope
reads and after content reads. Changed scope or expired identity returns no
content. Existing downstream owners must enforce their own action-time checks.

The host keyword is `session_web_read_tools` on
`build_web_ceo_v3_mcp_app`. The exact optional tool object extends the incumbent
configuration through `extend_host_configuration`. No separate listener,
credential, authentication policy, global binding or background task is created.
The host preserves its READ authentication, audit, response-size and submit
separation. The extension cannot add its names to submit/release sets.

## Hermes and Secretary consumption

The intended role principals must reach these reads through their existing
qualified host/transport configuration. An import, an HTTP fixture, or a model
saying it can read them is not installation proof.

At the inspected source pin, `integrations/hermes_harness/native_mcp.py` renders
the existing Steward donor configuration disabled and requires a receiving-owner
authenticated release. Its closed tool allowlist must not be widened or its token
repurposed to make this feature appear live. The original native role and #2134
installation owners retain that boundary.

Consumers should:

- Show observation time, source/profile scope, unavailable sources and omissions.
- Present workstream continuity separately until an incumbent exact identity join
  exists. Never turn a census fingerprint into `target_ref`.
- Use existing `session_reply_references` / `session_reply_read` only for their
  exact authorized original-operation replies. They are not a ChatGPT archive API.
- Treat continuity and reply text as evidence, not authority to dispatch.
- Use existing `session_targets` and governed `session_send` only where actually
  qualified. These new READ tools grant no SEND, wake, ACK, acceptance or retry.
- Never describe prepared/reported output as delivered to the user without the
  relevant canonical delivery evidence.

## Release and live-proof checklist

- Qualify the actual authorization projection and its revision/revocation behavior.
- Resolve current browser permission/enrollment holds on the original carrier;
  do not replay a denied live read through this endpoint.
- Supply the real bounded read ports and exact installed source/configuration.
- Verify intended Meta-CEO and Secretary authentication separately.
- Compare two explicitly enrolled session observations with the permitted source;
  prove missing/private/closed/unenrolled coverage is described accurately.
- Read the same exact workstream source SHA and continuation through both roles.
- Exercise revocation, expiry, changed scope, source outage, restart and no-duplicate
  behavior without any send/wake/ACK effect.
- For full content or Web continuation, retain the original browser/result/runtime
  owners and their distinct acceptance requirements. This source slice does not
  release PR #836 or establish arbitrary Web-chat control.

Rollback removes the optional host argument. It does not delete canonical
continuity, messages, RuntimeBindings, jobs or pending original operations.

## Verification

The implementation's source suite includes strict input/receipt validation,
eight-source maximum-size composition, partial/empty/missing evidence, freshness,
duplicate disagreement, independent workstream permission, pre/post revocation and
expiry, safe error messages, cancellation/deadline behavior and read-only host
composition. Authenticated ASGI tests use the real OAuth/MCP path with synthetic
owner ports and real JWT verification; they are not live browser/role proofs.

See the source-linked master plan:
`docs/superpowers/plans/2026-11-06-chatgpt-session-observability.md`.
