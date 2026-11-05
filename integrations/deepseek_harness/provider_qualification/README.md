# DSH sealed-analysis compatibility fixture

This is HC-P2.T0 source preparation for [Mastermind #1841](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1841).
The task and remaining wave gates are pinned in [Macro #10167](https://github.com/mastermindx-market-intelligence/macro/pull/10167).

The supported claim is **SOURCE_CONTRACT_QUALIFIED / FIXTURE_ONLY**, after the real
donor test succeeds. This directory does not install a model route or admit a Job.

## Why this boundary exists

DSH's native model API accepts rich conversation history, tools, attachments,
auxiliary calls and streaming. The existing canonical paid GLM profile accepts
one sealed text request, with stream=false and a fixed output limit. Its private
capability issuer is owned by the existing Control start and paid Fabric backend.
Changing a provider URL in DSH does not establish that ownership.

This fixture implements the compatible one-shot text subset and rejects unsupported
requests before native DSH projection can turn attachments or history into text.
It helps qualify the join while retaining the live route's actual admission gap.

The Python test uses the incumbent compile_request() and descriptor() from
control_plane/paid_model_execution_contract.py. It also uses the incumbent
paid_glm_model_client.py validate_body() and result_bytes() functions. The JavaScript
module checks consistency of those supplied fixture vectors; it does not implement
another compiler, issuer, validator of authority, or provider client.

## Behavior

| Input or event | Observed behavior required by the tests |
|---|---|
| One identity-free user text message matching the compiler vector | Exact compiled body reaches one local fixture callback; its complete result is projected through the real DSH runtime and assembler |
| Two canonical model identifiers | Requested route and body model match; the model label does not attest which model served a live request |
| System input, tools, tool history, session identity, multiple messages, image/file/tool blocks, auxiliary purpose or unsupported model controls | Refused before the callback |
| Changed prompt, descriptor, model, request bytes or result digest | Refused; no alternate model, route or reconstruction |
| Prepared call reuse or changed prepared configuration | Native DSH prepared-call checks remain in force |
| Simulated 429, timeout, ambiguous transport failure or authentication failure | One callback attempt, captured normal retry policy with maxRetries=0, no replacement attempt |
| Pre-abort, abort during an unsettled callback, abort between chunks, or consumer stop | No successful finish; pre-abort performs no callback |
| Partial, tool-shaped, wrong-body, truncated or widened result envelope | No text content is emitted |
| Missing usage, served-model or account evidence | Remains absent; no zero token count or invented attestation |

The emitted text chunks project an already complete buffered fixture result. They
are not evidence of provider streaming. A terminal DSH stop is only a successful
local text projection; it is not schema acceptance, Executive acceptance, review
acceptance or original-parent consumption. Consumers must observe the explicit finish
chunk; an assembler's default finish value after a partial iterator is not completion proof.

## Native execution and lifecycle

prepareSealedAnalysisFixture() takes the actual donor LlmRuntime, LlmAdapter,
LlmError, resolveRetryPolicy and Cordis Context modules as dependencies. It creates
one disposable private Context and one native prepared call. There is no default
plugin registration, production loader, endpoint configuration, credential lookup,
lease request, capsule minting, network transport, persistent service or background
work in this directory.

The caller supplies a local readFixture callback and an inert vector. A callback is
ordinary caller-owned code, not a grant or sandbox. The supported fixture callback
returns complete text already validated by the Python oracle. This interface must
not be relabeled as an admitted live transport.

The immutable native provider retry policy explicitly pins maxRetries=0. The donor
normally defaults to five retries; merely disabling retries in an underlying SDK
would leave the enclosing DSH policy unresolved. Native Cordis fiber disposal runs
after completion, failure or iterator close.

## Reproduce

Use an existing clean, installed full-app donor checkout at exactly:

    deepseek-ai/deepseek-harness
    687f282e8625c6b8d11ff58211a90524be2e4317

The fixture imports packages/llm/llm/src/index.ts from that checkout through its
installed tsx loader and uses its installed Cordis dependency. It does not copy,
modify, install or rebuild donor code. The dependency installation/build must be
qualified separately; the receipt hashes the exercised LLM source entry points
and the loaded built Cordis module, not the entire dependency closure.

From the Mastermind repository root:

    MMX_DSH_DONOR_ROOT=/absolute/path/to/the/pinned/donor \
      python3 -m unittest tests.test_meta_ceo_dsh_provider_contract -v

Regression dependency:

    python3 -m pytest tests/test_paid_model_execution_contract.py -q

The wrapper checks the donor Git pin and clean tracked state before execution and
again checks tracked state afterward. It feeds Python-generated vectors to the Node
test through stdin and reports the actual Node test totals, exercised source hashes
and the fixture-only ceiling. Test input uses invented fixture identities and no
real account, lease, capability or credentials.

If MMX_DSH_DONOR_ROOT is absent, the native integration test reports an explicit
skip with "actual DSH proof NOT RUN". A skipped CI test does not satisfy this gate.
No source claim should be promoted without the non-skipped donor receipt.

## Remaining owner work

HC-P2 still requires an independently accepted incumbent-owned route compatible
with the intended DSH request surface, actual admission and lease/controller
binding, live provider identity and metering, cancellation/failure observations,
and downstream original-parent consumption where applicable.

The current canonical model-only profile does not authorize a DSH tool loop.
Do not widen its body, encode prohibited tool authority into a sealed prompt,
borrow another worker's capability, or use an older native-worker route as an
implicit new grant. A future live consumer must bind its actual Attempt through the
existing Control/Capacity/Fabric owners and preserve the current replay rules.

HC-P1 authenticated UI proof, the Rakazo comparison, independent fleet review,
production release, the real 24-hour continuity canary and seven-day evaluation
remain separate gates. This task does not modify their original carriers.

## Source references

- [Canonical sealed-input compiler](../../../control_plane/paid_model_execution_contract.py)
- [Incumbent paid Fabric backend](../../../control_plane/paid_fabric_backend.py)
- [Canonical lease gateway](../../../ops/native_fabric/paid_canonical_glm/candidate/glm_lease_gateway.py)
- [Model-only client and result parser](../../../ops/native_fabric/quota_continuity/candidate/paid_glm_model_client.py)
- [Pinned donor LLM runtime](https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/packages/llm/llm/src/index.ts)
- [Pinned donor retry policy](https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/packages/llm/llm/src/retry-policy.ts)
