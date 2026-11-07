# Provider plan integration — November 7, 2026

Operation: `provider-plans-byteplus-experiential-20261107-c2`.
Protected source pin: `779fc3be9d07c366bf5b47c650b64e59fc6f3903`.
Parent: [Capacity Fabric #983](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983).
Source plan: [Experiential gateway, P5](../plans/EXPERIENTIAL_FABRIC_GATEWAY.md).
This report distinguishes source qualification, account observations and live execution.

## Implemented and qualified source

- The existing gateway enforces opt-in `free_only` and
  `free_and_uncensored` modes before any RPM/slot reservation or upstream send.
- All seven requested free models have exact model/protocol mappings. Chat and
  Responses keep five chat models; Jev uses System One; GPT-6 Luna Decisions uses
  Decisions. All free model IDs retain `:free`; no paid spill or automatic retry.
- Paid mode permits exactly DeepSeek V4.1 Flash Uncensored and GLM 5.3 Flash
  Uncensored. The declared new-selection preference is DeepSeek first. The
  gateway does not select models or override the incumbent router.
- The Attempt-owned consumer binds the plan policy digest into its route
  generation and sends it to the existing gateway. Drift/missing policy fails
  before admission. Legacy routes preserve their prior identity.
- Paired null key limits now remain null; malformed/partial nulls still fail.
  This fixes the actual supplied key's valid metadata without minting capacity.
- BytePlus's existing readback projection now supports an opaque owner-issued
  subscription reference and a bounded freshness evaluation. Any one of the
  three windows can report exhaustion. Expired-reset or stale/future observations
  remain unknown. Rounded percentages never become request counts/concurrency.
- Additional API keys share a subscription's scope. Additional subscriptions
  need distinct enrolled identities and actual concurrency proof.

Focused local qualification on the registered M2 worktree:
**289 passed, zero skipped** in 34.13 seconds after installing the declared
OpenAI SDK dependency into an isolated temporary virtual environment. The earlier
system-Python run was 281 passed / 7 skipped; the SDK run resolved those skips
and includes the added policy-header client test. Command:

```sh
python3 -m pytest --noconftest -o addopts='' -q --tb=short \
  tests/test_experiential_plan_policy.py \
  tests/test_experiential_account_metadata_proxy.py \
  tests/test_experiential_systemone_gateway.py \
  tests/test_experiential_proxy.py \
  tests/test_experiential_harness_endpoint.py \
  tests/test_subscription_catalog_byteplus_readback.py \
  tests/test_subscription_harness_bindings.py
```

Tests use local/mock upstreams and fixture credentials. They do not prove a
provider inference, native lease, installed generation or production acceptance.
SDK-dependent cases completed in the isolated SDK-enabled run.

## Actual account observations

Only read-only requests were made to the documented Experiential origin. The
supplied credential authenticated for `/api/whoami`, `/api/v1/key`,
`/api/v1/credits` and `/v1/models` (HTTP 200).

- Credential is an **inference key**, `is_provisioning=false`.
- Key's daily USD restriction: `limit=null`, `limit_remaining=null`.
- Credits API's **USD** totals: 46.0 credited, 8.768133843 used,
  **37.231866157 USD** wallet difference. Pending reservations were not measured.
- This is not proof of the claimed $200/month subscription allowance or the
  current remaining 7,000 daily free credits. Those are Chairman-declared plan
  expectations pending account-level readback.
- Authenticated catalog included all seven requested base slugs and both paid
  Uncensored slugs. Public model detail confirms GPT-6 Luna Decisions is
  `POST /v1/decisions`, not chat/streaming.
- Daily usage read initially returned 422 naming missing `org_id`. One request
  corrected that schema using the same authenticated organization; it returned
  400. No daily balance was inferred. This is a request error, not an auth-denial
  claim; no unchanged request loop was performed.
- The connected-browser bootstrap timed out. No dashboard session or budget
  control was observed.

Credentials were handled only in short-lived process stdin/memory for these
reads. No key was committed, placed in a worker packet, installed in a live
service, or disclosed in this report. No billable/provider inference was sent.

## Preserved owners and remaining live gates

1. **Incumbent native composition:** PR #2175 and its original Studio/native
   release effects remain with the active writer. This change does not edit its
   lease broker, launcher, publication, rollout or current-generation files.
2. **Experiential installation:** no loopback gateway was listening on M2 port
   8311; installed native registry contained no enrolled Experiential/BytePlus
   pool. Installation must use the existing gateway and Attempt consumer, then
   the existing broker/ledger. No parallel queue or quota database was added.
3. **Paid budget:** before enabling paid mode, the existing account/budget owner
   must verify the monthly boundary. The supplied inference key cannot administer
   it. Use an authorized account-dashboard session or the provider's provisioning
   control; never relabel wallet money as a monthly allowance.
4. **Old holds:** Account A's HTTP403 hold, Account B's original $1/day restriction,
   `experiential53` manual route and qualification constants remain unchanged.
   New enrollment must establish actual account identity without bypassing those
   holds or treating another key as another organization.
5. **BytePlus:** the $50 personal plan is supported-tool, individual/attended
   scope. Its existing models already include `deepseek-v4.1-flash` and
   `glm-5.3-flash`. Current account-bound quota data, credential-owner enrollment,
   supported harness canary and accepted release are not yet proven. No
   commercial PAYG endpoint substitution or autonomous grant occurred.
6. **Real-path acceptance:** still requires one actually admitted Fabric
   Attempt through the installed gateway/supported harness, canonical quota
   observations, and consumed result. Source tests are not that receipt.

The bounded paid Fabric implementation request
`provider-plan-gateway-policy-20261107-c2` returned
`REQUEST_REFUSED_BEFORE_LAUNCH`, `EXECUTION_NOT_ELIGIBLE`; controller 80807 exited
75. No worker start/result was proven and no retry was issued. Principal
source work continued in the existing registered workspace.

## Primary provider references

- [Experiential errors and free-only contract](https://platform.experientiallabs.ai/docs/errors)
- [Account API and key permissions](https://platform.experientiallabs.ai/docs/account-api)
- [Cost API: wallet units](https://platform.experientiallabs.ai/docs/cost-api)
- [Billing and budget controls](https://platform.experientiallabs.ai/docs/billing)
- [Authenticated model discovery](https://platform.experientiallabs.ai/docs/models)
- [GPT-6 Luna Decisions public model detail](https://api.experientiallabs.ai/api/models/gpt-6-luna-decisions)
- [BytePlus Singapore plan documentation](https://console.byteplus.com/ark/region%3Aap-southeast-1/docs/coding-plan-personal-plan-overview)
- [BytePlus plan FAQ](https://docs.byteplus.com/en/docs/ModelArk/coding-plan-personal-faq)

BytePlus's public FAQ and regional overview disagree on advertised request
estimates; neither number set is used to initialize live capacity.


## Release capability observation

Reading the protected branch rules through the connected GitHub integration
returned HTTP 403, `Resource not accessible by integration`. That denied action
was not retried through another tool/account. The source PR can be published,
but native merge-queue enrollment remains held until the actual enforced rules
can be verified through an authorized control. No review approval, queue entry,
merge or deployment is claimed by this report.
