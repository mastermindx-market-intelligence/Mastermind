# Secretary shared-team access — source consumer

Project [Mastermind #2082](https://github.com/mastermindx-market-intelligence/Mastermind/issues/2082), source [Draft PR #2085](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2085).

This package is a **stateless source-only consumer**, not an installed endpoint, authentication principal, always-on daemon, runtime owner or new control plane. It does not touch the Y7 Elevate Retail Hermes/BYOK harness, authority, credential renewal, source publication or the #1966 NO INSTALL / DO NOT DEPLOY hold.

## Host wiring

The existing installed host enrolls **GB1 and Secretary 2 separately** through its authenticators and grants. Instantiate a **different** `httpx.AsyncClient` for each principal with its own host-owned bearer token/Unix transport and `follow_redirects=False`. The host chooses and pins the service origins. Never share GB1's credential or original COO-only native catalog privilege with Secretary 2.

For each principal construct `SecretaryAccessClient(work_ref="WS:...", root_job_id="JOB-...", workspace=authenticated_workspace_client)`. `coo=` is optional and absent by default; it must be the authenticated existing COO App with the appropriate modifying grant. `ruling=` must be coupled to a host-selected `PrincipalRulingTarget` naming one **existing** pending obligation; it is not arbitrary child steering. All clients, credentials, target, origination, clock and lifetimes are supplied by the incumbent host, **not** the model.

Source APIs:

- `await sdk.read_mission(previous_fingerprint=None, limit=8)`: fixed `GET /workspace/mission/v3/current`, exact host-bound Mission v3 selection and closed bounded summary; invalid/missing/foreign sources fail closed.
- `await sdk.read_project_plan()`: one fixed `GET /workspace/project-plan/current` using only the host-selected workstream, the incumbent v1/v2 canonical validator and 131072-byte wire cap. No caller selector, raw filesystem path or new authorization. This is authored plan evidence, not dispatch authority or a guaranteed root-job plan. The leadership reader can optionally consume a bounded projection.
- `await sdk.read_native_catalog(...)`: fixed `GET /workspace/fabric/catalog/current`, always explicitly `PARTIAL`, `EXACT_RUN_SET`, unknown fleet count; original COO-only entitlement is enforced by the existing server.
- `await sdk.read_native_status(root_id="JOB-...", run_id="ATT-...")`: fixed exact native status read; owner fields preserve execution/acceptance separately.
- `await sdk.mandate()`: fixed `POST /v1/tools/executive_mandate`; an observed mandate never grants a new effect locally.
- `await sdk.submit_intent(canonical_business_request)`: **one** `POST /v1/tools/submit_principal_intent`, normalized by the existing COO source policy. The original `req-coo` reference is computed **before** send and survives malformed/lost responses. `ADMISSION_ACCEPTED` does **not** mean DISPATCHED/STARTED/accepted product.
- `await sdk.reconcile_intent(original_request_ref)`: **read-only logical operation** through the original `POST /v1/tools/principal_intent_status`; no new work.
- `await sdk.rule(public_ruling_arguments)`: opt-in **one** original `POST /mcp/principal-ruling` `tools/call` using the original validated public argument schema, bound target and caller supplied by host. A transport loss yields `EFFECT_UNKNOWN` with the original obligation; no reroute.

No method takes an arbitrary URL, origin, actor, credential, Authorization header, model/provider/host, account, new-obligation ID or retry destination. Responses are bounded and strict JSON (duplicate keys, nonfinite values, oversize and deep shapes refused). Redirects are never followed. Source-invalid READ returns `UNAVAILABLE`; HTTP permission refusal remains `REFUSED`, including observed 401/403 responses whose body is empty, malformed, oversized or interrupted. Modifying response loss, cancellation, malformed post-send status, or an unverified receipt leaves the **original** effect `EFFECT_UNKNOWN`, with `replay_authorized=false`. The host must supply a **non-retrying transport**. Never retry or fail over an unknown effect; use only the incumbent reconciliation path.

## Proven vs outstanding

This package consumes existing Mission v3 and COO/native contracts; the signed two-member real ASGI → Unix → Workspace → Runtime fixture is in `tests/test_secretary_team_mission_http.py`. SDK contract tests cover separate host clients, result/source refusal, fixed paths, exact request identities, mutation loss and bounded ruling.

**Not proven by this source**: actual GB1/Secretary 2 live enrollment, existing owner's full host/pool/model placement receipts, job submission in production, a real ruling, session-reply audience extension, any installed service or background execution, original-parent accepted result consumption, catch-up after reboot, or seven-day token savings. Those require installed host and canonical Runtime/Wake/Agent OS evidence. No synthetic test is a seven-day service receipt. See `docs/GROK_SECRETARY_TEAM_INTEGRATION.md` for the owner-linked handoff and full acceptance ruler.
