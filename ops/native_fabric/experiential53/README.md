# experiential53 — MANUAL-only Experiential Labs GLM 5.3 UNCENSORED (native Fabric)

Isolated, source-only contribution: a NEW provider pool `experiential`
carrying exactly one model slug, `glm-5.3-uncensored` (Experiential Labs
GLM 5.3 UNCENSORED), selectable **only** by an explicit manual pin
(pool=experiential AND model=glm-5.3-uncensored) with a strict transport
re-evaluation before any effect — never ambient auto selection, never a
default promotion, never a fallback, never a cross-model/provider retry.

Base: protected `mastermindx-market-intelligence/Mastermind` master
`910803421beca53ca25145392725ab2d84c7a8e9` (Skillpack v1.0.1). This
directory is entirely NEW files; no incumbent file is modified.

Stack provenance (billing01 corrective child): this generation is stacked
EXACTLY on upstream transport PR #2035 head
`f68b5b25d57c8ca90e3e503b5388d6e292a0fc7b` (itself stacked on the manual-pin
base PR #2031 head `b983bf9fd78e8a11c4ba60c691c6b627b0b5a7f3`). The
transport source author of PR #2035 remains its live writer and was NOT
touched: the corrective delta lives only on this child's own branch, scoped
to the three transport source files in this directory. The vendor
single-attempt/no-fallback gateway routing control from `f68b5b2`
(`gateway.retry` one-dispatch budget + `gateway.routing.allow_fallbacks=false`)
is preserved byte-for-byte.

## Files

| File | Role |
|---|---|
| `experiential_pin.py` | Typed manual-pin law: exact pool/slug pin, distinctness from the canonical Z.AI glm tier, no-default-promotion, no-fallback, and the ordered fail-closed execution admission. Stdlib only; no network, no credential, no storage access. |
| `experiential_transport.py` | The actual opt-in native gateway inference transport: one bounded, non-streaming OpenAI-compatible `chat/completions` POST to the shared loopback gateway (PR #1849 contract). Disabled at source until qualification (`ROUTE_QUALIFIED = False`); every run refuses before any dial. Stdlib only; no env/file credential path; secret-free result/refusal surfaces. Carries a fixed conservative `max_tokens` worst-case output bound (tighten-only), preserves/validates the provider `X-Request-Id` response handle as an opaque reconciliation key, and reports a typed never-invented cost posture (`COST_RECONCILIATION_PENDING` / inline-observation-only; `usage.is_byok` true fails closed). |
| `experiential_exec.sh` | Fail-closed worker scaffold in the incumbent exec-wrapper shape. Every path ends in a typed refusal (exit 78). Zero writes, zero reads of the packet, zero provider contact. |
| `pools.yaml.experiential.poolblock.yaml` | Declarative registry block for the runtime pool registry owner to merge under `pools:`. Not a patch against moving runtime bytes and NOT installed by this child. |
| `test_experiential_pin_contract.py` | Hermetic deterministic contract suite (unittest; also pytest-collectable). |
| `test_experiential_transport.py` | Hermetic mock-localhost suite for the transport: exact frame, one POST, the full fail-closed status/redirect/timeout ladder, proxy-poisoning, secret-free surfaces, and every admission gate through the transport. In-process mock on an ephemeral loopback port; zero provider contact. |

## The law this encodes

* **Distinctness.** `glm-5.3-uncensored` is not Z.AI `glm-5.3` and not
  `glm-5.3-flash`; it can never be assigned to, emitted by, or folded into
  the `glm` pool. The canonical GLM model tier (`model_tier.py`) and default
  task routing are untouched.
* **Manual only.** `auto_selection_verdict` returns `NONE
  experiential_manual_only` for every task class; the registry block carries
  `manual_only: true`, `enabled: false` and an empty `task_class_fit`, so no
  scoring or promotion hook exists. Selection emits no `ESCALATE_TO`.
* **Strict pin.** The pin is validated, then re-validated, before anything
  happens (`selection_rechecked_at_request`), mirroring the incumbent
  preview → recheck → `launch-policy` law; at wiring time the incumbent
  transport recheck remains the final owner.
* **Fail-closed execution.** Ordered typed gates: carrier → slug → task
  class → provider enabled → entitlement → retention acknowledgement →
  sensitive-data opt-in → (proprietary code ⇒ independent code-exposure
  opt-in) → account (A stays `HELD_HTTP403`, never retried; B keeps its
  $1/day cap and, with no authenticated quota readback, has UNKNOWN quota —
  unknown quota is not capacity) → verified gateway route → transport.
  In this generation the transport gate always refuses
  (`EXPERIENTIAL_TRANSPORT_NOT_INSTALLED`): no false admission.
* **Retention & sensitivity.** The provider retains prompt/response even
  after settings are disabled or the account is deleted; spend is
  platform-funded only. Execution therefore requires an explicit retention
  acknowledgement and an explicit sensitive-data disclosure opt-in, and
  proprietary code is never exposed automatically (independent opt-in).
* **No new owners.** No key storage, queue, ledger, router or retry
  authority is created here. The approved shared Experiential gateway
  (PR #1849) and the Attempt-owned consumer/transport (PR #1920) remain the
  only route; the existing provider secret owner keeps custody of the
  upstream key.

## The transport (experiential_transport.py)

The missing piece this generation contributes is the ACTUAL executable
inference transport behind the manual pin — not a second status scaffold:

* **Contract reuse, no duplication.** It speaks the existing shared
  gateway's wire contract (PR #1849): `POST /v1/chat/completions` on
  loopback with the host-managed proxy token as `Bearer`, `stream: false`,
  and the run id as `Idempotency-Key` for one logical request. It composes
  the pin law unchanged instead of re-deriving admission, and it names the
  Attempt-owned consumer seam (`control_plane.experiential_harness_endpoint`,
  PR #1920) with an explicit probe/refusal (`EXPERIENTIAL_ATTEMPT_SEAM_UNAVAILABLE`)
  while that PR is unmerged — never a shim.
* **Disabled at source until qualification.** `ROUTE_QUALIFIED = False` is an
  immutable module constant, the transport-side twin of the pin's
  `TRANSPORT_INSTALLED`. Every run refuses
  `EXPERIENTIAL_GATEWAY_ROUTE_UNQUALIFIED` before any dial; the constant is
  never an argument. Flipping either constant is an owner source attestation
  on a qualified host, and the mock suite proves behaviour by patching them
  in-process only.
* **Transport laws (all typed, all mock-tested).** Pinned numeric
  `127.0.0.1` host (a name cannot re-resolve a bearer request off loopback);
  `http`/owner-qualified `https` loopback scheme only; exact `/v1` base path
  and `/v1/chat/completions` dialled path; `ProxyHandler({})` opener so no
  ambient `http(s)_proxy`/`all_proxy`/`trust_env` value is consulted; any 3xx
  refused and never followed; exactly one POST — no retry, no key rotation,
  no cross-account or cross-route fallback, and `Retry-After` observed but
  never obeyed. The vendor's *internal* waterfall is also restricted by an
  exact `gateway.retry` one-dispatch total/per-route budget and
  `gateway.routing.allow_fallbacks=false` in the JSON request body. SDK
  no-retry alone would not prevent hidden vendor generation retries. No
  unverified `route_id` or alternate org is invented; original provider
  eligibility remains binding. Bounded prompt/system chars, 1 MiB encoded request cap,
  8 MiB response cap, bounded timeouts; every non-200 refused with a status
  class (401/403 auth, 413 body, 429 rate limit, 503/504 local queue, other
  4xx/5xx, and 204 never silently accepted as empty success); a 200 must be
  JSON with non-empty `choices` and content, and a substituted `model` echo
  is refused (`GATEWAY_RESPONSE_MODEL_MISMATCH`).
* **Bounded worst-case output (billing01).** Every admitted frame carries a
  fixed conservative `max_tokens` (module constant `MAX_OUTPUT_TOKENS = 512`
  — ample for bounded fix_build-class packet work, small enough to cap the
  billed exposure of any single request, including one that fails or
  disconnects mid-generation, which the vendor documents as possibly still
  charged). A caller may tighten the cap per request
  (`max_output_tokens=64`); nothing can loosen it — the constant is the
  ceiling, never a runtime flag or route field
  (`MAX_OUTPUT_TOKENS_INVALID`).
* **Provider reconciliation handle (billing01).** The provider/gateway
  `X-Request-Id` RESPONSE header is captured, validated against a strict
  bounded printable-ASCII shape (1–128 chars, log-safe by construction) and
  surfaced on the outcome/summary as an opaque, non-secret reconciliation
  key that is distinct from the locally sent `Idempotency-Key`. Missing is
  typed `PROVIDER_REQUEST_ID_MISSING`; a malformed value is discarded and
  typed `PROVIDER_REQUEST_ID_MALFORMED`, never surfaced or logged raw. A
  validated handle on a FAILED post rides the typed refusal detail (vendor
  law: failed/disconnected requests may still incur charge, so the billing
  owner can reconcile even refused POSTs). Settlement belongs to the
  EXISTING billing owner via `GET /api/v1/generation?id=<x-request-id>` /
  the settled org-scoped usage export — this module never dials either.
* **Cost is never invented (billing01).** Per the Experiential Cost API
  law, any request carrying an `Idempotency-Key` is deliberately NOT
  annotated with `usage.cost`, so per-request cost is UNKNOWN at transport
  time. The outcome therefore reports `COST_RECONCILIATION_PENDING` unless
  a type-safe inline `usage.cost` observation exists
  (`COST_RECONCILIATION_OBSERVED_INLINE` — explicitly an inline observation,
  `cost_settled` is `False` by law). Zero USD is never synthesized;
  untrusted observations (wrong type, negative, non-finite, beyond the
  typed sanity bound) are recorded PENDING, never surfaced as a figure; no
  ledger write, no charge, no provider query. `usage.is_byok` true fails
  the request closed (`COST_BYOK_REFUSED`) for this platform-funded-only
  pool — completion discarded, no retry, no fallback.
* **Exact model echo (billing01).** A present echoed `model` must equal the
  pinned slug byte-for-byte: `GLM-5.3-UNCENSORED`, mixed-case and
  whitespace-padded variants are substituted-model refusals — the incumbent
  case-insensitive fold could accept case variants contrary to exact-slug
  law and no longer does.
* **Secret-free surface.** The proxy token is host-managed and org-scoped,
  supplied per-forward by trusted host composition — this module has NO
  environment or file credential path (it does not even import `os`), and a
  provider `xpl_` key is refused outright (`PROVIDER_KEY_REFUSED`). The token
  is excluded from `repr`/results/summaries/refusal details; refusal details
  carry metadata only, so they are log-safe. Rejected model values and
  Content-Type headers contribute only bounded expected-model/content-type
  metadata; their raw values never enter reason, detail, str or repr.
* **Per-request acks.** Retention acknowledgement, sensitive-data disclosure
  opt-in and the independent proprietary-code opt-in are re-validated by the
  pin admission on every call — nothing cached, nothing implied. Account A
  stays `HELD_HTTP403`; account B keeps the $1/day cap and, without an
  authenticated readback, has unknown quota = no capacity.
* **Packet identity preserved.** `run_id` and `packet_root` are validated,
  carried through unchanged, and returned on the secret-free outcome.
* **Mock proof vs live proof.** `test_experiential_transport.py` (91 tests)
  and the CLI `mockproof` subcommand prove every law above against an
  in-process mock gateway on an ephemeral loopback port with zero provider
  contact. That is SOURCE MOCK PROOF only — not a live provider call, not an
  installed service, not a worker START. `status` (exit 78) reports the
  shipped fail-closed gate state; `route` proves the refusal ladder without
  dialing.

## Custody respected

* `quota_continuity/source/pick.py` and `candidate/pick.py` have a live
  modifying writer (PR #2029) — not touched by this child.
* PRs #1849 (gateway), #1934 (SystemOne), #1945 (metadata), #1920 (Attempt
  SDK), #1918/#1946 (Brain pool/gateway), #1851 (native Jev), #1938
  (inert model alias), #2020/#2022/#2024 (GLM lease / readiness / manual
  diagnostics) — none of their branches or files are touched.

## Returned gaps (outside this child's authority — owners must wire)

1. **Registry merge**: `orch/fabric/pools.yaml` is host runtime state; the
   registry owner merges the pool block (and only then flips
   `enabled: true`) after the qualification below.
2. **Picker wiring**: `experiential` must be added to `_HOST_POOL_MODES`,
   `launch_policy` mode admission, `hard_filter`, and the manual-pin path of
   `_format_pick` in the incumbent `source/pick.py` — fenced by the live
   writer (PR #2029) until that lands.
3. **Transport wiring**: a `experiential` mode in `remote_sub.sh`/`sub.sh`
   mapping to this exec wrapper, plus `slot.py` cap registration — same
   owners, same fence.
4. **Qualified gateway transport**: the transport SOURCE now exists
   (`experiential_transport.py`) and is fully mock-proven, but it ships
   disabled. An installed, attested loopback Experiential gateway route
   (PR #1849) consumed directly or via the Attempt-owned client (PR #1920),
   qualified on the host, must exist before the transport owner flips
   `ROUTE_QUALIFIED` in source and the pin owner flips
   `TRANSPORT_INSTALLED` — never as runtime flags, and never by this child.
5. **Account B quota readback**: an authenticated $1/day readback does not
   exist; until an owner provides one, execution stays refused regardless
   of any other gate.

## Running the tests

```sh
python3 ops/native_fabric/experiential53/test_experiential_pin_contract.py
python3 ops/native_fabric/experiential53/test_experiential_transport.py
# or: pytest ops/native_fabric/experiential53/ --basetemp <dir>

# zero-network gate report (exit 78 while fail-closed) and the hermetic
# loopback mock proof (no provider contact):
python3 ops/native_fabric/experiential53/experiential_transport.py status
python3 ops/native_fabric/experiential53/experiential_transport.py mockproof
```

No test contacts a provider, reads credentials or the runtime registry, or
writes outside a temporary directory. Transport tests dial only an in-process
mock gateway bound to an ephemeral `127.0.0.1` port.
